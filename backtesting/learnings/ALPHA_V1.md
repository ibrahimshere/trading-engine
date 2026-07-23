# ALPHA_V1 Portfolio

Separate-account portfolio optimized for prop firm payout extraction. Each leg runs on its own independent funded account. As of 2026-04-12, the NQ NY leg has been swapped from the archived legacy `NQ_NY_LSI` branch to the current preferred **live / discretionary** NQ NY LSI profile: the `ALPHA_V1` HTF-LSI override (`08:30-13:30`, `rr=3.5`, `tp1=0.4`, risk governed by the sizing table below). This should be treated as the active operating profile. The standalone `HTF_LSI_5M_LAG24` block remains the frozen canonical research anchor for the underlying HTF-LSI thesis.

2026-05-06 operating update: **NQ NY ORB R11** is added as a fifth live-native ALPHA leg, but only as a risk-split NY ORB sleeve beside a reduced **ES_NY ORB** allocation. Keep both NY ORB legs on their exact-replayed split ladders; solve the ES_NY discomfort with lower risk, not single-target compression.

2026-05-07 fee update: the new MNQ/MES fee accounting materially degrades the phase-one payout read versus the pre-fee R-scaled screen. The live aggressive sprint menu is still fastest, but no current tested menu is genuinely low-breach after exact fee-aware sizing; treat the old `95%+` payout / low-breach rows as superseded.

Source: LLM Council sessions (2026-04-03), exact replacement sizing packets, and current HTF-LSI exact replay (updated 2026-04-12).

---

## Account Model

| Parameter | Value |
|-----------|-------|
| Account size | $50,000 |
| Trailing drawdown | $2,000 |
| Trail stops at | $52,000 |
| Phase 1 (Sprint) target | $52,500 |
| First payout withdrawal | $500 |
| Phase 2 (Extraction) risk | $200/trade |
| Weekly withdrawal | Friday, withdraw above $52.5K to $52K |
| Account cost | $150 per account |
| Stagger interval | 14 calendar days |

### Risk Sizing Per Leg

Risk is differentiated per leg based on actual trade-level prop sims. For the NQ NY HTF leg, the sizing row below uses the exact replacement risk sweep. The 2026-05-07 fee-aware replay reran the current `ALPHA_V1-A` five-leg profile at each risk menu with MNQ/MES fees applied in the exact engine; this supersedes the older 2026-05-06 stitched pre-fee payout read.

Live execution single-contract cap rule: each leg sets `max_single_risk_usd = 1.5 * risk_usd`. If one micro contract would exceed that cap, the setup is skipped; if it fits, one-contract split trades now exit the full position at TP1 instead of using TP1 only as a breakeven trigger.

| Leg | Sprint Risk | Pay% | PayD | MCBch | EV$/acct | Rationale |
|-----|------------|------|------|-------|----------|-----------|
| NQ NY HTF-LSI lag24 | $500 | 82.6/73.1%* | 41/21d* | 7* | +$202* | Selected aggressive sprint sizing; fastest payout sleeve, accepts higher breach variance |
| NQ Asia ORB | $400 | 82.6/73.1%* | 41/21d* | 7* | +$202* | Selected aggressive sprint sizing; primary Asia accelerator |
| ES Asia Cont | $150 | 82.6/73.1%* | 41/21d* | 7* | +$202* | Trimmed from `$200` in the annual payout sim to reduce breach clustering while preserving speed |
| NQ NY ORB R11 | $250 | 82.6/73.1%* | 41/21d* | 7* | +$202* | Added NY ORB companion leg; exact split replay `+148.3R`, `PF 1.51`, `-6.45R` DD |
| ES NY Cont | $300 | 82.6/73.1%* | 41/21d* | 7* | +$202* | Higher-risk aggressive sprint satellite; monitor 2026 NY stress closely |

\* Fee-aware exact profile rerun for selected aggressive sprint `HTF $500 / NQ Asia $400 / ES Asia $150 / NQ R11 $250 / ES NY $300`: `82.6%` payout / `17.4%` breach / `41.1d` average payout in 2024, `73.1%` payout / `26.9%` breach / `20.8d` average payout in 2025, and partial `2026_YTD` had `3` payouts, `0` breaches, and `3` open accounts through `2026-03-24`.

### Phase-Two (Post-First-Payout) Operating Mode (2026-07-22)

Report: `backtesting/learnings/reports/ALPHA_V1_PHASE_TWO_PORTFOLIO_20260722.md`

Once an account has taken first payout (locked $50k floor, ~$2k room, >=5 days of >=$250
profit per payout cycle), the sprint risk menus above are too hot and base-hit single-target
menus are a trap: at consistency-qualifying risk (>=$250/leg) every pure singles structure
showed 50-88% one-year MC breach odds. Phase-2 default is the **same five legs and exits at
flat $150 risk with banked-buffer withdrawals (trigger $53.0k, withdraw to $52.5k)**: 0%
cohort breach, ~8% MC 1y breach full-window (~1% on 2025+), median ~$7.1k/yr withdrawn
(~$12.4k/yr in the 2025+ regime). Conditional upgrade pending exact replay: swap ES Asia to
single-target 1.25R at 1.3x leg risk (qualifying days 2.3 -> 2.9/mo, ~$9.3k/yr, 11.3% MC
breach with the $53k buffer). Expect a 5-qualifying-day cycle to take ~6-9 weeks at $150 flat.

Churn-ROI addendum (same report): if accounts are treated as $300 disposable leverage instead
of preserved assets, every menu is 15-80x positive EV per account and extraction rate scales
with risk: the live SPRINT menu earns ~$13.4k/slot-yr (MC, ~$23.5k on 2025+) with first
withdrawal ~30d and ~1.5 accounts churned/yr; SPRINT x1.5 reaches ~$21k/slot-yr with first
withdrawal ~20d. Beyond ~x1.5 the median historical account extracts $0 (tail-carried EV) —
treat x1-x1.5 sprint with withdraw-max policy as the churn-mode operating band. Base-hit
single-target menus are dominated in the churn frame as well.

Apex-exact addendum (same report, supersedes the generic churn read for Apex accounts): the
50K EOD PA has a 6-payout lifetime cap ($13k max extraction), per-payout caps ($1.5k-$3k),
a 50% best-day consistency gate, tier-based DLL ($1k-$3k intraday) and contract caps
(20-40 micros), and a threshold lock at $50,100. Under these rules EV/account converges
(~$4-7k) and the objective becomes completion probability x speed. The 50% consistency rule
specifically taxes sprint-sized runner days (historical median withdrawn: SPRINT x1 $2.8k
vs SPLIT5 $250 $11.6k). **Apex operating band: current five split legs at flat $200-250,
withdraw max every eligible Friday.** Base-hit singles menus are dominated under every frame.

### ALPHA-V1-APEX Execution Profile (2026-07-22)

Execution profile added: `ALPHA-V1-APEX` in `execution/config/exec_configs.json` (dry-run,
`webhooks=[]`). Same five legs and exits as `ALPHA_V1-A`; sizing is adaptive via the new
`execution/src/trader/adaptive_risk.py` (`AdaptiveRiskManager`), wired into both ORB and LSI
engines and tested in `execution/tests/test_adaptive_risk.py`.

Rules implemented:
- **Tier sizing** (base `risk_usd=$250`, `max_single=$375`, both scaled): profit < $1.5k ->
  0.8x ($200) with a 20-micro cap; $1.5k-$3k -> 1.0x with 30 micros; >= $3k -> 1.0x with 40
  micros. The profile's `ContractCapManager` cap follows the tier automatically.
- **Consistency throttle**: while the best profitable day since the last approved payout is
  >= 50% of cycle net profit, risk scales a further 0.5x until the gate clears.
- **Account state**: tracked from the profile's own closed trades (net PnL by ET date),
  anchored at `anchor` (date + balance) in the config block; payouts are recorded by
  appending `{date, amount}` to `adaptive_risk.payouts` (this resets the consistency cycle
  and lowers balance/tier, mirroring Apex). State persists to
  `execution/config/adaptive_risk_state.json` and re-seeds from trade history on restart.

Operating notes: on each approved Apex payout, append the payout to the profile's
`payouts` list and restart/reload; use `balance_override` if engine-tracked balance drifts
from the real account. Historical exact replay does not apply adaptive scaling (account
state is lifecycle-dependent); validate sizing behavior in dry-run logs, then promote by
adding webhooks per the usual acceptance flow.

### Risk Combination Suggestions

These are operating risk menus. The 2026-05-07 fee-aware annual sim uses current `ALPHA_V1-A` exact profile replays with MNQ/MES fees at `$0.575` per contract per side and per-menu `max_single_risk_usd = 1.5 * risk_usd`.

| Mode | NQ NY HTF-LSI | NQ Asia ORB | ES Asia ORB | NQ NY ORB R11 | ES NY ORB | Read |
|------|---------------|-------------|-------------|---------------|-----------|------|
| Fast-safe annual default | $300 | $300 | $150 | $150 | $100 | No longer clean after fees: `59d` avg 2024-2025 payout, `77.5%` resolved payout, `22.5%` breach, `6` max consecutive breaches |
| Balanced NY sleeve challenger | $300 | $300 | $200 | $250 | $200 | Best clustering tradeoff among tested rows: `46d` avg payout, `76.8%` resolved payout, `23.3%` breach, `4` max consecutive breaches |
| Aggressive sprint | $500 | $400 | $150 | $250 | $300 | Selected live sprint menu remains fastest: `31d` avg payout, `77.8%` resolved payout, `22.2%` breach, but `7` max consecutive breaches |

**Current combined-account exact packet with HTF swap (legacy `NQ_NY_LSI` replaced by `HTF_LSI_5M_LAG24` at `$300`; other legs unchanged):**

| Window | Pay% | Avg PayD | Payouts | Breaches | Open | Notes |
|--------|------|----------|---------|----------|------|-------|
| 10Y | 73.6% | 134d | 192 | 69 | 0 | Exact replacement packet |
| 2024 | 84.2% | 110d | 16 | 3 | 7 | Strong replacement year |
| 2025 | 84.6% | 96d | 22 | 4 | 0 | Best fully resolved recent year |
| 2026 YTD | 100.0%* | 42d | 1 | 0 | 5 | Too open-heavy to lean on |

\* Resolved accounts only. This portfolio packet was run on the immediately prior lag24 baseline (`08:30-15:00`, `rr=3.0`, `tp1=0.6`). The live `ALPHA_V1` leg is now the tighter `08:30-13:30`, `rr=3.5`, `tp1=0.4` version. The HTF-LSI leg itself was rerun on `2026-05-16` after the stale HTF-level invalidation fix; a fresh full four-leg exact portfolio rerun is still pending.

---

## Active Legs

### Leg 1: HTF_LSI/NQ_NY-L24

**Tier 1 — Canonical LSI Swap-In**

| Param | Value |
|-------|-------|
| strategy | htf_lsi |
| entry_mode | fvg_limit |
| sweep_window | 08:30-15:00 |
| session | NY (08:30-13:30 entry, flat 15:50) |
| direction | long only |
| rr | 3.5 |
| tp1_ratio | 0.4 |
| atr_length | 14 |
| min_gap_atr_pct | 3.0% |
| htf_level_tf_minutes | 60 |
| htf_n_left | 3 |
| htf_trade_max_per_session | 2 |
| fvg_window | 20 / 2 |
| max_fvg_to_inversion_bars | 24 |
| DOW exclusion | None |
| regime gate | None |
| magnifier | 1s |

| Metric | Full History | Holdout (2025-04-01 to 2026-05-01) |
|--------|-------------|-------------------|
| Trades | 394 | 29 |
| Win Rate | 53.6% | 62.1% |
| PF | 1.47 | 2.10 |
| Sharpe | 2.916 | 5.290 |
| Net R | +82.3 | +11.7 |
| Max DD | -8.0R | -3.0R |
| Calmar | 10.29 | 3.92 |
| Neg years | 1 | — |

