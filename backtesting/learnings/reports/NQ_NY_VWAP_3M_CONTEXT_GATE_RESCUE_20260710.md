# NQ NY VWAP 3m Context-Gate Rescue

- Run slug: `nq_ny_vwap_3m_context_gate_rescue_20260710`
- Track: **TRACK 1 of 4** - can context gates rescue the frozen NQ NY 3m VWAP mean-reversion leg?
- Data: `2021-06-07` through `<2026-06-06` (`1293` NY RTH days), parity-audited 3m signal stream.
- Frozen leg: 3m bars, VWAP mean, 2.5% prior-ATR extension, 30-minute consolidation (<=20% ATR range), sweep/reclaim, next-bar entry, 7.5% prior-ATR even-tick stop, fixed 1.5R target, max 3 trades/day, flat 15:55.
- Friction: integer MNQ sizing, `$0.575`/side commission, adverse slippage `0/1/2/4` ticks/side. Grid metrics use native 3m fills at 1 tick/side; finalists are re-checked on 1s path replay.
- VWAP-slope adaptation: 3m slope over the trailing **10 bars (30 minutes)** with the same **0.02-ATR** rejection threshold, the time-normalized analogue of the 5m 6-bar/30-minute slope.
- Deployability: `research_only`. The 3m VWAP sweep/reclaim state machine, native-timeframe static-R exit, and these context gates are research-script only; the live execution engine cannot arm this setup yet.

## Baseline Parity Audit

- Regenerated frozen ungated stream: `1498` trades, `+82.1820R`.
- Saved champion: `1498` trades, `+82.1820R`.
- Delta: trades `0`, R `+0.000000`; parity **PASS**.

## Context-Gate Grid (top 5 per scope, ranked by friction-adjusted Calmar)

Grid = `vwap_acceptance{none, slope}` x `efficiency_max{none,0.45,0.55,0.65,0.70}` x `time_bucket{full,10-12,10-14,11-15}` x `session_range_atr_max{2.0,1.5,none}` = 120 contexts, scored per direction scope. `total_r` is after MNQ commission + 1 adverse tick/side on native 3m fills; `gross_total_r` is pre-friction.

