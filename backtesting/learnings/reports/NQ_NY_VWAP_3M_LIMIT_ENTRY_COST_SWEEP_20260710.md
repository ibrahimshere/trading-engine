# NQ NY VWAP 3m Limit-Entry + Realistic-Fill Cost Sweep

- Run slug: `nq_ny_vwap_3m_limit_entry_cost_sweep_20260710`
- Track: **TRACK 2 of 4** (final track) - does resting-limit entry improvement beat market entry on TOTAL net R once non-fills are paid for?
- Data: `2021-06-07` through `<2026-06-06` (`1293` NY RTH days).
- Survivor leg (frozen, from TRACK 1 rescue): 3m bars, VWAP mean, 2.5% prior-ATR extension, 30-minute consolidation (<=20% ATR range), sweep/reclaim, LONG-ONLY, gated by `efficiency_max=0.65`, `time_bucket 10:00-14:00`, `session_range_atr_max=1.5`, no slope gate. 7.5% prior-ATR even-tick stop, fixed 1.5R target, max 3 trades/day, ~10-min cooldown, flat 15:55.
- Friction: integer MNQ sizing, `$0.575`/side commission, adverse slippage `0/1/2` ticks/side plus a mixed model (0 ticks on a passive limit fill, 1 tick on the stop/target exit; the market baseline pays 1 tick each side).
- Deployability: `research_only`. The 3m VWAP sweep/reclaim state machine, native-timeframe static-R exit, the TRACK 1 context gates, and this limit-entry fill model are research-script only; the live execution engine cannot arm this setup yet.

## Scope

The 204-signal survivor set is held FIXED (the exact long trades the frozen gated leg takes at market). Each entry variant only re-prices the entry on that same signal set; unfilled orders contribute 0 R. This keeps every comparison a clean per-signal paired test against the market-entry control and does not let a limit variant free up cooldown slots for other signals (that dynamic re-selection is out of scope).

## Baseline Parity Audit

- Regenerated frozen gated survivor stream: `204` trades, gross `+60.4782R`, net@1t `+48.7442R`.
- Expected (TRACK 1 survivor row): `204` trades, gross `+60.4782R`, net@1t `+48.7442R`.
- Delta: trades `0`, gross `+0.0000R`, net@1t `-0.0000R`; parity **PASS**.

## Fill Model (precise)

1. **Limit price** (LONG, per variant): signal-bar close; consolidation low (the swept level); 25/50/75% retrace from the next-bar open toward the sweep-extreme (signal-bar) low; or the sweep-extreme low itself. Off-grid retrace prices are floored to the NQ tick (harder to fill, conservative).
2. **Placement**: after the signal 3m bar completes, the limit rests for the entry bar onward on the lower-timeframe path (1m and 1s).
3. **Marketable case**: if the limit is at/above the entry-bar open, it fills immediately at the open (no improvement) -- a limit can never fill worse than the market it was placed into.
4. **Resting fill**: otherwise a fill requires the lower-timeframe price to trade strictly THROUGH the limit (low <= limit - 1 tick). Fill price is the limit.
5. **Pre-fill cancels/misses**: while unfilled, if the baseline target level is reached first the order is a MISSED WINNER (no trade); if the baseline stop level trades first the order is CANCELLED (no trade). Same lower-timeframe-bar ambiguity resolves against the trade: target-miss > stop-cancel > fill.
6. **Time stop**: cancel-if-unfilled after K = 1, 2, 4 3m bars, and good-till-window-end (`gtc`, until 15:55).
7. **After fill**: `recomputed` mode re-anchors stop/target to the fill (fill-D / fill+1.5D); `original` mode keeps the baseline market levels (open-D / open+1.5D). Exit is the conservative lower-TF path with stop priority on same-bar stop/target touches, else flat at 15:55.
8. **R unit**: every variant's R uses the SAME fixed baseline risk D (the even-tick 7.5%-ATR stop distance in points), so a few points of entry improvement is a directly-additive fractional R lift and total R is comparable across variants. In `original` mode a winner therefore pays `1.5R + improvement_R` and a loser `-1R + improvement_R`; in `recomputed` mode the trade is a rigid `[-1R, +1.5R]` shape shifted to a lower, safer entry.

## Entry Variants (best K/stop-mode per variant, 1s path, mixed slippage)

