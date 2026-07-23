"""Dashboard API for the ORB execution service.

Provides REST endpoints and WebSocket streaming for the monitoring frontend.
Runs in-process alongside the trading engine via asyncio.gather().
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .auth import authenticate_http_request, authenticate_websocket
from .overrides import EDITABLE_FIELDS, load_overrides, save_overrides, validate_fields

if TYPE_CHECKING:
    from .engine import ORBEngine, TradeRecord

logger = logging.getLogger(__name__)

LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"

# Main DB URL for live trade, log, and execution-config persistence.
_DEFAULT_MAIN_DB_URL = "http://143.110.148.234:8100"
_MAIN_DB_URL = (
    os.environ.get("MAIN_DB_URL")
    or os.environ.get("EXPERIMENTS_DB_URL")
    or _DEFAULT_MAIN_DB_URL
).rstrip("/")


_LOG_TYPE_MAP = {"trade_log": "trades", "log": "main", "webhook_log": "webhooks"}
_CONFIG_NAME_ALIASES = {
    "ALPHA_V1": "ALPHA_V1-A",
}


# Buffered log writer — collects entries and flushes in batches via a single
# background thread, avoiding the thread-per-line explosion on startup.
import queue as _queue
import threading as _log_threading

_log_queue: _queue.Queue[tuple[str, dict]] = _queue.Queue(maxsize=10_000)
_LOG_FLUSH_INTERVAL = 2.0  # seconds
_LOG_BATCH_SIZE = 200


def _log_writer_loop() -> None:
    """Drain the log queue and batch-POST to the main DB."""
    import json
    import urllib.request
    import time

    while True:
        # Collect a batch (block on first item, then drain quickly)
        batch: dict[str, list[dict]] = {}
        try:
            log_type, entry = _log_queue.get(timeout=_LOG_FLUSH_INTERVAL)
            batch.setdefault(log_type, []).append(entry)
        except _queue.Empty:
            continue

        # Drain remaining without blocking, up to batch size
        while len(batch.get(log_type, [])) < _LOG_BATCH_SIZE:
            try:
                lt, ent = _log_queue.get_nowait()
                batch.setdefault(lt, []).append(ent)
            except _queue.Empty:
                break

        # Send each log type as a batch
        for lt, entries in batch.items():
            try:
                payload = json.dumps({"entries": entries}).encode()
                req = urllib.request.Request(
                    f"{_MAIN_DB_URL}/api/execution-logs/{lt}",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    resp.read()
            except Exception as exc:
                logger.debug("Failed to write %d %s log(s) to DB: %s", len(entries), lt, exc)


_log_writer_thread = _log_threading.Thread(target=_log_writer_loop, daemon=True)
_log_writer_thread.start()


def _write_log_to_db(log_type: str, entry: dict) -> None:
    """Queue a parsed log entry for batch write to the main DB."""
    try:
        _log_queue.put_nowait((log_type, entry))
    except _queue.Full:
        pass  # Drop silently if queue is full — local files are the fallback


def _normalize_config_name(name: str | None) -> str:
    """Map legacy config names to their canonical display/query names."""
    if not name:
        return ""
    base, bracket, suffix = name.partition("[")
    normalized_base = _CONFIG_NAME_ALIASES.get(base, base)
    return f"{normalized_base}[{suffix}" if bracket else normalized_base


def _config_query_names(name: str | None) -> tuple[str, ...]:
    """Return all DB/query names that should be treated as one config bucket."""
    normalized = _normalize_config_name(name)
    if not normalized:
        return ()
    aliases = [normalized]
    if normalized == "ALPHA_V1-A":
        aliases.append("ALPHA_V1")
    return tuple(dict.fromkeys(aliases))


def _normalize_trade_log_entry(entry: dict) -> dict:
    normalized = dict(entry)
    config = normalized.get("config")
    if config:
        normalized["config"] = _normalize_config_name(str(config))
    return normalized


def _normalize_live_trade(trade: dict) -> dict:
    normalized = dict(trade)
    config_name = normalized.get("config_name")
    if config_name:
        normalized["config_name"] = _normalize_config_name(str(config_name))
    return normalized


def _trade_log_sort_key(entry: dict) -> tuple:
    details = entry.get("details") or {}
    return (
        str(entry.get("timestamp") or ""),
        str(entry.get("config") or ""),
        str(entry.get("asset") or ""),
        str(entry.get("session") or ""),
        str(entry.get("event") or ""),
        tuple(sorted((str(k), str(v)) for k, v in details.items())),
    )


def _live_trade_sort_key(trade: dict) -> tuple:
    return (
        str(trade.get("timestamp") or ""),
        str(trade.get("exit_timestamp") or ""),
        int(trade.get("id") or 0),
    )


def _engine_state_value(engine: Any) -> str:
    state = getattr(engine, "_state", None)
    value = getattr(state, "value", None)
    return str(value if value is not None else state or "")


def _latest_engine_bar(engine: Any) -> Any | None:
    latest = getattr(engine, "_last_market_bar", None)
    if latest is not None:
        return latest
    for attr in ("_bars", "_session_bars"):
        bars = getattr(engine, attr, None)
        if bars:
            return bars[-1]
    return None


def _mark_engine_flat(engine: Any) -> None:
    state = getattr(engine, "_state", None)
    flat_state = getattr(getattr(state, "__class__", None), "FLAT", None)
    if flat_state is not None:
        engine._state = flat_state

    cleanup_task = getattr(engine, "_cleanup_task", None)
    if cleanup_task is not None and not cleanup_task.done():
        cleanup_task.cancel()
        engine._cleanup_task = None

    clear_overlap = getattr(engine, "_set_trade_overlap", None)
    if callable(clear_overlap):
        clear_overlap(False, notify=False)

    reset_setup = getattr(engine, "_reset_active_setup", None)
    if callable(reset_setup):
        reset_setup()

    release_position_cap = getattr(engine, "_release_position_cap", None)
    if callable(release_position_cap):
        release_position_cap()

    request_checkpoint = getattr(engine, "_request_checkpoint", None)
    if callable(request_checkpoint):
        request_checkpoint()

    notify_state_change = getattr(engine, "_notify_state_change", None)
    if callable(notify_state_change):
        notify_state_change()


def _record_manual_flatten(engine: Any) -> dict[str, Any]:
    if getattr(engine, "_levels", None) is None:
        return {"recorded": False, "exit_price": None, "exit_timestamp": None}

    emit_trade_record = getattr(engine, "_emit_trade_record", None)
    if not callable(emit_trade_record):
        return {"recorded": False, "exit_price": None, "exit_timestamp": None}

    latest_bar = _latest_engine_bar(engine)
    exit_price = getattr(latest_bar, "close", None) if latest_bar is not None else None
    exit_timestamp = getattr(latest_bar, "timestamp", None) if latest_bar is not None else datetime.now()
    emit_trade_record("manual_flat", exit_price=exit_price, exit_timestamp=exit_timestamp)
    return {
        "recorded": True,
        "exit_price": exit_price,
        "exit_timestamp": exit_timestamp.isoformat() if hasattr(exit_timestamp, "isoformat") else str(exit_timestamp),
    }


async def _manual_flatten_engine(engine: Any) -> dict[str, Any]:
    previous_state = _engine_state_value(engine)
    action = "already_flat"
    trade_record: dict[str, Any] = {"recorded": False, "exit_price": None, "exit_timestamp": None}

    log_trade = getattr(engine, "_log_trade", None)
    if previous_state == "armed_limit":
        if callable(log_trade):
            log_trade("MANUAL_CANCEL", f"state={previous_state}")
        await engine.broker.send_cancel(ticker=_broker_ticker_from_engine(engine))
        action = "cancelled_pending_order"
    elif previous_state in {"filled", "managing"}:
        if callable(log_trade):
            log_trade("MANUAL_FLAT", f"state={previous_state}")
        await engine.broker.send_flatten(ticker=_broker_ticker_from_engine(engine))
        trade_record = _record_manual_flatten(engine)
        action = "flattened_position"
    elif previous_state not in {"", "idle", "flat"}:
        if callable(log_trade):
            log_trade("MANUAL_FLAT", f"state={previous_state} broker_action=none")
        action = "marked_flat"

    _mark_engine_flat(engine)
    return {
        "action": action,
        "previous_state": previous_state,
        "state": _engine_state_value(engine),
        "trade_record": trade_record,
    }


def _fetch_logs_from_db_raw(
    log_type: str,
    limit: int = 500,
    offset: int = 0,
    **filters,
) -> dict:
    """Fetch execution logs from the main DB API."""
    import json
    import urllib.request
    from urllib.parse import urlencode

    params = {k: str(v) for k, v in {
        "limit": limit,
        "offset": offset,
        **filters,
    }.items() if v}
    url = f"{_MAIN_DB_URL}/api/execution-logs/{log_type}?{urlencode(params)}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read().decode())
    if result.get("success"):
        data = result["result"]
        return {
            "entries": data["entries"],
            "total": data["total"],
            "limit": data.get("limit", limit),
            "offset": data.get("offset", offset),
        }
    return {"entries": [], "total": 0, "limit": limit, "offset": offset}


def _fetch_logs_from_db(
    log_type: str,
    limit: int = 500,
    offset: int = 0,
    **filters,
) -> dict:
    """Fetch execution logs from the main DB API with config alias support."""
    config_filter = filters.get("config", "")
    if log_type == "trades" and config_filter:
        query_names = _config_query_names(str(config_filter))
        if len(query_names) > 1:
            merged: list[dict] = []
            seen: set[tuple] = set()
            fetch_limit = limit + offset
            for query_name in query_names:
                raw = _fetch_logs_from_db_raw(
                    log_type,
                    limit=fetch_limit,
                    offset=0,
                    **{**filters, "config": query_name},
                )
                for entry in raw["entries"]:
                    normalized = _normalize_trade_log_entry(entry)
                    key = _trade_log_sort_key(normalized)
                    if key in seen:
                        continue
                    seen.add(key)
                    merged.append(normalized)
            merged.sort(key=lambda entry: str(entry.get("timestamp") or ""), reverse=True)
            return {
                "entries": merged[offset:offset + limit],
                "total": len(merged),
                "limit": limit,
                "offset": offset,
            }

    raw = _fetch_logs_from_db_raw(log_type, limit=limit, offset=offset, **filters)
    if log_type == "trades":
        raw["entries"] = [_normalize_trade_log_entry(entry) for entry in raw["entries"]]
    return raw


def _write_trade_to_db(record: "TradeRecord") -> None:
    """Write a trade record to the main DB (non-blocking)."""
    import threading
    from dataclasses import asdict

    def _send():
        try:
            import json
            import urllib.request
            trade_dict = asdict(record)
            entry_context = trade_dict.get("entry_context") or {}
            # Remap fields for DB schema
            payload = {
                "trade": {
                    "session": trade_dict["session"],
                    "date": trade_dict["date"],
                    "direction": trade_dict["direction"],
                    "entry_price": trade_dict["entry_price"],
                    "stop_price": trade_dict["stop_price"],
                    "tp1_price": trade_dict["tp1_price"],
                    "tp2_price": trade_dict["tp2_price"],
                    "exit_type": trade_dict["exit_type"],
                    "tp1_hit": trade_dict["tp1_hit"],
                    "exit_timestamp": trade_dict["timestamp"],
                    "config_name": trade_dict.get("config_name", ""),
                    "r_result": trade_dict.get("r_result"),
                    "entry_timestamp": trade_dict.get("entry_timestamp", ""),
                    "ticker": trade_dict.get("ticker", ""),
                    "exec_ticker": trade_dict.get("exec_ticker", ""),
                    "leg": trade_dict.get("leg") or trade_dict["session"],
                    "net_pnl_usd": trade_dict.get("net_pnl_usd"),
                    "net_r_result": trade_dict.get("net_r_result"),
                    "commission_usd": trade_dict.get("commission_usd"),
                    "qty": trade_dict.get("qty"),
                    "notes": json.dumps(
                        {"entry_context": entry_context},
                        sort_keys=True,
                    ) if entry_context else None,
                }
            }
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{_MAIN_DB_URL}/api/live-trades",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
            logger.debug("Trade written to DB: %s %s %s", record.config_name, record.session, record.date)
        except Exception as exc:
            logger.warning("Failed to write trade to DB: %s", exc)

    threading.Thread(target=_send, daemon=True).start()
FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "dist"


def _fetch_trades_from_db(
    session: str = "",
    config: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 500,
) -> list[dict]:
    """Fetch live trades from the main DB API."""
    import json
    import urllib.request
    from urllib.parse import urlencode

    def _fetch_once(config_name: str = "") -> list[dict]:
        params = {k: v for k, v in {
            "session": session,
            "config": config_name,
            "date_from": date_from,
            "date_to": date_to,
            "limit": str(limit),
        }.items() if v}
        url = f"{_MAIN_DB_URL}/api/live-trades?{urlencode(params)}"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
        if result.get("success"):
            return result.get("result", [])
        return []

    query_names = _config_query_names(config) if config else ()
    if len(query_names) > 1:
        merged: list[dict] = []
        seen: set[tuple] = set()
        for query_name in query_names:
            for trade in _fetch_once(query_name):
                normalized = _normalize_live_trade(trade)
                key = _live_trade_sort_key(normalized)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(normalized)
        merged.sort(key=lambda trade: _live_trade_sort_key(trade), reverse=True)
        return merged[:limit]

    trades = _fetch_once(config)
    return [_normalize_live_trade(trade) for trade in trades]


def _signal_ticker_from_engine(engine: Any) -> str:
    asset_tag = getattr(engine, "_asset_tag", "")
    if asset_tag:
        return str(asset_tag).upper()
    prefix = str(getattr(engine, "name", "")).split("_", maxsplit=1)[0].upper()
    if prefix in {"NQ", "ES", "GC", "CL"}:
        return prefix
    exec_ticker = str(getattr(engine, "exec_ticker", "")).upper()
    ticker_map = {
        "MNQ": "NQ",
        "MES": "ES",
        "MGC": "GC",
        "MCL": "CL",
        "NQ": "NQ",
        "ES": "ES",
        "GC": "GC",
        "CL": "CL",
    }
    return ticker_map.get(exec_ticker, exec_ticker)


def _broker_ticker_from_engine(engine: Any) -> str:
    return str(getattr(engine, "broker_ticker", getattr(engine, "exec_ticker", "")))


def _broker_cleanup_tickers_from_engine(engine: Any) -> list[str]:
    root = str(getattr(engine, "exec_ticker", "") or "")
    contracts = [
        getattr(engine, "broker_ticker", ""),
        getattr(engine, "_exec_contract", ""),
        getattr(engine, "_trade_exec_contract", ""),
        getattr(engine, "_signal_contract", ""),
        getattr(engine, "_trade_signal_contract", ""),
    ]
    try:
        from .contracts import cleanup_traderspost_contracts

        tickers = cleanup_traderspost_contracts(
            exec_root=root,
            contracts=contracts,
            as_of=datetime.now(),
        )
    except Exception:
        tickers = [_broker_ticker_from_engine(engine)]

    result: list[str] = []
    seen: set[str] = set()
    for ticker in tickers:
        normalized = str(ticker or "").strip().upper()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _enrich_live_trades(trades: list[dict], state: "DashboardState") -> list[dict]:
    """Add dashboard display fields that older live_trades rows may not store."""
    engines_by_key = {
        (_normalize_config_name(getattr(e, "config_name", "")), getattr(e, "name", "")): e
        for e in state.all_engines
    }
    history_by_key: dict[tuple, Any] = {}
    for record in state.trade_history:
        history_by_key[
            (
                _normalize_config_name(record.config_name),
                record.session,
                record.date,
                record.direction,
                record.timestamp,
            )
        ] = record

    enriched: list[dict] = []
    for trade in trades:
        row = _normalize_live_trade(trade)
        config_name = _normalize_config_name(row.get("config_name"))
        session = str(row.get("session") or "")
        row["config_name"] = config_name
        row["leg"] = row.get("leg") or session

        history = history_by_key.get(
            (
                config_name,
                session,
                row.get("date"),
                row.get("direction"),
                row.get("exit_timestamp"),
            )
        )
        if history is not None:
            row["entry_timestamp"] = row.get("entry_timestamp") or getattr(history, "entry_timestamp", "")
            row["ticker"] = row.get("ticker") or getattr(history, "ticker", "")
            row["exec_ticker"] = row.get("exec_ticker") or getattr(history, "exec_ticker", "")
            row["entry_context"] = row.get("entry_context") or getattr(history, "entry_context", {})
            for field in (
                "gross_pnl_usd",
                "commission_per_contract",
                "commission_usd",
                "net_pnl_usd",
                "net_r_result",
            ):
                row[field] = row.get(field) if row.get(field) is not None else getattr(history, field, None)

        engine = engines_by_key.get((config_name, session))
        if engine is not None:
            row["ticker"] = row.get("ticker") or _signal_ticker_from_engine(engine)
            row["exec_ticker"] = row.get("exec_ticker") or getattr(engine, "exec_ticker", "")

        row["ticker"] = row.get("ticker") or _signal_ticker_from_engine(type("_Fallback", (), {
            "name": session,
            "exec_ticker": row.get("exec_ticker", ""),
        })())
        enriched.append(row)
    return enriched

# Known execution config names (used to distinguish config tag from asset tag in log parsing)
_KNOWN_CONFIGS: set[str] = set()


# ---------------------------------------------------------------------------
# Dashboard state (shared between engine and API)
# ---------------------------------------------------------------------------

@dataclass
class DashboardState:
    """In-memory state store read by API, written by engines."""

    engines_by_config: dict[str, list] = field(default_factory=dict)
    config: dict = field(default_factory=dict)
    mode: str = "DRY-RUN"
    start_time: float = field(default_factory=time.time)
    trade_history: list[TradeRecord] = field(default_factory=list)
    exec_configs: dict[str, dict] = field(default_factory=dict)
    multi_brokers_by_config: dict[str, Any] = field(default_factory=dict)
    orderbook_status: dict[str, Any] = field(default_factory=dict)
    _ws_clients: set[WebSocket] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        # Register config names for log parsing
        _KNOWN_CONFIGS.update(self.engines_by_config.keys())

    @property
    def all_engines(self) -> list:
        """Flat list of all engines across all configs."""
        return [e for engines in self.engines_by_config.values() for e in engines]

    async def broadcast(self, message: dict) -> None:
        """Send a JSON message to all connected WebSocket clients."""
        dead: list[WebSocket] = []
        for ws in tuple(self._ws_clients):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._ws_clients.discard(ws)

    def record_trade(self, record: TradeRecord) -> None:
        """Called by engines on trade exit. Stores record for G5 gate + DB."""
        self.trade_history.append(record)
        logger.info(
            "Trade recorded: [%s] %s %s exit=%s tp1=%s",
            record.config_name, record.session, record.date,
            record.exit_type, record.tp1_hit,
        )
        # Persist to disk for crash recovery
        from .checkpoint import save_trade_history
        save_trade_history(self.trade_history)

        # Fire-and-forget write to the main DB.
        _write_trade_to_db(record)

    def asia_tp1_hit_for_date(self, date: str, config_name: str = "") -> bool:
        """Check if any Asia session hit TP1 on the given date (for G5 gate).

        When config_name is provided, only checks trades from that config.
        """
        for r in self.trade_history:
            if r.date == date and r.tp1_hit and r.session in ("NQ_Asia", "ES_Asia"):
                if config_name and _normalize_config_name(r.config_name) != _normalize_config_name(config_name):
                    continue
                return True
        return False

    def on_state_change(self, status: dict) -> None:
        """Called by engines on state transitions. Schedules WS broadcast."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.broadcast({
                "type": "status",
                "data": self._build_status(),
            }))
        except RuntimeError:
            pass  # No event loop — skip (e.g. during tests)

    def _build_status(self) -> dict:
        return {
            "configs": {
                cfg_name: {
                    "engines": [e.status_dict() for e in engines],
                }
                for cfg_name, engines in self.engines_by_config.items()
            },
            "uptime_seconds": round(time.time() - self.start_time),
            "mode": self.mode,
            "exec_configs": _public_exec_config_meta(self),
            "orderbook": self.orderbook_status,
        }


