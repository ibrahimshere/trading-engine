from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest

from trader.api import DashboardState, _build_exec_config_meta, _session_info
from trader.engine import State
from trader.gates import (
    _classify_vol,
    blocking_regime_gate_name,
    build_regime_gate,
    build_regime_gates,
    evaluate_regime_gate,
    evaluate_regime_gates,
    format_regime_gate_detail,
    normalize_regime_gate_fields,
    normalize_regime_gates,
    required_daily_history_symbols_for_regime_gates,
    set_daily_history_provider,
)
from trader.lsi_engine import LSIState
from trader.main import (
    LSI_SESSION_CONFIGS,
    SESSION_CONFIGS,
    _checkpoint_shutdown_flat,
    _required_regime_daily_symbols,
    apply_atr_values,
    apply_ath_highs,
    build_engines,
    build_lsi_engines,
    load_exec_configs,
    required_ath_seed_symbols,
    _resolve_orderbook_runtime_config,
)


def _make_daily_history(closes: list[float], *, start: date = date(2025, 1, 1)) -> list[tuple]:
    return [
        (start + timedelta(days=i), close, close + 2.0, close - 2.0, close)
        for i, close in enumerate(closes)
    ]


def test_normalize_regime_gates_accepts_legacy_and_arrays():
    assert normalize_regime_gates("bull_no_low_confidence", None) == ("bull_no_low_confidence",)
    assert normalize_regime_gates(
        None,
        ["block_bull_medium_vol", "block_sideways_medium_vol"],
    ) == ("block_bull_medium_vol", "block_sideways_medium_vol")
    assert normalize_regime_gates(
        "bull_no_low_confidence",
        ["bull_no_low_confidence", "block_full_medium_vol", "none", ""],
    ) == ("bull_no_low_confidence", "block_full_medium_vol")


def test_frozen_vol_threshold_edges_match_backtest_buckets():
    assert _classify_vol(0.1252) == "low_vol"
    assert _classify_vol(0.1252001) == "medium_vol"
    assert _classify_vol(0.2040) == "medium_vol"
    assert _classify_vol(0.2040001) == "high_vol"


def test_required_daily_history_symbols_for_regime_gates_use_nq_calendar():
    assert required_daily_history_symbols_for_regime_gates(()) == ()
    assert required_daily_history_symbols_for_regime_gates(("block_full_medium_vol",)) == ("NQ.FUT",)


def test_build_engines_applies_session_date_overrides():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0, "be_offset_ticks": 0},
        "dates": {
            "half_days": ["20250703"],
            "excluded": ["20241218"],
            "half_day_flat_start": "12:50",
            "half_day_flat_end": "13:00",
        },
        "sessions": {},
    }

    engines, _, _ = build_engines(
        config,
        broker,
        config_name="FAST_V2",
        session_list=["NQ_NY"],
        exec_overrides={
            "NQ_NY": {
                "excluded_dates": ["20260101"],
                "half_days": ["20260119"],
                "half_day_flat_start": "12:40",
                "half_day_flat_end": "12:45",
            }
        },
    )

    engine = engines[0]
    assert engine.excluded_dates == ("20260101",)
    assert engine.half_days == ("20260119",)
    assert engine.half_day_flat_start == "12:40"
    assert engine.half_day_flat_end == "12:45"


def test_build_engines_applies_exit_mode_override():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0, "be_offset_ticks": 0},
        "dates": {"half_days": [], "excluded": []},
        "sessions": {},
    }

    engines, _, _ = build_engines(
        config,
        broker,
        config_name="TEST",
        session_list=["NQ_NY"],
        exec_overrides={"NQ_NY": {"rr": 1.4, "tp1_ratio": 1.0, "exit_mode": "single_target"}},
    )

    engine = engines[0]
    assert engine.exit_mode == "single_target"
    assert engine.tp1_ratio == 1.0


def test_neutral_rolling_gate_profile_builds_context_gates():
    configs = {cfg.name: cfg for cfg in load_exec_configs()}
    profile = configs["NQ_NY_ORB_NEUTRAL_ROLLING_GATE"]

    assert profile.enabled is False
    assert set(profile.session_overrides) == {"NQ_NY"}
    override = profile.session_overrides["NQ_NY"]
    assert override["excluded_dow"] is None
    assert override["max_prior_rolling_atr_pct"] == pytest.approx(1.6228084238855573)
    assert override["max_orb_range_pct"] == pytest.approx(0.4657663656763981)

    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0, "be_offset_ticks": 0},
        "dates": {"half_days": [], "excluded": []},
        "sessions": {},
    }

    engines, symbol_map, atr_lengths = build_engines(
        config,
        broker,
        config_name=profile.name,
        session_list=["NQ_NY"],
        exec_overrides=profile.session_overrides,
    )

    engine = engines[0]
    assert engine.excluded_dow is None
    assert engine.max_prior_rolling_atr_pct == pytest.approx(1.6228084238855573)
    assert engine.max_orb_range_pct == pytest.approx(0.4657663656763981)
    assert symbol_map["NQ.FUT"] == [engine]
    assert atr_lengths["NQ.FUT"] == {14}


def test_alpha_v2_rr2_alias_builds_nq_ny_dry_run_engine():
    configs = {cfg.name: cfg for cfg in load_exec_configs()}
    profile = configs["ALPHA_V2"]

    assert profile.enabled is True
    assert profile.webhooks == []
    assert set(profile.session_overrides) == {"NQ_NY-RR2"}
    override = profile.session_overrides["NQ_NY-RR2"]
    assert override["base_session"] == "NQ_NY"
    assert override["rr"] == 2.0
    assert override["tp1_ratio"] == 1.0
    assert override["exit_mode"] == "single_target"
    assert override["risk_usd"] == 250
    assert override["excluded_dow"] is None
    assert override["max_prior_rolling_atr_pct"] == pytest.approx(1.6228084238855573)
    assert override["max_orb_range_pct"] == pytest.approx(0.4657663656763981)

    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0, "be_offset_ticks": 0},
        "dates": {"half_days": [], "excluded": []},
        "sessions": {},
    }

    engines, symbol_map, atr_lengths = build_engines(
        config,
        broker,
        config_name=profile.name,
        session_list=list(profile.session_overrides),
        exec_overrides=profile.session_overrides,
    )

    assert len(engines) == 1
    engine = engines[0]
    assert engine.name == "NQ_NY-RR2"
    assert engine.config_name == "ALPHA_V2"
    assert engine.exec_ticker == "MNQ"
    assert engine.exit_mode == "single_target"
    assert engine.tp1_ratio == 1.0
    assert engine.risk_usd == 250
    assert engine.max_single_risk_usd == 375
    assert engine.max_prior_rolling_atr_pct == pytest.approx(1.6228084238855573)
    assert engine.max_orb_range_pct == pytest.approx(0.4657663656763981)
    assert symbol_map["NQ.FUT"] == [engine]
    assert atr_lengths["NQ.FUT"] == {14}


