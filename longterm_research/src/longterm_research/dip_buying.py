from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable

import pandas as pd

from .data import parse_date
from .dca import _as_price_frame, _xirr


@dataclass(frozen=True)
class DipBuyingResult:
    target_symbol: str
    reserve_symbol: str
    summary: dict[str, object]
    contributions: pd.DataFrame
    transfers: pd.DataFrame
    equity_curve: pd.DataFrame


def _joined_prices(
    prices: pd.DataFrame,
    *,
    target_symbol: str,
    reserve_symbol: str,
    price_col: str,
    requested_start: pd.Timestamp,
    requested_end: pd.Timestamp | None,
) -> pd.DataFrame:
    target = _as_price_frame(prices, target_symbol, price_col)[["date", price_col]].rename(
        columns={price_col: "target_price"}
    )
    reserve = _as_price_frame(prices, reserve_symbol, price_col)[["date", price_col]].rename(
        columns={price_col: "reserve_price"}
    )
    joined = target.merge(reserve, on="date", how="inner").sort_values("date")
    if requested_end is not None:
        joined = joined[joined["date"] <= requested_end]
    joined = joined[joined["date"] >= requested_start]
    if joined.empty:
        raise ValueError(
            f"No common dates for {target_symbol.upper()} and {reserve_symbol.upper()} "
            f"from {requested_start.date()}."
        )
    return joined.reset_index(drop=True)


def _max_drawdown(values: pd.Series) -> float:
    running_peak = values.cummax()
    drawdowns = values / running_peak - 1.0
    return float(drawdowns.min()) if not drawdowns.empty else 0.0


def _first_common_date(prices: pd.DataFrame, symbols: Iterable[str], price_col: str) -> pd.Timestamp:
    first_dates = []
    for symbol in symbols:
        frame = _as_price_frame(prices, symbol, price_col)
        first_dates.append(frame["date"].min())
    return max(first_dates)


