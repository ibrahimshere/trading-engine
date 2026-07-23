#!/usr/bin/env python3
"""TRACK 4: causal daily-regime switch for the NQ NY VWAP mean-reversion sleeve.

Goal: find a single, monotone, mechanistically-motivated daily regime feature,
computable causally BEFORE the session opens (prior daily RTH bars only), that
explains why the validated recent-window VWAP mean-reversion sleeve fails on the
2016-01..2021-06 cold window -- so the cold window can be justifiably excluded.

Method discipline (high overfit risk -- we choose a filter using BOTH windows):
- strong preference for ONE feature + ONE round/percentile threshold,
- evaluate: recent-trades retained %, recent R preserved, cold R removed
  (blocked subset must be clearly negative), full-history year split, and the
  switch's on/off time-series behaviour (does it toggle sensibly or memorise
  the split?).

Works from the SAVED validation trade streams (no signal regeneration):
  recent = best_candidate_5m_trades.csv   (370 trades, +127.777R)  [audit parity]
  cold   = cold_window_trades.csv         (441 trades, +7.523R)
Daily features are computed from data/raw/NQ_5m.parquet (US/Eastern), aggregated
to daily RTH bars, and shifted by one session so every feature is known as-of the
PRIOR session close (no intraday lookahead).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(REPO_ROOT / ".agents" / "skills" / "prop-firm-risk-analysis" / "scripts"))

from prop_firm_risk import (  # noqa: E402
    PropFirmRiskProfile,
    make_account_starts,
    profile_to_dict,
    score_prop_firm_outcomes,
    simulate_prop_firm_risk,
)

RUN_SLUG = "nq_ny_vwap_sleeve_regime_switch_20260710"
SRC_SLUG = "nq_ny_vwap_mean_reversion_validation_20260630"
SRC_DIR = ROOT / "data" / "results" / SRC_SLUG
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_VWAP_SLEEVE_REGIME_SWITCH_20260710.md"
RAW_5M = ROOT / "data" / "raw" / "NQ_5m.parquet"

RECENT_START = "2021-06-07"
RECENT_END_EXCLUSIVE = "2026-06-06"
COLD_SPLIT = "2021-06-05"  # cold window is < this date

# Winning switch (chosen below; round, interpretable extreme-trend-extension cap)
SWITCH_FEATURE = "dist_sma200_atr"
SWITCH_THRESHOLD = 12.0  # keep day if prior close <= 12 ATRs above the 200d SMA


# --------------------------------------------------------------------------- #
# Daily causal features
# --------------------------------------------------------------------------- #
def build_daily_features() -> pd.DataFrame:
    """Daily RTH aggregates from 5m (US/Eastern), features shifted to prior close.

    RTH = 09:30..15:55 ET 5m bars (last bar 15:55 covers the 15:55-16:00 close).
    Every returned column is the value known as-of the PRIOR session close.
    """
    df = pd.read_parquet(RAW_5M).between_time("09:30", "15:55")
    df["date"] = df.index.normalize()
    g = df.groupby("date")
    d = pd.DataFrame(
        {
            "open": g["open"].first(),
            "high": g["high"].max(),
            "low": g["low"].min(),
            "close": g["close"].last(),
            "nbars": g["close"].count(),
        }
    )
    d = d[d["nbars"] >= 50]  # keep full RTH sessions only (drop half-days/holidays)

    pc = d["close"].shift(1)
    tr = np.maximum(
        d["high"] - d["low"],
        np.maximum((d["high"] - pc).abs(), (d["low"] - pc).abs()),
    )
    d["tr"] = tr
    d["atr14"] = tr.rolling(14).mean()
    d["atr50"] = tr.rolling(50).mean()
    d["rng"] = d["high"] - d["low"]
    d["sma50"] = d["close"].rolling(50).mean()
    d["sma200"] = d["close"].rolling(200).mean()
    d["hi252"] = d["high"].rolling(252).max()
    d["day_eff"] = (d["close"] - d["open"]).abs() / d["rng"].replace(0, np.nan)

    f = pd.DataFrame(index=d.index)
    # (1) volatility LEVEL
    f["atr_scaled"] = d["atr14"] / d["close"]                       # ATR/price
    f["atr_pctile"] = d["atr14"].rolling(252).apply(lambda x: (x[-1] > x).mean(), raw=True)
    # (2) volatility TREND
    f["atr_trend"] = d["atr14"] / d["atr50"]
    # (3) TREND regime
    f["dist_sma200_atr"] = (d["close"] - d["sma200"]) / d["atr14"]  # signed extension
    f["abs_dist_sma200_atr"] = f["dist_sma200_atr"].abs()
    f["sma50_slope_atr"] = (d["sma50"] - d["sma50"].shift(10)) / d["atr14"]  # 10d slope in ATRs
    # (4) ATH proximity
    f["ath_prox"] = d["close"] / d["hi252"]                         # 1.0 == at 252d high
    # (5) prior-day character
    f["prior_range_atr"] = d["rng"] / d["atr14"]
    f["prior_day_eff"] = d["day_eff"]

    f = f.shift(1)  # <-- causal: value as-of prior session close, known before open
    f.index = f.index.strftime("%Y-%m-%d")
    return f


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def pf(r: np.ndarray) -> float:
    r = np.asarray(r, float)
    up, dn = r[r > 0].sum(), -r[r < 0].sum()
    return float(up / dn) if dn > 0 else float("inf")


def max_dd(r: np.ndarray) -> float:
    eq = np.cumsum(np.asarray(r, float))
    return float((eq - np.maximum.accumulate(eq)).min()) if len(eq) else 0.0


def tstat(r: np.ndarray) -> float:
    r = np.asarray(r, float)
    return float(r.mean() / r.std(ddof=1) * np.sqrt(len(r))) if len(r) > 1 else float("nan")


def keep_mask(series: pd.Series, thr: float, mode: str) -> pd.Series:
    """NaN (feature not yet computable, e.g. SMA200 warmup) -> keep (trade)."""
    if mode == "le":
        m = series <= thr
    else:
        m = series >= thr
    return m | series.isna()


FEATURES = {
    "atr_scaled": ("ge", "vol level: ATR14/price floor"),
    "atr_pctile": ("ge", "vol level: ATR14 percentile (252d) floor"),
    "atr_trend": ("le", "vol trend: ATR14/ATR50 cap"),
    "dist_sma200_atr": ("le", "trend: signed (close-SMA200)/ATR14 cap"),
    "abs_dist_sma200_atr": ("le", "trend: |close-SMA200|/ATR14 cap"),
    "sma50_slope_atr": ("le", "trend: 10d SMA50 slope in ATRs cap"),
    "ath_prox": ("le", "ATH proximity: close/252d-high cap"),
    "prior_range_atr": ("ge", "prior-day range/ATR14 floor"),
    "prior_day_eff": ("le", "prior-day |c-o|/range cap"),
}


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    feat = build_daily_features()
    feat.to_csv(RESULT_DIR / "daily_features.csv")

    rec = pd.read_csv(SRC_DIR / "best_candidate_5m_trades.csv").join(feat, on="date")
    cold = pd.read_csv(SRC_DIR / "cold_window_trades.csv").join(feat, on="date")
    exitref = pd.read_csv(SRC_DIR / "best_exit_refined_5m_trades.csv").join(feat, on="date")
    rec["year"] = rec["date"].str.slice(0, 4)
    cold["year"] = cold["date"].str.slice(0, 4)
    allt = pd.concat([cold, rec], ignore_index=True)

    # audit parity
    assert len(rec) == 370 and abs(rec["r_multiple"].sum() - 127.777) < 0.05, "recent parity failed"
    assert len(cold) == 441, "cold parity failed"

    lines: list[str] = []
    W = lines.append

    W("# NQ NY VWAP Mean-Reversion Sleeve -- Causal Regime Switch (TRACK 4)")
    W("")
    W(f"- Run slug: `{RUN_SLUG}`")
    W(f"- Source streams: `{SRC_SLUG}` (recent `best_candidate_5m_trades.csv` = 370 trades / +127.777R; "
      "cold `cold_window_trades.csv` = 441 trades / +7.523R)")
    W("- Scope: find ONE causal daily-regime feature + threshold that justifies excluding the "
      "2016-01..2021-06 cold window, retaining >=~75-80% of recent trades with recent total R preserved.")
    W("- Deployability: `research_only`.")
    W("")
    W("## Feature Definitions (all as-of prior session close, no intraday lookahead)")
    W("")
    W("Daily RTH bars = 09:30-15:55 ET 5m bars aggregated per session (full sessions, >=50 bars). "
      "`TR` = true range on daily bars; `ATR14/ATR50` = simple rolling means of TR. Every feature "
      "below is computed on the daily series through session *t* and then **shifted one session**, so "
      "the value used for a trade on day *t+1* is known at day *t*'s close (before the open).")
    W("")
    W("| feature | definition | rule |")
    W("|---|---|---|")
    W("| `atr_scaled` | ATR14 / close (vol level, price-normalized) | floor |")
    W("| `atr_pctile` | rank of ATR14 within trailing 252d (vol level) | floor |")
    W("| `atr_trend` | ATR14 / ATR50 (vol trend) | cap |")
    W("| `dist_sma200_atr` | (close - SMA200) / ATR14  (signed trend extension) | cap |")
    W("| `abs_dist_sma200_atr` | \\|close - SMA200\\| / ATR14 | cap |")
    W("| `sma50_slope_atr` | (SMA50 - SMA50[-10]) / ATR14 (trend slope) | cap |")
    W("| `ath_prox` | close / trailing-252d high (1.0 = at high) | cap |")
    W("| `prior_range_atr` | prior RTH range / ATR14 | floor |")
    W("| `prior_day_eff` | prior \\|close-open\\|/range (trend-vs-range) | cap |")
    W("")

    # ------------------------------------------------------------------ #
    # Diagnosis 1: year attribution
    # ------------------------------------------------------------------ #
    W("## Diagnosis: where the cold losses concentrate")
    W("")
    W("### Year attribution (baseline, both windows)")
    W("")
    W("| year | window | trades | total_R | avg_R |")
    W("|---|---|---:|---:|---:|")
    for nm, d in [("cold", cold), ("recent", rec)]:
        for y, gy in d.groupby("year"):
            W(f"| {y} | {nm} | {len(gy)} | {gy.r_multiple.sum():+.1f} | {gy.r_multiple.mean():+.3f} |")
    W("")
    W("The cold window is a near-breakeven aggregate (+7.5R over 441 trades). Losses are NOT spread "
      "across the quiet 2016-2019 tape -- those years are flat-to-slightly-positive. The damage is "
      "concentrated in **2020 (COVID, -20.5R)** and secondarily **2018 (-7.5R)**, i.e. sharp trending "
      "dislocations, plus a long shallow bleed that produces the -45R max drawdown. **This already "
      "falsifies the naive `low-vol => bad` story: the single worst cold year is the highest-vol one.**")
    W("")

    # ------------------------------------------------------------------ #
    # Diagnosis 2: cold decile attribution
    # ------------------------------------------------------------------ #
    W("### Cold-window decile (quintile) PnL attribution")
    W("")
    diag_feats = ["atr_scaled", "atr_pctile", "atr_trend", "dist_sma200_atr", "sma50_slope_atr", "ath_prox"]
    for col in diag_feats:
        sub = cold.dropna(subset=[col]).copy()
        sub["q"] = pd.qcut(sub[col], 5, duplicates="drop")
        W(f"**`{col}`** (cold quintiles, low->high):  " +
          " | ".join(f"{gy.r_multiple.sum():+.1f}R (n{len(gy)})" for _, gy in sub.groupby("q")))
        W("")
    W("Reads: the strongest, most repeatable cold-loss signal is **trend extension**. The top "
      "`dist_sma200_atr` quintile (prior close far above the 200d mean) is the worst bucket (~-30R), "
      "matched by the steepest `sma50_slope_atr` quintile (~-20R) and the nearest-`ath_prox` buckets "
      "(~-19R). Vol-level buckets (`atr_scaled`, `atr_pctile`) are non-monotone and do not isolate the "
      "losses. Mechanism: intraday fade-to-VWAP gets run over on days when the tape is powerfully, "
      "persistently extended relative to *current* volatility -- a quiet one-way trend (2017 melt-up) "
      "or a violent directional move (2020). Dividing the extension by ATR14 is what makes this fire on "
      "the quiet 2016-19 grind while leaving the choppier, higher-ATR recent up-trends (2023-24) untouched.")
    W("")

    # ------------------------------------------------------------------ #
    # Feature comparison table
    # ------------------------------------------------------------------ #
    W("## Candidate-switch comparison (one representative round/percentile threshold each)")
    W("")
    W("Threshold picked per feature to target ~75-90% recent retention (the regime the sleeve is "
      "validated on). `rec_kept%` = fraction of the 370 recent trades retained; `rec_R` = their total R "
      "(baseline +127.8R); `cold_R_kept` / `cold_R_blocked` = R of the kept vs blocked cold trades "
      "(want blocked clearly negative). NaN feature (warmup) => keep.")
    W("")
    W("| feature | rule | thr | rec_kept% | rec_R | cold_R_kept | cold_R_blocked | verdict |")
    W("|---|---|---:|---:|---:|---:|---:|---|")
    cand_thr = {
        "atr_scaled": 0.012, "atr_pctile": 0.5, "atr_trend": 1.2,
        "dist_sma200_atr": 12.0, "abs_dist_sma200_atr": 12.0, "sma50_slope_atr": 1.3,
        "ath_prox": 0.995, "prior_range_atr": 0.55, "prior_day_eff": 0.75,
    }
    comp_rows = []
    for feat_name, thr in cand_thr.items():
        mode = FEATURES[feat_name][0]
        rk = keep_mask(rec[feat_name], thr, mode)
        ck = keep_mask(cold[feat_name], thr, mode)
        rec_pct = rk.mean()
        rec_R = rec[rk].r_multiple.sum()
        cold_R_kept = cold[ck].r_multiple.sum()
        cold_R_blk = cold[~ck].r_multiple.sum()
        # verdict heuristic
        if rec_pct >= 0.75 and rec_R >= 120 and cold_R_blk <= -8:
            verdict = "helps"
        elif rec_pct < 0.7 or rec_R < 100:
            verdict = "guts recent"
        elif cold_R_blk > 0:
            verdict = "wrong sign"
        else:
            verdict = "weak"
        comp_rows.append(dict(feature=feat_name, rule=mode, thr=thr, rec_kept_pct=round(rec_pct, 3),
                              rec_R=round(rec_R, 1), cold_R_kept=round(cold_R_kept, 1),
                              cold_R_blocked=round(cold_R_blk, 1), verdict=verdict))
        W(f"| `{feat_name}` | {mode} | {thr} | {rec_pct:.2f} | {rec_R:+.1f} | {cold_R_kept:+.1f} | "
          f"{cold_R_blk:+.1f} | {verdict} |")
    pd.DataFrame(comp_rows).to_csv(RESULT_DIR / "feature_comparison.csv", index=False)
    W("")
    W("Only `dist_sma200_atr` (and its absolute twin) clears the bar: recent retention high, recent R "
      "preserved, and the blocked cold subset clearly negative. The headline **vol-floor hypothesis is "
      "falsified**: `atr_scaled` at 0.012 blocks *profitable* cold trades (blocked subset is POSITIVE) "
      "and still keeps the -20R 2020 book; `atr_pctile` only helps by gutting recent R.")
    W("")

    # ------------------------------------------------------------------ #
    # Deep dive: dist_sma200_atr threshold sweep
    # ------------------------------------------------------------------ #
    W("## Deep dive -- winning switch: `dist_sma200_atr` cap")
    W("")
    W("Rule: **trade only when prior close is <= X ATR14 above the 200-day SMA** "
      "(skip extreme, volatility-normalized trend extension). Threshold sweep:")
    W("")
    W("| cap (ATRs) | rec_kept% | rec_R | cold_R_kept | cold_R_blocked | full_R | full_t |")
    W("|---:|---:|---:|---:|---:|---:|---:|")
    sweep_rows = []
    for thr in [8, 9, 10, 11, 12, 13, 14]:
        rk = keep_mask(rec["dist_sma200_atr"], thr, "le")
        ck = keep_mask(cold["dist_sma200_atr"], thr, "le")
        ak = keep_mask(allt["dist_sma200_atr"], thr, "le")
        full_r = allt[ak].r_multiple
        row = dict(cap=thr, rec_kept_pct=round(rk.mean(), 3), rec_R=round(rec[rk].r_multiple.sum(), 1),
                   cold_R_kept=round(cold[ck].r_multiple.sum(), 1),
                   cold_R_blocked=round(cold[~ck].r_multiple.sum(), 1),
                   full_R=round(full_r.sum(), 1), full_t=round(tstat(full_r.values), 2))
        sweep_rows.append(row)
        W(f"| {thr} | {row['rec_kept_pct']:.2f} | {row['rec_R']:+.1f} | {row['cold_R_kept']:+.1f} | "
          f"{row['cold_R_blocked']:+.1f} | {row['full_R']:+.1f} | {row['full_t']:.2f} |")
    pd.DataFrame(sweep_rows).to_csv(RESULT_DIR / "dist_sma200_threshold_sweep.csv", index=False)
    W("")
    W(f"Chosen threshold: **cap = {SWITCH_THRESHOLD:.0f} ATRs** (round, and just above the recent window's "
      "own extension range -- recent prior-close extension maxes near ~17.7 ATRs but is <=12 on ~92% of "
      "sessions). At cap=12 recent retention is ~95% with recent R essentially intact, and the cold "
      "window sheds ~-16R of pure drawdown.")
    W("")

    # ------------------------------------------------------------------ #
    # Full-history year split
    # ------------------------------------------------------------------ #
    W("### Full-history year split (baseline vs switched)")
    W("")
    ak = keep_mask(allt["dist_sma200_atr"], SWITCH_THRESHOLD, "le")
    W("| year | n_all | R_base | n_kept | R_switch |")
    W("|---|---:|---:|---:|---:|")
    ysplit_rows = []
    for y in sorted(allt["year"].unique()):
        ay = allt[allt["year"] == y]
        ky = allt[ak & (allt["year"] == y)]
        ysplit_rows.append(dict(year=y, n_all=len(ay), R_base=round(ay.r_multiple.sum(), 1),
                                n_kept=len(ky), R_switch=round(ky.r_multiple.sum(), 1)))
        W(f"| {y} | {len(ay)} | {ay.r_multiple.sum():+.1f} | {len(ky)} | {ky.r_multiple.sum():+.1f} |")
    pd.DataFrame(ysplit_rows).to_csv(RESULT_DIR / "full_history_year_split.csv", index=False)
    base_full, sw_full = allt.r_multiple.sum(), allt[ak].r_multiple.sum()
    W(f"| ALL | {len(allt)} | {base_full:+.1f} | {int(ak.sum())} | {sw_full:+.1f} |")
    W("")

    # ------------------------------------------------------------------ #
    # On-rate time series (all sessions)
    # ------------------------------------------------------------------ #
    sess = feat[["dist_sma200_atr"]].copy()
    sess.index = pd.to_datetime(sess.index)
    sess["year"] = sess.index.year
    sess["on"] = (sess["dist_sma200_atr"] <= SWITCH_THRESHOLD) | sess["dist_sma200_atr"].isna()
    onrate = sess.groupby("year")["on"].mean()
    onrate.to_csv(RESULT_DIR / "switch_on_rate_by_year.csv")
    W("### Switch on-rate over ALL sessions (does it toggle or memorise the split?)")
    W("")
    W("| year | " + " | ".join(str(y) for y in onrate.index) + " |")
    W("|---|" + "|".join("---:" for _ in onrate.index) + "|")
    W("| on-rate | " + " | ".join(f"{v:.2f}" for v in onrate.values) + " |")
    W("")
    W("The switch is ON ~90% of sessions in most years and dips to ~0.66/0.78 in the steadiest-trend "
      "years (2017 melt-up, 2020 COVID recovery). It toggles *inside both windows* (recent extension "
      "exceeds the cap in 2023-24 too), so it is not a disguised 2016-2021 date label -- but it is also "
      "mostly-on, i.e. a light-touch tail cap rather than a regime on/off gate.")
    W("")

    # ------------------------------------------------------------------ #
    # t-stat / deflation
    # ------------------------------------------------------------------ #
    n_features = 9
    n_thr_per = 7  # representative sweep breadth per feature
    n_combos = n_features * n_thr_per
    W("### t-stat and deflation read")
    W("")
    W(f"- Full-history baseline: n={len(allt)}, R={base_full:+.1f}, t={tstat(allt.r_multiple.values):.2f}.")
    W(f"- Switched full history (cap=12): n={int(ak.sum())}, R={sw_full:+.1f}, "
      f"t={tstat(allt[ak].r_multiple.values):.2f}.")
    W(f"- Recent-only baseline (the validated regime): n={len(rec)}, R={rec.r_multiple.sum():+.1f}, "
      f"t={tstat(rec.r_multiple.values):.2f}.")
    W(f"- Feature/threshold combinations examined ~ {n_features} features x ~{n_thr_per} thresholds "
      f"= ~{n_combos}. Deflated for that many looks, lifting the full-history t from ~2.4 to ~2.9 is a "
      "modest, non-decisive improvement, and it never reaches the recent-only t (~3.2). The switch "
      "reduces cold *drag*; it does not reveal a hidden cold-window *edge* (switched cold is still only "
      "~breakeven-positive per trade).")
    W("")

    # ------------------------------------------------------------------ #
    # Bonus: exit-refined stream + prop lifecycle
    # ------------------------------------------------------------------ #
    W("## Bonus: exit-refined stream and prop lifecycle under the switch")
    W("")
    ek = keep_mask(exitref["dist_sma200_atr"], SWITCH_THRESHOLD, "le")
    W(f"- Exit-refined day_mid-target recent stream: baseline n={len(exitref)}, "
      f"R={exitref.r_multiple.sum():+.1f}; switched n={int(ek.sum())}, R={exitref[ek].r_multiple.sum():+.1f} "
      f"(retains {ek.mean():.0%}). The cap is nearly free on the recent exit-refined book too.")

    # prop lifecycle on filtered recent 1s path stream
    path = pd.read_csv(SRC_DIR / "path_replay_trades.csv")
    path_1s = path[path["path_label"] == "1s"].copy().join(feat, on="date")
    path_1s["r_multiple"] = path_1s["path_r_multiple"].astype(float)
    prop_pk = keep_mask(path_1s["dist_sma200_atr"], SWITCH_THRESHOLD, "le")

    profile = PropFirmRiskProfile(
        trailing_drawdown_usd=2000.0, pass_target_usd=3000.0, first_payout_usd=1500.0,
        floor_cap_delta_usd=0.0, challenge_fee_usd=0.0, account_start_spacing_days=14,
    )
    starts = make_account_starts(RECENT_START, RECENT_END_EXCLUSIVE, profile.account_start_spacing_days)

    def prop_grid(stream: pd.DataFrame, tag: str) -> pd.DataFrame:
        rows = []
        for risk in (100, 125, 150, 175, 200):
            trades = stream.assign(pnl_usd=stream["r_multiple"] * float(risk),
                                   exit_ts=stream["path_exit_ts"]).to_dict("records")
            out = simulate_prop_firm_risk(variant_id=f"{tag}_r{risk}", trades=trades,
                                          account_starts=starts, profile=profile,
                                          end_exclusive=RECENT_END_EXCLUSIVE)
            rows.append({"stream": tag, "risk_usd_per_r": risk, **score_prop_firm_outcomes(out)})
        return pd.DataFrame(rows)

    prop = pd.concat([prop_grid(path_1s, "unfiltered"),
                      prop_grid(path_1s[prop_pk], "switched")], ignore_index=True)
    prop.to_csv(RESULT_DIR / "prop_lifecycle_switch.csv", index=False)
    W("")
    W("Prop lifecycle ($2,000 EOD trailing DD, $3,000 pass, $1,500 first payout, 14-day starts; "
      "recent 1s path stream):")
    W("")
    W("| stream | risk/R | first_payout_rate | pre_payout_bust | ev_per_start | avg_days_to_payout |")
    W("|---|---:|---:|---:|---:|---:|")
    for _, r in prop.iterrows():
        W(f"| {r['stream']} | ${int(r['risk_usd_per_r'])} | {r['first_payout_rate']:.3f} | "
          f"{r['pre_payout_bust_rate']:.3f} | ${r['ev_per_start_usd']:.0f} | {r['avg_days_to_first_payout']:.0f} |")
    W("")
    W("Because the switch removes <5% of recent trades, prop economics are essentially unchanged from "
      "the validation packet -- the switch is a cold-window justification, not a recent-window edge lift.")
    W("")

    # ------------------------------------------------------------------ #
    # Summary
    # ------------------------------------------------------------------ #
    W("## Summary Read")
    W("")
    W("- **The headline vol-floor hypothesis is falsified on this data.** The worst cold year (2020) is "
      "the *highest*-vol one, and scaled-ATR / ATR-percentile floors either block profitable cold trades "
      "(wrong sign) or only 'help' by gutting recent R. A minimum-volatility deactivation rule is NOT "
      "supported.")
    W("- **The one feature that survives is trend extension: `dist_sma200_atr` (cap = 12 ATRs).** "
      "Skip days whose prior close sits >12 ATR14 above the 200-day SMA. Recent: retains ~95% of trades "
      f"({rec[keep_mask(rec['dist_sma200_atr'],12,'le')].r_multiple.sum():+.1f}R vs +127.8R baseline). "
      f"Cold: blocked subset is {cold[~keep_mask(cold['dist_sma200_atr'],12,'le')].r_multiple.sum():+.1f}R "
      "of pure drawdown removed; full history improves from +135.3R to "
      f"{sw_full:+.1f}R and t from ~2.4 to ~2.9.")
    W("- **But this is a qualified pass, not a clean regime story.** In the recent window the blocked "
      "extended days were themselves profitable, so the feature is a *proxy* whose sign flips across "
      "windows (extension is fatal in the quiet cold tape, benign in the choppier recent tape). It "
      "reduces cold *drag* to breakeven; it does not manufacture a cold-window edge. Deflated for ~63 "
      "feature/threshold looks the t-lift is modest and never beats the recent-only sleeve (t~3.2).")
    W("- **Recommendation: treat the sleeve as recent-regime-only.** The trend-extension cap "
      "(`dist_sma200_atr <= 12`) is the best available single-feature deactivation rule if one is "
      "required -- it is causal, monotone at the loss-bearing tail, and mechanistically motivated -- but "
      "it should be deployed as a drawdown-tail guard, not as evidence that 2016-2021 is tradable. A "
      "*volatility* floor should NOT be used; it is contradicted by the diagnosis.")
    W("")
    W("## Artifacts")
    W("")
    for name in ["daily_features.csv", "feature_comparison.csv", "dist_sma200_threshold_sweep.csv",
                 "full_history_year_split.csv", "switch_on_rate_by_year.csv",
                 "prop_lifecycle_switch.csv"]:
        W(f"- `data/results/{RUN_SLUG}/{name}`")
    W(f"- report: `learnings/reports/{REPORT_PATH.name}`")
    W("")

    REPORT_PATH.write_text("\n".join(lines) + "\n")
    print(f"Wrote {REPORT_PATH}")
    print(f"Wrote artifacts to {RESULT_DIR}")
    print(f"switched full history: n={int(ak.sum())} R={sw_full:.1f} t={tstat(allt[ak].r_multiple.values):.2f}")


if __name__ == "__main__":
    main()
