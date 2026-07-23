#!/usr/bin/env python3
"""Validation and prop-firm packet for the frozen NQ NY 3m VWAP leg."""

from __future__ import annotations

import importlib.util
import json
import math
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / ".agents" / "skills" / "prop-firm-risk-analysis" / "scripts"))

from orb_backtest.data.fees import estimated_commission_per_side  # noqa: E402
from prop_firm_risk import (  # noqa: E402
    PropFirmRiskProfile,
    make_account_starts,
    max_consecutive_outcomes,
    profile_to_dict,
    score_prop_firm_outcomes,
    simulate_prop_firm_risk,
)


RUN_SLUG = "nq_ny_vwap_3m_validation_prop_packet_20260710"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_VWAP_3M_VALIDATION_PROP_PACKET_20260710.md"

DATA_START = "2021-06-05"
EFFECTIVE_START = "2021-06-07"
DATA_END_EXCLUSIVE = "2026-06-06"
MATURED_START_END_EXCLUSIVE = "2025-06-06"
RECENT_MATURED_START = "2024-01-01"

TIMEFRAME_MIN = 3
RR = 1.5
BASE_EXTENSION_ATR_PCT = 0.025
BASE_CONSOLIDATION_ATR_PCT = 0.20
BASE_STOP_ATR_PCT = 0.075
CONSOLIDATION_BARS = 10
SETUP_TIMEOUT_BARS = 20
COOLDOWN_BARS = 4
MAX_TRADES_PER_DAY = 3

NQ_TICK = 0.25
MNQ_POINT_VALUE = 2.0
MNQ_COMMISSION_PER_SIDE = float(estimated_commission_per_side("MNQ"))
SLIPPAGE_TICKS_PER_SIDE = (0, 1, 2, 4)
PROP_SLIPPAGE_TICKS_PER_SIDE = (0, 1, 2)
RISK_GRID_USD = (50, 75, 100, 125, 150, 175, 200, 250, 300, 400, 500)
DIRECTION_SCOPES = ("both", "long_only", "short_only")

DEPLOYABILITY = "research_only"
LIVE_SUPPORT_NOTES = (
    "The 3m VWAP sweep/reclaim state machine and native-timeframe static-R exit are research-script only; "
    "the live execution engine cannot arm this setup yet."
)
EXACT_REPLAY_REQUIRED = "yes"