def test_build_lsi_engines_applies_session_date_overrides():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0},
        "dates": {
            "half_days": ["20250703"],
            "excluded": ["20241218"],
            "half_day_flat_start": "12:50",
            "half_day_flat_end": "13:00",
        },
    }

    symbol_map: dict[str, list] = {}
    atr_lengths: dict[str, int] = {}
    engines = build_lsi_engines(
        config,
        broker,
        symbol_map,
        atr_lengths,
        config_name="FAST_V2",
        lsi_list=["NQ_Asia_LSI"],
        lsi_overrides={
            "NQ_Asia_LSI": {
                "excluded_dates": ["20260102"],
                "half_days": ["20260119"],
                "half_day_flat_start": "12:35",
                "half_day_flat_end": "12:40",
            }
        },
    )

    engine = engines[0]
    assert engine.excluded_dates == ("20260102",)
    assert engine.half_days == ("20260119",)
    assert engine._half_day_flat_start_t.hour == 12
    assert engine._half_day_flat_start_t.minute == 35
    assert engine._half_day_flat_end_t.hour == 12
    assert engine._half_day_flat_end_t.minute == 40


def test_build_lsi_engines_applies_exit_mode_override():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0},
        "dates": {"half_days": [], "excluded": []},
    }

    symbol_map: dict[str, list] = {}
    atr_lengths: dict[str, int] = {}
    engines = build_lsi_engines(
        config,
        broker,
        symbol_map,
        atr_lengths,
        config_name="TEST",
        lsi_list=["NQ_Asia_LSI"],
        lsi_overrides={"NQ_Asia_LSI": {"rr": 1.4, "tp1_ratio": 1.0, "exit_mode": "single_target"}},
    )

    engine = engines[0]
    assert engine.exit_mode == "single_target"
    assert engine.tp1_ratio == 1.0


def test_orderbook_runtime_config_defaults_to_zero_cost():
    resolved = _resolve_orderbook_runtime_config({})

    assert resolved["enable_mbp10"] is False
    assert resolved["mbp10_cost_ack"] is False
    assert resolved["dynamic_sizing_enabled"] is False
    assert resolved["dynamic_sizing_shadow_enabled"] is False
    assert resolved["provider_enabled"] is False


def test_orderbook_runtime_config_requires_cost_ack_for_mbp10():
    with pytest.raises(ValueError, match="mbp10_cost_ack"):
        _resolve_orderbook_runtime_config({"orderbook": {"enable_mbp10": True}})


def test_orderbook_runtime_config_allows_acknowledged_shadow_mode():
    resolved = _resolve_orderbook_runtime_config({
        "orderbook": {
            "enable_mbp10": True,
            "mbp10_cost_ack": True,
            "dynamic_sizing_shadow_enabled": True,
            "dynamic_sizing_enabled": True,
            "dynamic_sizing_sessions": "NQ_NY_LSI",
        }
    })

    assert resolved["enable_mbp10"] is True
    assert resolved["mbp10_cost_ack"] is True
    assert resolved["dynamic_sizing_shadow_enabled"] is True
    assert resolved["dynamic_sizing_enabled"] is False
    assert resolved["provider_enabled"] is True
    assert resolved["dynamic_sizing_sessions"] == {"NQ_NY_LSI"}


def test_dashboard_status_includes_orderbook_status():
    state = DashboardState(orderbook_status={"enable_mbp10": False, "cache": None})

    status = state._build_status()

    assert status["orderbook"] == {"enable_mbp10": False, "cache": None}


def test_build_lsi_engines_applies_legacy_lsi_variant_override():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0},
        "dates": {
            "half_days": ["20250703"],
            "excluded": [],
            "half_day_flat_start": "12:50",
            "half_day_flat_end": "13:00",
        },
    }

    symbol_map: dict[str, list] = {}
    atr_lengths: dict[str, int] = {}
    engines = build_lsi_engines(
        config,
        broker,
        symbol_map,
        atr_lengths,
        config_name="LEGACY_TEST",
        lsi_list=["NQ_Asia_LSI"],
        lsi_overrides={"NQ_Asia_LSI": {"lsi_variant": "legacy-LSI"}},
    )

    assert engines[0].lsi_variant == "legacy-LSI"


def test_build_lsi_engines_applies_htf_lsi_overrides():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0},
        "dates": {
            "half_days": ["20250703"],
            "excluded": [],
            "half_day_flat_start": "12:50",
            "half_day_flat_end": "13:00",
        },
    }

    symbol_map: dict[str, list] = {}
    atr_lengths: dict[str, int] = {}
    engines = build_lsi_engines(
        config,
        broker,
        symbol_map,
        atr_lengths,
        config_name="HTF_TEST",
        lsi_list=["NQ_NY_LSI"],
        lsi_overrides={
            "NQ_NY_LSI": {
                "sweep_start": "08:30",
                "sweep_end": "15:00",
                "entry_start": "08:30",
                "entry_end": "15:00",
                "lsi_variant": "htf-LSI",
                "htf_level_tf_minutes": 60,
                "htf_n_left": 3,
                "htf_trade_max_per_session": 2,
                "max_fvg_to_inversion_bars": 24,
                "lsi_stale_breach_consumes_pivot": False,
            }
        },
    )

    engine = engines[0]
    assert engine.lsi_variant == "htf-LSI"
    assert engine.sweep_start == "08:30"
    assert engine.sweep_end == "15:00"
    assert engine.htf_level_tf_minutes == 60
    assert engine.htf_n_left == 3
    assert engine.htf_trade_max_per_session == 2
    assert engine.max_fvg_to_inversion_bars == 24
    assert engine.lsi_stale_breach_consumes_pivot is False