`total_r_1t` is symmetric 1 tick/side; `total_r_mixed` uses the passive-limit-fill assumption. Baseline is the market control.

| entry_variant        | k_bars   | stop_mode   |   fill_rate |   missed_winner_rate |   missed_loser_rate |   avg_improvement_pts |   avg_improvement_r |   total_r_1t |   total_r_mixed |   avg_r_all_mixed |   pf_mixed |   dd_r_mixed |   calmar_mixed |
|:---------------------|:---------|:------------|------------:|---------------------:|--------------------:|----------------------:|--------------------:|-------------:|----------------:|------------------:|-----------:|-------------:|---------------:|
| baseline_market_open | n/a      | original    |      1      |               0      |              0      |                0      |             0       |      48.7234 |         48.7234 |           0.23884 |     1.4822 |      -6.0712 |         1.5641 |
| limit_signal_close   | gtc      | recomputed  |      0.9902 |               0.0098 |              0      |                0.1238 |             0.00604 |      48.4172 |         51.1205 |           0.25059 |     1.5183 |      -6.1305 |         1.6252 |
| limit_cons_low       | gtc      | original    |      0.7304 |               0.25   |              0.0196 |                6.0587 |             0.30127 |      26.3747 |         28.343  |           0.13894 |     1.4415 |      -4.4267 |         1.2479 |
| limit_retrace25      | 4        | original    |      0.8627 |               0.1078 |              0.0294 |                2.8594 |             0.14428 |      49.7742 |         52.1353 |           0.25557 |     1.6498 |      -6.3911 |         1.5899 |
| limit_retrace50      | gtc      | recomputed  |      0.7892 |               0.2108 |              0      |                5.5248 |             0.27423 |      34.1979 |         36.3215 |           0.17805 |     1.4504 |      -8.2663 |         0.8564 |
| limit_retrace75      | gtc      | original    |      0.701  |               0.2696 |              0.0294 |                7.5822 |             0.37498 |      30.5792 |         32.4575 |           0.15911 |     1.5658 |      -4.863  |         1.3008 |
| limit_sweep_extreme  | gtc      | recomputed  |      0.5539 |               0.3529 |              0.0931 |                8.8451 |             0.4201  |      16.8782 |         18.3459 |           0.08993 |     1.3085 |     -12.6199 |         0.2833 |

## Slippage Sensitivity: Best Limit Variant vs Market Baseline (1s path)

| slippage   |   baseline_total_r |   best_variant_total_r |   delta_total_r |
|:-----------|-------------------:|-----------------------:|----------------:|
| 0t         |            54.1811 |                54.4964 |          0.3153 |
| 1t         |            48.7234 |                49.7742 |          1.0508 |
| 2t         |            43.2657 |                45.052  |          1.7863 |
| mixed      |            48.7234 |                52.1353 |          3.4119 |

## Paired Per-Signal Deltas vs Market Baseline (1s, mixed slippage)

Every row is scored on the identical 204-signal set, so the delta is a paired difference. `paired_t_stat` = mean(delta)*sqrt(n)/std(delta).

