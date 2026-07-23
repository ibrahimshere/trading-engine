# ALPHA_V1 Phase-Two (Post-First-Payout) Portfolio Construction - 2026-07-22

## Question

After first payout, the funded account operates with a locked $50k floor, ~$2k of room, and a
consistency rule (>=5 days of >=$250 profit per payout cycle). ALPHA_V1-A's home-run payoff
shape slow-bleeds between big hits. Would a base-hit portfolio (single-target exits, higher WR,
smaller targets) be a better phase-2 operating mode?

## Method

Pipeline: `phase-two-robust-pipeline` posture (post-payout continuity + path risk), no new
engine runs — cached exact streams only:

- Current five-leg ALPHA_V1-A split ladders, fee-aware:
  `alpha_v1_ath_fragility_20260608/baseline_trades_ath_annotated.csv` (2021-06-07 .. 2026-06-03)
- Exact single-target variants (ES_NY 1.0R, ES_Asia 1.25R, NQ R11 1.4R):
  `alpha_v1_single_target_exact_prop_20260506/exact_trades.csv` (2016-04 .. 2026-03-19),
  with a flat `-0.02R/trade` fee proxy (replay predates the MNQ/MES fee model)

Common comparison window `2021-06-07 .. 2026-03-19`; recent split `2025-01-01+`.
Account model: balance $52,000, locked floor $50,000, EOD breach; Friday withdrawal to the
reset level when balance >= trigger AND >=5 qualifying days (day PnL >= +$250) since last
withdrawal. Monthly-start cohorts to window end plus 2,000-path iid daily bootstrap (252d).
Day PnL accounted on exit date.

Scripts: `backtesting/scripts/run_alpha_v1_phase_two_portfolio_20260722.py`,
`backtesting/scripts/run_alpha_v1_phase_two_risk_frontier_20260722.py`
Artifacts: `backtesting/data/results/alpha_v1_phase_two_portfolio_20260722/`

## Key Findings

**1. The consistency rule sets a risk floor; the locked $2k sets a heat ceiling — and for
base-hit menus they don't overlap.** A single-target win must be >=$250 to print a qualifying
day, so single-exit legs need >=$250 risk each (at $200 risk a 1R winner stops qualifying and
cadence collapses). But every singles structure at qualifying size carried unacceptable path
risk against $2k of room:

| Structure (flat risk) | Qual days/mo | First WD (med) | MC 1y breach | Verdict |
|---|---|---|---|---|
| BH3 singles $275 | 7.2 | 17d | 80.3% | NO-GO |
| BH2 ES Asia+R11 $275 | 6.5 | 19d | 63.9% | NO-GO |
| BH2 ES NY+ES Asia $275 | 7.0 | 19d | 72.2% | NO-GO |
| Singles $200 + LSI $150 | 2.5 | 42d | 37.4% | NO-GO (wins stop qualifying) |

Higher WR does not mean safer here: singles convert drawdown *depth* into loss *frequency*,
and the risk needed to satisfy the $250 rule makes worst-day/worst-month larger, not smaller.
The intuition that base hits are gentler on a monetized account is wrong at this floor size.

**2. The current five-leg split book at reduced risk is the phase-2 core.** SPLIT5 flat $150:
0% cohort breach (both windows), MC 1y breach 16.6% full / 3.1% recent, median withdrawals
~$7.3k/yr full-window and ~$12.4k/yr on 2025+. Flat $175 is the tolerance bound (22% cohort
breach full window at the default withdrawal policy). $200 flat is too hot post-payout
(75% cohort breach) even though it is fine for phase-1 sprints.

**3. The withdrawal reset level is the strongest free lever.** Withdrawing to $52.0k every
Friday pins the buffer at $2k forever. Banking a cushion first (withdraw to $52.5k, trigger
$53k) costs ~2-8% of withdrawal volume and roughly halves ruin risk:

| Menu | Policy | Coh breach | MC 1y breach | Ann WD (med) | 2025+ MC breach |
|---|---|---|---|---|---|
| SPLIT5 $150 | reset $52.0k | 0.0% | 16.6% | $7,294 | 3.1% |
| SPLIT5 $150 | reset $52.5k | 0.0% | **8.4%** | $7,136 | 1.4% |
| SPLIT5 $175 | reset $52.5k | 2.0% | 16.0% | $8,258 | 3.3% |
| SPLIT5 + ES Asia single 1.25R @1.3x, $150 | reset $53.0k | 6.1% | 11.3% | $9,340 | 3.1% |

