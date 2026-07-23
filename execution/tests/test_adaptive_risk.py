"""Tests for the adaptive prop-firm risk manager (Apex EOD PA rules)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from trader.adaptive_risk import AdaptiveRiskManager
from trader.position_limits import ContractCapManager


@dataclass
class FakeRecord:
    config_name: str = "APEX_TEST"
    session: str = "ES_NY"
    date: str = "20260722"
    timestamp: str = "2026-07-22T10:00:00-04:00"
    net_pnl_usd: float | None = 100.0
    entry_context: dict = field(default_factory=dict)


APEX_CFG = {
    "enabled": True,
    "anchor": {"date": "2026-07-01", "balance": 50000.0},
    "payouts": [],
    "tiers": [
        {"profit_below": 1500.0, "risk_scale": 0.8, "max_open_contracts": 20},
        {"profit_below": 3000.0, "risk_scale": 1.0, "max_open_contracts": 30},
        {"profit_below": 6000.0, "risk_scale": 1.0, "max_open_contracts": 40},
    ],
    "default_tier": {"risk_scale": 1.0, "max_open_contracts": 40},
    "consistency": {"best_day_frac": 0.5, "blocked_risk_scale": 0.5},
}


def make_manager(tmp_path, cfg=None, name="APEX_TEST"):
    return AdaptiveRiskManager(name, cfg or APEX_CFG, state_path=tmp_path / "state.json")


def record(date, net, session="ES_NY", ts_suffix="T10:00:00-04:00", config="APEX_TEST"):
    return FakeRecord(
        config_name=config, session=session, date=date,
        timestamp=f"{date[:4]}-{date[4:6]}-{date[6:]}{ts_suffix}", net_pnl_usd=net,
    )


class TestTierSizing:
    def test_fresh_account_is_tier1(self, tmp_path):
        m = make_manager(tmp_path)
        assert m.risk_scale() == pytest.approx(0.8)
        assert m.max_open_contracts() == 20

    def test_tier2_at_1500_profit(self, tmp_path):
        m = make_manager(tmp_path)
        m.record_trade(record("20260706", 800.0))
        m.record_trade(record("20260707", 700.0))
        assert m.profit() == pytest.approx(1500.0)
        assert m.max_open_contracts() == 30
        # consistency may throttle, but the tier scale component is 1.0
        assert m._tier()["risk_scale"] == pytest.approx(1.0)

    def test_payout_lowers_tier(self, tmp_path):
        cfg = dict(APEX_CFG)
        cfg["payouts"] = [{"date": "2026-07-10", "amount": 1500.0}]
        m = make_manager(tmp_path, cfg)
        m.record_trade(record("20260706", 1600.0))
        m.record_trade(record("20260707", 1500.0))
        # balance 53100 - 1500 payout = 51600 -> profit 1600 -> tier 2
        assert m.balance() == pytest.approx(51600.0)
        assert m.max_open_contracts() == 30

    def test_balance_override_wins(self, tmp_path):
        cfg = dict(APEX_CFG)
        cfg["balance_override"] = 53500.0
        m = make_manager(tmp_path, cfg)
        assert m.profit() == pytest.approx(3500.0)
        assert m.max_open_contracts() == 40


class TestConsistencyThrottle:
    def test_blocked_when_best_day_dominates(self, tmp_path):
        m = make_manager(tmp_path)
        m.record_trade(record("20260706", 1000.0))
        assert m.consistency_blocked()
        assert m.risk_scale() == pytest.approx(0.8 * 0.5)

    def test_unblocked_once_net_reaches_2x_best(self, tmp_path):
        m = make_manager(tmp_path)
        m.record_trade(record("20260706", 1000.0))
        m.record_trade(record("20260707", 600.0))
        m.record_trade(record("20260708", 500.0))
        # net 2100, best 1000 < 50% of net -> clear
        assert not m.consistency_blocked()
        assert m.risk_scale() == pytest.approx(1.0)  # tier 2 by now

    def test_negative_net_with_positive_day_blocks(self, tmp_path):
        m = make_manager(tmp_path)
        m.record_trade(record("20260706", 400.0))
        m.record_trade(record("20260707", -900.0))
        assert m.consistency_blocked()

    def test_payout_resets_cycle(self, tmp_path):
        cfg = dict(APEX_CFG)
        cfg["payouts"] = [{"date": "2026-07-08", "amount": 500.0}]
        m = make_manager(tmp_path, cfg)
        m.record_trade(record("20260706", 2000.0))  # before payout date
        assert not m.consistency_blocked()  # cycle empty after payout
        m.record_trade(record("20260709", 900.0))  # first day of new cycle
        assert m.consistency_blocked()

    def test_all_losses_never_blocks(self, tmp_path):
        m = make_manager(tmp_path)
        m.record_trade(record("20260706", -300.0))
        assert not m.consistency_blocked()


class TestRecordingAndPersistence:
    def test_dedupe_by_trade_key(self, tmp_path):
        m = make_manager(tmp_path)
        r = record("20260706", 500.0)
        m.record_trade(r)
        m.record_trade(r)
        assert m.profit() == pytest.approx(500.0)

    def test_other_config_ignored(self, tmp_path):
        m = make_manager(tmp_path)
        m.record_trade(record("20260706", 500.0, config="OTHER"))
        assert m.profit() == pytest.approx(0.0)

    def test_trades_before_anchor_ignored(self, tmp_path):
        m = make_manager(tmp_path)
        m.record_trade(record("20260601", 5000.0))
        assert m.profit() == pytest.approx(0.0)

    def test_state_survives_restart(self, tmp_path):
        m = make_manager(tmp_path)
        m.record_trade(record("20260706", 800.0))
        m2 = make_manager(tmp_path)
        assert m2.profit() == pytest.approx(800.0)
        # replaying the same history after restart must not double-count
        m2.replay_history([record("20260706", 800.0)])
        assert m2.profit() == pytest.approx(800.0)

    def test_replay_history_seeds_state(self, tmp_path):
        m = make_manager(tmp_path)
        m.replay_history([record("20260706", 300.0), record("20260707", 400.0, session="NQ_NY")])
        assert m.profit() == pytest.approx(700.0)

    def test_none_pnl_ignored(self, tmp_path):
        m = make_manager(tmp_path)
        m.record_trade(record("20260706", None))
        assert m.profit() == pytest.approx(0.0)


class TestCapManagerSync:
    def test_tier_up_raises_cap(self, tmp_path):
        m = make_manager(tmp_path)
        cap = ContractCapManager(max_open_contracts=20)
        m.bind_cap_manager(cap)
        assert cap.max_open_contracts == 20
        m.record_trade(record("20260706", 1600.0))
        assert cap.max_open_contracts == 30

    def test_disabled_manager_neutral(self, tmp_path):
        cfg = dict(APEX_CFG)
        cfg["enabled"] = False
        m = make_manager(tmp_path, cfg)
        cap = ContractCapManager(max_open_contracts=20)
        m.bind_cap_manager(cap)
        m.record_trade(record("20260706", 5000.0))
        assert cap.max_open_contracts == 20
        assert m.risk_scale() == pytest.approx(1.0)


class TestEngineIntegration:
    def test_orb_engine_scales_risk(self, make_orb_engine):
        engine = make_orb_engine(risk_usd=250.0, max_single_risk_usd=375.0)

        class StubManager:
            def risk_scale(self):
                return 0.8

        engine._daily_atr = 100.0
        engine._orb_high = 20010.0
        engine._orb_low = 20000.0
        baseline = engine._compute_setup_levels(entry=20000.0, direction=1, gap_size=5.0)
        engine.adaptive_risk = StubManager()
        scaled = engine._compute_setup_levels(entry=20000.0, direction=1, gap_size=5.0)
        assert baseline is not None and scaled is not None
        assert scaled.qty == pytest.approx(baseline.qty * 0.8, abs=engine.qty_step)

    def test_orb_engine_without_manager_unchanged(self, make_orb_engine):
        engine = make_orb_engine(risk_usd=250.0)
        engine._daily_atr = 100.0
        engine._orb_high = 20010.0
        engine._orb_low = 20000.0
        a = engine._compute_setup_levels(entry=20000.0, direction=1, gap_size=5.0)
        assert a is not None
        assert engine._adaptive_risk_scale() == 1.0
