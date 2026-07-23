# NQ NY VWAP 3m Validation and Prop-Firm Packet

- Run slug: `nq_ny_vwap_3m_validation_prop_packet_20260710`
- Data: `2021-06-07` through `<2026-06-06` (`1,293` NY RTH days).
- Frozen setup: 3m bars, VWAP mean, 2.5% prior-ATR extension, 30-minute consolidation, 20% ATR maximum consolidation range, sweep/reclaim, next-bar entry, 7.5% prior-ATR stop, fixed 1.5R target.
- Friction: integer MNQ sizing on NQ price data, `$0.575` commission per side, and adverse slippage stress of `0/1/2/4` ticks per side.
- Holdout status: retrospective only. The full 2021-2026 history had already been inspected during discovery; rolling test folds are causally selected but are not a pristine untouched holdout.
- Deployability: `research_only`. The 3m VWAP sweep/reclaim state machine and native-timeframe static-R exit are research-script only; the live execution engine cannot arm this setup yet.

## Baseline Audit

- Regenerated `1498` trades, `+82.1820R`, PF `1.0970`, max DD `-22.7535R`.
- Saved champion parity: trade-count delta `0`, total-R delta `+0.000000R`; parity `PASS`.

## Lower-Timeframe Path Replay

| path_label   | direction_scope   |   total_trades |   total_r |   profit_factor |   max_drawdown_r |   exit_type_changes |   total_r_delta_vs_3m | deployability   |
|:-------------|:------------------|---------------:|----------:|----------------:|-----------------:|--------------------:|----------------------:|:----------------|
| 1m           | both              |           1498 |   83.1792 |          1.0983 |         -22.6727 |                   0 |                0.9972 | research_only   |
| 1m           | long_only         |            497 |   64.1587 |          1.2396 |         -17.5382 |                   0 |               -0.3807 | research_only   |
| 1m           | short_only        |           1001 |   19.0205 |          1.0329 |         -25.9758 |                   0 |                1.3779 | research_only   |
| 1s           | both              |           1498 |   87.4503 |          1.1036 |         -22.2026 |                   3 |                5.2683 | research_only   |
| 1s           | long_only         |            497 |   64.567  |          1.2414 |         -17.1734 |                   0 |                0.0276 | research_only   |
| 1s           | short_only        |           1001 |   22.8833 |          1.0397 |         -22.7026 |                   3 |                5.2407 | research_only   |

## Friction Stress

| direction_scope   |   slippage_ticks_per_side |   total_trades |   total_r |   avg_r |   profit_factor |   max_drawdown_r |   negative_years | deployability   |
|:------------------|--------------------------:|---------------:|----------:|--------:|----------------:|-----------------:|-----------------:|:----------------|
| both              |                         0 |           1498 |   40.7346 |  0.0272 |          1.0468 |         -27.0317 |                2 | research_only   |
| both              |                         1 |           1498 |    0.1123 |  0.0001 |          1.0001 |         -38.1814 |                3 | research_only   |
| both              |                         2 |           1498 |  -40.5101 | -0.027  |          0.9559 |         -72.7229 |                3 | research_only   |
| both              |                         4 |           1498 | -121.755  | -0.0813 |          0.8738 |        -148.518  |                5 | research_only   |
| long_only         |                         0 |            497 |   49.804  |  0.1002 |          1.1807 |         -20.0964 |                2 | research_only   |
| long_only         |                         1 |            497 |   36.9666 |  0.0744 |          1.1308 |         -22.6414 |                2 | research_only   |
| long_only         |                         2 |            497 |   24.1292 |  0.0485 |          1.0833 |         -25.2049 |                2 | research_only   |
| long_only         |                         4 |            497 |   -1.5456 | -0.0031 |          0.9949 |         -32.5079 |                3 | research_only   |
| short_only        |                         0 |           1001 |   -9.0694 | -0.0091 |          0.9848 |         -39.5795 |                4 | research_only   |
| short_only        |                         1 |           1001 |  -36.8543 | -0.0368 |          0.9397 |         -58.6778 |                5 | research_only   |
| short_only        |                         2 |           1001 |  -64.6393 | -0.0646 |          0.8971 |         -84.5565 |                5 | research_only   |
| short_only        |                         4 |           1001 | -120.209  | -0.1201 |          0.8181 |        -137.163  |                5 | research_only   |