Corrected exact replay on the current live params, after stale HTF levels are consumed when breached outside the valid sweep/entry window: only `2019` was a negative full year; `2016-2018` and `2020-2026 YTD` were positive. This supersedes the old `493`-trade ALPHA leg summary.

The older `$300` sizing and combined swap-in payout references were generated on the pre-correction stream and should be treated as stale until rerun.

R by year: 2016:+2.6 | 2017:+6.0 | 2018:+11.6 | 2019:-1.5 | 2020:+13.2 | 2021:+7.9 | 2022:+6.2 | 2023:+10.4 | 2024:+14.8 | 2025:+8.9 | 2026:+2.3

Corrected rolling exact windows:

| Window | Dates | Trades | Win Rate | PF | Net R | Max DD | Calmar |
|--------|-------|-------:|---------:|---:|------:|-------:|-------:|
| 10Y | 2016-05-01 to 2026-05-01 | 385 | 53.5% | 1.49 | +83.3 | -8.0R | 10.42 |
| 2Y | 2024-05-01 to 2026-05-01 | 60 | 58.3% | 1.92 | +21.1 | -3.7R | 5.70 |
| 1Y | 2025-05-01 to 2026-05-01 | 25 | 68.0% | 2.78 | +13.3 | -2.0R | 6.67 |

Execution: `ALPHA_V1` live `NQ_NY_LSI` override now mirrors this HTF-LSI profile.

Corrected challenger retest: no other NQ NY LSI/HTF-LSI candidate cleanly replaced this slot on all-weather evidence. The only live-native conditional tweak worth portfolio-level exact testing is adding `block_bear_high_vol`: exact holdout improved to `28` trades, PF `2.29`, `+12.7R`, with the same `-3.0R` holdout DD, but full-history R slipped to `+78.7R` and Calmar to `9.84`. Research-only additive EQHL (`15m tol1`) remains interesting but is not execution-supported.

---

### Leg 2: ORB/NQ_ASIA-RR6

**Tier 1 — Fastest payout engine**

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia (20:00-20:15 ORB, entry 20:15-22:30, flat 04:00) |
| direction | long only |
| rr | 6.0 |
| tp1_ratio | 0.3 |
| atr_length | 5 |
| stop | ORB 100% |
| gap_filter | ORB-based, min_gap_orb_pct=10.0 |
| DOW exclusion | Tuesday |
| regime gate | None |
| magnifier | 1s |

| Metric | Full History | Holdout (2025-03+) |
|--------|-------------|-------------------|
| Trades | 753 | 68 |
| Win Rate | 45.2% | — |
| Sharpe | 2.860 | 5.87 |
| Net R | +212.0 | +30.8 |
| Max DD | -10.2R | — |
| Neg years | 0 | — |

Payout sim: 82.4% success, +3.31R EV, **67 days avg payout** (fastest), 9 max consec breach.
Lifecycle sim: **$657K net**, 226 days avg extraction.

R by year: 2016:+21.5 | 2017:+19.7 | 2018:+28.1 | 2019:+11.0 | 2020:+15.8 | 2021:+5.5 | 2022:+31.3 | 2023:+24.6 | 2024:+12.6 | 2025:+37.1 | 2026:+4.8

---

### Leg 3: ORB/ES_ASIA-RR1.5

**Tier 2 — Session diversification, exceptionally robust parameter surface**

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia (20:00-20:15 ORB, entry 20:15-03:00, flat 07:00) |
| direction | long only |
| rr | 1.5 |
| tp1_ratio | 0.7 |
| atr_length | 14 |
| stop | ORB 125% |
| min_gap_atr_pct | 0.5% |
| min_stop_points | 3.0 |
| min_tp1_points | 3.0 |
| magnifier | 1s |

| Metric | Full History | Holdout (2025+) |
|--------|-------------|-----------------|
| Trades | 1,454 | 164 |
| Win Rate | 55.1% | — |
| PF | 1.28 | 1.56 |
| Sharpe | 1.900 | 3.47 |
| Net R | +183.3 | +37.6 |
| Max DD | -12.5R | — |
| Calmar | 14.68 | — |
| Neg years | 0 | — |

WF: WFE 0.834, stability 0.893. MC: 89.7% survival. 672/900 grid combos have 0 neg years.
Lifecycle sim: **$598K net**, 321 days avg extraction.

R by year: 2016:+7.5 | 2017:+7.6 | 2018:+1.9 | 2019:+15.3 | 2020:+14.4 | 2021:+9.1 | 2022:+22.1 | 2023:+21.7 | 2024:+18.5 | 2025:+27.4 | 2026:+1.1

Operating rationale after the 2026-05-16 ES Asia-B exact compare: keep active `ORB/ES_ASIA-RR1.5` in `ALPHA_V1` even though ES Asia-B is a good recent-regime challenger. The active ES Asia leg has the stronger full-history exact profile and pairs better with `NQ Asia RR6`: ES Asia's nearer `1.05R` TP1 / `1.5R` TP2 structure balances NQ Asia's farther `1.8R` TP1 / `6R` runner, giving the Asia sleeve more useful payoff variance than replacing ES Asia with another farther-target branch.

DB: `bt-es-asia-cont-long-2016-2026-final-6f79d8`

---

### Leg 4: ORB/ES_NY-RR5

**Tier 2 — Most parameter-stable leg in the portfolio**

Execution note: this `ES_NY ORB` leg was backtested with the hierarchical bar magnifier enabled, so ambiguous fills/exits were resolved using `5m -> 1m -> 1s` execution data rather than 5-minute bars alone.

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | NY (09:30-09:45 ORB, entry 09:45-13:00, flat 15:50) |
| direction | long only |
| rr | 5.0 |
| tp1_ratio | 0.2 |
| atr_length | 7 |
| stop_atr_pct | 5.0% |
| min_gap_atr_pct | 0.25% |
| min_stop_points | 3.0 |
| min_tp1_points | 3.0 |
| DOW exclusion | Thursday |
| magnifier | 1s |

| Metric | Full History | Holdout (2025+) |
|--------|-------------|-----------------|
| Trades | 866 | 101 |
| Win Rate | 61.3% | — |
| PF | 1.42 | 1.55 |
| Sharpe | 2.280 | 2.83 |
| Net R | +142.8 | +18.2 |
| Max DD | -10.4R | — |
| Calmar | 13.74 | — |
| Neg years | 0 | — |

WF: WFE 0.776, stability 0.893. **tp1=0.2 selected in 7/7 WF folds** (extremely stable). MC: 97.3% survival.
Lifecycle sim: **$563K net**, 289 days avg extraction.

R by year: 2016:+15.4 | 2017:+25.9 | 2018:+4.6 | 2019:+11.0 | 2020:+16.6 | 2021:+19.0 | 2022:+15.2 | 2023:+13.8 | 2024:+1.7 | 2025:+17.7 | 2026:+1.8

DB: `bt-es-ny-cont-long-2016-2026-final-650260`

---

### Leg 5: ORB/NQ_NY-R11

**Tier 2 - NY ORB companion leg; risk-split with ES_NY**

Execution note: `NQ NY ORB R11` is now a live-native ALPHA candidate because the exact split replay completed through `2026-03-24`. It should run the split ladder, not the single-target exit: exact split beat single by `+11.6R` with effectively the same drawdown.

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | NY (09:30-09:50 ORB, entry 09:50-12:00, flat 15:30) |
| direction | long only |
| rr | 3.5 |
| tp1_ratio | 0.4 |
| atr_length | 12 |
| stop_atr_pct | 7.0% |
| min_gap_atr_pct | 2.5% |
| DOW exclusion | Friday |
| exit_mode | split |
| magnifier | 1s |

| Metric | Exact Full History | Exact Last 2Y | Exact Last 1Y |
|--------|--------------------|---------------|---------------|
| Trades | 554 | 110 | 49 |
| Win Rate | 52.2% | 49.1% | 44.9% |
| PF | 1.51 | 1.37 | 1.18 |
| Net R | +148.3 | +20.4 | +4.7 |
| Max DD | -6.45R | -6.0R | -6.0R |
| Full TP | 20.9% | 19.1% | 16.3% |
| TP1-BE | 29.2% | 27.3% | 24.5% |
| SL | 47.7% | 50.9% | 55.1% |

Frontend ID: `bt-alpha-v1-exact-split-nq-ny-orb-r11-2016-04-17-to-1a7130`

Operating conclusion: add NQ R11 as the stronger side of the NY ORB pair, but do not stack it at full risk beside a full-size ES_NY. The prior sleeve `NQ R11 $250 / ES_NY $200` is now a sprint challenger; the 2026-05-06 annual payout sim default is `NQ R11 $150 / ES_NY $100` inside the five-leg menu.

### ES_NY ORB Live Retention Review (2026-05-05)

Live `ALPHA_V1-A` currently risks `$400` on `ES_NY`, while the original ALPHA sizing table marked `$300` as the preferred sprint risk and explicitly noted that `$400` reduced first-payout quality (`82.7%` payout, `7` max consecutive breaches). Treat `$400` ES_NY as an aggressive live override, not the canonical ALPHA risk.

Production exact replay still supports keeping the leg in the research portfolio: over `2016-04-17` to `2026-03-24`, exact `ALPHA_V1-A` replay shows `ES_NY ORB` at `506` trades, `+71.13R`, `55.34%` WR, `PF 1.33`, and `-12.00R` DD; last 1y shows `57` trades, `+18.88R`, `61.40%` WR, `PF 1.996`, and `-6.00R` DD. Removing ES_NY from the same exact replay lowers full-history portfolio R from `+445.45R` to `+374.33R`, but only slightly improves full-history DD (`-14.89R` to `-14.42R`).

Live DB sample after the local data cutoff is weak and matches the discretionary concern: from `2026-04-15` through `2026-05-05`, `ES_NY` has `7` closed live trades for `-4.0R` / `-$1,600` at `$400` risk, with `5` full stopouts, `2` TP1-to-breakeven exits, and `0` full TP2 exits. This is not enough sample to invalidate the historical edge, but it confirms the leg's uncomfortable payoff shape: without occasional TP2/EOD extension, two `+0.5R` partials are needed just to offset one `-1R` loss.

**Operating conclusion:** do not permanently delete ES_NY ORB on this sample alone, but do not keep it at `$400` while it is failing live. Demote to `$200-$300` or pause until fresh post-2026-03-24 data can be exact-replayed. If ALPHA_V1 needs a leg removed for simplicity or drawdown relief, ES_NY is the first ORB leg to cut because it is positive but least essential: the portfolio remains profitable without it, and the current live sizing magnifies its worst behavioral mode.

2026-05-06 sizing action: the initial ALPHA operating table demoted ES_NY to `$200` and paired it with added `NQ NY ORB R11` at `$250`; the later recent annual payout sim supersedes that as the default and further reduces the NY ORB sleeve to `NQ R11 $150 / ES_NY $100`.

### NY ORB Wide-Stop Target Sweep (2026-05-05)

Report: `backtesting/learnings/reports/NQ_ES_NY_ORB_WIDE_STOP_TARGET_SWEEP_20260505.md`

Focused sweep across `794` valid configs tested whether **NQ NY ORB R11** and **ES_NY ORB** could use wider NY-session stops while sweeping `rr` and TP1 distance. Structure was held fixed for each candidate; only stop basis/width, `rr`, and TP1 moved.

**Conclusion: do not widen either NY ORB as an ALPHA_V1 replacement.** Zero rows widened the actual median stop by at least `20%` while preserving full-history, last-1y, last-2y, PF, DD, and negative-year quality. NQ R11's least-bad actual widening (`ATR 9%`, about `1.29x` wider) cost roughly `26R-30R` full-history. ES_NY's first meaningful wider families (`ATR 10%+`, `ATR 12%+`, `ORB 50%+`) either damaged recent performance or materially increased DD; `ATR 6%` and `ORB 25%` mostly hit the same `12`-tick median stop because the `3pt` floor dominated.