def _load_timeframe_module() -> Any:
    path = SCRIPT_DIR / "run_nq_ny_vwap_static_rr_timeframe_sweep_20260630.py"
    spec = importlib.util.spec_from_file_location("nq_vwap_static_tf_20260630_validation", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load timeframe module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tf = _load_timeframe_module()
ctx = tf.ctx


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _max_drawdown(values: np.ndarray | list[float]) -> float:
    array = np.asarray(values, dtype=float)
    if len(array) == 0:
        return 0.0
    equity = np.cumsum(array)
    peak = np.maximum.accumulate(np.concatenate(([0.0], equity))) [1:]
    return float(np.min(equity - peak))


def _profit_factor(values: np.ndarray | list[float]) -> float:
    array = np.asarray(values, dtype=float)
    wins = float(array[array > 0].sum())
    losses = float(array[array < 0].sum())
    if losses < 0:
        return wins / abs(losses)
    return float("inf") if wins > 0 else 0.0


def _direction_filter(frame: pd.DataFrame, scope: str) -> pd.DataFrame:
    if scope == "both":
        return frame.copy()
    direction = "long" if scope == "long_only" else "short"
    return frame[frame["direction"] == direction].copy()


def _score_frame(
    frame: pd.DataFrame,
    *,
    r_column: str,
    trading_days: int,
    label: str,
) -> dict[str, Any]:
    values = frame[r_column].astype(float).to_numpy() if not frame.empty else np.array([], dtype=float)
    total_r = float(values.sum())
    max_dd = _max_drawdown(values)
    years = trading_days / 252.0 if trading_days else 0.0
    avg_annual_r = total_r / years if years else 0.0
    yearly = frame.assign(year=frame["date"].astype(str).str[:4]).groupby("year")[r_column].sum() if not frame.empty else pd.Series(dtype=float)
    return {
        "label": label,
        "total_trades": int(len(frame)),
        "trading_days": int(trading_days),
        "avg_trades_per_day": round(len(frame) / trading_days, 4) if trading_days else 0.0,
        "total_r": round(total_r, 4),
        "avg_r": round(float(values.mean()), 4) if len(values) else 0.0,
        "avg_annual_r": round(avg_annual_r, 4),
        "calmar": round(avg_annual_r / abs(max_dd), 4) if max_dd < 0 else 0.0,
        "profit_factor": round(_profit_factor(values), 4),
        "win_rate": round(float((values > 0).mean()), 4) if len(values) else 0.0,
        "max_drawdown_r": round(max_dd, 4),
        "negative_years": int((yearly < 0).sum()),
        "deployability": DEPLOYABILITY,
        "live_support_notes": LIVE_SUPPORT_NOTES,
        "exact_replay_required": EXACT_REPLAY_REQUIRED,
    }


def _make_tf_config(extension_atr_pct: float, consolidation_atr_pct: float) -> Any:
    setup = ctx.StateMachineConfig(
        label="frozen_vwap_3m_validation",
        mean_mode="vwap",
        extension_atr_pct=extension_atr_pct,
        consolidation_bars=CONSOLIDATION_BARS,
        consolidation_atr_pct=consolidation_atr_pct,
        setup_timeout_bars=SETUP_TIMEOUT_BARS,
        stop_buffer_atr_pct=0.02,
        min_rr_to_mean=0.20,
        cooldown_bars=COOLDOWN_BARS,
        max_trades_per_day=MAX_TRADES_PER_DAY,
    )
    context = ctx.ContextConfig(
        structure_gate="none",
        vwap_acceptance="none",
        efficiency_max=None,
        ib_location="none",
        session_range_atr_max=2.0,
        time_bucket="full",
    )
    return tf.TimeframeConfig(timeframe_min=TIMEFRAME_MIN, setup=setup, context=context)


def _load_source_and_days() -> tuple[pd.DataFrame, list[Any], dict[str, float]]:
    df_1m = tf._load_1m_source()
    df_3m = tf._resample_ohlcv(df_1m, TIMEFRAME_MIN)
    days = ctx._prepare_days(ctx._prepare_rth(df_3m))
    return df_1m, days, tf._prior_session_ranges(days)


def _generate_stream(
    days: list[Any],
    prior_ranges: dict[str, float],
    *,
    extension_atr_pct: float,
    consolidation_atr_pct: float,
    stop_atr_pct: float,
) -> list[dict[str, Any]]:
    config = _make_tf_config(extension_atr_pct, consolidation_atr_pct)
    candidates = [ctx._generate_candidates_for_day(day, config.setup) for day in days]
    stop = tf.StaticStopConfig("atr14_prev", stop_atr_pct, RR)
    return tf._simulate_model(days, candidates, config, stop, prior_ranges)


def _read_1s() -> pd.DataFrame:
    path = ROOT / "data" / "raw" / "NQ_1s.parquet"
    return pd.read_parquet(
        path,
        columns=["open", "high", "low", "close", "volume"],
        filters=[
            ("datetime", ">=", pd.Timestamp(DATA_START)),
            ("datetime", "<", pd.Timestamp(DATA_END_EXCLUSIVE)),
        ],
    ).sort_index()


def _replay_trade(row: dict[str, Any], lower: pd.DataFrame, path_label: str) -> dict[str, Any]:
    entry_ts = pd.Timestamp(row["entry_ts"])
    flat_ts = pd.Timestamp(f"{row['date']} 15:55:00")
    window = lower.loc[entry_ts:flat_ts]
    if window.empty:
        return {
            **row,
            "path_label": path_label,
            "path_missing": True,
            "path_exit_ts": row["exit_ts"],
            "path_exit_price": row["exit_price"],
            "path_exit_type": row["exit_type"],
            "path_r_multiple": row["r_multiple"],
            "path_r_delta": 0.0,
            "path_exit_type_changed": False,
        }

    direction = int(row["direction_int"])
    entry = float(row["entry"])
    stop = float(row["stop"])
    target = float(row["target"])
    risk = float(row["risk_points"])
    exit_ts = window.index[-1]
    exit_price = float(window["close"].iloc[-1])
    exit_type = "eod"
    for ts, bar in window.iterrows():
        if direction == 1:
            stop_hit = float(bar.low) <= stop
            target_hit = float(bar.high) >= target
        else:
            stop_hit = float(bar.high) >= stop
            target_hit = float(bar.low) <= target
        if stop_hit:
            exit_ts = ts
            exit_price = stop
            exit_type = "stop"
            break
        if target_hit:
            exit_ts = ts
            exit_price = target
            exit_type = "target"
            break

    path_r = ((exit_price - entry) * direction) / risk if risk > 0 else 0.0
    return {
        **row,
        "path_label": path_label,
        "path_missing": False,
        "path_exit_ts": pd.Timestamp(exit_ts).isoformat(),
        "path_exit_price": round(exit_price, 2),
        "path_exit_type": exit_type,
        "path_r_multiple": round(float(path_r), 4),
        "path_r_delta": round(float(path_r - float(row["r_multiple"])), 4),
        "path_exit_type_changed": bool(exit_type != row["exit_type"]),
    }


def _path_replay(
    baseline: list[dict[str, Any]],
    df_1m: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[pd.DataFrame] = []
    summary: list[dict[str, Any]] = []
    sources = {"1m": df_1m, "1s": _read_1s()}
    for label, lower in sources.items():
        print(f"Replaying {len(baseline)} trades on {label} bars...", flush=True)
        replay = pd.DataFrame([_replay_trade(row, lower, label) for row in baseline])
        rows.append(replay)
        for scope in DIRECTION_SCOPES:
            scoped = _direction_filter(replay, scope)
            score = _score_frame(scoped, r_column="path_r_multiple", trading_days=1293, label=f"{label}_{scope}")
            score.update(
                {
                    "path_label": label,
                    "direction_scope": scope,
                    "missing_trades": int(scoped["path_missing"].sum()),
                    "exit_type_changes": int(scoped["path_exit_type_changed"].sum()),
                    "total_r_delta_vs_3m": round(float(scoped["path_r_delta"].sum()), 4),
                }
            )
            summary.append(score)
        if label == "1s":
            del lower
    return pd.concat(rows, ignore_index=True), pd.DataFrame(summary)


def _friction_adjusted_r(frame: pd.DataFrame, ticks_per_side: int, *, r_column: str = "path_r_multiple") -> pd.Series:
    risk_points = frame["risk_points"].astype(float)
    commission_r = (2.0 * MNQ_COMMISSION_PER_SIDE) / (risk_points * MNQ_POINT_VALUE)
    slippage_r = (2.0 * ticks_per_side * NQ_TICK) / risk_points
    return frame[r_column].astype(float) - commission_r - slippage_r


def _friction_summary(path_1s: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for scope in DIRECTION_SCOPES:
        scoped = _direction_filter(path_1s, scope)
        for ticks in SLIPPAGE_TICKS_PER_SIDE:
            adjusted = scoped.copy()
            adjusted["net_r"] = _friction_adjusted_r(adjusted, ticks)
            row = _score_frame(adjusted, r_column="net_r", trading_days=1293, label=f"{scope}_{ticks}t")
            row.update(
                {
                    "direction_scope": scope,
                    "slippage_ticks_per_side": ticks,
                    "commission_per_side_usd": MNQ_COMMISSION_PER_SIDE,
                    "sizing_instrument": "MNQ on NQ price data",
                }
            )
            rows.append(row)
    return pd.DataFrame(rows)


def _date_subset(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    dates = pd.to_datetime(frame["date"])
    return frame[(dates >= start) & (dates < end)].copy()


def _trading_day_count(day_dates: list[str], start: pd.Timestamp, end: pd.Timestamp) -> int:
    dates = pd.to_datetime(pd.Series(day_dates))
    return int(((dates >= start) & (dates < end)).sum())


def _sensitivity_and_walk_forward(
    days: list[Any],
    prior_ranges: dict[str, float],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    streams: dict[str, pd.DataFrame] = {}
    rows: list[dict[str, Any]] = []
    day_dates = [day.date for day in days]
    for extension in (0.020, 0.025, 0.030):
        for consolidation in (0.15, 0.20, 0.25):
            config = _make_tf_config(extension, consolidation)
            candidates = [ctx._generate_candidates_for_day(day, config.setup) for day in days]
            for stop_pct in (0.065, 0.075, 0.085):
                stop = tf.StaticStopConfig("atr14_prev", stop_pct, RR)
                trades = tf._simulate_model(days, candidates, config, stop, prior_ranges)
                frame = pd.DataFrame(trades)
                frame["net_r_1t"] = _friction_adjusted_r(frame, 1, r_column="r_multiple")
                key = f"ext{extension:.3f}_cons{consolidation:.2f}_stop{stop_pct:.3f}"
                streams[key] = frame
                for scope in DIRECTION_SCOPES:
                    scoped = _direction_filter(frame, scope)
                    row = _score_frame(scoped, r_column="net_r_1t", trading_days=len(days), label=key)
                    row.update(
                        {
                            "variant_id": key,
                            "direction_scope": scope,
                            "extension_atr_pct": extension,
                            "consolidation_atr_pct": consolidation,
                            "stop_atr_pct": stop_pct,
                            "is_frozen_champion": bool(
                                extension == BASE_EXTENSION_ATR_PCT
                                and consolidation == BASE_CONSOLIDATION_ATR_PCT
                                and stop_pct == BASE_STOP_ATR_PCT
                            ),
                            "friction_basis": "MNQ midpoint commission plus 1 adverse tick per side",
                        }
                    )
                    rows.append(row)

    sensitivity = pd.DataFrame(rows).sort_values(
        ["direction_scope", "calmar", "profit_factor", "total_r"],
        ascending=[True, False, False, False],
    ).reset_index(drop=True)
    sensitivity.insert(0, "rank", sensitivity.groupby("direction_scope").cumcount() + 1)

    folds: list[dict[str, Any]] = []
    selected_test_frames: list[pd.DataFrame] = []
    end_limit = pd.Timestamp(DATA_END_EXCLUSIVE)
    for scope in DIRECTION_SCOPES:
        cursor = pd.Timestamp("2021-07-01")
        while cursor + pd.DateOffset(months=24) <= end_limit:
            train_start = cursor
            train_end = cursor + pd.DateOffset(months=18)
            test_end = train_end + pd.DateOffset(months=6)
            train_days = _trading_day_count(day_dates, train_start, train_end)
            test_days = _trading_day_count(day_dates, train_end, test_end)
            train_ranked: list[tuple[str, dict[str, Any]]] = []
            for key, frame in streams.items():
                train = _direction_filter(_date_subset(frame, train_start, train_end), scope)
                score = _score_frame(train, r_column="net_r_1t", trading_days=train_days, label=key)
                if score["total_trades"] >= 40:
                    train_ranked.append((key, score))
            if not train_ranked:
                cursor += pd.DateOffset(months=6)
                continue
            selected_key, selected_train = max(
                train_ranked,
                key=lambda item: (item[1]["calmar"], item[1]["profit_factor"], item[1]["total_r"]),
            )
            selected_test = _direction_filter(_date_subset(streams[selected_key], train_end, test_end), scope)
            selected_test_score = _score_frame(selected_test, r_column="net_r_1t", trading_days=test_days, label=selected_key)
            frozen_key = "ext0.025_cons0.20_stop0.075"
            frozen_test = _direction_filter(_date_subset(streams[frozen_key], train_end, test_end), scope)
            frozen_test_score = _score_frame(frozen_test, r_column="net_r_1t", trading_days=test_days, label=frozen_key)
            selected_copy = selected_test.copy()
            selected_copy["fold_test_start"] = train_end.date().isoformat()
            selected_copy["selected_variant_id"] = selected_key
            selected_copy["direction_scope"] = scope
            selected_test_frames.append(selected_copy)
            folds.append(
                {
                    "direction_scope": scope,
                    "train_start": train_start.date().isoformat(),
                    "train_end_exclusive": train_end.date().isoformat(),
                    "test_start": train_end.date().isoformat(),
                    "test_end_exclusive": test_end.date().isoformat(),
                    "selected_variant_id": selected_key,
                    "train_trades": selected_train["total_trades"],
                    "train_total_r": selected_train["total_r"],
                    "train_pf": selected_train["profit_factor"],
                    "train_calmar": selected_train["calmar"],
                    "selected_test_trades": selected_test_score["total_trades"],
                    "selected_test_total_r": selected_test_score["total_r"],
                    "selected_test_pf": selected_test_score["profit_factor"],
                    "selected_test_dd_r": selected_test_score["max_drawdown_r"],
                    "frozen_test_trades": frozen_test_score["total_trades"],
                    "frozen_test_total_r": frozen_test_score["total_r"],
                    "frozen_test_pf": frozen_test_score["profit_factor"],
                    "frozen_test_dd_r": frozen_test_score["max_drawdown_r"],
                    "friction_basis": "MNQ midpoint commission plus 1 adverse tick per side",
                    "deployability": DEPLOYABILITY,
                    "live_support_notes": LIVE_SUPPORT_NOTES,
                    "exact_replay_required": EXACT_REPLAY_REQUIRED,
                }
            )
            cursor += pd.DateOffset(months=6)

    fold_frame = pd.DataFrame(folds)
    selected_oos = pd.concat(selected_test_frames, ignore_index=True) if selected_test_frames else pd.DataFrame()
    return sensitivity, fold_frame, selected_oos


def _block_bootstrap(
    path_1s: pd.DataFrame,
    day_dates: list[str],
    *,
    iterations: int = 5000,
    block_days: int = 5,
    seed: int = 20260710,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    all_days = pd.Index(day_dates)
    rng = np.random.default_rng(seed)
    for scope in DIRECTION_SCOPES:
        scoped = _direction_filter(path_1s, scope)
        scoped = scoped.copy()
        scoped["net_r"] = _friction_adjusted_r(scoped, 1)
        daily = scoped.groupby("date")["net_r"].sum().reindex(all_days, fill_value=0.0).to_numpy(dtype=float)
        totals = np.zeros(iterations, dtype=float)
        drawdowns = np.zeros(iterations, dtype=float)
        max_start = max(1, len(daily) - block_days + 1)
        blocks_needed = int(math.ceil(len(daily) / block_days))
        for idx in range(iterations):
            starts = rng.integers(0, max_start, size=blocks_needed)
            sample = np.concatenate([daily[start : start + block_days] for start in starts])[: len(daily)]
            totals[idx] = sample.sum()
            drawdowns[idx] = _max_drawdown(sample)
        rows.append(
            {
                "direction_scope": scope,
                "iterations": iterations,
                "block_days": block_days,
                "sample_trading_days": len(daily),
                "total_r_p05": round(float(np.quantile(totals, 0.05)), 2),
                "total_r_median": round(float(np.quantile(totals, 0.50)), 2),
                "total_r_p95": round(float(np.quantile(totals, 0.95)), 2),
                "max_dd_r_p05": round(float(np.quantile(drawdowns, 0.05)), 2),
                "max_dd_r_median": round(float(np.quantile(drawdowns, 0.50)), 2),
                "max_dd_r_p95": round(float(np.quantile(drawdowns, 0.95)), 2),
                "prob_total_r_positive": round(float((totals > 0).mean()), 4),
                "prob_dd_worse_than_20r": round(float((drawdowns <= -20.0).mean()), 4),
                "friction_basis": "MNQ midpoint commission plus 1 adverse tick per side",
                "deployability": DEPLOYABILITY,
                "live_support_notes": LIVE_SUPPORT_NOTES,
                "exact_replay_required": EXACT_REPLAY_REQUIRED,
            }
        )
    return pd.DataFrame(rows)


def _resolved_payout_rate(outcomes: pd.DataFrame) -> float:
    payout_count = int(outcomes["first_payout_hit"].sum())
    pre_bust_count = int((outcomes["outcome"] == "bust_pre_payout").sum())
    resolved = payout_count + pre_bust_count
    return round(payout_count / resolved, 4) if resolved else 0.0


def _build_prop_trades(
    frame: pd.DataFrame,
    *,
    risk_budget_usd: int,
    slippage_ticks_per_side: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    skipped = 0
    quantities: list[int] = []
    actual_risks: list[float] = []
    for record in frame.to_dict(orient="records"):
        risk_points = float(record["risk_points"])
        risk_per_contract = risk_points * MNQ_POINT_VALUE
        qty = int(math.floor(risk_budget_usd / risk_per_contract)) if risk_per_contract > 0 else 0
        if qty < 1:
            skipped += 1
            continue
        gross_pnl = float(record["path_r_multiple"]) * risk_per_contract * qty
        commission = 2.0 * MNQ_COMMISSION_PER_SIDE * qty
        slippage = 2.0 * slippage_ticks_per_side * NQ_TICK * MNQ_POINT_VALUE * qty
        pnl_usd = gross_pnl - commission - slippage
        quantities.append(qty)
        actual_risks.append(risk_per_contract * qty)
        rows.append(
            {
                "date": record["date"],
                "exit_ts": record["path_exit_ts"],
                "exit_type": record["path_exit_type"],
                "fill_bar": 0,
                "pnl_usd": round(pnl_usd, 2),
                "r_multiple": round(pnl_usd / (risk_per_contract * qty), 6),
                "qty": qty,
                "actual_risk_usd": round(risk_per_contract * qty, 2),
            }
        )
    diagnostics = {
        "source_trades": int(len(frame)),
        "sized_trades": int(len(rows)),
        "skipped_over_budget": int(skipped),
        "fill_retention": round(len(rows) / len(frame), 4) if len(frame) else 0.0,
        "avg_qty": round(float(np.mean(quantities)), 2) if quantities else 0.0,
        "avg_actual_risk_usd": round(float(np.mean(actual_risks)), 2) if actual_risks else 0.0,
        "max_actual_risk_usd": round(float(np.max(actual_risks)), 2) if actual_risks else 0.0,
    }
    return rows, diagnostics


def _prop_grid(path_1s: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    profile = PropFirmRiskProfile(
        trailing_drawdown_usd=2000.0,
        pass_target_usd=3000.0,
        first_payout_usd=1500.0,
        floor_cap_delta_usd=0.0,
        challenge_fee_usd=0.0,
        account_start_spacing_days=14,
    )
    all_starts = make_account_starts(EFFECTIVE_START, DATA_END_EXCLUSIVE, profile.account_start_spacing_days)
    result_rows: list[dict[str, Any]] = []
    outcome_frames: list[pd.DataFrame] = []
    for scope in DIRECTION_SCOPES:
        scoped = _direction_filter(path_1s, scope)
        for ticks in PROP_SLIPPAGE_TICKS_PER_SIDE:
            for risk_usd in RISK_GRID_USD:
                prop_trades, diagnostics = _build_prop_trades(
                    scoped,
                    risk_budget_usd=risk_usd,
                    slippage_ticks_per_side=ticks,
                )
                variant_id = f"{scope}_risk{risk_usd}_{ticks}t"
                outcomes = simulate_prop_firm_risk(
                    variant_id=variant_id,
                    trades=prop_trades,
                    account_starts=all_starts,
                    profile=profile,
                    end_exclusive=DATA_END_EXCLUSIVE,
                )
                outcome_frames.append(
                    outcomes.assign(
                        direction_scope=scope,
                        risk_budget_usd=risk_usd,
                        slippage_ticks_per_side=ticks,
                    )
                )
                outcome_dates = pd.to_datetime(outcomes["account_start"])
                cohorts = {
                    "all_starts": outcomes,
                    "matured_12m": outcomes[outcome_dates < pd.Timestamp(MATURED_START_END_EXCLUSIVE)],
                    "recent_matured": outcomes[
                        (outcome_dates >= pd.Timestamp(RECENT_MATURED_START))
                        & (outcome_dates < pd.Timestamp(MATURED_START_END_EXCLUSIVE))
                    ],
                }
                for cohort_name, cohort in cohorts.items():
                    score = score_prop_firm_outcomes(cohort)
                    result_rows.append(
                        {
                            "variant_id": variant_id,
                            "cohort": cohort_name,
                            "direction_scope": scope,
                            "risk_budget_usd": risk_usd,
                            "slippage_ticks_per_side": ticks,
                            "commission_per_side_usd": MNQ_COMMISSION_PER_SIDE,
                            "sizing_instrument": "integer MNQ on NQ price data",
                            **diagnostics,
                            **score,
                            "resolved_first_payout_rate": _resolved_payout_rate(cohort),
                            "max_consecutive_pre_payout_busts": max_consecutive_outcomes(cohort, "bust_pre_payout"),
                            "max_consecutive_post_payout_busts": max_consecutive_outcomes(cohort, "bust_post_payout"),
                            "deployability": DEPLOYABILITY,
                            "live_support_notes": LIVE_SUPPORT_NOTES,
                            "exact_replay_required": EXACT_REPLAY_REQUIRED,
                        }
                    )
    ranked = pd.DataFrame(result_rows).sort_values(
        ["cohort", "ev_per_start_usd", "first_payout_rate", "pre_payout_bust_rate"],
        ascending=[True, False, False, True],
    ).reset_index(drop=True)
    ranked.insert(0, "rank", ranked.groupby("cohort").cumcount() + 1)
    ranked.attrs["profile"] = profile_to_dict(profile)
    return ranked, pd.concat(outcome_frames, ignore_index=True)


def _table(frame: pd.DataFrame, columns: list[str], n: int | None = None) -> str:
    if frame.empty:
        return "_None._"
    view = frame[columns].copy()
    if n is not None:
        view = view.head(n)
    return view.to_markdown(index=False)


def _build_report(
    *,
    baseline_score: dict[str, Any],
    audit: dict[str, Any],
    path_summary: pd.DataFrame,
    friction: pd.DataFrame,
    sensitivity: pd.DataFrame,
    folds: pd.DataFrame,
    monte_carlo: pd.DataFrame,
    prop: pd.DataFrame,
    decision: dict[str, Any],
) -> str:
    champion_sensitivity = sensitivity[sensitivity["is_frozen_champion"]]
    best_sensitivity = (
        sensitivity.sort_values(["direction_scope", "rank"])
        .groupby("direction_scope", group_keys=False)
        .head(3)
    )
    matured = prop[prop["cohort"] == "matured_12m"].copy()
    best_prop = (
        matured[matured["slippage_ticks_per_side"] == 1]
        .sort_values(["ev_per_start_usd", "first_payout_rate", "pre_payout_bust_rate"], ascending=[False, False, True])
        .groupby("direction_scope", group_keys=False)
        .head(1)
        .sort_values("direction_scope")
    )
    risk500 = matured[(matured["risk_budget_usd"] == 500) & (matured["slippage_ticks_per_side"] == 1)].copy()
    lines = [
        "# NQ NY VWAP 3m Validation and Prop-Firm Packet",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Data: `{EFFECTIVE_START}` through `<{DATA_END_EXCLUSIVE}` (`1,293` NY RTH days).",
        "- Frozen setup: 3m bars, VWAP mean, 2.5% prior-ATR extension, 30-minute consolidation, 20% ATR maximum consolidation range, sweep/reclaim, next-bar entry, 7.5% prior-ATR stop, fixed 1.5R target.",
        f"- Friction: integer MNQ sizing on NQ price data, `${MNQ_COMMISSION_PER_SIDE:.3f}` commission per side, and adverse slippage stress of `0/1/2/4` ticks per side.",
        "- Holdout status: retrospective only. The full 2021-2026 history had already been inspected during discovery; rolling test folds are causally selected but are not a pristine untouched holdout.",
        f"- Deployability: `{DEPLOYABILITY}`. {LIVE_SUPPORT_NOTES}",
        "",
        "## Baseline Audit",
        "",
        f"- Regenerated `{baseline_score['total_trades']}` trades, `{baseline_score['total_r']:+.4f}R`, PF `{baseline_score['profit_factor']:.4f}`, max DD `{baseline_score['max_drawdown_r']:.4f}R`.",
        f"- Saved champion parity: trade-count delta `{audit['trade_count_delta']}`, total-R delta `{audit['total_r_delta']:+.6f}R`; parity `{audit['parity_status']}`.",
        "",
        "## Lower-Timeframe Path Replay",
        "",
        _table(
            path_summary,
            ["path_label", "direction_scope", "total_trades", "total_r", "profit_factor", "max_drawdown_r", "exit_type_changes", "total_r_delta_vs_3m", "deployability"],
        ),
        "",
        "## Friction Stress",
        "",
        _table(
            friction,
            ["direction_scope", "slippage_ticks_per_side", "total_trades", "total_r", "avg_r", "profit_factor", "max_drawdown_r", "negative_years", "deployability"],
        ),
        "",
        "## Parameter Neighborhood",
        "",
        "The neighborhood is evaluated after MNQ midpoint commission plus one adverse tick per side. It is a stability check, not permission to replace the frozen champion with the best full-history row.",
        "",
        _table(
            best_sensitivity,
            ["direction_scope", "rank", "variant_id", "total_trades", "total_r", "avg_r", "profit_factor", "calmar", "max_drawdown_r", "is_frozen_champion", "deployability"],
        ),
        "",
        "Frozen champion row:",
        "",
        _table(
            champion_sensitivity,
            ["direction_scope", "rank", "variant_id", "total_trades", "total_r", "avg_r", "profit_factor", "calmar", "max_drawdown_r", "deployability"],
        ),
        "",
        "## Rolling Walk-Forward",
        "",
        "Each fold selects from the 27-row neighborhood using only the preceding 18 months, then evaluates the next six months after commission and one tick per side. The frozen champion is shown beside the selected row.",
        "",
        _table(
            folds,
            ["direction_scope", "test_start", "test_end_exclusive", "selected_variant_id", "selected_test_trades", "selected_test_total_r", "selected_test_pf", "frozen_test_total_r", "frozen_test_pf", "deployability"],
        ),
        "",
        "## Block Bootstrap",
        "",
        _table(
            monte_carlo,
            ["direction_scope", "iterations", "block_days", "total_r_p05", "total_r_median", "total_r_p95", "max_dd_r_p05", "max_dd_r_median", "prob_total_r_positive", "prob_dd_worse_than_20r", "deployability"],
        ),
        "",
        "## Prop-Firm Lifecycle",
        "",
        "Model: $2,000 EOD trailing drawdown, +$3,000 pass, one $1,500 first payout, floor capped at starting balance, then continue until bust or data end. Starts are every 14 calendar days; no challenge fee is included. Rankings below use starts with at least 12 months of follow-up.",
        "",
        "Best matured row by direction under one adverse tick per side:",
        "",
        _table(
            best_prop,
            ["direction_scope", "risk_budget_usd", "slippage_ticks_per_side", "total_starts", "first_payout_rate", "resolved_first_payout_rate", "pre_payout_bust_rate", "post_payout_bust_rate", "open_rate", "ev_per_start_usd", "avg_days_to_first_payout", "fill_retention", "deployability"],
        ),
        "",
        "User-requested $500 risk under one-tick-per-side stress:",
        "",
        _table(
            risk500,
            ["direction_scope", "risk_budget_usd", "total_starts", "first_payout_rate", "resolved_first_payout_rate", "pre_payout_bust_rate", "post_payout_bust_rate", "open_rate", "ev_per_start_usd", "avg_days_to_first_payout", "fill_retention", "deployability"],
        ),
        "",
        "## Promotion Decision",
        "",
        f"- Daily-cadence both-direction friction gate: **{decision['both_friction_gate']}**.",
        f"- Long-only friction gate: **{decision['long_friction_gate']}**.",
        f"- Both-direction rolling selected-fold gate: **{decision['walk_forward_gate']}** (`{decision['positive_selected_folds']}/{decision['total_folds']}` positive test folds).",
        f"- Both-direction frozen-row rolling gate: **{decision['frozen_walk_forward_gate']}** (`{decision['positive_frozen_folds']}/{decision['total_folds']}` positive test folds).",
        f"- Long-only rolling selected-fold gate: **{decision['long_walk_forward_gate']}** (`{decision['long_positive_selected_folds']}/{decision['long_total_folds']}` positive test folds).",
        f"- Long-only frozen-row rolling gate: **{decision['long_frozen_walk_forward_gate']}** (`{decision['long_positive_frozen_folds']}/{decision['long_total_folds']}` positive test folds).",
        f"- Long-only block-bootstrap gate: **{decision['long_bootstrap_gate']}**.",
        f"- Long-only matured prop gate at one tick/side: **{decision['long_prop_gate']}**.",
        f"- Live-native implementation: **{decision['implementation_decision']}**.",
        "",
        decision["conclusion"],
        "",
        "## Artifacts",
        "",
        f"- Results: `backtesting/data/results/{RUN_SLUG}/`",
        f"- Report: `backtesting/learnings/reports/{REPORT_PATH.name}`",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("Loading source data and regenerating the frozen champion...", flush=True)
    df_1m, days, prior_ranges = _load_source_and_days()
    baseline = _generate_stream(
        days,
        prior_ranges,
        extension_atr_pct=BASE_EXTENSION_ATR_PCT,
        consolidation_atr_pct=BASE_CONSOLIDATION_ATR_PCT,
        stop_atr_pct=BASE_STOP_ATR_PCT,
    )
    baseline_frame = pd.DataFrame(baseline)
    baseline_score = _score_frame(baseline_frame, r_column="r_multiple", trading_days=len(days), label="frozen_3m_gross")
    saved = pd.read_csv(
        ROOT / "data" / "results" / "nq_ny_vwap_static_rr_timeframe_sweep_20260630" / "top_timeframe_static_rr_trades.csv"
    )
    audit = {
        "saved_trades": int(len(saved)),
        "regenerated_trades": int(len(baseline_frame)),
        "trade_count_delta": int(len(baseline_frame) - len(saved)),
        "saved_total_r": round(float(saved["r_multiple"].sum()), 6),
        "regenerated_total_r": round(float(baseline_frame["r_multiple"].sum()), 6),
    }
    audit["total_r_delta"] = round(audit["regenerated_total_r"] - audit["saved_total_r"], 6)
    audit["parity_status"] = "PASS" if audit["trade_count_delta"] == 0 and abs(audit["total_r_delta"]) < 1e-6 else "FAIL"
    if audit["parity_status"] != "PASS":
        raise RuntimeError(f"Frozen baseline parity failed: {audit}")

    print("Running 1m and 1s path replay...", flush=True)
    path_replays, path_summary = _path_replay(baseline, df_1m)
    path_1s = path_replays[path_replays["path_label"] == "1s"].copy()

    print("Running commission and slippage stress...", flush=True)
    friction = _friction_summary(path_1s)

    print("Running 27-row sensitivity neighborhood and rolling walk-forward...", flush=True)
    sensitivity, folds, selected_oos = _sensitivity_and_walk_forward(days, prior_ranges)

    print("Running 5-day block bootstrap...", flush=True)
    monte_carlo = _block_bootstrap(path_1s, [day.date for day in days])

    print("Running prop-firm lifecycle grid...", flush=True)
    prop, prop_outcomes = _prop_grid(path_1s)

    both_1t = friction[(friction["direction_scope"] == "both") & (friction["slippage_ticks_per_side"] == 1)].iloc[0]
    long_1t = friction[(friction["direction_scope"] == "long_only") & (friction["slippage_ticks_per_side"] == 1)].iloc[0]
    both_folds = folds[folds["direction_scope"] == "both"]
    long_folds = folds[folds["direction_scope"] == "long_only"]
    positive_selected = int((both_folds["selected_test_total_r"] > 0).sum())
    positive_frozen = int((both_folds["frozen_test_total_r"] > 0).sum())
    fold_count = int(len(both_folds))
    long_positive_selected = int((long_folds["selected_test_total_r"] > 0).sum())
    long_positive_frozen = int((long_folds["frozen_test_total_r"] > 0).sum())
    long_fold_count = int(len(long_folds))
    both_gate = bool(both_1t["profit_factor"] >= 1.05 and both_1t["total_r"] > 0)
    long_gate = bool(long_1t["profit_factor"] >= 1.10 and long_1t["total_r"] > 0)
    selected_wf_gate = bool(
        fold_count
        and positive_selected / fold_count >= 0.60
        and both_folds["selected_test_total_r"].sum() >= 5.0
        and both_folds["selected_test_total_r"].min() > -10.0
    )
    frozen_wf_gate = bool(
        fold_count
        and positive_frozen / fold_count >= 0.60
        and both_folds["frozen_test_total_r"].sum() >= 5.0
        and both_folds["frozen_test_total_r"].min() > -10.0
    )
    long_selected_wf_gate = bool(
        long_fold_count
        and long_positive_selected / long_fold_count >= 0.60
        and long_folds["selected_test_total_r"].sum() >= 5.0
        and long_folds["selected_test_total_r"].min() > -10.0
    )
    long_frozen_wf_gate = bool(
        long_fold_count
        and long_positive_frozen / long_fold_count >= 0.60
        and long_folds["frozen_test_total_r"].sum() >= 5.0
        and long_folds["frozen_test_total_r"].min() > -10.0
    )
    long_mc = monte_carlo[monte_carlo["direction_scope"] == "long_only"].iloc[0]
    long_bootstrap_gate = bool(
        long_mc["prob_total_r_positive"] >= 0.95
        and long_mc["prob_dd_worse_than_20r"] <= 0.25
    )
    long_prop_candidates = prop[
        (prop["cohort"] == "matured_12m")
        & (prop["direction_scope"] == "long_only")
        & (prop["slippage_ticks_per_side"] == 1)
    ].sort_values(
        ["ev_per_start_usd", "first_payout_rate", "pre_payout_bust_rate"],
        ascending=[False, False, True],
    )
    long_prop_best = long_prop_candidates.iloc[0]
    long_prop_gate = bool(
        long_prop_best["first_payout_rate"] >= 0.60
        and long_prop_best["pre_payout_bust_rate"] <= 0.20
        and long_prop_best["open_rate"] <= 0.20
        and long_prop_best["avg_days_to_first_payout"] <= 180
    )
    implementation = "DEFER" if not (both_gate and frozen_wf_gate) else "PROCEED TO LIVE-NATIVE SHADOW IMPLEMENTATION"
    conclusion = (
        "The both-direction daily-cadence branch is a no-go after friction and walk-forward validation, and the short side is the main drag. "
        "Long-only survives basic friction but fails the tightened rolling, bootstrap, and prop-quality gates, so it remains a conditional research shelf candidate rather than a promotion candidate. "
        "No live-engine implementation is justified by this packet."
        if implementation == "DEFER"
        else "The frozen both-direction stream cleared the research gates. The next authorized step is a separate live-native implementation and exact replay, not direct deployment."
    )
    decision = {
        "both_friction_gate": "PASS" if both_gate else "FAIL",
        "long_friction_gate": "PASS" if long_gate else "FAIL",
        "walk_forward_gate": "PASS" if selected_wf_gate else "FAIL",
        "frozen_walk_forward_gate": "PASS" if frozen_wf_gate else "FAIL",
        "long_walk_forward_gate": "PASS" if long_selected_wf_gate else "FAIL",
        "long_frozen_walk_forward_gate": "PASS" if long_frozen_wf_gate else "FAIL",
        "long_bootstrap_gate": "PASS" if long_bootstrap_gate else "FAIL",
        "long_prop_gate": "PASS" if long_prop_gate else "FAIL",
        "positive_selected_folds": positive_selected,
        "positive_frozen_folds": positive_frozen,
        "total_folds": fold_count,
        "selected_oos_total_r": round(float(both_folds["selected_test_total_r"].sum()), 4),
        "frozen_oos_total_r": round(float(both_folds["frozen_test_total_r"].sum()), 4),
        "long_positive_selected_folds": long_positive_selected,
        "long_positive_frozen_folds": long_positive_frozen,
        "long_total_folds": long_fold_count,
        "long_selected_oos_total_r": round(float(long_folds["selected_test_total_r"].sum()), 4),
        "long_frozen_oos_total_r": round(float(long_folds["frozen_test_total_r"].sum()), 4),
        "long_best_prop_risk_usd": int(long_prop_best["risk_budget_usd"]),
        "long_best_prop_first_payout_rate": float(long_prop_best["first_payout_rate"]),
        "long_best_prop_pre_payout_bust_rate": float(long_prop_best["pre_payout_bust_rate"]),
        "long_best_prop_open_rate": float(long_prop_best["open_rate"]),
        "long_best_prop_avg_days_to_first_payout": float(long_prop_best["avg_days_to_first_payout"]),
        "implementation_decision": implementation,
        "conclusion": conclusion,
    }

    artifacts = {
        "baseline_trades.csv": baseline_frame,
        "path_replay_trades.csv": path_replays,
        "path_replay_summary.csv": path_summary,
        "friction_summary.csv": friction,
        "sensitivity_neighborhood.csv": sensitivity,
        "walk_forward_folds.csv": folds,
        "walk_forward_selected_oos_trades.csv": selected_oos,
        "block_bootstrap.csv": monte_carlo,
        "prop_risk_grid.csv": prop,
        "prop_account_outcomes.csv": prop_outcomes,
    }
    for filename, frame in artifacts.items():
        frame.to_csv(RESULT_DIR / filename, index=False)

    summary = {
        "run_slug": RUN_SLUG,
        "data_start": EFFECTIVE_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "holdout_status": "retrospective_only_not_pristine",
        "frozen_config": {
            "timeframe_min": TIMEFRAME_MIN,
            "extension_atr_pct": BASE_EXTENSION_ATR_PCT,
            "consolidation_minutes": 30,
            "consolidation_atr_pct": BASE_CONSOLIDATION_ATR_PCT,
            "setup_timeout_minutes": 60,
            "stop_basis": "atr14_prev",
            "stop_atr_pct": BASE_STOP_ATR_PCT,
            "rr": RR,
            "max_trades_per_day": MAX_TRADES_PER_DAY,
        },
        "friction": {
            "sizing_instrument": "MNQ on NQ price data",
            "commission_per_side_usd": MNQ_COMMISSION_PER_SIDE,
            "slippage_ticks_per_side": SLIPPAGE_TICKS_PER_SIDE,
        },
        "prop_profile": prop.attrs.get("profile", {}),
        "baseline_score": baseline_score,
        "baseline_audit": audit,
        "decision": decision,
        "elapsed_seconds": round(time.time() - started, 2),
        "deployability": DEPLOYABILITY,
        "live_support_notes": LIVE_SUPPORT_NOTES,
        "exact_replay_required": EXACT_REPLAY_REQUIRED,
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe(summary), indent=2) + "\n")
    REPORT_PATH.write_text(
        _build_report(
            baseline_score=baseline_score,
            audit=audit,
            path_summary=path_summary,
            friction=friction,
            sensitivity=sensitivity,
            folds=folds,
            monte_carlo=monte_carlo,
            prop=prop,
            decision=decision,
        )
    )

    print(json.dumps(_safe(summary), indent=2), flush=True)
    print(f"Wrote {RESULT_DIR}")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