**4. The only singles idea that survives is the ES Asia single-target swap inside the split
book.** Replacing ES Asia split rr1.5 with the exact-validated single 1.25R (at 1.3x leg risk,
$195 on a $150 book) lifts qualifying days from 2.3 to 2.9/mo and median withdrawals from
~$7.1k to ~$9.3k/yr, at 11.3% MC breach with the $53k buffer policy. It is the one exit-style
change worth carrying into phase 2 — consistent with the 2026-05-06 exact compare where ES Asia
single 1.25R was the only true R/PF upgrade.

## Decision

- **GO (phase-2 default): SPLIT5 flat $150 with banked-buffer withdrawals (trigger $53.0k,
  reset $52.5k).** Same legs, same exits as ALPHA_V1-A — only risk and withdrawal policy change.
- **CONDITIONAL: ES Asia single 1.25R swap at 1.3x leg risk with $53k buffer.** Best
  withdrawal/qualifying cadence per unit of breach risk, but requires a live-engine exact
  profile + fresh exact replay before deployment (current stream is the 2026-05-06 replay with
  a fee proxy).
- **NO-GO: all pure base-hit singles menus at consistency-qualifying risk.** 50-88% one-year
  ruin odds against a $2k locked floor.

Expected cadence at the GO menu: ~2.3-2.9 qualifying days/month -> a 5-day consistency cycle
completes in ~6-9 weeks; median first withdrawal ~50-60 trading days, then every ~7-8 weeks
(faster in 2025+ regime: ~$12k/yr median). The slow bleed between home runs is survivable at
$150 flat; the base-hit alternative feels smoother day-to-day and dies an order of magnitude
more often.

## Addendum: Churn ROI Frame (same day, follow-up)

Reframed objective: accounts are disposable leverage. $300 per funded account (eval ignored),
fresh account $50k with $2k trailing floor locking at $50k, run until breach, withdraw max
each Friday (reset $52.0k) under the 5x$250 consistency rule. Renewal-reward metric:
`$/slot-yr = 252 * (E[withdrawn] - 300) / E[lifetime days]`.

Script: `backtesting/scripts/run_alpha_v1_funded_churn_roi_20260722.py`
Artifact: `alpha_v1_phase_two_portfolio_20260722/churn_roi.csv`

| Menu | EV/acct (MC) | $/slot-yr (MC) | Med life | 1st WD | 2025+ $/slot-yr | Hist: breached / med WD |
|---|---|---|---|---|---|---|
| SPLIT5 $150 | +$24,953 | $6,027 | 820d | 80d | $10,539 | 2/53 / $16.5k |
| SPLIT5 $200 | +$14,941 | $8,210 | 302d | 55d | $14,232 | 33/53 / $13.3k |
| SPRINT x1 (live menu) | +$9,302 | $13,446 | 112d | 30d | $23,525 | 48/53 / $3.3k |
| SPRINT x1.5 | +$6,022 | $21,354 | 42d | 20d | $35,915 | 52/53 / $1.1k |
| SPRINT x2.0 | +$4,867 | $30,125 | 25d | 15d | $48,163 | 52/53 / $1.5k |
| SPRINT x2.5 | +$4,723 | $39,455 | 18d | 15d | $61,440 | 53/53 / **$0** |
| BH3 singles $350 | +$4,291 | $12,444 | 55d | 25d | $13,879 | 53/53 / $1.2k |

Key reads:

1. **Every tested menu is strongly positive EV against a $300 account cost** — the cost is
   nearly irrelevant (EV 15-80x cost). The binding constraints are account supply and
   consistency-rule frictions, not the $300.
2. **Extraction rate rises ~linearly with risk in iid MC** because EV/account plateaus
   (~$5-9k) while churn accelerates. But historical monthly cohorts (clustered losses, one
   regime cycle) show mean resolved extraction of roughly 1/3 the MC value, and beyond
   ~x1.5 sprint the **median** historical account withdrew $0 — tail paths carry all EV.
