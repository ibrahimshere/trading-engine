# NQ NY ORB Failure Fade — First-Pass Discovery Screen

- Run slug: `nq_ny_orb_failure_fade_discovery_20260710`
- Thesis: fade FAILED opening-range breakouts back toward the range. Short a failed upside breakout, long a failed downside breakout. TRACK 3 of a 4-track NQ research program; the mirror of the exhaustively-mapped NY ORB continuation.
- Instrument/session: NQ, NY RTH (09:30 anchor, US Eastern). Signal timeframes 5m (primary) and 3m (variant), resampled from raw 1m.
- Discovery window (grid search only): `2021-06-07` .. `2024-12-31` (924 5m days / 924 3m days).
- Validation window (single-shot, frozen shortlist only): `2025-01-01` .. `2026-06-05`.
- Cold window (single-shot regime stress, frozen shortlist only): `2016-01-01` .. `2021-06-05`.
- Intrabar path: entries on the NEXT bar open after the signal bar completes (no lookahead); stop wins on a same-bar stop/target touch; flat by 15:55 ET.
- Guards: max 2 trades/day, one position at a time (+1-bar cooldown), `session_range_atr_max=2.0`, min stop 4 ticks.
- Friction: MNQ sizing, $0.575/side commission, 1 and 2 ticks/side slippage. All rows `deployability=research_only`.

## Entry Criteria (written out precisely)

Opening range: the high and low of NY RTH bars with time `< 09:45` (15m ORB) or `< 10:00` (30m ORB). ORB mid = (ORB high + ORB low) / 2. Breakout scanning begins on the first bar after the ORB window.

Failed UPSIDE breakout (fade SHORT):
1. A bar's high reaches `ORB_high + breakout_frac * atr14_prev` (breakout leg). `atr14_prev` is the prior 14-day mean RTH range.
2. Within `N` signal-timeframe bars of that breakout bar, a bar CLOSES back inside the range: `close < ORB_high - reentry_buffer_frac * atr14_prev` (the failure trigger / signal bar).
3. Enter SHORT on the next bar's open (no lookahead).
4. Stop: either just beyond the breakout extreme (highest high from breakout through signal) plus `0.05 * atr14_prev`, or a fixed `stop_param * atr14_prev` ATR-fraction stop. Risk floored at 4 ticks.
5. Target: fixed 1.5R, or ORB mid, or the opposite ORB edge (ORB low).
6. Signal must occur at/before the entry cutoff (12:00 or 13:00). Flat by 15:55.

Failed DOWNSIDE breakout (fade LONG) is the exact mirror: low reaches `ORB_low - breakout_frac*atr`, a bar closes back above `ORB_low + reentry_buffer_frac*atr` within N bars, enter LONG next open, stop below the breakout extreme (or ATR-fraction), target 1.5R / ORB mid / ORB high.

## Grid Searched

- Timeframes: `(5, 3)`; ORB windows: `['15m', '30m']`
- breakout_frac (* atr14_prev): `(0.0, 0.05, 0.1)`; failure N bars: `(2, 4, 8)`; reentry_buffer_frac: `(0.0, 0.02)`
- stop bases: `(('breakout_extreme', 0.05), ('atr_frac', 0.075), ('atr_frac', 0.1))`; targets: `('rr1p5', 'orb_mid', 'opp_edge')`; entry cutoffs: `('12:00', '13:00')`
- **Total configs searched: 1296.** Eligible (>=120 trades, 0.25-2.0 trades/day, PF>1): 122.

## ORB Level Sanity (5m 15m-ORB vs raw 1m)

```
2021-06-07: 5m-ORB H/L=13764.50/13720.75 vs raw-1m H/L=13764.50/13720.75 -> OK
2022-04-28: 5m-ORB H/L=13280.75/13117.00 vs raw-1m H/L=13280.75/13117.00 -> OK
2023-03-21: 5m-ORB H/L=12815.25/12774.00 vs raw-1m H/L=12815.25/12774.00 -> OK
2024-02-09: 5m-ORB H/L=17911.25/17875.00 vs raw-1m H/L=17911.25/17875.00 -> OK
```
- Per-day trade-cap check on the shortlist: PASS (no day exceeds the cap).
- Entry-after-signal check: enforced by assertion in the exit builder (entry_ts > signal_ts on every trade).

## Discovery — Top 20 by t-stat