|   rank | direction_scope   | context_label                       | vwap_acceptance        |   efficiency_max | time_bucket   |   session_range_atr_max |   total_trades |   avg_trades_per_day |   gross_total_r |   total_r |   profit_factor |   calmar |   max_drawdown_r |   t_stat | deployability   |
|-------:|:------------------|:------------------------------------|:-----------------------|-----------------:|:--------------|------------------------:|---------------:|---------------------:|----------------:|----------:|----------------:|---------:|-----------------:|---------:|:----------------|
|      1 | both              | noslope_eff0.45_t10:00-14:00_sr1.5  | none                   |             0.45 | 10:00-14:00   |                     1.5 |            334 |               0.2583 |         78.801  |   58.9661 |          1.3363 |   0.7543 |         -15.2359 |   2.6072 | research_only   |
|      2 | both              | noslope_eff0.45_t10:00-14:00_sr2    | none                   |             0.45 | 10:00-14:00   |                     2   |            338 |               0.2614 |         82.301  |   62.2    |          1.3525 |   0.743  |         -16.3156 |   2.7333 | research_only   |
|      3 | both              | noslope_eff0.45_t10:00-14:00_srnone | none                   |             0.45 | 10:00-14:00   |                   nan   |            338 |               0.2614 |         82.301  |   62.2    |          1.3525 |   0.743  |         -16.3156 |   2.7333 | research_only   |
|      4 | both              | noslope_eff0.55_t10:00-14:00_sr1.5  | none                   |             0.55 | 10:00-14:00   |                     1.5 |            460 |               0.3558 |         90.1925 |   63.0368 |          1.2523 |   0.7041 |         -17.4493 |   2.3747 | research_only   |
|      5 | both              | noslope_eff0.55_t10:00-14:00_sr2    | none                   |             0.55 | 10:00-14:00   |                     2   |            464 |               0.3589 |         93.6925 |   66.2706 |          1.2641 |   0.6971 |         -18.5289 |   2.485  | research_only   |
|      1 | long_only         | noslope_eff0.65_t10:00-14:00_sr1.5  | none                   |             0.65 | 10:00-14:00   |                     1.5 |            204 |               0.1578 |         60.4782 |   48.7442 |          1.4824 |   1.5648 |          -6.0712 |   2.7648 | research_only   |
|      2 | long_only         | noslope_eff0.65_t10:00-14:00_sr2    | none                   |             0.65 | 10:00-14:00   |                     2   |            207 |               0.1601 |         59.9782 |   48.0025 |          1.4651 |   1.541  |          -6.0712 |   2.7016 | research_only   |
|      3 | long_only         | noslope_eff0.65_t10:00-14:00_srnone | none                   |             0.65 | 10:00-14:00   |                   nan   |            207 |               0.1601 |         59.9782 |   48.0025 |          1.4651 |   1.541  |          -6.0712 |   2.7016 | research_only   |
|      4 | long_only         | noslope_eff0.7_t10:00-14:00_sr2     | none                   |             0.7  | 10:00-14:00   |                     2   |            238 |               0.1841 |         62.4782 |   48.7523 |          1.4023 |   1.249  |          -7.6075 |   2.5596 | research_only   |
|      5 | long_only         | noslope_eff0.7_t10:00-14:00_srnone  | none                   |             0.7  | 10:00-14:00   |                   nan   |            238 |               0.1841 |         62.4782 |   48.7523 |          1.4023 |   1.249  |          -7.6075 |   2.5596 | research_only   |
|      1 | short_only        | slope_eff0.45_t10:00-14:00_sr1.5    | reject_vwap_side_slope |             0.45 | 10:00-14:00   |                     1.5 |            154 |               0.1191 |         34.4358 |   25.0072 |          1.3086 |   0.3629 |         -13.4283 |   1.6341 | research_only   |
|      2 | short_only        | slope_eff0.45_t10:00-14:00_sr2      | reject_vwap_side_slope |             0.45 | 10:00-14:00   |                     2   |            156 |               0.1206 |         34.9358 |   25.3776 |          1.3091 |   0.3409 |         -14.5079 |   1.6471 | research_only   |
|      3 | short_only        | slope_eff0.45_t10:00-14:00_srnone   | reject_vwap_side_slope |             0.45 | 10:00-14:00   |                   nan   |            156 |               0.1206 |         34.9358 |   25.3776 |          1.3091 |   0.3409 |         -14.5079 |   1.6471 | research_only   |
|      4 | short_only        | slope_eff0.55_t10:00-14:00_sr1.5    | reject_vwap_side_slope |             0.55 | 10:00-14:00   |                     1.5 |            210 |               0.1624 |         37.9358 |   25.3413 |          1.2207 |   0.3378 |         -14.6229 |   1.4172 | research_only   |
|      5 | short_only        | slope_eff0.55_t10:00-14:00_sr2      | reject_vwap_side_slope |             0.55 | 10:00-14:00   |                     2   |            212 |               0.164  |         38.4358 |   25.7116 |          1.2218 |   0.3191 |         -15.7025 |   1.4307 | research_only   |

Frozen ungated reference rows (the DEFER baseline from the validation packet):

|   rank | direction_scope   | context_label             | vwap_acceptance   |   efficiency_max | time_bucket   |   session_range_atr_max |   total_trades |   avg_trades_per_day |   gross_total_r |   total_r |   profit_factor |   calmar |   max_drawdown_r |   t_stat | deployability   |
|-------:|:------------------|:--------------------------|:------------------|-----------------:|:--------------|------------------------:|---------------:|---------------------:|----------------:|----------:|----------------:|---------:|-----------------:|---------:|:----------------|
|    112 | both              | noslope_effnone_tfull_sr2 | none              |              nan | full          |                       2 |           1498 |               1.1585 |         82.182  |    -5.156 |          0.9943 |  -0.0251 |         -39.9577 |  -0.1094 | research_only   |
|    100 | long_only         | noslope_effnone_tfull_sr2 | none              |              nan | full          |                       2 |            497 |               0.3844 |         64.5394 |    36.939 |          1.1305 |   0.3176 |         -22.669  |   1.3427 | research_only   |
|    112 | short_only        | noslope_effnone_tfull_sr2 | none              |              nan | full          |                       2 |           1001 |               0.7742 |         17.6426 |   -42.095 |          0.9315 |  -0.1295 |         -63.3742 |  -1.1005 | research_only   |