def test_build_lsi_engines_supports_pure_1m_cisd_survivor():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0},
        "dates": {"half_days": [], "excluded": []},
    }
    symbol_map: dict[str, list] = {}
    atr_lengths: dict[str, set[int]] = {}

    engines = build_lsi_engines(
        config,
        broker,
        symbol_map,
        atr_lengths,
        config_name="PURE_TEST",
        lsi_list=["NQ_NY_LSI_PURE_1M"],
    )

    assert len(engines) == 1
    engine = engines[0]
    assert engine.name == "NQ_NY_LSI_PURE_1M"
    assert engine.entry_end == "12:00"
    assert engine.sweep_start == "09:30"
    assert engine.sweep_end == "15:30"
    assert engine.lsi_confirmation_mode == "cisd"
    assert engine.lsi_entry_mode == "level_limit"
    assert engine.lsi_stop_mode == "atr_pct"
    assert engine.stop_atr_pct == pytest.approx(15.0)
    assert engine.base_bar_minutes == 1
    assert engine.lsi_reset_swing_window_on_new_day is False
    assert engine.cisd_min_leg_bars == 2
    assert engine.cisd_min_leg_atr_pct == pytest.approx(7.5)
    assert engine.cisd_max_leg_bars == 300
    assert atr_lengths["NQ.FUT"] == {10}


def test_build_exec_config_meta_reads_disk_configs(monkeypatch):
    class FakeWebhook:
        def __init__(self, url: str, label: str):
            self.url = url
            self.label = label
            self.paused = False
            self.multiplier = 1.0

    class FakeConfig:
        def __init__(self):
            self.name = "FAST_V2"
            self.enabled = True
            self.max_open_contracts = 20
            self.webhooks = [FakeWebhook("https://example.test/hook", "Account 1")]
            self.session_overrides = {"NQ_NY": {}}
            self.lsi_session_overrides = {"NQ_NY_LSI": {}}

    monkeypatch.setattr(
        "trader.main.load_exec_configs",
        lambda config=None, **_kwargs: [FakeConfig()],
    )

    state = DashboardState(
        config={},
        exec_configs={
            "FAST_V2": {
                "webhooks": [
                    {
                        "url": "https://live.example/hook",
                        "label": "Account 1",
                        "paused": True,
                        "multiplier": 2.0,
                    }
                ]
            }
        },
    )

    meta = _build_exec_config_meta(state)
    assert list(meta) == ["FAST_V2"]
    assert meta["FAST_V2"]["max_open_contracts"] == 20
    assert meta["FAST_V2"]["sessions"] == ["NQ_NY"]
    assert meta["FAST_V2"]["lsi_sessions"] == ["NQ_NY_LSI"]
    assert meta["FAST_V2"]["webhooks"][0]["paused"] is True
    assert meta["FAST_V2"]["webhooks"][0]["multiplier"] == 2.0


def test_build_engines_symbol_map():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0, "be_offset_ticks": 0},
        "dates": {
            "half_days": ["20250703"],
            "excluded": [],
            "half_day_flat_start": "12:50",
            "half_day_flat_end": "13:00",
        },
        "sessions": {},
    }
    _engines, sym_map, _atr_lens = build_engines(
        config,
        broker,
        config_name="FAST",
        session_list=["NQ_NY", "ES_NY"],
        exec_overrides={},
    )
    assert "NQ.FUT" in sym_map
    assert "ES.FUT" in sym_map
    assert _engines[0].atr_length == 12
    assert _atr_lens["NQ.FUT"] == {12}
    assert _atr_lens["ES.FUT"] == {7}


def test_build_engines_respects_long_only_override():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0, "be_offset_ticks": 0},
        "dates": {
            "half_days": ["20250703"],
            "excluded": [],
            "half_day_flat_start": "12:50",
            "half_day_flat_end": "13:00",
        },
        "sessions": {},
    }

    engines, _, _ = build_engines(
        config,
        broker,
        config_name="FAST_V2",
        session_list=["NQ_NY"],
        exec_overrides={"NQ_NY": {"long_only": False}},
    )

    assert engines[0].long_only is False


def test_build_engines_applies_ath_gate_overrides():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0, "be_offset_ticks": 0},
        "dates": {
            "half_days": ["20250703"],
            "excluded": [],
            "half_day_flat_start": "12:50",
            "half_day_flat_end": "13:00",
        },
        "sessions": {},
    }

    engines, _, _ = build_engines(
        config,
        broker,
        config_name="FAST_V2",
        session_list=["ES_NY"],
        exec_overrides={"ES_NY": {"ath_block_min_pct": 0.5, "ath_block_max_pct": 1.0}},
    )

    assert engines[0].ath_block_min_pct == 0.5
    assert engines[0].ath_block_max_pct == 1.0


def test_es_ny_ath_gate_session_config_tracks_es_ny_with_gate_enabled():
    base = SESSION_CONFIGS["ES_NY"]
    ath = SESSION_CONFIGS["ES_NY_ATH_GATE"]

    for key, value in base.items():
        if key.startswith("ath_block_"):
            continue
        assert ath[key] == value
    assert ath["ath_block_min_pct"] == 0.5
    assert ath["ath_block_max_pct"] == 0.75


def test_required_ath_seed_symbols_only_includes_enabled_ath_gates():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0, "be_offset_ticks": 0},
        "dates": {
            "half_days": ["20250703"],
            "excluded": [],
            "half_day_flat_start": "12:50",
            "half_day_flat_end": "13:00",
        },
        "sessions": {},
    }

    _engines, sym_map, _ = build_engines(
        config,
        broker,
        config_name="ATH_TEST",
        session_list=["NQ_NY", "ES_NY"],
        exec_overrides={"ES_NY": {"ath_block_min_pct": 0.5, "ath_block_max_pct": 0.75}},
    )

    assert required_ath_seed_symbols(sym_map) == ["ES.FUT"]


def test_apply_ath_highs_seeds_gated_engines_without_lowering_existing_high():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0, "be_offset_ticks": 0},
        "dates": {
            "half_days": ["20250703"],
            "excluded": [],
            "half_day_flat_start": "12:50",
            "half_day_flat_end": "13:00",
        },
        "sessions": {},
    }

    engines, sym_map, _ = build_engines(
        config,
        broker,
        config_name="ATH_TEST",
        session_list=["ES_NY"],
        exec_overrides={"ES_NY": {"ath_block_min_pct": 0.5, "ath_block_max_pct": 0.75}},
    )
    engine = engines[0]

    assert apply_ath_highs(sym_map, {"ES.FUT": 5200.0}) == {"ES.FUT": 1}
    assert engine._ath_high == 5200.0
    assert apply_ath_highs(sym_map, {"ES.FUT": 5000.0}) == {}
    assert engine._ath_high == 5200.0
    assert apply_ath_highs(sym_map, {"ES.FUT": 5300.0}) == {"ES.FUT": 1}
    assert engine._ath_high == 5300.0