|   rank | label                                                        |   timeframe | orb   |   breakout_frac |   n_bars |   reentry_buffer_frac | stop_basis       |   stop_param | target_mode   | entry_cutoff   |   total_trades |   trades_per_day |   total_r |   avg_r |   profit_factor |   win_rate |   max_drawdown_r |   calmar |   t_stat |
|-------:|:-------------------------------------------------------------|------------:|:------|----------------:|---------:|----------------------:|:-----------------|-------------:|:--------------|:---------------|---------------:|-----------------:|----------:|--------:|----------------:|-----------:|-----------------:|---------:|---------:|
|      1 | tf5_15m_brk0_N4_buf0.02_breakout_extreme0.05_orb_mid_cut1200 |           5 | 15m   |            0    |        4 |                  0.02 | breakout_extreme |         0.05 | orb_mid       | 12:00          |           1071 |           1.1591 |   38.3192 | 0.03578 |          1.1255 |     0.7124 |         -22.5254 |   0.464  |   1.6183 |
|      2 | tf5_15m_brk0_N8_buf0.02_breakout_extreme0.05_orb_mid_cut1200 |           5 | 15m   |            0    |        8 |                  0.02 | breakout_extreme |         0.05 | orb_mid       | 12:00          |           1092 |           1.1818 |   36.8746 | 0.03377 |          1.1232 |     0.7216 |         -22.9726 |   0.4378 |   1.5956 |
|      3 | tf5_15m_brk0_N8_buf0.02_breakout_extreme0.05_orb_mid_cut1300 |           5 | 15m   |            0    |        8 |                  0.02 | breakout_extreme |         0.05 | orb_mid       | 13:00          |           1181 |           1.2781 |   28.3335 | 0.02399 |          1.0858 |     0.7155 |         -23.1289 |   0.3341 |   1.1788 |
|      4 | tf5_15m_brk0_N4_buf0.02_breakout_extreme0.05_orb_mid_cut1300 |           5 | 15m   |            0    |        4 |                  0.02 | breakout_extreme |         0.05 | orb_mid       | 13:00          |           1161 |           1.2565 |   28.8193 | 0.02482 |          1.0848 |     0.7037 |         -21.6669 |   0.3628 |   1.1651 |
|      5 | tf5_15m_brk0_N2_buf0.02_breakout_extreme0.05_orb_mid_cut1200 |           5 | 15m   |            0    |        2 |                  0.02 | breakout_extreme |         0.05 | orb_mid       | 12:00          |           1059 |           1.1461 |   26.4426 | 0.02497 |          1.0847 |     0.7044 |         -24.2183 |   0.2978 |   1.1168 |
|      6 | tf5_15m_brk0_N4_buf0_breakout_extreme0.05_orb_mid_cut1200    |           5 | 15m   |            0    |        4 |                  0    | breakout_extreme |         0.05 | orb_mid       | 12:00          |           1177 |           1.2738 |   28.6705 | 0.02436 |          1.0745 |     0.6695 |         -24.1753 |   0.3234 |   1.066  |
|      7 | tf3_15m_brk0_N4_buf0.02_breakout_extreme0.05_orb_mid_cut1200 |           3 | 15m   |            0    |        4 |                  0.02 | breakout_extreme |         0.05 | orb_mid       | 12:00          |           1189 |           1.2868 |   21.0723 | 0.01772 |          1.055  |     0.677  |         -20.1854 |   0.2847 |   0.7957 |
|      8 | tf3_15m_brk0_N4_buf0.02_atr_frac0.1_orb_mid_cut1300          |           3 | 15m   |            0    |        4 |                  0.02 | atr_frac         |         0.1  | orb_mid       | 13:00          |           1313 |           1.421  |   28.3932 | 0.02162 |          1.0475 |     0.543  |         -30.2927 |   0.2556 |   0.7578 |
|      9 | tf5_15m_brk0_N2_buf0.02_breakout_extreme0.05_orb_mid_cut1300 |           5 | 15m   |            0    |        2 |                  0.02 | breakout_extreme |         0.05 | orb_mid       | 13:00          |           1149 |           1.2435 |   18.3422 | 0.01596 |          1.0529 |     0.6963 |         -25.4051 |   0.1969 |   0.7408 |
|     10 | tf5_15m_brk0_N8_buf0_breakout_extreme0.05_orb_mid_cut1200    |           5 | 15m   |            0    |        8 |                  0    | breakout_extreme |         0.05 | orb_mid       | 12:00          |           1188 |           1.2857 |   19.3394 | 0.01628 |          1.0504 |     0.6717 |         -24.4978 |   0.2153 |   0.7273 |
|     11 | tf3_15m_brk0_N8_buf0_breakout_extreme0.05_orb_mid_cut1200    |           3 | 15m   |            0    |        8 |                  0    | breakout_extreme |         0.05 | orb_mid       | 12:00          |           1289 |           1.395  |   20.465  | 0.01588 |          1.044  |     0.6369 |         -19.1211 |   0.2919 |   0.6783 |
|     12 | tf3_15m_brk0_N4_buf0.02_breakout_extreme0.05_orb_mid_cut1300 |           3 | 15m   |            0    |        4 |                  0.02 | breakout_extreme |         0.05 | orb_mid       | 13:00          |           1269 |           1.3734 |   17.9367 | 0.01413 |          1.0435 |     0.673  |         -18.9017 |   0.2588 |   0.6557 |
|     13 | tf5_15m_brk0_N4_buf0_breakout_extreme0.05_orb_mid_cut1300    |           5 | 15m   |            0    |        4 |                  0    | breakout_extreme |         0.05 | orb_mid       | 13:00          |           1260 |           1.3636 |   17.8416 | 0.01416 |          1.0423 |     0.6595 |         -24.3458 |   0.1999 |   0.6384 |
|     14 | tf3_15m_brk0_N4_buf0.02_atr_frac0.1_orb_mid_cut1200          |           3 | 15m   |            0    |        4 |                  0.02 | atr_frac         |         0.1  | orb_mid       | 12:00          |           1239 |           1.3409 |   23.0281 | 0.01859 |          1.0407 |     0.5424 |         -30.794  |   0.2039 |   0.6313 |
|     15 | tf5_15m_brk0.1_N8_buf0_breakout_extreme0.05_rr1p5_cut1200    |           5 | 15m   |            0.1  |        8 |                  0    | breakout_extreme |         0.05 | rr1p5         | 12:00          |            556 |           0.6017 |   15.8898 | 0.02858 |          1.0553 |     0.4263 |         -37.5703 |   0.1153 |   0.5971 |
|     16 | tf3_15m_brk0.05_N4_buf0_atr_frac0.1_orb_mid_cut1200          |           3 | 15m   |            0.05 |        4 |                  0    | atr_frac         |         0.1  | orb_mid       | 12:00          |           1036 |           1.1212 |   21.8518 | 0.02109 |          1.0408 |     0.4836 |         -43.9338 |   0.1356 |   0.5901 |
|     17 | tf5_15m_brk0_N4_buf0.02_breakout_extreme0.05_rr1p5_cut1200   |           5 | 15m   |            0    |        4 |                  0.02 | breakout_extreme |         0.05 | rr1p5         | 12:00          |            932 |           1.0087 |   20.6475 | 0.02215 |          1.0401 |     0.4152 |         -40.2708 |   0.1398 |   0.5748 |
|     18 | tf5_15m_brk0_N8_buf0.02_breakout_extreme0.05_rr1p5_cut1200   |           5 | 15m   |            0    |        8 |                  0.02 | breakout_extreme |         0.05 | rr1p5         | 12:00          |            936 |           1.013  |   20.2486 | 0.02163 |          1.0399 |     0.4156 |         -38.4571 |   0.1436 |   0.5698 |
|     19 | tf5_15m_brk0_N2_buf0_breakout_extreme0.05_orb_mid_cut1200    |           5 | 15m   |            0    |        2 |                  0    | breakout_extreme |         0.05 | orb_mid       | 12:00          |           1165 |           1.2608 |   15.0437 | 0.01291 |          1.0383 |     0.6618 |         -20.96   |   0.1957 |   0.5543 |
|     20 | tf3_15m_brk0_N4_buf0_breakout_extreme0.05_orb_mid_cut1200    |           3 | 15m   |            0    |        4 |                  0    | breakout_extreme |         0.05 | orb_mid       | 12:00          |           1288 |           1.3939 |   16.9712 | 0.01318 |          1.0358 |     0.6297 |         -23.7371 |   0.195  |   0.5541 |

