#!/usr/bin/env python3
"""Phase-two (post-first-payout) portfolio construction for ALPHA_V1-A.

Builds candidate extraction menus from cached exact trade streams and simulates
a monetized funded account under day-level consistency rules:
  - locked floor $50,000 after first payout, balance restarts at $52,000
  - Friday withdrawal down to $52,000 when balance >= $52,500 AND at least
    5 qualifying days (day PnL >= +$250) since the last withdrawal
  - EOD breach when balance <= $50,000

Sources (no engine run; cached exact replays only):
  - alpha_v1_ath_fragility_20260608/baseline_trades_ath_annotated.csv
      current five-leg ALPHA_V1-A split ladders, fee-aware, 2021-06 .. 2026-06
  - alpha_v1_single_target_exact_prop_20260506/exact_trades.csv
      exact single-target variants (ES_NY 1.0R, ES_Asia 1.25R, NQ R11 1.4R),
      2016-04 .. 2026-03; a flat 0.02R/trade fee proxy is subtracted because
      this replay predates the MNQ/MES fee model.

Menus are compared on a common window (2021-06-07 .. 2026-03-19) with a
2025-01-01+ recent split, monthly-start cohort simulation, and an iid daily
bootstrap for path risk.
"""
from __future__ import annotations

import csv
import json
import random
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "results"
OUT_DIR = RESULTS / "alpha_v1_phase_two_portfolio_20260722"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_CSV = RESULTS / "alpha_v1_ath_fragility_20260608" / "baseline_trades_ath_annotated.csv"
SINGLE_CSV = RESULTS / "alpha_v1_single_target_exact_prop_20260506" / "exact_trades.csv"

COMMON_START = date(2021, 6, 7)
COMMON_END = date(2026, 3, 19)
RECENT_START = date(2025, 1, 1)

START_BAL = 52_000.0
FLOOR = 50_000.0
WD_TRIGGER = 52_500.0
WD_RESET = 52_000.0
QUAL_DAY_USD = 250.0
QUAL_DAYS_REQUIRED = 5
SINGLE_FEE_R = 0.02  # fee proxy per trade for the pre-fee single-target replay


def parse_day(ts: str) -> date:
    return datetime.fromisoformat(ts[:19].replace(" ", "T")).date()


def load_baseline() -> dict[str, list[tuple[date, float]]]:
    """session -> [(accounting_day, fee-aware R at configured risk)]"""
    legs: dict[str, list[tuple[date, float]]] = defaultdict(list)
    with open(BASE_CSV) as fh:
        for row in csv.DictReader(fh):
            day = parse_day(row["exit_local"] or row["exit_time"])
            legs[row["session"]].append((day, float(row["configured_net_r"])))
    return legs


def load_singles() -> dict[str, list[tuple[date, float]]]:
    legs: dict[str, list[tuple[date, float]]] = defaultdict(list)
    with open(SINGLE_CSV) as fh:
        for row in csv.DictReader(fh):
            day = parse_day(row["exit_ts"])
            legs[row["candidate"]].append((day, float(row["r_multiple"]) - SINGLE_FEE_R))
    return legs


BASELINE = load_baseline()
SINGLES = load_singles()

