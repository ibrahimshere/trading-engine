"""Main DB tracking for backtests, optimization runs, and execution state."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import os as _os

DEFAULT_MAIN_DB_URL = "http://143.110.148.234:8100"
DEFAULT_BACKTEST_RISK_USD = 5000.0


def _resolve_main_db_url() -> str:
    """Resolve the preferred main DB API URL.

    MAIN_DB_URL is the canonical name. EXPERIMENTS_DB_URL remains as a
    compatibility alias for older scripts and service env files.
    """
    if "MAIN_DB_URL" in _os.environ:
        return _os.environ.get("MAIN_DB_URL", "").rstrip("/")
    if "EXPERIMENTS_DB_URL" in _os.environ:
        return _os.environ.get("EXPERIMENTS_DB_URL", "").rstrip("/")
    return DEFAULT_MAIN_DB_URL


MAIN_DB_URL = _resolve_main_db_url()
if MAIN_DB_URL:
    _os.environ["MAIN_DB_URL"] = MAIN_DB_URL
    _os.environ.setdefault("EXPERIMENTS_DB_URL", MAIN_DB_URL)

DB_PATH = Path(
    _os.environ.get("MAIN_DB_PATH")
    or _os.environ.get("EXPERIMENTS_DB_PATH")
    or str(Path(__file__).resolve().parents[2] / "data" / "results" / "experiments.db")
)
BACKUP_DIR = DB_PATH.parent / "backups"
MAX_BACKUPS = 20  # Keep last 20 backups


def backup_db() -> Path | None:
    """Create a timestamped backup of the local main DB before destructive operations.

    Returns the backup path, or None if the DB doesn't exist.
    Keeps the last MAX_BACKUPS backups, pruning oldest.
    """
    if not DB_PATH.exists():
        return None

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"main_{ts}.db"
    shutil.copy2(DB_PATH, backup_path)

    # Prune old backups
    backups = sorted(BACKUP_DIR.glob("main_*.db"))
    while len(backups) > MAX_BACKUPS:
        backups.pop(0).unlink()

    return backup_path

# ---------------------------------------------------------------------------
# Single source of truth for strategy param columns.
# To add a new param: just add an entry here. The schema DDL, migrations,
# log_run(), list_backtest_history(), and query_runs() all derive from this.
# ---------------------------------------------------------------------------
PARAM_COLUMNS: dict[str, str] = {
    # Global
    "rr": "REAL",
    "tp1_ratio": "REAL",
    "exit_mode": "TEXT",
    "runner_trail_mode": "TEXT",
    "runner_trail_trigger_r": "REAL",
    "runner_trail_stop_r": "REAL",
    "runner_trail_step_r": "REAL",
    "runner_trail_gap_r": "REAL",
    "runner_trail_atr_pct": "REAL",
    "risk_usd": "REAL",
    "atr_length": "INTEGER",

    "min_qty": "REAL",
    "qty_step": "REAL",
    "point_value": "REAL",
    # NY session
    "ny_stop_atr_pct": "REAL",
    "ny_min_gap_atr_pct": "REAL",
    "ny_stop_orb_pct": "REAL",
    "ny_min_gap_orb_pct": "REAL",
    "ny_max_prior_atr_pct": "REAL",
    "ny_max_prior_rolling_atr_pct": "REAL",
    "ny_max_orb_range_pct": "REAL",
    "ny_orb_window": "TEXT",
    "ny_entry_window": "TEXT",
    "ny_flat_window": "TEXT",
    # Asia session
    "asia_stop_atr_pct": "REAL",
    "asia_min_gap_atr_pct": "REAL",
    "asia_stop_orb_pct": "REAL",
    "asia_min_gap_orb_pct": "REAL",
    "asia_max_prior_atr_pct": "REAL",
    "asia_max_prior_rolling_atr_pct": "REAL",
    "asia_max_orb_range_pct": "REAL",
    "asia_orb_window": "TEXT",
    "asia_entry_window": "TEXT",
    "asia_flat_window": "TEXT",
    # London session
    "ldn_stop_atr_pct": "REAL",
    "ldn_min_gap_atr_pct": "REAL",
    "ldn_stop_orb_pct": "REAL",
    "ldn_min_gap_orb_pct": "REAL",
    "ldn_max_prior_atr_pct": "REAL",
    "ldn_max_prior_rolling_atr_pct": "REAL",
    "ldn_max_orb_range_pct": "REAL",
    "ldn_orb_window": "TEXT",
    "ldn_entry_window": "TEXT",
    "ldn_flat_window": "TEXT",
    # VWAP Reversion params
    "deviation_atr_pct": "REAL",
    "deviation_std": "REAL",
    "deviation_mode": "TEXT",
    "rejection_mode": "TEXT",
    "tp2_mode": "TEXT",
    "vwap_anchor": "TEXT",
    "stop_atr_buffer_pct": "REAL",
    # Strategy type
    "strategy": "TEXT",
    # LSI params
    "lsi_n_left": "INTEGER",
    "lsi_n_right": "INTEGER",
    "lsi_fvg_window_left": "INTEGER",
    "lsi_fvg_window_right": "INTEGER",
    "lsi_stop_mode": "TEXT",
    "lsi_target_mode": "TEXT",
    "lsi_entry_mode": "TEXT",
    "lsi_confirmation_mode": "TEXT",
    "cisd_min_leg_bars": "INTEGER",
    "cisd_min_leg_atr_pct": "REAL",
    "cisd_max_leg_bars": "INTEGER",
    "lsi_first_fvg_only": "INTEGER",
    "lsi_clean_path": "INTEGER",
    "lsi_be_swing_n_left": "INTEGER",
    "lsi_cancel_on_swing": "INTEGER",
    "lsi_lrlr_enabled": "INTEGER",
    "lsi_lrlr_gate": "TEXT",
    "lsi_lrlr_swing_n_left": "INTEGER",
    "lsi_lrlr_swing_n_right": "INTEGER",
    "lsi_lrlr_min_pivots": "INTEGER",
    "lsi_lrlr_lookback_minutes": "INTEGER",
    "lsi_lrlr_max_pivot_gap_minutes": "INTEGER",
    "lsi_lrlr_max_cluster_span_minutes": "INTEGER",
    "lsi_lrlr_max_price_span_atr": "REAL",
    "lsi_lrlr_monotonic_tolerance_atr": "REAL",
    "lsi_lrlr_line_tolerance_atr": "REAL",
    "lsi_lrlr_tp1_path_enabled": "INTEGER",
    "lsi_lrlr_tp1_buffer_atr": "REAL",
    "htf_level_tf_minutes": "INTEGER",
    "htf_n_left": "INTEGER",
    "htf_trade_max_per_session": "INTEGER",
    "htf_lsi_inversion_ordinal": "INTEGER",
    "max_fvg_to_inversion_bars": "INTEGER",
    "htf_lsi_include_htf_levels": "INTEGER",
    "htf_lsi_reference_levels": "TEXT",
    "data_sweep_min_daily_atr_pct": "REAL",
    "data_sweep_require_session_extreme": "INTEGER",
    "data_sweep_event_types": "TEXT",
    "data_sweep_release_window_minutes": "INTEGER",
}

# Params that are always present (non-nullable) vs per-session (nullable)
_GLOBAL_PARAMS = {"rr", "tp1_ratio", "exit_mode",
                  "runner_trail_mode", "runner_trail_trigger_r",
                  "runner_trail_stop_r", "runner_trail_step_r",
                  "runner_trail_gap_r", "runner_trail_atr_pct",
                  "risk_usd", "atr_length",
                  "min_qty", "qty_step", "point_value",
                  "htf_level_tf_minutes", "htf_n_left",
                  "htf_trade_max_per_session", "htf_lsi_inversion_ordinal",
                  "max_fvg_to_inversion_bars",
                  "htf_lsi_include_htf_levels", "htf_lsi_reference_levels",
                  "data_sweep_min_daily_atr_pct", "data_sweep_require_session_extreme",
                  "data_sweep_event_types", "data_sweep_release_window_minutes"}

# ---------------------------------------------------------------------------
# Metric columns promoted from json_extract to dedicated columns.
# Same self-driving pattern: DDL, migration, backfill, INSERT, SELECT all
# derive from this dict.
# ---------------------------------------------------------------------------
METRIC_COLUMNS: dict[str, str] = {
    "total_pnl_usd": "REAL",
    "win_rate": "REAL",
    "sharpe_ratio": "REAL",
    "max_drawdown_usd": "REAL",
    "profit_factor": "REAL",
    "sortino_ratio": "REAL",
    "calmar_ratio": "REAL",
    "total_r": "REAL",
    "max_drawdown_r": "REAL",
}

_param_ddl = ",\n    ".join(f"{col} {dtype}" for col, dtype in PARAM_COLUMNS.items())
_metric_ddl = ",\n    ".join(f"{col} {dtype}" for col, dtype in METRIC_COLUMNS.items())

_SCHEMA = f"""\
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    run_type TEXT NOT NULL DEFAULT 'backtest',
    experiment_name TEXT,
    notes TEXT,
    git_hash TEXT,
    config_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    total_trades INTEGER NOT NULL,
    result_file TEXT,
    sessions TEXT,
    instrument TEXT,
    date_start TEXT,
    date_end TEXT,
    {_param_ddl},
    {_metric_ddl}
);
"""

_OPTIMIZATIONS_SCHEMA = """\
CREATE TABLE IF NOT EXISTS optimizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    git_hash TEXT,
    instrument TEXT,
    sessions TEXT,
    total_combinations INTEGER NOT NULL,
    swept_params_json TEXT NOT NULL,
    best_by_sharpe_json TEXT,
    best_by_pnl_json TEXT,
    best_by_pf_json TEXT,
    all_results_json TEXT NOT NULL
);
"""

_TESTING_PLAN_SCHEMA = """\
CREATE TABLE IF NOT EXISTS testing_plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    notes TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_testing_plan_instrument ON testing_plan(instrument);
"""

_RISK_ENGINE_LAYOUTS_SCHEMA = """\
CREATE TABLE IF NOT EXISTS risk_engine_layouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    account_risk REAL NOT NULL,
    strategies_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_SAVED_CONFIGS_SCHEMA = """\
CREATE TABLE IF NOT EXISTS saved_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    name TEXT NOT NULL,
    notes TEXT,
    instrument TEXT NOT NULL,
    sessions TEXT NOT NULL,
    strategy TEXT NOT NULL,
    config_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_saved_configs_instrument ON saved_configs(instrument);
CREATE INDEX IF NOT EXISTS idx_saved_configs_strategy ON saved_configs(strategy);
"""