def _build_exec_config_meta(state: DashboardState) -> dict[str, dict]:
    """Load execution config metadata from disk and merge live webhook state."""
    from .main import load_exec_configs

    configs = load_exec_configs(state.config, include_remote_webhooks=True)
    meta: dict[str, dict] = {}
    for cfg in configs:
        live_meta = state.exec_configs.get(cfg.name, {})
        webhooks = live_meta.get("webhooks")
        if webhooks is None:
            webhooks = [
                {
                    "url": w.url,
                    "label": w.label,
                    "paused": w.paused,
                    "multiplier": w.multiplier,
                }
                for w in cfg.webhooks
            ]
        meta[cfg.name] = {
            "enabled": cfg.enabled,
            "max_open_contracts": getattr(cfg, "max_open_contracts", 0.0),
            "webhooks": webhooks,
            "sessions": list(cfg.session_overrides.keys()),
            "lsi_sessions": list(cfg.lsi_session_overrides.keys()),
        }
    return meta


def _runtime_mode_from_brokers(state: DashboardState) -> str:
    """Return LIVE when any current runtime broker has a real webhook URL."""
    for multi_broker in state.multi_brokers_by_config.values():
        for broker in getattr(multi_broker, "_brokers", []):
            if not getattr(broker, "dry_run", True):
                return "LIVE"
    return "DRY-RUN"


