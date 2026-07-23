# NQ NY VWAP Mean-Reversion Sleeve -- Causal Regime Switch (TRACK 4)

- Run slug: `nq_ny_vwap_sleeve_regime_switch_20260710`
- Source streams: `nq_ny_vwap_mean_reversion_validation_20260630` (recent `best_candidate_5m_trades.csv` = 370 trades / +127.777R; cold `cold_window_trades.csv` = 441 trades / +7.523R)
- Scope: find ONE causal daily-regime feature + threshold that justifies excluding the 2016-01..2021-06 cold window, retaining >=~75-80% of recent trades with recent total R preserved.
- Deployability: `research_only`.

## Feature Definitions (all as-of prior session close, no intraday lookahead)

Daily RTH bars = 09:30-15:55 ET 5m bars aggregated per session (full sessions, >=50 bars). `TR` = true range on daily bars; `ATR14/ATR50` = simple rolling means of TR. Every feature below is computed on the daily series through session *t* and then **shifted one session**, so the value used for a trade on day *t+1* is known at day *t*'s close (before the open).

| feature | definition | rule |
|---|---|---|
| `atr_scaled` | ATR14 / close (vol level, price-normalized) | floor |
| `atr_pctile` | rank of ATR14 within trailing 252d (vol level) | floor |
| `atr_trend` | ATR14 / ATR50 (vol trend) | cap |
| `dist_sma200_atr` | (close - SMA200) / ATR14  (signed trend extension) | cap |
| `abs_dist_sma200_atr` | \|close - SMA200\| / ATR14 | cap |
| `sma50_slope_atr` | (SMA50 - SMA50[-10]) / ATR14 (trend slope) | cap |
| `ath_prox` | close / trailing-252d high (1.0 = at high) | cap |
| `prior_range_atr` | prior RTH range / ATR14 | floor |
| `prior_day_eff` | prior \|close-open\|/range (trend-vs-range) | cap |

## Diagnosis: where the cold losses concentrate

### Year attribution (baseline, both windows)

| year | window | trades | total_R | avg_R |
|---|---|---:|---:|---:|
| 2016 | cold | 78 | +6.0 | +0.077 |
| 2017 | cold | 91 | +13.3 | +0.146 |
| 2018 | cold | 68 | -7.5 | -0.111 |
| 2019 | cold | 96 | +8.9 | +0.093 |
| 2020 | cold | 77 | -20.5 | -0.267 |
| 2021 | cold | 31 | +7.4 | +0.239 |
| 2021 | recent | 39 | +8.9 | +0.228 |
| 2022 | recent | 60 | +16.5 | +0.275 |
| 2023 | recent | 78 | +42.7 | +0.547 |
| 2024 | recent | 95 | +43.0 | +0.453 |
| 2025 | recent | 72 | +6.5 | +0.091 |
| 2026 | recent | 26 | +10.2 | +0.391 |

The cold window is a near-breakeven aggregate (+7.5R over 441 trades). Losses are NOT spread across the quiet 2016-2019 tape -- those years are flat-to-slightly-positive. The damage is concentrated in **2020 (COVID, -20.5R)** and secondarily **2018 (-7.5R)**, i.e. sharp trending dislocations, plus a long shallow bleed that produces the -45R max drawdown. **This already falsifies the naive `low-vol => bad` story: the single worst cold year is the highest-vol one.**

### Cold-window decile (quintile) PnL attribution

**`atr_scaled`** (cold quintiles, low->high):  -5.9R (n88) | +1.9R (n88) | +10.9R (n87) | -6.1R (n88) | +6.5R (n88)

**`atr_pctile`** (cold quintiles, low->high):  +5.1R (n73) | -19.4R (n72) | +4.0R (n76) | +12.8R (n68) | -0.0R (n73)

**`atr_trend`** (cold quintiles, low->high):  +13.3R (n86) | -26.3R (n85) | +7.5R (n85) | +14.9R (n85) | -9.7R (n85)

**`dist_sma200_atr`** (cold quintiles, low->high):  -3.9R (n76) | +29.2R (n75) | +0.2R (n76) | +9.5R (n75) | -30.3R (n76)

**`sma50_slope_atr`** (cold quintiles, low->high):  +1.5R (n85) | +12.2R (n84) | +11.1R (n84) | -3.5R (n84) | -19.8R (n85)

**`ath_prox`** (cold quintiles, low->high):  +3.6R (n73) | +7.8R (n73) | +8.1R (n73) | -14.8R (n72) | -4.2R (n73)

Reads: the strongest, most repeatable cold-loss signal is **trend extension**. The top `dist_sma200_atr` quintile (prior close far above the 200d mean) is the worst bucket (~-30R), matched by the steepest `sma50_slope_atr` quintile (~-20R) and the nearest-`ath_prox` buckets (~-19R). Vol-level buckets (`atr_scaled`, `atr_pctile`) are non-monotone and do not isolate the losses. Mechanism: intraday fade-to-VWAP gets run over on days when the tape is powerfully, persistently extended relative to *current* volatility -- a quiet one-way trend (2017 melt-up) or a violent directional move (2020). Dividing the extension by ATR14 is what makes this fire on the quiet 2016-19 grind while leaving the choppier, higher-ATR recent up-trends (2023-24) untouched.