## Parameter Neighborhood

The neighborhood is evaluated after MNQ midpoint commission plus one adverse tick per side. It is a stability check, not permission to replace the frozen champion with the best full-history row.

| direction_scope   |   rank | variant_id                  |   total_trades |   total_r |   avg_r |   profit_factor |   calmar |   max_drawdown_r | is_frozen_champion   | deployability   |
|:------------------|-------:|:----------------------------|---------------:|----------:|--------:|----------------:|---------:|-----------------:|:---------------------|:----------------|
| both              |      1 | ext0.020_cons0.20_stop0.065 |           1535 |    2.0987 |  0.0014 |          1.0023 |   0.0108 |         -37.7089 | False                | research_only   |
| both              |      2 | ext0.025_cons0.20_stop0.065 |           1534 |    0.6847 |  0.0004 |          1.0007 |   0.0034 |         -39.1229 | False                | research_only   |
| both              |      3 | ext0.030_cons0.20_stop0.065 |           1534 |    0.6847 |  0.0004 |          1.0007 |   0.0034 |         -39.1229 | False                | research_only   |
| long_only         |      1 | ext0.020_cons0.20_stop0.065 |            506 |   34.5004 |  0.0682 |          1.1187 |   0.4037 |         -16.6549 | False                | research_only   |
| long_only         |      2 | ext0.025_cons0.20_stop0.065 |            506 |   34.5004 |  0.0682 |          1.1187 |   0.4037 |         -16.6549 | False                | research_only   |
| long_only         |      3 | ext0.030_cons0.20_stop0.065 |            506 |   34.5004 |  0.0682 |          1.1187 |   0.4037 |         -16.6549 | False                | research_only   |
| short_only        |      1 | ext0.020_cons0.20_stop0.065 |           1029 |  -32.4017 | -0.0315 |          0.9491 |  -0.1147 |         -55.0641 | False                | research_only   |
| short_only        |      2 | ext0.020_cons0.15_stop0.065 |            727 |  -35.3565 | -0.0486 |          0.9217 |  -0.1162 |         -59.2899 | False                | research_only   |
| short_only        |      3 | ext0.025_cons0.20_stop0.065 |           1028 |  -33.8157 | -0.0329 |          0.9468 |  -0.1167 |         -56.4781 | False                | research_only   |

Frozen champion row:

| direction_scope   |   rank | variant_id                  |   total_trades |   total_r |   avg_r |   profit_factor |   calmar |   max_drawdown_r | deployability   |
|:------------------|-------:|:----------------------------|---------------:|----------:|--------:|----------------:|---------:|-----------------:|:----------------|
| both              |      5 | ext0.025_cons0.20_stop0.075 |           1498 |    -5.156 | -0.0034 |          0.9943 |  -0.0251 |         -39.9577 | research_only   |
| long_only         |     11 | ext0.025_cons0.20_stop0.075 |            497 |    36.939 |  0.0743 |          1.1305 |   0.3176 |         -22.669  | research_only   |
| short_only        |      8 | ext0.025_cons0.20_stop0.075 |           1001 |   -42.095 | -0.0421 |          0.9315 |  -0.1295 |         -63.3742 | research_only   |

## Rolling Walk-Forward

Each fold selects from the 27-row neighborhood using only the preceding 18 months, then evaluates the next six months after commission and one tick per side. The frozen champion is shown beside the selected row.

