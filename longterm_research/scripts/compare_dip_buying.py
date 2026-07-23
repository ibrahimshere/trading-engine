#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from longterm_research.data import (
    ensure_yfinance_prices,
    load_cached_prices,
    normalize_symbols,
    start_from_years,
)
from longterm_research.dca import compare_dca, summary_frame
from longterm_research.dip_buying import dip_summary_frame, simulate_reserve_dip_buying
from longterm_research.metrics import (
    benchmark_returns,
    calculate_return_metrics,
    metrics_to_dict,
    time_weighted_returns,
)


def _max_drawdown(values: pd.Series) -> float:
    running_peak = values.cummax()
    drawdowns = values / running_peak - 1.0
    return float(drawdowns.min()) if not drawdowns.empty else 0.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare reserve-funded dip buying against blind DCA.")
    parser.add_argument("targets", nargs="+", help="Target tickers to compare, e.g. SPY QQQ")
    parser.add_argument("--reserve", default="SGOV", help="Reserve ticker used for staged dip buys.")
    parser.add_argument("--benchmark", default="SPY", help="Benchmark ticker for beta/correlation.")
    parser.add_argument("--amount", type=float, default=1000.0, help="Contribution amount per purchase.")
    parser.add_argument("--every-weeks", type=int, default=2, help="Contribution interval in weeks.")
    parser.add_argument("--years", type=int, default=20, help="Requested lookback ending at --end.")
    parser.add_argument("--start", help="Inclusive requested start date, YYYY-MM-DD.")
    parser.add_argument("--end", default=date.today().isoformat(), help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument("--target-weight", type=float, default=0.70)
    parser.add_argument("--reserve-weight", type=float, default=0.30)
    parser.add_argument("--thresholds", default="0.10,0.20,0.30,0.40")
    parser.add_argument("--tranche-fraction", type=float, default=0.25)
    parser.add_argument("--price-col", default="adj_close", choices=["adj_close", "close"])
    parser.add_argument("--fetch", action="store_true", help="Fetch or refresh missing price data before simulation.")
    parser.add_argument("--force-fetch", action="store_true", help="Fetch price data even if cache exists.")
    parser.add_argument("--output-dir", help="Directory for CSV/JSON artifacts.")
    return parser.parse_args()


def _parse_thresholds(raw: str) -> list[float]:
    values = [float(part.strip()) for part in raw.split(",") if part.strip()]
    if not values:
        raise ValueError("At least one threshold is required.")
    return values


def _format_money(value: float) -> str:
    return f"${value:,.2f}"


def _format_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value:,.2f}%"


