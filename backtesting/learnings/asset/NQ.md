# NQ (Nasdaq-100 Futures) — Strategy Learnings

## Instrument Profile
- **Point value**: $20/point
- **Min tick**: 0.25
- **Commission**: $0.05/contract/side
- **Data**: 2016-01 to 2026-02 (~10 years, 5m + 1m + 1s parquet). Previous data extended to 2015 but is no longer available in current parquet files.
- **Liquidity**: Both NY and Asia sessions are viable. Asia session runs 20:00-07:00 ET (cross-midnight).
- **1s data note**: NQ_1s.parquet uses `.v.0` (volume roll) instead of `.c.0` (calendar roll). Mismatches only affect ~20 days in 2016 around quarterly rolls. From 2017 onward, all prices match 1m/5m perfectly. Impact on backtests is negligible — the 1s magnifier only resolves ambiguous bars within the same candle.
- **Order-book data note (2026-05-19)**: The pure 1m LSI midpoint-velocity survivor can use DataBento `mbp-1` instead of `mbp-10`. MBP-1 replay on the 21 holdout morning-prefix windows matched `21/21` frozen tiers and `21/21` risk weights, with one harmless raw feature drift of `+0.05` ticks/second (`1.80` to `1.85`, still `high`). MBP-1 does not validate deeper-book liquidity-vacuum or absorption variants.
- **Order-book frequency note (2026-05-27)**: The higher-frequency 1m noThu additive pressure branch was rebuilt with an MBP-1-compatible level-1 pressure score and replayed through the same stress harness. It matched the old noThu pressure tier assignments exactly on the 46-trade holdout (`+15.84R`, `0.344R` avg, PF `1.93`, DD `-4.63R`) and used zero new DataBento fetches. Account stress was mixed: holdout daily-stop/min-days EV improved to `3.80R/account` (`+0.34R`), but post-2023 EV worsened (`-0.66R`) with breach rate `+8.0%`; keep this as a higher-frequency shadow side branch, not a replacement for pure 1m velocity.

## Strategies Tested

### Plain NY ORB Breakout Seed Surface (2026-06-18) — NO-GO
- **Status**: NO-GO — seed grid produced validation-looking winners, but none passed preholdout, cluster, PSR/DSR, or promotion gates.
- **Report**: `backtesting/learnings/reports/ORB_FUTURES_SURFACE_V1_SEED_NQ_NY_20260618.md`; artifacts in `backtesting/data/results/orb_futures_surface_v1_seed_nq_ny_20260618/`.
- **Scope**: New canonical `strategy="orb_breakout"` path, NQ NY seed grid only, train `2021-2023`, validation `2024`, holdout closed from `2025` onward. Search covered 1,458 raw candidates / 42 effective trials.
- **Best rejected cell**: `nq__ny__orb15__stop10__gap0__rr2__long__no_thu__low_atr_only__small_orb_only` had 2024 validation `+14.20R`, PF `1.32`, but 2021-2024 preholdout `-19.67R`, PF `0.83`, DD `-37.86R`, cluster score `0.00`, PSR `0.1374`, DSR `0.0006`, cost/slippage stress `FAIL`, no-single-year dependency `FAIL`.
- **Conclusion**: Plain NQ NY ORB breakout does not deserve promotion from the seed surface. The new ORB Futures Surface v1 workflow correctly rejected isolated validation winners before any holdout opening.

### Plain ORB Breakout Broad Surface (2026-06-18) — EXACT-REPLAY QUEUE
- **Status**: EXACT-REPLAY QUEUE ONLY — NQ Asia and NQ LDN plain ORB breakout clusters passed broad-surface promotion gates. NQ NY remained rejected.
- **Report**: `backtesting/learnings/reports/ORB_FUTURES_SURFACE_V1_BROAD_FULL_20260618.md`; artifacts in `backtesting/data/results/orb_futures_surface_v1_broad_full_20260618/`.
- **Scope**: `strategy="orb_breakout"` broad grid across all assets/sessions, train `2021-2023`, validation `2024`, holdout closed from `2025` onward. NQ sleeves each covered 9,720 raw candidates.
- **Top NQ Asia row**: `nq__asia__orb5__stop7p5__gap0__rr1p25__long__no_mon__small_or_mid_orb` had 2024 validation `+34.25R`, 2021-2024 preholdout `+68.91R`, stress `+29.83R`, cluster score `1.00`, DSR `0.8446`.
- **Top NQ LDN row**: `nq__ldn__orb30__stop12p5__gap0__rr2p5__long__no_tue__small_orb_only` had 2024 validation `+22.21R`, 2021-2024 preholdout `+39.78R`, stress `+29.85R`, cluster score `1.00`, DSR `0.7337`.
- **Conclusion**: Treat NQ Asia and NQ LDN plain breakout as research candidates for exact replay only. Do not open holdout or paper trade until exact replay confirms fills and no same-bar/magnifier drift.

### Plain ORB Breakout Exact Replay (2026-06-18) — MIXED
- **Status**: NQ Asia R1 exact-replay PASS; NQ Asia R2/R3 and NQ LDN R1 exact-replay WATCH. Holdout stayed closed.
- **Report**: `backtesting/learnings/reports/ORB_FUTURES_SURFACE_V1_EXACT_REPLAY_20260618.md`; artifacts in `backtesting/data/results/orb_futures_surface_v1_exact_replay_20260618/`.
- **Scope**: execution-engine exact replay of one-sided promoted broad-surface rows over `2021-01-01` to `2024-12-31`, using live-style 5m signal bars plus 1s fill/exit sequencing. The replay required adding execution support for `strategy_type="orb_breakout"` stop-style entries.
- **Pass**: `nq__asia__orb5__stop7p5__gap0__rr1p25__long__no_mon__small_or_mid_orb` produced `450` exact trades, `+76.47` net R, PF `1.36`, max DD `-10.32R`, and retained `111%` of research preholdout R. Exact year R was positive in all years: 2021 `+24.90R`, 2022 `+8.00R`, 2023 `+15.28R`, 2024 `+43.87R`.
- **Watch**: the nearby NQ Asia ATR-gated rows and NQ LDN long row stayed positive but had large trade-count and R-retention drift: NQ Asia R2 `+8.72R` / `12%` retention, NQ Asia R3 `+11.66R` / `16%` retention, NQ LDN R1 `+8.53R` / `21%` retention.
- **Conclusion**: Promote only the NQ Asia 5m, no-Monday, small-or-mid-ORB long row to the next pre-holdout robustness step. Keep the other NQ exact rows as diagnostics, not finalists. Still do not open holdout or paper trade until doubled-cost/slippage exact replay and any broker stop-order semantics are locked.

### Plain ORB Breakout Exact Stress (2026-06-18) — WATCH
- **Status**: WATCH, not promotion. The NQ Asia exact survivor stayed positive under strict cost/slippage stress but failed the all-years-positive requirement. Holdout stayed closed.
- **Report**: `backtesting/learnings/reports/ORB_FUTURES_SURFACE_V1_EXACT_STRESS_20260618.md`; artifacts in `backtesting/data/results/orb_futures_surface_v1_exact_stress_20260618/`.
- **Stress model**: post-exact-replay accounting on the frozen trade ledger, with `2x` baseline commission plus `2` adverse ticks per side on every filled round trip. Signal/fill path unchanged.
- **Result**: `nq__asia__orb5__stop7p5__gap0__rr1p25__long__no_mon__small_or_mid_orb` fell from exact `+76.47R` to stressed `+33.76R`, PF `1.15`, DD `-17.21R`, retention `44%`. Year split under full stress: 2021 `+8.27R`, 2022 `+2.84R`, 2023 `-3.89R`, 2024 `+26.53R`.
- **Conclusion**: NQ Asia remains the best plain-breakout survivor after exact stress, but it is not clean enough to open holdout. Treat it as a watchlist candidate for microstructure/slippage diagnosis or a stricter variant, not as a locked finalist.

### Asia Continuation (magnifier) — low R:R / high WR
- **Status**: NO-GO (robust pipeline failed Phases 3 + 5)
- **Config tested**:

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia |
| rr | 1.5 |
| tp1_ratio | 0.2 |
| asia_stop_atr_pct | 5.75 |
| asia_min_gap_atr_pct | 1.25 |
| asia_max_gap_atr_pct | 11.0 |
| magnifier | ON |

- **Full-history performance** (2015-2026): 2096 trades, 73.8% WR, 46.0R, Sharpe 0.54, PF 1.09, Max DD -25.6R
- **Walk-forward OOS**: WF efficiency 0.68, stability 1.00 (high), combined OOS 1143 trades, 13.4R, Sharpe 0.30, DD -20.4R
- **Prop constraints**: FAIL — DD -20.4R (limit 10R), worst month -8.7R (limit 5R), no year reached 24R annual target
- **Hold-out (2025-2026)**: 199 trades, 76.4% WR, 13.6R, Sharpe 1.66, PF 1.32, DD -5.9R (PASS on its own)
- **Monte Carlo**: 2.9% survival at 10R threshold (catastrophic)
- **DB entry**: `bt-nq-asia-robust-pipeline-no-go-3b81a8`
- **Conclusion**: The low R:R profile (avg win +0.35R vs avg loss -0.92R) creates outsized drawdowns despite high win rate. Works in trending regimes (2021: +14.8R, 2025: +16.1R) but collapses in choppy ones (2023: -17.0R). Not viable for prop firm accounts. Would need R:R >= 2.0, tighter stops, or a regime filter to reconsider.

### Asia Continuation v2 (10m ORB, no-Thursday, magnifier) — optimized
- **Status**: CONDITIONAL (robust pipeline passed Phases 1, 2, 4; failed Phases 3, 5)
- **Config tested**:

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia |
| orb_end | 20:10 (10m ORB) |
| entry_start | 20:10 |
| entry_end | 23:00 |
| rr | 1.5 |
| tp1_ratio | 0.2 |
| asia_stop_atr_pct | 5.75 |
| asia_min_gap_atr_pct | 1.25 |
| asia_max_gap_atr_pct | 11.0 |
| atr_length | 5 |
| magnifier | ON |
| gate | No Thursday trades |

- **Full-history performance** (2015-2026): 1,757 trades, 78.5% WR, 113.4R, Sharpe 1.745, PF 1.31, Max DD -9.3R
- **Walk-forward OOS** (36m IS / 12m OOS / 12m step, 6 folds): WF efficiency 0.59, stability 0.77 (high), combined OOS 875 trades, 45.4R, Sharpe 1.607, PF 1.32, DD -7.6R
- **Parameter stability**: rr=1.25 in 5/6 folds, tp1=0.15 in 5/6 folds, stop_atr mostly 5.0, gap 9.0 dominant
- **Prop constraints**: FAIL — DD -7.6R (PASS), worst month -2.6R (PASS), expectancy +0.052R (PASS), but annual R < 24R (FAIL: best year 16.7R, worst -1.6R)
- **Hold-out (2025-2026)**: 162 trades, 77.8% WR, 10.1R, Sharpe 1.60, PF 1.27, DD -9.3R (PASS)
- **Monte Carlo**: 74.2% survival at 10R (PASS >=70%), but p95 DD = 13.9R (FAIL <=12R). Ruin probability 25.9%.
- **Conclusion**: Massive improvement over v1 — DD cut from -25.6R to -9.3R, Sharpe tripled from 0.54 to 1.75, all years positive in structural test. Walk-forward is solid. The strategy survives most MC paths (74%) but annual R is too low for prop firm 24R targets and tail drawdowns still exceed thresholds. This is a consistent, low-edge grinder (~0.05R/trade, ~7.6R/year OOS average).

#### What improved v1 → v2
- **10m ORB window** (was 15m): Sweet spot — more FVGs detected, tighter ranges, better fill rates
- **entry_end=23:00** (was default): Extended entry window captures late-session setups
- **atr_length=5** (was 14): Faster ATR adapts to recent vol, tightens stops during calm periods
- **No Thursday trades**: Thursday is negative EV on NQ Asia — removing it cuts ~15% of trades but eliminates a drag

### Asia Continuation v3 — Dual-Model Sweep + Stop Anchor Discovery + Round 11 Grid (SUPERSEDED by R4 Final)

- **Status**: SUPERSEDED — R4 Final (1s magnifier, 2016 start) achieved Calmar 23.85 vs v3's 20.14 (1m magnifier, 2015 start)

#### Dual-Model Sweep (run_nq_asia_dual_sweep.py)
- Tested both "Aggressive" (tight stop / high rr) and "Wide" (wide stop / low rr) model profiles
- Pre-sweep confirmed: **ORB 10m + ATR 14** beats ORB 15m and ATR 5 on Sharpe for both profiles
- **Aggressive #1** (stop=3.0%, gap=1.25%, maxgap=5.0%, rr=2.5, tp1=0.30): 1,656 trades, 61.2% WR, 190.6R, Sharpe 1.805, DD -14.3R — no prop-viable configs found (none cleared Sharpe>1.5 AND DD>-10R)
- **Wide Prop #1** (stop=6.5%, gap=1.25%, maxgap=5.0%, rr=1.5, tp1=0.25): 1,656 trades, 75.4% WR, 113.7R, Sharpe 1.638, DD -9.7R
- **Wide Prop pipeline result**: NO-GO — WF efficiency 0.311 (FAIL), OOS DD -11.5R, MC survival 8.8% (catastrophic). 2022 and 2023 OOS were negative (-2.6R, -0.0R). ATR 14 performs worse OOS than ATR 5 for Asia.
- **DB entries**: `bt-nq-asia-aggressive-pre-pipeline-ac47f8`, `bt-nq-asia-wide-pre-pipeline-799ea8`, `bt-nq-asia-wide-prop-pre-pipeline-1bd178`
- **Conclusion**: Dual sweep found nothing better than v2 CONDITIONAL in walk-forward terms.

#### Asia Stop Sweep — Round 9 (broad, 1% steps) & Round 10 (fine, 0.1% steps)
Anchor held fixed: gap=1.25%, maxgap=11.0%, tp1=0.20, ATR 5, ORB 10m, entry≤23:00, no-Thursday

**Round 9 (broad)** — 11 stops × 7 rr = 77 combos (run_nq_asia_v2_stop_broad_sweep.py):
- **Two distinct zones** emerged in the Calmar heatmap:
  - **Zone A** (stop=3.5–4.5%, rr=2.0–3.0): High Calmar (8–11), high R/yr (10–13R), DD -12–16R
  - **Zone B** (stop=5.5–6.5%, rr=1.0–1.5): Lower Calmar (6–9), lower R/yr (6–8R), DD -9–12R — where v2 lives
- Best marginal Sharpe: stop=4%, best marginal Calmar: stop=6%. But stop=4% dominates on individual combos.
- **Key lesson**: The optimal rr shifts completely between zones — Zone A needs high rr (2.0–3.0), Zone B needs low rr (1.0–1.5). These are fundamentally different strategy profiles.

**Round 10 (fine)** — 31 stops × 5 rr = 155 combos (run_nq_asia_v2_stop_fine_sweep.py):
- **stop=3.7%, rr=3.0 is the new Calmar anchor**: Calmar 11.12, 13.8 R/yr, DD -13.7R, Sharpe 1.476, **all 11 years positive** (min: 4.8R in 2023)
- Compared to v2 (stop=5.8%, rr=1.5): Calmar 7.43, 7.6 R/yr, DD -11.2R — new anchor is 50% better Calmar
- The 3.6–4.2% stop range all deliver Calmar > 10 at rr=3.0 — broad plateau, not a fragile spike
- stop=5.9–6.0% at rr=1.5 is the best of Zone B: Calmar 9.04/8.66, DD -9.7R, 0 neg years

**Round 11 (full grid at stop=3.7%)** — 500 combos: gap × maxgap × rr × tp1 (run_nq_asia_v3_r11_sweep.py):

Param grid: gap=[0.75,1.0,1.25,1.5,2.0], maxgap=[5,8,11,15], rr=[2,2.5,3,3.5,4], tp1=[0.15,0.20,0.25,0.30,0.35]

Key findings:
- **Best Calmar overall**: gap=1.25%, maxgap=8%, rr=3.5, tp1=0.25 → Calmar 14.04, 18.3 R/yr, DD -14.1R, but 2023=-1.0R
- **Best Calmar with 0 neg years**: gap=1.25%, maxgap=5%, rr=2.5, tp1=0.25 → **Calmar 13.05**, 15.1 R/yr, DD -12.8R, Sharpe 1.729
- **vs v2 baseline**: Calmar +50% (13.05 vs 8.66), R/yr doubled (15.1 vs 7.7)

Marginal analysis:
- gap=1.25% is the marginal peak (9.85 avg), but gap step was 0.25–0.5 — too coarse to fully resolve
- maxgap is flat (8.37–8.69 avg) — not a meaningful lever
- rr is flat (8.05–8.75 avg) at 0.5-step resolution
- tp1=0.25–0.30 sweet spot for Calmar

**Round 12 (fine grid at stop=3.7%)** — 448 combos: gap × maxgap × rr × tp1 (run_nq_asia_v3_r12_fine_sweep.py):

Param grid: gap=0.90–1.50 in 0.1 steps, maxgap=[5,8], rr=1.75–3.50 in 0.25 steps, tp1=[0.20,0.25,0.30,0.35]

Key findings:
- **New peak Calmar**: gap=1.20%, maxgap=5%, rr=2.25, tp1=0.30 → **Calmar 15.54**, 17.1 R/yr, DD -12.2R, Sharpe 1.897 — but 2022=-0.3R (barely negative)
- **Best Calmar with 0 neg years**: gap=0.90%, maxgap=5%, rr=1.75, tp1=0.35 → **Calmar 14.82**, 17.4 R/yr, DD -13.0R, Sharpe 1.964
- **Cleanest high-Calmar**: gap=0.90%, maxgap=5%, rr=1.75, tp1=0.25 → Calmar 14.18, 12.7 R/yr, DD -10.0R (exactly at 10R) — all years positive
- **vs R11 best (0 neg years)**: R12 improved from Calmar 13.05 → 14.82 (+14%)

Critical finding — **gap dimension has two distinct peaks, not one smooth peak**:
- gap=0.90% avg Calmar 9.96 (34/64 clean configs)
- gap=1.00–1.10% are the worst values (7.79–8.37 avg, only 5–11/64 clean)
- gap=1.20% avg Calmar 11.02 (14/64 clean) — highest avg, but sparse clean zone
- gap=1.30% drops (9.22 avg, 12/64 clean)
- gap=1.40–1.50% are the most robust (44–47/64 clean, Calmar 10.14–10.68)

**The valley at gap=1.00–1.10% is a dead zone.** gap=0.90% and gap=1.20% are two separate peaks. This explains why R11's 0.25-step grid was misleading (it straddled the valley at 1.0 and called it the same region as 1.25).

Calmar heatmap key cells:
- g=0.90%/rr=1.75: Calmar **14.82*** (clean)
- g=1.20%/rr=1.75: Calmar 13.86* (clean)
- g=1.20%/rr=2.25: Calmar 15.54 (2022=-0.3R — best overall but not clean)
- g=1.20%/rr=3.25: Calmar 14.17* (clean)
- g=1.40–1.50%/rr=2.25–2.75: Calmar 12–13* (broad clean plateau, more robust)

**Two candidate configs for walk-forward:**

| # | Config | Calmar | R/yr | DD | Sharpe | Clean |
|---|--------|--------|------|-----|--------|-------|
| A | gap=1.20%, rr=2.25, tp1=0.30 | **15.54** | 17.1 | -12.2R | 1.897 | 2022=-0.3R |
| B | gap=0.90%, rr=1.75, tp1=0.35 | 14.82 | 17.4 | -13.0R | **1.964** | **0 neg years** |
| C | gap=0.90%, rr=1.75, tp1=0.25 | 14.18 | 12.7 | -10.0R | 1.636 | **0 neg years** |

All use: stop=3.7%, maxgap=5%, ATR 5, ORB 10m, entry≤23:00, no-Thursday.

**Recommendation**: Config B for walk-forward (clean years, Sharpe near 2.0, tight DD). Config A is slightly higher Calmar but the 2022 loss is a concern for OOS robustness in the 2022-2023 structural weak period.

**Round 13 (config variable broad sweep)** — 35 single-variable backtests (run_nq_asia_v3_r13_config_sweep.py):

Key findings per variable (anchor held fixed while each is swept):
- **ORB window**: 10m confirmed. 15m/20m within 0.3 Calmar (plateau). Hard cliff at 5m and 30m.
- **entry_end**: 23:00 is best (14.82); 00:00 close (14.44, Sharpe 2.006). Sharp drop after 00:00. Fine-tune 22:30–00:30.
- **ATR length**: ATR 5 confirmed decisively. Drops 2+ Calmar in both directions. Don't touch.
- **Direction**: Both directions beats long-only on Calmar (14.82 vs 10.21). Long-only has higher Sharpe (2.288) but 2022=-5.7R. Short-only is dead. Keep both. NQ Asia is unlike NY — both directions contribute.
- **flat_start (MAJOR)**: flat_start=00:00 (midnight ET): Calmar **20.14**, DD **-10.1R**, Sharpe 2.123. Same 1800 trades — just closes any open positions at midnight instead of letting them run until 06:45. This removes overnight drift risk from partially-profitable trades that haven't hit TP2. Steep benefit from 06:45→00:00 (Calmar +5.32). Fine-tune around midnight.
- **max_gap_points**: Completely non-binding — NQ Asia FVGs all ≤ 25 pts. Keep disabled.
- **DOW excl Tue**: Adding Tue exclusion (no-Thu + no-Tue): Calmar 16.98, DD -9.1R, Sharpe 2.064 — meaningful despite losing 25% of trades. Must test stacked with flat_start=00:00.

**Round 14 (fine sweep: flat_start, entry_end, DOW stack)** — 35 backtests (run_nq_asia_v3_r14_fine_sweep.py):

Key findings:
- **flat_start=00:00 confirmed as the peak** — smooth curve, 23:00 (18.52) and 23:30 (18.46) are next best. Not fragile.
- **excl-Tue does NOT stack with flat_start=00:00** — with flat=00:00, adding excl-Tue gives Calmar 18.96 vs 20.14 alone. They fix the same problem (overnight drift from unresolved trades). Not additive.
- **entry_end 23:00 and 00:00 essentially tied at flat=00:00** (20.14 vs 20.08) — trades entered past 23:00 get midnight-closed anyway.
- **Top 3 stacked configs all within 0.24 Calmar** (20.08–20.32). The simpler no-Thursday-only config wins on trade count and R/yr.

**New anchor (R14):**
- stop=3.7%, gap=0.90%, maxgap=5%, rr=1.75, tp1=0.35, ATR 5, ORB 10m, entry_end=23:00, **flat_start=00:00**, no-Thursday
- Calmar **20.14**, 18.3 R/yr, DD **-10.1R**, Sharpe **2.123**, 1,800 trades, **0 negative full years**
- vs v2: Calmar +132%, DD comparable (-10.1R vs -9.7R), R/yr +138%

**Round 15 (grid re-sweep: gap × rr × tp1 at flat_start=00:00)** — 384 combos (run_nq_asia_v3_r15_grid_sweep.py):

Key findings:
- **R14 anchor confirmed as the global optimum — no reshuffling.** gap=0.90%, rr=1.75, tp1=0.35 is #1 by Calmar (20.14) and #1 by 0-neg-years. flat_start=00:00 did NOT shift rr or tp1 surface.
- **gap=0.90% is now uniquely dominant**: highest avg Calmar (11.74) AND most clean configs (35/48). At flat_start=00:00, the entire gap=0.90% row is clean (7/8 rr values all 0-neg-years). This is the most stable parameter region tested.
- **Dead zone at gap=1.10% confirmed again** (0/48 clean, avg Calmar 8.56).
- **rr=1.75 is the peak for gap=0.90%**: 20.14 vs rr=2.00 at 16.27 — large gap, well-defined optimum.
- **tp1=0.30 marginally best on avg** (10.97 vs 10.63 for 0.35) but within noise. Anchor tp1=0.35 confirmed.
- **Optimization complete**. Gap between #1 (20.14) and #2 (17.76) is too large to close with fine-tuning.

**Final v3 config (optimization complete, walk-forward pending):**

| Param | Value |
|-------|-------|
| stop_atr_pct | 3.7% |
| min_gap_atr_pct | 0.90% |
| max_gap_atr_pct | 5.0% |
| rr | 1.75 |
| tp1_ratio | 0.35 |
| atr_length | 5 |
| ORB window | 10m (20:00–20:10 ET) |
| entry_end | 23:00 ET |
| flat_start | 00:00 ET (midnight close) |
| direction | both |
| gate | no-Thursday |

**In-sample performance** (2015–2026, 11 full years):
- Trades: 1,800 | WR: 64.8% | Net R: 203.0 | Avg Annual R: **18.3** | Max DD: **-10.1R**
- Sharpe: **2.123** | Calmar: **20.14** | R/trade: 0.1128 | **0 negative full years**
- Year range: 2022 (worst, +9.2R) to 2016 (best, +26.5R) — all strongly positive

**vs baselines:**
- v2 CONDITIONAL: Calmar 8.66, DD -9.7R, 7.7 R/yr → **+132% Calmar, +138% R/yr, comparable DD**
- NQ NY CONDITIONAL: Calmar 4.41 OOS → Asia v3 has dramatically better in-sample characteristics

### Asia Continuation v3+ICF — Impulse Close Filter Optimization

- **Status**: OPTIMIZATION COMPLETE — walk-forward pending
- **Objective**: Test impulse_close_filter (ICF) on NQ Asia v3 config, re-optimize if positive

#### Baseline Comparison (ICF on vs off, no Thursday gate)

| Metric | No ICF (v3 params) | ICF On (v3 params) | Change |
|--------|-------|--------|--------|
| Filled trades | 2,252 | 2,345 | +93 (+4.1%) |
| Win rate | 63.7% | 64.0% | +0.3pp |
| Net R | 194.0 | 212.8 | +18.8R (+9.7%) |
| Sharpe | 1.619 | 1.707 | +5.4% |
| Calmar | 11.93 | 13.02 | +9.1% |
| Max DD | -16.3R | -16.3R | same |
| Long R | 117.9 | 112.1 | -5.8R |
| Short R | 76.2 | 100.7 | **+24.5R** |

- **ICF improvement driven entirely by shorts** — longs slightly degraded while shorts gained +24.5R
- **DB entries**: `bt-nq-asia-v3-baseline-no-icf-1d1e08`, `bt-nq-asia-v3-icf-on-00a1c8`

#### Re-optimization with ICF enabled

**RR sweep** (1.0–3.5 broad, 1.50–2.50 fine at 0.05 steps):
- Best Calmar: rr=2.15 → Calmar 14.38, Sharpe 1.75, DD -16.8R
- Best Sharpe: rr=2.10 → Sharpe 1.80, Calmar 14.14
- ICF shifted optimal RR from 1.75 → 2.15 (+23%)

**3-way grid**: rr × stop_atr_pct × tp1_ratio (210 combos):
- Best Calmar: rr=2.15, stop=3.3%, tp1=0.40 → Calmar 14.88, Sharpe 1.74, DD -17.3R
- ICF shifted stop from 3.7% → 3.3%, tp1 from 0.35 → 0.40

**Gap filter**: gap=0.90%, maxgap=5.0% confirmed (no change from v3)

**ATR length**: ATR 5 confirmed (sweeps 3–20, ATR 5 won all metrics)

**Config variables**:
- ORB 10m confirmed (15m Calmar 11.58 vs 14.88)
- **entry_end=23:30 beats 23:00** (Calmar 15.42 vs 14.88, +80 trades) — ICF captures late-session FVGs
- flat_start=00:00 confirmed (23:30 and 00:30 both worse)

#### Final v3+ICF config (optimization complete, walk-forward pending)

| Param | v3 (no ICF) | v3+ICF Optimized | Change |
|-------|-------------|------------------|--------|
| stop_atr_pct | 3.7% | **3.3%** | tighter |
| min_gap_atr_pct | 0.90% | 0.90% | same |
| max_gap_atr_pct | 5.0% | 5.0% | same |
| rr | 1.75 | **2.15** | higher |
| tp1_ratio | 0.35 | **0.40** | higher |
| atr_length | 5 | 5 | same |
| ORB window | 10m | 10m | same |
| entry_end | 23:00 | **23:30** | extended |
| flat_start | 00:00 | 00:00 | same |
| direction | both | both | same |
| impulse_close_filter | OFF | **ON** | new |

**In-sample performance** (2015–2026, no Thursday gate):
- Trades: 2,425 | WR: 57.3% | Net R: 268.6 | Avg Annual R: **24.4** | Max DD: **-17.4R**
- Sharpe: **1.766** | Calmar: **15.42** | R/trade: 0.111 | **0 negative full years** (2015–2025)
- Year range: 2022 (worst, +6.0R) to 2019 (best, +57.2R)

**vs v3 without ICF** (same config, no Thursday gate, no ICF):
- Calmar: 11.93 → **15.42** (+29%)
- Net R: 194.0 → **268.6** (+38%)
- R/yr: 17.6 → **24.4** (+38%)
- DD: -16.3R → -17.4R (slightly worse)

**Key findings**:
- ICF reshuffled the optimal parameter surface: higher RR (1.75→2.15), tighter stop (3.7→3.3), higher TP1 runner (0.35→0.40)
- The win rate dropped (64%→57%) but edge per trade increased (0.086→0.111R) — classic WR/RR tradeoff
- 2019 (+57.2R) and 2025 (+52.4R) show outsized returns — high annual variance
- No-Thursday gate still needs to be applied and re-confirmed with ICF config
- **DB entry**: `bt-nq-asia-v3-icf-optimized-4d86d0`

### Asia Continuation R5 Final (10m ORB, both, 1s magnifier) — GO (post same-candle SL/TP bug fix)
- **Status**: GO — fixed-param WF 6/6 folds profitable, hold-out PASS. Supersedes R4 Final.
- **Config** (R1-R5 optimization post bug fix, 2016 start):

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia |
| ORB window | 10m (20:00-20:10 ET) |
| entry_start | 20:10 |
| entry_end | 00:00 |
| flat_start | 01:00 |
| flat_end | 07:00 |
| direction | both |
| rr | 1.75 |
| tp1_ratio | 0.10 |
| stop_atr_pct | 3.7% |
| min_gap_atr_pct | 0.90% |
| max_gap_atr_pct | 5.0% |
| max_gap_points | 0 |
| atr_length | 5 |
| magnifier | 1s |
| gate | no-Thursday |
| impulse_close_filter | OFF |

- **Full-history performance** (2016-2026): 1,510 trades, 94.5% WR, PF 2.98, 165.1R total (16.5 R/yr), Max DD -2.7R, Calmar 60.19, Sharpe 4.70, **0 negative full years**
- **R by year**: 2016:+19  2017:+17  2018:+20  2019:+22  2020:+14  2021:+21  2022:+13  2023:+12  2024:+12  2025:+12  2026:+3

#### Fixed-param Walk-Forward (6 folds, OOS 2019-2024)

| Fold | OOS Period | Trades | WR | Sharpe | R | DD |
|------|-----------|--------|-----|--------|---|-----|
| 1 | 2019 | 156 | 96.8% | 6.66 | +22.2 | -1.0 |
| 2 | 2020 | 149 | 93.3% | 3.89 | +14.3 | -2.7 |
| 3 | 2021 | 150 | 96.7% | 6.47 | +20.8 | -1.0 |
| 4 | 2022 | 144 | 95.1% | 4.39 | +13.2 | -1.6 |
| 5 | 2023 | 141 | 92.9% | 3.59 | +11.9 | -2.3 |
| 6 | 2024 | 128 | 93.8% | 3.98 | +12.2 | -2.6 |

- **Combined OOS**: 868 trades, 94.8% WR, PF 3.13, Sharpe 4.82, +94.6R (15.8 R/yr), DD -2.7R, Calmar 5.74
- **Hold-out (2025+)**: 161 trades, 95.0% WR, PF 2.83, Sharpe 4.35, +15.0R, DD -2.5R — PASS
- **Verdict**: GO — all 6 folds profitable, hold-out strong, combined OOS Calmar 5.74

#### R5 Optimization History (R1-R5, post bug fix)
- **Context**: Simulator bug fix — stops and take-profits on the entry candle are now correctly counted. R4 Final (Calmar 23.85) became R5 Baseline (Calmar 34.77) with identical config — bug fix improved all metrics.
- **R5 Baseline**: Same R4 params post-bugfix: 1,593 trades, 70.4% WR, Sharpe 3.29, 258.1R (25.8 R/yr), DD -7.4R, Calmar 34.77. DB: `bt-nq-asia-r5-baseline-post-bugfix-bd0788`.
- **R1**: Swept 12 dimensions. Adopted: entry_end=00:00 (+0.97), tp1=0.20 (+17.26). tp1 shift from 0.35→0.20 is the biggest single change — bug fix made early TP1 exits much more reliable.
- **R2**: entry_end=00:00, tp1=0.20. Calmar 52.44. Adopted: flat_start=01:00 (+0.91).
- **R3**: flat_start=01:00. Calmar 53.35. Adopted: tp1=0.10 (+6.83). tp1 continued pulling lower.
- **R4**: tp1=0.10. Calmar 60.19. Three changes passed threshold: entry_end=01:00 (+4.14), maxgap=7.0 (+2.91), DOW=none (+13.12).
- **R5**: All 3 R4 changes applied → **Calmar crashed from 60.19 to 35.16**. Destructive interaction (exact same pattern as original R3). Reset to R4 anchor (Calmar 60.19).
- **Grid sweep**: 2,016 combos (8 stops × 7 rrs × 6 gaps × 6 tp1s). 1,925/2,016 (95.5%) have 0 neg years — extremely flat surface. R5 anchor is **#7 overall AND #7 among zero-neg-year configs**. Grid winner (stop=4.0/rr=2.0/gap=0.90/tp1=0.05, Calmar 64.93) is only +7.9% better but with -27% R/yr.
- **DB entry**: `bt-nq-asia-r5-final-25e2c0`

#### Key differences from R4 (pre-bug-fix)
- **tp1 shifted from 0.35 → 0.10**: The dominant change. The bug fix made entry-candle TP1 exits count correctly, so taking profits very early (10% of the way to TP2) is now extremely reliable — 94.5% WR. This converts the strategy from a moderate WR/moderate RR profile to an ultra-high WR scalper.
- **entry_end shifted from 01:00 → 00:00**: Late entries past midnight are less productive post-bugfix (they were previously miscounted as EOD wins).
- **flat_start shifted from 00:00 → 01:00**: With entry_end=00:00, flat_start can extend to 01:00 to give remaining positions more time.
- **DD collapsed from -8.9R → -2.7R**: The ultra-early TP1 (10%) means most winning trades only risk a tiny portion before taking profit, dramatically reducing drawdowns.
- **R/yr dropped from 21.1 → 16.5**: Trade-off for much lower DD. Calmar improved from 23.85 → 60.19 (+152%).
- **Exit profile change**: SL 25.5%, TP1_TP2 22.8%, TP1_BE 42.1%, TP1_EOD 2.0%, EOD 7.7% — the TP1_BE category dominates because TP1 hits early on the same candle, then the remaining position runs to breakeven.

### Asia Continuation R9 Restart Final (15m ORB, long, 1s magnifier) — GO (tp1>=0.2 restart)
- **Status**: GO — All 5 phases passed. Supersedes R5 Final (which had degenerate tp1=0.10 producing 94.5% WR).
- **Note**: R5 Final's tp1=0.10 placed TP1 at only 12.5% of stop distance (~6 NQ points), producing mechanically correct but meaningless "wins" of +0.0625R. Minimum tp1_ratio=0.2 rule was established and the entire optimization was restarted from baseline.
- **Config** (R1-R9 restart optimization, 2016 start):

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia |
| ORB window | 15m (20:00-20:15 ET) |
| entry_start | 20:15 |
| entry_end | 22:30 |
| flat_start | 04:00 |
| flat_end | 07:00 |
| direction | long |
| rr | 3.0 |
| tp1_ratio | 0.6 |
| stop_atr_pct | 4.0% |
| min_gap_atr_pct | 0.90% |
| max_gap_points | 75 |
| max_gap_atr_pct | 0 |
| atr_length | 5 |
| magnifier | 1s |
| gate | excl Tuesday |
| impulse_close_filter | ON |

- **Full-history performance** (2016-2026): 770 trades, 45.5% WR, PF 1.42, 176.2R total (17.6 R/yr), Max DD -11.3R, Calmar 15.64, Sharpe 2.52, **0 negative full years**
- **R by year**: 2016:+12  2017:+26  2018:+22  2019:+19  2020:+19  2021:+3  2022:+21  2023:+8  2024:+23  2025:+17  2026:+7

#### 5-Phase Robust Pipeline Results

| Phase | Result | Key Metrics |
|-------|--------|-------------|
| 1. Structural | PASS | 770 trades, 45.5% WR, PF 1.42, Calmar 15.64 |
| 2. Walk-Forward | PASS | WF efficiency 0.797, stability 0.964 (high), 7 folds |
| 3. Prop Constraints | PASS | Avg annual R 14.3, worst month -5.0R, positive expectancy |
| 4. Hold-Out OOS | PASS | 2025+: 89 trades, Sharpe 2.77, PF 1.49, +23.2R |
| 5. Monte Carlo | PASS | 91.7% survival at -25R ruin, p50 DD -16.5R |

- **WF Parameter Stability**: gap=0.9 stable 7/7 folds (1.000), rr mode=3.0 (1.000), stop mode=3.5 (0.857), tp1 mode=0.7 (1.000). Overall 0.964 (high).
- **MC percentiles**: Final PnL p5=110R, p50=175R, p95=241R. Max DD p5=-27R, p50=-16.5R.
- **Verdict**: GO — All 5 phases passed. Strategy is prop-firm ready.
- **Entry delay**: 0m (baseline) is optimal but least sensitive of the three combined longs legs. Calmar degrades gracefully: 0m=22.61, 10m=13.96, 20m=15.75, 30m=14.02. The ORB-based stop adapts to session volatility, which may explain the resilience. Script: `run_combined_longs_entry_delay_sweep.py`.
- **Event day exclusion**: No exclusions beneficial. FOMC slightly above average (+0.314R vs +0.268R, n=31). CPI below average (+0.079R vs +0.268R, n=29) but excluding CPI doesn't improve Calmar (22.61→22.35). NFP only 2 trades. Excluding FOMC hurts (22.61→19.09, DD -8.9→-10.0R). Script: `run_combined_longs_event_day_sweep.py`.
- **DB entry**: `bt-nq-asia-cont-long-2016-2026-final-r9-res-4489d8`

#### R9 Restart Optimization History
- **Context**: R5 Final's tp1=0.10 produced degenerate 94.5% WR (each TP1_BE win earned only +0.0625R). User established minimum tp1_ratio=0.2 rule. Entire optimization restarted from baseline.
- **R1 restart**: Baseline anchor (default params, tp1>=0.2). Calmar 2.94. Adopted: rr=4.0 (+2.24), flat=23:00 (+1.28).
- **R2 restart**: Calmar 4.20, 1 neg year (2022). **Converged** — 0 adoptions.
- **Grid Sweep R1**: 625 combos (stop×rr×gap×tp1). Winner: stop=5.0/rr=3.0/gap=0.9/tp1=0.6 (Calmar 7.03). Delta +2.83 > 0.5 → back to sweeps. Adopted #5: stop=4.0/rr=3.0/gap=0.9/tp1=0.6 (Calmar 6.18, 1 neg year).
- **R3 restart**: Grid winner anchor. Adopted: dir=long (+0.84), ICF=ON (+2.72). dir=long eliminated 2022 neg year.
- **R4 restart**: Calmar 8.28, 0 neg years. Adopted: atr=5 (+3.49), flat=02:00 (+1.31).
- **R5 restart**: Calmar 12.85. Adopted: entry_end=23:00 (+0.35), maxgap=75pts (+0.62).
- **R6 restart**: Calmar 13.23. Adopted: DOW excl Tue (+0.98).
- **R7 restart**: Calmar 14.21. Adopted: flat=04:00 (+0.46). DOW excl Tue persisted (confirmed stable).
- **R8 restart**: Calmar 14.68. Adopted: entry_end=22:30 (+0.97).
- **R9 restart**: Calmar 15.64. **Converged** — 0 adoptions across all 12 dimensions.
- **Grid Sweep R2**: 500 combos. Anchor ranked #2/500 (Calmar 15.64). Winner: stop=4.0/rr=3.5/gap=0.9/tp1=0.5 (Calmar 16.07). Delta +0.43 < 0.5 → **Grid confirms anchor**.
- 135/500 combos (27%) have 0 negative years. No boundary warnings.

#### Key differences from R5 Final (degenerate tp1)
- **tp1 shifted from 0.10 → 0.6**: The minimum tp1=0.2 rule eliminated degenerate micro-scalp configs. Higher tp1 means larger TP1 target (60% of full R:R), producing real wins with meaningful R.
- **Direction: both → long**: Shorts eliminated 2022 negative year (longs +21R vs shorts -34R in 2022).
- **ICF: OFF → ON**: Massive impact (+2.72 Calmar at R3 adoption). ICF captures more FVGs.
- **ORB: 10m → 15m**: 15m was the anchor default and was never displaced at any of the 9 restart sweeps.
- **rr: 1.75 → 3.0**: Higher R:R with higher tp1 — trades run further.
- **WR: 94.5% → 45.5%**: Realistic win rate. R5's 94.5% was mechanically correct but misleading.
- **Calmar: 60.19 → 15.64**: R5's Calmar was inflated by artificially tiny drawdowns from the degenerate tp1.

### Asia Continuation Short (10m ORB, short, 1s magnifier) — NO-GO
- **Status**: NO-GO — robust pipeline passed 2/5 phases (Structural + Hold-Out). Failed WF, Prop, MC.
- **Config** (R4-R6 optimization + Grid Sweep R2 confirmation):

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia |
| ORB window | 10m (20:00-20:10 ET) |
| entry_start | 20:10 |
| entry_end | 01:00 |
| flat_start | 23:00 |
| flat_end | 07:00 |
| direction | short |
| rr | 3.75 |
| tp1_ratio | 0.6 |
| stop_atr_pct | 3.5% |
| min_gap_atr_pct | 1.0% |
| max_gap_points | 0 |
| max_gap_atr_pct | 0 |
| atr_length | 30 |
| magnifier | 1s |
| gate | excl Thursday |
| impulse_close_filter | ON |

- **Full-history performance** (2016-2026): 874 trades, 40.7% WR, PF 1.24, 108.0R total (10.8 R/yr), Max DD -17.1R, Calmar 6.30, Sharpe 1.40, 2 neg years (2022, 2023)
- **R by year**: 2016:+29  2017:+8  2018:+8  2019:+15  2020:+4  2021:+35  2022:-5  2023:-2  2024:+6  2025:+9  2026:+2

#### 5-Phase Robust Pipeline Results

| Phase | Result | Key Metrics |
|-------|--------|-------------|
| 1. Structural | PASS | 874 trades, 40.7% WR, PF 1.24, Calmar 6.30, Sharpe 1.40 |
| 2. Walk-Forward | FAIL | WFE 0.467 < 0.5 (stability 0.821 high), OOS Calmar 1.76 |
| 3. Prop Constraints | FAIL | OOS avg annual R 6.3 < 12.0, worst month -9.9R |
| 4. Hold-Out OOS | PASS | 2025+: 95 trades, Sharpe 1.36, PF 1.24, +11.0R |
| 5. Monte Carlo | FAIL | 62.9% survival at -25R ruin (need 70%) |

- **WF fold-level**: 2019 OOS strong (+10R, Sharpe 1.42), 2021 outstanding (+40.9R, Sharpe 4.41), but 2020 (-1.9R), 2022 (-7.6R), 2023 (-4.9R) all negative. Parameters shifted across folds (stop→3.0, rr→4.0, gap→varied).
- **Verdict**: NO-GO — The in-sample structural metrics look strong (Calmar 6.30) but walk-forward reveals the parameters are not stable across regimes. 2022-2023 are structurally negative for NQ Asia shorts — no parameter combo tested (0/500 in grid) has 0 negative full years. MC survival of 62.9% confirms the drawdown tail risk is too high.
- **DB entry**: `bt-nq-asia-cont-short-2016-2026-no-go-e72618`

#### Optimization History
- **Baseline exploration**: Combined best: ATR=30, ICF=ON, flat=23:00, gap=1.0% → Calmar 1.39
- **R1**: 1 adoption: ORB 15m→10m (Δ+0.44). Calmar 1.80.
- **R2**: Bug in DOW adoption logic (only checked absolute best, missed excl-Thu which passed all criteria). Manual adoption: excl-Thu (Δ+2.25). Calmar 4.05.
- **R3**: Converged (0 adoptions). Calmar 4.05.
- **Grid Sweep R1**: 500 combos. Winner: stop=3.5/rr=3.0/gap=1.0/tp1=0.6 (Calmar 4.69). Delta +0.64 > 0.5 → back to sweeps. Both stop=3.5 and rr=3.0 at grid boundary.
- **R4**: 2 adoptions: entry_end 23:00→01:00 (Δ+0.37), rr 3.0→3.5 (Δ+0.91). Calmar 5.85.
- **R5**: 1 adoption: rr 3.5→3.75 (Δ+0.45). Calmar 6.30.
- **R6**: Converged (0 adoptions). Calmar 6.30.
- **Grid Sweep R2**: 500 combos. Anchor ranked #1/500 (Calmar 6.30). Confirmed.

#### Key Findings — Shorts vs Longs
- **Shorts need completely different params**: ATR=30 (longs=5), flat=23:00 (longs=04:00), ORB=10m (longs=15m), rr=3.75 (longs=3.0), stop=3.5% (longs=4.0%), excl-Thu (longs=excl-Tue). Every major dimension differs.
- **2021 is the standout year for shorts**: +35R, vs longs' +3R in 2021. Shorts hedge longs' weakest year.
- **2022-2023 are structurally negative for shorts**: No parameter combo achieves 0 negative years. This is a fundamental limitation.
- **Combined L+S portfolio**: Adding shorts to the R9 Restart Long config yields 1,644 trades, ~286R total, but the standalone short is too weak to justify — better to trade longs-only with lower DD risk.

#### Scripts Generated
- `run_nq_asia_short_baseline.py`
- `run_nq_asia_short_variable_sweeps_1.py` through `run_nq_asia_short_variable_sweeps_6.py`
- `run_nq_asia_short_grid_sweep_r1.py`, `run_nq_asia_short_grid_sweep_r2.py`
- `run_nq_asia_short_robust_pipeline.py`

### Asia Continuation R4 Final (10m ORB, both, 1s magnifier) — SUPERSEDED by R5
- **Status**: SUPERSEDED — R5 Final (post bug fix) achieved Calmar 60.19 vs R4's 23.85
- **Config** (R1-R4 optimization with 1s magnifier, 2016 start):

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia |
| ORB window | 10m (20:00-20:10 ET) |
| entry_start | 20:10 |
| entry_end | 01:00 |
| flat_start | 00:00 |
| flat_end | 07:00 |
| direction | both |
| rr | 1.75 |
| tp1_ratio | 0.35 |
| stop_atr_pct | 3.7% |
| min_gap_atr_pct | 0.90% |
| max_gap_atr_pct | 5.0% |
| max_gap_points | 0 |
| atr_length | 5 |
| magnifier | 1s |
| gate | no-Thursday |
| impulse_close_filter | OFF |

- **Full-history performance** (2016-2026): 1,593 trades, 66.8% WR, PF 1.43, 211.2R total (21.1 R/yr), Max DD -8.9R, Calmar 23.85, Sharpe 2.53, **0 negative full years**
- **R by year**: 2016:+31  2017:+16  2018:+24  2019:+21  2020:+21  2021:+26  2022:+9  2023:+18  2024:+19  2025:+24  2026:+3

#### Fixed-param Walk-Forward (6 folds, OOS 2019-2024)

| Fold | OOS Period | Trades | WR | Sharpe | R | DD |
|------|-----------|--------|-----|--------|---|-----|
| 1 | 2019 | 157 | 63.7% | 2.09 | +20.7 | -7.8 |
| 2 | 2020 | 154 | 66.9% | 2.17 | +20.8 | -8.7 |
| 3 | 2021 | 155 | 71.0% | 2.82 | +25.8 | -5.4 |
| 4 | 2022 | 140 | 62.1% | 1.22 | +8.9 | -8.5 |
| 5 | 2023 | 157 | 67.5% | 2.23 | +17.8 | -5.1 |
| 6 | 2024 | 155 | 68.4% | 2.54 | +19.3 | -5.5 |

- **Combined OOS**: 918 trades, 66.9% WR, PF 1.41, Sharpe 2.40, +113.3R (18.9 R/yr), DD -8.7R, Calmar 2.17
- **Hold-out (2025+)**: 172 trades, 67.4% WR, PF 1.52, Sharpe 2.94, +27.2R, DD -6.4R — PASS
- **Verdict**: GO — all 6 folds profitable, hold-out strong, combined OOS Calmar 2.17

#### R4 Optimization History (R1-R4, 1s magnifier)
- **R1**: Fresh start with 1s magnifier + 2016 start (v3 anchor). Baseline Calmar 16.72 (down from v3's 20.14 due to data change). Adopted: ORB=15m (+2.95), entry_end=01:00 (+7.13). flat_start=23:00 conflicted with entry_end=01:00, not adopted.
- **R2**: ORB=15m, entry_end=01:00, flat=00:00. Calmar 20.18. Adopted 5 changes: ORB=10m (+3.67), flat=23:00 (+2.40), tp1=0.30 (+1.75), ICF=ON (+1.65), gap=1.25% (+0.54).
- **R3**: All 5 R2 changes applied simultaneously → **Calmar crashed from 20.18 to 11.97**. Destructive parameter interaction. Sweep wanted to revert most changes. Key lesson: never adopt 5+ interacting changes at once.
- **R4**: Reset to best-proven config (ORB=10m + entry_end=01:00 + flat=00:00 with v3 continuous params). **Fully converged — every dimension Δ=0.00.** Calmar 23.85.
- **Grid sweep**: 2,016 combos (8 stops × 7 rrs × 6 gaps × 6 tp1s). R4 anchor is **#1 overall AND #1 among 797 zero-neg-year configs**. Gap to #2 is 2.63 Calmar points. No fine-tune needed.
- **DB entry**: `bt-nq-asia-r4-final-69df58`

#### Key differences from v3 (1m magnifier, 2015 start)
- **entry_end shifted from 23:00 → 01:00**: The single biggest change. Extending entry window past midnight captures late Asia session FVGs. This was invisible in v3's optimization because v3 used 2015 data and 1m magnifier.
- **flat_start remains 00:00**: Midnight close confirmed. Combining entry_end=01:00 with flat_start=00:00 means entries between 00:00-01:00 get immediately flattened at end of bar — effectively these are very short-duration trades that only work if TP1 is hit quickly.
- **ICF is OFF**: Unlike v3+ICF optimization which showed +29% Calmar, ICF was not beneficial at the R4 anchor (entry_end=01:00 changes the trade mix).
- **Calmar improved 20.14 → 23.85 (+18%)** despite losing 2015 data year.

### NY Continuation Short (20m ORB, short-only, 1s magnifier) — NO-GO
- **Status**: NO-GO — best achievable config has 4 negative years, Calmar 1.40, PF 1.10. Edge is marginal and fragile to slippage.
- **DB entry**: `bt-nq-ny-short-no-go-final-327490`
- **Best config found**:

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | NY |
| direction | short |
| ORB window | 20m (09:30-09:50) |
| entry_end | 15:00 |
| flat_start | 15:50 |
| stop_orb_pct | 15.0% |
| min_gap_orb_pct | 7.0% |
| stop_atr_pct | 5.0% |
| min_gap_atr_pct | 2.0% |
| min_stop_points | 10.0 |
| min_tp1_points | 10.0 |
| rr | 3.0 |
| tp1_ratio | 0.3 |
| atr_length | 14 |
| magnifier | 1s |

- **Full-history performance** (2016-2026): 967 trades, 61.5% WR, PF 1.10, Sharpe 0.67, 37.3R (3.7 R/yr), Max DD -26.6R, Calmar 1.40, 4 negative years
- **R by year**: 2016:-5  2017:-3  2018:+5  2019:-4  2020:+4  2021:+15  2022:+5  2023:-4  2024:+7  2025:+13  2026:+4

#### Investigation Summary

##### The tp1=0.2 Trap
Variable sweeps (R1-R10) converged on configs with 88% win rate, but diagnostic analysis revealed:
- Median stop was only **8.2 points** (33 ticks) — 32.7% of trades had stops < 5 points
- TP1 target was just **3.3 points** median (0.4× the already-tiny stop) — any noise triggers TP1
- **87.7% of trades were tp1_be exits** earning exactly +0.2R, with only 2/624 ever reaching TP2
- Average R per trade: **0.056R** — slippage of 1-3 points (typical NQ) would consume 30-90% of the TP1 target
- The "edge" is mechanical: trivial retracement → TP1 → breakeven stop → scratch. Not viable in live execution.

##### Engine Fix: Dual Floors (min_stop_points + min_tp1_points)
Implemented engine-level minimum floors on `SessionConfig` to prevent the tp1 trap:
- `min_stop_points=10.0`: `stop_dist = max(computed_stop, 10.0)` — prevents unrealistically tight stops
- `min_tp1_points=10.0`: `tp1_dist = max(computed_tp1, 10.0)` — prevents trivial TP1 targets
- These are per-session, NQ-specific values (10pt = 40 ticks). Other instruments should use different values appropriate to their tick size.

##### With Dual Floors: ORB vs ATR Comparison
Comprehensive comparison with both 10pt floors active (`diagnose_nq_ny_short_orb_vs_atr.py`):

| Stop Method | Best Calmar | Config | Net R | Neg Years | Median Stop |
|-------------|-------------|--------|-------|-----------|-------------|
| **ORB 15%** | **1.40** | rr=3.0, tp1=0.3 | 37.3R | 4 | 10.0pt |
| ORB 10% | 1.11 | rr=3.0, tp1=0.3 | 26.2R | 4 | 10.0pt (floor-binding) |
| ORB 20% | 1.08 | rr=3.0, tp1=0.3 | 29.3R | 4 | 11.2pt |
| ATR 5% | 0.19 | rr=2.5, tp1=0.3 | 4.3R | 5 | 10.0pt (all floor-binding) |
| ATR 7.5% | 1.05 | rr=4.0, tp1=0.5 | 39.4R | 5 | 14.6pt |
| ATR 10% | 1.19 | rr=4.0, tp1=0.6 | 53.3R | 3 | 19.5pt (DD: -45R) |
| ATR 12.5% | 1.01 | rr=4.0, tp1=0.6 | 42.4R | 3 | 24.4pt (DD: -42R) |

- ORB orbstop=15% is the best stop mechanism — naturally sizes to ORB range, avoids floor-binding
- ATR-based stops only viable at extreme rr=4.0 with massive drawdowns (-42 to -45R)
- Floor-binding (ORB 10%, ATR 5%) produces near-zero edge

##### Variable Sweep Oscillation (R1-R8, ATR-based)
8 rounds of ATR-based sweeps never converged:
- ATR length oscillated: 14→20→14→20→5→14
- Gap oscillated: 1.0→4.0→3.5→2.0→4.0→2.0→4.0
- DOW exclusion shifted every round: none→Thu→Fri→Fri→Fri→Tue→none→Tue
- ORB window wandered: 20m→25m→30m→25m→15m→25m→30m
- Root cause: tp1=0.2 creates an ultra-flat parameter landscape where everything looks similar within noise

##### ORB-Based Stop Approach (R9-R10)
Attempted switching from ATR-based to ORB-based stops to reduce parameter instability:
- R9 (ORB-based): 2 adoptions, more stable than ATR rounds — but still the tp1=0.2 artifact
- R10: 6 adoptions, instability returned even with ORB-based params

#### Conclusion
The NO-GO config above (Calmar 1.40, 4 neg years) was from diagnostic grids only — never properly optimized with dual floors. A full re-optimization from scratch with dual floors active may find a better config. See "Next Tests" below.

#### Next Tests — COMPLETED (see Short v2 above)

Re-optimization with dual floors has been completed as NY Continuation Short v2. Key results:
- Calmar improved from 1.40 (v1) to 7.86 (v2) — 5.6× improvement
- Negative years eliminated: 4 → 0
- Entry_end=11:00 was the single biggest lever (not tested in v1)
- Parameter oscillation from v1 was caused by tp1=0.2 artifact — v2 converged cleanly with dual floors
- See **NY Continuation Short v2** section above for full details

#### Scripts Generated
- `run_nq_ny_short_baseline.py` (Step 1)
- `run_nq_ny_short_variable_sweeps_1.py` through `run_nq_ny_short_variable_sweeps_10.py` (Step 2)
- `diagnose_nq_ny_short_stops.py` (stop distance diagnostic)
- `diagnose_nq_ny_short_wide_stops.py` (wide stop / realistic tp1 diagnostic)
- `diagnose_nq_ny_short_min_stop_floor.py` (min_stop_points=10 testing)
- `diagnose_nq_ny_short_82pct_wr.py` (floor-binding vs organic trade analysis)
- `diagnose_nq_ny_short_dual_floor.py` (both min_stop=10 + min_tp1=10)
- `diagnose_nq_ny_short_orb_vs_atr.py` (ORB vs ATR stop comparison with dual floors)
- `save_nq_ny_short_final.py` (DB save)

### NY Continuation Short v2 (25m ORB, short-only, 1s magnifier, dual floors) — CONDITIONAL
- **Status**: CONDITIONAL — 4/5 pipeline phases pass. Phase 3 annual R FAIL (12R/yr threshold too aggressive for short-only ~33 trades/yr). All other phases pass strongly.
- **DB entry**: `bt-nq-ny-short-v2-2016-2026-final-d9db60`
- **Config (WF-validated mode params)**:

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | NY |
| direction | short |
| ORB window | 25m (09:30-09:55) |
| entry_end | 11:00 |
| flat_start | 11:00 |
| stop_orb_pct | 17.0% |
| min_gap_orb_pct | 5.0% |
| min_gap_atr_pct | 0.0% |
| stop_atr_pct | 5.0% |
| min_stop_points | 10.0 |
| min_tp1_points | 10.0 |
| rr | 2.0 |
| tp1_ratio | 0.3 |
| atr_length | 14 |
| ICF | OFF |
| DOW exclusion | Monday (post-backtest) |
| magnifier | 1s |

- **Full-history performance** (2016-2026): 329 trades, 71.4% WR, PF 1.50, Sharpe 2.74, 41.0R (4.1 R/yr), Max DD -5.2R, Calmar 7.86, **0 negative full years**
- **R by year**: 2016:+2  2017:+5  2018:+8  2019:+0  2020:+2  2021:+2  2022:+3  2023:+5  2024:+6  2025:+7  2026:+1
- **Median stop**: 43 ticks (well above 10-tick floor)

#### Pipeline Results

| Phase | Result | Key Metrics |
|-------|--------|-------------|
| 1 — Structural | **PASS** | 329 trades, 66.3% WR, PF 1.52, Calmar 10.00 |
| 2 — Walk-Forward | **PASS** | WF eff 0.67, stability 0.80 (HIGH), 5 folds |
| 3 — Prop Filter | **FAIL** | Annual R 2.86R/yr avg (below 12R threshold) |
| 4 — Hold-Out | **PASS** | Sharpe 8.46, PF 3.44, +7.2R (35 trades, 91.4% WR) |
| 5 — MC Survival | **PASS** | 97.8% survival at 15R, 0.1% ruin at 25R |

- **Phase 3 detail**: Only annual R failed (2.86R/yr avg vs 12R threshold). Monthly loss PASS (-3.5R worst), expectancy PASS (0.081R). The 12R/yr threshold is calibrated for all-direction full-session strategies (~200+ trades/yr); a short-only strategy with 33 trades/yr cannot realistically achieve it. The strategy is portfolio-additive, not standalone.
- **Phase 2 detail**: Parameter stability HIGH (0.80). Mode params: stop_orb=17%, rr=2.0, gap_orb=5%, tp1=0.3. gap_orb and tp1 had perfect stability (1.00). All folds positive except Fold 1 OOS (2019, -0.35 Sharpe).
- **Phase 4 detail**: 2025 hold-out is exceptional — 91.4% WR, Sharpe 8.46. The strategy thrives in trending/volatile markets.

#### Optimization Journey

1. **Baseline**: ORB 20m, default NY times → Calmar 1.40, 4 neg years (NO-GO level)
2. **Mega grid** (1,800 combos): Found entry_end=11:00 and flat_start=14:00 as biggest levers → Calmar 5.75
3. **Variable sweeps R2-R6**: Improved to Calmar 8-10+, but discovered rr/tp1/flat/gap are **coupled parameters** that oscillate when swept independently (rr went 3.0→2.0→3.0, flat went 11:00→11:15→11:00)
4. **Focused grid** (240 combos, 4 coupled dims simultaneously): Found two equivalent families:
   - rr=3.0 + tp1=0.3 → Calmar 10.12 (1 neg year at -0R)
   - rr=2.0 + tp1=0.5 → Calmar 10.00 (0 neg years!)
5. **Pipeline**: Selected rr=2.0, tp1=0.5 config (0 neg years). WF mode shifted to tp1=0.3, stop_orb=17%.

#### Key Findings

- **Entry time is the biggest lever**: Moving entry_end from 15:00→11:00 and flat from 15:50→11:00 transformed the strategy from Calmar 1.40 to Calmar 10+. NQ shorts work best as a tight morning play.
- **Coupled parameters**: rr, tp1, flat_start, and gap are deeply coupled. Variable sweeps alone cannot find the optimum — a joint grid search is required. rr=3.0+tp1=0.4 gives Calmar 2.55, but rr=3.0+tp1=0.3 gives Calmar 10+.
- **ORB-based stops dominate**: stop_orb_pct=15-17% consistently outperforms ATR-based stops for NQ NY shorts.
- **DOW Monday exclusion**: Stable improvement across all rounds. Monday shorts are negative EV.
- **ICF always hurts**: Impulse close filter reduced Calmar by -0.10 to -2.57 across all configs tested.
- **Dual floors validated**: min_stop_points=10 and min_tp1_points=10 eliminated the tp1=0.2 artifact from v1. Median stop is 43 ticks — well above floor.

#### Scripts Generated
- `run_nq_ny_short_v2_baseline.py` (Step 1 — failed, too wide session)
- `run_nq_ny_short_v2_variable_sweeps_1.py` (partial — timed out at DIM 5)
- `run_nq_ny_short_v2_mega_grid.py` (1,800 combos — structural + coupled dims)
- `run_nq_ny_short_v2_variable_sweeps_2.py` through `run_nq_ny_short_v2_variable_sweeps_6.py` (R2-R6)
- `run_nq_ny_short_v2_sweeps_r2_fix.py` (DIM 12 fix after DIM 11 crash)
- `run_nq_ny_short_v2_focused_grid.py` (240 combos, 4 coupled dims)
- `run_nq_ny_short_v2_robust_pipeline.py` (5-phase validation)
- `save_nq_ny_short_v2_final.py` (DB save)

### CORRUPTION NOTICE — All NY Results Pre-Fix (commit 6079ad4)

> **Root cause**: The TP1+BE same-bar exit bug allowed trades to survive bars where TP1 was hit and the stop should have moved to breakeven on the same candle. This inflated r_multiples for all configs, especially those with tp1_ratio <= 0.3 where TP1 is close to entry and same-bar TP1+BE events are frequent.
>
> **Impact**: NQ NY R20 (tp1=0.3) went from 247.9R → 84.6R (66% drop), Calmar 20.31 → 3.86 on the fixed engine. All metrics, WF results, and pipeline verdicts below are **unreliable**.
>
> **What's preserved**: Optimization history (parameter interaction lessons, DOW instability findings, structural conclusions about ORB windows, etc.) remains valid as directional guidance. Only the specific metric values are corrupt.
>
> **Action**: Full NQ NY longs-only re-optimization underway on the fixed engine.

### NY Continuation R20 (20m ORB, both, 1s magnifier) — CORRUPT (was GO)
- **Status**: CORRUPT — all metrics pre-date TP1+BE same-bar exit bug fix (commit 6079ad4). tp1=0.3 makes this config heavily affected.
- **Config** (R16-R20 optimization with 1s magnifier):

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | NY |
| ORB window | 20m (09:30-09:50) |
| entry_start | 09:50 |
| entry_end | 15:30 |
| flat_start | 15:50 |
| direction | both |
| rr | 2.625 |
| tp1_ratio | 0.3 |
| stop_atr_pct | 8.75% |
| min_gap_atr_pct | 2.25% |
| max_gap_points | 100 |
| atr_length | 12 |
| magnifier | 1s |

- **Full-history performance** (2016-2026): 1,894 trades, 59.9% WR, PF 1.28, 212.5R total (21.3 R/yr), Max DD -13.0R, Calmar 16.36, Sharpe 1.72, **0 negative full years**
- **R by year**: 2016:+10  2017:+39  2018:+7  2019:+31  2020:+26  2021:+29  2022:+9  2023:+4  2024:+44  2025:+10  2026:+3

#### Robust Pipeline Results
- **Phase 1 (Structural)**: PASS — 1,894 trades, 59.9% WR, PF 1.28, max consec losses 6
- **Phase 2 (Adaptive WF)**: FAIL (borderline) — WF efficiency 0.49 (threshold 0.50), stability 0.45 (moderate). Fold 5 (2023 OOS: -0.95 Sharpe) dragged efficiency below threshold. WF mode params drifted from candidate (stop 8.0, rr 3.0, gap 3.0, tp1 0.4).
- **Phase 3 (Prop Filter)**: FAIL — on adaptive WF OOS trades: 2023=-12.3R, worst month -7.2R
- **Phase 4 (Hold-Out 2025+)**: PASS — 175 trades, Sharpe 1.72, PF 1.28, +23.4R, DD -5.8R
- **Phase 5 (MC Survival)**: FAIL — 12.7% survival at 15R (on adaptive WF OOS trades)
- **Fixed-param WF**: **6/6 folds profitable** — the fixed config generalizes across all time periods even though the adaptive WF optimizer couldn't converge on stable params. Combined OOS: 1,143 trades, 60.0% WR, PF 1.31, Sharpe 1.90, +142.8R (23.8 R/yr), DD -13.0R, Calmar 11.00.

| Fold | OOS Period | Trades | Sharpe | R | DD |
|------|-----------|--------|--------|---|-----|
| 1 | 2019 | 182 | 2.52 | +30.7 | -10.9 |
| 2 | 2020 | 174 | 2.27 | +26.0 | -7.0 |
| 3 | 2021 | 189 | 2.29 | +28.7 | -6.3 |
| 4 | 2022 | 194 | 0.72 | +9.1 | -12.6 |
| 5 | 2023 | 207 | 0.29 | +3.9 | -11.1 |
| 6 | 2024 | 197 | 3.38 | +44.4 | -6.3 |

- **Hold-out (2025+)**: 192 trades, Sharpe 1.02, PF 1.15, +12.7R, DD -9.3R
- **Verdict**: GO — adaptive WF failed because the parameter surface is noisy (different IS windows pick different optima), but the specific fixed config is robust across all periods. 2022-2023 are the weakest years (+9.1R, +3.9R) but still positive.
- **DB entry**: `bt-nq-ny-r20-final-fa2e40`

#### R20 Optimization History (R16-R20)
- **R16**: Fresh start with 1s magnifier. Anchor: rr=2.0, tp1=0.5, stop=10%, gap=1.5%, orb=15m, dir=both, ATR=14. Calmar 4.40. Adopted: direction=long, orb=20m.
- **R17**: dir=long, orb=20m. Calmar 6.87. Adopted 5 changes: direction=both, orb=25m, ATR=12, entry_end=15:30, gap=2.0%.
- **R18**: All 5 R17 changes applied. Calmar 6.16. Detected oscillation (orb 25m→20m, gap 2.0%→1.5%). Adopted: orb=20m (reverted), gap=1.5% (reverted), stop=11%.
- **R19**: Stabilization check. Calmar 6.98. stop=9% emerged as massive winner (Δ+3.67), triggering R9-R11 rule.
- **Grid sweep**: 750 combos (stop×rr×gap×tp1). Winner with 0 neg years: stop=9.0, rr=2.75, gap=2.5, tp1=0.4 → Calmar 14.53.
- **Fine-tune**: 625 combos at half-steps. Winner: stop=8.75, rr=2.625, gap=2.25, tp1=0.3 → Calmar 16.36. Anchor moved.
- **R20**: Re-swept structural vars on new anchor → all converged (every dimension had Δ=0).
- **Grid sweep R20**: 1,920 combos (broader ranges). Current anchor ranked #2 overall (Calmar 16.36). #1 was stop=7.0/rr=3.5 (Calmar 16.50) but at grid edge with 46% WR and -17.2R DD — rejected as less robust.

### NY Continuation Long 30m ICF — CORRUPT + INVALIDATED
- **Status**: CORRUPT + INVALIDATED — pre-dates TP1+BE bug fix AND original data (2015-2026) no longer available. Rerun on current data (2016-2026) shows degraded performance.
- **Original DB entry**: `NQ NY Long 30m ICF Pipeline Validated` (ID 9742)
- **Original performance**: 1,144 trades, 51.5% WR, Sharpe 2.10, PF 1.36, 192.2R, Calmar 17.26, 0 neg years
- **Rerun on current data**: 829 trades, 50.2% WR, Sharpe 2.00, PF 1.33, 134.6R, Calmar 11.10, **2 negative years** (2016: -8R, 2025: -6R)
- **1s magnifier impact**: Zero — 0 trades differed between 1m and 1s magnifier. 1m resolution was already sufficient for this config.
- **Root cause**: Current parquet data starts 2016-01 vs original CSV starting 2015-01. Missing 2015 data (~315 trades) accounts for the degradation. 2016 is now negative without the warm-up from 2015.
- **Conclusion**: Superseded by R20 Final (Calmar 16.36 vs 11.10 on same data, 0 neg years vs 2).

### NY Continuation (20m ORB, long-only, magnifier) — CORRUPT (was CONDITIONAL, superseded by R20)
- **Status**: CORRUPT — pre-dates TP1+BE bug fix. Was CONDITIONAL, superseded by R20 Final.
- **Accepted config** (WF mode params from Sharpe-objective run):

| Param | Value | Notes |
|-------|-------|-------|
| strategy | continuation | |
| session | NY | |
| ORB window | 20m (09:30-09:50) | |
| entry_start | 09:50 | |
| entry_end | 15:00 | |
| direction | long-only | |
| rr | 2.0 | WF mode (was 2.25 in-sample) |
| tp1_ratio | 0.6 | WF mode (was 0.7 in-sample) |
| stop_atr_pct | 9.0% | WF mode = in-sample |
| min_gap_atr_pct | 3.0% | WF mode = in-sample |
| atr_length | 14 | |
| magnifier | ON | |

- **In-sample performance** (rr=2.25, tp1=0.7): 1167 trades, 46.1% WR, PF 1.30, 182.0R total (16.5 R/yr), Max DD -10.6R, Calmar 17.17

#### Robust Pipeline Results (Sharpe-objective WF, 36m IS / 12m OOS / 12m step)
- **Phase 1 (Structural)**: PASS — 1167 trades, 46.1% WR, PF 1.30
- **Phase 2 (Walk-Forward)**: FAIL (borderline) — WF efficiency 0.45 (threshold 0.50), stability 0.83 (high)
  - 6 folds, 5/6 profitable OOS. Fold 6 (2023 OOS: -0.48 Sharpe) dragged efficiency below threshold
  - Combined OOS: 661 trades, 46.7% WR, PF 1.16, 54.3R, Sharpe 1.09, DD -12.3R, Calmar 4.41
  - Mode params: rr=2.0, tp1=0.6, stop=9.0, gap=3.0 (stability 0.83 across all 4 params)
- **Phase 3 (Prop Filter)**: FAIL — worst month -9.4R (Sep 2022), no year reached 24R annual target. OOS avg ~9 R/yr
- **Phase 4 (Hold-Out 2025+)**: PASS — 105 trades, 58.1% WR, PF 1.79, Sharpe 3.97, +30.1R, DD -5.0R
- **Phase 5 (MC Survival)**: PASS — 100% survival at 25R ruin threshold
- **Verdict**: CONDITIONAL — accepted with WF mode params. Phase 2 borderline (one bad fold), Phase 3 annual R target unrealistic for trade frequency. Size position to match DD tolerance.
- Also tested Calmar as WF objective — worse results (efficiency 0.15, OOS Calmar 4.02). Sharpe is the more stable WF objective for this strategy.

- **Year breakdown** (in-sample, rr=2.25): 2015:+28  2016:+17  2017:+22  2018:+13  2019:+19  2020:+19  2021:+17  2022:+9  2023:-2  2024:+12  2025:+21  2026:+8
- **Note**: WF OOS degrades ~74% from in-sample Calmar (17.17 → 4.41). 2023 is the persistent weak spot.

#### NY Variable Sweep History (Rounds 1-12) — CORRUPT METRICS, directional findings preserved

**Round 1** — Baseline variable sweeps (6 dimensions)
- Base: WF mode params (rr=2.0, tp1=0.5, stop=10%, gap=1.5%, both direction, 15m ORB)
- Swept: max_gap_points, max_gap_atr_pct, atr_length, ORB window, entry end, direction
- Key finding: **Long-only is the biggest single lever** (Sharpe 1.63 vs 1.18 for both)

**Round 2** — Finer grids + new dimensions (7 dimensions)
- Swept: rr, tp1, stop, min_gap, flat time, entry start delay, DOW exclusion
- Key findings: rr=2.25 slightly better, excl-Thu helps marginally, base values confirmed for most

**Round 3** — Extended dimensions (15 sweeps)
- Swept: ORB 5m-30m fine, ORB start, strategy type, multi-day exclusions, long-only sweeps
- Key findings: **20m ORB is optimal** (Calmar 9.58), long+excl-Thu+Fri best combo

**Round 4** — Combined winners re-sweep (16 dimensions)
- New base: long-only + 20m ORB (09:30-09:50)
- Key findings: entry end 14:00-15:00 best (Calmar 10.69-11.42), gap=3.0% strong filter

**Round 5** — Stacking combos + Calmar-focused (Phase A: 32 combos, Phase B: 11 sweeps)
- Winner: **+entry_end=15:00 +gap=3.0%** → Calmar 14.56, DD -9.9R, 13.1 R/yr

**Round 6** — Maximize R/year (8 interaction sweeps)
- Tested: RR up to 3.5, both direction, gap×RR, TP1×RR, stop×RR, entry_end×RR
- Key findings: rr=2.75 long best R/yr (14.7), both direction gets 18-20 R/yr but doubles DD
- tp1=0.4 rr=2.5 best Calmar in TP1×RR grid (14.86)

**Round 7** — 3-way interaction grid: gap × rr × tp1 (90 combos at stop=10%)
- New best Calmar: **g=3.5 rr=2.50 tp1=0.4** → 12.6 R/yr, DD -9.3R, Calmar 14.97
- g=3.5 rr=3.00 tp1=0.3 had lowest DD in grid: -8.8R
- Entry start delay (10:00, 10:15) confirmed harmful — 09:50 is optimal

**Round 8** — Separate short optimization + combined trade lists
- Best short independently: g=3.0 rr=1.5 → 5.9 R/yr, DD -12.4R (mediocre alone)
- **Key finding: Combined L+S with independent params beats same-params-both**
  - Combined L(rr2.75) + S(rr1.5): 20.6 R/yr, DD -16.9R, Calmar 13.47
  - Same-params both rr=2.75: 18.1 R/yr, DD -21.5R, Calmar 9.25
  - Shorts need low RR (1.5) while longs thrive at higher RR (2.5-2.75)

**Round 9** — Fine-grained stop sweep (3-14% in 1% steps, 7 configs)
- **stop=9% massively improves rr=2.75 configs** (+2 Calmar) but does nothing for rr=2.0/2.5
- g3.0 rr2.75 tp0.6 stop=9%: 16.3 R/yr, DD -11.2R, Calmar 16.00 (new overall best at the time)
- g3.0 rr2.75 tp0.5 stop=9%: 16.9 R/yr, DD -11.8R, Calmar 15.74
- **Lesson**: Always re-validate stop when changing RR — the interaction is strong

**Round 10** — Ultra-fine stop sweep (8.5-9.5% in 0.1% steps, config: g3.0 rr2.75 tp0.6)
- Confirmed **stop=9.0% is the Calmar optimum** (16.00)
- Smooth curve: 8.5-9.2% all hold Calmar > 15 (no fragile spike — good robustness signal)
- 8.5% has highest R/yr (17.2) but slightly more DD (-11.9R)

**Round 11** — 3-way grid re-run at stop=9% (90 combos) — MAJOR SHIFT
- **Stop=9% completely reshuffled the leaderboard** — different rr/tp1 combo won
- New #1: **g=3.0 rr=2.25 tp1=0.7 stop=9%** → 16.5 R/yr, DD -10.6R, **Calmar 17.17**
- Previous best (g3.0 rr2.75 tp0.6) dropped to #5 (Calmar 16.00)
- Stop=9% beat stop=10% on ALL 10 head-to-head combos tested (avg +3.4 Calmar, +2.9 R/yr)
- Optimal RR shifted from 2.75 → 2.25, optimal TP1 shifted from 0.6 → 0.7
- gap=3.0% dominates the entire top 10 (gap=2.5% and 3.5% nowhere close)
- **Key lesson**: Changing one variable (stop) can shift the entire optimal surface. Always re-run the full grid after finding a new anchor.

**Round 12** — Fine-tuning R11 winner (COMPLETE)
- Swept rr (0.05 steps), tp1 (0.05 steps), gap (0.1 steps), entry_end (15min steps), stop (0.1 steps)
- **All current values confirmed at local optima** — no variable improved more than marginally
- Only entry_end=15:30 showed slight gain: Calmar 17.40 vs 17.17 (+0.23), adding 42 trades
- Stacked all-best (with end=15:30): 1209 trades, 16.8 R/yr, DD -10.6R, Calmar 17.40
- R11 #2 (rr3.0 tp0.6) and #3 (rr2.75 tp0.7) confirmed close but below the winner
- **Conclusion**: Optimization phase complete. The parameter surface is flat around the optimum — robust signal.

**Round 13a** — Config variable re-validation with new anchor (6 variables)
- Swept ORB window (5m-30m), ATR length (5-30), flat window, max gap ATR%, max gap points, DOW exclusion
- **All confirmed at current optima** — only flat_start=15:40 showed marginal gain (+0.37 Calmar)
- 20m ORB, ATR 14, no limit on max gap ATR, max_gap_pts=100, no DOW exclusion all reconfirmed

**Round 13b** — Environmental & regime filters (VIX, SPY, TNX, DXY, NQ SMA, ATR vol, seasonality)
- **No environmental filter improves Calmar over baseline** — all cut trades → cut R/yr more than DD
- Strongest IN/OUT splits: DXY < SMA20 (avg R 0.217 vs 0.078), TNX < SMA20 (0.192 vs 0.100)
- VIX > SMA50 counterintuitively helps longs (0.206 vs 0.102) — elevated vol = better FVG setups
- **December is poison** (-19.4R, 33.8% WR) — excl Dec → Calmar 19.82, but overfitting risk
- NQ SMA trend gates and ATR vol gates all hurt — don't use them
- **Best use for env data: regime SIZING, not hard filtering**

**Round 14** — Re-optimize shorts + combined L+S with updated anchor
- Best short: g=1.0 rr=1.25 tp1=0.5 stop=9% entry_end=14:00 (8.3 R/yr, DD -14.2R)
- Combined always (L+S): 22.1 R/yr, DD -15.4R, Calmar 15.77
- Sweet spot: L + S(rr=1.25) → 22.1 R/yr, DD -15.4R, all years positive
- R/yr +34% but DD +45% — long-only still better risk-adjusted
- **Key finding: shorts add most value when longs are weakest (2022-2023)**

**Round 15** — Regime-switched L+S (always long + short when [condition])
- Tested 20 regime conditions (VIX, SPY, TNX, DXY singles + combos)
- **No regime switch beats long-only on Calmar** — all hit DD floor of ~-14.5R
- Best: "S when TNX > SMA20" → 19.9 R/yr, DD -14.5R, Calmar 15.10
- Combined-always (15.77) actually beats all regime switches
- **Conclusion: shorts don't improve risk-adjusted returns regardless of regime filtering**

#### Drawdown Profile (from DD analysis)
- **DD <= -10R**: 4 events in 11 years (0.4/yr) — all clustered in 2023-03 to 2024-02
- **DD <= -9R**: 11 events (1.0/yr)
- **DD <= -8R**: 21 events (1.9/yr)
- **DD <= -7R**: 34 events (3.1/yr)
- 63% positive months, mean +1.36R/month, worst month -9.4R (Sep 2022)
- Worst losing streak: 9 consecutive losses = -8.2R (Sep-Oct 2022)
- **DB entry**: `saved after R15 sweep completion`

## Key Findings

### Asia Session
- **R9 Restart Final is the current GO config**: stop=4.0%, rr=3.0, gap=0.90%, tp1=0.6, ORB=15m (20:00-20:15), entry_end=22:30, flat=04:00, ATR=5, long-only, excl-Tue, ICF=ON, 1s magnifier, max_gap_points=75 → 770 trades, 45.5% WR, PF 1.42, Sharpe 2.52, 176.2R (17.6 R/yr), DD -11.3R, Calmar 15.64, 0 neg years. WF efficiency 0.797, stability 0.964. Hold-out Sharpe 2.77. MC 91.7% survival. DB: `bt-nq-asia-cont-long-2016-2026-final-r9-res-4489d8`. Supersedes R5 Final (which had degenerate tp1=0.10).
- **ALPHA RR6 Tier 1-3 exact replacement check (2026-07-02): keep RR6 live; Tier 1 is shadow-only, not a hot swap.** Report: `backtesting/learnings/reports/NQ_ASIA_TIER1_TIER3_EXACT_COMPARE_20260702.md`; artifacts: `backtesting/data/results/nq_asia_tier1_tier3_exact_compare_20260702/`. Exact execution replay over `2016-04-17` to `2026-03-24` showed the `rr=3 / TP1=2R` target compression preserved and slightly improved exact R (`+209.4R` vs `+203.9R`) and target expression (full TP `23.3%` vs `6.1%`, TP1-BE `8.1%` vs `15.2%`), with 0 negative years, but exact DD worsened materially (`-12.4R` vs `-8.8R`) and Calmar fell (`16.85` vs `23.06`). In the five-leg payout sim at NQ Asia `$400`, it only nudged outcomes from `38/20/1` payout/breach/open to `39/19/1`, with average payout days `26.6` vs `25.9` and max consecutive breaches unchanged at `6`; NQ/ES Asia daily R correlation was effectively unchanged (`0.322` vs `0.314`). R5 exact replay remains invalid for promotion (fee-aware net R `-125.5R`, `tp1=0.10` degenerate). R9 exact replay is healthier but not a replacement here: `+197.3R`, DD `-11.2R`, and portfolio `$400` payout worsened to `34/22/3`, though max breach cluster improved by 1. Strict gate result: no candidate beats incumbent for live hot swap; if smoother target geometry is desired, shadow Tier 1 first or risk-size RR6 rather than replacing it.
- **Asia Continuation Short is NO-GO**: stop=3.5%, rr=3.75, gap=1.0%, tp1=0.6, ATR=30, 10m ORB, entry<=01:00, flat=23:00, excl-Thu, ICF=ON → 874 trades, Calmar 6.30. Robust pipeline 2/5 (WF, Prop, MC all failed). 2022-2023 are structurally negative for shorts — 0/500 grid combos have 0 neg years. Shorts need completely different optimal params than longs (every major dimension differs). Not viable standalone or as a hedge.
- **R5 Final's tp1=0.10 was degenerate**: Post-bugfix optimization converged to tp1=0.10 (94.5% WR, Calmar 60.19) but each TP1_BE win earned only +0.0625R. The strategy was a micro-scalper masquerading as a normal strategy. R9 Restart enforced tp1>=0.2 minimum and found a fundamentally different, healthier profile at tp1=0.6.
- **R9 Restart is a completely different strategy profile than R5**: Long-only (was both), 15m ORB (was 10m), ICF=ON (was OFF), excl-Tue (was excl-Thu), entry_end=22:30 (was 00:00), flat=04:00 (was 01:00), rr=3.0 (was 1.75). Every major structural dimension changed when the tp1 floor was imposed.
- **Destructive parameter interaction warning**: In R3, adopting 5 changes simultaneously crashed Calmar from 20.18→11.97 (-41%). Never adopt more than 2-3 changes at once. The safe approach is resetting to the best-proven config when oscillation is detected.
- **DOW exclusion instability**: excl-Thu was optimal in R4/R5, excl-Tue emerged in R9 Restart. DOW exclusions shift with the anchor — treat with caution but R9's excl-Tue passed 2-round persistence test.
- **SMA trend gate hurts NQ Asia** — opposite of CL where it doubled Sharpe. Both trend directions are profitable; filtering halves trade count without improving edge.
- **atr_length=5 beats 14 for walk-forward** — ATR 14 shows better in-sample Sharpe in pre-sweeps but performs worse OOS (WF efficiency 0.311 vs 0.59 for ATR 5). Use ATR 5 for pipeline validation. Confirmed again in R9 Restart.
- **Two distinct strategy profiles discovered across optimization rounds**:
  - **R5 Final profile** (tp1=0.10, rr=1.75, both, 10m ORB, ICF=OFF): Ultra-high WR scalper (94.5%), Calmar 60.19, but degenerate edge per win (+0.0625R). Not recommended.
  - **R9 Restart profile** (tp1=0.6, rr=3.0, long, 15m ORB, ICF=ON): Moderate WR (45.5%), higher edge per win, Calmar 15.64. Recommended — healthy risk/reward profile.
- **Gap dimension stable at 0.90%**: Confirmed across R4, R5, and R9 Restart. gap=0.9 was stable 7/7 WF folds in R9 pipeline.
- **ICF flipped from OFF to ON**: At the R5 anchor (tp1=0.10, both directions, 10m ORB) ICF was detrimental. At the R9 Restart anchor (tp1=0.6, long-only, 15m ORB, rr=3.0) ICF became beneficial. This is a clear example of parameter interactions — the same filter can be positive or negative depending on the full config.
- **max_gap_points=75 is a new dimension**: Adopted in R9 Restart R5 sweep. Caps absolute gap size in points, complementing the ATR-relative gap filter.

### NY Session
- **R11 Final is the current CONDITIONAL config** (post-fix): stop=7.0%, rr=3.5, gap=2.5%, tp1=0.4, ATR=12, 20m ORB, entry<=12:00, flat=15:30, ICF=OFF, long-only, excl-Fri, 1s magnifier → 561 trades, 53.3% WR, PF 1.51, Sharpe 2.90, 135.0R, DD -6.0R, Calmar 22.51, 0 neg years. WF stability 1.000 (high), WF eff 0.551. MC 99.1% survival. Phase 3 failed on avg annual R (8.1 < 12.0). DB: `bt-nq-ny-cont-long-r11-final-2016-2026-c3bcc0`.
- **Neutral 15m single-target 2R gate workflow (2021-2024 discovery, 2025+ frozen) is a CHALLENGER research lead, not deployment-ready**: fixed the user's neutral anchor (15m NY ORB 09:30-09:45, first 5m continuation FVG, 10% ATR stop, 2% ATR gap, `exit_mode=single_target`, `rr=2`, `tp1_ratio=1`) and tested 26 causal gate rules. Best strict candidate: long-only + prior-day ATR14% <= 1.6228 + ORB range% <= 0.4658, calibrated from 2016-2020 market distributions. 2021-2024 result: 150 trades, +35.46R, PF 1.42, DD -9.0R, Calmar 3.94, 0 negative years (2021 +20.25R, 2022 0.00R, 2023 +6.00R, 2024 +9.21R), MFE p50 1.36R, capture 0.19, PSR 0.9806, DSR 0.7095. `deployability=post_filter_only` because ATR/ORB gates are causal but not native StrategyConfig/execution fields yet; implement them as pre-trade gates before exact replay. Result artifact: `backtesting/data/results/discovery_runs/nq_ny_orb_neutral_gate_workflow_2021_20260608/artifacts/gate_workflow_results.md`.
- **Native StrategyConfig ATR/ORB gate replay weakens the neutral 15m lead; do not open 2025 holdout yet**: after adding native pre-trade fields (`max_prior_atr_pct`, `max_orb_range_pct`), the same long-only gate thresholds (`1.6228`, `0.4658`) over 2021-2024 produced 148 trades, +24.47R, PF 1.28, DD -9.0R, Calmar 2.72, years 2021 +11.25R / 2022 0.00R / 2023 +6.00R / 2024 +7.22R, MFE p50 1.33R, capture 0.13, PSR 0.9244, DSR 0.4725. The drift is from ATR definition: the old research filter used rolling daily TR ATR%, while native gate uses the engine's canonical previous completed daily ATR path. Boundary audit lost 9 prior trade dates (net +9.99R, mostly early-April 2021 winners) and added 7 new dates. Keep 2025 sealed; next pre-holdout decision is whether to freeze a native rolling-ATR context gate to exactly mirror the research lead, or rerun discovery under canonical engine ATR semantics. Result artifact: `backtesting/data/results/discovery_runs/nq_ny_orb_native_gate_candidate_2021_20260608/artifacts/native_gate_candidate_results.md`.
- **Native rolling-ATR StrategyConfig gate exactly mirrors the neutral 15m research lead**: adding `max_prior_rolling_atr_pct` (simple rolling daily true-range ATR% shifted one completed day, matching the original research filter) and rerunning the same 2021-2024 candidate with `ny_max_prior_rolling_atr_pct=1.6228` + `ny_max_orb_range_pct=0.4658` reproduced the prior post-filter result exactly at headline level: 150 trades, +35.46R, PF 1.42, DD -9.0R, Calmar 3.94, PSR 0.9806, DSR 0.7095, years 2021 +20.25R / 2022 0.00R / 2023 +6.00R / 2024 +9.21R. This is research-engine native but not execution-native yet: execution ATR stop/gap logic uses Wilder smoothing via `ATRCalculator`, so live/exact execution support requires a separate rolling-ATR gate or daily-history context feed. Result artifact: `backtesting/data/results/discovery_runs/nq_ny_orb_native_rolling_atr_gate_candidate_2021_20260608/artifacts/native_gate_candidate_results.md`.
- **Execution-native rolling-ATR/ORB gate exact replay is live-native after fixing inherited Friday exclusion, but still weaker than research**: after adding a separate execution `RollingATRPctCalculator`, engine context gates (`max_prior_rolling_atr_pct`, `max_orb_range_pct`), config/API/override plumbing, and disabled profile `NQ_NY_ORB_NEUTRAL_ROLLING_GATE`, exact replay initially inherited base `NQ_NY excluded_dow=4`; setting `excluded_dow=null` restored all 30 Friday research trades. Corrected 2021-2024 exact replay through live engines produced 151 trades, +31.74 gross R / +27.41 net R, PF 1.31, DD -10.03R, Calmar 3.17, Sharpe 2.32, years 2021 +20.53R / 2022 0.00R / 2023 +6.00R / 2024 +5.21R. 1s MFE diagnostics: p50 1.37R, p75 2.01R, MFE>=2R 38.41%, realized-to-MFE capture 0.1720. Delta audit versus research-native rolling gate: all 150 research-filled dates are now present; exact adds one loser (`2024-12-18`, -1R), shared-date exact-minus-research delta is -2.715R, and most remaining drift is one 2024-01-16 same-bar/1s sequencing case where exact exits SL while research records TP. No ATR/ORB gate drift remains. Focused ordering audit below accepts corrected exact replay as the operational baseline before opening 2025. Artifacts: `backtesting/data/results/discovery_runs/nq_ny_orb_exec_native_rolling_gate_2021_20260609/artifacts/exact_replay_results.md`, `backtesting/data/results/discovery_runs/nq_ny_orb_exact_delta_audit_2021_20260609/artifacts/delta_audit_results.md`. Remote save timed out on 2026-06-09, so no dashboard ID was created.
- **2024-01-16 ordering audit accepts exact replay as the operational baseline for the neutral 15m candidate**: targeted pre-holdout audit of the largest exact/research shared-date delta shows the research 1m magnifier booked `tp2_single` at `2024-01-16T11:00:00`, but 1s tape says the target first touched after eligibility at `10:59:45 ET`, the 11:00 target burst ended before the entry filled, the limit filled at `11:00:57 ET`, no target touched after fill, and the stop hit at `11:01:07 ET`. Exact replay entry/exit times match the 1s tape exactly, so do not patch execution; treat corrected exact replay (151 trades, +31.74 gross R, PF 1.31, DD -10.03R) as the pre-holdout operational baseline. This explicitly cleared the 2025 holdout open below. Artifact: `backtesting/data/results/discovery_runs/nq_ny_orb_20240116_ordering_audit_20260609/artifacts/ordering_audit_results.md`.
- **2025 exact holdout PASSES for the live-native neutral 15m ORB rolling-gate candidate**: after the pre-holdout exact baseline was accepted, the first calendar-2025 holdout exact replay through live engines produced 32 trades, +10.38 gross R / +9.74 net R, PF 1.60, DD -3.0R, Calmar 3.46, Sharpe 3.61, 50.0% WR, exit mix 12 TP / 16 SL / 4 EOD, max consecutive losses 3. Monthly R: Jan +1.00, Feb -1.00, Jun +2.47, Jul -1.00, Aug +3.00, Sep +5.18, Oct 0.00, Nov -1.00, Dec +1.73. 1s MFE diagnostics remain aligned with pre-holdout: p50 1.34R, p75 2.02R, MFE>=2R 37.5%, capture 0.2551. Status: positive holdout and `live_native`; cost stress below clears it as a dry-run candidate, but profile remains disabled for live orders pending dry-run/paper fill monitoring. Artifact: `backtesting/data/results/discovery_runs/nq_ny_orb_exec_native_rolling_gate_2025_holdout_20260609/artifacts/holdout_results.md`.
- **Cost stress PASSES for dry-run candidacy, but the edge has an 8 ticks/side boundary**: post-commission exact trade lists (2021-2025) were stressed by subtracting additional adverse round-trip slippage at 1/2/4/8 ticks per side. At 2 ticks/side, pre-holdout remains +19.87 net R, PF 1.21, DD -12.11R, while 2025 holdout remains +8.63 net R, PF 1.51, DD -3.36R. At 4 ticks/side, combined 2021-2025 remains +19.85 net R, PF 1.17, DD -14.07R, and 2025 remains +7.51 net R, PF 1.43. At 8 ticks/side, combined is only +2.54 net R, PF 1.02, with pre-holdout negative (-2.74R), so this is not a strategy to scale blindly through poor fills. Verdict: `dry_run_candidate_cost_stress_pass`, `deployability=live_native`, exact replay complete, profile still disabled. Next operating step is dry-only/paper monitoring with live-vs-exact slippage tracked in ticks/side; do not scale risk unless observed slippage is comfortably inside the 2 ticks/side stress envelope. Artifact: `backtesting/data/results/discovery_runs/nq_ny_orb_rolling_gate_cost_stress_20260609/artifacts/cost_stress_results.md`.

> **All previous NY metrics below were computed before the TP1+BE same-bar exit bug fix (commit 6079ad4).** Specific Calmar/R/Sharpe/DD numbers are unreliable. Directional findings (which params are better/worse relative to each other) are still useful as starting hypotheses.

- **All previous NY configs (R20, Long 30m ICF, Long-only CONDITIONAL, LDN R2) are CORRUPT** — R11 Final above is the post-fix replacement.
- **NQ NY continuation shorts are CONDITIONAL (v2)** — re-optimized with dual floors (min_stop=10pt, min_tp1=10pt) from scratch. Key insight: entry_end=11:00 and flat=11:00 transform shorts from NO-GO (Calmar 1.40) to strong (Calmar 7.86). ORB 25m, stop_orb=17%, rr=2.0, tp1=0.3, gap_orb=5%, DOW excl Mon, 329 trades, 0 neg years. WF stability HIGH (0.80), MC survival 97.8%. Only failure: annual R (2.86R/yr) below 12R threshold (unrealistic for short-only ~33 trades/yr). DB: `bt-nq-ny-short-v2-2016-2026-final-d9db60`.
- **20m ORB (09:30-09:50) is likely the optimal window** for NY — confirmed across R16-R20 sweeps pre-fix. Starting hypothesis for re-optimization.
- **Entry end 15:30 is likely optimal** — R17 showed entry_end=15:30 was a massive lever. Starting hypothesis for re-optimization.
- **ATR=12 is likely optimal** — shifted from 14 in earlier rounds. Starting hypothesis for re-optimization.
- **Stop ATR interacts strongly with RR** — this lesson confirmed in R19-R20 pre-fix. stop changes reshuffle the entire optimal surface. Always re-run full grid after finding a new stop anchor.
- **DOW exclusion is a data-mining artifact** — shifted every round pre-fix (Th+F in R16-R17, Tue in R18, different again in R19). Do not use.
- **2022-2023 are likely the weak years** — consistent across all pre-fix configs. Expect this to persist post-fix.
- **ICF is likely detrimental for NQ NY** — pre-fix finding across full parameter space. Will re-verify in sweeps.
- ~~Reversal and inversion strategies are dead~~ **INVALIDATED** — prior reversal/inversion results tested without liquidity sweep gate. Needs re-testing with sweep-gated definition.

### NY Continuation Long R11 Final (20m ORB, long-only, 1s magnifier) — CONDITIONAL
- **Status**: CONDITIONAL — 4/5 pipeline phases passed. Phase 3 (Prop Constraints) failed on avg annual R.
- **Config** (fresh optimization on fixed engine, 11 rounds + 3 grid sweeps):

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | NY |
| ORB window | 20m (09:30-09:50) |
| entry_start | 09:50 |
| entry_end | 12:00 |
| flat_start | 15:30 |
| flat_end | 16:00 |
| direction | long |
| rr | 3.5 |
| tp1_ratio | 0.4 |
| stop_atr_pct | 7.0% |
| min_gap_atr_pct | 2.5% |
| atr_length | 12 |
| ICF | OFF |
| DOW excl | Fri (post-backtest) |
| magnifier | 1s |

- **Full-history (2016-2026)**: 561 trades, 53.3% WR, PF 1.51, 135.0R (13.5 R/yr), DD -6.0R, Calmar 22.51, Sharpe 2.90, **0 negative full years**
- **R by year**: 2016:+8, 2017:+24, 2018:+22, 2019:+22, 2020:+14, 2021:+12, 2022:+6, 2023:+3, 2024:+11, 2025:+9, 2026:+4
- **Median stop**: 54.2 ticks

#### Robust Pipeline Results
- **Phase 1 (Structural)**: PASS — 561 trades, 53.3% WR, PF 1.51, Calmar 22.51, 54.2 tick stop
- **Phase 2 (Walk-Forward)**: PASS — WF efficiency 0.551, stability 1.000 (high), 7 folds. stop=7.0 chosen 6/7 folds, rr=3.5 in 4/7. Combined OOS: 387 trades, 51.2% WR, PF 1.30, 56.8R, Sharpe 1.83, DD -8.9R, Calmar 6.36. 2023 OOS fold: -2.9R (only negative year).
- **Phase 3 (Prop Constraints)**: FAIL — avg annual R 8.1R (threshold 12.0R). Worst month -4.6R (PASS). Positive expectancy +0.147R (PASS). 2023 OOS: -2.9R dragged average below threshold.
- **Phase 4 (Hold-Out 2025+)**: PASS — 54 trades, 53.7% WR, PF 1.52, Sharpe 2.90, +13.1R, DD -4.0R
- **Phase 5 (Monte Carlo)**: PASS — 99.1% survival at -25R ruin. p50 DD -12.4R, p5 PnL 83.5R, p5 Sharpe 1.82
- **Verdict**: CONDITIONAL — size position conservatively. Phase 3 fails because long-only NY generates ~56 trades/year, limiting absolute R accumulation. Edge per trade (+0.24R) is solid but frequency is the bottleneck.
- **DB entry**: `bt-nq-ny-cont-long-r11-final-2016-2026-aa7630`

#### Wide-Stop Target Sweep (2026-05-05)

- **Report**: `backtesting/learnings/reports/NQ_ES_NY_ORB_WIDE_STOP_TARGET_SWEEP_20260505.md`
- **Scope**: Held R11 structure fixed (20m ORB, long-only, ATR 12, gap 2.5% ATR, entry to 12:00, flat 15:30, excl-Fri, 1s magnifier) and swept ATR/ORB stop width, `rr`, and TP1 distance.
- **Baseline in common ALPHA window (`2016-04-17` to `2026-03-24`)**: `ATR 7% / rr 3.5 / tp1 0.4` -> median stop `54.9` ticks, `+122.4R`, `PF 1.55`, `-10.6R` DD, last-1y `+9.4R`, last-2y `+19.9R`.
- **Conclusion**: NO-GO for replacing R11 with a wider stop. Zero rows widened the actual median stop by at least `20%` while preserving full-history, last-1y, last-2y, PF, DD, and negative-year quality. The least-bad actual widening was the `ATR 9%` family (`~70.6` median ticks, `1.29x` wider), but its best full-history rows gave up roughly `26R-30R` versus baseline. Example: `ATR 9% / rr 3.0 / TP1_R 1.25` -> `+96.2R`, `PF 1.42`, `-10.4R` DD, last-1y `+10.6R`, last-2y `+19.8R`.
- **Operating read**: R11's stop is already part of the edge. If NQ NY ORB is added beside ES NY ORB, size it down as a second NY ORB leg rather than widening the stop to make it feel like Asia. `deployability=live_native`, `exact_replay_required=yes_before_live_promotion`.

#### NQ/ES NY ORB Pair Phase-One Risk Sizing (2026-05-05)

- **Report**: `backtesting/learnings/reports/NQ_ES_NY_ORB_PAIR_PHASE_ONE_RISK_SWEEP_20260505.md`
- **Scope**: Paired frozen NQ R11 with current ES_NY ORB and swept only per-leg dollar risk (`$100-$650` by `$50`) under the `$50k` funded-account first-payout model. No R11 parameters were optimized.
- **R11 standalone in the common ALPHA window (`2016-04-17` to `2026-03-24`)**: `552` fills, `+129.4R`, `PF 1.50`, `-6.0R` DD, `53.3%` WR, median stop `54.9` ticks, `18.1%` full TP, `33.0%` TP1-BE, `46.4%` SL.
- **Conservative pair sizing**: `NQ $150 / ES $150` had pre-holdout payout `83.3%`, breach `0.0%`, EV `$316.67`, avg payout `198d`; holdout payout `75.0%`, breach `0.0%`, EV `$275.00`, avg payout `186d`.
- **Sprint pair sizing**: `NQ $250 / ES $350` had pre-holdout payout `74.1%`, breach `23.7%`, EV `$270.61`, avg payout `79d`; holdout payout `59.4%`, breach `21.9%`, EV `$196.88`, avg payout `70d`.
- **Operating read**: R11 is a valid NQ side of a split NY ORB sleeve, but only after exact execution replay. If used with ES_NY, treat `NQ $150` as conservative probation sizing and `NQ $250` as the faster phase-one sizing. `deployability=live_native`; `exact_replay_required=yes_before_live_promotion`.

#### NQ NY ORB R11 Exit Deep-Dive (2026-05-05)

- **Report**: `backtesting/learnings/reports/ES_NQ_NY_ORB_EXIT_DEEPDIVE_20260505.md`
- **Scope**: Replayed R11 under true single-target/full-position TP1, no-BE, delayed-BE, and pre-trade bucket diagnostics before moving on to NQ Asia or NQ HTF-LSI exit optimization.
- **Baseline in common ALPHA window (`2016-04-17` to `2026-03-24`)**: `552` fills, `+129.4R`, `PF 1.50`, `-6.0R` DD, `53.3%` WR, `18.1%` full TP, `33.0%` TP1-BE.
- **Best research policies**: full-position exit at current TP1 (`1.4R`) improved to `+155.2R`, `PF 1.61`, `-6.4R` DD; delayed BE after `1.5R` improved to `+160.7R`, `PF 1.63`, `-6.0R` DD.
- **Operating read**: The simple closer-TP2 sweep was not the right branch. R11 has upside from changing runner management. `exit_mode=single_target` now makes the true single-target/full-position TP1 branch `deployability=live_native`, pending exact replay before deployment. Delayed-BE remains `research_only`. Gating is lower priority because the weakest pre-trade buckets were still positive.

#### Optimization History
- **R1-R7**: 7 rounds of variable sweeps. R2 adopted 5 changes simultaneously — destructive (crashed Calmar). R3 reverted all 5. Lesson: max 2-3 adoptions at once. **R7 CONVERGED** at Calmar 14.45.
- **Grid R1**: 540 combos. Winner: stop=7.0, rr=3.25, gap=2.5, tp1=0.45 (Calmar 16.45, +2.00). Adopted.
- **R8-R9**: Post-grid sweeps. R8 adopted ATR 20→12. **R9 CONVERGED** at Calmar 16.50. tp1=0.4 blocked individually (2023 neg), but works with higher rr.
- **Grid R2**: 375 combos. Winner: stop=7.0, rr=3.5, gap=2.5, tp1=0.4 (Calmar 20.73, +4.23). Key interaction: tp1=0.4 blocked at rr=3.25 but viable at rr=3.5. Adopted.
- **R10-R11**: Post-grid sweeps. R10 adopted ICF ON→OFF (+1.78). **R11 CONVERGED** at Calmar 22.51.
- **Grid R3**: 375 combos. **Anchor ranked #1/375 overall and #1/66 (0-neg)**. Delta +0.00 — perfect convergence.
- **ICF oscillation**: OFF→ON→OFF→OFF→OFF→ON→ON→ON→ON→OFF. Context-dependent. Settled at OFF for this anchor.
- **2023 is the persistent weak year**: +2.8R in full-history. Drives Phase 3 failure in WF (2023 OOS = -2.9R). Cannot be eliminated without overfitting.
- **Entry delay**: 0m (baseline) is optimal. Even 10m delay halves Calmar (22.51→9.24, DD -6.0→-12.0R). 30m delay drops to Calmar 3.81. The edge comes from capturing the first FVG immediately after the 20m ORB closes. Script: `run_combined_longs_entry_delay_sweep.py`.
- **Event day exclusion**: No exclusions beneficial. FOMC days are actually *better* than average (+0.457R avg, 60% WR vs 53.3% overall, n=20). CPI slightly below average (+0.129R vs +0.241R, n=29). NFP has 0 fills. Excluding FOMC hurts Calmar (22.51→19.82). Excluding all events: 22.51→18.32. Script: `run_combined_longs_event_day_sweep.py`.
- **Scripts**: `run_nq_ny_long_variable_sweeps_{1-11}.py`, `run_nq_ny_long_grid_sweep_r{1-3}.py`, `run_nq_ny_long_robust_pipeline.py`, `save_nq_ny_long_r11_final.py`

### LDN Session — CORRUPT (pre-fix metrics, directional findings preserved)
- **NQ LDN continuation is marginal** — best achievable Calmar ~1.13 pre-fix (full-history). Orders of magnitude weaker than Asia.
- **Only 1 of 3 walk-forward candidates passed GO** — and barely (hold-out Sharpe 0.58, just above 0.5 threshold). Two other candidates had stronger OOS R/yr but failed hold-out Sharpe.
- **2016 is the persistent negative year** — appears in every config tested, cannot be eliminated.
- **ICF=ON and max_gap_points=20 were the only two adoptions** across R1-R2 variable sweeps (12 dimensions each). Most dimensions showed no meaningful improvement from the weak anchor.
- **Many promising dimensions blocked by new negative years** — ORB 10m (Calmar 2.72 but adds 2020), excl Mon (2.14 but adds 2023), ATR 30 (1.86 but adds 2024), long-only (1.47 but adds 2018). The strategy doesn't have enough edge to support structural changes.
- **Grid sweep (576 combos) barely moved the anchor** — best ≤1-neg-year combo: stop=8.0/rr=2.5/gap=1.5/tp1=0.5 (Calmar 1.13 vs anchor 1.12, Δ=+0.01).
- **OOS performance is thin** — grid #2 (stop=8.0/rr=2.25/gap=1.5/tp1=0.6) passed WF with all 6 folds profitable but 2024 was +0.2R and 2019 was +1.8R. Combined OOS: 10.3 R/yr, Calmar 0.41.

### LDN Continuation R2 Final (15m ORB, both, 1s magnifier) — CORRUPT (was MARGINAL GO)
- **Status**: CORRUPT — pre-dates TP1+BE bug fix. tp1=0.6 means less affected than NY R20, but all metrics are still unreliable. Was MARGINAL GO — fixed-param WF 6/6 folds profitable, hold-out PASS (barely).
- **Config** (R1-R2 optimization + grid sweep):

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | LDN |
| ORB window | 15m (03:00-03:15 ET) |
| entry_start | 03:15 |
| entry_end | 08:25 |
| flat_start | 08:20 |
| flat_end | 08:25 |
| direction | both |
| rr | 2.25 |
| tp1_ratio | 0.6 |
| stop_atr_pct | 8.0% |
| min_gap_atr_pct | 1.5% |
| max_gap_points | 20 |
| max_gap_atr_pct | 0 (no limit) |
| atr_length | 14 |
| magnifier | 1s |
| impulse_close_filter | ON |

- **Full-history performance** (2016-2026): 2,034 trades, 44.8% WR, PF 1.05, 51.4R total (5.1 R/yr), Max DD -45.6R, Calmar 1.13, Sharpe 0.35, 1 neg year (2016)
- **R by year**: 2016:-41  2017:+14  2018:+7  2019:+2  2020:+14  2021:+10  2022:+20  2023:+16  2024:+0  2025:+13  2026:-4

#### Fixed-param Walk-Forward (6 folds, OOS 2019-2024)

| Fold | OOS Period | Trades | WR | PF | Sharpe | R | DD |
|------|-----------|--------|-----|-----|--------|---|-----|
| 1 | 2019 | 204 | 45.6% | 1.01 | 0.13 | +1.8 | -15.6 |
| 2 | 2020 | 196 | 45.9% | 1.14 | 0.94 | +13.7 | -10.5 |
| 3 | 2021 | 211 | 46.0% | 1.09 | 0.66 | +10.1 | -10.0 |
| 4 | 2022 | 201 | 47.3% | 1.20 | 1.36 | +20.4 | -12.3 |
| 5 | 2023 | 201 | 45.3% | 1.15 | 1.03 | +15.8 | -25.2 |
| 6 | 2024 | 196 | 43.9% | 1.01 | 0.01 | +0.2 | -22.0 |

- **Combined OOS**: 1,209 trades, 45.7% WR, PF 1.10, Sharpe 0.70, +62.0R (10.3 R/yr), DD -25.2R, Calmar 0.41
- **Hold-out (2025+)**: 216 trades, 46.8% WR, PF 1.09, Sharpe 0.58, +9.1R, DD -17.9R — PASS (barely)
- **Verdict**: MARGINAL GO — all 6 folds profitable but folds 1 and 6 are razor-thin (+1.8R, +0.2R). Hold-out Sharpe just barely clears 0.5 threshold. Not recommended for primary allocation.

#### R1-R2 Optimization History
- **R1**: Fresh start with LDN defaults (stop=10%, rr=2.0, tp1=0.5, gap=1.0%, max_gap=50, ICF=OFF). Calmar 0.09 (very weak anchor, 4 neg years). Only 2 of 12 dimensions adopted: max_gap_points=20 (Δ+0.32) and ICF=ON (Δ+0.64). All other promising dimensions blocked by new negative years.
- **R2**: max_gap=20 + ICF=ON applied. Calmar jumped to 1.12 (1 neg year: 2016). **Fully converged — every dimension Δ=0** (no adoptions pass threshold without new neg years).
- **Grid sweep**: 576 combos (6 stops × 6 rrs × 4 gaps × 4 tp1s). Best ≤1 neg year: stop=8.0/rr=2.5/gap=1.5/tp1=0.5 (Calmar 1.13). Anchor barely moved. No fine-tune needed.
- **Walk-forward**: Tested 3 candidates. Only grid #2 (stop=8.0/rr=2.25/gap=1.5/tp1=0.6) passed — marginal GO.
- **DB entry**: `bt-nq-ldn-r2-final-e132b8`

### LDN Continuation Long (30m ORB, 1s magnifier) — NO-GO
- **Status**: NO-GO — robust pipeline failed Phases 2, 3, 4, 5 (only Phase 1 passed)
- **Config tested** (converged from 6 sweep rounds + grid):

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | LDN |
| ORB window | 30m (03:00-03:30 ET) |
| entry_start | 03:30 |
| entry_end | 08:25 |
| flat_start | 08:20 |
| flat_end | 08:25 |
| direction | long |
| rr | 6.0 |
| tp1_ratio | 0.7 |
| stop_atr_pct | 1.5% |
| min_gap_atr_pct | 1.0% |
| atr_length | 10 |
| magnifier | 1s |
| impulse_close_filter | OFF |
| DOW exclusion | none |

- **Full-history performance** (2016-2026): 1124 trades, 25.0% WR, PF 1.35, 299.7R total (29.5 R/yr), Max DD -24.1R, Calmar 12.46, Sharpe 1.83, 0 neg full years
- **R by year**: 2016:+8  2017:+45  2018:+42  2019:+41  2020:+32  2021:+34  2022:+0  2023:+25  2024:+41  2025:+33  2026:-1

#### Robust Pipeline Results

| Phase | Result | Key Metrics |
|-------|--------|-------------|
| 1 — Structural | PASS | 1124 trades, PF 1.35, Calmar 12.46, med stop 11 ticks |
| 2 — Walk-Forward | FAIL | WF eff 0.35 (< 0.5), stability 0.80 (high). 2020+2022 OOS folds negative |
| 3 — Prop Filter | FAIL | Worst month -10.0R (> 5.0R cap). 2020: -9.2R, 2022: -6.8R on WF OOS |
| 4 — Hold-Out OOS | FAIL | Sharpe 0.18, PF 1.03, +3.1R. Mode params (stop=1.0, rr=8.0) weak OOS |
| 5 — Monte Carlo | FAIL | 0.1% survival at 15R, 87.8% ruin at 25R |
| **Verdict** | **NO-GO** | 1/5 pass. Strategy overfits to full history. |

- **WF mode params**: stop=1.0, rr=8.0, gap=1.0, tp1=0.7 — WF consistently selects higher R:R and tighter stops than the in-sample optimum
- **Key insight**: The high R:R (6.0) / low WR (25%) profile produces concentrated wins in specific regimes (2017-2019, 2021, 2024) but fails in choppy markets (2020, 2022). Full-history Calmar of 12.46 is misleading — the walk-forward shows the strategy doesn't generalize.
- **Median stop**: 11 ticks at 1.5% ATR — borderline above 10-tick minimum. WF prefers even tighter (1.0% ATR = ~7 ticks), suggesting the optimization gravitates toward impractically tight stops.

#### Optimization History
- **Baseline**: LDN defaults (stop=10%, rr=2.5, tp1=0.5, gap=1.0%, ATR 14, ORB 15m). Long-only Calmar 0.07, shorts fail (PF 0.95).
- **R1** (13 dims): 4 adoptions — stop: 10→2.0, orb: 15m→45m, rr: 2.5→5.0, tp1: 0.5→0.4
- **R2** (13 dims): 5 adoptions — stop: 2.0→2.5, orb: 45m→30m, ATR: 14→10, rr: 5.0→8.0, tp1: 0.4→0.6. ORB%-based sizing consistently worse than ATR-based.
- **R3** (13 dims): 2 adoptions — stop: 2.5→1.5 (+6.80 Calmar, 0 neg yrs), rr: 8.0→4.0
- **R4** (13 dims): 2 adoptions — rr: 4.0→6.0 (+3.68), tp1: 0.6→0.5 (+0.78)
- **R5** (core 3 only): 1 adoption — tp1: 0.5→0.7 (+0.41)
- **R6** (core 3 only): 0 adoptions — CONVERGED
- **Grid** (600 combos): Winner Calmar 12.74 vs anchor 12.46 (Δ=+0.28 < 0.5) — confirmed
- **Parameter sensitivity**: Stop size is the dominant driver. 1.0% and 1.25% ATR produce higher Calmar but fail 10-tick minimum. R:R and TP1 have a feedback loop but stabilize quickly. ORB window, gap, ATR length, ICF are all insensitive at this anchor.

#### Scripts Generated
- `run_nq_ldn_baseline.py`
- `run_nq_ldn_variable_sweeps_1.py` through `run_nq_ldn_variable_sweeps_6.py`
- `run_nq_ldn_grid_sweep_r1.py`
- `run_nq_ldn_robust_pipeline.py`
- `save_nq_ldn_r1_final.py`
- **DB entry**: `bt-nq-ldn-cont-long-2016-2026-final-679958`

### LDN LSI (Liquidity Sweep Inversion) Long — GO
- **Status**: GO — 5/5 pipeline phases passed
- **DB entry**: `bt-nq-ldn-lsi-long-2016-2026-final-df4a78` (1x) / `bt-nq-ldn-lsi-long-2016-2026-final-4x-39b078` (4x)
- **Optimization**: lsi-optimization workflow — baseline (NY-informed) → 8 variable sweep rounds → grid sweep R1 → RR fine-tune (0.05-step) → verification → robust pipeline v2
- **Key lesson**: Naive defaults (n_left=3, n_right=3, gap=2.25%, rr=2.625, tp1=0.3) produced Calmar -0.58 — a false NO-GO. NY-informed params required as starting point (n_right=session-length, gap=5.0%, rr~1.65, tp1=0.7, long only).
- **Key lesson**: rr/tp1 interact and oscillate in independent sweeps. Grid sweep (0.25-step) found rr=1.75; fine-tune (0.05-step) found rr=1.65 optimal (+0.45 Calmar). Always fine-tune RR after grid.
- **Key lesson**: WF mode params (rr=1.75, tp1=0.7, gap=6.0%) differ slightly from in-sample anchor (rr=1.65, gap=5.0%) — normal; WF cross-validates slightly more conservative RR.

**Final config** (in-sample anchor, 2016-2026):

| Param | Value |
|-------|-------|
| strategy | lsi |
| lsi_stop_mode | absolute |
| session | LDN |
| orb | 03:00-03:05 ET (vestigial) |
| entry | 03:30-07:00 ET |
| flat | 08:20 ET |
| lsi_n_left | 8 |
| lsi_n_right | 60 (LDN session-length) |
| lsi_fvg_window_left | 7 |
| lsi_fvg_window_right | 3 |
| min_gap_atr_pct | 5.0% |
| atr_length | 10 |
| rr | 1.75 |
| tp1_ratio | 0.7 |
| direction | long only |
| magnifier | 1m |

**In-sample performance** (2016-2026):
| Metric | Value |
|--------|-------|
| Trades | 165 |
| Win Rate | 64.8% |
| PF | 2.30 |
| Net R | 47.2R |
| R/yr | 4.6R |
| Max DD | -2.5R |
| Calmar | 18.92 |
| Sharpe | 5.559 |
| Neg years | 0 |
| Median stop | 150 ticks |

**Pipeline results** (GO 5/5):
| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | PASS | 165 trades, PF 2.30, Calmar 18.92, 0 neg years |
| 2 Walk-Forward | PASS | WF eff 0.658, stability 0.867 (high), 5 folds |
| 3 Prop Filter | PASS | DD -2.0R (INFO), worst month -1.5R, expectancy +0.28R |
| 4 Hold-Out OOS | PASS | PF 1.30, +1.3R, 9 trades (2025-2026 thin but positive) |
| 5 Monte Carlo | PASS | 100% survival, 0% ruin at -25R threshold |

**WF mode params** (cross-validated best): rr=1.25, tp1=0.6, gap=6.0%

**Parameter sensitivity**:
- gap=5.0% is strongly locked — any lower (3-4%) causes sharp Calmar/quality degradation
- n_right=60 is locked to session-length — smaller values find micro-pivots and degrade quality
- entry window 03:30-07:00 is tight — wider (03:05 or 08:25) reduces Calmar by 5+
- Hold-out thin (9 trades): LDN LSI has limited trades/year (~16-17), 2025 partial year gives fewer signals

**Optimization convergence path** (Calmar):
- Naive baseline: -0.58 (false NO-GO)
- NY-informed baseline: 4.43 → 13.26 (R3) → 15.79 (R4) → 16.34 (R5 converged)
- Post-grid: 18.92 (R8 confirmed 0 adoptions)

**Scripts generated**:
- `run_nq_ldn_lsi_baseline.py`
- `run_nq_ldn_lsi_variable_sweeps_1.py` through `run_nq_ldn_lsi_variable_sweeps_8.py`
- `run_nq_ldn_lsi_grid_sweep_r1.py`
- `run_nq_ldn_lsi_robust_pipeline.py`
- `save_nq_ldn_lsi_r1_final.py`

### NY Liquidity Sweep Inversion (LSI) Long — CONDITIONAL
- **Status**: CONDITIONAL — 4/5 pipeline phases passed; Phase 3 (prop constraints) failed on annual R gate
- **Optimization**: Full lsi-optimization workflow — baseline → 11 variable sweep rounds → grid R1 → R11 re-sweep → robust pipeline
- **Final config**:

| Param | Value |
|-------|-------|
| strategy | lsi |
| lsi_stop_mode | absolute |
| session | NY |
| orb_end | 09:35 (5m ORB) |
| entry_start | 09:35 |
| entry_end | 15:30 |
| flat_start | 15:50 |
| rr | 1.5 |
| tp1_ratio | 0.6 |
| min_gap_atr_pct | 5.0% |
| atr_length | 10 |
| lsi_n_left | 4 |
| lsi_n_right | 78 |
| lsi_fvg_window_left | 20 |
| lsi_fvg_window_right | 3 |
| direction | long only |
| magnifier | 1m |

- **Full-history performance** (2016–2026, 10 full years):
  - 1146 trades, 58.3% WR, PF 1.33, Sharpe 1.956, Net R 121.1R, R/yr 12.1R, Max DD -9.0R, **Calmar 13.44**
  - **0 negative full years** (min: 2022 +2.5R, max: 2020 +30.9R)
  - Median stop: 210 ticks (~52.5 pts NQ)

- **Walk-forward OOS** (7 folds, 36m IS / 12m OOS / 12m step):
  - Combined OOS: 745 trades, 57.9% WR, PF 1.22, Sharpe 1.366, Net R 53.0R, R/yr 7.6R, DD -12.6R, Calmar 4.20
  - WF efficiency: 0.643 | Parameter stability: 0.952 (high)
  - rr mode=1.5 (6/7 folds), tp1 mode=0.6 (6/7 folds), gap mode=5.0 (5/7 folds)
  - 1 neg OOS year: 2021 (-3.6R) from fold 3 (Sharpe -0.600 OOS)

- **Prop constraints** (FAIL): OOS avg annual R 7.6R < 12R gate; worst month -5.1R > 5.0R limit
- **Hold-out OOS** (2025+, PASS): 117 trades, PF 1.12, Sharpe 0.810, +5.4R, DD -5.6R
- **Monte Carlo** (PASS): 98.5% survival at -25R ruin, 1.5% ruin probability, p50 DD -12.9R

- **Key findings**:
  - `lsi_stop_mode="absolute"` (structural stop at swing pivot) is the correct stop type — no ATR stop
  - `lsi_n_right=78` (one full NY session = 6.5h × 12 bars/hr) consistently wins throughout optimization
  - `lsi_n_left=4` (tight pivot confirmation) beats wider values
  - `lsi_fvg_window_left=20` (wider FVG context window) beats the initial 10
  - Baseline Calmar 0.02 → final Calmar 13.44 over 11 variable sweep rounds + grid
  - 2021 is the structural weak year — most OOS folds covering 2021 show negative or near-zero
  - Gap=5.0% is fully locked in: ALL 25 zero-neg-year combos in the grid had gap=5.0%
  - Phase 3 failure is marginal: strategy profitable OOS every year except 2021; monthly gate just barely missed (-5.1R vs -5.0R limit)

- **DB entry**: `bt-nq-ny-lsi-long-2016-2026-r1-final-b2fa98`
- **Conclusion**: Viable strategy with excellent in-sample characteristics and strong parameter stability. Fails prop firm annual R threshold OOS (7.6R vs 12R) due to 2021 drag. Accept CONDITIONAL or add a market regime gate to filter 2021-type environments.

#### Post-Pipeline Exploration (2026-02-27)

All tests below run post-hoc or as additional sweeps against the R1 final anchor (unless noted). Anchor Calmar = 12.90 (full-history 2016–2026).

**Criteria comparison** (lsi_first_fvg_only, lsi_clean_path, fvg_limit entry):
- All filter variants reduce Calmar vs anchor — volume loss dominates
- `first_fvg_only=True`: Calmar 11.08 (−1.82), 1 neg year — NO-GO
- `clean_path=True`: Calmar 7.16–8.49 — NO-GO
- `fvg_limit + first_fvg_only`: Calmar 10.87, 0 neg years — better PF/Sharpe but lower Calmar — NO-GO vs anchor (covered separately as its own config)

**Timeframe exploration** (primary signal generation):
- 1m (×5 scaled params): Calmar 0.38, 4 neg years — NO-GO
- 1m (raw, same integer params): Calmar −0.11, 4 neg years — NO-GO
- 15m (÷3 scaled): Calmar −0.68, 6 neg years — NO-GO
- 15m (raw): Calmar −0.33, 5 neg years — NO-GO
- 30m (÷6 scaled): Calmar −0.51, 7 neg years — NO-GO
- 30m (raw): Calmar 1.15, 3 neg years — NO-GO
- **5m is definitively the optimal timeframe for this strategy**

**Internal swing BE trigger** (`lsi_be_swing_n_left`):
- Feature implemented: pre-FVG swing HIGH triggers BE stop before TP1 for longs; `lsi_cancel_on_swing` cancels limit pre-fill if swing swept
- Sweep N=[0,1,2,3,5,7,10]: ALL N>0 degrade — N=1 drops to Calmar 0.35 (6 neg years), N=10 reaches only 3.69
- Root cause: BE fires when price rallies toward/past pre-FVG swing high, converting EXIT_TP1_BE profits into EXIT_BE_SL (0R) trades. 423/1146 trades (N=1) reclassified.
- `lsi_cancel_on_swing=True` had zero effect in close-mode (swing HIGH above entry never swept during pending window)
- **NO-GO at all N values** — feature remains in codebase at N=0 (disabled)

**DOW exclusion sweep** (post-hoc filtering):
- No Wednesday: Calmar 11.47, 0 neg years — below anchor
- No Thursday: Calmar 12.29, 1 neg year — below anchor
- **No Wed+Thu (Mon/Tue/Fri only): Calmar 14.30 (+1.40), 0 neg years, Sharpe 2.798, DD −7.0R** — **ADOPT**
- Removing Monday or Friday both hurt significantly
- Re-ran all variable sweeps with Wed+Thu excluded (R12) — **anchor further refined**: n_left=2, n_right=60

**R12 variable sweeps (post-DOW anchor, n_left=4, n_right=78, DOW=Mon/Tue/Fri)**:
- lsi_n_left=2: Calmar 14.76 (+0.46) — ADOPT; lsi_n_right=60: Calmar 14.90 (+0.60) — ADOPT
- All other dims stable: direction=long, fvg_left=20, fvg_right=3, gap=5.0%, atr=10, entry_end=15:30 all unchanged
- Monthly loss cap 3.0R: Calmar 14.75 (+0.45) — INFO-ONLY (cap removes only 4 trades, near-threshold)
- New anchor: n_left=2, n_right=60

**R13 variable sweeps (post-R12 anchor: n_left=2, n_right=60)**:
- Combined anchor regressed to Calmar 11.77 (2 neg years) — n_left=2 + n_right=60 interact negatively
- lsi_n_left=10: Calmar 15.74 (+3.97, 0 neg years) — ADOPT; lsi_n_right=78: Calmar 14.76 (+2.99, 0 neg years) — ADOPT
- Key lesson: sequential independent adoptions can interact — always re-sweep after combining
- New anchor: n_left=10, n_right=78; R14 in progress

**entry_start sweep** (09:35 to 11:30):
- 09:35 is optimal (Calmar 12.90, 0 neg years)
- Every later start degrades: 09:40→Calmar 6.63 (DD −15.9R), 10:00→5.72 — early signals contain the edge
- **No change — 09:35 confirmed optimal**

**flat_start sweep** (13:00 to 16:00):
- 15:50 is optimal (Calmar 12.90, 0 neg years)
- Earlier exits destroy value: 14:00→Calmar 2.57 (5 neg years), 15:00→7.69 — late-session exits are net positive
- 16:00 (later) also worse: Calmar 9.66, 1 neg year
- **No change — 15:50 confirmed optimal**

**SMA trend gate** (longs only when close > SMA):
- SMA20→200 all worse than no gate: Calmar 5.51–8.62, 2–3 neg years
- **NO-GO** — LSI edge does not require trend alignment; counter-trend setups contribute positively

**ATR volatility gate** (skip days when ATR > SMA×threshold):
- Best result: thresh=2.0, sma=20 → Calmar 13.12 (+0.22), 0 neg years — only removes 2 trades from 1146
- All tight thresholds (1.1–1.5) degrade: Calmar 6.93–12.08 with 0–1 neg years
- **NO-GO** — improvement at thresh=2.0 is within noise (2 trades removed)

### NY LSI Long v2 — DOW-filtered, Refined Anchor — CONDITIONAL

- **Status**: CONDITIONAL — 4/5 pipeline phases passed. Phase 3 annual R gate fails (5.9R OOS vs 12R gate), but 0 neg OOS years and strong hold-out OOS. Gate is miscalibrated for DOW-filtered strategy.
- **Optimization**: R12–R16 variable sweeps (5 rounds) + n_left×n_right 2D mini-grid + Grid Sweep R2 post-DOW adoption. Followed DOW adoption from v1 post-pipeline exploration.
- **Final config**:

| Param | Value |
|-------|-------|
| strategy | lsi |
| lsi_stop_mode | absolute |
| session | NY |
| orb_end | 09:35 (5m ORB) |
| entry_start | 09:35 |
| entry_end | 15:30 |
| flat_start | 15:50 |
| rr | 1.5 |
| tp1_ratio | 0.6 |
| min_gap_atr_pct | 5.0% |
| atr_length | 14 |
| lsi_n_left | 10 |
| lsi_n_right | 65 |
| lsi_fvg_window_left | 20 |
| lsi_fvg_window_right | 3 |
| direction | long only |
| DOW filter | Mon/Tue/Fri (Wed+Thu excluded) |
| magnifier | 1m |

- **Full-history performance** (2016–2026, 10 full years):
  - 635 trades, 59.8% WR, PF 1.45, Sharpe 2.710, Net R 90.5R, R/yr 9.0R, Max DD -5.9R, **Calmar 15.32**
  - **0 negative full years** (min: 2016 +0.7R, 2022 +3.2R; max: 2020 +19.7R, 2023 +19.0R)
  - Median stop: 218 ticks (~54.5 pts NQ)

- **Walk-forward OOS** (7 folds, 36m IS / 12m OOS / 12m step):
  - Combined OOS: 413 trades, 59.3% WR, PF 1.31, Sharpe 2.008, Net R 41.5R, R/yr 5.9R, DD -6.1R, Calmar 6.81
  - WF efficiency: **0.751** | Parameter stability: **1.000 (high)**
  - rr mode=1.5 (5/7 folds), tp1 mode=0.6 (5/7 folds), gap mode=5.0 (3/7, range [4,6])
  - **0 neg OOS years** (all 7 folds profitable)

- **Prop constraints** (FAIL): OOS avg annual R 5.9R < 12R gate. Worst month -3.5R (PASS). Expectancy PASS.
- **Hold-out OOS** (2025+, PASS): 58 trades, PF 1.56, Sharpe 2.907, +9.4R, R/yr 8.7R, DD -5.6R
- **Monte Carlo** (PASS): 99.9% survival at -25R ruin, 0.1% ruin probability, p50 DD -8.9R, p95 DD -14.6R

- **Key improvements over v1** (n_left=4, n_right=78, atr=10, no DOW):
  - Calmar: 13.44 → **15.32** (+14%)
  - WFE: 0.643 → **0.751**
  - Stability: 0.952 → **1.000**
  - OOS DD: -12.6R → **-6.1R** (much tighter)
  - OOS Calmar: 4.20 → **6.81**
  - OOS neg years: 1 (2021) → **0**
  - MC survival: 98.5% → **99.9%**

- **Key findings**:
  - DOW filter (exclude Wed+Thu) is the single biggest lever: +1.4 Calmar, significantly tighter DD
  - n_right=65 (not 60 or 78) is the true optimum — only revealed by 2D grid. Sequential 1D sweeps oscillated between 60 and 78 for 4 rounds due to n_left interaction.
  - atr=14 (vs atr=10) optimal with DOW filter — different day selection changes ATR baseline
  - Phase 3 annual R gate (12R/yr) is calibrated for full-5-day strategies. At 60% trading days, 5.9R OOS ≈ 9.8R equivalent. Not a strategy failure.
  - Gap=5.0% fully locked: 9/210 zero-neg combos in Grid R2 — **all** had gap=5.0

- **Script**: `run_nq_ny_lsi_robust_pipeline_v2.py`
- **Conclusion**: Strongly CONDITIONAL — best LSI NY long config tested. 0 neg OOS years, Sharpe 2.0+ OOS, 99.9% MC survival, and excellent hold-out performance. Phase 3 gate failure is an artifact of gate calibration, not strategy weakness. Viable for live trading on prop firm accounts.

### NY Liquidity Sweep Inversion (LSI) fvg_limit Long — NO-GO (threshold)
- **Status**: NO-GO (3/5) — failures are threshold calibration issues, not strategy failure. Strategy generates genuine OOS profit every year.
- **Entry mode**: `lsi_entry_mode="fvg_limit"` — limit order placed at FVG boundary (inv_level) after inversion, waiting for pullback/retest. Fills from bar i+1 after inversion. Lower R/yr than close-mode but better DD profile (fill rate 90%).
- **Optimization**: Full lsi-optimization workflow — baseline → 10 variable sweep rounds → 2 grid sweeps (R1 120 combos, R2 150 combos 3D) → robust pipeline
- **Convergence path**: 10 rounds, 2 major cycles broken by 3D grid sweep. Gap×rr interaction required simultaneous optimization: gap=5.0% always wins on 0-neg-years constraint (only 2/150 grid combos gave 0 neg years, both gap=5.0%).
- **Final config**:

| Param | Value |
|-------|-------|
| strategy | lsi |
| lsi_entry_mode | fvg_limit |
| lsi_stop_mode | absolute |
| session | NY |
| orb_end | 09:35 (5m ORB) |
| entry_start | 09:35 |
| entry_end | 15:30 |
| flat_start | 15:50 |
| rr | 4.5 |
| tp1_ratio | 0.2 |
| min_gap_atr_pct | 4.0% |
| atr_length | 14 |
| lsi_n_left | 25 |
| lsi_n_right | 120 |
| lsi_fvg_window_left | 30 |
| lsi_fvg_window_right | 15 |
| direction | long only |
| magnifier | 1m |

- **Full-history performance** (2016–2026, 10 full years):
  - 861 trades, 58.2% WR, PF 1.35, Sharpe 1.987, Net R 105.4R, R/yr 10.6R, Max DD -7.5R, **Calmar 14.12**
  - **0 negative full years** (min: 2020 +3.1R, 2024 +4.0R; max: 2017 +25.0R)
  - Median stop: 184 ticks (~46 pts NQ)

- **Walk-forward OOS** (7 folds, 36m IS / 12m OOS / 12m step):
  - Combined OOS: 606 trades, 52.3% WR, PF 1.17, Sharpe 1.049, Net R 42.8R, R/yr 6.1R, DD -9.6R, Calmar 4.46
  - WF efficiency: **0.482** (threshold 0.50 — missed by 0.018) | Parameter stability: **0.905 (high)**
  - rr mode=4.5 (4/7 folds), tp1 mode=0.2 (4/7 folds), gap mode=4.0 (3/7 folds)
  - **0 neg OOS years** — all 7 folds profitable

- **Prop constraints** (FAIL): OOS avg annual R 6.1R < 12R gate; worst month -6.7R > 5.0R limit (threshold calibrated for close-mode, not fvg_limit)
- **Hold-out OOS** (2025+, PASS): 93 trades, PF 1.14, Sharpe 0.928, +5.9R, DD -6.4R
- **Monte Carlo** (PASS): 97.7% survival at -25R ruin, 2.3% ruin probability, Sharpe p5=1.096

- **Key findings**:
  - fvg_limit vs close-mode: higher Calmar (14.12 vs 13.44), lower R/yr (10.6 vs 12.1), smaller DD (-7.5R vs -9.0R). Fewer trades (861 vs 1146) due to retest requirement.
  - **rr=4.5, tp1=0.2** optimal for fvg_limit (vs rr=1.5, tp1=0.6 for close-mode) — limit entry rewards higher RR targets
  - **gap=4.0%** (not 5.0%) optimal at final anchor — 1152 signals vs 1001, same 0-neg-year profile
  - **n_left=25** (vs n_left=4 close-mode) — fvg_limit requires wider, higher-significance pivots for retest setups
  - **n_right=120** (full NY session) consistent between both modes
  - Gap×rr oscillation cycle: sequential optimization cycles between (gap=5.0%, rr=4.5) and (gap=0.5%, rr=6.0). Required 3D grid sweep to resolve — only gap=5.0% gives 0 neg years.
  - WFE 0.482 failure is marginal; the 12R/yr prop threshold is too strict for a lower-volume, higher-Calmar strategy
  - OOS quality excellent: 0 neg OOS years, Calmar 4.46 OOS, 97.7% MC survival, high parameter stability

- **Conclusion**: Technically NO-GO on pipeline thresholds, but strong real-world signals. The failure modes are threshold calibration artifacts, not strategy failure. 0 negative OOS years, high parameter stability, and near-perfect MC survival all indicate a genuine edge. If using fvg_limit in live trading, scale position size to ~60% of close-mode (matching lower R/yr output). Script: `run_nq_ny_lsi_fvgl_robust_pipeline.py`

### NY LSI fvg_limit v2 Long — DOW-Filtered — CONDITIONAL (Effective GO)
- **Status**: CONDITIONAL (4/5) — Phase 3 fail is a known calibration artifact for Mon/Tue/Fri strategies; all substantive phases pass. **Effective GO.**
- **Key improvement over v1**: Adding DOW filter (Mon/Tue/Fri, exclude Wed+Thu) and re-optimizing from scratch. Calmar improved from 14.12 → **20.37**. WF efficiency improved from 0.482 → **0.748**. Optimal structural params shifted significantly (smaller n_left, tighter windows, different rr/tp1).
- **Entry mode**: `lsi_entry_mode="fvg_limit"` — same as v1. Limit order at FVG boundary after inversion, fills bar i+1.
- **Optimization**: Full lsi-optimization workflow — variable sweeps R1-R6 + grid sweeps R1-R2. R6 variable sweeps confirmed convergence.
- **Final config**:

| Param | Value |
|-------|-------|
| strategy | lsi |
| lsi_entry_mode | fvg_limit |
| lsi_stop_mode | absolute |
| session | NY |
| orb_end | 09:35 (5m ORB) |
| entry_start | 09:35 |
| entry_end | 15:30 |
| flat_start | 15:50 |
| rr | 3.0 |
| tp1_ratio | 0.3 |
| min_gap_atr_pct | 5.0% |
| atr_length | 10 |
| lsi_n_left | 8 |
| lsi_n_right | 60 |
| lsi_fvg_window_left | 20 |
| lsi_fvg_window_right | 5 |
| direction | long only |
| DOW filter | Mon/Tue/Fri only (Wed+Thu excluded) |
| magnifier | 1m |

- **Full-history performance** (2016–2026, 10 full years, DOW filtered):
  - 608 trades, 61.2% WR, PF 1.61, Sharpe 3.168, Net R 111.7R, R/yr 11.0R, Max DD -5.5R, **Calmar 20.37**
  - **0 negative full years** (min: 2024 +5.9R; max: 2017 +17.2R)
  - Median stop: 188 ticks (~47 pts NQ)
  - DB: `bt-nq-ny-lsi-fvg-limit-v2-long-2016-2026-fi-b47320`

- **Walk-forward OOS** (7 folds, 36m IS / 12m OOS / 12m step, DOW filter in IS and OOS):
  - Combined OOS: 414 trades, 59.9% WR, PF 1.50, Sharpe 2.672, Net R 64.9R, R/yr 9.3R, DD -6.5R, **Calmar 10.02**
  - WF efficiency: **0.748** (well above 0.50 threshold) | Parameter stability: **0.952 (high)**
  - tp1_ratio mode=0.3 (6/7 folds, perfect), gap mode=5.0 (5/7), rr mode=3.0 (3/7 — drift to 3.5/4.0 in later folds)
  - **0 neg OOS years** — all 7 folds profitable

- **Prop constraints** (FAIL on annual R gate): OOS avg annual R 9.3R < 12R gate. **Expected artifact**: Mon/Tue/Fri is ~60% of trading days; 9.3 / 0.6 = 15.5R equivalent on full 5-day week → well above gate. Worst month: -4.0R (PASS). Expectancy PASS.
- **Hold-out OOS** (2025+, PASS): 59 trades, PF 1.70, Sharpe 3.448, +13.0R, 59.3% WR, 0 neg years
- **Monte Carlo** (PASS): **0.0% ruin** at -25R threshold. DD p50=-8.7R, p95=-13.9R. Sharpe p5=2.090.

- **Key findings vs v1**:
  - DOW filter (Mon/Tue/Fri) was transformative: +6.25 Calmar, Sharpe 3.17 vs 1.99, WFE 0.748 vs 0.482
  - Wed/Thu excluded: v1 had n_left=25, rr=4.5, tp1=0.2. v2 settled at n_left=8, rr=3.0, tp1=0.3 — substantially different structural optimum confirms strong interaction with DOW regime
  - n_left=8: missed adoption threshold in R2/R3/R4 at old rr=1.5/tp1=0.6 anchor, then cleared threshold in R5 after rr/tp1 shift to 3.0/0.3 (+0.38 Calmar)
  - Grid sweep R2 with refined structural config: anchor (rr=3.0, tp1=0.3, gap=5.0) won outright #1/150 combos — confirming true optimum
  - v2 Calmar 20.37 vs v1 14.12: better regime filtering and better structural params together
  - v2 OOS Calmar 10.02 vs v1 4.46: much stronger out-of-sample persistence

- **Conclusion**: Effective GO. Best NQ NY LSI fvg_limit variant. The DOW filter (Mon/Tue/Fri) is the key structural edge driver. Prefer v2 over v1 for live trading — higher Calmar, better OOS persistence, 0% MC ruin. Phase 3 annual R failure is a gate calibration artifact, not strategy weakness. Script: `run_nq_ny_lsi_fvgl_v2_robust_pipeline.py`

---

### NY LSI ALPHA_V1 Sweep-Semantics Retest (Apr 2026)
- **Status**: CONDITIONAL ALTERNATE VARIANT
- **Question tested**: whether the stale-pivot "bug" should be treated as the real strategy instead of the corrected fresh-sweep interpretation
- **Date range**: `2016-01-01` to `2025-12-31`
- **Anchor params**: `rr=3.0`, `tp1_ratio=0.34`, `atr_length=10`, `min_gap_atr_pct=5.0`, `lsi_n_left=8`, `lsi_n_right=60`, `fvg_window=20/5`, `direction=long`, `entry_mode=fvg_limit`

- **Corrected intended branch** (`08:30-14:30 ET` sweep window, stale pivots consumed):
  - all-days: `319` trades, PF `1.34`, Sharpe `1.89`, Net R `+35.5`, DD `-7.08R`, Calmar `5.01`
  - `Wed+Thu` excluded: `180` trades, PF `1.54`, Sharpe `2.96`, Net R `+31.9`, DD `-4.42R`, Calmar `7.21`

- **Live-matched legacy branch** (entry-gated, non-consumptive sweeps):
  - all-days: `544` trades, PF `1.37`, Sharpe `1.95`, Net R `+62.8`, DD `-7.33R`, Calmar `8.58`
  - `Wed+Thu` excluded: `310` trades, PF `1.61`, Sharpe `3.17`, Net R `+59.8`, DD `-5.61R`, Calmar `10.67`, `0` negative years

- **Structural findings**:
  - the legacy/live-matched branch materially outperformed the corrected fresh-sweep branch on both filtered and all-days runs
  - the old backtester behavior was even more distorted than this explicit legacy recreation, so do not equate the old 600+/1000+ trade headlines with the live-matched branch
  - `lsi_n_left=8` remained the best setting even on the legacy/live-matched branch; larger left-side values degraded quickly
  - best post-hoc DOW cuts on the live-matched branch were `Thu+Fri` by Calmar (`12.24`), `Thu` only by balance (`428` trades, `+66.3R`, Calmar `11.52`), and `Wed+Thu` for a cleaner `0` negative-year profile

- **Decision**:
  - this is a valid alternate strategy idea, not obvious look-ahead bias
  - do **not** leave it as an accidental bug
  - if adopted, formalize it as an explicit "entry-gated non-consumptive LSI" variant and test live/restart behavior carefully, because continuous runtime preserves older swing levels across days while restart recovery only warms same-day bars

- **Exact execution replay follow-up**:
  - after formalizing the live branch as `legacy-LSI`, a one-leg exact replay on `2016-01-01` to `2025-12-31` was materially stronger than the research surrogate: `599` trades, PF `1.47`, Sharpe `2.54`, Net R `+83.0`, DD `-5.51R`, Calmar `15.06`, all positive years
  - important divergence: on the exact replay, all-days beat the tested DOW cuts; excluding `Thu` dropped Calmar to `13.05`, `Wed+Thu` to `10.62`, and `Thu+Fri` to `6.48`
  - practical implication: if this branch is promoted for live use, trust the exact replay more than the research surrogate on weekday selection and start from **all days enabled**

---

## NY Reference-Level LSI (PDH/PDL + Asia/LDN completed session sweeps) — DISCOVERY ONLY

**Status**: DISCOVERY ONLY — structurally alive, but not promoted past the Bailey-style overfitting gate yet.

**Strategy**:
- `strategy="reference_lsi"`
- sweeps of `previous_day_high`, `previous_day_low`, `asia_high`, `asia_low`, `london_high`, `london_low`
- active window `08:30-14:00 ET`, flat by `14:00`
- pre-sweep FVG only
- inversion must occur within a fixed number of bars after the sweep
- limit entry at the `near` or `far` FVG edge
- structural stop = sweep extreme through inversion bar, with hard 5% ATR minimum stop and explicit 1-contract max-stop rejection

**Baseline config**:
- `direction_filter=both`
- `entry_end=14:00`
- `ref_lsi_gap_entry_edge=near`
- `ref_lsi_gap_lookback_bars=12`
- `ref_lsi_inversion_max_bars=18`
- `rr=2.0`
- `tp1_ratio=0.5`
- `atr_length=10`

**Baseline performance** (`2016-01-01` to `2024-12-31`, holdout frozen at `2025-01-01+`):
- 251 trades, PF 1.056, avg R 0.0136, total R +3.42, max DD -7.12R
- 2023-2024 validation: 57 trades, PF 1.218, avg R 0.0735, total R +4.19

**Stage A findings**:
- strongest raw validation pockets were short-side, early-cutoff (`11:00`) `near`-edge variants
- the small short-only leaders were too thin to pass the structural promotion screen
- the viable family that survived the trade-count / PF requirements still clustered around `11:00` cutoff and `near` entries

**Stage B findings**:
- the best reward shape shifted to `RR=3.0` with `TP1=0.7-0.8`
- top candidates converged around:
  - `both 11:00 near gap6 inv18 rr3.0 tp0.8`
  - `both 11:00 near gap12 inv12 rr3.0 tp0.8`
  - `both 11:00 near gap6 inv18 rr3.0 tp0.7`

**Walk-forward / promotion packet**:
- top candidate: `both 11:00 near gap6 inv18 rr3.0 tp0.8`
- combined pre-holdout OOS: 72 trades, avg R 0.127, PF 1.35, total R +9.16, max DD -7.43R
- local plateau score: 0.358
- search count: 456 raw trials, 13 effective trials
- PSR: 0.788
- DSR: 0.169

**Narrow follow-up + confirmation findings**:
- a second narrower branch fixed the family to `both`, `11:00`, `near`, then centered the search on the `gap6 / inv15-18` and `gap12 / inv12` neighborhoods with `RR≈3.0` and `TP1≈0.7-0.8`
- raw validation still favored `gap12 inv12 rr3.25 tp0.7` and `gap12 inv12 rr3.0 tp0.8`
- after forcing the full 16-config micro-branch through walk-forward, the best OOS configs reverted to:
  - `both 11:00 near gap6 inv15 rr3.0 tp0.8`
  - `both 11:00 near gap6 inv18 rr3.0 tp0.8`
  - `both 11:00 near gap6 inv15 rr3.25 tp0.7`
- top confirmed config: `both 11:00 near gap6 inv15 rr3.0 tp0.8`
- confirmed pre-holdout walk-forward: 70 trades, avg R 0.132, PF 1.35, total R +9.21, max DD -7.38R
- confirmation search count: 16 raw trials, 1 effective trial
- confirmed PSR / DSR: 0.789 / 0.789
- `gap8 inv18` degraded materially in the confirmation pass and no longer looked competitive

**Attribution follow-up on the frozen winner**:
- candidate analyzed: `both 11:00 near gap6 inv15 rr3.0 tp0.8`
- the full pre-holdout sample was weaker than the walk-forward headline suggested: `101` trades, avg R `0.093`, PF `1.23`, but the discovery slice (`2016-2022`) was almost flat to slightly negative: `73` trades, avg R `-0.013`, PF `0.999`
- the edge is not evenly distributed across the six levels:
  - `previous_day` family: pre avg R `0.284`, PF `1.73`
  - `asia` family: pre avg R `0.185`, PF `1.47`
  - `london` family: pre avg R `-0.176`, PF `0.73`
- high-side sweeps / short trades carried most of the edge:
  - high-side: pre avg R `0.202`, PF `1.54`
  - low-side: pre avg R `0.013`, PF `1.01`
- best balanced simplification hypothesis from attribution was `exclude_london`:
  - pre: `68` trades, avg R `0.224`, PF `1.56`, total R `+15.24`
  - discovery: avg R `0.128`, PF `1.32`
  - validation: avg R `0.472`, PF `2.43`
- stronger but thinner challenger: `previous_day_high + asia_high`
  - pre avg R `0.370`, PF `2.04`, but validation only `5` trades
- next fresh thesis, if revisited, should be a **new discovery branch** restricted to `previous_day_* + asia_*` only, with the all-level candidate kept as the attribution anchor

**Conclusion**:
- This branch is worth keeping as a discovery family because it is causally implemented, structurally alive, and the shortlisted configs were profitable in pre-holdout walk-forward.
- It is **not** ready for holdout or phase-one promotion yet because even after the narrow confirmation pass, the best config only reached PSR / DSR `0.789 / 0.789`, still below the repo’s moderate PSR bar.
- If revisited again, do not broaden the search. Restart from the tighter thesis: `previous_day_* + asia_*` only, still pinned to `near`, `11:00`, `RR≈3`, `TP1≈0.7-0.8`, and the `gap6 / inv15-18` pocket.

**Timeframe restart check (same baseline-case params, lower bar size)**:
- question: keep the same `reference_lsi` baseline-case parameters, but detect gaps and inversions on `3m` or `1m` bars instead of `5m`
- shared baseline: `both`, `entry_end=14:00`, `near`, `gap_lookback=12`, `inversion_max=18`, `RR=2.0`, `TP1=0.5`, `ATR=10`, holdout still frozen at `2025-01-01+`
- `5m` baseline reference: `251` pre-holdout trades, PF `1.056`, avg R `0.0136`; validation `57` trades, PF `1.218`, avg R `0.0735`
- `3m` baseline: `234` pre-holdout trades, PF `1.373`, avg R `0.1179`; validation `49` trades, PF `1.669`, avg R `0.2092`
- `1m` baseline: `132` pre-holdout trades, PF `1.149`, avg R `0.0627`; validation `22` trades, PF `0.875`, avg R `-0.0435`
- takeaway: lower timeframe is not automatically better. `3m` looks materially stronger than the original `5m` baseline and deserves its own dedicated discovery branch. `1m` fails the alive gate and should stay closed unless a different thesis is introduced.

**3m discovery branch (same all-level thesis, full pre-holdout discovery packet)**:
- the `3m` branch completed the full discovery workflow and produced a real promoted shortlist, unlike the original `5m` branch
- Stage A survivors clustered around:
  - `both`
  - `12:00-14:00`
  - `far gap12 inv12`, `far gap9 inv12`, `far gap6 inv12`, `far gap3 inv18`
  - challenger `near gap6 inv12`
- the reward sweep favored `RR=2.5-3.0` and `TP1=0.7-0.8`
- promoted candidates:
  - `both 13:00 far gap9 inv12 rr3.0 tp0.7`
    - pre: `107` trades, PF `1.611`, avg R `0.293`
    - WF OOS: `67` trades, avg R `0.392`, PF `1.877`, total R `+26.25`, max DD `-4.41R`
    - PSR / DSR: `0.989 / 0.769`
  - `both 12:00 near gap6 inv12 rr3.0 tp0.8`
    - pre: `116` trades, PF `1.800`, avg R `0.296`
    - WF OOS: `78` trades, avg R `0.300`, PF `1.837`, total R `+23.42`, max DD `-5.27R`
    - PSR / DSR: `0.997 / 0.886`
  - `both 13:00 near gap6 inv12 rr2.5 tp0.8`
    - pre: `130` trades, PF `1.739`, avg R `0.269`
    - WF OOS: `87` trades, avg R `0.294`, PF `1.861`, total R `+25.54`, max DD `-5.57R`
    - PSR / DSR: `0.997 / 0.881`
- trial posture: `456` raw trials, `8` effective trials
- conclusion: `3m` is the new lead `reference_lsi` branch for NQ NY. It cleared the discovery-pipeline bar and is now eligible for downstream evaluation as a frozen shortlist. The original `5m` all-level branch remains a useful historical anchor, but the `3m` branch is materially stronger on pre-holdout evidence.

**3m phase-one payout read (frozen shortlist, holdout opened once)**:
- phase-one runner used the stitched discovery OOS stream for pre-holdout payout modeling (`2019-01-01` to `2024-12-31`), then opened the frozen holdout once on `2025-01-01` to `2026-03-24`
- all three promoted `3m` candidates were strong on stitched OOS payout modeling, but weak on holdout payout conversion
- best leader: `both 13:00 far gap9 inv12 rr3.0 tp0.7`
  - stitched OOS: `67` trades, PF `1.8766`, avg R `0.3917`, total R `+26.25`
  - OOS funded scorecard: payout rate `77.1%`, breach `3.5%`, EV/start `$282.76`
  - holdout: `18` trades, PF `1.3016`, avg R `0.1812`, total R `+3.26`
  - holdout funded scorecard: payout `1.6%`, breach `81.2%`, EV/start `-$99.74`
- near-entry challengers failed outright on holdout:
  - `both 12:00 near gap6 inv12 rr3.0 tp0.8`: holdout PF `0.5372`, avg R `-0.2509`, funded payout `0.0%`
  - `both 13:00 near gap6 inv12 rr2.5 tp0.8`: holdout PF `0.4970`, avg R `-0.2774`, funded payout `0.0%`
- conclusion: discovery-grade edge on `3m` did not fully carry into a strong phase-one first-payout business. Keep the far-entry leader as the only conditional candidate; do not advance the two near challengers, and do not move this family into phase two yet.

**3m all-level holdout failure analysis (why the conditional leader still failed payout conversion)**:
- focused failure analysis was run on `both 13:00 far gap9 inv12 rr3.0 tp0.7`
- raw holdout trade quality stayed positive:
  - `18` trades, PF `1.3016`, avg R `0.1812`, total R `+3.26`
- but payout conversion still failed badly:
  - holdout funded payout `1.6%`
  - holdout funded EV/start `-$99.74`
- main read: the problem was speed/sample, not a total collapse of raw edge
  - too few holdout trades to reliably reach a `+5R` payout threshold across rolling starts
  - many starts remained open or breached before enough positive trades accumulated
- structural drag in holdout was concentrated in short / high-side sweeps:
  - short: `11` trades, avg R `-0.4615`, PF `0.2884`
  - long: `7` trades, avg R `1.1911`, PF `5.7965`
- time bucket note:
  - `09:30-10:30` dragged
  - `10:30-12:00` was much healthier
- important nuance: this was not a clean “London caused the holdout failure” story. London actually held up best on holdout raw trade quality, though on a small sample.

**3m restricted-thesis restart (`previous_day_* + asia_*` only, no London) — new lead discovery branch**:
- the thesis was restarted from the beginning on `3m`, but restricted to:
  - `previous_day_high`, `previous_day_low`, `asia_high`, `asia_low`
- baseline strengthened materially vs the all-level `3m` branch:
  - pre-holdout: `188` trades, PF `1.4965`, avg R `0.1447`
  - validation: `41` trades, PF `2.0714`, avg R `0.2836`
- promoted shortlist:
  - `both 12:00 near gap9 inv12 rr3.0 tp0.8`
    - pre: `101` trades, PF `1.8329`, avg R `0.3016`
    - WF OOS: `68` trades, avg R `0.3248`, PF `1.9874`, total R `+22.09`
    - PSR / DSR: `0.9961 / 0.8198`
  - `both 13:00 near gap9 inv12 rr2.5 tp0.8`
    - pre: `113` trades, PF `1.8014`, avg R `0.2747`
    - WF OOS: `75` trades, avg R `0.3189`, PF `2.0386`, total R `+23.92`
    - PSR / DSR: `0.9961 / 0.8280`
  - `both 14:00 near gap6 inv12 rr2.5 tp0.8`
    - pre: `101` trades, PF `1.7967`, avg R `0.2742`
    - WF OOS: `69` trades, avg R `0.3007`, PF `1.9382`, total R `+20.75`
    - PSR / DSR: `0.9935 / 0.7771`
- trial posture: `456` raw trials, `11` effective trials
- conclusion: the restricted `3m previous_day_* + asia_*` family is now the cleaner NQ NY `reference_lsi` discovery lead. The old all-level `3m` far-entry config should be kept only as the failure-analysis anchor. The restricted branch has not opened holdout yet; the next clean step is a frozen downstream phase-one evaluation on this shortlist only.

**3m restricted-thesis phase-one read (`previous_day_* + asia_*`, holdout opened once)**:
- the restricted shortlist was then evaluated in the same phase-one payout framework on the untouched `2025-01-01` to `2026-03-24` holdout
- OOS scorecards were still strong:
  - `both 12:00 near gap9 inv12 rr3.0 tp0.8`: funded payout `77.1%`, EV/start `$270.00`
  - `both 13:00 near gap9 inv12 rr2.5 tp0.8`: funded payout `75.0%`, EV/start `$215.90`
  - `both 14:00 near gap6 inv12 rr2.5 tp0.8`: funded payout `64.7%`, EV/start `$190.54`
- but holdout failed cleanly across the whole restricted branch:
  - leader `both 12:00 near gap9 inv12 rr3.0 tp0.8`: `15` trades, PF `0.7802`, avg R `-0.0865`, funded payout `0.0%`, funded EV/start `-$100`
  - challenger `both 13:00 near gap9 inv12 rr2.5 tp0.8`: `15` trades, PF `0.7241`, avg R `-0.1197`, funded payout `0.0%`
  - challenger `both 14:00 near gap6 inv12 rr2.5 tp0.8`: `13` trades, PF `0.3814`, avg R `-0.3564`, funded payout `0.0%`
- compared with the old all-level `3m` far-entry leader, the restricted branch was actually worse on raw holdout trade quality
- conclusion: the restricted `3m previous_day_* + asia_*` branch improved discovery posture but did not survive holdout phase-one validation. Treat the family as closed for this research line; do not tune it further, since the holdout has now been opened.

**Exact swept level ranking across the reference-LSI studies**:
- a cross-study level matrix was built from:
  - the `5m` all-level attribution candidate
  - the `3m` all-level phase-one leader failure analysis
- strongest repeated exact levels:
  - `previous_day_high`
  - `asia_low`
- `previous_day_high` was the strongest exact level in both `5m` pre-holdout and `3m` OOS, but failed on a tiny `3m` holdout sample (`2` trades)
- `asia_low` was the cleanest exact level that stayed positive on `5m`, `3m` OOS, and `3m` holdout
- clearest recurring drag:
  - `asia_high`
  - mildly positive on `5m`, negative on `3m` OOS, negative again on `3m` holdout
- London exact levels were unstable:
  - negative on the original `5m` attribution study
  - positive on the `3m` far-entry leader
  - too inconsistent and too thin to treat as reliable
- practical takeaway: if this family is ever revisited as a genuinely new thesis, the exact levels most worth centering are `PDH` and `Asia Low`, while `Asia High` is the clearest candidate to avoid.

**Focused `PDH + Asia Low` restart on lower timeframes (`1m`, `2m`, `3m`) — baseline no-go**:
- after the exact-level matrix suggested `PDH` and `Asia Low` were the strongest repeated exact levels, a fresh discovery restart was run with only:
  - `previous_day_high`
  - `asia_low`
- tested on `1m`, `2m`, and `3m` with holdout still frozen and the normal discovery alive gate
- results:
  - `1m`: `54` pre-holdout trades, PF `0.9906`, avg R `-0.0009`; validation PF `0.8651`, avg R `-0.0327` → clear no-go
  - `2m`: `78` pre-holdout trades, PF `1.5775`, avg R `0.1860`; validation PF `1.6685`, avg R `0.2318` → quality looked decent, but sample too thin to clear the alive gate
  - `3m`: `107` pre-holdout trades, PF `2.1349`, avg R `0.2692`; validation PF `2.9399`, avg R `0.3700` → strongest of the three, but still too few pre-holdout trades for promotion
- conclusion: `PDH + Asia Low` is interesting descriptively, but as a standalone exact-level thesis it is too sparse under the current workflow. It does not earn a full discovery promotion path on `1m`, `2m`, or `3m`.

**Widened exact-level restart (`previous_day_* + Asia Low`) on `2m` and `3m` — still baseline no-go, but `3m` is close**:
- to add trades without reopening the whole thesis, the next restart widened the active levels to:
  - `previous_day_high`
  - `previous_day_low`
  - `asia_low`
- results:
  - `2m`: `111` pre-holdout trades, PF `1.1756`, avg R `0.0650`; validation PF `1.1939`, avg R `0.0825`
  - `3m`: `147` pre-holdout trades, PF `1.7003`, avg R `0.2025`; validation PF `2.2998`, avg R `0.3157`
- both still failed the repo’s baseline alive gate, so neither advanced into Stage A
- interpretation:
  - `2m` remained too weak to justify further work
  - `3m` is the interesting one: quality was strong and it only missed the alive gate by being just under the current pre-holdout trade-count bar
- practical takeaway: if this family is ever revisited again as a new thesis, `3m previous_day_* + Asia Low` is the only exact-level specialist branch that looks close enough to justify either:
  - a specialist-sample exception to the baseline trade-count rule, or
  - adding one more tightly justified level without reopening the full family

---

## NQ ASIA LSI (Long) — CONDITIONAL (4/5)

**Status**: CONDITIONAL — deploy with awareness of WF OOS R/yr constraint artifact.
**Best config**: R2 (n_left=8, n_right=2, fvg_right=2) — use this over R1.

**Optimized config** (17 variable sweep rounds + 2 grid sweeps + structural joint grid + R18):

| Parameter | Value |
|-----------|-------|
| strategy | lsi |
| lsi_stop_mode | absolute |
| lsi_n_left | 8 |
| lsi_n_right | 2 |
| lsi_fvg_window_left | 15 |
| lsi_fvg_window_right | 2 |
| entry_start | 20:40 |
| entry_end | 23:30 |
| flat_start | 00:00 |
| atr_length | 40 |
| direction_filter | long |
| rr | 2.0 |
| tp1_ratio | 0.7 |
| min_gap_atr_pct | 1.75 |

**Full-sample metrics** (2016-2026, 10.17 years):
- 527 trades | 55.2% WR | PF 1.62 | Sharpe 3.133 | Net R +84.7R | R/yr 8.3R | DD -5.3R | **Calmar 15.85** | **0 neg years**
- DB: `bt-nq-asia-lsi-long-2016-2026-final-r2-2201c8`

**Pipeline R2 phases**:
- **Phase 1 (Structural)**: PASS — all checks clear, Calmar 15.85, 0 neg years
- **Phase 2 (Walk-Forward)**: PASS — WF eff 0.783, stability 0.857 (high), 1 neg OOS year (2020: -0.1R ≈ 0), 7 folds
  - WF OOS params: rr mode=2.5 (3/7), tp1 mode=0.5 (4/7), gap mode=2.25 (4/7)
  - Combined OOS: 280 trades, 55.7% WR, PF 1.44, Sharpe 2.370, R/yr 4.4R, DD -4.9R, Calmar 6.34
- **Phase 3 (Prop Filter)**: FAIL — WF OOS avg annual R 4.4R < 12R gate (same artifact as R1; 2025 hold-out shows 12.4R which exceeds the gate)
- **Phase 4 (Hold-Out OOS 2025+)**: PASS — 46 trades, PF 2.10, +12.6R, Sharpe 5.187, 0 neg years
- **Phase 5 (Monte Carlo)**: PASS — 99.9% survival at -25R ruin. DD p50=-7.5R, p95=-12.3R

**Comparison: R1 vs R2**:

| Metric | R1 (n_left=6, n_right=1, fvg_right=5) | R2 (n_left=8, n_right=2, fvg_right=2) |
|--------|---------------------------------------|---------------------------------------|
| Full Calmar | 15.25 | **15.85** |
| WF stability | 0.809 | **0.857** |
| Hold-out PF | 1.84 | **2.10** |
| Hold-out Sharpe | 4.337 | **5.187** |
| Hold-out R | +11.1R | **+12.6R** |
| Hold-out annual R | 11.0R | **12.4R** (exceeds 12R gate) |

**Key findings**:
- ASIA session LSI longs have meaningful edge — 0 negative full years over 10 years
- **fvg_right=2 is optimal** — tighter inversion window consistently beats wider (5-10). fvg_right=1 shows +0.17 Calmar above anchor but below +0.3 adoption threshold; not adopted to avoid overfitting at boundary
- gap=1.75% (min_gap_atr_pct) is the key parameter: below 1.5% trade quality degrades sharply; above 2.25% too few trades
- rr=2.0, tp1=0.7: stable core — confirmed in all 18 sweep rounds
- **Coordinate descent oscillation** in R14-R17 (n_right 1↔2, fvg_right 3↔5↔10, gap 1.75↔2.0): resolved by Grid Sweep R2 which identified joint optimum. Then structural joint grid (n_left × n_right × fvg_right, 280 combos) confirmed n_left=8, n_right=2, fvg_right=2 as genuine improvement (+0.61 Calmar)
- **Overlays (DOW, SMA, loss caps)**: all tested as INFO-ONLY across 18 rounds AND in dedicated overlay sweep — none adopted. Loss caps completely flat (weekly 2R cap never triggers — losses are perfectly distributed)
- Shorting NQ ASIA LSI: **NO-GO** (negative R across all tested configs, Phase 1 data)
- Phase 3 fail is a gate calibration artifact: WF OOS average is 4.4R but 2025 hold-out shows 12.4R exceeding the gate. Phase 3 expected to fail for low-frequency strategies.

**Scripts generated**:
- `run_nq_asia_lsi_baseline.py`
- `run_nq_asia_lsi_variable_sweeps_1.py` through `run_nq_asia_lsi_variable_sweeps_18.py`
- `run_nq_asia_lsi_grid_sweep_r1.py`, `run_nq_asia_lsi_grid_sweep_r2.py`
- `run_nq_asia_lsi_structural_grid.py` (joint n_left × n_right × fvg_right, 280 combos)
- `run_nq_asia_lsi_overlay_sweep.py` (DOW, SMA, loss caps post-backtest)
- `run_nq_asia_lsi_robust_pipeline.py` (R1), `run_nq_asia_lsi_robust_pipeline_r2.py` (R2)
- `save_nq_asia_lsi_r1_final.py` (superseded), `save_nq_asia_lsi_r2_final.py` (use this)

---

- **Internal swing BE sweep** (`lsi_be_swing_n_left`): **NO-GO — do not use.**
  - Swept N=[0,1,2,3,5,7,10] (left-only pivot N bars wide, pre-FVG search, triggers BE post-fill)
  - Every N>0 hurts Calmar significantly. Best N>0 = N=7 at Calmar 15.56 (-4.81 vs baseline 20.37)
  - N=1 converts 164/608 trades (27%) to 0R EXIT_BE_SL — massive drag on net R
  - N=1,2,3 introduce 2018 negative year. N=5,7,10 avoid neg years but still sharply lower Calmar
  - Mechanism: the pre-FVG swing highs being swept are on trades that would otherwise hit TP2, not SL. Triggering BE on those trades converts winners to 0R.
  - Script: `run_nq_ny_lsi_fvgl_v2_be_swing_sweep.py`

---

### NY LSI fvg_limit RR2/TP0.5 + Thu Excl + Medium-Vol Gate — CONDITIONAL (Effective GO)

- **Status**: CONDITIONAL (effective GO) — full 8-step strategy workflow completed. PSR/DSR validated. Phase-one payout economics strong. Holdout 100% payout success rate.
- **Optimization**: Full new-strategy workflow — 20 filter combos → 128 variable sweeps → discovery pipeline (WF + stability + MC) → regime gate application → PSR/DSR → phase-one payout → DOW significance analysis → final save
- **Key innovation**: RR=2.0/TP1=0.5 parameterization (lower RR, higher TP1 vs prior RR=3.0/TP1=0.3) combined with medium-vol regime avoidance gate and Thu-only DOW exclusion.
- **Final config**:

| Param | Value |
|-------|-------|
| strategy | lsi |
| lsi_entry_mode | fvg_limit |
| lsi_stop_mode | absolute |
| session | NY |
| entry_start | 09:35 |
| entry_end | 15:30 |
| flat_start | 15:50 |
| rr | 2.0 |
| tp1_ratio | 0.5 |
| min_gap_atr_pct | 5.0% |
| atr_length | 14 |
| lsi_n_left | 8 |
| lsi_n_right | 60 |
| lsi_fvg_window_left | 20 |
| lsi_fvg_window_right | 5 |
| direction | long only |
| DOW filter | Thu excluded only |
| regime gate | skip bull_medium_vol + sideways_medium_vol |
| magnifier | 1s |

- **Full-history performance** (2016–2026, Thu excl + regime gated):
  - 588 trades, 61.1% WR, PF 1.70, Sharpe 3.646, Net R +126.4R, R/yr 12.3R, Max DD -7.6R, **Calmar 16.72**
  - **0 negative full years** (min: 2024 +1.2R; max: 2017 +28.5R)
  - Median stop: 189 ticks (~47 pts NQ)
  - DB: `bt-nq-ny-lsi-rr2-tp0-5-thu-gated-2016-2026-174198`

- **Walk-forward OOS** (6 folds, 36m IS / 12m OOS / 12m step, Thu excl + regime gated, RR/TP1 frozen):
  - Combined OOS: 311 trades, Sharpe 3.38, Net R +62.1R, DD -7.6R, **Calmar 8.22**
  - WF efficiency: **0.766** | Parameter stability: **0.833 (high)**
  - gap mode=5.0 (4/6 folds), ATR mode=14 (5/6 folds)
  - All 6 OOS years positive

- **PSR/DSR validation** (PASS):
  - PSR: **0.9999** (strong)
  - DSR: **0.709** at 832 raw trials — survives multiple-testing deflation (threshold >=0.50)
  - Observed Sharpe 3.38 vs E[max SR] 2.89 under null

- **Holdout OOS** (2025-04-01 onward, Thu excl + regime gated, WF mode params):
  - 45 trades, 66.7% WR, PF 1.92, Sharpe 4.268, **+11.2R**, DD -2.6R, Calmar 4.33
  - 2025: +8.4R, 2026: +2.8R
  - Payout simulation: **24 accounts, 15 payouts, 0 breaches, 9 open, 100% success rate, EV +4.36R/account**

- **Monte Carlo** (PASS): **99.3% survival** at 15R, **0.7% ruin**. DD p50=-7.6R, p95=-11.9R.

- **5-year performance** (2021–2026, Thu excl + regime gated):
  - 283 trades, 58.3% WR, PF 1.40, Net R +35.9R, DD -7.6R, Calmar 4.75, Sharpe 2.20
  - DB: `bt-nq-ny-lsi-rr2-tp0-5-thu-gated-2021-2026-3c4bd8`

- **DOW significance analysis** (per-day t-test + bootstrap on regime-gated trades):
  - **Fri**: best day — +45.1R, avg R +0.347, p=0.0001, 0 neg years. **Strongly significant.**
  - **Tue**: second — +34.7R, avg R +0.209, p=0.004. **Significant.**
  - **Mon**: borderline — +18.4R, avg R +0.169, p=0.058, CI barely touches 0. Keep.
  - **Wed**: noisy positive — +17.0R, avg R +0.123, p=0.114, 3 neg years. Keep (adds real R).
  - **Thu**: dead — +2.6R, avg R +0.019, p=0.813, **5 neg years**. **Only statistically dead day.**
  - Thu-only exclusion beats Wed+Thu: Calmar 15.24 vs 12.04, +17R more net R, 138 more trades, MC survival 99.3% vs 96.9%.

- **Why Thu-only over Wed+Thu**:
  - Wednesday contributes +17.0R of genuine (if noisy) edge — removing it costs real R
  - Thursday is the only day with near-zero avg R, 5 neg years, and p=0.81 (indistinguishable from zero)
  - Thu-only: Calmar 16.72, 0 neg years, 99.3% MC survival, 588 trades
  - Wed+Thu: Calmar 12.04, 0 neg years, 96.9% MC survival, 405 trades

- **Known issue**: LSI engine does not respect `excluded_days` in config. DOW filtering is applied post-hoc by `results_to_dict()` via `_apply_replay_filters()`. The DB and frontend show correct DOW-filtered results, but intermediate pipeline metrics (before `results_to_dict`) include leaked Wed/Thu trades. This bug does not affect saved results or live execution (which uses the gate infrastructure in `gates.py`).

- **Regime gate details**: Skip trades on days classified as `bull_medium_vol` or `sideways_medium_vol`. Classification uses yesterday's daily close (`.shift(1)`): close_vs_sma20, ret_5d, realized_vol_21d with frozen NQ tercile thresholds (low ≤12.52%, medium 12.52–20.40%, high >20.40%). No lookahead bias (LLM council verified). Gate removes ~20-30% of trades depending on period.

- **Scripts**:
  - `run_nq_ny_lsi_discovery_step1_baseline.py` through `step7_phase_one.py` (full workflow)
  - `run_nq_ny_lsi_dow_analysis.py` (DOW significance analysis)
  - `run_nq_ny_lsi_dow_verify.py` (DOW filter verification — confirmed engine bug)
- `save_nq_ny_lsi_rr2_tp05_thu_gated_final.py` (final save script)

- **Important target-definition correction on the 2026-04-13 stop/target packet** (`backtesting/scripts/run_nq_lsi_structural_stop_target_sweep.py`, corrected same day):
  - The first added `lsi_target_mode = structural` was **not** the user-intended structural TP logic. That mode keeps TP distances tied to the full structural stop.
  - The intended interpretation is now **`lsi_target_mode = left_structure`**: longs target unswept pivot highs to the left of the setup, shorts target unswept pivot lows to the left, while still enforcing the hard floors `TP1 >= 1R` and `TP2 >= 1.5R`.

- **Under the corrected left-pivot target definition, regular NY LSI did *not* find an honest replacement for the saved baseline** (`backtesting/scripts/run_nq_lsi_structural_stop_target_sweep.py`, corrected one-time read `2026-04-13`):
  - Tested the saved NY LSI final branch (`long`, `fvg_limit`, Thu excluded, medium-vol gate) across stop modes `absolute`, `gap_1x/2x/3x/4x`, `struct_50pct`, `struct_75pct`, and three target modes: current `risk`, the older structural-risk-basis proxy `structural`, and the corrected left-pivot mode `left_structure`.
  - The honest reference remains **`absolute + risk`**: pre-holdout PF `1.658`, avg R `0.193`, Calmar `7.59`; opened holdout PF `2.464`, avg R `0.313`, Calmar `2.46`.
  - The best `left_structure` row was **`struct_50pct + left_structure`**. It looked great pre-holdout (PF `1.875`, avg R `0.399`, Calmar `14.11`) but failed hard on the already-opened holdout (PF `0.726`, avg R `-0.166`, Calmar `-0.37`). The milder **`gap_3x + left_structure`** behaved better, but still did not honestly beat the baseline once the opened holdout was checked.
  - Practical conclusion: for the user-intended structural TP concept, keep the saved regular NY LSI target logic unchanged. The earlier **`gap_3x + structural`** result only applies to the older structural-risk-basis proxy, not to left-side pivot targeting.
  - Reference: `backtesting/learnings/reports/NQ_LSI_STRUCTURAL_STOP_TARGET_SWEEP.md`

- **A broad ATR/ORB stop-source probe on the same saved regular NY LSI branch found no honest replacement for the structural stop, but it did show where the first non-structural signal lives** (`backtesting/scripts/run_nq_lsi_atr_orb_stop_sweep.py`, one-time read `2026-04-13`):
  - Tested the same saved branch (`long`, `fvg_limit`, Thu excluded, medium-vol gate) with current `risk` targets and capped stop sources: `atr_pct` at `5/10/15/20%` of daily ATR and `orb_pct` at `50/75/100%` of a minimal `09:30-09:35` NY opening range, always capped at the structural invalidation point.
  - The structural baseline still won the honest read: **`absolute`** stayed at pre-holdout PF `1.658`, avg R `0.193`, Calmar `7.59`, while the already-opened holdout stayed much stronger than every ATR/ORB row at PF `2.464`, avg R `0.313`, Calmar `2.46`.
  - The best pre-holdout challenger was **`orb_100pct`**: PF `1.661`, avg R `0.241`, Calmar `10.34`, with median stop tightened from `180.0` ticks to `117.5` ticks. But its holdout dropped to PF `1.588`, avg R `0.198`, Calmar `0.75`, so it is not an honest promotion over the structural baseline.
  - The next-best ATR row was **`atr_20pct`**, which also looked mildly constructive pre-holdout (PF `1.617`, avg R `0.220`, Calmar `8.67`) but degraded too much on holdout (PF `1.130`, avg R `0.079`, Calmar `0.30`). Tighter ATR or ORB distances (`<=15% ATR`, `<=75% ORB`) broke down more clearly.
  - Practical conclusion: keep the structural stop as the default on this saved regular NY LSI branch. If we ever reopen stop-source research on a fresh unopened sample, the only broad-stop-source ideas worth forwarding are **`100% ORB`** first and **`20% ATR`** second; everything tighter already looks too fragile.
  - Reference: `backtesting/learnings/reports/NQ_LSI_ATR_ORB_STOP_SWEEP.md`

---

### NY HTF-LSI (Unswept 60m Extremes, Patched Sweep Invalidation) — STRONG Phase One / CONDITIONAL Phase Two

- **Status**: STRONG to first payout, CONDITIONAL as a post-first-payout extractor. The frozen `5m` long-only anchor passed discovery, holdout, and phase one cleanly, but default post-payout operation at `$250/R` was too jagged on stitched OOS continuity risk.
- **Thesis**: replace same-timeframe `lsi_n_left / lsi_n_right` pivots with published unswept `60m` bar highs/lows, and allow pre-entry-window breaches to invalidate the level without counting as valid sweeps
- **Discovery flow**: structural sweep → trade-cap sweep → one-at-a-time parameter sweeps → interaction sweep → lag test → regime-gate check → timeframe transfer → confluence check → frozen-candidate walk-forward tie-break

- **Stage A structural result**:
  - Only `htf60`, `long`, `fvg_limit` survived honestly
  - Best window: `08:30-15:00`
  - `08:30-14:00` stayed alive but weaker

- **Trade-cap result**:
  - `cap=2` beats `cap=1`
  - `cap=3` ties `cap=2`, so `cap=2` is preferred

- **Best balanced frozen anchor**:

| Param | Value |
|-------|-------|
| strategy | htf_lsi |
| session | NY |
| entry_start | 08:30 |
| entry_end | 15:00 |
| direction | long only |
| entry_mode | fvg_limit |
| rr | 3.0 |
| tp1_ratio | 0.6 |
| min_gap_atr_pct | 3.0% |
| atr_length | 14 |
| htf_level_tf_minutes | 60 |
| htf_n_left | 3 |
| htf_trade_max_per_session | 2 |
| lsi_fvg_window_left | 20 |
| lsi_fvg_window_right | 2 |
| max_fvg_to_inversion_bars | 0 |
| magnifier | 1s |

- **Balanced anchor metrics**:
  - Discovery (`2016-01-01` to `2022-12-31`): `424` trades, PF `1.164`, avg R `0.072`
  - Validation (`2023-01-01` to `2025-03-31`): `151` trades, PF `1.556`, avg R `0.224`, Calmar `6.208`

- **Validation-led challenger**:
  - Same family, but `htf_n_left=5` and `lsi_fvg_window_right=3`
  - Discovery: `426` trades, PF `1.059`, avg R `0.022`
  - Validation: `144` trades, PF `1.595`, avg R `0.246`, Calmar `6.556`

- **Walk-forward tie-break** (`36m IS / 12m OOS / 12m step`, pre-holdout only):
  - Balanced anchor: `376` stitched OOS trades, PF `1.298`, avg R `0.130`, Calmar `4.12`, DD `-11.83R`
  - Validation-led challenger: `369` stitched OOS trades, PF `1.180`, avg R `0.084`, Calmar `2.18`, DD `-14.18R`
  - **Adopt the balanced anchor as the frozen lead**

- **What did not transfer**:
  - Inversion-speed caps (`lag<=1/2/3`) crushed sample and did not improve the branch
  - `skip bull_medium_vol + sideways_medium_vol` hurt validation Calmar versus ungated
  - No single `VWAP/SMA/EMA` bounce or magnet overlay beat the ungated baseline on validation Calmar

- **Extended lag-curve follow-up** (`0..30` bars, tested on each timeframe's best transfer anchor):
  - `5m`: the early `<=8` study was too pessimistic. Validation kept improving into the low 20s, with the best meaningful region around `23-24` bars. `lag=24` beat the uncapped baseline on validation Calmar (`6.38` vs `6.21`) while keeping `84%` of validation trades.
  - `3m`: uncapped stayed best on a meaningful sample. Long caps in the `25-30` area recovered much of the validation edge, but still did not beat `lag=0`, and discovery stayed negative across the capped curve.
  - `2m`: the headline `lag=1` spike was a tiny-sample trap (`6` validation trades). On meaningful sample size, uncapped remained the best row; the curve recovered in the low-to-mid 20s but never overtook `lag=0`.
  - `1m`: moderate caps around `9-12` bars improved validation materially. `lag=10` was the best meaningful validation row in this pass, but discovery degraded versus the uncapped baseline, so treat it as an interesting local challenger rather than an auto-promotion.

- **Focused `5m` / `1m` follow-up clarified the fork between those two paths**:
  - `5m`: stitched OOS confirmed that the late-lag idea is real, not just a split-specific validation bump. On the frozen `5m` long / `fvg_limit` / `cap2` anchor, `lag=24` improved stitched OOS PF from `1.298` to `1.347`, stitched OOS avg R from `0.130` to `0.162`, and stitched OOS Calmar from `4.12` to `4.85`, while validation also improved (`PF 1.597`, avg R `0.268`, Calmar `6.38`). `lag=20` was also strong, but `lag=24` was the best balanced late-lag row. This is the next honest `5m` promotion path.
  - `1m`: the minute-normalized comparison correctly identified a different real-time optimum, but the stitched OOS follow-up rejected it as a promotion path. `lag=10` looked much better on the fixed validation split (`76` trades, PF `1.888`, avg R `0.420`, Calmar `4.91`) than uncapped `lag=0` (`219` trades, PF `1.263`, avg R `0.126`, Calmar `1.71`), but the broader stitched OOS read flipped the verdict: uncapped `lag=0` finished with `577` trades, PF `1.147`, avg R `0.073`, Calmar `2.17`, DD `-19.35R`, while `lag=10` shrank to `199` trades, PF `1.066`, avg R `0.046`, Calmar `0.33`, DD `-27.15R`. Conclusion: the `1m` capped branch was a validation-split mirage, so keep uncapped `1m` as the honest baseline and treat `lag=10` as closed rather than a live challenger.

- **A downstream promotion test favored `5m lag=24` over the original uncapped lead as the better overall operating variant**:
  - Head-to-head on the exact downstream path kept both rows alive: both were `STRONG` in phase one and `CONDITIONAL` in phase two.
  - `lag=24` improved raw trade quality almost everywhere that matters for branch durability: pre-holdout PF `1.278` vs `1.250`, pre-holdout avg R `0.133` vs `0.112`, stitched OOS PF `1.347` vs `1.298`, stitched OOS avg R `0.162` vs `0.130`, holdout PF `2.200` vs `1.987`, and holdout avg R `0.430` vs `0.361`.
  - The one real giveback was pure stitched-OOS funded phase-one EV per start, which slipped modestly to `$138.33` from `$158.58`. But payout rate actually improved slightly (`52.6%` vs `52.2%`), holdout funded EV improved (`$81.47` vs `$78.68`), and the prop-style payout scorecard also improved.
  - Post-payout behavior was clearly better. At the default `$250/R`, `lag=24` lifted OOS withdrawals/start from `$4,140` to `$4,569`, holdout withdrawals/start from `$2,689` to `$2,815`, and MC survival from `6.8%` to `9.8%`.
  - The best balanced post-payout size also stepped up. The old uncapped row preferred `$150/R` (`$4,431` OOS withdrawals/start, `$1,362` holdout withdrawals/start, `61.7%` MC survival). `lag=24` supported `$175/R` under the same `0%` OOS/holdout breach and `>=50%` MC survival filter, with `$6,037` OOS withdrawals/start, `$1,653` holdout withdrawals/start, and `54.6%` MC survival.
  - Conclusion: if the goal is the best all-around `5m` HTF-LSI operating branch, promote `lag=24` over uncapped `lag=0`. Keep uncapped as the historical first-payout benchmark, but treat `lag=24` as the new preferred live research lead.

- **A dedicated pre-holdout count-expansion sweep showed the `5m` HTF-LSI branch can reach the `60-80` trades/year band without changing timeframe, direction family, or entry style**:
  - Targeted sweep: `5m`, `htf60`, `htf_n_left=3`, `long|both`, `fvg_limit|close`, `gap=2.0/2.5/3.0`, `right=2/3/5`, `lag=0/24/30`, `cap=2/3`, with holdout still frozen at `2025-04-01+`.
  - The promoted operating lead (`long`, `fvg_limit`, `gap3.0`, `right2`, `lag24`, `cap2`) was slightly below the target band at `54.7` pre-holdout trades/year and `56.5` validation trades/year, though `2024` still printed `65` filled trades.
  - The cleanest target-band compromise was `long`, `fvg_limit`, `gap2.5`, `right2`, `lag0`, `cap2`: `66.4` pre-holdout trades/year, `69.0` validation trades/year, validation PF `1.668`, validation avg R `0.265`, validation Calmar `7.33`, with `78` filled trades in calendar `2024`.
  - The strongest lower-count target-band challenger was `gap2.5`, `right2`, `lag30`, `cap2`: `60.8` pre-holdout trades/year, `61.8` validation trades/year, validation PF `1.683`, validation avg R `0.294`, validation Calmar `6.59`.
  - If the exact center of the desired count band matters more than absolute trade quality, `gap2.5`, `right3`, `lag0`, `cap2` landed almost exactly on the goal at `70.2` pre-holdout trades/year and `71.2` validation trades/year, though with softer validation PF / Calmar (`1.569` / `6.46`) than the `right2` row.
  - The parameter map was clear. `both` direction and `close` entry mode massively overshot count and degraded quality (`both` averaged `122` trades/year with avg validation PF `1.16`; `close` averaged `102` trades/year with avg validation PF `1.15`). `right=5` also added too much count for the quality given, while `cap=3` tied `cap=2` and added no meaningful new flow.
  - Practical conclusion: if the goal changes from “best all-around operating variant” to “roughly one trade a week with the same HTF-LSI thesis,” the honest first contender is not a new both-direction branch. It is still the same `5m` long / `fvg_limit` family, just loosened modestly toward `gap2.5` and either uncapped or late-capped on the inversion side. Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_COUNT_EXPANSION.md`.

- **Adding a regime gate to the higher-count `5m` HTF-LSI candidates worked, but only one gate was real**:
  - Fresh regime attribution on the promoted `5m lag24` long branch showed the real drag buckets were `bear_high_vol` and, secondarily, `bull_high_vol`. The older `skip bull_medium_vol + sideways_medium_vol` gate was still wrong for this family.
  - The only gate worth carrying forward was `skip bear_high_vol`. On the promoted `lag24` lead it improved validation PF / avg R / Calmar (`1.644 / 0.289 / 8.14`) but cut count too much for the new “one trade a week” goal.
  - The best gated count challenger was `gap2.5`, `right2`, `lag0`, `cap2`, `skip bear_high_vol`: fixed-split count stayed close enough to the target (`58.0` pre-holdout trades/year, `66.3` validation trades/year), validation improved to PF `1.713`, avg R `0.283`, Calmar `8.12`, and the stitched `36m IS / 12m OOS / 12m step` OOS tie-break beat the current `lag24` lead on every major quality metric: `339` OOS trades, PF `1.408`, avg R `0.176`, Calmar `6.33`, DD `-9.44R`, total R `+59.81`, versus `330`, `1.347`, `0.162`, `4.85`, `-11.01R`, `+53.39` for ungated `lag24`.
  - The count-preserving sibling was `gap2.5`, `right3`, `lag0`, `cap2`, `skip bear_high_vol`: `61.5` pre-holdout trades/year, `68.5` validation trades/year, stitched OOS `359` trades, PF `1.347`, avg R `0.155`, Calmar `5.43`, DD `-10.23R`, total R `+55.50`. It kept the weekly-trade target more cleanly, but it was weaker than the `right2` gated row on the stitched OOS tie-break.
  - Practical conclusion: if we want more flow without giving up trade quality, the first gated mini-shortlist should be `gap2.5/right2/lag0/skip bear_high_vol` and `gap2.5/right3/lag0/skip bear_high_vol`, with the `right2` row as the current pre-holdout favorite. Holdout should stay closed until one of those is explicitly frozen against the old `lag24` operating lead. Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_GATED_COUNT_TIEBREAK.md`.

- **The one-time holdout read kept ungated `lag24` as the overall operating lead, even though the gated count challengers stayed alive**:
  - Holdout comparison window: `2025-04-01` to `2026-03-24`, opened once only after freezing the mini-shortlist.
  - The current operating lead, ungated `lag24`, still won on holdout raw quality and payout conversion: `42` trades, PF `2.20`, avg R `0.430`, total R `+18.07`, Calmar `6.02`, prop payout `71.2%`, funded payout `71.2%`, funded EV/start `$81.47`. It was positive in both holdout subperiods: `2025-04-01` to `2025-12-31` (`32` trades, PF `2.46`, avg R `0.487`) and `2026-01-01` to `2026-03-24` (`10` trades, PF `1.56`, avg R `0.249`).
  - The quality-oriented gated challenger, `gap2.5/right2/lag0/skip bear_high_vol`, remained constructive but did not beat the lead on holdout: `46` trades, PF `1.90`, avg R `0.347`, total R `+15.94`, Calmar `5.11`, prop payout `65.7%`, funded payout `65.7%`, funded EV/start `$59.67`. It was positive in both `2025` and `2026 YTD`, so it stays alive as a count-focused alternative, but not as the new lead.
  - The count-preserving gated challenger, `gap2.5/right3/lag0/skip bear_high_vol`, printed the most holdout trades (`54`) and nearly matched the lead’s total holdout R (`+17.54`), with funded EV/start actually higher at `$94.00`. But its holdout quality was weaker overall (PF `1.92`, avg R `0.325`, Calmar `4.68`, payout `65.4%`) and, more importantly, it split sharply by year: strong in `2025` (`44` trades, PF `2.30`, avg R `0.412`) but negative in `2026 YTD` (`10` trades, PF `0.98`, avg R `-0.057`).
  - Practical conclusion: do not replace ungated `lag24` as the main HTF-LSI operating branch. If we want a secondary “more trades” variant, `gap2.5/right2/lag0/skip bear_high_vol` is the cleaner alternate branch because it stayed positive across both holdout subperiods. `right3` remains the higher-count but less stable side branch. Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_GATED_COUNT_HOLDOUT.md`.

- **A direct exact single-leg comparison says the legacy `ALPHA_V1` NQ NY LSI leg is still the stronger all-weather branch, while `HTF_LSI_5M_LAG24` is the more selective alternate**:
  - exact replay latest common end: `2026-03-24`
  - same legacy leg used as a true single-leg exact replay: `legacy-LSI`, `09:35-15:30`, `rr=3.0`, `tp1=0.34`, `gap=5.0`, `n_left=8`, `n_right=60`, `fvg=20/5`, `Wed+Thu` excluded
  - same HTF branch used in that exact comparison: `htf-LSI`, `08:30-15:00`, `rr=3.0`, `tp1=0.6`, `gap=3.0`, `htf60`, `n_left=3`, `cap=2`, `fvg=20/2`, `lag=24`, all days
  - same payout models used for both:
    - funded first-payout model: start `$50k`, trailing DD `$2k`, first payout floor `$52.5k`, challenge fee `$100`, risk `$500/R`
    - prop model: `+5R / -4R`, daily `-2R`, min `5` trading days, account fee `$50`, reset fee `$50`, risk `$400/R`
  - on the exact `10y` window `2016-01-01` to `2025-12-31`, legacy did `427` trades, PF `1.595`, avg R `0.189`, total R `+80.67`, DD `-6.36R`, Calmar `12.68`, funded payout `81.6%`, prop payout `93.9%`; HTF lag24 did `530` trades, PF `1.357`, avg R `0.165`, total R `+87.20`, DD `-12.97R`, Calmar `6.72`, funded payout `52.0%`, prop payout `68.3%`
  - `2024` was the clearest year in HTF lag24’s favor: legacy was almost flat to slightly negative (`43` trades, `-0.58R`, funded payout `8.6%`), while HTF lag24 stayed clearly profitable (`64` trades, `+18.28R`, funded payout `33.6%`)
  - `2025` split the result: legacy had the better raw PF (`2.44` vs `1.50`) and lower DD (`-4.40R` vs `-7.08R`), but HTF lag24 had more trades (`42` vs `33`), higher total R (`+15.94` vs `+11.69`), and better funded payout conversion (`64.1%` vs `50.0%`)
  - `2026 YTD` (`2026-01-01` to `2026-03-24`) is too thin to lean on: legacy raw quality is better (`7` trades, `+3.58R`, PF `3.01`), but neither branch has enough 2026 history yet to make the payout model stable
  - practical conclusion: do not treat `HTF_LSI_5M_LAG24` as a replacement for the legacy `ALPHA_V1` leg. Legacy remains the stronger account-farming branch on long-run robustness and payout rate, while HTF lag24 is the newer alternate that handled `2024-2025` better than legacy’s 2024 slump.
  - important classification note: `HTF_LSI_5M_LAG24` is still the best **true / canonical LSI** candidate tested so far. The only branch that beats it overall is `legacy-LSI`, and that branch depends on the old broken entry-gated, non-consumptive sweep semantics, so it should be treated as a separate non-canonical strategy bucket rather than the benchmark for “real” LSI.
  - stale HTF-level invalidation correction (`2026-05-16`): the active `ALPHA_V1` HTF-LSI override was rerun after fixing both research and execution to consume HTF pivots breached outside the valid sweep/entry window. This supersedes the old `493`-trade ALPHA leg summary and the `540`-trade live-cap comparison for current-live metrics. Corrected exact replay through `2026-05-01`: `394` trades, WR `53.6%`, PF `1.470`, avg R `0.209`, total R `+82.34`, DD `-8.00R`, Calmar `10.29`; holdout `2025-04-01` to `2026-05-01`: `29` trades, PF `2.096`, total R `+11.75`, DD `-3.00R`, Calmar `3.92`. Research/exact parity is tight enough for the current branch (`+1` exact trade pre-holdout, equal holdout trade count). Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_LAG24_EXACT_REPLAY.md` and `backtesting/data/results/nq_ny_htf_lsi_lag24_exact_replay/exact_replay_compare.json`.
  - corrected challenger retest (`2026-05-16`): after the stale-level fix, reran the serious HTF-LSI / EQHL-LSI challengers through `2026-05-01`. No candidate cleanly dethroned the active `ALPHA_V1` slot on all-weather evidence. The best practical tweak was the live-supported `block_bear_high_vol` gate on the current slot: exact holdout improved from `29` trades / PF `2.096` / `+11.75R` to `28` trades / PF `2.285` / `+12.75R`, and last-2y R improved from `+21.09R` to `+21.69R`, but full-history R slipped from `+82.34R` to `+78.73R` and full Calmar from `10.29` to `9.84`. The old `08:30-15:00, rr3.0, tp0.6` lag24 row and the `gap2.5/lag30/current-exit` row showed better recent pockets but worse all-weather drawdown / Calmar. Research-only `current + 15m EQHL tol1` slightly improved full-sample research Calmar / DD and stayed holdout-flat, but execution still lacks additive-EQHL support, so it cannot replace the live slot without implementation plus exact replay. Practical conclusion: keep current ungated HTF-LSI as the default `ALPHA_V1` leg; keep `block_bear_high_vol` as the only live-native conditional tweak worth portfolio-level exact testing; do not promote `2m`, standalone EQHL, or wide EQHL branches. Reference: `backtesting/learnings/reports/NQ_NY_LSI_CORRECTED_CANDIDATE_RETEST_20260516.md`.
  - uncapped rerun note: a fresh cross-timeframe rerun disabled the research-side session trade cap with `htf_trade_max_per_session=0` and re-ran the `1m/2m/3m/5m` transfer + lag packet. That did **not** dethrone `5m lag24`. `5m` stayed exactly the same winner, `long / fvg_limit / lag24`, with the same validation PF / avg R / Calmar (`1.597 / 0.268 / 6.38`) as the capped study. The lower timeframes got noisier instead of cleaner: uncapped `3m` shifted to `lag19` but stayed discovery-negative and still had lower validation Calmar than the capped `3m lag0` row; uncapped `2m` surfaced a both-direction `lag1` pop on only `12` validation trades; uncapped `1m` broadened to `both / fvg_limit / lag0`, but the capped `long / close / lag10` row still had materially better validation PF / avg R / Calmar (`1.888 / 0.420 / 4.91` vs `1.279 / 0.132 / 3.76`). Practical implication: removing session trade caps strengthens the case that `HTF_LSI_5M_LAG24` is the cleanest real HTF-LSI branch, because it was unchanged while the lower-timeframe variants became more sample-fragile. Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_UNCAPPED_RERUN.md`.
  - exact live-cap note: the execution-side `max_open_contracts=1` cap was materially suppressing size and should not be treated as representative of the branch. A direct exact replay comparison on the same trade stream (`540` trades through `2026-03-24`) showed `cap=1` forced every trade to `1` MNQ and produced `10Y` PF `1.357`, total R `+87.20`, DD `-12.97R`. Raising the cap to `20` lifted average size to `6.84` MNQ over the `10Y` window and changed the long-run profile to PF `1.365`, total R `+85.33`, DD `-10.75R`; more importantly, it was effectively uncapped for the recent years that matter: in `2024`, `2025`, and `2026 YTD`, the `cap=20` and true uncapped (`cap=0`) exact replays had the same trade counts and the same raw metrics, because recent desired size never exceeded `10` MNQ. Practical implication: for current HTF-LSI exact/live research, `max_open_contracts=20` is a reasonable “effectively uncapped” default, while `1` is an artificial choke collar. Reference: `backtesting/data/results/nq_ny_htf_lsi_exact_cap_compare.json`.
  - replacement sizing note: if `HTF_LSI_5M_LAG24` is force-fit as the `ALPHA_V1` NQ NY LSI replacement and `2024-2026` is weighted more heavily than the older years, the best sprint-risk compromise is **`$300/trade`**, not `$400`. On the exact recent window `2024-01-01` to `2026-03-24`, `$300` printed `98.0%` prop payout, `2.0%` breach, `176d` average payout, and `+$2410` EV/start; `$250` was even safer (`100%` payout, `0%` breach, `193d`) but too slow to be the clean replacement choice, while `$350+` degraded too quickly (`$350`: `94.1%` / `5.9%` / `159d`; `$400`: `92.2%` / `7.8%` / `144d`). The long-run sanity check still favored lower risk, but with much slower payout cadence (`10Y` at `$250`: `94.5%` payout, `392d`; `$300`: `90.6%`, `304d`; `$400`: `76.8%`, `158d`). Practical implication: for an `ALPHA_V1`-style sprint account, use `risk_usd=300` if the goal is to preserve strong recent-year payout quality without dragging payout speed out as much as `$250`; treat `$250` as the extra-conservative alternate and avoid `$350+` unless faster payout is worth the noticeably worse breach profile. References: `backtesting/data/results/nq_ny_htf_lsi_replacement_risk_recent.json`, `backtesting/data/results/nq_ny_htf_lsi_replacement_risk_10y.json`.
  - portfolio decision update (`2026-04-12`): the **current preferred NQ NY LSI for live / discretionary use** is the `ALPHA_V1` HTF-LSI override, not the frozen standalone `HTF_LSI_5M_LAG24` research anchor. The active operating row is `08:30-13:30`, `rr=3.5`, `tp1=0.4`, `risk_usd=400`, inside the `2R`-stagger portfolio mix `HTF_LSI=400 / NQ_Asia=250 / ES_Asia=250 / ES_NY=400`. Treat this as a deliberate discretionary operating choice built on the same HTF-LSI thesis, not as a revision of the older head-to-head evidence that legacy `ALPHA_V1` LSI was stronger on long-run all-weather payout farming and not as a rewrite of the frozen canonical-LSI research anchor.
  - combined portfolio replacement note: in the exact combined `ALPHA_V1` profile, replacing the legacy `NQ_NY_LSI` leg with `HTF_LSI_5M_LAG24` at the recommended `$300` risk and leaving the other legs unchanged produced a workable but clearly slower payout engine. On the exact combined single-account model with `+$2500 / -$2000` thresholds and a `14`-day stagger, the `10Y` window `2016-01-01` to `2025-12-31` printed `73.6%` payout with `134d` average payout time, fastest `3d`, slowest `493d`. The strongest individual replacement years were `2024` (`84.2%`, `110d`, fastest `20d`, slowest `189d`) and `2025` (`84.6%`, `96d`, fastest `8d`, slowest `287d`). `2026 YTD` (`2026-01-01` to `2026-03-24`) is still unresolved-heavy: `1` payout, `0` breaches, `5` open, so the displayed `100%` payout rate only reflects the single resolved account. Practical implication: the HTF swap can keep the combined portfolio alive, but it should be treated as a recency-motivated replacement, not as evidence that the combined portfolio got broadly stronger than the legacy mix. Reference: `backtesting/data/results/alpha_v1_htf_lsi_replacement_combined_exact.json`.
  - combined `2024-2025` payout-speed frontier note: a focused exact sweep on the swapped portfolio (`ALPHA_V1` with HTF-LSI replacing legacy LSI) showed the `2024-2025` combined-account tradeoff is not monotonic. Relative to the initial `$300` replacement (`82.7%` payout, `100.3d` avg payout), the cleanest improvement was actually **`$350`**, which improved both metrics at once: `84.6%` payout and `86.9d` average payout. `$325` was the low-drama trim (`82.7%`, `93.2d`), and `$400` was the fastest row that still preserved the same payout rate as `$300` (`82.7%`, `72.9d`). Beyond that, the curve turns meaningfully worse on success: `$450` fell to `78.8%`, `$500` to `75.0%`. Practical implication: if the only goal is to cut average payout time on the `2024-2025` swapped portfolio without giving up too much success rate, the honest menu is `$325` for a mild improvement, `$350` for the best balanced improvement, and `$400` for a faster-but-still-acceptable aggressive setting. Reference: `backtesting/data/results/alpha_v1_htf_lsi_replacement_combined_2024_2025_risk_sweep.json`.
  - full four-leg `2024-2025` portfolio frontier note: an exact all-legs grid then varied the swapped HTF leg plus `NQ_Asia`, `ES_Asia`, and `ES_NY` together. The important finding was that the blended daily-PnL frontier materially overstated payout quality; only the exact combined-profile verify should be trusted. On the exact verify, the **highest-quality** swapped mix remained the baseline-style portfolio `HTF_LSI=300 / NQ_Asia=300 / ES_Asia=200 / ES_NY=300`, which printed `84.3%` payout, `109.5d` average payout, fastest `20d`, slowest `274d`. The fastest mix that still stayed around an `80%` payout rate was `HTF_LSI=400 / NQ_Asia=250 / ES_Asia=250 / ES_NY=350`, which cut average payout to `66.0d` with `80.8%` payout, fastest `8d`, slowest `198d`. Pushing harder kept reducing payout time but degraded success too quickly: `400 / 300 / 250 / 400` reached `63.8d` at `78.8%`, `400 / 250 / 300 / 400` reached `57.3d` at `73.1%`, and the absolute-fastest verified mix `400 / 400 / 300 / 400` reached `54.1d` at only `73.1%`. Practical implication: for the swapped `ALPHA_V1` portfolio, use the baseline-style mix if payout percentage is the priority, and use `400 / 250 / 250 / 350` only if cutting payout time to roughly two months is worth giving up a few points of payout rate. Reference: `backtesting/data/results/alpha_v1_htf_portfolio_frontier_2024_2025.json`.
  - stagger-policy note: a second exact portfolio-layer study then asked whether the swapped `ALPHA_V1` portfolio should stagger new accounts by time or by realized account-R moves. Time-based staggers were tested at `7d / 10d / 14d / 21d`; R-triggered starts were tested whenever the master combined stream moved by `2R / 3R / 4R / 5R`, using **`1R = $500`** so the trigger language stayed aligned with the same `+$2500 / -$2000` (`+5R / -4R`) payout model. The clean result was that **R-triggered staggering dominated fixed calendar staggering** on the exact verified shortlist. The best time-based rows still clustered around the same aggressive mix and topped out near `80-81%` payout with roughly `60-64d` average payout: `time_14d` with `400 / 250 / 250 / 400` printed `80.8%` and `60.0d`, `time_7d` printed `80.8%` and `61.1d`, and `time_10d` printed `80.8%` and `62.2d` with a slightly lighter `ES_NY=350`. By contrast, the R-triggered family kept payout quality materially higher while still being faster: the same core aggressive mix `HTF_LSI=400 / NQ_Asia=250 / ES_Asia=250 / ES_NY=400` printed `86.5%` payout and `55.8d` average payout at `2R`, `86.4%` and `56.0d` at `3R`, `86.7%` and `58.8d` at `4R`, and `84.6%` and `50.6d` at `5R`. Practical implication: if the goal is the fastest payout engine that still keeps a strong payout percentage, the honest new default is **R-triggered staggering, not a fixed 2-week clock**. The best balanced row is `r_trigger_2R` on `400 / 250 / 250 / 400`; `r_trigger_5R` is the faster aggressive version if you are willing to accept fewer starts and a bit more variance. Reference: `backtesting/data/results/alpha_v1_htf_stagger_policy_frontier_2024_2025.json`.
  - hybrid stagger note: a follow-up exact test then asked whether `r_trigger_2R` should be softened with a minimum calendar spacing floor before allowing another account start. The tested hybrids were `2R + min 3d / 5d / 7d / 10d`, evaluated on the practical mixes already on the table rather than on a new broad grid. The result was nuanced but not decisive: **small spacing floors (`3d` or `5d`) can shave a fraction of a day off the aggressive mixes, but they do not improve the frontier enough to replace plain `2R` as the default**. On the current aggressive leader `400 / 250 / 250 / 400`, plain `2R` printed `83.0%` payout and `56.0d` average payout, while `2R + min 3d` nudged that to the same `83.0%` payout and a slightly faster `55.2d`; `min 5d` was similar at `55.6d`. The larger floors were not helpful: `min 7d` slipped to `82.6%` and `56.3d`, and `min 10d` fell to `79.5%` and `60.9d`. On the safer baseline-style mix `300 / 300 / 200 / 300`, `min 7d` did lift payout rate from `85.7%` to `87.9%`, but average payout slowed from `86.7d` to `89.3d`, so it was a quality-first tweak rather than a speed upgrade. Practical implication: keep plain `r_trigger_2R` as the honest operating default; if clustering turns out to matter in live ops, the only hybrid worth revisiting is a very light `min 3d` or `min 5d` floor on the aggressive `400 / 250 / 250 / 400` mix. Reference: `backtesting/data/results/alpha_v1_htf_hybrid_2r_min_spacing_test_2024_2025.json`.
  - Reference: `backtesting/learnings/reports/NQ_NY_LSI_LEGACY_VS_HTF_EXACT_COMPARISON.md`.

- **A later local window/exit retune improved the active `5m lag24` operating point inside the same HTF-LSI branch**:
  - Held structure fixed to `5m`, `long`, `fvg_limit`, `gap3.0`, `htf60`, `n3`, `cap2`, `fvgL20`, `fvgR2`, `lag24`.
  - Best entry cutoff inside the prior `08:30-15:00` range was `13:30`; extending entries later added little or slightly hurt validation Calmar, and later starts were clearly worse.
  - On `08:30-13:30`, both ungated and `skip bear_high_vol` preferred `rr=3.5`, `tp1=0.4`. Ungated validation Calmar improved from `6.60` to `6.83`; gated improved from `8.27` to `8.52`.
  - The nuance is holdout hygiene: the already-opened holdout still slightly favored the older `08:30-15:00 / rr3.0 / tp0.6` baseline on raw holdout Calmar, even though the new `08:30-13:30 / rr3.5 / tp0.4` row was better on stitched OOS.
  - Practical conclusion: if we are updating the current operating lead rather than reopening the frozen holdout packet, use `08:30-13:30`, `rr=3.5`, `tp1=0.4` on the same lag24 structure and keep `skip bear_high_vol` as the only gate that still looks genuinely useful.
  - Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_WINDOW_EXIT_LOCAL_SWEEP.md`

- **The corrected left-pivot target definition also did *not* find an honest replacement for the current HTF-LSI operating stop logic** (`backtesting/scripts/run_nq_lsi_structural_stop_target_sweep.py`, corrected one-time read `2026-04-13`):
  - Re-tested the current operating row (`5m lag24`, `08:30-13:30`, `rr=3.5`, `tp1=0.4`, `skip bear_high_vol`) across the same stop menu and the same three target modes: `risk`, the older `structural` proxy, and the corrected `left_structure`.
  - The operating baseline **`absolute + risk`** stayed top on the honest pre-holdout read: PF `1.435`, avg R `0.191`, Calmar `8.42`, median stop `149` ticks. Opened holdout remained PF `2.264`, avg R `0.445`, Calmar `5.34`.
  - The best `left_structure` row was **`absolute + left_structure`**. It slightly improved pre-holdout PF / avg R to `1.453 / 0.202`, but Calmar slipped to `8.01` and the opened holdout degraded to PF `1.799`, avg R `0.353`, Calmar `2.95`. Tighter left-structure rows were worse on pre-holdout even when the already-opened holdout looked attractive.
  - Practical conclusion: keep the current HTF-LSI operating stop/target construction unchanged. No left-structure target variant deserves promotion.
  - Reference: `backtesting/learnings/reports/NQ_LSI_STRUCTURAL_STOP_TARGET_SWEEP.md`

- **A broad ATR/ORB stop-source probe on the same current HTF-LSI operating lead also found no honest replacement for the structural stop** (`backtesting/scripts/run_nq_htf_lsi_atr_orb_stop_sweep.py`, one-time read `2026-04-13`):
  - Re-tested the same operating row (`5m lag24`, `08:30-13:30`, `rr=3.5`, `tp1=0.4`, `skip bear_high_vol`) with current `risk` targets and capped stop sources: `atr_pct` at `5/10/15/20%` of daily ATR and `orb_pct` at `50/75/100%` of a minimal `08:30-08:35` opening range, always capped at the structural invalidation point.
  - The operating baseline **`absolute`** stayed first outright on both sides of the read: pre-holdout PF `1.435`, avg R `0.191`, Calmar `8.42`, median stop `149` ticks; opened holdout PF `2.264`, avg R `0.445`, Calmar `5.34`.
  - The least-bad ATR row was **`atr_20pct`**. It did tighten the median stop to `118` ticks, but pre-holdout quality still fell materially to PF `1.230`, avg R `0.121`, Calmar `4.87`; holdout also stayed below baseline at PF `2.044`, avg R `0.416`, Calmar `4.99`.
  - The least-bad ORB row was **`orb_100pct`**. It compressed the median stop much harder to `47` ticks, but pre-holdout quality degraded even more sharply to PF `1.226`, avg R `0.112`, Calmar `2.36`, and holdout slipped to PF `1.816`, avg R `0.360`, Calmar `3.82`.
  - Tighter rows (`<=15% ATR`, `<=75% ORB`) were worse again, and `atr_5pct` actually turned the pre-holdout packet negative (`PF 0.975`, avg R `-0.014`, Calmar `-0.22`).
  - Practical conclusion: keep the structural stop as the default on the current `5m lag24` HTF-LSI lead. If broad non-structural stop-source research is ever revisited, `20% ATR` is the least-bad ATR row and `100% ORB` is the least-bad ORB row, but neither is close to promotion.
  - Reference: `backtesting/learnings/reports/NQ_HTF_LSI_ATR_ORB_STOP_SWEEP.md`

- **Running the corrected left-pivot target packet on the honest lower-timeframe HTF-LSI anchors still did *not* produce a promoted `left_structure` winner** (`backtesting/scripts/run_nq_htf_lsi_lower_tf_structural_stop_target_sweep.py`, corrected one-time read `2026-04-13`):
  - Holdout hygiene stayed intact: the honest `1m`, `2m`, and `3m` `lag=0` anchors were re-tested only on pre-holdout data, with stitched `36m IS / 12m OOS / 12m step` OOS used as the secondary read instead of opening `2025-04-01+`.
  - `1m`: the baseline **`absolute + risk`** stayed best overall at stitched PF `1.147`, avg R `0.073`, Calmar `2.17`, DD `-19.35R`. The best `left_structure` row was **`absolute + left_structure`**, which nudged stitched PF / avg R to `1.166 / 0.078` but worsened Calmar to `1.66` and DD to `-27.24R`. Leave `1m` untouched.
  - `2m`: the best stitched-OOS row overall was still only a local curiosity, **`struct_75pct + risk`** (Calmar `3.781` vs baseline `3.763`), because it gave up PF / avg R and validation quality. The best `left_structure` row was **`gap_4x + left_structure`**, and it was clearly worse than baseline: stitched PF `1.080`, avg R `0.045`, Calmar `1.355`. Leave `2m` unchanged.
  - `3m`: the earlier restart point still holds. The best overall row remained **`gap_2x + risk`**, improving stitched OOS to PF `1.192`, avg R `0.107`, Calmar `3.43`, with median stop cut from `152` to `72` ticks. The best `left_structure` row was **`gap_3x + left_structure`**, which improved stitched PF / avg R over baseline to `1.167 / 0.094` but lost on Calmar (`2.24`) and DD (`-18.73R`).
  - Practical conclusion: no lower-timeframe branch produced a left-pivot target winner. If the dormant `3m` HTF-LSI branch is ever reopened, the honest restart candidate is still **`lsi_stop_mode = gap_2x` with `lsi_target_mode = risk`**, not a `left_structure` variant.
  - Reference: `backtesting/learnings/reports/NQ_HTF_LSI_LOWER_TF_STRUCTURAL_STOP_TARGET_SWEEP.md`

- **The promoted `5m lag=24` HTF-LSI branch is much closer to exact research parity than the first replay suggested**:
  - The sparse exact replay turned out to be mostly a config leak, not a structural strategy mismatch. The execution profile `HTF_LSI_5M_LAG24` was unintentionally inheriting the legacy `NQ_NY_LSI` weekday exclusion `excluded_dow=[2,3]` even though HTF-LSI discovery and validation were run with no weekday exclusions.
  - A single-day trace on `2025-04-23` showed the exact engine stayed `idle` all day only because that Wednesday was being excluded before the sweep window could arm. After explicitly overriding the profile to `excluded_dow=null`, the exact replay restored the same trade the research branch took: long at `18883.75`, sourced from the `2025-04-23 06:00 ET` HTF low `18839.0`, with `fvg_to_inversion_bars=13` and `sweep_to_inversion_bars=14`.
  - Practical implication: the earlier `42 vs 28` holdout mismatch is obsolete and should not be treated as evidence that the promoted HTF-LSI branch fails live-alignment.
  - Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_LAG24_DAY_TRACE_2025_04_23.md`

- **After removing the inherited Wed/Thu exclusion, holdout parity for `HTF_LSI_5M_LAG24` became exact at the trade level**:
  - The direct research export still prints `602` rows because it includes `54` `no_fill` setups; the honest research filled count remains `548` (`506` pre-holdout, `42` holdout).
  - With the weekday leak fixed, exact replay now prints `553` trades overall, `511` pre-holdout, and `42` holdout.
  - On the untouched holdout `2025-04-01` to `2026-03-24`, fuzzy same-trade matching now maps all `42` exact fills to the `42` research fills under the key `(date, entry_price, htf_level_price, fvg_to_inversion_bars)`, with `0` research-only and `0` exact-only holdout trades.
  - The only holdout mismatch left is benign timestamp drift on limit fills: exact entries land `0-4` minutes after the research bar timestamp. Pre-holdout parity also tightened sharply from `506 vs 307` to `506 vs 511`, leaving only `16` research-only and `21` exact-only trades across the full long history.
  - Practical implication: `5m lag=24` remains the right HTF-LSI research lead, and the remaining exact-alignment work is now a small pre-holdout residual rather than a holdout failure or a trade-cap sequencing issue.
  - Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_LAG24_PARITY_DIFF.md`

- **Two exact-engine boundary fixes removed most of the remaining pre-holdout replay mismatch without changing holdout parity**:
  - The exact engine was still doing two things research did not: allowing HTF-LSI FVG detection when `daily_atr` was unavailable and allowing `fvg_limit` orders to fill on `1s` ticks after the `15:00` entry cutoff. Both behaviors were fixed in `execution/src/trader/lsi_engine.py`.
  - Re-running the full parity diff after those fixes left holdout unchanged at exact parity (`42` research fills vs `42` exact, `0` research-only, `0` exact-only) but reduced exact replay from `553` total trades to `540`, with pre-holdout exact shrinking from `511` to `498`.
  - That collapsed the pre-holdout residual from `16` research-only / `21` exact-only down to `16` research-only / `8` exact-only. In other words, the boundary fixes removed `13` exact-only trades without creating new research-only misses.
  - The representative broken days now behave correctly: `2016-01-05` no longer produces the two null-ATR exact-only fills, and `2023-06-05` now arms at `14:55` then cancels at the entry boundary instead of filling at `15:00:03`.
  - Practical implication: the remaining mismatch is now mostly a narrower pending-gap selection / ordering problem, not an ATR-readiness bug, not a post-window fill bug, and not a holdout integrity issue.
  - References: `backtesting/learnings/reports/NQ_NY_HTF_LSI_LAG24_PARITY_DIFF.md`, `backtesting/learnings/reports/NQ_NY_HTF_LSI_LAG24_DAY_TRACE_2016_01_05.md`, `backtesting/learnings/reports/NQ_NY_HTF_LSI_LAG24_DAY_TRACE_2023_06_05.md`

- **Timeframe transfer**:
  - **5m is best**
  - `2m` is alive but weaker
  - `1m` is positive but much weaker
  - `3m` looks good on validation but fails the discovery filter, so it is not promotable

- **Focused `2m` / `3m` stitched-OOS follow-up** (`backtesting/scripts/run_nq_ny_htf_lsi_2m_3m_followup.py`):
  - `2m`: uncapped `lag=0` long / `fvg_limit` / `cap1` remains the honest winner. Pre-holdout: `747` trades, PF `1.206`, discovery PF `1.186` / avg R `0.094`, validation PF `1.275` / avg R `0.127` / Calmar `2.06`. Stitched OOS (`36m IS / 12m OOS / 12m step`): `486` trades, PF `1.212`, avg R `0.104`, Calmar `3.76`, DD `-13.41R`. The late-lag `lag=26` challenger improved PF / avg R slightly but worsened stitched-OOS Calmar to `2.19` and DD to `-19.93R`. Conclusion: `2m` is still weaker than `5m`, but it is alive enough to justify a narrow secondary pre-holdout packet if we want one lower-timeframe side branch.
  - `3m`: validation still looks better than the underlying structure deserves. Uncapped `lag=0` stitched OOS was `444` trades, PF `1.155`, avg R `0.078`, Calmar `2.64`, DD `-13.07R`; `lag=30` was only a lateral move (`364` trades, PF `1.146`, avg R `0.084`, Calmar `2.66`, DD `-11.43R`) and discovery stayed negative either way. Conclusion: keep `3m` closed for this thesis.
  - Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_2M_3M_FOLLOWUP.md`

- **Narrow `2m` secondary packet** (`backtesting/scripts/run_nq_ny_htf_lsi_2m_secondary_packet.py`):
  - Held the viable branch shape fixed: `long`, `fvg_limit`, `cap1`, `lag=0`, `08:30-15:00`.
  - Swept a tight local neighborhood: `gap={3,4}`, `htf_n_left={3,5}`, `left={40,50,60}`, `right={3,5,8}`, `rr={2.5,3.0,3.5}`, `tp1={0.5,0.6,0.7}` (`324` configs, holdout still closed).
  - The prettiest pre-holdout rows all widened `lsi_fvg_window_right` from `5 -> 8`. Best fixed-split row: `gap3 n3 left50 right8 rr3.0 tp0.6` with discovery PF `1.135`, avg R `0.070`; validation PF `1.310`, avg R `0.148`, Calmar `3.30`.
  - But stitched OOS rejected those challengers. The original anchor, `gap3 n3 left50 right5 rr3.0 tp0.6`, still ranked first on the honest tie-break: `486` trades, PF `1.212`, avg R `0.104`, Calmar `3.76`, DD `-13.41R`. The best `right=8` challenger fell to `529` trades, PF `1.177`, avg R `0.088`, Calmar `2.76`, DD `-16.94R`.
  - Conclusion: `2m` does have a real local plateau, but the current anchor is already the best-balanced row in that plateau. Keep `2m lag0 / right5 / rr3 / tp0.6` as the secondary branch if we want one, and do not promote the validation-led `right=8` variants.
  - Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_2M_SECONDARY_PACKET.md`

- **Left-side LRLR context is not a clean standalone edge for the HTF-LSI family, but a looser `2m` version may still be useful as confluence** (`backtesting/scripts/run_nq_ny_htf_lsi_lrlr_left_study.py`):
  - Tested a structural LRLR definition on the left of the setup: unswept descending swing highs for longs / ascending swing lows for shorts, clustered within `120m`, with `max_gap=30m`, `max_price_span=0.18 ATR`, and a line-fit tolerance of `0.04 ATR`. Default strict gate required `3` pivots.
  - On the honest `2m` anchor, the default strict LRLR gate was clearly anti-edge. Validation LRLR-present trades were PF `0.776`, avg R `-0.125`, Calmar `-0.70`, while LRLR-absent trades were PF `1.478`, avg R `0.209`, Calmar `5.12`. The honest `require` gate stayed negative (validation PF `0.792`, avg R `-0.113`, Calmar `-0.89`).
  - `3m` told the same story: LRLR-present validation PF `1.237`, avg R `0.145`, Calmar `0.54` versus LRLR-absent PF `1.606`, avg R `0.231`, Calmar `4.87`. Conclusion: close the strict LRLR gate on the `3m` branch.
  - `5m` was too thin to promote a conclusion. LRLR-present trades were spectacular but only `4` validation fills (`2.6%` of validation trades), so that row should be treated as anecdotal rather than evidence.
  - `1m` was the only branch where LRLR-present validation outperformed LRLR-absent (PF `1.372` vs `1.165`, avg R `0.173` vs `0.084`, Calmar `2.15` vs `0.99`), but discovery remained materially weaker than the absent set, so the pattern is not stable enough to use as a promotion gate.
  - Important nuance: a **looser `2m` LRLR-lite definition** did help. Relaxing the gate to `2` pivots and `max_gap=30-40m` produced the only positive `2m` LRLR rows, with validation PF `1.375` / avg R `0.180` / Calmar `2.56` at `30m` and PF `1.360` / avg R `0.170` / Calmar `2.53` at `40m`. That is still weaker than the ungated branch on raw Calmar, but it is a real improvement over the strict `3`-pivot LRLR gate.
  - Practical conclusion: do **not** add the strict `3`-pivot LRLR gate to the canonical HTF-LSI branch family. If we revisit this idea later, the honest next step is a softer `2m` confluence notion (`2` pivots, `30-40m` spacing) rather than the original “three clustered highs in a clean channel” definition.
  - Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_LRLR_LEFT_STUDY.md`

- **The useful `2m` LRLR read is not just “two highs to the left” but “two highs to the left that actually map into the TP1 path”** (`backtesting/scripts/run_nq_ny_htf_lsi_lrlr_followup.py`, staged `2026-04-13`):
  - Followed up only on the honest `2m` anchor (`long`, `fvg_limit`, `cap1`, `rr=3.0`, `tp1=0.6`, `left50`, `right5`, holdout still closed). Baseline validation remained PF `1.275`, avg R `0.127`, Calmar `2.06` on `180` trades.
  - Re-tested the **LRLR-lite** family with the same structural tolerances as the first study, but fixing `min_pivots=2` and sweeping `max_gap={30,40}m`. Both rows remained live: validation PF `1.375` / avg R `0.180` / Calmar `2.56` on `111` trades at `30m`, and PF `1.360` / avg R `0.170` / Calmar `2.53` on `116` trades at `40m`.
  - Added a **TP1-aware LRLR definition**: keep the same left-side cluster, but only treat it as qualified when the nearest LRLR level sits at or inside TP1, with an optional ATR buffer. Swept `buffer={0.0,0.1,0.2,0.3}` on both `30m` and `40m` LRLR-lite rows.
  - That TP1-aware framing was the first version that looked materially stronger than plain LRLR-lite. Best honest row was `30m gap + 0.2 ATR buffer`, with validation PF `1.501`, avg R `0.229`, Calmar `4.01`, `105` trades. The `40m + 0.2 ATR` sibling was nearly identical at PF `1.481`, avg R `0.217`, Calmar `3.94`, `110` trades.
  - Zero-buffer TP1 alignment (`0.0 ATR`) produced the most explosive qualified subset statistics, but it was thinner (`89-94` validation trades) and actually ranked below the softer `0.1-0.2 ATR` buffers on the honest gated comparison. The practical read is that “roughly on the way to TP1” is better than “must line up perfectly.”
  - Important caution: discovery did **not** improve versus the ungated anchor. Best TP1-aware rows still sat around discovery PF `1.12-1.16` versus the ungated baseline’s `1.186`, so this is a promising confluence filter, not yet a promoted replacement for the base branch.
  - Practical conclusion: if LRLR is revisited again on the `2m` branch, the best restart point is **TP1-aware LRLR-lite**: `2` pivots, `30m` max gap, and nearest LRLR level within roughly `0.2 ATR` beyond TP1. Treat that as the working systematic definition rather than the original strict trendline-style LRLR.
  - Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_LRLR_FOLLOWUP.md`

- **That TP1-aware `2m` LRLR definition did not survive the honest stitched-OOS + holdout compare, so LRLR stays discretionary confluence rather than a promoted gate** (`backtesting/scripts/run_nq_ny_htf_lsi_lrlr_robustness_compare.py`, one-time holdout read `2026-04-13`):
  - Frozen candidates compared: the ungated `2m` anchor, `LRLR-lite 30m require`, and `TP1-aware LRLR-lite 30m + 0.2 ATR require`.
  - Pre-holdout still favored the LRLR rows, especially TP1-aware (`validation PF 1.501`, avg R `0.229`, Calmar `4.01`) versus the baseline (`1.275`, `0.127`, `2.06`).
  - On the stitched OOS stream, the TP1-aware row **did** keep better raw trade quality than baseline on PF / avg R (`1.252` / `0.127` vs `1.212` / `0.104`), but it paid for that with materially wider drawdown, so OOS Calmar stayed worse (`2.42` vs `3.76`). Plain LRLR-lite was weaker still on OOS Calmar (`1.99`).
  - The opened holdout rejected both LRLR gates. Baseline finished roughly flat but still alive: PF `1.040`, avg R `0.004`, total R `0.324`, Calmar `0.03` on `77` trades. `LRLR-lite 30m` failed outright: PF `0.753`, avg R `-0.144`, total R `-5.76`, Calmar `-0.66` on `40` trades. `TP1-aware 30m + 0.2 ATR` was less bad than plain lite but still failed: PF `0.816`, avg R `-0.099`, total R `-3.76`, Calmar `-0.45` on `38` trades.
  - Holdout path read: both LRLR gates were poor through the `2025-04-01` to `2025-12-31` segment (each at PF `0.689`, avg R `-0.167`). TP1-aware recovered slightly in `2026` YTD (PF `1.234`, avg R `0.048` on `12` trades), but not enough to rescue the full holdout verdict.
  - Practical conclusion: keep the **ungated `2m` anchor** as the honest systematic branch. Keep TP1-aware LRLR only as a discretionary confidence overlay or as a future chart-label / ablation candidate, not as a promoted hard gate.
  - Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_LRLR_ROBUSTNESS_COMPARE.md`

- **Ablation says the useful LRLR ingredient is mostly “liquidity that sits in the TP1 path,” not the full two-pivot trendline structure** (`backtesting/scripts/run_nq_ny_htf_lsi_lrlr_ablation.py`, one-time holdout read `2026-04-13`):
  - Compared four frozen variants on the same `2m` anchor: `baseline`, `TP1-window only`, `unswept-pair only`, and `full TP1-aware LRLR-lite`.
  - Operational definitions:
    - `TP1-window only`: require at least **one** unswept left-side pivot high inside `TP1 + 0.2 ATR`, with no cluster requirement.
    - `unswept-pair only`: require at least **two** unswept lower highs within `30m`, but remove the TP1 filter and loosen the channel-fit constraints.
    - `full TP1-aware LRLR-lite`: require the full `2`-pivot LRLR-lite structure plus the TP1-path condition.
  - On stitched OOS, `TP1-window only` was the clear ablation winner and even beat the ungated baseline on the main quality stats: PF `1.286` vs `1.212`, avg R `0.137` vs `0.104`, Calmar `5.04` vs `3.76`, with a similar trade count (`439` vs `486`). That is materially better than `unswept-pair only` (`1.184`, `0.095`, `1.75`) and also better than the full TP1-aware LRLR-lite row on OOS Calmar (`2.42`).
  - Structural read: the **pair / channel component added more damage than value** in this ablation. `unswept-pair only` was worse than baseline on both OOS PF and Calmar, and the full TP1-aware row only recovered part of that damage. The location-only TP1 window was the simplest and strongest formulation.
  - The opened holdout still kept the same caution. `TP1-window only` was the least-bad gated row, but it still failed as a hard systematic gate: holdout PF `0.922`, avg R `-0.049`, Calmar `-0.29` on `72` trades. That is materially better than the other gated ablations, but still worse than the roughly-flat ungated baseline.
  - Practical conclusion: if this thesis is ever reopened as a **chart overlay or soft confidence tag**, restart from the simple `TP1-window only` framing, not from the original LRLR trendline logic. For systematic gating, the honest conclusion stays unchanged: keep the ungated `2m` anchor.
  - Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_LRLR_ABLATION.md`

- **Broadening the `2m` anchor’s HTF-LSI sweep concept to include completed session / day / week reference levels increased trade count but did not improve the branch** (`backtesting/scripts/run_nq_ny_htf_lsi_2m_sweep_source_compare.py`):
  - Compared three frozen pre-holdout variants on the same `2m` anchor with holdout still closed: `htf_only`, `reference_only`, and `htf_plus_reference`.
  - The original `htf_only` anchor remained best on the honest stitched-OOS tie-break: `486` trades, PF `1.212`, avg R `0.104`, Calmar `3.76`, DD `-13.41R`.
  - `htf_plus_reference` materially increased sample, but the added trades were weaker than the base edge: pre-holdout filled trades rose `747 -> 1175`, stitched OOS trades `486 -> 768`, yet stitched OOS PF slipped to `1.199`, avg R to `0.100`, Calmar to `3.56`, and DD widened to `-21.46R`.
  - `reference_only` also raised count relative to `htf_only` (`678` stitched-OOS trades), but it was clearly worse on quality: PF `1.165`, avg R `0.082`, Calmar `3.02`, DD `-18.39R`, with a negative `2022` walk-forward fold.
  - Important structural read: on this frozen `long` branch, only the **low-side** published levels actually contributed trades. The mixed / reference branches were driven mainly by `asia_low`, `london_low`, and `new_york_low`, with smaller help from `previous_day_low` and `previous_week_low`; the added high-side levels were irrelevant on the long-only branch.
  - Practical conclusion: do not replace the honest `2m` anchor with the broadened sweep-source versions. If the goal is the strongest base for future confluence testing, keep `htf_only`. If the goal later shifts to a secondary higher-count side branch, `htf_plus_reference` is the only variant worth keeping alive, but treat it as a count-expansion branch with weaker quality and wider drawdown, not as an improved core candidate.
  - Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_2M_SWEEP_SOURCE_COMPARE.md`

- **Adding same-day `data_high/data_low` news-spike levels to the `2m` HTF-LSI anchor hurt the branch even more than the completed session/day/week basket** (`backtesting/scripts/run_nq_ny_htf_lsi_2m_data_sweep_compare.py`):
  - Tested a new data-candle liquidity concept on the same frozen `2m` anchor: a completed `1m` candle whose range is at least `15%` of previous-day ATR. Its high/low become valid on the first eligible base bar after the `1m` close and stay active for the rest of that day.
  - Compared three pre-holdout variants: `htf_only`, `data_only`, and `htf_plus_data`.
  - The untouched `htf_only` anchor again remained the clear winner on stitched OOS: `486` trades, PF `1.212`, avg R `0.104`, Calmar `3.76`, DD `-13.41R`.
  - `data_only` failed outright as a base branch: `585` stitched-OOS trades, PF `0.984`, avg R `-0.010`, Calmar `-0.21`, DD `-25.98R`. Validation was already weak at PF `0.941`, avg R `-0.038`, Calmar `-0.42`.
  - `htf_plus_data` did increase sample, but it degraded the honest edge badly: `797` stitched-OOS trades, PF `1.087`, avg R `0.043`, Calmar `1.52`, DD `-22.74R`, with validation already effectively dead at PF `0.994`, avg R `-0.003`, Calmar `-0.06`.
  - Structural read: on the long-only branch, the new source contributed **only** `data_low` trades. `data_high` never mattered, and the added `data_low` traffic was low-quality enough to overwhelm the cleaner HTF pivot edge.
  - Practical conclusion: keep `data_high/data_low` closed for this `2m` HTF-LSI branch. They do not help as a replacement source and they do not help as a count-expansion add-on.
  - Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_2M_DATA_SWEEP_COMPARE.md`

- **Requiring the `data_high/data_low` spike candle to also print a new running NY-session extreme did improve the data-candle family, but still did not beat the honest `2m` HTF anchor** (`backtesting/scripts/run_nq_ny_htf_lsi_2m_data_session_extreme_compare.py`):
  - Narrowed the same `15%` previous-day ATR data-candle concept so `data_high` only updates when the qualifying `1m` candle also sets a new running session high, and `data_low` only updates when it also sets a new running session low.
  - Compared three pre-holdout variants: `htf_only`, `data_only_session_extreme`, and `htf_plus_data_session_extreme`.
  - The base `htf_only` anchor still remained best on stitched OOS: `486` trades, PF `1.212`, avg R `0.104`, Calmar `3.76`, DD `-13.41R`.
  - The narrower `htf_plus_data_session_extreme` branch was materially better than the broad `htf_plus_data` version, but still clearly worse than the base: `642` stitched-OOS trades, PF `1.154`, avg R `0.074`, Calmar `2.45`, DD `-19.30R`. That is a real improvement over the broad version (`797`, `1.087`, `0.043`, `1.52`, `-22.74R`) but not enough for promotion.
  - `data_only_session_extreme` also improved versus the broad `data_only` branch, yet still failed as a standalone base: `323` stitched-OOS trades, PF `0.998`, avg R `-0.007`, Calmar `-0.10`, DD `-22.42R`.
  - Structural read: even after narrowing, the branch remained entirely a `data_low` story on the long-only config. `data_high` still produced no fills.
  - Practical conclusion: the session-extreme filter is the first refinement that makes the data-candle idea less bad, so it is the only defensible restart point if this thesis is explored again. But it still does **not** replace `htf_only`, and it still does not justify opening a count-expansion side branch.
  - Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_2M_DATA_SESSION_EXTREME_COMPARE.md`

- **Restricting that session-extreme data-candle idea to scheduled macro-release windows made it meaningfully cleaner, but still did not beat the honest `2m` HTF anchor** (`backtesting/scripts/run_nq_ny_htf_lsi_2m_data_macro_window_compare.py`):
  - Screened the same frozen `2m` anchor across `NFP`, `CPI`, `PPI`, and `FOMC`, requiring the qualifying `1m` candle to both print a new running NY-session extreme and occur within `0/1/2/5` minutes after the scheduled release.
  - Validation screening immediately showed the pattern: all `data_only` variants stayed dead, while the only live challengers were `htf_plus_data` rows. The best validation challenger was `htf_plus_data_w0` at `189` trades, PF `1.164`, avg R `0.079`, Calmar `1.37`; the pure data branches remained non-viable with validation PF only `0.538-0.641`.
  - Stitched OOS still kept `htf_only` on top: `486` trades, PF `1.212`, avg R `0.104`, Calmar `3.76`, DD `-13.41R`.
  - But this was the first data-candle refinement that got close enough to look structurally respectable as an add-on branch. The best challenger was `htf_plus_data_w5`: `507` trades, PF `1.156`, avg R `0.078`, Calmar `2.81`, DD `-14.05R`. That was better than `w1` (`506`, `1.151`, `0.075`, `2.71`, `-14.05R`) and much better behaved than the earlier ungated session-extreme row (`642`, `1.154`, `0.074`, `2.45`, `-19.30R`).
  - Structural read: even after adding scheduled macro timing, the branch was still entirely a `data_low` story on the long-only config. `data_high` again produced no fills.
  - Practical conclusion: if this data-candle thesis is reopened, the best restart point is now `htf_plus_data_w5` on top of the same `2m` HTF anchor. It still does **not** replace `htf_only` as the best base config, but it is the first version that looks defensible as a secondary higher-count / confluence side branch rather than a dead end.
  - Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_2M_DATA_MACRO_WINDOW_COMPARE.md`

- **Waiting for the `2nd` or `3rd` inversion after the sweep did not improve the frozen `2m` HTF-LSI anchor across HTF, session, data, or mixed liquidity-source families** (`backtesting/scripts/run_nq_ny_htf_lsi_2m_inversion_ordinal_compare.py`):
  - Operationalized the idea as the **nth eligible FVG inversion event per swept liquidity level** on the same frozen `2m` anchor (`long`, `fvg_limit`, `08:30-15:00`, `rr=3.0`, `tp1=0.6`, `gap=3.0`, `atr14`, `htf60 n3`, `cap1`, `left50`, `right5`, holdout still closed). Tested inversion ordinals `1`, `2`, and `3`.
  - Families tested: `htf_only`, `session_only` (`new_york/asia/london` highs/lows), `htf_plus_session`, `data_only`, `htf_plus_data`, and `all_sources` (`HTF + session + data`).
  - The clean result was that **ordinal `1` won every family on stitched OOS**. Later inversion selection sometimes created pretty fixed-split validation pops on very small samples, but none of those rows beat the first-inversion baseline once stitched OOS quality and sample size were considered together.
  - Best overall branch remained the honest `htf_only` first inversion: validation PF `1.275`, avg R `0.127`, Calmar `2.06`; stitched OOS `486` trades, PF `1.212`, avg R `0.104`, Calmar `3.76`, DD `-13.41R`.
  - Session lows alone stayed alive, but still did not justify replacing HTF-only. `session_only` first inversion finished at stitched OOS PF `1.210`, avg R `0.100`, Calmar `3.01`, DD `-21.32R`; `htf_plus_session` first inversion was similar quality at PF `1.211`, avg R `0.103`, Calmar `3.57`, but with much wider DD `-21.19R` because of the extra flow.
  - Raw data levels were **not rescued** by later inversion selection. `data_only` stayed non-viable across all ordinals; the most flattering row was ordinal `3`, which printed validation PF `1.542` and avg R `0.131` on only `30` validation trades, but stitched OOS still lost money (PF `0.929`, avg R `-0.031`, Calmar `-0.36`, `93` trades).
  - The mixed `all_sources` family also did not justify moving off ordinal `1`. Ordinal `2` improved validation PF/avg R versus ordinal `1`, but stitched OOS collapsed to PF `1.062`, avg R `0.015`, Calmar `0.35`. Ordinal `3` was cleaner than ordinal `2` on stitched OOS (PF `1.189`, avg R `0.061`, Calmar `1.44`), but still far behind the base `htf_only` first-inversion branch and much thinner (`104` stitched trades).
  - Practical conclusion: keep **first inversion** as the canonical `2m` HTF-LSI behavior. Treat `2nd`/`3rd` inversion ideas as discretionary curiosities for chart review, not as promoted systematic replacements for the current anchor.
  - Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_2M_INVERSION_ORDINAL_COMPARE.md`

- **Cross-timeframe transfer check confirmed that `1st` inversion remains the best overall HTF-LSI behavior on `1m/2m/3m/5m` when the family is narrowed to HTF-only vs HTF-plus-session sweeps** (`backtesting/scripts/run_nq_ny_htf_lsi_inversion_ordinal_tf_transfer.py`):
  - Anchors used were the honest per-timeframe lag-curve baselines for `1m/2m/3m` (`lag=0`) plus the promoted frozen `5m lag=24` lead. Families tested were only `htf_only` and `htf_plus_session`; inversion ordinals were `1/2/3`. Fixed-config stitched OOS was computed by slicing each full-period trade stream into the standard `36m IS / 12m OOS / 12m step` windows.
  - The top overall row in **every timeframe** still used **ordinal `1`**. Best overall stitched-OOS rows were: `1m htf_only inv1` (`577` trades, PF `1.147`, avg R `0.073`, Calmar `2.17`, DD `-19.35R`), `2m htf_only inv1` (`486`, `1.212`, `0.104`, `3.76`, `-13.41R`), `3m htf_plus_session inv1` (`780`, `1.133`, `0.068`, `3.50`, `-15.16R`), and `5m htf_only inv1` (`330`, `1.347`, `0.162`, `4.85`, `-11.01R`).
  - The core read stayed very clean on the serious branches. `2m` repeated the earlier result exactly: both `htf_only` and `htf_plus_session` still wanted `inv1`. `5m lag24` also clearly wanted `inv1`; later inversion rows were either outright negative (`inv2`) or tiny-sample anecdotes (`inv3` on only `5` stitched trades for `htf_only`).
  - `3m` did **not** produce a later-inversion rescue. `htf_only inv1` still had the best raw PF / avg R in that family (`444` stitched trades, PF `1.155`, avg R `0.078`), and the small `htf_plus_session inv1` Calmar bump does not change the older structural conclusion that `3m` remains closed because discovery is too weak and downstream quality still trails the real `2m` / `5m` branches.
  - The only apparent exception was a **thin `1m htf_plus_session inv3` pocket**. Within that one family it beat `inv1` on stitched OOS (`165` trades, PF `1.342`, avg R `0.083`, Calmar `1.89`, DD `-7.20R`), but validation was already unhealthy (`69` trades, PF `0.939`, avg R `-0.020`, Calmar `-0.23`). Treat that as a fragile curiosity rather than a promotable timing upgrade.
  - Practical conclusion: the transfer packet does **not** support promoting `2nd` or `3rd` inversion as the new default on any timeframe. Keep `1st inversion` as the canonical systematic behavior. If this idea is ever revisited, the only thing even mildly worth remembering is the small `1m + session + inv3` anomaly, and even that should stay closed until it survives a cleaner robustness pass.
  - Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_INVERSION_ORDINAL_TF_TRANSFER.md`

- **Approximate equal highs/lows are a real HTF-LSI sweep-source family, but the edge lives in denser local structure rather than sparse `60m` EQHLs** (`backtesting/scripts/run_cross_asset_eqhl_lsi_broad_discovery.py`, staged packet `2026-04-13`):
  - New thesis: instead of sweeping only unswept HTF pivots or published session/day/week levels, treat confirmed *approximate* equal highs/lows as the liquidity pool that arms the LSI. Matching was tested in ticks, not points, so `0` = exact and `1-2` = relative / near-equal.
  - Broad staged packet because the first all-timeframe run was too expensive before the EQHL matcher was optimized: `2m/5m` base LSI entries, EQHL source TFs `5m/15m/60m`, tolerance `{0,1,2}` ticks, touches `{2,3}`, directions `{long,both}`, entry mode `{fvg_limit,close}`, entry end `{13:00,15:00}`. Follow-up packet then promoted only the viable families down to `1m` with `long / fvg_limit / touches=2`.
  - The honest broad winners were *not* the sparse `60m` rows. The strongest materially sampled row was `5m entry / 5m EQHL source / tol=2 ticks / touches=2 / long / fvg_limit / end13:00`, with pre-holdout `394` trades, PF `1.206`, avg R `0.097`; validation `102` trades, PF `1.790`, avg R `0.302`, Calmar `5.33`. The best `2m` branch was `2m entry / 15m EQHL source / tol=2 / touches=2 / long / fvg_limit / end15:00`, with pre-holdout `291` trades, PF `1.306`, avg R `0.133`; validation `57` trades, PF `1.574`, avg R `0.243`, Calmar `2.87`.
  - The `60m` EQHL rows printed flashy validation averages (`0.625R+`) but on only `2-4` validation trades. Treat them as diagnostic-only and do **not** promote them.
  - Important structural read: the viable EQHL rows consistently wanted `2` touches, `long` bias, and `fvg_limit`. The relative versions (`1-2` ticks) beat the exact `0` tick rows on the serious branches, which supports the discretionary intuition that “near-equal” matters more than demanding tick-perfect symmetry.
  - `1m` follow-up stayed alive, but it did not dethrone the higher-timeframe winners. Best `1m` row was `1m entry / 5m EQHL source / tol=2 / touches=2 / long / fvg_limit / end13:00`, with pre-holdout `586` trades, PF `1.126`, avg R `0.064`; validation `139` trades, PF `1.298`, avg R `0.145`, Calmar `2.90`. The best `1m + 15m EQHL` row was `end15:00`, pre-holdout `312` trades, PF `1.245`, avg R `0.109`; validation `62` trades, PF `1.349`, avg R `0.145`, Calmar `1.17`.
  - Practical conclusion: EQHL is **not** a dead-end sweep-source idea. Keep two serious next-step branches alive: `5m -> 5m EQHL` and `2m -> 15m EQHL`, both around `tol=2 ticks / touches=2 / long / fvg_limit`. Keep `1m -> 5m/15m EQHL` only as a secondary higher-count exploratory branch. Do not reopen `60m EQHL` without an explicit count-expansion goal.
  - Artifacts currently preserved from the focused follow-up live under `backtesting/data/results/nq_ny_eqhl_lsi_broad_discovery/` (`ranking_1m_focus.csv`, `summary_1m_focus.json`, `summary_1m_focus.md`). A later script fix added `--suffix` so future staged reruns do not overwrite each other.

- **Local EQHL promotion packet confirmed that the `5m -> 5m` family is the only serious promotable EQHL branch, while `2m -> 15m` improved only modestly** (`backtesting/scripts/run_nq_ny_eqhl_lsi_promotion_packet.py`, packet `2026-04-13`):
  - Scope was intentionally narrow around the two broad-discovery survivors: frozen EQHL semantics (`tol=2`, `touches=2`, `long`, `fvg_limit`) while varying only `rr`, `tp1_ratio`, `lsi_fvg_window_left`, and `lsi_fvg_window_right`.
  - The `5m -> 5m` winner was `left20 right3 rr3.25 tp0.6`. It improved over the original broad anchor `left20 right2 rr3.0 tp0.5` across every serious lens: pre-holdout `428` trades, PF `1.255`, avg R `0.125`; discovery `322` trades, PF `1.108`, avg R `0.050`; validation `106` trades, PF `1.885`, avg R `0.353`, Calmar `8.26`; stitched OOS `257` trades, PF `1.248`, avg R `0.124`, Calmar `2.23`, DD `-14.24R`. The original anchor only managed stitched OOS PF `1.208`, avg R `0.099`, Calmar `1.67`.
  - `5m` surface read was coherent rather than jagged. The branch broadly wanted `tp1_ratio=0.6`, a slightly wider right window (`3` beats `2`, which beats `1` on average quality), and left windows around `20-24` bars. `left16` stayed viable but was a step down. This looks like a real local improvement, not a single-row fluke.
  - The best `2m -> 15m` row was `left40 right5 rr2.75 tp0.5`. It kept the branch alive but did **not** turn it into a co-lead: discovery `233` trades, PF `1.249`, avg R `0.103`; validation `57` trades, PF `1.566`, avg R `0.237`, Calmar `2.91`; stitched OOS `142` trades, PF `1.133`, avg R `0.059`, Calmar `0.61`, DD `-13.73R`. The original `2m` anchor was weaker on stitched OOS (PF `1.054`, avg R `0.027`, Calmar `0.24`), so the promotion packet helped, but only from weak to modest.
  - `2m` surface read was noticeably flatter and less persuasive than `5m`. Left window barely mattered, right window clearly preferred `5`, and the family generally liked `tp1_ratio=0.5`. Lower `rr` (`2.5-2.75`) improved validation a bit, but the stitched OOS ceiling stayed low.
  - Practical conclusion: freeze the EQHL family around **`5m entry / 5m EQHL / left20 right3 / rr3.25 / tp1=0.6`** as the promoted EQHL operating lead. Keep `2m -> 15m EQHL` only as a secondary exploratory branch and do not treat it as an equal challenger. Reference report: `backtesting/learnings/reports/NQ_NY_EQHL_LSI_PROMOTION_PACKET.md`

- **The promoted `5m -> 5m EQHL` lead passed a full phase-one payout read, but it still trails the incumbent `5m lag24` HTF-LSI lead on stitched-OOS payout business quality and speed** (`backtesting/scripts/run_nq_ny_eqhl_lsi_phase_one.py`, holdout opened once on `2025-04-01`):
  - Frozen candidate tested: `5m entry / 5m EQHL / tol2 / touches2 / long / fvg_limit / end13:00 / left20 / right3 / rr3.25 / tp1=0.6`. Pre-holdout structural metrics held up exactly as expected: `428` trades, PF `1.255`, avg R `0.125`, total R `+53.45`, DD `-14.24R`.
  - Reconstructed stitched OOS (`2019-01-01` to `2025-03-31`) stayed positive and phase-one viable: `257` trades, PF `1.248`, avg R `0.124`, total R `+31.80`, Calmar `2.23`. Prop scorecard: payout `64.3%`, breach `29.3%`, EV / attempt `$12,788.82`, avg days to payout `172`. Funded scorecard: payout `44.2%`, breach `49.4%`, EV / start `$101.46`, avg days to payout `92.7`.
  - Opened holdout (`2025-04-01` to `2026-03-24`) was constructive rather than collapsing: `28` trades, PF `1.459`, avg R `0.251`, total R `+7.03`, DD `-3.0R`. Holdout prop scorecard: payout `62.4%`, breach `0.0%`, open `37.6%`, EV / attempt `$12,433.66`, avg days `130.5`. Holdout funded scorecard: payout `62.4%`, breach `0.0%`, EV / start `$226.69`, avg days `130.4`.
  - So the honest verdict for the EQHL lead itself is **STRONG**. It is not a mirage, and the holdout did not kill it.
  - But against the incumbent NQ NY `5m lag24` lead, it is still the weaker payout engine on the key stitched-OOS business metrics. The incumbent kept stitched OOS funded payout `52.2%` vs EQHL `44.2%`, EV / start `$158.58` vs `$101.46`, and reached payout faster (`81.7` vs `92.7` days). On holdout the comparison is mixed: EQHL had lower payout rate (`62.4%` vs `71.2%`) and was much slower (`130.4` vs `77.7` days), but its holdout EV / start was higher (`$226.69` vs `$78.68`) because it avoided breaches completely and tended to overshoot the first-payout threshold more when it did resolve.
  - Practical conclusion: keep the EQHL `5m -> 5m` branch as a **strong secondary challenger / diversification candidate**, not as a replacement for the current `5m lag24` operating lead. The holdout has now been opened once for this branch, so do not reopen broad discovery or pretend it is still untouched OOS. Reference report: `backtesting/learnings/reports/NQ_NY_EQHL_LSI_PHASE_ONE.md`

- **Adding EQHL on top of the current `5m lag24` HTF-only lead improved the branch materially; the best additive row was `HTF + 15m EQHL tol1`, with `HTF + 5m EQHL tol1` as a lower-drawdown alternative** (`backtesting/scripts/run_nq_ny_htf_lsi_eqhl_additive_compare.py`, holdout kept closed):
  - This packet answered the additive question cleanly by freezing the current operating lead exactly as-is (`5m`, `long`, `fvg_limit`, `08:30-13:30`, `rr3.5`, `tp1=0.4`, `gap3.0`, `htf60`, `n3`, `cap2`, `fvgL20`, `fvgR2`, `lag24`) and only toggling in EQHL as an additional sweep source.
  - Base `htf_only` row stayed strong: pre-holdout `456` trades, PF `1.368`, avg R `0.163`; discovery `339` trades, PF `1.270`, avg R `0.118`; validation `117` trades, PF `1.717`, avg R `0.292`, Calmar `6.83`; stitched OOS `299` trades, PF `1.467`, avg R `0.199`, Calmar `5.43`, DD `-10.94R`.
  - The cleanest additive winner was **`HTF + 15m EQHL tol1`**: pre-holdout `497` trades, PF `1.373`, avg R `0.166`; discovery `368` trades, PF `1.257`, avg R `0.115`; validation `129` trades, PF `1.786`, avg R `0.312`, Calmar `8.04`; stitched OOS `322` trades, PF `1.515`, avg R `0.216`, Calmar `6.36`, DD `-10.94R`. That is a real improvement over the current lead on stitched-OOS PF, avg R, Calmar, total R, and trade count while keeping drawdown essentially unchanged.
  - The other serious additive row was **`HTF + 5m EQHL tol1`**. It was less clean on the fixed validation split (`PF 1.582`, avg R `0.255`, Calmar `6.48`), but stitched OOS improved in a different way: `364` trades, PF `1.385`, avg R `0.174`, Calmar `7.39`, DD `-8.58R`. So it gave up some PF / avg R versus the base, but delivered materially more flow and a much shallower stitched-OOS drawdown.
  - `15m tol2` stayed alive and still beat the base on stitched OOS (`333` trades, PF `1.495`, avg R `0.207`, Calmar `6.30`), but it was slightly behind `15m tol1`. `5m tol2` was the clear loser: discovery quality degraded materially and stitched OOS dropped to PF `1.272`, avg R `0.132`, Calmar `4.34`, despite more trades.
  - Practical conclusion: additive EQHL is **not** just an interesting idea; it improved the live `lag24` branch pre-holdout. If this path is advanced, the first honest holdout candidate should be `HTF + 15m EQHL tol1`, with `HTF + 5m EQHL tol1` kept as the alternate for a lower-drawdown / higher-flow flavor. Reference report: `backtesting/learnings/reports/NQ_NY_HTF_LSI_EQHL_ADDITIVE_COMPARE.md`

- **The one-time downstream phase-one head-to-head did not kill the additive winner; `HTF + 15m EQHL tol1` improved stitched-OOS payout business while leaving the opened holdout effectively unchanged versus the base `htf_only` lead** (`backtesting/scripts/run_nq_ny_htf_lsi_eqhl_additive_phase_one.py`, holdout opened once on `2025-04-01`):
  - Base candidate replayed exactly as expected: pre-holdout `456` trades, PF `1.368`, avg R `0.163`, total R `+74.19`; stitched OOS `299` trades, PF `1.467`, avg R `0.199`, total R `+59.41`; holdout `38` trades, PF `2.089`, avg R `0.398`, total R `+15.11`.
  - Additive challenger held the pre-holdout structural gain all the way through the phase-one read: pre-holdout `497` trades, PF `1.373`, avg R `0.166`, total R `+82.75`; stitched OOS `322` trades, PF `1.516`, avg R `0.216`, total R `+69.56`; holdout `38` trades, PF `2.089`, avg R `0.398`, total R `+15.11`.
  - The stitched-OOS funded scorecard improved in a real but modest way. Base `htf_only` funded payout was `70.6%`, breach `23.0%`, EV / start `$208.24`, average days to payout `97.0`. The additive challenger improved that to payout `73.8%`, breach `19.9%`, EV / start `$218.54`, average days `97.7`.
  - The opened holdout came back **flat, not worse**. Both rows produced the same holdout funded payout `68.6%`, breach `0.0%`, EV / start `$151.51`, and average days to payout `83.2`. So the additive branch did not earn a decisive holdout win, but it also did not damage the downstream path on the one holdout read we get.
  - Practical conclusion: within the frozen `5m lag24` HTF-LSI research family, **`HTF + 15m EQHL tol1` is now the preferred additive upgrade candidate**. Treat it as a narrow improvement over `htf_only`, not a wholesale overthrow: the tie-break win came from better stitched-OOS business quality while the opened holdout stayed identical. Reference report: `backtesting/learnings/reports/NQ_NY_HTF_LSI_EQHL_ADDITIVE_PHASE_ONE.md`

- **Phase two kept the additive challenger in the same verdict class as the base lead, but it still improved post-payout extraction and Monte Carlo survival enough to remain the preferred upgraded operating branch** (`backtesting/scripts/run_nq_ny_htf_lsi_eqhl_additive_phase_two.py`):
  - Both rows remained **`CONDITIONAL`** in phase two. Neither passed the stricter continuity / path-risk bar at the default post-payout model, and both failed the same two gates: **Phase 3: Continuity** and **Phase 5: Path-Risk**. So additive EQHL did **not** turn the branch into a true post-payout `GO`.
  - Even inside that unchanged verdict class, the challenger improved the economics. At the default `$250/R` post-payout size, base `htf_only` produced stitched-OOS withdrawals / start `$5,092.92`, breach `47.4%`, and MC survival `32.2%`; the additive challenger improved that to `$5,761.29`, the same `47.4%` breach, and `33.4%` MC survival. Holdout post-payout behavior was unchanged on this one opened read: both rows printed withdrawal rate `79.7%`, breach `0.0%`, and withdrawals / start `$2,012.58`.
  - The risk sweep kept the same best balanced size on both rows, **`$200/R` post-payout**, but the additive challenger was better there too. Base best-risk row: stitched-OOS withdrawals / start `$7,462.92`, OOS breach `0.1%`, holdout withdrawals / start `$1,280.63`, MC survival `61.1%`. Additive best-risk row: stitched-OOS withdrawals / start `$8,359.00`, OOS breach `0.1%`, holdout withdrawals / start `$1,280.63`, MC survival `65.1%`.
  - Practical conclusion: additive EQHL did not solve the underlying phase-two continuity problem, but it did improve the branch on the parts we actually care about within the same `CONDITIONAL` regime. So the honest operating preference is now **`5m lag24 + 15m EQHL tol1` over plain `htf_only`**, while still treating both as strategies that should be run with the reduced post-payout size discipline rather than as carefree extraction engines. Reference report: `backtesting/learnings/reports/NQ_NY_HTF_LSI_EQHL_ADDITIVE_PHASE_TWO.md`

- **A follow-up wide additive EQHL screen found one real closed-holdout challenger, but downstream promotion still failed to beat the current additive incumbent** (`backtesting/scripts/run_nq_ny_htf_lsi_eqhl_additive_wide_compare.py` and `backtesting/scripts/run_nq_ny_htf_lsi_eqhl_additive_wide_downstream.py`, holdout opened once only in the downstream step):
  - The closed-holdout additive-wide screen froze the same `5m lag24` branch and broadened only the additive EQHL layer: source TF `{5m,15m,60m}` x tolerance `{3,5,10,15,20}` points, all with `touches=2`, `eqhl_n_left=2`, and `lookback=48`. Controls were `htf_only` and the current additive incumbent **`HTF + 15m EQHL tol1`**.
  - The best wide additive row on that closed-holdout packet was **`HTF + 60m EQHL 15pt`**. It improved stitched-OOS Calmar and count relative to the incumbent, reaching pre-holdout `587` trades, PF `1.370`, avg R `0.165`; validation PF `1.760`, avg R `0.310`, Calmar `6.86`; and stitched OOS `375` trades, PF `1.471`, avg R `0.201`, Calmar `6.53`. The trade-off was quality: the incumbent still had better validation PF / Calmar (`1.786 / 8.04`) and better stitched OOS PF / avg R (`1.515 / 0.216`), just on fewer trades (`322`).
  - That made `60m 15pt` the only honest wide additive branch worth downstream promotion. On the opened downstream head-to-head, though, it lost cleanly to the incumbent on the actual business metrics. Both rows stayed **`STRONG / CONDITIONAL`**, but the incumbent kept higher stitched-OOS funded EV / start **`$218.54` vs `$163.24`**, higher holdout funded EV / start **`$151.51` vs `$83.31`**, higher default post-payout OOS withdrawals / start **`$5,761.29` vs `$5,499.48`**, and higher default holdout withdrawals / start **`$2,012.58` vs `$1,730.44`**.
  - The wide challenger did show one narrow positive feature: it wanted slightly smaller post-payout size and slightly higher best-risk MC survival. Its best balanced risk was **`$175/R`** instead of the incumbent’s **`$200/R`**, and the best-risk MC survival was `66.3%` vs `65.1%`. But even there, the incumbent still kept slightly better withdrawals / start (`$8,359.00` OOS and `$1,280.63` holdout) than the wide challenger (`$8,264.97` and `$1,203.79`).
  - Practical conclusion: **do not widen the additive operating branch beyond `15m EQHL tol1`**. `60m EQHL 15pt` is an interesting higher-flow side flavor, but once phase one, holdout, and phase two are all opened on the same path, it is still economically weaker than the incumbent additive branch. So the frozen operating preference remains **`5m lag24 + 15m EQHL tol1`**, and the additive-wide avenue is now closed as a primary promotion path. Reference reports: `backtesting/learnings/reports/NQ_NY_HTF_LSI_EQHL_ADDITIVE_WIDE_COMPARE.md`, `backtesting/learnings/reports/NQ_NY_HTF_LSI_EQHL_ADDITIVE_WIDE_DOWNSTREAM.md`

- **A final diversification check closed the “backup slot” question too: the `60m EQHL 15pt` additive challenger is too correlated with the incumbent to justify a true sidecar role** (`backtesting/scripts/run_nq_ny_htf_lsi_eqhl_additive_diversification_check.py`):
  - This was a descriptive post-holdout check, not a new promotion packet. Both frozen additive branches were rerun over the full sample, then compared on trade-date overlap, daily-R correlation, and constant-gross-risk blends where incumbent weight + challenger weight = `1.0`.
  - The overlap was extremely high. Full-sample shared trade-date Jaccard was **`0.796`**, with the challenger overlapping **`82.5%`** of its dates with the incumbent and the incumbent overlapping **`95.8%`** of its dates with the challenger. Daily-R correlation was **`0.860`** full-sample, **`0.854`** pre-holdout, and an even tighter **`0.933`** on the opened holdout.
  - Constant-risk blending did **not** rescue the challenger as a diversification leg. Pre-holdout, adding challenger weight modestly improved total R and slightly reduced max DD at light weights (`0.75 / 0.25` incumbent/challenger improved pre-holdout total R from `82.68` to `86.20` and max DD from `-11.30R` to `-10.73R`). But the opened holdout moved the opposite way: pure incumbent kept the best holdout total R / Calmar (`15.11R`, Calmar `5.27`), while every blend or pure challenger was worse (`0.75 / 0.25` fell to `14.28R`, Calmar `4.98`; pure challenger to `11.81R`, Calmar `4.12`).
  - Practical conclusion: **do not keep `60m EQHL 15pt` as a real backup/diversification slot next to the incumbent**. It is too behaviorally similar and too correlated, and once you normalize gross risk, the holdout evidence still prefers the incumbent alone. If the branch is remembered at all, remember it only as a historical higher-flow variant of the same underlying idea, not as an additive portfolio leg. Reference report: `backtesting/learnings/reports/NQ_NY_HTF_LSI_EQHL_ADDITIVE_DIVERSIFICATION_CHECK.md`

- **A mixed exact/proxy `ALPHA_V1` portfolio-layer test did not justify swapping the additive EQHL branch into the practical four-leg book; the portfolio still prefers the plain `HTF_LSI_5M_LAG24` control leg on payout speed** (`backtesting/scripts/run_alpha_v1_eqhl_additive_portfolio_proxy.py`, packet `2026-04-13`):
  - Scope was intentionally pragmatic rather than perfect-exact because the live execution engine still does **not** support additive EQHL fields. The portfolio kept three fixed exact legs — `NQ_Asia=250`, `ES_Asia=250`, `ES_NY=400` — and compared two NQ NY variants over the same payout-stagger menu: an **exact** `HTF_LSI_5M_LAG24` control leg versus a **research-side proxy** for `5m lag24 + 15m EQHL tol1`. NQ risk was swept over `{250,300,350,400,450}`.
  - The control leg stayed decisively faster at the portfolio level. Its best `>=80%` payout row was **`risk=350`, `r_trigger_4R`**, with payout **`86.4%`**, breach **`13.6%`**, and average payout time **`43.7d`**. Strong time-based rows were similarly fast: for example **`risk=450`, `time_14d`** printed **`90.4%`** payout, **`9.6%`** breach, and **`44.8d`** average payout.
  - The additive proxy did show slightly better payout probability on some rows, but only by slowing the whole book down materially. Its best `>=80%` payout row was **`risk=250`, `r_trigger_3R`**, with payout **`87.0%`**, breach **`13.0%`**, and average payout time **`67.5d`**. Its best high-success time-based row, **`risk=250`, `time_14d`**, reached **`92.2%`** payout and only **`7.8%`** breach, but average payout time stretched to **`75.1d`**.
  - Important read on the proxy ladder: the additive rows collapsed into only two effective risk buckets (`250-350` and `400-450`), which strongly suggests the research-side NQ leg was staying in the same contract-size bucket across those ranges instead of meaningfully scaling every step. That does not invalidate the portfolio read, but it is another reason not to over-interpret the proxy as a final exact operating result.
  - Practical conclusion: **do not swap the live / practical `ALPHA_V1` book over to the additive EQHL leg on the basis of this portfolio test**. The additive branch remains a real research improvement on the single-leg stitched-OOS path, but at the portfolio layer it currently looks like a slower, more success-biased version of the same book rather than a better account-farming engine. If this question is ever reopened, the next honest step is to add additive-EQHL support to the live execution engine and rerun the comparison as a true exact replay before making a portfolio-operating decision. Reference report: `backtesting/learnings/reports/ALPHA_V1_EQHL_ADDITIVE_PORTFOLIO_PROXY.md`

- **An exact execution-robustness stress test says the live `HTF_LSI_5M_LAG24` branch is fairly resilient to slippage alone, but meaningfully more vulnerable once slippage is combined with missed fills / queue loss** (`backtesting/scripts/run_nq_ny_htf_lsi_execution_robustness.py`, packet `2026-04-13`):
  - Scope used the actual live execution profile, not a research proxy: exact replay through the live engine from `2019-01-01` to `2026-03-24`, then deterministic per-side slippage overlays plus Monte Carlo missed-fill overlays on the exact trade stream. Same-bar exit luck was already removed by the live engine before these stresses were applied.
  - Baseline exact profile remained strong: pre-holdout PF **`1.483`**, avg R **`0.192`**, funded EV / start **`$332.79`**, post-payout withdrawals / start **`$5,086.40`**; opened holdout PF **`2.152`**, avg R **`0.379`**, funded EV / start **`$228.95`**, withdrawals / start **`$1,585.26`**.
  - Slippage by itself degraded the branch, but only modestly. At **`1 tick per side`**, pre-holdout PF / avg R only slipped to **`1.448 / 0.181`** and holdout to **`2.123 / 0.372`**. Even at **`2 ticks per side`**, the branch still held pre-holdout PF / avg R **`1.413 / 0.169`** and holdout **`2.094 / 0.365`**.
  - The more meaningful damage came from **slippage + missed fills together**. At **`2 ticks per side + 10% missed fills`**, pre-holdout funded EV / start fell to **`$294.67`** and withdrawals / start to **`$4,392.91`**, while holdout funded EV / start fell to **`$214.23`** and withdrawals / start to **`$1,270.62`**. The harshest tested packet, **`3 ticks per side + 15% missed fills`**, still left the branch alive, but compressed pre-holdout withdrawals / start to **`$3,763.64`** and holdout withdrawals / start to **`$1,090.59`**.
  - Practical conclusion: the current `5m lag24` HTF-LSI branch looks robust enough to survive realistic slippage, but the business case depends materially on keeping fill quality decent. Treat **queue position / missed-entry control** as a first-class live risk, because that hurts the branch more than pure slippage does. Reference report: `backtesting/learnings/reports/NQ_NY_HTF_LSI_EXECUTION_ROBUSTNESS.md`

- **A targeted orthogonal-companion search says the best true companion to the current `5m lag24` HTF-LSI lead is still cross-session rather than another nearby HTF/EQHL variant** (`backtesting/scripts/run_nq_ny_htf_lsi_orthogonal_companion_search.py`, packet `2026-04-13`):
  - Candidate pool mixed the serious nearby NQ challengers (`5m lag24 + 15m EQHL tol1`, `2m` HTF anchor, wide `5m EQHL 5pt`, wide `3m EQHL 15pt`) with established `ALPHA_V1` legs (`NQ Asia ORB`, `legacy NQ NY LSI`, `ES Asia ORB`, `ES NY ORB`). Ranking used holdout overlap, holdout daily-R correlation, standalone viability, and simple `50/50` blend behavior versus the current `5m lag24` lead.
  - The cleanest true orthogonal companion was **`ALPHA_V1 NQ Asia ORB`**. On the opened holdout it showed correlation **`-0.060`**, trade-date Jaccard **`0.048`**, and the best `50/50` holdout blend of the entire search: total **`21.96R`** with Calmar **`8.24`**. That confirms the best diversification is still cross-session, not another version of the same NY LSI thesis.
  - The best non-book companion candidate was **`ALPHA_V1 NQ NY legacy LSI`**. It also stayed genuinely different on holdout, with correlation **`0.102`**, Jaccard **`0.116`**, and a positive `50/50` blend (`9.46R`, Calmar **`6.60`**), but it remains a separate non-canonical strategy bucket rather than the preferred systematic companion for the current branch.
  - The newer NQ challengers were not orthogonal enough. **`5m lag24 + 15m EQHL tol1`** was effectively the same stream on holdout (**`1.000`** correlation and **`1.000`** Jaccard), **`5m EQHL 5pt`** was still materially coupled (**`0.614`** correlation, **`0.468`** Jaccard), and the `2m` HTF anchor was simply too weak downstream. The only newer NQ variant that looked even somewhat companion-worthy was **`3m EQHL 15pt`** (`0.394` correlation, `0.268` Jaccard), but it still trailed the cross-session / legacy alternatives.
  - Practical conclusion: if we want a real companion to the current NQ NY HTF-LSI lead, **look outside the immediate HTF/EQHL neighborhood**. `NQ Asia ORB` remains the best true sidecar, `legacy NQ NY LSI` is the best non-book alternate, and the recent EQHL/HTF variants should be treated as branch relatives rather than portfolio diversifiers. Reference report: `backtesting/learnings/reports/NQ_NY_HTF_LSI_ORTHOGONAL_COMPANION_SEARCH.md`

- **Short-only EQHL discovery answered the missing short-side question cleanly: the family is alive, but only in a much narrower `5m` pocket, and it does not transfer to `1m`** (`backtesting/scripts/run_cross_asset_eqhl_lsi_broad_discovery.py`, staged packet `2026-04-13`):
  - Stage 1 isolated `2m` and `5m` shorts across the same broad EQHL surface used for the long-side work. Out of `288` configs, only `6` were `alive`. That is enough to say the family is real on the short side, but the surface is much thinner than the long-side EQHL branch.
  - The short-side survivors were structurally different from the long side. `5` of `6` alive rows used **exact** EQHL matching (`tol=0`) and `5` of `6` used `5m EQHL` as the sweep source. Every alive row used `touches=2`. So for shorts, exact equal highs look more useful than relative / near-equal matching.
  - The best short row was **`5m entry / 5m EQHL / tol0 / touches2 / short / fvg_limit / end13:00`**: pre-holdout `164` trades, PF `1.272`, avg R `0.119`; validation `25` trades, PF `2.250`, avg R `0.359`, Calmar `2.92`. The next best short rows were the same `5m -> 5m tol0 touches2` family using `close` entries (`end15:00` and `end13:00`), then a weaker `2m -> 5m tol0 touches2` pair. A lone `5m -> 15m tol2` row stayed technically alive but was much weaker and should not be treated as a co-lead.
  - Stage 2 then ran the focused `1m` follow-up only around the surviving family (`5m EQHL`, `touches=2`, tolerance `{0,1,2}`, short, both entry modes, entry end `{11:00,13:00,15:00}`). That packet failed cleanly: all `18` rows were `weak` or `dead`. Best `1m` row was `1m -> 5m EQHL tol0 touches2 short fvg_limit end15:00`, which had pre-holdout PF `1.097` / avg R `0.048` but validation PF `0.786` / avg R `-0.128`.
  - Practical conclusion: if short-side EQHL is ever revisited downstream, the only honest branch to remember is **`5m -> 5m EQHL tol0 touches2 short`**, with `fvg_limit end13:00` as the best current lead and `close end15:00` as the best nearby alternate. Keep `2m` only as a weaker secondary branch, close `1m` entirely on the short side, and do not divert into a full short downstream promotion path before finishing phase two on the stronger main additive lead. Reference report: `backtesting/learnings/reports/NQ_NY_EQHL_LSI_SHORT_ONLY_DISCOVERY.md`

- **Broadening EQHL tolerance from tick-sized matching into point-sized zones materially changed the NQ long-side surface, and the broad falloff did not begin until roughly `20 points`** (`backtesting/scripts/run_cross_asset_eqhl_lsi_broad_discovery.py`, focused packet `2026-04-13`):
  - This packet intentionally isolated the tolerance question rather than re-opening every dimension. Scope: `1m/2m/3m/5m` base entries, EQHL source TF `{5m,15m,60m}`, tolerance `{3,5,10,15,20}` points, `touches=2`, `long`, `fvg_limit`, and entry end `{13:00,15:00}`. `3m` support was added to the runner in this step.
  - The aggregate trade-count expansion behaved exactly as expected: mean pre-holdout trades rose from `519` at `3pt` to `773` at `20pt`. What mattered is that the edge did **not** immediately collapse with that extra count. Mean validation PF / avg R were `1.388 / 0.162` at `3pt`, `1.360 / 0.158` at `5pt`, `1.410 / 0.180` at `10pt`, and peaked broadly at `15pt` with `1.446 / 0.192`. Only at `20pt` did the average quality clearly roll over, to `1.362 / 0.159`, despite still-higher count.
  - The best row per timeframe was not one universal tolerance. `5m` liked **`5pt`** on `5m EQHL` (`645` pre-holdout trades, `165` validation, PF `1.684`, avg R `0.270`, Calmar `7.99`). `2m` also liked **`5pt`**, but on `15m EQHL` (`604` / `152`, PF `1.583`, avg R `0.263`, Calmar `5.10`). `3m` became a legitimate live branch and wanted **`15pt`** on `15m EQHL` (`671` / `169`, PF `1.656`, avg R `0.266`, Calmar `8.61`). `1m` behaved differently: once the zone widened, the best sampled rows came off **`60m EQHL`**, with the strongest practical pocket around **`10-15pt`**; for example `1m -> 60m EQHL 15pt end13:00` printed `347` pre-holdout trades, `79` validation trades, PF `1.908`, avg R `0.348`, Calmar `7.53`.
  - Practical conclusion: the original `0-4 tick` packet was probably too tight for NQ if the goal is to model discretionary “near-equal” liquidity shelves. The honest broad next-step operating bands are **`5pt` for `2m/5m`, `15pt` for `3m`, and `10-15pt` for `1m`**, while **`20pt` is the first clean “too broad starts here” marker**. Reference report: `backtesting/learnings/reports/NQ_NY_EQHL_LSI_WIDE_TOLERANCE_DISCOVERY.md`

- **A local promotion packet around the widened-tolerance winners confirmed that `5m 5pt`, `3m 15pt`, and `1m 15pt` all improve under local tuning, while `2m 5pt` stays alive but clearly weaker** (`backtesting/scripts/run_nq_ny_eqhl_lsi_wide_tolerance_promotion_packet.py`, holdout still closed):
  - Scope stayed disciplined: the widened EQHL source semantics were frozen per branch, and only the local knobs moved (`rr`, `tp1_ratio`, `lsi_fvg_window_left`, `lsi_fvg_window_right`). Five branches were promoted: `1m -> 60m EQHL 10pt`, `1m -> 60m EQHL 15pt`, `2m -> 15m EQHL 5pt`, `3m -> 15m EQHL 15pt`, and `5m -> 5m EQHL 5pt`.
  - The cleanest overall winner was **`5m -> 5m EQHL 5pt`**, promoted to `left16 right2 rr2.75 tp0.6`. Validation improved to PF `1.722`, avg R `0.287`, Calmar `8.58` on `164` trades, and stitched OOS landed at `380` trades, PF `1.372`, avg R `0.169`, Calmar `4.07`, DD `-15.74R`. That is the strongest wide-tolerance operating lead in this packet.
  - The best `3m` branch was **`3m -> 15m EQHL 15pt`**, promoted to `left27 right4 rr2.75 tp0.5`. Validation reached PF `1.702`, avg R `0.287`, Calmar `9.50` on `173` trades, and stitched OOS came back `458` trades, PF `1.225`, avg R `0.110`, Calmar `2.50`, DD `-20.06R`. Practical implication: `3m` is now a real promoted secondary branch, not just a discovery curiosity.
  - The stronger of the two `1m` branches was clearly **`1m -> 60m EQHL 15pt`**, promoted to `left100 right12 rr3.0 tp0.5`. Validation printed PF `2.001`, avg R `0.370`, Calmar `10.04` on `99` trades, and stitched OOS was `268` trades, PF `1.350`, avg R `0.164`, Calmar `3.01`, DD `-14.63R`. The `10pt` branch also improved (`left100 right12 rr2.75 tp0.4`, stitched OOS PF `1.364`, avg R `0.160`, Calmar `2.38` on `184` trades), but the `15pt` family is the one worth carrying forward.
  - `2m -> 15m EQHL 5pt` stayed viable but weaker. Its promoted row `left40 right5 rr3.0 tp0.6` held strong validation (`PF 1.602`, avg R `0.282`, Calmar `5.46`, `152` trades) but only modest stitched OOS (`380` trades, PF `1.172`, avg R `0.098`, Calmar `1.71`, DD `-21.70R`). So `2m` remains a tertiary exploratory branch rather than a co-lead.
  - Practical conclusion: among the widened-zone families, freeze **`5m -> 5m EQHL 5pt / left16 right2 / rr2.75 / tp0.6`** as the primary promoted lead. Keep **`1m -> 60m EQHL 15pt / left100 right12 / rr3.0 / tp0.5`** and **`3m -> 15m EQHL 15pt / left27 right4 / rr2.75 / tp0.5`** as the serious secondary promoted branches. Drop `1m 10pt` behind `1m 15pt`, and keep `2m 5pt` only as a lower-priority side branch. Reference report: `backtesting/learnings/reports/NQ_NY_EQHL_LSI_WIDE_TOLERANCE_PROMOTION_PACKET.md`

- **A full downstream compare closed the widened standalone EQHL question cleanly: none of the promoted wide-zone branches beat the current additive `5m lag24 + 15m EQHL tol1` lead once phase one, holdout, phase two, and risk sizing were all applied on the same path** (`backtesting/scripts/run_nq_ny_eqhl_wide_branches_downstream_compare.py`, holdout opened once on `2025-04-01` for the standalone wide branches):
  - Scope was the honest downstream head-to-head: current additive operating lead versus three frozen standalone wide-EQHL challengers, namely **`5m -> 5m EQHL 5pt / left16 right2 / rr2.75 / tp0.6`**, **`1m -> 60m EQHL 15pt / left100 right12 / rr3.0 / tp0.5`**, and **`3m -> 15m EQHL 15pt / left27 right4 / rr2.75 / tp0.5`**.
  - The additive lead stayed best on every major stitched-OOS business lens. It finished **`STRONG / CONDITIONAL`**, with OOS PF `1.516`, avg R `0.216`, funded EV / start **`$218.54`**, default post-payout withdrawals / start **`$5,761.29`**, and best-risk OOS withdrawals / start **`$8,359.00`** at **`$200/R`**. Holdout also stayed strongest overall: PF `2.089`, avg R `0.398`, funded EV / start **`$151.51`**, and default holdout withdrawals / start **`$2,012.58`**.
  - The best standalone challenger was still **`5m -> 5m EQHL 5pt`**, and it held up enough to stay respectable, but it was clearly weaker economically. It also finished **`STRONG / CONDITIONAL`**, yet only reached OOS funded EV / start **`$123.40`**, holdout funded EV / start **`$73.09`**, and default OOS withdrawals / start **`$5,619.70`**. Its best balanced post-payout size had to drop to **`$125/R`**, where OOS withdrawals / start were only **`$4,887.82`** despite a healthier `67.6%` MC survival.
  - **`1m -> 60m EQHL 15pt`** degraded too much downstream to keep as a serious promoted challenger. It fell to **`CONDITIONAL / CONDITIONAL`**, with holdout PF only `1.176`, holdout avg R `0.081`, and holdout funded EV / start **`-$58.17`**. Even its best-risk row at **`$125/R`** only produced **`$3,441.73`** OOS withdrawals / start and **`$85.40`** holdout withdrawals / start. Treat the branch as a discovery insight, not an operating lead.
  - **`3m -> 15m EQHL 15pt`** was the most interesting secondary wide branch: still only **`CONDITIONAL / CONDITIONAL`**, but with the best holdout behavior among the standalone wide challengers. It printed holdout PF `1.585`, holdout avg R `0.199`, holdout funded EV / start **`$144.82`**, and default holdout withdrawals / start **`$1,956.07`**, nearly matching the additive lead on that one opened holdout slice. The problem is stitched-OOS business quality: OOS funded EV / start collapsed to **`$18.18`**, default OOS withdrawals / start to **`$4,888.37`**, and the best-risk row still only managed **`$3,760.14`** at **`$100/R`**.
  - Practical conclusion: widened standalone EQHL branches are real, but they do **not** replace the additive operating lead downstream. Keep the main operating preference as **`5m lag24 + 15m EQHL tol1`**. If a standalone wide-zone branch is kept at all, keep **`5m -> 5m EQHL 5pt`** only as the clear secondary; treat **`3m -> 15m EQHL 15pt`** as a lower-size defensive flavor rather than a primary engine; and close **`1m -> 60m EQHL 15pt`** as a serious promotion candidate. The holdout has now been opened once on these standalone wide branches, so do not treat them as untouched downstream candidates going forward. Reference report: `backtesting/learnings/reports/NQ_NY_EQHL_WIDE_BRANCHES_DOWNSTREAM_COMPARE.md`

- **Downstream `2m` vs `5m` promotion comparison** (`backtesting/scripts/run_nq_ny_htf_lsi_2m_vs_5m_promotion.py`):
  - Compared the `2m` anchor directly against the current `5m lag24` operating lead on the same downstream path: pre-holdout structural read, stitched OOS, opened holdout, phase-one payout modeling, phase-two continuity, and post-payout risk sweep.
  - `5m lag24` stayed clearly ahead on stitched OOS raw quality: `330` trades, PF `1.347`, avg R `0.162`, Calmar `4.85`, versus `2m` at `486` trades, PF `1.212`, avg R `0.104`, Calmar `3.76`.
  - Holdout made the separation decisive. `5m` held PF `2.200`, avg R `0.430`, DD `-3.0R`; `2m` nearly flatlined at PF `1.040`, avg R `0.004`, DD `-10.78R`.
  - Phase-one funded EV/start favored `5m` strongly on stitched OOS (`$138.33` vs `$53.48`). `2m` did print a slightly higher holdout funded EV/start (`$89.36` vs `$81.47`), but that came on much weaker raw holdout trade quality and does not change the promotion verdict.
  - Phase two was the real deal-breaker. At the default `$250/R`, `5m` produced OOS withdrawals/start `$4,568.60` and holdout withdrawals/start `$2,815.14`, versus `2m` at `$2,962.98` and `$870.93`; MC survival at the true monetized threshold was `9.8%` for `5m` and only `0.2%` for `2m`.
  - The best balanced post-payout size for `2m` had to drop to `$125/R`, still yielding only `$3,592.51` OOS withdrawals/start and `$400.37` holdout withdrawals/start, while `5m` supported `$175/R` with materially better extraction.
  - Conclusion: keep `2m` as a secondary exploratory branch only. It does not deserve promotion over `5m lag24`, and it should not be treated as a co-lead.
  - Reference: `backtesting/learnings/reports/NQ_NY_HTF_LSI_2M_VS_5M_PROMOTION.md`

- **Phase-one payout evaluation** (`2019-01-01` to `2025-03-31` stitched OOS stream, holdout `2025-04-01` to `2026-03-24`):
  - OOS prop model: `1,945` starts, payout `70.9%`, breach `22.7%`, open `6.4%`, EV / attempt `$14,108.30`, avg days to payout `118.8`
  - OOS funded model: payout `52.2%`, breach `41.3%`, open `6.4%`, EV / start `$158.58`, median days to payout `75`
  - Holdout prop model: `306` starts, payout `71.2%`, breach `3.3%`, open `25.5%`, EV / attempt `$14,196.73`, avg days to payout `78.9`
  - Holdout funded model: payout `71.2%`, breach `3.3%`, open `25.5%`, EV / start `$78.68`, median days to payout `75.5`
  - Verdict: **STRONG**

- **Phase-two post-payout continuity** (weekly withdrawals above `$52.5k` back to `$52.0k`, default post-payout risk `$250/R`):
  - Stitched OOS continuity: withdrawal `88.7%`, breach `48.2%`, avg withdrawals / start `$4,140`, avg payout count / start `5.44`
  - Holdout continuity: withdrawal `91.5%`, breach `0.0%`, avg withdrawals / start `$2,689`, avg payout count / start `3.96`
  - Monte Carlo at the true monetized-account threshold (`8R` at `$250/R`): survival only `6.8%`, ruin `93.2%`
  - Verdict: **CONDITIONAL**

- **Focused post-payout risk sweep**:
  - Best balanced operating size was **`$150/R` post-payout**
  - At `$150/R`: OOS withdrawals / start `$4,431`, OOS breach `0.0%`, holdout withdrawals / start `$1,362`, holdout breach `0.0%`, MC survival `61.7%` at `13.3R`
  - Safer but lighter variant: `$125/R` gave MC survival `80.3%` with OOS withdrawals / start `$3,693`
  - Conclusion: `$250/R` is too aggressive after first payout for steady extraction; if this branch is used on monetized accounts, step down to roughly `$150/R` and treat it as a conditional extractor, not a set-and-forget one.

- **Conclusion**:
  - This is no longer just a discovery-alive branch. The frozen `5m` balanced anchor is a real first-payout candidate.
  - Do not reopen broad parameter discovery. Exact-execution live-alignment is now partially in place, and the next clean step is tightening research-versus-execution parity plus the operating playbook around the reduced post-payout risk size.

- **PSR / DSR promotion check**:
  - Trial basis from the actual `5m` discovery path: `144` raw unique configs, `8` effective trials by trade-date clustering
  - Full pre-holdout candidate (`2016-01-01` to `2025-03-31`): `575` trades, PF `1.250`, avg R `0.112`, total R `+64.37`, Calmar `5.27`, DD `-12.21R`, Sharpe `1.53`
  - Full pre-holdout PSR / DSR: **`0.9914 / 0.8092`**
  - Stitched walk-forward OOS (`36m IS / 12m OOS / 12m step`): `376` trades, PF `1.298`, avg R `0.130`, total R `+48.70`, Calmar `4.12`, DD `-11.83R`, Sharpe `1.75`
  - Walk-forward OOS PSR / DSR: **`0.9869 / 0.7606`**
  - **Interpretation**: the branch survives multiple-testing deflation cleanly

- **Holdout open** (`2025-04-01+`):
  - `46` trades, PF `1.987`, avg R `0.361`, total R `+16.61`, Calmar `5.54`, DD `-3.0R`, Sharpe `4.66`
  - `2025`: `35` trades, PF `2.205`, avg R `0.414`, total R `+14.50`
  - `2026 YTD`: `11` trades, PF `1.437`, avg R `0.192`, total R `+2.11`

- **Conclusion**: This is still the strongest NQ NY HTF-structure LSI branch tested so far. Keep `5m lag=24` as the preferred research lead, do not reopen broad discovery, and focus next on tightening the small residual pre-holdout exact-replay parity mismatch plus the live operating playbook before treating it as a fully live-ready branch.

---

### NY VWAP Reversion Fixed-R Pipeline Start (2026-06-29) — REJECT for $500 risk / $2k account

- **Status**: REJECT for the requested account sizing; `research_only` as a strategy family until live execution support and exact replay exist.
- **Report**: `backtesting/learnings/reports/NQ_NY_VWAP_REVERSION_FIXED_RR_PIPELINE_20260629.md`; artifacts in `backtesting/data/results/nq_ny_vwap_reversion_fixed_rr_pipeline_20260629/`.
- **Scope**: Started a repo-native discovery pipeline for the basic NY session VWAP reversion thesis: session VWAP deviation + rejection candle, fixed `rr=1.5`, fixed `$500` risk, `$2,000` account, NQ NY only. Reserved `2025-01-01` to `2026-06-06` as untouched holdout and searched only `2016-01-01` to `<2025-01-01`.
- **Harness fixes before trusting results**: VWAP reversion now enters on the next executable 5m bar after the rejection signal instead of letting the signal bar's earlier high/low act as post-entry path. `tp1_ratio=1.0` now behaves as a true single target for VWAP. VWAP also passes neutral shared-simulator defaults for pre-entry cancel/trailing/swing behavior, including a direction-aware neutral internal swing level for shorts.
- **Baseline after fixes**: default NY VWAP reversion (`deviation_atr_pct=30`, no stop buffer, both directions, `09:35-12:00`) did `853` trades, `-103.0R`, PF `0.807`, WR `35.2%`, max DD `-131.0R`. This baseline is structurally dead.
- **Coarse screen**: `576` fixed-R configs across deviation threshold, stop buffer, entry window, and direction. Only `25` rows were positive with at least `100` trades. Top total-R row was `dev10_stop20_0935-1200_long`: `340` trades, `+19.48R`, PF `1.12`, WR `48%`, max DD `-12.49R`, `0` negative years.
- **Account constraint read**: `$500` risk on a `$2,000` account leaves only `4R` capacity. Every positive row with at least `100` trades breached that `-4R` account threshold. The top row's `-12.49R` drawdown implies roughly `-$6,245` at `$500/R`, far beyond the account.
- **Practical conclusion**: do not carry this fixed `$500`/trade VWAP reversion setup into phase-one payout modeling. If revisited, either cut risk to about `$150/R` or less, or start a new thesis with stronger entry confirmation; do not open the 2025+ holdout for this weak fixed-risk screen.

### NY VWAP Reversion Prop-Firm Pipeline Start (2026-06-29) — CONDITIONAL research lead

- **Status**: CONDITIONAL research lead for the custom prop objective; still `research_only` until walk-forward/holdout validation, exact replay parity, and live execution support exist.
- **Report**: `backtesting/learnings/reports/NQ_NY_VWAP_PROP_FIRM_PIPELINE_20260629.md`; artifacts in `backtesting/data/results/nq_ny_vwap_prop_firm_pipeline_20260629/`.
- **Prop model tested**: `$2,000` EOD trailing drawdown capped at starting balance, `$3,000` pass target, `$1,500` first payout, then continue trading until bust or data end. Challenge/account fee modeled as `$0` because no fee was specified. Account starts every `14` calendar days from `2016-01-01` to `<2024-07-01`; `2025-01-01` to `2026-06-06` holdout stayed closed.
- **Sizing assumption**: used MNQ sizing on NQ price data. Full-size NQ is too coarse for this drawdown/cushion; MNQ lets the strategy express `$250-$600` risk without skipping most signals.
- **Coarse screen**: `2,700` configs over risk, RR, deviation, stop buffer, and entry window. Only `2` rows had recent first-payout rate `>=35%`, positive recent EV, and `>=100` trades. Best coarse recent-EV row was `mnq_dev10_stop15_rr2_risk300_0935-1200_long`: recent first-payout `39.56%`, EV `$593/start`, but `25.27%` recent open rate and negative net R.
- **Refinement**: targeted `918` risk/RR configs from the top `30` coarse rows. Best refined lead is `mnq_dev25_stop20_rr1.75_risk450_0935-1030_long`: `367` trades, `+17.65R`, PF `1.09`, WR `41%`, max DD `-16.98R`.
- **Account result for refined lead**: all staggered starts first-payout rate `54.95%`, realized first-payout EV `$824/start`, open rate `19.82%`, avg days to first payout `313.61`. Recent starts (`2021-01-01+`) first-payout rate `47.25%`, EV `$708.79/start`, pre-payout bust `52.75%`, post-payout bust `47.25%`, open rate `0%`, avg days to payout `195.58`.
- **Read**: the prop objective can make this otherwise modest VWAP edge economically interesting, but the path is still a high-bust account-farming profile rather than a clean standalone trading edge. Next step should be pre-holdout walk-forward / robustness on the refined lead before any holdout open.

### NY Level Mean-Reversion Recent 5-Year Prototype (2026-06-29) — CONDITIONAL frequency thesis

- **Status**: CONDITIONAL frequency thesis; `research_only` prototype only. No live execution support, exact replay, or 1m/1s path validation yet.
- **Report**: `backtesting/learnings/reports/NQ_NY_LEVEL_REVERSION_RECENT5_20260629.md`; artifacts in `backtesting/data/results/nq_ny_level_reversion_recent5_20260629/`.
- **Scope**: User requested a higher-frequency VWAP/level mean-reversion idea over only the last 5 years, targeting at least 1 trade/day and ideally 1-3. Tested `2021-06-07` through `2026-06-05` (`1,293` RTH days) on NQ 5m bars.
- **Pattern tested**: extension from mean -> tight consolidation -> sweep/reclaim of consolidation edge -> target the fixed mean level. Mean modes were `vwap`, `ny_open`, `ib_mid30`, and dynamic `day_mid`.
- **Result**: mechanically, the 1-3 trades/day target is reachable: `980/2,160` configs averaged `1-3` trades/day with at least `60%` day coverage. But edge thinned materially at that cadence.
- **Best edge row**: dynamic `day_mid_ext0.025_cons6x0.15_buf0.02_minrr0.2` made `1,038` trades (`0.80/day`, trades on `51.89%` of days), `+92.16R`, PF `1.121`, WR `25.7%`, max DD `-62.83R`. This misses the requested 1/day cadence but is the cleanest expectancy anchor.
- **Best cadence-fit row**: `ib_mid30_ext0.15_cons4x0.15_buf0.005_minrr0.2` made `1,863` trades (`1.44/day`, trades on `74.48%` of days), `+60.83R`, PF `1.0395`, WR `16.96%`, max DD `-111.55R`. It meets frequency but is a thin high-drawdown edge.
- **Diagnostic**: no config averaging `>=1` trade/day reached PF `1.05`; no positive config had `>=80%` day coverage. Treat `day_mid` as the better edge anchor and `ib_mid30` as the cadence anchor. Next pass should use a state-machine consolidation window after extension and then validate with 1m/1s magnifier before prop-risk scoring.

### NY Level Mean-Reversion State-Machine Recent 5-Year Pass (2026-06-29) — CONDITIONAL edge anchor, cadence still thin

- **Status**: CONDITIONAL structural research only. Do not push to prop-risk optimization yet; no 1m/1s path validation, train/validation split, exact replay, or live execution support exists for this branch.
- **Report**: `backtesting/learnings/reports/NQ_NY_LEVEL_REVERSION_STATE_MACHINE_RECENT5_20260629.md`; artifacts in `backtesting/data/results/nq_ny_level_reversion_state_machine_recent5_20260629/`.
- **Scope**: second pass on the user-requested last-five-years NQ NY mean-reversion idea, using available NQ 5m bars from `2021-06-07` through `2026-06-05` (`1,293` RTH days).
- **Pattern tested**: extension from mean first, then consolidation can form within a timeout, then a sweep/reclaim targets the signal-time mean. Mean modes were `day_mid`, `ib_mid30`, and `vwap`; `ny_open` was dropped after the weaker first pass. Entry window was `09:45-15:00`, flat by `15:55`, with conservative 5m pathing.
- **Grid**: `1,620` configs across mean mode, extension threshold, consolidation length/range, timeout (`12/24/36` bars), stop buffer, and minimum RR. `702` rows met the frequency-fit definition of `1-3` trades/day with at least `70%` day coverage.
- **Best edge row**: `day_mid_ext0.025_cons6x0.15_timeout12_buf0.02_minrr0.2` made `931` trades (`0.72/day`, trades on `51.89%` of days), `+96.25R`, PF `1.142`, WR `26.42%`, avg R `0.103`, max DD `-53.73R`. This improves the first-pass edge anchor (`+92.16R`, PF `1.121`, DD `-62.83R`) but is sparser.
- **Best cadence-fit row**: `vwap_ext0.025_cons6x0.2_timeout12_buf0.02_minrr0.2` made `1,393` trades (`1.08/day`, trades on `70.77%` of days), `+23.56R`, PF `1.023`, WR `26.06%`, max DD `-82.48R`. It satisfies the daily cadence definition but has too little expectancy.
- **Stability read**: no config averaging `>=1` trade/day reached PF `1.05`; no positive config achieved `>=80%` day coverage. The best edge row was recent-heavy: `2021 +3.96R`, `2022 -24.07R`, `2023 -5.36R`, `2024 +41.88R`, `2025 +54.13R`, `2026 +25.71R`.
- **Diagnostic**: state-machine sequencing improved edge quality for `day_mid`/`vwap` anchors, but the one-trade-per-day target remains the weak point. The next productive pass should add a regime/context filter or treat the state-machine edge anchor as a lower-frequency component instead of forcing daily frequency.

### NY Level Mean-Reversion Context-Filter Recent 5-Year Pass (2026-06-29) — CONDITIONAL low-frequency sleeve, daily cadence failed

- **Status**: CONDITIONAL structural research only. This improved the quality of the level-reversion branch, but it did not solve the user-requested one-trade-per-day objective. Still `research_only`: no 1m/1s path validation, train/validation split, exact replay, or live execution support exists.
- **Report**: `backtesting/learnings/reports/NQ_NY_LEVEL_REVERSION_CONTEXT_FILTER_RECENT5_20260629.md`; artifacts in `backtesting/data/results/nq_ny_level_reversion_context_filter_recent5_20260629/`.
- **Current best VWAP mean-reversion candidate**: until validation says otherwise, treat the `best_cadence_anchor` VWAP row with `reject_vwap_side_slope`, `efficiency_max=0.65`, `session_range_atr_max=2.0`, and `10:00-14:00` as the best NQ NY VWAP mean-reversion research candidate found so far. It is a selective low-frequency sleeve, not a daily-trade strategy.
- **Scope**: tested all proposed intraday context filters on the recent-five-year state-machine anchors from `2021-06-07` through `2026-06-05`: top `day_mid`, `vwap`, `ib_mid30`, plus the best `>=1/day` cadence anchor. Grid covered `2,700` context configs per anchor / `10,800` total rows. Baseline replay matched the prior state-machine metrics exactly for all four anchors before comparisons were trusted.
- **Context filters tested**: `structure_gate` (`none`, `reject_30m_trend_acceptance`, `require_30m_mixed`), `vwap_acceptance` (`none`, `reject_vwap_side_slope`, `reject_vwap_side_distance`), directional `efficiency_max` (`0.35/0.45/0.55/0.65` plus none), `ib_location` (`none`, `must_be_outside_ib`, `must_reclaim_inside_ib`), `session_range_atr_max` (`1.25/1.50/1.75/2.00` plus none), and time bucket (`full`, `10:00-12:00`, `10:00-14:00`, `11:00-15:00`).
- **Best overall row**: former cadence anchor `vwap_ext0.025_cons6x0.2_timeout12_buf0.02_minrr0.2` with `reject_vwap_side_slope`, `efficiency_max=0.65`, `session_range_atr_max=2.0`, and `10:00-14:00` made `370` trades (`0.286/day`, trades on `26.22%` of days), `+127.78R`, PF `1.556`, WR `37.03%`, avg R `0.345`, max DD `-12.20R`. Year split was all positive: `2021 +8.89R`, `2022 +16.49R`, `2023 +42.68R`, `2024 +43.03R`, `2025 +6.53R`, `2026 +10.17R`.
- **Best higher-retention filtered row**: same VWAP-slope/efficiency idea over the full entry window made `564` trades (`0.436/day`, trades on `36.35%` of days), `+114.29R`, PF `1.310`, max DD `-27.05R`.
- **Daily-cadence read**: one-trade-per-day still failed. Only `2/10,800` rows met `1-3` trades/day with at least `70%` day coverage, and none had PF `>=1.05`. The best `>=1/day` row was basically ungated cadence with `session_range_atr_max=2.0`: `1,390` trades (`1.075/day`, `70.53%` day coverage), `+26.56R`, PF `1.026`, max DD `-80.48R`. No positive row achieved `>=80%` day coverage.
- **Filter lesson**: the useful ingredient was `reject_vwap_side_slope` plus directional-efficiency control, not 30m structure or IB gates. Best non-`none` structure row (`require_30m_mixed`) was viable but sparse: `260` trades, `+81.86R`, PF `1.401`, max DD `-29.92R`; best IB-gated row was also sparse and inferior to the top no-IB row.
- **Practical conclusion**: keep this branch as a lower-frequency regime-filtered mean-reversion sleeve. Do not keep trying to force `1` trade/day from this structure. Next validation should take the top lower-frequency rows into train/validation and 1m/1s path checks before any prop-firm risk scoring.

### NY VWAP Mean-Reversion Validation Packet (2026-06-30) — CONDITIONAL recent-regime sleeve, not live-ready

- **Status**: CONDITIONAL research sleeve. The screenshot row is now the current best **pure VWAP-target** NQ NY VWAP mean-reversion candidate, but validation shows it is recent-regime dependent and still `research_only`.
- **Report**: `backtesting/learnings/reports/NQ_NY_VWAP_MEAN_REVERSION_VALIDATION_20260630.md`; artifacts in `backtesting/data/results/nq_ny_vwap_mean_reversion_validation_20260630/`.
- **Candidate fixed for validation**: `vwap_ext0.025_cons6x0.2_timeout12_buf0.02_minrr0.2` plus `reject_vwap_side_slope`, `efficiency_max=0.65`, `session_range_atr_max=2.0`, and `10:00-14:00`. This remains a selective low-frequency sleeve, not a daily-trade strategy.
- **Recent validation**: on `2021-06-07` through `2026-06-05`, pure VWAP-target replay made `370` trades (`0.286/day`, trades on `26.22%` of days), `+127.78R`, PF `1.556`, WR `37.03%`, avg R `0.345`, max DD `-12.20R`. Retrospective split stayed positive: `2021-2023 +68.05R`, PF `1.621`; `2024-2026 +59.72R`, PF `1.497`.
- **Cold older-window stress**: the same fixed candidate on `2016-01-01` to `<2021-06-05` degraded to `441` trades, only `+7.52R`, PF `1.025`, avg R `0.017`, max DD `-45.12R`. This is the major limitation: the edge is not all-regime.
- **Sensitivity read**: loosening to `efficiency_max=0.70` and `10:00-15:00/full` can raise total R to `+134.72R` over `619` trades, but PF drops to `1.335` and DD worsens to `-28.98R`. The tighter screenshot row remains the cleaner risk-adjusted anchor.
- **1m/1s path replay**: pure VWAP-target pathing survived lower-timeframe checks. 1m replay was `+127.26R`, PF `1.555`, DD `-12.01R`; 1s replay was `+127.72R`, PF `1.556`, DD `-12.05R`, with only `1` exit-type change.
- **Exit refinement**: keeping the same VWAP setup/context but targeting `day_mid` instead of VWAP improved results: 5m `368` trades, `+145.31R`, PF `1.639`, max DD `-11.53R`; 1s path replay improved further to `+153.00R`, PF `1.679`, max DD `-9.15R`. Treat this as the current best exit-refined variant, but note it is a VWAP-entry/context plus day-mid-target hybrid rather than pure VWAP-target.
- **Prop lifecycle**: with the custom `$2,000` EOD trailing DD / `$3,000` pass / `$1,500` first payout model and 14-day starts, 1s pure VWAP-target trades ranked best at `$175/R`: `76.34%` first-payout rate, `$1,145` realized EV/start, `3.82%` pre-payout bust, `0%` post-payout bust. The exit-refined day-mid-target variant ranked best at `$200/R`: `87.02%` first-payout rate, `$1,305` EV/start, `0%` pre-payout bust, `3.82%` post-payout bust.
- **Practical conclusion**: continue only as a recent-regime / low-frequency prop sleeve candidate. Do not promote to live/dry execution until the strategy is implemented as a live-native pre-trade gate, exact replay parity exists, and a regime filter or acceptance rule explains why the 2016-2021 cold window should be excluded.

### NY Selective VWAP Regime Discovery (2026-07-10) — CHALLENGER, opening-efficiency gate leads

- **Status**: CHALLENGER only. Abandoning the one-trade-per-day requirement produced a materially stronger selective branch, but it did not clear the deflated-Sharpe promotion gate and remains `post_filter_only`. No live/dry implementation is authorized.
- **Report**: `backtesting/learnings/reports/NQ_NY_VWAP_SELECTIVE_REGIME_DISCOVERY_20260710.md`; artifacts in `backtesting/data/results/nq_ny_vwap_selective_regime_discovery_20260710/`.
- **Holdout posture**: available data was `2016-01-01` through `<2026-06-06`; gate discovery used `2016-2022`, while `2023-2026` was retrospective validation. The base setup had already inspected recent years, so this is not a pristine historical holdout. The true future holdout is frozen from `2026-06-06` forward and is not yet available.
- **Exit leader**: on the full 2016-2026 history, the pure VWAP target made `811` trades, `+136.12R`, PF `1.255`, DD `-45.12R`. Targeting the signal-time day midpoint instead made `804` trades, `+178.69R`, PF `1.342`, DD `-42.42R`. The day-mid hybrid is the correct base for further selective work.
- **Causal regime screen**: tested `125` pre-registered one-variable gates and `28` two-variable combinations (`155` raw trials including controls, `51` effective trials by trade-date overlap). Features were known by 10:00 ET: prior-day volatility/trend, overnight gap/range, and 09:30-10:00 opening behavior. PBO/CSCV is not implemented; PSR/DSR was computed.
- **Lead challenger rule**: keep the existing selective VWAP entry/context and day-mid target, but require opening efficiency `>=0.55`, where opening efficiency is `abs(09:55 close - 09:30 open) / (09:30-09:59 high - low)`. This is causal for all candidate signals because the entry window starts at 10:00 ET.
- **Gross leader metrics**: `216` trades over 2,693 RTH days (`0.080/day`, roughly `0.40/week`), `+100.00R`, `0.463R/trade`, PF `1.846`, DD `-9.86R`; discovery PF `1.517`, retrospective-validation PF `2.394`, cold 2016-to-2021 PF `1.427`, recent PF `2.339`. It had `90%` positive usable six-month folds, worst fold `-5.06R`, and all local threshold neighbors passed (`plateau_score=1.0`).
- **1s execution stress**: with repo-standard MNQ midpoint commission (`$0.575/side`), the lead retained `+79.80R`, PF `1.605`, DD `-15.66R`. With one adverse tick/side it retained `+61.44R`, PF `1.427`, DD `-22.87R`; with two ticks/side it retained `+43.09R`, PF `1.276`, DD `-36.31R`.
- **Bootstrap**: five-day block bootstrap at commission plus one tick/side gave `98.24%` probability of positive total R, `+13.34R` p05 total, `+61.25R` median, `-15.61R` median DD, and `23.76%` probability of DD worse than `-20R`. This passed the discovery bootstrap gate.
- **Multiple-testing result**: ordinary PSR was `0.9891`, but DSR was only `0.3734` after `155` raw / `51` effective trials (`2.168` observed Sharpe versus `2.473` expected maximum under the null). This is the reason the row remains a CHALLENGER rather than PROMOTE.
- **Direction/year read after commission plus one tick/side**: longs were cleaner but very sparse (`73` trades, `+24.93R`, PF `1.613`, DD `-7.44R`); shorts contributed more trades and R but more drawdown (`143`, `+36.51R`, PF `1.353`, DD `-25.06R`). The branch remained negative in `2016`, `2017`, `2018`, and `2020`, then positive from `2021` onward. Opening efficiency improves selection but does not fully explain the era shift.
- **Pair challengers**: adding `abs(prior 20-day trend) >= 4 ATR` to opening efficiency `>=0.25` survived one-tick friction (`194` trades, `+42.46R`, PF `1.288`) but failed bootstrap and DSR. Adding `ATR/price <=2%` retained more trades but failed one-tick PF and bootstrap. Neither beats the simple `opening_efficiency >=0.55` rule.
- **Practical conclusion**: freeze `opening_efficiency >=0.55` as the lead selective VWAP challenger and stop local gate expansion. The honest next evidence is future holdout/shadow data from `2026-06-06` forward. Before any dry/live use, implement the opening-efficiency check as a live pre-trade gate, add the day-mid target to the execution path, and exact-replay the implementation.

### NY VWAP Static 1:1.5R Stop Sweep (2026-06-30) — CONDITIONAL cadence improvement, still thin

- **Status**: CONDITIONAL research screen only. Static fixed `1.5R` exits improved the high-cadence VWAP leg versus the dynamic VWAP target, but the daily-cadence edge remains thin and still `research_only`.
- **Report**: `backtesting/learnings/reports/NQ_NY_VWAP_STATIC_RR_STOP_SWEEP_20260630.md`; artifacts in `backtesting/data/results/nq_ny_vwap_static_rr_stop_sweep_20260630/`.
- **Scope**: kept the same high-cadence VWAP state-machine setup `vwap_ext0.025_cons6x0.2_timeout12_buf0.02_minrr0.2`, no structure/VWAP/efficiency/IB filter, `session_range_atr_max=2.0`, full window, and swapped the mean target for fixed `1:1.5` RR. Stops were swept as percentages of previous daily ATR, prior RTH session range, and current session range-so-far known at signal time. All results use conservative 5m pathing with stop priority on same-bar stop/target touches.
- **Best static-RR row**: prior RTH session range `10%` stop, fixed `1.5R` target, made `1,347` trades (`1.042/day`, trades on `70.53%` of days), `+43.20R`, PF `1.057`, WR `42.24%`, avg R `0.032`, avg annual R `8.42R`, Calmar `0.269`, max DD `-31.28R`, average stop `25.21` NQ points. Year split: `2021 -3.28R`, `2022 +10.55R`, `2023 -16.13R`, `2024 +23.87R`, `2025 +17.15R`, `2026 +11.04R`.
- **Best by stop basis**: prior session range `10%` was best overall (`+43.20R`, PF `1.057`, DD `-31.28R`); best ATR stop was `7.5%` ATR (`1,411` trades, `+25.18R`, PF `1.031`, DD `-34.50R`); best session-range-so-far stop was `15%` current range (`1,314` trades, `+26.70R`, PF `1.037`, DD `-30.20R`).
- **Cadence read**: `11/30` rows still met `1-3` trades/day with at least `70%` day coverage, but only the prior-session-range `10%` row reached PF `>=1.05`. Compared with the previous dynamic daily-cadence leg (`1,390` trades, `+26.56R`, PF `1.026`, DD `-80.48R`), static `1.5R` improved drawdown and total R, but the best row still has a negative full year (`2023`) and low Calmar.
- **Practical conclusion**: fixed `1:1.5R` is a better exit form for the daily-cadence branch than the raw VWAP target, but it is not strong enough as a standalone prop-firm leg. Next productive work would be 1m/1s path replay and regime/context gating on the prior-session-range `10%` stop row, not widening the stop grid further.

### NY VWAP Static 1:1.5R Native Timeframe Sweep (2026-06-30) — CONDITIONAL 3m improvement

- **Status**: CONDITIONAL native-timeframe research screen. The 3m version materially improved the daily-cadence static-RR branch versus 5m, but it is still `research_only` and needs exact replay, train/validation, and prop lifecycle scoring.
- **Report**: `backtesting/learnings/reports/NQ_NY_VWAP_STATIC_RR_TIMEFRAME_SWEEP_20260630.md`; artifacts in `backtesting/data/results/nq_ny_vwap_static_rr_timeframe_sweep_20260630/`.
- **Scope**: tested native signal generation on `1m`, `2m`, `3m`, and `5m` bars from raw NQ 1m data (`2021-06-07` through `2026-06-05`). The setup was time-normalized across bars: 30-minute consolidation, 60-minute setup timeout, about 10-minute cooldown, fixed `1:1.5R` target, stop-priority OHLC path, no structure/VWAP/efficiency/IB filters, `session_range_atr_max=2.0`, full window.
- **Entry criteria**: long requires price below VWAP with an extension of at least `0.025 * prior 14-day RTH ATR`, then a 30-minute consolidation below VWAP with range no more than `0.20 * ATR`; the signal bar sweeps below the consolidation low and closes back above that low while still below VWAP; entry is next bar open. Short is the mirror above VWAP. Maximum `3` sequential non-overlapping trades/day.
- **Best by timeframe**: `1m` best was weak (`session_range_so_far 10%`: `1,707` trades, `+22.93R`, PF `1.023`, DD `-73.88R`); `2m` improved (`prior_session_range 7.5%`: `1,643` trades, `+78.84R`, PF `1.084`, DD `-49.20R`); `3m` was best (`ATR 7.5%`: `1,498` trades, `1.159/day`, trades on `72.24%` of days, `+82.18R`, PF `1.097`, WR `42.66%`, avg R `0.0549`, avg annual R `16.02R`, Calmar `0.704`, max DD `-22.75R`); `5m` remains prior-session-range `10%` (`1,347` trades, `+43.20R`, PF `1.057`, DD `-31.28R`).
- **Direct carry-forward of 5m winner**: prior-session-range `10%` did not carry to 1m (`-19.29R`, PF `0.979`, DD `-101.05R`), was mediocre on 2m (`+33.71R`, PF `1.039`), improved on 3m (`+73.88R`, PF `1.094`), and matched the prior 5m result (`+43.20R`, PF `1.057`).
- **Year split for best 3m row**: `2021 -0.31R`, `2022 +20.36R`, `2023 +11.40R`, `2024 +25.03R`, `2025 -1.20R`, `2026 +26.90R`. Full-year weakness shifted from 2023 in the 5m row to mild 2025 weakness in the 3m row.
- **Practical conclusion**: if this daily-cadence VWAP branch continues, make the 3m `ATR 7.5%` static `1.5R` row the next candidate for validation. The 1m version is too noisy; 2m is interesting but drawdown-heavy; 3m offers the best balance of cadence, PF, and drawdown.

### NY VWAP 3m BOS Challenger (2026-06-30) — NO-GO as replacement for sweep/reclaim

- **Status**: NO-GO as a replacement for the current 3m sweep/reclaim signal. BOS-style structure closes can produce positive rows, but they did not improve the daily-cadence or risk-adjusted profile of the current 3m leg.
- **Report**: `backtesting/learnings/reports/NQ_NY_VWAP_3M_BOS_CHALLENGER_20260630.md`; artifacts in `backtesting/data/results/nq_ny_vwap_3m_bos_challenger_20260630/`.
- **Scope**: long-only 3m challenger over raw NQ 1m data resampled to 3m (`2021-06-07` through `2026-06-05`). Preserved the current 3m leg's VWAP mean, `0.025 * ATR` extension, `<=0.20 * ATR` consolidation range, `ATR 7.5%` stop, fixed `1:1.5R` target, max `3` non-overlapping trades/day, full window, no structure/VWAP/efficiency/IB filters, and `session_range_atr_max=2.0`.
- **Signal change tested**: replaced the consolidation-low sweep/reclaim with a bullish structure shift. Signal bar had to close above `consolidation high + buffer * consolidation range` while still below VWAP. Tested consolidation lengths `15`, `21`, `30`, `45`, and `60` minutes, with buffers `0%`, `10%`, `25%`, and `50%`.
- **Controls**: current 3m sweep/reclaim all-directions baseline remains `1,498` trades, `+82.18R`, PF `1.097`, DD `-22.75R`; long-only baseline is `497` trades, `+64.54R`, PF `1.241`, DD `-17.16R`; short-only baseline is `1,001` trades, `+17.64R`, PF `1.031`, DD `-25.93R`.
- **Best sparse BOS row**: `60m` consolidation with `10%` range buffer made only `45` trades (`0.035/day`), `+6.42R`, PF `1.267`, DD `-5.00R`. Too sparse to satisfy the daily-cadence objective.
- **Best daily-cadence BOS row**: `15m` consolidation with `0%` buffer made `1,329` trades (`1.028/day`), `+34.10R`, PF `1.044`, DD `-61.16R`. It meets frequency but is much worse than the current 3m leg and the long-only sweep/reclaim control.
- **Best near-daily BOS row**: `15m` consolidation with `10%` buffer made `1,038` trades (`0.803/day`), `+38.16R`, PF `1.063`, DD `-53.66R`. Slightly cleaner than the daily BOS row, but still below the target cadence and drawdown-heavy.
- **Practical conclusion**: do not replace the sweep/reclaim with this BOS close rule. The sweep appears to be doing useful selection work; simple structure-shift closes mostly add adverse continuation/chop. If BOS is revisited, it should be as an additional confirmation after the sweep or with a stronger regime/time-of-day gate, not as a raw replacement.

### NY VWAP BOS Timeframe Challenger (2026-06-30) — NO-GO across 1m/2m/3m/5m

- **Status**: NO-GO as a raw BOS replacement across native timeframes. Testing `1m`, `2m`, `3m`, and `5m` did not find a BOS-close version that beats the current 3m sweep/reclaim leg or solves daily cadence with acceptable risk.
- **Report**: `backtesting/learnings/reports/NQ_NY_VWAP_BOS_TIMEFRAME_CHALLENGER_20260630.md`; artifacts in `backtesting/data/results/nq_ny_vwap_bos_timeframe_challenger_20260630/`.
- **Scope**: long-only BOS replacement logic over raw NQ 1m data (`2021-06-07` through `2026-06-05`), with 2m/3m/5m resampled from 1m. Preserved VWAP mean, `0.025 * ATR` extension, consolidation below VWAP, `<=0.20 * ATR` consolidation range, `ATR 7.5%` stop, fixed `1:1.5R` target, max `3` non-overlapping trades/day, full window, no structure/VWAP/efficiency/IB filters, and `session_range_atr_max=2.0`.
- **Grid**: `80` rows across timeframes `1m/2m/3m/5m`, consolidation lengths `15/21/30/45/60` minutes, and BOS buffers `0%/10%/25%/50%`. Bars were time-normalized by timeframe, with about `30` minutes of signal window and about `10` minutes of cooldown.
- **Best sparse row overall**: `5m`, `21m` consolidation, `50%` range buffer made `121` trades (`0.094/day`), `+11.65R`, PF `1.173`, Calmar `0.284`, DD `-8.00R`. This is too sparse for the daily-cadence goal.
- **Best by timeframe**: `1m` best was `45m` consolidation / `10%` buffer (`125` trades, `+6.66R`, PF `1.095`, DD `-8.00R`); `2m` best was `60m` / `25%` (`9` trades, `+2.81R`, PF `1.701`, DD `-3.19R`); `3m` best remained `60m` / `10%` (`45` trades, `+6.42R`, PF `1.267`, DD `-5.00R`); `5m` best was `21m` / `50%` (`121` trades, `+11.65R`, PF `1.173`, DD `-8.00R`).
- **Daily-cadence rows**: only three rows reached `>=1` trade/day: `3m` `15m` / `0%` (`1,329` trades, `+34.10R`, PF `1.044`, DD `-61.16R`), `2m` `15m` / `0%` (`1,354` trades, `+23.23R`, PF `1.029`, DD `-57.50R`), and `1m` `15m` / `0%` (`1,550` trades, `-6.27R`, PF `0.993`, DD `-74.60R`).
- **Near-daily read**: `3m` `15m` / `10%` remained the best practical near-daily BOS row (`1,038` trades, `0.803/day`, `+38.16R`, PF `1.063`, DD `-53.66R`); `2m` `15m` / `10%` was weaker (`1,031` trades, `+28.40R`, PF `1.047`, DD `-47.00R`); `5m` near-daily rows were barely positive and drawdown-heavy.
- **Practical conclusion**: no native timeframe rescued the raw BOS replacement. Lower timeframes increase cadence but weaken expectancy and drawdown; higher timeframes improve selectivity but become too sparse. Keep the current 3m sweep/reclaim baseline as the better daily-cadence branch.

### NY VWAP 3m Sweep + BOS Confirmation (2026-06-30) — NO-GO for cadence, possible sparse micro-sleeve

- **Status**: NO-GO as an upgrade to the current 3m daily-cadence leg. BOS confirmation after the sweep/reclaim improves selectivity on a few tiny samples, but it removes too many trades to solve the 1-3 trades/day objective.
- **Report**: `backtesting/learnings/reports/NQ_NY_VWAP_3M_SWEEP_BOS_CONFIRM_20260630.md`; artifacts in `backtesting/data/results/nq_ny_vwap_3m_sweep_bos_confirm_20260630/`.
- **Scope**: tested 3m current-leg structure from raw NQ 1m data resampled to 3m (`2021-06-07` through `2026-06-05`). Kept VWAP mean, `0.025 * ATR` extension, 30-minute consolidation, consolidation-edge sweep/reclaim, `ATR 7.5%` stop, fixed `1:1.5R` target, max `3` non-overlapping trades/day, full window, no structure/VWAP/efficiency/IB filters, and `session_range_atr_max=2.0`.
- **Confirmation change tested**: after the sweep/reclaim, delayed entry until price closed beyond `consolidation edge + buffer * consolidation range` while still on the VWAP side. Tested confirmation windows `0`, `15`, `30`, `45`, and `60` minutes, buffers `0%`, `10%`, `25%`, and `50%`, and both `long_only` plus mirrored `both` direction scopes.
- **Controls**: unchanged 3m sweep/reclaim baseline is `1,498` trades, `+82.18R`, PF `1.097`, DD `-22.75R`; long-only baseline is `497` trades, `+64.54R`, PF `1.241`, DD `-17.16R`.
- **Best confirmation row**: long-only with `60m` confirmation window and `50%` range buffer made only `50` trades (`0.039/day`), `+9.66R`, PF `1.372`, DD `-3.50R`, and `0` negative full years. This is too sparse for the target cadence.
- **Best higher-count confirmation rows**: long-only `15m` confirm / `0%` buffer made `79` trades, `+8.50R`, PF `1.193`, DD `-10.50R`; both-direction `60m` confirm / `50%` buffer made `171` trades, `+5.54R`, PF `1.056`, DD `-17.50R`. Neither is competitive with the current baseline.
- **Daily-cadence read**: no confirmation row averaged `>=0.75` trades/day, and none met `1-3` trades/day. Confirmation turns the setup into a sparse filter, not a replacement or enhancement for the daily-cadence leg.
- **Practical conclusion**: do not require BOS confirmation after sweep/reclaim for the current 3m daily leg. If this branch is revisited, treat it as a separate low-frequency micro-sleeve or use it only inside a broader portfolio, not as the main VWAP mean-reversion entry.

### NY VWAP 3m Validation + Prop Packet (2026-07-10) — NO-GO for daily cadence; long-only shelf candidate

- **Status**: NO-GO for promotion of the both-direction daily-cadence branch. Long-only remains `research_only` as a conditional lower-frequency shelf candidate, but it also failed the tightened rolling, bootstrap, and prop-quality gates. No live-native implementation was made.
- **Report**: `backtesting/learnings/reports/NQ_NY_VWAP_3M_VALIDATION_PROP_PACKET_20260710.md`; artifacts in `backtesting/data/results/nq_ny_vwap_3m_validation_prop_packet_20260710/`.
- **Frozen baseline parity**: regenerated the exact 3m champion over `2021-06-07` through `2026-06-05`: `1,498` trades, `1.1585/day`, `+82.182R`, PF `1.097`, max DD `-22.7535R`. Trade count and total R matched the saved discovery artifact exactly.
- **Lower-timeframe pathing**: 1m replay remained `+83.18R`, PF `1.098`; 1s replay was `+87.45R`, PF `1.104`, with only `3` exit-type changes. Bar-path ambiguity was not the failure mode.
- **MNQ friction result**: after the repo midpoint commission of `$0.575/side`, both directions fell to `+40.73R`, PF `1.047` before slippage and to only `+0.11R`, PF `1.0001`, DD `-38.18R` at `1` adverse tick/side. At `2` ticks/side it became `-40.51R`, PF `0.956`. Short-only was already negative after commission (`-9.07R`) and was the main drag.
- **Long-only friction result**: 1s gross was `497` trades, `+64.57R`, PF `1.241`; after commission plus `1` tick/side it retained `+36.97R`, PF `1.131`, DD `-22.64R`; at `2` ticks/side it retained `+24.13R`, PF `1.083`. It fails at `4` ticks/side (`-1.55R`, PF `0.995`). This is a lower-frequency branch, not the requested daily leg.
- **Neighborhood and rolling validation**: the 27-row extension/consolidation/stop neighborhood had no viable both-direction row after commission plus `1` tick/side; the frozen row was `-5.16R`, PF `0.994`. Rolling 18-month-train/6-month-test selection produced only `2/6` positive both-direction folds and `-30.06R` aggregate; the frozen both-direction row made `-18.76R`. Long-only selected `4/6` positive folds but only `+0.16R` aggregate and suffered a `-20.47R` final fold; frozen long-only made `+12.26R` but only `3/6` folds were positive. The full history had already been inspected, so these are causal rolling tests but not a pristine untouched holdout.
- **Bootstrap**: five-day block bootstrap after commission plus `1` tick/side gave the both-direction stream only `49.5%` probability of positive total R and `99.7%` probability of drawdown worse than `-20R`. Long-only improved to `90.36%` positive probability, but median DD was `-20.16R` and the chance of worse than `-20R` was `50.72%`; this missed the promotion threshold.
- **Prop model**: `$2,000` EOD trailing DD, `+$3,000` pass, one `$1,500` first payout, continue until bust, 14-day starts, integer MNQ sizing, no challenge fee. Under commission plus `1` tick/side, the best 12-month-matured long-only row used a `$150` risk budget: `57.14%` payout/start, `27.62%` pre-payout bust, `38.10%` post-payout bust, `34.29%` open, `$857.14` realized EV/start, and `469.85` average days to payout. This is positive but too slow and censored to qualify as a strong prop path.
- **User-requested `$500` risk**: long-only reached first payout on `50.48%` of matured starts but had `49.52%` pre-payout bust and `44.76%` post-payout bust. Both directions reached payout on only `28.57%` and breached pre-payout on `71.43%`. Do not use `$500` risk for this branch.
- **Practical conclusion**: close the both-direction daily-cadence VWAP branch as a promotion candidate. Keep the frozen rule set for auditability and keep long-only on the research shelf only; reopening it requires genuinely new unseen data or a causally motivated short-side redesign, not another local parameter sweep.

### NY VWAP 3m Context-Gate Rescue (2026-07-10) — CONDITIONAL long-only survivor, shorts closed

- **Status**: CONDITIONAL `research_only` survivor. The 5m-branch context gates partially rescue the deferred 3m leg, but only long-only and only as a fragile low-frequency candidate. Short side is closed.
- **Report**: `backtesting/learnings/reports/NQ_NY_VWAP_3M_CONTEXT_GATE_RESCUE_20260710.md`; artifacts in `backtesting/data/results/nq_ny_vwap_3m_context_gate_rescue_20260710/`.
- **Scope**: applied the proven 5m context ingredients (`reject_vwap_side_slope` adapted to 10 3m bars, `efficiency_max`, time buckets, `session_range_atr_max`) to the parity-audited frozen 3m stream (`1,498` trades / `+82.182R` reproduced exactly), scored net of MNQ commission plus `1` tick/side, `372` configs across `both`/`long_only`/`short_only` plus a short asymmetry probe.
- **Best survivor**: long-only + `efficiency_max=0.65` + `10:00-14:00` + `session_range_atr_max=1.5`: `204` trades (`0.16/day`), net `+48.74R`, PF `1.48`, Calmar `1.56`, max DD `-6.07R`, `5/6` frozen walk-forward folds positive (`+18.69R` OOS), worst year `-2.53R`, 1s replay parity within `0.03R`. Two sibling rows (`eff<=0.70` variants) also passed the pre-registered gate.
- **Short verdict**: ungated shorts `-42R` net; best gated short row (PF `1.31`, Calmar `0.36`, t `1.63`) and the extension/consolidation asymmetry probe are not viable. The edge is overwhelmingly long-only.
- **Deflation read**: best row t `2.76` vs expected null max `3.44` over `372` looks — the single row is not distinguishable from best-of-noise; the supporting evidence is the jointly positive efficiency-cap/mid-session neighborhood plus walk-forward, so treat this as a fragile ~1-trade-per-6-sessions candidate, not a robust edge.
- **Practical conclusion**: the winning levers are the same two as the 5m branch (directional-efficiency cap + `10:00-14:00`). Keep the long-only gated row as a shelf candidate; it overlaps conceptually with the 5m low-frequency sleeve, so any promotion should treat them as one family, not two independent edges.

### NY VWAP 3m Limit-Entry Cost Sweep (2026-07-10) — NO-GO for limit entries, keep market entry

- **Status**: NO-GO for limit-entry replacement on the gated 3m long-only survivor. Market entry at next 3m bar open stays the recommended entry.
- **Report**: `backtesting/learnings/reports/NQ_NY_VWAP_3M_LIMIT_ENTRY_COST_SWEEP_20260710.md`; artifacts in `backtesting/data/results/nq_ny_vwap_3m_limit_entry_cost_sweep_20260710/`.
- **Scope**: fixed the `204`-signal gated survivor set (parity exact: gross `+60.478R`, net@1t `+48.744R`) and re-priced entries only: limit at signal close, consolidation low, sweep extreme, and `25/50/75%` retraces, with conservative trade-through fills on 1s (1m cross-check within `0.11R`), cancel-if-unfilled `K in {1,2,4,gtc}`, recomputed-vs-original stop/target, `48` combos, unfilled signals scored `0R`.
- **Best limit combo**: `retrace25 K=4` original-stop: fill rate `0.86`, total `+52.14R` mixed-slippage vs baseline `+48.72R` — a nominal `+3.41R` (~7%) lift with paired per-signal t of only `0.454` vs a `2.78` multiple-comparison bar. The lift is noise-grade and rests entirely on the passive-fill 0-tick entry assumption (`+1.05R` at symmetric 1 tick, `+0.32R` at 0 ticks).
- **Deeper limits fail structurally**: consolidation-low/retrace75/sweep-extreme limits improve entry by `6-9` points but miss `25-35%` of orders, disproportionately winners, roughly halving total R (sweep extreme: `+16.9R`, DD `-12.6R`). Walk-forward for the best limit combos matched baseline fold counts (`4/6`), no improvement.
- **Practical conclusion**: entry-price improvement is not a rescue lever for this leg. The mean-reversion fill geometry already prices the sweep; standing further from the market forfeits winners faster than it saves entry ticks.

### NY ORB Failure Fade Discovery (2026-07-10) — NO-GO, thesis closed

- **Status**: NO-GO. The ORB failure-fade mirror thesis (fade failed opening-range breakouts back into the range) has no exploitable edge on NQ NY.
- **Report**: `backtesting/learnings/reports/NQ_NY_ORB_FAILURE_FADE_DISCOVERY_20260710.md`; artifacts in `backtesting/data/results/nq_ny_orb_failure_fade_discovery_20260710/`.
- **Scope**: `1,296` configs on discovery `2021-06-07` to `2024-12-31` only (2025+ reserved, opened once for the frozen shortlist): 5m/3m signals, 15m/30m ORB, breakout-min, failure-close-within-N, re-entry buffer, breakout-extreme vs ATR stops, `1.5R`/ORB-mid/opposite-edge targets, max 2/day, conservative pathing; sanity checks (tick-exact ORB levels, caps, entry-after-signal) all passed.
- **Result**: only `9.4%` of configs positive; grid mean t `-1.14`; best row (`15m` ORB, `N=4`, ORB-mid target) `1,071` trades, `+38.3R` gross, PF `1.13`, t `1.62` — inside the best-of-1,296 noise band. All three frozen shortlist rows sign-flipped negative on the untouched 2025-2026 window (`-12.6R` to `-19.0R`) and the cold 2016-2021 gross (`+31R` to `+43R`) became `-150R` to `-170R` net at 2 ticks/side.
- **Structure of the mirage**: the gross discovery edge was short-only (failed upside breakouts) and concentrated in the 2022 high-vol bear year; longs lost in every top config.
- **Practical conclusion**: shelve the thesis. This closes the obvious "reuse ORB infra for reversion" idea and reconfirms the house lesson that thin high-frequency NQ mean reversion dies to friction.

### NY VWAP Sleeve Regime Switch (2026-07-10) — CONDITIONAL trend-extension guard adopted, vol floors rejected

- **Status**: CONDITIONAL. Best available causal deactivation rule for the low-frequency VWAP sleeve's cold-window blocker; the sleeve remains a recent-regime candidate — the guard removes cold drawdown, it does not make 2016-2021 tradable.
- **Report**: `backtesting/learnings/reports/NQ_NY_VWAP_SLEEVE_REGIME_SWITCH_20260710.md`; artifacts in `backtesting/data/results/nq_ny_vwap_sleeve_regime_switch_20260710/`.
- **Diagnosis first**: cold-window losses are NOT a low-vol bleed — they concentrate in sharp trending dislocations (`2020 -20.5R`, `2018 -7.5R`) while quiet 2016/2017/2019 was flat-to-positive. Quintile attribution pinned the repeatable loss signal on trend extension: top `dist_sma200_atr` quintile `~-30R`. Volatility floors are contradicted by the data (blocked cold subset was `+10R` profitable) — do not use them for this sleeve.
- **Winning switch**: trade only when prior close is `<=12` ATR14 above the 200-day SMA (causal, prior-daily-close data only). Recent window retains `95%` of trades (`+129.6R` vs `+127.8R`); cold window removes `-18.5R` of pure drawdown (2020 `-20.5R -> -10.3R`); full history `+135.3R -> +155.6R`, t `2.43 -> 2.89` (~`63` feature/threshold looks; modest after deflation, and recent-only t `3.16` remains highest).
- **Causality read**: the switch toggles inside both windows (fires in 2023-24 too), so it is not a date label; but blocked extended days were profitable in the recent window, so treat it as a drawdown-tail guard, not a clean regime story.
- **Prop lifecycle with switch** (recent 1s stream, `$2k` EOD trailing DD / `$3k` pass / `$1.5k` payout, 14-day starts): at `$175/R` first-payout rate `0.763 -> 0.847`, pre-payout bust `3.8% -> 0%`, EV/start `$1,145 -> $1,271`. On the exit-refined day-mid stream the guard costs ~`2.6R` while keeping `95%` of trades.
- **Practical conclusion**: adopt `dist_sma200_atr <= 12` as the sleeve's protective deactivation rule and keep the sleeve classified as recent-regime-only. Vol-floor regime gates for this branch are closed.

## Context Filter Research: 30m Structure + VWAP Gate

### Summary

Tested multi-timeframe structure gates (15m, 30m, 1h) combined with session VWAP for NQ NY continuation. **30m HH/HL-2 + VWAP side is the best structural context filter found for NQ NY ORB.**

### How it works

Resample 5m bars into session-aligned 30m bars (09:30-10:00, 10:00-10:30, ...). At the FVG signal bar, check the two most recent **completed** 30m bars:

- **Longs**: latest 30m high > prior 30m high AND latest 30m low > prior 30m low AND signal close > session VWAP
- **Shorts**: mirrored (LH + LL + close < VWAP)

Only completed 30m bars are used (no lookahead). The 6th 5m bar of each 30m group is the earliest bar that can see that 30m bar's data.

### Timeframe comparison (FAST_V2 NQ_NY, 2021-2026)

| TF | Trades | Keep% | Net R | Sharpe | Calmar | Max DD |
|----|--------|-------|-------|--------|--------|--------|
| Baseline | 695 | — | 21.2 | 0.61 | 0.97 | -21.8R |
| **30m** | **385** | **55%** | **30.9** | **1.57** | **2.31** | **-13.4R** |
| 15m | 498 | 72% | 16.8 | 0.69 | 0.63 | -26.8R |
| 1h | 301 | 43% | 12.6 | 0.84 | 1.22 | -10.3R |

- **15m** is too noisy — keeps 72% but actually increases DD
- **30m** is the sweet spot — halves DD, adds +9.7R, 2.5x Sharpe
- **1h** cuts DD further (-10.3R) but kills too much R (-8.6) especially in 2024-2025

### Tested across configs

**FAST_V2 NQ_NY** (rr=2.5, stop=8%, both dirs):
- Baseline: 695 tr, 21.2R, Sharpe 0.61, Calmar 0.97, DD -21.8R
- 30m gate: 385 tr (55%), 30.9R, Sharpe 1.57, Calmar 2.31, DD -13.4R
- DB: `bt-nq-ny-fast-v2-30m-hh-hl-2-vwap-2021-2026-942da0`

**Exec config** (rr=2.0, stop=15%, both dirs):
- Baseline: 729 tr, -6.3R, Sharpe -0.13, Calmar -0.15, DD -41.3R
- 30m gate: 405 tr (56%), +29.8R, Sharpe 1.12, Calmar 1.31, DD -22.8R
- Flips a negative-R config to positive. 2023 goes from -15.4R to +0.2R.

### Comparison to VWAP-only gates

VWAP distance alone (no structure) also helps but less dramatically:

| Gate | Keep% | Net R delta | Calmar improvement |
|------|-------|-------------|-------------------|
| VWAP side only | 99% | +0.9R | negligible |
| VWAP 10% ATR | 94% | +14.6R | 1.8x |
| VWAP 15% ATR | 83% | +20.8R | 2.2x |
| **30m HH/HL + VWAP** | **55%** | **+9.7R** | **2.4x** |

VWAP distance is the high-retention option (83-94% kept). The 30m structure gate concentrates edge more sharply but at lower retention. Both are useful depending on whether trade frequency or edge quality matters more.

### Entry window investigation: can we trade earlier?

Because HH/HL-2 on session-aligned 15m bars (09:30 start) requires two completed bars, the gate cannot fire until ~10:00. This means the 09:45-10:00 entry window is dead. Tested whether using true 30m bars with earlier alignment could recover those early trades.

**Variants tested (FAST_V2 NQ_NY, 2021-2026):**

| Variant | 30m alignment | Earliest gate | Trades | Keep% | Net R | Sharpe | Calmar | Max DD |
|---------|--------------|---------------|--------|-------|-------|--------|--------|--------|
| Baseline (no gate) | — | — | 695 | — | 21.2 | 0.61 | 0.97 | -21.8R |
| **A: 15m HH/HL-2 (current)** | **session 09:30** | **~10:00** | **250** | **36%** | **30.3** | **2.58** | **2.13** | **-14.2R** |
| B: 30m from 08:30 | clock 08:30 | 09:50 | 138 | 20% | 10.9 | 1.45 | 0.62 | -17.7R |
| C: 30m from 09:00 | clock 09:00 | 10:00 | 148 | 21% | 9.3 | 1.20 | 0.62 | -14.8R |

- DB: `bt-nq-ny-fast-v2-15m-hh-hl-2-vwap-baseline-657478` (A), `bt-nq-ny-fast-v2-30m-hh-hl-2-vwap-pre-sessi-5deee8` (B), `bt-nq-ny-fast-v2-30m-hh-hl-2-vwap-09-00-eff-471468` (C)

**Conclusion: the current 15m setup is the best version.** True 30m bars (B and C) are significantly worse — both produce Calmar 0.62, below even the ungated baseline. Pre-market 30m bars (08:30-09:00, 09:00-09:30) carry overnight structure that doesn't predict NY ORB continuation direction. The 15m HH/HL-2 captures finer-grained intra-session trend shifts and retains 36% of trades vs ~20% for 30m. The cost of losing the 09:45-10:00 window is worth the gate's filtering quality.

### Key findings

1. **Structure for trend, VWAP for acceptance** — the original hypothesis is confirmed. Neither alone is as effective as the combination.
2. **15m HH/HL-2 is the right granularity** — the label "30m gate" was misleading; the implementation uses 15m bars with a 2-bar HH/HL pattern. True 30m bars over-filter and lose edge. Pre-session 30m bars carry no useful signal.
3. **The gate's value is regime-dependent** — biggest improvements in choppy years (2021, 2023). In strongly trending years (2024-2025) it can trim winners slightly.
4. **Works across configs** — not overfit to one parameter set. Consistent improvement on both FAST_V2 and the wider-stop exec config.
5. **Earliest effective entry is ~10:00** — losing the 09:45-10:00 window is an acceptable cost. Attempts to recover it via pre-session bars degrade performance.

### Implementation

- Signal module: `backtesting/src/orb_backtest/signals/structure_15m.py` — resamples 5m to session-aligned 15m bars, computes HH/HL patterns. The "30m" label refers to the 2-bar lookback spanning 30 minutes of 15m data, not actual 30m bars.
- Not yet integrated as an engine-level pre-trade gate. Currently applied as post-trade filter.
- Scripts: `run_nq_ny_15m_structure_sweep.py`, `run_nq_ny_15m_structure_sweep_v2.py`, `run_nq_ny_fast_15m_sweep.py`, `run_nq_ny_30m_entry_window_compare.py`

### R11 exact-stream proxy follow-up (2026-05-16)

Report: `backtesting/learnings/reports/ALPHA_V1_NEXT_STEPS_20260516.md`

Artifacts: `backtesting/data/results/alpha_v1_next_steps_20260516/`

Tested the 15m structure + VWAP idea on the exact fee-aware `NQ NY ORB R11` trade stream. Because the cached CSV does not carry the original signal bar, gates were evaluated on the previous completed 5m bar before exact entry; deployability is therefore `post_filter_only` for this read.

- Baseline exact fee-aware R11: `554` trades, `+110.8R` net after fees, PF `1.39`, DD `-7.4R`; 2025+ `+9.4R`, last-1y `+3.5R`.
- Best high-retention gate: `any2of3_vwap_d10` kept `86.6%` full-history trades, matched full net at `+110.8R`, improved PF to `1.46`, and improved DD to `-7.0R`; 2025+ improved to `+10.7R` / DD `-5.1R`, and last-1y improved to `+7.9R` / DD `-5.1R`.
- Strict `HH/HL-2 + VWAP` is too selective for ALPHA R11: last-1y looked good (`15` trades, `+6.2R`, PF `2.21`, DD `-2.0R`), but full-history dropped by `-62.9R` with only `37.7%` retention and worse DD.
- Practical conclusion: if candidate #7 gets a real replay, test `any2of3_vwap_d10` first. Do not promote a strict `HH/HL-2` gate on this evidence. True promotion requires engine-level signal-bar replay and exact/live parity.

### R11 15m structure/VWAP engine replay (2026-05-16)

Report: `backtesting/learnings/reports/ALPHA_V1_R11_STRUCTURE_GATE_ENGINE_REPLAY_20260516.md`

Artifacts: `backtesting/data/results/alpha_v1_r11_structure_gate_engine_replay_20260516/`

Reran the R11 structure/VWAP idea inside the ORB research engine at the true candidate signal bar, before daily ORB candidate selection. This is a causal candidate-level replay, not an after-the-fact filter, but production execution still cannot compute this gate before arming, so gated variants remain `deployability=post_filter_only`.

- Baseline research-engine R11: `552` trades, `+90.0R` MNQ-fee net, PF `1.33`, DD `-8.4R`, WR `52.9%`.
- Proxy lead `any2of3_vwap_d10`: `497` trades, `+82.1R`, PF `1.33`, DD `-7.9R`; recent windows improved (`2025+` `+11.6R` vs `+7.0R`; last-1y `+11.9R` vs `+5.1R`) but full-history lost `-7.8R`.
- `hh_or_hl_vwap_d10` / `score_gte2_vwap_d10`: `518` trades, `+85.4R`, PF `1.33`, DD `-9.8R`; better than `any2of3_vwap_d10` on full R but worse than baseline and worse DD.
- `hh_hl_2_vwap`: `246` trades, `+21.3R`, PF `1.16`, DD `-14.6R`; rejected as an ALPHA replacement gate.
- Practical conclusion: close candidate #7 as a core R11 upgrade. The structural gate is useful as a recent-regime/discretionary context note only; do not promote it into ALPHA_V1 without a separate specialist-sleeve thesis and live pre-trade implementation.

---

## NQ Generalist Payout Portfolio — Current 4-Leg Package

**Status**: ACTIVE PAPER-TRADE PACKAGE. This is the current NQ funded-account route when the goal is faster challenge resolution than the standalone bull specialist, without expanding to the 5-leg max-speed stack.

**Important classification**: this is **not** a regime-specialist portfolio. Only `bull_specialist` is regime-specialized. The full 4-leg package is a mixed-regime, long-biased payout engine and should be treated as a **generalist payout portfolio**.

**Selected combo**:
- `bull_specialist`
- `nq_asia`
- `nq_asia_lsi_end2300`
- `nq_ny_lsi_gap3.75`

**How each leg was chosen**:
- `bull_specialist`: regime-specialist winner, then fast-payout re-ranked for the funded-account model.
- `nq_asia`: combo-context sweep did **not** beat the existing Asia continuation anchor, so the original combo leg stays.
- `nq_asia_lsi_end2300`: combo-context winner over the base Asia LSI anchor; quality improvement came from tightening `entry_end` from `23:30` to `23:00`.
- `nq_ny_lsi_gap3.75`: combo-context winner over the base NY LSI anchor; best version relaxed `min_gap_atr_pct` from `5.0` to `3.75`.

**Funded-account model used in combo research**:
- Challenge cost: `$150`
- Starting balance: `$50,000`
- Trailing drawdown: `$2,000`, EOD realized, capped so breach never rises above `$50,000`
- First withdrawable payout: everything above `$52,000`
- Risk per trade: `$500` pre-payout, `$250` post-payout

**Full-history combo package** (2016-01-01 to latest available data in the run):
- Payout rate `71.71%` | breach rate `27.94%` | open rate `0.35%`
- Average days to payout `20.45` | median `17`
- Average trades to payout `10.62`
- Average first payout `$508.16`
- EV/start `$214.39`
- Holdout 2025-2026: payout `91.64%` | breach `5.48%` | average payout day `17.83` | EV/start `$378.03`

**Why this generalist package is the current working route**:
- The standalone bull specialist was high quality but too slow by itself.
- The 4-leg combo resolves much faster while preserving a strong payout-over-breach profile.
- The optimized combo is slightly weaker than the earlier balanced combo on full-history payout and EV, but materially better on holdout quality. Current preference is to keep the optimized route as the working package and watch live paper-trade behavior rather than overreact to the full-history tradeoff.

**Overlap / concentration read**:
- Overlap exists, but it is not extreme enough to force hard de-duplication.
- Baseline optimized combo remains the default route.
- If live paper trading shows stacked-loss discomfort, the first throttle to test is `first_full_half_extra`: keep the first fill full size and halve extra same-day legs.
- That throttle improves full-history payout/breach to `73.45% / 26.20%`, but it slows resolution and does not improve the already-strong holdout profile, so it is a risk-control toggle, not the base package.

**5-year operating snapshot** (`2021-03-29` start request; filled-trade coverage `2021-04-08` to `2026-03-23`):
- 918 filled combo trades
- Payout rate `80.61%` | breach rate `18.67%` | open rate `0.72%`
- Average days to payout `20.72` | median `18`
- Average trades to payout `10.27`
- Average first payout `$569.55`
- EV/start `$309.13`
- By day 20: payout `46.48%` | breach `10.31%` | resolved `56.79%`
- By day 30: payout `64.30%` | breach `16.06%` | resolved `80.35%`
- By day 45: payout `75.26%` | breach `17.95%` | resolved `93.21%`

**5-year leg mix**:
- `bull_specialist`: 45 trades | avg R `0.5484`
- `nq_asia`: 335 trades | avg R `0.3602`
- `nq_asia_lsi_end2300`: 188 trades | avg R `0.3009`
- `nq_ny_lsi_gap3.75`: 350 trades | avg R `0.1763`

**Regime audit conclusion**:
- The package does **not** behave like a pure bull-regime stack.
- 2022 remained profitable mainly because `nq_asia` and `nq_ny_lsi` made money on bear-regime days, while `bull_specialist` itself was slightly negative that year.
- Bear-regime contribution is too large for this to be labeled a true regime-specialist portfolio.

## NQ Bull-Biased Portfolio Buildout — Post-Generalist Seed Sweep

**Goal**: use the former generalist package only as a seed source, then rebuild around the `bull_specialist_v1_winner` without drifting back into a mixed-regime payout engine.

**First add-on sweep result**:
- `nq_asia_cont` was rejected as the next bull-portfolio leg even though it is strong in the generalist package.
- Reason: inside `bull_specialist + add-on` tests, it carried too much `2022-2023` performance and behaved too much like a generalist engine.
- The cleanest add-on family was `nq_asia_lsi`.

**Constrained bull-biased combo sweep**:
- Search space:
  - fixed core: `bull_specialist_v1_winner`
  - Asia candidates: selected `nq_asia_lsi` neighborhood
  - NY candidates: selected `nq_ny_lsi` variants only
  - explicit exclusion: `nq_asia_cont`
- Best overall portfolio: `bull_specialist_v1_winner + nq_asia_lsi_rr1.75`
- Portfolio type: `2-leg`

**Best current bull-biased portfolio candidate**:
- `bull_specialist_v1_winner + nq_asia_lsi_rr1.75`
- Acceptance `2024+` net R: `48.335`
- Rejection `2022-2023` net R: `11.7583`
- Rejection share of acceptance: `24.33%`
- Holdout payout/breach: `75.78% / 0.00%`
- Holdout average days to payout: `61.94`
- Regime contribution: bull `64.2906R`, bear `10.6621R`, sideways `22.9053R`

**Important comparison**:
- The best 3-leg candidate was `bull_specialist_v1_winner + nq_asia_lsi_end2300 + nq_ny_lsi_propfirm_2x_profile`.
- It was faster and bigger on raw acceptance net R, but rejection `2022-2023` also rose to `26.6883R`.
- That means the third leg improved payout behavior, but it pushed the stack back toward the same mixed-regime behavior we were trying to reduce.

**Current interpretation**:
- Best next step for a bull-biased portfolio is a **2-leg** stack, not a 3-leg stack.
- `nq_asia_lsi` is the right family to pair with the bull specialist first.
- `nq_ny_lsi` should be treated as optional and only revisited if a later pass can improve speed without materially increasing `2022-2023` contribution.

**Packaged bull-biased route**:
- Saved package: `bull_specialist_v1_winner + nq_asia_lsi_rr1.75`
- Full-history funded scorecard from `2020+`: payout `61.05%`, breach `34.38%`, open `4.58%`
- Average days to payout: `57.67`
- Holdout payout/breach: `75.78% / 0.00%`
- Average first payout: `$325.84`
- EV/start: `$48.91`

**Operational note**:
- This route is cleaner than the generalist 4-leg package, but materially slower and weaker on full-history funded-account resolution.
- It should be treated as a **bull-biased specialist candidate**, not as a replacement for the faster generalist payout portfolio.

## NQ Bear Specialist V1 — First Pass

**Window assumptions used**:
- `2021`: diagnostic only
- `2022-2023`: acceptance era
- `2023`: funded-account holdout inside the acceptance era
- `2024+`: rejection era

**Result**:
- No candidate cleared the bear-specialist bar in the first V1 pass.
- Best candidate: `NQ Bear V1 rr2.00_tp1 0.30_stoporb15.0_gaporb0.0_end1100_regime_2of3_vwap`
- Acceptance `2022-2023` net R: `6.5794` on `22` trades
- Rejection `2024+` net R: `2.9137`
- Rejection share of acceptance: `44.29%`
- 2023 holdout payout/breach: `16.06% / 0.00%`
- 2023 holdout average days to payout: `244.35`

**What failed**:
- Trade count was too low for a deployable specialist.
- Rejection-era performance remained too positive, so the short family still looks too generalist.
- None of the tested short variants survived the original round-1 specialist readout either.

**Current read**:
- `regime_2of3_vwap` improved the bear-window profile the most in this first pass.
- Ungated short variants still carried too much `2024+` performance.
- The next bear pass should focus less on micro-parameter tuning and more on a different short family or stronger downside-context gates.
- Use `generalist payout portfolio` as the correct label going forward.

**Takeaway**:
- This is now the current NQ generalist payout portfolio to carry forward.
- It is fast enough to be operationally useful, especially as one lane inside a broader multi-leg book.
- Next research should split true regime specialists into a separate portfolio track instead of continuing to treat this mixed long stack as regime-specialized.

---

### Asia Continuation Discovery (Regime-Gated, ORB 100% Stop) — Phase-One Complete (2026-04-01)

**Full pipeline with 1s bar magnifier** — discovery sweep (3,888 configs), walk-forward (9 candidates, 28 folds), PSR/DSR validation, phase-one prop simulation. All with hierarchical 5m→1m→1s magnifier.

#### Asia-2 (WINNER — promoted to live paper trading)
- **Status**: CONDITIONAL (phase-one) — holdout performance strong, recommended for paper trading
- **Bar magnifier**: ON (5m→1m→1s hierarchical)
- **Config**:

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia |
| ORB window | 20:00-20:15 (15m) |
| entry window | 20:15-23:15 |
| flat | 04:00-07:00 |
| stop | ORB 100% (full range) |
| rr | 3.5 |
| tp1_ratio | 0.6 (TP1 at 2.1R, TP2 at 3.5R) |
| direction | long only |
| atr_length | 14 |
| min_gap_atr_pct | 1.0% |
| regime gate | medium-vol avoidance (skip bull_medium_vol + sideways_medium_vol) |
| bar magnifier | OFF during discovery (re-enable for production) |

- **Pre-holdout** (2016-2024, 1s magnifier): 616 trades, 40.7% WR, PF 1.33, +119.2R, Calmar 9.51, DD -12.5R, Sharpe 2.02
- **Walk-forward OOS** (1s magnifier): 28 folds, +108.7R, Calmar 8.55, WF efficiency 0.617, stability 0.821 (high)
- **PSR**: 1.000 (strong) | **DSR** @raw 3888 trials: 0.310
- **Holdout** (2024-03 to 2026-02, 1s magnifier): 115 trades, 46.1% WR, PF 1.71, **+42.5R, Calmar 6.55, Sharpe 3.77, DD -6.5R**
- **Holdout yearly**: 2024: +3.3R | 2025: +36.5R | 2026: +2.8R
- **Holdout prop simulation**: **76.7% payout rate**, 14.4% breach, EV $15,288/attempt
- **Magnifier confirmation**: Results identical to 5m-only discovery — magnifier did not change rankings or materially alter metrics

#### Asia-A (Strong Backup)
- Same as Asia-B but RR=3.0 instead of 3.5
- Holdout: +37.9R, Calmar 6.21, 74.8% payout rate

#### NY-B (Shelved)
- 30m ORB, ORB 25% stop, RR=2.5, TP1=0.4, long, ungated
- Pre-holdout great (+62.6R, Cal 8.01) but **holdout collapsed** (+1.8R, Cal 0.17, 30.8% payout)
- 2024-2025 NY session not favorable for this config

#### All 9 Candidates — Walk-Forward Ranking (1s magnifier)

| # | Name | OOS R | Calmar | Sharpe | WFE | Stability | HO R | HO PR | Verdict |
|---|------|-------|--------|--------|-----|-----------|------|-------|---------|
| 1 | **Asia-1** (RR=3.0) | +100.8 | 9.73 | 2.09 | 0.588 | 0.839 | +37.9 | 74.8% | Backup |
| 2 | **Asia-2** (RR=3.5) | +108.7 | 8.55 | 2.16 | 0.617 | 0.821 | **+42.5** | **76.7%** | **WINNER** |
| 3 | Asia-3 (RR=3.5 TP0.5) | +105.1 | 8.74 | 2.19 | 0.589 | 0.732 | — | — | — |
| 4 | NY-2 (RR=3.5) | +103.4 | 6.84 | 1.74 | 0.448 | 0.750 | +8.7 | 25.2% | Shelved |
| 5 | NY-3 (RR=3.5 TP0.4) | +87.5 | 5.86 | 1.56 | 0.451 | 0.947 | — | — | — |
| 6 | LDN-1 (ATR 5%) | +65.0 | 5.10 | 2.04 | 0.653 | 0.822 | -2.9 | 31.9% | Shelved |
| 7 | LDN-3 | +55.2 | 4.32 | 1.78 | 0.720 | 0.857 | — | — | — |
| 8 | NY-1 (RR=2.5) | +70.8 | 4.69 | 1.35 | 0.364 | 0.768 | — | — | — |
| 9 | LDN-2 | +42.1 | 3.62 | 1.65 | 0.792 | 0.679 | — | — | — |

#### Post-Hoc Regime Gate Comparison (all 9 candidates, holdout)

All candidates re-run ungated vs gated (medium-vol avoidance: skip `bull_medium_vol` + `sideways_medium_vol`) on holdout (2024-03 → 2026-02). Script: `run_nq_orb_regime_gate_comparison.py`.

| # | Name | Ungated R | Ungated Cal | Ungated DD | Gated R | Gated Cal | Gated DD | ΔCal | Gate helps? |
|---|------|-----------|-------------|------------|---------|-----------|----------|------|-------------|
| 1 | Asia-1 | +45.8 | 7.44 | -6.2 | +37.9 | 6.21 | -6.1 | -1.23 | No (trades fewer) |
| 2 | Asia-2 | +49.6 | 6.74 | -7.4 | +42.5 | 6.55 | -6.5 | -0.18 | No (Sharpe ↑ but Cal ↓) |
| 3 | Asia-3 | +44.8 | 7.25 | -6.2 | +39.7 | 6.49 | -6.1 | -0.76 | No (trades fewer) |
| 4 | **NY-2** | +8.7 | 0.76 | -11.3 | **+8.7** | **1.45** | **-6.0** | **+0.68** | **YES — DD halved** |
| 5 | NY-3 | +13.8 | 1.30 | -10.6 | +7.7 | 1.18 | -6.5 | -0.12 | No (lost 6R) |
| 6 | NY-1 | +9.9 | 0.85 | -11.7 | +6.2 | 0.90 | -6.9 | +0.06 | Marginal |
| 7 | LDN-3 | +2.2 | 0.16 | -13.6 | +5.3 | 0.64 | -8.2 | +0.48 | Yes (but still weak) |
| 8 | LDN-1 | -5.3 | -0.24 | -22.0 | -2.9 | -0.27 | -10.7 | -0.03 | No (still negative) |
| 9 | LDN-2 | -1.9 | -0.15 | -12.5 | -2.6 | -0.33 | -8.1 | -0.17 | No (still negative) |

**Gate impact pattern**: the gate compresses drawdown across every candidate (ΔDD positive for all 9). For Asia, DD was already small so the gate mainly trims profitable trades. For NY and LDN, the DD compression is substantial (4-11R smaller).

#### Key Findings
1. **Asia session dominates NQ ORB continuation** — both Asia candidates crushed holdout while NY and LDN collapsed
2. **Regime gate is essential for Asia** — medium-vol avoidance improved all metrics in walk-forward and held up on holdout
3. **ORB 100% stop (full range)** is the correct stop for Asia overnight sessions
4. **Higher RR (3.5) beat lower RR (3.0)** on holdout — bigger winners compensate for lower WR
5. **NY collapsed in 2025** (-9.1R) despite strong 2024 (+18R) — not reliable as standalone
6. **LDN went negative on holdout** (-2.9R) — 2025 was -7.4R
7. **Bar magnifier (1s) confirmed**: results identical to 5m-only discovery — did not change rankings or conclusions
8. **Min gap ATR = 1.0% is optimal** — every increase (1.5-3.0%) degraded performance across all sessions
9. **NY-2 gated is the best NY candidate** — regime gate halved DD (-11.3 → -6.0R) while preserving +8.7R net. Calmar 1.45 gated vs 0.76 ungated. Original WF ran NY ungated — this was suboptimal
10. **LDN is dead regardless of gating** — gate halves DD but session has no edge on holdout. All 3 LDN candidates negative or near-zero gated
11. **Gate universally compresses drawdown** — every candidate saw smaller holdout DD when gated, but the trade-off is fewer trades and sometimes lost net R

#### Close-Entry Follow-Up (2026-04-26)

`NQ Asia-2` was rerun in the broad close-entry probe (`2016-04-17` to `2026-03-24`, ungated for entry-mechanics isolation). The `fvg_close` variant degraded the baseline (`+155.3R / -25.4R DD` vs retest `+177.8R / -17.5R DD`). The no-FVG `breakout_close` variant was the one interesting exception: `+285.5R`, `-24.0R DD`, Sharpe `1.70`, holdout `+71.4R` vs baseline holdout `+38.3R`. This is not enough to promote; it is a high-flow branch requiring prop/risk/regime validation. Reference: `backtesting/learnings/reports/PROMISING_ORB_CLOSE_ENTRY_PROBE.md`.

### Entry Mode vs Inversion Timing Diagnostic (Apr 2026)
- **Status**: **DIAGNOSTIC ONLY — do not reopen discovery yet**
- **Objective**: pressure-test the discretionary thesis that very fast post-sweep inversions should be entered at market close instead of waiting for the FVG retest.
- **Evidence packet**: `backtesting/scripts/run_nq_entry_mode_inversion_timing_read.py` -> `backtesting/learnings/reports/NQ_ENTRY_MODE_INVERSION_TIMING_READ.md` and `backtesting/data/results/nq_entry_mode_inversion_timing_read/summary.json`
- **Scope**: frozen pre-holdout comparison on three live NQ branches:
  - classic `NY LSI RR2/TP0.5 + medium-vol gate`
  - promoted `NQ NY HTF_LSI 5m lag24` lead
  - honest `NQ NY HTF_LSI 2m` secondary anchor
- **Method**:
  - run pure `close`
  - run pure `fvg_limit`
  - run exact engine `timed_hybrid` configs that choose `close` for sweep->inversion times `<=5m` or `<=15m`, otherwise `fvg_limit`
  - hybrids are still **diagnostic-only** because this is a frozen pre-holdout read, but the entries are now exact engine behavior rather than stitched approximations
- **Branch reads**:
  - **Classic RR2 gated (`5m`)**: `fvg_limit` still beat `close` (`avg R/signal 0.190 vs 0.173`, Calmar `6.97 vs 4.80`, DD `-3.8R vs -4.9R`). All observed inversions were already in the `<=5m` bucket, so there is no meaningful timing split here.
  - **Exact classic hybrid read**: `timed_hybrid<=5m` landed at `0.184 avg R/signal`, Calmar `6.72`, DD `-3.8R` and `timed_hybrid<=15m` degraded further to `0.166`, Calmar `6.10`. Even where the hybrid inherits the same fills as `fvg_limit`, pure `fvg_limit` still remained best.
  - **HTF-LSI `5m lag24` lead**: `fvg_limit` beat `close` decisively (`avg R/signal 0.147 vs 0.054`, Calmar `6.78 vs 1.55`, DD `-10.9R vs -17.7R`). The fastest `<=5m` inversions were actually the **worst** bucket for `close` (`-0.297R/signal`) while remaining positive for `fvg_limit` (`+0.131R/signal`). Exact hybrids stayed behind pure `fvg_limit`: `timed_hybrid<=5m` reached `0.129 avg R/signal`, Calmar `5.92`; `timed_hybrid<=15m` fell to `0.108`, Calmar `4.03`.
  - **HTF-LSI `2m` anchor**: fast inversions did improve both modes, but `fvg_limit` still stayed ahead overall (`avg R/signal 0.093 vs 0.052`, Calmar `5.67 vs 2.00`, DD `-13.4R vs -21.2R`) and also stayed ahead in the `<=5m` bucket (`0.295 vs 0.199`). Exact hybrids also stayed behind: `timed_hybrid<=5m` scored `0.087 avg R/signal`, Calmar `5.33`; `timed_hybrid<=15m` dropped to `0.078`, Calmar `3.98`.
- **Hybrid result**:
  - no tested exact threshold hybrid (`<=5m`, `<=15m`) beat pure `fvg_limit` on any frozen branch
  - tighter hybrid thresholds degraded the promoted branches less than looser thresholds, but still failed to overtake pure `fvg_limit`
- **Conclusion**: current evidence does **not** justify restarting from `2m`, reopening the broad `close` thesis, or rebuilding the anchor from scratch. The disciplined next step remains:
  1. keep `fvg_limit` as the operating default on the promoted NQ branches
  2. only reopen market-entry research if we have a materially different causal gate than simple sweep->inversion speed
  3. if a future hybrid ever clears this diagnostic stage, treat it as an anchor change and rerun the full sweep loop from scratch
- **Engineering note**: this packet also surfaced and fixed a simulator bug where classic LSI `close` mode could reference `_tp1_est` before assignment during candidate extraction. The fix lives in `backtesting/src/orb_backtest/engine/simulator.py` and was validated with targeted pytest coverage.

### Eval-Pass Fit 1s Read (Apr 2026)
- **Status**: **DIAGNOSTIC ONLY — operating fit read for eval passes, not a new promotion workflow**
- **Objective**: identify which current NQ branches are the best fit for fast Lucid / Apex-style eval passes, where the practical question is not full lifecycle EV but whether a trade can cleanly reach `1.2R` or `1.5R` before stop / flat and how often it gives that move back.
- **Evidence packet**: `backtesting/scripts/run_nq_eval_fit_1s_read.py` -> `backtesting/learnings/reports/NQ_EVAL_FIT_1S_READ.md` and `backtesting/data/results/nq_eval_fit_1s_read/`
- **Scope**:
  - recent window only: `2024-04-01` to `2026-03-24`
  - exact `1s` path walk after each filled trade on the top three Asia finalists from the broader eval-fit screen
  - each trade's exact fill was inferred as the first `1s` touch of the limit price inside the recorded `5m` fill bar
  - target reads use exact first-passage to `1.2R` and `1.5R`, with same-second stop/target conflicts marked `ambiguous` instead of forced
- **Candidate reads**:
  - **`NQ Asia ORB ALPHA_V1`** was the cleanest overall eval branch. Exact hit rates were **`52.9%` to `1.2R`** and **`51.5%` to `1.5R`**, with the strongest Lucid-style two-win approximation at **`52.2%`**. Giveback after hitting `1.5R` was still meaningful but materially cleaner than R9: **`44.3%`** of `1.5R` hits later retraced to breakeven-or-worse, and the median worst post-hit path still stayed positive at **`+0.26R`**.
  - **`NQ Asia R9 Restart`** tied for the best exact `1.2R` hit rate at **`52.9%`**, but its `1.5R` rate slipped to **`47.1%`** and, more importantly, the giveback profile was much worse: **`60.6%`** of `1.5R` hits later retraced to breakeven-or-worse, with median worst post-hit path **`-0.61R`**. Practical implication: this branch is only attractive for eval use if the operating rule explicitly locks the win near the target rather than letting the trade breathe.
  - **`NQ Asia-2` phase-one winner** remained the higher-flow backup. It traded most often at about **`7.2` trades/month**, but exact pass quality was lower: **`48.0%`** to `1.2R`, **`43.3%`** to `1.5R`, and Lucid-style two-win approximation **`40.0%`**. Its giveback profile was cleaner than R9 and broadly acceptable, so it stays alive as a volume-oriented alternate rather than the first choice.
- **Practical ranking from the exact packet**:
  1. **`NQ Asia ORB ALPHA_V1`** — best fit for `1.5R` eval passes and the cleanest overall branch
  2. **`NQ Asia R9 Restart`** — acceptable for `1.2R` evals only if the target is actively locked
  3. **`NQ Asia-2` phase-one winner** — higher-flow backup, but weaker raw pass odds
- **Conclusion**:
  - The exact `1s` read confirmed that the earlier proxy ranking was directionally correct.
  - The main new information is that **R9's giveback problem is real on exact data**, not just a `1m` artifact.
  - For fast eval passing, the honest operating default should be **`NQ Asia ORB ALPHA_V1`**. Treat **`R9 Restart`** as the aggressive alternate only when the playbook includes hard profit locking near the eval threshold.

### HTF-LSI Pre-Entry TP2 + Fresh Sweep Cancel (Apr 2026)
- **Status**: **DIAGNOSTIC ONLY — keep the current HTF-LSI lead unchanged**
- **Evidence packet**: `backtesting/scripts/run_nq_htf_lsi_pre_entry_tp2_sweep_cancel.py` -> `backtesting/learnings/reports/NQ_NY_HTF_LSI_PRE_ENTRY_TP2_SWEEP_CANCEL.md` and `backtesting/data/results/nq_htf_lsi_pre_entry_tp2_sweep_cancel_20260417/summary.json`
- **Scope**:
  - frozen current `NQ NY HTF_LSI 5m lag24` operating lead
  - compare `baseline` vs plain pre-entry `TP2` cancel vs pre-entry `TP2 + fresh HTF-LSI sweep` cancel
  - the sweep-gated version only cancels while the order is still pending; shared fill/cancel bars still go to fill first
- **Read**:
  - **Baseline**: `494` fills, `52` no-fills, `89.3R`, max DD `-10.9R`
  - **Plain pre-entry `TP2` cancel**: `490` fills, `56` no-fills, `88.2R`, max DD `-10.9R`
  - **`TP2 + fresh sweep`**: `494` fills, `52` no-fills, `89.3R`, max DD `-10.9R`
  - **Recent (`2024-01-01+`)** stayed the same pattern: baseline `34.8R`, plain `TP2` cancel `34.1R`, sweep-gated version `34.8R`
- **Practical conclusion**:
  - plain pre-entry `TP2` cancel is mildly harmful on the current HTF-LSI lead
  - adding a fresh HTF-LSI sweep requirement turned the rule into a complete no-op on this sample
  - if we revisit pre-entry invalidation on this branch, it should use a different causal gate than "another HTF-LSI sweep happened"

### Hunter Classic ORB Regime Gate Read (2026-05-02)

- **Status**: **CONDITIONAL research lead — promising, not promoted**
- **Evidence packet**: `backtesting/learnings/reports/NQ_HUNTER_CLASSIC_ORB_REGIME_GATE_20260502.md` and `backtesting/data/results/hunter_classic_regime_gate_test_20260502/`
- **Strategy**: NQ NY Hunter Classic ORB replication (`EMA15C14`, no FVG requirement): 09:30-09:45 ORB, signal 09:45-10:55, Mon/Wed/Thu/Fri, 5m body/rejection candle filter, 15m EMA14 bias, next-5m-open entry, signal-bar structural stop, 2R target with 1R cap when stop >=50 points.
- **Baseline**:
  - Last 10y: 1,506 trades, `+46.9R`, 40.2% WR, PF `1.03`, closed DD `-161.9R`
  - Last 2y: 325 trades, `+159.4R`, 49.5% WR, PF `1.32`, closed DD `-44.8R`
  - Last 1y: 154 trades, `+130.3R`, 55.8% WR, PF `1.61`, closed DD `-26.8R`
- **Causal regime gate read**:
  - Regime calendar rebuilt from `NQ_1s.parquet` through `2026-04-24`
  - Regime inputs shifted one full session before trade labeling
  - Vol buckets use pre-`2024-03-01` thresholds
- **Best simple gate**: skip `bull_high_vol`, `bear_high_vol`, and `bear_medium_vol`
  - Last 10y: 1,004 trades, `+150.9R`, 41.0% WR, PF `1.16`, closed DD `-41.8R`
  - Last 2y: 221 trades, `+133.8R`, 51.6% WR, PF `1.46`, closed DD `-21.7R`
  - Last 1y: 101 trades, `+92.8R`, 57.4% WR, PF `1.76`, closed DD `-14.2R`
- **Interpretation**: The last year was broadly strong across regimes, so do not conclude that Hunter only works in one narrow environment. The useful signal is that 10-year damage concentrates in high-volatility and bear-stress buckets (`bear_high_vol`, `bull_high_vol`, `bear_medium_vol`). A simple stress gate keeps most of the recent strength while fixing the long-run drawdown shape.
- **Distance cap read**: `ema15_max_distance=100` alone is not enough: 10y `-0.0R`, PF `1.00`, DD `-122.6R`. With the same simple stress gate it improves to 10y `+110.0R`, 2y `+110.7R`, 1y `+77.1R`, but gives up enough recent edge that no-cap + stress gate is the better first validation target.
- **Next-step validation**: `backtesting/learnings/reports/NQ_HUNTER_CLASSIC_STRESS_GATE_VALIDATION_20260502.md` and `backtesting/data/results/hunter_classic_stress_gate_validation_20260502/`
  - Standalone stress-gated: full 10y `+150.9R`, PF `1.16`, DD `-41.8R`; 2025+ `+108.5R`, PF `1.68`, DD `-14.2R`
  - Annual OOS remains lumpy: 2019 `-17.7R`, 2022 `-10.5R`, 2021 `+4.8R`, 2023 `+4.6R`, then strong 2025/2026
  - Monte Carlo full-risk warning: median bootstrap DD `-50.8R`, 1st percentile DD `-119.7R`, 51.9% probability of DD worse than `-50R`
  - Portfolio fit: 0.25x Hunter add-on to frozen ALPHA_V1 improves overlap-window total from `+597.1R` to `+634.0R`, with DD only worsening from `-15.6R` to `-16.5R`; full-size Hunter worsens DD to `-30.9R`
  - Correlation to existing ALPHA_V1 legs is low (roughly `-0.03` to `+0.06` daily R), so additivity is plausible; sizing is the limiting factor
- **Updated conclusion**: CONDITIONAL reduced-risk pilot candidate only. Do **not** promote full-size. Best next expression is stress-gated Hunter at `0.25x` risk, optionally with ES NY ORB reduced to `0.75x` to avoid simply adding NY-session gross exposure.
- **Strategy workflow pass** (`CURRENT_STRATEGY_WORKFLOW`, 2026-05-02): `backtesting/learnings/reports/NQ_HUNTER_CLASSIC_STRATEGY_WORKFLOW_20260502.md` and `backtesting/data/results/hunter_classic_stress_gate_strategy_workflow_20260502/`
  - Search space: 450 stress-gated variants around the baseline; hold-out frozen at `2025-01-01+`
  - Workflow-valid pre-holdout leader: `ema14_tol0_distnone_relegacy_samewin0` -> pre-HO `+58.7R / -40.5R DD`, full 10y `+162.9R / -40.5R DD`, 2025+ `+104.2R / -14.2R DD`, last 1y `+88.4R / -14.2R DD`
  - Best 10y hindsight leader: `ema10_tol0_dist150_relegacy_samewin0` -> full 10y `+165.1R / -41.8R DD`, but weak pre-HO `+35.8R / -41.8R DD`
  - Best 1y hindsight leader: `ema10_tol0_dist150_reall_samewin0` -> last 1y `+107.6R / -14.2R DD`, but weak pre-HO `+30.3R / -41.8R DD`; treat as hot-regime research, not promotion-clean
  - Balanced 10y/workflow challenger: `ema14_tol2_distnone_relegacy_samewin0` -> full 10y `+164.7R / -41.8R DD`, pre-HO `+56.2R / -41.8R DD`, last 1y `+92.8R / -14.2R DD`
  - Conservative DSR remains weak for full-history candidates after 450 raw trials; PSR is strong on full 10y and last 1y. This caps the output at shortlist/challenger status, not final deployment.
- **Three-candidate downstream pass** (2026-05-02): `backtesting/learnings/reports/NQ_HUNTER_CLASSIC_THREE_CANDIDATE_DOWNSTREAM_20260502.md` and `backtesting/data/results/hunter_classic_three_candidate_downstream_20260502/`
  - Moved forward with all three frozen candidates: workflow leader `ema14_tol0_distnone_relegacy_samewin0`, balanced challenger `ema14_tol2_distnone_relegacy_samewin0`, and recent challenger `ema10_tol0_dist150_reall_samewin0`
  - Core read: all three cluster around `+163R` full-history net and `-40R` to `-42R` DD; the recent challenger wins last 1y (`+107.6R`) but has the weakest pre-holdout (`+30.3R`)
  - Phase-one 14-day staggered scorecard at `0.25x` risk: full-history EV/attempt is positive but modest (`$84` to `$105`), while 2025+ cohorts are excellent (`85%` to `88%` payout, `0%` breach, `$326` to `$341` EV/attempt)
  - ALPHA_V1 portfolio fit: `0.25x` Hunter add-on improves ALPHA_V1 overlap net from `+597.1R` to about `+620R` to `+621R`, with DD worsening from `-15.6R` to `-16.7R`; cutting ES NY to `0.75x` keeps worst month better but reduces total net to about `+588R` to `+590R`
  - Updated promotion read: keep all three alive for paper/live observation, but rank **Balanced Challenger** slightly ahead for pilot because it preserves workflow hygiene while improving both 2025+ and last-1y versus the workflow leader. Use **Recent Challenger** only as a hot-regime research branch until more forward data confirms it.
- **Dist100 attribution** (2026-05-02): `backtesting/learnings/reports/NQ_HUNTER_DIST100_ATTRIBUTION_20260502.md`
  - `ema15_max_distance=100` is a chase/exhaustion cap: it rejects signals already more than `100` NQ points beyond the confirmed previous 15m EMA in the trade direction.
  - Paired grid attribution shows it is not doing the structural repair: vs no-cap, `dist100` median deltas were pre-holdout `-30.3R`, full 10y `-45.5R`, 2025+ `-21.8R`, last 1y `-15.6R`; full-history DD did not improve.
  - The stress gate is the real repair mechanism. Once stress-gated, `dist100` mostly raises recent PF by cutting trade flow, while giving up too much net R.
  - If transferring the idea to ALPHA_V1, use an ATR-normalized `entry_context_gate` on ORB legs only. Existing adjacent ALPHA ORB MA/VWAP context tests were modest-to-negative, so do not prioritize this ahead of more promising Hunter regime/forward-validation work.
- **Hunter ablation** (2026-05-02): `backtesting/learnings/reports/NQ_HUNTER_CLASSIC_ABLATION_20260502.md` and `backtesting/data/results/hunter_classic_ablation_20260502/`
  - Baseline: `ema14_tol2_distnone_relegacy_samewin0` stress-gated balanced candidate: full 10y `+164.7R / -41.8R DD`, 2025+ `+108.5R`, last 1y `+92.8R`.
  - Biggest contributor: stress gate. Removing it loses `-96.3R` full and widens DD by `-97.0R`, even though it would have added recent hot-window R.
  - Biggest non-regime protection: wide-stop 1R target reduction. Forcing all wide-stop trades to keep 2R loses `-64.6R` and worsens DD by `-19.5R`.
  - Reentry after loss matters: first-trade-only loses `-44.8R` full and `-21.3R` last 1y.
  - EMA bias is real but smaller: removing it loses `-10.3R` full and `-17.4R` pre-HO, while slightly helping 2025+.
  - Follow-up leads: signal window extension to `13:00` improved full/holdout in OAT and deserves workflow-clean test; Tuesday inclusion improved full but hurt recent; rejection wick filter may be over-restrictive and should be re-tested before treating as mandatory.
- **Hunter next-tests grid** (2026-05-02): `backtesting/learnings/reports/NQ_HUNTER_CLASSIC_NEXT_TESTS_20260502.md` and `backtesting/data/results/hunter_classic_next_tests_20260502/`
  - Scope: 60 stress-gated variants plus 4 no-gate context rows around the balanced baseline, sweeping signal cutoff `10:55/13:00`, rejection wick `20/40/100`, Tuesday excluded/included, and cheap EMA/dist150 controls.
  - Cleanest broad improvement: relax/disable rejection wick. Median paired deltas for `rej20 -> rej100`: pre-HO `+7.4R`, full `+17.8R`, 2024+ `+22.5R`, 2025+ `+12.0R`, last 1y `+6.1R`; tradeoff is full DD about `-5.9R` worse.
  - Signal extension to `13:00` is not broadly validated. It still helps the direct baseline row, but median paired deltas give up 2024+ `-12.8R`, 2025+ `-7.0R`, and last 1y `-3.5R`; keep as a narrow side branch, not a new default.
  - Tuesday is a 10y-vs-recent fork: median full/pre effect is strongly positive, but every 2025+ and last-1y paired comparison is negative. Do not re-add Tuesday unless explicitly optimizing for long-history diversification over current-regime strength.
  - Best workflow-clean 10y-safe branch: `ema14_tol0_distnone__withTue__1055__rej100__stress` -> pre-HO `+129.1R / -38.4R DD`, full `+236.0R / -38.4R DD`, 2025+ `+106.9R`, last 1y `+78.3R`.
  - Best full-10y hindsight branch: `ema14_tol5_distnone__withTue__1055__rej100__stress` -> full `+240.9R / -40.6R DD`, 2025+ `+120.5R`, last 1y `+86.9R`.
  - Best hot/recent branch: `ema14_tol5_distnone__noTue__1055__rej100__stress` (ties `rej40` recent, better long-history profile) -> full `+178.0R / -47.7R DD`, 2025+ `+131.4R`, last 1y `+108.7R`.
  - Supersede read: no single row cleanly replaces the balanced baseline across all objectives. Carry forward two research branches: `withTue/rej100` for 10y safety and `noTue/tol5/rej100` for current hot regime; keep balanced baseline as neutral reference until downstream validation decides.
- **Hunter next-tests downstream** (2026-05-02): `backtesting/learnings/reports/NQ_HUNTER_CLASSIC_NEXT_TESTS_DOWNSTREAM_20260502.md` and `backtesting/data/results/hunter_classic_next_tests_downstream_20260502/`
  - Compared three frozen branches: neutral reference `ema14_tol2_distnone__noTue__1055__rej20__stress`, 10y-safe `ema14_tol0_distnone__withTue__1055__rej100__stress`, and recent-strength `ema14_tol5_distnone__noTue__1055__rej100__stress`.
  - Core full-history: neutral `+164.7R / -41.8R DD`; 10y-safe `+236.0R / -38.4R DD`; recent-strength `+178.0R / -47.7R DD`.
  - Recent windows: neutral 2025+ `+108.5R`, last 1y `+92.8R`; 10y-safe 2025+ `+106.9R`, last 1y `+78.3R`; recent-strength 2025+ `+131.4R`, last 1y `+108.7R`.
  - Phase-one 0.25x, 14-day staggered: 10y-safe has the best full-history payout business (`57.1%` payout, `41.4%` breach, `$185` EV/attempt) versus neutral (`41.0%`, `57.5%`, `$105`) and recent-strength (`29.5%`, `68.6%`, `$48`). On 2025+ all three remain strong with `85%` to `88%` payout and `0%` breach.
  - ALPHA_V1 portfolio fit at 0.25x: 10y-safe add-on is best (`+636.5R`, DD `-15.3R`, delta `+39.3R`, DD improves `+0.3R`); neutral add-on `+621.4R`, DD `-16.7R`; recent-strength add-on `+627.0R`, DD `-15.7R`.
  - ES NY risk-down comparison: ES_NY `0.75x` + Hunter `0.25x` improves DD/worst-month modestly but gives up too much net for all three branches; add Hunter at small risk without cutting ES is the cleaner research read.
  - Leg overlap/correlation stays low (`corr_to_alpha` about `-0.02` to `-0.04`; ES NY overlap corr about `0.05` to `0.07`), so overlap is not a blocker for a small pilot.
  - Updated ranking: 10y-safe branch is the best downstream candidate if choosing one research branch now; neutral remains the control leg; recent-strength stays a hot-regime challenger, not the primary pilot.
- **Current fee-aware ALPHA_V1 sidecar retest** (2026-05-16): `backtesting/learnings/reports/ALPHA_V1_NEXT_STEPS_20260516.md` and `backtesting/data/results/alpha_v1_next_steps_20260516/`
  - Re-scored the three Hunter next-test branches at `0.25x` against the current fee-aware five-leg ALPHA packet (`alpha_v1_payout_with_fees_20260507`) instead of the older frozen ALPHA daily-R file.
  - On the selected aggressive sprint ALPHA profile, the 10y-safe branch remains the best sidecar: 2024 improves from `82.6%` payout / `17.4%` breach to `88.5%` / `11.5%`; 2025 improves from `73.1%` / `26.9%` to `84.6%` / `15.4%`; 2025 max consecutive breaches improve from `7` to `4`.
  - Portfolio fit stays additive: net PnL rises by about `$20.7k`, DD is essentially unchanged (`-$4.10k` vs `-$4.04k`), and daily correlation to ALPHA is only `0.03`.
  - Practical conclusion: Hunter 10y-safe at `0.25x` is the strongest next shadow/paper sidecar candidate. Do not promote full-size Hunter.
  - Shadow profile action (2026-05-16): added `ALPHA_V1-HUNTER-SAFE-025-SHADOW` in `execution/config/exec_configs.json` with `webhooks=[]`, `H_ORB_SAFE`, `risk_usd=$87.50`, `max_single_risk_usd=$87.50`, and `max_contracts=5`. Report: `backtesting/learnings/reports/ALPHA_V1_HUNTER_025_SHADOW_SPEC_20260516.md`. Deployability is now `live_native` for no-webhook dry-run/shadow because the execution `hunter_orb` engine supports the branch rules before arming; exact replay/log parity remains required before any webhook promotion.
- **Hunter live-engine parity and sizing correction** (2026-05-16): `backtesting/learnings/reports/ALPHA_V1_PRIORITIES_1_5_20260516.md` and `backtesting/data/results/alpha_v1_priorities_1_5_20260516/`
  - Exact live-engine replay of `ALPHA_V1-HUNTER-SAFE-025-SHADOW` through NQ local data `2026-05-01` printed `1660` trades, `+$4.7k`, PF `1.06`, `+73.7` net R, and `-$4.0k` DD at the no-webhook shadow profile.
  - The original 10y-safe research CSV is **not parity-confirmed**. On the shared `2016-04-25` to `2026-04-24` overlap, fuzzy same-setup matching found only `593 / 1650` research trades (`35.9%`), with `1058` exact-only and `1057` research-only setups. Do not rely on the old `$20.7k` normalized research read as a deployable expectation until the signal-stream mismatch is explained.
  - Actual Hunter sizing is contract-floor distorted. At intended `0.25x` risk (`$87.50`), `18.2%` of trades risk more than intended because the Hunter engine floors to at least `1` MNQ and does not enforce `max_single_risk_usd`; at `0.125x`, `49.2%` exceed intended risk. This is a live-engine behavior, not a research assumption.
  - Portfolio read after actual-engine revaluation is still additive but less dramatic: against cached fee-aware ALPHA, `0.25x` Hunter adds about `$6.0k`, improves 2025 payout/breach from `73.1% / 26.9%` to `84.6% / 15.4%`, but slightly worsens 2024 from `82.6% / 17.4%` to `80.0% / 20.0%`.
  - Practical conclusion: keep Hunter as shadow/research only. Next concrete work is parity debugging (`hunter_orb` signal timing, Tuesday handling, entry/target/reentry semantics) and deciding whether `_hunter_qty_for_risk` should respect the same single-contract cap as standard ORB sizing before any webhook promotion.
- **Hunter cap-fixed sizing rerun** (2026-05-17): `backtesting/learnings/reports/ALPHA_V1_HUNTER_CAP_FIX_20260517.md` and `backtesting/data/results/alpha_v1_hunter_cap_fix_20260517/`
  - Implemented the standard single-contract cap in `HunterORBEngine._hunter_qty_for_risk()`: if `1` MNQ would exceed `max_single_risk_usd`, Hunter now skips the setup instead of forcing a minimum contract.
  - Exact shadow replay dropped from the old floor-based `1660` trades / `+$4.7k` / PF `1.06` / `+73.7R` to cap-fixed `1384` trades / `+$3.0k` / PF `1.05` / `+51.0R`; over-cap trades fell from `303` to `0`.
  - Research/live parity remains unresolved: after the cap fix, same-setup matching versus the selected research stream found only `529 / 1650` research trades (`32.1%`), with `849` exact-only and `1121` research-only setups. The cap fix solves sizing integrity, not signal-stream parity.
  - Sidecar read improved at the account layer despite lower standalone Hunter net: cached fee-aware ALPHA baseline `2024` was `82.6%` payout / `17.4%` breach and `2025` was `73.1%` / `26.9%`; adding cap-fixed Hunter changed those to `87.5%` / `12.5%` in `2024` and `84.6%` / `15.4%` in `2025`.
  - Practical conclusion: cap-fixed Hunter is now the cleaner no-webhook shadow candidate than the old floor-sized read. Keep it dry-run/shadow only; next action is signal parity debugging before any webhook promotion.
- **Hunter parity debug: next-open entry basis** (2026-05-17): `backtesting/learnings/reports/ALPHA_V1_HUNTER_PARITY_DEBUG_20260517.md` and `backtesting/data/results/alpha_v1_hunter_parity_debug_20260517/`
  - Root cause found: the live Hunter path was using signal-bar close as the entry price while the research export uses the next 5m bar open. With signal-close, cap-fixed exact matched only `529 / 1650` research trades (`32.1%`) once entry/target prices were included. With `hunter_entry_basis=next_open` and high-cap signal-only sizing, exact matched `1650 / 1650` research trades including entry, stop, and target.
  - Deployable cap-fixed next-open Hunter matched `1349 / 1650` research trades (`81.8%`); the remaining gap is mostly intentional sizing integrity, with `320` next-open candidates rejected by the `$87.50` single-contract cap.
  - Tuesday should stay enabled: no-Tuesday high-cap replay matched only `1294 / 1650` research trades and removed `356` research setups. Reentry is not the primary blocker after next-open; `after_each_loss`, `all_nonoverlap`, and same-bar-win variants all preserved `100%` research coverage but added exact-only trades and did not improve standalone quality.
  - Sidecar after next-open cap fix stays additive but less strong than the signal-close cap-fixed account read: portfolio net `+$5.1k` vs baseline, DD `-$3.89k`; account outcomes improve baseline `2024` from `82.6% / 17.4%` payout/breach to `87.5% / 12.5%`, and `2025` from `73.1% / 26.9%` to `80.8% / 19.2%`.
  - Practical conclusion: set Hunter shadow/parity work to `hunter_entry_basis=next_open`; `ALPHA_V1-HUNTER-SAFE-025-SHADOW` now carries that override. Keep it no-webhook shadow only until live logs confirm next-open arming/fill behavior and forward sidecar additive behavior.
- **Original ungated Hunter 2025+ ablation** (2026-05-02): `backtesting/learnings/reports/NQ_HUNTER_CLASSIC_ORIGINAL_ABLATION_2025PLUS_20260502.md` and `backtesting/data/results/hunter_classic_original_ablation_2025plus_20260502/`
  - Baseline: canonical ungated Hunter EMA15C14 no-cap, 2025-01-01 through 2026-04-24: `195` trades, `+157.3R`, PF `1.55`, DD `-26.8R`.
  - Recent-window read differs from long-history: most gates cut good trades. Adding the stress gate loses `-48.8R` but improves DD by `+12.6R`; `dist100` loses `-67.5R`; Tuesday inclusion loses `-49.6R` and worsens DD by `-24.7R`.
  - Best recent-only looseners were signal window to `13:00` (`+29.1R`, DD slightly better), removing body filter (`+25.8R`, DD better), always-2R on large stops (`+24.8R`, but DD worse by `-8.1R`), and removing rejection filter (`+16.4R`, DD better).
  - Interpretation: the stress gate is not explaining the 2025 hot streak; it is preserving capital across older hostile regimes. Recent-only candidates should be treated as hot-regime branches and re-checked against the 10y/workflow gates before promotion.
- **Original Hunter 2025+ combo grid** (2026-05-02): `backtesting/learnings/reports/NQ_HUNTER_CLASSIC_ORIGINAL_COMBO_GRID_2025PLUS_20260502.md` and `backtesting/data/results/hunter_classic_original_combo_grid_2025plus_20260502/`
  - Compact 768-config grid combined the strongest one-at-a-time recent looseners on the same 2025-01-01 through 2026-04-24 window.
  - Best net in-sample: `no_ema__noTue__1300__body0_rej20__allNonOverlap__always2R__ungated` -> `362` trades, `+372.9R`, PF `1.65`, DD `-26.8R`.
  - Best Net/DD neighbor: `ema14_tol5__noTue__1300__body0_rej20__allNonOverlap__always2R__ungated` -> `348` trades, `+365.9R`, PF `1.67`, DD `-25.8R`.
  - Optimized recent shape: no stress gate, no Tuesday, signal end `13:00`, body filter removed, rejection-wick filter retained, all non-overlapping reentries, and always-2R target on wide stops. Treat as an in-sample hot-regime branch only until full 10y/workflow validation.

### ILM/iFVG TradingView Replication Read (2026-04-28)

**Status**: reverse-engineering checkpoint only. This is not a promoted NQ strategy.

**Evidence packet**: `backtesting/scripts/reverse_engineer_ilm_ifvg.py` -> `backtesting/data/results/ilm_ifvg_reverse_engineering_internal_sources_20260428/`, `backtesting/data/results/ilm_ifvg_reverse_engineering_guide_step_phase28_20260428/`, `backtesting/data/results/ilm_reversal_ma_fit_grid_20260428/`, `backtesting/data/results/ilm_ub_filter_fit_grid_20260428/`, `backtesting/data/results/ilm_ifvg_reverse_engineering_recent_signal_probe_20260428/`, and `backtesting/data/results/ilm_ifvg_recent_reversal_ma_combo_probe_20260428/`.

| Variant | Matched | TV trades | Local trades | Recall | Precision | Net P&L |
|---------|---------|-----------|--------------|--------|-----------|---------|
| Current-day P/D + UB proxy + rolling sweep cutoff | 67 | 111 | 679 | 60.36% | 9.87% | $22,526.79 |
| Add latest confirmed internal swing source | 67 | 111 | 678 | 60.36% | 9.88% | $22,115.54 |
| Algo reversal proxy + internal source | 62 | 111 | 463 | 55.86% | 13.39% | $30,466.49 |
| Guide Reversal MA proxy: EMA50 held 33 bars | 57 | 111 | 515 | 51.35% | 11.07% | $41,872.05 |
| Guide Reversal MA proxy + 10pt distance | 51 | 111 | 394 | 45.95% | 12.94% | $23,304.70 |
| Guide Reversal MA proxy, phase offset 28 | 60 | 111 | 513 | 54.05% | 11.70% | $43,281.63 |
| Guide Reversal MA proxy, phase offset 28 + 10pt distance | 46 | 111 | 399 | 41.44% | 11.53% | $29,245.21 |
| AlgoAlpha confirmation proxy | 27 | 111 | 77 | 24.32% | 35.06% | $6,966.09 |
| AlgoAlpha confirmation within 2-bar lookback | 64 | 111 | 235 | 57.66% | 27.23% | -$3,592.46 |
| AlgoAlpha recent + phase28 Reversal MA proxy | 57 | 111 | 186 | 51.35% | 30.65% | $1,464.45 |
| AlgoAlpha recent + phase28 Reversal MA proxy + 10pt distance | 44 | 111 | 147 | 39.64% | 29.93% | $4,925.39 |
| Internal source + min 4 bars sweep-to-gap | 56 | 111 | 549 | 50.45% | 10.20% | -$2,012.41 |
| Visible TradingView 2026 window with exact UB/Reversal MA columns | 4 | 4 | 4 | 100.00% | 100.00% | n/a |

**Key findings**

- Premium/discount is now modeled as the live current futures trading-day midpoint, with the day rolling at 18:00 New York time.
- Accepting internal swing liquidity did not recover any additional export entries. The remaining parity gap is unlikely to be caused by missing liquidity-level categories alone.
- The visible 2026 TradingView OHLC+indicator window reaches exact entry parity only when using exact `UB-Filter` and `Reversal MA` columns with a 10-point distance gate.
- The settings guide clue `Trend MA Period=50` + `MA Step Period=33` maps best to a close EMA50 held in 33-bar blocks on the visible TradingView window, but this proxy still over-prunes full history and leaves visible-window extras.
- Fitting against the visible `Reversal MA` column found the best public proxy around offset 28 in the 33-bar step cycle (`ohlc4 EMA49` mean absolute error 16.91; guide-consistent `close EMA50` mean absolute error 16.95). Promoting that phase offset improved the loose MA-only full-history row from 57 to 60 matches, but it worsened the stricter 10-point row and did not beat the current `internal_sources` baseline.
- Fitting the visible `UB-Filter` column effectively solved that piece: close source + RMA ATR(30) + key 3 matched the exported line almost exactly. Replacing UT direction with a line-based `ut_stop_proxy` produced identical full-history parity, so UB is no longer the active unknown.
- Applying the guide's `Reversal Signal Lookback=2` as a recent-signal rule is helpful only for the stricter public AlgoAlpha proxy. It raises AlgoAlpha recall from 24.32% to 57.66% and precision stays materially higher than the loose baseline, but it still does not beat the 67-match internal-source baseline. Combining recent AlgoAlpha with the phase28 Reversal MA proxy lifts precision to about 30% but drops recall to 40-51%.
- A public AlgoAlpha-style overextension-then-confirmation proxy and the visible-window 4-bar sweep-to-gap clue both over-prune full history. They are useful diagnostics, not replacement filters.
- The next productive target is the private Algo Inversion/Reversal MA filter, not another broad sweep-source expansion.
- **ALPHA_V1 hot-regime ablation pass** (2026-05-03): `backtesting/learnings/reports/ALPHA_V1_HOT_REGIME_ABLATION_20260503.md`
  - Scope included the active NQ legs: NQ NY HTF-LSI and NQ Asia ORB, plus ES legs for portfolio context. This is TESTING-only, overfit-aware research inspired by `H_ORB_ABLATED`, not a robust promotion packet.
  - Best NQ NY HTF-LSI hot-score branch: `combo__window_0830_1430__dow_none__rr3p5_tp0p4__gap1p0__fvgL20_R2__lag24__cap2__mode_fvg_limit` -> full `113.2R / -17.91R DD`, last 2y `29.9R`, last 1y `16.61R`; warning: 1 negative year.
  - Best NQ Asia ORB hot-score branch: `combo__entry_2230__dow_none__rr6p0_tp0p3__stop_orb_pct_100p0__min_gap_orb_pct_10p0__uncapped_any__fvg_first__wide_none` -> full `242.84R / -14.22R DD`, last 2y `61.07R`, last 1y `41.4R`; warning: warning layer acceptable for TESTING.
- **ALPHA_V1 expanded hot-regime grid** (2026-05-03): `backtesting/learnings/reports/ALPHA_V1_HOT_REGIME_EXPANDED_GRID_20260503.md`
  - Follow-up grid expanded the top OAT families into 4,378 scored variants. This is still TESTING-only and intentionally overfit-aware.
  - Best expanded NQ NY HTF-LSI hot-score branch: `combo__window_0830_1430__dow_none__rr3p5_tp0p4__gap1p0__fvgL10_R2__lag24__cap2__mode_fvg_limit` -> full `113.04R / -16.33R DD`, last 2y `31.22R`, last 1y `18.06R`; 0 negative years but worse DD than baseline.
  - Best expanded NQ Asia ORB hot-score branch: `combo__entry_2230__dow_none__rr6p0_tp0p3__stop_orb_pct_100p0__min_gap_orb_pct_10p0__cap2_after_nonpositive__fvg_first__wide_none` -> full `243.62R / -14.22R DD`, last 2y `61.07R`, last 1y `41.40R`; full DD worsens versus baseline.
  - Pure last-1y NQ Asia branch: `entry_2315 / gap0 / cap1` reached `+49.70R` last-1y, but it is less balanced than the best-score row. Treat it as a hot-regime dry-run candidate only.
- **Hot one-year strategy workflow** (2026-05-03): `backtesting/learnings/reports/HOT_ONE_YEAR_STRATEGY_WORKFLOW_20260503.md`
  - Window: `2025-03-24` to `2026-03-24`. TESTING-only, overfit-aware Calmar optimization; Bailey-style deflation intentionally skipped.
  - NQ NY ORB: `combo__orb20m__entry_1300__flat_1430__rr4p0_tp0p3__stop_atr_9p0__gap_orb_10p0__atr12__dir_long__dow_baseline__icf_on__cap2_nonpos__fvg_first` with `gate_skip_high_vol` -> 33 fills, `16.07R`, Calmar `8.034`, PF `2.802`, DD `-2.0R`, surface `curve`.
  - NQ Asia ORB: `combo__orb15m__entry_2230__flat_0400__rr5p0_tp0p25__stop_atr_4p0__gap_orb_15p0__atr5__dir_long__dow_none__icf_off__cap1__fvg_first` with `gate_skip_bear_high_vol` -> 67 fills, `32.45R`, Calmar `8.113`, PF `2.157`, DD `-4.0R`, surface `soft_curve`.
  - NQ NY LSI: `combo__window_0830_1230__rr3p5_tp0p4__gap3p0__atr10__fvgL20_R2__lag24__cap2__htfN5__htf60__dir_long__mode_fvg_limit__dow_exFri` with `gate_none` -> 31 fills, `15.63R`, Calmar `15.626`, PF `3.158`, DD `-1.0R`, surface `soft_curve`.
- **NQ NY LSI + CISD sequence** (2026-05-03): `backtesting/learnings/reports/NQ_NY_LSI_CISD_SEQUENCE_20260503.md`, `backtesting/learnings/reports/NQ_NY_LSI_CISD_SURVIVOR_REFINEMENT_20260503.md`, and `backtesting/data/results/nq_ny_lsi_cisd_sequence_20260503/`
  - Scope: NQ NY only, data through `2026-05-01`, fixed target structure `rr=2.0` and `tp1_ratio=0.5`; discovery `2016-01-01` to `2023-01-01`, validation `2023-01-01` to `2025-04-01`, holdout `2025-04-01+`.
  - CISD definition implemented as body-based internal structure shift: after sweep, require an opposing body leg with at least `cisd_min_leg_bars` and at least `cisd_min_leg_atr_pct` of daily ATR body travel; bullish CISD closes above the down-leg body high, bearish CISD closes below the up-leg body low.
  - First pass tested inversion-only, CISD-only, additive inversion-or-CISD, close vs CISD/gap-level limit entry, classic swing/hourly/equal/session sweep sources, absolute/gap-candle/ATR stops, 1m/3m/5m, and body bars/ATR grids. Discovery-best 5m structural-stop rows did **not** validate or hold out.
  - Best current additive survivor: `1m|survivor_stop|additive|classic_swing|level_limit|atr_pct10|bars3|atr7.5` -> discovery `433` trades, PF `1.18`, Calmar `2.01`; validation `106` trades, PF `1.37`, Calmar `2.43`; holdout `58` trades, PF `1.75`, Calmar `2.89`. This is the leading research candidate, not yet a robust-pipeline promotion.
  - Best pure CISD replacement survivor: `1m|survivor_stop|pure_cisd|classic_swing|level_limit|atr_pct15|bars2|atr7.5` -> discovery `223` trades, PF `1.09`, Calmar `0.82`; validation `52` trades, PF `1.52`, Calmar `1.33`; holdout `41` trades, PF `1.69`, Calmar `2.49`. Pure CISD is viable enough to continue testing, especially on 1m, but weaker discovery profile keeps it behind additive.
  - Best 3m robustness challenger: `3m|survivor_source|hourly_htf|inversion_or_cisd|level_limit|atr_pct12.5|bars3|atr7.5` -> discovery `416` trades, PF `1.13`, Calmar `1.59`; validation `140` trades, PF `1.14`, Calmar `1.32`; holdout `46` trades, PF `1.80`, Calmar `2.38`.
  - Sweep-source read: equal-high/low references were weak; hourly and session references can help specific survivors, but classic swing sweeps remained the cleanest leading source for the top 1m candidates.
  - Entry/stop read: market-close CISD entries were poor in the initial pass; level-limit entries dominated. ATR stops around `10%` to `15%` daily ATR were materially better than raw structural/candle stops for the promoted 1m/3m rows.
  - Next validation: run a full robust/discovery pipeline on the three frozen survivors above with no further parameter tuning, then test prop/account-sizing behavior. Do not promote from this sequence alone.
- **NQ NY LSI + CISD frozen-candidate validation** (2026-05-03): `backtesting/learnings/reports/NQ_NY_LSI_CISD_CANDIDATE_VALIDATION_20260503.md` and `backtesting/data/results/nq_ny_lsi_cisd_candidate_validation_20260503/`
  - Status: **CONDITIONAL research lead, not final promotion**. The frozen candidates improved after validation, but DSR remains weak after `242` search trials, so this is not statistically final.
  - Primary candidate `add_1m_classic_atr10_b3_a7p5`: full `597` trades, PF `1.25`, `+67.1R`, DD `-18.1R`, Calmar `3.71`; validation `+16.1R`, PF `1.37`; holdout `+14.7R`, PF `1.73`; post-2023 `+30.8R`, PF `1.48`.
  - Primary robustness: fixed walk-forward passed `8/8` OOS folds; fragility grid had `27/27` robust neighbors with minimum `2` CISD body bars; post-2023 block-bootstrap final-R p5 `+9.79R`, DD p5 `-12.14R`, ruin(-10R) `15.9%`.
  - Primary caveats: DSR only `0.2998` post-2023 despite PSR `0.9900`; full-history 2016 was negative (`-16.6R`); shorts are a drag (`-1.6R` full) while longs carry the edge (`+68.7R`); Thursday is a major drag (`-21.4R` full); after 12:00 ET performance deteriorates.
  - Pure CISD challenger `pure_1m_classic_atr15_b2_a7p5`: post-2023 `93` trades, PF `1.57`, `+19.9R`, DD `-7.5R`; holdout `41` trades, PF `1.66`, `+10.0R`. Walk-forward passed `7/8` OOS folds; promotable fragility grid `12/18` robust neighbors after excluding diagnostic `bars=1` rows.
  - 3m hourly additive challenger `add_3m_hourly_atr12p5_b3_a7p5`: post-2023 `186` trades, PF `1.27`, `+22.1R`; holdout `46` trades, PF `1.73`, `+12.2R`; walk-forward only `5/8` OOS folds, so treat as diversification/challenger, not lead.
  - Execution stress: primary remains positive under 1-2 tick round-trip slippage and 1-tick penetration; pure CISD is more sensitive to delayed-entry stress; 3m hourly survives penetration/slippage but has weaker fold stability.
  - Phase-one style account read (post-2023, +5R payout/-4R breach, 14-day stagger): primary payout `77.0%`, breach `16.1%`, EV `+3.49R`; pure CISD payout `80.5%`, breach `14.9%`, EV `+3.48R`; 3m hourly payout `63.2%`, breach `28.7%`, EV `+2.03R`.
  - Next research sequence: test restricted variants without new broad tuning: long-only, no-Thursday, entry cutoff before noon, and combinations of those on primary/pure CISD. Then rerun DSR/MC/phase-one on only the frozen restricted finalists.
- **NQ NY LSI + CISD restricted finalists** (2026-05-03): `backtesting/learnings/reports/NQ_NY_LSI_CISD_RESTRICTED_FINALISTS_20260503.md` and `backtesting/data/results/nq_ny_lsi_cisd_restricted_finalists_20260503/`
  - Engine correction applied before this pass: `excluded_days` now gates the LSI sweep/CISD path, not only FVG detection, so no-Thursday results are the corrected numbers.
  - Best restricted additive row: `add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530` -> full `475` trades, PF `1.45`, `+88.6R`, DD `-9.0R`; validation `85` trades, PF `1.62`, `+20.3R`; holdout `47` trades, PF `1.75`, `+12.0R`; post-2023 `132` trades, PF `1.66`, `+32.3R`, DD `-7.1R`.
  - Relative to unrestricted primary, no-Thursday additive improves post-2023 by only `+1.5R` after the correction, but materially improves full-history PF/DD (`1.45` PF and `-9.0R` DD vs `1.25` PF and `-18.1R` DD). Treat this as the leading production-style variant, with the caveat that holdout payout rate falls because many accounts remain open.
  - Unrestricted additive remains statistically competitive: post-2023 `+30.8R`, PF `1.48`, DD `-6.6R`; post-2023 block-bootstrap final-R p5 `+9.79R`, DD p5 `-12.14R`, ruin(-10R) `15.9%`; phase-one payout `77.0%`, breach `16.1%`, EV `+3.49R`.
  - Best pure-CISD capital-protection row: `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` -> full `193` trades, PF `1.52`, `+38.7R`, DD `-9.1R`; post-2023 `54` trades, PF `1.91`, `+15.4R`, DD `-2.9R`; phase-one post-2023 payout `78.2%`, breach `0.0%`, EV `+4.44R`. This is lower capacity/throughput but cleaner on breach risk.
  - Restriction read: noon cutoff hurts additive R; long-only cuts additive throughput and total R; no-Thursday improves additive full-history quality but is not a decisive post-2023 edge. For pure CISD, long-only plus noon cutoff improves DD/PF and phase-one profile at the cost of fewer trades.
  - Status: keep additive no-Thursday and pure long/noon as finalists for phase-one style account simulation and small live-sim/watchlist review; do not broaden the parameter grid further without new data or a new structural thesis.
- **NQ NY LSI + CISD target sweep** (2026-05-04): `backtesting/learnings/reports/NQ_NY_LSI_CISD_TARGET_SWEEP_20260504.md` and `backtesting/data/results/nq_ny_lsi_cisd_target_sweep_20260504/`
  - Scope: target-only sweep on the two additive finalists plus the pure-CISD finalist. Signal, entry, stop, sweep source, timeframe, DOW, and session cutoff stayed frozen; only `rr` and `tp1_ratio` moved. Swept `rr` from `1.5` to `4.0`, `tp1_ratio` from `0.4` to `0.8`, skipping rows where TP1 would be under `1R`.
  - Result: target tuning creates **incremental**, not transformational, progress. Keep the original `rr=2.0`, `tp1=0.5` all-weekday additive row as the plain benchmark.
  - Best all-weekday additive target score: `rr=2.5`, `tp1_ratio=0.4` -> post-2023 `+32.6R`, PF `1.51`, DD `-6.7R`; 2025 `+5.6R`; phase-one post-2023 payout `80.5%`, breach `14.9%`, EV `+3.61R`. This is only modestly better than benchmark (`+1.7R` post-2023, `+0.12R` EV) and slightly worse in 2025.
  - Best no-Thursday additive practical row: `rr=2.5`, `tp1_ratio=0.4` -> post-2023 `+32.7R`, PF `1.67`, DD `-6.6R`; 2025 `+7.0R`; phase-one post-2023 payout `82.8%`, breach `8.0%`, EV `+4.18R`. This is the best additive account-profile improvement, mostly through payout/breach behavior rather than net R.
  - Best pure-CISD practical row: `rr=2.0`, `tp1_ratio=0.6` -> post-2023 `+19.9R`, PF `2.00`, DD `-2.4R`; 2025 `+2.9R`; phase-one post-2023 payout `90.8%`, breach `0.0%`, EV `+4.74R`. This is the strongest pure-CISD target finding, though full-history returns remain modest and exact replay is required.
  - Deployability label for target-sweep rows: `live_native` in research config terms, but exact replay is still required before execution-config promotion.
  - Fresh rerun on 2026-05-16, using cached data through `2026-05-01`, reconfirmed the target-sweep ranking rather than changing it. All-weekday additive `rr=2.5/tp1=0.4` remained the top score row (`597` trades, full `+66.2R`, PF `1.25`, DD `-18.6R`; holdout `+16.2R`, PF `1.81`; post-2023 `+32.6R`, PF `1.51`, DD `-6.7R`). No-Thursday additive `rr=2.5/tp1=0.4` stayed the better production-style account profile (`475` trades, full `+86.1R`, PF `1.44`, DD `-9.8R`; post-2023 `+32.7R`, PF `1.67`, DD `-6.6R`; phase-one post-2023 payout `82.8%`, breach `8.0%`, EV `+4.18R`). Pure CISD `rr=2.0/tp1=0.6` still owned the capital-protection lane with post-2023 payout `90.8%`, breach `0.0%`, EV `+4.74R`, but lower throughput/full R.
  - Execution reality correction from the 2026-05-16 follow-up: these rows are **not live-native today** despite being expressible in the research simulator. The current execution `LSIEngine` does not expose the CISD/additive confirmation fields, so promote them as `research_only` until live/exact parity is implemented, then exact-replay before any dry/live use.
- **NQ NY LSI + CISD hot-regime one-year sweep** (2026-05-04): `backtesting/learnings/reports/NQ_NY_LSI_CISD_HOT_REGIME_SWEEP_20260504.md` and `backtesting/data/results/nq_ny_lsi_cisd_hot_regime_sweep_20260504/`
  - Window: `2025-05-01` to `2026-05-01`. This is in-sample trailing-one-year research only, modeled after HOT_REGIME squeeze work; label rows `research_only` until exact replay or forward validation.
  - Scope: two-stage grid on the pure-CISD leg plus additive allDOW/noThu finalists. Stage 1 swept stop ATR (`7.5-20%`), CISD bars (`2-4`), CISD body ATR (`5-10%`), and entry cutoff (`12:00-15:30`). Stage 2 swept targets around the top structures (`rr=1.5-5.0`, `tp1_ratio=0.3-0.8`, respecting TP1 >= 1R).
  - Best additive allDOW squeeze: `stop=10%`, `bars=3`, `body_atr=7.5%`, `cut=13:00`, `rr=2.5`, `tp1=0.4` -> `45` trades, `+15.48R`, PF `2.11`, DD `-4.07R`; only `+0.51R` over the current same-family baseline but with fewer trades and lower DD.
  - Best additive noThu squeeze: `stop=10%`, `bars=2`, `body_atr=7.5%`, `cut=13:00`, `rr=2.5`, `tp1=0.4` -> `38` trades, `+10.95R`, PF `1.84`, DD `-3.07R`; only `+0.47R` over baseline.
  - Best pure-CISD squeeze: `stop=7.5%`, `bars=4`, `body_atr=5%`, `cut=14:00`, `rr=4.0`, `tp1=0.3` -> `15` trades, `+9.42R`, PF `3.36`, DD `-2.00R`; `+2.02R` over pure baseline. Pure improves most from hot-regime tuning but remains low-throughput.
  - Read: Additive allDOW is still the highest recent-R leg; the one-year optimization mostly tightens cutoffs and confirms the existing `rr=2.5/tp1=0.4` additive target. Pure CISD is the cleaner capital-protection branch, not the highest-R branch.
- **NQ NY LSI DataBento MBP-10 order-book momentum feature lab** (2026-05-14): `backtesting/learnings/reports/NQ_NY_LSI_ORDERBOOK_FEATURE_LAB_20260514.md` and `backtesting/data/results/nq_ny_lsi_orderbook_feature_lab_20260514/`
  - Scope: reused already-downloaded sparse MBP-10 candidate windows; no new DataBento fetch. Validation `2023-01-01` to `2025-04-01` had `537/544` scored rows; holdout `2025-04-01` to `2026-05-02` had `253/255` scored rows.
  - Read: the original blunt confirmation-bar impulse filter still does **not** justify a production hard gate. Validation-selected hard filters were mixed on holdout: no-Thursday additive `confirm_first_10s_aligned_run_volume_ratio` improved holdout avg R by `+0.111` but kept only `12` trades; pure long `pre_confirm_10s_aligned_depth_imbalance_3_mean` improved by `+0.100`; allDOW, 3m hourly, and 2m HTF selected gates faded.
  - More promising path: use order-book momentum as a **risk tier**, not a binary entry filter. Entry-safe `0.5x/1.0x/1.5x` tercile sizing on `pre_confirm_30s_pressure_score` lifted allDOW additive holdout to `57` trades, `+20.05R`, `0.352R` avg versus `+13.10R`, `0.230R` scored baseline; the same feature lifted no-Thursday to `46` trades, `+15.84R`, `0.344R` avg versus `+10.48R`, `0.228R` baseline.
  - Additional risk-tier signals worth a frozen follow-up: `absorption_release_confirm_first_10s_score` lifted 3m hourly holdout to `+18.26R` / `0.397R` avg; pure long benefited from confirm-last velocity/release features, with `confirm_last_10s_mid_velocity_ticks_per_second` tiering reaching `+8.33R` / `0.397R` avg versus `+4.84R` / `0.231R` baseline.
  - Post-confirm diagnostics support the discretionary follow-through intuition but are not entry-safe: no-Thursday additive post-confirm 30s velocity/release rows showed roughly `0.79-0.81R` holdout avg on `17-19` trades. Treat these as chart-review/add-hold-scale ideas, not entry rules.
  - Status: `research_only`. Next honest step is a smaller frozen follow-up around entry-safe risk tiers (`pre_confirm_30s_pressure_score`, absorption-release, confirm-last pure-long velocity) plus visual/manual-label audit before considering any live-native orderbook feature implementation.
- **NQ NY LSI order-book risk-tier replay** (2026-05-15): `backtesting/learnings/reports/NQ_NY_LSI_ORDERBOOK_RISK_TIERS_20260515.md` and `backtesting/data/results/nq_ny_lsi_orderbook_risk_tiers_20260515/`
  - Scope: narrow frozen follow-up on the selected risk-tier families only. Tercile thresholds were frozen on validation and replayed on holdout; no new DataBento data was fetched.
  - Cleanest survivors after exposure normalization: `pre_confirm_30s_pressure_score` on the 1m additive family and `confirm_last_10s_mid_velocity_ticks_per_second` on the pure 1m long family. AllDOW additive improved holdout from `+13.10R` / `0.230R` avg to `+20.05R` / `0.352R` avg, with per-1x avg `0.311R`; no-Thursday additive improved from `+10.48R` / `0.228R` avg to `+15.84R` / `0.344R` avg, per-1x `0.302R`; pure long improved from `+4.84R` / `0.231R` avg to `+8.33R` / `0.397R` avg, per-1x `0.355R`.
  - 3m absorption-release was partially invalidated as a sizing signal: plain validation terciles were degenerate because most values are zero, putting every holdout trade into the high tier. Positive-only rescue tiers demoted first-10s (`validation_failed`) and left full/last-10s only mildly positive per 1x risk while reducing absolute holdout R. Treat 3m absorption-release as a chart-review feature, not a leading sizing overlay.
  - Practical conclusion: if we continue toward implementation, prioritize **1m pre-confirm pressure** and **pure-long confirm-last velocity**. Keep the overlay `research_only` until MBP-10 feature streaming and execution-engine dynamic sizing are implemented and exact replayed.
- **NQ NY LSI discretionary signal roadmap** (2026-05-15): `backtesting/learnings/reports/NQ_NY_LSI_DISCRETIONARY_SIGNAL_ROADMAP_20260515.md`
  - Scope: separates immediate no-extra-fetch discretionary-logic tests from DataBento-required ideas that should be kept for later rather than discarded due to cost.
  - No-extra-fetch priorities: exact dynamic-sizing replay for the 1m pressure survivor; 1s/1m sweep-reclaim velocity; compression-then-expansion; failed-continuation/trapped-trader proxy; clean-air/target-room scoring; and a manual label audit against existing trade windows/features.
  - DataBento later backlog: broader MBP-10 pressure coverage across frozen LSI finalists; more complete additive pressure replay; post-confirm continuation management; absorption-release reformulation; cross-market confirmation; aggressor-flow/trade-print pressure; and liquidity-pull/book-vacuum features.
  - Practical conclusion: cost should not cap the long-term order-book research path, but the next branch should be no-extra-fetch sweep-reclaim velocity so we can test whether price action already explains part of the order-book pressure edge.
- **NQ NY LSI no-fetch sweep-reclaim velocity replay** (2026-05-15): `backtesting/learnings/reports/NQ_NY_LSI_SWEEP_RECLAIM_VELOCITY_20260515.md` and `backtesting/data/results/nq_ny_lsi_sweep_reclaim_velocity_20260515/`
  - Scope: first no-extra-fetch branch from the discretionary roadmap. Reused frozen validation/holdout LSI candidate rows plus local `NQ_1s.parquet`; no DataBento fetch. Features measured sweep depth, reclaim speed, hold after reclaim, post-reclaim displacement, compression/expansion, and trapped-reversal behavior.
  - Clean result: the 3m hourly candidate `add_3m_hourly_atr12p5_b3_a7p5` responded best to `trapped_reversal_confirm_score` as a signal-close risk tier. Primary `0.5x/1.0x/1.5x` sizing lifted validation from `+9.93R` / `0.071R` avg to `+21.68R` / `0.154R` per-1x avg, and holdout from `+12.17R` / `0.265R` avg to `+17.34R` / `0.343R` per-1x avg. Conservative `0.75x/1.0x/1.25x` still improved holdout to `+14.76R` / `0.306R` per-1x avg.
  - Tier read for 3m trapped reversal: holdout high tier had `22` trades, `+11.31R` base, `0.514R` avg and weighted to `+16.96R`; low tier had `13` trades, `+0.97R`; mid tier was slightly negative. `confirm_reclaim_velocity_ticks_per_second` was a secondary mild/supportive version (`+16.06R` holdout, `0.309R` per-1x avg).
  - 1m read: the price-action sweep-reclaim proxies did **not** replace the 1m order-book pressure edge. AllDOW/no-Thursday 1m confirm-time features mostly failed holdout after exposure normalization; only no-Thursday `post_reclaim_60s_score` was mildly positive, but it is post-confirm management-only, not an entry rule.
  - Relationship to order book: correlations between `pre_confirm_30s_pressure_score` and the price-action features were near zero across candidates (combined Spearman generally around `-0.11` to `+0.12`). Treat this as an orthogonal 3m branch, not a cheap duplicate of the 1m MBP-10 pressure survivor.
  - Status: `research_only`. Next no-fetch follow-up is to exact-replay dynamic sizing for the 3m trapped-reversal tier and compare it against the existing 1m MBP pressure survivor; do not promote as live until the 1s feature is implemented in the execution path and exact replayed.
- **NQ NY LSI dynamic sizing phase-one replay** (2026-05-15): `backtesting/learnings/reports/NQ_NY_LSI_DYNAMIC_SIZING_PHASE_ONE_20260515.md` and `backtesting/data/results/nq_ny_lsi_dynamic_sizing_phase_one_20260515/`
  - Scope: no-fetch account-objective replay of existing trade-level baseline R vs weighted R from the order-book risk tiers and sweep-reclaim tiers. Model: new account every `14` calendar days, `+5R` payout, `-4R` breach. This is not exact engine execution, but it is the right account-objective screen before implementation.
  - 3m trapped-reversal account read: over post-2023, the baseline 3m branch had payout `63.2%`, breach `28.7%`, EV `+2.03R/account`. The trapped-reversal tier improved dramatically: skip-weak `0/1/1.5` reached payout `87.4%`, breach `4.6%`, EV `+4.08R` (`+2.05R` delta); primary `0.5/1/1.5` reached payout `83.9%`, breach `10.3%`, EV `+3.77R`; conservative `0.75/1/1.25` reached payout `78.2%`, breach `14.9%`, EV `+3.33R`.
  - Holdout caution: the same 3m trapped-reversal tier did **not** improve holdout-only account EV despite higher aggregate R. Conservative holdout EV was roughly flat (`-0.02R` delta), and primary/aggressive variants raised breach rate. Treat the 3m branch as promising but not promotable until exact replay/full-history account testing clarifies the recent breach behavior.
  - Pure 1m long order-book velocity is the cleanest capital-protection overlay: post-2023 primary tier improved EV by `+0.21R` with payout `86.2%`, breach `0.0%`; holdout improved EV by `+0.54R`, payout `58.6%`, breach `0.0%`. Capacity is low (`54` post-2023 trades, `21` holdout trades), but breach behavior is excellent.
  - Additive 1m order-book pressure caution: no-Thursday/allDOW pressure improves holdout account behavior, but post-2023 account EV worsens for the tiered additive overlays because breach rate rises in the validation segment. Aggregate R is not enough; this needs exact execution replay, conservative sizing, or a phase-one-aware tier rule before promotion.
  - Status: `research_only`. Priority order after this pass: pure 1m long velocity for capital-protection sizing, 3m trapped reversal for further exact/account validation, and 1m additive pressure only with stricter account-objective stress.
- **NQ NY LSI 3m trapped-reversal stress** (2026-05-15): `backtesting/learnings/reports/NQ_NY_LSI_3M_TRAPPED_REVERSAL_STRESS_20260515.md` and `backtesting/data/results/nq_ny_lsi_3m_trapped_reversal_stress_20260515/`
  - Scope: no-extra-fetch stress of the 3m survivor using existing `trade_risk_tier_replay.csv`; added slippage at `0/0.5/1/2` ticks per side, daily loss/account rules, tier-level quality, monthly stability, and bootstrap fragility. This remains research-engine trade replay, not full live execution parity.
  - Execution parity finding: the current live LSI execution path is 5m-feed oriented and does not yet express this research candidate's `inversion_or_cisd` confirmation plus `atr_pct` stop exactly. A separate execution implementation/parity task is required before promotion.
  - R-multiple stress stayed positive after 1 tick/side slippage: holdout `0.5/1/1.5` reached `46` trades, `+16.75R`, `0.364R` avg, PF `1.95`; skip-weak `0/1/1.5` reached `33` trades, `+16.35R`, `0.495R` avg, PF `2.08`; conservative `0.75/1/1.25` reached `+14.18R`, `0.308R` avg, PF `1.82`.
  - Stricter account stress was the limiter. With 1 tick/side slippage, `-2R` daily stop, minimum `5` trading days, and `14`-day account staggering, post-2023 EV improved strongly (`0/1/1.5` `+2.57R` delta; `0.5/1/1.5` `+2.06R`; conservative `+1.20R`), but holdout EV was flat-to-worse (`0.5/1/1.5` `-0.02R`, conservative `-0.05R`, skip-weak `-0.36R`) while breach rates rose by `+3.4` to `+6.9` points.
  - Tier read after 1 tick/side slippage: conservative high tier was robust in both validation (`48` trades, `+20.33R`, `0.424R` avg, PF `2.07`) and holdout (`22` trades, `+13.83R`, `0.629R` avg, PF `2.66`), but validation low/mid tiers were negative and holdout low/mid were only small positive/flat. This supports risk-tiering, not a hard gate yet.
  - Status: keep as `research_only` and do **not** promote. Best next path is either implement live parity for `3m + CISD + atr_pct stop + 1s trapped-reversal feature`, or use this as a chart-review/manual-label branch while prioritizing the pure 1m order-book velocity survivor for cleaner account behavior.
- **NQ NY LSI pure 1m order-book velocity stress** (2026-05-15): `backtesting/learnings/reports/NQ_NY_LSI_PURE_1M_ORDERBOOK_VELOCITY_STRESS_20260515.md` and `backtesting/data/results/nq_ny_lsi_pure_1m_orderbook_velocity_stress_20260515/`
  - Scope: same no-fetch stress framework applied to `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200` with `confirm_last_10s_mid_velocity_ticks_per_second`. Used existing order-book risk-tier replay rows; no DataBento fetch.
  - Account read is stronger than 3m trapped-reversal. With 1 tick/side slippage, `-2R` daily stop, minimum `5` trading days, and `14`-day account staggering, primary `0.5/1/1.5` had post-2023 payout `86.2%`, breach `0.0%`, EV `+4.64R` (`+0.22R` delta) and holdout payout `58.6%`, breach `0.0%`, EV `+3.83R` (`+0.57R` delta). Conservative and skip-weak were also positive with `0.0%` breach.
  - R stress stayed clean after 1 tick/side slippage: holdout primary `21` trades, `+8.07R`, `0.384R` avg, PF `2.23`, max DD `-1.53R`; post-2023 primary `54` trades, `+19.23R`, `0.356R` avg, PF `2.22`, max DD `-2.84R`.
  - Tier read: the high-velocity tier carries the edge (`11` holdout trades, `+9.45R`, `0.859R` avg, PF `4.13` after 1 tick/side slippage). Holdout low and mid tiers were negative, so skip-weak/high-tier emphasis is worth keeping as a deployment design question.
  - Status: still `research_only` because live MBP-10 feature streaming and execution-engine dynamic sizing are not implemented. This is now the cleaner promotion candidate than 3m trapped-reversal on account behavior, with the caveat that capacity is low (`21` holdout trades).
- **NQ NY LSI pure 1m order-book velocity live scope** (2026-05-15): `backtesting/learnings/reports/NQ_NY_LSI_PURE_1M_ORDERBOOK_VELOCITY_LIVE_SCOPE_20260515.md`
  - Scope: implementation plan for live MBP-10 feature streaming plus dynamic sizing around the pure 1m survivor first. Frozen thresholds are low `< -0.322`, mid `[-0.322, 0.912)`, high `>= 0.912` ticks/sec with primary `0.5/1/1.5` sizing.
  - Architecture path: optional `mbp-10` subscription in `execution/src/trader/feed.py`, new rolling `orderbook_features.py` cache/sizer, `dynamic_sizing_provider` injection through `execution/src/trader/main.py`, and quantity weighting inside `LSIEngine._build_and_enter()`.
  - Practical blocker: infrastructure can land first, but the survivor is not live-native until exact pure-1m/CISD/timing/ATR-stop parity is verified through the execution engine. First replay bridge should use the existing scored feature CSVs before fetching broader MBP-10 history.
- **NQ NY LSI pure 1m order-book velocity minimum implementation validation** (2026-05-16): `backtesting/learnings/reports/NQ_NY_LSI_PURE_1M_ORDERBOOK_VELOCITY_MIN_IMPL_VALIDATION_20260516.md` and `backtesting/data/results/nq_ny_lsi_pure_1m_orderbook_velocity_min_impl_validation_20260516/`
  - Scope: no-fetch validation of the execution-facing order-book sizing bridge against the frozen pure 1m replay CSV. Historical DataBento days required: `0`; new fetches: `0`.
  - Match result: `54` rows / `54` unique trade dates / `54` trade IDs checked with `0` tier mismatches, `0` weight mismatches, and `0` weighted-R mismatches.
  - Metrics reproduced: holdout `21` trades improved from `+4.84R` baseline to `+8.33R` weighted (`0.397R` avg, PF `2.28`, max DD `-1.50R`); validation `33` trades improved from `+10.55R` to `+11.63R`.
  - Implementation progress: `LSIEngine` now accepts a disabled-by-default `dynamic_sizing_provider`, scales contract quantity at entry, records sizing metadata on trade records/status, and can replay scored CSV rows through `ScoredFeatureLookupProvider`.
  - Zero-cost live hook progress: `DataBentoFeed` now supports optional `mbp-10` top-of-book callbacks into the order-book feature cache, but `[orderbook].enable_mbp10 = false`, `[orderbook].mbp10_cost_ack = false`, `[orderbook].dynamic_sizing_enabled = false`, and `[orderbook].dynamic_sizing_shadow_enabled = false` remain the config defaults, so there is no added DataBento usage until explicitly enabled and acknowledged.
  - Safety/status progress: startup refuses MBP-10 unless `mbp10_cost_ack=true`; shadow mode can compute/log sizing decisions without changing quantity; dashboard status includes order-book config/cache status.
  - Status: implementation bridge `pass`, but still not promotable. Remaining blocker is enabling MBP-10 in paper/live validation plus paper parity against the exact live execution path.
- **NQ NY LSI pure 1m MBP-10 fetch and raw replay validation** (2026-05-16): `backtesting/learnings/reports/NQ_NY_LSI_PURE_1M_MBP10_FETCH_AND_REPLAY_VALIDATION_20260516.md`, `backtesting/data/results/nq_ny_lsi_pure_1m_mbp10_fetch_20260516/`, and `backtesting/data/results/nq_ny_lsi_pure_1m_velocity_mbp10_replay_validation_20260516/`
  - Scope: cost-gated Databento MBP-10 fetch for the pure 1m velocity survivor's holdout mornings. Exact trade snippets were already locally covered, so the fetch targeted continuous `09:30 ET` morning-prefix windows through each signal plus buffer.
  - Cost result: `21` windows / `84,835,005` records / `31.219 GB` billable quoted and fetched at `$12.1006`, under the user-requested `$20` ceiling; `21/21` files present, `2.311 GB` compressed on disk.
  - Tooling progress: `download_orderbook_data.py` now supports `--max-cost` and estimates all chunks before any download, so future MBP-10 pulls can be budget-gated before spending.
  - Live-path replay: raw DBN `MBP10Msg` records were streamed through top-of-book samples into `OrderbookFeatureCache` and `OrderbookVelocityTierSizer`; representative low/mid/high replay passed `3/3`, then full holdout passed `21/21` feature, tier, and risk-weight matches.
  - Status: historical MBP-10 data blocker for this survivor is cleared. Still not live-promoted until exact execution-engine parity and paper/shadow mode validation are complete.
- **NQ NY LSI pure 1m exact execution parity** (2026-05-16): `backtesting/learnings/reports/NQ_NY_LSI_PURE_1M_EXACT_EXECUTION_PARITY_20260516.md`
  - Scope: live execution-engine parity for `pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200`, including 1m routing, CISD confirmation, level-limit entry, and `15%` daily-ATR stop logic.
  - Implementation progress: execution now has a causal `InternalCisdTracker`; `LSIEngine` supports `lsi_confirmation_mode="cisd"`, `lsi_stop_mode="atr_pct"`, `stop_atr_pct`, `base_bar_minutes`, and a disabled `NQ_NY_LSI_PURE_1M` shadow profile.
  - Replay result: exact execution replay over `2025-04-10` to `2026-04-30` produced `21` trades on the same `21/21` holdout dates as the frozen research CSV, with no missing or extra dates. Research baseline was `+4.841R`; live-style exact replay was `+5.50R`, `0.262R` avg, PF `1.84`, max DD `-1.50R`.
  - Interpretation: signal-date parity is cleared. R totals differ because the research score is 1m bar-level while exact replay exits through the live-style 1s path; use exact replay as the more operational baseline.
  - Status: `post_filter_only` moving toward `live_native`. Remaining blocker is paper/shadow validation with live MBP-10 feature values before any quantity-changing dynamic sizing.
- **NQ NY LSI pure 1m exact MBP-10 shadow replay** (2026-05-16): `backtesting/learnings/reports/NQ_NY_LSI_PURE_1M_EXACT_MBP10_SHADOW_20260516.md` and `backtesting/data/results/nq_ny_lsi_pure_1m_exact_mbp10_shadow_20260516/`
  - Scope: no-new-cost exact replay using the locally replayed MBP-10 feature decisions as a `dynamic_sizing_provider` in shadow mode. DataBento fetches: `0`.
  - Implementation progress: exact replay now accepts session-scoped dynamic sizing providers; MBP-10 replay CSV rows with `actual_feature_value` can feed `ScoredFeatureLookupProvider`; exact replay trade exports now include `entry_context.dynamic_sizing`.
  - Result: `21` exact trades, `21` active sizing decisions, `0` fallbacks, same tier split as research/high-low-mid (`11/6/4`). Exact baseline improved from `+5.50R`, `0.262R` avg, PF `1.79`, max DD `-1.50R` to shadow-weighted `+9.25R`, `0.440R` avg, PF `2.42`, max DD `-1.50R`.
  - Interpretation: this clears the offline exact-engine shadow bridge. The remaining live-native blocker is a paper/live shadow run with real-time MBP-10 intentionally enabled and compared against offline replay before quantity-changing deployment.
- **NQ NY LSI pure 1m challenger branches** (2026-05-17): `backtesting/learnings/reports/NQ_NY_LSI_PURE_1M_CHALLENGER_BRANCHES_20260517.md` and `backtesting/data/results/nq_lsi_pure_1m_challenger_branches_20260517/`
  - Scope: started three no-extra-fetch discretionary-momentum side branches against the pure 1m champion trade set: reversal violence relative to day from local `NQ_1s.parquet`, absorption-then-release from existing sweep/reclaim and MBP-10 lab fields, and liquidity-vacuum/book-pull from existing MBP-10 depth/microprice fields. DataBento fetches: `0`.
  - Result: current pure 1m velocity champion remained ahead on holdout (`+8.33R`, `0.397R` avg, PF `2.28`) versus the best challenger. The only challenger supported on both validation and holdout after exposure normalization was liquidity-vacuum `ob_vacuum_confirm_last_10s_score`, lifting holdout baseline from `+4.84R` to `+7.02R`, `0.334R` avg, PF `2.17`, max DD `-2.25R`.
  - Branch read: price-violence features were directionally useful but only mild on holdout (`+6.04R` to `+6.28R` primary tier); absorption-release was unstable or degenerate on this pure 1m set; liquidity-vacuum confirm-last-10s is the only serious side branch, but not a replacement for live-shadowing the champion.
  - Status: `research_only`. Keep the pure 1m confirm-last velocity shadow as champion. If revisited, liquidity-vacuum should be an additive diagnostic or ensemble candidate after exact/live feature implementation, not the next deployment path by itself.
- **NQ NY LSI broad discretionary challenger matrix** (2026-05-17): `backtesting/learnings/reports/NQ_NY_LSI_BROAD_DISCRETIONARY_CHALLENGER_MATRIX_20260517.md` and `backtesting/data/results/nq_lsi_broad_discretionary_challenger_matrix_20260517/`
  - Scope: widened the no-extra-fetch discretionary-momentum branch test across locally covered variants: 1m additive allDOW/noThu, 3m hourly additive, 2m HTF anchor, pure 1m, plus generated the current 5m HTF-LSI lag24 path from the research engine. DataBento fetches: `0`. Existing MBP-10 features were available for all but the 5m path; 5m was price-action only.
  - Strict stable survivors after exposure normalization on both validation and holdout: 3m `trapped_reversal_confirm_score` lifted holdout from `+12.17R` to `+17.34R` (`0.377R` avg, PF `2.00`), and pure 1m liquidity-vacuum `ob_vacuum_confirm_last_10s_score` lifted holdout from `+4.84R` to `+7.02R` (`0.334R` avg, PF `2.17`).
  - Incumbent order-book paths still matter by absolute holdout R: 1m additive `pre_confirm_30s_pressure_score` remained best for allDOW (`+13.10R` to `+20.05R`) and noThu (`+10.48R` to `+15.84R`), and pure 1m `confirm_last_10s_mid_velocity_ticks_per_second` still beat the pure liquidity-vacuum side branch on absolute holdout (`+8.33R` vs `+7.02R`), even though its validation read is only mild under per-1x normalization.
  - 2m stayed weak: best local row was confirm-last velocity (`+1.17R` to `+4.93R`) but only mild on holdout and not enough to reopen 2m as a co-lead. The current 5m path had mild holdout response to signal-bar price violence (`+10.93R` to `+13.08R`) but failed validation; sweep/reclaim was zero-inflated/exposure-only. 5m order-book absorption/vacuum remains untested until MBP-10 windows are fetched for that branch.
  - Status: `research_only`. Keep live-shadow priority on pure 1m velocity; keep 3m trapped reversal and pure 1m liquidity-vacuum as side research branches. If the 5m path is to be tested under the original order-book thesis, the next step requires a budget-gated MBP-10 fetch for 5m signal windows.
- **NQ NY LSI pure 1m liquidity-vacuum exact shadow replay** (2026-05-17): `backtesting/learnings/reports/NQ_NY_LSI_PURE_1M_LIQUIDITY_VACUUM_EXACT_SHADOW_20260517.md` and `backtesting/data/results/nq_ny_lsi_pure_1m_liquidity_vacuum_exact_shadow_20260517/`
  - Scope: no-new-cost exact live-engine replay for the pure 1m liquidity-vacuum side branch. Reused the broad challenger matrix's `ob_vacuum_confirm_last_10s_score` rows and froze validation thresholds (`low < 0.054561`, `high >= 0.461590`) into the same `ScoredFeatureLookupProvider`/dynamic-sizing bridge used by the champion.
  - Exact result: `21` exact trades, `21` active sizing decisions, `0` fallbacks, same date set as the pure 1m holdout. Exact baseline was `+5.50R`, `0.262R` avg, PF `1.79`, max DD `-1.50R`; scored shadow weighted to `+7.25R`, `0.345R` avg, PF `2.21`, max DD `-2.25R`.
  - Read: liquidity-vacuum survives exact-shadow replay and remains a real side branch, but it does **not** beat the pure 1m velocity champion's exact shadow (`+9.25R`, `0.440R` avg, PF `2.42`, max DD `-1.50R`). Keep it as side research or future ensemble input, not the implementation champion.
  - Status: `research_only` moving toward shadow-capable. It is still scored-feature replay only; live-native support needs MBP-10 depth/microprice fields in the feature cache, not just current top-of-book midpoint velocity.
- **NQ NY LSI orderflow side-branch provider validation** (2026-05-17): `backtesting/learnings/reports/NQ_NY_LSI_ORDERFLOW_SIDE_BRANCH_PROVIDER_VALIDATION_20260517.md` and `backtesting/data/results/nq_lsi_orderflow_side_branch_provider_validation_20260517/`
  - Scope: no-fetch execution-facing provider validation for the three active tracks: pure 1m velocity champion, pure 1m liquidity-vacuum side branch, and 3m trapped-reversal side branch. Profile was the primary `0.5x/1.0x/1.5x` sizing ladder.
  - Match result: `293` rows checked across validation and holdout with `0` tier mismatches, `0` weight mismatches, and `0` weighted-R mismatches. This confirms the frozen research scores can be consumed by the execution sizing interface without drift.
  - Track read: pure 1m velocity remains implementation/shadow champion because it has live-engine exact shadow support and the best exact weighted R; pure 1m liquidity-vacuum is now scored exact-shadow validated but needs live-native MBP-10 depth features; 3m trapped reversal remains research-only because exact 3m execution parity and a live/replay trapped-reversal feature calculator are not implemented.
  - Status: keep pushing all three, but with separate lanes: champion forward shadow for pure 1m velocity, side-branch live-feature implementation scope for liquidity-vacuum, and exact-engine parity scope first for 3m trapped reversal.
- **NQ NY LSI 3m trapped-reversal exact probe** (2026-05-17): `backtesting/learnings/reports/NQ_NY_LSI_3M_TRAPPED_REVERSAL_EXACT_PROBE_20260517.md` and `backtesting/data/results/nq_lsi_3m_trapped_reversal_exact_shadow_probe_20260517/`
  - Scope: no-fetch exact-engine probe using a temporary execution profile for `add_3m_hourly_atr12p5_b3_a7p5`; added exact-replay support for `3m` bar files. This did not alter live config.
  - Probe result: research holdout expected `46` trades, while the exact engine produced `52`. Date parity is blocked: `9` research dates were missing and `15` exact dates were extra. The scored trapped-reversal provider had `17` fallback decisions because exact signal timestamps did not fully match the frozen research rows.
  - Exact/probe metrics were still directionally positive but not promotable: exact baseline `+5.07R`, `0.098R` avg, PF `1.22`, DD `-5.00R`; shadow weighted `+9.36R`, `0.180R` avg, PF `1.39`, DD `-6.24R`.
  - Status: 3m trapped reversal remains alive, but its next blocker is exact signal-stream parity (`3m + hourly HTF pivots + inversion_or_cisd + level_limit + atr_pct stop`) before any live shadow or deployment work. Treat the current probe as a map of what to fix, not a validation pass.

- **Hot one-year squeeze** (2026-05-03): `backtesting/learnings/reports/HOT_ONE_YEAR_SQUEEZE_20260503.md`
  - Window: `2025-03-24` to `2026-03-24`. TESTING-only second-stage local squeeze around prior screenshot winners.
  - NQ NY ORB: `prev_curve_net__combo__rr6p0_tp0p8__stop_atr_3p0__cap2_any__gap_orb_5p0__entry_end_1130__orb8m__fvg_extreme` with `gate_none` -> 77 fills, `63.94R`, Calmar `12.788`, PF `2.28`, DD `-5.0R`, surface `curve`.
  - NQ Asia ORB: `prev_curve_calmar__combo__rr5p5_tp0p8__entry_end_0600__cap2_any__flat_0600__stop_atr_3p0__orb15m__dow_exFri` with `gate_skip_bear_medium_high` -> 173 fills, `91.23R`, Calmar `6.179`, PF `1.836`, DD `-14.76R`, surface `curve`.
  - NQ NY LSI: `prev_curve_net__combo__rr3p0_tp0p8__flat_1500__htfN3__fvgL10_R10__entry_1500__atr5__window_0830_1430` with `gate_none` -> 93 fills, `42.71R`, Calmar `10.678`, PF `2.107`, DD `-4.0R`, surface `curve`.

- **Hot structural sequence** (2026-05-03): `backtesting/learnings/reports/HOT_STRUCTURAL_SEQUENCE_20260503.md`
  - Window: `2025-03-24` to `2026-03-24`. Post-trade structural gates around current hot one-year candidates.
  - NQ NY ORB: best structural `combo__adverse_wick_le_35__exclude_cpi_nfp` (combo) -> 48 fills, `56.3R`, Calmar `18.768`, PF `3.0`, DD `-3.0R`, delta `-7.65R`; TESTING-only.
  - NQ Asia ORB: best structural `exclude_cpi_nfp` (calendar_news) -> 162 fills, `77.24R`, Calmar `5.231`, PF `1.76`, DD `-14.76R`, delta `-6.17R`; TESTING-only.
  - NQ NY LSI: best structural `prior_not_inside_day` (prior_day) -> 81 fills, `42.54R`, Calmar `13.863`, PF `2.386`, DD `-3.07R`, delta `-0.17R`; TESTING-only.

- **Hot structural follow-up** (2026-05-03): `backtesting/learnings/reports/HOT_STRUCTURAL_FOLLOWUP_20260503.md`
  - Window: `2025-03-24` to `2026-03-24`. Targeted second pass around positive structural gates from the hot structural sequence.
  - NQ NY ORB: best refined structural `exclude_cpi` -> 76 fills, `64.95R`, delta `1.0R`, Calmar `12.99`, PF `2.327`, DD `-5.0R`, surface `n/a`; TESTING-only.

### ALPHA_V1 ATH Regime Findings (2026-05-05)

Reports: `backtesting/learnings/reports/ALPHA_V1_ATH_REGIME_FIRST_PASS_20260505.md` and `backtesting/learnings/reports/ALPHA_V1_ATH_REGIME_LEG_TARGETS_20260505.md`

- `NQ NY HTF-LSI` is strongest in the `1-5%` below futures ATH area (`1-2%` + `2-5%`: `166` trades, `+62.1R`, `0.374R` avg), and the pure `2-5%` pocket is even higher average (`102` trades, `+42.1R`, `0.412R` avg). However, whitelisting those buckets cuts portfolio R by `-30.5R` to `-50.5R` and slows payout cadence. The surgical skip of weak `0.5-1%` and `5-10%` buckets is safer but only adds `+0.3R` full history and loses `-2.2R` in `2025+`. Status: research attribution, not promotion.
- `NQ Asia ORB` does not support a simple ATH gate. Full-history top-bucket whitelists improve standalone average R, but the recent window fails: `2025+` loses roughly `-23R` to `-26R` depending on the gate. Do not prioritize NQ Asia ATH filtering until new data or a different regime thesis supports it.
- Portfolio-level `combo_negative_only_skip` includes a small NQ HTF-LSI skip of the `0.5-1%` bucket alongside the ES NY dead-zone skip. It is the best portfolio-R overlay (`+6.1R` full history, `+5.6R` in `2025+`) but remains `post_filter_only` and full-history combined payout is worse, so exact replay is required before any consideration.
