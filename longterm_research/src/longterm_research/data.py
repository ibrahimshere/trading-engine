from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import pandas as pd


SOURCE_YFINANCE = "yfinance"


@dataclass(frozen=True)
class PriceCoverage:
    symbol: str
    rows: int
    first_date: pd.Timestamp | None
    last_date: pd.Timestamp | None
    path: Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_data_dir() -> Path:
    return project_root() / "data"


def normalize_symbols(symbols: Iterable[str]) -> list[str]:
    cleaned = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
    if not cleaned:
        raise ValueError("At least one symbol is required.")
    return list(dict.fromkeys(cleaned))


def parse_date(value: str | date | datetime | pd.Timestamp | None) -> pd.Timestamp | None:
    if value is None:
        return None
    return pd.Timestamp(value).tz_localize(None).normalize()


def end_for_yfinance(end: str | date | datetime | pd.Timestamp | None) -> str | None:
    parsed = parse_date(end)
    if parsed is None:
        return None
    return (parsed + pd.Timedelta(days=1)).date().isoformat()


def start_from_years(end: str | date | datetime | pd.Timestamp | None, years: int) -> pd.Timestamp:
    parsed_end = parse_date(end) or pd.Timestamp(date.today()).normalize()
    return parsed_end - pd.DateOffset(years=int(years))


def price_cache_path(symbol: str, *, data_dir: Path | None = None, source: str = SOURCE_YFINANCE) -> Path:
    return (data_dir or default_data_dir()) / "prices" / source / f"{symbol.upper()}_daily.parquet"


def _standardize_columns(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    rename = {
        "Date": "date",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Adj Close": "adj_close",
        "Volume": "volume",
        "Dividends": "dividends",
        "Stock Splits": "stock_splits",
        "Capital Gains": "capital_gains",
    }
    out = frame.reset_index().rename(columns=rename)
    if "date" not in out.columns:
        first_col = out.columns[0]
        out = out.rename(columns={first_col: "date"})

    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None).dt.normalize()
    out["symbol"] = symbol.upper()
    out["source"] = SOURCE_YFINANCE

    if "adj_close" not in out.columns:
        out["adj_close"] = out["close"]
    for optional in ["dividends", "stock_splits", "capital_gains"]:
        if optional not in out.columns:
            out[optional] = 0.0

    columns = [
        "date",
        "symbol",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "dividends",
        "stock_splits",
        "capital_gains",
        "source",
    ]
    available = [column for column in columns if column in out.columns]
    out = out[available].dropna(subset=["date", "adj_close"]).sort_values("date")
    return out.reset_index(drop=True)


def _split_yfinance_frame(raw: pd.DataFrame, symbols: list[str]) -> dict[str, pd.DataFrame]:
    if raw.empty:
        raise ValueError("Downloaded price data is empty.")

    if isinstance(raw.columns, pd.MultiIndex):
        level_zero = set(str(value).upper() for value in raw.columns.get_level_values(0))
        level_one = set(str(value).upper() for value in raw.columns.get_level_values(1))
        ticker_first = any(symbol in level_zero for symbol in symbols)
        result: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            if ticker_first:
                if symbol not in raw.columns.get_level_values(0):
                    continue
                result[symbol] = raw[symbol].dropna(how="all")
            else:
                if symbol not in level_one:
                    continue
                result[symbol] = raw.xs(symbol, level=1, axis=1).dropna(how="all")
        return result

    if len(symbols) != 1:
        raise ValueError("Expected a multi-symbol yfinance response.")
    return {symbols[0]: raw.dropna(how="all")}


def download_yfinance_daily(
    symbols: Iterable[str],
    *,
    start: str | date | datetime | pd.Timestamp,
    end: str | date | datetime | pd.Timestamp | None = None,
) -> dict[str, pd.DataFrame]:
    import yfinance as yf

    normalized = normalize_symbols(symbols)
    raw = yf.download(
        normalized,
        start=parse_date(start).date().isoformat(),
        end=end_for_yfinance(end),
        auto_adjust=False,
        actions=True,
        group_by="ticker",
        progress=False,
        threads=False,
    )
    split = _split_yfinance_frame(raw, normalized)
    missing = [symbol for symbol in normalized if symbol not in split or split[symbol].empty]
    if missing:
        raise ValueError(f"No yfinance data returned for: {', '.join(missing)}")
    return {
        symbol: _standardize_columns(frame, symbol)
        for symbol, frame in split.items()
    }