def simulate_reserve_dip_buying(
    prices: pd.DataFrame,
    *,
    target_symbol: str,
    reserve_symbol: str,
    amount: float,
    every_weeks: int,
    start: str | date | datetime | pd.Timestamp,
    end: str | date | datetime | pd.Timestamp | None = None,
    target_weight: float = 0.70,
    reserve_weight: float = 0.30,
    thresholds: Iterable[float] = (0.10, 0.20, 0.30, 0.40),
    tranche_fraction: float = 0.25,
    price_col: str = "adj_close",
) -> DipBuyingResult:
    if amount <= 0:
        raise ValueError("amount must be positive.")
    if every_weeks <= 0:
        raise ValueError("every_weeks must be positive.")
    if target_weight < 0 or reserve_weight < 0:
        raise ValueError("weights must be non-negative.")
    if abs((target_weight + reserve_weight) - 1.0) > 1e-9:
        raise ValueError("target_weight + reserve_weight must equal 1.0.")
    if tranche_fraction <= 0:
        raise ValueError("tranche_fraction must be positive.")

    target_symbol = target_symbol.upper()
    reserve_symbol = reserve_symbol.upper()
    requested_start = parse_date(start)
    requested_end = parse_date(end)
    common_start = _first_common_date(prices, [target_symbol, reserve_symbol], price_col)
    effective_start = max(requested_start, common_start)
    joined = _joined_prices(
        prices,
        target_symbol=target_symbol,
        reserve_symbol=reserve_symbol,
        price_col=price_col,
        requested_start=effective_start,
        requested_end=requested_end,
    )
    trading_dates = pd.DatetimeIndex(joined["date"])
    final_date = trading_dates.max()
    schedule = pd.date_range(start=effective_start, end=final_date, freq=f"{every_weeks * 7}D")
    schedule_positions: set[int] = set()
    for scheduled_date in schedule:
        loc = trading_dates.searchsorted(scheduled_date, side="left")
        if loc < len(trading_dates):
            schedule_positions.add(int(loc))

    ordered_thresholds = sorted({float(threshold) for threshold in thresholds})
    if any(threshold <= 0 or threshold >= 1 for threshold in ordered_thresholds):
        raise ValueError("thresholds must be between 0 and 1.")

    target_shares = 0.0
    reserve_shares = 0.0
    total_contributed = 0.0
    peak_price: float | None = None
    peak_date: pd.Timestamp | None = None
    triggered_thresholds: set[float] = set()
    cycle_start_reserve_value = 0.0

    contribution_rows: list[dict[str, object]] = []
    transfer_rows: list[dict[str, object]] = []
    equity_rows: list[dict[str, object]] = []

    for pos, row in enumerate(joined.itertuples(index=False)):
        current_date = pd.Timestamp(row.date)
        target_price = float(row.target_price)
        reserve_price = float(row.reserve_price)
        if target_price <= 0 or reserve_price <= 0:
            raise ValueError(f"Non-positive price on {current_date.date()}.")

        if pos in schedule_positions:
            target_amount = amount * target_weight
            reserve_amount = amount * reserve_weight
            target_buy_shares = target_amount / target_price
            reserve_buy_shares = reserve_amount / reserve_price
            target_shares += target_buy_shares
            reserve_shares += reserve_buy_shares
            total_contributed += amount
            contribution_rows.append(
                {
                    "date": current_date,
                    "target_symbol": target_symbol,
                    "reserve_symbol": reserve_symbol,
                    "amount": float(amount),
                    "target_amount": target_amount,
                    "reserve_amount": reserve_amount,
                    "target_price": target_price,
                    "reserve_price": reserve_price,
                    "target_shares_bought": target_buy_shares,
                    "reserve_shares_bought": reserve_buy_shares,
                }
            )

        if peak_price is None or target_price > peak_price:
            peak_price = target_price
            peak_date = current_date
            triggered_thresholds = set()
            cycle_start_reserve_value = reserve_shares * reserve_price

        drawdown = target_price / peak_price - 1.0
        for threshold in ordered_thresholds:
            if threshold in triggered_thresholds or drawdown > -threshold:
                continue
            requested_transfer_value = cycle_start_reserve_value * tranche_fraction
            available_reserve_value = reserve_shares * reserve_price
            transfer_value = min(requested_transfer_value, available_reserve_value)
            if transfer_value <= 0:
                triggered_thresholds.add(threshold)
                continue
            reserve_shares_sold = transfer_value / reserve_price
            target_shares_bought = transfer_value / target_price
            reserve_shares -= reserve_shares_sold
            target_shares += target_shares_bought
            triggered_thresholds.add(threshold)
            transfer_rows.append(
                {
                    "date": current_date,
                    "threshold": threshold,
                    "drawdown_pct": drawdown * 100.0,
                    "peak_date": peak_date,
                    "peak_price": peak_price,
                    "reserve_value_sold": transfer_value,
                    "reserve_price": reserve_price,
                    "reserve_shares_sold": reserve_shares_sold,
                    "target_price": target_price,
                    "target_shares_bought": target_shares_bought,
                    "cycle_start_reserve_value": cycle_start_reserve_value,
                }
            )

        target_value = target_shares * target_price
        reserve_value = reserve_shares * reserve_price
        total_value = target_value + reserve_value
        equity_rows.append(
            {
                "date": current_date,
                "target_symbol": target_symbol,
                "reserve_symbol": reserve_symbol,
                "target_price": target_price,
                "reserve_price": reserve_price,
                "target_shares": target_shares,
                "reserve_shares": reserve_shares,
                "target_value": target_value,
                "reserve_value": reserve_value,
                "total_value": total_value,
                "total_contributed": total_contributed,
                "drawdown_from_target_peak_pct": drawdown * 100.0,
                "target_weight_actual": target_value / total_value if total_value else 0.0,
                "reserve_weight_actual": reserve_value / total_value if total_value else 0.0,
            }
        )

    contributions = pd.DataFrame(contribution_rows)
    transfers = pd.DataFrame(transfer_rows)
    equity_curve = pd.DataFrame(equity_rows)
    if contributions.empty or equity_curve.empty:
        raise ValueError("Simulation produced no portfolio rows.")

    ending_value = float(equity_curve["total_value"].iloc[-1])
    gain_loss = ending_value - total_contributed
    total_return = gain_loss / total_contributed if total_contributed else 0.0
    cash_flows = [
        (pd.Timestamp(row.date), -float(row.amount))
        for row in contributions.itertuples(index=False)
    ]
    cash_flows.append((final_date, ending_value))
    money_weighted = _xirr(cash_flows)
    summary: dict[str, object] = {
        "strategy": "reserve_dip_buying",
        "target_symbol": target_symbol,
        "reserve_symbol": reserve_symbol,
        "price_column": price_col,
        "requested_start_date": requested_start.date().isoformat(),
        "effective_start_date": effective_start.date().isoformat(),
        "final_price_date": pd.Timestamp(final_date).date().isoformat(),
        "amount_per_purchase": float(amount),
        "every_weeks": int(every_weeks),
        "target_weight": float(target_weight),
        "reserve_weight": float(reserve_weight),
        "thresholds": ",".join(f"{threshold:.2f}" for threshold in ordered_thresholds),
        "tranche_fraction_of_cycle_start_reserve": float(tranche_fraction),
        "contributions": int(len(contributions)),
        "dip_transfers": int(len(transfers)),
        "total_contributed": float(total_contributed),
        "ending_value": ending_value,
        "gain_loss": gain_loss,
        "total_return_pct": total_return * 100.0,
        "money_weighted_annual_return_pct": None if money_weighted is None else money_weighted * 100.0,
        "max_drawdown_pct": _max_drawdown(equity_curve["total_value"]) * 100.0,
        "ending_target_value": float(equity_curve["target_value"].iloc[-1]),
        "ending_reserve_value": float(equity_curve["reserve_value"].iloc[-1]),
        "ending_target_weight": float(equity_curve["target_weight_actual"].iloc[-1]),
        "ending_reserve_weight": float(equity_curve["reserve_weight_actual"].iloc[-1]),
        "assumptions": "fractional shares; scheduled contribution date or next trading day; thresholds use target drawdown from prior adjusted-close peak; each threshold sells 25% of cycle-start reserve value, capped by available reserve; no taxes, fees, spread, or slippage",
    }
    return DipBuyingResult(
        target_symbol=target_symbol,
        reserve_symbol=reserve_symbol,
        summary=summary,
        contributions=contributions,
        transfers=transfers,
        equity_curve=equity_curve,
    )


def dip_summary_frame(results: Iterable[DipBuyingResult]) -> pd.DataFrame:
    return pd.DataFrame([result.summary for result in results])