def _public_exec_config_meta(state: DashboardState) -> dict[str, dict]:
    """Return public-safe execution config metadata for status displays.

    The authenticated config endpoint can expose webhook URLs. Public status
    only needs enough shape to decide LIVE vs DRY and show strategy counts.
    """
    public_meta: dict[str, dict] = {}
    for config_name, meta in state.exec_configs.items():
        webhooks = meta.get("webhooks") or []
        public_meta[config_name] = {
            "enabled": bool(meta.get("enabled", True)),
            "max_open_contracts": meta.get("max_open_contracts", 0.0),
            "webhooks": [{} for _ in webhooks],
            "sessions": list(meta.get("sessions") or []),
            "lsi_sessions": list(meta.get("lsi_sessions") or []),
        }
    return public_meta


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------

def parse_trade_log_line(line: str) -> dict | None:
    """Parse a trade log line into a structured dict.

    Formats (new — with config tag):
      - YYYY-MM-DD HH:MM:SS | CONFIG | ASSET | SESSION | EVENT | key=value ...

    Legacy formats (backward-compatible):
      - YYYY-MM-DD HH:MM:SS | SESSION | EVENT | key=value ...
      - YYYY-MM-DD HH:MM:SS | ASSET | SESSION | EVENT | key=value ...
    """
    line = line.strip()
    if not line:
        return None

    parts = [part.strip() for part in line.split(" | ")]
    if len(parts) < 3:
        return None

    timestamp = parts[0]
    config = None
    asset = ""

    # Detect config + asset tags. Log format:
    #   new:    TIMESTAMP | CONFIG | ASSET | SESSION | EVENT | details
    #   legacy: TIMESTAMP | [ASSET |] SESSION | EVENT | details
    # Assets are always lowercase short symbols; configs are uppercase.
    _ASSETS = {
        "nq",
        "es",
        "gc",
        "cl",
        "ym",
        "si",
        "mnq",
        "mes",
        "mym",
        "mgc",
        "mcl",
        "sil",
        "rty",
    }
    remaining = parts[1:]

    # If first field is not an asset and not a session (sessions contain "_"),
    # and the next field IS an asset, then first field is a config tag.
    if (
        len(remaining) >= 3
        and remaining[0].lower() not in _ASSETS
        and remaining[1].lower() in _ASSETS
    ):
        config = remaining[0]
        remaining = remaining[1:]

    # Detect asset tag
    if remaining and remaining[0].lower() in _ASSETS:
        asset = remaining[0].lower()
        remaining = remaining[1:]

    if len(remaining) < 2:
        return None

    session = remaining[0]
    event = remaining[1]
    detail_str = " | ".join(remaining[2:]) if len(remaining) > 2 else ""

    details: dict[str, str] = {}

    if detail_str:
        for match in re.finditer(r'(\w+)=([^|]+?)(?=\s+\w+=|$)', detail_str):
            details[match.group(1)] = match.group(2).strip()

    # Some events embed key=value in the event string itself
    if not details and " " in event:
        ev_parts = event.split(None, 1)
        event = ev_parts[0]
        if len(ev_parts) > 1:
            for match in re.finditer(r'(\w+)=([^|]+?)(?=\s+\w+=|$)', ev_parts[1]):
                details[match.group(1)] = match.group(2).strip()

    return {
        "timestamp": timestamp,
        "config": _normalize_config_name(config),
        "asset": asset or None,
        "session": session,
        "event": event,
        "details": details,
    }