_NEWS_STRADDLE_SCHEMA = """\
CREATE TABLE IF NOT EXISTS news_straddle_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    instrument TEXT NOT NULL,
    buffer_points REAL NOT NULL,
    target_points REAL NOT NULL,
    observation_window_seconds INTEGER NOT NULL,
    event_types TEXT NOT NULL,
    date_start TEXT,
    date_end TEXT,
    fills INTEGER,
    target_hit_rate REAL,
    whipsaw_rate REAL,
    pct_profitable REAL,
    avg_mfe REAL,
    avg_mae REAL,
    avg_final_points REAL,
    stop_loss_points REAL,
    result_json TEXT NOT NULL
);
"""

_LIVE_TRADES_SCHEMA = """\
CREATE TABLE IF NOT EXISTS live_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    session TEXT NOT NULL,
    date TEXT NOT NULL,
    direction INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    stop_price REAL NOT NULL,
    tp1_price REAL NOT NULL,
    tp2_price REAL NOT NULL,
    exit_type TEXT NOT NULL,
    tp1_hit INTEGER NOT NULL DEFAULT 0,
    exit_timestamp TEXT NOT NULL,
    config_name TEXT NOT NULL DEFAULT '',
    r_result REAL,
    entry_timestamp TEXT,
    ticker TEXT,
    exec_ticker TEXT,
    leg TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_live_trades_date ON live_trades(date);
CREATE INDEX IF NOT EXISTS idx_live_trades_session ON live_trades(session);
CREATE INDEX IF NOT EXISTS idx_live_trades_config ON live_trades(config_name);
"""

_EXECUTION_TRADE_LOGS_SCHEMA = """\
CREATE TABLE IF NOT EXISTS execution_trade_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    config TEXT,
    asset TEXT,
    session TEXT NOT NULL,
    event TEXT NOT NULL,
    details_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_exec_trade_logs_ts ON execution_trade_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_exec_trade_logs_session ON execution_trade_logs(session);
CREATE INDEX IF NOT EXISTS idx_exec_trade_logs_config ON execution_trade_logs(config);
"""

_EXECUTION_MAIN_LOGS_SCHEMA = """\
CREATE TABLE IF NOT EXISTS execution_main_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    level TEXT NOT NULL,
    logger TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_exec_main_logs_ts ON execution_main_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_exec_main_logs_level ON execution_main_logs(level);
"""

_EXECUTION_WEBHOOK_LOGS_SCHEMA = """\
CREATE TABLE IF NOT EXISTS execution_webhook_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    account TEXT NOT NULL,
    status TEXT NOT NULL,
    http_code TEXT,
    latency TEXT,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_exec_webhook_logs_ts ON execution_webhook_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_exec_webhook_logs_account ON execution_webhook_logs(account);
"""

_EXECUTION_CONFIGS_SCHEMA = """\
CREATE TABLE IF NOT EXISTS execution_configs (
    config_name TEXT PRIMARY KEY,
    enabled INTEGER,
    max_open_contracts REAL,
    config_json TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS execution_config_webhooks (
    config_name TEXT NOT NULL,
    webhook_index INTEGER NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL,
    paused INTEGER NOT NULL DEFAULT 0,
    multiplier REAL NOT NULL DEFAULT 1.0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (config_name, webhook_index),
    FOREIGN KEY (config_name) REFERENCES execution_configs(config_name) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_execution_config_webhooks_config
    ON execution_config_webhooks(config_name);
"""

_PAYOUTS_SCHEMA = """\
CREATE TABLE IF NOT EXISTS payouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    config_name TEXT NOT NULL,
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_payouts_config ON payouts(config_name);
"""

_REGIME_REPORTS_SCHEMA = """\
CREATE TABLE IF NOT EXISTS regime_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    instrument TEXT NOT NULL,
    sessions TEXT,
    backtest_result_id TEXT NOT NULL,
    backtest_name TEXT,
    date_start TEXT,
    date_end TEXT,
    methods TEXT NOT NULL,
    hmm_states INTEGER,
    lstm_clusters INTEGER,
    hmm_total_r REAL,
    lstm_total_r REAL,
    hmm_best_pf REAL,
    lstm_best_pf REAL,
    report_json TEXT NOT NULL
);
"""

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def init_db() -> Path:
    """Create the data directory and tables if they don't exist.

    Returns the path to the SQLite database file.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(_SCHEMA)
        conn.executescript(_OPTIMIZATIONS_SCHEMA)
        conn.executescript(_TESTING_PLAN_SCHEMA)
        conn.executescript(_NEWS_STRADDLE_SCHEMA)
        conn.executescript(_RISK_ENGINE_LAYOUTS_SCHEMA)
        conn.executescript(_SAVED_CONFIGS_SCHEMA)
        conn.executescript(_REGIME_REPORTS_SCHEMA)
        conn.executescript(_LIVE_TRADES_SCHEMA)
        conn.executescript(_EXECUTION_TRADE_LOGS_SCHEMA)
        conn.executescript(_EXECUTION_MAIN_LOGS_SCHEMA)
        conn.executescript(_EXECUTION_WEBHOOK_LOGS_SCHEMA)
        conn.executescript(_EXECUTION_CONFIGS_SCHEMA)
        conn.executescript(_PAYOUTS_SCHEMA)

        # Migrate: add live execution display fields if missing
        live_existing = {row[1] for row in conn.execute("PRAGMA table_info(live_trades)").fetchall()}
        live_new_cols = {
            "entry_timestamp": "TEXT",
            "ticker": "TEXT",
            "exec_ticker": "TEXT",
            "leg": "TEXT",
            "net_pnl_usd": "REAL",
            "net_r_result": "REAL",
            "commission_usd": "REAL",
            "qty": "REAL",
        }
        for col, dtype in live_new_cols.items():
            if col not in live_existing:
                conn.execute(f"ALTER TABLE live_trades ADD COLUMN {col} {dtype}")

        # Migrate: add stop_loss_points to news_straddle_runs if missing
        ns_existing = {row[1] for row in conn.execute("PRAGMA table_info(news_straddle_runs)").fetchall()}
        if "stop_loss_points" not in ns_existing:
            conn.execute("ALTER TABLE news_straddle_runs ADD COLUMN stop_loss_points REAL")
            conn.execute(
                "UPDATE news_straddle_runs SET stop_loss_points = json_extract(result_json, '$.config.stop_loss_points')"
            )
        if "starred" not in ns_existing:
            conn.execute("ALTER TABLE news_straddle_runs ADD COLUMN starred INTEGER NOT NULL DEFAULT 0")

        # Migrate: add columns to optimizations if missing
        opt_existing = {row[1] for row in conn.execute("PRAGMA table_info(optimizations)").fetchall()}
        if "experiment_name" not in opt_existing:
            conn.execute("ALTER TABLE optimizations ADD COLUMN experiment_name TEXT")

        # Migrate: add columns if missing
        existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
        if "trades_json" not in existing:
            conn.execute("ALTER TABLE runs ADD COLUMN trades_json TEXT")
        if "equity_json" not in existing:
            conn.execute("ALTER TABLE runs ADD COLUMN equity_json TEXT")
        if "starred" not in existing:
            conn.execute("ALTER TABLE runs ADD COLUMN starred INTEGER DEFAULT 0")
        if "hidden" not in existing:
            conn.execute("ALTER TABLE runs ADD COLUMN hidden INTEGER DEFAULT 0")

        # Migrate: add dedicated param columns
        new_param_cols: list[str] = []
        for col, dtype in PARAM_COLUMNS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {col} {dtype}")
                new_param_cols.append(col)

        # Backfill newly added param columns from config_json
        if new_param_cols:
            backfill_sets = ", ".join(
                f"{col} = json_extract(config_json, '$.{col}')"
                for col in new_param_cols
            )
            conn.execute(f"UPDATE runs SET {backfill_sets} WHERE {new_param_cols[0]} IS NULL")

        # Migrate: add dedicated metric columns
        new_metric_cols: list[str] = []
        for col, dtype in METRIC_COLUMNS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {col} {dtype}")
                new_metric_cols.append(col)

        # Backfill newly added metric columns from metrics_json
        if new_metric_cols:
            backfill_sets = ", ".join(
                f"{col} = json_extract(metrics_json, '$.{col}')"
                for col in new_metric_cols
            )
            conn.execute(f"UPDATE runs SET {backfill_sets} WHERE {new_metric_cols[0]} IS NULL")

    return DB_PATH


def _get_git_hash() -> str:
    """Return the current HEAD git hash, or 'unknown' on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _json_default(obj):
    """JSON serializer fallback for numpy types and infinity."""
    import math
    if isinstance(obj, float) and (math.isinf(obj) or math.isnan(obj)):
        return None
    # numpy scalar types
    type_name = type(obj).__module__
    if type_name == "numpy":
        return obj.item()
    return str(obj)