| direction_scope   | test_start   | test_end_exclusive   | selected_variant_id         |   selected_test_trades |   selected_test_total_r |   selected_test_pf |   frozen_test_total_r |   frozen_test_pf | deployability   |
|:------------------|:-------------|:---------------------|:----------------------------|-----------------------:|------------------------:|-------------------:|----------------------:|-----------------:|:----------------|
| both              | 2023-01-01   | 2023-07-01           | ext0.020_cons0.20_stop0.085 |                    150 |                -10.9053 |             0.8842 |                1.9643 |           1.0212 | research_only   |
| both              | 2023-07-01   | 2024-01-01           | ext0.020_cons0.20_stop0.075 |                    162 |                -11.51   |             0.8871 |              -12.9332 |           0.8732 | research_only   |
| both              | 2024-01-01   | 2024-07-01           | ext0.020_cons0.20_stop0.075 |                    139 |                  6.1371 |             1.0755 |                6.1371 |           1.0755 | research_only   |
| both              | 2024-07-01   | 2025-01-01           | ext0.020_cons0.20_stop0.065 |                    160 |                 -3.1138 |             0.9679 |                0.8817 |           1.0096 | research_only   |
| both              | 2025-01-01   | 2025-07-01           | ext0.020_cons0.20_stop0.075 |                    135 |                  4.0605 |             1.0522 |                4.0605 |           1.0522 | research_only   |
| both              | 2025-07-01   | 2026-01-01           | ext0.020_cons0.15_stop0.075 |                    108 |                -14.7322 |             0.7887 |              -18.8722 |           0.7968 | research_only   |
| long_only         | 2023-01-01   | 2023-07-01           | ext0.020_cons0.20_stop0.085 |                     50 |                  5.1972 |             1.1858 |                3.7095 |           1.1266 | research_only   |
| long_only         | 2023-07-01   | 2024-01-01           | ext0.020_cons0.20_stop0.085 |                     52 |                  2.7279 |             1.0944 |                4.0682 |           1.1349 | research_only   |
| long_only         | 2024-01-01   | 2024-07-01           | ext0.020_cons0.20_stop0.085 |                     34 |                 12.951  |             1.8724 |               14.1906 |           1.9471 | research_only   |
| long_only         | 2024-07-01   | 2025-01-01           | ext0.020_cons0.20_stop0.075 |                     49 |                 -4.4514 |             0.856  |               -4.4514 |           0.856  | research_only   |
| long_only         | 2025-01-01   | 2025-07-01           | ext0.020_cons0.25_stop0.085 |                     53 |                  4.2123 |             1.1403 |               -0.3488 |           0.9848 | research_only   |
| long_only         | 2025-07-01   | 2026-01-01           | ext0.020_cons0.25_stop0.065 |                     63 |                -20.4743 |             0.5626 |               -4.9058 |           0.8276 | research_only   |
| short_only        | 2023-01-01   | 2023-07-01           | ext0.020_cons0.20_stop0.075 |                    104 |                 -1.7452 |             0.9725 |               -1.7452 |           0.9725 | research_only   |
| short_only        | 2023-07-01   | 2024-01-01           | ext0.020_cons0.20_stop0.065 |                    108 |                -14.5942 |             0.797  |              -17.0013 |           0.7632 | research_only   |
| short_only        | 2024-01-01   | 2024-07-01           | ext0.020_cons0.20_stop0.065 |                    105 |                 -7.1997 |             0.8926 |               -8.0535 |           0.8786 | research_only   |
| short_only        | 2024-07-01   | 2025-01-01           | ext0.020_cons0.20_stop0.065 |                    111 |                  4.2005 |             1.0648 |                5.333  |           1.0873 | research_only   |
| short_only        | 2025-01-01   | 2025-07-01           | ext0.020_cons0.15_stop0.075 |                     75 |                 12.9283 |             1.3409 |                4.4093 |           1.0802 | research_only   |
| short_only        | 2025-07-01   | 2026-01-01           | ext0.020_cons0.15_stop0.075 |                     82 |                -11.3053 |             0.786  |              -13.9664 |           0.7833 | research_only   |

## Block Bootstrap

| direction_scope   |   iterations |   block_days |   total_r_p05 |   total_r_median |   total_r_p95 |   max_dd_r_p05 |   max_dd_r_median |   prob_total_r_positive |   prob_dd_worse_than_20r | deployability   |
|:------------------|-------------:|-------------:|--------------:|-----------------:|--------------:|---------------:|------------------:|------------------------:|-------------------------:|:----------------|
| both              |         5000 |            5 |        -76.63 |            -0.56 |         74.3  |        -101.75 |            -51.16 |                  0.495  |                   0.997  | research_only   |
| long_only         |         5000 |            5 |         -9.66 |            36.4  |         81.03 |         -38.92 |            -20.16 |                  0.9036 |                   0.5072 | research_only   |
| short_only        |         5000 |            5 |        -96.7  |           -38.61 |         22.09 |        -108.86 |            -60.42 |                  0.1444 |                   0.9946 | research_only   |