# menu: name -> list of (stream, risk_usd)
MENUS: dict[str, list[tuple[list[tuple[date, float]], float, str]]] = {
    "M0_current_split_200": [
        (BASELINE["NQ_NY_LSI"], 200, "LSI split"),
        (BASELINE["NQ_Asia"], 200, "NQ Asia split rr6"),
        (BASELINE["ES_Asia"], 200, "ES Asia split rr1.5"),
        (BASELINE["NQ_NY"], 200, "NQ R11 split"),
        (BASELINE["ES_NY"], 200, "ES NY split rr5"),
    ],
    "M4_current_split_150": [
        (BASELINE["NQ_NY_LSI"], 150, "LSI split"),
        (BASELINE["NQ_Asia"], 150, "NQ Asia split rr6"),
        (BASELINE["ES_Asia"], 150, "ES Asia split rr1.5"),
        (BASELINE["NQ_NY"], 150, "NQ R11 split"),
        (BASELINE["ES_NY"], 150, "ES NY split rr5"),
    ],
    "M1_base_hits": [
        (SINGLES["es_ny_orb_single_1r"], 300, "ES NY single 1.0R"),
        (SINGLES["es_asia_orb_single_1p25r"], 275, "ES Asia single 1.25R"),
        (SINGLES["nq_ny_orb_r11_single_1p4r"], 275, "NQ R11 single 1.4R"),
        (BASELINE["NQ_NY_LSI"], 200, "LSI split"),
    ],
    "M2_singles_only": [
        (SINGLES["es_ny_orb_single_1r"], 300, "ES NY single 1.0R"),
        (SINGLES["es_asia_orb_single_1p25r"], 275, "ES Asia single 1.25R"),
        (SINGLES["nq_ny_orb_r11_single_1p4r"], 275, "NQ R11 single 1.4R"),
    ],
    "M3_hybrid_kicker": [
        (SINGLES["es_ny_orb_single_1r"], 300, "ES NY single 1.0R"),
        (SINGLES["es_asia_orb_single_1p25r"], 275, "ES Asia single 1.25R"),
        (SINGLES["nq_ny_orb_r11_single_1p4r"], 275, "NQ R11 single 1.4R"),
        (BASELINE["NQ_NY_LSI"], 200, "LSI split"),
        (BASELINE["NQ_Asia"], 100, "NQ Asia split rr6 @0.5x"),
    ],
    "M5_base_hits_low": [
        (SINGLES["es_ny_orb_single_1r"], 200, "ES NY single 1.0R"),
        (SINGLES["es_asia_orb_single_1p25r"], 200, "ES Asia single 1.25R"),
        (SINGLES["nq_ny_orb_r11_single_1p4r"], 200, "NQ R11 single 1.4R"),
        (BASELINE["NQ_NY_LSI"], 150, "LSI split"),
    ],
}


def business_days(start: date, end: date) -> list[date]:
    days, d = [], start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


CALENDAR = business_days(COMMON_START, COMMON_END)


def daily_pnl(menu: list, start: date, end: date) -> dict[date, float]:
    pnl: dict[date, float] = defaultdict(float)
    for stream, risk, _label in menu:
        for day, r in stream:
            if start <= day <= end:
                pnl[day] += r * risk
    return pnl


def day_stats(pnl: dict[date, float], calendar: list[date]) -> dict:
    vals = [pnl.get(d, 0.0) for d in calendar]
    traded = [v for v in vals if v != 0.0]
    months: dict[str, float] = defaultdict(float)
    for d in calendar:
        months[d.strftime("%Y-%m")] += pnl.get(d, 0.0)
    worst_streak = streak = 0
    for v in vals:
        streak = streak + 1 if v < 0 else 0
        worst_streak = max(worst_streak, streak)
    qual = sum(1 for v in vals if v >= QUAL_DAY_USD)
    n_months = max(len(months), 1)
    return {
        "trade_days": len(traded),
        "day_wr_pct": round(100 * sum(1 for v in traded if v > 0) / max(len(traded), 1), 1),
        "qual_days_per_month": round(qual / n_months, 2),
        "pct_days_qual": round(100 * qual / len(vals), 1),
        "pct_days_big_loss": round(100 * sum(1 for v in vals if v <= -QUAL_DAY_USD) / len(vals), 1),
        "worst_day": round(min(vals), 0),
        "best_day": round(max(vals), 0),
        "avg_month": round(statistics.mean(months.values()), 0),
        "worst_month": round(min(months.values()), 0),
        "neg_months": sum(1 for v in months.values() if v < 0),
        "n_months": len(months),
        "max_consec_down_days": worst_streak,
        "total_pnl": round(sum(vals), 0),
    }


