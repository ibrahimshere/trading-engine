"""Session state machine for live trade management.

Each ORBEngine tracks one trading session through its daily lifecycle:
ORB building → waiting for gap → order placement → position management.

Supports the 5-leg combined longs portfolio:
  NQ NY R11, NQ Asia R9, GC NY R3, ES NY Final, ES Asia Final

State machine:
    IDLE → ORB_BUILDING → WAITING_FOR_GAP → ARMED_LIMIT → FILLED → MANAGING → FLAT → IDLE
"""

from __future__ import annotations

import asyncio
import enum
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Callable

from .position_limits import ContractCapManager, resize_trade_levels
from .broker import TradersPostClient
from .sizing import TradeLevels, compute_trade_levels

logger = logging.getLogger(__name__)
trade_logger = logging.getLogger("trader.trades")


# ---------------------------------------------------------------------------
# Bar data
# ---------------------------------------------------------------------------

@dataclass
class Bar:
    """OHLCV bar (5m for signals, 1s for tick-level exit management)."""

    timestamp: datetime  # bar open time (Eastern)
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class TradeRecord:
    """Completed trade record for cross-session history (e.g. G5 gate)."""

    session: str          # e.g. "NQ_Asia", "ES_Asia", "NQ_LDN"
    date: str             # YYYYMMDD (session start date)
    direction: int        # +1 long, -1 short
    entry_price: float
    stop_price: float
    tp1_price: float
    tp2_price: float
    exit_type: str        # sl, tp1_single, tp1_be, tp1_eod, tp1_tp2, tp2_direct, eod, manual_flat, cancelled
    tp1_hit: bool         # critical for G5 gate
    timestamp: str        # ISO format exit timestamp
    config_name: str = "" # execution config (e.g. "FAST", "SLOW")
    r_result: float | None = None
    net_r_result: float | None = None
    gross_pnl_usd: float | None = None
    commission_per_contract: float = 0.0
    commission_usd: float = 0.0
    net_pnl_usd: float | None = None
    entry_timestamp: str = ""
    ticker: str = ""      # signal ticker displayed in dashboard (e.g. "NQ")
    exec_ticker: str = "" # execution contract routed to broker (e.g. "MNQ")
    leg: str = ""         # display leg/session name (e.g. "H_ORB_SAFE")
    entry_context: dict[str, object] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------

class State(enum.Enum):
    IDLE = "idle"
    ORB_BUILDING = "orb_building"
    WAITING_FOR_GAP = "waiting_for_gap"
    ARMED_LIMIT = "armed_limit"
    FILLED = "filled"
    MANAGING = "managing"
    FLAT = "flat"


# ---------------------------------------------------------------------------
# FOMC dates (GC exclusion) — update annually
# ---------------------------------------------------------------------------

FOMC_DATES: frozenset[str] = frozenset([
    "20160127", "20160316", "20160427", "20160615", "20160727", "20160921", "20161102", "20161214",
    "20170201", "20170315", "20170503", "20170614", "20170726", "20170920", "20171101", "20171213",
    "20180131", "20180321", "20180502", "20180613", "20180801", "20180926", "20181108", "20181219",
    "20190130", "20190320", "20190501", "20190619", "20190731", "20190918", "20191030", "20191211",
    "20200129", "20200311", "20200429", "20200610", "20200729", "20200916", "20201105", "20201216",
    "20210127", "20210317", "20210428", "20210616", "20210728", "20210922", "20211103", "20211215",
    "20220126", "20220316", "20220504", "20220615", "20220727", "20220921", "20221102", "20221214",
    "20230201", "20230322", "20230503", "20230614", "20230726", "20230920", "20231101", "20231213",
    "20240131", "20240320", "20240501", "20240612", "20240731", "20240918", "20241107", "20241218",
    "20250129", "20250319", "20250507", "20250618", "20250730", "20250917", "20251029", "20251210",
    "20260128", "20260318", "20260429", "20260610", "20260729", "20260916", "20261104", "20261216",
])


# ---------------------------------------------------------------------------
# Session time helpers
# ---------------------------------------------------------------------------

def _parse_time(s: str) -> time:
    """Parse 'HH:MM' to datetime.time."""
    h, m = s.split(":")
    return time(int(h), int(m))


def _time_in_range(t: time, start: time, end: time) -> bool:
    """Check if time t is in [start, end). Handles cross-midnight."""
    if start <= end:
        return start <= t < end
    else:
        return t >= start or t < end


# ---------------------------------------------------------------------------
# Session engine
# ---------------------------------------------------------------------------