Operating implication: if NY ORB stopouts are emotionally or live-operationally uncomfortable, solve that with **risk sizing**, not wider stops. ES_NY remains the first ORB leg to risk down or pause when live behavior is bad. NQ NY ORB R11 is now exact-replayed and promoted only as a risk-split companion leg; widening its stop is not the upgrade path. Both tested branches are `deployability=live_native`; exact split replay is complete through `2026-03-24`.

### ALPHA_V1 Exit Target MFE Sweep (2026-05-05)

Report: `backtesting/learnings/reports/ALPHA_V1_EXIT_TARGET_MFE_SWEEP_20260505.md`

Three-pass exit optimization reviewed the active `ALPHA_V1` legs plus **NQ NY ORB R11**: baseline MFE diagnostics, true engine replay of `rr`/TP1-distance-only variants, then Calmar/edge-first ranking versus each leg's baseline. Entries, stops, sessions, DOW filters, ORB windows, and gap filters were held fixed. MFE touch rates were treated as diagnostic only; promotion decisions came from full engine replay. All rows are mechanically `deployability=live_native`, but any live target change still requires exact execution replay.

Key MFE read: low full-TP rate is not automatically a reason to shorten every target. `NQ Asia RR6` only reaches current `6R` on `5.3%` of trades, but TP1-hit trades have p75 MFE `4.47R` and p90 `6.08R`, so the runner is real. `ES_NY RR5` has the clearest "TP2 too far" symptom (`59.8%` TP1-hit, only `10.7%` TP2/TP1 conversion), but the closer-target engine sweep still failed to preserve enough edge.

Promotion read:
- **NQ Asia ORB** is the strongest target-compression candidate: `rr=3.0 / TP1=2.0R` improves full-history R from `+213.5R` to `+217.6R`, keeps PF essentially flat (`1.55` to `1.55`), raises full TP from `5.1%` to `22.7%`, cuts TP1-BE from `14.7%` to `8.6%`, and keeps recent 2y slightly better (`+53.2R` to `+54.8R`). DD worsens only `+0.43R` (`10.2R` to `10.6R`). This is the one target change worth exact replay.
- **NQ Asia exact follow-up (2026-07-02)**: `rr=3.0 / TP1=2.0R` was exact-replayed through the execution engine and stitched into the five-leg payout model in `backtesting/learnings/reports/NQ_ASIA_TIER1_TIER3_EXACT_COMPARE_20260702.md`. It confirmed smoother target expression (`23.3%` full TP, `8.1%` TP1-BE) and slightly higher exact R (`+209.4R` vs `+203.9R` incumbent), but exact DD worsened (`-12.4R` vs `-8.8R`) and portfolio payout at NQ Asia `$400` improved only marginally (`39/19/1` vs `38/20/1`, max breach cluster still `6`). Treat as dry-run/shadow or sizing experiment, not a live replacement under strict promotion criteria.
- **NQ NY HTF-LSI** has a smoother closer-target candidate: `rr=2.0 / TP1=1.4R` raises full TP from `6.2%` to `21.0%` and improves DD (`10.9R` to `10.0R`) while giving up only `-2.6R` full-history. It is plausible for a smoother payout profile, but because it is not an ORB leg and slightly reduces R, treat it as a secondary exact-replay candidate rather than an automatic replacement.
- **ES Asia ORB** does not need compression. `rr=1.25 / TP1=1.0R` raises full TP (`21.7%` to `28.4%`) but loses `-7.9R` and worsens DD. Some farther-target rows improve full R slightly, which argues the current `rr=1.5` is already close enough rather than too far.
- **ES_NY ORB** remains uncomfortable but not fixed by shorter TP2. Best loose closer row `rr=4.0 / TP1=1.0R` raises full TP only to `8.0%` while cutting `-13.6R`, lowering PF (`1.39` to `1.34`), and slightly worsening DD. Keep the current target if the leg stays active; solve live discomfort with risk sizing or gating, not target compression.
- **NQ NY ORB R11** should keep its current `rr=3.5 / TP1=1.4R`. The best loose closer row `rr=3.0 / TP1=1.4R` gives up `-10.6R` and lowers PF (`1.50` to `1.46`) for only a small full-TP lift (`18.1%` to `20.6%`).

### ES/NQ NY ORB Exit Deep-Dive (2026-05-05)

Report: `backtesting/learnings/reports/ES_NQ_NY_ORB_EXIT_DEEPDIVE_20260505.md`

Artifacts: `backtesting/data/results/es_nq_ny_orb_exit_deepdive_20260505/`

Follow-up on **ES_NY ORB** and **NQ NY ORB R11** tested true single-target/full-position TP1, no-BE, delayed-BE, and pre-trade bucket diagnostics. The previous `rr`/TP1 compression pass was too narrow: the missed branch is runner management, not just a closer final TP2.

Best research rows:
- **ES_NY ORB true full-position TP1 at 1R**: `+222.5R`, `PF 1.72`, `-8.0R` DD versus baseline `+126.6R`, `PF 1.39`, `-10.9R` DD. Last-2y improves `+36.9R`; last-1y improves `+16.8R`.
- **ES_NY ORB delayed BE after 1.5R**: `+213.5R`, `PF 1.68`, `-9.3R` DD. This is strong but changes the risk path because some partial winners become `tp1_sl` givebacks.
- **NQ NY ORB R11 full-position TP1 at 1.4R**: `+155.2R`, `PF 1.61`, `-6.4R` DD versus baseline `+129.4R`, `PF 1.50`, `-6.0R` DD.
- **NQ NY ORB R11 delayed BE after 1.5R**: `+160.7R`, `PF 1.63`, `-6.0R` DD, but recent-year lift is less clean than ES.

Implementation update: `exit_mode=single_target` is now supported in research and live execution, with `tp1_ratio=1.0` required so `rr` is the sole target. The single-target rows above are now `deployability=live_native` candidates pending exact replay. Delayed-BE and no-BE rows remain `research_only`. The existing `wide_stop_full_exit_at_tp1` path is still not equivalent; a quick engine-native sanity check with a tiny threshold produced only `+51.4R`/`PF 1.16`/`-14.5R` DD for ES and `+81.8R`/`PF 1.32`/`-7.2R` DD for NQ.

Operating conclusion: before spending more effort optimizing **NQ Asia ORB** or **NQ NY HTF-LSI** exits, exact-replay the proper `exit_mode=single_target` path for ES_NY and NQ R11. Pre-trade buckets did not reveal an obvious negative skip slice; the weak buckets were still positive, so gating is secondary to exit-policy parity.

### ALPHA_V1 Native Single-Target Sweep (2026-05-06)

Report: `backtesting/learnings/reports/ALPHA_V1_SINGLE_TARGET_SWEEP_20260506.md`

Artifacts: `backtesting/data/results/alpha_v1_single_target_sweep_20260506/`

Follow-up tested the now-native `exit_mode=single_target` path across all five reviewed legs: active `NQ NY HTF-LSI`, `NQ Asia ORB`, `ES Asia ORB`, `ES_NY ORB`, and conditional `NQ NY ORB R11`. For each leg, the current split ladder was compared against a full-position single target at the current TP1 distance, then a focused RR-only single-target sweep. All entries, stops, sessions, DOW filters, ORB windows, gap filters, and magnifier settings were held fixed.

Best operating rows:
- **ES_NY ORB**: `single_target 1.0R` is a material upgrade: current split `+126.6R / PF 1.39 / -10.9R DD / 6.4% target`; single target `+186.4R / PF 1.57 / -8.0R DD / 59.8% target`. Exact replay this before any live change.
- **NQ NY ORB R11**: `single_target 1.4R` was the research-engine preferred R11 exit: current split `+129.4R / PF 1.50 / -6.0R DD / 18.1% target`; single target `+149.2R / PF 1.58 / -6.4R DD / 52.4% target`. This read was superseded by exact replay, where the split ladder won on edge.
- **ES Asia ORB**: native single target changes the earlier split-compression read. `single_target 1.25R` improved to `+173.7R / PF 1.32 / -13.6R DD / 32.2% target` versus current split `+145.9R / PF 1.28 / -12.3R DD / 21.7% target`. This is promising but a tradeoff, not automatic: it adds `+27.9R` and PF, but gives back `+1.35R` DD.
- **NQ Asia ORB**: keep split structure. Single target at current TP1 (`1.8R`) loses `-33.5R` and adds a negative year. Best Calmar-ish single row (`2.0R`) still loses `-10.4R`, lowers PF, and slightly worsens DD. High single targets can raise raw R (`6.0R -> +274.0R`) but DD expands to `-15.6R` and Calmar falls, so this is not a cleaner replacement.
- **NQ NY HTF-LSI**: keep split structure. Single at current TP1 (`1.4R`) loses `-5.4R`, adds a negative year, and weakens recent 1y. The best smoother row (`1.5R`) lowers DD but loses `-9.0R` and PF; treat it as inferior unless a future prop-sim specifically values lower DD over edge.

Deployment label: single-target rows are mechanically `live_native` because `exit_mode=single_target` is now supported in research and execution with `tp1_ratio=1.0`; any selected row still has `exact_replay_required=yes_before_live_change`.

### ALPHA_V1 Single-Target Exact Replay + Phase-One Sizing (2026-05-06)

Report: `backtesting/learnings/reports/ALPHA_V1_SINGLE_TARGET_EXACT_PROP_20260506.md`

Artifacts: `backtesting/data/results/alpha_v1_single_target_exact_prop_20260506/`

Exact replay completed for the three native single-target candidates using temporary live-engine profiles only; `execution/config/exec_configs.json` was not edited. Funded model was the standard phase-one account: `$50k` start, `$2k` EOD trailing DD capped at `$50k`, first payout at `$52.5k`, `$500` first withdrawal, `$100` account/reset cost, and account starts every `14` calendar days.

Exact replay supersedes the optimistic research sweep for promotion decisions:
- **ES NY ORB single 1.0R** exact replay: `849` trades, `+101.6R`, `PF 1.28`, `55.8%` WR, `-12.2R` DD, `55.0%` target. This is a large haircut versus research (`+186.4R`, `PF 1.57`, `-8.0R` DD). Treat the single-target ES upgrade as weaker than expected; do not increase ES NY risk based on the research row alone.
- **NQ NY ORB R11 single 1.4R** exact replay: `554` trades, `+136.7R`, `PF 1.47`, `52.2%` WR, `-6.4R` DD, `51.6%` target. This is close enough to the research thesis to remain the cleaner NY ORB promotion candidate.
- **ES Asia ORB single 1.25R** exact replay: `1,428` trades, `+219.6R`, `PF 1.34`, `52.0%` WR, `-15.0R` DD, `47.6%` target. Exact replay is stronger than research on R/PF but carries a bigger DD footprint than the split baseline.

Phase-one sizing read:
- **Practical sprint sizing**: ES NY `$175` (`79.2%` payout / `9.2%` breach / avg payout `403d`), NQ R11 `$325` (`88.5%` / `6.5%` / `187d`), ES Asia `$200` (`90.8%` / `5.4%` / `189d`).
- **Conservative standalone sizing**: ES NY `$150` (`83.8%` payout / `0.0%` breach / `496d`), NQ R11 `$300` (`92.7%` / `0.0%` / `209d`), ES Asia `$125` (`94.6%` / `0.0%` / `295d`).

Operating conclusion from this pass alone: **NQ R11 single 1.4R** and **ES Asia single 1.25R** were the serious candidates for dry-run sizing review, while ES NY single 1.0R was positive but no longer looked like the clean replacement implied by research. This read is superseded for exit-policy selection by the next exact split-vs-single comparison, which showed NQ R11's split ladder still has better exact edge.

### ALPHA_V1 Exact Single vs Split Target Comparison (2026-05-06)

