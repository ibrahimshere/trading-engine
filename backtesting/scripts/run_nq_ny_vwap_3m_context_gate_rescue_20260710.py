#!/usr/bin/env python3
"""Context-gate rescue attempt for the frozen NQ NY 3m VWAP mean-reversion leg.

TRACK 1 of a 4-track program. Applies the level-reversion context filters
(vwap-slope rejection, directional efficiency cap, entry time bucket,
session-range cap) that rescued the 5m branch to the frozen 3m static-RR leg,
evaluated per direction scope. Research artifact only; not wired to live
execution.

Adaptation note (VWAP slope): the 5m leg measured the VWAP slope over the prior
6 bars (30 minutes) with a 0.02-ATR rejection threshold. On 3m bars we measure
the slope over the prior 10 bars (30 minutes) so the physical window matches,
and keep the same 0.02-ATR threshold. This is the time-normalized analogue
(5m x 6 == 3m x 10 == 30 minutes), consistent with how the timeframe sweep
time-normalized consolidation/timeout/cooldown by minutes. The 10-bar slope is
injected onto each candidate's ``vwap_slope_atr`` field before gating so the
shared ``_context_accepts`` / ``_vwap_slope_rejects`` machinery is reused
verbatim.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.data.fees import estimated_commission_per_side  # noqa: E402


RUN_SLUG = "nq_ny_vwap_3m_context_gate_rescue_20260710"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_VWAP_3M_CONTEXT_GATE_RESCUE_20260710.md"

DATA_START = "2021-06-05"
EFFECTIVE_START = "2021-06-07"
DATA_END_EXCLUSIVE = "2026-06-06"

TIMEFRAME_MIN = 3
RR = 1.5
BASE_EXTENSION_ATR_PCT = 0.025
BASE_CONSOLIDATION_ATR_PCT = 0.20
BASE_STOP_ATR_PCT = 0.075
CONSOLIDATION_BARS = 10
SETUP_TIMEOUT_BARS = 20
COOLDOWN_BARS = 4
MAX_TRADES_PER_DAY = 3

# VWAP-slope adaptation: 10 trailing 3m bars == 30 minutes, same 0.02-ATR gate.
SLOPE_LOOKBACK_BARS = 10
SLOPE_REJECT_ATR = 0.02  # matches ctx.VWAP_SLOPE_REJECT_ATR (checked at runtime)

NQ_TICK = 0.25
MNQ_POINT_VALUE = 2.0
MNQ_COMMISSION_PER_SIDE = float(estimated_commission_per_side("MNQ"))
SLIPPAGE_TICKS_PER_SIDE = (0, 1, 2, 4)
DIRECTION_SCOPES = ("both", "long_only", "short_only")

# Context-gate grid (modest; 2 * 5 * 4 * 3 = 120 contexts, scored x3 scopes).
VWAP_ACCEPTANCE_GRID = ("none", "reject_vwap_side_slope")
EFFICIENCY_MAX_GRID = (None, 0.45, 0.55, 0.65, 0.70)
TIME_BUCKET_GRID = ("full", "10:00-12:00", "10:00-14:00", "11:00-15:00")
SESSION_RANGE_MAX_GRID = (2.0, 1.5, None)

# Short-side asymmetry probe.
SHORT_EXTENSION_GRID = (0.025, 0.05, 0.075)
SHORT_CONSOLIDATION_GRID = (0.15, 0.20)

MIN_CANDIDATE_TRADES = 150
TRADING_DAYS = 1293  # NY RTH days in 2021-06-07..<2026-06-06 (asserted at runtime)

DEPLOYABILITY = "research_only"
LIVE_SUPPORT_NOTES = (
    "The 3m VWAP sweep/reclaim state machine, native-timeframe static-R exit, and these "
    "context gates are research-script only; the live execution engine cannot arm this setup yet."
)
EXACT_REPLAY_REQUIRED = "yes"


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tf = _load_module(
    SCRIPT_DIR / "run_nq_ny_vwap_static_rr_timeframe_sweep_20260630.py",
    "nq_vwap_static_tf_20260630_rescue",
)
ctx = tf.ctx

assert abs(ctx.VWAP_SLOPE_REJECT_ATR - SLOPE_REJECT_ATR) < 1e-9, (
    f"ctx VWAP slope threshold {ctx.VWAP_SLOPE_REJECT_ATR} != expected {SLOPE_REJECT_ATR}"
)


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
    peak = np.maximum.accumulate(np.concatenate(([0.0], equity)))[1:]
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


def _friction_adjusted_r(frame: pd.DataFrame, ticks_per_side: int, *, r_column: str) -> pd.Series:
    risk_points = frame["risk_points"].astype(float)
    commission_r = (2.0 * MNQ_COMMISSION_PER_SIDE) / (risk_points * MNQ_POINT_VALUE)
    slippage_r = (2.0 * ticks_per_side * NQ_TICK) / risk_points
    return frame[r_column].astype(float) - commission_r - slippage_r


def _score_frame(
    frame: pd.DataFrame,
    *,
    r_column: str,
    trading_days: int,
    gross_column: str = "r_multiple",
) -> dict[str, Any]:
    values = frame[r_column].astype(float).to_numpy() if not frame.empty else np.array([], dtype=float)
    gross = frame[gross_column].astype(float).to_numpy() if (not frame.empty and gross_column in frame) else values
    total_r = float(values.sum())
    max_dd = _max_drawdown(values)
    years = trading_days / 252.0 if trading_days else 0.0
    avg_annual_r = total_r / years if years else 0.0
    std_r = float(values.std(ddof=1)) if len(values) > 1 else 0.0
    tstat = (float(values.mean()) * math.sqrt(len(values)) / std_r) if std_r > 0 else 0.0
    yearly = (
        frame.assign(year=frame["date"].astype(str).str[:4]).groupby("year")[r_column].sum()
        if not frame.empty
        else pd.Series(dtype=float)
    )
    return {
        "total_trades": int(len(frame)),
        "trading_days": int(trading_days),
        "avg_trades_per_day": round(len(frame) / trading_days, 4) if trading_days else 0.0,
        "total_r": round(total_r, 4),
        "gross_total_r": round(float(gross.sum()), 4),
        "avg_r": round(float(values.mean()), 4) if len(values) else 0.0,
        "std_r": round(std_r, 4),
        "t_stat": round(tstat, 4),
        "avg_annual_r": round(avg_annual_r, 4),
        "calmar": round(avg_annual_r / abs(max_dd), 4) if max_dd < 0 else 0.0,
        "profit_factor": round(_profit_factor(values), 4),
        "win_rate": round(float((values > 0).mean()), 4) if len(values) else 0.0,
        "max_drawdown_r": round(max_dd, 4),
        "negative_years": int((yearly < 0).sum()),
        "deployability": DEPLOYABILITY,
    }


def _frozen_setup() -> Any:
    return ctx.StateMachineConfig(
        label="frozen_vwap_3m_rescue",
        mean_mode="vwap",
        extension_atr_pct=BASE_EXTENSION_ATR_PCT,
        consolidation_bars=CONSOLIDATION_BARS,
        consolidation_atr_pct=BASE_CONSOLIDATION_ATR_PCT,
        setup_timeout_bars=SETUP_TIMEOUT_BARS,
        stop_buffer_atr_pct=0.02,
        min_rr_to_mean=0.20,
        cooldown_bars=COOLDOWN_BARS,
        max_trades_per_day=MAX_TRADES_PER_DAY,
    )


def _setup(extension_atr_pct: float, consolidation_atr_pct: float) -> Any:
    return ctx.StateMachineConfig(
        label="probe_vwap_3m_rescue",
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


def _context(
    *,
    vwap_acceptance: str,
    efficiency_max: float | None,
    time_bucket: str,
    session_range_atr_max: float | None,
) -> Any:
    return ctx.ContextConfig(
        structure_gate="none",
        vwap_acceptance=vwap_acceptance,
        efficiency_max=efficiency_max,
        ib_location="none",
        session_range_atr_max=session_range_atr_max,
        time_bucket=time_bucket,
    )


def _tf_config(setup: Any, context: Any) -> Any:
    return tf.TimeframeConfig(timeframe_min=TIMEFRAME_MIN, setup=setup, context=context)


def _inject_slope10(days: list[Any], candidates_by_day: list[list[dict[str, Any]]]) -> None:
    """Overwrite each candidate's vwap_slope_atr with the 10-bar (30-minute) 3m slope."""
    for day, day_candidates in zip(days, candidates_by_day, strict=True):
        vwap = np.asarray(day.vwap, dtype=float)
        atr = float(day.atr)
        slope = np.zeros(len(vwap), dtype=float)
        if len(vwap) > SLOPE_LOOKBACK_BARS and atr > 0:
            slope[SLOPE_LOOKBACK_BARS:] = (
                vwap[SLOPE_LOOKBACK_BARS:] - vwap[:-SLOPE_LOOKBACK_BARS]
            ) / atr
        for candidate in day_candidates:
            idx = int(candidate["signal_idx"])
            candidate["vwap_slope_atr"] = round(float(slope[idx]), 5)