def _dumps(obj) -> str:
    """Compact JSON serialization with fallback for special types."""
    return json.dumps(obj, default=_json_default, separators=(",", ":"))


# Whitelist pattern for param filter names (alphanumeric + underscores)
_SAFE_PARAM_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Default param values — used to detect non-default params for auto-naming
_DEFAULT_PARAMS: dict[str, object] = {
    "rr": 2.5,
    "tp1_ratio": 0.5,
    "exit_mode": "split",
    "runner_trail_mode": "",
    "runner_trail_trigger_r": 0.0,
    "runner_trail_stop_r": 0.0,
    "runner_trail_step_r": 1.0,
    "runner_trail_gap_r": 1.0,
    "runner_trail_atr_pct": 0.0,

    "atr_length": 14,
}


def _auto_experiment_name(
    config: dict, date_start: str, date_end: str, sessions_str: str,
) -> str:
    """Generate a human-readable experiment name from config and date range.

    Examples: ``NQ ASIA+NY 2015-2026``, ``ES NY 2024-2025 rr3``
    """
    instrument = config.get("instrument", "UNK")

    start_year = date_start[:4] if date_start and len(date_start) >= 4 else ""
    end_year = date_end[:4] if date_end and len(date_end) >= 4 else ""
    if start_year and end_year and start_year != end_year:
        year_range = f"{start_year}-{end_year}"
    elif start_year:
        year_range = start_year
    else:
        year_range = ""

    parts = [instrument, sessions_str]
    if year_range:
        parts.append(year_range)

    for param, default_val in sorted(_DEFAULT_PARAMS.items()):
        val = config.get(param)
        if val is not None and val != default_val:
            parts.append(f"{param}{val:g}" if isinstance(val, float) else f"{param}{val}")

    # Append 4-char fingerprint of session-specific params for uniqueness.
    # Runs with different session configs (stop_atr_pct, min_gap_atr_pct, etc.)
    # will always produce different names even when global params match.
    session_keys = sorted(
        k for k in config
        if any(k.startswith(p) for p in ("ny_", "asia_", "ldn_"))
    )
    if session_keys:
        fp_str = "|".join(f"{k}={config[k]}" for k in session_keys)
        fp = hashlib.md5(fp_str.encode()).hexdigest()[:4]
        parts.append(f"({fp})")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_run(
    result_dict: dict,
    result_id: str,
    run_type: str = "backtest",
    *,
    git_hash: str | None = None,
) -> int:
    """Insert a single run into the main DB.

    Args:
        result_dict: Structured result dict (as produced by results_to_dict).
        result_id: Identifier for the saved result file.
        run_type: 'backtest' or 'optimization'.
        git_hash: Pre-computed git hash (avoids repeated subprocess calls in sweeps).

    Returns:
        The rowid of the newly inserted row.
    """
    init_db()

    config = result_dict["config"]
    summary = result_dict["summary"]

    # Extract session names from config keys like "ny_orb_window" or "ny_entry_window"
    sessions: list[str] = []
    seen_sessions: set[str] = set()
    for key in config:
        if key.endswith("_orb_window") or key.endswith("_entry_window"):
            sess_name = key.split("_")[0].upper()
            if sess_name not in seen_sessions:
                sessions.append(sess_name)
                seen_sessions.add(sess_name)
    session_str = "+".join(sorted(sessions)) if sessions else ""

    # Extract date range from equity_curve or trades list
    equity_curve = result_dict.get("equity_curve", [])
    trades_list = result_dict.get("trades", [])
    dates_source = equity_curve or trades_list
    date_start = dates_source[0]["date"] if dates_source else ""
    date_end = dates_source[-1]["date"] if dates_source else ""

    # Serialize trades and equity curve
    trades_json = _dumps(trades_list) if trades_list else None
    equity_json = _dumps(equity_curve) if equity_curve else None

    experiment_name = result_dict.get("name")
    if not experiment_name:
        experiment_name = _auto_experiment_name(config, date_start, date_end, session_str)

    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_type": run_type,
        "experiment_name": experiment_name,
        "notes": result_dict.get("notes"),
        "git_hash": git_hash if git_hash is not None else _get_git_hash(),
        "config_json": json.dumps(config, default=_json_default),
        "metrics_json": json.dumps(summary, default=_json_default),
        "total_trades": int(summary["total_trades"]),
        "result_file": result_id,
        "sessions": session_str,
        "instrument": config.get("instrument", ""),
        "date_start": date_start,
        "date_end": date_end,
        "trades_json": trades_json,
        "equity_json": equity_json,
        # Dedicated param columns (driven by PARAM_COLUMNS)
        **{col: config.get(col) for col in PARAM_COLUMNS},
        # Dedicated metric columns (driven by METRIC_COLUMNS)
        **{col: summary.get(col) for col in METRIC_COLUMNS},
    }

    columns = ", ".join(row.keys())
    placeholders = ", ".join(f":{k}" for k in row.keys())
    sql = f"INSERT INTO runs ({columns}) VALUES ({placeholders})"

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(sql, row)
        return cur.lastrowid  # type: ignore[return-value]


def log_sweep_runs(
    all_results: list[tuple],
    optimization_id: str,
) -> int:
    """Log every combination from a parameter sweep.

    Args:
        all_results: List of (StrategyConfig, list[TradeResult]) tuples.
        optimization_id: Shared identifier for this sweep.

    Returns:
        The number of rows logged.
    """
    # Lazy import to avoid circular dependency
    from .results.export import results_to_dict

    # Compute git hash once for the entire sweep (avoids N subprocess calls)
    git_hash = _get_git_hash()

    count = 0
    for config, trades in all_results:
        result_dict = results_to_dict(trades, config, include_trades=False)
        log_run(result_dict, optimization_id, run_type="optimization", git_hash=git_hash)
        count += 1
    return count


# ---------------------------------------------------------------------------
# Backtest CRUD
# ---------------------------------------------------------------------------

def get_backtest_result(result_id: str) -> dict | None:
    """Load a full backtest result from the DB by result_file ID.

    Returns a BacktestResult-shaped dict with config, summary, trades, equity_curve,
    or None if not found.
    """
    init_db()

    sql = """
        SELECT config_json, metrics_json, trades_json, equity_json,
               experiment_name, notes, result_file
        FROM runs
        WHERE result_file = ? AND run_type = 'backtest'
        ORDER BY id DESC
        LIMIT 1
    """

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(sql, [result_id]).fetchone()

    if row is None:
        return None

    result: dict = {
        "config": json.loads(row["config_json"]),
        "summary": json.loads(row["metrics_json"]),
    }

    if row["trades_json"]:
        result["trades"] = json.loads(row["trades_json"])
    else:
        result["trades"] = []

    if row["equity_json"]:
        result["equity_curve"] = json.loads(row["equity_json"])
    else:
        result["equity_curve"] = []

    if row["experiment_name"]:
        result["name"] = row["experiment_name"]
    if row["notes"]:
        result["notes"] = row["notes"]

    return result


def delete_backtest_run(result_id: str) -> bool:
    """Delete a backtest from the runs table by result_file. Returns True if deleted."""
    init_db()
    backup_db()

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "DELETE FROM runs WHERE result_file = ? AND run_type = 'backtest'",
            [result_id],
        )
        return cur.rowcount > 0


def rename_backtest(result_id: str, new_name: str) -> str | None:
    """Rename a backtest's experiment_name. Returns new name, or None if not found."""
    init_db()

    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM runs WHERE result_file = ? AND run_type = 'backtest' ORDER BY id DESC LIMIT 1",
            [result_id],
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE runs SET experiment_name = ? WHERE result_file = ? AND run_type = 'backtest'",
            [new_name, result_id],
        )
        return new_name


def toggle_star(result_id: str) -> bool | None:
    """Toggle the starred flag for a backtest run. Returns the new starred state, or None if not found."""
    init_db()

    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT starred FROM runs WHERE result_file = ? AND run_type = 'backtest' ORDER BY id DESC LIMIT 1",
            [result_id],
        ).fetchone()
        if row is None:
            return None
        new_val = 0 if row[0] else 1
        conn.execute(
            "UPDATE runs SET starred = ? WHERE result_file = ? AND run_type = 'backtest'",
            [new_val, result_id],
        )
        return bool(new_val)


