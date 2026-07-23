"""Adaptive per-profile risk scaling for prop-firm rulesets (Apex EOD PA).

Implements two sizing rules driven by simulated account state:

1. Tier sizing: risk scale and max-open-contracts follow the account's profit
   tier (Apex 50K EOD PA: 2/3/4 standard contracts and rising DLL as the
   balance grows; payouts lower the balance and therefore the tier).
2. Consistency throttle: while the 50% consistency gate is blocking (best
   profitable day >= ``best_day_frac`` of net profit since the last approved
   payout), scale risk down (default 0.5x) until the gate clears.

Account state is tracked from the profile's own closed trades (net PnL per ET
session date), anchored at a configured start balance, with payouts recorded
in config. State persists to ``config/adaptive_risk_state.json`` and is
re-seeded from the dashboard trade-history file on startup (dedupe by trade
key), so a restart inside the 7-day history retention window loses nothing.

Config schema (profile-level ``adaptive_risk`` block in exec_configs.json):

    "adaptive_risk": {
      "enabled": true,
      "anchor": {"date": "2026-07-22", "balance": 50000.0},
      "payouts": [{"date": "2026-08-15", "amount": 1500.0}],
      "balance_override": null,
      "tiers": [
        {"profit_below": 1500.0, "risk_scale": 0.8, "max_open_contracts": 20},
        {"profit_below": 3000.0, "risk_scale": 1.0, "max_open_contracts": 30}
      ],
      "default_tier": {"risk_scale": 1.0, "max_open_contracts": 40},
      "consistency": {"best_day_frac": 0.5, "blocked_risk_scale": 0.5}
    }

The manager is intentionally conservative: with no config block or on any
malformed state it scales 1.0x and leaves contract caps untouched.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

STATE_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "adaptive_risk_state.json"
SEEN_RETENTION_DAYS = 14


def _compact_date(value: str) -> str:
    """Normalize 'YYYY-MM-DD' or 'YYYYMMDD' to 'YYYYMMDD'."""
    return value.replace("-", "")[:8]


class AdaptiveRiskManager:
    """Per-profile adaptive risk state machine."""

    def __init__(
        self,
        config_name: str,
        cfg: dict,
        *,
        state_path: Path = STATE_PATH,
    ) -> None:
        self.config_name = config_name
        self.enabled = bool(cfg.get("enabled", True))
        anchor = cfg.get("anchor") or {}
        self.anchor_date = _compact_date(str(anchor.get("date", "19700101")))
        self.anchor_balance = float(anchor.get("balance", 50_000.0))
        self.balance_override = cfg.get("balance_override")
        self.payouts = [
            {"date": _compact_date(str(p.get("date", ""))), "amount": float(p.get("amount", 0.0))}
            for p in (cfg.get("payouts") or [])
        ]
        self.tiers = sorted(
            (
                {
                    "profit_below": float(t["profit_below"]),
                    "risk_scale": float(t.get("risk_scale", 1.0)),
                    "max_open_contracts": float(t.get("max_open_contracts", 0.0)),
                }
                for t in (cfg.get("tiers") or [])
            ),
            key=lambda t: t["profit_below"],
        )
        default_tier = cfg.get("default_tier") or {}
        self.default_risk_scale = float(default_tier.get("risk_scale", 1.0))
        self.default_max_open = float(default_tier.get("max_open_contracts", 0.0))
        consistency = cfg.get("consistency") or {}
        self.best_day_frac = float(consistency.get("best_day_frac", 0.5))
        self.blocked_risk_scale = float(consistency.get("blocked_risk_scale", 1.0))

        self._state_path = state_path
        self._daily_net: dict[str, float] = {}
        self._seen: set[str] = set()
        self._cap_manager = None
        self._last_logged: tuple[float, bool] | None = None
        self._load_state()

    # -- persistence --------------------------------------------------------

    def _load_state(self) -> None:
        try:
            if self._state_path.exists():
                data = json.loads(self._state_path.read_text())
                entry = data.get(self.config_name) or {}
                self._daily_net = {
                    str(k): float(v) for k, v in (entry.get("daily_net") or {}).items()
                }
                self._seen = set(entry.get("seen") or [])
        except Exception:
            logger.exception("[%s] adaptive risk: failed to load state, starting fresh", self.config_name)
            self._daily_net, self._seen = {}, set()

    def _save_state(self) -> None:
        try:
            data = {}
            if self._state_path.exists():
                try:
                    data = json.loads(self._state_path.read_text())
                except Exception:
                    data = {}
            dates = sorted(self._daily_net)
            keep_from = dates[-1] if dates else ""
            if keep_from:
                # seen-keys only need to cover the recent overlap window
                cutoff = str(int(keep_from[:8]) - SEEN_RETENTION_DAYS)
                seen = [k for k in self._seen if k.split("|", 1)[0] >= cutoff]
            else:
                seen = list(self._seen)
            data[self.config_name] = {"daily_net": self._daily_net, "seen": seen}
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(self._state_path.parent), suffix=".tmp")
            with os.fdopen(fd, "w") as fh:
                json.dump(data, fh, indent=1)
            os.replace(tmp, self._state_path)
        except Exception:
            logger.exception("[%s] adaptive risk: failed to save state", self.config_name)

    # -- recording ----------------------------------------------------------

    @staticmethod
    def _trade_key(record) -> str:
        date = _compact_date(str(getattr(record, "date", "") or ""))
        return f"{date}|{getattr(record, 'session', '')}|{getattr(record, 'timestamp', '')}"

    def record_trade(self, record) -> None:
        """Fold one closed TradeRecord into daily net PnL (idempotent)."""
        if getattr(record, "config_name", "") != self.config_name:
            return
        net = getattr(record, "net_pnl_usd", None)
        if net is None:
            return
        date = _compact_date(str(getattr(record, "date", "") or ""))
        if not date or date < self.anchor_date:
            return
        key = self._trade_key(record)
        if key in self._seen:
            return
        self._seen.add(key)
        self._daily_net[date] = self._daily_net.get(date, 0.0) + float(net)
        self._save_state()
        self._sync_cap_manager()
        self._log_transition()

    def replay_history(self, records: list) -> None:
        """Seed state from restored trade history (dedupes against saved state)."""
        for record in records:
            self.record_trade(record)

    # -- derived state ------------------------------------------------------

    def balance(self) -> float:
        if self.balance_override is not None:
            return float(self.balance_override)
        total = sum(self._daily_net.values())
        paid = sum(p["amount"] for p in self.payouts)
        return self.anchor_balance + total - paid

    def profit(self) -> float:
        return self.balance() - self.anchor_balance

    def _cycle_days(self) -> dict[str, float]:
        """Daily net PnL since the last approved payout (exclusive of its date)."""
        last = max((p["date"] for p in self.payouts), default="")
        return {d: v for d, v in self._daily_net.items() if d > last}

    def consistency_blocked(self) -> bool:
        cycle = self._cycle_days()
        best = max((v for v in cycle.values() if v > 0), default=0.0)
        if best <= 0.0:
            return False
        net = sum(cycle.values())
        if net <= 0.0:
            return True
        return best >= self.best_day_frac * net

    def _tier(self) -> dict:
        profit = self.profit()
        for tier in self.tiers:
            if profit < tier["profit_below"]:
                return tier
        return {
            "profit_below": float("inf"),
            "risk_scale": self.default_risk_scale,
            "max_open_contracts": self.default_max_open,
        }

    def risk_scale(self) -> float:
        if not self.enabled:
            return 1.0
        scale = self._tier()["risk_scale"]
        if self.blocked_risk_scale != 1.0 and self.consistency_blocked():
            scale *= self.blocked_risk_scale
        return scale

    def max_open_contracts(self) -> float:
        if not self.enabled:
            return 0.0
        return self._tier()["max_open_contracts"]

    # -- wiring -------------------------------------------------------------

    def bind_cap_manager(self, cap_manager) -> None:
        """Attach a ContractCapManager whose cap follows the profit tier."""
        self._cap_manager = cap_manager
        self._sync_cap_manager()

    def _sync_cap_manager(self) -> None:
        if self._cap_manager is None or not self.enabled:
            return
        cap = self.max_open_contracts()
        if cap > 0 and self._cap_manager.max_open_contracts != cap:
            logger.info(
                "[%s] adaptive risk: tier cap -> %.0f contracts (profit=%.0f)",
                self.config_name, cap, self.profit(),
            )
            self._cap_manager.max_open_contracts = cap

    def _log_transition(self) -> None:
        current = (self.risk_scale(), self.consistency_blocked())
        if current != self._last_logged:
            logger.info(
                "[%s] adaptive risk: scale=%.2fx blocked=%s balance=%.0f profit=%.0f",
                self.config_name, current[0], current[1], self.balance(), self.profit(),
            )
            self._last_logged = current

    def status(self) -> dict:
        """Snapshot for dashboards/logs."""
        cycle = self._cycle_days()
        return {
            "enabled": self.enabled,
            "balance": round(self.balance(), 2),
            "profit": round(self.profit(), 2),
            "risk_scale": self.risk_scale(),
            "max_open_contracts": self.max_open_contracts(),
            "consistency_blocked": self.consistency_blocked(),
            "cycle_net": round(sum(cycle.values()), 2),
            "cycle_best_day": round(max((v for v in cycle.values() if v > 0), default=0.0), 2),
            "cycle_days": len(cycle),
            "n_payouts": len(self.payouts),
        }
