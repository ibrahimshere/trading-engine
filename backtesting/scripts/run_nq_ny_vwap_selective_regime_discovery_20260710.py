#!/usr/bin/env python3
"""Causal regime-gate discovery for the selective NQ NY VWAP sleeve."""

from __future__ import annotations

import importlib.util
import itertools
import json
import math
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.data.fees import estimated_commission_per_side  # noqa: E402
from orb_backtest.validate.deflated_sharpe import (  # noqa: E402
    compute_dsr,
    compute_psr,
    estimate_effective_trials,
)


RUN_SLUG = "nq_ny_vwap_selective_regime_discovery_20260710"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_VWAP_SELECTIVE_REGIME_DISCOVERY_20260710.md"

DATA_START = "2016-01-01"
DATA_END_EXCLUSIVE = "2026-06-06"
DISCOVERY_END_EXCLUSIVE = "2023-01-01"
RETROSPECTIVE_VALIDATION_START = "2023-01-01"
FUTURE_HOLDOUT_START = "2026-06-06"

MNQ_POINT_VALUE = 2.0
NQ_TICK = 0.25
MNQ_COMMISSION_PER_SIDE = float(estimated_commission_per_side("MNQ"))
SLIPPAGE_TICKS_PER_SIDE = (0, 1, 2)

DEPLOYABILITY = "post_filter_only"
LIVE_SUPPORT_NOTES = (
    "The regime variables are causal and available by 10:00 ET, but this discovery applies them to completed "
    "research trades. The gate must be implemented before order arming and exact-replayed before dry/live use."
)
EXACT_REPLAY_REQUIRED = "yes"


GATE_GRID: dict[str, tuple[tuple[float, ...], tuple[str, ...]]] = {
    "atr_ratio_5_20": ((0.80, 1.00, 1.20), ("le", "ge")),
    "atr_pct_price": ((0.0075, 0.0100, 0.0125, 0.0150, 0.0200), ("le", "ge")),
    "prior_day_range_atr": ((0.75, 1.00, 1.25, 1.50), ("le", "ge")),
    "prior_day_efficiency": ((0.25, 0.40, 0.55, 0.70), ("le", "ge")),
    "abs_gap_atr": ((0.10, 0.25, 0.50, 0.75, 1.00), ("le",)),
    "overnight_range_atr": ((0.50, 0.75, 1.00, 1.25, 1.50), ("le", "ge")),
    "abs_overnight_return_atr": ((0.25, 0.50, 0.75, 1.00), ("le",)),
    "ib30_range_atr": ((0.25, 0.40, 0.60, 0.80, 1.00), ("le", "ge")),
    "opening_efficiency": ((0.25, 0.40, 0.55, 0.70), ("le", "ge")),
    "abs_opening_drive_atr": ((0.10, 0.25, 0.50, 0.75), ("le", "ge")),
    "abs_trend5_atr": ((1.00, 2.00, 3.00, 4.00), ("le", "ge")),
    "abs_trend20_atr": ((2.00, 4.00, 6.00, 8.00), ("le", "ge")),
    "dir_trend5_atr": ((-2.00, -1.00, 0.00, 1.00, 2.00), ("le", "ge")),
    "dir_trend20_atr": ((-4.00, -2.00, 0.00, 2.00, 4.00), ("le", "ge")),
    "dir_gap_atr": ((-0.50, 0.00, 0.50), ("le", "ge")),
    "dir_opening_drive_atr": ((-0.50, 0.00, 0.50), ("le", "ge")),
}