Report: `backtesting/learnings/reports/ALPHA_V1_SINGLE_VS_SPLIT_EXACT_COMPARE_20260506.md`

Artifacts: `backtesting/data/results/alpha_v1_single_vs_split_exact_compare_20260506/`

This follow-up exact-replayed the **split target counterparts** as single-leg live-engine profiles, then compared them to the cached exact single-target runs over the same `2016-04-17` to `2026-03-24` window. Split counterparts used the same session, stop, gap, DOW, and flat settings as the single-target candidates; only `exit_mode`, `rr`, and `tp1_ratio` changed back to the split ladder.

Full-window exact comparison:
- **ES NY ORB**: single `1.0R` produced `+101.6R / PF 1.28 / -12.2R DD / 55.0% target`; split `rr 5 / tp1 0.2` produced `+145.8R / PF 1.40 / -12.0R DD / 10.1% full target / 37.7% TP1-BE`. Exact verdict: **keep split if this leg stays active**. Single target feels cleaner but gives up `-44.2R` and PF.
- **NQ NY ORB R11**: single `1.4R` produced `+136.7R / PF 1.47 / -6.4R DD / 51.6% target`; split `rr 3.5 / tp1 0.4` produced `+148.3R / PF 1.51 / -6.45R DD / 20.9% full target / 29.2% TP1-BE`. Exact verdict: **keep split** unless smoother all-or-nothing payouts are explicitly worth giving up `-11.6R`.
- **ES Asia ORB**: single `1.25R` produced `+219.6R / PF 1.34 / -15.0R DD / 47.6% target`; split `rr 1.5 / tp1 0.7` produced `+181.4R / PF 1.30 / -12.5R DD / 35.4% full target / 14.2% TP1-BE`. Exact verdict: **single target is the only true R/PF upgrade**, but it expands DD by `+2.5R`; size down if promoted.

Operating conclusion: do **not** promote ES NY or NQ R11 single-target exits on edge grounds. ES NY and NQ R11 split ladders remain the better exact-engine structures despite the awkward TP1-BE profile. ES Asia single `1.25R` remains a valid challenger if accepting the DD tradeoff. All rows are `deployability=live_native`; split exact replay is complete through `2026-03-24`.

### ALPHA_V1 ES_NY Runner-Trail Sweep (2026-05-11)

Report: `backtesting/learnings/reports/ALPHA_V1_ES_NY_RUNNER_TRAIL_SWEEP_20260511.md`

Artifacts: `backtesting/data/results/alpha_v1_es_ny_runner_trail_sweep_20260511/`

This tested the active **ES_NY ORB** split ladder with post-TP1 runner trailing while holding entries, stops, sessions, DOW filter, `rr=5.0`, `tp1_ratio=0.2`, and the `5m -> 1m -> 1s` magnifier fixed. Three runner-management families were swept: stepped R locks, continuous high-water trailing by initial risk, and continuous high-water trailing by daily ATR percent.

Full-history result: the current no-trail split ladder still wins as the all-weather default (`846` trades, `+126.6R`, `PF 1.39`, `-10.9R` DD, Calmar `11.65`). The best full-history trailing challenger, `atr_gap_5pct`, reduced DD to `-8.9R` but gave up `-27.4R` and PF (`1.30`). The best recent challenger, `risk_gap_0p75r`, confirmed the live discomfort thesis by improving last-2Y from `+21.4R / -9.7R` to `+25.0R / -7.6R` and 2025+ from `+19.5R / -9.6R` to `+25.0R / -7.6R`, but full-history fell to `+104.8R` and PF `1.32`.

Operating conclusion: runner trailing is a valid research branch, not a live replacement yet. If optimizing for recent ES_NY giveback specifically, `risk_gap_0p75r` is the first exact-replay candidate after execution support exists. If optimizing for smoother full-history DD, `atr_gap_5pct` is the only serious branch. Do not replace the current ES_NY split ladder on this sweep alone because the baseline remains better on full-history R/PF/Calmar. All trailing rows are `deployability=research_only`; exact/live execution support plus exact replay are required before any promotion.

Exact follow-up: `backtesting/learnings/reports/ALPHA_V1_ES_NY_RUNNER_TRAIL_EXACT_20260511.md`

The exact/live engine now supports post-TP1 runner trails and broker-side runner-stop replacement. The two best simulator candidates were replayed through the exact ES_NY live engine over `2016-04-17` to `2026-03-24`.

- **Baseline exact remains production incumbent**: `849` trades, `+145.8R`, `PF 1.215`, `-12.0R` DD, Calmar `12.15`; 2025+ `+18.0R / -9.0R`.
- **`risk_gap_0p75r` exact rejected**: `+83.2R`, `PF 1.057`, `-15.4R` DD, Calmar `5.40`; 2025+ only `+8.1R`. It created `458` positive runner-stop exits but nearly eliminated full TP2s (`2` vs baseline `86`), so it solved giveback by over-cutting winners.
- **`atr_gap_5pct` exact rejected as replacement**: `+103.1R`, `PF 1.107`, `-12.1R` DD, Calmar `8.51`; 2025+ `+13.3R`. It is less damaging than risk-gap but still gives up too much R/PF without a material DD improvement.

Promotion decision: **do not move either runner-trail candidate into ALPHA_V1-A production**. Keep the current ES_NY split ladder. Trail variants can remain paper/shadow research only if we want to diagnose live psychology/giveback, but exact evidence says the no-trail 5R runner is still the better trading system.

### NQ/ES NY ORB Pair Phase-One Risk Sizing (2026-05-05)

Report: `backtesting/learnings/reports/NQ_ES_NY_ORB_PAIR_PHASE_ONE_RISK_SWEEP_20260505.md`

The frozen ORB-only NY pair was evaluated with **NQ NY ORB R11** (`ATR 7% / rr 3.5 / tp1 0.4`, long, no Friday) plus current **ES_NY ORB** (`ATR 5% / rr 5.0 / tp1 0.2`, long, no Thursday). The sweep varied only per-leg dollar risk from `$100` to `$650` by `$50`; no signal, stop, target, DOW, or session parameters were optimized. Funded model: `$50k` account, `$2k` EOD trailing DD capped at `$50k`, first payout at `$52.5k`, `$500` first withdrawal, `$100` challenge/reset fee, starts every `14` calendar days. Holdout opened once at `2025-01-01`.

Frozen stats over `2016-04-17` to `2026-03-24`: NQ R11 produced `552` fills, `+129.4R`, `PF 1.50`, `-6.0R` DD, `53.3%` WR, `18.1%` full TP, `33.0%` TP1-BE, `46.4%` SL. ES_NY produced `846` fills, `+126.6R`, `PF 1.39`, `-10.9R` DD, `61.0%` WR, only `6.4%` full TP, `46.9%` TP1-BE, `38.2%` SL.

Sizing read:
- **Conservative / lowest-breach**: `NQ $150 / ES $150` -> pre-holdout payout `83.3%`, breach `0.0%`, EV `$316.67`, avg payout `198d`; holdout payout `75.0%`, breach `0.0%`, EV `$275.00`, avg payout `186d`. This is robust but slow.
- **Balanced ES-reduced default**: `NQ $250 / ES $200` -> pre-holdout payout `78.1%`, breach `18.9%`, EV `$290.35`, avg payout `116d`; holdout payout `81.2%`, breach `0.0%`, EV `$306.25`, avg payout `135d`. This is the preferred first pass if adding NQ R11 while reducing ES_NY.
- **NQ-led sprint**: `NQ $350 / ES $150` -> pre-holdout payout `73.2%`, breach `23.7%`, EV `$275.00`, avg payout `100d`; holdout payout `81.2%`, breach `12.5%`, EV `$306.25`, avg payout `123d`, max consecutive holdout breaches `4`. This is the faster branch, but not the default.
- **Too hot reference**: `NQ $400 / ES $400` -> pre-holdout breach `34.2%`, holdout breach `34.4%`; not recommended as the default NY ORB sleeve risk despite faster payouts.

Operating conclusion: if adding NQ R11 beside ES_NY, run the pair as a deliberately risk-split NY ORB sleeve. Use `NQ $150 / ES $150` for conservative paper/live probation; use `NQ $250 / ES $200` as the balanced default; use `NQ $350 / ES $150` only if accepting a faster, breach-tolerant phase-one sprint profile. Because ES_NY has weak post-cutoff live behavior at `$400`, do not promote an ES-heavy live increase without fresh exact replay through post-`2026-03-24` data. Both legs are `deployability=live_native`; NQ R11 exact split replay is complete through `2026-03-24`.

### ALPHA_V1 Recent Annual Payout Simulation (2026-05-06)

Report: `backtesting/learnings/reports/ALPHA_V1_RECENT_PAYOUT_SIM_20260506.md`

Artifacts: `backtesting/data/results/alpha_v1_recent_payout_sim_20260506/`

This stitched cached exact trade streams for the four active `ALPHA_V1-A` legs plus exact split **NQ NY ORB R11**, then simulated phase-one accounts in calendar `2024`, `2025`, and partial `2026_YTD` through `2026-03-24`. Account model matched ALPHA docs: `$50k`, `$2k` EOD trailing DD capped at `$50k`, payout trigger `$52.5k`, first payout `$500`, account cost `$150`, starts every `14` days. Payout and breach rates are resolved-account rates; open accounts are tracked separately.

Key result: payout speed is not the blocker. Even low-risk rows reached first payout inside the desired `2-3 month` window. Breach clustering is the blocker.

| Risk Menu | 2024 | 2025 | 2026_YTD | Read |
|-----------|------|------|----------|------|
| `HTF 300 / NQ Asia 300 / ES Asia 150 / R11 150 / ES NY 100` | `91.3%` resolved payout, `8.7%` breach, `56.7d` avg payout | `100%` resolved payout, `0%` breach, `47.3d` avg payout | `2` payout / `0` breach / `4` open | Best fast-safe default |
| `HTF 300 / NQ Asia 300 / ES Asia 200 / R11 250 / ES NY 200` | `82.6%` payout, `17.4%` breach, `47.2d` | `84.6%` payout, `15.4%` breach, `27.7d` | `2` payout / `3` breach / `1` open | Fast but too much 2026 NY stress |
| `HTF 500 / NQ Asia 400 / ES Asia 150 / R11 250 / ES NY 300` | `87.0%` payout, `13.0%` breach, `32.8d` | `84.6%` payout, `15.4%` breach, `21.2d` | `3` payout / `2` breach / `1` open | Very fast, but breach is no longer minimized |

Operating conclusion: the breach-controlled default remains `HTF $300 / NQ Asia $300 / ES Asia $150 / NQ R11 $150 / ES NY $100`, but the live execution profile is intentionally moving to the aggressive sprint menu `HTF $500 / NQ Asia $400 / ES Asia $150 / NQ R11 $250 / ES NY $300` for faster payout velocity. This accepts the known higher breach rate and should be monitored closely against partial-2026 NY stress.

### ALPHA_V1 Fee-Aware Exact Profile Payout Rerun (2026-05-07)

Artifacts: `backtesting/data/results/alpha_v1_payout_with_fees_20260507/`

This reran the three operating menus through the current live exact engine using the new fee model: MNQ/MES `$0.575` per contract per side, current `ALPHA_V1-A` session definitions, current `NQ_NY` ORB leg, per-menu `risk_usd`, per-menu `max_single_risk_usd = 1.5 * risk_usd`, and the single-contract TP1 full-exit rule. Replay window was `2023-01-01` to `2026-03-24`, with 2023 used as warmup and account starts scored only for `2024`, `2025`, and `2026_YTD`.

