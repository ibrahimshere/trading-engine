#!/usr/bin/env python3
"""Apex 50K EOD PA exact-rules lifecycle simulation for ALPHA_V1-A menus.

Rules modeled (from apextraderfunding.com help center, fetched 2026-07-22):
  - EOD trailing threshold: $2,000 behind highest EOD balance, locks at $50,100
    once highest EOD balance reaches $52,100; threshold never decreases;
    payouts do not lower it. Breach (EOD balance <= threshold) closes the PA.
  - Daily Loss Limit, tier-based, intraday: day PnL clipped at -DLL
    (positions liquidated, account survives). 50K tiers by profit
    (balance - 50k): <$1.5k -> $1,000; <$3k -> $1,000; <$6k -> $2,000;
    else $3,000.
  - Payout request (Fridays): needs balance >= $52,600, >= 5 qualifying days
    (day net >= +$250) since last payout, and 50% consistency (best profitable
    day < 50% of net profit since last approved payout). Withdrawal amount =
    min(payout-number cap, balance - $52,100), must be >= $500.
    Caps: $1,500 / $1,500 / $2,000 / $2,500 / $2,500 / $3,000.
  - After 6 approved payouts the PA closes (lifetime extraction cap $13,000).
  - Account cost $300 (per user's churn framing; eval ignored).

Not modeled (noted as caveats): intraday unrealized-PnL enforcement of the
threshold, tier-based contract caps (order rejection), inactivity rule.
"""
from __future__ import annotations

import csv
import random
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_alpha_v1_phase_two_portfolio_20260722 import (  # noqa: E402
    BASELINE, SINGLES, CALENDAR, COMMON_START, COMMON_END, RECENT_START,
    OUT_DIR, daily_pnl,
)

ACCOUNT_COST = 300.0
START_BAL = 50_000.0
TRAIL = 2_000.0
HWM_LOCK = 52_100.0          # highest EOD balance where threshold stops trailing
SAFETY_NET = 52_100.0        # balance that must remain after payout
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


def run_pa(days, start_idx: int = 0):
    """Simulate one Apex 50K EOD PA. Returns dict with outcome."""
    bal = START_BAL
    hwm_eod = START_BAL
    qual = 0
    best_day = 0.0
    net_since_payout = 0.0
    payouts: list[float] = []
    first_wd_day = None
    for i in range(start_idx, len(days)):
        t = i - start_idx
        profit = bal - START_BAL
        raw = days[i]
        v = max(raw, -dll_for_profit(profit))  # DLL truncation
        bal += v
        hwm_eod = max(hwm_eod, bal)
        threshold = min(hwm_eod, HWM_LOCK) - TRAIL
        if bal <= threshold:
            return {"outcome": "breach", "days": t + 1, "withdrawn": sum(payouts),
                    "n_payouts": len(payouts), "first_wd": first_wd_day}
        if v >= QUAL_USD:
            qual += 1
        if v > 0:
            best_day = max(best_day, v)
        net_since_payout += v
        if t % 5 == 4:  # Friday
            can = (bal >= MIN_BAL_REQUEST and qual >= QUAL_REQ
                   and net_since_payout > 0 and best_day < 0.5 * net_since_payout)
            if can:
                amt = min(PAYOUT_CAPS[len(payouts)], bal - SAFETY_NET)
                if amt >= MIN_PAYOUT:
                    payouts.append(amt)
                    bal -= amt
                    if first_wd_day is None:
                        first_wd_day = t + 1
                    qual = 0
                    best_day = 0.0
                    net_since_payout = 0.0
                    if len(payouts) == 6:
                        return {"outcome": "complete", "days": t + 1,
                                "withdrawn": sum(payouts), "n_payouts": 6,
                                "first_wd": first_wd_day}
    return {"outcome": "censored", "days": len(days) - start_idx,
            "withdrawn": sum(payouts), "n_payouts": len(payouts),
            "first_wd": first_wd_day}


def mc(pool, seed=20260722) -> dict:
    rng = random.Random(seed)
    rows = []
    for _ in range(N_PATHS):
        days = [rng.choice(pool) for _ in range(LIFE_CAP_DAYS)]
        rows.append(run_pa(days))
    W = [r["withdrawn"] for r in rows]
    T = [r["days"] for r in rows]
    comp = [r for r in rows if r["outcome"] == "complete"]
    breach = [r for r in rows if r["outcome"] == "breach"]
    mean_w, mean_t = statistics.mean(W), statistics.mean(T)
    return {
        "complete_pct": round(100 * len(comp) / len(rows), 1),
        "breach_pct": round(100 * len(breach) / len(rows), 1),
        "med_days_complete": statistics.median([r["days"] for r in comp]) if comp else None,
        "med_payouts_at_breach": statistics.median([r["n_payouts"] for r in breach]) if breach else None,
        "mean_withdrawn": round(mean_w, 0),
        "ev_per_account": round(mean_w - ACCOUNT_COST, 0),
        "rate_per_slot_yr": round(252 * (mean_w - ACCOUNT_COST) / mean_t, 0),
        "med_first_wd": statistics.median([r["first_wd"] for r in rows if r["first_wd"]]) if any(r["first_wd"] for r in rows) else None,
        "pct_zero_wd": round(100 * sum(1 for w in W if w == 0) / len(W), 1),
        "mean_life_days": round(mean_t, 0),
    }