def test_build_engines_normalizes_multi_regime_gates():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0, "be_offset_ticks": 0},
        "dates": {
            "half_days": ["20250703"],
            "excluded": [],
            "half_day_flat_start": "12:50",
            "half_day_flat_end": "13:00",
        },
        "sessions": {},
    }

    engines, _, _ = build_engines(
        config,
        broker,
        config_name="FAST_V2",
        session_list=["NQ_NY"],
        exec_overrides={
            "NQ_NY": {
                "regime_gate": "bull_no_low_confidence",
                "regime_gates": ["bull_no_low_confidence", "block_full_medium_vol"],
            }
        },
    )

    engine = engines[0]
    assert engine.regime_gate is None
    assert engine.regime_gates == ("bull_no_low_confidence", "block_full_medium_vol")
    assert [name for name, _check in engine.regime_gate_checks] == list(engine.regime_gates)


def test_build_lsi_engines_normalizes_multi_regime_gates():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0},
        "dates": {
            "half_days": ["20250703"],
            "excluded": ["20241218"],
            "half_day_flat_start": "12:50",
            "half_day_flat_end": "13:00",
        },
    }

    symbol_map: dict[str, list] = {}
    atr_lengths: dict[str, int] = {}
    engines = build_lsi_engines(
        config,
        broker,
        symbol_map,
        atr_lengths,
        config_name="FAST_V2",
        lsi_list=["NQ_Asia_LSI"],
        lsi_overrides={
            "NQ_Asia_LSI": {
                "regime_gate": "bull_no_low_confidence",
                "regime_gates": ["block_full_medium_vol"],
            }
        },
    )

    engine = engines[0]
    assert engine.regime_gate is None
    assert engine.regime_gates == ("bull_no_low_confidence", "block_full_medium_vol")
    assert [name for name, _check in engine.regime_gate_checks] == list(engine.regime_gates)


def test_required_regime_daily_symbols_collects_aux_history_from_engines():
    engine_a = MagicMock()
    engine_a.regime_gates = ()
    engine_b = MagicMock()
    engine_b.regime_gates = ("block_full_medium_vol",)
    engine_c = MagicMock()
    engine_c.regime_gates = ("bull_no_low_confidence",)

    assert _required_regime_daily_symbols([engine_a, engine_b, engine_c]) == ["NQ.FUT"]


def test_session_info_exposes_regime_gates_for_continuation_and_lsi():
    class ContEngine:
        pass

    class LsiEngine:
        pass

    cont_engine = ContEngine()
    cont_engine.config_name = "FAST"
    cont_engine.orb_start = "09:30"
    cont_engine.orb_end = "09:45"
    cont_engine.entry_start = "09:45"
    cont_engine.entry_end = "12:00"
    cont_engine.flat_start = "15:50"
    cont_engine.flat_end = "16:00"
    cont_engine.atr_length = 14
    cont_engine.stop_atr_pct = 8.0
    cont_engine.stop_basis = "atr"
    cont_engine.stop_orb_pct = 0.0
    cont_engine.min_gap_atr_pct = 2.0
    cont_engine.max_gap_atr_pct = 0.0
    cont_engine.gap_filter_basis = "atr"
    cont_engine.min_gap_orb_pct = 0.0
    cont_engine.rr = 2.0
    cont_engine.tp1_ratio = 0.5
    cont_engine.risk_usd = 250.0
    cont_engine.point_value = 2.0
    cont_engine.min_qty = 1.0
    cont_engine.max_single_risk_usd = 500.0
    cont_engine.qty_step = 1.0
    cont_engine.be_offset_ticks = 0
    cont_engine.min_tick = 0.25
    cont_engine.long_only = True
    cont_engine.icf_enabled = False
    cont_engine.excluded_dow = None
    cont_engine.fomc_exclusion = False
    cont_engine.min_stop_pts = 0.0
    cont_engine.min_tp1_pts = 0.0
    cont_engine.exec_ticker = "MNQ"
    cont_engine.regime_gates = ("bull_no_low_confidence", "block_full_medium_vol")
    cont_engine.structure_gate = None

    lsi_engine = LsiEngine()
    lsi_engine.config_name = "FAST"
    lsi_engine.sweep_start = "09:45"
    lsi_engine.sweep_end = "12:00"
    lsi_engine.entry_start = "09:45"
    lsi_engine.entry_end = "12:00"
    lsi_engine.flat_start = "15:50"
    lsi_engine.flat_end = "16:00"
    lsi_engine.atr_length = 14
    lsi_engine.rr = 2.0
    lsi_engine.tp1_ratio = 0.5
    lsi_engine.min_gap_atr_pct = 2.0
    lsi_engine.min_stop_points = 0.0
    lsi_engine.fvg_window_left = 20
    lsi_engine.fvg_window_right = 5
    lsi_engine.qty_multiplier = 1.0
    lsi_engine.lsi_variant = "legacy-LSI"
    lsi_engine.risk_usd = 250.0
    lsi_engine.point_value = 2.0
    lsi_engine.min_qty = 1.0
    lsi_engine.max_single_risk_usd = 500.0
    lsi_engine.qty_step = 1.0
    lsi_engine.min_tick = 0.25
    lsi_engine.long_only = True
    lsi_engine.excluded_dow = None
    lsi_engine.exec_ticker = "MNQ"
    lsi_engine.regime_gates = ("block_full_medium_vol",)
    lsi_engine.qty_multiplier = 1.0
    lsi_engine.lsi_entry_mode = "close"
    lsi_engine.htf_level_tf_minutes = 60
    lsi_engine.htf_n_left = 5
    lsi_engine.htf_trade_max_per_session = 1
    lsi_engine.max_fvg_to_inversion_bars = 0

    cont_info = _session_info(cont_engine)
    lsi_info = _session_info(lsi_engine)

    assert cont_info["regime_gate"] is None
    assert cont_info["regime_gates"] == ["bull_no_low_confidence", "block_full_medium_vol"]
    assert lsi_info["regime_gate"] == "block_full_medium_vol"
    assert lsi_info["regime_gates"] == ["block_full_medium_vol"]
    assert lsi_info["lsi_variant"] == "legacy-LSI"
    assert lsi_info["sweep_start"] == "09:45"
    assert lsi_info["htf_level_tf_minutes"] == 60


def test_apply_atr_values_updates_engines():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0, "be_offset_ticks": 0},
        "dates": {
            "half_days": ["20250703"],
            "excluded": [],
            "half_day_flat_start": "12:50",
            "half_day_flat_end": "13:00",
        },
        "sessions": {},
    }
    engines, sym_map, _atr_lens = build_engines(
        config,
        broker,
        config_name="FAST",
        session_list=["NQ_NY"],
        exec_overrides={},
    )
    apply_atr_values(sym_map, {"NQ.FUT": {12: 123.0}})
    assert engines[0]._daily_atr == 123.0


