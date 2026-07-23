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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare recurring contribution outcomes across tickers.")
    parser.add_argument("symbols", nargs="+", help="Tickers to compare, e.g. SPY QQQ")
    parser.add_argument("--amount", type=float, required=True, help="Contribution amount per purchase.")
    parser.add_argument("--every-weeks", type=int, default=2, help="Purchase interval in weeks.")
    parser.add_argument("--start", help="Inclusive start date, YYYY-MM-DD.")
    parser.add_argument("--end", default=date.today().isoformat(), help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument("--years", type=int, help="Set start date to N years before --end.")
    parser.add_argument("--price-col", default="adj_close", choices=["adj_close", "close"])
    parser.add_argument("--fetch", action="store_true", help="Fetch or refresh missing price data before simulation.")
    parser.add_argument("--force-fetch", action="store_true", help="Fetch price data even if cache exists.")
    parser.add_argument("--output-dir", help="Directory for CSV/JSON artifacts.")
    return parser.parse_args()


def _format_money(value: float) -> str:
    return f"${value:,.2f}"


def _format_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value:,.2f}%"


def _print_summary(frame: pd.DataFrame) -> None:
    columns = [
        "symbol",
        "purchases",
        "total_invested",
        "ending_value",
        "gain_loss",
        "total_return_pct",
        "money_weighted_annual_return_pct",
        "final_price_date",
    ]
    print("\nDCA comparison")
    print("--------------")
    for row in frame[columns].itertuples(index=False):
        print(
            f"{row.symbol}: buys={row.purchases} invested={_format_money(row.total_invested)} "
            f"value={_format_money(row.ending_value)} gain={_format_money(row.gain_loss)} "
            f"return={_format_pct(row.total_return_pct)} "
            f"mwr={_format_pct(row.money_weighted_annual_return_pct)} "
            f"final_price_date={row.final_price_date}"
        )


def main() -> None:
    args = parse_args()
    symbols = normalize_symbols(args.symbols)
    if args.start:
        start = args.start
    elif args.years:
        start = start_from_years(args.end, args.years).date().isoformat()
    else:
        raise SystemExit("Provide --start or --years.")

    if args.fetch or args.force_fetch:
        ensure_yfinance_prices(symbols, start=start, end=args.end, force=args.force_fetch)

    prices = load_cached_prices(symbols, start=start, end=args.end)
    results = compare_dca(
        prices,
        symbols=symbols,
        amount=args.amount,
        every_weeks=args.every_weeks,
        start=start,
        end=args.end,
        price_col=args.price_col,
    )
    summary = summary_frame(results)
    _print_summary(summary)

    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        slug = "_".join(symbols).lower()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = ROOT / "data" / "results" / f"dca_{slug}_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / "summary.csv"
    summary.to_csv(summary_path, index=False)
    (output_dir / "summary.json").write_text(json.dumps(summary.to_dict(orient="records"), indent=2))

    transactions = pd.concat([result.transactions for result in results], ignore_index=True)
    transactions.to_csv(output_dir / "transactions.csv", index=False)

    equity = pd.concat([result.equity_curve for result in results], ignore_index=True)
    equity.to_csv(output_dir / "equity_curve.csv", index=False)
    print(f"\nWrote artifacts: {output_dir}")


if __name__ == "__main__":
    main()