def hist(pnl_by_day, calendar) -> dict:
    days = [pnl_by_day.get(d, 0.0) for d in calendar]
    starts, seen = [], set()
    for i, d in enumerate(calendar):
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            if len(calendar) - i >= 120:
                starts.append(i)
    rows = [run_pa(days, s) for s in starts]
    comp = [r for r in rows if r["outcome"] == "complete"]
    breach = [r for r in rows if r["outcome"] == "breach"]
    return {
        "cohorts": len(rows),
        "complete": len(comp),
        "breach": len(breach),
        "med_withdrawn": round(statistics.median([r["withdrawn"] for r in rows]), 0),
        "med_days_complete": statistics.median([r["days"] for r in comp]) if comp else None,
        "med_payouts_at_breach": statistics.median([r["n_payouts"] for r in breach]) if breach else None,
    }


MENUS = {
    "SPLIT5_150": [(BASELINE[s], 150, s) for s in ("NQ_NY_LSI", "NQ_Asia", "ES_Asia", "NQ_NY", "ES_NY")],
    "SPLIT5_200": [(BASELINE[s], 200, s) for s in ("NQ_NY_LSI", "NQ_Asia", "ES_Asia", "NQ_NY", "ES_NY")],
    "SPLIT5_250": [(BASELINE[s], 250, s) for s in ("NQ_NY_LSI", "NQ_Asia", "ES_Asia", "NQ_NY", "ES_NY")],
    "SPRINT_X1": [
        (BASELINE["NQ_NY_LSI"], 500, "LSI"), (BASELINE["NQ_Asia"], 400, "NQ Asia"),
        (BASELINE["ES_Asia"], 150, "ES Asia"), (BASELINE["NQ_NY"], 250, "NQ R11"),
        (BASELINE["ES_NY"], 300, "ES NY"),
    ],
    "SPRINT_X1_5": [
        (BASELINE["NQ_NY_LSI"], 750, "LSI"), (BASELINE["NQ_Asia"], 600, "NQ Asia"),
        (BASELINE["ES_Asia"], 225, "ES Asia"), (BASELINE["NQ_NY"], 375, "NQ R11"),
        (BASELINE["ES_NY"], 450, "ES NY"),
    ],
    "BH3_275": [
        (SINGLES["es_ny_orb_single_1r"], 275, "ES NY 1.0R"),
        (SINGLES["es_asia_orb_single_1p25r"], 275, "ES Asia 1.25R"),
        (SINGLES["nq_ny_orb_r11_single_1p4r"], 275, "NQ R11 1.4R"),
    ],
    "BH3_PLUS_LSI_250": [
        (SINGLES["es_ny_orb_single_1r"], 250, "ES NY 1.0R"),
        (SINGLES["es_asia_orb_single_1p25r"], 250, "ES Asia 1.25R"),
        (SINGLES["nq_ny_orb_r11_single_1p4r"], 250, "NQ R11 1.4R"),
        (BASELINE["NQ_NY_LSI"], 250, "LSI"),
    ],
    "HYBRID_MID": [
        (SINGLES["es_ny_orb_single_1r"], 250, "ES NY 1.0R"),
        (SINGLES["es_asia_orb_single_1p25r"], 250, "ES Asia 1.25R"),
        (SINGLES["nq_ny_orb_r11_single_1p4r"], 250, "NQ R11 1.4R"),
        (BASELINE["NQ_NY_LSI"], 200, "LSI"),
        (BASELINE["NQ_Asia"], 150, "NQ Asia 6R"),
    ],
}


def main() -> None:
    out = []
    for name, menu in MENUS.items():
        pnl = daily_pnl(menu, COMMON_START, COMMON_END)
        pool_full = [pnl.get(d, 0.0) for d in CALENDAR]
        pool_rec = [pnl.get(d, 0.0) for d in RECENT_CAL]
        f = mc(pool_full)
        r = mc(pool_rec, seed=20260723)
        h = hist(pnl, CALENDAR)
        row = {"menu": name}
        row.update({f"full_{k}": v for k, v in f.items()})
        row.update({f"rec_{k}": v for k, v in r.items()})
        row.update({f"hist_{k}": v for k, v in h.items()})
        out.append(row)
        print(f"{name:18s} | comp {f['complete_pct']:5.1f}% breach {f['breach_pct']:5.1f}% | "
              f"EV {f['ev_per_account']:6.0f} $/slot-yr {f['rate_per_slot_yr']:6.0f} | "
              f"6th@{str(f['med_days_complete']):>5s}d 1stWD {str(f['med_first_wd']):>4s}d | "
              f"2025+: comp {r['complete_pct']:5.1f}% EV {r['ev_per_account']:6.0f} "
              f"$/yr {r['rate_per_slot_yr']:6.0f} 6th@{str(r['med_days_complete']):>5s}d | "
              f"hist comp {h['complete']}/{h['cohorts']} medWD {h['med_withdrawn']:.0f} "
              f"6th@{h['med_days_complete']}d")

    with open(OUT_DIR / "apex_lifecycle.csv", "w", newline="") as fh:
        keys = sorted({k for r0 in out for k in r0})
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(out)
    print(f"\nSaved {OUT_DIR / 'apex_lifecycle.csv'}")


if __name__ == "__main__":
    main()