## Discovery — Eligible Shortlist Pool (top 15)

|   rank | label                                                        |   timeframe | orb   |   breakout_frac |   n_bars |   reentry_buffer_frac | stop_basis       |   stop_param | target_mode   | entry_cutoff   |   total_trades |   trades_per_day |   total_r |   avg_r |   profit_factor |   win_rate |   max_drawdown_r |   calmar |   t_stat |
|-------:|:-------------------------------------------------------------|------------:|:------|----------------:|---------:|----------------------:|:-----------------|-------------:|:--------------|:---------------|---------------:|-----------------:|----------:|--------:|----------------:|-----------:|-----------------:|---------:|---------:|
|      1 | tf5_15m_brk0_N4_buf0.02_breakout_extreme0.05_orb_mid_cut1200 |           5 | 15m   |             0   |        4 |                  0.02 | breakout_extreme |         0.05 | orb_mid       | 12:00          |           1071 |           1.1591 |   38.3192 | 0.03578 |          1.1255 |     0.7124 |         -22.5254 |   0.464  |   1.6183 |
|      2 | tf5_15m_brk0_N8_buf0.02_breakout_extreme0.05_orb_mid_cut1200 |           5 | 15m   |             0   |        8 |                  0.02 | breakout_extreme |         0.05 | orb_mid       | 12:00          |           1092 |           1.1818 |   36.8746 | 0.03377 |          1.1232 |     0.7216 |         -22.9726 |   0.4378 |   1.5956 |
|      3 | tf5_15m_brk0_N8_buf0.02_breakout_extreme0.05_orb_mid_cut1300 |           5 | 15m   |             0   |        8 |                  0.02 | breakout_extreme |         0.05 | orb_mid       | 13:00          |           1181 |           1.2781 |   28.3335 | 0.02399 |          1.0858 |     0.7155 |         -23.1289 |   0.3341 |   1.1788 |
|      4 | tf5_15m_brk0_N4_buf0.02_breakout_extreme0.05_orb_mid_cut1300 |           5 | 15m   |             0   |        4 |                  0.02 | breakout_extreme |         0.05 | orb_mid       | 13:00          |           1161 |           1.2565 |   28.8193 | 0.02482 |          1.0848 |     0.7037 |         -21.6669 |   0.3628 |   1.1651 |
|      5 | tf5_15m_brk0_N2_buf0.02_breakout_extreme0.05_orb_mid_cut1200 |           5 | 15m   |             0   |        2 |                  0.02 | breakout_extreme |         0.05 | orb_mid       | 12:00          |           1059 |           1.1461 |   26.4426 | 0.02497 |          1.0847 |     0.7044 |         -24.2183 |   0.2978 |   1.1168 |
|      6 | tf5_15m_brk0_N4_buf0_breakout_extreme0.05_orb_mid_cut1200    |           5 | 15m   |             0   |        4 |                  0    | breakout_extreme |         0.05 | orb_mid       | 12:00          |           1177 |           1.2738 |   28.6705 | 0.02436 |          1.0745 |     0.6695 |         -24.1753 |   0.3234 |   1.066  |
|      7 | tf3_15m_brk0_N4_buf0.02_breakout_extreme0.05_orb_mid_cut1200 |           3 | 15m   |             0   |        4 |                  0.02 | breakout_extreme |         0.05 | orb_mid       | 12:00          |           1189 |           1.2868 |   21.0723 | 0.01772 |          1.055  |     0.677  |         -20.1854 |   0.2847 |   0.7957 |
|      8 | tf3_15m_brk0_N4_buf0.02_atr_frac0.1_orb_mid_cut1300          |           3 | 15m   |             0   |        4 |                  0.02 | atr_frac         |         0.1  | orb_mid       | 13:00          |           1313 |           1.421  |   28.3932 | 0.02162 |          1.0475 |     0.543  |         -30.2927 |   0.2556 |   0.7578 |
|      9 | tf5_15m_brk0_N2_buf0.02_breakout_extreme0.05_orb_mid_cut1300 |           5 | 15m   |             0   |        2 |                  0.02 | breakout_extreme |         0.05 | orb_mid       | 13:00          |           1149 |           1.2435 |   18.3422 | 0.01596 |          1.0529 |     0.6963 |         -25.4051 |   0.1969 |   0.7408 |
|     10 | tf5_15m_brk0_N8_buf0_breakout_extreme0.05_orb_mid_cut1200    |           5 | 15m   |             0   |        8 |                  0    | breakout_extreme |         0.05 | orb_mid       | 12:00          |           1188 |           1.2857 |   19.3394 | 0.01628 |          1.0504 |     0.6717 |         -24.4978 |   0.2153 |   0.7273 |
|     11 | tf3_15m_brk0_N8_buf0_breakout_extreme0.05_orb_mid_cut1200    |           3 | 15m   |             0   |        8 |                  0    | breakout_extreme |         0.05 | orb_mid       | 12:00          |           1289 |           1.395  |   20.465  | 0.01588 |          1.044  |     0.6369 |         -19.1211 |   0.2919 |   0.6783 |
|     12 | tf3_15m_brk0_N4_buf0.02_breakout_extreme0.05_orb_mid_cut1300 |           3 | 15m   |             0   |        4 |                  0.02 | breakout_extreme |         0.05 | orb_mid       | 13:00          |           1269 |           1.3734 |   17.9367 | 0.01413 |          1.0435 |     0.673  |         -18.9017 |   0.2588 |   0.6557 |
|     13 | tf5_15m_brk0_N4_buf0_breakout_extreme0.05_orb_mid_cut1300    |           5 | 15m   |             0   |        4 |                  0    | breakout_extreme |         0.05 | orb_mid       | 13:00          |           1260 |           1.3636 |   17.8416 | 0.01416 |          1.0423 |     0.6595 |         -24.3458 |   0.1999 |   0.6384 |
|     14 | tf3_15m_brk0_N4_buf0.02_atr_frac0.1_orb_mid_cut1200          |           3 | 15m   |             0   |        4 |                  0.02 | atr_frac         |         0.1  | orb_mid       | 12:00          |           1239 |           1.3409 |   23.0281 | 0.01859 |          1.0407 |     0.5424 |         -30.794  |   0.2039 |   0.6313 |
|     15 | tf5_15m_brk0.1_N8_buf0_breakout_extreme0.05_rr1p5_cut1200    |           5 | 15m   |             0.1 |        8 |                  0    | breakout_extreme |         0.05 | rr1p5         | 12:00          |            556 |           0.6017 |   15.8898 | 0.02858 |          1.0553 |     0.4263 |         -37.5703 |   0.1153 |   0.5971 |