## Short-Side Asymmetry Probe

Short-only, sweeping extension `{0.025,0.05,0.075}` x consolidation `{0.15,0.20}` under an ungated and a gated context (net of commission + 1 tick/side):

| probe_context                |   extension_atr_pct |   consolidation_atr_pct |   total_trades |   avg_trades_per_day |   total_r |   profit_factor |   calmar |   max_drawdown_r |   t_stat | deployability   |
|:-----------------------------|--------------------:|------------------------:|---------------:|---------------------:|----------:|----------------:|---------:|-----------------:|---------:|:----------------|
| gated_slope_eff55_t1014_sr15 |               0.05  |                    0.2  |            207 |               0.1601 |   24.379  |          1.2143 |   0.3506 |         -13.5536 |   1.3706 | research_only   |
| gated_slope_eff55_t1014_sr15 |               0.025 |                    0.2  |            210 |               0.1624 |   25.3413 |          1.2207 |   0.3378 |         -14.6229 |   1.4172 | research_only   |
| gated_slope_eff55_t1014_sr15 |               0.075 |                    0.2  |            192 |               0.1485 |   19.0006 |          1.1754 |   0.2636 |         -14.0476 |   1.1025 | research_only   |
| gated_slope_eff55_t1014_sr15 |               0.025 |                    0.15 |            147 |               0.1137 |   -2.6801 |          0.9696 |  -0.0222 |         -23.4949 |  -0.1825 | research_only   |
| gated_slope_eff55_t1014_sr15 |               0.05  |                    0.15 |            145 |               0.1121 |   -4.7118 |          0.9466 |  -0.0381 |         -24.0879 |  -0.3227 | research_only   |
| gated_slope_eff55_t1014_sr15 |               0.075 |                    0.15 |            136 |               0.1052 |   -6.4677 |          0.9238 |  -0.0445 |         -28.3563 |  -0.4538 | research_only   |
| ungated_sr2_full             |               0.025 |                    0.2  |           1001 |               0.7742 |  -42.095  |          0.9315 |  -0.1295 |         -63.3742 |  -1.1005 | research_only   |
| ungated_sr2_full             |               0.05  |                    0.2  |            994 |               0.7688 |  -43.4271 |          0.9289 |  -0.1305 |         -64.8492 |  -1.1394 | research_only   |
| ungated_sr2_full             |               0.025 |                    0.15 |            709 |               0.5483 |  -48.2837 |          0.89   |  -0.1317 |         -71.4352 |  -1.5166 | research_only   |
| ungated_sr2_full             |               0.075 |                    0.15 |            688 |               0.5321 |  -47.4573 |          0.8891 |  -0.1349 |         -68.5433 |  -1.509  | research_only   |
| ungated_sr2_full             |               0.075 |                    0.2  |            975 |               0.7541 |  -47.9772 |          0.9204 |  -0.1373 |         -68.0822 |  -1.2698 | research_only   |
| ungated_sr2_full             |               0.05  |                    0.15 |            702 |               0.5429 |  -49.9026 |          0.8854 |  -0.1394 |         -69.7506 |  -1.5757 | research_only   |

## Finalists: Frozen-Config Walk-Forward, 1s Friction, Year Splits

Top gated candidates (>=150 trades, PF>=1.0, ranked by friction-adjusted Calmar). Survivor gate: 1s friction-adjusted (1 tick) total R > 0, frozen-config WF OOS R > 0 with >=4/6 positive folds, no single year eating the whole edge.