3. **Base-hit singles are dominated in the churn frame too**: BH3 $350 earns less per
   slot-year than SPRINT x1 with worse EV/account, and 2025+ regime favors the split book
   ~2:1. The home-run payoff shape is what makes churn EV work.
4. **Withdraw-max beats buffer-banking under churn** (buffer adds life, not rate).
5. Practical ceiling: ~**SPRINT x1 to x1.5**. Beyond that, median-account-extracts-zero,
   consistency/best-day rules and payout-denial risk at rapid churn make the modeled rate
   unrealistic; iid MC is most optimistic exactly where losses cluster hardest.

## Addendum 2: Apex 50K EOD PA Exact Rules (same day, follow-up)

Rules fetched from the Apex help center (2026-07-22) and encoded in
`backtesting/scripts/run_alpha_v1_apex_lifecycle_20260722.py`
(artifact `alpha_v1_phase_two_portfolio_20260722/apex_lifecycle.csv`):

- EOD trailing threshold $2,000, locks at **$50,100** once highest EOD balance hits $52,100;
  never decreases; payouts do not lower it. Enforced intraday incl. unrealized PnL.
- **Daily Loss Limit (intraday, tier-based)**: $1,000 until +$3k profit, $2,000 to $6k,
  $3,000 above. Hitting DLL liquidates + pauses the day; account survives.
- **Contract caps, tier-based**: 2 standard (=20 micros) until +$1.5k profit, 3 to $3k,
  4 above. 10 micros = 1 standard. Payouts lower the tier.
- **Payouts**: Friday-eligible with balance >= $52,600, >= 5 qualifying days ($250+),
  and **50% consistency** (best profitable day < 50% of net profit since last approved
  payout; resets each payout). Amount = min(cap, balance - $52,100), min $500.
  Caps: $1.5k/$1.5k/$2k/$2.5k/$2.5k/$3k. **Max 6 payouts, then the PA closes** —
  lifetime extraction cap **$13,000** per account.

Lifecycle sim (complete-6 = success; $300/account):

| Menu | MC complete | EV/acct | $/slot-yr | 6th payout | 2025+ complete / $/yr | Hist complete / med WD |
|---|---|---|---|---|---|---|
| SPLIT5 $150 | 71% | $7,098 | $4,987 | 405d | 95% / $8,680 | 46/53 / $8.6k |
| SPLIT5 $200 | 57% | $6,963 | $6,822 | 330d | 86% / $11,739 | 39/53 / $10.3k |
| **SPLIT5 $250** | 48% | $6,371 | $8,328 | 280d | **79% / $14,392** | **30/53 / $11.6k** |
| SPRINT x1 | 53% | $6,749 | $8,251 | 315d | 80% / $14,055 | 23/53 / **$2.8k** |
| SPRINT x1.5 | 43% | $5,460 | $8,990 | 290d | 69% / $15,636 | 21/53 / **$785** |
| BH3 singles $275 | 31% | $4,185 | $8,073 | 210d | 40% / $9,073 | 15/53 / $1.5k |
| HYBRID mid | 46% | $6,111 | $10,126 | 215d | 65% / $13,029 | 19/53 / $6.5k |

Key reads:

1. **The 6-payout / $13k lifetime cap turns each PA into a coupon book.** EV per account is
   capped and converges (~$4-7k) across menus; unbounded-churn logic (rate scales with risk)
   is dead. The objective is now `P(clip all 6 coupons) x speed`, and EV and EW collapse
   into the same metric.
2. **The 50% consistency rule specifically taxes the sprint's payoff signature.** At sprint
   sizing, a 6R NQ Asia day (~$2,400) or 3.5R LSI day (~$1,750) forces net-per-cycle >= 2x
   that before any payout, while the payout is capped at $1.5-3k anyway. Historical cohorts:
   sprint median withdrawn collapses to $2.8k (x1) and $785 (x1.5) vs $11.6k for SPLIT5 $250.
   At $200-250 flat the same runner day is $1,200-1,500 -> consistency barely binds.
3. **Home-run excess is not wasted despite payout caps**: retained profit builds balance
   buffer, de-risks later cycles, and tiers the account UP (more contracts, higher DLL).
4. **Base-hit singles are dominated under every frame tested** — thinner edge, worst
   completion (15/53 historical), worst EV.
