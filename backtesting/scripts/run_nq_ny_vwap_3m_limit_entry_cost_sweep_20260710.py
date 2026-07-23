#!/usr/bin/env python3
"""Limit-entry improvement + realistic-fill cost sweep for the frozen gated
NQ NY 3m VWAP mean-reversion survivor.

TRACK 2 of a 4-track program (final track). The TRACK 1 rescue produced a
long-only survivor: frozen 3m VWAP sweep/reclaim leg gated by
efficiency_max=0.65, time_bucket 10:00-14:00, session_range_atr_max=1.5, no
slope gate. Baseline entry is a market fill at the next 3m bar open. This script
quantifies whether resting-limit entries (priced at/below the next-bar open) add
total net R once realistic non-fills are honestly accounted for.

Fill model (conservative, non-negotiable) -- see the report's Fill Model section
for the precise write-up. In short: after the signal 3m bar completes the limit
is placed for the entry bar; on the lower-timeframe path (1m and 1s) a resting
buy limit at L fills only when price trades strictly THROUGH it (low <= L - 1
tick). A marketable limit (L >= entry-bar open O) fills immediately at O. Before
a fill, if the baseline target level is reached the order is a MISSED WINNER
(no trade); if the baseline stop level trades the order is CANCELLED (no trade);
same lower-timeframe bar ambiguity resolves against the trade (target-miss >
stop-cancel > fill). Cancel-if-unfilled after K 3m bars (K in {1,2,4} and
good-till-window-end). After a fill, stop and target come from either the actual
fill (recomputed, mode A: L-D / L+1.5D) or the original baseline levels (mode B:
O-D / O+1.5D); R is always expressed in the fixed baseline risk unit D (the even-
tick 7.5%-ATR stop distance) so every variant is directly comparable and paired
per-signal against the market-entry control on the identical 204-signal set.

Research artifact only; not wired to live execution.
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
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.data.fees import estimated_commission_per_side  # noqa: E402


RUN_SLUG = "nq_ny_vwap_3m_limit_entry_cost_sweep_20260710"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_VWAP_3M_LIMIT_ENTRY_COST_SWEEP_20260710.md"

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

# Frozen survivor context (do NOT re-tune).
SURVIVOR_EFFICIENCY_MAX = 0.65
SURVIVOR_TIME_BUCKET = "10:00-14:00"
SURVIVOR_SESSION_RANGE_ATR_MAX = 1.5
SURVIVOR_DIRECTION = "long"

# Parity targets from the TRACK 1 rescue survivor row (native 3m fills).
PARITY_TRADES = 204
PARITY_GROSS_R = 60.4782
PARITY_NET_1T_R = 48.7442

NQ_TICK = 0.25
MNQ_POINT_VALUE = 2.0
MNQ_COMMISSION_PER_SIDE = float(estimated_commission_per_side("MNQ"))
FLAT_TIME = "15:55"
TRADING_DAYS = 1293

# Entry variants. Each maps to a limit-price rule (baseline is the market control).
ENTRY_VARIANTS = (
    "baseline_market_open",
    "limit_signal_close",
    "limit_cons_low",
    "limit_retrace25",
    "limit_retrace50",
    "limit_retrace75",
    "limit_sweep_extreme",
)
LIMIT_VARIANTS = tuple(v for v in ENTRY_VARIANTS if v != "baseline_market_open")
K_VALUES = (1, 2, 4, "gtc")
STOP_MODES = ("recomputed", "original")  # A = fill-anchored, B = baseline levels
SLIPPAGE_TICKS = (0, 1, 2)
PATHS = ("1s", "1m")

DEPLOYABILITY = "research_only"
LIVE_SUPPORT_NOTES = (
    "The 3m VWAP sweep/reclaim state machine, native-timeframe static-R exit, the TRACK 1 context "
    "gates, and this limit-entry fill model are research-script only; the live execution engine "
    "cannot arm this setup yet."
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
    "nq_vwap_static_tf_20260630_limitentry",
)
ctx = tf.ctx


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

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


def _floor_tick(price: float) -> float:
    """Floor a price to the NQ tick grid (conservative for a resting buy limit)."""
    return math.floor(round(price / NQ_TICK, 6)) * NQ_TICK


def _frozen_setup() -> Any:
    return ctx.StateMachineConfig(
        label="frozen_vwap_3m_limit_entry",
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


def _survivor_context() -> Any:
    return ctx.ContextConfig(
        structure_gate="none",
        vwap_acceptance="none",
        efficiency_max=SURVIVOR_EFFICIENCY_MAX,
        ib_location="none",
        session_range_atr_max=SURVIVOR_SESSION_RANGE_ATR_MAX,
        time_bucket=SURVIVOR_TIME_BUCKET,
    )


def _load_days_and_baseline() -> tuple[list[Any], dict[str, Any], pd.DataFrame, dict[str, Any]]:
    df_1m = tf._load_1m_source()
    df_3m = tf._resample_ohlcv(df_1m, TIMEFRAME_MIN)
    days = ctx._prepare_days(ctx._prepare_rth(df_3m))
    trading_days = len(days)
    assert trading_days == TRADING_DAYS, f"expected {TRADING_DAYS} RTH days, got {trading_days}"
    prior_ranges = tf._prior_session_ranges(days)
    day_by_date = {day.date: day for day in days}

    frozen_setup = _frozen_setup()
    candidates_by_day = [ctx._generate_candidates_for_day(day, frozen_setup) for day in days]
    tf_config = tf.TimeframeConfig(timeframe_min=TIMEFRAME_MIN, setup=frozen_setup, context=_survivor_context())
    stop = tf.StaticStopConfig("atr14_prev", BASE_STOP_ATR_PCT, RR)
    gated_trades = tf._simulate_model(days, candidates_by_day, tf_config, stop, prior_ranges)
    frame = pd.DataFrame(gated_trades)
    long_frame = frame[frame["direction"] == SURVIVOR_DIRECTION].copy().reset_index(drop=True)

    gross_r = float(long_frame["r_multiple"].sum())
    risk = long_frame["risk_points"].astype(float)
    commission_r = (2.0 * MNQ_COMMISSION_PER_SIDE) / (risk * MNQ_POINT_VALUE)
    slippage_1t = (2.0 * 1 * NQ_TICK) / risk
    net_1t = float((long_frame["r_multiple"].astype(float) - commission_r - slippage_1t).sum())
    audit = {
        "regenerated_trades": int(len(long_frame)),
        "expected_trades": PARITY_TRADES,
        "trade_count_delta": int(len(long_frame) - PARITY_TRADES),
        "regenerated_gross_r": round(gross_r, 4),
        "expected_gross_r": PARITY_GROSS_R,
        "gross_r_delta": round(gross_r - PARITY_GROSS_R, 4),
        "regenerated_net_1t_r": round(net_1t, 4),
        "expected_net_1t_r": PARITY_NET_1T_R,
        "net_1t_r_delta": round(net_1t - PARITY_NET_1T_R, 4),
    }
    audit["parity_status"] = (
        "PASS"
        if audit["trade_count_delta"] == 0
        and abs(audit["gross_r_delta"]) < 5e-3
        and abs(audit["net_1t_r_delta"]) < 5e-3
        else "FAIL"
    )
    return days, day_by_date, long_frame, audit


def _enrich_geometry(frame: pd.DataFrame, day_by_date: dict[str, Any]) -> pd.DataFrame:
    rows = frame.to_dict(orient="records")
    for row in rows:
        day = day_by_date[row["date"]]
        signal_idx = int(row["signal_idx"])
        entry_idx = int(row["entry_idx"])
        risk = float(row["stop_ticks"]) * NQ_TICK  # D: fixed even-tick 7.5%-ATR stop distance
        market_open = float(day.opens[entry_idx])
        signal_close = float(day.closes[signal_idx])
        signal_low = float(day.lows[signal_idx])
        cons_low = float(np.min(day.lows[signal_idx - CONSOLIDATION_BARS:signal_idx]))
        row["D"] = risk
        row["market_open"] = market_open
        row["signal_close"] = signal_close
        row["signal_low"] = signal_low
        row["cons_low"] = cons_low
        row["stop_orig"] = market_open - risk
        row["target_orig"] = market_open + RR * risk
        row["limit_baseline_market_open"] = market_open
        row["limit_limit_signal_close"] = signal_close
        row["limit_limit_cons_low"] = cons_low
        row["limit_limit_sweep_extreme"] = signal_low
        for frac in (0.25, 0.50, 0.75):
            price = market_open - frac * (market_open - signal_low)
            row[f"limit_limit_retrace{int(frac * 100)}"] = _floor_tick(price)
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Lower-timeframe path loading + per-trade array prep
# --------------------------------------------------------------------------- #

def _read_lower(path_label: str, trade_dates: set[str]) -> pd.DataFrame:
    if path_label == "1m":
        df = tf._load_1m_source()
    else:
        df = pd.read_parquet(
            ROOT / "data" / "raw" / "NQ_1s.parquet",
            columns=["open", "high", "low", "close", "volume"],
            filters=[
                ("datetime", ">=", pd.Timestamp(DATA_START)),
                ("datetime", "<", pd.Timestamp(DATA_END_EXCLUSIVE)),
            ],
        ).sort_index()
    df = df.between_time("09:30", "16:00")
    date_key = df.index.normalize().strftime("%Y-%m-%d")
    df = df[pd.Index(date_key).isin(trade_dates)]
    return df[["open", "high", "low", "close"]]


def _prep_trade_arrays(frame: pd.DataFrame, day_by_date: dict[str, Any], lower: pd.DataFrame) -> list[dict[str, Any]]:
    """Slice each trade's lower-TF path once and precompute K-bar fill-window bounds."""
    prepped: list[dict[str, Any]] = []
    lower_by_date = {date: sub for date, sub in lower.groupby(lower.index.normalize().strftime("%Y-%m-%d"))}
    for row in frame.to_dict(orient="records"):
        day = day_by_date[row["date"]]
        entry_idx = int(row["entry_idx"])
        entry_ts = pd.Timestamp(row["entry_ts"])
        flat_ts = pd.Timestamp(f"{row['date']} {FLAT_TIME}:00")
        sub = lower_by_date.get(row["date"])
        if sub is None:
            prepped.append({"row": row, "empty": True})
            continue
        window = sub[(sub.index >= entry_ts) & (sub.index <= flat_ts)]
        if window.empty:
            prepped.append({"row": row, "empty": True})
            continue
        ts = window.index.asi8
        opens = window["open"].to_numpy(dtype=float)
        highs = window["high"].to_numpy(dtype=float)
        lows = window["low"].to_numpy(dtype=float)
        closes = window["close"].to_numpy(dtype=float)
        # K-bar fill-window bounds (number of lower bars strictly before the Kth 3m boundary).
        kb: dict[Any, int] = {}
        n_bars_day = len(day.timestamps)
        for k in K_VALUES:
            if k == "gtc":
                kb[k] = len(ts)
            else:
                bound_idx = entry_idx + int(k)
                if bound_idx >= n_bars_day:
                    kb[k] = len(ts)
                else:
                    bound_ns = pd.Timestamp(day.timestamps[bound_idx]).value
                    kb[k] = int(np.searchsorted(ts, bound_ns, side="left"))
        prepped.append(
            {
                "row": row,
                "empty": False,
                "opens": opens,
                "highs": highs,
                "lows": lows,
                "closes": closes,
                "kb": kb,
            }
        )
    return prepped