def parse_main_log_line(line: str) -> dict | None:
    """Parse a main log line into a structured dict.

    Format: YYYY-MM-DD HH:MM:SS | LEVEL | logger_name | message
    """
    line = line.strip()
    if not line:
        return None

    parts = line.split(" | ", maxsplit=3)
    if len(parts) < 4:
        return None

    return {
        "timestamp": parts[0].strip(),
        "level": parts[1].strip(),
        "logger": parts[2].strip(),
        "message": parts[3].strip(),
    }


def parse_webhook_log_line(line: str) -> dict | None:
    """Parse a webhook log line into a structured dict.

    Format: YYYY-MM-DD HH:MM:SS | CONFIG[ACCOUNT] | STATUS | HTTP_CODE | LATENCYms | PAYLOAD
    DRY-RUN: YYYY-MM-DD HH:MM:SS | CONFIG[ACCOUNT] | DRY-RUN | LATENCYms | PAYLOAD
    """
    line = line.strip()
    if not line:
        return None

    parts = [p.strip() for p in line.split(" | ", maxsplit=5)]
    if len(parts) < 4:
        return None

    result: dict = {
        "timestamp": parts[0],
        "account": parts[1],
        "status": parts[2],  # OK, FAILED, DRY-RUN, ERROR
    }

    if parts[2] == "DRY-RUN":
        result["latency"] = parts[3] if len(parts) > 3 else ""
        result["payload"] = parts[4] if len(parts) > 4 else ""
    else:
        result["http_code"] = parts[3] if len(parts) > 3 else ""
        result["latency"] = parts[4] if len(parts) > 4 else ""
        result["payload"] = parts[5] if len(parts) > 5 else ""

    return result


def _read_log_lines(
    path: Path,
    limit: int = 50,
    offset: int = 0,
    search: str = "",
    level: str = "",
    config_filter: str = "",
    parser=None,
) -> tuple[list[dict], int]:
    """Read and parse log lines from a file (newest first).

    Returns (entries, total_count).
    """
    if not path.exists():
        return [], 0

    with open(path, "r") as f:
        raw_lines = f.readlines()

    # Parse all lines
    entries = []
    for line in raw_lines:
        parsed = parser(line) if parser else None
        if parsed is not None:
            entries.append(parsed)

    # Filter by config name (trade log only)
    if config_filter:
        config_names = {name.upper() for name in _config_query_names(config_filter)}
        if not config_names:
            config_names = {_normalize_config_name(config_filter).upper()}
        entries = [e for e in entries if str(e.get("config", "")).upper() in config_names]

    # Filter by level (main log only)
    if level:
        level_upper = level.upper()
        level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "WARN": 2, "ERROR": 3, "CRITICAL": 4}
        min_level = level_order.get(level_upper, 0)
        entries = [
            e for e in entries
            if level_order.get(e.get("level", "").upper().strip(), 0) >= min_level
        ]

    # Filter by search text
    if search:
        search_lower = search.lower()
        entries = [
            e for e in entries
            if search_lower in str(e).lower()
        ]

    total = len(entries)

    # Reverse for newest-first, then paginate
    entries.reverse()
    entries = entries[offset:offset + limit]

    return entries, total


# ---------------------------------------------------------------------------
# Log tailing for WebSocket
# ---------------------------------------------------------------------------

class LogTailer:
    """Tails log files and broadcasts new lines to WebSocket clients."""

    def __init__(self, state: DashboardState, poll_interval: float = 0.5) -> None:
        self.state = state
        self.poll_interval = poll_interval
        self._positions: dict[str, int] = {}
        self._inodes: dict[str, int] = {}

    async def run(self) -> None:
        """Poll log files forever, broadcasting new lines."""
        trade_log = LOG_DIR / "trades.log"
        main_log = LOG_DIR / "trader.log"
        webhook_log = LOG_DIR / "webhooks.log"

        # Seek to end of existing files
        for path in [trade_log, main_log, webhook_log]:
            if path.exists():
                self._positions[str(path)] = path.stat().st_size
                self._inodes[str(path)] = path.stat().st_ino

        while True:
            await asyncio.sleep(self.poll_interval)

            if not self.state._ws_clients:
                continue

            await self._tail_file(trade_log, "trade_log", parse_trade_log_line)
            await self._tail_file(main_log, "log", parse_main_log_line)
            await self._tail_file(webhook_log, "webhook_log", parse_webhook_log_line)

    async def _tail_file(self, path: Path, msg_type: str, parser) -> None:
        """Read new lines from a log file and broadcast."""
        key = str(path)
        if not path.exists():
            return

        try:
            stat = path.stat()
        except OSError:
            return

        # Check for rotation (inode change or file shrunk)
        prev_inode = self._inodes.get(key, 0)
        prev_pos = self._positions.get(key, 0)

        if stat.st_ino != prev_inode or stat.st_size < prev_pos:
            # File was rotated — start from beginning
            prev_pos = 0
            self._inodes[key] = stat.st_ino

        if stat.st_size <= prev_pos:
            return

        try:
            with open(path, "r") as f:
                f.seek(prev_pos)
                new_data = f.read()
                self._positions[key] = f.tell()
        except OSError:
            return

        for line in new_data.splitlines():
            parsed = parser(line)
            if parsed is not None:
                await self.state.broadcast({"type": msg_type, "data": parsed})
                _write_log_to_db(_LOG_TYPE_MAP[msg_type], parsed)


# ---------------------------------------------------------------------------
# WebSocket logging handler
# ---------------------------------------------------------------------------

