# NQ NY Selective VWAP Regime Discovery

- Run slug: `nq_ny_vwap_selective_regime_discovery_20260710`
- Available data: `2016-01-01` through `<2026-06-06`.
- Discovery window: `2016-01-01` through `<2023-01-01`; retrospective gate validation: `2023-01-01` through `<2026-06-06`.
- True future holdout is frozen from `2026-06-06` forward and was not available in this run.
- The retrospective validation segment is not pristine for the base setup because prior work already inspected 2021-2026. The new regime-gate thresholds were selected from the discovery window only.
- Search count: `155` raw trials and `51` effective trials by trade-date overlap clustering. PBO/CSCV is not implemented; PSR/DSR is reported.
- Deployability: `post_filter_only`. The regime variables are causal and available by 10:00 ET, but this discovery applies them to completed research trades. The gate must be implemented before order arming and exact-replayed before dry/live use.

## Baseline Controls

| candidate_id     |   full_trades |   full_total_r |   full_profit_factor |   full_max_drawdown_r |   cold_trades |   cold_total_r |   cold_profit_factor |   cold_max_drawdown_r |   recent_trades |   recent_total_r |   recent_profit_factor |   recent_max_drawdown_r | deployability    |
|:-----------------|--------------:|---------------:|---------------------:|----------------------:|--------------:|---------------:|---------------------:|----------------------:|----------------:|-----------------:|-----------------------:|------------------------:|:-----------------|
| pure_vwap_target |           811 |        136.118 |               1.2551 |              -45.1152 |           441 |         7.3278 |               1.0241 |              -45.1152 |             370 |          128.79  |                 1.5607 |                -12.1977 | post_filter_only |
| day_mid_target   |           804 |        178.688 |               1.3422 |              -42.4196 |           436 |        32.2453 |               1.1093 |              -42.4196 |             368 |          146.443 |                 1.6442 |                -11.5293 | post_filter_only |

The day-mid target is the leader: it improves both the cold and recent windows versus the pure VWAP target, but the cold-window PF and drawdown still require a regime explanation.

## Discovery Screen

- Pre-registered univariate gates: `125`.
- Pair gates from `8` discovery-selected feature families: `28`.
- Candidates clearing structural discovery/retrospective gates: `43`.

Top univariate rows by discovery Calmar:

| candidate_id                      | candidate_type   | gate_1                       | gate_2   |   full_trades |   full_total_r |   full_profit_factor |   full_max_drawdown_r |   discovery_profit_factor |   validation_profit_factor |   cold_profit_factor |   positive_fold_rate |   worst_fold_r | deployability    |
|:----------------------------------|:-----------------|:-----------------------------|:---------|--------------:|---------------:|---------------------:|----------------------:|--------------------------:|---------------------------:|---------------------:|---------------------:|---------------:|:-----------------|
| uni__dir_gap_atr_ge_0p5           | univariate       | dir_gap_atr_ge_0p5           | none     |            51 |        33.0185 |               2.1006 |               -6      |                    2.4449 |                     1.412  |               2.4497 |               0      |         0      | post_filter_only |
| uni__opening_efficiency_ge_0p25   | univariate       | opening_efficiency_ge_0p25   | none     |           543 |       160.171  |               1.475  |              -18.4498 |                    1.32   |                     1.8115 |               1.2368 |               0.7    |        -8.3141 | post_filter_only |
| uni__opening_efficiency_ge_0p55   | univariate       | opening_efficiency_ge_0p55   | none     |           216 |       100.002  |               1.8455 |               -9.8598 |                    1.5174 |                     2.394  |               1.4271 |               0.9    |        -5.057  | post_filter_only |
| uni__opening_efficiency_ge_0p7    | univariate       | opening_efficiency_ge_0p7    | none     |           106 |        43.8533 |               1.7398 |               -7.3536 |                    1.6426 |                     1.9015 |               1.6889 |               0      |         0      | post_filter_only |
| uni__dir_trend20_atr_le_neg4      | univariate       | dir_trend20_atr_le_neg4      | none     |           196 |        66.5706 |               1.523  |              -13      |                    1.3803 |                     1.9651 |               1.3323 |               0.7143 |        -8.4318 | post_filter_only |
| uni__atr_ratio_5_20_le_1p2        | univariate       | atr_ratio_5_20_le_1p2        | none     |           694 |       182.423  |               1.4163 |              -33.3027 |                    1.3018 |                     1.6752 |               1.1933 |               0.8    |       -14.3394 | post_filter_only |
| uni__abs_trend5_atr_ge_3          | univariate       | abs_trend5_atr_ge_3          | none     |            52 |         7.1046 |               1.2153 |              -10.968  |                    1.7758 |                     0.6197 |               2.2935 |               0      |         0      | post_filter_only |
| uni__abs_opening_drive_atr_ge_0p5 | univariate       | abs_opening_drive_atr_ge_0p5 | none     |            31 |        12.4154 |               1.6208 |               -4      |                    2.0286 |                     1.2129 |               1.6279 |               0      |         0      | post_filter_only |
| uni__abs_trend5_atr_ge_1          | univariate       | abs_trend5_atr_ge_1          | none     |           481 |       115.606  |               1.3759 |              -19.7956 |                    1.2484 |                     1.6241 |               1.122  |               0.75   |        -9.3249 | post_filter_only |
| uni__atr_pct_price_le_0p02        | univariate       | atr_pct_price_le_0p02        | none     |           660 |       155.86   |               1.3718 |              -23.8122 |                    1.2173 |                     1.6539 |               1.1941 |               0.7778 |        -8.7042 | post_filter_only |
| uni__abs_trend20_atr_ge_4         | univariate       | abs_trend20_atr_ge_4         | none     |           277 |       102.868  |               1.5868 |              -17.7013 |                    1.3319 |                     2.3462 |               1.2807 |               0.8    |        -8.7013 | post_filter_only |
| uni__opening_efficiency_ge_0p4    | univariate       | opening_efficiency_ge_0p4    | none     |           363 |       113.481  |               1.5178 |              -21.1694 |                    1.3454 |                     1.8829 |               1.3341 |               0.7222 |       -16.2374 | post_filter_only |

Qualified rows:

| candidate_id                                               | candidate_type   | gate_1                     | gate_2                       |   full_trades |   full_total_r |   full_profit_factor |   full_max_drawdown_r |   discovery_profit_factor |   validation_profit_factor |   cold_profit_factor |   positive_fold_rate |   worst_fold_r | deployability    |
|:-----------------------------------------------------------|:-----------------|:---------------------------|:-----------------------------|--------------:|---------------:|---------------------:|----------------------:|--------------------------:|---------------------------:|---------------------:|---------------------:|---------------:|:-----------------|
| pair__opening_efficiency_ge_0p25__atr_pct_price_le_0p02    | pair             | opening_efficiency_ge_0p25 | atr_pct_price_le_0p02        |           452 |       140.284  |               1.5116 |              -13.6977 |                    1.4243 |                     1.6676 |               1.3199 |               0.7778 |        -6.1448 | post_filter_only |
| pair__opening_efficiency_ge_0p25__abs_trend20_atr_ge_4     | pair             | opening_efficiency_ge_0p25 | abs_trend20_atr_ge_4         |           194 |        83.8163 |               1.7026 |              -11      |                    1.5915 |                     2.0183 |               1.4704 |               0.75   |        -3.3665 | post_filter_only |
| pair__opening_efficiency_ge_0p25__overnight_range_atr_le_1 | pair             | opening_efficiency_ge_0p25 | overnight_range_atr_le_1     |           493 |       152.531  |               1.5031 |              -17.5936 |                    1.3906 |                     1.7602 |               1.2895 |               0.8    |        -8.3141 | post_filter_only |
| pair__opening_efficiency_ge_0p25__abs_trend5_atr_ge_1      | pair             | opening_efficiency_ge_0p25 | abs_trend5_atr_ge_1          |           314 |        88.179  |               1.4603 |              -12.0211 |                    1.456  |                     1.4681 |               1.2676 |               0.6875 |        -7.8612 | post_filter_only |
| pair__atr_pct_price_le_0p02__abs_opening_drive_atr_ge_0p1  | pair             | atr_pct_price_le_0p02      | abs_opening_drive_atr_ge_0p1 |           392 |       141.671  |               1.5978 |              -18.6977 |                    1.4902 |                     1.8089 |               1.3867 |               0.7222 |       -13      | post_filter_only |
| pair__atr_ratio_5_20_le_1p2__dir_gap_atr_ge_neg0p5         | pair             | atr_ratio_5_20_le_1p2      | dir_gap_atr_ge_neg0p5        |           603 |       169.337  |               1.4514 |              -27.4474 |                    1.4144 |                     1.5412 |               1.3191 |               0.85   |       -10.3394 | post_filter_only |
| uni__opening_efficiency_ge_0p25                            | univariate       | opening_efficiency_ge_0p25 | none                         |           543 |       160.171  |               1.475  |              -18.4498 |                    1.32   |                     1.8115 |               1.2368 |               0.7    |        -8.3141 | post_filter_only |
| pair__opening_efficiency_ge_0p25__atr_ratio_5_20_le_1p2    | pair             | opening_efficiency_ge_0p25 | atr_ratio_5_20_le_1p2        |           474 |       139.189  |               1.4796 |              -20.3361 |                    1.3945 |                     1.671  |               1.3031 |               0.75   |        -5.5269 | post_filter_only |
| uni__opening_efficiency_ge_0p55                            | univariate       | opening_efficiency_ge_0p55 | none                         |           216 |       100.002  |               1.8455 |               -9.8598 |                    1.5174 |                     2.394  |               1.4271 |               0.9    |        -5.057  | post_filter_only |
| pair__abs_trend20_atr_ge_4__dir_gap_atr_ge_neg0p5          | pair             | abs_trend20_atr_ge_4       | dir_gap_atr_ge_neg0p5        |           242 |        76.7344 |               1.4943 |              -14      |                    1.4333 |                     1.6702 |               1.367  |               0.8333 |        -4.7013 | post_filter_only |
| pair__atr_ratio_5_20_le_1p2__overnight_range_atr_le_1      | pair             | atr_ratio_5_20_le_1p2      | overnight_range_atr_le_1     |           641 |       174.567  |               1.4351 |              -30.0007 |                    1.3757 |                     1.574  |               1.2616 |               0.75   |       -11.3394 | post_filter_only |
| pair__atr_pct_price_le_0p02__overnight_range_atr_le_1      | pair             | atr_pct_price_le_0p02      | overnight_range_atr_le_1     |           595 |       144.31   |               1.3867 |              -20.5102 |                    1.29   |                     1.5735 |               1.2691 |               0.7222 |        -5.7042 | post_filter_only |
| pair__atr_ratio_5_20_le_1p2__atr_pct_price_le_0p02         | pair             | atr_ratio_5_20_le_1p2      | atr_pct_price_le_0p02        |           579 |       155.559  |               1.4342 |              -22.4473 |                    1.3209 |                     1.6501 |               1.2784 |               0.8333 |        -6.7042 | post_filter_only |
| pair__opening_efficiency_ge_0p25__dir_gap_atr_ge_neg0p5    | pair             | opening_efficiency_ge_0p25 | dir_gap_atr_ge_neg0p5        |           470 |       131.005  |               1.453  |              -22.3329 |                    1.3636 |                     1.6669 |               1.2918 |               0.8    |        -5.3141 | post_filter_only |
| pair__atr_ratio_5_20_le_1p2__abs_trend20_atr_ge_4          | pair             | atr_ratio_5_20_le_1p2      | abs_trend20_atr_ge_4         |           248 |        96.1858 |               1.6234 |              -16      |                    1.4443 |                     2.1012 |               1.4036 |               0.8462 |        -5.7013 | post_filter_only |