def toggle_hidden(result_id: str) -> bool | None:
    """Toggle the hidden flag for a backtest run. Returns the new hidden state, or None if not found."""
    init_db()

    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT hidden FROM runs WHERE result_file = ? AND run_type = 'backtest' ORDER BY id DESC LIMIT 1",
            [result_id],
        ).fetchone()
        if row is None:
            return None
        new_val = 0 if row[0] else 1
        conn.execute(
            "UPDATE runs SET hidden = ? WHERE result_file = ? AND run_type = 'backtest'",
            [new_val, result_id],
        )
        return bool(new_val)


def list_starred(limit: int = 100) -> list[dict]:
    """Return starred backtest runs, same shape as list_backtest_history()."""
    init_db()

    param_cols = ", ".join(PARAM_COLUMNS.keys())
    metric_cols = ", ".join(METRIC_COLUMNS.keys())
    sql = f"""
        SELECT
            result_file,
            timestamp,
            instrument,
            sessions,
            experiment_name,
            notes,
            total_trades,
            date_start,
            date_end,
            starred,
            hidden,
            {param_cols},
            {metric_cols}
        FROM runs
        WHERE run_type = 'backtest' AND starred = 1
        ORDER BY id DESC
        LIMIT ?
    """

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, [limit]).fetchall()

    items: list[dict] = []
    for row in rows:
        sessions_str = row["sessions"] or ""
        item: dict = {
            "id": row["result_file"] or "",
            "timestamp": row["timestamp"] or "",
            "instrument": row["instrument"] or "",
            "sessions": sessions_str.split("+") if sessions_str else [],
            "total_trades": row["total_trades"] or 0,
            "date_start": row["date_start"] or "",
            "date_end": row["date_end"] or "",
            "starred": True,
            "hidden": bool(row["hidden"]),
        }
        for col in PARAM_COLUMNS:
            val = row[col]
            if col in _GLOBAL_PARAMS or val is not None:
                item[col] = val
        for col in METRIC_COLUMNS:
            item[col] = row[col] or 0
        if row["experiment_name"]:
            item["name"] = row["experiment_name"]
        if row["notes"]:
            item["notes"] = row["notes"]
        items.append(item)

    return items


# ---------------------------------------------------------------------------
# Optimization CRUD
# ---------------------------------------------------------------------------

def log_optimization(result_dict: dict, result_id: str) -> int:
    """Insert an optimization result into the optimizations table.

    Args:
        result_dict: Grid sweep result dict (from grid_results_to_dict).
        result_id: Unique identifier for this optimization run.

    Returns:
        The rowid of the newly inserted row.
    """
    init_db()

    # Extract instrument and sessions from first result's config
    all_results = result_dict.get("all_results", [])
    instrument = ""
    sessions_set: set[str] = set()
    if all_results:
        config = all_results[0].get("config", {})
        instrument = config.get("instrument", "")
        for key in config:
            if key.endswith("_orb_window") or key.endswith("_entry_window"):
                sessions_set.add(key.split("_")[0].upper())
    session_str = "+".join(sorted(sessions_set))

    # Auto-generate experiment name from instrument, sessions, swept params
    swept_params = result_dict.get("swept_params", {})
    swept_names = ", ".join(sorted(swept_params.keys())) if swept_params else ""
    n_combos = result_dict.get("total_combinations", len(all_results))
    name_parts = [instrument or "UNK", session_str or "UNK"]
    if swept_names:
        name_parts.append(swept_names)
    name_parts.append(f"({n_combos}c)")
    experiment_name = " ".join(name_parts)

    row = {
        "result_id": result_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_hash": _get_git_hash(),
        "instrument": instrument,
        "sessions": session_str,
        "experiment_name": experiment_name,
        "total_combinations": result_dict.get("total_combinations", len(all_results)),
        "swept_params_json": _dumps(result_dict.get("swept_params", {})),
        "best_by_sharpe_json": _dumps(result_dict.get("best_by_sharpe")),
        "best_by_pnl_json": _dumps(result_dict.get("best_by_pnl")),
        "best_by_pf_json": _dumps(result_dict.get("best_by_profit_factor")),
        "all_results_json": _dumps(all_results),
    }

    columns = ", ".join(row.keys())
    placeholders = ", ".join(f":{k}" for k in row.keys())
    sql = f"INSERT OR REPLACE INTO optimizations ({columns}) VALUES ({placeholders})"

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(sql, row)
        return cur.lastrowid  # type: ignore[return-value]


def list_optimization_history(limit: int = 100) -> list[dict]:
    """Return optimization runs shaped for the frontend OptimizationHistoryItem."""
    init_db()

    sql = """
        SELECT result_id, timestamp, instrument, sessions,
               total_combinations, swept_params_json,
               best_by_sharpe_json, best_by_pnl_json,
               experiment_name
        FROM optimizations
        ORDER BY id DESC
        LIMIT ?
    """

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, [limit]).fetchall()

    items: list[dict] = []
    for row in rows:
        swept_params = json.loads(row["swept_params_json"]) if row["swept_params_json"] else {}
        sessions_str = row["sessions"] or ""

        best_sharpe = 0.0
        best_pnl_usd = 0.0
        risk_usd = DEFAULT_BACKTEST_RISK_USD

        if row["best_by_sharpe_json"]:
            best = json.loads(row["best_by_sharpe_json"])
            if best:
                best_sharpe = best.get("summary", {}).get("sharpe_ratio", 0)
                risk_usd = best.get("config", {}).get("risk_usd", DEFAULT_BACKTEST_RISK_USD)

        if row["best_by_pnl_json"]:
            best = json.loads(row["best_by_pnl_json"])
            if best:
                best_pnl_usd = best.get("summary", {}).get("total_pnl_usd", 0)

        item: dict = {
            "id": row["result_id"],
            "timestamp": row["timestamp"],
            "instrument": row["instrument"] or "",
            "sessions": sessions_str.split("+") if sessions_str else [],
            "risk_usd": risk_usd,
            "swept_params": list(swept_params.keys()),
            "total_combinations": row["total_combinations"],
            "best_sharpe": best_sharpe,
            "best_pnl_usd": best_pnl_usd,
        }
        if row["experiment_name"]:
            item["name"] = row["experiment_name"]
        items.append(item)

    return items


def get_optimization_result(result_id: str) -> dict | None:
    """Load a full optimization result from the DB by result_id."""
    init_db()

    sql = """
        SELECT result_id, timestamp, instrument, sessions,
               total_combinations, swept_params_json,
               best_by_sharpe_json, best_by_pnl_json, best_by_pf_json,
               all_results_json
        FROM optimizations
        WHERE result_id = ?
    """

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(sql, [result_id]).fetchone()

    if row is None:
        return None

    result: dict = {
        "total_combinations": row["total_combinations"],
        "all_results": json.loads(row["all_results_json"]),
    }

    if row["swept_params_json"]:
        result["swept_params"] = json.loads(row["swept_params_json"])

    if row["best_by_sharpe_json"]:
        val = json.loads(row["best_by_sharpe_json"])
        if val:
            result["best_by_sharpe"] = val

    if row["best_by_pnl_json"]:
        val = json.loads(row["best_by_pnl_json"])
        if val:
            result["best_by_pnl"] = val

    if row["best_by_pf_json"]:
        val = json.loads(row["best_by_pf_json"])
        if val:
            result["best_by_profit_factor"] = val

    return result


def delete_optimization_run(result_id: str) -> bool:
    """Delete an optimization from the optimizations table. Returns True if deleted."""
    init_db()
    backup_db()

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "DELETE FROM optimizations WHERE result_id = ?",
            [result_id],
        )
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Querying
# ---------------------------------------------------------------------------