def main() -> None:
    args = parse_args()
    targets = normalize_symbols(args.targets)
    reserve = args.reserve.strip().upper()
    benchmark = args.benchmark.strip().upper()
    all_symbols = normalize_symbols([*targets, reserve, benchmark])
    start = args.start or start_from_years(args.end, args.years).date().isoformat()
    thresholds = _parse_thresholds(args.thresholds)

    if args.fetch or args.force_fetch:
        ensure_yfinance_prices(all_symbols, start=start, end=args.end, force=args.force_fetch)

    prices = load_cached_prices(all_symbols, start=start, end=args.end)
    dip_results = [
        simulate_reserve_dip_buying(
            prices,
            target_symbol=target,
            reserve_symbol=reserve,
            amount=args.amount,
            every_weeks=args.every_weeks,
            start=start,
            end=args.end,
            target_weight=args.target_weight,
            reserve_weight=args.reserve_weight,
            thresholds=thresholds,
            tranche_fraction=args.tranche_fraction,
            price_col=args.price_col,
        )
        for target in targets
    ]
    benchmark_daily_returns = benchmark_returns(prices, benchmark_symbol=benchmark, price_col=args.price_col)
    dip_summary = dip_summary_frame(dip_results)
    dip_metric_rows = []
    for result in dip_results:
        returns = time_weighted_returns(
            result.equity_curve,
            value_col="total_value",
            flows=result.contributions,
            flow_amount_col="amount",
        )
        dip_metric_rows.append(
            {
                "target_symbol": result.target_symbol,
                **metrics_to_dict(
                    calculate_return_metrics(returns, benchmark=benchmark_daily_returns),
                    prefix="dip_",
                ),
            }
        )
    dip_metrics = pd.DataFrame(dip_metric_rows)
    dip_summary = dip_summary.merge(dip_metrics, on="target_symbol", how="left")
    effective_start_by_target = {
        str(row.target_symbol): str(row.effective_start_date)
        for row in dip_summary.itertuples(index=False)
    }
    dca_results = []
    for target in targets:
        dca_results.extend(
            compare_dca(
                prices,
                symbols=[target],
                amount=args.amount,
                every_weeks=args.every_weeks,
                start=effective_start_by_target[target],
                end=args.end,
                price_col=args.price_col,
            )
        )
    dca_summary = summary_frame(dca_results)
    dca_metric_rows = []
    for result in dca_results:
        returns = time_weighted_returns(
            result.equity_curve,
            value_col="value",
            flow_col="amount",
        )
        dca_metric_rows.append(
            {
                "target_symbol": result.symbol,
                **metrics_to_dict(
                    calculate_return_metrics(returns, benchmark=benchmark_daily_returns),
                    prefix="dca_",
                ),
            }
        )
    dca_metrics = pd.DataFrame(dca_metric_rows)
    dca_summary["dca_max_drawdown_pct"] = [
        _max_drawdown(result.equity_curve["value"]) * 100.0
        for result in dca_results
    ]
    dca_summary = dca_summary.rename(
        columns={
            "symbol": "target_symbol",
            "total_invested": "dca_total_contributed",
            "ending_value": "dca_ending_value",
            "gain_loss": "dca_gain_loss",
            "total_return_pct": "dca_total_return_pct",
            "money_weighted_annual_return_pct": "dca_money_weighted_annual_return_pct",
        }
    )
    dca_summary = dca_summary.merge(dca_metrics, on="target_symbol", how="left")
    comparison = dip_summary.merge(
        dca_summary[
            [
                "target_symbol",
                "dca_total_contributed",
                "dca_ending_value",
                "dca_gain_loss",
                "dca_total_return_pct",
                "dca_money_weighted_annual_return_pct",
                "dca_max_drawdown_pct",
                "dca_annual_arithmetic_return_pct",
                "dca_annual_arithmetic_compounded_return_pct",
                "dca_annual_geometric_return_pct",
                "dca_annual_volatility_pct",
                "dca_volatility_drag_pct",
                "dca_volatility_drag_approx_pct",
                "dca_cumulative_time_weighted_return_pct",
                "dca_beta",
                "dca_correlation",
                "dca_r_squared",
                "dca_return_observations",
            ]
        ],
        on="target_symbol",
        how="left",
    )
    comparison["ending_value_diff_vs_dca"] = comparison["ending_value"] - comparison["dca_ending_value"]
    comparison["return_pct_diff_vs_dca"] = comparison["total_return_pct"] - comparison["dca_total_return_pct"]
    comparison["mwr_pct_diff_vs_dca"] = (
        comparison["money_weighted_annual_return_pct"]
        - comparison["dca_money_weighted_annual_return_pct"]
    )

    print("\nDip buying vs blind DCA")
    print("-----------------------")
    for row in comparison.itertuples(index=False):
        print(
            f"{row.target_symbol}+{row.reserve_symbol}: effective_start={row.effective_start_date} "
            f"contrib={row.contributions} transfers={row.dip_transfers} "
            f"dip_value={_format_money(row.ending_value)} dca_value={_format_money(row.dca_ending_value)} "
            f"diff={_format_money(row.ending_value_diff_vs_dca)} "
            f"dip_mwr={_format_pct(row.money_weighted_annual_return_pct)} "
            f"dca_mwr={_format_pct(row.dca_money_weighted_annual_return_pct)} "
            f"dip_dd={_format_pct(row.max_drawdown_pct)} dca_dd={_format_pct(row.dca_max_drawdown_pct)} "
            f"dip_beta={row.dip_beta:.2f} dca_beta={row.dca_beta:.2f} "
            f"dip_drag={_format_pct(row.dip_volatility_drag_pct)} "
            f"dca_drag={_format_pct(row.dca_volatility_drag_pct)}"
        )

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        slug = "_".join([*targets, reserve]).lower()
        weight_slug = (
            f"tw{int(round(args.target_weight * 100)):02d}_"
            f"rw{int(round(args.reserve_weight * 100)):02d}"
        )
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = ROOT / "data" / "results" / f"dip_buying_{slug}_{weight_slug}_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    comparison.to_csv(output_dir / "comparison.csv", index=False)
    (output_dir / "comparison.json").write_text(json.dumps(comparison.to_dict(orient="records"), indent=2))
    dip_summary.to_csv(output_dir / "dip_summary.csv", index=False)
    dca_summary.to_csv(output_dir / "dca_summary.csv", index=False)
    risk_cols = [
        column
        for column in comparison.columns
        if column.startswith("dip_") or column.startswith("dca_") or column == "target_symbol"
    ]
    comparison[risk_cols].to_csv(output_dir / "risk_metrics.csv", index=False)

    contributions = pd.concat(
        [
            result.contributions.assign(scenario=f"{result.target_symbol}_{result.reserve_symbol}")
            for result in dip_results
        ],
        ignore_index=True,
    )
    transfers = pd.concat(
        [
            result.transfers.assign(scenario=f"{result.target_symbol}_{result.reserve_symbol}")
            for result in dip_results
            if not result.transfers.empty
        ],
        ignore_index=True,
    ) if any(not result.transfers.empty for result in dip_results) else pd.DataFrame()
    equity = pd.concat(
        [
            result.equity_curve.assign(scenario=f"{result.target_symbol}_{result.reserve_symbol}")
            for result in dip_results
        ],
        ignore_index=True,
    )
    contributions.to_csv(output_dir / "dip_contributions.csv", index=False)
    transfers.to_csv(output_dir / "dip_transfers.csv", index=False)
    equity.to_csv(output_dir / "dip_equity_curve.csv", index=False)
    print(f"\nWrote artifacts: {output_dir}")


if __name__ == "__main__":
    main()