def simulate_account(pnl: dict[date, float], calendar: list[date]) -> dict:
    bal, qual, withdrawn, wds = START_BAL, 0, 0.0, []
    last_wd_idx = 0
    breach_day = None
    ready_days = 0
    peak, max_giveback = START_BAL, 0.0
    for i, d in enumerate(calendar):
        bal += pnl.get(d, 0.0)
        peak = max(peak, bal)
        max_giveback = max(max_giveback, peak - bal)
        if bal <= FLOOR:
            breach_day = i
            break
        if pnl.get(d, 0.0) >= QUAL_DAY_USD:
            qual += 1
        if bal >= WD_TRIGGER:
            ready_days += 1
        is_friday = d.weekday() == 4
        if is_friday and bal >= WD_TRIGGER and qual >= QUAL_DAYS_REQUIRED:
            amt = bal - WD_RESET
            withdrawn += amt
            wds.append((i, amt))
            bal = WD_RESET
            qual = 0
            peak = bal
            last_wd_idx = i
    n = breach_day if breach_day is not None else len(calendar)
    gaps = [j - i for (i, _), (j, _) in zip(wds, wds[1:])]
    first_gap = wds[0][0] if wds else None
    return {
        "breached": breach_day is not None,
        "breach_day": breach_day,
        "days_run": n,
        "n_withdrawals": len(wds),
        "withdrawn": round(withdrawn, 0),
        "withdrawn_per_year": round(withdrawn / max(n / 252, 1e-9), 0) if n else 0.0,
        "first_wd_day": first_gap,
        "median_wd_gap": statistics.median(gaps) if gaps else None,
        "max_wd_gap": max(gaps) if gaps else None,
        "pct_days_ready": round(100 * ready_days / max(n, 1), 1),
        "max_giveback": round(max_giveback, 0),
    }


def cohort_sim(pnl: dict[date, float], calendar: list[date], min_days: int = 189) -> dict:
    """Start a phase-2 account at each month boundary; run to window end."""
    starts = []
    seen = set()
    for i, d in enumerate(calendar):
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            if len(calendar) - i >= min_days:
                starts.append(i)
    rows = [simulate_account(pnl, calendar[s:]) for s in starts]
    breach = [r for r in rows if r["breached"]]
    ann = [r["withdrawn_per_year"] for r in rows]
    first = [r["first_wd_day"] for r in rows if r["first_wd_day"] is not None]
    gaps = [r["median_wd_gap"] for r in rows if r["median_wd_gap"] is not None]
    return {
        "cohorts": len(rows),
        "breach_pct": round(100 * len(breach) / max(len(rows), 1), 1),
        "median_breach_day": statistics.median([r["breach_day"] for r in breach]) if breach else None,
        "ann_withdrawn_p25": round(statistics.quantiles(ann, n=4)[0], 0) if len(ann) >= 4 else None,
        "ann_withdrawn_med": round(statistics.median(ann), 0),
        "ann_withdrawn_p75": round(statistics.quantiles(ann, n=4)[2], 0) if len(ann) >= 4 else None,
        "median_first_wd_day": statistics.median(first) if first else None,
        "median_wd_gap_days": statistics.median(gaps) if gaps else None,
        "median_pct_days_ready": statistics.median([r["pct_days_ready"] for r in rows]),
        "median_max_giveback": statistics.median([r["max_giveback"] for r in rows]),
    }


def bootstrap_sim(pnl: dict[date, float], calendar: list[date], n_paths: int = 2000,
                  horizon: int = 252, seed: int = 20260722) -> dict:
    rng = random.Random(seed)
    pool = [pnl.get(d, 0.0) for d in calendar]
    breaches = 0
    withdrawn_paths, max_gaps = [], []
    for _ in range(n_paths):
        bal, qual, withdrawn = START_BAL, 0, 0.0
        day_since_wd, worst_gap, breached = 0, 0, False
        for i in range(horizon):
            v = rng.choice(pool)
            bal += v
            if bal <= FLOOR:
                breached = True
                break
            if v >= QUAL_DAY_USD:
                qual += 1
            day_since_wd += 1
            if i % 5 == 4 and bal >= WD_TRIGGER and qual >= QUAL_DAYS_REQUIRED:
                withdrawn += bal - WD_RESET
                bal = WD_RESET
                qual = 0
                worst_gap = max(worst_gap, day_since_wd)
                day_since_wd = 0
        worst_gap = max(worst_gap, day_since_wd)
        if breached:
            breaches += 1
        else:
            withdrawn_paths.append(withdrawn)
            max_gaps.append(worst_gap)
    withdrawn_paths.sort()
    q = lambda arr, p: arr[int(p * (len(arr) - 1))] if arr else None
    return {
        "mc_breach_pct_1y": round(100 * breaches / n_paths, 1),
        "mc_withdrawn_p10": round(q(withdrawn_paths, 0.10), 0) if withdrawn_paths else None,
        "mc_withdrawn_med": round(q(withdrawn_paths, 0.50), 0) if withdrawn_paths else None,
        "mc_withdrawn_p90": round(q(withdrawn_paths, 0.90), 0) if withdrawn_paths else None,
        "mc_median_max_wd_gap": statistics.median(max_gaps) if max_gaps else None,
    }