def _simulate_fill(prep: dict[str, Any], limit_price: float, k: Any, stop_mode: str) -> dict[str, Any]:
    """Return the fill/exit outcome for one trade under one (limit, K, stop_mode).

    All prices are for a LONG. R is expressed in the fixed baseline risk unit D.
    """
    row = prep["row"]
    d_risk = float(row["D"])
    market_open = float(row["market_open"])
    stop_orig = float(row["stop_orig"])
    target_orig = float(row["target_orig"])
    tick = NQ_TICK

    outcome = {
        "outcome": "unfilled",
        "filled": False,
        "fill_price": np.nan,
        "improvement_pts": 0.0,
        "improvement_r": 0.0,
        "exit_type": "none",
        "r_multiple": 0.0,
    }
    if prep.get("empty"):
        return outcome

    highs = prep["highs"]
    lows = prep["lows"]
    closes = prep["closes"]
    n = len(lows)

    # Marketable limit (priced at/above the entry-bar open): immediate fill at the open.
    if limit_price >= market_open - 1e-9:
        fill_idx = 0
        fill_price = market_open
    else:
        kb = int(prep["kb"][k])
        kb = min(kb, n)
        if kb <= 0:
            return outcome
        h_win = highs[:kb]
        l_win = lows[:kb]
        # Pre-fill events; same-bar priority miss > cancel > fill (against the trade).
        miss_hits = np.nonzero(h_win >= target_orig)[0]
        cancel_hits = np.nonzero(l_win <= stop_orig)[0]
        fill_hits = np.nonzero(l_win <= limit_price - tick)[0]
        first_miss = int(miss_hits[0]) if miss_hits.size else n + 1
        first_cancel = int(cancel_hits[0]) if cancel_hits.size else n + 1
        first_fill = int(fill_hits[0]) if fill_hits.size else n + 1
        earliest = min(first_miss, first_cancel, first_fill)
        if earliest > n:
            outcome["outcome"] = "cancelled_timeout"
            return outcome
        # Resolve ties at the same bar against the trade.
        if first_miss == earliest:
            outcome["outcome"] = "missed_winner_prefill"
            return outcome
        if first_cancel == earliest:
            outcome["outcome"] = "cancelled_stop_prefill"
            return outcome
        fill_idx = first_fill
        fill_price = limit_price

    # Post-fill exit levels.
    if stop_mode == "recomputed":
        stop_level = fill_price - d_risk
        target_level = fill_price + RR * d_risk
    else:  # original baseline levels
        stop_level = stop_orig
        target_level = target_orig

    h_post = highs[fill_idx:]
    l_post = lows[fill_idx:]
    stop_hits = np.nonzero(l_post <= stop_level)[0]
    target_hits = np.nonzero(h_post >= target_level)[0]
    first_stop = int(stop_hits[0]) if stop_hits.size else n + 1
    first_target = int(target_hits[0]) if target_hits.size else n + 1
    if first_stop == n + 1 and first_target == n + 1:
        exit_price = float(closes[-1])
        exit_type = "eod"
    elif first_stop <= first_target:  # stop priority on same-bar ambiguity
        exit_price = stop_level
        exit_type = "stop"
    else:
        exit_price = target_level
        exit_type = "target"

    r_multiple = (exit_price - fill_price) / d_risk if d_risk > 0 else 0.0
    outcome.update(
        {
            "outcome": "filled",
            "filled": True,
            "fill_price": round(float(fill_price), 4),
            "improvement_pts": round(float(market_open - fill_price), 4),
            "improvement_r": round(float((market_open - fill_price) / d_risk), 6) if d_risk > 0 else 0.0,
            "exit_type": exit_type,
            "r_multiple": round(float(r_multiple), 6),
        }
    )
    return outcome


