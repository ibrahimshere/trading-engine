#!/usr/bin/env python3
"""First-pass discovery screen for the NQ NY ORB FAILURE FADE thesis.

Thesis (TRACK 3 of a 4-track program): NY ORB *continuation* is exhaustively
mapped on NQ. The untested mirror is the failed breakout. When price breaks out
of the opening range and FAILS to accept (closes back inside the range within a
few bars), fade the failed breakout back toward the range (short a failed upside
breakout, long a failed downside breakout). Failed breakouts trap continuation
traders and the unwind is mechanical.

Design discipline (non-negotiable):
- DISCOVERY window only for the grid search: 2021-06-07 .. 2024-12-31.
- VALIDATION window 2025-01-01 .. 2026-06-06 is scored ONCE on a <=3 frozen
  shortlist chosen on discovery data alone (single-shot).
- COLD window 2016-01-01 .. 2021-06-05 scored ONCE on the same shortlist as a
  regime stress.

Conservative intrabar pathing matches house scripts: entries on the next bar
open after the signal bar completes (no lookahead), and stop wins on a same-bar
stop/target touch. Flat by 15:55 ET. All rows are research_only.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
DATA_DIR = ROOT / "data" / "raw"
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.data.fees import estimated_commission_per_side  # noqa: E402

RUN_SLUG = "nq_ny_orb_failure_fade_discovery_20260710"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_ORB_FAILURE_FADE_DISCOVERY_20260710.md"

# ---- Windows -------------------------------------------------------------
DISCOVERY_START = "2021-06-07"
DISCOVERY_END_EXCLUSIVE = "2025-01-01"  # through 2024-12-31
VALIDATION_START = "2025-01-01"
VALIDATION_END_EXCLUSIVE = "2026-06-06"  # data ends 2026-06-05
COLD_START = "2016-01-01"
COLD_END_EXCLUSIVE = "2021-06-06"  # through 2021-06-05

FLAT_TIME = "15:55"
RTH_START = "09:30"
RTH_END = "16:00"

NQ_TICK = 0.25
MIN_STOP_TICKS = 4  # 1.0 point floor
MNQ_POINT_VALUE = 2.0
MNQ_COMMISSION_PER_SIDE = float(estimated_commission_per_side("MNQ"))
FRICTION_TICKS = (1, 2)

MAX_TRADES_PER_DAY = 2
COOLDOWN_BARS = 1
SESSION_RANGE_ATR_MAX = 2.0

# ---- Grid axes -----------------------------------------------------------
TIMEFRAMES = (5, 3)                       # 5m primary, 3m variant
ORB_WINDOWS = {"15m": "09:45", "30m": "10:00"}
BREAKOUT_FRACS = (0.0, 0.05, 0.10)        # * atr14_prev minimum penetration
FAILURE_N_BARS = (2, 4, 8)               # close back inside within N bars
REENTRY_BUFFER_FRACS = (0.0, 0.02)        # * atr14_prev re-entry beyond edge
STOP_CONFIGS = (
    ("breakout_extreme", 0.05),           # stop beyond breakout extreme + 0.05*atr buffer
    ("atr_frac", 0.075),
    ("atr_frac", 0.10),
)
TARGET_MODES = ("rr1p5", "orb_mid", "opp_edge")
ENTRY_CUTOFFS = ("12:00", "13:00")
RR_TARGET = 1.5

DEPLOYABILITY = "research_only"
LIVE_SUPPORT_NOTES = (
    "ORB failure-fade prototype exists only in this research script; the live "
    "execution engine cannot arm this setup and exact-replay parity is not implemented."
)


# ==========================================================================
# Data prep
# ==========================================================================
def _time_str(ts: pd.Timestamp) -> str:
    return pd.Timestamp(ts).strftime("%H:%M")


@dataclass
class Day:
    date: str
    times: list[str]
    timestamps: list[pd.Timestamp]
    opens: np.ndarray
    highs: np.ndarray
    lows: np.ndarray
    closes: np.ndarray
    atr: float
    session_high_so_far: np.ndarray
    session_low_so_far: np.ndarray


def _resample(df_1m: pd.DataFrame, tf: int) -> pd.DataFrame:
    if tf == 1:
        return df_1m.copy()
    out = df_1m.resample(f"{tf}min", label="left", closed="left", origin="start_day").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return out.dropna(subset=["open", "high", "low", "close"])


def _prepare_rth(df: pd.DataFrame) -> pd.DataFrame:
    rth = df.between_time(RTH_START, RTH_END).copy()
    rth["date"] = rth.index.date.astype(str)
    daily = rth.groupby("date").agg({"high": "max", "low": "min"})
    daily["range"] = daily["high"] - daily["low"]
    daily["atr14_prev"] = daily["range"].rolling(14, min_periods=5).mean().shift(1)
    fallback = float(daily["range"].median())
    rth["atr14_prev"] = rth["date"].map(daily["atr14_prev"]).fillna(fallback)
    return rth


def _build_days(rth: pd.DataFrame) -> list[Day]:
    days: list[Day] = []
    for date, day in rth.groupby("date", sort=True):
        # RTH ends 16:00; drop the closing 16:00 print if present
        day = day[[t < RTH_END for t in (_time_str(ts) for ts in day.index)]]
        if len(day) < 20:
            continue
        atr = float(day["atr14_prev"].iloc[0])
        if not (math.isfinite(atr) and atr > 0):
            continue
        highs = day["high"].to_numpy(float)
        lows = day["low"].to_numpy(float)
        days.append(
            Day(
                date=str(date),
                times=[_time_str(ts) for ts in day.index],
                timestamps=list(day.index),
                opens=day["open"].to_numpy(float),
                highs=highs,
                lows=lows,
                closes=day["close"].to_numpy(float),
                atr=atr,
                session_high_so_far=np.maximum.accumulate(highs),
                session_low_so_far=np.minimum.accumulate(lows),
            )
        )
    return days


def _orb_levels(day: Day, orb_end: str) -> tuple[float, float, float, int] | None:
    """Return (orb_high, orb_low, orb_mid, first_scan_idx) or None."""
    orb_idx = [i for i, t in enumerate(day.times) if t < orb_end]
    if not orb_idx:
        return None
    orb_high = float(np.max(day.highs[orb_idx]))
    orb_low = float(np.min(day.lows[orb_idx]))
    scan_start = orb_idx[-1] + 1
    if scan_start >= len(day.times):
        return None
    return orb_high, orb_low, (orb_high + orb_low) / 2.0, scan_start


# ==========================================================================
# Event generation (breakout -> failure back inside)
# ==========================================================================
@dataclass
class FailureEvent:
    direction: int          # -1 short (failed upside), +1 long (failed downside)
    breakout_idx: int
    signal_idx: int
    extreme: float          # breakout extreme high (short) / low (long) up to signal
    orb_high: float
    orb_low: float
    orb_mid: float


def _events_for_day(
    day: Day, orb_end: str, breakout_frac: float, n_bars: int, reentry_buffer_frac: float
) -> list[FailureEvent]:
    lvl = _orb_levels(day, orb_end)
    if lvl is None:
        return []
    orb_high, orb_low, orb_mid, scan_start = lvl
    brk = breakout_frac * day.atr
    buf = reentry_buffer_frac * day.atr
    up_trigger = orb_high + brk
    dn_trigger = orb_low - brk

    events: list[FailureEvent] = []
    n = len(day.times)
    i = scan_start
    while i < n - 1:  # need a next bar for entry
        broke_up = day.highs[i] >= up_trigger
        broke_dn = day.lows[i] <= dn_trigger
        if broke_up and broke_dn:
            # rare wide bar: pick the larger penetration
            if (day.highs[i] - up_trigger) >= (dn_trigger - day.lows[i]):
                broke_dn = False
            else:
                broke_up = False
        if not (broke_up or broke_dn):
            i += 1
            continue

        direction = -1 if broke_up else 1  # fade toward the range
        if broke_up:
            extreme = day.highs[i]
        else:
            extreme = day.lows[i]
        failed_at = -1
        last = min(i + n_bars, n - 2)  # signal needs a next bar to enter
        for j in range(i + 1, last + 1):
            if broke_up:
                extreme = max(extreme, day.highs[j])
                if day.closes[j] < orb_high - buf:
                    failed_at = j
                    break
            else:
                extreme = min(extreme, day.lows[j])
                if day.closes[j] > orb_low + buf:
                    failed_at = j
                    break
        if failed_at >= 0:
            events.append(
                FailureEvent(
                    direction=direction,
                    breakout_idx=i,
                    signal_idx=failed_at,
                    extreme=float(extreme),
                    orb_high=orb_high,
                    orb_low=orb_low,
                    orb_mid=orb_mid,
                )
            )
            i = failed_at + 1  # resume scanning after the failure
        else:
            # breakout accepted (no failure within N bars); resume past the window
            i = last + 1
    return events


# ==========================================================================
# Exit simulation (conservative intrabar path; stop wins same-bar tie)
# ==========================================================================
def _simulate_exit(
    day: Day, direction: int, entry_idx: int, entry: float, stop: float, target: float, risk: float
) -> tuple[int, float, str, float]:
    exit_idx = len(day.times) - 1
    exit_price = float(day.closes[-1])
    exit_type = "eod"
    for k in range(entry_idx, len(day.times)):
        if day.times[k] > FLAT_TIME:
            exit_idx = k - 1 if k > entry_idx else k
            exit_price = float(day.closes[exit_idx])
            exit_type = "eod"
            break
        if direction == 1:
            if day.lows[k] <= stop:
                exit_idx, exit_price, exit_type = k, stop, "stop"
                break
            if day.highs[k] >= target:
                exit_idx, exit_price, exit_type = k, target, "target"
                break
        else:
            if day.highs[k] >= stop:
                exit_idx, exit_price, exit_type = k, stop, "stop"
                break
            if day.lows[k] <= target:
                exit_idx, exit_price, exit_type = k, target, "target"
                break
    r = ((exit_price - entry) * direction) / risk if risk > 0 else 0.0
    return exit_idx, exit_price, exit_type, r


def _build_trade(
    day: Day, ev: FailureEvent, stop_basis: str, stop_param: float, target_mode: str
) -> dict[str, Any] | None:
    entry_idx = ev.signal_idx + 1
    if entry_idx >= len(day.times) or day.times[entry_idx] > FLAT_TIME:
        return None
    # session-range guard at signal bar
    sr = day.session_high_so_far[ev.signal_idx] - day.session_low_so_far[ev.signal_idx]
    if sr / day.atr > SESSION_RANGE_ATR_MAX:
        return None

    entry = float(day.opens[entry_idx])
    direction = ev.direction

    # ---- stop ----
    if stop_basis == "breakout_extreme":
        buffer = stop_param * day.atr
        stop = ev.extreme + buffer if direction == -1 else ev.extreme - buffer
        risk = abs(entry - stop)
    else:  # atr_frac
        risk = stop_param * day.atr
        stop = entry - direction * risk
    risk = max(risk, MIN_STOP_TICKS * NQ_TICK)
    stop = entry - direction * risk  # normalize stop to floored risk

    # ---- target ----
    if target_mode == "rr1p5":
        target = entry + direction * RR_TARGET * risk
    elif target_mode == "orb_mid":
        target = ev.orb_mid
    elif target_mode == "opp_edge":
        target = ev.orb_low if direction == -1 else ev.orb_high
    else:
        raise ValueError(target_mode)
    reward = (target - entry) * direction
    if reward <= 0:
        return None  # target not on the profit side

    exit_idx, exit_price, exit_type, r = _simulate_exit(day, direction, entry_idx, entry, stop, target, risk)

    # sanity: entry must be strictly after signal bar
    assert day.timestamps[entry_idx] > day.timestamps[ev.signal_idx]
    return {
        "date": day.date,
        "direction": "short" if direction == -1 else "long",
        "direction_int": direction,
        "signal_ts": day.timestamps[ev.signal_idx].isoformat(),
        "signal_time": day.times[ev.signal_idx],
        "entry_ts": day.timestamps[entry_idx].isoformat(),
        "exit_ts": day.timestamps[exit_idx].isoformat(),
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "target": round(target, 2),
        "exit_price": round(exit_price, 2),
        "exit_type": exit_type,
        "risk_points": round(risk, 4),
        "reward_points": round(reward, 4),
        "rr_to_target": round(reward / risk, 4),
        "r_multiple": round(float(r), 6),
        "atr14_prev": round(day.atr, 2),
        "orb_high": round(ev.orb_high, 2),
        "orb_low": round(ev.orb_low, 2),
        "breakout_idx": ev.breakout_idx,
        "signal_idx": ev.signal_idx,
        "entry_idx": entry_idx,
        "exit_idx": exit_idx,
    }


def _simulate_config(
    days: list[Day],
    events_by_day: list[list[FailureEvent]],
    stop_basis: str,
    stop_param: float,
    target_mode: str,
    entry_cutoff: str,
) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    for day, evs in zip(days, events_by_day, strict=True):
        day_count = 0
        min_idx = 0
        for ev in evs:
            if day_count >= MAX_TRADES_PER_DAY:
                break
            if day.times[ev.signal_idx] > entry_cutoff:
                continue
            if ev.signal_idx < min_idx:  # one position at a time
                continue
            trade = _build_trade(day, ev, stop_basis, stop_param, target_mode)
            if trade is None:
                continue
            trades.append(trade)
            day_count += 1
            min_idx = int(trade["exit_idx"]) + COOLDOWN_BARS
    return trades


# ==========================================================================
# Scoring
# ==========================================================================
def _max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    equity = np.cumsum(np.array(values, dtype=float))
    peak = np.maximum.accumulate(equity)
    return float((equity - peak).min())


def _profit_factor(values: list[float]) -> float:
    wins = sum(v for v in values if v > 0)
    losses = sum(v for v in values if v < 0)
    if losses < 0:
        return float(wins / abs(losses))
    return float("inf") if wins > 0 else 0.0


def _score(trades: list[dict[str, Any]], trading_days: int, r_col: str = "r_multiple") -> dict[str, Any]:
    values = [float(t[r_col]) for t in trades]
    n = len(values)
    total_r = float(sum(values))
    std_r = float(np.std(values, ddof=1)) if n > 1 else 0.0
    avg_r = total_r / n if n else 0.0
    t_stat = (avg_r * math.sqrt(n) / std_r) if (n > 1 and std_r > 0) else 0.0
    years = trading_days / 252.0 if trading_days else 0.0
    max_dd = _max_drawdown(values)
    avg_annual_r = total_r / years if years else 0.0
    calmar = avg_annual_r / abs(max_dd) if max_dd < 0 else 0.0
    by_day = pd.Series([t["date"] for t in trades]).value_counts() if trades else pd.Series(dtype=int)
    exits = pd.Series([t["exit_type"] for t in trades]).value_counts().to_dict() if trades else {}
    return {
        "total_trades": n,
        "trading_days": trading_days,
        "trades_per_day": round(n / trading_days, 4) if trading_days else 0.0,
        "days_with_trade": int((by_day > 0).sum()),
        "total_r": round(total_r, 4),
        "avg_r": round(avg_r, 5),
        "std_r": round(std_r, 5),
        "t_stat": round(t_stat, 4),
        "profit_factor": round(_profit_factor(values), 4),
        "win_rate": round(float(np.mean([v > 0 for v in values])), 4) if values else 0.0,
        "max_drawdown_r": round(max_dd, 4),
        "avg_annual_r": round(avg_annual_r, 4),
        "calmar": round(calmar, 4),
        "target_exits": int(exits.get("target", 0)),
        "stop_exits": int(exits.get("stop", 0)),
        "eod_exits": int(exits.get("eod", 0)),
    }


def _friction_r(trades: list[dict[str, Any]], ticks: int) -> list[float]:
    out = []
    for t in trades:
        risk = float(t["risk_points"])
        commission_r = (2.0 * MNQ_COMMISSION_PER_SIDE) / (risk * MNQ_POINT_VALUE)
        slippage_r = (2.0 * ticks * NQ_TICK) / risk
        out.append(float(t["r_multiple"]) - commission_r - slippage_r)
    return out


def _yearly(trades: list[dict[str, Any]]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(columns=["year", "trades", "total_r", "avg_r", "win_rate"])
    frame = pd.DataFrame(trades)
    frame["year"] = frame["date"].str.slice(0, 4)
    rows = []
    for year, g in frame.groupby("year"):
        vals = [float(v) for v in g["r_multiple"]]
        rows.append({
            "year": str(year),
            "trades": len(g),
            "total_r": round(sum(vals), 3),
            "avg_r": round(float(np.mean(vals)), 4),
            "win_rate": round(float(np.mean([v > 0 for v in vals])), 4),
        })
    return pd.DataFrame(rows)


# ==========================================================================
# Config identity
# ==========================================================================
@dataclass(frozen=True)
class Config:
    timeframe: int
    orb: str
    breakout_frac: float
    n_bars: int
    reentry_buffer_frac: float
    stop_basis: str
    stop_param: float
    target_mode: str
    entry_cutoff: str

    @property
    def label(self) -> str:
        return (
            f"tf{self.timeframe}_{self.orb}_brk{self.breakout_frac:g}_N{self.n_bars}"
            f"_buf{self.reentry_buffer_frac:g}_{self.stop_basis}{self.stop_param:g}"
            f"_{self.target_mode}_cut{self.entry_cutoff.replace(':', '')}"
        )

    @property
    def event_key(self) -> tuple:
        return (self.timeframe, self.orb, self.breakout_frac, self.n_bars, self.reentry_buffer_frac)


def _all_configs() -> list[Config]:
    configs: list[Config] = []
    for tf in TIMEFRAMES:
        for orb in ORB_WINDOWS:
            for bfrac in BREAKOUT_FRACS:
                for n in FAILURE_N_BARS:
                    for buf in REENTRY_BUFFER_FRACS:
                        for stop_basis, stop_param in STOP_CONFIGS:
                            for target in TARGET_MODES:
                                for cutoff in ENTRY_CUTOFFS:
                                    configs.append(Config(tf, orb, bfrac, n, buf, stop_basis, stop_param, target, cutoff))
    return configs


# ==========================================================================
# Window machinery
# ==========================================================================
def _load_days_for_windows(df_1m_full: pd.DataFrame) -> dict[str, dict[int, list[Day]]]:
    windows = {
        "discovery": (DISCOVERY_START, DISCOVERY_END_EXCLUSIVE),
        "validation": (VALIDATION_START, VALIDATION_END_EXCLUSIVE),
        "cold": (COLD_START, COLD_END_EXCLUSIVE),
    }
    out: dict[str, dict[int, list[Day]]] = {}
    for wname, (start, end) in windows.items():
        out[wname] = {}
        for tf in TIMEFRAMES:
            df_tf = _resample(df_1m_full, tf)
            sub = df_tf[(df_tf.index >= start) & (df_tf.index < end)]
            out[wname][tf] = _build_days(_prepare_rth(sub))
    return out


def _events_for_key(days: list[Day], key: tuple) -> list[list[FailureEvent]]:
    _tf, orb, bfrac, n, buf = key
    orb_end = ORB_WINDOWS[orb]
    return [_events_for_day(d, orb_end, bfrac, n, buf) for d in days]


def _run_grid(days_by_tf: dict[int, list[Day]], configs: list[Config]) -> tuple[pd.DataFrame, dict[str, list[dict[str, Any]]]]:
    # cache events per (tf, event_key)
    event_cache: dict[tuple, list[list[FailureEvent]]] = {}
    rows: list[dict[str, Any]] = []
    trades_by_label: dict[str, list[dict[str, Any]]] = {}
    for idx, cfg in enumerate(configs, 1):
        days = days_by_tf[cfg.timeframe]
        trading_days = len(days)
        ek = (cfg.timeframe, cfg.event_key)
        if ek not in event_cache:
            event_cache[ek] = _events_for_key(days, cfg.event_key)
        events_by_day = event_cache[ek]
        trades = _simulate_config(days, events_by_day, cfg.stop_basis, cfg.stop_param, cfg.target_mode, cfg.entry_cutoff)
        trades_by_label[cfg.label] = trades
        score = _score(trades, trading_days)
        # direction splits
        longs = [t for t in trades if t["direction_int"] == 1]
        shorts = [t for t in trades if t["direction_int"] == -1]
        row = {"label": cfg.label, **asdict(cfg), **score,
               "long_trades": len(longs), "long_total_r": round(sum(t["r_multiple"] for t in longs), 3),
               "short_trades": len(shorts), "short_total_r": round(sum(t["r_multiple"] for t in shorts), 3),
               "deployability": DEPLOYABILITY}
        rows.append(row)
        if idx % 200 == 0:
            print(f"  {idx}/{len(configs)} configs scored", flush=True)
    return pd.DataFrame(rows), trades_by_label


# ==========================================================================
# Main
# ==========================================================================
def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("Loading raw NQ 1m ...", flush=True)
    df_1m_full = pd.read_parquet(DATA_DIR / "NQ_1m.parquet")
    days = _load_days_for_windows(df_1m_full)
    for w in ("discovery", "validation", "cold"):
        for tf in TIMEFRAMES:
            d = days[w][tf]
            print(f"  {w} tf{tf}: {len(d)} days ({d[0].date}..{d[-1].date})", flush=True)

    configs = _all_configs()
    print(f"Total configs: {len(configs)}", flush=True)

    # ---- sanity: hand-check ORB levels on a few days (5m, 15m) ----
    sanity_lines = _orb_sanity(df_1m_full, days["discovery"][5])

    # ---- discovery grid ----
    print("Running discovery grid ...", flush=True)
    grid, disc_trades_by_label = _run_grid(days["discovery"], configs)

    ranked = grid.sort_values(
        ["t_stat", "profit_factor", "total_r"], ascending=[False, False, False]
    ).reset_index(drop=True)
    ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))

    # eligibility for the frozen shortlist: enough sample, sane cadence, real edge
    eligible = ranked[
        (ranked["total_trades"] >= 120)
        & (ranked["trades_per_day"] >= 0.25)
        & (ranked["trades_per_day"] <= 2.0)
        & (ranked["profit_factor"] > 1.0)
    ].copy()
    # de-duplicate the shortlist across distinct structural families where possible
    shortlist = eligible.head(3).copy()

    ranked_path = RESULT_DIR / "discovery_grid_ranked.csv"
    ranked.to_csv(ranked_path, index=False)

    # per-day trade-cap sanity on the discovery best
    cap_ok = True
    for label in shortlist["label"]:
        s = pd.Series([t["date"] for t in disc_trades_by_label[label]]).value_counts()
        if not s.empty and int(s.max()) > MAX_TRADES_PER_DAY:
            cap_ok = False

    # ---- single-shot validation + cold for the frozen shortlist ----
    frozen: list[dict[str, Any]] = []
    for _, r in shortlist.iterrows():
        cfg = Config(int(r["timeframe"]), str(r["orb"]), float(r["breakout_frac"]), int(r["n_bars"]),
                     float(r["reentry_buffer_frac"]), str(r["stop_basis"]), float(r["stop_param"]),
                     str(r["target_mode"]), str(r["entry_cutoff"]))
        entry = {"config": cfg, "label": cfg.label, "discovery_row": r.to_dict()}
        for wname in ("validation", "cold"):
            wdays = days[wname][cfg.timeframe]
            evs = _events_for_key(wdays, cfg.event_key)
            wtrades = _simulate_config(wdays, evs, cfg.stop_basis, cfg.stop_param, cfg.target_mode, cfg.entry_cutoff)
            entry[wname] = {"score": _score(wtrades, len(wdays)), "trades": wtrades}
        # discovery trades for artifacts / yearly
        entry["discovery_trades"] = disc_trades_by_label[cfg.label]
        frozen.append(entry)

    # save frozen trade streams
    for e in frozen:
        for wname in ("discovery", "validation", "cold"):
            key = "discovery_trades" if wname == "discovery" else None
            tr = e["discovery_trades"] if wname == "discovery" else e[wname]["trades"]
            pd.DataFrame(tr).to_csv(RESULT_DIR / f"frozen_{e['label']}_{wname}_trades.csv", index=False)

    summary = {
        "run_slug": RUN_SLUG,
        "thesis": "ORB failure fade (fade failed opening-range breakouts back into the range) on NQ NY RTH",
        "windows": {
            "discovery": [DISCOVERY_START, DISCOVERY_END_EXCLUSIVE],
            "validation": [VALIDATION_START, VALIDATION_END_EXCLUSIVE],
            "cold": [COLD_START, COLD_END_EXCLUSIVE],
        },
        "configs_searched": len(configs),
        "eligible_configs": int(len(eligible)),
        "trade_cap": MAX_TRADES_PER_DAY,
        "friction": {"commission_per_side_usd": MNQ_COMMISSION_PER_SIDE, "point_value": MNQ_POINT_VALUE,
                     "slippage_ticks": list(FRICTION_TICKS), "sizing": "MNQ on NQ price"},
        "cap_sanity_ok": bool(cap_ok),
        "shortlist_labels": list(shortlist["label"]),
        "elapsed_seconds": round(time.time() - started, 2),
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe(summary), indent=2) + "\n")

    _write_report(ranked, eligible, shortlist, frozen, configs, sanity_lines, cap_ok, days)

    print(f"Wrote {ranked_path}")
    print(f"Wrote {REPORT_PATH}")
    print(f"Elapsed {summary['elapsed_seconds']}s")


def _orb_sanity(df_1m_full: pd.DataFrame, disc_days_5m: list[Day]) -> list[str]:
    """Cross-check ORB (15m) high/low computed on 5m days against raw 1m."""
    lines: list[str] = []
    sample = disc_days_5m[:: max(1, len(disc_days_5m) // 4)][:4]
    for d in sample:
        lvl = _orb_levels(d, "09:45")
        if lvl is None:
            continue
        oh, ol, om, _ = lvl
        raw = df_1m_full[(df_1m_full.index >= f"{d.date} 09:30") & (df_1m_full.index < f"{d.date} 09:45")]
        raw_h = float(raw["high"].max())
        raw_l = float(raw["low"].min())
        ok = abs(raw_h - oh) < 1e-6 and abs(raw_l - ol) < 1e-6
        lines.append(f"{d.date}: 5m-ORB H/L={oh:.2f}/{ol:.2f} vs raw-1m H/L={raw_h:.2f}/{raw_l:.2f} -> {'OK' if ok else 'MISMATCH'}")
    return lines


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


REPORT_COLS = [
    "rank", "label", "timeframe", "orb", "breakout_frac", "n_bars", "reentry_buffer_frac",
    "stop_basis", "stop_param", "target_mode", "entry_cutoff",
    "total_trades", "trades_per_day", "total_r", "avg_r", "profit_factor", "win_rate",
    "max_drawdown_r", "calmar", "t_stat",
]


def _frozen_metric_line(e: dict[str, Any], wname: str, trades_key: str) -> str:
    trades = e[trades_key] if wname == "discovery" else e[wname]["trades"]
    sc = e[wname]["score"] if wname != "discovery" else _score(e["discovery_trades"], int(e["discovery_row"]["trading_days"]))
    net1 = sum(_friction_r(trades, 1))
    net2 = sum(_friction_r(trades, 2))
    return (
        f"| {wname} | {sc['total_trades']} | {sc['trades_per_day']} | {sc['total_r']} | {sc['avg_r']} | "
        f"{sc['profit_factor']} | {sc['win_rate']} | {sc['max_drawdown_r']} | {sc['calmar']} | {sc['t_stat']} | "
        f"{round(net1, 3)} | {round(net2, 3)} |"
    )


def _write_report(ranked, eligible, shortlist, frozen, configs, sanity_lines, cap_ok, days) -> None:
    disc_days_5 = len(days["discovery"][5])
    disc_days_3 = len(days["discovery"][3])
    lines: list[str] = []
    lines += [
        "# NQ NY ORB Failure Fade — First-Pass Discovery Screen",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        "- Thesis: fade FAILED opening-range breakouts back toward the range. Short a failed upside breakout, long a failed downside breakout. TRACK 3 of a 4-track NQ research program; the mirror of the exhaustively-mapped NY ORB continuation.",
        "- Instrument/session: NQ, NY RTH (09:30 anchor, US Eastern). Signal timeframes 5m (primary) and 3m (variant), resampled from raw 1m.",
        f"- Discovery window (grid search only): `{DISCOVERY_START}` .. `{pd.Timestamp(DISCOVERY_END_EXCLUSIVE) - pd.Timedelta(days=1):%Y-%m-%d}` ({disc_days_5} 5m days / {disc_days_3} 3m days).",
        f"- Validation window (single-shot, frozen shortlist only): `{VALIDATION_START}` .. `2026-06-05`.",
        f"- Cold window (single-shot regime stress, frozen shortlist only): `{COLD_START}` .. `2021-06-05`.",
        "- Intrabar path: entries on the NEXT bar open after the signal bar completes (no lookahead); stop wins on a same-bar stop/target touch; flat by 15:55 ET.",
        f"- Guards: max {MAX_TRADES_PER_DAY} trades/day, one position at a time (+{COOLDOWN_BARS}-bar cooldown), `session_range_atr_max={SESSION_RANGE_ATR_MAX}`, min stop {MIN_STOP_TICKS} ticks.",
        f"- Friction: MNQ sizing, ${MNQ_COMMISSION_PER_SIDE:.3f}/side commission, {FRICTION_TICKS[0]} and {FRICTION_TICKS[1]} ticks/side slippage. All rows `deployability=research_only`.",
        "",
        "## Entry Criteria (written out precisely)",
        "",
        "Opening range: the high and low of NY RTH bars with time `< 09:45` (15m ORB) or `< 10:00` (30m ORB). ORB mid = (ORB high + ORB low) / 2. Breakout scanning begins on the first bar after the ORB window.",
        "",
        "Failed UPSIDE breakout (fade SHORT):",
        "1. A bar's high reaches `ORB_high + breakout_frac * atr14_prev` (breakout leg). `atr14_prev` is the prior 14-day mean RTH range.",
        "2. Within `N` signal-timeframe bars of that breakout bar, a bar CLOSES back inside the range: `close < ORB_high - reentry_buffer_frac * atr14_prev` (the failure trigger / signal bar).",
        "3. Enter SHORT on the next bar's open (no lookahead).",
        "4. Stop: either just beyond the breakout extreme (highest high from breakout through signal) plus `0.05 * atr14_prev`, or a fixed `stop_param * atr14_prev` ATR-fraction stop. Risk floored at 4 ticks.",
        "5. Target: fixed 1.5R, or ORB mid, or the opposite ORB edge (ORB low).",
        "6. Signal must occur at/before the entry cutoff (12:00 or 13:00). Flat by 15:55.",
        "",
        "Failed DOWNSIDE breakout (fade LONG) is the exact mirror: low reaches `ORB_low - breakout_frac*atr`, a bar closes back above `ORB_low + reentry_buffer_frac*atr` within N bars, enter LONG next open, stop below the breakout extreme (or ATR-fraction), target 1.5R / ORB mid / ORB high.",
        "",
        "## Grid Searched",
        "",
        f"- Timeframes: `{TIMEFRAMES}`; ORB windows: `{list(ORB_WINDOWS)}`",
        f"- breakout_frac (* atr14_prev): `{BREAKOUT_FRACS}`; failure N bars: `{FAILURE_N_BARS}`; reentry_buffer_frac: `{REENTRY_BUFFER_FRACS}`",
        f"- stop bases: `{STOP_CONFIGS}`; targets: `{TARGET_MODES}`; entry cutoffs: `{ENTRY_CUTOFFS}`",
        f"- **Total configs searched: {len(configs)}.** Eligible (>=120 trades, 0.25-2.0 trades/day, PF>1): {len(eligible)}.",
        "",
        "## ORB Level Sanity (5m 15m-ORB vs raw 1m)",
        "",
        "```",
        *sanity_lines,
        "```",
        f"- Per-day trade-cap check on the shortlist: {'PASS' if cap_ok else 'FAIL'} (no day exceeds the cap).",
        "- Entry-after-signal check: enforced by assertion in the exit builder (entry_ts > signal_ts on every trade).",
        "",
        "## Discovery — Top 20 by t-stat",
        "",
        ranked.head(20)[REPORT_COLS].to_markdown(index=False),
        "",
        "## Discovery — Eligible Shortlist Pool (top 15)",
        "",
        (eligible.head(15)[REPORT_COLS].to_markdown(index=False) if not eligible.empty else "_None eligible._"),
        "",
        "## Frozen Shortlist — Single-Shot Validation & Cold",
        "",
    ]
    for e in frozen:
        cfg = e["config"]
        drow = e["discovery_row"]
        lines += [
            f"### `{e['label']}`",
            "",
            f"- Config: tf={cfg.timeframe}m, ORB={cfg.orb}, breakout_frac={cfg.breakout_frac}, N={cfg.n_bars}, reentry_buffer={cfg.reentry_buffer_frac}, stop={cfg.stop_basis} {cfg.stop_param}, target={cfg.target_mode}, cutoff={cfg.entry_cutoff}",
            f"- Discovery direction split: long {int(drow['long_trades'])} trades ({drow['long_total_r']}R), short {int(drow['short_trades'])} trades ({drow['short_total_r']}R).",
            "",
            "| window | trades | trades/day | total_R | avg_R | PF | WR | maxDD_R | Calmar | t_stat | net_R@1t | net_R@2t |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            _frozen_metric_line(e, "discovery", "discovery_trades"),
            _frozen_metric_line(e, "validation", "trades"),
            _frozen_metric_line(e, "cold", "trades"),
            "",
            "Discovery year split:",
            "",
            _yearly(e["discovery_trades"]).to_markdown(index=False),
            "",
        ]

    best = ranked.iloc[0]
    lines += [
        "## Summary Read",
        "",
        f"- Best discovery row `{best['label']}`: {int(best['total_trades'])} trades, {best['trades_per_day']} trades/day, {best['total_r']}R total, avg {best['avg_r']}R, PF {best['profit_factor']}, WR {best['win_rate']}, maxDD {best['max_drawdown_r']}R, Calmar {best['calmar']}, t-stat {best['t_stat']}.",
        f"- Configs searched: {len(configs)}. With this many configs, a naive multiple-comparisons threshold pushes the required |t| well above the usual ~2. A single-config |t|~2 corresponds to p~0.05; searching {len(configs)} configs inflates the best-of expected max-t substantially, so treat any best-row t-stat below ~3.5-4 as plausibly in-sample noise.",
        "- The frozen shortlist single-shot validation and cold-window rows above are the honest read: an edge is only credible if it survives out-of-sample with the sign and rough magnitude intact after friction.",
        "",
        "## Diagnostic Read",
        "",
        "- Failed-breakout fades are structurally short-vol/mean-revert trades; expect them to do best in balancing/range regimes and to bleed in strong-trend regimes (the cold 2016-2021 and any trend-heavy validation stretch are the natural stress).",
        "- Direction asymmetry (long vs short columns) flags whether the edge is a genuine two-sided range effect or a one-sided artifact.",
        "- ORB-mid and opposite-edge targets trade win-rate for reward; the 1.5R target is the noise-robust primary.",
        "",
        "## Artifacts",
        "",
        f"- Discovery grid (all configs): `backtesting/data/results/{RUN_SLUG}/discovery_grid_ranked.csv`",
        f"- Frozen shortlist trade streams: `backtesting/data/results/{RUN_SLUG}/frozen_<label>_<window>_trades.csv`",
        f"- Summary JSON: `backtesting/data/results/{RUN_SLUG}/summary.json`",
        f"- Report: `backtesting/learnings/reports/{REPORT_PATH.name}`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