def main() -> None:
    summary: dict[str, dict] = {}
    recent_cal = [d for d in CALENDAR if d >= RECENT_START]
    for name, menu in MENUS.items():
        pnl = daily_pnl(menu, COMMON_START, COMMON_END)
        entry = {
            "legs": [(label, risk) for _s, risk, label in menu],
            "full": day_stats(pnl, CALENDAR),
            "recent_2025p": day_stats(pnl, recent_cal),
            "cohorts_full": cohort_sim(pnl, CALENDAR),
            "cohorts_2025p": cohort_sim(pnl, recent_cal, min_days=120),
            "mc_1y": bootstrap_sim(pnl, CALENDAR),
            "mc_1y_recent": bootstrap_sim(pnl, recent_cal),
        }
        summary[name] = entry

    with open(OUT_DIR / "summary.json", "w") as fh:
        json.dump(summary, fh, indent=1, default=str)

    with open(OUT_DIR / "menu_compare.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["menu", "day_wr", "pct_days_qual", "qual_days_per_mo", "worst_day",
                    "worst_month", "neg_months", "max_consec_down", "total_pnl",
                    "cohort_breach_pct", "ann_withdrawn_med", "median_first_wd_day",
                    "median_wd_gap", "pct_days_ready", "median_max_giveback",
                    "mc_breach_1y", "mc_wd_med", "mc_wd_p10", "recent_mc_breach",
                    "recent_ann_wd_med"])
        for name, e in summary.items():
            w.writerow([name, e["full"]["day_wr_pct"], e["full"]["pct_days_qual"],
                        e["full"]["qual_days_per_month"], e["full"]["worst_day"],
                        e["full"]["worst_month"], e["full"]["neg_months"],
                        e["full"]["max_consec_down_days"], e["full"]["total_pnl"],
                        e["cohorts_full"]["breach_pct"], e["cohorts_full"]["ann_withdrawn_med"],
                        e["cohorts_full"]["median_first_wd_day"], e["cohorts_full"]["median_wd_gap_days"],
                        e["cohorts_full"]["median_pct_days_ready"], e["cohorts_full"]["median_max_giveback"],
                        e["mc_1y"]["mc_breach_pct_1y"], e["mc_1y"]["mc_withdrawn_med"],
                        e["mc_1y"]["mc_withdrawn_p10"], e["mc_1y_recent"]["mc_breach_pct_1y"],
                        e["cohorts_2025p"]["ann_withdrawn_med"]])

    for name, e in summary.items():
        print(f"\n=== {name} ===")
        print("  legs:", ", ".join(f"{l} ${r:.0f}" for l, r in e["legs"]))
        for k in ("full", "recent_2025p"):
            s = e[k]
            print(f"  [{k}] dayWR {s['day_wr_pct']}%  qual/mo {s['qual_days_per_month']}"
                  f"  worst_day {s['worst_day']}  worst_mo {s['worst_month']}"
                  f"  negMo {s['neg_months']}/{s['n_months']}  consecDown {s['max_consec_down_days']}"
                  f"  totPnL {s['total_pnl']}")
        c = e["cohorts_full"]
        print(f"  [cohorts] breach {c['breach_pct']}%  annWD med {c['ann_withdrawn_med']}"
              f"  firstWD {c['median_first_wd_day']}d  gap {c['median_wd_gap_days']}d"
              f"  ready {c['median_pct_days_ready']}%  giveback {c['median_max_giveback']}")
        cr = e["cohorts_2025p"]
        print(f"  [cohorts 2025+] breach {cr['breach_pct']}%  annWD med {cr['ann_withdrawn_med']}"
              f"  firstWD {cr['median_first_wd_day']}d")
        m = e["mc_1y"]
        print(f"  [MC 1y full] breach {m['mc_breach_pct_1y']}%  WD med {m['mc_withdrawn_med']}"
              f"  p10 {m['mc_withdrawn_p10']}  maxGap {m['mc_median_max_wd_gap']}d")
        mr = e["mc_1y_recent"]
        print(f"  [MC 1y 2025+] breach {mr['mc_breach_pct_1y']}%  WD med {mr['mc_withdrawn_med']}"
              f"  p10 {mr['mc_withdrawn_p10']}")
    print(f"\nArtifacts: {OUT_DIR}")


if __name__ == "__main__":
    main()