## Prop-Firm Lifecycle

Model: $2,000 EOD trailing drawdown, +$3,000 pass, one $1,500 first payout, floor capped at starting balance, then continue until bust or data end. Starts are every 14 calendar days; no challenge fee is included. Rankings below use starts with at least 12 months of follow-up.

Best matured row by direction under one adverse tick per side:

| direction_scope   |   risk_budget_usd |   slippage_ticks_per_side |   total_starts |   first_payout_rate |   resolved_first_payout_rate |   pre_payout_bust_rate |   post_payout_bust_rate |   open_rate |   ev_per_start_usd |   avg_days_to_first_payout |   fill_retention | deployability   |
|:------------------|------------------:|--------------------------:|---------------:|--------------------:|-----------------------------:|-----------------------:|------------------------:|------------:|-------------------:|---------------------------:|-----------------:|:----------------|
| both              |               300 |                         1 |            105 |              0.3238 |                       0.3238 |                 0.6762 |                  0.3238 |      0      |             485.71 |                      58.68 |                1 | research_only   |
| long_only         |               150 |                         1 |            105 |              0.5714 |                       0.6742 |                 0.2762 |                  0.381  |      0.3429 |             857.14 |                     469.85 |                1 | research_only   |
| short_only        |               500 |                         1 |            105 |              0.181  |                       0.181  |                 0.819  |                  0.181  |      0      |             271.43 |                      38.16 |                1 | research_only   |

User-requested $500 risk under one-tick-per-side stress:

| direction_scope   |   risk_budget_usd |   total_starts |   first_payout_rate |   resolved_first_payout_rate |   pre_payout_bust_rate |   post_payout_bust_rate |   open_rate |   ev_per_start_usd |   avg_days_to_first_payout |   fill_retention | deployability   |
|:------------------|------------------:|---------------:|--------------------:|-----------------------------:|-----------------------:|------------------------:|------------:|-------------------:|---------------------------:|-----------------:|:----------------|
| long_only         |               500 |            105 |              0.5048 |                       0.5048 |                 0.4952 |                  0.4476 |      0.0571 |             757.14 |                      59.72 |                1 | research_only   |
| both              |               500 |            105 |              0.2857 |                       0.2857 |                 0.7143 |                  0.2857 |      0      |             428.57 |                      20.03 |                1 | research_only   |
| short_only        |               500 |            105 |              0.181  |                       0.181  |                 0.819  |                  0.181  |      0      |             271.43 |                      38.16 |                1 | research_only   |

## Promotion Decision

- Daily-cadence both-direction friction gate: **FAIL**.
- Long-only friction gate: **PASS**.
- Both-direction rolling selected-fold gate: **FAIL** (`2/6` positive test folds).
- Both-direction frozen-row rolling gate: **FAIL** (`4/6` positive test folds).
- Long-only rolling selected-fold gate: **FAIL** (`4/6` positive test folds).
- Long-only frozen-row rolling gate: **FAIL** (`3/6` positive test folds).
- Long-only block-bootstrap gate: **FAIL**.
- Long-only matured prop gate at one tick/side: **FAIL**.
- Live-native implementation: **DEFER**.

The both-direction daily-cadence branch is a no-go after friction and walk-forward validation, and the short side is the main drag. Long-only survives basic friction but fails the tightened rolling, bootstrap, and prop-quality gates, so it remains a conditional research shelf candidate rather than a promotion candidate. No live-engine implementation is justified by this packet.

## Artifacts

- Results: `backtesting/data/results/nq_ny_vwap_3m_validation_prop_packet_20260710/`
- Report: `backtesting/learnings/reports/NQ_NY_VWAP_3M_VALIDATION_PROP_PACKET_20260710.md`