| Risk Menu | 2024 | 2025 | 2026_YTD | Read |
|-----------|------|------|----------|------|
| `HTF 300 / NQ Asia 300 / ES Asia 150 / R11 150 / ES NY 100` | `79.0%` payout, `21.1%` breach, `77.2d` avg payout | `76.0%` payout, `24.0%` breach, `41.2d`, `6` MCBch | `2` payout / `0` breach / `4` open | Old "fast-safe" row is no longer fast-safe after fees |
| `HTF 300 / NQ Asia 300 / ES Asia 200 / R11 250 / ES NY 200` | `72.7%` payout, `27.3%` breach, `58.4d` | `80.8%` payout, `19.2%` breach, `32.7d`, `4` MCBch | `2` payout / `0` breach / `4` open | Best tested compromise if breach clustering matters |
| `HTF 500 / NQ Asia 400 / ES Asia 150 / R11 250 / ES NY 300` | `82.6%` payout, `17.4%` breach, `41.1d` | `73.1%` payout, `26.9%` breach, `20.8d`, `7` MCBch | `3` payout / `0` breach / `3` open | Fastest, highest EV/start, but worst 2025 breach clustering |

Operating conclusion: fee-aware exact sizing changes the read materially. Payout speed is still acceptable, but breach rate is now the primary blocker across all three menus. The aggressive sprint menu can remain a deliberate speed test, but it should not be described as breach-minimized; the balanced challenger is the cleaner compromise among the three tested rows because it avoids the aggressive row's `7` consecutive-breach cluster.

### ALPHA_V1 Next-Step Packet: Asia Geometry, R11 Gate, Hunter Sidecar (2026-05-16)

Report: `backtesting/learnings/reports/ALPHA_V1_NEXT_STEPS_20260516.md`

Artifacts: `backtesting/data/results/alpha_v1_next_steps_20260516/`

This packet ran the three follow-ups from the 2-8 candidate review against cached exact/current fee-aware streams. It did not search new signal parameters.

1. **Asia sleeve payoff geometry**: keep active `ES Asia RR1.5` in the portfolio. The active sleeve `NQ Asia + active ES Asia` produced `+239.2R`, DD `-28.7R`, Sharpe `0.99`, and weighted net `$70.4k` at current aggressive Asia risks (`NQ Asia $400 / ES Asia $150`). Replacing ES with Asia-B original reduced sleeve R to `+207.8R` and raised NQ/ES daily correlation from `0.25` to `0.39`. Asia-B still looks stronger in 2025-only account cohorts, but the full-history and payoff-geometry read supports the existing near-target ES / far-runner NQ pairing.
2. **NQ R11 15m structure + VWAP gate**: the only gate worth a true replay is `any2of3_vwap_d10`. Using an entry-minus-one-5m proxy, it kept `86.6%` of full-history trades and matched baseline net (`+110.8R` fee-aware net R), while improving 2025+ from `+9.4R` to `+10.7R`, last-1y from `+3.5R` to `+7.9R`, and DD from `-6.1R` to `-5.1R` in recent windows. Strict `HH/HL-2` looked good in last-1y but gutted full-history R. Deployability is `post_filter_only` until rerun inside the engine at the true signal bar.
3. **Hunter 0.25x sidecar**: this is the strongest next candidate. On the current fee-aware aggressive sprint profile, adding the 10y-safe Hunter branch (`ema14_tol0_distnone__withTue__1055__rej100__stress`) improved 2024 from `82.6%` payout / `17.4%` breach to `88.5%` / `11.5%`, and 2025 from `73.1%` / `26.9%` to `84.6%` / `15.4%`. Max consecutive 2025 breaches improved from `7` to `4`, portfolio net rose by about `$20.7k`, DD stayed similar (`-$4.10k` vs `-$4.04k`), and daily corr to ALPHA was only `0.03`. The shadow profile below supersedes the prior `research_only` status for dry-run purposes.

Operating conclusion: no change to active ES Asia. Prioritize Hunter 0.25x as the next shadow/paper add-on candidate. The R11 structure/VWAP replay below closes candidate #7 as an ALPHA replacement path for now.

### Hunter 0.25x Shadow Profile (2026-05-16)

Report: `backtesting/learnings/reports/ALPHA_V1_HUNTER_025_SHADOW_SPEC_20260516.md`

Execution profile added: `ALPHA_V1-HUNTER-SAFE-025-SHADOW` in `execution/config/exec_configs.json`.

This converts the Hunter 10y-safe `0.25x` sidecar from `research_only` into a practical no-webhook dry-run profile. It uses existing execution-native `hunter_orb` support and the existing `H_ORB_SAFE` branch, with only the profile-level risk scaled down: `risk_usd=$87.50`, `max_single_risk_usd=$87.50`, `max_contracts=5`, `webhooks=[]`. Deployability for dry-run/shadow is now `live_native`; exact replay/log parity is still required before any webhook promotion.

Shadow acceptance checks: startup must show `DRY-RUN (no webhooks)`, engine creation must show `H_ORB_SAFE` with the three stress regime gates, and live logs must confirm `REGIME_GATE_PASSED` / blocking-gate behavior plus Hunter setup, EMA, re-entry, and sizing behavior before considering promotion.

### R11 Structure/VWAP Engine Replay (2026-05-16)

Report: `backtesting/learnings/reports/ALPHA_V1_R11_STRUCTURE_GATE_ENGINE_REPLAY_20260516.md`

Artifacts: `backtesting/data/results/alpha_v1_r11_structure_gate_engine_replay_20260516/`

This reran the R11 structure/VWAP idea as a true research-engine candidate gate at the ORB signal bar, before one-trade-per-day selection. That removed the entry-minus-one-5m proxy caveat from the next-step packet.

Result: candidate #7 is **not ALPHA-grade as a replacement gate**. Baseline research-engine R11 printed `552` trades, `+90.0R` net after MNQ fees, PF `1.33`, and `-8.4R` DD. The proxy lead `any2of3_vwap_d10` kept `497` trades but fell to `+82.1R` (`-7.8R`), PF `1.33`, and `-7.9R` DD. It still improved recent windows (`2025+` `+11.6R` vs `+7.0R`; last-1y `+11.9R` vs `+5.1R`), but the full-history R haircut is not acceptable for a core ALPHA leg. Strict `hh_hl_2_vwap` collapsed to `+21.3R` and `-14.6R` DD.

Deployability: baseline R11 remains `live_native`; structure-gated variants are `post_filter_only` because production execution does not yet compute this 15m structure/VWAP context before arming. Do not promote the gate. Keep it only as a discretionary/recent-regime context note unless a separate low-risk specialist sleeve is intentionally designed.

### ALPHA_V1 ORB Range Gate Sweep (2026-05-29)

Report: `backtesting/learnings/reports/ALPHA_V1_ORB_RANGE_GATE_SWEEP_20260529.md`

Artifacts: `backtesting/data/results/alpha_v1_orb_range_gate_sweep_20260529/`

Broad post-filter attribution pass over the active ALPHA ORB legs asked whether an `orb_mid` style gate could skip sessions where the opening range is unusually small or unusually large. The sweep annotated `NQ Asia ORB`, `ES Asia ORB`, `ES_NY ORB`, and `NQ NY ORB R11` with a causal 60-session ORB range percentile available after ORB completion, then swept percentile and ORB/ATR bands against the active exact stream, split-exact counterparts, and the fee-aware aggressive sprint stream.

Primary active exact sleeve baseline over `2016-04-17` to `2026-03-24`: `2,816` ORB trades, `+523.5R`, `0.186R/trade`, `PF 1.397`, `-19.87R` DD.

Key read:
- **There is quality concentration, but not a clean hard skip rule.** Sleeve-wide `40%-67%` ORB percentile kept only `759` trades (`27%`) but improved average trade from `0.186R` to `0.232R`, PF from `1.397` to `1.503`, and DD from `-19.87R` to `-10.78R`. It gave up `-347.2R` of total edge, so it is better framed as a risk throttle or specialist sleeve idea than a full replacement.
- **Do not blindly skip all large ORBs.** The `80%-100%` sleeve bucket still produced `+149.7R`, `0.232R/trade`, `PF 1.522`; ES_NY, NQ Asia, and NQ R11 each had strong very-large ORB buckets. The weak large-zone pattern is mostly the `67%-80%` bucket, not the entire high tail.
- **ES Asia is the cleanest candidate for a true gate.** Its `0%-20%` bucket was weak (`+11.9R`, `0.060R/trade`, `PF 1.13`) and `67%-100%` was also below baseline (`0.105R/trade`, `PF 1.24`). The `20%-67%` band kept `528` trades and improved PF/DD (`PF 1.365`, `-7.20R` DD versus baseline `PF 1.281`, `-12.23R`), though it still cut total R materially.
- **ES_NY is not an `orb_mid` pure play.** `30%-60%` was excellent (`0.269R/trade`, `PF 1.74`), but the `80%-100%` bucket was also excellent (`0.309R/trade`, `PF 1.80`). A simple "not high" filter would remove real winners.
- **NQ Asia and NQ R11 do not support a small-plus-large skip.** NQ Asia had good `0%-30%`, `40%-67%`, and `80%-100%` bands with a weak `67%-80%` pocket. NQ R11's tiny `0%-30%` zone underperformed, while `50%-67%` and `75%-100%` were both strong.

Operating conclusion: keep this `post_filter_only` / `research_only`. The only follow-up that looks structurally worth a true engine replay is an **ES Asia ORB-size gate** around `20%-67%`, or a portfolio-level **risk throttle** that sizes up the `40%-67%` band instead of deleting everything outside it. Percentile gates should be implemented at the ORB completion/signal bar and then exact-replayed plus rerun through the fee-aware prop model before any ALPHA_V1 promotion.

---

## ORB Mechanic Transfer Test — Hunter Wide-Stop + Re-Entry

2026-05-02 report: `backtesting/learnings/reports/ALPHA_V1_ORB_WIDESTOP_REENTRY_TRANSFER_20260502.md`

Artifacts: `backtesting/data/results/alpha_v1_orb_widestop_reentry_transfer_20260502/`

Scope was the three active ALPHA_V1 ORB legs only: `NQ Asia ORB`, `ES Asia ORB`, `ES NY ORB`. The HTF-LSI leg was excluded because the hypothesis was whether Hunter ORB mechanics transfer to ORB continuation legs.

**Conclusion: one-loss/nonpositive re-entry transfers; wide-stop TP compression does not.**

Combined ORB sleeve, `2016-04-17` to `2026-03-24`:

| Variant | Fills | Net R | PF | Sharpe | DD | Neg years | Read |
|---------|------:|------:|---:|-------:|---:|----------:|------|
| Baseline `cap1` | 2,989 | +486.9R | 1.40 | 1.73 | -21.2R | 0 | Current one-trade-per-session ORB sleeve |
| `cap2_after_nonpositive` / `after_sl` | 3,224 | +545.6R | 1.41 | 1.93 | -22.0R | 0 | Best clean Hunter-style transfer |
| `cap2_any` | 3,698 | +568.5R | 1.37 | 1.92 | -23.2R | 0 | Highest R, but more flow and worse DD/PF |
| Best wide-stop only | 2,989 | +482.3R | 1.39 | — | -21.2R | 0 | Still loses R; no meaningful DD benefit |

Recent windows:
- `cap2_after_nonpositive` adds `+25.7R` in 2024+, `+6.6R` in 2025+, and `+1.7R` in the last 1y, with small DD giveback.
- `cap2_any` adds more R (`+34.7R` in 2024+, `+13.6R` in 2025+, `+11.7R` last 1y) but worsens recent daily DD by about `-2.7R`.
- Every combined wide-stop-only variant loses net R versus baseline. Best full-history wide-only is still `-4.7R`; median wide-only is about `-32.9R`. Do not port Hunter's wide-stop 1R cap to ALPHA_V1 ORB as a sleeve rule.

Per-leg read:
- `NQ Asia` and `ES Asia` both favor `cap2_after_nonpositive` / `after_sl` over target compression.
- `ES NY` likes extra flow most; its best full-history row is a cap2-any + light wide-stop combo, but it introduces a negative year and needs prop/risk validation before promotion.

2026-05-03 follow-up report: `backtesting/learnings/reports/ALPHA_V1_ORB_GAP_CANDLE_STOP_COMPARE_20260503.md`

