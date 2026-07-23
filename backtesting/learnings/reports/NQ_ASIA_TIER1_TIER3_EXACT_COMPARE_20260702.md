# NQ Asia Tier 1-3 Exact Compare

- Run slug: `nq_asia_tier1_tier3_exact_compare_20260702`
- Window: `2016-04-17` to `2026-03-24`
- Base profile source: `ALPHA_V1-A` for the ALPHA RR6 incumbent and Tier 1 target compression.
- Exact replay: execution engine via in-memory profiles only; `execution/config/exec_configs.json` was not edited.
- Account model: `$50k`, `$2k` EOD trailing drawdown capped at `$50k`, first payout trigger `$52.5k`, first withdrawal `$500`, fee `$150`, starts every `14` calendar days.

## Standalone Exact Replay

| Candidate | Tier | Trades | Net R | WR% | PF | DD R | Calmar | Full TP% | TP1-BE% | NegY |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALPHA RR6 incumbent | incumbent | 726 | 204 | 45.2 | 1.43 | -8.80 | 23.1 | 6.10 | 15.2 | 0 |
| Tier 1 rr=3 / TP1=2R | tier_1_exit_compression | 726 | 209 | 43.9 | 1.45 | -12.4 | 16.9 | 23.3 | 8.10 | 0 |
| Tier 2 R5 Final | tier_2_shelf | 1477 | 82.5 | 50.9 | 0.81 | -5.50 | 15.1 | 11.0 | 77.0 | 0 |
| Tier 2 R9 Restart Final | tier_2_shelf | 748 | 197 | 45.3 | 1.30 | -11.2 | 17.6 | 26.5 | 18.2 | 0 |

## Portfolio Payout At NQ Asia $400

Risk map: HTF `$300`, NQ Asia `$400`, ES Asia `$200`, R11 `$250`, ES NY `$200`.

| Candidate | Accts | Pay | Breach | Open | Start Pay% | Resolved Pay% | Avg PayD | MCBch | EV/start |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| alpha_rr6_incumbent | 59 | 38 | 20 | 1 | 64.4 | 65.5 | 25.9 | 6 | 172 |
| alpha_rr3_tp1_2r | 59 | 39 | 19 | 1 | 66.1 | 67.2 | 26.6 | 6 | 181 |
| r5_final | 59 | 45 | 12 | 2 | 76.3 | 79.0 | 55.8 | 10 | 231 |
| r9_restart_final | 59 | 34 | 22 | 3 | 57.6 | 60.7 | 27.1 | 5 | 138 |

## Single-Leg NQ Asia Payout At $400

| Candidate | Accts | Pay | Breach | Open | Start Pay% | Resolved Pay% | Avg PayD | MCBch | EV/start |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| alpha_rr6_incumbent | 59 | 45 | 8 | 6 | 76.3 | 84.9 | 65.5 | 4 | 231 |
| alpha_rr3_tp1_2r | 59 | 46 | 8 | 5 | 78.0 | 85.2 | 59.0 | 4 | 240 |
| r5_final | 59 | 52 | 0 | 7 | 88.1 | 100 | 230 | 0 | 291 |
| r9_restart_final | 59 | 34 | 19 | 6 | 57.6 | 64.2 | 54.6 | 10 | 138 |

## Sleeve Correlation

| Candidate | NQ/ES Asia Corr | NQ/Other Corr | Avg Pair Corr | NQ Active Days |
| --- | --- | --- | --- | --- |
| alpha_rr6_incumbent | 0.31 | 0.16 | 0.05 | 726 |
| alpha_rr3_tp1_2r | 0.32 | 0.16 | 0.05 | 726 |
| r5_final | 0.06 | 0.01 | 0.02 | 1477 |
| r9_restart_final | 0.20 | 0.09 | 0.03 | 748 |

## Pre-Registered Gate Read

| Candidate | R>=90% | No New NegY | DD OK | Full TP Delta | Pay Delta | PayD Delta | MCBch Delta | Gate Pass |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| alpha_rr6_incumbent | 1 | 1 | 1 | 0.00 | 0.00 | 0.00 | 0 | 1 |
| alpha_rr3_tp1_2r | 1 | 1 | 0 | 17.2 | 1.70 | 0.70 | 0 | 0 |
| r5_final | 0 | 1 | 1 | 5.00 | 11.9 | 29.9 | 4 | 0 |
| r9_restart_final | 1 | 1 | 0 | 20.4 | -6.80 | 1.20 | -1 | 0 |

## Interpretation Notes

- `R5 Final` is replayed for comparison but remains deprecated because `tp1_ratio=0.10` was later judged degenerate.
- `R9 Restart Final` is replayed through execution-native fields. The research history mentions `max_gap_points=75`, but the current execution ORB engine does not expose that as a config field, so this is the deployable execution-native replay of the same main structure rather than a max-gap-points parity proof.
- Payout rows include open accounts separately. Use both start-rate and resolved-rate semantics when reading partial `2026_ytd` windows.

## Artifacts

- `exact_metrics.csv`
- `payout_summary.csv`
- `payout_outcomes.csv`
- `correlations.csv`
- `promotion_gates.csv`
- `summary.json`