def test_apply_atr_values_uses_engine_specific_length():
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0, "be_offset_ticks": 0},
        "dates": {
            "half_days": ["20250703"],
            "excluded": [],
            "half_day_flat_start": "12:50",
            "half_day_flat_end": "13:00",
        },
        "sessions": {},
    }
    cont_engines, sym_map, atr_lens = build_engines(
        config,
        broker,
        config_name="FAST",
        session_list=["NQ_NY"],
        exec_overrides={},
    )
    lsi_engines = build_lsi_engines(
        config,
        broker,
        sym_map,
        atr_lens,
        config_name="FAST_V2",
        lsi_list=["NQ_Asia_LSI"],
        lsi_overrides={"NQ_Asia_LSI": {"atr_length": 40}},
    )
    apply_atr_values(sym_map, {"NQ.FUT": {12: 123.0, 40: 456.0}})
    assert cont_engines[0]._daily_atr == 123.0
    assert lsi_engines[0]._daily_atr == 456.0


def test_fast_and_fast_v2_exec_configs_load_original_baseline_portfolios():
    configs = {cfg.name: cfg for cfg in load_exec_configs()}

    fast = configs["FAST"]
    fast_v2 = configs["FAST_V2"]

    assert set(fast.session_overrides) == {
        "NQ_NY",
        "NQ_Asia",
        "GC_NY",
        "ES_NY",
        "ES_Asia",
        "NQ_LDN",
    }
    assert set(fast.lsi_session_overrides) == {"NQ_Asia_LSI", "NQ_NY_LSI"}
    assert all(override["risk_usd"] == 400 for override in fast.session_overrides.values())
    assert all(override["risk_usd"] == 400 for override in fast.lsi_session_overrides.values())
    assert fast.lsi_session_overrides["NQ_NY_LSI"]["tp1_ratio"] == 0.34
    assert fast.lsi_session_overrides["NQ_NY_LSI"]["qty_multiplier"] == 1.0

    assert set(fast_v2.session_overrides) == {"NQ_NY", "NQ_Asia", "ES_Asia"}
    assert set(fast_v2.lsi_session_overrides) == {"NQ_Asia_LSI", "NQ_NY_LSI"}
    assert fast_v2.session_overrides["NQ_NY"]["tp1_ratio"] == 0.4
    assert fast_v2.session_overrides["ES_Asia"]["tp1_ratio"] == 0.58
    assert fast_v2.lsi_session_overrides["NQ_NY_LSI"]["tp1_ratio"] == 0.4


def test_recommended_exec_configs_match_phase_one_subset_portfolios():
    configs = {cfg.name: cfg for cfg in load_exec_configs()}

    fast = configs["FAST_V1.1"]
    fast_v2 = configs["FAST_V2.1"]

    assert set(fast.session_overrides) == {
        "NQ_Asia",
        "ES_NY",
        "ES_Asia",
    }
    assert set(fast.lsi_session_overrides) == {"NQ_Asia_LSI", "NQ_NY_LSI"}
    assert all(override["risk_usd"] == 400 for override in fast.session_overrides.values())
    assert all(override["risk_usd"] == 400 for override in fast.lsi_session_overrides.values())
    assert fast.lsi_session_overrides["NQ_NY_LSI"]["tp1_ratio"] == 0.34

    assert set(fast_v2.session_overrides) == {"NQ_Asia"}
    assert set(fast_v2.lsi_session_overrides) == {"NQ_Asia_LSI", "NQ_NY_LSI"}
    assert all(override["risk_usd"] == 400 for override in fast_v2.session_overrides.values())
    assert all(override["risk_usd"] == 400 for override in fast_v2.lsi_session_overrides.values())
    assert fast_v2.webhook_url == ""


def test_alpha_v1_c_is_disabled_conservative_clone_without_tracked_webhook():
    configs = {cfg.name: cfg for cfg in load_exec_configs()}

    aggressive = configs["ALPHA_V1-A"]
    conservative = configs["ALPHA_V1-C"]

    def _without_sizing(overrides: dict[str, dict]) -> dict[str, dict]:
        return {
            name: {
                key: value
                for key, value in values.items()
                if key not in {"risk_usd", "max_single_risk_usd"}
            }
            for name, values in overrides.items()
        }

    assert aggressive.enabled is True
    assert conservative.enabled is False
    assert aggressive.max_open_contracts == conservative.max_open_contracts
    assert aggressive.webhooks == []
    assert conservative.webhooks == []
    assert _without_sizing(aggressive.session_overrides) == _without_sizing(conservative.session_overrides)
    assert _without_sizing(aggressive.lsi_session_overrides) == _without_sizing(conservative.lsi_session_overrides)
    assert aggressive.session_overrides["NQ_NY"]["risk_usd"] == 400
    assert aggressive.session_overrides["NQ_NY"]["max_single_risk_usd"] == 600
    assert aggressive.session_overrides["NQ_Asia"]["risk_usd"] == 250
    assert aggressive.session_overrides["NQ_Asia"]["max_single_risk_usd"] == 375
    assert aggressive.session_overrides["ES_Asia"]["risk_usd"] == 250
    assert aggressive.session_overrides["ES_Asia"]["max_single_risk_usd"] == 375
    assert aggressive.session_overrides["ES_NY"]["risk_usd"] == 400
    assert aggressive.session_overrides["ES_NY"]["max_single_risk_usd"] == 600
    assert aggressive.lsi_session_overrides["NQ_NY_LSI"]["risk_usd"] == 400
    assert aggressive.lsi_session_overrides["NQ_NY_LSI"]["max_single_risk_usd"] == 600
    assert set(conservative.session_overrides) == {"NQ_NY", "NQ_Asia", "ES_Asia", "ES_NY"}
    assert set(conservative.lsi_session_overrides) == {"NQ_NY_LSI"}
    assert conservative.session_overrides["NQ_NY"]["risk_usd"] == 150
    assert conservative.session_overrides["NQ_Asia"]["risk_usd"] == 150
    assert conservative.session_overrides["ES_Asia"]["risk_usd"] == 200
    assert conservative.session_overrides["ES_NY"]["risk_usd"] == 200
    assert conservative.lsi_session_overrides["NQ_NY_LSI"]["risk_usd"] == 150