def query_runs(**filters) -> list[dict]:
    """Query runs with optional filters.

    Keyword Args:
        date_from: Filter timestamp >= value.
        date_to: Filter timestamp <= value.
        instrument: Exact match on instrument column.
        sessions: Exact match on sessions column (e.g. "NY" or "NY+Asia").
        min_profit_factor: Minimum profit_factor from metrics_json.
        min_sharpe: Minimum sharpe_ratio from metrics_json.
        experiment_name: LIKE match on experiment_name column.
        run_type: Exact match ('backtest' or 'optimization').
        param_filters: Dict mapping param name to (min, max) tuple,
            filtered via json_extract on config_json.
        limit: Max rows returned (default 100).

    Returns:
        List of dicts with all columns plus extracted key metrics.
    """
    init_db()

    clauses: list[str] = []
    params: list = []

    date_from = filters.get("date_from")
    if date_from is not None:
        clauses.append("timestamp >= ?")
        params.append(date_from)

    date_to = filters.get("date_to")
    if date_to is not None:
        clauses.append("timestamp <= ?")
        params.append(date_to)

    instrument = filters.get("instrument")
    if instrument is not None:
        clauses.append("instrument = ?")
        params.append(instrument)

    sessions = filters.get("sessions")
    if sessions is not None:
        clauses.append("sessions = ?")
        params.append(sessions)

    min_profit_factor = filters.get("min_profit_factor")
    if min_profit_factor is not None:
        clauses.append("profit_factor >= ?")
        params.append(min_profit_factor)

    min_sharpe = filters.get("min_sharpe")
    if min_sharpe is not None:
        clauses.append("sharpe_ratio >= ?")
        params.append(min_sharpe)

    experiment_name = filters.get("experiment_name")
    if experiment_name is not None:
        clauses.append("experiment_name LIKE ?")
        params.append(f"%{experiment_name}%")

    run_type = filters.get("run_type")
    if run_type is not None:
        clauses.append("run_type = ?")
        params.append(run_type)

    param_filters: dict[str, tuple[float, float]] | None = filters.get("param_filters")
    if param_filters:
        for param_name, (lo, hi) in param_filters.items():
            if not _SAFE_PARAM_RE.match(param_name):
                raise ValueError(f"Invalid param filter name: {param_name!r}")
            if param_name in PARAM_COLUMNS or param_name in METRIC_COLUMNS:
                clauses.append(f"{param_name} >= ?")
                params.append(lo)
                clauses.append(f"{param_name} <= ?")
                params.append(hi)
            else:
                clauses.append(f"json_extract(config_json, '$.{param_name}') >= ?")
                params.append(lo)
                clauses.append(f"json_extract(config_json, '$.{param_name}') <= ?")
                params.append(hi)

    limit = filters.get("limit", 100)

    where = ""
    if clauses:
        where = "WHERE " + " AND ".join(clauses)

    metric_cols = ", ".join(METRIC_COLUMNS.keys())
    sql = f"""
        SELECT id, timestamp, run_type, experiment_name, notes, git_hash,
            config_json, metrics_json, total_trades, result_file,
            sessions, instrument, date_start, date_end,
            {metric_cols}
        FROM runs
        {where}
        ORDER BY id DESC
        LIMIT ?
    """
    params.append(limit)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()

    return [dict(row) for row in rows]


def list_recent_runs(limit: int = 50) -> list[dict]:
    """Return the most recent runs, newest first."""
    return query_runs(limit=limit)


def list_backtest_history(limit: int = 100) -> list[dict]:
    """Return backtest runs shaped for the frontend BacktestHistoryItem.

    Returns list of dicts with: id, timestamp, instrument, sessions,
    risk_usd, total_pnl_usd, total_trades, win_rate, date_start,
    date_end, name, notes.
    """
    init_db()

    param_cols = ", ".join(PARAM_COLUMNS.keys())
    metric_cols = ", ".join(METRIC_COLUMNS.keys())
    sql = f"""
        SELECT
            result_file,
            timestamp,
            instrument,
            sessions,
            experiment_name,
            notes,
            total_trades,
            date_start,
            date_end,
            starred,
            hidden,
            {param_cols},
            {metric_cols}
        FROM runs
        WHERE run_type = 'backtest'
        ORDER BY id DESC
        LIMIT ?
    """

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, [limit]).fetchall()

    items: list[dict] = []
    for row in rows:
        sessions_str = row["sessions"] or ""
        item: dict = {
            "id": row["result_file"] or "",
            "timestamp": row["timestamp"] or "",
            "instrument": row["instrument"] or "",
            "sessions": sessions_str.split("+") if sessions_str else [],
            "total_trades": row["total_trades"] or 0,
            "date_start": row["date_start"] or "",
            "date_end": row["date_end"] or "",
            "starred": bool(row["starred"]),
            "hidden": bool(row["hidden"]),
        }
        # Add param columns: globals always, session params only when present
        for col in PARAM_COLUMNS:
            val = row[col]
            if col in _GLOBAL_PARAMS or val is not None:
                item[col] = val
        # Add metric columns (always present)
        for col in METRIC_COLUMNS:
            item[col] = row[col] or 0
        if row["experiment_name"]:
            item["name"] = row["experiment_name"]
        if row["notes"]:
            item["notes"] = row["notes"]
        items.append(item)

    return items


def compare_runs(run_ids: list[int]) -> list[dict]:
    """Load full details for specific run IDs, with parsed JSON fields.

    Args:
        run_ids: List of run IDs to compare.

    Returns:
        List of dicts with config_json and metrics_json parsed into dicts.
    """
    init_db()

    if not run_ids:
        return []

    placeholders = ", ".join("?" for _ in run_ids)
    sql = f"""SELECT id, timestamp, run_type, experiment_name, notes, git_hash,
            config_json, metrics_json, total_trades, result_file,
            sessions, instrument, date_start, date_end
        FROM runs WHERE id IN ({placeholders})"""

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, run_ids).fetchall()

    results: list[dict] = []
    for row in rows:
        d = dict(row)
        d["config_json"] = json.loads(d["config_json"])
        d["metrics_json"] = json.loads(d["metrics_json"])
        results.append(d)

    return results


# ---------------------------------------------------------------------------
# Coverage queries
# ---------------------------------------------------------------------------

def get_instrument_coverage() -> list[dict]:
    """Aggregate coverage stats from the runs table, grouped by instrument."""
    init_db()

    sql = """
        SELECT
            instrument,
            SUM(CASE WHEN run_type = 'backtest' THEN 1 ELSE 0 END) AS backtest_count,
            SUM(CASE WHEN run_type = 'optimization' THEN 1 ELSE 0 END) AS optimization_count,
            MIN(date_start) AS earliest_date,
            MAX(date_end) AS latest_date,
            MAX(timestamp) AS last_run_at,
            GROUP_CONCAT(DISTINCT sessions) AS sessions_raw,
            MAX(CASE WHEN typeof(sharpe_ratio) IN ('real', 'integer') THEN sharpe_ratio END) AS best_sharpe,
            MAX(
                COALESCE(
                    json_extract(metrics_json, '$.total_r'),
                    json_extract(metrics_json, '$.avg_r') * total_trades
                )
                / MAX(1.0, (julianday(date_end) - julianday(date_start)) / 365.25)
            ) AS best_r_per_year,
            MAX(CASE WHEN typeof(win_rate) IN ('real', 'integer') AND win_rate <= 1.0 THEN win_rate END) AS best_win_rate,
            MAX(CASE WHEN typeof(profit_factor) IN ('real', 'integer') THEN profit_factor END) AS best_profit_factor
        FROM runs
        WHERE instrument IS NOT NULL AND instrument != ''
        GROUP BY instrument
        ORDER BY instrument
    """

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql).fetchall()

    results: list[dict] = []
    for row in rows:
        # Parse unique sessions from the concatenated sessions_raw
        sessions_raw = row["sessions_raw"] or ""
        sessions_set: set[str] = set()
        for chunk in sessions_raw.split(","):
            for s in chunk.strip().split("+"):
                s = s.strip()
                if s:
                    sessions_set.add(s)

        results.append({
            "instrument": row["instrument"],
            "backtest_count": row["backtest_count"] or 0,
            "optimization_count": row["optimization_count"] or 0,
            "earliest_date": row["earliest_date"] or "",
            "latest_date": row["latest_date"] or "",
            "last_run_at": row["last_run_at"] or "",
            "sessions_tested": sorted(sessions_set),
            "best_sharpe": row["best_sharpe"],
            "best_r_per_year": row["best_r_per_year"],
            "best_win_rate": row["best_win_rate"],
            "best_profit_factor": row["best_profit_factor"],
        })

    return results


def get_param_coverage(instrument: str) -> dict:
    """Return distinct values of key sweep params for an instrument."""
    init_db()

    # Key params we want to show coverage for
    key_params = [
        "rr", "tp1_ratio",
        "ny_stop_atr_pct", "ny_min_gap_atr_pct",
        "asia_stop_atr_pct", "asia_min_gap_atr_pct",
        "ldn_stop_atr_pct", "ldn_min_gap_atr_pct",
    ]

    result: dict = {}
    with sqlite3.connect(DB_PATH) as conn:
        for param in key_params:
            if param not in PARAM_COLUMNS:
                continue
            sql = f"""
                SELECT DISTINCT {param} FROM runs
                WHERE instrument = ? AND {param} IS NOT NULL
                ORDER BY {param}
            """
            rows = conn.execute(sql, [instrument]).fetchall()
            values = [r[0] for r in rows]
            if values:
                result[param] = {
                    "values": values,
                    "min": min(values),
                    "max": max(values),
                    "count": len(values),
                }

    return result


# ---------------------------------------------------------------------------
# Testing plan CRUD
# ---------------------------------------------------------------------------

def list_testing_plan(instrument: str | None = None) -> list[dict]:
    """List testing plan items, optionally filtered by instrument."""
    init_db()

    if instrument:
        sql = """
            SELECT id, instrument, title, status, notes, sort_order, created_at, completed_at
            FROM testing_plan
            WHERE instrument = ?
            ORDER BY status ASC, sort_order ASC, id ASC
        """
        params = [instrument]
    else:
        sql = """
            SELECT id, instrument, title, status, notes, sort_order, created_at, completed_at
            FROM testing_plan
            ORDER BY status ASC, sort_order ASC, id ASC
        """
        params = []

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()

    return [dict(row) for row in rows]