| context_label                      | direction_scope   |   total_trades |   avg_trades_per_day |   gross_total_r |   net_r_1t_total_r |   path_1s_net_r_1t_total |   profit_factor |   calmar |   max_drawdown_r |   t_stat |   wf_positive_folds |   wf_oos_total_r |   worst_year_net_r_1t | survivor   | deployability   |
|:-----------------------------------|:------------------|---------------:|---------------------:|----------------:|-------------------:|-------------------------:|----------------:|---------:|-----------------:|---------:|--------------------:|-----------------:|----------------------:|:-----------|:----------------|
| noslope_eff0.65_t10:00-14:00_sr1.5 | long_only         |            204 |               0.1578 |         60.4782 |            48.7442 |                  48.7234 |          1.4824 |   1.5648 |          -6.0712 |   2.7648 |                   5 |          18.6941 |               -2.5281 | True       | research_only   |
| noslope_eff0.7_t10:00-14:00_sr2    | long_only         |            238 |               0.1841 |         62.4782 |            48.7523 |                  48.7315 |          1.4023 |   1.249  |          -7.6075 |   2.5596 |                   4 |          21.0373 |                0.1018 | True       | research_only   |
| slope_eff0.7_t10:00-14:00_sr2      | long_only         |            151 |               0.1168 |         49.5068 |            40.4705 |                  40.4497 |          1.5648 |   1.1448 |          -6.89   |   2.6914 |                   4 |          14.1301 |               -2.5231 | True       | research_only   |

### Rolling walk-forward folds (frozen-config, 6 folds, net 1 tick/side)

| context_label                      | direction_scope   | test_start   | test_end_exclusive   |   test_trades |   test_total_r |   test_pf |   test_dd_r |
|:-----------------------------------|:------------------|:-------------|:---------------------|--------------:|---------------:|----------:|------------:|
| noslope_eff0.65_t10:00-14:00_sr1.5 | long_only         | 2023-01-01   | 2023-07-01           |            26 |         7.8854 |    1.6476 |     -2.855  |
| noslope_eff0.65_t10:00-14:00_sr1.5 | long_only         | 2023-07-01   | 2024-01-01           |            25 |         9.1804 |    1.8531 |     -3.9555 |
| noslope_eff0.65_t10:00-14:00_sr1.5 | long_only         | 2024-01-01   | 2024-07-01           |            20 |         0.1464 |    1.0124 |     -4.2996 |
| noslope_eff0.65_t10:00-14:00_sr1.5 | long_only         | 2024-07-01   | 2025-01-01           |            12 |        -2.6745 |    0.685  |     -4.2544 |
| noslope_eff0.65_t10:00-14:00_sr1.5 | long_only         | 2025-01-01   | 2025-07-01           |            17 |         3.8954 |    1.4656 |     -4.227  |
| noslope_eff0.65_t10:00-14:00_sr1.5 | long_only         | 2025-07-01   | 2026-01-01           |            14 |         0.261  |    1.031  |     -3.3537 |
| noslope_eff0.7_t10:00-14:00_sr2    | long_only         | 2023-01-01   | 2023-07-01           |            27 |         6.8182 |    1.5148 |     -2.855  |
| noslope_eff0.7_t10:00-14:00_sr2    | long_only         | 2023-07-01   | 2024-01-01           |            32 |        12.6981 |    1.9805 |     -4.9486 |
| noslope_eff0.7_t10:00-14:00_sr2    | long_only         | 2024-01-01   | 2024-07-01           |            24 |         5.923  |    1.5028 |     -4.2996 |
| noslope_eff0.7_t10:00-14:00_sr2    | long_only         | 2024-07-01   | 2025-01-01           |            15 |        -5.8211 |    0.4998 |     -5.8211 |
| noslope_eff0.7_t10:00-14:00_sr2    | long_only         | 2025-01-01   | 2025-07-01           |            19 |         1.8017 |    1.1722 |     -4.227  |
| noslope_eff0.7_t10:00-14:00_sr2    | long_only         | 2025-07-01   | 2026-01-01           |            17 |        -0.3826 |    0.9636 |     -3.3395 |
| slope_eff0.7_t10:00-14:00_sr2      | long_only         | 2023-01-01   | 2023-07-01           |            16 |         6.03   |    1.8828 |     -2.1198 |
| slope_eff0.7_t10:00-14:00_sr2      | long_only         | 2023-07-01   | 2024-01-01           |            20 |        10.5803 |    2.6163 |     -3.2454 |
| slope_eff0.7_t10:00-14:00_sr2      | long_only         | 2024-01-01   | 2024-07-01           |            20 |         0.1515 |    1.0129 |     -4.9539 |
| slope_eff0.7_t10:00-14:00_sr2      | long_only         | 2024-07-01   | 2025-01-01           |            12 |        -2.6745 |    0.685  |     -4.2544 |
| slope_eff0.7_t10:00-14:00_sr2      | long_only         | 2025-01-01   | 2025-07-01           |            13 |         0.5712 |    1.0781 |     -2.1132 |
| slope_eff0.7_t10:00-14:00_sr2      | long_only         | 2025-07-01   | 2026-01-01           |            10 |        -0.5284 |    0.9163 |     -3.1899 |