## Frozen Shortlist — Single-Shot Validation & Cold

### `tf5_15m_brk0_N4_buf0.02_breakout_extreme0.05_orb_mid_cut1200`

- Config: tf=5m, ORB=15m, breakout_frac=0.0, N=4, reentry_buffer=0.02, stop=breakout_extreme 0.05, target=orb_mid, cutoff=12:00
- Discovery direction split: long 556 trades (-1.084R), short 515 trades (39.403R).

| window | trades | trades/day | total_R | avg_R | PF | WR | maxDD_R | Calmar | t_stat | net_R@1t | net_R@2t |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| discovery | 1071 | 1.1591 | 38.3192 | 0.03578 | 1.1255 | 0.7124 | -22.5254 | 0.464 | 1.6183 | 10.475 | -2.475 |
| validation | 412 | 1.1165 | -19.0178 | -0.04616 | 0.8569 | 0.6748 | -24.3381 | -0.5336 | -1.3173 | -26.383 | -29.808 |
| cold | 1654 | 1.1814 | 42.5325 | 0.02571 | 1.085 | 0.6965 | -25.6059 | 0.299 | 1.428 | -91.414 | -153.714 |

Discovery year split:

|   year |   trades |   total_r |   avg_r |   win_rate |
|-------:|---------:|----------:|--------:|-----------:|
|   2021 |      172 |    -0.174 | -0.001  |     0.6686 |
|   2022 |      298 |    26.973 |  0.0905 |     0.7383 |
|   2023 |      305 |    12.56  |  0.0412 |     0.7213 |
|   2024 |      296 |    -1.04  | -0.0035 |     0.7027 |