Tested replacing the current ATR/ORB-distance stop logic on the same three ORB legs with an FVG impulse-candle structural stop: long stop = `low[signal_bar - 1] - 1pt`, short stop = `high[signal_bar - 1] + 1pt`, while leaving the engine's hard floors active. **Conclusion: NO-GO as a sleeve rule.** Combined 10yr fell from `+486.9R / -21.2R DD` to `+375.5R / -28.8R DD`; funded first-payout outcomes fell from `186` payouts / `70` breaches to `170` payouts / `85` breaches. The damage was largest in `ES NY` (`-62.6R`) and `NQ Asia` (`-35.0R`). The only favorable read was small 2026 YTD noise (`+1.6R`, DD `+0.9R`) and is not enough to offset the long-run and 2025 degradation.

2026-05-04 follow-up report: `backtesting/learnings/reports/ALPHA_V1_ASIA_ORB_FULL_TP1_WIDESTOP_SWEEP_20260504.md`

Tested a narrower wide-stop exit rule on the two Asia ORB legs only: when realized stop/risk points are above `large_sl_threshold_points`, exit the full trade at the normal TP1 level instead of partialing at TP1 and targeting TP2. **Conclusion: NO-GO / tiny research-only NQ sidecar at best.** NQ Asia's best full-history threshold was `35` points for only `+3.82R` with no DD change. ES Asia's best threshold was `15` points and still lost `-0.18R`. The best combined NQ+ES Asia row was simply `nq_sl35p0__es_baseline`, adding `+3.82R` with no DD improvement; 2025+ best combined lift was only `+1.42R`. This does not justify live/exact replay implementation unless paired with a broader exit-management project.

Completed follow-up: the promotion packet below tests `cap2_after_nonpositive` on `NQ Asia ORB` and `ES Asia ORB` inside the full active ALPHA_V1 stack.

### ORB One-Loss Reentry Promotion Packet (2026-05-02)

Report: `backtesting/learnings/reports/ALPHA_V1_ORB_REENTRY_PROMOTION_20260502.md`

Artifacts: `backtesting/data/results/alpha_v1_orb_reentry_promotion_20260502/`

Candidate: `NQ Asia ORB` and `ES Asia ORB` move to `orb_trade_max_per_session=2` with `orb_reentry_policy=after_nonpositive_first`; `ES NY ORB` and `NQ NY HTF-LSI` stay unchanged. The test used the active four-leg ALPHA_V1 lineup and current sprint risk sizing: HTF-LSI `$300`, NQ Asia `$300`, ES Asia `$200`, ES NY `$300`.

**Read: research pass, execution build required before dry-run.** Full-history combined R improves, recent windows improve, and 2025 remains strong; however, current-dollar funded cohorts are mixed across the entire 10-year history and the generic execution `ORBEngine` does not yet support the same cap2/reentry semantics.

Combined active portfolio, `2016-04-17` to `2026-03-24`:

| Window | Baseline | Candidate | Delta | DD change | Current-$ delta |
|--------|---------:|----------:|------:|----------:|----------------:|
| Full | +579.5R | +625.6R | +46.1R | -0.9R | +$11.6k |
| 2024+ | +159.0R | +174.0R | +15.0R | +0.5R | +$4.0k |
| 2025+ | +106.5R | +113.1R | +6.6R | +1.3R | +$1.6k |
| Last 1y | +91.4R | +98.1R | +6.7R | +1.3R | +$1.6k |
| Calendar 2025 | +97.5R | +103.1R | +5.6R | +1.3R | +$1.4k |

Per-leg contribution on full history:
- `NQ Asia ORB`: `+23.8R` / `+$7.1k`, DD roughly flat (`-0.1R`).
- `ES Asia ORB`: `+22.3R` / `+$4.5k`, DD slightly better (`+0.6R`).
- `ES NY ORB` and `NQ NY HTF-LSI`: unchanged by design.

Funded first-payout model at current risk sizing:

| Window | Baseline Pay% | Candidate Pay% | Baseline breaches | Candidate breaches | Read |
|--------|--------------:|---------------:|------------------:|-------------------:|------|
| Full | 77.2% | 74.1% | 55 | 64 | Mixed: more R, but slightly more historical account stress |
| 2024+ | 81.4% | 79.7% | 7 | 8 | Slightly worse |
| 2025+ | 84.4% | 84.4% | 2 | 2 | Same payout rate, faster median payout |
| Last 1y | 74.1% | 77.8% | 3 | 2 | Better recent cohort behavior |

Timing-overlap check: candidate generated `134` reentry fills for `+46.1R` / `+$11.6k`; other legs were negative on `31.3%` of reentry days versus `46.2%` of all candidate trading days. The reentry trades do not appear to disproportionately cluster with other-leg loss days, though the worst overlap days still include multi-leg drawdowns.

Execution action: do not flip this live from config alone. Add generic `ORBEngine` support for `orb_trade_max_per_session` and `orb_reentry_policy=after_nonpositive_first`, wire checkpoint/API/exact-replay fields, then run dry-mode parity before promotion.

---

## Dry Run — Historical Reference

### Legacy LSI/NQ_NY-RR2
#### NQ NY Legacy LSI RR2/TP0.5 + Thu-only + Regime Gate

**Archived legacy alternate. No longer the active `ALPHA_V1` swap candidate after the HTF-LSI lag24 promotion.**

The research variant has better per-trade quality on full history (higher WR, PF, Sharpe, DSR) and dramatically shallower holdout DD (-2.6R vs -5.4R). But FAST generated more raw holdout R (+16.2 vs +11.2) and higher holdout Sharpe (5.12 vs 4.27). The regime gate is a fitted parameter that needs live confirmation.

| Param | Value |
|-------|-------|
| strategy | lsi |
| entry_mode | fvg_limit |
| session | NY (09:35-15:30, flat 15:50) |
| direction | long only |
| rr | 2.0 |
| tp1_ratio | 0.5 |
| atr_length | 14 |
| min_gap_atr_pct | 5.0% |
| lsi_n_left | 8 |
| lsi_n_right | 60 |
| fvg_window | 20 / 5 |
| DOW exclusion | Thu only |
| regime gate | skip bull_medium_vol + sideways_medium_vol |
| magnifier | 1s |

| Metric | Full History | Holdout (2025-04+) |
|--------|-------------|-------------------|
| Trades | 588 | 45 |
| Win Rate | 61.1% | 66.7% |
| PF | 1.70 | 1.92 |
| Sharpe | 3.646 | 4.268 |
| Net R | +126.4 | +11.2 |
| Max DD | -7.6R | -2.6R |
| Calmar | 16.72 | 4.33 |
| Neg years | 0 | — |

WF OOS: 311 trades, Sharpe 3.38, WFE 0.766, stability 0.833.
PSR: 0.9999, DSR: **0.709** (survives multiple-testing deflation).
MC: 99.3% survival, 0.7% ruin.
Holdout payout sim: 17 payouts, 0 breaches, 9 open = **100% success rate**.

**OOS verification passed** (2026-04-03):
- 45 holdout trades >= 30 threshold
- Sharpe 4.268 >= 1.0 threshold
- PF 1.92 >= 1.0 threshold

**Holdout comparison vs FAST:**

| Metric | RR2 Gated | FAST V1.1 | Better for... |
|--------|-----------|-----------|---------------|
| Net R | +11.2 | **+16.2** | FAST wins raw R |
| Sharpe | 4.268 | **5.122** | FAST wins quality |
| Max DD | **-2.6R** | -5.4R | RR2 wins risk |
| Calmar | **4.33** | 2.99 | RR2 wins risk-adjusted |
| PF | 1.92 | **2.16** | FAST wins efficiency |

**Interpretation**: In the old legacy family, FAST was better for sprint phase (more R, faster to payout) while RR2 Gated was better for extraction phase (shallower DD = longer survival). Keep this as historical context only unless the legacy family is explicitly reopened.

R by year: 2016:+10.6 | 2017:+28.5 | 2018:+10.7 | 2019:+17.2 | 2020:+23.4 | 2021:+10.5 | 2022:+5.0 | 2023:+5.2 | 2024:+1.2 | 2025:+11.2 | 2026:+2.8

DB: `bt-nq-ny-lsi-rr2-tp0-5-thu-gated-2016-2026-174198`

**Action**: Archived reference only. Reopen only if the legacy LSI family is intentionally put back on the roadmap.

---

## Session Coverage

```
20:00  21:00  22:00  ...  04:00  ...  08:30  09:30  10:00  ...  12:00  13:00  ...  15:00  15:50
|-- NQ Asia (entry 20:15-22:30) --|
|-- ES Asia (entry 20:15-03:00) -----|
                                    |-- NQ NY HTF-LSI (entry 08:30-13:30, sweep 08:30-15:00) -----|
                                            |-- ES NY (entry 09:45-13:00) --------|
```

---

## Expansion Sequence

| Phase | Timeline | Account | Leg | Status |
|-------|----------|---------|-----|--------|
| 1 | Now | Acct 1 | NQ NY HTF-LSI lag24 | Live swap-in |
| 2 | Week 1-2 | Acct 2 | NQ Asia ORB | Already live |
| 3 | Month 1-2 | Acct 3 | ES Asia | New account application |
| 4 | Month 2-3 | Acct 4 | ES NY | New account application |
| DRY | Historical | Archive | Legacy NQ NY LSI RR2 Gated | Archived reference only |

---

## Paused Legs

### GC NY R3 Continuation Longs

**Paused — GC trading banned on Apex Trader Funding. RR 9.0 also exceeds practical prop firm constraints at standard risk sizing. Could see future use with smaller risk per trade or on a different prop firm that allows GC.**

This was the strongest walk-forward validated leg in the entire candidate set (WFE 0.956). If GC becomes tradeable, this is the first leg to activate.

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | NY (09:30-09:38 ORB, entry 09:40-12:00, flat 13:30) |
| direction | long only |
| rr | 9.0 |
| tp1_ratio | 0.35 |
| atr_length | 7 |
| stop_atr_pct | 4.5% |
| min_gap_atr_pct | 3.0% |
| impulse_close_filter | ON |
| DOW exclusion | Friday |
| excluded_dates | FOMC |
| magnifier | 1s |

| Metric | Full History | Holdout (2025+) |
|--------|-------------|-----------------|
| Trades | 622 | 62 |
| Win Rate | 31.8% | 37.1% |
| PF | 1.52 | 2.08 |
| Sharpe | 2.310 | 4.256 |
| Net R | +200.3 | +41.7 |
| Max DD | -12.4R | — |
| Calmar | 16.11 | — |
| Neg years | 0 | — |

WF: **WFE 0.956** (near-perfect), stability 0.929. MC: 63.4% survival (borderline).

R by year: 2016:+3 | 2017:+9 | 2018:+19 | 2019:+28 | 2020:+24 | 2021:+13 | 2022:+12 | 2023:+27 | 2024:+26 | 2025:+42.4

DB: `bt-gc-ny-cont-longs-r3-high-rr-final-fri-ex-692e90`

---

## Excluded Legs (with reasoning)

| Leg | Reason |
|-----|--------|
| SI Asia-1 | DSR 0.507 barely above noise — insufficient statistical confidence |
| RTY NY-4 | 2026: -10R — live regime break, recent performance disqualifying |
| CL LDN-1 | 2025: +0R — no recent edge detected |
| GC NY LSI | PF 2.29, Sharpe 4.79, but only 13 trades/year — below 30-trade OOS threshold |
| GC Asia-1 | DSR 0.652 (strong), but GC banned on Apex — revisit if prop firm changes |
| NQ Asia Discovery Asia-2 | Holdout +42.5R is exceptional, but requires regime gate build. Evaluate after the HTF-LSI swap-in stabilizes |

---

## ORB Entry Research Notes

### Close-Entry Probe (2026-04-25)

