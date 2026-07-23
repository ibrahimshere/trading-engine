#!/usr/bin/env python3
"""Phase-two risk/structure frontier for ALPHA_V1-A extraction menus.

Sweeps leg-count and flat risk for the structures identified in
run_alpha_v1_phase_two_portfolio_20260722.py, looking for the best
withdrawal cadence subject to breach control on a $2k locked floor.
"""
from __future__ import annotations

import csv
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_alpha_v1_phase_two_portfolio_20260722 import (  # noqa: E402
    BASELINE, SINGLES, CALENDAR, COMMON_START, COMMON_END, RECENT_START,
    OUT_DIR, daily_pnl, day_stats, cohort_sim, bootstrap_sim,
)

RECENT_CAL = [d for d in CALENDAR if d >= RECENT_START]

# structure -> list of (stream, weight, label); risk = flat_risk * weight
STRUCTURES = {
    "SPLIT5": [
        (BASELINE["NQ_NY_LSI"], 1.0, "LSI"),
        (BASELINE["NQ_Asia"], 1.0, "NQ Asia"),
        (BASELINE["ES_Asia"], 1.0, "ES Asia"),
        (BASELINE["NQ_NY"], 1.0, "NQ R11"),
        (BASELINE["ES_NY"], 1.0, "ES NY"),
    ],
    "BH2_ESNY_ESASIA": [
        (SINGLES["es_ny_orb_single_1r"], 1.0, "ES NY 1.0R"),
        (SINGLES["es_asia_orb_single_1p25r"], 1.0, "ES Asia 1.25R"),
    ],
    "BH2_ESASIA_R11": [
        (SINGLES["es_asia_orb_single_1p25r"], 1.0, "ES Asia 1.25R"),
        (SINGLES["nq_ny_orb_r11_single_1p4r"], 1.0, "NQ R11 1.4R"),
    ],
    "BH3": [
        (SINGLES["es_ny_orb_single_1r"], 1.0, "ES NY 1.0R"),
        (SINGLES["es_asia_orb_single_1p25r"], 1.0, "ES Asia 1.25R"),
        (SINGLES["nq_ny_orb_r11_single_1p4r"], 1.0, "NQ R11 1.4R"),
    ],
    "BH2_PLUS_LSI": [
        (SINGLES["es_ny_orb_single_1r"], 1.0, "ES NY 1.0R"),
        (SINGLES["es_asia_orb_single_1p25r"], 1.0, "ES Asia 1.25R"),
        (BASELINE["NQ_NY_LSI"], 0.6, "LSI @0.6x"),
    ],
    "SPLIT5_ESASIA_SINGLE": [
        (BASELINE["NQ_NY_LSI"], 1.0, "LSI"),
        (BASELINE["NQ_Asia"], 1.0, "NQ Asia"),
        (SINGLES["es_asia_orb_single_1p25r"], 1.3, "ES Asia single @1.3x"),
        (BASELINE["NQ_NY"], 1.0, "NQ R11"),
        (BASELINE["ES_NY"], 1.0, "ES NY"),
    ],
}

RISKS = {
    "SPLIT5": [125, 150, 175, 200],
    "BH2_ESNY_ESASIA": [250, 275, 300, 325, 350],
    "BH2_ESASIA_R11": [250, 275, 300, 325, 350],
    "BH3": [250, 275, 300],
    "BH2_PLUS_LSI": [250, 275, 300, 325],
    "SPLIT5_ESASIA_SINGLE": [125, 150, 175, 200],
}


def main() -> None:
    rows = []
    for sname, legs in STRUCTURES.items():
        for base_risk in RISKS[sname]:
            menu = [(stream, base_risk * w, label) for stream, w, label in legs]
            pnl = daily_pnl(menu, COMMON_START, COMMON_END)
            full = day_stats(pnl, CALENDAR)
            rec = day_stats(pnl, RECENT_CAL)
            coh = cohort_sim(pnl, CALENDAR)
            cohr = cohort_sim(pnl, RECENT_CAL, min_days=120)
            mc = bootstrap_sim(pnl, CALENDAR)
            mcr = bootstrap_sim(pnl, RECENT_CAL)
            row = {
                "structure": sname, "risk": base_risk,
                "qual_mo": full["qual_days_per_month"], "day_wr": full["day_wr_pct"],
                "worst_day": full["worst_day"], "worst_mo": full["worst_month"],
                "coh_breach": coh["breach_pct"], "ann_wd": coh["ann_withdrawn_med"],
                "first_wd": coh["median_first_wd_day"], "wd_gap": coh["median_wd_gap_days"],
                "giveback": coh["median_max_giveback"],
                "mc_breach": mc["mc_breach_pct_1y"], "mc_wd": mc["mc_withdrawn_med"],
                "mc_wd_p10": mc["mc_withdrawn_p10"],
                "r_coh_breach": cohr["breach_pct"], "r_ann_wd": cohr["ann_withdrawn_med"],
                "r_first_wd": cohr["median_first_wd_day"],
                "r_mc_breach": mcr["mc_breach_pct_1y"],
                "r_qual_mo": rec["qual_days_per_month"],
            }
            rows.append(row)
            print(f"{sname:22s} ${base_risk:3d} | qual/mo {row['qual_mo']:5.2f} | "
                  f"worst_day {row['worst_day']:7.0f} | coh_breach {row['coh_breach']:5.1f}% | "
                  f"annWD {row['ann_wd']:7.0f} | firstWD {str(row['first_wd']):>5s}d | "
                  f"gap {str(row['wd_gap']):>5s}d | MC1y breach {row['mc_breach']:4.1f}% "
                  f"WD {row['mc_wd']:7.0f} | 2025+: breach {row['r_coh_breach']:5.1f}%/"
                  f"mc {row['r_mc_breach']:4.1f}% annWD {row['r_ann_wd']:7.0f} "
                  f"firstWD {str(row['r_first_wd']):>5s}d qual/mo {row['r_qual_mo']:.2f}")

    with open(OUT_DIR / "risk_frontier.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nSaved {OUT_DIR / 'risk_frontier.csv'}")


if __name__ == "__main__":
    main()