### `tf5_15m_brk0_N8_buf0.02_breakout_extreme0.05_orb_mid_cut1200`

- Config: tf=5m, ORB=15m, breakout_frac=0.0, N=8, reentry_buffer=0.02, stop=breakout_extreme 0.05, target=orb_mid, cutoff=12:00
- Discovery direction split: long 564 trades (-2.167R), short 528 trades (39.042R).

| window | trades | trades/day | total_R | avg_R | PF | WR | maxDD_R | Calmar | t_stat | net_R@1t | net_R@2t |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| discovery | 1092 | 1.1818 | 36.8746 | 0.03377 | 1.1232 | 0.7216 | -22.9726 | 0.4378 | 1.5956 | 9.58 | -3.115 |
| validation | 416 | 1.1274 | -15.1933 | -0.03652 | 0.8822 | 0.6875 | -22.8354 | -0.4544 | -1.0703 | -22.298 | -25.603 |
| cold | 1661 | 1.1864 | 31.5773 | 0.01901 | 1.0632 | 0.6972 | -24.6645 | 0.2304 | 1.0658 | -99.089 | -159.864 |

Discovery year split:

|   year |   trades |   total_r |   avg_r |   win_rate |
|-------:|---------:|----------:|--------:|-----------:|
|   2021 |      171 |     0.015 |  0.0001 |     0.6784 |
|   2022 |      303 |    29.063 |  0.0959 |     0.7525 |
|   2023 |      315 |    13.046 |  0.0414 |     0.7302 |
|   2024 |      303 |    -5.249 | -0.0173 |     0.7063 |