def create_testing_plan_item(instrument: str, title: str, notes: str | None = None) -> dict:
    """Create a new testing plan item. Returns the created item."""
    init_db()

    now = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        # Auto-set sort_order to max + 1 for this instrument
        row = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM testing_plan WHERE instrument = ?",
            [instrument],
        ).fetchone()
        sort_order = row[0] if row else 0

        cur = conn.execute(
            """INSERT INTO testing_plan (instrument, title, notes, sort_order, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            [instrument, title, notes, sort_order, now],
        )
        item_id = cur.lastrowid

    return {
        "id": item_id,
        "instrument": instrument,
        "title": title,
        "status": "pending",
        "notes": notes,
        "sort_order": sort_order,
        "created_at": now,
        "completed_at": None,
    }


def update_testing_plan_item(item_id: int, **updates) -> dict | None:
    """Update a testing plan item. Returns the updated item, or None if not found."""
    init_db()

    allowed = {"title", "notes", "status", "sort_order"}
    sets: list[str] = []
    params: list = []

    for key, val in updates.items():
        if key not in allowed:
            continue
        sets.append(f"{key} = ?")
        params.append(val)

    # Auto-set completed_at when status changes to completed
    if updates.get("status") == "completed":
        sets.append("completed_at = ?")
        params.append(datetime.now(timezone.utc).isoformat())
    elif updates.get("status") == "pending":
        sets.append("completed_at = ?")
        params.append(None)

    if not sets:
        return None

    params.append(item_id)
    sql = f"UPDATE testing_plan SET {', '.join(sets)} WHERE id = ?"

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(sql, params)
        if cur.rowcount == 0:
            return None

        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM testing_plan WHERE id = ?", [item_id]).fetchone()
        return dict(row) if row else None


def delete_testing_plan_item(item_id: int) -> bool:
    """Delete a testing plan item. Returns True if deleted."""
    init_db()
    backup_db()

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("DELETE FROM testing_plan WHERE id = ?", [item_id])
        return cur.rowcount > 0


def reorder_testing_plan(instrument: str, item_ids: list[int]) -> bool:
    """Batch update sort_order from the provided ID sequence."""
    init_db()

    with sqlite3.connect(DB_PATH) as conn:
        for idx, item_id in enumerate(item_ids):
            conn.execute(
                "UPDATE testing_plan SET sort_order = ? WHERE id = ? AND instrument = ?",
                [idx, item_id, instrument],
            )
    return True


# ---------------------------------------------------------------------------
# Bulk import (for syncing from another DB)
# ---------------------------------------------------------------------------

def import_runs(rows: list[dict]) -> int:
    """Bulk import run rows from another DB. Uses INSERT OR REPLACE keyed on result_file.

    Each row dict should contain all columns except 'id' (auto-increment).
    Idempotent — safe to call multiple times with the same data.

    Returns the number of rows imported.
    """
    init_db()
    if not rows:
        return 0

    # Ensure result_file uniqueness index exists for REPLACE to work
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_result_file ON runs(result_file)"
        )

        count = 0
        for row in rows:
            # Strip 'id' — let the remote DB assign its own
            clean = {k: v for k, v in row.items() if k != "id"}
            if not clean.get("result_file"):
                continue

            columns = ", ".join(clean.keys())
            placeholders = ", ".join(f":{k}" for k in clean.keys())
            sql = f"INSERT OR REPLACE INTO runs ({columns}) VALUES ({placeholders})"
            conn.execute(sql, clean)
            count += 1

    return count


def import_optimizations(rows: list[dict]) -> int:
    """Bulk import optimization rows from another DB. Uses INSERT OR REPLACE keyed on result_id.

    Each row dict should contain all columns except 'id' (auto-increment).
    Idempotent — safe to call multiple times with the same data.

    Returns the number of rows imported.
    """
    init_db()
    if not rows:
        return 0

    with sqlite3.connect(DB_PATH) as conn:
        count = 0
        for row in rows:
            clean = {k: v for k, v in row.items() if k != "id"}
            if not clean.get("result_id"):
                continue

            columns = ", ".join(clean.keys())
            placeholders = ", ".join(f":{k}" for k in clean.keys())
            sql = f"INSERT OR REPLACE INTO optimizations ({columns}) VALUES ({placeholders})"
            conn.execute(sql, clean)
            count += 1

    return count


# ---------------------------------------------------------------------------
# News Straddle CRUD
# ---------------------------------------------------------------------------

def log_news_straddle_run(result_dict: dict, result_id: str) -> int:
    """Save a news straddle backtest run to the DB."""
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    config = result_dict.get("config", {})
    summary = result_dict.get("summary", {})

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO news_straddle_runs
               (result_id, timestamp, instrument, buffer_points, target_points,
                observation_window_seconds, event_types, date_start, date_end,
                fills, target_hit_rate, whipsaw_rate, pct_profitable,
                avg_mfe, avg_mae, avg_final_points, stop_loss_points, result_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result_id,
                now,
                config.get("instrument", "NQ"),
                config.get("buffer_points"),
                config.get("target_points"),
                config.get("observation_window_seconds"),
                json.dumps(config.get("event_types", [])),
                config.get("date_start"),
                config.get("date_end"),
                summary.get("fills"),
                summary.get("target_hit_rate"),
                summary.get("whipsaw_rate"),
                summary.get("pct_profitable"),
                summary.get("avg_mfe"),
                summary.get("avg_mae"),
                summary.get("avg_final_points"),
                config.get("stop_loss_points"),
                json.dumps(result_dict),
            ),
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def list_news_straddle_history(limit: int = 100) -> list[dict]:
    """List recent news straddle runs (most recent first)."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT id, result_id, timestamp, instrument,
                      buffer_points, target_points, observation_window_seconds,
                      event_types, date_start, date_end,
                      fills, target_hit_rate, whipsaw_rate, pct_profitable,
                      avg_mfe, avg_mae, avg_final_points, stop_loss_points,
                      starred,
                      json_extract(result_json, '$.config.max_atr_pct') AS max_atr_pct,
                      json_extract(result_json, '$.config.min_volume_ratio') AS min_volume_ratio,
                      json_extract(result_json, '$.config.max_volume_ratio') AS max_volume_ratio,
                      json_extract(result_json, '$.config.direction_filter') AS direction_filter,
                      json_extract(result_json, '$.config.skip_days') AS skip_days
               FROM news_straddle_runs
               ORDER BY timestamp DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_news_straddle_run(result_id: str) -> dict | None:
    """Load a full news straddle result by result_id."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT result_json FROM news_straddle_runs WHERE result_id = ?",
            (result_id,),
        ).fetchone()
    if row is None:
        return None
    return json.loads(row[0])


def delete_news_straddle_run(result_id: str) -> bool:
    """Delete a news straddle run by result_id."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "DELETE FROM news_straddle_runs WHERE result_id = ?",
            (result_id,),
        )
        return cursor.rowcount > 0


def toggle_news_straddle_star(result_id: str) -> bool | None:
    """Toggle the starred state of a news straddle run. Returns new state or None if not found."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT starred FROM news_straddle_runs WHERE result_id = ?",
            (result_id,),
        ).fetchone()
        if row is None:
            return None
        new_val = 0 if row[0] else 1
        conn.execute(
            "UPDATE news_straddle_runs SET starred = ? WHERE result_id = ?",
            (new_val, result_id),
        )
        return bool(new_val)


# ---------------------------------------------------------------------------
# Regime Reports CRUD
# ---------------------------------------------------------------------------


def log_regime_report(result_dict: dict, result_id: str) -> int:
    """Save a regime report to the DB."""
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    meta = result_dict.get("meta", {})
    summary = result_dict.get("summary", {})
    hmm = result_dict.get("hmm", {}) if result_dict.get("hmm") else {}
    lstm = result_dict.get("lstm", {}) if result_dict.get("lstm") else {}

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO regime_reports
               (result_id, timestamp, instrument, sessions, backtest_result_id, backtest_name,
                date_start, date_end, methods, hmm_states, lstm_clusters,
                hmm_total_r, lstm_total_r, hmm_best_pf, lstm_best_pf, report_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result_id,
                now,
                meta.get("instrument", ""),
                meta.get("sessions", ""),
                meta.get("backtest_result_id", ""),
                meta.get("backtest_name"),
                meta.get("date_start"),
                meta.get("date_end"),
                json.dumps(summary.get("methods", [])),
                hmm.get("states"),
                lstm.get("clusters"),
                hmm.get("total_r"),
                lstm.get("total_r"),
                hmm.get("best_pf"),
                lstm.get("best_pf"),
                json.dumps(result_dict, default=_json_default),
            ),
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def list_regime_reports(limit: int = 100) -> list[dict]:
    """List recent regime reports (most recent first)."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT id, result_id, timestamp, instrument, sessions, backtest_result_id,
                      backtest_name, date_start, date_end, methods, hmm_states, lstm_clusters,
                      hmm_total_r, lstm_total_r, hmm_best_pf, lstm_best_pf
               FROM regime_reports
               ORDER BY timestamp DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_regime_report(result_id: str) -> dict | None:
    """Load a full regime report by result_id."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT report_json FROM regime_reports WHERE result_id = ?",
            (result_id,),
        ).fetchone()
    if row is None:
        return None
    return json.loads(row[0])


def delete_regime_report(result_id: str) -> bool:
    """Delete a regime report by result_id."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "DELETE FROM regime_reports WHERE result_id = ?",
            (result_id,),
        )
        return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# Risk Engine Layouts