### Finalist friction stress on 1s path replay

| context_label                      | direction_scope   |   slippage_ticks_per_side |   total_trades |   total_r |   avg_r |   profit_factor |   max_drawdown_r | deployability   |
|:-----------------------------------|:------------------|--------------------------:|---------------:|----------:|--------:|----------------:|-----------------:|:----------------|
| noslope_eff0.65_t10:00-14:00_sr1.5 | long_only         |                         0 |            204 |   54.1811 |  0.2656 |          1.5506 |          -5.5729 | research_only   |
| noslope_eff0.65_t10:00-14:00_sr1.5 | long_only         |                         1 |            204 |   48.7234 |  0.2388 |          1.4822 |          -6.0712 | research_only   |
| noslope_eff0.65_t10:00-14:00_sr1.5 | long_only         |                         2 |            204 |   43.2657 |  0.2121 |          1.4173 |          -6.8815 | research_only   |
| noslope_eff0.7_t10:00-14:00_sr2    | long_only         |                         0 |            238 |   55.1157 |  0.2316 |          1.467  |          -7.0592 | research_only   |
| noslope_eff0.7_t10:00-14:00_sr2    | long_only         |                         1 |            238 |   48.7315 |  0.2048 |          1.4021 |          -7.6075 | research_only   |
| noslope_eff0.7_t10:00-14:00_sr2    | long_only         |                         2 |            238 |   42.3474 |  0.1779 |          1.3405 |          -8.1557 | research_only   |
| slope_eff0.7_t10:00-14:00_sr2      | long_only         |                         0 |            151 |   44.6527 |  0.2957 |          1.6411 |          -6.2435 | research_only   |
| slope_eff0.7_t10:00-14:00_sr2      | long_only         |                         1 |            151 |   40.4497 |  0.2679 |          1.5645 |          -6.89   | research_only   |
| slope_eff0.7_t10:00-14:00_sr2      | long_only         |                         2 |            151 |   36.2468 |  0.24   |          1.4922 |          -7.5365 | research_only   |

### Finalist year-by-year (net 1 tick/side)