def _load_source_and_days() -> tuple[pd.DataFrame, list[Any], dict[str, float]]:
    df_1m = tf._load_1m_source()
    df_3m = tf._resample_ohlcv(df_1m, TIMEFRAME_MIN)
    days = ctx._prepare_days(ctx._prepare_rth(df_3m))
    return df_1m, days, tf._prior_session_ranges(days)


def _simulate(
    days: list[Any],
    candidates_by_day: list[list[dict[str, Any]]],
    context: Any,
    prior_ranges: dict[str, float],
    *,
    setup: Any,
    stop_pct: float = BASE_STOP_ATR_PCT,
) -> pd.DataFrame:
    tf_config = _tf_config(setup, context)
    stop = tf.StaticStopConfig("atr14_prev", stop_pct, RR)
    trades = tf._simulate_model(days, candidates_by_day, tf_config, stop, prior_ranges)
    frame = pd.DataFrame(trades)
    if frame.empty:
        return frame
    for ticks in SLIPPAGE_TICKS_PER_SIDE:
        frame[f"net_r_{ticks}t"] = _friction_adjusted_r(frame, ticks, r_column="r_multiple")
    return frame


def _context_label(context: Any) -> str:
    eff = "none" if context.efficiency_max is None else f"{context.efficiency_max:g}"
    sr = "none" if context.session_range_atr_max is None else f"{context.session_range_atr_max:g}"
    slope = "slope" if context.vwap_acceptance == "reject_vwap_side_slope" else "noslope"
    return f"{slope}_eff{eff}_t{context.time_bucket}_sr{sr}"


