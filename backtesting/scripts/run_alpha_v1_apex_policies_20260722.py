#!/usr/bin/env python3
"""Apex 50K EOD PA policy explorations for ALPHA_V1-A menus.

Three questions (follow-ups to run_alpha_v1_apex_lifecycle_20260722.py):
  A. Day-capping: flatten/stop for the day once day PnL reaches a cap
     (e.g. $1,300 = 50% of the $2,600 fresh-PA request minimum). Worth it?
     Where is the best cap? Modeled as clipping positive day PnL at the cap.
  B. Adaptive consistency sizing: when the 50% consistency gate is currently
     blocking (best day >= 50% of cycle net), trade at half size until it
     unblocks. Modeled as scaling subsequent day PnL by 0.5 while blocked.
  C. Tier-1 contract-cap feasibility: max concurrent micro contracts implied
     by the historical exact stream at a given flat risk vs the 20/30/40
     micro caps (10 micros = 1 standard).

Same Apex rules as the lifecycle script otherwise.
"""
from __future__ import annotations

import csv
import random
import statistics
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_alpha_v1_phase_two_portfolio_20260722 import (  # noqa: E402
    BASELINE, CALENDAR, COMMON_START, COMMON_END, RECENT_START, OUT_DIR, daily_pnl,
)

ACCOUNT_COST = 300.0
START_BAL = 50_000.0
TRAIL = 2_000.0
HWM_LOCK = 52_100.0
SAFETY_NET = 52_100.0
MIN_BAL_REQUEST = 52_600.0
QUAL_USD = 250.0
QUAL_REQ = 5
MIN_PAYOUT = 500.0
PAYOUT_CAPS = [1500.0, 1500.0, 2000.0, 2500.0, 2500.0, 3000.0]
LIFE_CAP_DAYS = 2520
N_PATHS = 3000

RECENT_CAL = [d for d in CALENDAR if d >= RECENT_START]


def dll_for_profit(profit: float) -> float:
    if profit < 3_000:
        return 1_000.0
    if profit < 6_000:
        return 2_000.0
    return 3_000.0


def run_pa(days, day_cap: float | None = None, adaptive_half: bool = False,
           start_idx: int = 0):
    bal, hwm_eod = START_BAL, START_BAL
    qual, best_day, net_cycle = 0, 0.0, 0.0
    payouts: list[float] = []
    first_wd = None
    for i in range(start_idx, len(days)):
        t = i - start_idx
        profit = bal - START_BAL
        v = days[i]
        blocked = best_day > 0 and net_cycle > 0 and best_day >= 0.5 * net_cycle
        if adaptive_half and blocked:
            v *= 0.5
        if day_cap is not None and v > day_cap:
            v = day_cap
        v = max(v, -dll_for_profit(profit))
        bal += v
        hwm_eod = max(hwm_eod, bal)
        if bal <= min(hwm_eod, HWM_LOCK) - TRAIL:
            return {"outcome": "breach", "days": t + 1, "withdrawn": sum(payouts),
                    "n_payouts": len(payouts), "first_wd": first_wd}
        if v >= QUAL_USD:
            qual += 1
        if v > 0:
            best_day = max(best_day, v)
        net_cycle += v
        if t % 5 == 4:
            if (bal >= MIN_BAL_REQUEST and qual >= QUAL_REQ and net_cycle > 0
                    and best_day < 0.5 * net_cycle):
                amt = min(PAYOUT_CAPS[len(payouts)], bal - SAFETY_NET)
                if amt >= MIN_PAYOUT:
                    payouts.append(amt)
                    bal -= amt
                    if first_wd is None:
                        first_wd = t + 1
                    qual, best_day, net_cycle = 0, 0.0, 0.0
                    if len(payouts) == 6:
                        return {"outcome": "complete", "days": t + 1,
                                "withdrawn": sum(payouts), "n_payouts": 6,
                                "first_wd": first_wd}
    return {"outcome": "censored", "days": len(days) - start_idx,
            "withdrawn": sum(payouts), "n_payouts": len(payouts), "first_wd": first_wd}


def mc(pool, day_cap=None, adaptive_half=False, seed=20260722):
    rng = random.Random(seed)
    rows = [run_pa([rng.choice(pool) for _ in range(LIFE_CAP_DAYS)],
                   day_cap, adaptive_half) for _ in range(N_PATHS)]
    W = [r["withdrawn"] for r in rows]
    T = [r["days"] for r in rows]
    comp = [r for r in rows if r["outcome"] == "complete"]
    breach = [r for r in rows if r["outcome"] == "breach"]
    return {
        "complete_pct": round(100 * len(comp) / len(rows), 1),
        "breach_pct": round(100 * len(breach) / len(rows), 1),
        "med_days_complete": statistics.median([r["days"] for r in comp]) if comp else None,
        "ev": round(statistics.mean(W) - ACCOUNT_COST, 0),
        "rate_yr": round(252 * (statistics.mean(W) - ACCOUNT_COST) / statistics.mean(T), 0),
    }