@dataclass
class ORBEngine:
    """Manages one session's daily trade lifecycle.

    Args:
        name: Session name (e.g. "NQ_NY", "NQ_Asia", "GC_NY", "ES_NY", "ES_Asia").
        broker: TradersPost webhook client.
        orb_start: ORB window start (HH:MM).
        orb_end: ORB window end (HH:MM).
        entry_start: Entry window start (HH:MM).
        entry_end: Entry window end (HH:MM).
        flat_start: Flat/EOD window start (HH:MM).
        flat_end: Flat/EOD window end (HH:MM).
        stop_atr_pct: Stop distance as % of daily ATR (ATR-based stops).
        stop_basis: "atr" or "orb" — how to compute stop distance.
        stop_orb_pct: Stop distance as % of ORB range (ORB-based stops).
        min_gap_atr_pct: Min FVG gap as % of daily ATR (0 = use ORB-based).
        max_gap_atr_pct: Max FVG gap as % of daily ATR (0 = no limit).
        min_gap_orb_pct: Min FVG gap as % of ORB range (for ORB-based gap filter).
        gap_filter_basis: "atr" or "orb" — how to filter gap size.
        rr: Reward/risk ratio.
        tp1_ratio: Fraction of target for TP1.
        exit_mode: "split" for TP1 + runner, "single_target" for full exit at R:R.
        risk_usd: Risk per trade in USD.
        point_value: Dollar value per point (execution instrument).
        commission_per_contract: Per-contract, per-side execution fee estimate.
        min_qty: Minimum contract quantity.
        qty_step: Contract quantity step.
        be_offset_ticks: Ticks above/below entry for BE stop.
        min_tick: Minimum price tick.
        excluded_dates: Dates to skip (YYYYMMDD strings).
        half_days: Half-day dates (YYYYMMDD strings) — flat earlier.
        half_day_flat_start: Flat window start on half days (HH:MM).
        half_day_flat_end: Flat window end on half days (HH:MM).
        excluded_dow: Day-of-week to exclude (0=Mon..6=Sun). None = no exclusion.
        fomc_exclusion: If True, skip FOMC meeting days.
        icf_enabled: If True, use impulse close filter (relaxed ORB check).
        min_stop_pts: Minimum stop distance in points (dual floor, ES only).
        min_tp1_pts: Minimum TP1 distance in points (dual floor, ES only).
        long_only: If True, only take long setups (no short FVG detection).
    """

    name: str
    broker: TradersPostClient
    exec_ticker: str  # Execution instrument ticker (e.g. "MNQ", "MES", "MGC")

    # Session time windows
    orb_start: str
    orb_end: str
    entry_start: str
    entry_end: str
    flat_start: str
    flat_end: str

    # Strategy params
    stop_atr_pct: float
    min_gap_atr_pct: float
    max_gap_atr_pct: float
    rr: float
    tp1_ratio: float
    risk_usd: float
    point_value: float
    min_qty: float
    qty_step: float
    be_offset_ticks: int
    min_tick: float
    commission_per_contract: float = 0.0
    atr_length: int = 14
    exit_mode: str = "split"

    # Stop basis: "atr" or "orb"
    stop_basis: str = "atr"
    stop_orb_pct: float = 0.0

    # Gap filter basis: "atr" or "orb"
    gap_filter_basis: str = "atr"
    min_gap_orb_pct: float = 0.0

    # Dual floor (ES only)
    min_stop_pts: float = 0.0
    min_tp1_pts: float = 0.0

    # Single-contract risk cap: if 1 contract > risk_usd, allow up to this max
    max_single_risk_usd: float = 500.0

    # Direction filter
    long_only: bool = True
    short_only: bool = False

    # ICF (impulse close filter) — GC only
    icf_enabled: bool = False

    # Hot-regime ORB research knobs.
    continuation_fvg_selection: str = "first"
    orb_trade_max_per_session: int = 1
    orb_reentry_policy: str = "any_reentry"
    strategy_type: str = "continuation"
    orb_breakout_trigger: str = "touch"
    orb_breakout_buffer_ticks: int = 0
    orb_breakout_buffer_atr_pct: float = 0.0
    base_bar_minutes: int = 5
    wide_stop_target_threshold_points: float = 0.0
    wide_stop_target_rr: float = 0.0
    limit_cancel_on_pre_entry_target_touch: str = ""

    # Optional post-TP1 runner trailing. Disabled by default.
    runner_trail_mode: str = ""
    runner_trail_trigger_r: float = 0.0
    runner_trail_stop_r: float = 0.0
    runner_trail_step_r: float = 1.0
    runner_trail_gap_r: float = 1.0
    runner_trail_atr_pct: float = 0.0

    # Optional all-time-high distance block, checked on the closed signal bar
    # before an order is armed. Disabled unless max > min.
    ath_block_min_pct: float = 0.0
    ath_block_max_pct: float = 0.0

    # Optional pre-trade context gates, checked after ORB completion before
    # scanning for FVG setups. Disabled at 0.
    max_prior_rolling_atr_pct: float = 0.0
    max_orb_range_pct: float = 0.0

    # Day-of-week exclusion (0=Mon..6=Sun, None=no exclusion)
    excluded_dow: int | list[int] | None = None

    # FOMC exclusion (GC only)
    fomc_exclusion: bool = False

    # Date filters
    excluded_dates: tuple[str, ...] = ()
    half_days: tuple[str, ...] = ()
    half_day_flat_start: str = "12:50"
    half_day_flat_end: str = "13:00"

    # Execution config name (e.g. "FAST", "SLOW")
    config_name: str = ""

    # Fill detection mode
    allow_5m_fill_detection: bool = True

    # Per-leg pause: when True, all broker.send_*() calls are suppressed
    paused: bool = False

    # Optional callback for dashboard state change notifications
    on_state_change: Callable[[dict], None] | None = None
    # Optional callback for recording completed trades (G5 gate, history)
    on_trade_exit: Callable[[TradeRecord], None] | None = None
    # G5 gate: callback returns True if session should be skipped for a date
    g5_gate_check: Callable[[str], bool] | None = None
    regime_gate: str | None = None
    regime_gates: tuple[str, ...] = ()
    regime_gate_check: Callable[[str], bool] | None = None
    regime_gate_checks: tuple[tuple[str, Callable[[str], bool]], ...] = ()
    structure_gate: str | None = None
    structure_gate_check: Callable[["ORBEngine", Bar], bool] | None = None
    # Optional callback to request a state checkpoint to disk (crash recovery)
    on_checkpoint: Callable[[], None] | None = None
    # Optional per-config position cap manager
    position_manager: ContractCapManager | None = None
    position_limit_key: str = ""
    post_exit_cleanup_delay_s: float = 6.0
    post_exit_cancel_settle_delay_s: float = 0.25
    contract_routing_required: bool = False

    # Internal state (reset daily)
    _state: State = field(default=State.IDLE, init=False)
    _orb_high: float = field(default=float("nan"), init=False)
    _orb_low: float = field(default=float("nan"), init=False)
    _bars: list[Bar] = field(default_factory=list, init=False)  # rolling window
    _session_bars: list[Bar] = field(default_factory=list, init=False)
    _levels: TradeLevels | None = field(default=None, init=False)
    _tp1_hit: bool = field(default=False, init=False)
    _tp1_bar_count: int = field(default=-1, init=False)  # _bar_count when TP1 hit (1s)
    _runner_stop: float | None = field(default=None, init=False)
    _trade_daily_atr: float = field(default=0.0, init=False)
    _fill_bar_idx: int = field(default=-1, init=False)
    _fill_timestamp: datetime | None = field(default=None, init=False)
    _fill_via_tick: bool = field(default=False, init=False)
    _armed_at: datetime | None = field(default=None, init=False)
    _bar_count: int = field(default=0, init=False)
    _long_fvg_found: bool = field(default=False, init=False)
    _short_fvg_found: bool = field(default=False, init=False)
    _entry_order_type: str = field(default="limit", init=False)
    _session_filled_trades: int = field(default=0, init=False)
    _current_date: str = field(default="", init=False)
    _skip_reason: str | None = field(default=None, init=False)
    _blocking_gate: str | None = field(default=None, init=False)
    _regime_gate_status: dict | None = field(default=None, init=False)
    _last_regime_gate_audit: tuple[str, bool] | None = field(default=None, init=False)
    _ath_high: float = field(default=float("nan"), init=False)
    _ath_last_update: str = field(default="", init=False)
    _ath_last_close: float = field(default=float("nan"), init=False)
    _ath_last_gap_pct: float = field(default=float("nan"), init=False)
    _ath_check_count: int = field(default=0, init=False)
    _ath_block_count: int = field(default=0, init=False)
    _ath_pass_count: int = field(default=0, init=False)
    _ath_last_check: dict | None = field(default=None, init=False)
    _ath_last_block: dict | None = field(default=None, init=False)
    _daily_atr: float = field(default=0.0, init=False)
    _prior_rolling_atr_pct: float = field(default=float("nan"), init=False)
    _orb_open: float = field(default=float("nan"), init=False)
    _asset_tag: str = field(default="", init=False)
    _exit_type: str | None = field(default=None, init=False)
    _r_result: float | None = field(default=None, init=False)
    _cleanup_task: asyncio.Task | None = field(default=None, init=False, repr=False)
    _signal_contract: str = field(default="", init=False)
    _exec_contract: str = field(default="", init=False)
    _trade_signal_contract: str = field(default="", init=False)
    _trade_exec_contract: str = field(default="", init=False)
    _contract_routing_error: str = field(default="", init=False)

    # Parsed times (computed on first bar)
    _orb_start_t: time | None = field(default=None, init=False, repr=False)
    _orb_end_t: time | None = field(default=None, init=False, repr=False)
    _entry_start_t: time | None = field(default=None, init=False, repr=False)
    _entry_end_t: time | None = field(default=None, init=False, repr=False)
    _flat_start_t: time | None = field(default=None, init=False, repr=False)
    _flat_end_t: time | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._orb_start_t = _parse_time(self.orb_start)
        self._orb_end_t = _parse_time(self.orb_end)
        self._entry_start_t = _parse_time(self.entry_start)
        self._entry_end_t = _parse_time(self.entry_end)
        self._flat_start_t = _parse_time(self.flat_start)
        self._flat_end_t = _parse_time(self.flat_end)
        self._asset_tag = self._resolve_asset_tag()
        from .gates import normalize_regime_gate_fields
        (
            self.regime_gate,
            self.regime_gates,
            self.regime_gate_check,
            self.regime_gate_checks,
        ) = normalize_regime_gate_fields(
            self.regime_gate,
            self.regime_gates,
            self.regime_gate_check,
            self.regime_gate_checks,
        )
        if self.continuation_fvg_selection not in {"first", "extreme"}:
            raise ValueError(
                "continuation_fvg_selection must be one of 'first' or 'extreme' "
                f"(got {self.continuation_fvg_selection!r})"
            )
        if self.strategy_type not in {"continuation", "orb_breakout"}:
            raise ValueError(
                "strategy_type must be one of 'continuation' or 'orb_breakout' "
                f"(got {self.strategy_type!r})"
            )
        if self.orb_breakout_trigger not in {"touch", "close"}:
            raise ValueError(
                "orb_breakout_trigger must be one of 'touch' or 'close' "
                f"(got {self.orb_breakout_trigger!r})"
            )
        if self.orb_breakout_buffer_ticks < 0:
            raise ValueError("orb_breakout_buffer_ticks must be >= 0")
        if self.orb_breakout_buffer_atr_pct < 0.0:
            raise ValueError("orb_breakout_buffer_atr_pct must be >= 0")
        if self.base_bar_minutes <= 0:
            raise ValueError("base_bar_minutes must be > 0")
        if self.orb_trade_max_per_session < 0:
            raise ValueError(
                "orb_trade_max_per_session must be >= 0 "
                f"(got {self.orb_trade_max_per_session!r})"
            )
        if self.orb_reentry_policy not in {
            "any_reentry",
            "after_positive_first",
            "after_nonpositive_first",
            "after_sl_first",
            "after_full_target_first",
        }:
            raise ValueError(
                "orb_reentry_policy must be one of any_reentry, after_positive_first, "
                "after_nonpositive_first, after_sl_first, or after_full_target_first "
                f"(got {self.orb_reentry_policy!r})"
            )
        if self.exit_mode not in {"split", "single_target"}:
            raise ValueError(
                "exit_mode must be one of 'split' or 'single_target' "
                f"(got {self.exit_mode!r})"
            )
        if self.exit_mode == "single_target" and not math.isclose(
            self.tp1_ratio,
            1.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError(
                "tp1_ratio must be 1.0 when exit_mode='single_target' "
                f"(got {self.tp1_ratio!r})"
            )
        if self.wide_stop_target_threshold_points < 0.0:
            raise ValueError(
                "wide_stop_target_threshold_points must be >= 0 "
                f"(got {self.wide_stop_target_threshold_points!r})"
            )
        if self.wide_stop_target_rr < 0.0:
            raise ValueError(
                "wide_stop_target_rr must be >= 0 "
                f"(got {self.wide_stop_target_rr!r})"
            )
        if self.wide_stop_target_rr > 0.0:
            if self.wide_stop_target_rr < 1.0:
                raise ValueError(
                    "wide_stop_target_rr must be >= 1.0 when enabled "
                    f"(got {self.wide_stop_target_rr!r})"
                )
            if self.wide_stop_target_rr > self.rr:
                raise ValueError(
                    "wide_stop_target_rr must be <= rr "
                    f"(got wide_stop_target_rr={self.wide_stop_target_rr!r}, rr={self.rr!r})"
                )
        if self.runner_trail_mode not in {"", "step_r", "risk", "atr"}:
            raise ValueError(
                "runner_trail_mode must be one of '', 'step_r', 'risk', or 'atr' "
                f"(got {self.runner_trail_mode!r})"
            )
        if self.runner_trail_trigger_r < 0.0:
            raise ValueError("runner_trail_trigger_r must be >= 0")
        if self.runner_trail_stop_r < 0.0:
            raise ValueError("runner_trail_stop_r must be >= 0")
        if self.runner_trail_step_r <= 0.0:
            raise ValueError("runner_trail_step_r must be > 0")
        if self.runner_trail_gap_r <= 0.0:
            raise ValueError("runner_trail_gap_r must be > 0")
        if self.runner_trail_atr_pct < 0.0:
            raise ValueError("runner_trail_atr_pct must be >= 0")
        if self.runner_trail_mode == "step_r":
            if self.runner_trail_trigger_r <= 0.0:
                raise ValueError("runner_trail_trigger_r must be > 0 when runner_trail_mode='step_r'")
            if self.runner_trail_trigger_r <= self.runner_trail_stop_r:
                raise ValueError(
                    "runner_trail_trigger_r must be > runner_trail_stop_r when runner_trail_mode='step_r'"
                )
        if self.runner_trail_mode == "atr" and self.runner_trail_atr_pct <= 0.0:
            raise ValueError("runner_trail_atr_pct must be > 0 when runner_trail_mode='atr'")
        if self.limit_cancel_on_pre_entry_target_touch not in {"", "tp1", "tp2"}:
            raise ValueError(
                "limit_cancel_on_pre_entry_target_touch must be one of '', 'tp1', or 'tp2' "
                f"(got {self.limit_cancel_on_pre_entry_target_touch!r})"
            )
        if self.ath_block_min_pct < 0.0:
            raise ValueError(
                "ath_block_min_pct must be >= 0 "
                f"(got {self.ath_block_min_pct!r})"
            )
        if self.ath_block_max_pct < 0.0:
            raise ValueError(
                "ath_block_max_pct must be >= 0 "
                f"(got {self.ath_block_max_pct!r})"
            )
        if self.ath_block_max_pct > 0.0 and self.ath_block_max_pct <= self.ath_block_min_pct:
            raise ValueError(
                "ath_block_max_pct must be > ath_block_min_pct when enabled "
                f"(got min={self.ath_block_min_pct!r}, max={self.ath_block_max_pct!r})"
            )
        if self.max_prior_rolling_atr_pct < 0.0:
            raise ValueError("max_prior_rolling_atr_pct must be >= 0")
        if self.max_orb_range_pct < 0.0:
            raise ValueError("max_orb_range_pct must be >= 0")

    def set_context_gate_values(
        self,
        *,
        prior_rolling_atr_pct: float | None = None,
    ) -> None:
        """Update pre-trade context values computed by the feed/replay path."""
        if prior_rolling_atr_pct is not None:
            self._prior_rolling_atr_pct = float(prior_rolling_atr_pct)

    @property
    def _should_send(self) -> bool:
        """Whether this engine should send broker payloads."""
        return not self.paused

    def _resolve_asset_tag(self) -> str:
        """resolve canonical asset tag for trade logs."""
        prefix = self.name.split("_", maxsplit=1)[0].upper()
        if prefix in {"NQ", "ES", "GC", "CL"}:
            return prefix.lower()

        ticker_map = {
            "NQ": "nq",
            "MNQ": "nq",
            "ES": "es",
            "MES": "es",
            "GC": "gc",
            "MGC": "gc",
            "CL": "cl",
            "MCL": "cl",
        }
        return ticker_map.get(self.exec_ticker.upper(), self.exec_ticker.lower())

    def _blocking_regime_gate_name(self, date_key: str) -> str | None:
        from .gates import blocking_regime_gate_name
        return blocking_regime_gate_name(self.regime_gate_checks, date_key)

    def _clear_gate_audit(self) -> None:
        self._skip_reason = None
        self._blocking_gate = None
        self._regime_gate_status = None
        self._last_regime_gate_audit = None

    def _record_regime_gate_status(self, date_key: str, blocking_gate: str | None) -> None:
        from .gates import evaluate_regime_gates

        evaluations: list[dict[str, object]] = []
        if self.regime_gates:
            try:
                evaluations = [
                    evaluation.to_status_dict()
                    for evaluation in evaluate_regime_gates(self.regime_gates, date_key)
                ]
            except ValueError:
                evaluations = []

        if evaluations and blocking_gate is not None:
            for evaluation in evaluations:
                evaluation["allowed"] = evaluation.get("gate") != blocking_gate

        self._blocking_gate = blocking_gate
        self._skip_reason = "regime_gate" if blocking_gate is not None else None
        self._regime_gate_status = {
            "date": date_key,
            "allowed": blocking_gate is None,
            "blocking_gate": blocking_gate,
            "evaluations": evaluations,
        } if (self.regime_gates or blocking_gate is not None) else None

    def _maybe_log_regime_gate_audit(self) -> None:
        from .gates import RegimeGateEvaluation, format_regime_gate_detail

        status = self._regime_gate_status
        if not status:
            return

        date_key = str(status.get("date") or self._current_date)
        allowed = bool(status.get("allowed"))
        marker = (date_key, allowed)
        if self._last_regime_gate_audit == marker:
            return

        evaluations = status.get("evaluations") or []
        primary_eval: RegimeGateEvaluation | None = None
        if evaluations:
            blocking_gate = status.get("blocking_gate")
            for evaluation in evaluations:
                if evaluation.get("gate") == blocking_gate or primary_eval is None:
                    primary_eval = RegimeGateEvaluation(
                        gate=str(evaluation.get("gate", "")),
                        date_key=str(evaluation.get("date", date_key)),
                        allowed=bool(evaluation.get("allowed")),
                        reason=str(evaluation["reason"]) if evaluation.get("reason") else None,
                        regime=str(evaluation["regime"]) if evaluation.get("regime") is not None else None,
                        vol_regime=str(evaluation["vol_regime"]) if evaluation.get("vol_regime") is not None else None,
                        combined_regime=(
                            str(evaluation["combined_regime"])
                            if evaluation.get("combined_regime") is not None else None
                        ),
                        low_confidence=(
                            bool(evaluation["low_confidence"])
                            if evaluation.get("low_confidence") is not None else None
                        ),
                        warmup_ok=(
                            bool(evaluation["warmup_ok"])
                            if evaluation.get("warmup_ok") is not None else None
                        ),
                    )
                if evaluation.get("gate") == blocking_gate:
                    break

        if allowed:
            if primary_eval is not None:
                self._log_trade("REGIME_GATE_PASSED", format_regime_gate_detail(primary_eval))
            else:
                self._log_trade("REGIME_GATE_PASSED", f"date={date_key}")
        else:
            blocking_gate = status.get("blocking_gate") or self._blocking_gate
            self._log_trade("REGIME_GATE_BLOCKED", f"gate={blocking_gate} date={date_key}")

        self._last_regime_gate_audit = marker

    def _request_checkpoint(self) -> None:
        """Request a state checkpoint to disk for crash recovery."""
        if self.on_checkpoint is not None:
            self.on_checkpoint()

    @property
    def _ath_gate_enabled(self) -> bool:
        return self.ath_block_max_pct > self.ath_block_min_pct

    def seed_ath_high(self, value: float) -> None:
        """Seed expanding ATH state from historical data before live/replay bars."""
        if math.isfinite(value) and value > 0.0:
            if not math.isfinite(self._ath_high) or value > self._ath_high:
                self._ath_high = value

    def _update_ath_state(self, bar: Bar) -> None:
        if not math.isfinite(bar.high) or bar.high <= 0.0:
            return
        if not math.isfinite(self._ath_high) or bar.high > self._ath_high:
            self._ath_high = bar.high
        self._ath_last_update = bar.timestamp.isoformat()
        if math.isfinite(bar.close) and math.isfinite(self._ath_high) and self._ath_high > 0.0:
            self._ath_last_close = bar.close
            self._ath_last_gap_pct = (self._ath_high - bar.close) / self._ath_high * 100.0

    def _ath_gap_pct_for_bar(self, bar: Bar) -> float | None:
        if not self._ath_gate_enabled:
            return None
        if not math.isfinite(self._ath_high) or self._ath_high <= 0.0:
            return None
        if not math.isfinite(bar.close):
            return None
        return (self._ath_high - bar.close) / self._ath_high * 100.0

    def _ath_gate_blocks(self, bar: Bar) -> tuple[bool, float | None]:
        gap_pct = self._ath_gap_pct_for_bar(bar)
        if gap_pct is None:
            return False, None
        blocked = self.ath_block_min_pct <= gap_pct <= self.ath_block_max_pct
        return blocked, gap_pct

    def _record_ath_gate_check(
        self,
        bar: Bar,
        gap_pct: float | None,
        direction: str,
        *,
        blocked: bool,
    ) -> None:
        gap = float(gap_pct) if gap_pct is not None else float("nan")
        available = math.isfinite(gap)
        self._ath_check_count += 1
        if blocked:
            self._ath_block_count += 1
        elif available:
            self._ath_pass_count += 1
        check = {
            "direction": direction,
            "bar_time": bar.timestamp.isoformat(),
            "blocked": blocked,
            "available": available,
            "gap_pct": gap if math.isfinite(gap) else None,
            "ath_high": self._ath_high if math.isfinite(self._ath_high) else None,
            "close": bar.close if math.isfinite(bar.close) else None,
            "block_min_pct": self.ath_block_min_pct,
            "block_max_pct": self.ath_block_max_pct,
        }
        self._ath_last_check = check
        if blocked:
            self._ath_last_block = check
        self._request_checkpoint()
        self._notify_state_change()

    def _position_cap_key(self) -> str:
        return self.position_limit_key or f"{self.config_name or 'DEFAULT'}:{self.name}"

    def _position_cap_owner(self) -> str:
        return self.name

    def _apply_position_cap(self, levels: TradeLevels) -> TradeLevels | None:
        """Resize or block a setup based on remaining config-level contract capacity."""
        if self.position_manager is None or not self.position_manager.enabled:
            return levels

        requested_qty = levels.qty
        approved_qty = self.position_manager.reserve(
            self._position_cap_key(),
            requested_qty,
            qty_step=self.qty_step,
            min_qty=self.min_qty,
            owner_id=self._position_cap_owner(),
            exclusive_key=True,
        )
        if approved_qty <= 0:
            self._log_trade(
                "ENTRY_SKIPPED_CAP",
                "requested_qty=%.1f open_qty=%.1f limit=%.1f"
                % (
                    requested_qty,
                    self.position_manager.total_allocated(),
                    self.position_manager.max_open_contracts,
                ),
            )
            return None
        if approved_qty < requested_qty:
            self._log_trade(
                "ENTRY_QTY_CAPPED",
                "requested_qty=%.1f approved_qty=%.1f open_qty=%.1f limit=%.1f"
                % (
                    requested_qty,
                    approved_qty,
                    self.position_manager.total_allocated(),
                    self.position_manager.max_open_contracts,
                ),
            )
            return resize_trade_levels(
                levels,
                approved_qty,
                min_qty=self.min_qty,
                qty_step=self.qty_step,
            )
        return levels

    def _remaining_position_qty(self) -> float:
        levels = self._levels
        if levels is None:
            return 0.0
        if self._tp1_hit and not levels.is_single_contract:
            return max(0.0, levels.qty - levels.half_qty)
        return levels.qty

    def _sync_position_cap(self) -> None:
        if self.position_manager is None or not self.position_manager.enabled:
            return
        self.position_manager.adjust(
            self._position_cap_key(),
            self._remaining_position_qty(),
            owner_id=self._position_cap_owner(),
        )

    def _release_position_cap(self) -> None:
        if self.position_manager is None or not self.position_manager.enabled:
            return
        self.position_manager.release(
            self._position_cap_key(),
            owner_id=self._position_cap_owner(),
        )

    def _schedule_post_exit_cleanup(self, *, reason: str, delay_s: float | None = None) -> None:
        """Flatten residual position and then sweep stale orders after an exit trigger.

        This is used for exits where a live broker-side stop/limit is already expected
        to do the real work (initial stop, BE stop, or TP2 limit). We wait a short
        grace period so that resting order can complete, then send a cleanup sweep.
        Flatten must happen before cancel: if strategy data marked a limit as filled
        but the broker still has only resting orders, cancel-first can remove the
        protective orders and leave the subsequent exit with no broker position.
        """
        if not self._should_send:
            self._release_position_cap()
            return

        if self._cleanup_task is not None and not self._cleanup_task.done():
            return

        cleanup_delay = self.post_exit_cleanup_delay_s if delay_s is None else delay_s
        cleanup_ticker = self.broker_ticker

        async def _runner() -> None:
            try:
                if cleanup_delay > 0:
                    await asyncio.sleep(cleanup_delay)
                await self.broker.send_flatten(ticker=cleanup_ticker)
                if self.post_exit_cancel_settle_delay_s > 0:
                    await asyncio.sleep(self.post_exit_cancel_settle_delay_s)
                await self.broker.send_cancel(ticker=cleanup_ticker)
            except Exception:
                logger.exception("[%s] post-exit cleanup failed (%s)", self.name, reason)
            finally:
                self._release_position_cap()
                self._cleanup_task = None
                self._request_checkpoint()
                self._notify_state_change()

        self._cleanup_task = asyncio.create_task(_runner())

    def _broker_exit_cleanup_delay(self, default_delay_s: float) -> float:
        return 0.0 if self.post_exit_cleanup_delay_s <= 0 else default_delay_s

    def _log_trade(self, event: str, details: str = "") -> None:
        """emit trade log with config + asset + session tags."""
        cfg = self.config_name or "DEFAULT"
        if details:
            trade_logger.info(
                "%s | %s | %s | %s | %s",
                cfg,
                self._asset_tag,
                self.name,
                event,
                details,
            )
            return
        trade_logger.info("%s | %s | %s | %s", cfg, self._asset_tag, self.name, event)

    def _notify_state_change(self) -> None:
        """Notify dashboard of a state transition."""
        if self.on_state_change is not None:
            self.on_state_change(self.status_dict())

    @property
    def broker_ticker(self) -> str:
        """Concrete ticker used for broker actions."""
        return self._trade_exec_contract or self._exec_contract or self.exec_ticker

    def set_contract_context(
        self,
        *,
        signal_contract: str | None,
        exec_contract: str | None,
        error: str | None = None,
    ) -> None:
        """Update the currently selected feed/broker contract pair."""
        old_pair = (self._signal_contract, self._exec_contract, self._contract_routing_error)
        self._signal_contract = signal_contract or ""
        self._exec_contract = exec_contract or ""
        self._contract_routing_error = error or ""
        new_pair = (self._signal_contract, self._exec_contract, self._contract_routing_error)
        if old_pair == new_pair:
            return
        if self._contract_routing_error:
            self._log_trade(
                "CONTRACT_ROUTE_ERROR",
                "signal_contract=%s exec_root=%s error=%s"
                % (self._signal_contract or "-", self.exec_ticker, self._contract_routing_error),
            )
        else:
            self._log_trade(
                "CONTRACT_ROUTE",
                "signal_contract=%s exec_contract=%s"
                % (self._signal_contract or "-", self._exec_contract or self.exec_ticker),
            )
        self._request_checkpoint()
        self._notify_state_change()

    def _contract_ready_for_entry(self, timestamp: datetime | None = None) -> bool:
        if self._contract_routing_error:
            self._log_trade(
                "ENTRY_SKIPPED_CONTRACT",
                "time=%s error=%s"
                % (timestamp.isoformat() if timestamp else "-", self._contract_routing_error),
            )
            return False
        if self.contract_routing_required and not self._exec_contract:
            self._log_trade(
                "ENTRY_SKIPPED_CONTRACT",
                "time=%s reason=missing_explicit_contract exec_root=%s"
                % (timestamp.isoformat() if timestamp else "-", self.exec_ticker),
            )
            return False
        return True

    def _lock_trade_contract(self) -> None:
        """Freeze the routed contract for the current order/position lifecycle."""
        self._trade_signal_contract = self._signal_contract
        self._trade_exec_contract = self._exec_contract

    def _clear_trade_contract(self) -> None:
        self._trade_signal_contract = ""
        self._trade_exec_contract = ""

    def _emit_trade_record(
        self,
        exit_type: str,
        exit_price: float | None = None,
        *,
        exit_timestamp: datetime | None = None,
    ) -> None:
        """Record a completed trade for cross-session history (G5 gate etc.)."""
        self._exit_type = exit_type
        self._r_result = self._compute_r_result(exit_type, exit_price=exit_price)
        if self.on_trade_exit is None:
            return
        levels = self._levels
        record = TradeRecord(
            session=self.name,
            date=self._current_date,
            direction=levels.direction if levels else 0,
            entry_price=levels.entry if levels else 0.0,
            stop_price=levels.stop if levels else 0.0,
            tp1_price=levels.tp1 if levels else 0.0,
            tp2_price=levels.tp2 if levels else 0.0,
            exit_type=exit_type,
            tp1_hit=self._tp1_hit,
            timestamp=(exit_timestamp or datetime.now()).isoformat(),
            config_name=self.config_name,
            r_result=self._r_result,
            **self._trade_accounting_fields(),
            entry_timestamp=self._fill_timestamp.isoformat() if self._fill_timestamp else "",
            ticker=self._asset_tag.upper(),
            exec_ticker=self.broker_ticker,
            leg=self.name,
            entry_context=self._trade_entry_context(),
        )
        self.on_trade_exit(record)

    def _trade_entry_context(self) -> dict[str, object]:
        """Return strategy-specific entry diagnostics for completed trades."""
        return {}

    async def _exit_single_contract_at_tp1(
        self,
        *,
        exit_timestamp: datetime,
        direction_str: str,
        resolution: str,
    ) -> None:
        """Exit a single-contract split trade at TP1 instead of converting it to BE."""
        levels = self._levels
        if levels is None:
            return
        self._tp1_hit = True
        self._request_checkpoint()
        self._tp1_bar_count = self._bar_count
        self._sync_position_cap()
        self._log_trade(
            "TP1_SINGLE_EXIT",
            "dir=%s tp1=%.2f qty=%.1f exit_time=%s resolution=%s"
            % (direction_str, levels.tp1, levels.qty, exit_timestamp, resolution),
        )
        if self._should_send:
            await self.broker.send_flatten(ticker=self.broker_ticker)
        self._schedule_post_exit_cleanup(
            reason=f"tp1_single_{resolution}",
            delay_s=self._broker_exit_cleanup_delay(1.0),
        )
        self._emit_trade_record("tp1_single", exit_timestamp=exit_timestamp)
        self._set_post_exit_state(exit_timestamp.time(), "tp1_single")
        self._request_checkpoint()
        self._notify_state_change()

    def _price_to_r(self, exit_price: float) -> float:
        """Convert an exit price into an R-multiple using the active trade risk."""
        levels = self._levels
        if levels is None:
            return 0.0
        risk_pts = abs(levels.entry - levels.stop)
        if risk_pts <= 0:
            return 0.0
        pnl_pts = exit_price - levels.entry if levels.direction == 1 else levels.entry - exit_price
        return pnl_pts / risk_pts

    def _runner_stop_price(self) -> float:
        """Current active runner stop after TP1."""
        levels = self._levels
        if levels is None:
            return 0.0
        return self._runner_stop if self._runner_stop is not None else levels.be

    @property
    def _runner_trail_enabled(self) -> bool:
        return self.runner_trail_mode in {"step_r", "risk", "atr"}

    def _runner_trail_candidate_stop(self, high_price: float, low_price: float) -> float | None:
        levels = self._levels
        if levels is None or not self._runner_trail_enabled:
            return None
        risk_pts = abs(levels.entry - levels.stop)
        if risk_pts <= 0.0:
            return None

        if self.runner_trail_mode == "step_r":
            if self.runner_trail_trigger_r <= 0.0 or self.runner_trail_step_r <= 0.0:
                return None
            if levels.direction == 1:
                mfe_r = (high_price - levels.entry) / risk_pts
            else:
                mfe_r = (levels.entry - low_price) / risk_pts
            if mfe_r < self.runner_trail_trigger_r:
                return None
            steps = math.floor((mfe_r - self.runner_trail_trigger_r) / self.runner_trail_step_r + 1e-9)
            lock_r = max(0.0, self.runner_trail_stop_r + steps * self.runner_trail_step_r)
            return levels.entry + lock_r * risk_pts * levels.direction

        if self.runner_trail_mode == "risk":
            if self.runner_trail_gap_r <= 0.0:
                return None
            if levels.direction == 1:
                return high_price - self.runner_trail_gap_r * risk_pts
            return low_price + self.runner_trail_gap_r * risk_pts

        if self.runner_trail_mode == "atr":
            trade_atr = self._trade_daily_atr if self._trade_daily_atr > 0.0 else self._daily_atr
            atr_points = (self.runner_trail_atr_pct / 100.0) * trade_atr
            if atr_points <= 0.0:
                return None
            if levels.direction == 1:
                return high_price - atr_points
            return low_price + atr_points

        return None

    async def _update_runner_trail_stop(
        self,
        *,
        high_price: float,
        low_price: float,
        timestamp: datetime,
        resolution: str,
    ) -> None:
        levels = self._levels
        if levels is None or not self._tp1_hit:
            return
        if self._runner_stop is None:
            self._runner_stop = levels.be
        candidate = self._runner_trail_candidate_stop(high_price, low_price)
        if candidate is None:
            return

        if levels.direction == 1:
            improved = candidate > self._runner_stop + 1e-9
        else:
            improved = candidate < self._runner_stop - 1e-9
        if not improved:
            return

        self._runner_stop = candidate
        direction_str = "long" if levels.direction == 1 else "short"
        self._log_trade(
            "RUNNER_TRAIL_STOP",
            "dir=%s stop=%.2f mode=%s time=%s resolution=%s"
            % (direction_str, self._runner_stop, self.runner_trail_mode, timestamp, resolution),
        )
        if self._should_send:
            await self.broker.send_runner_stop_update(
                direction=direction_str,
                qty=self._remaining_position_qty(),
                stop_price=self._runner_stop,
                tp2=levels.tp2,
                ticker=self.broker_ticker,
            )
        self._request_checkpoint()
        self._notify_state_change()

    def _runner_stop_hit(self, high_price: float, low_price: float) -> tuple[bool, float]:
        """Return whether the active post-TP1 runner stop was touched."""
        levels = self._levels
        if levels is None:
            return False, 0.0
        stop_price = self._runner_stop_price()
        if levels.direction == 1:
            return low_price <= stop_price, stop_price
        return high_price >= stop_price, stop_price

    def _runner_stop_event_name(self, stop_price: float) -> str:
        """Distinguish true trailed runner stops from the original BE stop."""
        levels = self._levels
        if (
            levels is not None
            and self._runner_trail_enabled
            and self._runner_stop is not None
            and not math.isclose(stop_price, levels.be, rel_tol=0.0, abs_tol=1e-9)
        ):
            return "RUNNER_STOP_HIT"
        return "BE_HIT"

    def _compute_r_result(self, exit_type: str, exit_price: float | None = None) -> float:
        """Compute realized R-multiple for a trade exit."""
        levels = self._levels
        if levels is None:
            return 0.0

        is_single = levels.is_single_contract
        stop_r = self._price_to_r(levels.stop)
        tp1_r = self._price_to_r(levels.tp1)
        tp2_r = self._price_to_r(levels.tp2)
        be_r = self._price_to_r(levels.be)

        if exit_type == "sl":
            return stop_r
        elif exit_type == "tp1_single":
            return tp1_r
        elif exit_type == "tp1_be":
            if exit_price is not None:
                exit_r = self._price_to_r(exit_price)
                return exit_r if is_single else (tp1_r + exit_r) / 2.0
            return be_r if is_single else (tp1_r + be_r) / 2.0
        elif exit_type == "tp1_tp2":
            return tp2_r if is_single else (tp1_r + tp2_r) / 2.0
        elif exit_type == "tp2_direct":
            return tp2_r
        elif exit_type == "tp1_eod":
            if exit_price is None:
                return be_r if is_single else (tp1_r + be_r) / 2.0
            exit_r = self._price_to_r(exit_price)
            return exit_r if is_single else (tp1_r + exit_r) / 2.0
        elif exit_type == "eod":
            return self._price_to_r(exit_price) if exit_price is not None else 0.0
        elif exit_type == "manual_flat":
            if exit_price is None:
                return 0.0
            exit_r = self._price_to_r(exit_price)
            return exit_r if is_single or not self._tp1_hit else (tp1_r + exit_r) / 2.0
        return 0.0

    def _trade_accounting_fields(self) -> dict:
        """Return fee-adjusted PnL fields for a completed trade record."""
        levels = self._levels
        if levels is None or self._r_result is None:
            return {
                "net_r_result": None,
                "gross_pnl_usd": None,
                "commission_per_contract": self.commission_per_contract,
                "commission_usd": 0.0,
                "net_pnl_usd": None,
            }

        risk_pts = abs(levels.entry - levels.stop)
        gross_risk_usd = risk_pts * levels.qty * self.point_value
        gross_pnl_usd = self._r_result * gross_risk_usd
        commission_usd = 2.0 * levels.qty * self.commission_per_contract
        net_pnl_usd = gross_pnl_usd - commission_usd
        net_r_result = net_pnl_usd / gross_risk_usd if gross_risk_usd > 0 else self._r_result
        return {
            "net_r_result": net_r_result,
            "gross_pnl_usd": gross_pnl_usd,
            "commission_per_contract": self.commission_per_contract,
            "commission_usd": commission_usd,
            "net_pnl_usd": net_pnl_usd,
        }

    def _orb_reentry_policy_allows(self, exit_type: str, r_result: float | None) -> bool:
        r = 0.0 if r_result is None else r_result
        if self.orb_reentry_policy == "any_reentry":
            return True
        if self.orb_reentry_policy == "after_positive_first":
            return r > 0.0
        if self.orb_reentry_policy == "after_nonpositive_first":
            return r <= 0.0
        if self.orb_reentry_policy == "after_sl_first":
            return exit_type == "sl"
        if self.orb_reentry_policy == "after_full_target_first":
            return exit_type in {"tp1_single", "tp1_tp2", "tp2_direct"}
        return True

    def _set_post_exit_state(self, exit_time: time, exit_type: str) -> None:
        self._clear_trade_contract()
        cap_allows = (
            self.orb_trade_max_per_session <= 0
            or self._session_filled_trades < self.orb_trade_max_per_session
        )
        policy_allows = self._orb_reentry_policy_allows(exit_type, self._r_result)
        if cap_allows and policy_allows and self._in_entry(exit_time):
            self._levels = None
            self._tp1_hit = False
            self._tp1_bar_count = -1
            self._fill_bar_idx = -1
            self._fill_timestamp = None
            self._fill_via_tick = False
            self._armed_at = None
            self._runner_stop = None
            self._trade_daily_atr = 0.0
            self._long_fvg_found = False
            self._short_fvg_found = False
            self._state = State.WAITING_FOR_GAP
            self._log_trade(
                "REENTRY_READY",
                "filled_trades=%d policy=%s"
                % (self._session_filled_trades, self.orb_reentry_policy),
            )
            return
        self._state = State.FLAT

    def _pre_entry_cancel_touched(self, bar: Bar) -> bool:
        if self.limit_cancel_on_pre_entry_target_touch not in {"tp1", "tp2"}:
            return False
        levels = self._levels
        if levels is None:
            return False
        target = levels.tp1 if self.limit_cancel_on_pre_entry_target_touch == "tp1" else levels.tp2
        if levels.direction == 1:
            return bar.high >= target
        return bar.low <= target

    async def _cancel_armed_limit(self, reason: str) -> None:
        self._log_trade("CANCELLED_LIMITS", reason)
        self._release_position_cap()
        if self._should_send:
            await self.broker.send_cancel(ticker=self.broker_ticker)
        self._clear_trade_contract()
        self._state = State.FLAT
        self._request_checkpoint()
        self._notify_state_change()

    async def _replace_armed_limit_if_extreme(self, bar: Bar) -> bool:
        if self.continuation_fvg_selection != "extreme" or self._levels is None:
            return False

        current = self._levels
        if current.direction == 1:
            if self.short_only:
                return False
            detected, entry, gap_size = self._check_long_fvg()
            if not detected or not self._gap_valid(gap_size) or entry <= current.entry:
                return False
            new_levels = self._compute_setup_levels(entry=entry, direction=1, gap_size=gap_size)
            action = "buy"
        else:
            if self.long_only and not self.short_only:
                return False
            detected, entry, gap_size = self._check_short_fvg()
            if not detected or not self._gap_valid(gap_size) or entry >= current.entry:
                return False
            new_levels = self._compute_setup_levels(entry=entry, direction=-1, gap_size=gap_size)
            action = "sell"

        if new_levels is None:
            return False

        self._release_position_cap()
        capped = self._apply_position_cap(new_levels)
        if capped is None:
            restored = self._apply_position_cap(current)
            if restored is not None:
                self._levels = restored
            return False

        self._levels = capped
        self._runner_stop = None
        self._trade_daily_atr = self._daily_atr
        self._armed_at = bar.timestamp + timedelta(minutes=self.base_bar_minutes)
        self._request_checkpoint()
        self._log_trade(
            "LIMIT_REARMED_EXTREME",
            "dir=%s entry=%.2f stop=%.2f tp1=%.2f tp2=%.2f gap=%.2f"
            % (
                "long" if capped.direction == 1 else "short",
                capped.entry,
                capped.stop,
                capped.tp1,
                capped.tp2,
                gap_size,
            ),
        )
        if self._should_send:
            await self.broker.send_cancel(ticker=self.broker_ticker)
            await self.broker.send_entry(
                action=action,
                qty=capped.qty,
                price=capped.entry,
                tp2=capped.tp2,
                stop=capped.stop,
                ticker=self.broker_ticker,
            )
        self._notify_state_change()
        return True

    async def _flatten_position(self, bar: Bar, *, resolution: str, reason: str) -> None:
        """Force a market flatten and record it as an EOD-style exit."""
        levels = self._levels
        direction_str = "long" if (levels and levels.direction == 1) else "short"
        self._log_trade(
            "EOD_FLAT",
            f"dir={direction_str} {reason}={bar.timestamp} resolution={resolution}",
        )
        self._release_position_cap()
        if self._should_send:
            await self.broker.send_flatten(ticker=self.broker_ticker)
        self._emit_trade_record(
            "tp1_eod" if self._tp1_hit else "eod",
            exit_price=bar.close,
            exit_timestamp=bar.timestamp,
        )
        self._set_post_exit_state(bar.timestamp.time(), self._exit_type or "eod")
        self._request_checkpoint()
        self._notify_state_change()

    # ------------------------------------------------------------------
    # Time checks
    # ------------------------------------------------------------------

    @property
    def _crosses_midnight(self) -> bool:
        """True if the session's RTH window spans midnight (e.g. Asia sessions)."""
        return self._orb_start_t > self._flat_end_t

    def _in_orb(self, t: time) -> bool:
        return _time_in_range(t, self._orb_start_t, self._orb_end_t)

    def _in_entry(self, t: time) -> bool:
        return _time_in_range(t, self._entry_start_t, self._entry_end_t)

    def _in_rth(self, t: time) -> bool:
        return _time_in_range(t, self._orb_start_t, self._flat_end_t)

    def _flat_window_for_date(self, date_str: str) -> tuple[time, time]:
        if date_str in self.half_days:
            return _parse_time(self.half_day_flat_start), _parse_time(self.half_day_flat_end)
        return self._flat_start_t, self._flat_end_t

    def _in_flat(self, bar: Bar) -> bool:
        t = bar.timestamp.time()
        date_str = bar.timestamp.strftime("%Y%m%d")
        flat_start, flat_end = self._flat_window_for_date(date_str)
        if flat_start == flat_end:
            return t == flat_start
        return _time_in_range(t, flat_start, flat_end)

    def _is_same_session_night(self, date_str: str, bar_time: time) -> bool:
        """Check if a post-midnight bar belongs to the current session night.

        For cross-midnight sessions (e.g. Asia: ORB 20:00, flat 07:00),
        bars between 00:00 and flat_end belong to the session that started
        the previous evening.  Returns True if:
          1. The bar is in the post-midnight portion (bar_time < orb_start)
          2. The bar's date is exactly _current_date + 1 day
        """
        from datetime import datetime as _dt, timedelta as _td

        # Bar is in the pre-midnight portion (at or after ORB start) —
        # this is a NEW session starting, not a continuation.
        if bar_time >= self._orb_start_t:
            return False

        # Check that date_str is exactly _current_date + 1 day
        if not self._current_date:
            return False
        try:
            current = _dt.strptime(self._current_date, "%Y%m%d")
            bar_date = _dt.strptime(date_str, "%Y%m%d")
            return bar_date == current + _td(days=1)
        except ValueError:
            return False

    def _is_excluded(self, bar: Bar) -> bool:
        date_str = bar.timestamp.strftime("%Y%m%d")
        # Static excluded dates
        if date_str in self.excluded_dates:
            return True
        # Day-of-week exclusion (Monday=0 .. Sunday=6)
        if self.excluded_dow is not None:
            dow = bar.timestamp.weekday()
            if isinstance(self.excluded_dow, (list, tuple)):
                if dow in self.excluded_dow:
                    return True
            elif dow == self.excluded_dow:
                return True
        # FOMC exclusion (GC only)
        if self.fomc_exclusion and date_str in FOMC_DATES:
            return True
        return False

    # ------------------------------------------------------------------
    # Daily reset
    # ------------------------------------------------------------------

    def _reset_day(self, date_str: str, notify: bool = True) -> None:
        """Reset all state for a new trading day."""
        self._release_position_cap()
        self._clear_trade_contract()
        self._state = State.IDLE
        self._orb_high = float("nan")
        self._orb_low = float("nan")
        self._orb_open = float("nan")
        self._bars.clear()
        self._session_bars.clear()
        self._levels = None
        self._tp1_hit = False
        self._tp1_bar_count = -1
        self._fill_bar_idx = -1
        self._fill_timestamp = None
        self._fill_via_tick = False
        self._armed_at = None
        self._runner_stop = None
        self._trade_daily_atr = 0.0
        self._bar_count = 0
        self._long_fvg_found = False
        self._short_fvg_found = False
        self._entry_order_type = "limit"
        self._session_filled_trades = 0
        self._exit_type = None
        self._r_result = None
        self._current_date = date_str
        self._clear_gate_audit()
        logger.info("[%s] New session day: %s", self.name, date_str)
        if notify:
            self._notify_state_change()
        self._request_checkpoint()

    def _expected_orb_bar_count(self) -> int:
        """How many base bars should exist in the full ORB window."""
        from datetime import datetime as _dt, timedelta as _td
        # Build datetime objects on a dummy date to compute the span
        base = _dt(2000, 1, 1)
        start = _dt.combine(base, self._orb_start_t)
        end = _dt.combine(base, self._orb_end_t)
        if end <= start:
            end += _td(days=1)  # cross-midnight
        minutes = (end - start).total_seconds() / 60
        return max(1, int(minutes // self.base_bar_minutes))

    def recover_opening_range(self, bars: list[Bar], now: datetime) -> bool:
        """recover opening range/state for current day after restart."""
        from datetime import timedelta as _td

        now_t = now.time()

        # For cross-midnight sessions, if we're in the post-midnight
        # portion (time < flat_end), the ORB was built on the *previous*
        # calendar day.  Use that date as the session date so bar
        # filtering picks up the correct ORB bars.
        if self._crosses_midnight and now_t < self._orb_start_t:
            session_date = now - _td(days=1)
            date_str = session_date.strftime("%Y%m%d")
        else:
            date_str = now.strftime("%Y%m%d")

        # reset to a clean day state without broadcasting intermediate idle.
        self._reset_day(date_str, notify=False)

        # excluded dates should remain flat even if history exists.
        now_bar = Bar(timestamp=now, open=0.0, high=0.0, low=0.0, close=0.0, volume=0)
        if self._is_excluded(now_bar):
            self._state = State.FLAT
            self._notify_state_change()
            return False

        # For cross-midnight sessions, session bars span two calendar
        # days: the ORB date (pre-midnight) and the next date (post-midnight).
        if self._crosses_midnight:
            valid_dates = {date_str, (datetime.strptime(date_str, "%Y%m%d") + _td(days=1)).strftime("%Y%m%d")}
            today_bars = [b for b in bars if b.timestamp.strftime("%Y%m%d") in valid_dates]
        else:
            today_bars = [b for b in bars if b.timestamp.strftime("%Y%m%d") == date_str]
        session_bars = [b for b in today_bars if self._in_rth(b.timestamp.time())]
        orb_bars = [b for b in session_bars if self._in_orb(b.timestamp.time())]
        if not orb_bars:
            self._notify_state_change()
            return False

        self._orb_high = max(b.high for b in orb_bars)
        self._orb_low = min(b.low for b in orb_bars)
        self._orb_open = float(orb_bars[0].open)
        self._session_bars = list(session_bars)
        self._bars = session_bars[-10:]
        self._bar_count = len(session_bars)

        # Check if the preloaded history fully covers the ORB window.
        # If bars are missing (e.g. due to the DataBento historical delay),
        # stay in ORB_BUILDING so live bars can complete the range.
        expected_orb_bars = self._expected_orb_bar_count()
        orb_complete = len(orb_bars) >= expected_orb_bars

        if self._in_orb(now_t):
            self._state = State.ORB_BUILDING
        elif not orb_complete:
            # Past ORB window but preload missed some bars — stay in
            # ORB_BUILDING so the first live bars can fill the gap.
            self._state = State.ORB_BUILDING
            logger.warning(
                "[%s] ORB incomplete after recovery: got %d/%d bars, "
                "staying in ORB_BUILDING for live completion",
                self.name, len(orb_bars), expected_orb_bars,
            )
        elif self._in_entry(now_t):
            if self.g5_gate_check is not None and self.g5_gate_check(self._current_date):
                self._state = State.FLAT
            elif self._context_gate_block_reason() is not None:
                self._state = State.FLAT
            else:
                blocking_gate = self._blocking_regime_gate_name(self._current_date)
                self._record_regime_gate_status(self._current_date, blocking_gate)
                if blocking_gate is not None:
                    self._maybe_log_regime_gate_audit()
                    self._state = State.FLAT
                else:
                    self._maybe_log_regime_gate_audit()
                    self._state = State.WAITING_FOR_GAP
        elif self._in_flat(now_bar):
            self._state = State.FLAT
        elif self._in_rth(now_t):
            # post-entry/pre-flat should not scan for new setups.
            self._state = State.FLAT
        else:
            self._state = State.IDLE

        logger.info(
            "[%s] OR recovered: high=%.2f low=%.2f range=%.2f state=%s bars=%d/%d",
            self.name,
            self._orb_high,
            self._orb_low,
            self._orb_range,
            self._state.value,
            len(orb_bars),
            expected_orb_bars,
        )
        self._notify_state_change()
        return True

    # ------------------------------------------------------------------
    # ORB range helper
    # ------------------------------------------------------------------

    @property
    def _orb_range(self) -> float:
        """Current ORB range (high - low). Returns 0 if not ready."""
        if self._orb_high != self._orb_high or self._orb_low != self._orb_low:
            return 0.0  # NaN check
        return self._orb_high - self._orb_low

    def _bar_close_timestamp(self, bar: Bar) -> datetime:
        return bar.timestamp + timedelta(minutes=self.base_bar_minutes)

    def _bar_closes_orb_window(self, bar: Bar) -> bool:
        """True when this ORB bar closes at/after the configured ORB end."""
        if not self._in_orb(bar.timestamp.time()):
            return False
        close_time = self._bar_close_timestamp(bar).time()
        return not self._in_orb(close_time)

    def _context_gate_block_reason(self) -> str | None:
        if self.max_prior_rolling_atr_pct > 0.0:
            if not math.isfinite(self._prior_rolling_atr_pct):
                return "missing_prior_rolling_atr_pct"
            if self._prior_rolling_atr_pct > self.max_prior_rolling_atr_pct:
                return (
                    "prior_rolling_atr_pct=%.4f max=%.4f"
                    % (self._prior_rolling_atr_pct, self.max_prior_rolling_atr_pct)
                )

        if self.max_orb_range_pct > 0.0:
            if not math.isfinite(self._orb_open) or self._orb_open <= 0.0 or self._orb_range <= 0.0:
                return "missing_orb_range_pct"
            orb_range_pct = self._orb_range / self._orb_open * 100.0
            if orb_range_pct > self.max_orb_range_pct:
                return (
                    "orb_range_pct=%.4f max=%.4f open=%.2f range=%.2f"
                    % (orb_range_pct, self.max_orb_range_pct, self._orb_open, self._orb_range)
                )

        return None

    def _arm_order(self, signal_bar: Bar) -> None:
        """Activate a setup only after the signal bar has fully closed."""
        self._lock_trade_contract()
        self._state = State.ARMED_LIMIT
        self._armed_at = signal_bar.timestamp + timedelta(minutes=self.base_bar_minutes)
        self._entry_order_type = "limit"
        self._request_checkpoint()

    def _arm_order_at(self, armed_at: datetime) -> None:
        """Activate an already-known order at a specific timestamp."""
        self._lock_trade_contract()
        self._state = State.ARMED_LIMIT
        self._armed_at = armed_at
        self._request_checkpoint()

    def _breakout_buffer_points(self) -> float:
        buffer_points = float(self.orb_breakout_buffer_ticks) * float(self.min_tick)
        if self.orb_breakout_buffer_atr_pct > 0.0:
            if self._daily_atr <= 0.0:
                return float("nan")
            buffer_points += (self.orb_breakout_buffer_atr_pct / 100.0) * self._daily_atr
        return buffer_points

    def _entry_fill_touched(self, high_price: float, low_price: float) -> bool:
        levels = self._levels
        if levels is None:
            return False
        is_long = levels.direction == 1
        if self._entry_order_type == "stop":
            return high_price >= levels.entry if is_long else low_price <= levels.entry
        return low_price <= levels.entry if is_long else high_price >= levels.entry

    async def _arm_orb_breakout(self, bar: Bar, *, armed_at: datetime) -> None:
        if not self._in_entry(armed_at.time()):
            self._log_trade("NO_SETUP", "ORB breakout armed outside entry window")
            self._state = State.FLAT
            self._request_checkpoint()
            self._notify_state_change()
            return

        buffer_points = self._breakout_buffer_points()
        if not math.isfinite(buffer_points):
            self._log_trade("NO_SETUP", "missing ATR for ORB breakout buffer")
            self._state = State.FLAT
            self._request_checkpoint()
            self._notify_state_change()
            return

        direction = -1 if self.short_only else 1
        if self.long_only and not self.short_only:
            direction = 1
        elif self.short_only:
            direction = -1
        elif not self.long_only:
            self._log_trade("NO_SETUP", "two-sided ORB breakout requires split one-sided engines")
            self._state = State.FLAT
            self._request_checkpoint()
            self._notify_state_change()
            return

        entry = self._orb_high + buffer_points if direction == 1 else self._orb_low - buffer_points
        levels = self._compute_setup_levels(entry=entry, direction=direction, gap_size=0.0)
        if levels is not None:
            levels = self._apply_position_cap(levels)
        if levels is None:
            self._log_trade("NO_SETUP", "ORB breakout levels rejected")
            self._state = State.FLAT
            self._request_checkpoint()
            self._notify_state_change()
            return

        self._levels = levels
        self._runner_stop = None
        self._trade_daily_atr = self._daily_atr
        self._entry_order_type = "stop"
        self._arm_order_at(armed_at)
        self._log_trade(
            "ORB_BREAKOUT_ARMED",
            (
                "dir=%s entry=%.2f stop=%.2f tp1=%.2f tp2=%.2f qty=%.1f "
                "orb_high=%.2f orb_low=%.2f armed_at=%s"
            )
            % (
                "long" if direction == 1 else "short",
                levels.entry,
                levels.stop,
                levels.tp1,
                levels.tp2,
                levels.qty,
                self._orb_high,
                self._orb_low,
                armed_at.isoformat(),
            ),
        )
        self._notify_state_change()
        if self._should_send:
            await self.broker.send_entry(
                action="buy" if direction == 1 else "sell",
                qty=levels.qty,
                price=levels.entry,
                tp2=levels.tp2,
                stop=levels.stop,
                ticker=self.broker_ticker,
            )

    async def _finish_orb_ready(self, bar: Bar, *, armed_at: datetime | None = None) -> None:
        if self.g5_gate_check is not None and self.g5_gate_check(self._current_date):
            self._log_trade("G5_GATE_BLOCKED", "date=%s" % self._current_date)
            self._state = State.FLAT
            self._request_checkpoint()
            self._notify_state_change()
            return
        context_block_reason = self._context_gate_block_reason()
        if context_block_reason is not None:
            self._log_trade("CONTEXT_GATE_BLOCKED", context_block_reason)
            self._state = State.FLAT
            self._request_checkpoint()
            self._notify_state_change()
            return
        blocking_gate = self._blocking_regime_gate_name(self._current_date)
        self._record_regime_gate_status(self._current_date, blocking_gate)
        if blocking_gate is not None:
            self._maybe_log_regime_gate_audit()
            self._state = State.FLAT
            self._request_checkpoint()
            self._notify_state_change()
            return

        self._maybe_log_regime_gate_audit()
        self._state = State.WAITING_FOR_GAP
        self._request_checkpoint()
        self._log_trade(
            "ORB_READY",
            "high=%.2f low=%.2f range=%.2f atr=%.2f"
            % (
                self._orb_high,
                self._orb_low,
                self._orb_range,
                self._daily_atr,
            ),
        )
        self._notify_state_change()
        if self.strategy_type == "orb_breakout":
            await self._arm_orb_breakout(
                bar,
                armed_at=armed_at or self._bar_close_timestamp(bar),
            )
            return
        await self._handle_scanning(bar, bar.timestamp.time())

    # ------------------------------------------------------------------
    # FVG detection (inline, 3-bar check)
    # ------------------------------------------------------------------

    def _check_long_fvg(self) -> tuple[bool, float, float]:
        """Check for bullish FVG in last 3 bars.

        Returns (detected, entry_price, gap_size).
        """
        if len(self._bars) < 3:
            return False, 0.0, 0.0

        bar0 = self._bars[-1]  # current (most recent)
        bar1 = self._bars[-2]  # middle (impulse candle)
        bar2 = self._bars[-3]  # oldest (before candle)

        # Pine: high[2] < low[0] AND high[2] < high[1] AND low[2] < low[0]
        if bar2.high < bar0.low and bar2.high < bar1.high and bar2.low < bar0.low:
            gap_size = bar0.low - bar2.high
            entry = bar0.low  # FVG top

            # ORB directional filter
            if self.icf_enabled:
                # ICF-relaxed: FVG top above ORB high OR impulse close above ORB high
                orb_ok = (entry > self._orb_high) or (bar1.close > self._orb_high)
            else:
                # Standard: FVG top must be above ORB high
                orb_ok = entry > self._orb_high

            if orb_ok:
                return True, entry, gap_size

        return False, 0.0, 0.0

    def _check_short_fvg(self) -> tuple[bool, float, float]:
        """Check for bearish FVG in last 3 bars.

        Returns (detected, entry_price, gap_size).
        """
        if len(self._bars) < 3:
            return False, 0.0, 0.0

        bar0 = self._bars[-1]
        bar1 = self._bars[-2]
        bar2 = self._bars[-3]

        # Pine: low[2] > high[0] AND low[2] > low[1] AND high[2] > high[0]
        if bar2.low > bar0.high and bar2.low > bar1.low and bar2.high > bar0.high:
            gap_size = bar2.low - bar0.high
            entry = bar0.high  # FVG bottom
            # Must be below ORB low
            if entry < self._orb_low:
                return True, entry, gap_size

        return False, 0.0, 0.0

    def _gap_valid(self, gap_size: float) -> bool:
        """Check if gap size is within bounds (ATR-based or ORB-based)."""
        if self.gap_filter_basis == "orb":
            orb_range = self._orb_range
            if orb_range <= 0:
                return False
            min_gap = (self.min_gap_orb_pct / 100.0) * orb_range
            return gap_size >= min_gap
        else:
            # ATR-based gap filter
            if self._daily_atr <= 0:
                return False
            min_gap = (self.min_gap_atr_pct / 100.0) * self._daily_atr
            if gap_size < min_gap:
                return False
            if self.max_gap_atr_pct > 0:
                max_gap = (self.max_gap_atr_pct / 100.0) * self._daily_atr
                if gap_size > max_gap:
                    return False
            return True

    def _adaptive_risk_scale(self) -> float:
        manager = getattr(self, "adaptive_risk", None)
        if manager is None:
            return 1.0
        try:
            return float(manager.risk_scale())
        except Exception:
            logger.exception("[%s] adaptive risk scale failed; using 1.0x", self.name)
            return 1.0

    def _compute_setup_levels(self, *, entry: float, direction: int, gap_size: float) -> TradeLevels | None:
        risk_scale = self._adaptive_risk_scale()
        return compute_trade_levels(
            entry=entry,
            direction=direction,
            gap_size=gap_size,
            daily_atr=self._daily_atr,
            stop_atr_pct=self.stop_atr_pct,
            rr=self.rr,
            tp1_ratio=self.tp1_ratio,
            risk_usd=self.risk_usd * risk_scale,
            point_value=self.point_value,
            min_qty=self.min_qty,
            qty_step=self.qty_step,
            be_offset_ticks=self.be_offset_ticks,
            min_tick=self.min_tick,
            stop_basis=self.stop_basis,
            orb_range=self._orb_range,
            stop_orb_pct=self.stop_orb_pct,
            min_stop_pts=self.min_stop_pts,
            min_tp1_pts=self.min_tp1_pts,
            max_single_risk_usd=self.max_single_risk_usd * risk_scale,
            wide_stop_target_threshold_points=self.wide_stop_target_threshold_points,
            wide_stop_target_rr=self.wide_stop_target_rr,
            exit_mode=self.exit_mode,
        )

    # ------------------------------------------------------------------
    # Main bar handler
    # ------------------------------------------------------------------

    async def on_bar(self, bar: Bar, daily_atr: float) -> None:
        """Process a new confirmed 5m bar.

        This is the main entry point called by the feed on each bar close.
        """
        bar_time = bar.timestamp.time()
        date_str = bar.timestamp.strftime("%Y%m%d")

        # Store daily ATR
        self._daily_atr = daily_atr
        # ATH state is maintained from all completed 5m bars for the signal
        # instrument, including overnight bars. The signal check below uses
        # the current closed bar, matching the post-filter research context.
        self._update_ath_state(bar)

        # Skip if not in RTH
        if not self._in_rth(bar_time):
            # If we were in an active state and left RTH, go flat
            if self._state not in (State.IDLE, State.FLAT):
                self._release_position_cap()
                if self._state == State.ARMED_LIMIT:
                    self._log_trade("CANCEL", f"outside RTH state={self._state.value}")
                    if self._should_send:
                        await self.broker.send_cancel(ticker=self.broker_ticker)
                elif self._state in (State.FILLED, State.MANAGING):
                    await self._flatten_position(
                        bar,
                        resolution="5m",
                        reason="bar_time" if self._in_flat(bar) else "outside_rth_time",
                    )
                    return
                else:
                    self._log_trade("NO_SETUP", f"outside RTH state={self._state.value}")
                self._state = State.FLAT
                self._request_checkpoint()
                self._notify_state_change()
            return

        # New session day detection
        # For cross-midnight sessions (e.g. Asia: ORB 20:00, flat 07:00),
        # the calendar date changes at midnight while the session is still
        # active.  Post-midnight bars belong to the *previous* session
        # night and must NOT trigger a reset — regardless of engine state.
        if date_str != self._current_date:
            if self._crosses_midnight and self._is_same_session_night(date_str, bar_time):
                # Still the same session night — do NOT reset.
                logger.debug(
                    "[%s] Cross-midnight: skipping reset (same session night) "
                    "date=%s current_date=%s bar_time=%s state=%s",
                    self.name, date_str, self._current_date,
                    bar_time, self._state.value,
                )
            else:
                logger.debug(
                    "[%s] Day reset: %s -> %s bar_time=%s state=%s",
                    self.name, self._current_date, date_str,
                    bar_time, self._state.value,
                )
                if self._state == State.ARMED_LIMIT and self._should_send:
                    await self.broker.send_cancel(ticker=self.broker_ticker)
                self._reset_day(date_str)

        # Skip excluded dates (DOW, FOMC, static dates)
        if self._is_excluded(bar):
            return

        # Add bar to rolling window (keep last 10 for safety)
        self._session_bars.append(bar)
        self._bars.append(bar)
        if len(self._bars) > 10:
            self._bars.pop(0)
        self._bar_count += 1

        # State machine dispatch
        if self._state == State.IDLE:
            await self._handle_idle(bar, bar_time)
        elif self._state == State.ORB_BUILDING:
            await self._handle_orb_building(bar, bar_time)
        elif self._state == State.WAITING_FOR_GAP:
            await self._handle_scanning(bar, bar_time)
        elif self._state == State.ARMED_LIMIT:
            await self._handle_armed(bar, bar_time)
        elif self._state in (State.FILLED, State.MANAGING):
            await self._handle_managing(bar, bar_time)
        elif self._state == State.FLAT:
            pass  # done for the day

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    async def _handle_idle(self, bar: Bar, bar_time: time) -> None:
        """Waiting for ORB window to start."""
        if self._in_orb(bar_time):
            self._state = State.ORB_BUILDING
            self._request_checkpoint()
            self._orb_open = bar.open
            self._orb_high = bar.high
            self._orb_low = bar.low
            logger.info(
                "[%s] ORB building started: high=%.2f low=%.2f",
                self.name, bar.high, bar.low,
            )
            self._notify_state_change()
        elif not self._in_orb(bar_time) and self._orb_range == 0.0:
            # In RTH but past ORB window with no ORB data — missed the
            # session (e.g. service started after ORB closed and recovery
            # did not find historical bars).
            self._log_trade("NO_SETUP", "missed ORB window (late start)")
            self._state = State.FLAT
            self._request_checkpoint()
            self._notify_state_change()

    async def _handle_orb_building(self, bar: Bar, bar_time: time) -> None:
        """Accumulating ORB high/low."""
        if self._in_orb(bar_time):
            if not math.isfinite(self._orb_open):
                self._orb_open = bar.open
            if bar.high > self._orb_high:
                self._orb_high = bar.high
            if bar.low < self._orb_low:
                self._orb_low = bar.low
            logger.info(
                "[%s] ORB bar: time=%s H=%.2f L=%.2f | running high=%.2f low=%.2f",
                self.name, bar.timestamp, bar.high, bar.low,
                self._orb_high, self._orb_low,
            )
            if self.strategy_type == "orb_breakout" and self._bar_closes_orb_window(bar):
                await self._finish_orb_ready(bar, armed_at=self._bar_close_timestamp(bar))
        else:
            # ORB window closed — check gates before scanning/arming.
            await self._finish_orb_ready(bar, armed_at=self._bar_close_timestamp(bar))

    async def _handle_scanning(self, bar: Bar, bar_time: time) -> None:
        """Scanning for first FVG in entry window (long only)."""
        if (
            self.orb_trade_max_per_session > 0
            and self._session_filled_trades >= self.orb_trade_max_per_session
        ):
            self._log_trade("NO_SETUP", "trade cap reached")
            self._state = State.FLAT
            self._request_checkpoint()
            self._notify_state_change()
            return

        if not self._in_entry(bar_time):
            # Past entry window — cancel and go flat
            self._log_trade("NO_SETUP", "entry window closed")
            self._state = State.FLAT
            self._request_checkpoint()
            self._notify_state_change()
            return

        # Check for long FVG (first one only, skip if short_only)
        if not self.short_only and not self._long_fvg_found:
            detected, entry, gap_size = self._check_long_fvg()
            if detected:
                if not self._gap_valid(gap_size):
                    logger.debug(
                        "[%s] Long FVG rejected: gap=%.2f invalid size "
                        "bar_time=%s atr=%.2f orb_range=%.2f",
                        self.name, gap_size, bar_time,
                        self._daily_atr, self._orb_range,
                    )
                else:
                    if self.structure_gate_check is not None and not self.structure_gate_check(self, bar):
                        self._log_trade(
                            "STRUCTURE_GATE_BLOCKED",
                            "gate=%s bar_time=%s" % (
                                self.structure_gate or "custom",
                                bar.timestamp.isoformat(),
                            ),
                        )
                        return
                    ath_blocked, ath_gap_pct = self._ath_gate_blocks(bar)
                    if self._ath_gate_enabled:
                        self._record_ath_gate_check(
                            bar,
                            ath_gap_pct,
                            "long",
                            blocked=ath_blocked,
                        )
                    if ath_blocked:
                        self._log_trade(
                            "ATH_GATE_BLOCKED",
                            (
                                "gap_pct=%.3f min=%.3f max=%.3f ath=%.2f "
                                "close=%.2f bar_time=%s"
                            )
                            % (
                                ath_gap_pct if ath_gap_pct is not None else float("nan"),
                                self.ath_block_min_pct,
                                self.ath_block_max_pct,
                                self._ath_high,
                                bar.close,
                                bar.timestamp.isoformat(),
                            ),
                        )
                        return
                    self._long_fvg_found = True
                    if not self._contract_ready_for_entry(bar.timestamp):
                        return
                    levels = self._compute_setup_levels(entry=entry, direction=1, gap_size=gap_size)
                    if levels is not None:
                        levels = self._apply_position_cap(levels)
                    if levels is not None:
                        self._levels = levels
                        self._runner_stop = None
                        self._trade_daily_atr = self._daily_atr
                        self._arm_order(bar)
                        self._log_trade(
                            "LONG_SETUP",
                            (
                                "entry=%.2f stop=%.2f tp1=%.2f tp2=%.2f "
                                "qty=%.1f gap=%.2f atr=%.2f orb_range=%.2f"
                            )
                            % (
                                levels.entry,
                                levels.stop,
                                levels.tp1,
                                levels.tp2,
                                levels.qty,
                                gap_size,
                                self._daily_atr,
                                self._orb_range,
                            ),
                        )
                        self._notify_state_change()
                        if self._should_send:
                            await self.broker.send_entry(
                                action="buy",
                                qty=levels.qty,
                                price=levels.entry,
                                tp2=levels.tp2,
                                stop=levels.stop,
                                ticker=self.broker_ticker,
                            )
                        return
                    else:
                        logger.debug(
                            "[%s] Long FVG rejected: levels=None "
                            "entry=%.2f gap=%.2f bar_time=%s",
                            self.name, entry, gap_size, bar_time,
                        )
            elif len(self._bars) >= 3:
                logger.debug(
                    "[%s] No long FVG: H=[%.2f,%.2f,%.2f] "
                    "L=[%.2f,%.2f,%.2f] orb_high=%.2f bar_time=%s",
                    self.name,
                    self._bars[-3].high, self._bars[-2].high, self._bars[-1].high,
                    self._bars[-3].low, self._bars[-2].low, self._bars[-1].low,
                    self._orb_high, bar_time,
                )

        # Short FVG check (only if not long_only, or short_only)
        if (not self.long_only or self.short_only) and not self._short_fvg_found:
            detected, entry, gap_size = self._check_short_fvg()
            if detected and self._gap_valid(gap_size):
                ath_blocked, ath_gap_pct = self._ath_gate_blocks(bar)
                if self._ath_gate_enabled:
                    self._record_ath_gate_check(
                        bar,
                        ath_gap_pct,
                        "short",
                        blocked=ath_blocked,
                    )
                if ath_blocked:
                    self._log_trade(
                        "ATH_GATE_BLOCKED",
                        (
                            "gap_pct=%.3f min=%.3f max=%.3f ath=%.2f "
                            "close=%.2f bar_time=%s"
                        )
                        % (
                            ath_gap_pct if ath_gap_pct is not None else float("nan"),
                            self.ath_block_min_pct,
                            self.ath_block_max_pct,
                            self._ath_high,
                            bar.close,
                            bar.timestamp.isoformat(),
                        ),
                    )
                    return
                self._short_fvg_found = True
                if not self._contract_ready_for_entry(bar.timestamp):
                    return
                levels = self._compute_setup_levels(entry=entry, direction=-1, gap_size=gap_size)
                if levels is not None:
                    levels = self._apply_position_cap(levels)
                if levels is not None:
                    self._levels = levels
                    self._runner_stop = None
                    self._trade_daily_atr = self._daily_atr
                    # Re-use ARMED_LIMIT state for armed short in non-long-only mode
                    # (short not used in 5-leg portfolio but kept for backward compat)
                    self._arm_order(bar)
                    self._log_trade(
                        "SHORT_SETUP",
                        (
                            "entry=%.2f stop=%.2f tp1=%.2f tp2=%.2f "
                            "qty=%.1f gap=%.2f atr=%.2f"
                        )
                        % (
                            levels.entry,
                            levels.stop,
                            levels.tp1,
                            levels.tp2,
                            levels.qty,
                            gap_size,
                            self._daily_atr,
                        ),
                    )
                    self._notify_state_change()
                    if self._should_send:
                        await self.broker.send_entry(
                            action="sell",
                            qty=levels.qty,
                            price=levels.entry,
                            tp2=levels.tp2,
                            stop=levels.stop,
                            ticker=self.broker_ticker,
                        )
                    return

    async def _handle_armed(self, bar: Bar, bar_time: time) -> None:
        """Limit order placed, waiting for fill or cancellation."""
        levels = self._levels
        if levels is None:
            self._state = State.FLAT
            self._request_checkpoint()
            return

        # Cancel if past entry window
        if not self._in_entry(bar_time):
            await self._cancel_armed_limit("entry window expired entry=%.2f" % levels.entry)
            return

        if not self.allow_5m_fill_detection:
            await self._replace_armed_limit_if_extreme(bar)
            return

        # Check for fill: limit entries fill on retrace, breakout entries on stop touch.
        is_long = levels.direction == 1
        filled = self._entry_fill_touched(bar.high, bar.low)

        if filled:
            self._fill_bar_idx = self._bar_count
            self._fill_timestamp = bar.timestamp
            self._fill_via_tick = False
            self._armed_at = None
            self._runner_stop = None
            self._session_filled_trades += 1
            self._log_trade(
                "FILLED",
                "dir=%s entry=%.2f stop=%.2f tp1=%.2f tp2=%.2f qty=%.1f bar_time=%s resolution=5m"
                % ("long" if is_long else "short", levels.entry, levels.stop, levels.tp1, levels.tp2, levels.qty, bar.timestamp),
            )
            # Immediately transition to managing — but don't check exits on fill bar
            self._state = State.MANAGING
            self._request_checkpoint()
            self._notify_state_change()
            return

        if self._pre_entry_cancel_touched(bar):
            await self._cancel_armed_limit(
                "%s touched before entry target=%.2f entry=%.2f"
                % (
                    self.limit_cancel_on_pre_entry_target_touch,
                    levels.tp1 if self.limit_cancel_on_pre_entry_target_touch == "tp1" else levels.tp2,
                    levels.entry,
                )
            )
            return

        await self._replace_armed_limit_if_extreme(bar)

    async def _handle_managing(self, bar: Bar, bar_time: time) -> None:
        """Position open — manage TP1/TP2/SL/BE/EOD."""
        levels = self._levels
        if levels is None:
            self._state = State.FLAT
            self._request_checkpoint()
            return

        # EOD flat check (takes priority)
        if self._in_flat(bar):
            await self._flatten_position(bar, resolution="5m", reason="bar_time")
            return

        direction_str = "long" if levels.direction == 1 else "short"

        # Gate: don't check exits on the fill bar itself (same-bar prevention)
        if self._bar_count <= self._fill_bar_idx:
            return

        # If the fill happened on a 1s tick, only the 1s path can preserve
        # correct pre-fill/post-fill sequencing for exits.
        if self._fill_via_tick:
            return

        # Gate: skip the 5m bar that contains the TP1 hit.
        # When TP1 is detected on a 1s tick mid-bar, the enclosing 5m bar's
        # low includes pre-TP1 price action near the entry, making
        # bar.low <= BE trivially true and causing a false BE_HIT.
        # The 1s tick path is authoritative for exits on this bar.
        if self._tp1_hit and self._tp1_bar_count >= 0 and self._bar_count <= self._tp1_bar_count:
            return

        is_long = levels.direction == 1

        # Check stop loss (before TP1 — conservative)
        sl_hit = False
        if is_long and bar.low <= levels.stop:
            sl_hit = True
        elif not is_long and bar.high >= levels.stop:
            sl_hit = True

        if sl_hit and not self._tp1_hit:
            self._log_trade(
                "SL_HIT",
                "dir=%s stop=%.2f bar_time=%s resolution=5m"
                % (direction_str, levels.stop, bar.timestamp),
            )
            self._schedule_post_exit_cleanup(
                reason="sl_hit_5m",
                delay_s=self._broker_exit_cleanup_delay(1.0),
            )
            self._emit_trade_record("sl", exit_timestamp=bar.timestamp)
            self._set_post_exit_state(bar.timestamp.time(), "sl")
            self._request_checkpoint()
            self._notify_state_change()
            return

        if self.exit_mode == "single_target" and not self._tp1_hit:
            target_hit = False
            if is_long and bar.high >= levels.tp2:
                target_hit = True
            elif not is_long and bar.low <= levels.tp2:
                target_hit = True

            if target_hit:
                self._log_trade(
                    "SINGLE_TARGET_HIT",
                    "dir=%s target=%.2f bar_time=%s resolution=5m"
                    % (direction_str, levels.tp2, bar.timestamp),
                )
                self._schedule_post_exit_cleanup(
                    reason="single_target_5m",
                    delay_s=self._broker_exit_cleanup_delay(1.0),
                )
                self._emit_trade_record("tp2_direct", exit_timestamp=bar.timestamp)
                self._set_post_exit_state(bar.timestamp.time(), "tp2_direct")
                self._request_checkpoint()
                self._notify_state_change()
                return

        # Check TP1
        tp1_touched = False
        if is_long and bar.high >= levels.tp1:
            tp1_touched = True
        elif not is_long and bar.low <= levels.tp1:
            tp1_touched = True

        if tp1_touched and not self._tp1_hit:
            if levels.is_single_contract:
                await self._exit_single_contract_at_tp1(
                    exit_timestamp=bar.timestamp,
                    direction_str=direction_str,
                    resolution="5m",
                )
                return

            self._tp1_hit = True
            self._runner_stop = levels.be
            self._request_checkpoint()
            self._tp1_bar_count = self._bar_count
            self._sync_position_cap()

            self._log_trade(
                "TP1_PARTIAL",
                "dir=%s tp1=%.2f half_qty=%.1f be=%.2f tp2=%.2f bar_time=%s resolution=5m"
                % (
                    direction_str,
                    levels.tp1,
                    levels.half_qty,
                    levels.be,
                    levels.tp2,
                    bar.timestamp,
                ),
            )
            if self._should_send:
                await self.broker.send_tp1_multi(
                    direction=direction_str,
                    total_qty=levels.qty,
                    exit_qty=levels.half_qty,
                    be_price=levels.be,
                    tp2=levels.tp2,
                    ticker=self.broker_ticker,
                )

            if self._runner_trail_enabled:
                await self._update_runner_trail_stop(
                    high_price=bar.high,
                    low_price=bar.low,
                    timestamp=bar.timestamp,
                    resolution="5m",
                )
                runner_stop_hit, runner_stop = self._runner_stop_hit(bar.high, bar.low)
                if runner_stop_hit:
                    event_name = self._runner_stop_event_name(runner_stop)
                    self._log_trade(
                        event_name,
                        "dir=%s stop=%.2f bar_time=%s resolution=5m"
                        % (direction_str, runner_stop, bar.timestamp),
                    )
                    self._schedule_post_exit_cleanup(reason="runner_stop_same_bar_5m")
                    self._emit_trade_record(
                        "tp1_be",
                        exit_price=runner_stop,
                        exit_timestamp=bar.timestamp,
                    )
                    self._set_post_exit_state(bar.timestamp.time(), "tp1_be")
                    self._request_checkpoint()
                    self._notify_state_change()
                    return

            self._notify_state_change()
            return

        # After TP1, check BE stop and TP2
        if self._tp1_hit:
            await self._update_runner_trail_stop(
                high_price=bar.high,
                low_price=bar.low,
                timestamp=bar.timestamp,
                resolution="5m",
            )
            be_hit, runner_stop = self._runner_stop_hit(bar.high, bar.low)

            if be_hit:
                event_name = self._runner_stop_event_name(runner_stop)
                self._log_trade(
                    event_name,
                    "dir=%s stop=%.2f bar_time=%s resolution=5m"
                    % (direction_str, runner_stop, bar.timestamp),
                )
                self._schedule_post_exit_cleanup(reason="be_hit_5m")
                self._emit_trade_record(
                    "tp1_be",
                    exit_price=runner_stop,
                    exit_timestamp=bar.timestamp,
                )
                self._set_post_exit_state(bar.timestamp.time(), "tp1_be")
                self._request_checkpoint()
                self._notify_state_change()
                return

            tp2_hit = False
            if is_long and bar.high >= levels.tp2:
                tp2_hit = True
            elif not is_long and bar.low <= levels.tp2:
                tp2_hit = True

            if tp2_hit:
                self._log_trade(
                    "TP2_HIT",
                    "dir=%s tp2=%.2f bar_time=%s resolution=5m"
                    % (direction_str, levels.tp2, bar.timestamp),
                )
                self._schedule_post_exit_cleanup(reason="tp2_hit_5m")
                self._emit_trade_record("tp1_tp2", exit_timestamp=bar.timestamp)
                self._set_post_exit_state(bar.timestamp.time(), "tp1_tp2")
                self._request_checkpoint()
                self._notify_state_change()
                return
        else:
            # Before TP1: check if full TP2 hit (skipped TP1)
            tp2_hit = False
            if is_long and bar.high >= levels.tp2:
                tp2_hit = True
            elif not is_long and bar.low <= levels.tp2:
                tp2_hit = True

            if tp2_hit:
                self._log_trade(
                    "TP2_DIRECT",
                    "dir=%s tp2=%.2f bar_time=%s resolution=5m"
                    % (direction_str, levels.tp2, bar.timestamp),
                )
                self._schedule_post_exit_cleanup(
                    reason="tp2_direct_5m",
                    delay_s=self._broker_exit_cleanup_delay(1.0),
                )
                self._emit_trade_record("tp2_direct", exit_timestamp=bar.timestamp)
                self._set_post_exit_state(bar.timestamp.time(), "tp2_direct")
                self._request_checkpoint()
                self._notify_state_change()
                return

    # ------------------------------------------------------------------
    # 1-second tick handlers (fill detection + exit management)
    # ------------------------------------------------------------------

    async def on_tick(self, tick: Bar, daily_atr: float) -> None:
        """Process a 1-second bar for fill detection and exit management.

        Only acts in ARMED_LIMIT and MANAGING states. All other states
        (IDLE, ORB_BUILDING, WAITING_FOR_GAP, FLAT) ignore ticks entirely.
        """
        self._daily_atr = daily_atr

        if self._state == State.ARMED_LIMIT:
            await self._handle_armed_tick(tick)
        elif self._state in (State.FILLED, State.MANAGING):
            await self._handle_managing_tick(tick)

    async def _handle_armed_tick(self, tick: Bar) -> None:
        """Detect limit order fill on 1s bars."""
        levels = self._levels
        if levels is None:
            self._state = State.FLAT
            self._request_checkpoint()
            return

        tick_time = tick.timestamp.time()

        # Cancel if past entry window
        if not self._in_entry(tick_time):
            await self._cancel_armed_limit("entry window expired (1s) entry=%.2f" % levels.entry)
            return

        # A setup confirmed on a 5m close cannot fill from ticks that
        # chronologically belong to that same still-forming signal candle.
        if self._armed_at is not None and tick.timestamp < self._armed_at:
            return

        # Check fill. FVG entries are limit orders; ORB breakouts are stop orders.
        is_long = levels.direction == 1
        filled = self._entry_fill_touched(tick.high, tick.low)

        if filled:
            self._fill_timestamp = tick.timestamp
            self._fill_bar_idx = self._bar_count
            self._fill_via_tick = True
            self._armed_at = None
            self._runner_stop = None
            self._session_filled_trades += 1
            self._state = State.MANAGING
            self._request_checkpoint()
            self._log_trade(
                "FILLED",
                "dir=%s entry=%.2f stop=%.2f tp1=%.2f tp2=%.2f qty=%.1f tick_time=%s resolution=1s"
                % ("long" if is_long else "short", levels.entry, levels.stop, levels.tp1, levels.tp2, levels.qty, tick.timestamp),
            )
            self._notify_state_change()
            return

        if self._pre_entry_cancel_touched(tick):
            await self._cancel_armed_limit(
                "%s touched before entry target=%.2f entry=%.2f resolution=1s"
                % (
                    self.limit_cancel_on_pre_entry_target_touch,
                    levels.tp1 if self.limit_cancel_on_pre_entry_target_touch == "tp1" else levels.tp2,
                    levels.entry,
                )
            )

    async def _handle_managing_tick(self, tick: Bar) -> None:
        """Manage position exits at 1s resolution.

        Checks TP1/SL/BE/TP2/EOD on each 1-second bar. When TP1 and SL
        both trigger on the same 1s bar, SL wins (pessimistic — matches
        the backtester's finest-tier conflict resolution).
        """
        levels = self._levels
        if levels is None:
            self._state = State.FLAT
            self._request_checkpoint()
            return

        # EOD flat check (highest priority)
        if self._in_flat(tick):
            await self._flatten_position(tick, resolution="1s", reason="tick_time")
            return

        if not self._in_rth(tick.timestamp.time()):
            await self._flatten_position(tick, resolution="1s", reason="outside_rth_tick")
            return

        direction_str = "long" if levels.direction == 1 else "short"

        # Same-tick guard: skip the fill tick itself
        if self._fill_timestamp is not None and tick.timestamp <= self._fill_timestamp:
            return

        is_long = levels.direction == 1

        # --- Pre-TP1 phase ---
        if not self._tp1_hit:
            sl_hit = (is_long and tick.low <= levels.stop) or \
                     (not is_long and tick.high >= levels.stop)
            tp1_touched = (is_long and tick.high >= levels.tp1) or \
                          (not is_long and tick.low <= levels.tp1)

            # Both on same 1s bar — pessimistic: SL wins (matches backtester)
            if sl_hit and tp1_touched:
                self._log_trade(
                    "SL_HIT",
                    "dir=%s stop=%.2f (1s ambiguous, pessimistic) tick_time=%s resolution=1s"
                    % (direction_str, levels.stop, tick.timestamp),
                )
                self._schedule_post_exit_cleanup(
                    reason="sl_hit_1s_ambiguous",
                    delay_s=self._broker_exit_cleanup_delay(1.0),
                )
                self._emit_trade_record("sl", exit_timestamp=tick.timestamp)
                self._set_post_exit_state(tick.timestamp.time(), "sl")
                self._request_checkpoint()
                self._notify_state_change()
                return

            if sl_hit:
                self._log_trade(
                    "SL_HIT",
                    "dir=%s stop=%.2f tick_time=%s resolution=1s"
                    % (direction_str, levels.stop, tick.timestamp),
                )
                self._schedule_post_exit_cleanup(
                    reason="sl_hit_1s",
                    delay_s=self._broker_exit_cleanup_delay(1.0),
                )
                self._emit_trade_record("sl", exit_timestamp=tick.timestamp)
                self._set_post_exit_state(tick.timestamp.time(), "sl")
                self._request_checkpoint()
                self._notify_state_change()
                return

            if self.exit_mode == "single_target":
                target_touched = (is_long and tick.high >= levels.tp2) or \
                                 (not is_long and tick.low <= levels.tp2)
                if target_touched:
                    self._log_trade(
                        "SINGLE_TARGET_HIT",
                        "dir=%s target=%.2f tick_time=%s resolution=1s"
                        % (direction_str, levels.tp2, tick.timestamp),
                    )
                    self._schedule_post_exit_cleanup(
                        reason="single_target_1s",
                        delay_s=self._broker_exit_cleanup_delay(1.0),
                    )
                    self._emit_trade_record("tp2_direct", exit_timestamp=tick.timestamp)
                    self._set_post_exit_state(tick.timestamp.time(), "tp2_direct")
                    self._request_checkpoint()
                    self._notify_state_change()
                    return

            if tp1_touched:
                if levels.is_single_contract:
                    await self._exit_single_contract_at_tp1(
                        exit_timestamp=tick.timestamp,
                        direction_str=direction_str,
                        resolution="1s",
                    )
                    return

                self._tp1_hit = True
                self._runner_stop = levels.be
                self._request_checkpoint()
                self._tp1_bar_count = self._bar_count
                self._sync_position_cap()
                self._log_trade(
                    "TP1_PARTIAL",
                    "dir=%s tp1=%.2f half_qty=%.1f be=%.2f tp2=%.2f tick_time=%s resolution=1s"
                    % (
                        direction_str,
                        levels.tp1,
                        levels.half_qty,
                        levels.be,
                        levels.tp2,
                        tick.timestamp,
                    ),
                )
                if self._should_send:
                    await self.broker.send_tp1_multi(
                        direction=direction_str,
                        total_qty=levels.qty,
                        exit_qty=levels.half_qty,
                        be_price=levels.be,
                        tp2=levels.tp2,
                        ticker=self.broker_ticker,
                    )
                if self._runner_trail_enabled:
                    await self._update_runner_trail_stop(
                        high_price=tick.high,
                        low_price=tick.low,
                        timestamp=tick.timestamp,
                        resolution="1s",
                    )
                    runner_stop_hit, runner_stop = self._runner_stop_hit(tick.high, tick.low)
                    if runner_stop_hit:
                        event_name = self._runner_stop_event_name(runner_stop)
                        self._log_trade(
                            event_name,
                            "dir=%s stop=%.2f tick_time=%s resolution=1s"
                            % (direction_str, runner_stop, tick.timestamp),
                        )
                        self._schedule_post_exit_cleanup(reason="runner_stop_same_tick_1s")
                        self._emit_trade_record(
                            "tp1_be",
                            exit_price=runner_stop,
                            exit_timestamp=tick.timestamp,
                        )
                        self._set_post_exit_state(tick.timestamp.time(), "tp1_be")
                        self._request_checkpoint()
                        self._notify_state_change()
                        return
                self._notify_state_change()
                return

            # Check for direct TP2 (skipping TP1)
            tp2_hit = (is_long and tick.high >= levels.tp2) or \
                      (not is_long and tick.low <= levels.tp2)
            if tp2_hit:
                self._log_trade(
                    "TP2_DIRECT",
                    "dir=%s tp2=%.2f tick_time=%s resolution=1s"
                    % (direction_str, levels.tp2, tick.timestamp),
                )
                self._schedule_post_exit_cleanup(
                    reason="tp2_direct_1s",
                    delay_s=self._broker_exit_cleanup_delay(1.0),
                )
                self._emit_trade_record("tp2_direct", exit_timestamp=tick.timestamp)
                self._set_post_exit_state(tick.timestamp.time(), "tp2_direct")
                self._request_checkpoint()
                self._notify_state_change()
                return

        # --- Post-TP1 phase: check BE and TP2 ---
        else:
            await self._update_runner_trail_stop(
                high_price=tick.high,
                low_price=tick.low,
                timestamp=tick.timestamp,
                resolution="1s",
            )
            be_hit, runner_stop = self._runner_stop_hit(tick.high, tick.low)
            tp2_hit = (is_long and tick.high >= levels.tp2) or \
                      (not is_long and tick.low <= levels.tp2)

            if be_hit:
                event_name = self._runner_stop_event_name(runner_stop)
                self._log_trade(
                    event_name,
                    "dir=%s stop=%.2f tick_time=%s resolution=1s"
                    % (direction_str, runner_stop, tick.timestamp),
                )
                self._schedule_post_exit_cleanup(reason="be_hit_1s")
                self._emit_trade_record(
                    "tp1_be",
                    exit_price=runner_stop,
                    exit_timestamp=tick.timestamp,
                )
                self._set_post_exit_state(tick.timestamp.time(), "tp1_be")
                self._request_checkpoint()
                self._notify_state_change()
                return

            if tp2_hit:
                self._log_trade(
                    "TP2_HIT",
                    "dir=%s tp2=%.2f tick_time=%s resolution=1s"
                    % (direction_str, levels.tp2, tick.timestamp),
                )
                self._schedule_post_exit_cleanup(reason="tp2_hit_1s")
                self._emit_trade_record("tp1_tp2", exit_timestamp=tick.timestamp)
                self._set_post_exit_state(tick.timestamp.time(), "tp1_tp2")
                self._request_checkpoint()
                self._notify_state_change()
                return

    # ------------------------------------------------------------------
    # Public status
    # ------------------------------------------------------------------

    @property
    def state(self) -> State:
        return self._state

    @property
    def is_active(self) -> bool:
        """True if in a state that requires monitoring (not IDLE/FLAT)."""
        return self._state not in (State.IDLE, State.FLAT)

    def status_dict(self) -> dict:
        """Return current state as a dict for logging/debugging."""
        return {
            "config_name": self.config_name,
            "session": self.name,
            "signal_ticker": self._asset_tag.upper(),
            "exec_ticker": self.broker_ticker,
            "exec_root_ticker": self.exec_ticker,
            "signal_contract": self._signal_contract or None,
            "exec_contract": self._exec_contract or None,
            "trade_signal_contract": self._trade_signal_contract or None,
            "trade_exec_contract": self._trade_exec_contract or None,
            "contract_routing_required": self.contract_routing_required,
            "contract_routing_error": self._contract_routing_error or None,
            "state": self._state.value,
            "date": self._current_date,
            "orb_high": self._orb_high if self._orb_high == self._orb_high else None,
            "orb_low": self._orb_low if self._orb_low == self._orb_low else None,
            "orb_open": self._orb_open if math.isfinite(self._orb_open) else None,
            "orb_range": self._orb_range if self._orb_range > 0 else None,
            "daily_atr": self._daily_atr,
            "atr_length": self.atr_length,
            "context_gates": {
                "max_prior_rolling_atr_pct": self.max_prior_rolling_atr_pct,
                "prior_rolling_atr_pct": (
                    self._prior_rolling_atr_pct
                    if math.isfinite(self._prior_rolling_atr_pct)
                    else None
                ),
                "max_orb_range_pct": self.max_orb_range_pct,
                "orb_range_pct": (
                    self._orb_range / self._orb_open * 100.0
                    if math.isfinite(self._orb_open) and self._orb_open > 0.0 and self._orb_range > 0.0
                    else None
                ),
            },
            "levels": {
                "entry": self._levels.entry,
                "stop": self._levels.stop,
                "tp1": self._levels.tp1,
                "tp2": self._levels.tp2,
                "runner_stop": self._runner_stop_price() if self._tp1_hit else None,
                "qty": self._levels.qty,
                "direction": self._levels.direction,
            } if self._levels else None,
            "tp1_hit": self._tp1_hit,
            "exit_type": self._exit_type,
            "r_result": round(self._r_result, 2) if self._r_result is not None else None,
            "risk_usd": self.risk_usd,
            "point_value": self.point_value,
            "commission_per_contract": self.commission_per_contract,
            "exit_mode": self.exit_mode,
            "runner_trail": {
                "mode": self.runner_trail_mode,
                "trigger_r": self.runner_trail_trigger_r,
                "stop_r": self.runner_trail_stop_r,
                "step_r": self.runner_trail_step_r,
                "gap_r": self.runner_trail_gap_r,
                "atr_pct": self.runner_trail_atr_pct,
                "runner_stop": self._runner_stop,
                "trade_daily_atr": self._trade_daily_atr,
            },
            "fill_timestamp": str(self._fill_timestamp) if self._fill_timestamp else None,
            "stop_basis": self.stop_basis,
            "long_only": self.long_only,
            "short_only": self.short_only,
            "paused": self.paused,
            "excluded_dow": self.excluded_dow,
            "fomc_exclusion": self.fomc_exclusion,
            "skip_reason": self._skip_reason,
            "blocking_gate": self._blocking_gate,
            "regime_gate_status": self._regime_gate_status,
            "ath": {
                "enabled": self._ath_gate_enabled,
                "high": self._ath_high if math.isfinite(self._ath_high) else None,
                "last_update": self._ath_last_update or None,
                "last_close": self._ath_last_close if math.isfinite(self._ath_last_close) else None,
                "current_gap_pct": (
                    self._ath_last_gap_pct if math.isfinite(self._ath_last_gap_pct) else None
                ),
                "block_min_pct": self.ath_block_min_pct,
                "block_max_pct": self.ath_block_max_pct,
                "check_count": self._ath_check_count,
                "block_count": self._ath_block_count,
                "pass_count": self._ath_pass_count,
                "last_check": self._ath_last_check,
                "last_block": self._ath_last_block,
            },
        }