# --------------------------------------------------------------------------- #
# Friction
# --------------------------------------------------------------------------- #

def _net_r(gross_r: np.ndarray, d_risk: np.ndarray, *, entry_ticks: float, exit_ticks: float) -> np.ndarray:
    commission_r = (2.0 * MNQ_COMMISSION_PER_SIDE) / (d_risk * MNQ_POINT_VALUE)
    slippage_r = ((entry_ticks + exit_ticks) * NQ_TICK) / d_risk
    return gross_r - commission_r - slippage_r


def _slippage_specs(is_market_entry: bool) -> dict[str, tuple[float, float]]:
    """(entry_ticks, exit_ticks) per named slippage assumption."""
    specs: dict[str, tuple[float, float]] = {}
    for s in SLIPPAGE_TICKS:
        specs[f"{s}t"] = (float(s), float(s))
    # Mixed: limit entries fill passively (0 ticks); market entries still pay 1 tick.
    specs["mixed"] = (1.0 if is_market_entry else 0.0, 1.0)
    return specs


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #

def _score_variant(
    frame: pd.DataFrame,
    outcomes: list[dict[str, Any]],
    baseline_path_r: np.ndarray,
    *,
    is_market_entry: bool,
    trading_days: int = TRADING_DAYS,
) -> dict[str, Any]:
    d_risk = frame["D"].astype(float).to_numpy()
    dates = frame["date"].astype(str).to_numpy()
    gross = np.array([o["r_multiple"] for o in outcomes], dtype=float)
    filled = np.array([o["filled"] for o in outcomes], dtype=bool)
    n = len(outcomes)
    n_filled = int(filled.sum())

    unfilled_mask = ~filled
    unfilled_baseline = baseline_path_r[unfilled_mask]
    missed_winner = int((unfilled_baseline > 0).sum())
    missed_loser = int((unfilled_baseline <= 0).sum())
    outcome_counts: dict[str, int] = {}
    for o in outcomes:
        outcome_counts[o["outcome"]] = outcome_counts.get(o["outcome"], 0) + 1

    improvement_pts = np.array([o["improvement_pts"] for o in outcomes], dtype=float)[filled]
    improvement_r = np.array([o["improvement_r"] for o in outcomes], dtype=float)[filled]

    specs = _slippage_specs(is_market_entry)
    result: dict[str, Any] = {
        "total_signals": n,
        "filled": n_filled,
        "fill_rate": round(n_filled / n, 4) if n else 0.0,
        "missed_winner": missed_winner,
        "missed_loser": missed_loser,
        "missed_winner_rate": round(missed_winner / n, 4) if n else 0.0,
        "missed_loser_rate": round(missed_loser / n, 4) if n else 0.0,
        "avg_improvement_pts": round(float(improvement_pts.mean()), 4) if n_filled else 0.0,
        "avg_improvement_r": round(float(improvement_r.mean()), 5) if n_filled else 0.0,
        "cancelled_timeout": outcome_counts.get("cancelled_timeout", 0),
        "cancelled_stop_prefill": outcome_counts.get("cancelled_stop_prefill", 0),
        "missed_winner_prefill": outcome_counts.get("missed_winner_prefill", 0),
        "target_exits": sum(1 for o in outcomes if o["exit_type"] == "target"),
        "stop_exits": sum(1 for o in outcomes if o["exit_type"] == "stop"),
        "eod_exits": sum(1 for o in outcomes if o["exit_type"] == "eod"),
    }
    years = trading_days / 252.0
    for name, (entry_ticks, exit_ticks) in specs.items():
        net = _net_r(gross, d_risk, entry_ticks=entry_ticks, exit_ticks=exit_ticks)
        net = np.where(filled, net, 0.0)  # unfilled contribute 0
        # Order by date for drawdown.
        order = np.argsort(dates, kind="stable")
        net_ordered = net[order]
        total_r = float(net.sum())
        max_dd = _max_drawdown(net_ordered)
        avg_annual = total_r / years if years else 0.0
        filled_net = net[filled]
        result[f"total_r_{name}"] = round(total_r, 4)
        result[f"avg_r_all_{name}"] = round(total_r / n, 5) if n else 0.0
        result[f"avg_r_filled_{name}"] = round(float(filled_net.mean()), 5) if n_filled else 0.0
        result[f"pf_{name}"] = round(_profit_factor(net_ordered), 4)
        result[f"dd_r_{name}"] = round(max_dd, 4)
        result[f"calmar_{name}"] = round(avg_annual / abs(max_dd), 4) if max_dd < 0 else 0.0
    return result