def test_alpha_v1_es_ny_ath_shadow_is_dry_run_gate_profile():
    configs = {cfg.name: cfg for cfg in load_exec_configs()}

    shadow = configs["ALPHA_V1-ES-NY-ATH-SHADOW"]

    assert shadow.enabled is True
    assert shadow.webhooks == []
    assert set(shadow.session_overrides) == {"ES_NY"}
    assert shadow.lsi_session_overrides == {}
    assert shadow.session_overrides["ES_NY"]["ath_block_min_pct"] == 0.5
    assert shadow.session_overrides["ES_NY"]["ath_block_max_pct"] == 0.75
    assert shadow.session_overrides["ES_NY"]["risk_usd"] == 400


def test_testing_exec_config_includes_hunter_orb_dry_run_leg():
    configs = {cfg.name: cfg for cfg in load_exec_configs()}

    testing = configs["TESTING"]

    assert testing.webhook_url == ""
    assert "H_ORB" in testing.session_overrides
    assert testing.session_overrides["H_ORB"]["risk_usd"] == 350
    assert testing.session_overrides["H_ORB"]["max_contracts"] == 20
    assert "H_ORB_SAFE" in testing.session_overrides
    assert testing.session_overrides["H_ORB_SAFE"]["risk_usd"] == 350
    assert testing.session_overrides["H_ORB_SAFE"]["max_contracts"] == 20
    assert "H_ORB_ABLATED" in testing.session_overrides
    assert testing.session_overrides["H_ORB_ABLATED"]["risk_usd"] == 350
    assert testing.session_overrides["H_ORB_ABLATED"]["entry_end"] == "13:05"
    assert testing.session_overrides["H_ORB_ABLATED"]["ema15_enabled"] is False
    assert testing.session_overrides["H_ORB_ABLATED"]["body_min_pct"] == 0.0
    assert testing.session_overrides["H_ORB_ABLATED"]["rejection_wick_max_pct"] == 20.0
    assert testing.session_overrides["H_ORB_ABLATED"]["reentry_policy"] == "all_nonoverlap"
    assert testing.session_overrides["H_ORB_ABLATED"]["reduced_target_rr"] == 2.0
    assert "ES_NY_ATH_GATE" in testing.session_overrides
    assert testing.session_overrides["ES_NY_ATH_GATE"]["risk_usd"] == 400
    assert testing.session_overrides["ES_NY_ATH_GATE"]["max_single_risk_usd"] == 400
    assert testing.session_overrides["ES_NY_ATH_GATE"]["ath_block_min_pct"] == 0.5
    assert testing.session_overrides["ES_NY_ATH_GATE"]["ath_block_max_pct"] == 0.75


def test_testing_exec_config_includes_goldx_dry_run_legs():
    configs = {cfg.name: cfg for cfg in load_exec_configs()}

    testing = configs["TESTING"]

    assert testing.webhook_url == ""
    assert "GOLD_X" in testing.session_overrides
    assert testing.session_overrides["GOLD_X"]["goldx_mode"] == "both"
    assert testing.session_overrides["GOLD_X"]["goldx_classic_risk_usd"] == 400
    assert testing.session_overrides["GOLD_X"]["goldx_fvg_risk_usd"] == 300
    assert testing.session_overrides["GOLD_X"]["goldx_enable_fvg_ut_filter"] is True
    assert "GOLD_X_SAFE" in testing.session_overrides
    assert testing.session_overrides["GOLD_X_SAFE"]["goldx_mode"] == "fvg_only"
    assert testing.session_overrides["GOLD_X_SAFE"]["goldx_fvg_risk_usd"] == 300
    assert testing.session_overrides["GOLD_X_SAFE"]["goldx_enable_fvg_ut_filter"] is True
    assert "GOLD_X_ABLATED" in testing.session_overrides
    assert testing.session_overrides["GOLD_X_ABLATED"]["goldx_mode"] == "both"
    assert testing.session_overrides["GOLD_X_ABLATED"]["goldx_enable_fvg_ut_filter"] is False


def test_hot_regime_v1_exec_config_is_dry_run_hot_candidate_portfolio():
    configs = {cfg.name: cfg for cfg in load_exec_configs()}

    hot = configs["HOT_REGIME_V1"]

    assert hot.enabled is True
    assert hot.webhook_url == ""
    assert hot.webhooks == []
    assert set(hot.session_overrides) == {
        "NQ_NY",
        "NQ_Asia",
        "ES_NY",
        "ES_Asia",
        "GC_NY",
        "GC_Asia",
    }
    assert set(hot.lsi_session_overrides) == {
        "NQ_NY_LSI",
        "ES_NY_LSI",
        "GC_NY_LSI",
    }

    assert hot.session_overrides["NQ_NY"]["rr"] == 6.0
    assert hot.session_overrides["NQ_NY"]["entry_end"] == "11:30"
    assert hot.session_overrides["NQ_NY"]["gap_filter_basis"] == "orb"
    assert hot.session_overrides["NQ_NY"]["orb_trade_max_per_session"] == 2
    assert hot.session_overrides["NQ_NY"]["continuation_fvg_selection"] == "extreme"
    assert hot.session_overrides["NQ_Asia"]["regime_gates"] == [
        "block_bear_medium_vol",
        "block_bear_high_vol",
    ]
    assert hot.session_overrides["ES_NY"]["limit_cancel_on_pre_entry_target_touch"] == "tp1"
    assert hot.session_overrides["GC_Asia"]["wide_stop_target_rr"] == 1.0
    assert hot.session_overrides["ES_Asia"]["regime_gates"] == ["block_sideways_high_vol"]
    assert hot.session_overrides["GC_NY"]["rr"] == 12.0
    assert hot.lsi_session_overrides["ES_NY_LSI"]["regime_gates"] == ["block_full_high_vol"]
    assert hot.lsi_session_overrides["ES_NY_LSI"]["lsi_stop_mode"] == "struct_75pct"
    assert hot.lsi_session_overrides["GC_NY_LSI"]["lsi_entry_mode"] == "timed_hybrid"
    assert hot.lsi_session_overrides["GC_NY_LSI"]["lsi_close_on_sweep_to_inversion_minutes"] == 60
    assert hot.lsi_session_overrides["GC_NY_LSI"]["lsi_n_left"] == 10