def write_price_cache(
    prices_by_symbol: dict[str, pd.DataFrame],
    *,
    data_dir: Path | None = None,
    source: str = SOURCE_YFINANCE,
) -> list[PriceCoverage]:
    coverages: list[PriceCoverage] = []
    for symbol, frame in prices_by_symbol.items():
        path = price_cache_path(symbol, data_dir=data_dir, source=source)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.sort_values("date").to_parquet(path, index=False)
        coverages.append(price_coverage(symbol, data_dir=data_dir, source=source))
    return coverages


def load_cached_prices(
    symbols: Iterable[str],
    *,
    data_dir: Path | None = None,
    source: str = SOURCE_YFINANCE,
    start: str | date | datetime | pd.Timestamp | None = None,
    end: str | date | datetime | pd.Timestamp | None = None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    missing: list[str] = []
    start_ts = parse_date(start)
    end_ts = parse_date(end)
    for symbol in normalize_symbols(symbols):
        path = price_cache_path(symbol, data_dir=data_dir, source=source)
        if not path.exists():
            missing.append(symbol)
            continue
        frame = pd.read_parquet(path)
        frame["date"] = pd.to_datetime(frame["date"]).dt.tz_localize(None).dt.normalize()
        if start_ts is not None:
            frame = frame[frame["date"] >= start_ts]
        if end_ts is not None:
            frame = frame[frame["date"] <= end_ts]
        frames.append(frame)
    if missing:
        raise FileNotFoundError(f"Missing cached price data for: {', '.join(missing)}")
    if not frames:
        raise ValueError("No cached price data loaded.")
    return pd.concat(frames, ignore_index=True).sort_values(["symbol", "date"]).reset_index(drop=True)


def price_coverage(
    symbol: str,
    *,
    data_dir: Path | None = None,
    source: str = SOURCE_YFINANCE,
) -> PriceCoverage:
    normalized = symbol.upper()
    path = price_cache_path(normalized, data_dir=data_dir, source=source)
    if not path.exists():
        return PriceCoverage(normalized, 0, None, None, path)
    frame = pd.read_parquet(path, columns=["date"])
    if frame.empty:
        return PriceCoverage(normalized, 0, None, None, path)
    dates = pd.to_datetime(frame["date"]).dt.tz_localize(None).dt.normalize()
    return PriceCoverage(normalized, len(frame), dates.min(), dates.max(), path)


def cache_covers(
    symbol: str,
    *,
    start: str | date | datetime | pd.Timestamp,
    end: str | date | datetime | pd.Timestamp | None,
    data_dir: Path | None = None,
    source: str = SOURCE_YFINANCE,
    tolerance_days: int = 7,
) -> bool:
    coverage = price_coverage(symbol, data_dir=data_dir, source=source)
    if coverage.first_date is None or coverage.last_date is None:
        return False
    start_ts = parse_date(start)
    end_ts = parse_date(end) or pd.Timestamp(date.today()).normalize()
    return (
        coverage.first_date <= start_ts + pd.Timedelta(days=tolerance_days)
        and coverage.last_date >= end_ts - pd.Timedelta(days=tolerance_days)
    )


def ensure_yfinance_prices(
    symbols: Iterable[str],
    *,
    start: str | date | datetime | pd.Timestamp,
    end: str | date | datetime | pd.Timestamp | None = None,
    data_dir: Path | None = None,
    force: bool = False,
) -> list[PriceCoverage]:
    normalized = normalize_symbols(symbols)
    needs_fetch = force or any(
        not cache_covers(symbol, start=start, end=end, data_dir=data_dir)
        for symbol in normalized
    )
    if needs_fetch:
        downloaded = download_yfinance_daily(normalized, start=start, end=end)
        return write_price_cache(downloaded, data_dir=data_dir)
    return [price_coverage(symbol, data_dir=data_dir) for symbol in normalized]