# ---------------------------------------------------------------------------


def list_risk_engine_layouts() -> list[dict]:
    """Return all saved risk engine layouts."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, name, account_risk, strategies_json, created_at, updated_at "
            "FROM risk_engine_layouts ORDER BY name"
        ).fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "accountRisk": row["account_risk"],
                "strategies": json.loads(row["strategies_json"]),
                "createdAt": row["created_at"],
                "updatedAt": row["updated_at"],
            }
            for row in rows
        ]


def save_risk_engine_layout(
    name: str, account_risk: float, strategies: list[dict]
) -> dict:
    """Create or update a risk engine layout. Returns the saved layout."""
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    strategies_json = json.dumps(strategies)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """INSERT INTO risk_engine_layouts (name, account_risk, strategies_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                 account_risk = excluded.account_risk,
                 strategies_json = excluded.strategies_json,
                 updated_at = excluded.updated_at""",
            (name, account_risk, strategies_json, now, now),
        )
        row = conn.execute(
            "SELECT * FROM risk_engine_layouts WHERE name = ?", (name,)
        ).fetchone()
        return {
            "id": row["id"],
            "name": row["name"],
            "accountRisk": row["account_risk"],
            "strategies": json.loads(row["strategies_json"]),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }


def delete_risk_engine_layout(name: str) -> bool:
    """Delete a risk engine layout by name. Returns True if deleted."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "DELETE FROM risk_engine_layouts WHERE name = ?", (name,)
        )
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Saved configs CRUD
# ---------------------------------------------------------------------------


def list_saved_configs(limit: int = 200) -> list[dict]:
    """List saved config presets (most recent first)."""
    init_db()
    sql = """
        SELECT id, timestamp, updated_at, name, notes, instrument, sessions, strategy, config_json
        FROM saved_configs
        ORDER BY updated_at DESC, id DESC
        LIMIT ?
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, [limit]).fetchall()
    results: list[dict] = []
    for row in rows:
        results.append({
            "id": row["id"],
            "timestamp": row["timestamp"],
            "updated_at": row["updated_at"],
            "name": row["name"],
            "notes": row["notes"],
            "instrument": row["instrument"],
            "sessions": (row["sessions"] or "").split("+") if row["sessions"] else [],
            "strategy": row["strategy"],
            "config": json.loads(row["config_json"]) if row["config_json"] else {},
        })
    return results


def get_saved_config(config_id: int) -> dict | None:
    """Load a saved config by id."""
    init_db()
    sql = """
        SELECT id, timestamp, updated_at, name, notes, instrument, sessions, strategy, config_json
        FROM saved_configs
        WHERE id = ?
        LIMIT 1
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(sql, [config_id]).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "timestamp": row["timestamp"],
        "updated_at": row["updated_at"],
        "name": row["name"],
        "notes": row["notes"],
        "instrument": row["instrument"],
        "sessions": (row["sessions"] or "").split("+") if row["sessions"] else [],
        "strategy": row["strategy"],
        "config": json.loads(row["config_json"]) if row["config_json"] else {},
    }


def create_saved_config(
    *,
    name: str,
    notes: str | None,
    instrument: str,
    sessions: list[str],
    strategy: str,
    config: dict,
) -> dict:
    """Create a new saved config and return it."""
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    sessions_str = "+".join(sessions)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """INSERT INTO saved_configs
               (timestamp, updated_at, name, notes, instrument, sessions, strategy, config_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                now,
                now,
                name,
                notes,
                instrument,
                sessions_str,
                strategy,
                _dumps(config),
            ),
        )
        row_id = cur.lastrowid
        row = conn.execute(
            "SELECT id, timestamp, updated_at, name, notes, instrument, sessions, strategy, config_json "
            "FROM saved_configs WHERE id = ?",
            [row_id],
        ).fetchone()
    return {
        "id": row["id"],
        "timestamp": row["timestamp"],
        "updated_at": row["updated_at"],
        "name": row["name"],
        "notes": row["notes"],
        "instrument": row["instrument"],
        "sessions": (row["sessions"] or "").split("+") if row["sessions"] else [],
        "strategy": row["strategy"],
        "config": json.loads(row["config_json"]) if row["config_json"] else {},
    }


def update_saved_config(
    config_id: int,
    *,
    name: str,
    notes: str | None,
    instrument: str,
    sessions: list[str],
    strategy: str,
    config: dict,
) -> dict | None:
    """Update a saved config. Returns updated object or None if missing."""
    init_db()
    now = datetime.now(timezone.utc).isoformat()
    sessions_str = "+".join(sessions)
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """UPDATE saved_configs
               SET updated_at = ?, name = ?, notes = ?, instrument = ?, sessions = ?, strategy = ?, config_json = ?
               WHERE id = ?""",
            (
                now,
                name,
                notes,
                instrument,
                sessions_str,
                strategy,
                _dumps(config),
                config_id,
            ),
        )
        if cur.rowcount == 0:
            return None
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, timestamp, updated_at, name, notes, instrument, sessions, strategy, config_json "
            "FROM saved_configs WHERE id = ?",
            [config_id],
        ).fetchone()
    return {
        "id": row["id"],
        "timestamp": row["timestamp"],
        "updated_at": row["updated_at"],
        "name": row["name"],
        "notes": row["notes"],
        "instrument": row["instrument"],
        "sessions": (row["sessions"] or "").split("+") if row["sessions"] else [],
        "strategy": row["strategy"],
        "config": json.loads(row["config_json"]) if row["config_json"] else {},
    }


def delete_saved_config(config_id: int) -> bool:
    """Delete a saved config by id. Returns True if deleted."""
    init_db()
    backup_db()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("DELETE FROM saved_configs WHERE id = ?", [config_id])
        return cur.rowcount > 0

# ---------------------------------------------------------------------------
# Live Trades CRUD
# ---------------------------------------------------------------------------

def log_live_trade(trade: dict) -> int:
    """Insert a live trade record. Returns the rowid."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """\
            INSERT INTO live_trades
                (timestamp, session, date, direction, entry_price, stop_price,
                 tp1_price, tp2_price, exit_type, tp1_hit, exit_timestamp,
                 config_name, r_result, entry_timestamp, ticker, exec_ticker, leg, notes,
                 net_pnl_usd, net_r_result, commission_usd, qty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                datetime.now(timezone.utc).isoformat(),
                trade["session"],
                trade["date"],
                trade["direction"],
                trade["entry_price"],
                trade["stop_price"],
                trade["tp1_price"],
                trade["tp2_price"],
                trade["exit_type"],
                1 if trade.get("tp1_hit") else 0,
                trade["exit_timestamp"],
                trade.get("config_name", ""),
                trade.get("r_result"),
                trade.get("entry_timestamp"),
                trade.get("ticker"),
                trade.get("exec_ticker"),
                trade.get("leg") or trade["session"],
                trade.get("notes"),
                trade.get("net_pnl_usd"),
                trade.get("net_r_result"),
                trade.get("commission_usd"),
                trade.get("qty"),
            ],
        )
        return cur.lastrowid


def log_payout(payout: dict) -> int:
    """Insert a prop-firm payout record. Returns the rowid."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            """\
            INSERT INTO payouts (config_name, date, amount, notes, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                payout["config_name"],
                payout["date"],
                float(payout["amount"]),
                payout.get("notes"),
                datetime.now(timezone.utc).isoformat(),
            ],
        )
        return cur.lastrowid


def list_payouts(config_name: str = "") -> list[dict]:
    """List payout records, optionally filtered by config name."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        if config_name:
            rows = conn.execute(
                "SELECT * FROM payouts WHERE config_name = ? ORDER BY date, id",
                [config_name],
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM payouts ORDER BY date, id").fetchall()
        return [dict(row) for row in rows]


def delete_payout(payout_id: int) -> bool:
    """Delete a payout record. Returns True if a row was removed."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("DELETE FROM payouts WHERE id = ?", [payout_id])
        return cur.rowcount > 0