## Finalists And Stability

| candidate_id                                            | candidate_type   | gate_1                     | gate_2                |   full_trades |   full_total_r |   full_profit_factor |   full_max_drawdown_r |   discovery_profit_factor |   validation_profit_factor |   cold_profit_factor |   positive_fold_rate |   worst_fold_r | deployability    |   neighbors |   passing_neighbors |   plateau_score |
|:--------------------------------------------------------|:-----------------|:---------------------------|:----------------------|--------------:|---------------:|---------------------:|----------------------:|--------------------------:|---------------------------:|---------------------:|---------------------:|---------------:|:-----------------|------------:|--------------------:|----------------:|
| uni__opening_efficiency_ge_0p55                         | univariate       | opening_efficiency_ge_0p55 | none                  |           216 |       100.002  |               1.8455 |               -9.8598 |                    1.5174 |                     2.394  |               1.4271 |               0.9    |        -5.057  | post_filter_only |           3 |                   3 |          1      |
| pair__opening_efficiency_ge_0p25__atr_pct_price_le_0p02 | pair             | opening_efficiency_ge_0p25 | atr_pct_price_le_0p02 |           452 |       140.284  |               1.5116 |              -13.6977 |                    1.4243 |                     1.6676 |               1.3199 |               0.7778 |        -6.1448 | post_filter_only |           4 |                   4 |          1      |
| pair__opening_efficiency_ge_0p25__abs_trend20_atr_ge_4  | pair             | opening_efficiency_ge_0p25 | abs_trend20_atr_ge_4  |           194 |        83.8163 |               1.7026 |              -11      |                    1.5915 |                     2.0183 |               1.4704 |               0.75   |        -3.3665 | post_filter_only |           6 |                   4 |          0.6667 |

## 1s Friction Stress

| candidate_id                                            |   slippage_ticks_per_side |   trades |   total_r |   avg_r |   profit_factor |   max_drawdown_r | deployability    |
|:--------------------------------------------------------|--------------------------:|---------:|----------:|--------:|----------------:|-----------------:|:-----------------|
| uni__opening_efficiency_ge_0p55                         |                         0 |      216 |   79.797  |  0.3694 |          1.6047 |         -15.655  | post_filter_only |
| uni__opening_efficiency_ge_0p55                         |                         1 |      216 |   61.4415 |  0.2845 |          1.4265 |         -22.8685 | post_filter_only |
| uni__opening_efficiency_ge_0p55                         |                         2 |      216 |   43.086  |  0.1995 |          1.2757 |         -36.3111 | post_filter_only |
| pair__opening_efficiency_ge_0p25__atr_pct_price_le_0p02 |                         0 |      452 |   92.3244 |  0.2043 |          1.3    |         -27.5883 | post_filter_only |
| pair__opening_efficiency_ge_0p25__atr_pct_price_le_0p02 |                         1 |      452 |   49.9065 |  0.1104 |          1.1481 |         -54.1798 | post_filter_only |
| pair__opening_efficiency_ge_0p25__atr_pct_price_le_0p02 |                         2 |      452 |    7.4886 |  0.0166 |          1.0204 |         -83.9472 | post_filter_only |
| pair__opening_efficiency_ge_0p25__abs_trend20_atr_ge_4  |                         0 |      194 |   61.6959 |  0.318  |          1.4595 |         -14.3327 | post_filter_only |
| pair__opening_efficiency_ge_0p25__abs_trend20_atr_ge_4  |                         1 |      194 |   42.4633 |  0.2189 |          1.2881 |         -20.5194 | post_filter_only |
| pair__opening_efficiency_ge_0p25__abs_trend20_atr_ge_4  |                         2 |      194 |   23.2308 |  0.1197 |          1.1446 |         -36.0416 | post_filter_only |