## Candidate-switch comparison (one representative round/percentile threshold each)

Threshold picked per feature to target ~75-90% recent retention (the regime the sleeve is validated on). `rec_kept%` = fraction of the 370 recent trades retained; `rec_R` = their total R (baseline +127.8R); `cold_R_kept` / `cold_R_blocked` = R of the kept vs blocked cold trades (want blocked clearly negative). NaN feature (warmup) => keep.

| feature | rule | thr | rec_kept% | rec_R | cold_R_kept | cold_R_blocked | verdict |
|---|---|---:|---:|---:|---:|---:|---|
| `atr_scaled` | ge | 0.012 | 0.81 | +131.0 | -2.6 | +10.1 | wrong sign |
| `atr_pctile` | ge | 0.5 | 0.55 | +73.9 | +13.6 | -6.1 | guts recent |
| `atr_trend` | le | 1.2 | 0.89 | +107.9 | +13.7 | -6.1 | weak |
| `dist_sma200_atr` | le | 12.0 | 0.95 | +129.6 | +26.0 | -18.5 | helps |
| `abs_dist_sma200_atr` | le | 12.0 | 0.95 | +129.6 | +26.0 | -18.5 | helps |
| `sma50_slope_atr` | le | 1.3 | 0.79 | +110.8 | +33.1 | -25.6 | weak |
| `ath_prox` | le | 0.995 | 0.83 | +117.9 | +14.0 | -6.5 | weak |
| `prior_range_atr` | ge | 0.55 | 0.81 | +95.1 | -16.4 | +23.9 | guts recent |
| `prior_day_eff` | le | 0.75 | 0.81 | +115.9 | -3.0 | +10.5 | wrong sign |

Only `dist_sma200_atr` (and its absolute twin) clears the bar: recent retention high, recent R preserved, and the blocked cold subset clearly negative. The headline **vol-floor hypothesis is falsified**: `atr_scaled` at 0.012 blocks *profitable* cold trades (blocked subset is POSITIVE) and still keeps the -20R 2020 book; `atr_pctile` only helps by gutting recent R.

## Deep dive -- winning switch: `dist_sma200_atr` cap

Rule: **trade only when prior close is <= X ATR14 above the 200-day SMA** (skip extreme, volatility-normalized trend extension). Threshold sweep:

| cap (ATRs) | rec_kept% | rec_R | cold_R_kept | cold_R_blocked | full_R | full_t |
|---:|---:|---:|---:|---:|---:|---:|
| 8 | 0.65 | +100.9 | +13.7 | -6.2 | +114.6 | 2.53 |
| 9 | 0.74 | +114.5 | +26.8 | -19.3 | +141.3 | 2.96 |
| 10 | 0.84 | +114.2 | +30.1 | -22.6 | +144.4 | 2.89 |
| 11 | 0.90 | +116.4 | +29.5 | -22.0 | +145.9 | 2.84 |
| 12 | 0.95 | +129.6 | +26.0 | -18.5 | +155.6 | 2.89 |
| 13 | 0.98 | +133.8 | +20.2 | -12.6 | +153.9 | 2.82 |
| 14 | 0.99 | +132.8 | +13.6 | -6.1 | +146.4 | 2.66 |

