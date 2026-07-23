#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from longterm_research.data import ensure_yfinance_prices, normalize_symbols, start_from_years


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and cache adjusted daily ETF/equity prices.")
    parser.add_argument("symbols", nargs="+", help="Tickers to fetch, e.g. SPY QQQ DBMF")
    parser.add_argument("--provider", choices=["yfinance"], default="yfinance")
    parser.add_argument("--start", help="Inclusive start date, YYYY-MM-DD.")
    parser.add_argument("--end", default=date.today().isoformat(), help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument("--years", type=int, help="Set start date to N years before --end.")
    parser.add_argument("--force", action="store_true", help="Refresh even if cache appears to cover the range.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = normalize_symbols(args.symbols)
    if args.start:
        start = args.start
    elif args.years:
        start = start_from_years(args.end, args.years).date().isoformat()
    else:
        raise SystemExit("Provide --start or --years.")

    coverages = ensure_yfinance_prices(
        symbols,
        start=start,
        end=args.end,
        force=args.force,
    )
    print(f"provider={args.provider} start={start} end={args.end}")
    for coverage in coverages:
        first = coverage.first_date.date().isoformat() if coverage.first_date is not None else "missing"
        last = coverage.last_date.date().isoformat() if coverage.last_date is not None else "missing"
        print(f"{coverage.symbol}: rows={coverage.rows} first={first} last={last} path={coverage.path}")


if __name__ == "__main__":
    main()