5. **Recommended Apex operating band: current five split legs at flat $200-250** (between
   the balanced and old phase-2 sizing). MC and historical agree it maximizes completed
   coupon books per slot-year; 2025+ regime: ~79-86% completion, 6th payout in ~190-215
   trading days, ~$12-14k/slot-yr.

Follow-ups worth testing: adaptive risk (halve size after a monster day until consistency
clears; scale risk with buffer/tier), and Tier-1 contract-cap feasibility for overlapping
NY legs (LSI + R11 + ES NY concurrent micros vs the 20-micro cap).

## Addendum 3: Day-Cap, Adaptive Sizing, and Contract Feasibility (same day)

Script: `backtesting/scripts/run_alpha_v1_apex_policies_20260722.py`
Artifact: `alpha_v1_phase_two_portfolio_20260722/apex_policies.csv`

Policies tested on the Apex-exact lifecycle: hard day-cap (flatten once day PnL hits
$1,000 / $1,300 / $2,000), adaptive half-size while the 50% consistency gate is blocking,
and both combined.

| Menu + policy | MC comp | $/slot-yr | 2025+ comp / $/yr | Hist comp / med WD |
|---|---|---|---|---|
| SPLIT5 $250 no policy | 48.3% | $8,328 | 79% / $14,392 | 30/53 / $11.6k |
| SPLIT5 $250 cap $1,300 | 48.3% | $8,328 | 79% / $14,392 | 30/53 / $11.6k (identical) |
| SPLIT5 $250 cap $1,000 | 44.8% | $8,276 | 79% / $14,379 | 28/53 / $10.5k (worse) |
| SPLIT5 $250 adaptive half | 56.1% | $5,515 | 86% / $9,732 | 27/53 / $9.2k |
| SPRINT x1 no policy | 53.2% | $8,251 | 80% / $14,055 | 23/53 / $2.8k |
| SPRINT x1 cap $1,300 | 49.8% | $8,430 | 80% / $14,170 | 24/53 / **$9.8k** |
| SPRINT x1 adaptive half | 60.0% | $6,273 | 87% / $10,967 | **29/53 / $11.7k** |

Reads:

1. **At the recommended $200-250 flat sizing, a $1,300 day-cap is a no-op** — days that
   large are too rare to drive consistency blocking. Capping tighter ($1,000) actively hurts
   (cuts buffer-building with no consistency benefit). **Do not stop early at these sizes;
   excess profit above the threshold is pure buffer + tier-up value.**
2. **Day-capping only matters at sprint sizing**, where cap $1,300 repairs the historical
   consistency damage (median withdrawn $2.8k -> $9.8k) — but it still only ties SPLIT5 $250
   on extraction rate, so it rescues sprint rather than beating the flat book.
3. **Adaptive half-size while blocked is the better consistency medicine everywhere**: best
   completion rates (60-68% MC, 86-92% on 2025+) and best sprint history (29/53, $11.7k),
   because it de-risks exactly the grind-out stretch after a monster day. Cost: ~25-30%
   lower $/slot-yr from longer cycles. Choose it when completion reliability > speed
   (limited account supply); skip it when slots are plentiful and rate is king.
4. **Contract caps (10 micros = 1 standard)**: flat $200 needs >20 concurrent micros on only
   0.4% of days (p99 18.3) — clean at Tier 1. Flat $250 exceeds Tier 1 on 4.7% of days
   (p99 22.9, peak 29.2) but never exceeds Tier 2's 30. Operationally clean ramp:
   **$200 until +$1,500 profit (Tier 2), then $250**. Tier 3+ (40) is never touched.

## Caveats

- iid daily bootstrap ignores autocorrelation/vol clustering; cohort sim covers one regime
  cycle (2021-2026) with LSI data only from 2021-06.
- Singles streams predate the fee model; `-0.02R/trade` proxy applied.
- Consistency rule modeled as ">=5 days of >=$250 per cycle, reset on withdrawal" — verify the
  actual prop firm's wording (some use percent-of-profit or best-day ratios instead).
- Deployability: GO menu is `live_native` (risk + policy change only). ES Asia single swap is
  `live_native` mechanically (`exit_mode=single_target` supported) but
  `exact_replay_required=yes_before_live_change`.
