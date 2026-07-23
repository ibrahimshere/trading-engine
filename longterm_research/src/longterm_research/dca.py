from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

import pandas as pd

from .data import parse_date


@dataclass(frozen=True)
class DCAResult:
    symbol: str
    summary: dict[str, object]
    transactions: pd.DataFrame
    equity_curve: pd.DataFrame


def _as_price_frame(prices: pd.DataFrame, symbol: str, price_col: str) -> pd.DataFrame:
    required = {"date", "symbol", price_col}
    missing = required - set(prices.columns)
    if missing:
        raise ValueError(f"Price data missing required columns: {', '.join(sorted(missing))}")
    frame = prices[prices["symbol"].str.upper() == symbol.upper()].copy()
    if frame.empty:
        raise ValueError(f"No prices found for {symbol.upper()}.")
    frame["date"] = pd.to_datetime(frame["date"]).dt.tz_localize(None).dt.normalize()
    frame = frame.dropna(subset=[price_col]).sort_values("date")
    frame = frame.drop_duplicates(subset=["date"], keep="last")
    if frame.empty:
        raise ValueError(f"No usable {price_col} prices found for {symbol.upper()}.")
    return frame


def _xirr(cash_flows: list[tuple[pd.Timestamp, float]]) -> float | None:
    if not cash_flows:
        return None
    start = min(flow_date for flow_date, _ in cash_flows)

    def npv(rate: float) -> float:
        total = 0.0
        for flow_date, amount in cash_flows:
            years = (flow_date - start).days / 365.25
            total += amount / ((1.0 + rate) ** years)
        return total

    low = -0.999999
    high = 10.0
    low_value = npv(low)
    high_value = npv(high)
    expansions = 0
    while low_value * high_value > 0 and expansions < 8:
        high *= 10.0
        high_value = npv(high)
        expansions += 1
    if low_value * high_value > 0:
        return None

    for _ in range(200):
        mid = (low + high) / 2.0
        mid_value = npv(mid)
        if abs(mid_value) < 1e-7:
            return mid
        if low_value * mid_value <= 0:
            high = mid
            high_value = mid_value
        else:
            low = mid
            low_value = mid_value
    return (low + high) / 2.0


def simulate_dca(
    prices: pd.DataFrame,
    *,
    symbol: str,
    amount: float,
    every_weeks: int,
    start: str | date | datetime | pd.Timestamp,
    end: str | date | datetime | pd.Timestamp | None = None,
    price_col: str = "adj_close",
) -> DCAResult:
    if amount <= 0:
        raise ValueError("amount must be positive.")
    if every_weeks <= 0:
        raise ValueError("every_weeks must be positive.")

    symbol = symbol.upper()
    frame = _as_price_frame(prices, symbol, price_col)
    start_ts = parse_date(start)
    end_ts = parse_date(end) or frame["date"].max()
    frame = frame[(frame["date"] >= start_ts) & (frame["date"] <= end_ts)].copy()
    if frame.empty:
        raise ValueError(f"No prices for {symbol} between {start_ts.date()} and {end_ts.date()}.")

    trading_dates = pd.DatetimeIndex(frame["date"])
    final_date = trading_dates.max()
    final_price = float(frame.loc[frame["date"] == final_date, price_col].iloc[-1])
    schedule = pd.date_range(start=start_ts, end=final_date, freq=f"{every_weeks * 7}D")

    rows: list[dict[str, object]] = []
    for scheduled_date in schedule:
        loc = trading_dates.searchsorted(scheduled_date, side="left")
        if loc >= len(trading_dates):
            continue
        execution_date = trading_dates[loc]
        price = float(frame.iloc[loc][price_col])
        if price <= 0:
            raise ValueError(f"Non-positive price for {symbol} on {execution_date.date()}: {price}")
        shares = amount / price
        rows.append(
            {
                "scheduled_date": scheduled_date,
                "execution_date": execution_date,
                "symbol": symbol,
                "amount": float(amount),
                "price": price,
                "shares": shares,
            }
        )

    transactions = pd.DataFrame(rows)
    if transactions.empty:
        raise ValueError(f"No purchases were generated for {symbol}.")

    total_invested = float(transactions["amount"].sum())
    total_shares = float(transactions["shares"].sum())
    ending_value = total_shares * final_price
    gain_loss = ending_value - total_invested
    total_return = gain_loss / total_invested if total_invested else 0.0
    cash_flows = [
        (pd.Timestamp(row.execution_date), -float(row.amount))
        for row in transactions.itertuples(index=False)
    ]
    cash_flows.append((final_date, ending_value))
    money_weighted = _xirr(cash_flows)

    share_events = transactions.groupby("execution_date", as_index=False)["shares"].sum()
    equity_curve = frame[["date", "symbol", price_col]].merge(
        share_events,
        how="left",
        left_on="date",
        right_on="execution_date",
    )
    equity_curve["shares"] = equity_curve["shares"].fillna(0.0).cumsum()
    equity_curve["value"] = equity_curve["shares"] * equity_curve[price_col]
    invested_events = transactions.groupby("execution_date", as_index=False)["amount"].sum()
    equity_curve = equity_curve.merge(
        invested_events,
        how="left",
        left_on="date",
        right_on="execution_date",
        suffixes=("", "_invested"),
    )
    equity_curve["amount"] = equity_curve["amount"].fillna(0.0)
    equity_curve["cumulative_invested"] = equity_curve["amount"].cumsum()
    equity_curve["return_on_invested"] = (
        equity_curve["value"] / equity_curve["cumulative_invested"] - 1.0
    ).where(equity_curve["cumulative_invested"] > 0)
    equity_curve = equity_curve.drop(columns=[column for column in ["execution_date", "execution_date_invested"] if column in equity_curve.columns])

    first_buy = pd.Timestamp(transactions["execution_date"].min())
    last_buy = pd.Timestamp(transactions["execution_date"].max())
    summary: dict[str, object] = {
        "symbol": symbol,
        "price_column": price_col,
        "start_date": start_ts.date().isoformat(),
        "first_buy_date": first_buy.date().isoformat(),
        "last_buy_date": last_buy.date().isoformat(),
        "final_price_date": pd.Timestamp(final_date).date().isoformat(),
        "amount_per_purchase": float(amount),
        "every_weeks": int(every_weeks),
        "purchases": int(len(transactions)),
        "total_invested": total_invested,
        "ending_value": ending_value,
        "gain_loss": gain_loss,
        "total_return_pct": total_return * 100.0,
        "money_weighted_annual_return_pct": None if money_weighted is None else money_weighted * 100.0,
        "shares": total_shares,
        "final_price": final_price,
        "assumptions": "fractional shares; scheduled date or next trading day; adjusted close by default; no taxes, fees, spread, or slippage",
    }
    return DCAResult(symbol=symbol, summary=summary, transactions=transactions, equity_curve=equity_curve)


def compare_dca(
    prices: pd.DataFrame,
    *,
    symbols: Iterable[str],
    amount: float,
    every_weeks: int,
    start: str | date | datetime | pd.Timestamp,
    end: str | date | datetime | pd.Timestamp | None = None,
    price_col: str = "adj_close",
) -> list[DCAResult]:
    return [
        simulate_dca(
            prices,
            symbol=symbol,
            amount=amount,
            every_weeks=every_weeks,
            start=start,
            end=end,
            price_col=price_col,
        )
        for symbol in symbols
    ]


def summary_frame(results: Iterable[DCAResult]) -> pd.DataFrame:
    return pd.DataFrame([result.summary for result in results])
