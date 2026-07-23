from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class ReturnMetrics:
    annual_arithmetic_return_pct: float
    annual_arithmetic_compounded_return_pct: float
    annual_geometric_return_pct: float
    annual_volatility_pct: float
    volatility_drag_pct: float
    volatility_drag_approx_pct: float
    cumulative_time_weighted_return_pct: float
    beta: float | None
    correlation: float | None
    r_squared: float | None
    observations: int


def time_weighted_returns(
    equity_curve: pd.DataFrame,
    *,
    date_col: str = "date",
    value_col: str = "value",
    flow_col: str | None = None,
    flows: pd.DataFrame | None = None,
    flow_date_col: str = "date",
    flow_amount_col: str = "amount",
) -> pd.Series:
    required = {date_col, value_col}
    missing = required - set(equity_curve.columns)
    if missing:
        raise ValueError(f"Equity curve missing required columns: {', '.join(sorted(missing))}")

    frame = equity_curve[[date_col, value_col]].copy()
    frame[date_col] = pd.to_datetime(frame[date_col]).dt.tz_localize(None).dt.normalize()
    frame = frame.sort_values(date_col).drop_duplicates(subset=[date_col], keep="last")
    frame["external_flow"] = 0.0

    if flow_col is not None:
        if flow_col not in equity_curve.columns:
            raise ValueError(f"Equity curve missing flow column: {flow_col}")
        flow_frame = equity_curve[[date_col, flow_col]].copy()
        flow_frame[date_col] = pd.to_datetime(flow_frame[date_col]).dt.tz_localize(None).dt.normalize()
        daily_flows = flow_frame.groupby(date_col, as_index=False)[flow_col].sum()
        frame = frame.drop(columns=["external_flow"]).merge(
            daily_flows.rename(columns={flow_col: "external_flow"}),
            on=date_col,
            how="left",
        )
        frame["external_flow"] = frame["external_flow"].fillna(0.0)

    if flows is not None and not flows.empty:
        flow_frame = flows[[flow_date_col, flow_amount_col]].copy()
        flow_frame[flow_date_col] = pd.to_datetime(flow_frame[flow_date_col]).dt.tz_localize(None).dt.normalize()
        daily_flows = flow_frame.groupby(flow_date_col, as_index=False)[flow_amount_col].sum()
        frame = frame.merge(
            daily_flows.rename(
                columns={flow_date_col: date_col, flow_amount_col: "external_flow_extra"}
            ),
            on=date_col,
            how="left",
        )
        frame["external_flow"] = frame["external_flow"] + frame["external_flow_extra"].fillna(0.0)
        frame = frame.drop(columns=["external_flow_extra"])

    previous_value = frame[value_col].shift(1)
    returns = (frame[value_col] - frame["external_flow"]) / previous_value - 1.0
    returns = returns.where(previous_value > 0)
    returns.index = pd.DatetimeIndex(frame[date_col])
    return returns.replace([np.inf, -np.inf], np.nan).dropna()


def benchmark_returns(
    prices: pd.DataFrame,
    *,
    benchmark_symbol: str,
    price_col: str = "adj_close",
) -> pd.Series:
    required = {"date", "symbol", price_col}
    missing = required - set(prices.columns)
    if missing:
        raise ValueError(f"Price data missing required columns: {', '.join(sorted(missing))}")
    frame = prices[prices["symbol"].str.upper() == benchmark_symbol.upper()].copy()
    if frame.empty:
        raise ValueError(f"No benchmark prices found for {benchmark_symbol.upper()}.")
    frame["date"] = pd.to_datetime(frame["date"]).dt.tz_localize(None).dt.normalize()
    frame = frame.dropna(subset=[price_col]).sort_values("date").drop_duplicates("date", keep="last")
    returns = frame.set_index("date")[price_col].pct_change()
    return returns.replace([np.inf, -np.inf], np.nan).dropna()


def calculate_return_metrics(
    returns: pd.Series,
    *,
    benchmark: pd.Series | None = None,
    annualization: int = TRADING_DAYS_PER_YEAR,
) -> ReturnMetrics:
    clean = returns.replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        raise ValueError("No returns available for metrics.")

    mean_daily = float(clean.mean())
    arithmetic_annual = float(mean_daily * annualization)
    arithmetic_compounded_annual = float((1.0 + mean_daily) ** annualization - 1.0)
    geometric_annual = float(np.expm1(np.log1p(clean).mean() * annualization))
    annual_volatility = float(clean.std(ddof=1) * sqrt(annualization)) if len(clean) > 1 else 0.0
    volatility_drag = arithmetic_compounded_annual - geometric_annual
    volatility_drag_approx = 0.5 * annual_volatility * annual_volatility
    cumulative = float((1.0 + clean).prod() - 1.0)

    beta = None
    correlation = None
    r_squared = None
    if benchmark is not None:
        aligned = pd.concat(
            [
                clean.rename("portfolio"),
                benchmark.replace([np.inf, -np.inf], np.nan).dropna().rename("benchmark"),
            ],
            axis=1,
            join="inner",
        ).dropna()
        if len(aligned) > 1:
            benchmark_var = float(aligned["benchmark"].var(ddof=1))
            if benchmark_var > 0:
                beta = float(aligned["portfolio"].cov(aligned["benchmark"]) / benchmark_var)
            correlation_value = aligned["portfolio"].corr(aligned["benchmark"])
            if pd.notna(correlation_value):
                correlation = float(correlation_value)
                r_squared = float(correlation * correlation)

    return ReturnMetrics(
        annual_arithmetic_return_pct=arithmetic_annual * 100.0,
        annual_arithmetic_compounded_return_pct=arithmetic_compounded_annual * 100.0,
        annual_geometric_return_pct=geometric_annual * 100.0,
        annual_volatility_pct=annual_volatility * 100.0,
        volatility_drag_pct=volatility_drag * 100.0,
        volatility_drag_approx_pct=volatility_drag_approx * 100.0,
        cumulative_time_weighted_return_pct=cumulative * 100.0,
        beta=beta,
        correlation=correlation,
        r_squared=r_squared,
        observations=int(len(clean)),
    )


def metrics_to_dict(metrics: ReturnMetrics, *, prefix: str = "") -> dict[str, float | int | None]:
    return {
        f"{prefix}annual_arithmetic_return_pct": metrics.annual_arithmetic_return_pct,
        f"{prefix}annual_arithmetic_compounded_return_pct": metrics.annual_arithmetic_compounded_return_pct,
        f"{prefix}annual_geometric_return_pct": metrics.annual_geometric_return_pct,
        f"{prefix}annual_volatility_pct": metrics.annual_volatility_pct,
        f"{prefix}volatility_drag_pct": metrics.volatility_drag_pct,
        f"{prefix}volatility_drag_approx_pct": metrics.volatility_drag_approx_pct,
        f"{prefix}cumulative_time_weighted_return_pct": metrics.cumulative_time_weighted_return_pct,
        f"{prefix}beta": metrics.beta,
        f"{prefix}correlation": metrics.correlation,
        f"{prefix}r_squared": metrics.r_squared,
        f"{prefix}return_observations": metrics.observations,
    }