def _load_validation_module() -> Any:
    path = SCRIPT_DIR / "run_nq_ny_vwap_mean_reversion_validation_20260630.py"
    spec = importlib.util.spec_from_file_location("nq_vwap_validation_regime_20260710", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load validation module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


val = _load_validation_module()


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _max_drawdown(values: np.ndarray | list[float]) -> float:
    array = np.asarray(values, dtype=float)
    if len(array) == 0:
        return 0.0
    equity = np.cumsum(array)
    peak = np.maximum.accumulate(np.concatenate(([0.0], equity)))[1:]
    return float(np.min(equity - peak))


def _profit_factor(values: np.ndarray | list[float]) -> float:
    array = np.asarray(values, dtype=float)
    wins = float(array[array > 0].sum())
    losses = float(array[array < 0].sum())
    if losses < 0:
        return wins / abs(losses)
    return float("inf") if wins > 0 else 0.0


def _score(frame: pd.DataFrame, trading_days: int, *, r_column: str = "r_multiple") -> dict[str, Any]:
    values = frame[r_column].astype(float).to_numpy() if not frame.empty else np.array([], dtype=float)
    total_r = float(values.sum())
    max_dd = _max_drawdown(values)
    years = trading_days / 252.0 if trading_days else 0.0
    annual_r = total_r / years if years else 0.0
    yearly = frame.assign(year=frame["date"].astype(str).str[:4]).groupby("year")[r_column].sum() if not frame.empty else pd.Series(dtype=float)
    return {
        "trades": int(len(frame)),
        "total_r": round(total_r, 4),
        "avg_r": round(float(values.mean()), 4) if len(values) else 0.0,
        "profit_factor": round(_profit_factor(values), 4),
        "win_rate": round(float((values > 0).mean()), 4) if len(values) else 0.0,
        "max_drawdown_r": round(max_dd, 4),
        "avg_annual_r": round(annual_r, 4),
        "calmar": round(annual_r / abs(max_dd), 4) if max_dd < 0 else 0.0,
        "negative_years": int((yearly < 0).sum()),
    }


def _period(frame: pd.DataFrame, start: str, end_exclusive: str) -> pd.DataFrame:
    dates = pd.to_datetime(frame["date"])
    return frame[(dates >= pd.Timestamp(start)) & (dates < pd.Timestamp(end_exclusive))].copy()


def _day_count(daily: pd.DataFrame, start: str, end_exclusive: str) -> int:
    dates = daily.index
    return int(((dates >= pd.Timestamp(start)) & (dates < pd.Timestamp(end_exclusive))).sum())


def _prefix(prefix: str, score: dict[str, Any]) -> dict[str, Any]:
    return {f"{prefix}_{key}": value for key, value in score.items()}


def _load_full_trades() -> tuple[pd.DataFrame, pd.DataFrame]:
    days = val._prepare_days(DATA_START, DATA_END_EXCLUSIVE)
    candidates = val._make_candidates(days)
    streams: dict[str, pd.DataFrame] = {}
    for exit_name in ("signal_1x_to_vwap", "signal_1x_to_day_mid"):
        model = val._exit_model_from_name(exit_name)
        trades = val._simulate_candidate_set(days, candidates, **val.BEST_CONTEXT, exit_model=model)
        frame = pd.DataFrame(trades).sort_values(["entry_ts", "exit_ts"]).reset_index(drop=True)
        streams[exit_name] = frame
    return streams["signal_1x_to_vwap"], streams["signal_1x_to_day_mid"]


def _load_raw_5m() -> pd.DataFrame:
    return pd.read_parquet(
        ROOT / "data" / "raw" / "NQ_5m.parquet",
        columns=["open", "high", "low", "close", "volume"],
        filters=[
            ("datetime", ">=", pd.Timestamp(DATA_START) - pd.Timedelta(days=2)),
            ("datetime", "<", pd.Timestamp(DATA_END_EXCLUSIVE)),
        ],
    ).sort_index()


def _daily_features(raw: pd.DataFrame) -> pd.DataFrame:
    rth = raw.between_time("09:30", "16:00").copy()
    rth["date"] = rth.index.normalize()
    grouped = rth.groupby("date", sort=True)
    daily = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    daily["range"] = daily["high"] - daily["low"]
    daily["atr14_prev"] = daily["range"].rolling(14, min_periods=5).mean().shift(1)
    daily["prior_close"] = daily["close"].shift(1)
    daily["atr_ratio_5_20"] = (
        daily["range"].rolling(5, min_periods=5).mean().shift(1)
        / daily["range"].rolling(20, min_periods=10).mean().shift(1)
    )
    daily["atr_pct_price"] = daily["atr14_prev"] / daily["prior_close"]
    prior_range = daily["range"].shift(1).replace(0, np.nan)
    daily["prior_day_range_atr"] = prior_range / daily["atr14_prev"]
    daily["prior_day_efficiency"] = (
        (daily["close"].shift(1) - daily["open"].shift(1)).abs() / prior_range
    )
    daily["prior_day_return_atr"] = (
        (daily["close"].shift(1) - daily["open"].shift(1)) / daily["atr14_prev"]
    )
    daily["prior_close_location"] = (
        (daily["close"].shift(1) - daily["low"].shift(1)) / prior_range
    )
    daily["trend5_atr"] = (daily["close"].shift(1) - daily["close"].shift(6)) / daily["atr14_prev"]
    daily["trend20_atr"] = (daily["close"].shift(1) - daily["close"].shift(21)) / daily["atr14_prev"]

    ib = rth.between_time("09:30", "09:59").groupby("date", sort=True).agg(
        ib_open=("open", "first"),
        ib_high=("high", "max"),
        ib_low=("low", "min"),
        ib_close=("close", "last"),
    )
    ib["ib30_range"] = ib["ib_high"] - ib["ib_low"]
    daily = daily.join(ib)
    daily["ib30_range_atr"] = daily["ib30_range"] / daily["atr14_prev"]
    daily["opening_drive_atr"] = (daily["ib_close"] - daily["ib_open"]) / daily["atr14_prev"]
    daily["opening_efficiency"] = (
        (daily["ib_close"] - daily["ib_open"]).abs() / daily["ib30_range"].replace(0, np.nan)
    )

    overnight_rows: list[dict[str, Any]] = []
    for date in daily.index:
        start = date - pd.Timedelta(days=1) + pd.Timedelta(hours=18)
        end = date + pd.Timedelta(hours=9, minutes=29)
        window = raw.loc[start:end]
        overnight_rows.append(
            {
                "date": date,
                "overnight_open": float(window["open"].iloc[0]) if not window.empty else np.nan,
                "overnight_high": float(window["high"].max()) if not window.empty else np.nan,
                "overnight_low": float(window["low"].min()) if not window.empty else np.nan,
                "overnight_close": float(window["close"].iloc[-1]) if not window.empty else np.nan,
            }
        )
    overnight = pd.DataFrame(overnight_rows).set_index("date")
    daily = daily.join(overnight)
    daily["gap_atr"] = (daily["open"] - daily["prior_close"]) / daily["atr14_prev"]
    daily["overnight_range_atr"] = (
        (daily["overnight_high"] - daily["overnight_low"]) / daily["atr14_prev"]
    )
    daily["overnight_return_atr"] = (
        (daily["overnight_close"] - daily["prior_close"]) / daily["atr14_prev"]
    )
    return daily


def _attach_features(trades: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    out = trades.copy()
    out["date_key"] = pd.to_datetime(out["date"]).dt.normalize()
    out = out.join(daily, on="date_key", rsuffix="_daily")
    out["abs_gap_atr"] = out["gap_atr"].abs()
    out["abs_overnight_return_atr"] = out["overnight_return_atr"].abs()
    out["abs_opening_drive_atr"] = out["opening_drive_atr"].abs()
    out["abs_trend5_atr"] = out["trend5_atr"].abs()
    out["abs_trend20_atr"] = out["trend20_atr"].abs()
    direction = out["direction_int"].astype(float)
    out["dir_gap_atr"] = direction * out["gap_atr"]
    out["dir_opening_drive_atr"] = direction * out["opening_drive_atr"]
    out["dir_trend5_atr"] = direction * out["trend5_atr"]
    out["dir_trend20_atr"] = direction * out["trend20_atr"]
    return out


def _gate_label(gate: dict[str, Any]) -> str:
    op = "le" if gate["op"] == "le" else "ge"
    value = f"{float(gate['threshold']):g}".replace("-", "neg").replace(".", "p")
    return f"{gate['feature']}_{op}_{value}"


def _apply_gate(frame: pd.DataFrame, gate: dict[str, Any]) -> pd.DataFrame:
    values = pd.to_numeric(frame[gate["feature"]], errors="coerce")
    if gate["op"] == "le":
        mask = values <= float(gate["threshold"])
    else:
        mask = values >= float(gate["threshold"])
    return frame[mask.fillna(False)].copy()


def _apply_gates(frame: pd.DataFrame, gates: list[dict[str, Any]]) -> pd.DataFrame:
    out = frame
    for gate in gates:
        out = _apply_gate(out, gate)
    return out


def _gate_grid() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature, (thresholds, operators) in GATE_GRID.items():
        for operator in operators:
            for threshold in thresholds:
                gate = {"feature": feature, "op": operator, "threshold": threshold}
                gate["label"] = _gate_label(gate)
                rows.append(gate)
    return rows


def _feature_bins(trades: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    discovery = _period(trades, DATA_START, DISCOVERY_END_EXCLUSIVE)
    validation = _period(trades, RETROSPECTIVE_VALIDATION_START, DATA_END_EXCLUSIVE)
    rows: list[dict[str, Any]] = []
    for feature in GATE_GRID:
        values = pd.to_numeric(discovery[feature], errors="coerce").dropna()
        if values.nunique() < 5:
            continue
        quantiles = np.unique(values.quantile([0.2, 0.4, 0.6, 0.8]).to_numpy(dtype=float))
        edges = np.concatenate(([-np.inf], quantiles, [np.inf]))
        for period_name, frame, start, end in (
            ("discovery", discovery, DATA_START, DISCOVERY_END_EXCLUSIVE),
            ("retrospective_validation", validation, RETROSPECTIVE_VALIDATION_START, DATA_END_EXCLUSIVE),
        ):
            feature_values = pd.to_numeric(frame[feature], errors="coerce")
            bins = pd.cut(feature_values, bins=edges, include_lowest=True, duplicates="drop")
            for bin_index, interval in enumerate(bins.cat.categories):
                subset = frame[bins == interval]
                score = _score(subset, _day_count(daily, start, end))
                rows.append(
                    {
                        "feature": feature,
                        "period": period_name,
                        "bin_index": bin_index,
                        "bin_left": float(interval.left),
                        "bin_right": float(interval.right),
                        **score,
                    }
                )
    return pd.DataFrame(rows)


def _candidate_metrics(
    trades: pd.DataFrame,
    daily: pd.DataFrame,
    *,
    candidate_id: str,
    gates: list[dict[str, Any]],
    candidate_type: str,
) -> dict[str, Any]:
    filtered = _apply_gates(trades, gates)
    discovery = _period(filtered, DATA_START, DISCOVERY_END_EXCLUSIVE)
    validation = _period(filtered, RETROSPECTIVE_VALIDATION_START, DATA_END_EXCLUSIVE)
    cold = _period(filtered, DATA_START, "2021-06-05")
    recent = _period(filtered, "2021-06-05", DATA_END_EXCLUSIVE)
    full_score = _score(filtered, _day_count(daily, DATA_START, DATA_END_EXCLUSIVE))
    row = {
        "candidate_id": candidate_id,
        "candidate_type": candidate_type,
        "gate_count": len(gates),
        "gate_1": _gate_label(gates[0]) if gates else "none",
        "gate_2": _gate_label(gates[1]) if len(gates) > 1 else "none",
        "gate_json": json.dumps(gates, sort_keys=True),
        "full_retention": round(len(filtered) / len(trades), 4) if len(trades) else 0.0,
        **_prefix("full", full_score),
        **_prefix("discovery", _score(discovery, _day_count(daily, DATA_START, DISCOVERY_END_EXCLUSIVE))),
        **_prefix("validation", _score(validation, _day_count(daily, RETROSPECTIVE_VALIDATION_START, DATA_END_EXCLUSIVE))),
        **_prefix("cold", _score(cold, _day_count(daily, DATA_START, "2021-06-05"))),
        **_prefix("recent", _score(recent, _day_count(daily, "2021-06-05", DATA_END_EXCLUSIVE))),
        "deployability": DEPLOYABILITY,
        "live_support_notes": LIVE_SUPPORT_NOTES,
        "exact_replay_required": EXACT_REPLAY_REQUIRED,
    }
    return row


def _half_year_folds(frame: pd.DataFrame, daily: pd.DataFrame, candidate_id: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    cursor = pd.Timestamp("2016-01-01")
    end_limit = pd.Timestamp(DATA_END_EXCLUSIVE)
    while cursor + pd.DateOffset(months=6) <= end_limit:
        end = cursor + pd.DateOffset(months=6)
        subset = _period(frame, cursor.date().isoformat(), end.date().isoformat())
        rows.append(
            {
                "candidate_id": candidate_id,
                "fold_start": cursor.date().isoformat(),
                "fold_end_exclusive": end.date().isoformat(),
                **_score(subset, _day_count(daily, cursor.date().isoformat(), end.date().isoformat())),
                "deployability": DEPLOYABILITY,
                "live_support_notes": LIVE_SUPPORT_NOTES,
                "exact_replay_required": EXACT_REPLAY_REQUIRED,
            }
        )
        cursor = end
    return pd.DataFrame(rows)


def _fold_summary(folds: pd.DataFrame) -> dict[str, Any]:
    usable = folds[folds["trades"] >= 10]
    return {
        "usable_folds": int(len(usable)),
        "positive_folds": int((usable["total_r"] > 0).sum()),
        "positive_fold_rate": round(float((usable["total_r"] > 0).mean()), 4) if len(usable) else 0.0,
        "worst_fold_r": round(float(usable["total_r"].min()), 4) if len(usable) else 0.0,
        "median_fold_pf": round(float(usable["profit_factor"].median()), 4) if len(usable) else 0.0,
    }


def _local_plateau(
    trades: pd.DataFrame,
    daily: pd.DataFrame,
    gates: list[dict[str, Any]],
) -> dict[str, Any]:
    variants: list[list[dict[str, Any]]] = [[]]
    for gate in gates:
        values = list(GATE_GRID[gate["feature"]][0])
        index = values.index(float(gate["threshold"]))
        neighbors = values[max(0, index - 1) : min(len(values), index + 2)]
        expanded: list[list[dict[str, Any]]] = []
        for prefix in variants:
            for threshold in neighbors:
                expanded.append(prefix + [{**gate, "threshold": threshold}])
        variants = expanded

    passing = 0
    rows: list[dict[str, Any]] = []
    for variant in variants:
        metrics = _candidate_metrics(
            trades,
            daily,
            candidate_id="local_" + "__".join(_gate_label(gate) for gate in variant),
            gates=variant,
            candidate_type="local_neighbor",
        )
        passed = bool(
            metrics["discovery_profit_factor"] >= 1.10
            and metrics["validation_profit_factor"] >= 1.15
            and metrics["discovery_total_r"] > 0
            and metrics["validation_total_r"] > 0
        )
        passing += int(passed)
        metrics["local_pass"] = passed
        rows.append(metrics)
    return {
        "neighbors": len(rows),
        "passing_neighbors": passing,
        "plateau_score": round(passing / len(rows), 4) if rows else 0.0,
        "rows": rows,
    }


def _replay_1s_by_year(trades: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    source = ROOT / "data" / "raw" / "NQ_1s.parquet"
    trades = trades.copy()
    trades["year"] = trades["date"].astype(str).str[:4]
    for year, group in trades.groupby("year", sort=True):
        start = pd.Timestamp(f"{year}-01-01")
        end = min(start + pd.DateOffset(years=1), pd.Timestamp(DATA_END_EXCLUSIVE))
        print(f"  loading 1s path for {year}: {len(group)} trades", flush=True)
        lower = pd.read_parquet(
            source,
            columns=["open", "high", "low", "close", "volume"],
            filters=[("datetime", ">=", start), ("datetime", "<", end)],
        ).sort_index()
        replayed = [val._replay_trade_lower(row, lower, "1s") for row in group.drop(columns=["year"]).to_dict(orient="records")]
        frames.append(pd.DataFrame(replayed))
        del lower
    return pd.concat(frames, ignore_index=True).sort_values(["entry_ts", "path_exit_ts"]).reset_index(drop=True)


def _friction_r(frame: pd.DataFrame, ticks_per_side: int) -> pd.Series:
    risk_points = frame["risk_points"].astype(float)
    commission_r = (2.0 * MNQ_COMMISSION_PER_SIDE) / (risk_points * MNQ_POINT_VALUE)
    slippage_r = (2.0 * ticks_per_side * NQ_TICK) / risk_points
    return frame["path_r_multiple"].astype(float) - commission_r - slippage_r


def _block_bootstrap(
    frame: pd.DataFrame,
    daily: pd.DataFrame,
    *,
    iterations: int = 5000,
    block_days: int = 5,
    seed: int = 20260710,
) -> dict[str, Any]:
    day_index = daily.loc[pd.Timestamp(DATA_START) : pd.Timestamp(DATA_END_EXCLUSIVE)].index.astype(str)
    returns = frame.groupby("date")["net_r_1t"].sum().reindex(day_index, fill_value=0.0).to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    totals = np.zeros(iterations)
    drawdowns = np.zeros(iterations)
    block_count = int(math.ceil(len(returns) / block_days))
    max_start = max(1, len(returns) - block_days + 1)
    for index in range(iterations):
        starts = rng.integers(0, max_start, size=block_count)
        sample = np.concatenate([returns[start : start + block_days] for start in starts])[: len(returns)]
        totals[index] = sample.sum()
        drawdowns[index] = _max_drawdown(sample)
    return {
        "iterations": iterations,
        "block_days": block_days,
        "total_r_p05": round(float(np.quantile(totals, 0.05)), 2),
        "total_r_median": round(float(np.quantile(totals, 0.50)), 2),
        "total_r_p95": round(float(np.quantile(totals, 0.95)), 2),
        "max_dd_r_p05": round(float(np.quantile(drawdowns, 0.05)), 2),
        "max_dd_r_median": round(float(np.quantile(drawdowns, 0.50)), 2),
        "prob_total_r_positive": round(float((totals > 0).mean()), 4),
        "prob_dd_worse_than_20r": round(float((drawdowns <= -20.0).mean()), 4),
    }


def _table(frame: pd.DataFrame, columns: list[str], n: int | None = None) -> str:
    if frame.empty:
        return "_None._"
    view = frame[columns].copy()
    if n is not None:
        view = view.head(n)
    return view.to_markdown(index=False)


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("Generating full-history pure VWAP and day-mid exit streams...", flush=True)
    pure_vwap, day_mid = _load_full_trades()
    raw = _load_raw_5m()
    daily = _daily_features(raw)
    pure_vwap = _attach_features(pure_vwap, daily)
    day_mid = _attach_features(day_mid, daily)

    baseline_rows: list[dict[str, Any]] = []
    for label, frame in (("pure_vwap_target", pure_vwap), ("day_mid_target", day_mid)):
        row = _candidate_metrics(frame, daily, candidate_id=label, gates=[], candidate_type="baseline_control")
        baseline_rows.append(row)
    baselines = pd.DataFrame(baseline_rows)

    print("Building causal feature diagnostics...", flush=True)
    bin_diagnostics = _feature_bins(day_mid, daily)

    print("Running pre-registered univariate gate screen...", flush=True)
    univariate_rows: list[dict[str, Any]] = []
    univariate_frames: dict[str, pd.DataFrame] = {}
    univariate_gates: dict[str, list[dict[str, Any]]] = {}
    for gate in _gate_grid():
        candidate_id = "uni__" + gate["label"]
        metrics = _candidate_metrics(day_mid, daily, candidate_id=candidate_id, gates=[gate], candidate_type="univariate")
        univariate_rows.append(metrics)
        univariate_frames[candidate_id] = _apply_gates(day_mid, [gate])
        univariate_gates[candidate_id] = [gate]
    univariate = pd.DataFrame(univariate_rows).sort_values(
        ["discovery_calmar", "discovery_profit_factor", "discovery_total_r"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    univariate.insert(0, "discovery_rank", np.arange(1, len(univariate) + 1))

    eligible_uni = univariate[
        (univariate["discovery_trades"] >= 120)
        & (univariate["discovery_profit_factor"] >= 1.05)
        & (univariate["discovery_total_r"] > 0)
        & (univariate["full_retention"] >= 0.30)
    ]
    top_distinct: list[str] = []
    seen_features: set[str] = set()
    for candidate_id in eligible_uni["candidate_id"]:
        gate = univariate_gates[str(candidate_id)][0]
        if gate["feature"] in seen_features:
            continue
        seen_features.add(gate["feature"])
        top_distinct.append(str(candidate_id))
        if len(top_distinct) >= 8:
            break

    print(f"Running pair screen from {len(top_distinct)} discovery-selected feature families...", flush=True)
    pair_rows: list[dict[str, Any]] = []
    pair_frames: dict[str, pd.DataFrame] = {}
    pair_gates: dict[str, list[dict[str, Any]]] = {}
    for left_id, right_id in itertools.combinations(top_distinct, 2):
        gates = univariate_gates[left_id] + univariate_gates[right_id]
        candidate_id = "pair__" + "__".join(_gate_label(gate) for gate in gates)
        metrics = _candidate_metrics(day_mid, daily, candidate_id=candidate_id, gates=gates, candidate_type="pair")
        pair_rows.append(metrics)
        pair_frames[candidate_id] = _apply_gates(day_mid, gates)
        pair_gates[candidate_id] = gates
    pairs = pd.DataFrame(pair_rows)

    all_candidates = pd.concat([univariate, pairs], ignore_index=True, sort=False)
    candidate_frames = {**univariate_frames, **pair_frames}
    candidate_gates = {**univariate_gates, **pair_gates}

    print("Scoring fixed six-month folds...", flush=True)
    fold_frames: list[pd.DataFrame] = []
    fold_summaries: dict[str, dict[str, Any]] = {}
    for candidate_id, frame in candidate_frames.items():
        folds = _half_year_folds(frame, daily, candidate_id)
        fold_frames.append(folds)
        fold_summaries[candidate_id] = _fold_summary(folds)
    folds_all = pd.concat(fold_frames, ignore_index=True)
    for key in ("usable_folds", "positive_folds", "positive_fold_rate", "worst_fold_r", "median_fold_pf"):
        all_candidates[key] = all_candidates["candidate_id"].map(lambda candidate_id: fold_summaries[str(candidate_id)][key])
    univariate_scored = all_candidates[all_candidates["candidate_type"] == "univariate"].copy()
    pairs_scored = all_candidates[all_candidates["candidate_type"] == "pair"].copy()

    qualified = all_candidates[
        (all_candidates["discovery_trades"] >= 80)
        & (all_candidates["validation_trades"] >= 50)
        & (all_candidates["discovery_profit_factor"] >= 1.15)
        & (all_candidates["validation_profit_factor"] >= 1.20)
        & (all_candidates["cold_profit_factor"] >= 1.12)
        & (all_candidates["full_trades"] >= 150)
        & (all_candidates["full_max_drawdown_r"] >= -34.0)
        & (all_candidates["positive_fold_rate"] >= 0.65)
    ].copy()
    qualified["robustness_score"] = qualified[["discovery_calmar", "validation_calmar"]].min(axis=1)
    ranked_qualified = qualified.sort_values(
        ["robustness_score", "positive_fold_rate", "full_calmar", "full_profit_factor"],
        ascending=[False, False, False, False],
    )

    finalists: list[str] = []
    source_for_finalists = ranked_qualified if not ranked_qualified.empty else all_candidates.sort_values(
        ["discovery_calmar", "validation_calmar", "positive_fold_rate"],
        ascending=[False, False, False],
    )
    univariate_source = source_for_finalists[source_for_finalists["candidate_type"] == "univariate"]
    pair_source = source_for_finalists[source_for_finalists["candidate_type"] == "pair"]
    if not univariate_source.empty:
        univariate_source = univariate_source.copy()
        univariate_source["quality_score"] = univariate_source[
            ["discovery_profit_factor", "validation_profit_factor"]
        ].min(axis=1)
        univariate_source = univariate_source.sort_values(
            ["quality_score", "robustness_score", "positive_fold_rate"],
            ascending=[False, False, False],
        )
        finalists.append(str(univariate_source.iloc[0]["candidate_id"]))
    for candidate_id in pair_source["candidate_id"]:
        finalists.append(str(candidate_id))
        if len(finalists) >= 3:
            break
    if len(finalists) < 3:
        for candidate_id in source_for_finalists["candidate_id"]:
            candidate_id = str(candidate_id)
            if candidate_id in finalists:
                continue
            finalists.append(candidate_id)
            if len(finalists) >= 3:
                break

    print(f"Running local plateau checks for {len(finalists)} finalists...", flush=True)
    local_rows: list[dict[str, Any]] = []
    plateau_by_id: dict[str, dict[str, Any]] = {}
    for candidate_id in finalists:
        plateau = _local_plateau(day_mid, daily, candidate_gates[candidate_id])
        plateau_by_id[candidate_id] = {key: value for key, value in plateau.items() if key != "rows"}
        for row in plateau["rows"]:
            row["parent_candidate_id"] = candidate_id
            local_rows.append(row)
    local_stability = pd.DataFrame(local_rows)

    print("Replaying the day-mid leader on 1s paths by year...", flush=True)
    day_mid_1s = _replay_1s_by_year(day_mid)
    day_mid_1s = day_mid_1s.drop(columns=[column for column in day_mid_1s.columns if column in daily.columns], errors="ignore")
    day_mid_1s = _attach_features(day_mid_1s, daily)

    raw_trial_count = 2 + len(univariate) + len(pairs)
    trial_date_sets = [set(frame["date"].astype(str)) for frame in candidate_frames.values()]
    effective_trial_count = estimate_effective_trials(trial_date_sets)

    print("Running finalist cost, bootstrap, and PSR/DSR checks...", flush=True)
    friction_rows: list[dict[str, Any]] = []
    bootstrap_rows: list[dict[str, Any]] = []
    overfit_rows: list[dict[str, Any]] = []
    finalist_rows: list[dict[str, Any]] = []
    finalist_path_frames: list[pd.DataFrame] = []
    for candidate_id in finalists:
        gates = candidate_gates[candidate_id]
        path_frame = _apply_gates(day_mid_1s, gates)
        path_frame = path_frame.copy()
        for ticks in SLIPPAGE_TICKS_PER_SIDE:
            path_frame[f"net_r_{ticks}t"] = _friction_r(path_frame, ticks)
            friction_rows.append(
                {
                    "candidate_id": candidate_id,
                    "slippage_ticks_per_side": ticks,
                    "commission_per_side_usd": MNQ_COMMISSION_PER_SIDE,
                    **_score(path_frame, _day_count(daily, DATA_START, DATA_END_EXCLUSIVE), r_column=f"net_r_{ticks}t"),
                    "deployability": DEPLOYABILITY,
                    "live_support_notes": LIVE_SUPPORT_NOTES,
                    "exact_replay_required": EXACT_REPLAY_REQUIRED,
                }
            )
        path_frame["net_r_1t"] = _friction_r(path_frame, 1)
        path_export = path_frame.copy()
        path_export["candidate_id"] = candidate_id
        finalist_path_frames.append(path_export)
        bootstrap = _block_bootstrap(path_frame, daily)
        bootstrap_rows.append(
            {
                "candidate_id": candidate_id,
                **bootstrap,
                "deployability": DEPLOYABILITY,
                "live_support_notes": LIVE_SUPPORT_NOTES,
                "exact_replay_required": EXACT_REPLAY_REQUIRED,
            }
        )
        values = path_frame["net_r_1t"].astype(float).to_numpy()
        psr = compute_psr(values)
        dsr = compute_dsr(values, n_trials_raw=raw_trial_count, n_trials_effective=effective_trial_count)
        overfit_rows.append(
            {
                "candidate_id": candidate_id,
                **{f"psr_{key}": value for key, value in asdict(psr).items()},
                **{f"dsr_{key}": value for key, value in asdict(dsr).items()},
                "pbo_cscv_implemented": False,
                "deployability": DEPLOYABILITY,
                "live_support_notes": LIVE_SUPPORT_NOTES,
                "exact_replay_required": EXACT_REPLAY_REQUIRED,
            }
        )
        base_row = all_candidates[all_candidates["candidate_id"] == candidate_id].iloc[0].to_dict()
        base_row.update(plateau_by_id[candidate_id])
        finalist_rows.append(base_row)

    finalists_frame = pd.DataFrame(finalist_rows)
    friction = pd.DataFrame(friction_rows)
    bootstraps = pd.DataFrame(bootstrap_rows)
    overfit = pd.DataFrame(overfit_rows)
    finalist_paths = pd.concat(finalist_path_frames, ignore_index=True)

    segment_rows: list[dict[str, Any]] = []
    for candidate_id, candidate_frame in finalist_paths.groupby("candidate_id", sort=False):
        for direction, subset in candidate_frame.groupby("direction", sort=True):
            segment_rows.append(
                {
                    "candidate_id": candidate_id,
                    "segment": f"direction_{direction}",
                    **_score(subset, _day_count(daily, DATA_START, DATA_END_EXCLUSIVE), r_column="net_r_1t"),
                }
            )
        for year, subset in candidate_frame.groupby(candidate_frame["date"].astype(str).str[:4], sort=True):
            segment_rows.append(
                {
                    "candidate_id": candidate_id,
                    "segment": f"year_{year}",
                    **_score(subset, _day_count(daily, f"{year}-01-01", f"{int(year) + 1}-01-01"), r_column="net_r_1t"),
                }
            )
    segments = pd.DataFrame(segment_rows)
    segments["deployability"] = DEPLOYABILITY
    segments["live_support_notes"] = LIVE_SUPPORT_NOTES
    segments["exact_replay_required"] = EXACT_REPLAY_REQUIRED

    verdict_rows: list[dict[str, Any]] = []
    for candidate_id in finalists:
        base = finalists_frame[finalists_frame["candidate_id"] == candidate_id].iloc[0]
        cost = friction[(friction["candidate_id"] == candidate_id) & (friction["slippage_ticks_per_side"] == 1)].iloc[0]
        boot = bootstraps[bootstraps["candidate_id"] == candidate_id].iloc[0]
        audit = overfit[overfit["candidate_id"] == candidate_id].iloc[0]
        passed = bool(
            candidate_id in set(ranked_qualified["candidate_id"])
            and base["plateau_score"] >= 0.60
            and cost["profit_factor"] >= 1.20
            and cost["total_r"] > 0
            and boot["prob_total_r_positive"] >= 0.95
            and audit["dsr_dsr"] >= 0.95
        )
        verdict_rows.append(
            {
                "candidate_id": candidate_id,
                "verdict": "PROMOTE" if passed else ("CHALLENGER" if cost["profit_factor"] >= 1.10 else "REJECT"),
                "qualified_structural_gate": candidate_id in set(ranked_qualified["candidate_id"]),
                "plateau_pass": bool(base["plateau_score"] >= 0.60),
                "friction_pass": bool(cost["profit_factor"] >= 1.20 and cost["total_r"] > 0),
                "bootstrap_pass": bool(boot["prob_total_r_positive"] >= 0.95),
                "dsr_pass": bool(audit["dsr_dsr"] >= 0.95),
                "future_holdout_required": "yes",
                "deployability": DEPLOYABILITY,
                "live_support_notes": LIVE_SUPPORT_NOTES,
                "exact_replay_required": EXACT_REPLAY_REQUIRED,
            }
        )
    verdicts = pd.DataFrame(verdict_rows)

    artifacts = {
        "baseline_controls.csv": baselines,
        "day_mid_full_trades_with_features.csv": day_mid,
        "feature_bin_diagnostics.csv": bin_diagnostics,
        "univariate_gate_results.csv": univariate_scored,
        "pair_gate_results.csv": pairs_scored,
        "fixed_six_month_folds.csv": folds_all,
        "qualified_candidates.csv": ranked_qualified,
        "finalists.csv": finalists_frame,
        "local_stability.csv": local_stability,
        "finalist_friction.csv": friction,
        "finalist_1s_trades.csv": finalist_paths,
        "finalist_segment_summary.csv": segments,
        "finalist_bootstrap.csv": bootstraps,
        "finalist_psr_dsr.csv": overfit,
        "promotion_verdicts.csv": verdicts,
    }
    for name, frame in artifacts.items():
        frame.to_csv(RESULT_DIR / name, index=False)

    baseline_cols = [
        "candidate_id", "full_trades", "full_total_r", "full_profit_factor", "full_max_drawdown_r",
        "cold_trades", "cold_total_r", "cold_profit_factor", "cold_max_drawdown_r",
        "recent_trades", "recent_total_r", "recent_profit_factor", "recent_max_drawdown_r", "deployability",
    ]
    screen_cols = [
        "candidate_id", "candidate_type", "gate_1", "gate_2", "full_trades", "full_total_r", "full_profit_factor",
        "full_max_drawdown_r", "discovery_profit_factor", "validation_profit_factor", "cold_profit_factor",
        "positive_fold_rate", "worst_fold_r", "deployability",
    ]
    finalist_cols = screen_cols + ["neighbors", "passing_neighbors", "plateau_score"]
    friction_cols = [
        "candidate_id", "slippage_ticks_per_side", "trades", "total_r", "avg_r", "profit_factor", "max_drawdown_r", "deployability",
    ]
    bootstrap_cols = [
        "candidate_id", "iterations", "total_r_p05", "total_r_median", "total_r_p95", "max_dd_r_p05",
        "max_dd_r_median", "prob_total_r_positive", "prob_dd_worse_than_20r", "deployability",
    ]
    overfit_cols = [
        "candidate_id", "psr_observed_sharpe", "psr_psr", "dsr_expected_max_sharpe", "dsr_dsr",
        "dsr_n_trials_raw", "dsr_n_trials_effective", "pbo_cscv_implemented", "deployability",
    ]
    verdict_cols = [
        "candidate_id", "verdict", "qualified_structural_gate", "plateau_pass", "friction_pass", "bootstrap_pass",
        "dsr_pass", "future_holdout_required", "deployability",
    ]

    promoted = verdicts[verdicts["verdict"] == "PROMOTE"] if not verdicts.empty else verdicts
    leader_id = finalists[0]
    leader_segments = segments[segments["candidate_id"] == leader_id]
    report_lines = [
        "# NQ NY Selective VWAP Regime Discovery",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Available data: `{DATA_START}` through `<{DATA_END_EXCLUSIVE}`.",
        f"- Discovery window: `{DATA_START}` through `<{DISCOVERY_END_EXCLUSIVE}`; retrospective gate validation: `{RETROSPECTIVE_VALIDATION_START}` through `<{DATA_END_EXCLUSIVE}`.",
        f"- True future holdout is frozen from `{FUTURE_HOLDOUT_START}` forward and was not available in this run.",
        "- The retrospective validation segment is not pristine for the base setup because prior work already inspected 2021-2026. The new regime-gate thresholds were selected from the discovery window only.",
        f"- Search count: `{raw_trial_count}` raw trials and `{effective_trial_count}` effective trials by trade-date overlap clustering. PBO/CSCV is not implemented; PSR/DSR is reported.",
        f"- Deployability: `{DEPLOYABILITY}`. {LIVE_SUPPORT_NOTES}",
        "",
        "## Baseline Controls",
        "",
        _table(baselines, baseline_cols),
        "",
        "The day-mid target is the leader: it improves both the cold and recent windows versus the pure VWAP target, but the cold-window PF and drawdown still require a regime explanation.",
        "",
        "## Discovery Screen",
        "",
        f"- Pre-registered univariate gates: `{len(univariate)}`.",
        f"- Pair gates from `{len(top_distinct)}` discovery-selected feature families: `{len(pairs)}`.",
        f"- Candidates clearing structural discovery/retrospective gates: `{len(ranked_qualified)}`.",
        "",
        "Top univariate rows by discovery Calmar:",
        "",
        _table(univariate_scored, screen_cols, n=12),
        "",
        "Qualified rows:",
        "",
        _table(ranked_qualified, screen_cols, n=15),
        "",
        "## Finalists And Stability",
        "",
        _table(finalists_frame, finalist_cols),
        "",
        "## 1s Friction Stress",
        "",
        _table(friction, friction_cols),
        "",
        "## Block Bootstrap",
        "",
        _table(bootstraps, bootstrap_cols),
        "",
        "## Lead Challenger Segments",
        "",
        "These segments use the 1s path with MNQ midpoint commission and one adverse tick per side.",
        "",
        _table(
            leader_segments,
            ["segment", "trades", "total_r", "avg_r", "profit_factor", "max_drawdown_r", "negative_years", "deployability"],
        ),
        "",
        "## Bailey Diagnostics",
        "",
        _table(overfit, overfit_cols),
        "",
        "## Promotion Decision",
        "",
        _table(verdicts, verdict_cols),
        "",
        f"- Promoted candidates: `{len(promoted)}`.",
        "- A PROMOTE verdict means only that a frozen gate deserves the next research phase. It does not authorize deployment, and every candidate still requires the future holdout, a live pre-trade implementation, and exact replay.",
        "",
        "## Artifacts",
        "",
    ]
    for name in artifacts:
        report_lines.append(f"- `{name}`: `backtesting/data/results/{RUN_SLUG}/{name}`")
    report_lines.append(f"- `summary.json`: `backtesting/data/results/{RUN_SLUG}/summary.json`")
    REPORT_PATH.write_text("\n".join(report_lines) + "\n")

    summary = {
        "run_slug": RUN_SLUG,
        "data_start": DATA_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "discovery_end_exclusive": DISCOVERY_END_EXCLUSIVE,
        "retrospective_validation_start": RETROSPECTIVE_VALIDATION_START,
        "future_holdout_start": FUTURE_HOLDOUT_START,
        "holdout_status": "future_holdout_frozen_not_yet_available",
        "raw_trial_count": raw_trial_count,
        "effective_trial_count": effective_trial_count,
        "pbo_cscv_implemented": False,
        "baselines": _safe(baseline_rows),
        "top_distinct_univariate_ids": top_distinct,
        "qualified_count": int(len(ranked_qualified)),
        "finalists": finalists,
        "verdicts": _safe(verdicts.to_dict(orient="records")),
        "elapsed_seconds": round(time.time() - started, 2),
        "deployability": DEPLOYABILITY,
        "live_support_notes": LIVE_SUPPORT_NOTES,
        "exact_replay_required": EXACT_REPLAY_REQUIRED,
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe(summary), indent=2) + "\n")

    print(json.dumps(_safe(summary), indent=2), flush=True)
    print(f"Wrote {RESULT_DIR}")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