def list_live_trades(
    session: str = "",
    config_name: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 500,
) -> list[dict]:
    """List live trades with optional filters. Returns newest-first."""
    init_db()
    clauses: list[str] = []
    params: list = []
    if session:
        clauses.append("session = ?")
        params.append(session)
    if config_name:
        clauses.append("config_name = ?")
        params.append(config_name)
    if date_from:
        clauses.append("date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("date <= ?")
        params.append(date_to)

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    sql = f"SELECT * FROM live_trades {where} ORDER BY date DESC, id DESC LIMIT ?"
    params.append(limit)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_live_trade(trade_id: int) -> dict | None:
    """Get a single live trade by id."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM live_trades WHERE id = ?", [trade_id]).fetchone()
    return dict(row) if row else None


def update_live_trade(trade_id: int, updates: dict) -> dict | None:
    """Update fields on a live trade. Returns the updated record or None."""
    allowed = {
        "session", "date", "direction", "entry_price", "stop_price",
        "tp1_price", "tp2_price", "exit_type", "tp1_hit", "exit_timestamp",
        "config_name", "r_result", "entry_timestamp", "ticker", "exec_ticker", "leg", "notes",
    }
    fields = {k: v for k, v in updates.items() if k in allowed}
    if not fields:
        return get_live_trade(trade_id)

    if "tp1_hit" in fields:
        fields["tp1_hit"] = 1 if fields["tp1_hit"] else 0

    sets = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [trade_id]

    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(f"UPDATE live_trades SET {sets} WHERE id = ?", vals)
    return get_live_trade(trade_id)


def delete_live_trade(trade_id: int) -> bool:
    """Delete a live trade by id. Returns True if deleted."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("DELETE FROM live_trades WHERE id = ?", [trade_id])
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Execution log persistence
# ---------------------------------------------------------------------------

_EXEC_LOG_TABLES = {
    "trades": "execution_trade_logs",
    "main": "execution_main_logs",
    "webhooks": "execution_webhook_logs",
}

_EXEC_LOG_COLUMNS = {
    "trades": ("timestamp", "config", "asset", "session", "event", "details_json"),
    "main": ("timestamp", "level", "logger", "message"),
    "webhooks": ("timestamp", "account", "status", "http_code", "latency", "payload"),
}


def _prepare_exec_log_row(log_type: str, entry: dict) -> tuple:
    """Convert a parsed log entry dict to a DB row tuple."""
    cols = _EXEC_LOG_COLUMNS[log_type]
    row = []
    for col in cols:
        if col == "details_json":
            row.append(json.dumps(entry.get("details", {})))
        else:
            row.append(entry.get(col))
    return tuple(row)


def log_execution_log(log_type: str, entry: dict) -> int:
    """Insert a single execution log entry. Returns the rowid."""
    table = _EXEC_LOG_TABLES[log_type]
    cols = _EXEC_LOG_COLUMNS[log_type]
    placeholders = ", ".join("?" for _ in cols)
    col_names = ", ".join(cols)
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
            _prepare_exec_log_row(log_type, entry),
        )
        return cur.lastrowid


def log_execution_logs_batch(log_type: str, entries: list[dict]) -> int:
    """Batch-insert execution log entries. Returns the count inserted."""
    if not entries:
        return 0
    table = _EXEC_LOG_TABLES[log_type]
    cols = _EXEC_LOG_COLUMNS[log_type]
    placeholders = ", ".join("?" for _ in cols)
    col_names = ", ".join(cols)
    rows = [_prepare_exec_log_row(log_type, e) for e in entries]
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.executemany(
            f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
            rows,
        )
        return len(rows)


def list_execution_logs(
    log_type: str,
    *,
    limit: int = 500,
    offset: int = 0,
    config: str = "",
    session: str = "",
    level: str = "",
    account: str = "",
    search: str = "",
) -> tuple[list[dict], int]:
    """List execution logs with optional filters. Returns (entries, total)."""
    table = _EXEC_LOG_TABLES[log_type]
    init_db()

    clauses: list[str] = []
    params: list = []

    if config and log_type == "trades":
        clauses.append("config = ?")
        params.append(config)
    if session and log_type == "trades":
        clauses.append("session = ?")
        params.append(session)
    if level and log_type == "main":
        clauses.append("level = ?")
        params.append(level)
    if account and log_type == "webhooks":
        clauses.append("account = ?")
        params.append(account)
    if search:
        if log_type == "trades":
            clauses.append("(event LIKE ? OR details_json LIKE ? OR session LIKE ?)")
            params.extend([f"%{search}%"] * 3)
        elif log_type == "main":
            clauses.append("(message LIKE ? OR logger LIKE ?)")
            params.extend([f"%{search}%"] * 2)
        elif log_type == "webhooks":
            clauses.append("(payload LIKE ? OR account LIKE ?)")
            params.extend([f"%{search}%"] * 2)

    where = "WHERE " + " AND ".join(clauses) if clauses else ""

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute(f"SELECT COUNT(*) FROM {table} {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM {table} {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

    entries = []
    for r in rows:
        d = dict(r)
        # Deserialize details_json back to dict for trade logs
        if log_type == "trades" and "details_json" in d:
            try:
                d["details"] = json.loads(d.pop("details_json"))
            except (json.JSONDecodeError, TypeError):
                d["details"] = {}
                d.pop("details_json", None)
        entries.append(d)

    return entries, total


def count_execution_logs(log_type: str) -> int:
    """Return total row count for a log type."""
    table = _EXEC_LOG_TABLES[log_type]
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ---------------------------------------------------------------------------
# Execution config persistence
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _webhook_row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "url": row["url"],
        "label": row["label"] or "",
        "paused": bool(row["paused"]),
        "multiplier": float(row["multiplier"] if row["multiplier"] is not None else 1.0),
    }


def _list_execution_config_webhooks(conn: sqlite3.Connection, config_name: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT webhook_index, label, url, paused, multiplier
        FROM execution_config_webhooks
        WHERE config_name = ?
        ORDER BY webhook_index
        """,
        [config_name],
    ).fetchall()
    return [_webhook_row_to_dict(row) for row in rows]


def upsert_execution_config(
    config_name: str,
    *,
    enabled: bool | None = None,
    max_open_contracts: float | None = None,
    config: dict | None = None,
) -> dict:
    """Create or update a remote execution config metadata row."""
    init_db()
    now = _utc_now_iso()
    config_json = json.dumps(config) if config is not None else None
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO execution_configs
                (config_name, enabled, max_open_contracts, config_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(config_name) DO UPDATE SET
                enabled = COALESCE(excluded.enabled, execution_configs.enabled),
                max_open_contracts = COALESCE(excluded.max_open_contracts, execution_configs.max_open_contracts),
                config_json = COALESCE(excluded.config_json, execution_configs.config_json),
                updated_at = excluded.updated_at
            """,
            [
                config_name,
                None if enabled is None else int(enabled),
                max_open_contracts,
                config_json,
                now,
            ],
        )
        row = conn.execute(
            "SELECT * FROM execution_configs WHERE config_name = ?",
            [config_name],
        ).fetchone()
        result = dict(row)
        result["enabled"] = None if row["enabled"] is None else bool(row["enabled"])
        result["webhooks"] = _list_execution_config_webhooks(conn, config_name)
        return result


def list_execution_configs_db() -> list[dict]:
    """List execution configs and attached webhook accounts from the DB."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM execution_configs ORDER BY config_name"
        ).fetchall()
        configs: list[dict] = []
        for row in rows:
            item = dict(row)
            item["enabled"] = None if row["enabled"] is None else bool(row["enabled"])
            item["webhooks"] = _list_execution_config_webhooks(conn, row["config_name"])
            configs.append(item)
        return configs


def replace_execution_config_webhooks(config_name: str, webhooks: list[dict]) -> list[dict]:
    """Replace all webhook accounts for one execution config."""
    init_db()
    now = _utc_now_iso()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO execution_configs (config_name, updated_at)
            VALUES (?, ?)
            ON CONFLICT(config_name) DO UPDATE SET updated_at = excluded.updated_at
            """,
            [config_name, now],
        )
        conn.execute(
            "DELETE FROM execution_config_webhooks WHERE config_name = ?",
            [config_name],
        )
        for idx, webhook in enumerate(webhooks):
            conn.execute(
                """
                INSERT INTO execution_config_webhooks
                    (config_name, webhook_index, label, url, paused, multiplier, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    config_name,
                    idx,
                    str(webhook.get("label") or ""),
                    str(webhook.get("url") or ""),
                    int(bool(webhook.get("paused", False))),
                    float(webhook.get("multiplier", 1.0)),
                    now,
                ],
            )
        return _list_execution_config_webhooks(conn, config_name)


def patch_execution_config_webhook(
    config_name: str,
    webhook_index: int,
    updates: dict,
) -> dict | None:
    """Patch pause/multiplier/label/url for a single webhook account."""
    allowed = {"label", "url", "paused", "multiplier"}
    fields = {k: v for k, v in updates.items() if k in allowed}
    if not fields:
        return None

    assignments = []
    params: list = []
    for key, value in fields.items():
        assignments.append(f"{key} = ?")
        if key == "paused":
            params.append(int(bool(value)))
        elif key == "multiplier":
            params.append(float(value))
        else:
            params.append(str(value))
    assignments.append("updated_at = ?")
    params.append(_utc_now_iso())
    params.extend([config_name, webhook_index])

    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            f"""
            UPDATE execution_config_webhooks
            SET {", ".join(assignments)}
            WHERE config_name = ? AND webhook_index = ?
            """,
            params,
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute(
            """
            SELECT webhook_index, label, url, paused, multiplier
            FROM execution_config_webhooks
            WHERE config_name = ? AND webhook_index = ?
            """,
            [config_name, webhook_index],
        ).fetchone()
        return _webhook_row_to_dict(row) if row else None


# ---------------------------------------------------------------------------
# Remote-only mode.
#
# Client processes should use the main DB API exclusively when MAIN_DB_URL is
# configured. The API service itself sets MAIN_DB_URL="" before importing this
# module, so it remains the only process that writes the SQLite file directly.
# ---------------------------------------------------------------------------
if MAIN_DB_URL:
    from .experiments_remote import *  # noqa: F401, F403
