from __future__ import annotations

import pandas as pd

from longterm_research.dca import simulate_dca
from longterm_research.dip_buying import simulate_reserve_dip_buying
from longterm_research.metrics import calculate_return_metrics, time_weighted_returns


def test_simulate_dca_uses_next_trading_day_for_weekend_schedule() -> None:
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-05", "2024-01-08", "2024-01-22"]),
            "symbol": ["SPY", "SPY", "SPY"],
            "adj_close": [100.0, 110.0, 121.0],
        }
    )

    result = simulate_dca(
        prices,
        symbol="SPY",
        amount=110.0,
        every_weeks=2,
        start="2024-01-06",
        end="2024-01-22",
    )

    assert result.summary["purchases"] == 2
    assert result.summary["total_invested"] == 220.0
    assert list(result.transactions["execution_date"].dt.strftime("%Y-%m-%d")) == [
        "2024-01-08",
        "2024-01-22",
    ]
    assert round(float(result.summary["shares"]), 8) == round(110.0 / 110.0 + 110.0 / 121.0, 8)


def test_simulate_dca_reports_gain_loss_from_adjusted_close() -> None:
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-15", "2024-01-29"]),
            "symbol": ["QQQ", "QQQ", "QQQ"],
            "adj_close": [100.0, 100.0, 200.0],
        }
    )

    result = simulate_dca(
        prices,
        symbol="QQQ",
        amount=100.0,
        every_weeks=2,
        start="2024-01-01",
        end="2024-01-29",
    )

    assert result.summary["purchases"] == 3
    assert result.summary["total_invested"] == 300.0
    assert result.summary["ending_value"] == 500.0
    assert round(float(result.summary["total_return_pct"]), 6) == round((200.0 / 300.0) * 100.0, 6)


def test_reserve_dip_buying_transfers_cycle_start_reserve_tranches() -> None:
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"] * 2
            ),
            "symbol": ["SPY"] * 4 + ["SGOV"] * 4,
            "adj_close": [100.0, 90.0, 80.0, 60.0, 10.0, 10.0, 10.0, 10.0],
        }
    )

    result = simulate_reserve_dip_buying(
        prices,
        target_symbol="SPY",
        reserve_symbol="SGOV",
        amount=1000.0,
        every_weeks=52,
        start="2024-01-01",
        end="2024-01-04",
        thresholds=[0.10, 0.20, 0.30, 0.40],
        tranche_fraction=0.25,
    )

    assert result.summary["dip_transfers"] == 4
    assert result.transfers["reserve_value_sold"].round(8).tolist() == [75.0, 75.0, 75.0, 75.0]
    assert result.equity_curve["reserve_value"].iloc[-1] == 0.0


def test_reserve_dip_buying_uses_common_start_when_reserve_starts_later() -> None:
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-02"]),
            "symbol": ["QQQ", "QQQ", "SGOV"],
            "adj_close": [100.0, 101.0, 10.0],
        }
    )

    result = simulate_reserve_dip_buying(
        prices,
        target_symbol="QQQ",
        reserve_symbol="SGOV",
        amount=100.0,
        every_weeks=2,
        start="2024-01-01",
        end="2024-01-02",
    )

    assert result.summary["requested_start_date"] == "2024-01-01"
    assert result.summary["effective_start_date"] == "2024-01-02"


def test_time_weighted_returns_remove_external_flows() -> None:
    equity = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]),
            "value": [100.0, 210.0, 220.0],
            "amount": [100.0, 100.0, 0.0],
        }
    )

    returns = time_weighted_returns(equity, value_col="value", flow_col="amount")

    assert round(float(returns.iloc[0]), 8) == 0.10
    assert round(float(returns.iloc[1]), 8) == round(220.0 / 210.0 - 1.0, 8)


def test_beta_calculation_against_benchmark_returns() -> None:
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    benchmark = pd.Series([0.01, -0.02, 0.015, 0.005], index=dates)
    portfolio = benchmark * 2.0

    metrics = calculate_return_metrics(portfolio, benchmark=benchmark)

    assert round(float(metrics.beta), 8) == 2.0
    assert round(float(metrics.r_squared), 8) == 1.0


def test_volatility_drag_uses_no_volatility_compounded_path() -> None:
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    returns = pd.Series([0.10, -0.10], index=dates)

    metrics = calculate_return_metrics(returns, annualization=2)

    assert round(metrics.annual_arithmetic_compounded_return_pct, 8) == 0.0
    assert round(metrics.annual_geometric_return_pct, 8) == -1.0
    assert round(metrics.volatility_drag_pct, 8) == 1.0