## Block Bootstrap

| candidate_id                                            |   iterations |   total_r_p05 |   total_r_median |   total_r_p95 |   max_dd_r_p05 |   max_dd_r_median |   prob_total_r_positive |   prob_dd_worse_than_20r | deployability    |
|:--------------------------------------------------------|-------------:|--------------:|-----------------:|--------------:|---------------:|------------------:|------------------------:|-------------------------:|:-----------------|
| uni__opening_efficiency_ge_0p55                         |         5000 |         13.34 |            61.25 |        115.14 |         -29.01 |            -15.61 |                  0.9824 |                   0.2376 | post_filter_only |
| pair__opening_efficiency_ge_0p25__atr_pct_price_le_0p02 |         5000 |        -24.38 |            50.34 |        130.55 |         -64.47 |            -33.6  |                  0.8652 |                   0.9372 | post_filter_only |
| pair__opening_efficiency_ge_0p25__abs_trend20_atr_ge_4  |         5000 |        -16.04 |            41.92 |        104.77 |         -44.49 |            -22.71 |                  0.886  |                   0.6218 | post_filter_only |

## Lead Challenger Segments

These segments use the 1s path with MNQ midpoint commission and one adverse tick per side.

| segment         |   trades |   total_r |   avg_r |   profit_factor |   max_drawdown_r |   negative_years | deployability    |
|:----------------|---------:|----------:|--------:|----------------:|-----------------:|-----------------:|:-----------------|
| direction_long  |       73 |   24.9319 |  0.3415 |          1.6126 |          -7.4379 |                4 | post_filter_only |
| direction_short |      143 |   36.5096 |  0.2553 |          1.3532 |         -25.0591 |                6 | post_filter_only |
| year_2016       |       23 |   -1.039  | -0.0452 |          0.9457 |          -7.432  |                1 | post_filter_only |
| year_2017       |       32 |  -12.568  | -0.3928 |          0.5553 |         -16.1049 |                1 | post_filter_only |
| year_2018       |       13 |   -1.82   | -0.14   |          0.837  |          -5.182  |                1 | post_filter_only |
| year_2019       |       22 |    4.9313 |  0.2242 |          1.3564 |          -5.1994 |                0 | post_filter_only |
| year_2020       |       15 |   -1.6735 | -0.1116 |          0.8556 |          -9.4037 |                1 | post_filter_only |
| year_2021       |       10 |   13.7026 |  1.3703 |          5.1769 |          -1.0985 |                0 | post_filter_only |
| year_2022       |       15 |    4.132  |  0.2755 |          1.4862 |          -4.7213 |                0 | post_filter_only |
| year_2023       |       30 |   28.7959 |  0.9599 |          2.6994 |          -5.651  |                0 | post_filter_only |
| year_2024       |       25 |   22.8242 |  0.913  |          2.7432 |          -3.2956 |                0 | post_filter_only |
| year_2025       |       21 |    1.921  |  0.0915 |          1.1605 |          -6.8632 |                0 | post_filter_only |
| year_2026       |       10 |    2.235  |  0.2235 |          1.3549 |          -2.5408 |                0 | post_filter_only |

## Bailey Diagnostics

| candidate_id                                            |   psr_observed_sharpe |   psr_psr |   dsr_expected_max_sharpe |   dsr_dsr |   dsr_n_trials_raw |   dsr_n_trials_effective | pbo_cscv_implemented   | deployability    |
|:--------------------------------------------------------|----------------------:|----------:|--------------------------:|----------:|-------------------:|-------------------------:|:-----------------------|:-----------------|
| uni__opening_efficiency_ge_0p55                         |                2.1677 |    0.9891 |                    2.4726 |    0.3734 |                155 |                       51 | False                  | post_filter_only |
| pair__opening_efficiency_ge_0p25__atr_pct_price_le_0p02 |                0.8498 |    0.8858 |                    1.7072 |    0.1121 |                155 |                       51 | False                  | post_filter_only |
| pair__opening_efficiency_ge_0p25__abs_trend20_atr_ge_4  |                1.3904 |    0.9155 |                    2.6097 |    0.1139 |                155 |                       51 | False                  | post_filter_only |

