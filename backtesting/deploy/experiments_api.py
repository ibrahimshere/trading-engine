"""Standalone FastAPI service for the main DB.

Run on the droplet at port 8100 alongside the execution service (port 8000).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Point DB_PATH to the droplet's main DB location BEFORE importing experiments.
# This service is the canonical DB owner, so it must not route through itself.
_main_db_path = (
    os.environ.get("MAIN_DB_PATH")
    or os.environ.get("EXPERIMENTS_DB_PATH")
    or "/opt/main-db/main.db"
)
os.environ["MAIN_DB_PATH"] = _main_db_path
os.environ["EXPERIMENTS_DB_PATH"] = _main_db_path
os.environ["MAIN_DB_URL"] = ""
os.environ["EXPERIMENTS_DB_URL"] = ""

# Add the backtesting source to the path so we can import experiments
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from orb_backtest.experiments import (
    init_db,
    log_run,
    log_optimization,
    list_backtest_history,
    list_optimization_history,
    get_backtest_result,
    get_optimization_result,
    delete_backtest_run,
    delete_optimization_run,
    rename_backtest,
    toggle_star,
    toggle_hidden,
    list_starred,
    query_runs,
    compare_runs,
    get_instrument_coverage,
    get_param_coverage,
    list_testing_plan,
    create_testing_plan_item,
    update_testing_plan_item,
    delete_testing_plan_item,
    reorder_testing_plan,
    import_runs,
    import_optimizations,
    log_news_straddle_run,
    list_news_straddle_history,
    get_news_straddle_run,
    delete_news_straddle_run,
    log_regime_report,
    list_regime_reports,
    get_regime_report,
    delete_regime_report,
    list_risk_engine_layouts,
    save_risk_engine_layout,
    delete_risk_engine_layout,
    list_saved_configs,
    get_saved_config,
    create_saved_config,
    update_saved_config,
    delete_saved_config,
    log_live_trade,
    list_live_trades,
    get_live_trade,
    update_live_trade,
    delete_live_trade,
    log_payout,
    list_payouts,
    delete_payout,
    log_execution_log,
    log_execution_logs_batch,
    list_execution_logs,
    count_execution_logs,
    upsert_execution_config,
    list_execution_configs_db,
    replace_execution_config_webhooks,
    patch_execution_config_webhook,
)

app = FastAPI(title="Main DB")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def ok(data):
    return {"success": True, "result": data}


def fail(msg, status=400):
    return JSONResponse({"success": False, "error": msg}, status_code=status)


# --- Health ---

@app.get("/api/health")
def health():
    init_db()
    return ok("healthy")


# --- Backtest CRUD ---

class LogRunRequest(BaseModel):
    result_dict: dict
    result_id: str
    run_type: str = "backtest"
    git_hash: Optional[str] = None

@app.post("/api/runs")
def create_run(req: LogRunRequest):
    rowid = log_run(req.result_dict, req.result_id, req.run_type, git_hash=req.git_hash)
    return ok({"rowid": rowid})


@app.get("/api/backtests")
def list_backtests(limit: int = 100):
    return ok(list_backtest_history(limit=limit))


@app.get("/api/backtests/{result_id}")
def get_backtest(result_id: str):
    row = get_backtest_result(result_id)
    if row is None:
        return fail("not found", 404)
    return ok(row)


@app.delete("/api/backtests/{result_id}")
def delete_backtest(result_id: str):
    success = delete_backtest_run(result_id)
    if not success:
        return fail("not found", 404)
    return ok({"deleted": True})


@app.post("/api/backtests/{result_id}/star")
def star_backtest(result_id: str):
    val = toggle_star(result_id)
    if val is None:
        return fail("not found", 404)
    return ok({"starred": val})


@app.post("/api/backtests/{result_id}/hide")
def hide_backtest(result_id: str):
    val = toggle_hidden(result_id)
    if val is None:
        return fail("not found", 404)
    return ok({"hidden": val})


class RenameRequest(BaseModel):
    name: str

@app.patch("/api/backtests/{result_id}/name")
def rename_backtest_ep(result_id: str, req: RenameRequest):
    name = rename_backtest(result_id, req.name)
    if name is None:
        return fail("not found", 404)
    return ok({"name": name})


@app.get("/api/starred")
def get_starred(limit: int = 100):
    return ok(list_starred(limit=limit))


# --- Optimization CRUD ---

class LogOptimizationRequest(BaseModel):
    result_dict: dict
    result_id: str

@app.post("/api/optimizations")
def create_optimization(req: LogOptimizationRequest):
    rowid = log_optimization(req.result_dict, req.result_id)
    return ok({"rowid": rowid})


class LogSweepRunsRequest(BaseModel):
    all_results: list
    optimization_id: str

@app.post("/api/sweep-runs")
def create_sweep_runs(req: LogSweepRunsRequest):
    # Data arrives pre-serialized as dicts from the remote client.
    # Call log_run() directly instead of log_sweep_runs() which expects
    # native (StrategyConfig, list[TradeResult]) tuples.
    # Pre-compute git hash once for the entire batch (avoids N subprocess calls).
    from orb_backtest.experiments import _get_git_hash
    git_hash = _get_git_hash()
    count = 0
    for result_dict in req.all_results:
        log_run(result_dict, req.optimization_id, run_type="optimization", git_hash=git_hash)
        count += 1
    return ok({"count": count})


@app.get("/api/optimizations")
def list_optimizations(limit: int = 100):
    return ok(list_optimization_history(limit=limit))


@app.get("/api/optimizations/{result_id}")
def get_optimization(result_id: str):
    row = get_optimization_result(result_id)
    if row is None:
        return fail("not found", 404)
    return ok(row)


@app.delete("/api/optimizations/{result_id}")
def delete_optimization(result_id: str):
    success = delete_optimization_run(result_id)
    if not success:
        return fail("not found", 404)
    return ok({"deleted": True})


# --- Sync / Import ---

class SyncImportRequest(BaseModel):
    runs: list[dict] = []
    optimizations: list[dict] = []

@app.post("/api/sync/import")
def sync_import(req: SyncImportRequest):
    runs_count = import_runs(req.runs)
    opts_count = import_optimizations(req.optimizations)
    return ok({"runs_imported": runs_count, "optimizations_imported": opts_count})


# --- Query / Compare ---

@app.get("/api/experiments")
def list_experiments(
    instrument: Optional[str] = None,
    sessions: Optional[str] = None,
    min_sharpe: Optional[float] = None,
    min_profit_factor: Optional[float] = None,
    experiment_name: Optional[str] = None,
    run_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 200,
):
    filters = {}
    if instrument:
        filters["instrument"] = instrument
    if sessions:
        filters["sessions"] = sessions
    if min_sharpe is not None:
        filters["min_sharpe"] = min_sharpe
    if min_profit_factor is not None:
        filters["min_profit_factor"] = min_profit_factor
    if experiment_name:
        filters["experiment_name"] = experiment_name
    if run_type:
        filters["run_type"] = run_type
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to
    filters["limit"] = limit
    return ok(query_runs(**filters))


@app.get("/api/experiments/compare")
def compare_experiments(ids: str = Query(...)):
    run_ids = [int(x.strip()) for x in ids.split(",")]
    return ok(compare_runs(run_ids))


# --- Coverage ---

@app.get("/api/coverage")
def get_coverage():
    return ok(get_instrument_coverage())


@app.get("/api/coverage/{instrument}/params")
def get_coverage_params(instrument: str):
    return ok(get_param_coverage(instrument))


# --- Testing Plan ---

class PlanItemCreate(BaseModel):
    instrument: str
    title: str
    notes: Optional[str] = None

class PlanItemUpdate(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None

class PlanReorder(BaseModel):
    instrument: str
    item_ids: list[int]

@app.get("/api/testing-plan")
def get_testing_plan(instrument: Optional[str] = None):
    return ok(list_testing_plan(instrument))

@app.post("/api/testing-plan")
def create_plan_item(req: PlanItemCreate):
    return ok(create_testing_plan_item(req.instrument, req.title, req.notes))

@app.put("/api/testing-plan/{item_id}")
def update_plan_item(item_id: int, req: PlanItemUpdate):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    result = update_testing_plan_item(item_id, **updates)
    if result is None:
        return fail("not found", 404)
    return ok(result)

@app.delete("/api/testing-plan/{item_id}")
def delete_plan_item(item_id: int):
    success = delete_testing_plan_item(item_id)
    if not success:
        return fail("not found", 404)
    return ok({"deleted": True})

@app.post("/api/testing-plan/reorder")
def reorder_plan(req: PlanReorder):
    success = reorder_testing_plan(req.instrument, req.item_ids)
    return ok({"reordered": success})


# --- News Straddle CRUD ---

class LogNewsStraddleRequest(BaseModel):
    result_dict: dict
    result_id: str

@app.post("/api/news-straddle/runs")
def create_news_straddle_run(req: LogNewsStraddleRequest):
    rowid = log_news_straddle_run(req.result_dict, req.result_id)
    return ok({"rowid": rowid})

@app.get("/api/news-straddle/runs")
def list_news_straddle_runs(limit: int = 100):
    return ok(list_news_straddle_history(limit=limit))

@app.get("/api/news-straddle/runs/{result_id}")
def get_news_straddle(result_id: str):
    row = get_news_straddle_run(result_id)
    if row is None:
        return fail("not found", 404)
    return ok(row)

@app.delete("/api/news-straddle/runs/{result_id}")
def delete_news_straddle(result_id: str):
    success = delete_news_straddle_run(result_id)
    if not success:
        return fail("not found", 404)
    return ok({"deleted": True})


# --- Regime Reports CRUD ---

class RegimeReportSaveRequest(BaseModel):
    result_dict: dict
    result_id: str


@app.post("/api/regime-reports")
def save_regime_report_endpoint(req: RegimeReportSaveRequest):
    rowid = log_regime_report(req.result_dict, req.result_id)
    return ok({"rowid": rowid})


@app.get("/api/regime-reports")
def list_regime_reports_endpoint(limit: int = 100):
    return ok(list_regime_reports(limit=limit))


@app.get("/api/regime-reports/{result_id}")
def get_regime_report_endpoint(result_id: str):
    result = get_regime_report(result_id)
    if result is None:
        return fail("not found", 404)
    return ok(result)


@app.delete("/api/regime-reports/{result_id}")
def delete_regime_report_endpoint(result_id: str):
    if not delete_regime_report(result_id):
        return fail("not found", 404)
    return ok({"deleted": True})


# --- Risk Engine Layouts ---

class RiskEngineLayoutRequest(BaseModel):
    name: str
    accountRisk: float
    strategies: list[dict]

@app.get("/api/risk-engine/layouts")
def get_risk_engine_layouts():
    return ok(list_risk_engine_layouts())

@app.post("/api/risk-engine/layouts")
def save_layout(req: RiskEngineLayoutRequest):
    layout = save_risk_engine_layout(req.name, req.accountRisk, req.strategies)
    return ok(layout)

@app.delete("/api/risk-engine/layouts/{name}")
def delete_layout(name: str):
    if not delete_risk_engine_layout(name):
        return fail("not found", 404)
    return ok({"deleted": name})


# --- Live Trades CRUD ---

class LogLiveTradeRequest(BaseModel):
    trade: dict

@app.post("/api/live-trades")
def create_live_trade(req: LogLiveTradeRequest):
    rowid = log_live_trade(req.trade)
    return ok({"rowid": rowid})

@app.get("/api/live-trades")
def get_live_trades(
    session: str = "",
    config: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 500,
):
    trades = list_live_trades(
        session=session,
        config_name=config,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
    return ok(trades)

@app.get("/api/live-trades/{trade_id}")
def get_live_trade_ep(trade_id: int):
    trade = get_live_trade(trade_id)
    if trade is None:
        return fail("not found", 404)
    return ok(trade)

class UpdateLiveTradeRequest(BaseModel):
    updates: dict

@app.patch("/api/live-trades/{trade_id}")
def update_live_trade_ep(trade_id: int, req: UpdateLiveTradeRequest):
    result = update_live_trade(trade_id, req.updates)
    if result is None:
        return fail("not found", 404)
    return ok(result)

@app.delete("/api/live-trades/{trade_id}")
def delete_live_trade_ep(trade_id: int):
    if not delete_live_trade(trade_id):
        return fail("not found", 404)
    return ok({"deleted": True})


# --- Prop-firm payouts ---

class LogPayoutRequest(BaseModel):
    payout: dict

@app.post("/api/payouts")
def create_payout(req: LogPayoutRequest):
    payout = req.payout
    for field in ("config_name", "date", "amount"):
        if not payout.get(field):
            return fail(f"missing field: {field}", 400)
    rowid = log_payout(payout)
    return ok({"rowid": rowid})

@app.get("/api/payouts")
def get_payouts(config: str = ""):
    return ok(list_payouts(config_name=config))

@app.delete("/api/payouts/{payout_id}")
def delete_payout_ep(payout_id: int):
    if not delete_payout(payout_id):
        return fail("not found", 404)
    return ok({"deleted": True})


# --- Execution Logs ---

_VALID_LOG_TYPES = {"trades", "main", "webhooks"}


class ExecutionLogRequest(BaseModel):
    entry: Optional[dict] = None
    entries: Optional[list[dict]] = None


@app.post("/api/execution-logs/{log_type}")
def create_execution_log(log_type: str, req: ExecutionLogRequest):
    if log_type not in _VALID_LOG_TYPES:
        return fail(f"Invalid log type: {log_type}", 400)
    if req.entries:
        count = log_execution_logs_batch(log_type, req.entries)
        return ok({"count": count})
    if req.entry:
        rowid = log_execution_log(log_type, req.entry)
        return ok({"rowid": rowid})
    return fail("Provide 'entry' or 'entries'", 400)


@app.get("/api/execution-logs/{log_type}")
def get_execution_logs(
    log_type: str,
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    config: str = "",
    session: str = "",
    level: str = "",
    account: str = "",
    search: str = "",
):
    if log_type not in _VALID_LOG_TYPES:
        return fail(f"Invalid log type: {log_type}", 400)
    entries, total = list_execution_logs(
        log_type,
        limit=limit,
        offset=offset,
        config=config,
        session=session,
        level=level,
        account=account,
        search=search,
    )
    return ok({"entries": entries, "total": total, "limit": limit, "offset": offset})


@app.get("/api/execution-logs/{log_type}/count")
def get_execution_log_count(log_type: str):
    if log_type not in _VALID_LOG_TYPES:
        return fail(f"Invalid log type: {log_type}", 400)
    return ok({"count": count_execution_logs(log_type)})


# --- Execution Configs ---

class ExecutionConfigUpsertRequest(BaseModel):
    enabled: Optional[bool] = None
    max_open_contracts: Optional[float] = None
    config: Optional[dict] = None


class ExecutionWebhooksRequest(BaseModel):
    webhooks: list[dict] = []


class ExecutionWebhookPatchRequest(BaseModel):
    label: Optional[str] = None
    url: Optional[str] = None
    paused: Optional[bool] = None
    multiplier: Optional[float] = None


def _validate_webhook_payload(webhooks: list[dict]) -> JSONResponse | None:
    for webhook in webhooks:
        url = str(webhook.get("url") or "").strip()
        if not url:
            return fail("Each webhook must include a url", 422)
        if not url.startswith(("http://", "https://")):
            return fail("Webhook URLs must start with http:// or https://", 422)
        multiplier = float(webhook.get("multiplier", 1.0))
        if multiplier <= 0:
            return fail("Webhook multipliers must be > 0", 422)
    return None


@app.get("/api/execution-configs")
def list_execution_configs_ep():
    return ok({"configs": list_execution_configs_db()})


@app.put("/api/execution-configs/{config_name}")
def upsert_execution_config_ep(config_name: str, req: ExecutionConfigUpsertRequest):
    row = upsert_execution_config(
        config_name,
        enabled=req.enabled,
        max_open_contracts=req.max_open_contracts,
        config=req.config,
    )
    return ok(row)


@app.put("/api/execution-configs/{config_name}/webhooks")
def replace_execution_webhooks_ep(config_name: str, req: ExecutionWebhooksRequest):
    validation = _validate_webhook_payload(req.webhooks)
    if validation is not None:
        return validation
    webhooks = replace_execution_config_webhooks(config_name, req.webhooks)
    return ok({"config_name": config_name, "webhooks": webhooks})


@app.patch("/api/execution-configs/{config_name}/webhooks/{webhook_index}")
def patch_execution_webhook_ep(
    config_name: str,
    webhook_index: int,
    req: ExecutionWebhookPatchRequest,
):
    updates = req.model_dump(exclude_unset=True)
    if "url" in updates:
        url = str(updates["url"] or "").strip()
        if not url:
            return fail("Webhook URL cannot be empty", 422)
        if not url.startswith(("http://", "https://")):
            return fail("Webhook URLs must start with http:// or https://", 422)
        updates["url"] = url
    if "multiplier" in updates and updates["multiplier"] is not None and updates["multiplier"] <= 0:
        return fail("Webhook multiplier must be > 0", 422)
    row = patch_execution_config_webhook(config_name, webhook_index, updates)
    if row is None:
        return fail("not found", 404)
    return ok({"config_name": config_name, "webhook_index": webhook_index, "webhook": row})


# --- DB Upload (one-time migration) ---

@app.post("/api/upload-db")
async def upload_db(request: Request):
    """Replace the remote main DB SQLite file with an uploaded file.

    Usage:
        curl -X POST http://143.110.148.234:8100/api/upload-db \
             --data-binary @data/results/experiments.db \
             -H "Content-Type: application/octet-stream"
    """
    import shutil
    from datetime import datetime

    db_path = Path(os.environ.get("MAIN_DB_PATH", "/opt/main-db/main.db"))
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    body = await request.body()
    if len(body) < 100:
        return fail("Upload too small — doesn't look like a valid SQLite DB", 400)

    # Check SQLite magic header
    if body[:16] != b"SQLite format 3\x00":
        return fail("Not a valid SQLite file", 400)

    # Backup current DB before replacing
    if db_path.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(db_path, backup_dir / f"main_{ts}.db")

    # Write the new DB
    db_path.write_bytes(body)

    # Re-init to run any migrations
    init_db()

    # Count rows to confirm
    import sqlite3
    with sqlite3.connect(str(db_path)) as conn:
        runs_count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        opt_count = conn.execute("SELECT COUNT(*) FROM optimizations").fetchone()[0]
        starred = conn.execute("SELECT COUNT(*) FROM runs WHERE starred = 1").fetchone()[0]

    return ok({
        "uploaded": True,
        "size_bytes": len(body),
        "runs": runs_count,
        "optimizations": opt_count,
        "starred": starred,
    })


# --- Saved Configs CRUD ---

class SavedConfigRequest(BaseModel):
    name: str
    notes: Optional[str] = None
    instrument: str
    sessions: list[str]
    strategy: str
    config: dict

@app.get("/api/configs")
def list_configs(limit: int = 200):
    return ok(list_saved_configs(limit=limit))

@app.get("/api/configs/{config_id}")
def get_config(config_id: int):
    row = get_saved_config(config_id)
    if row is None:
        return fail("not found", 404)
    return ok(row)

@app.post("/api/configs")
def create_config(req: SavedConfigRequest):
    result = create_saved_config(
        name=req.name,
        notes=req.notes,
        instrument=req.instrument,
        sessions=req.sessions,
        strategy=req.strategy,
        config=req.config,
    )
    return ok(result)

@app.put("/api/configs/{config_id}")
def update_config(config_id: int, req: SavedConfigRequest):
    result = update_saved_config(
        config_id=config_id,
        name=req.name,
        notes=req.notes,
        instrument=req.instrument,
        sessions=req.sessions,
        strategy=req.strategy,
        config=req.config,
    )
    if result is None:
        return fail("not found", 404)
    return ok(result)

@app.delete("/api/configs/{config_id}")
def delete_config_ep(config_id: int):
    success = delete_saved_config(config_id)
    if not success:
        return fail("not found", 404)
    return ok({"deleted": True})


if __name__ == "__main__":
    import uvicorn
    init_db()
    uvicorn.run(app, host=os.environ.get("MAIN_DB_HOST", "127.0.0.1"), port=8100)
