#!/usr/bin/env python3
"""Tier 1-3 NQ Asia replacement comparison.

Runs execution-engine exact replay for:
- ALPHA_V1-A NQ Asia RR6 incumbent
- Tier 1 target compression: rr=3.0 / TP1=2.0R on the same ALPHA entries
- Tier 2 shelf challengers: NQ Asia R5 Final and R9 Restart Final

Then stitches each NQ Asia stream into the existing ALPHA five-leg recent
payout model and writes standalone, portfolio, and correlation diagnostics.
This is a research artifact only; it does not edit execution configs.
"""

from __future__ import annotations

import copy
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
BT_ROOT = SCRIPT_DIR.parent
ROOT = BT_ROOT.parent
EXEC_SRC = ROOT / "execution" / "src"
if str(EXEC_SRC) not in sys.path:
    sys.path.insert(0, str(EXEC_SRC))

from trader import historical_backtest as hb  # noqa: E402
from trader.main import DEFAULT_CONFIG, ExecutionConfig, load_config, load_exec_configs  # noqa: E402


RUN_SLUG = "nq_asia_tier1_tier3_exact_compare_20260702"
RESULT_DIR = BT_ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = BT_ROOT / "learnings" / "reports" / "NQ_ASIA_TIER1_TIER3_EXACT_COMPARE_20260702.md"

BASE_PROFILE = "ALPHA_V1-A"
FULL_START = "2016-04-17"
END_DATE = "2026-03-24"

WINDOWS = {
    "full": (FULL_START, END_DATE),
    "last_2y": ("2024-03-24", END_DATE),
    "last_1y": ("2025-03-24", END_DATE),
    "2024": ("2024-01-01", "2024-12-31"),
    "2025": ("2025-01-01", "2025-12-31"),
    "2026_ytd": ("2026-01-01", END_DATE),
}

ACTIVE_EXACT_TRADES = (
    BT_ROOT / "data" / "results" / "alpha_v1_live_replay_compare_20260503" / "exact_trades.csv"
)
R11_EXACT_TRADES = (
    BT_ROOT
    / "data"
    / "results"
    / "alpha_v1_single_vs_split_exact_compare_20260506"
    / "split_exact_trades.csv"
)

SESSION_TO_LEG = {
    "NQ_NY_LSI": "nq_ny_htf_lsi",
    "NQ_Asia": "nq_asia_orb",
    "ES_Asia": "es_asia_orb",
    "ES_NY": "es_ny_orb",
}

LEG_LABELS = {
    "nq_ny_htf_lsi": "NQ NY HTF-LSI",
    "nq_asia_orb": "NQ Asia ORB",
    "es_asia_orb": "ES Asia ORB",
    "nq_ny_orb_r11": "NQ NY ORB R11",
    "es_ny_orb": "ES NY ORB",
}

FUNDED_MODEL = {
    "starting_balance_usd": 50_000.0,
    "trailing_drawdown_usd": 2_000.0,
    "max_trailing_breach_usd": 50_000.0,
    "first_payout_floor_usd": 52_500.0,
    "first_payout_withdrawal_usd": 500.0,
    "challenge_fee_usd": 150.0,
    "cohort_spacing_days": 14,
}

PORTFOLIO_RISK_MAPS = {
    "balanced_default": {
        "nq_ny_htf_lsi": 300.0,
        "nq_asia_orb": 300.0,
        "es_asia_orb": 200.0,
        "nq_ny_orb_r11": 250.0,
        "es_ny_orb": 200.0,
    },
    "nq_asia_400": {
        "nq_ny_htf_lsi": 300.0,
        "nq_asia_orb": 400.0,
        "es_asia_orb": 200.0,
        "nq_ny_orb_r11": 250.0,
        "es_ny_orb": 200.0,
    },
}


@dataclass(frozen=True)
class CandidateSpec:
    key: str
    label: str
    tier: str
    deployability: str
    live_support_notes: str
    exact_replay_required: str
    overrides: dict[str, Any]

    @property
    def profile_name(self) -> str:
        return f"NQ_ASIA_{self.key}".upper()[:120]


def _round(value: Any, digits: int = 2) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return round(out, digits)


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, float):
        if not math.isfinite(value):
            return "inf" if value > 0 else "-"
        if abs(value) >= 100:
            return f"{value:.0f}"
        if abs(value) >= 10:
            return f"{value:.1f}"
        return f"{value:.2f}"
    return str(value)


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_No rows._"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(_fmt(row.get(col)) for col in columns) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def _safe_json(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(k): _safe_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_safe_json(v) for v in data]
    if isinstance(data, (np.integer,)):
        return int(data)
    if isinstance(data, (np.floating,)):
        out = float(data)
        return out if math.isfinite(out) else None
    if isinstance(data, float):
        return data if math.isfinite(data) else None
    if hasattr(data, "isoformat"):
        return data.isoformat()
    return data


