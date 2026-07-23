# Agent Instructions

Long-term portfolio research workspace for daily ETF/equity data, recurring contribution simulations, allocation studies, and total-return-style analysis.

Keep this workspace separate from intraday futures trading:

- Do not import or modify `execution/`.
- Do not reuse intraday ORB/FVG session assumptions from `backtesting/`.
- Use daily bars and explicit portfolio accounting assumptions.
- Prefer adjusted prices for long-horizon return research; preserve raw OHLCV where the data source provides it.
- Cache source data under `data/prices/` and derived runs under `data/results/`.

Current commands:

```bash
uv sync --extra dev
uv run python scripts/fetch_prices.py SPY QQQ --years 20
uv run python scripts/compare_dca.py SPY QQQ --amount 1000 --every-weeks 2 --years 20 --fetch
uv run python scripts/compare_dip_buying.py SPY QQQ --reserve SGOV --amount 1000 --every-weeks 2 --years 20 --fetch
uv run pytest
```

Baseline DCA assumptions:

- Fractional shares are allowed.
- Purchases execute on the scheduled date or the next available trading day.
- Purchases use adjusted close by default, approximating reinvested distributions.
- Taxes, fees, bid/ask spread, market impact, and account limits are not modeled yet.
- Dip-buying thresholds use drawdown from the target ETF's prior adjusted-close high.
- Volatility drag is annualized arithmetic return minus annualized geometric return from daily time-weighted returns.
- Beta defaults to daily time-weighted returns versus SPY unless another benchmark is specified.