**NO-GO for ALPHA_V1 ORB replacement.** Tested two broad variants against the three active ORB legs (`NQ Asia`, `ES Asia`, `ES NY`) over `2016-04-17` to `2026-03-24`:

1. `fvg_close`: keep the valid FVG requirement but enter at the 5m FVG confirmation close instead of waiting for retest.
2. `breakout_close`: enter on the first 5m close outside ORB with no FVG requirement.

Result: the retest remains an important quality/liquidity filter. ORB sleeve baseline was `+359.5R / -21.2R DD`; `fvg_close` fell to `+28.3R / -54.8R DD`; `breakout_close` fell to `-40.6R / -119.8R DD`. `breakout_close` improved NQ Asia raw R in isolation, but ES Asia degraded sharply and ES NY became structurally negative.

Report: `backtesting/learnings/reports/ALPHA_V1_ORB_CLOSE_ENTRY_PROBE.md`

### Promising Excluded/Paused ORB Candidate Probe (2026-04-26)

Extended the same close-entry screen to three non-ALPHA candidates that remain worth tracking: `NQ Asia-2 backup`, `GC NY R3 paused`, and `GC Asia-1 diversifier` over `2016-04-17` to `2026-03-24`. Regime gates were not applied in this broad entry-mechanics pass.

Result: `fvg_close` is a broad NO-GO. It did not improve any candidate cleanly. `breakout_close` is also a clear NO-GO for both GC candidates (`GC NY R3` fell from `+153.7R` baseline to `-43.0R`; `GC Asia-1` fell from `+114.7R` to `-120.4R`). The only open thread is `NQ Asia-2 breakout_close`, which improved full-history R from `+177.8R` to `+285.5R` and holdout R from `+38.3R` to `+71.4R`, but at the cost of wider DD (`-17.5R` to `-24.0R`) and lower Sharpe (`1.95` to `1.70`). Treat it as a separate high-flow NQ Asia branch needing prop/risk/regime validation, not as a general replacement for retest entries.

Report: `backtesting/learnings/reports/PROMISING_ORB_CLOSE_ENTRY_PROBE.md`

---

## ATH Regime First Pass (2026-05-05)

Report: `backtesting/learnings/reports/ALPHA_V1_ATH_REGIME_FIRST_PASS_20260505.md`

Artifacts: `backtesting/data/results/alpha_v1_ath_regime_first_pass_20260505/`

Scope was the active ALPHA_V1 baseline trade set from the 2026-05-02 reentry promotion packet: `3,470` filled trades across `NQ NY HTF-LSI`, `NQ Asia ORB`, `ES Asia ORB`, and `ES NY ORB`, annotated with point-in-time ATH features from local continuous futures data only.

**First read: useful attribution, but the broad skip gate is NO-GO for immediate promotion.** The clearest weak bucket is signal-time `0.5-1%` below futures ATH. Full history is almost flat in that zone (`381` trades, `+2.6R`, `0.01R` avg, `46.7%` WR), while the full portfolio baseline is `+579.5R`, `0.167R` avg, `54.0%` WR. A simple skip probe preserves full-history net R (`+576.9R`) while raising avg R to `0.187` and PF from `1.41` to `1.46`; in `2025+`, the same skip improves `+106.3R / -11.2R DD` to `+111.5R / -8.5R DD`. However, the funded first-payout model gets worse outside the most recent cohort: full-history payout rate falls from `73.8%` to `70.0%`, and `2024+` falls from `81.4%` to `64.4%`. The 2025+ cohort is the exception (`84.4%` payout unchanged, breaches `2` to `0`).

Leg-level behavior is not a universal "near ATH good" rule:
- `ES Asia ORB` likes the closest ATH band: `0-0.5%` below ATH produced `325` trades, `+61.1R`, `0.188R` avg, with much lower SL rate (`21.2%`) than its baseline.
- `NQ Asia ORB` is strongest in deeper ATH drawdowns or `1-2%` below ATH, not simply right at ATH.
- `NQ NY HTF-LSI` is strongest around `2-5%` below futures ATH (`102` trades, `+42.1R`, `0.412R` avg).
- `ES NY ORB` also dislikes the `0.5-1%` band, but has good buckets both very near ATH and far below ATH.

**Next step:** do not promote `skip_pct_0p5_1_all` broadly. Continue with leg-specific ATH theses and exact-engine replay only after a narrower gate preserves account-flow quality. Separately diagnose ES-near-ATH and HTF-LSI `2-5%` behavior.

### ATH Regime Leg Targets Follow-Up (2026-05-05)

Report: `backtesting/learnings/reports/ALPHA_V1_ATH_REGIME_LEG_TARGETS_20260505.md`

Artifacts: `backtesting/data/results/alpha_v1_ath_regime_leg_targets_20260505/`

Second pass tested the leg-specific targets as post-filter research profiles on the same `3,470` ALPHA_V1 trades. **Best next exact-replay candidate is the surgical `ES NY ORB` skip of signal-time `0.5-1%` below futures ATH.** It removes only `95` ES NY trades, improves full-history portfolio R by `+5.2R`, improves `2025+` by `+5.6R`, and raises ES NY standalone full-history first-payout rate from `64.2%` to `68.5%`. Recent standalone behavior is much stronger: `2025+` ES NY baseline is `43.8%` payout / `37.5%` breach, while the gated profile is `81.2%` payout / `0.0%` breach. Caveat: combined-account full-history payout worsens (`73.8%` to `70.8%`), so this should be evaluated as a leg-specific separate-account gate, not a broad portfolio overlay.

`combo_negative_only_skip` (skip ES NY `0.5-1%` plus NQ HTF-LSI `0.5-1%`) is the best portfolio-R overlay: `+6.1R` full history and `+5.6R` in `2025+`. It improves the `2025+` combined-account read (`84.4%` payout / `6.3%` breach -> `87.5%` payout / `3.1%` breach), but full-history combined payout falls from `73.8%` to `71.9%`. Treat it as a recent-flow watchlist, not a promotion.

The attractive whitelist pockets are mostly **flow-starvation traps**. `NQ HTF-LSI` `1-5%` and `2-5%` whitelists have excellent trade quality and no standalone first-payout breaches, but cut portfolio R by `-30.5R` to `-50.5R` and slow payout cadence. `ES Asia` `0-0.5%` below ATH is a real quality pocket (`0.188R` avg vs `0.103R` baseline), but converting the leg into a near-ATH-only specialist cuts `-84.8R` from the portfolio and stretches standalone median payout time to `655` days. `NQ Asia` top-bucket gates improve full-history standalone quality but fail the recent test (`2025+` loses roughly `-23R` to `-26R`).

Deployability: all ATH gates remain `post_filter_only`; exact replay and live/exact engine support for a futures ATH pre-trade gate are required before any dry-run or live promotion.

### ES NY ATH Exact Replay (2026-05-05)

Report: `backtesting/learnings/reports/ALPHA_V1_ES_NY_ATH_EXACT_REPLAY_20260505.md`

Artifacts: `backtesting/data/results/alpha_v1_es_ny_ath_exact_replay_20260505/`

The ES NY `0.5-1.0%` below ATH dead-zone gate was implemented in the live/exact `ORBEngine` as `ath_block_min_pct/max_pct` and exact-replayed as a causal pre-arm gate. Exact replay seeds the expanding ES futures ATH from all pre-window local 5m futures bars, then updates it from each completed 5m signal bar before checking the gate.

Result: **trade-level thesis confirmed, account-flow promotion not yet confirmed.** ES NY exact full-history improves from `849` trades / `+145.8R` to `774` trades / `+155.0R` (`+9.2R`, `+3,168.70` exact PnL), with unchanged max DD at `-12.0R`. Recent windows improve more: `2024+` rises from `+34.4R / -9.0R DD` to `+42.9R / -7.5R DD`, and `2025+` rises from `+18.0R / -9.0R DD` to `+27.5R / -7.5R DD`. The gate removed `95` baseline trades and allowed `20` later replacement trades after skipped setups.

Funded first-payout read is mixed. Full-history standalone payout worsens from `65.0%` payout / `32.7%` breach to `60.4%` payout / `37.3%` breach, but recent cohorts improve: `2024+` becomes `84.7%` payout / `5.1%` breach and `2025+` becomes `75.0%` payout / `9.4%` breach. Status: `post_filter_only` until production live has a trusted ATH seed source; not production-promoted. Next step is rolling split diagnostics and nearby exact band sensitivity (`0.25-0.75%`, `0.5-0.75%`, `0.75-1.0%`, `0.5-1.25%`) before any dry-run proposal.

### ES NY ATH Band Sensitivity (2026-05-05)

Report: `backtesting/learnings/reports/ALPHA_V1_ES_NY_ATH_BAND_SENSITIVITY_20260505.md`

Artifacts: `backtesting/data/results/alpha_v1_es_ny_ath_band_sensitivity_20260505/`

Exact-engine sensitivity tested five causal ATH block bands around the ES NY dead zone: `0.25-0.75%`, `0.50-0.75%`, `0.75-1.00%`, `0.50-1.00%`, and `0.50-1.25%` below expanding ES futures ATH. This replaces the earlier broad-band read with a sharper conclusion: **`0.50-0.75%` is the best all-around candidate.**

`0.50-0.75%` improved ES NY exact full-history from `849` trades / `+145.8R` / `65.0%` payout to `808` trades / `+157.3R` / `67.3%` payout. Recent windows still improve: `2024+` rises by `+5.0R` and payout by `+10.2pp`; `2025+` rises by `+10.0R` and payout by `+15.6pp`. Rolling 2-year diagnostics are acceptable but not perfect: `7/10` windows improve, median rolling delta is `+1.75R`, worst window is `-6.92R` in `2019-2020`.

The alternatives each have a flaw. `0.25-0.75%` is best for payout safety (`70.0%` full payout, `81.2%` `2025+` payout, zero `2025+` breaches) but only improves `4/10` rolling windows and has negative median rolling delta (`-1.86R`), making it more recent-flow specialist than stable default. `0.75-1.00%` is steadier but leaves too much recent R on the table (`2025+` only `+1.5R`). The original `0.50-1.00%` remains too wide because full-history payout worsens; `0.50-1.25%` is rejected.

Implementation update: the live startup path now refreshes a futures ATH seed from DataBento daily OHLCV, applies it only to engines with an enabled ATH gate, and re-applies after checkpoint restore without lowering a higher live/checkpoint ATH. Added execution profile `ALPHA_V1-ES-NY-ATH-SHADOW`: enabled, ES_NY only, no webhooks, `ath_block_min_pct=0.5`, `ath_block_max_pct=0.75`. This makes the candidate mechanically `deployability=live_native`; `live_support_notes=causal pre-arm ATH gate plus DataBento daily seed source are supported, but profile is dry-run/shadow because it has no webhooks`; `exact_replay_required=completed_through_2026-03-24_and_repeat_before_live_promotion_if_data_extends_materially`.

Operating status: forward shadow only. Do not merge this into the live webhook profile until shadow logs show the seeded ATH, intraday ATH updates, and skipped-arm counts match expectations in real time. Shadow diagnostics are exposed through the engine `ath` status payload: `high`, `last_update`, `last_close`, `current_gap_pct`, `check_count`, `block_count`, `pass_count`, `last_check`, and `last_block`. The execution frontend renders this as a separate ATH Gate panel, and TESTING now includes `ES_NY_ATH_GATE` so skipped and non-skipped ATH gate decisions can be verified side by side before promotion.

---

## Priorities 1-5 Follow-Up Packet (2026-05-16)

Report: `backtesting/learnings/reports/ALPHA_V1_PRIORITIES_1_5_20260516.md`

Artifacts: `backtesting/data/results/alpha_v1_priorities_1_5_20260516/`

Ran the requested priorities in order: Hunter live-engine parity, Hunter sidecar sizing around `0.25x`, Hunter + ES_NY ATH interaction, updated post-`2026-03-24` exact replay, and Asia sleeve risk balance.