class WebSocketLogHandler(logging.Handler):
    """Logging handler that broadcasts to WebSocket clients."""

    def __init__(self, state: DashboardState) -> None:
        super().__init__()
        self.state = state

    def emit(self, record: logging.LogRecord) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        msg = {
            "timestamp": self.format(record).split(" | ")[0] if " | " in self.format(record) else "",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        loop.create_task(self.state.broadcast({"type": "log", "data": msg}))


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

def create_app(state: DashboardState) -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(title="ORB Trader Dashboard", version="0.1.0")

    @app.middleware("http")
    async def require_dashboard_auth(request: Request, call_next):
        auth_response = await authenticate_http_request(request)
        if auth_response is not None:
            return auth_response
        return await call_next(request)

    # CORS for frontend dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── REST endpoints ──────────────────────────────────────────────

    @app.get("/api/status")
    async def get_status():
        return state._build_status()

    @app.get("/api/logs/trades")
    async def get_trade_logs(
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        search: str = Query(""),
        config: str = Query("", description="Filter by execution config name"),
        source: str = Query("db", description="'db' for main DB, 'local' for log files"),
    ):
        if source == "db":
            try:
                return _fetch_logs_from_db("trades", limit=limit, offset=offset, config=config, search=search)
            except Exception as exc:
                logger.warning("DB log fetch failed, falling back to local: %s", exc)
        entries, total = _read_log_lines(
            LOG_DIR / "trades.log",
            limit=limit,
            offset=offset,
            search=search,
            config_filter=config,
            parser=parse_trade_log_line,
        )
        return {"entries": entries, "total": total, "limit": limit, "offset": offset}

    @app.get("/api/logs/main")
    async def get_main_logs(
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
        level: str = Query(""),
        search: str = Query(""),
        source: str = Query("db", description="'db' for main DB, 'local' for log files"),
    ):
        if source == "db":
            try:
                return _fetch_logs_from_db("main", limit=limit, offset=offset, level=level, search=search)
            except Exception as exc:
                logger.warning("DB log fetch failed, falling back to local: %s", exc)
        entries, total = _read_log_lines(
            LOG_DIR / "trader.log",
            limit=limit,
            offset=offset,
            search=search,
            level=level,
            parser=parse_main_log_line,
        )
        return {"entries": entries, "total": total, "limit": limit, "offset": offset}

    @app.get("/api/logs/webhooks")
    async def get_webhook_logs(
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        search: str = Query(""),
        account: str = Query("", description="Filter by account/config name"),
        source: str = Query("db", description="'db' for main DB, 'local' for log files"),
    ):
        if source == "db":
            try:
                return _fetch_logs_from_db("webhooks", limit=limit, offset=offset, account=account, search=search)
            except Exception as exc:
                logger.warning("DB log fetch failed, falling back to local: %s", exc)
        entries, total = _read_log_lines(
            LOG_DIR / "webhooks.log",
            limit=limit,
            offset=offset,
            search=search if not account else account,
            parser=parse_webhook_log_line,
        )
        return {"entries": entries, "total": total, "limit": limit, "offset": offset}

    @app.get("/api/trades/history")
    async def get_trade_history(
        session: str = Query("", description="Filter by session name"),
        config: str = Query("", description="Filter by execution config name"),
        date_from: str = Query("", description="Filter from date (YYYYMMDD)"),
        date_to: str = Query("", description="Filter to date (YYYYMMDD)"),
        limit: int = Query(500, ge=1, le=5000),
        source: str = Query("db", description="'db' for main DB, 'memory' for in-memory"),
    ):
        if source == "memory":
            # Legacy: return in-memory trade history (JSON-backed, 7-day window)
            records = state.trade_history
            if config:
                records = [
                    r for r in records
                    if _normalize_config_name(r.config_name) == _normalize_config_name(config)
                ]
            if session:
                records = [r for r in records if r.session == session]
            records = list(reversed(records))[:limit]
            from dataclasses import asdict
            return {
                "trades": _enrich_live_trades([asdict(r) for r in records], state),
                "total": len(state.trade_history),
            }

        # Default: read from main DB.
        try:
            trades = _fetch_trades_from_db(
                session=session, config=config,
                date_from=date_from, date_to=date_to, limit=limit,
            )
            trades = _enrich_live_trades(trades, state)
            return {"trades": trades, "total": len(trades)}
        except Exception as exc:
            logger.warning("DB trade fetch failed, falling back to memory: %s", exc)
            records = state.trade_history
            if config:
                records = [
                    r for r in records
                    if _normalize_config_name(r.config_name) == _normalize_config_name(config)
                ]
            if session:
                records = [r for r in records if r.session == session]
            records = list(reversed(records))[:limit]
            from dataclasses import asdict
            return {
                "trades": _enrich_live_trades([asdict(r) for r in records], state),
                "total": len(state.trade_history),
            }

    class ManualTradeRequest(BaseModel):
        session: str
        date: str
        direction: int
        entry_price: float
        stop_price: float
        tp1_price: float
        tp2_price: float
        exit_type: str
        tp1_hit: bool
        exit_timestamp: str
        config_name: str = ""
        r_result: float | None = None
        notes: str | None = None
        entry_timestamp: str | None = None
        ticker: str | None = None
        exec_ticker: str | None = None
        leg: str | None = None

    @app.post("/api/trades/history")
    async def create_manual_trade(req: ManualTradeRequest):
        """Manually log a trade (retroactive or missed)."""
        trade_dict = req.model_dump()
        trade_dict["config_name"] = _normalize_config_name(trade_dict.get("config_name"))
        try:
            import json
            import urllib.request
            payload = json.dumps({"trade": trade_dict}).encode()
            http_req = urllib.request.Request(
                f"{_MAIN_DB_URL}/api/live-trades",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(http_req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
            return {"success": True, "rowid": result.get("result", {}).get("rowid")}
        except Exception as exc:
            logger.error("Failed to log manual trade: %s", exc)
            raise HTTPException(502, f"Failed to write to main DB: {exc}")

    @app.get("/api/config")
    async def get_config():
        overrides = load_overrides()
        all_engines = state.all_engines
        risk_cfg = state.config.get("risk", {})
        exec_configs = _build_exec_config_meta(state)
        return {
            "config": state.config,
            "baseline_r": risk_cfg.get("baseline_r", 250),
            "sessions": {
                f"{e.config_name}:{e.name}" if e.config_name else e.name: _session_info(e)
                for e in all_engines
            },
            "overrides": {
                e.name: overrides.get(e.name, {}) for e in all_engines
            },
            "defaults": {
                e.name: _defaults_for_session(e.name) for e in all_engines
            },
            "exec_configs": exec_configs,
        }

    # ── Config override endpoints ──────────────────────────────────

    @app.patch("/api/config/sessions/{session_name}")
    async def update_session_config(session_name: str, body: SessionOverrideRequest):
        from .overrides import LSI_EDITABLE_FIELDS
        engine = _find_engine(state, session_name)
        if engine is None:
            raise HTTPException(404, f"Session '{session_name}' not found")

        allowed = LSI_EDITABLE_FIELDS if _is_lsi_engine(engine) else None
        valid_fields, errors = validate_fields(body.overrides, allowed=allowed)
        if errors:
            raise HTTPException(422, detail=errors)
        if not valid_fields:
            raise HTTPException(400, "No valid fields to update")
        try:
            _validate_exit_mode_update(engine, valid_fields)
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc

        # Safety: reject if engine is mid-trade (covers both ORBEngine and LSIEngine states)
        blocked_states = {"armed_limit", "filled", "managing"}
        if engine._state.value in blocked_states:
            raise HTTPException(
                409,
                f"Session '{session_name}' is in state '{engine._state.value}'. "
                "Config changes are blocked while a trade is active.",
            )

        # Load, merge, persist
        overrides = load_overrides()
        session_overrides = overrides.get(session_name, {})
        session_overrides.update(valid_fields)

        # Remove overrides that match the default value (keep sparse)
        defaults = _defaults_for_session(session_name)
        session_overrides = {
            k: v for k, v in session_overrides.items() if defaults.get(k) != v
        }

        if session_overrides:
            overrides[session_name] = session_overrides
        elif session_name in overrides:
            del overrides[session_name]
        save_overrides(overrides)

        # Apply to in-memory engine
        _apply_overrides_to_engine(engine, valid_fields)

        await state.broadcast({"type": "config_update", "data": {
            "session": session_name,
            "config": _session_info(engine),
            "overrides": overrides.get(session_name, {}),
        }})

        return {
            "session": session_name,
            "config": _session_info(engine),
            "overrides": overrides.get(session_name, {}),
        }

    # ── Exec config webhook endpoints ──────────────────────────────

    @app.put("/api/config/exec/{config_name}/webhooks")
    async def update_exec_webhooks(config_name: str, body: "ExecWebhooksRequest"):
        """Replace remote DB webhook accounts for an execution config."""
        from .main import WebhookEntry, load_exec_configs, save_exec_webhooks_remote
        from .broker import TradersPostClient, MultiBroker

        configs = load_exec_configs(include_remote_webhooks=True)
        target = next((c for c in configs if c.name == config_name), None)
        if target is None:
            raise HTTPException(404, f"Exec config '{config_name}' not found")

        # Validate — reject empty/malformed URLs.
        new_webhooks = []
        for w in body.webhooks:
            url = (w.get("url") or "").strip()
            label = (w.get("label") or "").strip()
            if not url:
                raise HTTPException(422, "Each webhook must have a non-empty url")
            if not url.startswith(("https://", "http://")):
                raise HTTPException(422, "Webhook URLs must start with http:// or https://")
            multiplier = float(w.get("multiplier", 1.0))
            if multiplier <= 0:
                raise HTTPException(422, "Webhook multipliers must be > 0")
            new_webhooks.append(
                WebhookEntry(
                    url=url,
                    label=label,
                    paused=bool(w.get("paused", False)),
                    multiplier=multiplier,
                )
            )

        target.webhooks = new_webhooks
        try:
            new_webhooks = save_exec_webhooks_remote(config_name, new_webhooks)
        except Exception as exc:
            raise HTTPException(502, f"Remote execution config DB unavailable: {exc}") from exc

        # Rebuild live runtime brokers so the change takes effect immediately.
        # Close old broker sessions first.
        old_multi = state.multi_brokers_by_config.get(config_name)
        if old_multi:
            await old_multi.close()

        if new_webhooks:
            new_brokers = [
                TradersPostClient(
                    webhook_url=w.url,
                    config_name=f"{config_name}[{w.label}]" if w.label else config_name,
                )
                for w in new_webhooks
            ]
        else:
            # No webhooks → dry-run stub
            new_brokers = [
                TradersPostClient(webhook_url="", config_name=config_name)
            ]
        new_multi = MultiBroker(new_brokers)
        state.multi_brokers_by_config[config_name] = new_multi
        state.mode = _runtime_mode_from_brokers(state)

        # Point all engines for this config to the new broker
        for eng in state.engines_by_config.get(config_name, []):
            eng.broker = new_multi

        # Update metadata so the API reflects the change immediately
        state.exec_configs.setdefault(config_name, {
            "enabled": target.enabled,
            "max_open_contracts": target.max_open_contracts,
            "sessions": list(target.session_overrides.keys()),
            "lsi_sessions": list(target.lsi_session_overrides.keys()),
        })
        state.exec_configs[config_name]["webhooks"] = [
            {"url": w.url, "label": w.label, "paused": w.paused, "multiplier": w.multiplier}
            for w in new_webhooks
        ]

        mode = "LIVE" if new_webhooks else "DRY-RUN"
        logger.info("[%s] Webhooks updated → %s (%d webhooks)", config_name, mode, len(new_webhooks))

        await state.broadcast({"type": "config_update", "data": {
            "exec_config": config_name,
            "webhooks": state.exec_configs[config_name]["webhooks"],
        }})

        return {"config": config_name, "webhooks": state.exec_configs[config_name]["webhooks"]}

    @app.patch("/api/config/exec/{config_name}/webhooks/{webhook_index}")
    async def patch_webhook(config_name: str, webhook_index: int, body: "WebhookPatchRequest"):
        """Update pause state or multiplier for a single webhook entry."""
        from .main import load_exec_configs, save_exec_webhooks_remote

        configs = load_exec_configs(include_remote_webhooks=True)
        target = next((c for c in configs if c.name == config_name), None)
        if target is None:
            raise HTTPException(404, f"Exec config '{config_name}' not found")

        wh_list = state.exec_configs.get(config_name, {}).get("webhooks")
        if wh_list is None:
            wh_list = [
                {"url": w.url, "label": w.label, "paused": w.paused, "multiplier": w.multiplier}
                for w in target.webhooks
            ]
        if webhook_index < 0 or webhook_index >= len(wh_list):
            raise HTTPException(404, f"Webhook index {webhook_index} out of range")

        if body.multiplier is not None and body.multiplier <= 0:
            raise HTTPException(422, "multiplier must be > 0")

        # Persist to the remote execution config DB.
        wh = target.webhooks[webhook_index]
        if body.paused is not None:
            wh.paused = body.paused
        if body.multiplier is not None:
            wh.multiplier = body.multiplier
        try:
            target.webhooks = save_exec_webhooks_remote(config_name, target.webhooks)
        except Exception as exc:
            raise HTTPException(502, f"Remote execution config DB unavailable: {exc}") from exc

        # Apply to live runtime broker (no restart needed)
        multi_broker = state.multi_brokers_by_config.get(config_name)
        if multi_broker and webhook_index < len(multi_broker._brokers):
            live_broker = multi_broker._brokers[webhook_index]
            if body.paused is not None:
                live_broker.paused = body.paused
            if body.multiplier is not None:
                live_broker.multiplier = body.multiplier

        # Update in-memory metadata
        state.exec_configs.setdefault(config_name, {
            "enabled": target.enabled,
            "max_open_contracts": target.max_open_contracts,
            "sessions": list(target.session_overrides.keys()),
            "lsi_sessions": list(target.lsi_session_overrides.keys()),
            "webhooks": wh_list,
        })
        wh_meta = state.exec_configs[config_name]["webhooks"][webhook_index]
        if body.paused is not None:
            wh_meta["paused"] = body.paused
        if body.multiplier is not None:
            wh_meta["multiplier"] = body.multiplier

        await state.broadcast({"type": "accounts_update", "data": {
            "exec_config": config_name,
            "webhooks": state.exec_configs[config_name]["webhooks"],
        }})

        return {"config": config_name, "webhook_index": webhook_index, "webhook": wh_meta}

    @app.post("/api/config/exec/{config_name}/webhooks/{webhook_index}/flatten")
    async def flatten_webhook(config_name: str, webhook_index: int):
        """Send a flatten payload to a single specific webhook account."""
        if config_name not in state.exec_configs:
            raise HTTPException(404, f"Exec config '{config_name}' not found")

        multi_broker = state.multi_brokers_by_config.get(config_name)
        if multi_broker is None:
            raise HTTPException(404, f"No broker found for config '{config_name}'")

        if webhook_index < 0 or webhook_index >= len(multi_broker._brokers):
            raise HTTPException(404, f"Webhook index {webhook_index} out of range")

        broker = multi_broker._brokers[webhook_index]

        # Collect distinct cleanup tickers from all engines in this config.
        # Include adjacent rollover contracts so stale old-month positions or
        # resting orders are not missed during CME roll week.
        cfg_engines = state.engines_by_config.get(config_name, [])
        tickers = []
        seen_tickers: set[str] = set()
        for engine in cfg_engines:
            for ticker in _broker_cleanup_tickers_from_engine(engine):
                if ticker not in seen_tickers:
                    seen_tickers.add(ticker)
                    tickers.append(ticker)
        if not tickers:
            tickers = ["MNQ"]

        for t in tickers:
            await broker.send_flatten(ticker=t)
            await broker.send_cancel(ticker=t)

        label = (state.exec_configs[config_name].get("webhooks", [{}])[webhook_index] or {}).get("label", "")
        logger.info("[%s] Per-account flatten/cancel sent to index=%d label=%s tickers=%s", config_name, webhook_index, label, tickers)

        return {"config": config_name, "webhook_index": webhook_index, "tickers": tickers, "status": "sent"}

    @app.patch("/api/config/exec/{config_name}/enabled")
    async def patch_exec_enabled(config_name: str, body: "EnabledPatchRequest"):
        """Toggle enabled state for an execution config (dry-run ↔ disabled)."""
        from .main import load_exec_configs, save_exec_configs, save_exec_config_metadata_remote

        configs = load_exec_configs()
        target = next((c for c in configs if c.name == config_name), None)
        if target is None:
            raise HTTPException(404, f"Exec config '{config_name}' not found")

        target.enabled = body.enabled
        save_exec_configs(configs)
        try:
            save_exec_config_metadata_remote(target)
        except Exception as exc:
            logger.warning("[%s] Could not sync enabled state to remote DB: %s", config_name, exc)

        # Update in-memory state
        if config_name in state.exec_configs:
            state.exec_configs[config_name]["enabled"] = body.enabled

        await state.broadcast({"type": "config_update", "data": {
            "exec_config": config_name,
            "enabled": body.enabled,
        }})

        return {"config": config_name, "enabled": body.enabled}

    @app.delete("/api/config/sessions/{session_name}")
    async def reset_session_config(session_name: str):
        engine = _find_engine(state, session_name)
        if engine is None:
            raise HTTPException(404, f"Session '{session_name}' not found")

        if engine._state.value in {"armed_limit", "filled", "managing"}:
            raise HTTPException(
                409, "Cannot reset config while a trade is active",
            )

        # Remove overrides for this session
        overrides = load_overrides()
        if session_name in overrides:
            del overrides[session_name]
            save_overrides(overrides)

        # Reset engine fields to defaults
        _apply_defaults_to_engine(engine, session_name, state.config)

        await state.broadcast({"type": "config_update", "data": {
            "session": session_name,
            "config": _session_info(engine),
            "overrides": {},
        }})

        return {
            "session": session_name,
            "config": _session_info(engine),
            "overrides": {},
        }

    # ── Engine pause/resume endpoints ─────────────────────────────

    @app.post("/api/engines/{session_name}/pause")
    async def pause_engine(session_name: str, config: str | None = None):
        """Pause a single engine leg. Sends cancel/flatten if mid-trade."""
        engine = _find_engine(state, session_name, config)
        if engine is None:
            raise HTTPException(404, f"Engine '{session_name}' not found")
        if engine.paused:
            return {"session": session_name, "paused": True, "action": "already_paused"}

        # Safe cleanup: cancel pending orders or flatten open positions
        state_val = engine._state.value
        action_taken = "none"

        if state_val == "armed_limit":
            await engine.broker.send_cancel(ticker=_broker_ticker_from_engine(engine))
            action_taken = "cancelled"
            logger.info("[%s] Pause: cancelled pending order", engine.name)
        elif state_val in ("managing", "filled"):
            await engine.broker.send_flatten(ticker=_broker_ticker_from_engine(engine))
            action_taken = "flattened"
            logger.info("[%s] Pause: flattened open position", engine.name)

        engine.paused = True
        logger.info("[%s] Engine paused (action=%s)", engine.name, action_taken)

        # Trigger status broadcast so frontend updates immediately
        state.on_state_change(engine.status_dict())

        return {"session": session_name, "paused": True, "action": action_taken}

    @app.post("/api/engines/{session_name}/flatten")
    async def flatten_engine(session_name: str, config: str | None = None):
        """Manually flatten/cancel a single engine leg without pausing it."""
        engine = _find_engine(state, session_name, config)
        if engine is None:
            raise HTTPException(404, f"Engine '{session_name}' not found")

        try:
            result = await _manual_flatten_engine(engine)
        except Exception as exc:
            logger.exception("[%s] Manual flatten failed", session_name)
            raise HTTPException(502, f"Manual flatten failed: {exc}") from exc

        return {
            "session": session_name,
            "config": getattr(engine, "config_name", config),
            **result,
        }

    @app.post("/api/engines/{session_name}/resume")
    async def resume_engine(session_name: str, config: str | None = None):
        """Resume a paused engine leg."""
        engine = _find_engine(state, session_name, config)
        if engine is None:
            raise HTTPException(404, f"Engine '{session_name}' not found")
        if not engine.paused:
            return {"session": session_name, "paused": False, "action": "already_running"}

        engine.paused = False
        logger.info("[%s] Engine resumed", engine.name)

        # Trigger status broadcast
        state.on_state_change(engine.status_dict())

        return {"session": session_name, "paused": False}

    # ── WebSocket ───────────────────────────────────────────────────

    @app.websocket("/api/ws")
    async def websocket_endpoint(ws: WebSocket):
        if not await authenticate_websocket(ws):
            return
        await ws.accept()
        state._ws_clients.add(ws)
        logger.info("WebSocket client connected (%d total)", len(state._ws_clients))

        # Send initial status
        try:
            await ws.send_json({"type": "status", "data": state._build_status()})
        except Exception:
            state._ws_clients.discard(ws)
            return

        try:
            while True:
                # Keep connection alive — client can send pings
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            state._ws_clients.discard(ws)
            logger.info("WebSocket client disconnected (%d remaining)", len(state._ws_clients))

    # ── Static files (production) ───────────────────────────────────

    if FRONTEND_DIST.exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
        logger.info("Serving frontend from %s", FRONTEND_DIST)

    return app


class SessionOverrideRequest(BaseModel):
    """Sparse dict of fields to override for a session."""

    overrides: dict[str, Any]


class ExecWebhooksRequest(BaseModel):
    """Replacement webhooks list for an execution config."""

    webhooks: list[dict[str, Any]]


class WebhookPatchRequest(BaseModel):
    """Partial update for a single webhook entry (pause state or multiplier)."""

    paused: bool | None = None
    multiplier: float | None = None


class EnabledPatchRequest(BaseModel):
    """Toggle enabled state for an execution config."""

    enabled: bool


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _find_engine(state: DashboardState, name: str, config_name: str | None = None):
    """Find engine by session name, optionally scoped to a config."""
    for e in state.all_engines:
        if e.name == name:
            if config_name is None or e.config_name == config_name:
                return e
    return None


def _validate_exit_mode_update(engine, fields: dict) -> None:
    import math

    next_exit_mode = fields.get("exit_mode", getattr(engine, "exit_mode", "split"))
    next_tp1_ratio = fields.get("tp1_ratio", getattr(engine, "tp1_ratio", 0.0))
    if next_exit_mode not in {"split", "single_target"}:
        raise ValueError("exit_mode must be one of 'split' or 'single_target'")
    try:
        next_tp1_ratio_value = float(next_tp1_ratio)
    except (TypeError, ValueError) as exc:
        raise ValueError("tp1_ratio must be numeric") from exc
    if next_exit_mode == "single_target" and not math.isclose(
        next_tp1_ratio_value,
        1.0,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise ValueError("tp1_ratio must be 1.0 when exit_mode='single_target'")


def _apply_overrides_to_engine(engine, fields: dict) -> None:
    """Apply override fields to a live ORBEngine or LSIEngine."""
    from .engine import _parse_time

    time_fields = {"orb_start", "orb_end", "entry_start", "entry_end",
                   "flat_start", "flat_end"}

    _validate_exit_mode_update(engine, fields)

    for key, value in fields.items():
        setattr(engine, key, value)

    # Re-parse cached time objects if any time field changed
    if time_fields & fields.keys():
        if hasattr(engine, "_orb_start_t"):
            engine._orb_start_t = _parse_time(engine.orb_start)
            engine._orb_end_t = _parse_time(engine.orb_end)
        engine._entry_start_t = _parse_time(engine.entry_start)
        engine._entry_end_t = _parse_time(engine.entry_end)
        engine._flat_start_t = _parse_time(engine.flat_start)
        engine._flat_end_t = _parse_time(engine.flat_end)


def _apply_defaults_to_engine(engine, session_name: str, config: dict) -> None:
    """Reset engine fields back to config defaults."""
    from .engine import _parse_time
    from .main import SESSION_CONFIGS, LSI_SESSION_CONFIGS
    from .overrides import LSI_EDITABLE_FIELDS

    risk = config.get("risk", {})

    if _is_lsi_engine(engine):
        defaults = LSI_SESSION_CONFIGS.get(session_name, {})
        for key in LSI_EDITABLE_FIELDS:
            if key in defaults:
                setattr(engine, key, defaults[key])
            elif key == "risk_usd":
                setattr(engine, key, risk.get("risk_usd", 250))
            elif key == "min_qty":
                setattr(engine, key, risk.get("min_qty", 1.0))
            elif key == "max_single_risk_usd":
                risk_usd = getattr(engine, "risk_usd", risk.get("risk_usd", 250))
                setattr(engine, key, 1.5 * risk_usd)
            elif key == "lsi_variant":
                setattr(engine, key, "legacy-LSI")
            elif key == "exit_mode":
                setattr(engine, key, "split")
    else:
        defaults = SESSION_CONFIGS.get(session_name, {})
        for key in EDITABLE_FIELDS:
            if key in defaults:
                setattr(engine, key, defaults[key])
            elif key == "risk_usd":
                setattr(engine, key, risk.get("risk_usd", 250))
            elif key == "min_qty":
                setattr(engine, key, risk.get("min_qty", 1.0))
            elif key == "max_single_risk_usd":
                risk_usd = getattr(engine, "risk_usd", risk.get("risk_usd", 250))
                setattr(engine, key, 1.5 * risk_usd)
            elif key == "be_offset_ticks":
                setattr(engine, key, risk.get("be_offset_ticks", 0))
            elif key == "exit_mode":
                setattr(engine, key, "split")

    # Re-parse cached time objects
    if hasattr(engine, "_orb_start_t"):
        engine._orb_start_t = _parse_time(engine.orb_start)
        engine._orb_end_t = _parse_time(engine.orb_end)
    engine._entry_start_t = _parse_time(engine.entry_start)
    engine._entry_end_t = _parse_time(engine.entry_end)
    engine._flat_start_t = _parse_time(engine.flat_start)
    engine._flat_end_t = _parse_time(engine.flat_end)


def _is_lsi_engine(engine) -> bool:
    """Check if an engine is an LSIEngine (vs ORBEngine)."""
    return hasattr(engine, "qty_multiplier") and not hasattr(engine, "orb_start")


def _defaults_for_session(name: str) -> dict:
    """Get the raw config defaults for a session (editable fields only)."""
    from .main import SESSION_CONFIGS, LSI_SESSION_CONFIGS

    cfg = LSI_SESSION_CONFIGS.get(name)
    if cfg is not None:
        from .overrides import LSI_EDITABLE_FIELDS
        defaults = {k: v for k, v in cfg.items() if k in LSI_EDITABLE_FIELDS}
        defaults.setdefault("exit_mode", "split")
        return defaults

    cfg = SESSION_CONFIGS.get(name, {})
    defaults = {k: v for k, v in cfg.items() if k in EDITABLE_FIELDS}
    defaults.setdefault("exit_mode", "split")
    return defaults


def _session_info(engine) -> dict:
    """Extract session config info from an engine instance."""
    if _is_lsi_engine(engine):
        regime_gates = list(getattr(engine, "regime_gates", ()) or ())
        return {
            "type": "lsi",
            "config_name": engine.config_name,
            "sweep_start": engine.sweep_start,
            "sweep_end": engine.sweep_end,
            "entry_start": engine.entry_start,
            "entry_end": engine.entry_end,
            "flat_start": engine.flat_start,
            "flat_end": engine.flat_end,
            "atr_length": engine.atr_length,
            "rr": engine.rr,
            "tp1_ratio": engine.tp1_ratio,
            "exit_mode": getattr(engine, "exit_mode", "split"),
            "min_gap_atr_pct": engine.min_gap_atr_pct,
            "min_stop_points": engine.min_stop_points,
            "stop_atr_pct": getattr(engine, "stop_atr_pct", 0.0),
            "fvg_window_right": engine.fvg_window_right,
            "fvg_window_left": engine.fvg_window_left,
            "lsi_entry_mode": engine.lsi_entry_mode,
            "lsi_stop_mode": getattr(engine, "lsi_stop_mode", "absolute"),
            "lsi_target_mode": getattr(engine, "lsi_target_mode", "risk"),
            "lsi_confirmation_mode": getattr(engine, "lsi_confirmation_mode", "inversion"),
            "lsi_variant": engine.lsi_variant,
            "lsi_reset_swing_window_on_new_day": getattr(engine, "lsi_reset_swing_window_on_new_day", True),
            "base_bar_minutes": getattr(engine, "base_bar_minutes", 5),
            "cisd_min_leg_bars": getattr(engine, "cisd_min_leg_bars", None),
            "cisd_min_leg_atr_pct": getattr(engine, "cisd_min_leg_atr_pct", None),
            "cisd_max_leg_bars": getattr(engine, "cisd_max_leg_bars", None),
            "htf_level_tf_minutes": engine.htf_level_tf_minutes,
            "htf_n_left": engine.htf_n_left,
            "htf_trade_max_per_session": engine.htf_trade_max_per_session,
            "max_fvg_to_inversion_bars": engine.max_fvg_to_inversion_bars,
            "risk_usd": engine.risk_usd,
            "point_value": engine.point_value,
            "min_qty": engine.min_qty,
            "max_single_risk_usd": engine.max_single_risk_usd,
            "qty_step": engine.qty_step,
            "qty_multiplier": engine.qty_multiplier,
            "min_tick": engine.min_tick,
            "long_only": engine.long_only,
            "excluded_dow": engine.excluded_dow,
            "exec_ticker": _broker_ticker_from_engine(engine),
            "exec_root_ticker": getattr(engine, "exec_ticker", ""),
            "signal_contract": getattr(engine, "_signal_contract", "") or None,
            "exec_contract": getattr(engine, "_exec_contract", "") or None,
            "signal_ticker": _signal_ticker_from_engine(engine),
            "regime_gate": regime_gates[0] if len(regime_gates) == 1 else None,
            "regime_gates": regime_gates,
        }
    regime_gates = list(getattr(engine, "regime_gates", ()) or ())
    return {
        "type": "continuation",
        "config_name": engine.config_name,
        "orb_start": engine.orb_start,
        "orb_end": engine.orb_end,
        "entry_start": engine.entry_start,
        "entry_end": engine.entry_end,
        "flat_start": engine.flat_start,
        "flat_end": engine.flat_end,
        "atr_length": engine.atr_length,
        "stop_atr_pct": engine.stop_atr_pct,
        "stop_basis": engine.stop_basis,
        "stop_orb_pct": engine.stop_orb_pct,
        "min_gap_atr_pct": engine.min_gap_atr_pct,
        "max_gap_atr_pct": engine.max_gap_atr_pct,
        "gap_filter_basis": engine.gap_filter_basis,
        "min_gap_orb_pct": engine.min_gap_orb_pct,
        "rr": engine.rr,
        "tp1_ratio": engine.tp1_ratio,
        "exit_mode": getattr(engine, "exit_mode", "split"),
        "risk_usd": engine.risk_usd,
        "point_value": engine.point_value,
        "min_qty": engine.min_qty,
        "max_single_risk_usd": engine.max_single_risk_usd,
        "qty_step": engine.qty_step,
        "be_offset_ticks": engine.be_offset_ticks,
        "min_tick": engine.min_tick,
        "long_only": engine.long_only,
        "icf_enabled": engine.icf_enabled,
        "excluded_dow": engine.excluded_dow,
        "fomc_exclusion": engine.fomc_exclusion,
        "min_stop_pts": engine.min_stop_pts,
        "min_tp1_pts": engine.min_tp1_pts,
        "exec_ticker": _broker_ticker_from_engine(engine),
        "exec_root_ticker": getattr(engine, "exec_ticker", ""),
        "signal_contract": getattr(engine, "_signal_contract", "") or None,
        "exec_contract": getattr(engine, "_exec_contract", "") or None,
        "signal_ticker": _signal_ticker_from_engine(engine),
        "regime_gate": regime_gates[0] if len(regime_gates) == 1 else None,
        "regime_gates": regime_gates,
        "structure_gate": getattr(engine, "structure_gate", None),
        "ath_block_min_pct": getattr(engine, "ath_block_min_pct", 0.0),
        "ath_block_max_pct": getattr(engine, "ath_block_max_pct", 0.0),
        "max_prior_rolling_atr_pct": getattr(engine, "max_prior_rolling_atr_pct", 0.0),
        "max_orb_range_pct": getattr(engine, "max_orb_range_pct", 0.0),
    }