def _net_vector(frame: pd.DataFrame, outcomes: list[dict[str, Any]], *, is_market_entry: bool, spec_name: str) -> np.ndarray:
    d_risk = frame["D"].astype(float).to_numpy()
    gross = np.array([o["r_multiple"] for o in outcomes], dtype=float)
    filled = np.array([o["filled"] for o in outcomes], dtype=bool)
    entry_ticks, exit_ticks = _slippage_specs(is_market_entry)[spec_name]
    net = _net_r(gross, d_risk, entry_ticks=entry_ticks, exit_ticks=exit_ticks)
    return np.where(filled, net, 0.0)


def _year_split(frame: pd.DataFrame, net: np.ndarray) -> pd.DataFrame:
    years = frame["date"].astype(str).str[:4].to_numpy()
    rows = []
    for year in sorted(set(years)):
        mask = years == year
        vals = net[mask]
        rows.append(
            {
                "year": year,
                "signals": int(mask.sum()),
                "total_r": round(float(vals.sum()), 4),
                "avg_r": round(float(vals.mean()), 5) if mask.sum() else 0.0,
                "win_rate": round(float((vals > 0).mean()), 4) if mask.sum() else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _fold_windows() -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    windows: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    cursor = pd.Timestamp("2021-07-01")
    end_limit = pd.Timestamp(DATA_END_EXCLUSIVE)
    while cursor + pd.DateOffset(months=24) <= end_limit:
        windows.append((cursor + pd.DateOffset(months=18), cursor + pd.DateOffset(months=24)))
        cursor += pd.DateOffset(months=6)
    return windows


def _walk_forward(frame: pd.DataFrame, net: np.ndarray) -> list[dict[str, Any]]:
    dates = pd.to_datetime(frame["date"])
    folds: list[dict[str, Any]] = []
    for test_start, test_end in _fold_windows():
        mask = ((dates >= test_start) & (dates < test_end)).to_numpy()
        vals = net[mask]
        folds.append(
            {
                "test_start": test_start.date().isoformat(),
                "test_end_exclusive": test_end.date().isoformat(),
                "test_signals": int(mask.sum()),
                "test_total_r": round(float(vals.sum()), 4),
                "test_pf": round(_profit_factor(vals), 4),
                "test_dd_r": round(_max_drawdown(vals), 4),
            }
        )
    return folds


def _paired_tstat(delta: np.ndarray) -> tuple[float, float, float]:
    delta = np.asarray(delta, dtype=float)
    n = len(delta)
    mean = float(delta.mean()) if n else 0.0
    std = float(delta.std(ddof=1)) if n > 1 else 0.0
    tstat = (mean * math.sqrt(n) / std) if std > 0 else 0.0
    return round(mean, 5), round(std, 5), round(tstat, 4)


# --------------------------------------------------------------------------- #
# Table helper
# --------------------------------------------------------------------------- #

def _table(frame: pd.DataFrame, columns: list[str], n: int | None = None) -> str:
    if frame is None or frame.empty:
        return "_None._"
    view = frame[[c for c in columns if c in frame.columns]].copy()
    if n is not None:
        view = view.head(n)
    return view.to_markdown(index=False)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("Loading source, regenerating frozen gated survivor stream...", flush=True)
    days, day_by_date, baseline_long, audit = _load_days_and_baseline()
    print(json.dumps(audit, indent=2), flush=True)
    if audit["parity_status"] != "PASS":
        raise RuntimeError(f"Baseline parity failed: {audit}")

    frame = _enrich_geometry(baseline_long, day_by_date)
    trade_dates = set(frame["date"].astype(str))
    print(f"Survivor signals: {len(frame)} across {len(trade_dates)} trading days.", flush=True)

    variant_price_col = {
        "baseline_market_open": "limit_baseline_market_open",
        "limit_signal_close": "limit_limit_signal_close",
        "limit_cons_low": "limit_limit_cons_low",
        "limit_retrace25": "limit_limit_retrace25",
        "limit_retrace50": "limit_limit_retrace50",
        "limit_retrace75": "limit_limit_retrace75",
        "limit_sweep_extreme": "limit_limit_sweep_extreme",
    }

    grid_rows: list[dict[str, Any]] = []
    per_signal_store: dict[tuple[str, str, Any, str], list[dict[str, Any]]] = {}
    baseline_path_r_by_path: dict[str, np.ndarray] = {}
    trade_detail_rows: list[dict[str, Any]] = []

    for path_label in PATHS:
        print(f"Loading {path_label} path and prepping per-trade arrays...", flush=True)
        lower = _read_lower(path_label, trade_dates)
        prepped = _prep_trade_arrays(frame, day_by_date, lower)
        del lower

        # Baseline (market at next-bar open) on this path -- always filled, mode = original.
        baseline_outcomes = [
            _simulate_fill(prep, float(prep["row"]["market_open"]), "gtc", "original") for prep in prepped
        ]
        baseline_gross = np.array([o["r_multiple"] for o in baseline_outcomes], dtype=float)
        baseline_path_r_by_path[path_label] = baseline_gross.copy()
        base_score = _score_variant(frame, baseline_outcomes, baseline_gross, is_market_entry=True)
        base_score.update({"entry_variant": "baseline_market_open", "k_bars": "n/a", "stop_mode": "original", "path": path_label})
        grid_rows.append(base_score)
        per_signal_store[("baseline_market_open", "original", "gtc", path_label)] = baseline_outcomes

        for variant in LIMIT_VARIANTS:
            price_col = variant_price_col[variant]
            prices = frame[price_col].astype(float).to_numpy()
            for k in K_VALUES:
                for stop_mode in STOP_MODES:
                    outcomes = [
                        _simulate_fill(prep, float(prices[i]), k, stop_mode)
                        for i, prep in enumerate(prepped)
                    ]
                    score = _score_variant(frame, outcomes, baseline_gross, is_market_entry=False)
                    score.update(
                        {
                            "entry_variant": variant,
                            "k_bars": k,
                            "stop_mode": stop_mode,
                            "path": path_label,
                        }
                    )
                    grid_rows.append(score)
                    per_signal_store[(variant, stop_mode, k, path_label)] = outcomes
        del prepped

    grid = pd.DataFrame(grid_rows)
    grid.to_csv(RESULT_DIR / "entry_variant_grid.csv", index=False)

    # ---- Paired-delta significance (primary = 1s path, mixed slippage) --------
    primary_path = "1s"
    primary_spec = "mixed"
    base_net_primary = _net_vector(
        frame, per_signal_store[("baseline_market_open", "original", "gtc", primary_path)],
        is_market_entry=True, spec_name=primary_spec,
    )
    paired_rows: list[dict[str, Any]] = []
    for variant in LIMIT_VARIANTS:
        for k in K_VALUES:
            for stop_mode in STOP_MODES:
                outcomes = per_signal_store[(variant, stop_mode, k, primary_path)]
                net = _net_vector(frame, outcomes, is_market_entry=False, spec_name=primary_spec)
                mean_d, std_d, tstat = _paired_tstat(net - base_net_primary)
                paired_rows.append(
                    {
                        "entry_variant": variant,
                        "k_bars": k,
                        "stop_mode": stop_mode,
                        "path": primary_path,
                        "slippage": primary_spec,
                        "total_r": round(float(net.sum()), 4),
                        "baseline_total_r": round(float(base_net_primary.sum()), 4),
                        "delta_total_r": round(float(net.sum() - base_net_primary.sum()), 4),
                        "paired_mean_delta_r": mean_d,
                        "paired_std_delta_r": std_d,
                        "paired_t_stat": tstat,
                    }
                )
    paired = pd.DataFrame(paired_rows).sort_values("delta_total_r", ascending=False).reset_index(drop=True)
    paired.to_csv(RESULT_DIR / "paired_deltas_1s_mixed.csv", index=False)

    n_limit_combos = len(LIMIT_VARIANTS) * len(K_VALUES) * len(STOP_MODES)
    expected_max_null_t = math.sqrt(2.0 * math.log(n_limit_combos)) if n_limit_combos > 1 else 0.0
    best_paired = paired.iloc[0].to_dict()
    deflation = {
        "combos_scored_primary": int(n_limit_combos),
        "combos_scored_total_including_paths_slippage": int(
            n_limit_combos * len(PATHS) * (len(SLIPPAGE_TICKS) + 1)
        ),
        "best_combo": f"{best_paired['entry_variant']}|K={best_paired['k_bars']}|{best_paired['stop_mode']}",
        "best_delta_total_r": best_paired["delta_total_r"],
        "best_paired_t_stat": best_paired["paired_t_stat"],
        "expected_max_null_t": round(expected_max_null_t, 4),
        "best_over_expected_max_null": round(best_paired["paired_t_stat"] / expected_max_null_t, 4)
        if expected_max_null_t
        else 0.0,
    }

    # ---- Best (K, stop_mode) per limit variant on the primary path/slippage ----
    best_per_variant_rows: list[dict[str, Any]] = []
    primary_grid = grid[grid["path"] == primary_path].copy()
    total_col = f"total_r_{primary_spec}"
    for variant in ENTRY_VARIANTS:
        subset = primary_grid[primary_grid["entry_variant"] == variant]
        best = subset.sort_values(total_col, ascending=False).iloc[0].to_dict()
        best_per_variant_rows.append(best)
    best_per_variant = pd.DataFrame(best_per_variant_rows)
    best_per_variant.to_csv(RESULT_DIR / "best_per_variant_1s_mixed.csv", index=False)

    # ---- Walk-forward + year splits for the best 1-2 limit variants -----------
    wf_frames: list[pd.DataFrame] = []
    year_frames: list[pd.DataFrame] = []
    base_net_year = _net_vector(
        frame, per_signal_store[("baseline_market_open", "original", "gtc", primary_path)],
        is_market_entry=True, spec_name=primary_spec,
    )
    base_year = _year_split(frame, base_net_year)
    base_year.insert(0, "entry_variant", "baseline_market_open")
    year_frames.append(base_year)
    base_wf = pd.DataFrame(_walk_forward(frame, base_net_year))
    base_wf.insert(0, "entry_variant", "baseline_market_open")
    wf_frames.append(base_wf)

    best_limit_combos = (
        paired.sort_values("delta_total_r", ascending=False)
        .drop_duplicates("entry_variant")
        .head(2)
    )
    wf_summary: list[dict[str, Any]] = []
    for _, prow in best_limit_combos.iterrows():
        variant = str(prow["entry_variant"])
        k = prow["k_bars"]
        stop_mode = str(prow["stop_mode"])
        outcomes = per_signal_store[(variant, stop_mode, k, primary_path)]
        net = _net_vector(frame, outcomes, is_market_entry=False, spec_name=primary_spec)
        wf = pd.DataFrame(_walk_forward(frame, net))
        label = f"{variant}|K={k}|{stop_mode}"
        wf.insert(0, "entry_variant", label)
        wf_frames.append(wf)
        yr = _year_split(frame, net)
        yr.insert(0, "entry_variant", label)
        year_frames.append(yr)
        wf_summary.append(
            {
                "entry_variant": label,
                "positive_folds": int((wf["test_total_r"] > 0).sum()),
                "total_folds": int(len(wf)),
                "wf_total_r": round(float(wf["test_total_r"].sum()), 4),
            }
        )
    wf_all = pd.concat(wf_frames, ignore_index=True)
    year_all = pd.concat(year_frames, ignore_index=True)
    wf_all.to_csv(RESULT_DIR / "walk_forward_folds.csv", index=False)
    year_all.to_csv(RESULT_DIR / "year_splits.csv", index=False)

    # ---- Save a per-signal detail for the top combo ---------------------------
    top_variant = str(best_paired["entry_variant"])
    top_k = best_paired["k_bars"]
    top_mode = str(best_paired["stop_mode"])
    top_outcomes = per_signal_store[(top_variant, top_mode, top_k, primary_path)]
    for i, o in enumerate(top_outcomes):
        r = frame.iloc[i]
        trade_detail_rows.append(
            {
                "date": r["date"],
                "entry_ts": r["entry_ts"],
                "market_open": r["market_open"],
                "limit_price": frame.iloc[i][variant_price_col[top_variant]],
                "D_risk_pts": r["D"],
                "outcome": o["outcome"],
                "filled": o["filled"],
                "fill_price": o["fill_price"],
                "improvement_pts": o["improvement_pts"],
                "improvement_r": o["improvement_r"],
                "exit_type": o["exit_type"],
                "gross_r": o["r_multiple"],
                "baseline_path_gross_r": round(float(baseline_path_r_by_path[primary_path][i]), 6),
            }
        )
    pd.DataFrame(trade_detail_rows).to_csv(RESULT_DIR / f"top_combo_per_signal_{primary_path}.csv", index=False)

    # ---- Summary JSON ---------------------------------------------------------
    baseline_total_mixed = float(base_net_primary.sum())
    summary = {
        "run_slug": RUN_SLUG,
        "track": "TRACK 2 of 4 - limit-entry improvement + realistic-fill cost sweep",
        "data_start": EFFECTIVE_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "trading_days": TRADING_DAYS,
        "survivor_config": {
            "direction": SURVIVOR_DIRECTION,
            "efficiency_max": SURVIVOR_EFFICIENCY_MAX,
            "time_bucket": SURVIVOR_TIME_BUCKET,
            "session_range_atr_max": SURVIVOR_SESSION_RANGE_ATR_MAX,
            "stop_atr_pct": BASE_STOP_ATR_PCT,
            "rr": RR,
        },
        "baseline_parity": audit,
        "primary_path": primary_path,
        "primary_slippage": primary_spec,
        "baseline_total_r_primary": round(baseline_total_mixed, 4),
        "paired_best": best_paired,
        "deflation": deflation,
        "wf_summary": wf_summary,
        "elapsed_seconds": round(time.time() - started, 2),
        "deployability": DEPLOYABILITY,
        "live_support_notes": LIVE_SUPPORT_NOTES,
        "exact_replay_required": EXACT_REPLAY_REQUIRED,
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe(summary), indent=2) + "\n")

    # ---- Report ---------------------------------------------------------------
    _write_report(
        audit=audit,
        frame=frame,
        best_per_variant=best_per_variant,
        primary_spec=primary_spec,
        grid=grid,
        paired=paired,
        deflation=deflation,
        wf_all=wf_all,
        wf_summary=wf_summary,
        year_all=year_all,
        baseline_total_mixed=baseline_total_mixed,
        best_paired=best_paired,
    )

    print(json.dumps(_safe({"audit": audit, "paired_best": best_paired, "deflation": deflation, "wf_summary": wf_summary}), indent=2), flush=True)
    print(f"Wrote {RESULT_DIR}")
    print(f"Wrote {REPORT_PATH}")


def _write_report(
    *,
    audit: dict[str, Any],
    frame: pd.DataFrame,
    best_per_variant: pd.DataFrame,
    primary_spec: str,
    grid: pd.DataFrame,
    paired: pd.DataFrame,
    deflation: dict[str, Any],
    wf_all: pd.DataFrame,
    wf_summary: list[dict[str, Any]],
    year_all: pd.DataFrame,
    baseline_total_mixed: float,
    best_paired: dict[str, Any],
) -> None:
    bpv_cols = [
        "entry_variant",
        "k_bars",
        "stop_mode",
        "fill_rate",
        "missed_winner_rate",
        "missed_loser_rate",
        "avg_improvement_pts",
        "avg_improvement_r",
        f"total_r_1t",
        f"total_r_{primary_spec}",
        f"avg_r_all_{primary_spec}",
        f"pf_{primary_spec}",
        f"dd_r_{primary_spec}",
        f"calmar_{primary_spec}",
    ]
    paired_cols = [
        "entry_variant",
        "k_bars",
        "stop_mode",
        "total_r",
        "baseline_total_r",
        "delta_total_r",
        "paired_mean_delta_r",
        "paired_t_stat",
    ]
    wf_cols = ["entry_variant", "test_start", "test_end_exclusive", "test_signals", "test_total_r", "test_pf", "test_dd_r"]
    year_cols = ["entry_variant", "year", "signals", "total_r", "avg_r", "win_rate"]

    beats = bool(best_paired["delta_total_r"] > 0)
    sig = bool(best_paired["paired_t_stat"] > deflation["expected_max_null_t"])
    best_label = f"{best_paired['entry_variant']} (K={best_paired['k_bars']}, {best_paired['stop_mode']} stop)"

    # Slippage sensitivity of the headline variant vs baseline on the primary path.
    primary_grid = grid[grid["path"] == "1s"].copy()
    base_row = primary_grid[primary_grid["entry_variant"] == "baseline_market_open"].iloc[0]
    top_row = (
        primary_grid[
            (primary_grid["entry_variant"] == best_paired["entry_variant"])
            & (primary_grid["k_bars"] == best_paired["k_bars"])
            & (primary_grid["stop_mode"] == best_paired["stop_mode"])
        ].iloc[0]
    )
    slippage_rows = []
    for name in ("0t", "1t", "2t", "mixed"):
        slippage_rows.append(
            {
                "slippage": name,
                "baseline_total_r": round(float(base_row[f"total_r_{name}"]), 4),
                "best_variant_total_r": round(float(top_row[f"total_r_{name}"]), 4),
                "delta_total_r": round(float(top_row[f"total_r_{name}"] - base_row[f"total_r_{name}"]), 4),
            }
        )
    slippage_frame = pd.DataFrame(slippage_rows)

    recommend = (
        "MARKET (next-bar open)"
        if not (beats and sig)
        else best_label
    )

    lines = [
        "# NQ NY VWAP 3m Limit-Entry + Realistic-Fill Cost Sweep",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        "- Track: **TRACK 2 of 4** (final track) - does resting-limit entry improvement beat market entry on TOTAL net R once non-fills are paid for?",
        f"- Data: `{EFFECTIVE_START}` through `<{DATA_END_EXCLUSIVE}` (`{TRADING_DAYS}` NY RTH days).",
        "- Survivor leg (frozen, from TRACK 1 rescue): 3m bars, VWAP mean, 2.5% prior-ATR extension, 30-minute consolidation (<=20% ATR range), sweep/reclaim, LONG-ONLY, gated by `efficiency_max=0.65`, `time_bucket 10:00-14:00`, `session_range_atr_max=1.5`, no slope gate. 7.5% prior-ATR even-tick stop, fixed 1.5R target, max 3 trades/day, ~10-min cooldown, flat 15:55.",
        f"- Friction: integer MNQ sizing, `${MNQ_COMMISSION_PER_SIDE:.3f}`/side commission, adverse slippage `0/1/2` ticks/side plus a mixed model (0 ticks on a passive limit fill, 1 tick on the stop/target exit; the market baseline pays 1 tick each side).",
        f"- Deployability: `{DEPLOYABILITY}`. {LIVE_SUPPORT_NOTES}",
        "",
        "## Scope",
        "",
        "The 204-signal survivor set is held FIXED (the exact long trades the frozen gated leg takes at market). Each entry variant only re-prices the entry on that same signal set; unfilled orders contribute 0 R. This keeps every comparison a clean per-signal paired test against the market-entry control and does not let a limit variant free up cooldown slots for other signals (that dynamic re-selection is out of scope).",
        "",
        "## Baseline Parity Audit",
        "",
        f"- Regenerated frozen gated survivor stream: `{audit['regenerated_trades']}` trades, gross `{audit['regenerated_gross_r']:+.4f}R`, net@1t `{audit['regenerated_net_1t_r']:+.4f}R`.",
        f"- Expected (TRACK 1 survivor row): `{audit['expected_trades']}` trades, gross `{audit['expected_gross_r']:+.4f}R`, net@1t `{audit['expected_net_1t_r']:+.4f}R`.",
        f"- Delta: trades `{audit['trade_count_delta']}`, gross `{audit['gross_r_delta']:+.4f}R`, net@1t `{audit['net_1t_r_delta']:+.4f}R`; parity **{audit['parity_status']}**.",
        "",
        "## Fill Model (precise)",
        "",
        "1. **Limit price** (LONG, per variant): signal-bar close; consolidation low (the swept level); 25/50/75% retrace from the next-bar open toward the sweep-extreme (signal-bar) low; or the sweep-extreme low itself. Off-grid retrace prices are floored to the NQ tick (harder to fill, conservative).",
        "2. **Placement**: after the signal 3m bar completes, the limit rests for the entry bar onward on the lower-timeframe path (1m and 1s).",
        "3. **Marketable case**: if the limit is at/above the entry-bar open, it fills immediately at the open (no improvement) -- a limit can never fill worse than the market it was placed into.",
        "4. **Resting fill**: otherwise a fill requires the lower-timeframe price to trade strictly THROUGH the limit (low <= limit - 1 tick). Fill price is the limit.",
        "5. **Pre-fill cancels/misses**: while unfilled, if the baseline target level is reached first the order is a MISSED WINNER (no trade); if the baseline stop level trades first the order is CANCELLED (no trade). Same lower-timeframe-bar ambiguity resolves against the trade: target-miss > stop-cancel > fill.",
        "6. **Time stop**: cancel-if-unfilled after K = 1, 2, 4 3m bars, and good-till-window-end (`gtc`, until 15:55).",
        "7. **After fill**: `recomputed` mode re-anchors stop/target to the fill (fill-D / fill+1.5D); `original` mode keeps the baseline market levels (open-D / open+1.5D). Exit is the conservative lower-TF path with stop priority on same-bar stop/target touches, else flat at 15:55.",
        "8. **R unit**: every variant's R uses the SAME fixed baseline risk D (the even-tick 7.5%-ATR stop distance in points), so a few points of entry improvement is a directly-additive fractional R lift and total R is comparable across variants. In `original` mode a winner therefore pays `1.5R + improvement_R` and a loser `-1R + improvement_R`; in `recomputed` mode the trade is a rigid `[-1R, +1.5R]` shape shifted to a lower, safer entry.",
        "",
        "## Entry Variants (best K/stop-mode per variant, 1s path, mixed slippage)",
        "",
        "`total_r_1t` is symmetric 1 tick/side; `total_r_mixed` uses the passive-limit-fill assumption. Baseline is the market control.",
        "",
        _table(best_per_variant, bpv_cols),
        "",
        "## Slippage Sensitivity: Best Limit Variant vs Market Baseline (1s path)",
        "",
        _table(slippage_frame, ["slippage", "baseline_total_r", "best_variant_total_r", "delta_total_r"]),
        "",
        "## Paired Per-Signal Deltas vs Market Baseline (1s, mixed slippage)",
        "",
        "Every row is scored on the identical 204-signal set, so the delta is a paired difference. `paired_t_stat` = mean(delta)*sqrt(n)/std(delta).",
        "",
        _table(paired, paired_cols, n=16),
        "",
        "## Best-Variant Walk-Forward (frozen config, 6 rolling folds, 1s mixed slippage)",
        "",
        _table(wf_all, wf_cols),
        "",
        "## Year Splits (1s, mixed slippage)",
        "",
        _table(year_all, year_cols),
        "",
        "## Deflation Read",
        "",
        f"- Limit combos scored on the primary path/slippage (variant x K x stop-mode): **{deflation['combos_scored_primary']}**; total including both paths and all slippage assumptions: **{deflation['combos_scored_total_including_paths_slippage']}**.",
        f"- Best combo: `{deflation['best_combo']}`, paired delta `{deflation['best_delta_total_r']:+.4f}R`, paired t-stat `{deflation['best_paired_t_stat']}`.",
        f"- Expected max |t| of the null over {deflation['combos_scored_primary']} paired searches ~ sqrt(2 ln N) = `{deflation['expected_max_null_t']}`; best-over-expected ratio `{deflation['best_over_expected_max_null']}`.",
        f"- {'The best combo paired t-stat exceeds the expected null maximum; the lift is unlikely to be pure selection noise.' if best_paired['paired_t_stat'] > deflation['expected_max_null_t'] else 'The best combo paired t-stat does NOT exceed the expected null maximum; the lift is plausibly selection noise.'}",
        "",
        "## Summary Read",
        "",
        f"- **Recommended entry for this leg: {recommend}.**",
        f"- On TOTAL net R (1s, mixed slippage) the best limit variant `{best_paired['entry_variant']}` (K={best_paired['k_bars']}, {best_paired['stop_mode']} stop) delivers `{best_paired['total_r']:+.4f}R` vs the market baseline's `{baseline_total_mixed:+.4f}R` -- a delta of `{best_paired['delta_total_r']:+.4f}R` "
        + ("(limit BEATS market)." if beats else "(limit does NOT beat market).")
        + f" Paired t-stat `{best_paired['paired_t_stat']}` "
        + ("clears" if sig else "does not clear")
        + f" the multiple-comparison bar (`{deflation['expected_max_null_t']}`).",
        "- **Mixed-slippage read:** the passive-limit-fill assumption (0 ticks on entry) is where limit entries look best; under symmetric 1-2 ticks/side the miss cost erodes more of the edge. See the slippage-sensitivity table.",
        "- **The core tradeoff:** deeper limits (retrace75, sweep-extreme, cons-low) improve entry the most per fill but miss more winners; shallow/near-market limits fill almost always but add little. The best combo balances fill rate against improvement. Missed-winner vs missed-loser rates in the variant table show whether the misses are disproportionately the trades you wanted.",
        "- All rows are `research_only`; nothing here authorizes live implementation. Live limit-entry execution would additionally need real book/queue modelling, which this bar-path fill proxy does not provide.",
        "",
        "## Artifacts",
        "",
        f"- Results: `backtesting/data/results/{RUN_SLUG}/`",
        f"- Report: `backtesting/learnings/reports/{REPORT_PATH.name}`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