def _candidate_specs(alpha_nq_asia: dict[str, Any]) -> list[CandidateSpec]:
    incumbent = copy.deepcopy(alpha_nq_asia)
    tier1 = copy.deepcopy(alpha_nq_asia)
    tier1.update({"rr": 3.0, "tp1_ratio": 2.0 / 3.0})

    r5 = {
        "orb_start": "20:00",
        "orb_end": "20:10",
        "entry_start": "20:10",
        "entry_end": "00:00",
        "flat_start": "01:00",
        "flat_end": "07:00",
        "stop_basis": "atr",
        "stop_atr_pct": 3.7,
        "stop_orb_pct": 0.0,
        "gap_filter_basis": "atr",
        "min_gap_atr_pct": 0.90,
        "min_gap_orb_pct": 0.0,
        "max_gap_atr_pct": 5.0,
        "instrument": "NQ",
        "atr_length": 5,
        "rr": 1.75,
        "tp1_ratio": 0.10,
        "risk_usd": 400.0,
        "max_single_risk_usd": 500.0,
        "long_only": False,
        "short_only": False,
        "icf_enabled": False,
        "excluded_dow": [3],
    }

    r9 = {
        "orb_start": "20:00",
        "orb_end": "20:15",
        "entry_start": "20:15",
        "entry_end": "22:30",
        "flat_start": "04:00",
        "flat_end": "07:00",
        "stop_basis": "atr",
        "stop_atr_pct": 4.0,
        "stop_orb_pct": 0.0,
        "gap_filter_basis": "atr",
        "min_gap_atr_pct": 0.90,
        "min_gap_orb_pct": 0.0,
        "max_gap_atr_pct": 0.0,
        "instrument": "NQ",
        "atr_length": 5,
        "rr": 3.0,
        "tp1_ratio": 0.6,
        "risk_usd": 400.0,
        "max_single_risk_usd": 500.0,
        "long_only": True,
        "short_only": False,
        "icf_enabled": True,
        "excluded_dow": [1],
    }

    return [
        CandidateSpec(
            key="alpha_rr6_incumbent",
            label="ALPHA RR6 incumbent",
            tier="incumbent",
            deployability="live_native",
            live_support_notes="Current ALPHA_V1-A NQ_Asia execution profile.",
            exact_replay_required="complete",
            overrides=incumbent,
        ),
        CandidateSpec(
            key="alpha_rr3_tp1_2r",
            label="Tier 1 rr=3 / TP1=2R",
            tier="tier_1_exit_compression",
            deployability="live_native",
            live_support_notes="Same ALPHA entries, only rr/tp1 target knobs changed.",
            exact_replay_required="complete",
            overrides=tier1,
        ),
        CandidateSpec(
            key="r5_final",
            label="Tier 2 R5 Final",
            tier="tier_2_shelf",
            deployability="live_native_but_deprecated",
            live_support_notes="Execution-native fields, but tp1_ratio=0.10 is below the later 0.20 floor and was deprecated as degenerate.",
            exact_replay_required="complete",
            overrides=r5,
        ),
        CandidateSpec(
            key="r9_restart_final",
            label="Tier 2 R9 Restart Final",
            tier="tier_2_shelf",
            deployability="live_native_with_note",
            live_support_notes="Execution-native replay of the R9 restart config; historical note mentions max_gap_points=75, which is not an execution-engine field here.",
            exact_replay_required="complete",
            overrides=r9,
        ),
    ]


def _profile_for(spec: CandidateSpec) -> ExecutionConfig:
    return ExecutionConfig(
        name=spec.profile_name,
        enabled=True,
        max_open_contracts=20,
        webhooks=[],
        session_overrides={"NQ_Asia": copy.deepcopy(spec.overrides)},
        lsi_session_overrides={},
    )