**Main decision update:** Hunter remains interesting as a small additive idea, but the old research-selected Hunter CSV is **not live-engine parity confirmed**. The no-webhook `ALPHA_V1-HUNTER-SAFE-025-SHADOW` exact replay through NQ local data `2026-05-01` produced `1660` trades, `+$4.7k`, PF `1.06`, and about `+73.7` net R at the actual shadow profile. On the overlap with the original selected research stream (`2016-04-25` to `2026-04-24`), fuzzy same-setup matching found only `593 / 1650` research trades (`35.9%`), with `1058` exact-only and `1057` research-only setups. Treat prior Hunter downstream reads as suggestive only until the signal-stream mismatch is explained.

**Sizing update:** current Hunter engine sizing is not a clean proportional `0.25x` risk model because `_hunter_qty_for_risk` floors to at least `1` MNQ and ignores the `max_single_risk_usd` cap used by the standard ORB sizing path. At intended `$87.50` risk, `18.2%` of Hunter trades exceed intended risk; at `$43.75`, `49.2%` exceed intended risk. The apparent `0.125x`/`0.25x`/`0.375x` sidecar rows are therefore contract-floor variants, not pure scalar variants.

**Portfolio interaction update:** on the cached fee-aware ALPHA packet through `2026-03-24`, actual-engine Hunter `0.25x` added about `+$6.0k` and improved 2025 account outcomes (`73.1%` payout / `26.9%` breach -> `84.6%` / `15.4%`) but worsened 2024 slightly (`82.6%` / `17.4%` -> `80.0%` / `20.0%`). ES_NY ATH `0.50-0.75%` revalued to current `$300` ES_NY risk improved the ES_NY leg net (`$5.7k` -> `$11.5k`) but worsened combined DD and 2024 account outcomes when used alone. The combined ATH replacement + Hunter row looked strongest in 2024-2025 (`96.0%` / `4.0%` in 2024, `84.6%` / `15.4%` in 2025), but it mixes two not-yet-promoted overlays and should remain shadow/research until Hunter parity is resolved.

**Hunter cap-fix follow-up (2026-05-17):** patched `HunterORBEngine._hunter_qty_for_risk()` to honor the standard single-contract cap instead of forcing `1` MNQ when the setup risk exceeds `max_single_risk_usd`. Cap-fixed exact replay removed the hidden over-risking (`303` over-cap trades -> `0`) and reduced standalone Hunter from old floor-based `1660` trades / `+$4.7k` / `+73.7R` to `1384` trades / `+$3.0k` / `+51.0R`. The sidecar account read got cleaner anyway: baseline ALPHA `2024` moved from `82.6%` payout / `17.4%` breach to `87.5%` / `12.5%`, and `2025` moved from `73.1%` / `26.9%` to `84.6%` / `15.4%`. Actionable status: cap-fixed Hunter is the cleaner no-webhook shadow candidate, but still no webhook promotion because research/live parity remains poor (`529 / 1650` matched research trades, `32.1%`). Report: `backtesting/learnings/reports/ALPHA_V1_HUNTER_CAP_FIX_20260517.md`.

**Hunter parity debug follow-up (2026-05-17):** root cause was entry-price convention, not Tuesday handling or broad reentry logic. The research stream uses next 5m bar open; the live Hunter translation used signal-bar close. Adding `hunter_entry_basis=next_open` moved high-cap signal-only parity to `1650 / 1650` matched research trades including entry/stop/target. Deployable cap-fixed next-open matched `1349 / 1650` (`81.8%`), with the remaining gap mostly intentional `$87.50` single-contract cap rejection (`320` qty-rejected candidates). Tuesday stays enabled; no-Tuesday matched only `1294 / 1650`. Reentry variants preserved research coverage but added exact-only flow and did not improve quality. Sidecar remains additive: next-open cap-fixed Hunter adds about `+$5.1k`, improves `2024` from `82.6% / 17.4%` payout/breach to `87.5% / 12.5%`, and improves `2025` from `73.1% / 26.9%` to `80.8% / 19.2%`. `ALPHA_V1-HUNTER-SAFE-025-SHADOW` now sets `hunter_entry_basis=next_open`; keep it no-webhook shadow only until live logs confirm next-open arming/fill behavior. Report: `backtesting/learnings/reports/ALPHA_V1_HUNTER_PARITY_DEBUG_20260517.md`.

**Updated exact replay:** `latest_common_end(["NQ", "ES"])` is still `2026-03-24` because ES local data stops there, while NQ extends to `2026-05-01`. The combined ALPHA exact replay cannot genuinely test post-`2026-03-24` yet. The current exact `ALPHA_V1-A` replay over `2023-01-01` to `2026-03-24` printed `928` trades, `$44.4k`, PF `1.41`, `+149.3` net R, and `-$4.7k` DD, below the older cached fee-aware packet (`946` trades, `$53.8k`, PF `1.48`, `+171.2` net R). Use the updated exact packet as the current code/config reference until ES data is extended.

**Asia risk balance:** with updated exact ALPHA streams and no parameter changes, the top 2024-2025 risk-balance rows were clustered around the existing Asia sleeve. `NQ Asia $450 / ES Asia $150` ranked first on the packet score (`78.9%` average 2024-2025 payout, max breach `23.1%`, `30.3d` average payout), but the current `NQ Asia $400 / ES Asia $150` was effectively tied (`78.5%`, max breach `23.1%`, `30.4d`) with lower gross exposure. Keep the current Asia risk balance as the default unless deliberately pushing for slightly more NQ Asia exposure.

---

## Risk Factors

1. **Long-biased**: All 4 legs are long-only. No short-side hedge. A sustained bear market hits all legs simultaneously.
2. **NQ + ES concentration**: All 4 legs trade equity index futures (NQ or ES). No commodity diversification — GC is paused due to Apex ban.
3. **Equity correlation in stress**: NQ and ES co-drawdown during risk-off events (March 2020 type). Without GC as a partial decorrelator, all legs are exposed to the same macro risk.
4. **Portfolio-level projections are mixed-vintage**: Older lifecycle-style legacy figures should be treated as historical context only. The active NQ NY leg is now HTF-LSI, NQ NY ORB R11 has been added as a risk-split companion leg, and the full five-leg exact rerun on the tightened live row is still pending.
5. **The HTF swap plus NQ R11 addition are live-policy updates, not a fully rerun portfolio dossier yet**: the NQ NY HTF leg is backed by exact single-leg replay and replacement sizing packets, and NQ R11 has exact split replay through `2026-03-24`, but the complete `ALPHA_V1` stack has not yet been rerun end-to-end on the five-leg risk menu.
6. **Prop firm instrument restrictions**: Apex Trader Funding bans GC trading, removing the strongest non-equity diversifier from the portfolio. Monitor for policy changes or alternative prop firms that allow GC.

### Hot-Regime Ablation / Overfit Candidate Pass (2026-05-03)

Report: `backtesting/learnings/reports/ALPHA_V1_HOT_REGIME_ABLATION_20260503.md`

Artifacts: `backtesting/data/results/alpha_v1_hot_regime_ablation_20260503/`

Intentional TESTING-only research pass inspired by `TESTING.H_ORB_ABLATED`: maximize recent R with last 1y weighted most, last 2y second, and full 10y as warning context. Hot score used: `3*last1_net + 2*last2_net + full_net - 0.50*abs(last1_dd) - 0.25*abs(last2_dd) - 0.10*abs(full_dd) - 10*full_negative_years - 25*(last1_fills<12)`. Window was `2016-04-17` to `2026-03-24`.

Best hot-score candidates by active leg:

| Leg | Candidate | Full R / DD | Last 2y R | Last 1y R | Warning |
|-----|-----------|-------------|-----------|-----------|---------|
| NQ NY HTF-LSI | `combo__window_0830_1430__dow_none__rr3p5_tp0p4__gap1p0__fvgL20_R2__lag24__cap2__mode_fvg_limit` | `113.2R / -17.91R` | `29.9R` | `16.61R` | 1 negative year |
| NQ Asia ORB | `combo__entry_2230__dow_none__rr6p0_tp0p3__stop_orb_pct_100p0__min_gap_orb_pct_10p0__uncapped_any__fvg_first__wide_none` | `242.84R / -14.22R` | `61.07R` | `41.4R` | warning layer acceptable for TESTING |
| ES Asia ORB | `combo__entry_0600__dow_baseline__rr4p0_tp0p25__stop_orb_pct_125p0__min_gap_atr_pct_0p25__cap2_any__fvg_first__wide_none` | `203.35R / -17.05R` | `44.8R` | `38.33R` | warning layer acceptable for TESTING |
| ES NY ORB | `combo__entry_1300__dow_baseline__rr7p0_tp0p2__stop_atr_pct_5p0__min_gap_atr_pct_0p25__cap2_any__fvg_first__wide_none` | `157.1R / -20.62R` | `48.48R` | `19.75R` | 1 negative year |

Research read: this pass should not supersede the robust ALPHA_V1 operating profile. Use it to select dry-run TESTING candidates only, with full-history drawdown/negative-year warnings attached.

#### Expanded top-3 Cartesian follow-up

Report: `backtesting/learnings/reports/ALPHA_V1_HOT_REGIME_EXPANDED_GRID_20260503.md`

Artifacts: `backtesting/data/results/alpha_v1_hot_regime_expanded_grid_20260503/`

Follow-up grid expanded the top-ranked OAT families into 4,378 scored variants. It kept the intentionally hot-regime objective, but constrained clearly destructive branches from the first pass: FVG extreme chasing, wide-stop target compression, and close-entry HTF-LSI. Score formula was unchanged.

Best expanded hot-score candidates by active leg:

| Leg | Expanded candidate | Full R / DD | Last 2y R / DD | Last 1y R / DD | Warning |
|-----|--------------------|-------------|----------------|----------------|---------|
| NQ NY HTF-LSI | `combo__window_0830_1430__dow_none__rr3p5_tp0p4__gap1p0__fvgL10_R2__lag24__cap2__mode_fvg_limit` | `113.04R / -16.33R` | `31.22R / -8.48R` | `18.06R / -5.62R` | 0 negative years, but worse DD than baseline |
| NQ Asia ORB | `combo__entry_2230__dow_none__rr6p0_tp0p3__stop_orb_pct_100p0__min_gap_orb_pct_10p0__cap2_after_nonpositive__fvg_first__wide_none` | `243.62R / -14.22R` | `61.07R / -7.00R` | `41.40R / -7.00R` | Better recent R, full DD worse than baseline |
| ES Asia ORB | `combo__entry_0600__dow_baseline__rr1p5_tp0p7__stop_orb_pct_125p0__min_gap_atr_pct_0p25__uncapped_any__fvg_first__wide_none` | `252.59R / -21.65R` | `61.17R / -16.07R` | `38.52R / -6.38R` | 1 negative year, lower PF, high trade count |
| ES NY ORB | `combo__entry_1300__dow_baseline__rr7p0_tp0p2__stop_atr_pct_5p0__min_gap_atr_pct_0p5__cap2_any__fvg_first__wide_none` | `165.11R / -22.30R` | `50.06R / -13.25R` | `20.03R / -13.25R` | 0 negative years, but last-1y DD worsens |

Portfolio proxy replacing all four baseline legs with these expanded best-score rows improved total net R from `+578.51R` to `+774.36R`, last-2y from `+140.46R` to `+203.52R`, and last-1y from `+90.38R` to `+118.02R`. The cost is obvious: PF drops from `1.401` to `1.287`, full DD worsens from `-15.40R` to `-25.83R`, and last-1y DD worsens from `-11.21R` to `-18.20R`.

Pure last-1y maximizers exist, especially NQ Asia `entry_2315/gap0/cap1` at `+49.70R` last-1y and ES Asia `entry_0400/exMon/stop75/uncapped` at `+56.50R` last-1y. Those are more fragile than the best-score rows and should only be used as explicit hot-regime dry-run experiments.