## Promotion Decision

| candidate_id                                            | verdict    | qualified_structural_gate   | plateau_pass   | friction_pass   | bootstrap_pass   | dsr_pass   | future_holdout_required   | deployability    |
|:--------------------------------------------------------|:-----------|:----------------------------|:---------------|:----------------|:-----------------|:-----------|:--------------------------|:-----------------|
| uni__opening_efficiency_ge_0p55                         | CHALLENGER | True                        | True           | True            | True             | False      | yes                       | post_filter_only |
| pair__opening_efficiency_ge_0p25__atr_pct_price_le_0p02 | CHALLENGER | True                        | True           | False           | False            | False      | yes                       | post_filter_only |
| pair__opening_efficiency_ge_0p25__abs_trend20_atr_ge_4  | CHALLENGER | True                        | True           | True            | False            | False      | yes                       | post_filter_only |

- Promoted candidates: `0`.
- A PROMOTE verdict means only that a frozen gate deserves the next research phase. It does not authorize deployment, and every candidate still requires the future holdout, a live pre-trade implementation, and exact replay.

## Artifacts

- `baseline_controls.csv`: `backtesting/data/results/nq_ny_vwap_selective_regime_discovery_20260710/baseline_controls.csv`
- `day_mid_full_trades_with_features.csv`: `backtesting/data/results/nq_ny_vwap_selective_regime_discovery_20260710/day_mid_full_trades_with_features.csv`
- `feature_bin_diagnostics.csv`: `backtesting/data/results/nq_ny_vwap_selective_regime_discovery_20260710/feature_bin_diagnostics.csv`
- `univariate_gate_results.csv`: `backtesting/data/results/nq_ny_vwap_selective_regime_discovery_20260710/univariate_gate_results.csv`
- `pair_gate_results.csv`: `backtesting/data/results/nq_ny_vwap_selective_regime_discovery_20260710/pair_gate_results.csv`
- `fixed_six_month_folds.csv`: `backtesting/data/results/nq_ny_vwap_selective_regime_discovery_20260710/fixed_six_month_folds.csv`
- `qualified_candidates.csv`: `backtesting/data/results/nq_ny_vwap_selective_regime_discovery_20260710/qualified_candidates.csv`
- `finalists.csv`: `backtesting/data/results/nq_ny_vwap_selective_regime_discovery_20260710/finalists.csv`
- `local_stability.csv`: `backtesting/data/results/nq_ny_vwap_selective_regime_discovery_20260710/local_stability.csv`
- `finalist_friction.csv`: `backtesting/data/results/nq_ny_vwap_selective_regime_discovery_20260710/finalist_friction.csv`
- `finalist_1s_trades.csv`: `backtesting/data/results/nq_ny_vwap_selective_regime_discovery_20260710/finalist_1s_trades.csv`
- `finalist_segment_summary.csv`: `backtesting/data/results/nq_ny_vwap_selective_regime_discovery_20260710/finalist_segment_summary.csv`
- `finalist_bootstrap.csv`: `backtesting/data/results/nq_ny_vwap_selective_regime_discovery_20260710/finalist_bootstrap.csv`
- `finalist_psr_dsr.csv`: `backtesting/data/results/nq_ny_vwap_selective_regime_discovery_20260710/finalist_psr_dsr.csv`
- `promotion_verdicts.csv`: `backtesting/data/results/nq_ny_vwap_selective_regime_discovery_20260710/promotion_verdicts.csv`
- `summary.json`: `backtesting/data/results/nq_ny_vwap_selective_regime_discovery_20260710/summary.json`