def test_hot_regime_v1_builds_all_orb_and_lsi_engines():
    configs = {cfg.name: cfg for cfg in load_exec_configs()}
    hot = configs["HOT_REGIME_V1"]
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0, "be_offset_ticks": 0},
        "dates": {"half_days": [], "excluded": []},
        "sessions": {},
    }

    orb_engines, symbol_map, atr_lengths = build_engines(
        config,
        broker,
        config_name=hot.name,
        session_list=list(hot.session_overrides),
        exec_overrides=hot.session_overrides,
    )
    lsi_engines = build_lsi_engines(
        config,
        broker,
        symbol_map,
        atr_lengths,
        config_name=hot.name,
        lsi_list=list(hot.lsi_session_overrides),
        lsi_overrides=hot.lsi_session_overrides,
    )

    assert {engine.name for engine in orb_engines} == set(hot.session_overrides)
    assert {engine.name for engine in lsi_engines} == set(hot.lsi_session_overrides)
    assert LSI_SESSION_CONFIGS["ES_NY_LSI"]["instrument"] == "ES"
    assert LSI_SESSION_CONFIGS["GC_NY_LSI"]["instrument"] == "GC"
    by_name = {engine.name: engine for engine in lsi_engines}
    assert by_name["ES_NY_LSI"].exec_ticker == "MES"
    assert by_name["GC_NY_LSI"].exec_ticker == "MGC"
    assert by_name["ES_NY_LSI"].long_only is False
    assert by_name["GC_NY_LSI"].long_only is False
    assert by_name["ES_NY_LSI"].lsi_stop_mode == "struct_75pct"
    assert by_name["GC_NY_LSI"].lsi_entry_mode == "timed_hybrid"


def test_hunter_orb_safe_defaults_match_10y_safe_branch():
    config = SESSION_CONFIGS["H_ORB_SAFE"]

    assert config["engine_type"] == "hunter_orb"
    assert config["entry_end"] == "11:00"
    assert config["excluded_dow"] is None
    assert config["regime_gates"] == [
        "block_bull_high_vol",
        "block_bear_high_vol",
        "block_bear_medium_vol",
    ]
    assert config["rejection_wick_max_pct"] == 100.0
    assert config["ema15_length"] == 14
    assert config["ema15_tolerance_points"] == 0.0
    assert config["ema15_max_distance"] is None
    assert config["reentry_policy"] == "legacy_one_reentry_after_loss"
    assert config["allow_same_bar_win_reentry"] is False
    assert config["reentry_max_extension_pct"] is None
    assert config["enable_fast_reentry_exhaustion_filter"] is False
    assert config["reduced_target_rr"] == 1.0


def test_goldx_safe_and_ablated_defaults_match_ablation_branches():
    safe = SESSION_CONFIGS["GOLD_X_SAFE"]
    ablated = SESSION_CONFIGS["GOLD_X_ABLATED"]

    assert safe["engine_type"] == "gold_x"
    assert safe["instrument"] == "GC"
    assert safe["exec_ticker"] == "MGC"
    assert safe["goldx_mode"] == "fvg_only"
    assert safe["goldx_fvg_risk_usd"] == 300
    assert safe["goldx_enable_fvg_ut_filter"] is True
    assert safe["goldx_fvg_min_size_points"] == 9.0
    assert safe["goldx_fvg_max_orb_distance_points"] == 30.0

    assert ablated["engine_type"] == "gold_x"
    assert ablated["goldx_mode"] == "both"
    assert ablated["goldx_classic_risk_usd"] == 400
    assert ablated["goldx_fvg_risk_usd"] == 300
    assert ablated["goldx_enable_fvg_ut_filter"] is False


def test_goldx_variants_build_as_goldx_engines():
    from trader.goldx_engine import GoldXEngine

    configs = {cfg.name: cfg for cfg in load_exec_configs()}
    testing = configs["TESTING"]
    broker = MagicMock()
    config = {
        "risk": {"risk_usd": 250, "min_qty": 1.0, "qty_step": 1.0, "be_offset_ticks": 0},
        "dates": {"half_days": [], "excluded": []},
        "sessions": {},
    }

    engines, symbol_map, atr_lengths = build_engines(
        config,
        broker,
        config_name=testing.name,
        session_list=["GOLD_X", "GOLD_X_SAFE", "GOLD_X_ABLATED"],
        exec_overrides=testing.session_overrides,
    )

    assert {engine.name for engine in engines} == {"GOLD_X", "GOLD_X_SAFE", "GOLD_X_ABLATED"}
    assert all(isinstance(engine, GoldXEngine) for engine in engines)
    by_name = {engine.name: engine for engine in engines}
    assert by_name["GOLD_X"].exec_ticker == "MGC"
    assert by_name["GOLD_X_SAFE"].goldx_mode == "fvg_only"
    assert by_name["GOLD_X_ABLATED"].goldx_enable_fvg_ut_filter is False
    assert "GC.FUT" in symbol_map
    assert 40 in atr_lengths["GC.FUT"]


def test_checkpoint_shutdown_flat_marks_orb_engine_flat():
    cleanup_task = MagicMock()
    cleanup_task.done.return_value = False
    engine = MagicMock()
    engine._state = State.MANAGING
    engine._cleanup_task = cleanup_task

    _checkpoint_shutdown_flat(engine)

    assert engine._state == State.FLAT
    cleanup_task.cancel.assert_called_once()
    assert engine._cleanup_task is None
    engine._release_position_cap.assert_called_once()
    engine._notify_state_change.assert_called_once()


def test_checkpoint_shutdown_flat_marks_lsi_engine_flat():
    cleanup_task = MagicMock()
    cleanup_task.done.return_value = True
    engine = MagicMock()
    engine._state = LSIState.ARMED_LIMIT
    engine._cleanup_task = cleanup_task

    _checkpoint_shutdown_flat(engine)

    assert engine._state == LSIState.FLAT
    cleanup_task.cancel.assert_not_called()
    engine._release_position_cap.assert_called_once()
    engine._notify_state_change.assert_called_once()


def test_bull_regime_gate_uses_live_daily_history():
    gate = build_regime_gate("bull_no_low_confidence")

    try:
        set_daily_history_provider(lambda _symbol: _make_daily_history([130.0 - i for i in range(30)]))
        assert gate("20250131") is False

        set_daily_history_provider(lambda _symbol: _make_daily_history([100.0 for _ in range(30)]))
        assert gate("20250131") is False

        set_daily_history_provider(lambda _symbol: _make_daily_history([100.0 + i for i in range(30)]))
        assert gate("20250131") is True
    finally:
        set_daily_history_provider(None)


def test_bull_regime_gate_blocks_without_daily_history_provider():
    set_daily_history_provider(None)
    gate = build_regime_gate("bull_no_low_confidence")

    assert gate("20250131") is False