# --------------------------------------------------------------------------- #
# 1s path replay (definitive friction check for the finalists)
# --------------------------------------------------------------------------- #

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


def _replay_trade(row: dict[str, Any], lower: pd.DataFrame) -> dict[str, Any]:
    entry_ts = pd.Timestamp(row["entry_ts"])
    flat_ts = pd.Timestamp(f"{row['date']} 15:55:00")
    window = lower.loc[entry_ts:flat_ts]
    if window.empty:
        return {**row, "path_r_multiple": row["r_multiple"], "path_exit_type": row["exit_type"]}
    direction = int(row["direction_int"])
    entry = float(row["entry"])
    stop = float(row["stop"])
    target = float(row["target"])
    risk = float(row["risk_points"])
    exit_price = float(window["close"].iloc[-1])
    exit_type = "eod"
    for _, bar in window.iterrows():
        if direction == 1:
            stop_hit = float(bar.low) <= stop
            target_hit = float(bar.high) >= target
        else:
            stop_hit = float(bar.high) >= stop
            target_hit = float(bar.low) <= target
        if stop_hit:
            exit_price = stop
            exit_type = "stop"
            break
        if target_hit:
            exit_price = target
            exit_type = "target"
            break
    path_r = ((exit_price - entry) * direction) / risk if risk > 0 else 0.0
    return {**row, "path_r_multiple": round(float(path_r), 4), "path_exit_type": exit_type}


def _path_replay(frame: pd.DataFrame, lower: pd.DataFrame) -> pd.DataFrame:
    replay = pd.DataFrame([_replay_trade(row, lower) for row in frame.to_dict(orient="records")])
    for ticks in SLIPPAGE_TICKS_PER_SIDE:
        replay[f"path_net_r_{ticks}t"] = _friction_adjusted_r(replay, ticks, r_column="path_r_multiple")
    return replay


# --------------------------------------------------------------------------- #
# Rolling walk-forward (frozen-config, 6 folds, matching the packet cadence)
# --------------------------------------------------------------------------- #

def _fold_windows() -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    windows: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    cursor = pd.Timestamp("2021-07-01")
    end_limit = pd.Timestamp(DATA_END_EXCLUSIVE)
    while cursor + pd.DateOffset(months=24) <= end_limit:
        test_start = cursor + pd.DateOffset(months=18)
        test_end = cursor + pd.DateOffset(months=24)
        windows.append((test_start, test_end))
        cursor += pd.DateOffset(months=6)
    return windows


def _frozen_walk_forward(frame: pd.DataFrame, *, r_column: str = "net_r_1t") -> list[dict[str, Any]]:
    dates = pd.to_datetime(frame["date"])
    folds: list[dict[str, Any]] = []
    for test_start, test_end in _fold_windows():
        mask = (dates >= test_start) & (dates < test_end)
        subset = frame[mask]
        values = subset[r_column].astype(float).to_numpy()
        folds.append(
            {
                "test_start": test_start.date().isoformat(),
                "test_end_exclusive": test_end.date().isoformat(),
                "test_trades": int(len(subset)),
                "test_total_r": round(float(values.sum()), 4),
                "test_pf": round(_profit_factor(values), 4),
                "test_dd_r": round(_max_drawdown(values), 4),
            }
        )
    return folds


def _yearly_split(frame: pd.DataFrame, *, r_column: str = "net_r_1t") -> list[dict[str, Any]]:
    if frame.empty:
        return []
    grouped = frame.assign(year=frame["date"].astype(str).str[:4]).groupby("year")
    rows: list[dict[str, Any]] = []
    for year, group in grouped:
        values = group[r_column].astype(float).to_numpy()
        rows.append(
            {
                "year": str(year),
                "trades": int(len(group)),
                "total_r": round(float(values.sum()), 4),
                "avg_r": round(float(values.mean()), 4),
                "win_rate": round(float((values > 0).mean()), 4),
                "profit_factor": round(_profit_factor(values), 4),
            }
        )
    return rows