def _run_exact(config: dict[str, Any], spec: CandidateSpec) -> dict[str, Any]:
    cache_path = RESULT_DIR / f"exact_{spec.key}.json"
    if cache_path.exists():
        print(f"[cache] {spec.label}", flush=True)
        return json.loads(cache_path.read_text())

    profile = _profile_for(spec)
    original_loader = hb.load_exec_configs
    hb.load_exec_configs = lambda _config=None: [profile]
    try:
        result = hb.run_profile_backtest_sync(
            config=config,
            profile_name=profile.name,
            start_date=FULL_START,
            end_date=END_DATE,
            label=f"EXEC EXACT {spec.label} {FULL_START} to {END_DATE}",
        )
    finally:
        hb.load_exec_configs = original_loader

    payload = {
        "candidate": spec.__dict__,
        "profile_name": profile.name,
        "profile_session_overrides": _safe_json(profile.session_overrides),
        "result": result,
    }
    cache_path.write_text(json.dumps(_safe_json(payload), indent=2, sort_keys=True) + "\n")
    return payload


def _slice_trades(trades: list[dict[str, Any]], start: str, end: str) -> list[dict[str, Any]]:
    return [trade for trade in trades if start <= str(trade.get("date", "")) <= end]


def _exit_shape(trades: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(trades)
    counts: dict[str, int] = defaultdict(int)
    for trade in trades:
        counts[str(trade.get("exit_type", ""))] += 1
    full_tp = counts.get("tp1_tp2", 0) + counts.get("tp2_single", 0)
    tp1_be = counts.get("tp1_be", 0)
    tp1_eod = counts.get("tp1_eod", 0)
    tp1_hit = full_tp + tp1_be + tp1_eod
    return {
        "full_tp_count": full_tp,
        "full_tp_rate_pct": _round(full_tp / total * 100.0, 2) if total else 0.0,
        "tp1_be_count": tp1_be,
        "tp1_be_rate_pct": _round(tp1_be / total * 100.0, 2) if total else 0.0,
        "tp1_eod_count": tp1_eod,
        "tp1_eod_rate_pct": _round(tp1_eod / total * 100.0, 2) if total else 0.0,
        "tp1_hit_rate_pct": _round(tp1_hit / total * 100.0, 2) if total else 0.0,
        "exit_breakdown": dict(sorted(counts.items())),
    }


def _metric_row(spec: CandidateSpec, trades: list[dict[str, Any]], window: str, start: str, end: str) -> dict[str, Any]:
    selected = _slice_trades(trades, start, end)
    summary = hb._compute_summary(selected)
    r_by_year = summary.get("r_by_year") or {}
    neg_years = sum(1 for value in r_by_year.values() if float(value) < 0)
    return {
        "candidate": spec.key,
        "label": spec.label,
        "tier": spec.tier,
        "window": window,
        "start": start,
        "end": end,
        "deployability": spec.deployability,
        "live_support_notes": spec.live_support_notes,
        "exact_replay_required": spec.exact_replay_required,
        "trades": int(summary.get("total_trades", 0) or 0),
        "net_r": _round(summary.get("total_r", 0.0), 2),
        "net_r_fee_aware": _round(summary.get("total_net_r", 0.0), 2),
        "wr_pct": _round(float(summary.get("win_rate", 0.0) or 0.0) * 100.0, 2),
        "pf": _round(summary.get("profit_factor", 0.0), 3),
        "avg_r": _round(summary.get("avg_r", 0.0), 4),
        "sharpe": _round(summary.get("sharpe_ratio", 0.0), 3),
        "max_dd_r": _round(summary.get("max_drawdown_r", 0.0), 2),
        "calmar": _round(summary.get("calmar_ratio", 0.0), 3),
        "negative_years": int(neg_years),
        "r_by_year": json.dumps({k: _round(v, 2) for k, v in sorted(r_by_year.items())}),
        **_exit_shape(selected),
    }


def _cohort_starts(start: str, end: str) -> list[pd.Timestamp]:
    return [
        ts.normalize().tz_localize("UTC")
        for ts in pd.date_range(
            pd.Timestamp(start).normalize(),
            pd.Timestamp(end).normalize(),
            freq=f"{int(FUNDED_MODEL['cohort_spacing_days'])}D",
        )
    ]


def _prep_stream(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["date"] = out["date"].astype(str)
    out["exit_ts"] = pd.to_datetime(out["exit_time"], utc=True, errors="coerce")
    out["entry_ts"] = pd.to_datetime(out["entry_time"], utc=True, errors="coerce")
    out = out[out["exit_ts"].notna()].copy()
    out["r_multiple"] = out["r_multiple"].astype(float)
    return out.sort_values(["exit_ts", "leg", "entry_ts"]).reset_index(drop=True)


def _candidate_trade_df(spec: CandidateSpec, trades: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(trades)
    if df.empty:
        return pd.DataFrame(columns=["candidate", "leg", "date", "entry_time", "exit_time", "r_multiple", "source"])
    keep = ["date", "entry_time", "exit_time", "r_multiple", "session", "exit_type"]
    df = df[keep].copy()
    df["candidate"] = spec.key
    df["leg"] = "nq_asia_orb"
    df["source"] = f"exact_{spec.key}"
    return df[["candidate", "leg", "date", "entry_time", "exit_time", "r_multiple", "exit_type", "source"]]


def _base_non_nq_asia_stream() -> pd.DataFrame:
    active = pd.read_csv(ACTIVE_EXACT_TRADES)
    active = active.copy()
    active["leg"] = active["session"].map(SESSION_TO_LEG)
    active = active[active["leg"].notna()].copy()
    active = active[active["leg"] != "nq_asia_orb"].copy()
    active["source"] = "alpha_v1_live_exact_non_nq_asia"
    active["candidate"] = "shared"
    active_keep = ["candidate", "leg", "date", "entry_time", "exit_time", "r_multiple", "exit_type", "source"]

    r11 = pd.read_csv(R11_EXACT_TRADES)
    r11 = r11[r11["comparison_leg"] == "nq_ny_orb_r11"].copy()
    r11["leg"] = "nq_ny_orb_r11"
    r11["source"] = "nq_r11_exact_split"
    r11["candidate"] = "shared"
    r11_keep = ["candidate", "leg", "date", "entry_time", "exit_time", "r_multiple", "exit_type", "source"]

    return pd.concat([active[active_keep], r11[r11_keep]], ignore_index=True)


def _portfolio_stream(base_stream: pd.DataFrame, candidate_stream: pd.DataFrame) -> pd.DataFrame:
    combined = pd.concat([base_stream, candidate_stream], ignore_index=True)
    return _prep_stream(combined)


def _simulate_accounts(
    trades: pd.DataFrame,
    *,
    start: str,
    end: str,
    risk_map: dict[str, float],
) -> pd.DataFrame:
    mask = (trades["date"] >= start) & (trades["date"] <= end)
    subset = trades.loc[mask].copy()
    subset["risk_usd"] = subset["leg"].map(risk_map).astype(float)
    subset["pnl_usd"] = subset["r_multiple"] * subset["risk_usd"]
    subset = subset[subset["risk_usd"] > 0].sort_values(["exit_ts", "leg", "entry_ts"]).reset_index(drop=True)
    trade_tuples = [
        (
            row.exit_ts,
            pd.Timestamp(row.exit_ts).date().isoformat(),
            str(row.leg),
            float(row.pnl_usd),
        )
        for row in subset[["exit_ts", "leg", "pnl_usd"]].itertuples(index=False)
    ]

    rows: list[dict[str, Any]] = []
    for account_id, start_ts in enumerate(_cohort_starts(start, end), start=1):
        balance = float(FUNDED_MODEL["starting_balance_usd"])
        floor = balance - float(FUNDED_MODEL["trailing_drawdown_usd"])
        high_eod = balance
        current_day: str | None = None
        outcome = "open"
        outcome_date = pd.Timestamp(end).date().isoformat()
        trades_taken = 0
        leg_counts: dict[str, int] = defaultdict(int)
        leg_pnl: dict[str, float] = defaultdict(float)

        for exit_ts, trade_day, leg, pnl_usd in trade_tuples:
            if exit_ts < start_ts:
                continue
            if current_day is not None and trade_day != current_day:
                high_eod = max(high_eod, balance)
                floor = max(
                    floor,
                    min(
                        high_eod - float(FUNDED_MODEL["trailing_drawdown_usd"]),
                        float(FUNDED_MODEL["max_trailing_breach_usd"]),
                    ),
                )
            current_day = trade_day
            balance += pnl_usd
            trades_taken += 1
            leg_counts[leg] += 1
            leg_pnl[leg] += pnl_usd
            if balance <= floor:
                outcome = "breach"
                outcome_date = trade_day
                break
            if balance >= float(FUNDED_MODEL["first_payout_floor_usd"]):
                outcome = "payout"
                outcome_date = trade_day
                break

        net_after_fee = (
            float(FUNDED_MODEL["first_payout_withdrawal_usd"]) - float(FUNDED_MODEL["challenge_fee_usd"])
            if outcome == "payout"
            else -float(FUNDED_MODEL["challenge_fee_usd"])
        )
        rows.append(
            {
                "account_id": account_id,
                "account_start": start_ts.date().isoformat(),
                "outcome": outcome,
                "outcome_date": outcome_date,
                "days_to_outcome": int((pd.Timestamp(outcome_date).date() - start_ts.date()).days) + 1,
                "trades_to_outcome": trades_taken,
                "ending_balance_usd": _round(balance, 2),
                "breach_floor_usd": _round(floor, 2),
                "net_after_fee_usd": _round(net_after_fee, 2),
                **{f"{leg}_trades": int(leg_counts[leg]) for leg in sorted(risk_map)},
                **{f"{leg}_pnl_usd": _round(leg_pnl[leg], 2) for leg in sorted(risk_map)},
            }
        )
    return pd.DataFrame(rows)


def _max_consecutive(outcomes: pd.DataFrame, outcome_name: str) -> int:
    max_run = 0
    run = 0
    for _, row in outcomes.sort_values("account_start").iterrows():
        if row["outcome"] == outcome_name:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    return max_run


def _score_outcomes(
    *,
    candidate: str,
    scope: str,
    profile: str,
    window: str,
    outcomes: pd.DataFrame,
    risk_map: dict[str, float],
) -> dict[str, Any]:
    total = len(outcomes)
    payouts = outcomes[outcomes["outcome"] == "payout"]
    breaches = outcomes[outcomes["outcome"] == "breach"]
    opens = outcomes[outcomes["outcome"] == "open"]
    resolved = len(payouts) + len(breaches)
    return {
        "candidate": candidate,
        "scope": scope,
        "profile": profile,
        "window": window,
        "risk_map_json": json.dumps({k: int(v) for k, v in sorted(risk_map.items())}, sort_keys=True),
        "accounts": int(total),
        "payouts": int(len(payouts)),
        "breaches": int(len(breaches)),
        "open": int(len(opens)),
        "start_payout_rate_pct": _round(len(payouts) / total * 100.0, 2) if total else None,
        "start_breach_rate_pct": _round(len(breaches) / total * 100.0, 2) if total else None,
        "open_rate_pct": _round(len(opens) / total * 100.0, 2) if total else None,
        "resolved_payout_rate_pct": _round(len(payouts) / resolved * 100.0, 2) if resolved else None,
        "resolved_breach_rate_pct": _round(len(breaches) / resolved * 100.0, 2) if resolved else None,
        "avg_days_to_payout": _round(float(payouts["days_to_outcome"].mean()), 1) if not payouts.empty else None,
        "median_days_to_payout": _round(float(payouts["days_to_outcome"].median()), 1) if not payouts.empty else None,
        "avg_trades_to_payout": _round(float(payouts["trades_to_outcome"].mean()), 1) if not payouts.empty else None,
        "max_consecutive_breaches": _max_consecutive(outcomes, "breach"),
        "max_consecutive_payouts": _max_consecutive(outcomes, "payout"),
        "ev_per_start_usd": _round(float(outcomes["net_after_fee_usd"].mean()), 2) if total else None,
    }


def _payout_rows(candidate_streams: dict[str, pd.DataFrame], base_stream: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary_rows: list[dict[str, Any]] = []
    outcome_frames: list[pd.DataFrame] = []

    for candidate, nq_stream in candidate_streams.items():
        portfolio = _portfolio_stream(base_stream, nq_stream)
        single = _prep_stream(nq_stream.copy())
        scopes = {
            "single_nq_asia_400": (single, {"nq_asia_orb": 400.0}),
            **{
                f"portfolio_{profile}": (portfolio, risk_map)
                for profile, risk_map in PORTFOLIO_RISK_MAPS.items()
            },
        }
        for scope, (stream, risk_map) in scopes.items():
            profile = scope.replace("portfolio_", "").replace("single_", "")
            for window, (start, end) in {
                "2024_2026_ytd": ("2024-01-01", END_DATE),
                "2024": WINDOWS["2024"],
                "2025": WINDOWS["2025"],
                "2026_ytd": WINDOWS["2026_ytd"],
            }.items():
                outcomes = _simulate_accounts(stream, start=start, end=end, risk_map=risk_map)
                outcomes.insert(0, "candidate", candidate)
                outcomes.insert(1, "scope", scope)
                outcomes.insert(2, "profile", profile)
                outcomes.insert(3, "window", window)
                outcome_frames.append(outcomes)
                summary_rows.append(
                    _score_outcomes(
                        candidate=candidate,
                        scope=scope,
                        profile=profile,
                        window=window,
                        outcomes=outcomes,
                        risk_map=risk_map,
                    )
                )

    return pd.DataFrame(summary_rows), pd.concat(outcome_frames, ignore_index=True)


def _daily_r_frame(stream: pd.DataFrame) -> pd.DataFrame:
    daily = (
        stream.groupby(["date", "leg"], as_index=False)["r_multiple"]
        .sum()
        .pivot(index="date", columns="leg", values="r_multiple")
        .fillna(0.0)
    )
    return daily.sort_index()


def _corr(a: pd.Series, b: pd.Series) -> float | None:
    if len(a) < 2 or float(a.std()) == 0.0 or float(b.std()) == 0.0:
        return None
    value = float(a.corr(b))
    return value if math.isfinite(value) else None


def _correlation_rows(candidate_streams: dict[str, pd.DataFrame], base_stream: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for candidate, nq_stream in candidate_streams.items():
        stream = _portfolio_stream(base_stream, nq_stream)
        daily = _daily_r_frame(stream)
        nq = daily.get("nq_asia_orb", pd.Series(0.0, index=daily.index))
        es_asia = daily.get("es_asia_orb", pd.Series(0.0, index=daily.index))
        other = daily.drop(columns=["nq_asia_orb"], errors="ignore").sum(axis=1)
        corr_matrix = daily.corr()
        mask = np.triu(np.ones(corr_matrix.shape), k=1).astype(bool)
        avg_pair = corr_matrix.where(mask).stack().mean()
        rows.append(
            {
                "candidate": candidate,
                "corr_nq_asia_es_asia_daily_r": _round(_corr(nq, es_asia), 4),
                "corr_nq_asia_other_legs_daily_r": _round(_corr(nq, other), 4),
                "portfolio_avg_pairwise_corr": _round(float(avg_pair), 4) if math.isfinite(float(avg_pair)) else None,
                "nq_asia_active_days": int((nq != 0).sum()),
                "es_asia_active_days": int((es_asia != 0).sum()),
            }
        )
    return pd.DataFrame(rows)


def _promotion_rows(metric_rows: pd.DataFrame, payout_rows: pd.DataFrame) -> pd.DataFrame:
    full = metric_rows[metric_rows["window"] == "full"].set_index("candidate")
    incumbent = full.loc["alpha_rr6_incumbent"]
    port = payout_rows[
        (payout_rows["scope"] == "portfolio_nq_asia_400")
        & (payout_rows["window"] == "2024_2026_ytd")
    ].set_index("candidate")
    inc_port = port.loc["alpha_rr6_incumbent"]

    rows: list[dict[str, Any]] = []
    for candidate, row in full.iterrows():
        p = port.loc[candidate]
        net_r = float(row["net_r"] or 0.0)
        inc_r = float(incumbent["net_r"] or 0.0)
        dd = abs(float(row["max_dd_r"] or 0.0))
        inc_dd = abs(float(incumbent["max_dd_r"] or 0.0))
        rows.append(
            {
                "candidate": candidate,
                "label": row["label"],
                "within_10pct_r": bool(net_r >= inc_r * 0.90),
                "no_new_negative_years": bool(int(row["negative_years"]) <= int(incumbent["negative_years"])),
                "dd_not_worse": bool(dd <= inc_dd),
                "full_tp_rate_delta_pct": _round(
                    float(row["full_tp_rate_pct"] or 0.0) - float(incumbent["full_tp_rate_pct"] or 0.0),
                    2,
                ),
                "portfolio_payout_delta_pct": _round(
                    float(p["start_payout_rate_pct"] or 0.0) - float(inc_port["start_payout_rate_pct"] or 0.0),
                    2,
                ),
                "portfolio_avg_pay_days_delta": _round(
                    float(p["avg_days_to_payout"] or 999.0) - float(inc_port["avg_days_to_payout"] or 999.0),
                    1,
                ),
                "portfolio_max_consec_breach_delta": int(p["max_consecutive_breaches"])
                - int(inc_port["max_consecutive_breaches"]),
                "promotion_gate_pass": bool(
                    net_r >= inc_r * 0.90
                    and int(row["negative_years"]) <= int(incumbent["negative_years"])
                    and dd <= inc_dd
                    and float(p["start_payout_rate_pct"] or 0.0) >= float(inc_port["start_payout_rate_pct"] or 0.0)
                    and int(p["max_consecutive_breaches"]) <= int(inc_port["max_consecutive_breaches"])
                ),
            }
        )
    return pd.DataFrame(rows)


def _write_report(
    *,
    metric_rows: pd.DataFrame,
    payout_summary: pd.DataFrame,
    correlations: pd.DataFrame,
    promotion: pd.DataFrame,
) -> None:
    full = metric_rows[metric_rows["window"] == "full"].copy()
    full_rows = [
        {
            "Candidate": row["label"],
            "Tier": row["tier"],
            "Trades": int(row["trades"]),
            "Net R": _round(row["net_r"], 1),
            "WR%": _round(row["wr_pct"], 1),
            "PF": _round(row["pf"], 2),
            "DD R": _round(row["max_dd_r"], 1),
            "Calmar": _round(row["calmar"], 2),
            "Full TP%": _round(row["full_tp_rate_pct"], 1),
            "TP1-BE%": _round(row["tp1_be_rate_pct"], 1),
            "NegY": int(row["negative_years"]),
        }
        for _, row in full.iterrows()
    ]
    port = payout_summary[
        (payout_summary["scope"] == "portfolio_nq_asia_400")
        & (payout_summary["window"] == "2024_2026_ytd")
    ]
    port_rows = [
        {
            "Candidate": row["candidate"],
            "Accts": int(row["accounts"]),
            "Pay": int(row["payouts"]),
            "Breach": int(row["breaches"]),
            "Open": int(row["open"]),
            "Start Pay%": _round(row["start_payout_rate_pct"], 1),
            "Resolved Pay%": _round(row["resolved_payout_rate_pct"], 1),
            "Avg PayD": _round(row["avg_days_to_payout"], 1),
            "MCBch": int(row["max_consecutive_breaches"]),
            "EV/start": _round(row["ev_per_start_usd"], 0),
        }
        for _, row in port.iterrows()
    ]
    single = payout_summary[
        (payout_summary["scope"] == "single_nq_asia_400")
        & (payout_summary["window"] == "2024_2026_ytd")
    ]
    single_rows = [
        {
            "Candidate": row["candidate"],
            "Accts": int(row["accounts"]),
            "Pay": int(row["payouts"]),
            "Breach": int(row["breaches"]),
            "Open": int(row["open"]),
            "Start Pay%": _round(row["start_payout_rate_pct"], 1),
            "Resolved Pay%": _round(row["resolved_payout_rate_pct"], 1),
            "Avg PayD": _round(row["avg_days_to_payout"], 1),
            "MCBch": int(row["max_consecutive_breaches"]),
            "EV/start": _round(row["ev_per_start_usd"], 0),
        }
        for _, row in single.iterrows()
    ]
    corr_rows = [
        {
            "Candidate": row["candidate"],
            "NQ/ES Asia Corr": _round(row["corr_nq_asia_es_asia_daily_r"], 3),
            "NQ/Other Corr": _round(row["corr_nq_asia_other_legs_daily_r"], 3),
            "Avg Pair Corr": _round(row["portfolio_avg_pairwise_corr"], 3),
            "NQ Active Days": int(row["nq_asia_active_days"]),
        }
        for _, row in correlations.iterrows()
    ]
    promo_rows = [
        {
            "Candidate": row["candidate"],
            "R>=90%": row["within_10pct_r"],
            "No New NegY": row["no_new_negative_years"],
            "DD OK": row["dd_not_worse"],
            "Full TP Delta": _round(row["full_tp_rate_delta_pct"], 1),
            "Pay Delta": _round(row["portfolio_payout_delta_pct"], 1),
            "PayD Delta": _round(row["portfolio_avg_pay_days_delta"], 1),
            "MCBch Delta": int(row["portfolio_max_consec_breach_delta"]),
            "Gate Pass": row["promotion_gate_pass"],
        }
        for _, row in promotion.iterrows()
    ]

    report = f"""# NQ Asia Tier 1-3 Exact Compare

- Run slug: `{RUN_SLUG}`
- Window: `{FULL_START}` to `{END_DATE}`
- Base profile source: `{BASE_PROFILE}` for the ALPHA RR6 incumbent and Tier 1 target compression.
- Exact replay: execution engine via in-memory profiles only; `execution/config/exec_configs.json` was not edited.
- Account model: `$50k`, `$2k` EOD trailing drawdown capped at `$50k`, first payout trigger `$52.5k`, first withdrawal `$500`, fee `$150`, starts every `14` calendar days.

## Standalone Exact Replay

{_markdown_table(full_rows, ["Candidate", "Tier", "Trades", "Net R", "WR%", "PF", "DD R", "Calmar", "Full TP%", "TP1-BE%", "NegY"])}

## Portfolio Payout At NQ Asia $400

Risk map: HTF `$300`, NQ Asia `$400`, ES Asia `$200`, R11 `$250`, ES NY `$200`.

{_markdown_table(port_rows, ["Candidate", "Accts", "Pay", "Breach", "Open", "Start Pay%", "Resolved Pay%", "Avg PayD", "MCBch", "EV/start"])}

## Single-Leg NQ Asia Payout At $400

{_markdown_table(single_rows, ["Candidate", "Accts", "Pay", "Breach", "Open", "Start Pay%", "Resolved Pay%", "Avg PayD", "MCBch", "EV/start"])}

## Sleeve Correlation

{_markdown_table(corr_rows, ["Candidate", "NQ/ES Asia Corr", "NQ/Other Corr", "Avg Pair Corr", "NQ Active Days"])}

## Pre-Registered Gate Read

{_markdown_table(promo_rows, ["Candidate", "R>=90%", "No New NegY", "DD OK", "Full TP Delta", "Pay Delta", "PayD Delta", "MCBch Delta", "Gate Pass"])}

## Interpretation Notes

- `R5 Final` is replayed for comparison but remains deprecated because `tp1_ratio=0.10` was later judged degenerate.
- `R9 Restart Final` is replayed through execution-native fields. The research history mentions `max_gap_points=75`, but the current execution ORB engine does not expose that as a config field, so this is the deployable execution-native replay of the same main structure rather than a max-gap-points parity proof.
- Payout rows include open accounts separately. Use both start-rate and resolved-rate semantics when reading partial `2026_ytd` windows.

## Artifacts

- `exact_metrics.csv`
- `payout_summary.csv`
- `payout_outcomes.csv`
- `correlations.csv`
- `promotion_gates.csv`
- `summary.json`
"""
    REPORT_PATH.write_text(report)


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    config = load_config(DEFAULT_CONFIG)
    profiles = {profile.name: profile for profile in load_exec_configs(config)}
    alpha = profiles[BASE_PROFILE]
    specs = _candidate_specs(alpha.session_overrides["NQ_Asia"])

    exact_payloads: dict[str, dict[str, Any]] = {}
    metric_rows: list[dict[str, Any]] = []
    candidate_streams: dict[str, pd.DataFrame] = {}

    for spec in specs:
        print(f"Running exact replay: {spec.label}", flush=True)
        payload = _run_exact(config, spec)
        exact_payloads[spec.key] = payload
        trades = payload["result"].get("trades", [])
        candidate_streams[spec.key] = _candidate_trade_df(spec, trades)
        for window, (start, end) in WINDOWS.items():
            metric_rows.append(_metric_row(spec, trades, window, start, end))

    metric_df = pd.DataFrame(metric_rows)
    base_stream = _base_non_nq_asia_stream()
    payout_summary, payout_outcomes = _payout_rows(candidate_streams, base_stream)
    correlations = _correlation_rows(candidate_streams, base_stream)
    promotion = _promotion_rows(metric_df, payout_summary)

    metric_df.to_csv(RESULT_DIR / "exact_metrics.csv", index=False)
    payout_summary.to_csv(RESULT_DIR / "payout_summary.csv", index=False)
    payout_outcomes.to_csv(RESULT_DIR / "payout_outcomes.csv", index=False)
    correlations.to_csv(RESULT_DIR / "correlations.csv", index=False)
    promotion.to_csv(RESULT_DIR / "promotion_gates.csv", index=False)

    summary = {
        "run_slug": RUN_SLUG,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "window": {"start": FULL_START, "end": END_DATE},
        "base_profile": BASE_PROFILE,
        "funded_model": FUNDED_MODEL,
        "portfolio_risk_maps": PORTFOLIO_RISK_MAPS,
        "candidates": [_safe_json(spec.__dict__) for spec in specs],
        "topline_full": metric_df[metric_df["window"] == "full"].to_dict(orient="records"),
        "portfolio_nq_asia_400": payout_summary[
            (payout_summary["scope"] == "portfolio_nq_asia_400")
            & (payout_summary["window"] == "2024_2026_ytd")
        ].to_dict(orient="records"),
        "single_nq_asia_400": payout_summary[
            (payout_summary["scope"] == "single_nq_asia_400")
            & (payout_summary["window"] == "2024_2026_ytd")
        ].to_dict(orient="records"),
        "correlations": correlations.to_dict(orient="records"),
        "promotion_gates": promotion.to_dict(orient="records"),
        "paths": {
            "result_dir": str(RESULT_DIR),
            "report": str(REPORT_PATH),
        },
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe_json(summary), indent=2, sort_keys=True) + "\n")
    _write_report(
        metric_rows=metric_df,
        payout_summary=payout_summary,
        correlations=correlations,
        promotion=promotion,
    )

    print(json.dumps({"result_dir": str(RESULT_DIR), "report": str(REPORT_PATH)}, indent=2))


if __name__ == "__main__":
    main()