Chosen threshold: **cap = 12 ATRs** (round, and just above the recent window's own extension range -- recent prior-close extension maxes near ~17.7 ATRs but is <=12 on ~92% of sessions). At cap=12 recent retention is ~95% with recent R essentially intact, and the cold window sheds ~-16R of pure drawdown.

### Full-history year split (baseline vs switched)

| year | n_all | R_base | n_kept | R_switch |
|---|---:|---:|---:|---:|
| 2016 | 78 | +6.0 | 78 | +6.0 |
| 2017 | 91 | +13.3 | 63 | +18.1 |
| 2018 | 68 | -7.5 | 64 | -3.5 |
| 2019 | 96 | +8.9 | 89 | +7.3 |
| 2020 | 77 | -20.5 | 55 | -10.3 |
| 2021 | 70 | +16.3 | 68 | +18.3 |
| 2022 | 60 | +16.5 | 60 | +16.5 |
| 2023 | 78 | +42.7 | 73 | +43.8 |
| 2024 | 95 | +43.0 | 90 | +38.9 |
| 2025 | 72 | +6.5 | 67 | +8.4 |
| 2026 | 26 | +10.2 | 24 | +12.2 |
| ALL | 811 | +135.3 | 731 | +155.6 |

### Switch on-rate over ALL sessions (does it toggle or memorise the split?)

| year | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| on-rate | 1.00 | 0.66 | 0.92 | 0.96 | 0.78 | 0.90 | 1.00 | 0.87 | 0.91 | 0.92 | 0.96 |

The switch is ON ~90% of sessions in most years and dips to ~0.66/0.78 in the steadiest-trend years (2017 melt-up, 2020 COVID recovery). It toggles *inside both windows* (recent extension exceeds the cap in 2023-24 too), so it is not a disguised 2016-2021 date label -- but it is also mostly-on, i.e. a light-touch tail cap rather than a regime on/off gate.

### t-stat and deflation read

- Full-history baseline: n=811, R=+135.3, t=2.43.
- Switched full history (cap=12): n=731, R=+155.6, t=2.89.
- Recent-only baseline (the validated regime): n=370, R=+127.8, t=3.16.
- Feature/threshold combinations examined ~ 9 features x ~7 thresholds = ~63. Deflated for that many looks, lifting the full-history t from ~2.4 to ~2.9 is a modest, non-decisive improvement, and it never reaches the recent-only t (~3.2). The switch reduces cold *drag*; it does not reveal a hidden cold-window *edge* (switched cold is still only ~breakeven-positive per trade).

## Bonus: exit-refined stream and prop lifecycle under the switch

- Exit-refined day_mid-target recent stream: baseline n=368, R=+145.3; switched n=350, R=+142.7 (retains 95%). The cap is nearly free on the recent exit-refined book too.

Prop lifecycle ($2,000 EOD trailing DD, $3,000 pass, $1,500 first payout, 14-day starts; recent 1s path stream):

| stream | risk/R | first_payout_rate | pre_payout_bust | ev_per_start | avg_days_to_payout |
|---|---:|---:|---:|---:|---:|
| unfiltered | $100 | 0.656 | 0.000 | $985 | 300 |
| unfiltered | $125 | 0.664 | 0.000 | $996 | 252 |
| unfiltered | $150 | 0.702 | 0.000 | $1053 | 233 |
| unfiltered | $175 | 0.763 | 0.038 | $1145 | 220 |
| unfiltered | $200 | 0.756 | 0.107 | $1134 | 195 |
| switched | $100 | 0.656 | 0.000 | $985 | 298 |
| switched | $125 | 0.672 | 0.000 | $1008 | 263 |
| switched | $150 | 0.748 | 0.000 | $1122 | 252 |
| switched | $175 | 0.847 | 0.000 | $1271 | 249 |
| switched | $200 | 0.771 | 0.107 | $1156 | 206 |

Because the switch removes <5% of recent trades, prop economics are essentially unchanged from the validation packet -- the switch is a cold-window justification, not a recent-window edge lift.

## Summary Read

- **The headline vol-floor hypothesis is falsified on this data.** The worst cold year (2020) is the *highest*-vol one, and scaled-ATR / ATR-percentile floors either block profitable cold trades (wrong sign) or only 'help' by gutting recent R. A minimum-volatility deactivation rule is NOT supported.
- **The one feature that survives is trend extension: `dist_sma200_atr` (cap = 12 ATRs).** Skip days whose prior close sits >12 ATR14 above the 200-day SMA. Recent: retains ~95% of trades (+129.6R vs +127.8R baseline). Cold: blocked subset is -18.5R of pure drawdown removed; full history improves from +135.3R to +155.6R and t from ~2.4 to ~2.9.
- **But this is a qualified pass, not a clean regime story.** In the recent window the blocked extended days were themselves profitable, so the feature is a *proxy* whose sign flips across windows (extension is fatal in the quiet cold tape, benign in the choppier recent tape). It reduces cold *drag* to breakeven; it does not manufacture a cold-window edge. Deflated for ~63 feature/threshold looks the t-lift is modest and never beats the recent-only sleeve (t~3.2).
- **Recommendation: treat the sleeve as recent-regime-only.** The trend-extension cap (`dist_sma200_atr <= 12`) is the best available single-feature deactivation rule if one is required -- it is causal, monotone at the loss-bearing tail, and mechanistically motivated -- but it should be deployed as a drawdown-tail guard, not as evidence that 2016-2021 is tradable. A *volatility* floor should NOT be used; it is contradicted by the diagnosis.

## Artifacts

- `data/results/nq_ny_vwap_sleeve_regime_switch_20260710/daily_features.csv`
- `data/results/nq_ny_vwap_sleeve_regime_switch_20260710/feature_comparison.csv`
- `data/results/nq_ny_vwap_sleeve_regime_switch_20260710/dist_sma200_threshold_sweep.csv`
- `data/results/nq_ny_vwap_sleeve_regime_switch_20260710/full_history_year_split.csv`
- `data/results/nq_ny_vwap_sleeve_regime_switch_20260710/switch_on_rate_by_year.csv`
- `data/results/nq_ny_vwap_sleeve_regime_switch_20260710/prop_lifecycle_switch.csv`
- report: `learnings/reports/NQ_NY_VWAP_SLEEVE_REGIME_SWITCH_20260710.md`