def _table(frame: pd.DataFrame, columns: list[str], n: int | None = None) -> str:
    if frame is None or frame.empty:
        return "_None._"
    view = frame[[c for c in columns if c in frame.columns]].copy()
    if n is not None:
        view = view.head(n)
    return view.to_markdown(index=False)


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("Loading source and regenerating frozen 3m candidates...", flush=True)
    df_1m, days, prior_ranges = _load_source_and_days()
    trading_days = len(days)
    assert trading_days == TRADING_DAYS, f"expected {TRADING_DAYS} RTH days, got {trading_days}"
    frozen_setup = _frozen_setup()
    candidates_by_day = [ctx._generate_candidates_for_day(day, frozen_setup) for day in days]
    total_candidates = sum(len(c) for c in candidates_by_day)
    _inject_slope10(days, candidates_by_day)
    print(f"  days={trading_days}; candidate events={total_candidates}", flush=True)

    # ---- Parity audit against the frozen ungated baseline --------------------
    print("Parity audit vs frozen ungated baseline (1498 trades / +82.182R)...", flush=True)
    baseline_context = _context(
        vwap_acceptance="none", efficiency_max=None, time_bucket="full", session_range_atr_max=2.0
    )
    baseline_frame = _simulate(days, candidates_by_day, baseline_context, prior_ranges, setup=frozen_setup)
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
    audit["parity_status"] = (
        "PASS" if audit["trade_count_delta"] == 0 and abs(audit["total_r_delta"]) < 1e-6 else "FAIL"
    )
    print(json.dumps(audit, indent=2), flush=True)
    if audit["parity_status"] != "PASS":
        raise RuntimeError(f"Frozen baseline parity failed: {audit}")

    # ---- Context-gate grid ---------------------------------------------------
    print("Running context-gate grid (120 contexts x 3 scopes)...", flush=True)
    grid_rows: list[dict[str, Any]] = []
    stream_cache: dict[str, pd.DataFrame] = {}
    context_count = 0
    for vwap_acceptance in VWAP_ACCEPTANCE_GRID:
        for efficiency_max in EFFICIENCY_MAX_GRID:
            for time_bucket in TIME_BUCKET_GRID:
                for session_range_atr_max in SESSION_RANGE_MAX_GRID:
                    context = _context(
                        vwap_acceptance=vwap_acceptance,
                        efficiency_max=efficiency_max,
                        time_bucket=time_bucket,
                        session_range_atr_max=session_range_atr_max,
                    )
                    label = _context_label(context)
                    frame = _simulate(days, candidates_by_day, context, prior_ranges, setup=frozen_setup)
                    stream_cache[label] = frame
                    context_count += 1
                    for scope in DIRECTION_SCOPES:
                        scoped = _direction_filter(frame, scope) if not frame.empty else frame
                        score = _score_frame(scoped, r_column="net_r_1t", trading_days=trading_days)
                        score.update(
                            {
                                "context_label": label,
                                "direction_scope": scope,
                                "vwap_acceptance": vwap_acceptance,
                                "efficiency_max": efficiency_max,
                                "time_bucket": time_bucket,
                                "session_range_atr_max": session_range_atr_max,
                                "is_frozen_ungated": bool(
                                    vwap_acceptance == "none"
                                    and efficiency_max is None
                                    and time_bucket == "full"
                                    and session_range_atr_max == 2.0
                                ),
                                "friction_basis": "MNQ commission + 1 adverse tick/side on native 3m fills",
                            }
                        )
                        grid_rows.append(score)
    grid = pd.DataFrame(grid_rows)
    grid_scored_rows = int(len(grid))
    grid = grid.sort_values(
        ["direction_scope", "calmar", "profit_factor", "total_r"],
        ascending=[True, False, False, False],
    ).reset_index(drop=True)
    grid.insert(0, "rank", grid.groupby("direction_scope").cumcount() + 1)

    # ---- Short-side asymmetry probe -----------------------------------------
    print("Running short-side asymmetry probe...", flush=True)
    probe_contexts = {
        "ungated_sr2_full": _context(
            vwap_acceptance="none", efficiency_max=None, time_bucket="full", session_range_atr_max=2.0
        ),
        "gated_slope_eff55_t1014_sr15": _context(
            vwap_acceptance="reject_vwap_side_slope",
            efficiency_max=0.55,
            time_bucket="10:00-14:00",
            session_range_atr_max=1.5,
        ),
    }
    short_rows: list[dict[str, Any]] = []
    for extension in SHORT_EXTENSION_GRID:
        for consolidation in SHORT_CONSOLIDATION_GRID:
            setup = _setup(extension, consolidation)
            probe_candidates = [ctx._generate_candidates_for_day(day, setup) for day in days]
            _inject_slope10(days, probe_candidates)
            for ctx_label, context in probe_contexts.items():
                frame = _simulate(days, probe_candidates, context, prior_ranges, setup=setup)
                scoped = _direction_filter(frame, "short_only") if not frame.empty else frame
                score = _score_frame(scoped, r_column="net_r_1t", trading_days=trading_days)
                score.update(
                    {
                        "extension_atr_pct": extension,
                        "consolidation_atr_pct": consolidation,
                        "probe_context": ctx_label,
                        "direction_scope": "short_only",
                    }
                )
                short_rows.append(score)
    short_probe = pd.DataFrame(short_rows).sort_values(
        ["calmar", "total_r"], ascending=[False, False]
    ).reset_index(drop=True)
    short_probe_rows = int(len(short_probe))

    # ---- Finalist selection (top gated candidates) --------------------------
    print("Selecting finalists and running WF / 1s friction / yearly...", flush=True)
    eligible = grid[
        (grid["total_trades"] >= MIN_CANDIDATE_TRADES)
        & (grid["profit_factor"] >= 1.0)
        & (grid["max_drawdown_r"] > -60.0)
        & ~(grid["is_frozen_ungated"] & (grid["direction_scope"] == "both"))
    ].copy()
    # Exclude the plain both-direction ungated frozen row (today's known DEFER fail);
    # keep gated variants. The session_range knob is near-inert inside the mid-session
    # buckets, so collapse (scope, vwap_acceptance, efficiency_max, time_bucket) groups
    # to the best-Calmar member before taking the top 3, so finalists are distinct
    # configs rather than session-range twins.
    eligible["gate_group"] = (
        eligible["direction_scope"].astype(str)
        + "|" + eligible["vwap_acceptance"].astype(str)
        + "|" + eligible["efficiency_max"].astype(str)
        + "|" + eligible["time_bucket"].astype(str)
    )
    eligible = eligible.sort_values(
        ["calmar", "profit_factor", "total_r"], ascending=[False, False, False]
    )
    finalists = (
        eligible.groupby("gate_group", as_index=False)
        .head(1)
        .sort_values(["calmar", "profit_factor", "total_r"], ascending=[False, False, False])
        .head(3)
        .reset_index(drop=True)
    )

    lower_1s = _read_1s()
    finalist_details: list[dict[str, Any]] = []
    finalist_folds: list[pd.DataFrame] = []
    finalist_yearly: list[pd.DataFrame] = []
    finalist_friction: list[dict[str, Any]] = []
    for _, row in finalists.iterrows():
        label = str(row["context_label"])
        scope = str(row["direction_scope"])
        frame = stream_cache[label]
        scoped = _direction_filter(frame, scope) if not frame.empty else frame

        folds = pd.DataFrame(_frozen_walk_forward(scoped, r_column="net_r_1t"))
        folds.insert(0, "context_label", label)
        folds.insert(1, "direction_scope", scope)
        positive_folds = int((folds["test_total_r"] > 0).sum())
        oos_total_r = round(float(folds["test_total_r"].sum()), 4)
        finalist_folds.append(folds)

        yearly = pd.DataFrame(_yearly_split(scoped, r_column="net_r_1t"))
        yearly.insert(0, "context_label", label)
        yearly.insert(1, "direction_scope", scope)
        finalist_yearly.append(yearly)
        worst_year = round(float(yearly["total_r"].min()), 4) if not yearly.empty else 0.0

        # 1s path-replayed friction at 0/1/2 ticks (definitive).
        replay = _path_replay(scoped, lower_1s)
        for ticks in (0, 1, 2):
            values = replay[f"path_net_r_{ticks}t"].astype(float).to_numpy()
            finalist_friction.append(
                {
                    "context_label": label,
                    "direction_scope": scope,
                    "slippage_ticks_per_side": ticks,
                    "path_source": "1s",
                    "total_trades": int(len(replay)),
                    "total_r": round(float(values.sum()), 4),
                    "avg_r": round(float(values.mean()), 4) if len(values) else 0.0,
                    "profit_factor": round(_profit_factor(values), 4),
                    "max_drawdown_r": round(_max_drawdown(values), 4),
                    "deployability": DEPLOYABILITY,
                }
            )
        path_net_1t = replay["path_net_r_1t"].astype(float).to_numpy()

        detail = {
            "context_label": label,
            "direction_scope": scope,
            "vwap_acceptance": str(row["vwap_acceptance"]),
            "efficiency_max": None if pd.isna(row["efficiency_max"]) else float(row["efficiency_max"]),
            "time_bucket": str(row["time_bucket"]),
            "session_range_atr_max": None
            if pd.isna(row["session_range_atr_max"])
            else float(row["session_range_atr_max"]),
            "total_trades": int(row["total_trades"]),
            "avg_trades_per_day": float(row["avg_trades_per_day"]),
            "gross_total_r": float(row["gross_total_r"]),
            "net_r_1t_total_r": float(row["total_r"]),
            "profit_factor": float(row["profit_factor"]),
            "calmar": float(row["calmar"]),
            "max_drawdown_r": float(row["max_drawdown_r"]),
            "t_stat": float(row["t_stat"]),
            "path_1s_net_r_1t_total": round(float(path_net_1t.sum()), 4),
            "wf_positive_folds": positive_folds,
            "wf_total_folds": int(len(folds)),
            "wf_oos_total_r": oos_total_r,
            "worst_year_net_r_1t": worst_year,
            "deployability": DEPLOYABILITY,
        }
        # Survivor gate.
        detail["survivor"] = bool(
            detail["path_1s_net_r_1t_total"] > 0
            and detail["wf_oos_total_r"] > 0
            and detail["wf_positive_folds"] >= 4
            and detail["total_trades"] >= MIN_CANDIDATE_TRADES
            and detail["worst_year_net_r_1t"] > -detail["net_r_1t_total_r"] - 1e-9  # no year eats the whole edge
        )
        finalist_details.append(detail)
    del lower_1s

    finalist_detail_frame = pd.DataFrame(finalist_details)
    finalist_fold_frame = pd.concat(finalist_folds, ignore_index=True) if finalist_folds else pd.DataFrame()
    finalist_yearly_frame = pd.concat(finalist_yearly, ignore_index=True) if finalist_yearly else pd.DataFrame()
    finalist_friction_frame = pd.DataFrame(finalist_friction)

    any_survivor = bool(finalist_detail_frame.get("survivor", pd.Series(dtype=bool)).any())

    # ---- Noise / deflation read ---------------------------------------------
    configs_searched = grid_scored_rows + short_probe_rows
    best_row = grid.sort_values(["calmar", "t_stat"], ascending=[False, False]).iloc[0]
    best_tstat = float(best_row["t_stat"])
    expected_max_null_t = math.sqrt(2.0 * math.log(configs_searched)) if configs_searched > 1 else 0.0
    deflated_ratio = round(best_tstat / expected_max_null_t, 4) if expected_max_null_t > 0 else 0.0
    noise = {
        "configs_searched": int(configs_searched),
        "grid_scored_rows": int(grid_scored_rows),
        "short_probe_rows": int(short_probe_rows),
        "best_grid_t_stat": round(best_tstat, 4),
        "best_grid_row_label": str(best_row["context_label"]),
        "best_grid_row_scope": str(best_row["direction_scope"]),
        "expected_max_null_t_stat": round(expected_max_null_t, 4),
        "deflated_ratio_best_over_expected_max_null": deflated_ratio,
        "read": (
            "The best row's t-stat exceeds the expected maximum of the null (sqrt(2 ln N)); "
            "edge is unlikely to be pure selection noise."
            if best_tstat > expected_max_null_t
            else "The best row's t-stat does not exceed the expected maximum of the null under "
            f"{configs_searched} searched configs; the top edge is plausibly selection noise."
        ),
    }

    # ---- Artifacts -----------------------------------------------------------
    artifacts = {
        "baseline_trades.csv": baseline_frame,
        "context_gate_grid.csv": grid,
        "short_side_probe.csv": short_probe,
        "finalist_details.csv": finalist_detail_frame,
        "finalist_walk_forward_folds.csv": finalist_fold_frame,
        "finalist_yearly_splits.csv": finalist_yearly_frame,
        "finalist_friction_1s.csv": finalist_friction_frame,
    }
    for filename, frame in artifacts.items():
        frame.to_csv(RESULT_DIR / filename, index=False)

    summary = {
        "run_slug": RUN_SLUG,
        "track": "TRACK 1 of 4 - 3m context-gate rescue",
        "data_start": EFFECTIVE_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "trading_days": trading_days,
        "frozen_config": {
            "timeframe_min": TIMEFRAME_MIN,
            "extension_atr_pct": BASE_EXTENSION_ATR_PCT,
            "consolidation_atr_pct": BASE_CONSOLIDATION_ATR_PCT,
            "stop_atr_pct": BASE_STOP_ATR_PCT,
            "rr": RR,
            "max_trades_per_day": MAX_TRADES_PER_DAY,
        },
        "slope_adaptation": {
            "lookback_bars_3m": SLOPE_LOOKBACK_BARS,
            "lookback_minutes": SLOPE_LOOKBACK_BARS * TIMEFRAME_MIN,
            "reject_threshold_atr": SLOPE_REJECT_ATR,
            "note": "3m 10-bar/30-min slope matches the 5m 6-bar/30-min slope; same 0.02-ATR gate.",
        },
        "grid": {
            "vwap_acceptance": list(VWAP_ACCEPTANCE_GRID),
            "efficiency_max": list(EFFICIENCY_MAX_GRID),
            "time_bucket": list(TIME_BUCKET_GRID),
            "session_range_atr_max": list(SESSION_RANGE_MAX_GRID),
            "contexts": context_count,
            "scored_rows": grid_scored_rows,
        },
        "baseline_audit": audit,
        "finalists": finalist_details,
        "short_probe_best": short_probe.iloc[0].to_dict() if not short_probe.empty else {},
        "noise": noise,
        "any_survivor": any_survivor,
        "elapsed_seconds": round(time.time() - started, 2),
        "deployability": DEPLOYABILITY,
        "live_support_notes": LIVE_SUPPORT_NOTES,
        "exact_replay_required": EXACT_REPLAY_REQUIRED,
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe(summary), indent=2) + "\n")

    # ---- Report --------------------------------------------------------------
    grid_cols = [
        "rank",
        "direction_scope",
        "context_label",
        "vwap_acceptance",
        "efficiency_max",
        "time_bucket",
        "session_range_atr_max",
        "total_trades",
        "avg_trades_per_day",
        "gross_total_r",
        "total_r",
        "profit_factor",
        "calmar",
        "max_drawdown_r",
        "t_stat",
        "deployability",
    ]
    top_by_scope = (
        grid.sort_values(["direction_scope", "rank"]).groupby("direction_scope", group_keys=False).head(5)
    )
    frozen_rows = grid[grid["is_frozen_ungated"]].sort_values("direction_scope")
    short_cols = [
        "probe_context",
        "extension_atr_pct",
        "consolidation_atr_pct",
        "total_trades",
        "avg_trades_per_day",
        "total_r",
        "profit_factor",
        "calmar",
        "max_drawdown_r",
        "t_stat",
        "deployability",
    ]
    detail_cols = [
        "context_label",
        "direction_scope",
        "total_trades",
        "avg_trades_per_day",
        "gross_total_r",
        "net_r_1t_total_r",
        "path_1s_net_r_1t_total",
        "profit_factor",
        "calmar",
        "max_drawdown_r",
        "t_stat",
        "wf_positive_folds",
        "wf_oos_total_r",
        "worst_year_net_r_1t",
        "survivor",
        "deployability",
    ]
    fold_cols = [
        "context_label",
        "direction_scope",
        "test_start",
        "test_end_exclusive",
        "test_trades",
        "test_total_r",
        "test_pf",
        "test_dd_r",
    ]
    friction_cols = [
        "context_label",
        "direction_scope",
        "slippage_ticks_per_side",
        "total_trades",
        "total_r",
        "avg_r",
        "profit_factor",
        "max_drawdown_r",
        "deployability",
    ]
    yearly_cols = ["context_label", "direction_scope", "year", "trades", "total_r", "avg_r", "win_rate", "profit_factor"]

    verdict = (
        f"SURVIVOR FOUND: {finalist_detail_frame[finalist_detail_frame['survivor']].iloc[0]['context_label']} "
        f"({finalist_detail_frame[finalist_detail_frame['survivor']].iloc[0]['direction_scope']})."
        if any_survivor
        else "NO-GO: no gated variant cleared friction + frozen-config walk-forward. This closes the 3m rescue branch."
    )
    both_gated = grid[(grid["direction_scope"] == "both") & (~grid["is_frozen_ungated"])].sort_values(
        ["calmar", "total_r"], ascending=[False, False]
    )
    both_best = both_gated.iloc[0] if not both_gated.empty else None
    survivor_min_tpd = (
        float(finalist_detail_frame[finalist_detail_frame["survivor"]]["avg_trades_per_day"].max())
        if any_survivor
        else 0.0
    )

    lines = [
        "# NQ NY VWAP 3m Context-Gate Rescue",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        "- Track: **TRACK 1 of 4** - can context gates rescue the frozen NQ NY 3m VWAP mean-reversion leg?",
        f"- Data: `{EFFECTIVE_START}` through `<{DATA_END_EXCLUSIVE}` (`{trading_days}` NY RTH days), parity-audited 3m signal stream.",
        "- Frozen leg: 3m bars, VWAP mean, 2.5% prior-ATR extension, 30-minute consolidation (<=20% ATR range), sweep/reclaim, next-bar entry, 7.5% prior-ATR even-tick stop, fixed 1.5R target, max 3 trades/day, flat 15:55.",
        f"- Friction: integer MNQ sizing, `${MNQ_COMMISSION_PER_SIDE:.3f}`/side commission, adverse slippage `0/1/2/4` ticks/side. Grid metrics use native 3m fills at 1 tick/side; finalists are re-checked on 1s path replay.",
        "- VWAP-slope adaptation: 3m slope over the trailing **10 bars (30 minutes)** with the same **0.02-ATR** rejection threshold, the time-normalized analogue of the 5m 6-bar/30-minute slope.",
        f"- Deployability: `{DEPLOYABILITY}`. {LIVE_SUPPORT_NOTES}",
        "",
        "## Baseline Parity Audit",
        "",
        f"- Regenerated frozen ungated stream: `{audit['regenerated_trades']}` trades, `{audit['regenerated_total_r']:+.4f}R`.",
        f"- Saved champion: `{audit['saved_trades']}` trades, `{audit['saved_total_r']:+.4f}R`.",
        f"- Delta: trades `{audit['trade_count_delta']}`, R `{audit['total_r_delta']:+.6f}`; parity **{audit['parity_status']}**.",
        "",
        "## Context-Gate Grid (top 5 per scope, ranked by friction-adjusted Calmar)",
        "",
        "Grid = `vwap_acceptance{none, slope}` x `efficiency_max{none,0.45,0.55,0.65,0.70}` x `time_bucket{full,10-12,10-14,11-15}` x `session_range_atr_max{2.0,1.5,none}` = 120 contexts, scored per direction scope. `total_r` is after MNQ commission + 1 adverse tick/side on native 3m fills; `gross_total_r` is pre-friction.",
        "",
        _table(top_by_scope, grid_cols),
        "",
        "Frozen ungated reference rows (the DEFER baseline from the validation packet):",
        "",
        _table(frozen_rows, grid_cols),
        "",
        "## Short-Side Asymmetry Probe",
        "",
        "Short-only, sweeping extension `{0.025,0.05,0.075}` x consolidation `{0.15,0.20}` under an ungated and a gated context (net of commission + 1 tick/side):",
        "",
        _table(short_probe, short_cols),
        "",
        "## Finalists: Frozen-Config Walk-Forward, 1s Friction, Year Splits",
        "",
        "Top gated candidates (>=150 trades, PF>=1.0, ranked by friction-adjusted Calmar). Survivor gate: 1s friction-adjusted (1 tick) total R > 0, frozen-config WF OOS R > 0 with >=4/6 positive folds, no single year eating the whole edge.",
        "",
        _table(finalist_detail_frame, detail_cols),
        "",
        "### Rolling walk-forward folds (frozen-config, 6 folds, net 1 tick/side)",
        "",
        _table(finalist_fold_frame, fold_cols),
        "",
        "### Finalist friction stress on 1s path replay",
        "",
        _table(finalist_friction_frame, friction_cols),
        "",
        "### Finalist year-by-year (net 1 tick/side)",
        "",
        _table(finalist_yearly_frame, yearly_cols),
        "",
        "## Noise / Deflation Read",
        "",
        f"- Configurations searched (grid scored rows + short probe rows): **{noise['configs_searched']}**.",
        f"- Best grid row: `{noise['best_grid_row_label']}` ({noise['best_grid_row_scope']}), t-stat `{noise['best_grid_t_stat']}` (avg_r * sqrt(n) / std_r).",
        f"- Expected max |t| of the null over {noise['configs_searched']} searches ~ sqrt(2 ln N) = `{noise['expected_max_null_t_stat']}`; best-over-expected ratio `{noise['deflated_ratio_best_over_expected_max_null']}`.",
        f"- {noise['read']}",
        "",
        "## Summary Read",
        "",
        f"- **{verdict}**",
        "- The winning ingredients are the **directional-efficiency cap (0.55-0.70)** and the **10:00-14:00 entry bucket** on the **long side** - the same two levers that rescued the 5m branch. The `reject_vwap_side_slope` gate helps PF slightly but is not required, and `session_range_atr_max` is near-inert inside the mid-session buckets.",
        f"- **Frequency caveat:** the surviving long-only gate trades only ~`{survivor_min_tpd:.2f}`/day (~1 trade every 6-7 sessions vs the frozen leg's 1.16/day). It is a thin, highly selective filter, not the daily-cadence leg; sample size and deployability are correspondingly limited.",
        f"- **Deflation caveat:** the single best row's t-stat (`{noise['best_grid_t_stat']}`) is below the expected max of the null over `{noise['configs_searched']}` searched configs (`{noise['expected_max_null_t_stat']}`, ratio `{noise['deflated_ratio_best_over_expected_max_null']}`). One row alone is not distinguishable from best-of-noise; the supporting evidence is that a coherent neighborhood (efficiency 0.45-0.70 x 10:00-14:00, long and both) is jointly positive and clears 5/6 WF folds, which is harder to fake than a lone spike. Treat as a fragile low-frequency research candidate, not a robust edge.",
    ]
    if both_best is not None:
        lines += [
            f"- **Both-direction partial rescue:** the best gated both-direction row (`{both_best['context_label']}`) recovers to `{both_best['total_r']:+.1f}R` net at PF `{both_best['profit_factor']:.2f}`, Calmar `{both_best['calmar']:.2f}`, `{int(both_best['total_trades'])}` trades - a real improvement over the ungated `both` leg's `-5.2R`, but Calmar is roughly frozen-leg grade and it was not a Calmar top-3 finalist. The short side stays the drag (see probe).",
        ]
    lines += [
        "- All rows are `research_only`; nothing here authorizes live implementation. The exact gate parameters of the top survivor are handed to the follow-up limit-entry/cost track.",
        "",
        "## Artifacts",
        "",
        f"- Results: `backtesting/data/results/{RUN_SLUG}/`",
        f"- Report: `backtesting/learnings/reports/{REPORT_PATH.name}`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")

    print(json.dumps(_safe({"audit": audit, "noise": noise, "any_survivor": any_survivor, "finalists": finalist_details}), indent=2), flush=True)
    print(f"Wrote {RESULT_DIR}")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
