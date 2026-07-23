---
name: longterm-portfolio-research
description: Long-term portfolio research workflows for daily ETF/equity data, recurring contribution simulations, allocation comparisons, and total-return-style analysis in the trading_engine repo. This skill should be used when the user asks about long-term investing, portfolio construction, DCA, recurring buys, SPY/QQQ/DBMF-style ETF comparisons, adjusted daily data, or research that must stay separate from intraday futures trading.
---

# Longterm Portfolio Research

## Core Rule

Keep long-term investing research in `longterm_research/`. Do not route these requests through `execution/`, intraday ORB/FVG backtests, or futures session assumptions.

Use the local workspace instructions first:

- `longterm_research/AGENTS.md`
- `longterm_research/pyproject.toml`
- `longterm_research/scripts/`
- `longterm_research/src/longterm_research/`

## Default Workflow

1. Verify data coverage before answering performance questions.
2. Fetch or refresh cached daily prices when the requested date range is missing.
3. Run the narrowest script that answers the question.
4. Report assumptions: adjusted close or raw close, fractional shares, buy timing, fees/taxes/slippage, and final price date.
5. Save artifacts under `longterm_research/data/results/` for auditability.

## Commands

From `longterm_research/`:

```bash
uv sync --extra dev
uv run python scripts/fetch_prices.py SPY QQQ --years 20
uv run python scripts/compare_dca.py SPY QQQ --amount 1000 --every-weeks 2 --years 20 --fetch
uv run pytest
```

## Data Source Guidance

Use yfinance adjusted daily data for initial long-horizon portfolio return work because the repo's verified DataBento equities daily coverage is too short for 20-year SPY/QQQ comparisons. Keep DataBento raw OHLCV as a later auditable source for recent daily candles or intraday equity research.

For return calculations, default to `adj_close`. Raw close is allowed only when the user explicitly wants price-only behavior or when validating source data.

## Current Assumptions

- Fractional shares are allowed.
- Recurring buys execute on the scheduled date or the next available trading day.
- Adjusted close approximates reinvested distributions for portfolio return comparisons.
- Taxes, fees, bid/ask spread, market impact, and account constraints are not modeled yet.

## When Expanding

Add new functionality as small scripts or package modules under `longterm_research/`, then add tests. Keep result artifacts reproducible: inputs, assumptions, summary metrics, transactions, and equity curves should be saved whenever a simulation is run.