| entry_variant      | k_bars   | stop_mode   |   total_r |   baseline_total_r |   delta_total_r |   paired_mean_delta_r |   paired_t_stat |
|:-------------------|:---------|:------------|----------:|-------------------:|----------------:|----------------------:|----------------:|
| limit_retrace25    | 4        | original    |   52.1353 |            48.7234 |          3.4119 |               0.01672 |          0.454  |
| limit_retrace25    | gtc      | recomputed  |   51.6483 |            48.7234 |          2.9249 |               0.01434 |          0.279  |
| limit_signal_close | gtc      | recomputed  |   51.1205 |            48.7234 |          2.3971 |               0.01175 |          0.7381 |
| limit_signal_close | 1        | recomputed  |   50.7107 |            48.7234 |          1.9873 |               0.00974 |          0.5382 |
| limit_signal_close | 2        | recomputed  |   50.7107 |            48.7234 |          1.9873 |               0.00974 |          0.5382 |
| limit_signal_close | 4        | recomputed  |   50.7107 |            48.7234 |          1.9873 |               0.00974 |          0.5382 |
| limit_retrace25    | gtc      | original    |   50.1678 |            48.7234 |          1.4444 |               0.00708 |          0.2127 |
| limit_retrace25    | 4        | recomputed  |   50.0046 |            48.7234 |          1.2812 |               0.00628 |          0.1233 |
| limit_signal_close | gtc      | original    |   49.7566 |            48.7234 |          1.0332 |               0.00506 |          0.4983 |
| limit_signal_close | 2        | original    |   49.3195 |            48.7234 |          0.5961 |               0.00292 |          0.2194 |
| limit_signal_close | 4        | original    |   49.3195 |            48.7234 |          0.5961 |               0.00292 |          0.2194 |
| limit_signal_close | 1        | original    |   49.3195 |            48.7234 |          0.5961 |               0.00292 |          0.2194 |
| limit_retrace25    | 2        | original    |   43.9642 |            48.7234 |         -4.7592 |              -0.02333 |         -0.5476 |
| limit_retrace25    | 2        | recomputed  |   42.5638 |            48.7234 |         -6.1596 |              -0.03019 |         -0.5585 |
| limit_retrace25    | 1        | recomputed  |   39.038  |            48.7234 |         -9.6854 |              -0.04748 |         -0.8199 |
| limit_retrace25    | 1        | original    |   38.9563 |            48.7234 |         -9.7671 |              -0.04788 |         -1.0123 |

## Best-Variant Walk-Forward (frozen config, 6 rolling folds, 1s mixed slippage)

| entry_variant                       | test_start   | test_end_exclusive   |   test_signals |   test_total_r |   test_pf |   test_dd_r |
|:------------------------------------|:-------------|:---------------------|---------------:|---------------:|----------:|------------:|
| baseline_market_open                | 2023-01-01   | 2023-07-01           |             26 |         7.8854 |    1.6476 |     -2.855  |
| baseline_market_open                | 2023-07-01   | 2024-01-01           |             25 |         9.1804 |    1.8531 |     -3.9555 |
| baseline_market_open                | 2024-01-01   | 2024-07-01           |             20 |         0.1464 |    1.0124 |     -4.2996 |
| baseline_market_open                | 2024-07-01   | 2025-01-01           |             12 |        -2.6745 |    0.685  |     -4.2544 |
| baseline_market_open                | 2025-01-01   | 2025-07-01           |             17 |         3.8746 |    1.4631 |     -4.227  |
| baseline_market_open                | 2025-07-01   | 2026-01-01           |             14 |         0.261  |    1.031  |     -3.3537 |
| limit_retrace25|K=4|original        | 2023-01-01   | 2023-07-01           |             26 |         5.3211 |    1.5141 |     -3.1396 |
| limit_retrace25|K=4|original        | 2023-07-01   | 2024-01-01           |             25 |         7.4223 |    1.829  |     -2.6941 |
| limit_retrace25|K=4|original        | 2024-01-01   | 2024-07-01           |             20 |         2.8847 |    1.3238 |     -3.5959 |
| limit_retrace25|K=4|original        | 2024-07-01   | 2025-01-01           |             12 |        -0.3583 |    0.9482 |     -3.5858 |
| limit_retrace25|K=4|original        | 2025-01-01   | 2025-07-01           |             17 |         4.0541 |    1.6731 |     -3.3386 |
| limit_retrace25|K=4|original        | 2025-07-01   | 2026-01-01           |             14 |        -1.0899 |    0.8512 |     -3.9005 |
| limit_signal_close|K=gtc|recomputed | 2023-01-01   | 2023-07-01           |             26 |         8.3539 |    1.7005 |     -2.7725 |
| limit_signal_close|K=gtc|recomputed | 2023-07-01   | 2024-01-01           |             25 |         9.6036 |    1.9074 |     -3.8495 |
| limit_signal_close|K=gtc|recomputed | 2024-01-01   | 2024-07-01           |             20 |        -0.9459 |    0.9185 |     -4.6258 |
| limit_signal_close|K=gtc|recomputed | 2024-07-01   | 2025-01-01           |             12 |        -2.5177 |    0.6995 |     -4.1952 |
| limit_signal_close|K=gtc|recomputed | 2025-01-01   | 2025-07-01           |             17 |         4.04   |    1.4878 |     -4.1742 |
| limit_signal_close|K=gtc|recomputed | 2025-07-01   | 2026-01-01           |             14 |         2.9328 |    1.4029 |     -3.0934 |