| context_label                      | direction_scope   |   year |   trades |   total_r |   avg_r |   win_rate |   profit_factor |
|:-----------------------------------|:------------------|-------:|---------:|----------:|--------:|-----------:|----------------:|
| noslope_eff0.65_t10:00-14:00_sr1.5 | long_only         |   2021 |       23 |   12.9226 |  0.5619 |     0.6522 |          2.516  |
| noslope_eff0.65_t10:00-14:00_sr1.5 | long_only         |   2022 |       51 |   11.4914 |  0.2253 |     0.5098 |          1.4554 |
| noslope_eff0.65_t10:00-14:00_sr1.5 | long_only         |   2023 |       51 |   17.0658 |  0.3346 |     0.549  |          1.744  |
| noslope_eff0.65_t10:00-14:00_sr1.5 | long_only         |   2024 |       32 |   -2.5281 | -0.079  |     0.4062 |          0.8753 |
| noslope_eff0.65_t10:00-14:00_sr1.5 | long_only         |   2025 |       31 |    4.1564 |  0.1341 |     0.4839 |          1.2478 |
| noslope_eff0.65_t10:00-14:00_sr1.5 | long_only         |   2026 |       16 |    5.6361 |  0.3523 |     0.5625 |          1.7724 |
| noslope_eff0.7_t10:00-14:00_sr2    | long_only         |   2021 |       27 |    8.5729 |  0.3175 |     0.5556 |          1.6659 |
| noslope_eff0.7_t10:00-14:00_sr2    | long_only         |   2022 |       58 |   14.13   |  0.2436 |     0.5172 |          1.4979 |
| noslope_eff0.7_t10:00-14:00_sr2    | long_only         |   2023 |       59 |   19.5163 |  0.3308 |     0.5424 |          1.7451 |
| noslope_eff0.7_t10:00-14:00_sr2    | long_only         |   2024 |       39 |    0.1018 |  0.0026 |     0.4359 |          1.0043 |
| noslope_eff0.7_t10:00-14:00_sr2    | long_only         |   2025 |       36 |    1.4191 |  0.0394 |     0.4444 |          1.0677 |
| noslope_eff0.7_t10:00-14:00_sr2    | long_only         |   2026 |       19 |    5.0121 |  0.2638 |     0.5263 |          1.5348 |
| slope_eff0.7_t10:00-14:00_sr2      | long_only         |   2021 |       19 |    7.0338 |  0.3702 |     0.5789 |          1.8179 |
| slope_eff0.7_t10:00-14:00_sr2      | long_only         |   2022 |       31 |   14.9229 |  0.4814 |     0.6129 |          2.286  |
| slope_eff0.7_t10:00-14:00_sr2      | long_only         |   2023 |       36 |   16.6103 |  0.4614 |     0.5833 |          2.2417 |
| slope_eff0.7_t10:00-14:00_sr2      | long_only         |   2024 |       32 |   -2.5231 | -0.0788 |     0.4062 |          0.8755 |
| slope_eff0.7_t10:00-14:00_sr2      | long_only         |   2025 |       23 |    0.0429 |  0.0019 |     0.4348 |          1.0031 |
| slope_eff0.7_t10:00-14:00_sr2      | long_only         |   2026 |       10 |    4.3838 |  0.4384 |     0.6    |          2.0521 |

## Noise / Deflation Read

- Configurations searched (grid scored rows + short probe rows): **372**.
- Best grid row: `noslope_eff0.65_t10:00-14:00_sr1.5` (long_only), t-stat `2.7648` (avg_r * sqrt(n) / std_r).
- Expected max |t| of the null over 372 searches ~ sqrt(2 ln N) = `3.4406`; best-over-expected ratio `0.8036`.
- The best row's t-stat does not exceed the expected maximum of the null under 372 searched configs; the top edge is plausibly selection noise.

## Summary Read

- **SURVIVOR FOUND: noslope_eff0.65_t10:00-14:00_sr1.5 (long_only).**
- The winning ingredients are the **directional-efficiency cap (0.55-0.70)** and the **10:00-14:00 entry bucket** on the **long side** - the same two levers that rescued the 5m branch. The `reject_vwap_side_slope` gate helps PF slightly but is not required, and `session_range_atr_max` is near-inert inside the mid-session buckets.
- **Frequency caveat:** the surviving long-only gate trades only ~`0.18`/day (~1 trade every 6-7 sessions vs the frozen leg's 1.16/day). It is a thin, highly selective filter, not the daily-cadence leg; sample size and deployability are correspondingly limited.
- **Deflation caveat:** the single best row's t-stat (`2.7648`) is below the expected max of the null over `372` searched configs (`3.4406`, ratio `0.8036`). One row alone is not distinguishable from best-of-noise; the supporting evidence is that a coherent neighborhood (efficiency 0.45-0.70 x 10:00-14:00, long and both) is jointly positive and clears 5/6 WF folds, which is harder to fake than a lone spike. Treat as a fragile low-frequency research candidate, not a robust edge.
- **Both-direction partial rescue:** the best gated both-direction row (`noslope_eff0.45_t10:00-14:00_sr1.5`) recovers to `+59.0R` net at PF `1.34`, Calmar `0.75`, `334` trades - a real improvement over the ungated `both` leg's `-5.2R`, but Calmar is roughly frozen-leg grade and it was not a Calmar top-3 finalist. The short side stays the drag (see probe).
- All rows are `research_only`; nothing here authorizes live implementation. The exact gate parameters of the top survivor are handed to the follow-up limit-entry/cost track.

## Artifacts

- Results: `backtesting/data/results/nq_ny_vwap_3m_context_gate_rescue_20260710/`
- Report: `backtesting/learnings/reports/NQ_NY_VWAP_3M_CONTEXT_GATE_RESCUE_20260710.md`