### `tf5_15m_brk0_N8_buf0.02_breakout_extreme0.05_orb_mid_cut1300`

- Config: tf=5m, ORB=15m, breakout_frac=0.0, N=8, reentry_buffer=0.02, stop=breakout_extreme 0.05, target=orb_mid, cutoff=13:00
- Discovery direction split: long 611 trades (-5.31R), short 570 trades (33.643R).

| window | trades | trades/day | total_R | avg_R | PF | WR | maxDD_R | Calmar | t_stat | net_R@1t | net_R@2t |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| discovery | 1181 | 1.2781 | 28.3335 | 0.02399 | 1.0858 | 0.7155 | -23.1289 | 0.3341 | 1.1788 | -1.078 | -14.758 |
| validation | 453 | 1.2276 | -12.6035 | -0.02782 | 0.9086 | 0.6932 | -20.9407 | -0.411 | -0.8538 | -20.32 | -23.909 |
| cold | 1793 | 1.2807 | 39.1532 | 0.02184 | 1.0723 | 0.6955 | -19.8928 | 0.3543 | 1.2619 | -102.593 | -168.522 |

Discovery year split:

|   year |   trades |   total_r |   avg_r |   win_rate |
|-------:|---------:|----------:|--------:|-----------:|
|   2021 |      181 |    -2.408 | -0.0133 |     0.6685 |
|   2022 |      338 |    23.402 |  0.0692 |     0.7367 |
|   2023 |      334 |    10.736 |  0.0321 |     0.7246 |
|   2024 |      328 |    -3.397 | -0.0104 |     0.7104 |

## Summary Read

- Best discovery row `tf5_15m_brk0_N4_buf0.02_breakout_extreme0.05_orb_mid_cut1200`: 1071 trades, 1.1591 trades/day, 38.3192R total, avg 0.03578R, PF 1.1255, WR 0.7124, maxDD -22.5254R, Calmar 0.464, t-stat 1.6183.
- Configs searched: 1296. With this many configs, a naive multiple-comparisons threshold pushes the required |t| well above the usual ~2. A single-config |t|~2 corresponds to p~0.05; searching 1296 configs inflates the best-of expected max-t substantially, so treat any best-row t-stat below ~3.5-4 as plausibly in-sample noise.
- The frozen shortlist single-shot validation and cold-window rows above are the honest read: an edge is only credible if it survives out-of-sample with the sign and rough magnitude intact after friction.

## Diagnostic Read

- Failed-breakout fades are structurally short-vol/mean-revert trades; expect them to do best in balancing/range regimes and to bleed in strong-trend regimes (the cold 2016-2021 and any trend-heavy validation stretch are the natural stress).
- Direction asymmetry (long vs short columns) flags whether the edge is a genuine two-sided range effect or a one-sided artifact.
- ORB-mid and opposite-edge targets trade win-rate for reward; the 1.5R target is the noise-robust primary.

## Artifacts

- Discovery grid (all configs): `backtesting/data/results/nq_ny_orb_failure_fade_discovery_20260710/discovery_grid_ranked.csv`
- Frozen shortlist trade streams: `backtesting/data/results/nq_ny_orb_failure_fade_discovery_20260710/frozen_<label>_<window>_trades.csv`
- Summary JSON: `backtesting/data/results/nq_ny_orb_failure_fade_discovery_20260710/summary.json`
- Report: `backtesting/learnings/reports/NQ_NY_ORB_FAILURE_FADE_DISCOVERY_20260710.md`
