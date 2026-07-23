#!/usr/bin/env python3
"""Funded-account churn ROI for ALPHA_V1-A menus (accounts as leverage, not sacred).

Model: each funded account costs $300 (eval ignored). Fresh account: balance
$50,000, trailing EOD floor = max(HWM) - $2,000, locking at $50,000 once HWM
reaches $52,000. Friday withdrawal down to the reset level when balance >=
trigger AND >=5 qualifying days (day PnL >= +$250) since last withdrawal
(consistency rule also gates the first payout). Account runs until breach.

Objective: renewal-reward extraction rate per account slot
    rate_$_per_year = 252 * (E[withdrawn] - 300) / E[lifetime_days]
plus EV per account and time-to-first-withdrawal.

Sources: cached exact streams loaded via run_alpha_v1_phase_two_portfolio_20260722.
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
TRAIL_DD = 2_000.0
FLOOR_LOCK = 50_000.0
QUAL_USD = 250.0
QUAL_REQ = 5
LIFE_CAP_DAYS = 2520
N_PATHS = 3000

RECENT_CAL = [d for d in CALENDAR if d >= RECENT_START]

MENUS = {
    "SPLIT5_150": [(BASELINE[s], 150, s) for s in ("NQ_NY_LSI", "NQ_Asia", "ES_Asia", "NQ_NY", "ES_NY")],
    "SPLIT5_200": [(BASELINE[s], 200, s) for s in ("NQ_NY_LSI", "NQ_Asia", "ES_Asia", "NQ_NY", "ES_NY")],
    "SPLIT5_250": [(BASELINE[s], 250, s) for s in ("NQ_NY_LSI", "NQ_Asia", "ES_Asia", "NQ_NY", "ES_NY")],
    "SPLIT5_300": [(BASELINE[s], 300, s) for s in ("NQ_NY_LSI", "NQ_Asia", "ES_Asia", "NQ_NY", "ES_NY")],
    "SPRINT_MENU": [  # live aggressive sprint per-leg sizing on current legs
        (BASELINE["NQ_NY_LSI"], 500, "LSI"),
        (BASELINE["NQ_Asia"], 400, "NQ Asia"),
        (BASELINE["ES_Asia"], 150, "ES Asia"),
        (BASELINE["NQ_NY"], 250, "NQ R11"),
        (BASELINE["ES_NY"], 300, "ES NY"),
    ],
    "BH3_275": [
        (SINGLES["es_ny_orb_single_1r"], 275, "ES NY 1.0R"),
        (SINGLES["es_asia_orb_single_1p25r"], 275, "ES Asia 1.25R"),
        (SINGLES["nq_ny_orb_r11_single_1p4r"], 275, "NQ R11 1.4R"),
    ],
    "BH3_350": [
        (SINGLES["es_ny_orb_single_1r"], 350, "ES NY 1.0R"),
        (SINGLES["es_asia_orb_single_1p25r"], 350, "ES Asia 1.25R"),
        (SINGLES["nq_ny_orb_r11_single_1p4r"], 350, "NQ R11 1.4R"),
    ],
    "BH2_ESA_R11_325": [
        (SINGLES["es_asia_orb_single_1p25r"], 325, "ES Asia 1.25R"),
        (SINGLES["nq_ny_orb_r11_single_1p4r"], 325, "NQ R11 1.4R"),
    ],
    "HYBRID_275": [
        (SINGLES["es_ny_orb_single_1r"], 300, "ES NY 1.0R"),
        (SINGLES["es_asia_orb_single_1p25r"], 275, "ES Asia 1.25R"),
        (SINGLES["nq_ny_orb_r11_single_1p4r"], 275, "NQ R11 1.4R"),
        (BASELINE["NQ_NY_LSI"], 200, "LSI"),
        (BASELINE["NQ_Asia"], 100, "NQ Asia 0.5x"),
    ],
    "SPRINT_MENU_1_5X": [
        (BASELINE["NQ_NY_LSI"], 750, "LSI"),
        (BASELINE["NQ_Asia"], 600, "NQ Asia"),
        (BASELINE["ES_Asia"], 225, "ES Asia"),
        (BASELINE["NQ_NY"], 375, "NQ R11"),
        (BASELINE["ES_NY"], 450, "ES NY"),
    ],
}

POLICIES = [("wd_max", 52_500.0, 52_000.0), ("wd_buffer", 53_000.0, 52_500.0)]


def run_account(days: list[float], trigger: float, reset: float,
                start_idx: int = 0) -> tuple[float, int, int | None, bool]:
    """Return (withdrawn, lifetime_days, first_wd_day, breached). days is a
    daily PnL sequence; account ends at breach or sequence end."""
    bal, hwm = START_BAL, START_BAL
    qual, withdrawn = 0, 0.0
    first_wd = None
    for i in range(start_idx, len(days)):
        v = days[i]
        bal += v
        hwm = max(hwm, bal)
        floor = min(hwm, FLOOR_LOCK + TRAIL_DD) - TRAIL_DD
        if bal <= floor:
            return withdrawn, i - start_idx + 1, first_wd, True
        if v >= QUAL_USD:
            qual += 1
        if (i - start_idx) % 5 == 4 and bal >= trigger and qual >= QUAL_REQ:
            amt = bal - reset
            withdrawn += amt
            bal = reset
            qual = 0
            if first_wd is None:
                first_wd = i - start_idx + 1
    return withdrawn, len(days) - start_idx, first_wd, False


def mc_lifecycle(pool: list[float], trigger: float, reset: float,
                 seed: int = 20260722) -> dict:
    rng = random.Random(seed)
    W, T, F = [], [], []
    breaches = 0
    for _ in range(N_PATHS):
        days = [rng.choice(pool) for _ in range(LIFE_CAP_DAYS)]
        w, t, f, breached = run_account(days, trigger, reset)
        W.append(w)
        T.append(t)
        if f is not None:
            F.append(f)
        if breached:
            breaches += 1
    mean_w = statistics.mean(W)
    mean_t = statistics.mean(T)
    W_sorted = sorted(W)
    q = lambda p: W_sorted[int(p * (len(W_sorted) - 1))]
    return {
        "ev_per_account": round(mean_w - ACCOUNT_COST, 0),
        "rate_per_slot_yr": round(252 * (mean_w - ACCOUNT_COST) / mean_t, 0),
        "mean_withdrawn": round(mean_w, 0),
        "wd_p10": round(q(0.10), 0), "wd_p50": round(q(0.50), 0), "wd_p90": round(q(0.90), 0),
        "pct_paths_net_negative": round(100 * sum(1 for w in W if w < ACCOUNT_COST) / len(W), 1),
        "median_life_days": statistics.median(T),
        "mean_life_days": round(mean_t, 0),
        "median_first_wd": statistics.median(F) if F else None,
        "pct_no_wd": round(100 * (N_PATHS - len(F)) / N_PATHS, 1),
        "breach_pct_at_cap": round(100 * breaches / N_PATHS, 1),
        "accounts_per_year": round(252 / mean_t, 2),
    }


def hist_cohorts(pnl_by_day: dict, calendar: list) -> dict:
    days = [pnl_by_day.get(d, 0.0) for d in calendar]
    starts, seen = [], set()
    for i, d in enumerate(calendar):
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            if len(calendar) - i >= 120:
                starts.append(i)
    rows = [run_account(days, 52_500.0, 52_000.0, s) for s in starts]
    resolved = [r for r in rows if r[3]]
    W = [r[0] for r in rows]
    F = [r[2] for r in rows if r[2] is not None]
    return {
        "cohorts": len(rows),
        "resolved_breaches": len(resolved),
        "median_withdrawn_all": round(statistics.median(W), 0),
        "mean_withdrawn_resolved": round(statistics.mean([r[0] for r in resolved]), 0) if resolved else None,
        "median_life_resolved": statistics.median([r[1] for r in resolved]) if resolved else None,
        "median_first_wd": statistics.median(F) if F else None,
        "pct_cohorts_no_wd": round(100 * (len(rows) - len(F)) / len(rows), 1),
    }


def main() -> None:
    out_rows = []
    for name, menu in MENUS.items():
        pnl = daily_pnl(menu, COMMON_START, COMMON_END)
        pool_full = [pnl.get(d, 0.0) for d in CALENDAR]
        pool_recent = [pnl.get(d, 0.0) for d in RECENT_CAL]
        hist = hist_cohorts(pnl, CALENDAR)
        for plabel, trig, reset in POLICIES:
            full = mc_lifecycle(pool_full, trig, reset)
            recent = mc_lifecycle(pool_recent, trig, reset, seed=20260723)
            row = {"menu": name, "policy": plabel}
            row.update({f"full_{k}": v for k, v in full.items()})
            row.update({f"r_{k}": v for k, v in recent.items()})
            if plabel == "wd_max":
                row.update({f"hist_{k}": v for k, v in hist.items()})
            out_rows.append(row)
            print(f"{name:18s} {plabel:9s} | EV/acct {full['ev_per_account']:8.0f} | "
                  f"$/slot-yr {full['rate_per_slot_yr']:8.0f} | life {full['median_life_days']:5.0f}d | "
                  f"1stWD {str(full['median_first_wd']):>5s}d | acct/yr {full['accounts_per_year']:4.2f} | "
                  f"netNeg {full['pct_paths_net_negative']:4.1f}% | "
                  f"2025+: EV {recent['ev_per_account']:8.0f} $/yr {recent['rate_per_slot_yr']:8.0f} "
                  f"1stWD {str(recent['median_first_wd']):>5s}d netNeg {recent['pct_paths_net_negative']:4.1f}%")
        h = hist
        print(f"{'':18s} hist      | cohorts {h['cohorts']} breached {h['resolved_breaches']} "
              f"medWD_all {h['median_withdrawn_all']} meanWD_resolved {h['mean_withdrawn_resolved']} "
              f"medLife {h['median_life_resolved']} 1stWD {h['median_first_wd']} noWD {h['pct_cohorts_no_wd']}%")

    with open(OUT_DIR / "churn_roi.csv", "w", newline="") as fh:
        keys = sorted({k for r in out_rows for k in r})
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(out_rows)
    print(f"\nSaved {OUT_DIR / 'churn_roi.csv'}")


if __name__ == "__main__":
    main()