def test_combined_regime_avoidance_gates_use_named_buckets(monkeypatch):
    gates = dict(build_regime_gates((
        "block_bull_medium_vol",
        "block_sideways_medium_vol",
        "block_full_medium_vol",
        "block_bull_high_vol",
        "block_bear_high_vol",
        "block_bear_medium_vol",
        "block_sideways_high_vol",
        "block_full_high_vol",
    )))
    daily = pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0]},
        index=pd.DatetimeIndex([pd.Timestamp("2025-01-31")]),
    )

    def _fake_daily_loader(_name: str, _date_key: str):
        return daily

    calendars = iter((
        pd.DataFrame({"date": [pd.Timestamp("2025-01-31")], "combined_regime": ["bull_medium_vol"]}),
        pd.DataFrame({"date": [pd.Timestamp("2025-01-31")], "combined_regime": ["sideways_medium_vol"]}),
        pd.DataFrame({"date": [pd.Timestamp("2025-01-31")], "combined_regime": ["bear_high_vol"]}),
        pd.DataFrame({"date": [pd.Timestamp("2025-01-31")], "combined_regime": ["bull_high_vol"]}),
        pd.DataFrame({"date": [pd.Timestamp("2025-01-31")], "combined_regime": ["bear_high_vol"]}),
        pd.DataFrame({"date": [pd.Timestamp("2025-01-31")], "combined_regime": ["bear_medium_vol"]}),
        pd.DataFrame({"date": [pd.Timestamp("2025-01-31")], "combined_regime": ["sideways_high_vol"]}),
        pd.DataFrame({"date": [pd.Timestamp("2025-01-31")], "combined_regime": ["bull_high_vol"]}),
    ))

    monkeypatch.setattr("trader.gates._load_nq_daily_history", _fake_daily_loader)
    monkeypatch.setattr("trader.gates._build_nq_ny_extended_regime_calendar", lambda _daily: next(calendars))

    assert gates["block_bull_medium_vol"]("20250131") is False
    assert gates["block_sideways_medium_vol"]("20250131") is False
    assert gates["block_full_medium_vol"]("20250131") is True
    assert gates["block_bull_high_vol"]("20250131") is False
    assert gates["block_bear_high_vol"]("20250131") is False
    assert gates["block_bear_medium_vol"]("20250131") is False
    assert gates["block_sideways_high_vol"]("20250131") is False
    assert gates["block_full_high_vol"]("20250131") is False


def test_evaluate_regime_gate_returns_bucket_context(monkeypatch):
    daily = pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0]},
        index=pd.DatetimeIndex([pd.Timestamp("2025-01-31")]),
    )

    monkeypatch.setattr("trader.gates._load_nq_daily_history", lambda *_args, **_kwargs: daily)
    monkeypatch.setattr(
        "trader.gates._build_nq_ny_extended_regime_calendar",
        lambda _daily: pd.DataFrame(
            {
                "date": [pd.Timestamp("2025-01-31")],
                "regime": ["bull"],
                "vol_regime": ["medium_vol"],
                "combined_regime": ["bull_medium_vol"],
                "low_confidence": [False],
                "warmup_ok": [True],
            }
        ),
    )

    evaluation = evaluate_regime_gate("block_bull_medium_vol", "20250131")

    assert evaluation.allowed is False
    assert evaluation.combined_regime == "bull_medium_vol"
    assert evaluation.regime == "bull"
    assert evaluation.vol_regime == "medium_vol"
    assert "combined_regime=bull_medium_vol" in format_regime_gate_detail(evaluation)


def test_evaluate_regime_gates_returns_multiple_evaluations(monkeypatch):
    daily = pd.DataFrame(
        {"open": [100.0], "high": [101.0], "low": [99.0], "close": [100.0]},
        index=pd.DatetimeIndex([pd.Timestamp("2025-01-31")]),
    )

    monkeypatch.setattr("trader.gates._load_nq_daily_history", lambda *_args, **_kwargs: daily)
    monkeypatch.setattr(
        "trader.gates._build_nq_ny_extended_regime_calendar",
        lambda _daily: pd.DataFrame(
            {
                "date": [pd.Timestamp("2025-01-31")],
                "regime": ["bear"],
                "vol_regime": ["high_vol"],
                "combined_regime": ["bear_high_vol"],
                "low_confidence": [False],
                "warmup_ok": [True],
            }
        ),
    )

    evaluations = evaluate_regime_gates(("block_bull_medium_vol", "block_full_medium_vol"), "20250131")

    assert len(evaluations) == 2
    assert [evaluation.allowed for evaluation in evaluations] == [True, True]


def test_blocking_regime_gate_name_returns_first_failure():
    checks = (
        ("gate_a", lambda _d: True),
        ("gate_b", lambda _d: False),
        ("gate_c", lambda _d: False),
    )
    assert blocking_regime_gate_name(checks, "20250115") == "gate_b"


def test_blocking_regime_gate_name_returns_none_when_all_pass():
    checks = (
        ("gate_a", lambda _d: True),
        ("gate_b", lambda _d: True),
    )
    assert blocking_regime_gate_name(checks, "20250115") is None


def test_blocking_regime_gate_name_empty_checks():
    assert blocking_regime_gate_name((), "20250115") is None


def test_normalize_regime_gate_fields_single_check():
    check_fn = lambda _d: True
    gate, gates, gc, gcs = normalize_regime_gate_fields(
        None, (), None, (("my_gate", check_fn),),
    )
    assert gate == "my_gate"
    assert gates == ("my_gate",)
    assert gc is check_fn
    assert len(gcs) == 1


def test_normalize_regime_gate_fields_multi_check():
    fn_a = lambda _d: True
    fn_b = lambda _d: False
    gate, gates, gc, gcs = normalize_regime_gate_fields(
        None, (), None, (("a", fn_a), ("b", fn_b)),
    )
    assert gate is None
    assert gates == ("a", "b")
    assert len(gcs) == 2


def test_normalize_regime_gate_fields_legacy_check_wrapped():
    check_fn = lambda _d: True
    gate, gates, gc, gcs = normalize_regime_gate_fields(
        "legacy", (), check_fn, (),
    )
    assert gate == "legacy"
    assert gates == ("legacy",)
    assert gcs == (("legacy", check_fn),)


def test_min_periods_blocks_with_short_history():
    """With fewer than 20 daily bars, rolling windows produce NaN and the gate blocks."""
    short_closes = [100.0 + i * 0.5 for i in range(15)]
    try:
        set_daily_history_provider(lambda _symbol: _make_daily_history(short_closes))
        gate = build_regime_gate("bull_no_low_confidence")
        assert gate("20250116") is False
    finally:
        set_daily_history_provider(None)