## Year Splits (1s, mixed slippage)

| entry_variant                       |   year |   signals |   total_r |    avg_r |   win_rate |
|:------------------------------------|-------:|----------:|----------:|---------:|-----------:|
| baseline_market_open                |   2021 |        23 |   12.9226 |  0.56185 |     0.6522 |
| baseline_market_open                |   2022 |        51 |   11.4915 |  0.22532 |     0.5098 |
| baseline_market_open                |   2023 |        51 |   17.0658 |  0.33462 |     0.549  |
| baseline_market_open                |   2024 |        32 |   -2.5281 | -0.079   |     0.4062 |
| baseline_market_open                |   2025 |        31 |    4.1356 |  0.13341 |     0.4839 |
| baseline_market_open                |   2026 |        16 |    5.636  |  0.35225 |     0.5625 |
| limit_retrace25|K=4|original        |   2021 |        23 |   16.0324 |  0.69706 |     0.6087 |
| limit_retrace25|K=4|original        |   2022 |        51 |   12.9922 |  0.25475 |     0.4118 |
| limit_retrace25|K=4|original        |   2023 |        51 |   12.7434 |  0.24987 |     0.4118 |
| limit_retrace25|K=4|original        |   2024 |        32 |    2.5263 |  0.07895 |     0.375  |
| limit_retrace25|K=4|original        |   2025 |        31 |    2.9642 |  0.09562 |     0.3548 |
| limit_retrace25|K=4|original        |   2026 |        16 |    4.8768 |  0.3048  |     0.4375 |
| limit_signal_close|K=gtc|recomputed |   2021 |        23 |   13.2894 |  0.5778  |     0.6522 |
| limit_signal_close|K=gtc|recomputed |   2022 |        51 |   12.0493 |  0.23626 |     0.5098 |
| limit_signal_close|K=gtc|recomputed |   2023 |        51 |   17.9575 |  0.35211 |     0.549  |
| limit_signal_close|K=gtc|recomputed |   2024 |        32 |   -3.4635 | -0.10823 |     0.375  |
| limit_signal_close|K=gtc|recomputed |   2025 |        31 |    6.9728 |  0.22493 |     0.5161 |
| limit_signal_close|K=gtc|recomputed |   2026 |        16 |    4.3149 |  0.26968 |     0.5    |

## Deflation Read

- Limit combos scored on the primary path/slippage (variant x K x stop-mode): **48**; total including both paths and all slippage assumptions: **384**.
- Best combo: `limit_retrace25|K=4|original`, paired delta `+3.4119R`, paired t-stat `0.454`.
- Expected max |t| of the null over 48 paired searches ~ sqrt(2 ln N) = `2.7825`; best-over-expected ratio `0.1632`.
- The best combo paired t-stat does NOT exceed the expected null maximum; the lift is plausibly selection noise.

## Summary Read

- **Recommended entry for this leg: MARKET (next-bar open).**
- On TOTAL net R (1s, mixed slippage) the best limit variant `limit_retrace25` (K=4, original stop) delivers `+52.1353R` vs the market baseline's `+48.7234R` -- a delta of `+3.4119R` (limit BEATS market). Paired t-stat `0.454` does not clear the multiple-comparison bar (`2.7825`).
- **Mixed-slippage read:** the passive-limit-fill assumption (0 ticks on entry) is where limit entries look best; under symmetric 1-2 ticks/side the miss cost erodes more of the edge. See the slippage-sensitivity table.
- **The core tradeoff:** deeper limits (retrace75, sweep-extreme, cons-low) improve entry the most per fill but miss more winners; shallow/near-market limits fill almost always but add little. The best combo balances fill rate against improvement. Missed-winner vs missed-loser rates in the variant table show whether the misses are disproportionately the trades you wanted.
- All rows are `research_only`; nothing here authorizes live implementation. Live limit-entry execution would additionally need real book/queue modelling, which this bar-path fill proxy does not provide.

## Artifacts

- Results: `backtesting/data/results/nq_ny_vwap_3m_limit_entry_cost_sweep_20260710/`
- Report: `backtesting/learnings/reports/NQ_NY_VWAP_3M_LIMIT_ENTRY_COST_SWEEP_20260710.md`
