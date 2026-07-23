"""Entry point for the ORB live execution service.

Runs the 7-leg combined longs portfolio:
  NQ NY R11, NQ Asia R9, GC NY R3, ES NY Final, ES Asia Final,
  NQ LDN (G5 gated), NQ NY LSI (LSI 2x)

Usage:
    # Configs with webhooks send live; others are dry-run
    uv run orb-trader

    # Replay historical data for reconciliation
    uv run orb-trader --replay /path/to/NQ_5m.csv --start 2025-01-01

    # Custom config file
    uv run orb-trader --config config/live.toml
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import signal
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from .fees import estimated_commission_per_side

logger = logging.getLogger(__name__)

# Default config path relative to execution/ directory
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "live.toml"

# ---------------------------------------------------------------------------
# Instrument definitions (self-contained — no dependency on backtester)
# ---------------------------------------------------------------------------

INSTRUMENTS = {
    "NQ": {"point_value": 20.0, "min_tick": 0.25, "commission": 0.05, "db_symbol": "NQ.FUT"},
    "MNQ": {
        "point_value": 2.0,
        "min_tick": 0.25,
        "commission": estimated_commission_per_side("MNQ"),
        "db_symbol": "MNQ.FUT",
    },
    "ES": {"point_value": 50.0, "min_tick": 0.25, "commission": 0.05, "db_symbol": "ES.FUT"},
    "MES": {
        "point_value": 5.0,
        "min_tick": 0.25,
        "commission": estimated_commission_per_side("MES"),
        "db_symbol": "MES.FUT",
    },
    "GC": {"point_value": 100.0, "min_tick": 0.10, "commission": 0.05, "db_symbol": "GC.FUT"},
    "MGC": {
        "point_value": 10.0,
        "min_tick": 0.10,
        "commission": estimated_commission_per_side("MGC"),
        "db_symbol": "MGC.FUT",
    },
    "CL": {"point_value": 1000.0, "min_tick": 0.01, "commission": 0.05, "db_symbol": "CL.FUT"},
    "MCL": {
        "point_value": 100.0,
        "min_tick": 0.01,
        "commission": estimated_commission_per_side("MCL"),
        "db_symbol": "MCL.FUT",
    },
    "YM": {"point_value": 5.0, "min_tick": 1.0, "commission": 0.05, "db_symbol": "YM.FUT"},
    "MYM": {"point_value": 0.5, "min_tick": 1.0, "commission": 0.05, "db_symbol": "MYM.FUT"},
    "RTY": {"point_value": 50.0, "min_tick": 0.10, "commission": 0.05, "db_symbol": "RTY.FUT"},
    "M2K": {
        "point_value": 5.0,
        "min_tick": 0.10,
        "commission": estimated_commission_per_side("M2K"),
        "db_symbol": "M2K.FUT",
    },
    "SI": {"point_value": 5000.0, "min_tick": 0.005, "commission": 0.05, "db_symbol": "SI.FUT"},
    "SIL": {"point_value": 1000.0, "min_tick": 0.005, "commission": 0.05, "db_symbol": "SIL.FUT"},
}

# Signal instrument → execution instrument mapping.
# We subscribe to full-size contracts (NQ, ES, GC) for signal data via DataBento
# but execute on micro contracts (MNQ, MES, MGC, MCL) via TradersPost.
SIGNAL_TO_EXEC: dict[str, str] = {
    "NQ": "MNQ",
    "ES": "MES",
    "GC": "MGC",
    "CL": "MCL",
    "YM": "MYM",
    "RTY": "M2K",
    "SI": "SIL",
    # Micros map to themselves
    "MNQ": "MNQ",
    "MES": "MES",
    "MGC": "MGC",
    "MCL": "MCL",
    "MYM": "MYM",
    "M2K": "M2K",
    "SIL": "SIL",
}

# ---------------------------------------------------------------------------
# 5-leg combined longs portfolio session configs
# From COMBINED_LONGS_5LEG_PINE_SPEC.md
# ---------------------------------------------------------------------------

SESSION_CONFIGS = {
    # --- NQ NY R11 (ATR-based stop, Friday exclusion) ---
    "NQ_NY": {
        "orb_start": "09:30",
        "orb_end": "09:45",
        "entry_start": "09:45",
        "entry_end": "12:00",
        "flat_start": "15:30",
        "flat_end": "16:00",
        "stop_atr_pct": 7.0,
        "stop_basis": "atr",
        "min_gap_atr_pct": 2.5,
        "max_gap_atr_pct": 0,
        "gap_filter_basis": "atr",
        "rr": 3.5,
        "tp1_ratio": 0.4,
        "instrument": "NQ",
        "atr_length": 12,
        "long_only": True,
        "icf_enabled": False,
        "excluded_dow": 4,  # Friday (Monday=0..Sunday=6)
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
        "risk_usd": 200,
        "max_single_risk_usd": 300,
    },
    # --- NQ Asia R9 (ORB-based stop, Tuesday exclusion) ---
    "NQ_Asia": {
        "orb_start": "20:00",
        "orb_end": "20:15",
        "entry_start": "20:15",
        "entry_end": "22:30",
        "flat_start": "04:00",
        "flat_end": "07:00",
        "stop_atr_pct": 0.0,  # not used — stop is ORB-based
        "stop_basis": "orb",
        "stop_orb_pct": 100.0,
        "min_gap_atr_pct": 0.0,  # not used — gap filter is ORB-based
        "max_gap_atr_pct": 0,
        "gap_filter_basis": "orb",
        "min_gap_orb_pct": 10.0,
        "rr": 6.0,
        "tp1_ratio": 0.3,
        "instrument": "NQ",
        "atr_length": 5,  # only for warmup, not used in stop/gap
        "long_only": True,
        "icf_enabled": False,
        "excluded_dow": 1,  # Tuesday (Monday=0..Sunday=6)
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
        "risk_usd": 150,
        "max_single_risk_usd": 300,
    },
    # --- GC NY R3 (ATR-based stop, Friday+FOMC exclusion, ICF ON) ---
    "GC_NY": {
        "orb_start": "09:30",
        "orb_end": "09:40",  # 8m ORB → 10m approx on 5m chart (2 bars)
        "entry_start": "09:40",
        "entry_end": "12:00",
        "flat_start": "13:30",
        "flat_end": "16:00",
        "stop_atr_pct": 4.5,
        "stop_basis": "atr",
        "min_gap_atr_pct": 3.0,
        "max_gap_atr_pct": 0,
        "gap_filter_basis": "atr",
        "rr": 9.0,
        "tp1_ratio": 0.35,
        "instrument": "GC",
        "atr_length": 7,
        "long_only": True,
        "icf_enabled": True,
        "excluded_dow": 4,  # Friday
        "fomc_exclusion": True,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
        "risk_usd": 250,
        "max_single_risk_usd": 300,
    },
    # --- GC Asia-1 (ORB-based stop, both directions, regime gate) ---
    "GC_Asia": {
        "orb_start": "20:00",
        "orb_end": "20:30",  # 30m ORB
        "entry_start": "20:30",
        "entry_end": "23:15",
        "flat_start": "04:00",
        "flat_end": "07:00",
        "stop_orb_pct": 25.0,
        "stop_basis": "orb",
        "min_gap_atr_pct": 1.0,
        "gap_filter_basis": "atr",
        "rr": 2.5,
        "tp1_ratio": 0.6,
        "instrument": "GC",
        "atr_length": 14,
        "long_only": False,
        "icf_enabled": False,
        "excluded_dow": None,
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
        "risk_usd": 250,
        "max_single_risk_usd": 300,
    },
    # --- ES NY Final (ATR-based stop, Thursday exclusion, dual floor) ---
    "ES_NY": {
        "orb_start": "09:30",
        "orb_end": "09:45",
        "entry_start": "09:45",
        "entry_end": "13:00",
        "flat_start": "15:50",
        "flat_end": "16:00",
        "stop_atr_pct": 5.0,
        "stop_basis": "atr",
        "min_gap_atr_pct": 0.25,
        "max_gap_atr_pct": 0,
        "gap_filter_basis": "atr",
        "rr": 5.0,
        "tp1_ratio": 0.2,
        "instrument": "ES",
        "atr_length": 7,
        "long_only": True,
        "icf_enabled": False,
        "excluded_dow": 3,  # Thursday
        "fomc_exclusion": False,
        "min_stop_pts": 3.0,
        "min_tp1_pts": 3.0,
        "risk_usd": 250,
        "max_single_risk_usd": 300,
    },
    # --- ES Asia Final (ORB-based stop, ATR-based gap, no DOW excl, dual floor) ---
    "ES_Asia": {
        "orb_start": "20:00",
        "orb_end": "20:15",
        "entry_start": "20:15",
        "entry_end": "03:00",
        "flat_start": "07:00",
        "flat_end": "07:00",  # flat_start == flat_end → instant flat at 07:00
        "stop_atr_pct": 0.0,  # not used — stop is ORB-based
        "stop_basis": "orb",
        "stop_orb_pct": 125.0,
        "min_gap_atr_pct": 0.5,  # gap filter IS ATR-based (hybrid)
        "max_gap_atr_pct": 0,
        "gap_filter_basis": "atr",
        "min_gap_orb_pct": 0.0,
        "rr": 1.5,
        "tp1_ratio": 0.7,
        "instrument": "ES",
        "atr_length": 14,
        "long_only": True,
        "icf_enabled": False,
        "excluded_dow": None,  # no DOW exclusion — trades every day
        "fomc_exclusion": False,
        "min_stop_pts": 3.0,
        "min_tp1_pts": 3.0,
        "risk_usd": 100,
        "max_single_risk_usd": 300,
    },
    # --- NQ LDN (ATR-based stop, G5 gated — skip when Asia hit TP1) ---
    "NQ_LDN": {
        "orb_start": "03:00",
        "orb_end": "03:30",
        "entry_start": "03:30",
        "entry_end": "08:25",
        "flat_start": "08:20",
        "flat_end": "08:25",
        "stop_atr_pct": 1.5,
        "stop_basis": "atr",
        "min_gap_atr_pct": 1.0,
        "max_gap_atr_pct": 0,
        "gap_filter_basis": "atr",
        "rr": 6.0,
        "tp1_ratio": 0.7,
        "instrument": "NQ",
        "atr_length": 10,
        "long_only": True,
        "icf_enabled": False,
        "excluded_dow": None,  # no DOW exclusion; G5 gate applied instead
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
        "risk_usd": 150,
        "max_single_risk_usd": 300,
    },
    # --- SI Asia-1 Short (ORB-based stop, short-only continuation, regime gated) ---
    "SI_Asia": {
        "orb_start": "20:00",
        "orb_end": "20:30",
        "entry_start": "20:30",
        "entry_end": "23:15",
        "flat_start": "04:00",
        "flat_end": "07:00",
        "stop_orb_pct": 75.0,
        "stop_basis": "orb",
        "min_gap_atr_pct": 1.0,
        "gap_filter_basis": "atr",
        "rr": 2.5,
        "tp1_ratio": 0.6,
        "instrument": "SI",
        "atr_length": 14,
        "long_only": False,
        "short_only": True,
        "icf_enabled": False,
        "excluded_dow": None,
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
        "risk_usd": 200,
        "max_single_risk_usd": 300,
    },
    # --- NQ NY Short (ORB-based stop, short-only continuation, regime gated) ---
    "NQ_NY_Short": {
        "orb_start": "09:30",
        "orb_end": "09:55",
        "entry_start": "09:55",
        "entry_end": "11:30",
        "flat_start": "11:30",
        "flat_end": "16:00",
        "stop_orb_pct": 15.0,
        "stop_basis": "orb",
        "min_gap_orb_pct": 2.5,
        "gap_filter_basis": "orb",
        "rr": 2.5,
        "tp1_ratio": 0.4,
        "instrument": "NQ",
        "atr_length": 10,
        "long_only": False,
        "short_only": True,
        "icf_enabled": False,
        "excluded_dow": None,
        "fomc_exclusion": False,
        "min_stop_pts": 10.0,
        "min_tp1_pts": 10.0,
        "risk_usd": 200,
        "max_single_risk_usd": 300,
    },
    # --- NQ Hunter ORB (TradingView Hunter/classic parity leg, MNQ execution) ---
    "H_ORB": {
        "engine_type": "hunter_orb",
        "orb_start": "09:30",
        "orb_end": "09:45",
        "entry_start": "09:45",
        "entry_end": "11:00",
        "flat_start": "15:50",
        "flat_end": "16:00",
        "instrument": "NQ",
        "exec_ticker": "MNQ",
        "atr_length": 14,
        "risk_usd": 350,
        "max_single_risk_usd": 350,
        "max_contracts": 20,
        "long_only": False,
        "short_only": False,
        "excluded_dow": [1],
        "body_min_pct": 55.0,
        "rejection_wick_max_pct": 20.0,
        "sl_buffer_points": 1.0,
        "hunter_target_rr": 2.0,
        "large_sl_threshold_points": 50.0,
        "reduced_target_rr": 1.0,
        "max_hold_minutes": 270,
        "ema15_enabled": True,
        "ema15_length": 14,
        "ema15_source": "close",
        "ema15_tolerance_points": 2.0,
        "ema15_max_distance": None,
        "reentry_policy": "after_each_loss",
        "allow_same_bar_win_reentry": True,
        "same_bar_win_reentry_max_minutes": 5.0,
        "reentry_max_extension_pct": 100.0,
        "enable_fast_reentry_exhaustion_filter": True,
        "fast_reentry_exhaustion_max_minutes": 10.1,
        "fast_reentry_exhaustion_max_extension_pct": 12.0,
        "fast_reentry_exhaustion_min_ema15_distance": 50.0,
        # Compatibility fields for dashboard/reset paths shared with ORBEngine.
        "stop_atr_pct": 0.0,
        "stop_basis": "hunter",
        "stop_orb_pct": 0.0,
        "min_gap_atr_pct": 0.0,
        "max_gap_atr_pct": 0.0,
        "gap_filter_basis": "hunter",
        "min_gap_orb_pct": 0.0,
        "rr": 2.0,
        "tp1_ratio": 1.0,
        "icf_enabled": False,
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
    },
    # --- NQ Hunter ORB 10y-safe stress-gated branch, dry-run research leg ---
    "H_ORB_SAFE": {
        "engine_type": "hunter_orb",
        "orb_start": "09:30",
        "orb_end": "09:45",
        "entry_start": "09:45",
        "entry_end": "11:00",
        "flat_start": "15:50",
        "flat_end": "16:00",
        "instrument": "NQ",
        "exec_ticker": "MNQ",
        "atr_length": 14,
        "risk_usd": 350,
        "max_single_risk_usd": 350,
        "max_contracts": 20,
        "long_only": False,
        "short_only": False,
        "excluded_dow": None,
        "regime_gates": [
            "block_bull_high_vol",
            "block_bear_high_vol",
            "block_bear_medium_vol",
        ],
        "body_min_pct": 55.0,
        "rejection_wick_max_pct": 100.0,
        "sl_buffer_points": 1.0,
        "hunter_target_rr": 2.0,
        "large_sl_threshold_points": 50.0,
        "reduced_target_rr": 1.0,
        "max_hold_minutes": 270,
        "ema15_enabled": True,
        "ema15_length": 14,
        "ema15_source": "close",
        "ema15_tolerance_points": 0.0,
        "ema15_max_distance": None,
        "reentry_policy": "legacy_one_reentry_after_loss",
        "allow_same_bar_win_reentry": False,
        "same_bar_win_reentry_max_minutes": 5.0,
        "reentry_max_extension_pct": None,
        "enable_fast_reentry_exhaustion_filter": False,
        "fast_reentry_exhaustion_max_minutes": 10.1,
        "fast_reentry_exhaustion_max_extension_pct": 12.0,
        "fast_reentry_exhaustion_min_ema15_distance": 50.0,
        # Compatibility fields for dashboard/reset paths shared with ORBEngine.
        "stop_atr_pct": 0.0,
        "stop_basis": "hunter",
        "stop_orb_pct": 0.0,
        "min_gap_atr_pct": 0.0,
        "max_gap_atr_pct": 0.0,
        "gap_filter_basis": "hunter",
        "min_gap_orb_pct": 0.0,
        "rr": 2.0,
        "tp1_ratio": 1.0,
        "icf_enabled": False,
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
    },
    # --- NQ Hunter ORB ablated 2025+ combo, dry-run research leg ---
    "H_ORB_ABLATED": {
        "engine_type": "hunter_orb",
        "orb_start": "09:30",
        "orb_end": "09:45",
        "entry_start": "09:45",
        # Entry end is exclusive; 13:05 allows the 13:00 signal bar.
        "entry_end": "13:05",
        "flat_start": "15:50",
        "flat_end": "16:00",
        "instrument": "NQ",
        "exec_ticker": "MNQ",
        "atr_length": 14,
        "risk_usd": 350,
        "max_single_risk_usd": 350,
        "max_contracts": 20,
        "long_only": False,
        "short_only": False,
        "excluded_dow": [1],
        "body_min_pct": 0.0,
        "rejection_wick_max_pct": 20.0,
        "sl_buffer_points": 1.0,
        "hunter_target_rr": 2.0,
        "large_sl_threshold_points": 50.0,
        "reduced_target_rr": 2.0,
        "max_hold_minutes": 270,
        "ema15_enabled": False,
        "ema15_length": 14,
        "ema15_source": "close",
        "ema15_tolerance_points": 2.0,
        "ema15_max_distance": None,
        "reentry_policy": "all_nonoverlap",
        "allow_same_bar_win_reentry": False,
        "same_bar_win_reentry_max_minutes": 5.0,
        "reentry_max_extension_pct": None,
        "enable_fast_reentry_exhaustion_filter": False,
        "fast_reentry_exhaustion_max_minutes": 10.1,
        "fast_reentry_exhaustion_max_extension_pct": 12.0,
        "fast_reentry_exhaustion_min_ema15_distance": 50.0,
        # Compatibility fields for dashboard/reset paths shared with ORBEngine.
        "stop_atr_pct": 0.0,
        "stop_basis": "hunter",
        "stop_orb_pct": 0.0,
        "min_gap_atr_pct": 0.0,
        "max_gap_atr_pct": 0.0,
        "gap_filter_basis": "hunter",
        "min_gap_orb_pct": 0.0,
        "rr": 2.0,
        "tp1_ratio": 1.0,
        "icf_enabled": False,
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
    },
    # --- GC Gold-X v14.4 reverse-engineered proxy, MGC execution ---
    "GOLD_X": {
        "engine_type": "gold_x",
        "orb_start": "09:30",
        "orb_end": "09:45",
        "entry_start": "09:45",
        # Entry end is exclusive; 13:05 allows the 13:00 FVG signal bar.
        "entry_end": "13:05",
        "flat_start": "16:55",
        "flat_end": "17:00",
        "instrument": "GC",
        "exec_ticker": "MGC",
        "atr_length": 40,
        "risk_usd": 400,
        "max_single_risk_usd": 400,
        "max_contracts": 30,
        "long_only": False,
        "short_only": False,
        "excluded_dow": None,
        "goldx_mode": "both",
        "goldx_classic_risk_usd": 400,
        "goldx_classic_max_contracts": 20,
        "goldx_fvg_risk_usd": 300,
        "goldx_fvg_max_contracts": 30,
        "goldx_classic_weekdays": [0, 3, 4],
        "goldx_fvg_weekdays": [0, 1, 3],
        "goldx_classic_signal_end": "10:45",
        "goldx_fvg_signal_end": "13:00",
        "goldx_enable_classic_proxy_filters": True,
        "goldx_enable_classic_overextension_filter": True,
        "goldx_classic_overextension_max_pct": 60.0,
        "goldx_classic_cooldown_minutes": 50.0,
        "goldx_classic_max_hold_minutes": 180,
        "goldx_enable_fvg_ut_filter": True,
        "goldx_fvg_min_size_points": 9.0,
        "goldx_fvg_max_size_points": 60.0,
        "goldx_fvg_max_orb_distance_points": 30.0,
        "goldx_fvg_target_rr": 2.0,
        "goldx_fvg_min_stop_points": 10.0,
        "goldx_fvg_max_wait_bars": 30,
        "goldx_fvg_max_wait_minutes": 200,
        "goldx_fvg_selection_cooldown_minutes": 5.0,
        "goldx_fvg_after_classic_entry_cooldown_minutes": 10.0,
        "goldx_fvg_max_hold_minutes": 270,
        # Compatibility fields for dashboard/reset paths shared with ORBEngine.
        "stop_atr_pct": 0.0,
        "stop_basis": "gold_x",
        "stop_orb_pct": 0.0,
        "min_gap_atr_pct": 0.0,
        "max_gap_atr_pct": 0.0,
        "gap_filter_basis": "gold_x",
        "min_gap_orb_pct": 0.0,
        "rr": 2.0,
        "tp1_ratio": 1.0,
        "icf_enabled": False,
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
    },
    # --- GC Gold-X SAFE: sparse FVG-only high-PF branch from 2026-05-05 ablation ---
    "GOLD_X_SAFE": {
        "engine_type": "gold_x",
        "orb_start": "09:30",
        "orb_end": "09:45",
        "entry_start": "09:45",
        "entry_end": "13:05",
        "flat_start": "16:55",
        "flat_end": "17:00",
        "instrument": "GC",
        "exec_ticker": "MGC",
        "atr_length": 40,
        "risk_usd": 300,
        "max_single_risk_usd": 300,
        "max_contracts": 30,
        "long_only": False,
        "short_only": False,
        "excluded_dow": None,
        "goldx_mode": "fvg_only",
        "goldx_classic_risk_usd": 400,
        "goldx_classic_max_contracts": 20,
        "goldx_fvg_risk_usd": 300,
        "goldx_fvg_max_contracts": 30,
        "goldx_classic_weekdays": [0, 3, 4],
        "goldx_fvg_weekdays": [0, 1, 3],
        "goldx_classic_signal_end": "10:45",
        "goldx_fvg_signal_end": "13:00",
        "goldx_enable_classic_proxy_filters": True,
        "goldx_enable_classic_overextension_filter": True,
        "goldx_classic_overextension_max_pct": 60.0,
        "goldx_classic_cooldown_minutes": 50.0,
        "goldx_classic_max_hold_minutes": 180,
        "goldx_enable_fvg_ut_filter": True,
        "goldx_fvg_min_size_points": 9.0,
        "goldx_fvg_max_size_points": 60.0,
        "goldx_fvg_max_orb_distance_points": 30.0,
        "goldx_fvg_target_rr": 2.0,
        "goldx_fvg_min_stop_points": 10.0,
        "goldx_fvg_max_wait_bars": 30,
        "goldx_fvg_max_wait_minutes": 200,
        "goldx_fvg_selection_cooldown_minutes": 5.0,
        "goldx_fvg_after_classic_entry_cooldown_minutes": 10.0,
        "goldx_fvg_max_hold_minutes": 270,
        # Compatibility fields for dashboard/reset paths shared with ORBEngine.
        "stop_atr_pct": 0.0,
        "stop_basis": "gold_x",
        "stop_orb_pct": 0.0,
        "min_gap_atr_pct": 0.0,
        "max_gap_atr_pct": 0.0,
        "gap_filter_basis": "gold_x",
        "min_gap_orb_pct": 0.0,
        "rr": 2.0,
        "tp1_ratio": 1.0,
        "icf_enabled": False,
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
    },
    # --- GC Gold-X ABLATED: combined branch with FVG UT proxy disabled ---
    "GOLD_X_ABLATED": {
        "engine_type": "gold_x",
        "orb_start": "09:30",
        "orb_end": "09:45",
        "entry_start": "09:45",
        "entry_end": "13:05",
        "flat_start": "16:55",
        "flat_end": "17:00",
        "instrument": "GC",
        "exec_ticker": "MGC",
        "atr_length": 40,
        "risk_usd": 400,
        "max_single_risk_usd": 400,
        "max_contracts": 30,
        "long_only": False,
        "short_only": False,
        "excluded_dow": None,
        "goldx_mode": "both",
        "goldx_classic_risk_usd": 400,
        "goldx_classic_max_contracts": 20,
        "goldx_fvg_risk_usd": 300,
        "goldx_fvg_max_contracts": 30,
        "goldx_classic_weekdays": [0, 3, 4],
        "goldx_fvg_weekdays": [0, 1, 3],
        "goldx_classic_signal_end": "10:45",
        "goldx_fvg_signal_end": "13:00",
        "goldx_enable_classic_proxy_filters": True,
        "goldx_enable_classic_overextension_filter": True,
        "goldx_classic_overextension_max_pct": 60.0,
        "goldx_classic_cooldown_minutes": 50.0,
        "goldx_classic_max_hold_minutes": 180,
        "goldx_enable_fvg_ut_filter": False,
        "goldx_fvg_min_size_points": 9.0,
        "goldx_fvg_max_size_points": 60.0,
        "goldx_fvg_max_orb_distance_points": 30.0,
        "goldx_fvg_target_rr": 2.0,
        "goldx_fvg_min_stop_points": 10.0,
        "goldx_fvg_max_wait_bars": 30,
        "goldx_fvg_max_wait_minutes": 200,
        "goldx_fvg_selection_cooldown_minutes": 5.0,
        "goldx_fvg_after_classic_entry_cooldown_minutes": 10.0,
        "goldx_fvg_max_hold_minutes": 270,
        # Compatibility fields for dashboard/reset paths shared with ORBEngine.
        "stop_atr_pct": 0.0,
        "stop_basis": "gold_x",
        "stop_orb_pct": 0.0,
        "min_gap_atr_pct": 0.0,
        "max_gap_atr_pct": 0.0,
        "gap_filter_basis": "gold_x",
        "min_gap_orb_pct": 0.0,
        "rr": 2.0,
        "tp1_ratio": 1.0,
        "icf_enabled": False,
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
    },
}

SESSION_CONFIGS["ES_NY_ATH_GATE"] = {
    **SESSION_CONFIGS["ES_NY"],
    "ath_block_min_pct": 0.5,
    "ath_block_max_pct": 0.75,
}


# ---------------------------------------------------------------------------
# LSI reversal session configs — separate from continuation legs
# ---------------------------------------------------------------------------

LSI_SESSION_CONFIGS = {
    # --- NQ Asia LSI (LSI reversal, inversion-bar-close entry) ---
    "NQ_Asia_LSI": {
        "entry_start": "20:40",
        "entry_end": "23:30",
        "flat_start": "04:00",
        "flat_end": "07:00",
        "rr": 2.0,
        "tp1_ratio": 0.7,
        "min_gap_atr_pct": 1.75,  # 1.75% ATR-40
        "min_stop_points": 0.0,  # absolute floor (0 = disabled, matches backtester)
        "fvg_window_right": 2,
        "fvg_window_left": 15,
        "lsi_entry_mode": "close",
        "instrument": "NQ",
        "atr_length": 40,
        "long_only": True,
        "excluded_dow": None,  # no DOW exclusion
        "qty_multiplier": 1.0,
        "risk_usd": 250,
        "max_single_risk_usd": 300,
        "lsi_n_left": 8,
        "lsi_n_right": 2,
    },
    # --- NQ NY LSI (LSI reversal, 2x sizing, fvg_limit entry) ---
    "NQ_NY_LSI": {
        "entry_start": "09:35",
        "entry_end": "15:30",
        "flat_start": "15:50",
        "flat_end": "16:00",
        "rr": 3.0,
        "tp1_ratio": 0.3,
        "min_gap_atr_pct": 5.0,  # 5% ATR-10
        "min_stop_points": 0.0,
        "fvg_window_right": 5,
        "fvg_window_left": 20,
        "lsi_entry_mode": "fvg_limit",
        "instrument": "NQ",
        "atr_length": 10,
        "long_only": True,
        "excluded_dow": [2, 3],  # Wed, Thu excluded
        "qty_multiplier": 2.0,
        "risk_usd": 250,
        "max_single_risk_usd": 300,
        "lsi_n_left": 8,
        "lsi_n_right": 60,
        "lsi_variant": "legacy-LSI",
    },
    # --- NQ NY pure 1m CISD-LSI survivor for order-book velocity sizing ---
    "NQ_NY_LSI_PURE_1M": {
        "entry_start": "09:35",
        "entry_end": "12:00",
        "sweep_start": "09:30",
        "sweep_end": "15:30",
        "flat_start": "15:50",
        "flat_end": "16:00",
        "rr": 2.0,
        "tp1_ratio": 0.5,
        "min_gap_atr_pct": 5.0,
        "min_stop_points": 0.0,
        "stop_atr_pct": 15.0,
        "fvg_window_right": 25,
        "fvg_window_left": 100,
        "lsi_entry_mode": "level_limit",
        "lsi_stop_mode": "atr_pct",
        "lsi_confirmation_mode": "cisd",
        "lsi_variant": "legacy-LSI",
        "instrument": "NQ",
        "atr_length": 10,
        "long_only": True,
        "excluded_dow": None,
        "qty_multiplier": 1.0,
        "risk_usd": 250,
        "max_single_risk_usd": 500,
        "lsi_n_left": 40,
        "lsi_n_right": 300,
        "lsi_reset_swing_window_on_new_day": False,
        "cisd_min_leg_bars": 2,
        "cisd_min_leg_atr_pct": 7.5,
        "cisd_max_leg_bars": 300,
        "base_bar_minutes": 1,
    },
    # --- ES NY HTF-LSI hot-regime dry-run candidate ---
    "ES_NY_LSI": {
        "entry_start": "08:30",
        "entry_end": "14:00",
        "sweep_start": "08:30",
        "sweep_end": "14:00",
        "flat_start": "15:50",
        "flat_end": "16:00",
        "rr": 5.0,
        "tp1_ratio": 0.25,
        "min_gap_atr_pct": 3.0,
        "min_stop_points": 0.0,
        "fvg_window_left": 7,
        "fvg_window_right": 3,
        "lsi_entry_mode": "fvg_limit",
        "lsi_stop_mode": "struct_75pct",
        "lsi_variant": "htf-LSI",
        "instrument": "ES",
        "atr_length": 14,
        "long_only": False,
        "excluded_dow": [2],
        "qty_multiplier": 1.0,
        "risk_usd": 250,
        "max_single_risk_usd": 500,
        "lsi_n_left": 3,
        "lsi_n_right": 3,
        "htf_level_tf_minutes": 60,
        "htf_n_left": 3,
        "htf_trade_max_per_session": 2,
        "max_fvg_to_inversion_bars": 16,
    },
    # --- GC NY LSI hot-regime dry-run candidate ---
    "GC_NY_LSI": {
        "entry_start": "09:35",
        "entry_end": "15:30",
        "flat_start": "15:50",
        "flat_end": "16:00",
        "rr": 3.5,
        "tp1_ratio": 0.3,
        "min_gap_atr_pct": 5.0,
        "min_stop_points": 0.0,
        "fvg_window_left": 10,
        "fvg_window_right": 5,
        "lsi_entry_mode": "timed_hybrid",
        "lsi_close_on_sweep_to_inversion_minutes": 60,
        "lsi_stop_mode": "struct_75pct",
        "lsi_variant": "legacy-LSI",
        "instrument": "GC",
        "atr_length": 5,
        "long_only": False,
        "excluded_dow": None,
        "qty_multiplier": 1.0,
        "risk_usd": 250,
        "max_single_risk_usd": 500,
        "lsi_n_left": 10,
        "lsi_n_right": 75,
        "htf_level_tf_minutes": 60,
        "htf_n_left": 5,
        "htf_trade_max_per_session": 1,
    },
}


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_config(path: Path) -> dict:
    """Load TOML config file."""
    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    with open(path, "rb") as f:
        return tomllib.load(f)


def _env_or_key(
    cfg: dict,
    key: str,
    env_key: str | None = None,
    *,
    allow_config_value: bool = True,
) -> str:
    """Get a secret from an environment variable named directly or by config."""
    if env_key and env_key in os.environ:
        return os.environ[env_key]
    env_from_cfg = cfg.get(f"{key}_env")
    if env_from_cfg and env_from_cfg in os.environ:
        return os.environ[env_from_cfg]
    if allow_config_value:
        return cfg.get(key, "")
    return ""


def _string_set(value) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    return {str(item) for item in value if str(item)}


def _resolve_orderbook_runtime_config(config: dict) -> dict:
    """Resolve zero-cost-safe order-book runtime settings."""
    db_cfg = config.get("databento", {})
    orderbook_cfg = config.get("orderbook", {})
    enable_mbp10 = bool(
        orderbook_cfg.get("enable_mbp10", False)
        or db_cfg.get("enable_mbp10", False)
    )
    mbp10_cost_ack = bool(
        orderbook_cfg.get("mbp10_cost_ack", False)
        or db_cfg.get("mbp10_cost_ack", False)
    )
    if enable_mbp10 and not mbp10_cost_ack:
        raise ValueError(
            "MBP-10 streaming can incur DataBento/exchange fees. "
            "Set [orderbook].mbp10_cost_ack = true to enable it intentionally."
        )

    shadow_enabled = bool(orderbook_cfg.get("dynamic_sizing_shadow_enabled", False))
    apply_enabled = bool(orderbook_cfg.get("dynamic_sizing_enabled", False)) and not shadow_enabled
    provider_enabled = bool(apply_enabled or shadow_enabled)
    return {
        "enable_mbp10": enable_mbp10,
        "mbp10_cost_ack": mbp10_cost_ack,
        "dynamic_sizing_enabled": apply_enabled,
        "dynamic_sizing_shadow_enabled": shadow_enabled,
        "provider_enabled": provider_enabled,
        "dynamic_sizing_sessions": _string_set(orderbook_cfg.get("dynamic_sizing_sessions", [])),
        "retention_seconds": float(orderbook_cfg.get("retention_seconds", 90.0)),
    }


# ---------------------------------------------------------------------------
# Execution config profiles (FAST, SLOW, etc.)
# ---------------------------------------------------------------------------

EXECUTION_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
EXEC_CONFIGS_PATH = EXECUTION_CONFIG_DIR / "exec_configs.json"
DEFAULT_MAIN_DB_URL = "http://143.110.148.234:8100"


@dataclass
class WebhookEntry:
    """A single webhook endpoint with a human-readable label."""

    url: str
    label: str = ""
    paused: bool = False
    multiplier: float = 1.0


@dataclass
class ExecutionConfig:
    """Named execution profile with its own session subset and risk overrides."""

    name: str
    enabled: bool = True
    max_open_contracts: float = 0.0
    webhooks: list[WebhookEntry] = field(default_factory=list)
    session_overrides: dict[str, dict] = field(default_factory=dict)
    lsi_session_overrides: dict[str, dict] = field(default_factory=dict)
    adaptive_risk: dict | None = None

    @property
    def webhook_url(self) -> str:
        """First webhook URL (legacy compat). Empty string if none configured."""
        return self.webhooks[0].url if self.webhooks else ""


def _parse_webhook_list(items: object) -> list[WebhookEntry]:
    """Parse a list of webhook dictionaries into runtime entries."""
    if isinstance(items, list):
        return [
            WebhookEntry(
                url=w.get("url", ""),
                label=w.get("label", ""),
                paused=w.get("paused", False),
                multiplier=float(w.get("multiplier", 1.0)),
            )
            for w in items
            if isinstance(w, dict) and w.get("url")
        ]
    return []


def _parse_webhooks(data: dict) -> list[WebhookEntry]:
    """Parse webhooks from exec config dict, migrating legacy webhook_url."""
    # New format: webhooks array. This remains for legacy compatibility;
    # production webhook URLs should live in the remote main DB.
    if "webhooks" in data:
        return _parse_webhook_list(data["webhooks"])
    # Legacy: single webhook_url string
    url = data.get("webhook_url", "")
    if url:
        return [WebhookEntry(url=url, label="Default")]
    return []


def _main_db_url() -> str:
    return (
        os.environ.get("MAIN_DB_URL")
        or os.environ.get("EXPERIMENTS_DB_URL")
        or DEFAULT_MAIN_DB_URL
    ).rstrip("/")


def _remote_exec_config_request(method: str, path: str, body: dict | None = None) -> dict:
    """Call the remote main DB execution-config API."""
    import urllib.error
    import urllib.request

    url = f"{_main_db_url()}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode())
    if not result.get("success"):
        raise RuntimeError(str(result.get("error", "unknown main DB error")))
    return result.get("result", {})


def load_exec_config_metadata_remote() -> dict[str, dict]:
    """Load execution config metadata and webhook accounts from the remote main DB."""
    try:
        result = _remote_exec_config_request("GET", "/api/execution-configs")
    except Exception as exc:
        logger.warning("Could not load execution configs from remote main DB: %s", exc)
        return {}

    configs = result.get("configs", []) if isinstance(result, dict) else []
    configs_by_name: dict[str, dict] = {}
    for item in configs:
        if not isinstance(item, dict):
            continue
        name = item.get("config_name")
        if not name:
            continue
        remote_config = item.get("config_json")
        if isinstance(remote_config, str) and remote_config:
            try:
                remote_config = json.loads(remote_config)
            except json.JSONDecodeError:
                remote_config = None
        configs_by_name[str(name)] = {
            "enabled": item.get("enabled"),
            "max_open_contracts": item.get("max_open_contracts"),
            "config": remote_config if isinstance(remote_config, dict) else {},
            "webhooks": _parse_webhook_list(item.get("webhooks", [])),
        }
    return configs_by_name


def save_exec_webhooks_remote(config_name: str, webhooks: list[WebhookEntry]) -> list[WebhookEntry]:
    """Persist webhook accounts for one execution config to the remote main DB."""
    from urllib.parse import quote

    result = _remote_exec_config_request(
        "PUT",
        f"/api/execution-configs/{quote(config_name, safe='')}/webhooks",
        {
            "webhooks": [
                {
                    "url": w.url,
                    "label": w.label,
                    "paused": w.paused,
                    "multiplier": w.multiplier,
                }
                for w in webhooks
            ]
        },
    )
    return _parse_webhook_list(result.get("webhooks", []))


def save_exec_config_metadata_remote(config: ExecutionConfig) -> None:
    """Upsert non-secret execution config metadata into the remote main DB."""
    from urllib.parse import quote

    _remote_exec_config_request(
        "PUT",
        f"/api/execution-configs/{quote(config.name, safe='')}",
        {
            "enabled": config.enabled,
            "max_open_contracts": config.max_open_contracts,
            "config": {
                "sessions": config.session_overrides,
                "lsi_sessions": config.lsi_session_overrides,
            },
        },
    )


def sync_exec_config_metadata_remote(configs: list[ExecutionConfig]) -> None:
    """Best-effort sync of file-backed execution config metadata to the remote main DB."""
    for config in configs:
        try:
            save_exec_config_metadata_remote(config)
        except Exception as exc:
            logger.warning("[%s] Could not sync execution config metadata: %s", config.name, exc)


def load_exec_configs(
    config: dict | None = None,
    *,
    include_remote_webhooks: bool = False,
) -> list[ExecutionConfig]:
    """Load execution configs from exec_configs.json.

    Falls back to a single DEFAULT config built from live.toml sessions
    if the file does not exist.
    """
    remote_configs = load_exec_config_metadata_remote() if include_remote_webhooks else {}
    if EXEC_CONFIGS_PATH.exists():
        with open(EXEC_CONFIGS_PATH) as f:
            raw = json.load(f)
        configs = []
        for name, data in raw.items():
            remote = remote_configs.get(name, {})
            remote_config = remote.get("config") if isinstance(remote.get("config"), dict) else {}
            base_webhooks = [] if include_remote_webhooks else _parse_webhooks(data)
            configs.append(ExecutionConfig(
                name=name,
                enabled=(
                    bool(remote["enabled"])
                    if remote.get("enabled") is not None
                    else data.get("enabled", True)
                ),
                max_open_contracts=float(
                    remote["max_open_contracts"]
                    if remote.get("max_open_contracts") is not None
                    else data.get("max_open_contracts", 0.0)
                ),
                webhooks=remote["webhooks"] if name in remote_configs else base_webhooks,
                session_overrides=remote_config.get("sessions", data.get("sessions", {})),
                lsi_session_overrides=remote_config.get("lsi_sessions", data.get("lsi_sessions", {})),
                adaptive_risk=data.get("adaptive_risk"),
            ))
        if configs:
            return configs

    # Fallback: single DEFAULT config from live.toml
    cfg = config or {}
    sessions_enabled = cfg.get("sessions", {}).get("enabled", [
        "NQ_NY", "NQ_Asia", "GC_NY", "ES_NY", "ES_Asia",
    ])
    lsi_enabled = cfg.get("sessions", {}).get("lsi_enabled", [])
    return [ExecutionConfig(
        name="DEFAULT",
        enabled=True,
        webhooks=[],
        session_overrides={s: {} for s in sessions_enabled},
        lsi_session_overrides={s: {} for s in lsi_enabled},
    )]


def save_exec_configs(configs: list[ExecutionConfig]) -> None:
    """Persist non-secret execution configs back to exec_configs.json."""
    raw: dict = {}
    for ec in configs:
        raw[ec.name] = {
            "enabled": ec.enabled,
            "max_open_contracts": ec.max_open_contracts,
            "webhooks": [],
            "sessions": ec.session_overrides,
            "lsi_sessions": ec.lsi_session_overrides,
        }
    with open(EXEC_CONFIGS_PATH, "w") as f:
        json.dump(raw, f, indent=2)
        f.write("\n")


def _base_session_name(session_name: str, overrides: dict | None = None) -> str:
    base_session = (overrides or {}).get("base_session")
    if isinstance(base_session, str) and base_session:
        return base_session
    return session_name


def _required_regime_daily_symbols(engines: list) -> list[str]:
    """Collect extra daily-history symbols required by configured regime gates."""
    from .gates import required_daily_history_symbols_for_regime_gates

    required: set[str] = set()
    for engine in engines:
        required.update(
            required_daily_history_symbols_for_regime_gates(
                getattr(engine, "regime_gates", ()),
            )
        )
    return sorted(required)


def apply_atr_values(
    symbol_map: dict[str, list],
    atr_values_by_symbol: dict[str, dict[int, float]],
) -> None:
    for symbol, target_engines in symbol_map.items():
        symbol_atrs = atr_values_by_symbol.get(symbol, {})
        for engine in target_engines:
            atr = symbol_atrs.get(getattr(engine, "atr_length", 14), 0.0)
            if atr > 0:
                engine._daily_atr = atr


def _engine_ath_gate_enabled(engine) -> bool:
    return (
        hasattr(engine, "seed_ath_high")
        and float(getattr(engine, "ath_block_max_pct", 0.0) or 0.0)
        > float(getattr(engine, "ath_block_min_pct", 0.0) or 0.0)
    )


def required_ath_seed_symbols(symbol_map: dict[str, list]) -> list[str]:
    """Return feed symbols that have at least one enabled ATH-gated engine."""
    return sorted(
        symbol
        for symbol, target_engines in symbol_map.items()
        if any(_engine_ath_gate_enabled(engine) for engine in target_engines)
    )


def apply_ath_highs(
    symbol_map: dict[str, list],
    ath_highs_by_symbol: dict[str, float | None],
) -> dict[str, int]:
    """Seed ATH-gated engines from a per-symbol historical high map."""
    seeded: dict[str, int] = {}
    for symbol, target_engines in symbol_map.items():
        high = ath_highs_by_symbol.get(symbol)
        if high is None or not math.isfinite(float(high)) or float(high) <= 0.0:
            continue
        count = 0
        for engine in target_engines:
            if not _engine_ath_gate_enabled(engine):
                continue
            before = getattr(engine, "_ath_high", float("nan"))
            engine.seed_ath_high(float(high))
            after = getattr(engine, "_ath_high", float("nan"))
            if after != before:
                count += 1
        if count:
            seeded[symbol] = count
    return seeded


def _parse_ath_start_date(value: object) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        logger.warning("Invalid ath.start_date=%r; using lookback_years fallback", value)
        return None


# ---------------------------------------------------------------------------
# Build engines from config
# ---------------------------------------------------------------------------

def build_engines(
    config: dict,
    broker,
    *,
    config_name: str = "",
    session_list: list[str] | None = None,
    exec_overrides: dict[str, dict] | None = None,
    position_manager=None,
) -> tuple[list, dict[str, list], dict[str, set[int]]]:
    """Build ORBEngine instances from config.

    Args:
        config: TOML config dict.
        broker: TradersPost client for this exec config.
        config_name: Execution config name (e.g. "FAST", "SLOW").
        session_list: Which sessions to build. If None, uses live.toml enabled list.
        exec_overrides: Per-session overrides from the exec config (e.g. risk_usd).

    Returns:
        (engines, symbol_map, atr_lengths) where:
        - symbol_map maps DataBento symbol (e.g. "NQ.FUT") to engines.
        - atr_lengths maps DataBento symbol to ATR periods needed by that feed.
    """
    from .engine import ORBEngine
    from .gates import build_regime_gates, build_structure_gate, normalize_regime_gates
    from .overrides import load_overrides

    general = config.get("general", {})
    risk = config.get("risk", {})
    runtime_overrides = load_overrides()

    sessions_enabled = session_list if session_list is not None else config.get("sessions", {}).get("enabled", [
        "NQ_NY", "NQ_Asia", "GC_NY", "ES_NY", "ES_Asia",
    ])
    session_overrides = config.get("sessions", {})
    exec_overrides = exec_overrides or {}

    default_half_days = tuple(config.get("dates", {}).get("half_days", [
        "20250703", "20251128", "20251224", "20250109", "20260119",
    ]))
    default_excluded_dates = tuple(config.get("dates", {}).get("excluded", []))

    engines = []
    symbol_map: dict[str, list] = {}
    # track ATR lengths per feed symbol
    atr_lengths: dict[str, set[int]] = {}

    for sess_name in sessions_enabled:
        sess_exec_overrides = exec_overrides.get(sess_name, {})
        base_sess_name = _base_session_name(sess_name, sess_exec_overrides)
        sess_cfg = SESSION_CONFIGS.get(base_sess_name)
        if sess_cfg is None:
            logger.warning(
                "Unknown session '%s' (base_session=%s), skipping",
                sess_name,
                base_sess_name,
            )
            continue

        # Allow per-session overrides from TOML (keyed by lowercase name).
        # TOML [sessions.gc.ny] creates nested dicts, so traverse the path.
        def _toml_overrides_for(session_key: str) -> dict:
            toml_key = session_key.lower().replace("_", ".")
            toml_overrides: dict = session_overrides
            for part in toml_key.split("."):
                if isinstance(toml_overrides, dict):
                    toml_overrides = toml_overrides.get(part, {})
                else:
                    toml_overrides = {}
                    break
            return toml_overrides if isinstance(toml_overrides, dict) else {}

        toml_overrides = _toml_overrides_for(sess_name)
        if not toml_overrides and base_sess_name != sess_name:
            toml_overrides = _toml_overrides_for(base_sess_name)
        merged = {
            **sess_cfg,
            **toml_overrides,
            **runtime_overrides.get(base_sess_name, {}),
            **runtime_overrides.get(sess_name, {}),
            **sess_exec_overrides,
        }
        half_days = tuple(merged.get("half_days", default_half_days))
        excluded_dates = tuple(merged.get("excluded_dates", default_excluded_dates))
        regime_gates = normalize_regime_gates(
            merged.get("regime_gate"),
            merged.get("regime_gates"),
        )
        compiled_regime_gates = build_regime_gates(regime_gates)

        # Per-session instrument (signal data source) and execution ticker
        sess_instrument = merged.get("instrument", "NQ")
        inst = INSTRUMENTS.get(sess_instrument, INSTRUMENTS["NQ"])
        db_symbol = inst["db_symbol"]

        # Resolve execution ticker: use micro contract for order routing
        exec_ticker = merged.get("exec_ticker") or SIGNAL_TO_EXEC.get(sess_instrument, sess_instrument)
        exec_inst = INSTRUMENTS.get(exec_ticker, inst)

        # track ATR lengths per symbol
        sess_atr_length = merged.get("atr_length", 14)
        atr_lengths.setdefault(db_symbol, set()).add(sess_atr_length)

        risk_usd_value = merged.get("risk_usd", risk.get("risk_usd", 250))
        max_single_risk_usd_value = merged.get("max_single_risk_usd", 1.5 * risk_usd_value)

        common_kwargs = dict(
            name=sess_name,
            broker=broker,
            exec_ticker=exec_ticker,
            config_name=config_name,
            allow_5m_fill_detection=False,
            orb_start=merged["orb_start"],
            orb_end=merged["orb_end"],
            entry_start=merged["entry_start"],
            entry_end=merged["entry_end"],
            flat_start=merged["flat_start"],
            flat_end=merged["flat_end"],
            stop_atr_pct=merged.get("stop_atr_pct", 0.0),
            min_gap_atr_pct=merged.get("min_gap_atr_pct", 0.0),
            max_gap_atr_pct=merged.get("max_gap_atr_pct", 0),
            rr=merged["rr"],
            tp1_ratio=merged["tp1_ratio"],
            exit_mode=merged.get("exit_mode", "split"),
            atr_length=sess_atr_length,
            risk_usd=risk_usd_value,
            point_value=exec_inst["point_value"],
            commission_per_contract=exec_inst["commission"],
            min_qty=merged.get("min_qty", risk.get("min_qty", 1.0)),
            qty_step=risk.get("qty_step", 1.0),
            be_offset_ticks=risk.get("be_offset_ticks", 0),
            min_tick=exec_inst["min_tick"],
            stop_basis=merged.get("stop_basis", "atr"),
            stop_orb_pct=merged.get("stop_orb_pct", 0.0),
            gap_filter_basis=merged.get("gap_filter_basis", "atr"),
            min_gap_orb_pct=merged.get("min_gap_orb_pct", 0.0),
            min_stop_pts=merged.get("min_stop_pts", 0.0),
            min_tp1_pts=merged.get("min_tp1_pts", 0.0),
            max_single_risk_usd=max_single_risk_usd_value,
            long_only=merged.get("long_only", True),
            short_only=merged.get("short_only", False),
            icf_enabled=merged.get("icf_enabled", False),
            continuation_fvg_selection=merged.get("continuation_fvg_selection", "first"),
            orb_trade_max_per_session=merged.get("orb_trade_max_per_session", 1),
            orb_reentry_policy=merged.get("orb_reentry_policy", "any_reentry"),
            strategy_type=merged.get("strategy_type", "continuation"),
            orb_breakout_trigger=merged.get("orb_breakout_trigger", "touch"),
            orb_breakout_buffer_ticks=merged.get("orb_breakout_buffer_ticks", 0),
            orb_breakout_buffer_atr_pct=merged.get("orb_breakout_buffer_atr_pct", 0.0),
            base_bar_minutes=merged.get("base_bar_minutes", 5),
            wide_stop_target_threshold_points=merged.get("wide_stop_target_threshold_points", 0.0),
            wide_stop_target_rr=merged.get("wide_stop_target_rr", 0.0),
            limit_cancel_on_pre_entry_target_touch=merged.get("limit_cancel_on_pre_entry_target_touch", ""),
            runner_trail_mode=merged.get("runner_trail_mode", ""),
            runner_trail_trigger_r=merged.get("runner_trail_trigger_r", 0.0),
            runner_trail_stop_r=merged.get("runner_trail_stop_r", 0.0),
            runner_trail_step_r=merged.get("runner_trail_step_r", 1.0),
            runner_trail_gap_r=merged.get("runner_trail_gap_r", 1.0),
            runner_trail_atr_pct=merged.get("runner_trail_atr_pct", 0.0),
            ath_block_min_pct=merged.get("ath_block_min_pct", 0.0),
            ath_block_max_pct=merged.get("ath_block_max_pct", 0.0),
            max_prior_rolling_atr_pct=merged.get("max_prior_rolling_atr_pct", 0.0),
            max_orb_range_pct=merged.get("max_orb_range_pct", 0.0),
            excluded_dow=merged.get("excluded_dow"),
            fomc_exclusion=merged.get("fomc_exclusion", False),
            regime_gate=regime_gates[0] if len(regime_gates) == 1 else None,
            regime_gates=regime_gates,
            regime_gate_check=compiled_regime_gates[0][1] if len(compiled_regime_gates) == 1 else None,
            regime_gate_checks=compiled_regime_gates,
            structure_gate=merged.get("structure_gate"),
            structure_gate_check=build_structure_gate(merged.get("structure_gate")),
            excluded_dates=excluded_dates,
            half_days=half_days,
            half_day_flat_start=merged.get("half_day_flat_start", config.get("dates", {}).get("half_day_flat_start", "12:50")),
            half_day_flat_end=merged.get("half_day_flat_end", config.get("dates", {}).get("half_day_flat_end", "13:00")),
            position_manager=position_manager,
            position_limit_key=f"{config_name or 'DEFAULT'}:{db_symbol}",
        )
        if merged.get("engine_type") == "hunter_orb":
            from .hunter_orb_engine import HunterORBEngine

            engine = HunterORBEngine(
                **common_kwargs,
                engine_type=merged.get("engine_type", "hunter_orb"),
                body_min_pct=merged.get("body_min_pct", 55.0),
                rejection_wick_max_pct=merged.get("rejection_wick_max_pct", 20.0),
                hunter_entry_basis=merged.get("hunter_entry_basis", "signal_close"),
                sl_buffer_points=merged.get("sl_buffer_points", 1.0),
                hunter_target_rr=merged.get("hunter_target_rr", 2.0),
                large_sl_threshold_points=merged.get("large_sl_threshold_points", 50.0),
                reduced_target_rr=merged.get("reduced_target_rr", 1.0),
                max_hold_minutes=merged.get("max_hold_minutes", 270),
                max_contracts=merged.get("max_contracts", 20.0),
                ema15_enabled=merged.get("ema15_enabled", True),
                ema15_length=merged.get("ema15_length", 14),
                ema15_source=merged.get("ema15_source", "close"),
                ema15_tolerance_points=merged.get("ema15_tolerance_points", 2.0),
                ema15_max_distance=merged.get("ema15_max_distance"),
                reentry_policy=merged.get("reentry_policy", "after_each_loss"),
                allow_same_bar_win_reentry=merged.get("allow_same_bar_win_reentry", True),
                same_bar_win_reentry_max_minutes=merged.get("same_bar_win_reentry_max_minutes", 5.0),
                reentry_max_extension_pct=merged.get("reentry_max_extension_pct", 100.0),
                enable_fast_reentry_exhaustion_filter=merged.get("enable_fast_reentry_exhaustion_filter", True),
                fast_reentry_exhaustion_max_minutes=merged.get("fast_reentry_exhaustion_max_minutes", 10.1),
                fast_reentry_exhaustion_max_extension_pct=merged.get("fast_reentry_exhaustion_max_extension_pct", 12.0),
                fast_reentry_exhaustion_min_ema15_distance=merged.get("fast_reentry_exhaustion_min_ema15_distance", 50.0),
            )
        elif merged.get("engine_type") == "gold_x":
            from .goldx_engine import GoldXEngine

            engine = GoldXEngine(
                **common_kwargs,
                engine_type=merged.get("engine_type", "gold_x"),
                goldx_mode=merged.get("goldx_mode", "both"),
                goldx_classic_signal_end=merged.get("goldx_classic_signal_end", "10:45"),
                goldx_fvg_signal_end=merged.get("goldx_fvg_signal_end", "13:00"),
                goldx_classic_weekdays=merged.get("goldx_classic_weekdays", (0, 3, 4)),
                goldx_fvg_weekdays=merged.get("goldx_fvg_weekdays", (0, 1, 3)),
                goldx_classic_risk_usd=merged.get("goldx_classic_risk_usd", 400.0),
                goldx_classic_max_contracts=merged.get("goldx_classic_max_contracts", 20.0),
                goldx_classic_target_sd=merged.get("goldx_classic_target_sd", 1.0),
                goldx_classic_hard_stop_buffer_points=merged.get("goldx_classic_hard_stop_buffer_points", 7.0),
                goldx_classic_overextension_max_pct=merged.get("goldx_classic_overextension_max_pct", 60.0),
                goldx_enable_classic_overextension_filter=merged.get("goldx_enable_classic_overextension_filter", True),
                goldx_enable_classic_proxy_filters=merged.get("goldx_enable_classic_proxy_filters", True),
                goldx_classic_cooldown_minutes=merged.get("goldx_classic_cooldown_minutes", 50.0),
                goldx_classic_max_hold_minutes=merged.get("goldx_classic_max_hold_minutes", 180),
                goldx_fvg_risk_usd=merged.get("goldx_fvg_risk_usd", 300.0),
                goldx_fvg_max_contracts=merged.get("goldx_fvg_max_contracts", 30.0),
                goldx_fvg_min_size_points=merged.get("goldx_fvg_min_size_points", 9.0),
                goldx_fvg_max_size_points=merged.get("goldx_fvg_max_size_points", 60.0),
                goldx_fvg_max_orb_distance_points=merged.get("goldx_fvg_max_orb_distance_points", 30.0),
                goldx_fvg_target_rr=merged.get("goldx_fvg_target_rr", 2.0),
                goldx_fvg_min_stop_points=merged.get("goldx_fvg_min_stop_points", 10.0),
                goldx_fvg_bars_before_breakout=merged.get("goldx_fvg_bars_before_breakout", 2),
                goldx_fvg_bars_after_breakout=merged.get("goldx_fvg_bars_after_breakout", 2),
                goldx_fvg_max_wait_bars=merged.get("goldx_fvg_max_wait_bars", 30),
                goldx_fvg_max_wait_minutes=merged.get("goldx_fvg_max_wait_minutes", 200),
                goldx_fvg_selection_cooldown_minutes=merged.get("goldx_fvg_selection_cooldown_minutes", 5.0),
                goldx_fvg_after_classic_entry_cooldown_minutes=merged.get(
                    "goldx_fvg_after_classic_entry_cooldown_minutes", 10.0
                ),
                goldx_fvg_after_classic_exit_cooldown_minutes=merged.get(
                    "goldx_fvg_after_classic_exit_cooldown_minutes", 0.0
                ),
                goldx_fvg_max_hold_minutes=merged.get("goldx_fvg_max_hold_minutes", 270),
                goldx_enable_fvg_ut_filter=merged.get("goldx_enable_fvg_ut_filter", True),
                goldx_ut_key_value=merged.get("goldx_ut_key_value", 2.0),
                goldx_ut_atr_period=merged.get("goldx_ut_atr_period", 40),
            )
        else:
            engine = ORBEngine(**common_kwargs)
        engines.append(engine)
        symbol_map.setdefault(db_symbol, []).append(engine)
        logger.info(
            "[%s] Session engine created: %s (type=%s, signal=%s, exec=%s, feed=%s, stop=%s, atr=%d, risk=$%s, regime_gates=%s, structure_gate=%s)",
            config_name or "DEFAULT", sess_name, merged.get("engine_type", "orb"),
            sess_instrument, exec_ticker, db_symbol,
            merged.get("stop_basis", "atr"), sess_atr_length, merged.get("risk_usd", "?"),
            ",".join(regime_gates) if regime_gates else "-",
            merged.get("structure_gate") or "-",
        )

    return engines, symbol_map, atr_lengths


def build_lsi_engines(
    config: dict,
    broker,
    symbol_map: dict[str, list],
    atr_lengths: dict[str, set[int]],
    *,
    config_name: str = "",
    lsi_list: list[str] | None = None,
    lsi_overrides: dict[str, dict] | None = None,
    position_manager=None,
) -> list:
    """Build LSIEngine instances for LSI reversal sessions.

    Mutates symbol_map and atr_lengths in-place to register the new engines.
    """
    from .gates import build_regime_gates, normalize_regime_gates
    from .lsi_engine import LSIEngine

    risk = config.get("risk", {})
    lsi_enabled = lsi_list if lsi_list is not None else config.get("sessions", {}).get("lsi_enabled", [])
    lsi_overrides = lsi_overrides or {}
    if not lsi_enabled:
        return []

    default_half_days = tuple(config.get("dates", {}).get("half_days", [
        "20250703", "20251128", "20251224", "20250109", "20260119",
    ]))
    default_excluded_dates = tuple(config.get("dates", {}).get("excluded", []))

    engines = []
    for sess_name in lsi_enabled:
        sess_cfg = LSI_SESSION_CONFIGS.get(sess_name)
        if sess_cfg is None:
            logger.warning("Unknown LSI session '%s', skipping", sess_name)
            continue

        # Merge exec config overrides (e.g. risk_usd) on top of base config
        merged = {**sess_cfg, **lsi_overrides.get(sess_name, {})}
        sess_instrument = merged.get("instrument", "NQ")
        inst = INSTRUMENTS.get(sess_instrument, INSTRUMENTS["NQ"])
        db_symbol = inst["db_symbol"]
        exec_ticker = SIGNAL_TO_EXEC.get(sess_instrument, sess_instrument)
        exec_inst = INSTRUMENTS.get(exec_ticker, inst)
        sess_atr_length = merged.get("atr_length", sess_cfg.get("atr_length", 14))
        atr_lengths.setdefault(db_symbol, set()).add(sess_atr_length)
        half_days = tuple(merged.get("half_days", default_half_days))
        excluded_dates = tuple(merged.get("excluded_dates", default_excluded_dates))
        regime_gates = normalize_regime_gates(
            merged.get("regime_gate"),
            merged.get("regime_gates"),
        )
        compiled_regime_gates = build_regime_gates(regime_gates)

        # Handle excluded_dow as list → first value for single exclusion
        excl_dow = merged.get("excluded_dow")

        risk_usd_value = merged.get("risk_usd", risk.get("risk_usd", 250))
        max_single_risk_usd_value = merged.get("max_single_risk_usd", 1.5 * risk_usd_value)

        engine = LSIEngine(
            name=sess_name,
            broker=broker,
            exec_ticker=exec_ticker,
            config_name=config_name,
            entry_start=merged["entry_start"],
            entry_end=merged["entry_end"],
            sweep_start=merged.get("sweep_start"),
            sweep_end=merged.get("sweep_end"),
            flat_start=merged["flat_start"],
            flat_end=merged["flat_end"],
            rr=merged["rr"],
            tp1_ratio=merged["tp1_ratio"],
            exit_mode=merged.get("exit_mode", "split"),
            atr_length=sess_atr_length,
            min_gap_atr_pct=merged.get("min_gap_atr_pct", 5.0),
            min_stop_points=merged.get("min_stop_points", 0.0),
            stop_atr_pct=merged.get("stop_atr_pct", 0.0),
            fvg_window_left=merged.get("fvg_window_left", 10),
            fvg_window_right=merged.get("fvg_window_right", 5),
            lsi_entry_mode=merged.get("lsi_entry_mode", "close"),
            lsi_close_on_sweep_to_inversion_minutes=merged.get("lsi_close_on_sweep_to_inversion_minutes", 0),
            lsi_stop_mode=merged.get("lsi_stop_mode", "absolute"),
            lsi_target_mode=merged.get("lsi_target_mode", "risk"),
            lsi_confirmation_mode=merged.get("lsi_confirmation_mode", "inversion"),
            lsi_variant=merged.get("lsi_variant", "legacy-LSI"),
            risk_usd=risk_usd_value,
            point_value=exec_inst["point_value"],
            commission_per_contract=exec_inst["commission"],
            min_qty=merged.get("min_qty", risk.get("min_qty", 1.0)),
            qty_step=risk.get("qty_step", 1.0),
            qty_multiplier=merged.get("qty_multiplier", 1.0),
            dynamic_sizing_shadow=merged.get("dynamic_sizing_shadow", False),
            min_tick=exec_inst["min_tick"],
            max_single_risk_usd=max_single_risk_usd_value,
            wide_stop_target_threshold_points=merged.get("wide_stop_target_threshold_points", 0.0),
            wide_stop_target_rr=merged.get("wide_stop_target_rr", 0.0),
            long_only=merged.get("long_only", True),
            excluded_dow=excl_dow,
            regime_gate=regime_gates[0] if len(regime_gates) == 1 else None,
            regime_gates=regime_gates,
            regime_gate_check=compiled_regime_gates[0][1] if len(compiled_regime_gates) == 1 else None,
            regime_gate_checks=compiled_regime_gates,
            excluded_dates=excluded_dates,
            half_days=half_days,
            half_day_flat_start=merged.get("half_day_flat_start", config.get("dates", {}).get("half_day_flat_start", "12:50")),
            half_day_flat_end=merged.get("half_day_flat_end", config.get("dates", {}).get("half_day_flat_end", "13:00")),
            lsi_n_left=merged.get("lsi_n_left", 3),
            lsi_n_right=merged.get("lsi_n_right", 3),
            htf_level_tf_minutes=merged.get("htf_level_tf_minutes", 60),
            htf_n_left=merged.get("htf_n_left", 5),
            htf_trade_max_per_session=merged.get("htf_trade_max_per_session", 1),
            max_fvg_to_inversion_bars=merged.get("max_fvg_to_inversion_bars", 0),
            lsi_stale_breach_consumes_pivot=merged.get("lsi_stale_breach_consumes_pivot", True),
            lsi_reset_swing_window_on_new_day=merged.get("lsi_reset_swing_window_on_new_day", True),
            cisd_min_leg_bars=merged.get("cisd_min_leg_bars", 2),
            cisd_min_leg_atr_pct=merged.get("cisd_min_leg_atr_pct", 5.0),
            cisd_max_leg_bars=merged.get("cisd_max_leg_bars", 60),
            base_bar_minutes=merged.get("base_bar_minutes", 5),
        )
        engine.position_manager = position_manager
        engine.position_limit_key = f"{config_name or 'DEFAULT'}:{db_symbol}"
        engines.append(engine)
        symbol_map.setdefault(db_symbol, []).append(engine)
        logger.info(
            "[%s] LSI engine created: %s (signal=%s, exec=%s, feed=%s, variant=%s, qty_mult=%.1f, risk=$%s, regime_gates=%s)",
            config_name or "DEFAULT", sess_name, sess_instrument, exec_ticker, db_symbol,
            merged.get("lsi_variant", "legacy-LSI"),
            merged.get("qty_multiplier", 1.0), merged.get("risk_usd", "?"),
            ",".join(regime_gates) if regime_gates else "-",
        )

    return engines


# ---------------------------------------------------------------------------
# Shutdown helpers
# ---------------------------------------------------------------------------

def _checkpoint_shutdown_flat(engine) -> None:
    """Persist shutdown-driven cancel/flatten as FLAT for restart safety.

    During graceful shutdown we intentionally cancel pending entries and flatten
    open positions before writing the final checkpoint. If we keep the old
    in-memory state (`armed_limit` / `managing`), a restart will restore stale
    exposure and can emit duplicate exit orders later in the session.
    """
    state = getattr(engine, "_state", None)
    flat_state = getattr(getattr(state, "__class__", None), "FLAT", None)
    if flat_state is not None:
        engine._state = flat_state

    cleanup_task = getattr(engine, "_cleanup_task", None)
    if cleanup_task is not None and not cleanup_task.done():
        cleanup_task.cancel()
        engine._cleanup_task = None

    release_position_cap = getattr(engine, "_release_position_cap", None)
    if callable(release_position_cap):
        release_position_cap()

    notify_state_change = getattr(engine, "_notify_state_change", None)
    if callable(notify_state_change):
        notify_state_change()


# ---------------------------------------------------------------------------
# Main async loop
# ---------------------------------------------------------------------------

async def run_live(config: dict, api_host: str = "127.0.0.1", api_port: int = 8000) -> None:
    """Run the live execution service."""
    import uvicorn

    from .api import DashboardState, LogTailer, create_app
    from .broker import TradersPostClient
    from .contracts import explicit_traderspost_contract
    from .feed import ET, DataBentoFeed
    from .gates import set_daily_history_provider
    from .orderbook_features import OrderbookFeatureCache, OrderbookVelocityTierSizer
    from .position_limits import ContractCapManager

    general = config.get("general", {})
    db_cfg = config.get("databento", {})
    orderbook_runtime = _resolve_orderbook_runtime_config(config)
    orderbook_mbp10_enabled = orderbook_runtime["enable_mbp10"]
    orderbook_provider_enabled = orderbook_runtime["provider_enabled"]
    orderbook_dynamic_enabled = orderbook_runtime["dynamic_sizing_enabled"]
    orderbook_shadow_enabled = orderbook_runtime["dynamic_sizing_shadow_enabled"]
    orderbook_dynamic_sessions = orderbook_runtime["dynamic_sizing_sessions"]
    orderbook_cache: OrderbookFeatureCache | None = None
    orderbook_provider = None
    if orderbook_mbp10_enabled or orderbook_provider_enabled:
        orderbook_cache = OrderbookFeatureCache(
            retention_seconds=orderbook_runtime["retention_seconds"]
        )
        orderbook_sizer = OrderbookVelocityTierSizer()

        def _live_orderbook_dynamic_provider(context):
            return orderbook_sizer.decision_from_cache(context, orderbook_cache)

        orderbook_provider = _live_orderbook_dynamic_provider
        if orderbook_provider_enabled and not orderbook_mbp10_enabled:
            logger.warning(
                "Orderbook dynamic sizing is enabled but MBP-10 streaming is disabled; "
                "sizing decisions will fall back to neutral 1.0x."
            )

    def _orderbook_status_snapshot() -> dict:
        return {
            "enable_mbp10": orderbook_mbp10_enabled,
            "mbp10_cost_ack": orderbook_runtime["mbp10_cost_ack"],
            "dynamic_sizing_enabled": orderbook_dynamic_enabled,
            "dynamic_sizing_shadow_enabled": orderbook_shadow_enabled,
            "dynamic_sizing_sessions": sorted(orderbook_dynamic_sessions),
            "cache": orderbook_cache.status() if orderbook_cache is not None else None,
        }

    # Load execution configs (FAST, SLOW, etc.)
    exec_configs = load_exec_configs(config, include_remote_webhooks=True)
    sync_exec_config_metadata_remote(exec_configs)
    logger.info("Loaded %d execution config(s): %s", len(exec_configs), [ec.name for ec in exec_configs])

    # Build engines per execution config
    engines_by_config: dict[str, list] = {}
    adaptive_managers: dict[str, "AdaptiveRiskManager"] = {}
    brokers: list[TradersPostClient] = []
    global_symbol_map: dict[str, list] = {}
    global_atr_lengths: dict[str, set[int]] = {}
    exec_configs_meta: dict[str, dict] = {}  # metadata for API
    multi_brokers_by_config: dict[str, "MultiBroker"] = {}  # for per-account API control

    for ec in exec_configs:
        if not ec.enabled:
            logger.info("Execution config '%s' is disabled, skipping", ec.name)
            continue

        # One broker per webhook endpoint; no webhooks = dry-run stub
        config_brokers: list[TradersPostClient] = []
        webhook_entries = ec.webhooks or []
        if not webhook_entries:
            webhook_entries = [WebhookEntry(url="", label="")]

        for wh in webhook_entries:
            b = TradersPostClient(
                webhook_url=wh.url,
                ticker=general.get("instrument", "MNQ"),
                config_name=f"{ec.name}[{wh.label}]" if wh.label else ec.name,
            )
            b.paused = wh.paused
            b.multiplier = wh.multiplier
            config_brokers.append(b)
            brokers.append(b)

        # Multi-broker fan-out: wrap list so engines send to all accounts
        from .broker import MultiBroker
        broker = MultiBroker(config_brokers)
        multi_brokers_by_config[ec.name] = broker
        position_manager = ContractCapManager(max_open_contracts=ec.max_open_contracts)

        # Build continuation engines for this config's sessions
        session_list = list(ec.session_overrides.keys())
        engines, sym_map, atr_lens = build_engines(
            config, broker,
            config_name=ec.name,
            session_list=session_list,
            exec_overrides=ec.session_overrides,
            position_manager=position_manager,
        )

        # Build LSI engines for this config's LSI sessions
        lsi_list = list(ec.lsi_session_overrides.keys())
        lsi_engines = build_lsi_engines(
            config, broker, sym_map, atr_lens,
            config_name=ec.name,
            lsi_list=lsi_list,
            lsi_overrides=ec.lsi_session_overrides,
            position_manager=position_manager,
        )
        if orderbook_provider_enabled and orderbook_provider is not None:
            for engine in lsi_engines:
                if not orderbook_dynamic_sessions or engine.name in orderbook_dynamic_sessions:
                    engine.dynamic_sizing_provider = orderbook_provider
                    engine.dynamic_sizing_shadow = orderbook_shadow_enabled
                    logger.info(
                        "[%s] Orderbook dynamic sizing provider attached: %s shadow=%s apply=%s",
                        ec.name,
                        engine.name,
                        orderbook_shadow_enabled,
                        orderbook_dynamic_enabled,
                    )

        orb_by_name = {engine.name: engine for engine in engines}
        lsi_by_name = {engine.name: engine for engine in lsi_engines}
        nq_ny_orb = orb_by_name.get("NQ_NY")
        nq_ny_lsi = lsi_by_name.get("NQ_NY_LSI")
        if nq_ny_orb is not None and nq_ny_lsi is not None:
            def _make_nq_ny_overlap_check(orb_engine):
                def _check(direction: int) -> bool:
                    if direction != 1:
                        return False
                    levels = getattr(orb_engine, "_levels", None)
                    state = getattr(getattr(orb_engine, "_state", None), "value", "")
                    if state not in {"armed_limit", "filled", "managing"}:
                        return False
                    return bool(levels is not None and getattr(levels, "direction", 0) == -1)

                return _check

            nq_ny_lsi.trade_overlap_check = _make_nq_ny_overlap_check(nq_ny_orb)

        config_engines = engines + lsi_engines
        engines_by_config[ec.name] = config_engines

        # Adaptive prop-firm risk scaling (tier sizing + consistency throttle)
        if ec.adaptive_risk:
            from .adaptive_risk import AdaptiveRiskManager
            adaptive_manager = AdaptiveRiskManager(ec.name, ec.adaptive_risk)
            adaptive_manager.bind_cap_manager(position_manager)
            for engine in config_engines:
                engine.adaptive_risk = adaptive_manager
            adaptive_managers[ec.name] = adaptive_manager
            logger.info(
                "[%s] adaptive risk enabled: %s", ec.name, adaptive_manager.status(),
            )

        # Merge into global maps (feed routes bars to ALL engines across all configs)
        for sym, eng_list in sym_map.items():
            global_symbol_map.setdefault(sym, []).extend(eng_list)
        for sym, lengths in atr_lens.items():
            global_atr_lengths.setdefault(sym, set()).update(lengths)

        # Store metadata for API
        exec_configs_meta[ec.name] = {
            "enabled": ec.enabled,
            "max_open_contracts": ec.max_open_contracts,
            "webhooks": [{"url": w.url, "label": w.label, "paused": w.paused, "multiplier": w.multiplier} for w in ec.webhooks],
            "sessions": session_list,
            "lsi_sessions": lsi_list,
        }

        n_live_wh = sum(1 for b in config_brokers if not b.dry_run)
        config_mode = "LIVE (%d webhook%s)" % (n_live_wh, "s" if n_live_wh != 1 else "") if n_live_wh else "DRY-RUN (no webhooks)"
        logger.info(
            "[%s] %s — %d engines: sessions=%s lsi=%s",
            ec.name, config_mode, len(config_engines), session_list, lsi_list,
        )

    all_engines = [e for engines in engines_by_config.values() for e in engines]
    if not all_engines:
        logger.error("No session engines configured across any execution config")
        sys.exit(1)
    for engine in all_engines:
        if hasattr(engine, "contract_routing_required"):
            engine.contract_routing_required = True

    # Dashboard API — pass engines grouped by config
    has_live = any(not b.dry_run for b in brokers)
    mode = "LIVE" if has_live else "DRY-RUN"
    dashboard = DashboardState(
        engines_by_config=engines_by_config,
        config=config,
        mode=mode,
        exec_configs=exec_configs_meta,
        multi_brokers_by_config=multi_brokers_by_config,
        orderbook_status=_orderbook_status_snapshot(),
    )

    # Checkpoint persistence — debounced to one write per event loop turn
    from .checkpoint import (
        save_checkpoint, restore_engines, load_trade_history, save_trade_history,
    )
    _checkpoint_pending = False

    def _request_checkpoint():
        nonlocal _checkpoint_pending
        if _checkpoint_pending:
            return
        _checkpoint_pending = True
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon(_do_checkpoint)
        except RuntimeError:
            _do_checkpoint()

    def _do_checkpoint():
        nonlocal _checkpoint_pending
        _checkpoint_pending = False
        save_checkpoint(engines_by_config)

    # Wire callbacks into each engine (both ORBEngine and LSIEngine)
    def _make_trade_exit_handler(manager):
        def _handler(record):
            dashboard.record_trade(record)
            try:
                manager.record_trade(record)
            except Exception:
                logger.exception("[%s] adaptive risk record_trade failed", manager.config_name)
        return _handler

    for cfg_name, cfg_engines in engines_by_config.items():
        manager = adaptive_managers.get(cfg_name)
        on_exit = _make_trade_exit_handler(manager) if manager is not None else dashboard.record_trade
        for engine in cfg_engines:
            engine.on_state_change = dashboard.on_state_change
            engine.on_trade_exit = on_exit
            engine.on_checkpoint = _request_checkpoint

    # Wire G5 gate for NQ_LDN: skip when Asia hit TP1 the prior night.
    # Scoped per config — only checks trade_history from the same config.
    for cfg_name, cfg_engines in engines_by_config.items():
        def _make_g5_gate(config_name: str):
            def _g5_gate(ldn_date: str) -> bool:
                """Return True to BLOCK the trade (Asia TP1 hit prior night)."""
                from datetime import timedelta
                try:
                    ldn_dt = datetime.strptime(ldn_date, "%Y%m%d")
                except ValueError:
                    return False
                asia_dt = ldn_dt - timedelta(days=1)
                while asia_dt.weekday() >= 5:
                    asia_dt -= timedelta(days=1)
                asia_date_str = asia_dt.strftime("%Y%m%d")
                return dashboard.asia_tp1_hit_for_date(asia_date_str, config_name=config_name)
            return _g5_gate

        for engine in cfg_engines:
            if engine.name == "NQ_LDN":
                engine.g5_gate_check = _make_g5_gate(cfg_name)

    app = create_app(dashboard)
    tailer = LogTailer(dashboard)

    uvi_config = uvicorn.Config(
        app, host=api_host, port=api_port, log_level="warning",
    )
    server = uvicorn.Server(uvi_config)

    # Bar callback — route 5m bars to engines for signal detection (ORB, FVG)
    async def on_bar(symbol: str, bar, daily_atrs: dict[int, float]):
        target_engines = global_symbol_map.get(symbol, [])
        rolling_atr_pcts = getattr(daily_atrs, "rolling_atr_pct_by_length", {})
        for engine in target_engines:
            atr_length = getattr(engine, "atr_length", 14)
            daily_atr = daily_atrs.get(atr_length, 0.0)
            if hasattr(engine, "set_context_gate_values"):
                engine.set_context_gate_values(
                    prior_rolling_atr_pct=rolling_atr_pcts.get(atr_length)
                )
            try:
                await engine.on_bar(bar, daily_atr)
            except Exception:
                logger.exception("[%s] on_bar failed — engine isolated", getattr(engine, "name", "?"))

    # Tick callback — route 1s bars to engines for fill/exit management
    async def on_tick(symbol: str, tick, daily_atrs: dict[int, float]):
        target_engines = global_symbol_map.get(symbol, [])
        for engine in target_engines:
            daily_atr = daily_atrs.get(getattr(engine, "atr_length", 14), 0.0)
            try:
                await engine.on_tick(tick, daily_atr)
            except Exception:
                logger.exception("[%s] on_tick failed — engine isolated", getattr(engine, "name", "?"))

    async def on_orderbook(sample):
        if orderbook_cache is not None:
            orderbook_cache.add_sample(sample)
            dashboard.orderbook_status = _orderbook_status_snapshot()

    ACTIVE_BROKER_STATES = {"armed_limit", "filled", "managing"}

    def _active_trade_signal_contract(engine) -> str:
        state = getattr(getattr(engine, "_state", None), "value", "")
        if state not in ACTIVE_BROKER_STATES:
            return ""
        return str(getattr(engine, "_trade_signal_contract", "") or "")

    def allow_contract_roll(
        symbol: str,
        current_raw: str | None,
        candidate_raw: str,
        timestamp: datetime,
    ) -> bool:
        blockers = []
        for engine in global_symbol_map.get(symbol, []):
            active_signal = _active_trade_signal_contract(engine)
            if active_signal and active_signal != candidate_raw:
                blockers.append(
                    "%s/%s active=%s broker=%s"
                    % (
                        getattr(engine, "config_name", ""),
                        getattr(engine, "name", "?"),
                        active_signal,
                        getattr(engine, "broker_ticker", getattr(engine, "exec_ticker", "")),
                    )
                )
        if blockers:
            logger.warning(
                "Contract roll blocked for %s: %s → %s at %s; active trades pinned: %s",
                symbol,
                current_raw or "-",
                candidate_raw,
                timestamp.isoformat(),
                "; ".join(blockers),
            )
            return False
        return True

    async def on_contract(symbol: str, raw_contract: str, timestamp: datetime):
        target_engines = global_symbol_map.get(symbol, [])
        for engine in target_engines:
            exec_root = str(getattr(engine, "exec_ticker", "") or "")
            try:
                exec_contract = explicit_traderspost_contract(
                    signal_contract=raw_contract,
                    exec_root=exec_root,
                    as_of=timestamp,
                )
                error = None
            except Exception as exc:
                exec_contract = None
                error = str(exc)
                logger.error(
                    "[%s] Contract routing failed: feed=%s raw=%s exec_root=%s error=%s",
                    getattr(engine, "name", "?"),
                    symbol,
                    raw_contract,
                    exec_root,
                    error,
                )

            active_signal = getattr(engine, "_trade_signal_contract", "")
            state = getattr(getattr(engine, "_state", None), "value", "")
            if active_signal and active_signal != raw_contract and state in {"armed_limit", "filled", "managing"}:
                logger.warning(
                    "[%s] Feed contract rolled while engine active: active=%s new=%s state=%s broker_ticker=%s",
                    getattr(engine, "name", "?"),
                    active_signal,
                    raw_contract,
                    state,
                    getattr(engine, "broker_ticker", exec_root),
                )
                continue

            if hasattr(engine, "set_contract_context"):
                engine.set_contract_context(
                    signal_contract=raw_contract,
                    exec_contract=exec_contract,
                    error=error,
                )

    # DataBento feed — subscribe to all symbols needed by active engines
    api_key = _env_or_key(db_cfg, "api_key", allow_config_value=False)
    if not api_key:
        logger.warning(
            "DATABENTO_API_KEY is not set; add it to execution/.env or the process environment."
        )
    feed_symbols = list(global_symbol_map.keys())
    daily_only_symbols = [
        symbol for symbol in _required_regime_daily_symbols(all_engines)
        if symbol not in feed_symbols
    ]

    feed = DataBentoFeed(
        api_key=api_key or None,
        symbols=feed_symbols,
        daily_only_symbols=daily_only_symbols,
        dataset=db_cfg.get("dataset", "GLBX.MDP3"),
        on_bar=on_bar,
        on_tick=on_tick,
        on_orderbook=on_orderbook if orderbook_mbp10_enabled else None,
        on_contract=on_contract,
        on_contract_roll_check=allow_contract_roll,
        enable_mbp10=orderbook_mbp10_enabled,
        atr_lengths_by_symbol=global_atr_lengths,
        front_month_roll_min_volume=int(db_cfg.get("front_month_roll_min_volume", 100)),
        front_month_roll_ratio=float(db_cfg.get("front_month_roll_ratio", 1.10)),
    )
    if daily_only_symbols:
        logger.info("Daily-history-only symbols added for regime gates: %s", daily_only_symbols)
    set_daily_history_provider(feed.get_daily_history_for_symbol)

    # Refresh ATR from historical daily bars (prior completed day)
    atr_refresh_days = 60
    refresh_info = feed.refresh_atr_daily(lookback_days=atr_refresh_days)
    if refresh_info:
        logger.info(
            "ATR refresh complete: %s",
            {i.symbol: {"last_date": str(i.last_daily_date), "atr": round(i.atr_value, 2)} for i in refresh_info},
        )

    atr_values = {
        symbol: feed.get_atr_values_for_symbol(symbol) for symbol in feed_symbols
    }
    apply_atr_values(global_symbol_map, atr_values)

    # Seed ATH-gated ORB engines from historical daily highs before any
    # recovery/checkpoint path can evaluate a setup. This makes live startup
    # match exact replay's expanding-ATH context without using future bars.
    ath_highs: dict[str, float | None] = {}
    ath_seed_symbols = required_ath_seed_symbols(global_symbol_map)
    if ath_seed_symbols:
        ath_cfg = config.get("ath", {})
        try:
            ath_lookback_years = int(ath_cfg.get("lookback_years", 20))
        except (TypeError, ValueError):
            logger.warning("Invalid ath.lookback_years=%r; using 20", ath_cfg.get("lookback_years"))
            ath_lookback_years = 20
        ath_infos = feed.refresh_ath_highs(
            symbols=ath_seed_symbols,
            start_date=_parse_ath_start_date(ath_cfg.get("start_date")),
            lookback_years=ath_lookback_years,
        )
        ath_highs = {info.symbol: info.ath_high for info in ath_infos}
        seeded = apply_ath_highs(global_symbol_map, ath_highs)
        logger.info(
            "ATH seed refresh complete: highs=%s seeded_engines=%s",
            {
                info.symbol: {
                    "ath": info.ath_high,
                    "last_date": str(info.last_daily_date) if info.last_daily_date else None,
                    "bars": info.bars_used,
                }
                for info in ath_infos
            },
            seeded,
        )

    # Restore trade history from disk (G5 gate)
    dashboard.trade_history = load_trade_history()
    if dashboard.trade_history:
        logger.info("Restored %d trade(s) from history file", len(dashboard.trade_history))

    # Seed adaptive risk managers from restored history (dedupes against saved state)
    for manager in adaptive_managers.values():
        manager.replay_history(dashboard.trade_history)
        logger.info("[%s] adaptive risk after history replay: %s",
                    manager.config_name, manager.status())

    # Restore checkpoint before time-based recovery.  Intraday recovery below can
    # repair stale FLAT checkpoints from a prior session, but must not overwrite
    # live exposure or a completed FLAT state from the current session.
    checkpoint_restored = restore_engines(engines_by_config)
    if checkpoint_restored > 0:
        logger.info(
            "Checkpoint recovery: %d engine(s) restored from checkpoint",
            checkpoint_restored,
        )
        apply_atr_values(global_symbol_map, atr_values)
        if ath_highs:
            seeded = apply_ath_highs(global_symbol_map, ath_highs)
            logger.info("ATH seeds re-applied after checkpoint restore: %s", seeded)

    # Recover current-day opening ranges / session state from recent intraday history.
    # Keep this bypassable so a stalled historical preload cannot block the API
    # during operational restarts.
    skip_intraday_preload = os.environ.get("EXEC_SKIP_INTRADAY_PRELOAD", "").strip().lower()
    intraday_recovery_enabled = True
    if skip_intraday_preload in {"1", "true", "yes", "on"}:
        logger.warning("Skipping intraday preload because EXEC_SKIP_INTRADAY_PRELOAD is enabled")
        intraday_recovery_enabled = False
        intraday_5m = {}
    else:
        intraday_5m = feed.preload_intraday_5m(lookback_hours=18)
    now_et = datetime.now(tz=ET)
    for symbol, raw_contract in feed.get_preload_contracts().items():
        if allow_contract_roll(symbol, None, raw_contract, now_et):
            await on_contract(symbol, raw_contract, now_et)
        else:
            logger.warning(
                "Preload contract context held for %s: candidate=%s active trade is pinned",
                symbol,
                raw_contract,
            )

    def _startup_recovery_skip_reason(engine) -> str | None:
        state = getattr(engine, "_state", None)
        state_value = getattr(state, "value", state)
        if state_value in {"armed_limit", "filled", "managing"}:
            return "checkpoint has financial exposure"
        if state_value != "flat":
            return None

        current_date = getattr(engine, "_current_date", "")
        if not current_date:
            return None

        if hasattr(engine, "_crosses_midnight") and hasattr(engine, "_orb_start_t"):
            session_date = (
                (now_et - timedelta(days=1)).strftime("%Y%m%d")
                if engine._crosses_midnight and now_et.time() < engine._orb_start_t
                else now_et.strftime("%Y%m%d")
            )
        else:
            session_date = now_et.strftime("%Y%m%d")

        if current_date == session_date:
            return "checkpoint is flat for the current session"
        return None

    recovered = 0
    skipped_recovery = 0
    if intraday_recovery_enabled:
        for symbol, target_engines in global_symbol_map.items():
            bars = intraday_5m.get(symbol, [])
            if not bars:
                logger.info("No intraday preload bars for %s; preserving checkpoint state", symbol)
                continue
            for engine in target_engines:
                skip_reason = _startup_recovery_skip_reason(engine)
                if skip_reason is not None:
                    skipped_recovery += 1
                    logger.info(
                        "[%s] Skipping startup recovery: %s",
                        getattr(engine, "name", "engine"),
                        skip_reason,
                    )
                    continue
                if hasattr(engine, "recover_opening_range") and engine.recover_opening_range(bars, now_et):
                    recovered += 1
                elif hasattr(engine, "recover_session_state") and engine.recover_session_state(bars, now_et):
                    recovered += 1
    else:
        logger.info("Startup recovery skipped; preserving checkpoint state")
    logger.info(
        "startup recovery complete: recovered=%d skipped=%d total_engines=%d",
        recovered, skipped_recovery, len(all_engines),
    )

    for cfg_name, cfg_engines in engines_by_config.items():
        if not cfg_engines:
            continue
        position_manager = getattr(cfg_engines[0], "position_manager", None)
        if position_manager is None or not position_manager.enabled:
            continue
        for engine in cfg_engines:
            levels = getattr(engine, "_levels", None)
            state = getattr(engine, "_state", None)
            if levels is None or state is None:
                continue
            state_value = getattr(state, "value", "")
            if state_value not in {"armed_limit", "managing"}:
                continue
            if getattr(engine, "_tp1_hit", False) and not levels.is_single_contract:
                position_manager.adjust(
                    engine.position_limit_key,
                    max(0.0, levels.qty - levels.half_qty),
                    owner_id=engine.name,
                )
            else:
                position_manager.adjust(
                    engine.position_limit_key,
                    levels.qty,
                    owner_id=engine.name,
                )

    logger.info(
        "Starting ORB Trader — configs=%s feeds=%s total_engines=%d api=:%d",
        list(engines_by_config.keys()), feed_symbols, len(all_engines), api_port,
    )

    # Graceful shutdown handler — cancel/flatten active positions on SIGTERM/SIGINT
    shutdown_event = asyncio.Event()
    last_atr_refresh_date = datetime.now(tz=ET).date()

    def _handle_shutdown_signal(signum, _frame):
        sig_name = signal.Signals(signum).name
        logger.info("Received %s, initiating graceful shutdown...", sig_name)
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _handle_shutdown_signal)

    async def _shutdown_watcher():
        await shutdown_event.wait()
        logger.info("Graceful shutdown: cancelling/flattening active positions...")
        for engine in all_engines:
            try:
                state_val = engine._state.value if hasattr(engine._state, "value") else str(engine._state)
                if state_val == "armed_limit":
                    logger.info("[%s] Shutdown: cancelling pending order", engine.name)
                    await engine.broker.send_cancel(
                        ticker=getattr(engine, "broker_ticker", engine.exec_ticker)
                    )
                    _checkpoint_shutdown_flat(engine)
                elif state_val == "managing":
                    logger.info("[%s] Shutdown: flattening open position", engine.name)
                    await engine.broker.send_flatten(
                        ticker=getattr(engine, "broker_ticker", engine.exec_ticker)
                    )
                    _checkpoint_shutdown_flat(engine)
            except Exception:
                logger.exception("[%s] Error during shutdown cleanup", engine.name)

        # Final checkpoint
        save_checkpoint(engines_by_config)
        save_trade_history(dashboard.trade_history)
        logger.info("Graceful shutdown complete. Final checkpoint saved.")
        server.should_exit = True

    async def _atr_refresh_loop():
        nonlocal last_atr_refresh_date
        while not shutdown_event.is_set():
            now = datetime.now(tz=ET)
            if last_atr_refresh_date != now.date():
                try:
                    refresh_info = feed.refresh_atr_daily(lookback_days=atr_refresh_days)
                    atr_values = {
                        symbol: feed.get_atr_values_for_symbol(symbol) for symbol in feed_symbols
                    }
                    apply_atr_values(global_symbol_map, atr_values)
                    last_atr_refresh_date = now.date()
                    if refresh_info:
                        logger.info(
                            "Daily ATR refresh complete: %s",
                            {i.symbol: {"last_date": str(i.last_daily_date), "atr": round(i.atr_value, 2)} for i in refresh_info},
                        )
                except Exception:
                    logger.exception("Daily ATR refresh failed")
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=60)
            except asyncio.TimeoutError:
                pass

    try:
        await asyncio.gather(
            feed.run(),
            server.serve(),
            tailer.run(),
            _atr_refresh_loop(),
            _shutdown_watcher(),
        )
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        for broker in brokers:
            await broker.close()


async def run_replay(config: dict, csv_path: str, start: str | None, end: str | None) -> None:
    """Replay historical bars through the engine."""
    from .broker import TradersPostClient
    from .feed import ReplayFeed

    broker = TradersPostClient(
        webhook_url="",
        ticker="MNQ",
    )

    engines, _symbol_map, atr_lengths = build_engines(config, broker)

    replay_atr_lengths = sorted({
        length for lengths in atr_lengths.values() for length in lengths
    }) or [14]

    async def on_bar(bar, daily_atrs: dict[int, float]):
        rolling_atr_pcts = getattr(daily_atrs, "rolling_atr_pct_by_length", {})
        for engine in engines:
            atr_length = getattr(engine, "atr_length", 14)
            daily_atr = daily_atrs.get(atr_length, 0.0)
            if hasattr(engine, "set_context_gate_values"):
                engine.set_context_gate_values(
                    prior_rolling_atr_pct=rolling_atr_pcts.get(atr_length)
                )
            await engine.on_bar(bar, daily_atr)

    feed = ReplayFeed(
        csv_path=csv_path,
        on_bar=on_bar,
        atr_lengths=replay_atr_lengths,
        start_date=start,
        end_date=end,
    )

    logger.info(
        "Replaying %s — sessions=%s start=%s end=%s",
        csv_path, [e.name for e in engines], start or "all", end or "all",
    )
    await feed.run()
    logger.info("Replay complete")

    # Print final status
    for engine in engines:
        logger.info("Final state: %s", engine.status_dict())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cli() -> None:
    """Command-line entry point."""
    from dotenv import load_dotenv
    from .logging_config import setup_logging

    # Load .env file from execution/ directory (secrets stay out of git)
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    load_dotenv(env_path)

    parser = argparse.ArgumentParser(
        description="ORB Trader — 5-leg combined longs execution service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run orb-trader                           # Configs with webhooks send live; others dry-run
  uv run orb-trader --replay NQ_5m.csv       # Replay historical data (always dry-run)
  uv run orb-trader --config my_config.toml   # Custom config

5-Leg Portfolio:
  NQ_NY   — NQ NY R11  (ATR stop, rr=3.5,  Fri excl)
  NQ_Asia — NQ Asia R9 (ORB stop, rr=6.0,  Tue excl)
  GC_NY   — GC NY R3   (ATR stop, rr=9.0,  Fri+FOMC excl, ICF)
  ES_NY   — ES NY      (ATR stop, rr=5.0,  Thu excl, dual floor)
  ES_Asia — ES Asia    (ORB stop, rr=1.5,  no DOW excl, dual floor)
""",
    )

    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG,
        help="Path to TOML config file",
    )
    parser.add_argument(
        "--replay", type=str, default=None,
        help="Replay historical 5m CSV instead of live streaming",
    )
    parser.add_argument(
        "--start", type=str, default=None,
        help="Start date for replay (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end", type=str, default=None,
        help="End date for replay (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--host", type=str, default=os.environ.get("EXEC_API_HOST", "127.0.0.1"),
        help="Dashboard API host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port", type=int, default=8000,
        help="Dashboard API port (default: 8000)",
    )
    parser.add_argument(
        "--log-level", type=str, default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level",
    )

    args = parser.parse_args()

    setup_logging(level=args.log_level)

    # Load config
    if args.config.exists():
        config = load_config(args.config)
        logger.info("Loaded config from %s", args.config)
    else:
        logger.warning("Config file %s not found — using defaults", args.config)
        config = {}

    if args.replay:
        asyncio.run(run_replay(config, args.replay, args.start, args.end))
    else:
        asyncio.run(run_live(config, api_host=args.host, api_port=args.port))


if __name__ == "__main__":
    cli()