def hist(pnl_by_day, calendar, day_cap=None, adaptive_half=False):
    days = [pnl_by_day.get(d, 0.0) for d in calendar]
    starts, seen = [], set()
    for i, d in enumerate(calendar):
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            if len(calendar) - i >= 120:
                starts.append(i)
    rows = [run_pa(days, day_cap, adaptive_half, s) for s in starts]
    comp = [r for r in rows if r["outcome"] == "complete"]
    return {
        "h_complete": f"{len(comp)}/{len(rows)}",
        "h_medWD": round(statistics.median([r["withdrawn"] for r in rows]), 0),
        "h_med_days": statistics.median([r["days"] for r in comp]) if comp else None,
    }


MENUS = {
    "SPLIT5_200": [(BASELINE[s], 200, s) for s in ("NQ_NY_LSI", "NQ_Asia", "ES_Asia", "NQ_NY", "ES_NY")],
    "SPLIT5_250": [(BASELINE[s], 250, s) for s in ("NQ_NY_LSI", "NQ_Asia", "ES_Asia", "NQ_NY", "ES_NY")],
    "SPRINT_X1": [
        (BASELINE["NQ_NY_LSI"], 500, "LSI"), (BASELINE["NQ_Asia"], 400, "NQ Asia"),
        (BASELINE["ES_Asia"], 150, "ES Asia"), (BASELINE["NQ_NY"], 250, "NQ R11"),
        (BASELINE["ES_NY"], 300, "ES NY"),
    ],
}

POLICIES = [
    ("no_policy", None, False),
    ("cap_1000", 1000.0, False),
    ("cap_1300", 1300.0, False),
    ("cap_2000", 2000.0, False),
    ("adaptive_half", None, True),
    ("cap1300_adaptive", 1300.0, True),
]


def policy_sweep():
    out = []
    for mname, menu in MENUS.items():
        pnl = daily_pnl(menu, COMMON_START, COMMON_END)
        pool_full = [pnl.get(d, 0.0) for d in CALENDAR]
        pool_rec = [pnl.get(d, 0.0) for d in RECENT_CAL]
        for pname, cap, adapt in POLICIES:
            f = mc(pool_full, cap, adapt)
            r = mc(pool_rec, cap, adapt, seed=20260723)
            h = hist(pnl, CALENDAR, cap, adapt)
            row = {"menu": mname, "policy": pname}
            row.update({f"full_{k}": v for k, v in f.items()})
            row.update({f"rec_{k}": v for k, v in r.items()})
            row.update(h)
            out.append(row)
            print(f"{mname:11s} {pname:16s} | comp {f['complete_pct']:5.1f}% "
                  f"6th@{str(f['med_days_complete']):>5s}d EV {f['ev']:6.0f} "
                  f"$/yr {f['rate_yr']:6.0f} | 2025+ comp {r['complete_pct']:5.1f}% "
                  f"6th@{str(r['med_days_complete']):>5s}d $/yr {r['rate_yr']:6.0f} | "
                  f"hist {h['h_complete']} medWD {h['h_medWD']:.0f} 6th@{h['h_med_days']}d")
    with open(OUT_DIR / "apex_policies.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)


def contract_feasibility():
    """Max concurrent micros from the exact stream, scaled to flat-risk menus."""
    base_csv = (Path(__file__).resolve().parents[1] / "data" / "results"
                / "alpha_v1_ath_fragility_20260608" / "baseline_trades_ath_annotated.csv")
    configured_risk = {"NQ_NY_LSI": 500.0, "NQ_Asia": 400.0, "ES_Asia": 150.0,
                       "NQ_NY": 250.0, "ES_NY": 300.0}
    trades = []
    with open(base_csv) as fh:
        for row in csv.DictReader(fh):
            try:
                qty = float(row["qty"])
                t0 = datetime.fromisoformat(row["entry_time"])
                t1 = datetime.fromisoformat(row["exit_time"])
            except (ValueError, KeyError):
                continue
            trades.append((t0, t1, row["session"], qty))
    print("\n=== Contract-cap feasibility (max concurrent micros; 10 micros = 1 standard) ===")
    for label, flat in (("flat $200", 200.0), ("flat $250", 250.0)):
        events = []
        for t0, t1, sess, qty in trades:
            scaled = qty * flat / configured_risk[sess]
            events.append((t0, scaled))
            events.append((t1, -scaled))
        events.sort(key=lambda e: e[0])
        cur = peak = 0.0
        daily_peak = defaultdict(float)
        for ts, dq in events:
            cur += dq
            peak = max(peak, cur)
            key = ts.date()
            daily_peak[key] = max(daily_peak[key], cur)
        peaks = sorted(daily_peak.values())
        n = len(peaks)
        over20 = sum(1 for p in peaks if p > 20)
        over30 = sum(1 for p in peaks if p > 30)
        over40 = sum(1 for p in peaks if p > 40)
        q = lambda pct: peaks[int(pct * (n - 1))]
        print(f"  {label}: all-time peak {peak:.1f} micros | daily-peak p50 {q(0.5):.1f} "
              f"p90 {q(0.9):.1f} p99 {q(0.99):.1f} | days over Tier1(20) {over20}/{n} "
              f"({100*over20/n:.1f}%), Tier2(30) {over30} ({100*over30/n:.1f}%), "
              f"Tier3+(40) {over40} ({100*over40/n:.1f}%)")


if __name__ == "__main__":
    policy_sweep()
    contract_feasibility()
    print(f"\nSaved {OUT_DIR / 'apex_policies.csv'}")
