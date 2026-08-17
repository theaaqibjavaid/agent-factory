"""
Observability router (Phase 5.2) — run logs, cost/token dashboards, budget alerts.

- ``GET .../observability/summary`` — workspace totals (runs by status, cost,
  tokens, duration) plus per-agent and per-day rollups from ``agent_runs``.
- ``GET .../observability/budgets`` — per-agent spend today vs daily budget
  with alert levels (warn at 80%, exceeded at 100%).
- ``GET .../observability/events`` — persisted run events (``run_events``
  table, written by the runtime broker as runs execute).
- ``GET .../observability/alerts`` — recent budget alert rows.

All reads are workspace-scoped and membership-gated like the rest of the API.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from agentfactory.app import db
from agentfactory.app.deps import get_current_user, get_current_workspace

router = APIRouter(tags=["observability"], dependencies=[Depends(get_current_user)])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _day_start() -> str:
    """ISO timestamp for the start of today (UTC) — used for per-day budgets."""
    return datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def _parse_stats(raw) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _workspace_settings(workspace_id: str) -> Dict[str, Any]:
    conn = db.get_db()
    try:
        row = conn.execute("SELECT settings FROM workspaces WHERE id = ?", (workspace_id,)).fetchone()
    finally:
        conn.close()
    if row is None:
        return {}
    try:
        settings = json.loads(row["settings"])
        return settings if isinstance(settings, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@router.get("/workspaces/{workspace_id}/observability/summary")
def summary(workspace: dict = Depends(get_current_workspace)):
    """Aggregate run stats: totals, per-agent, per-day (Phase 5.2 dashboard)."""
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM agent_runs WHERE workspace_id = ? ORDER BY created_at",
            (workspace["id"],),
        ).fetchall()
        agent_rows = conn.execute(
            "SELECT id, name FROM agents WHERE workspace_id = ?", (workspace["id"],),
        ).fetchall()
    finally:
        conn.close()

    agents = {r["id"]: r["name"] for r in agent_rows}
    totals = {"runs": 0, "completed": 0, "failed": 0, "cancelled": 0, "pending": 0,
              "total_cost_usd": 0.0, "total_tokens": 0, "total_duration_seconds": 0.0}
    per_agent: Dict[str, Dict[str, Any]] = {}
    per_day: Dict[str, Dict[str, Any]] = {}

    for run in rows:
        stats = _parse_stats(run["stats"])
        totals["runs"] += 1
        totals[run["status"] if run["status"] in totals else "pending"] += 1

        cost = (stats or {}).get("total_cost_usd") or 0.0
        tokens = (stats or {}).get("total_tokens") or 0
        duration = (stats or {}).get("duration_seconds") or 0.0
        totals["total_cost_usd"] += cost
        totals["total_tokens"] += tokens
        totals["total_duration_seconds"] += duration

        agent_name = agents.get(run["agent_id"], run["agent_id"])
        bucket = per_agent.setdefault(agent_name, {"runs": 0, "total_cost_usd": 0.0, "total_tokens": 0})
        bucket["runs"] += 1
        bucket["total_cost_usd"] += cost
        bucket["total_tokens"] += tokens

        day = (run["created_at"] or "")[:10]
        if day:
            day_bucket = per_day.setdefault(day, {"runs": 0, "total_cost_usd": 0.0, "total_tokens": 0})
            day_bucket["runs"] += 1
            day_bucket["total_cost_usd"] += cost
            day_bucket["total_tokens"] += tokens

    totals["total_duration_seconds"] = round(totals["total_duration_seconds"], 3)
    totals["total_cost_usd"] = round(totals["total_cost_usd"], 6)
    return {
        "totals": totals,
        "per_agent": per_agent,
        "per_day": dict(sorted(per_day.items())),
    }


@router.get("/workspaces/{workspace_id}/observability/budgets")
def budgets(workspace: dict = Depends(get_current_workspace)):
    """Per-agent spend today vs daily budget, with 80%/100% alert levels (Phase 5.2)."""
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM agent_runs WHERE workspace_id = ? AND created_at >= ?",
            (workspace["id"], _day_start()),
        ).fetchall()
        agent_rows = conn.execute(
            "SELECT id, name, max_budget_usd_per_day FROM agents WHERE workspace_id = ?",
            (workspace["id"],),
        ).fetchall()
    finally:
        conn.close()

    spend: Dict[str, float] = {}
    for run in rows:
        stats = _parse_stats(run["stats"])
        spend[run["agent_id"]] = spend.get(run["agent_id"], 0.0) + ((stats or {}).get("total_cost_usd") or 0.0)

    settings = _workspace_settings(workspace["id"])
    workspace_budget = None
    budget_block = settings.get("budget")
    if isinstance(budget_block, dict):
        workspace_budget = budget_block.get("daily_usd")

    result = []
    for agent in agent_rows:
        agent_spend = round(spend.get(agent["id"], 0.0), 6)
        budget = float(agent["max_budget_usd_per_day"] or 0.0)
        if workspace_budget is not None:
            budget = min(budget, float(workspace_budget)) if budget > 0 else float(workspace_budget)
        pct = (agent_spend / budget * 100.0) if budget > 0 else 0.0
        level = "ok"
        if budget > 0:
            if pct >= 100.0:
                level = "exceeded"
            elif pct >= 80.0:
                level = "warn"
        result.append({
            "agent_id": agent["id"],
            "agent_name": agent["name"],
            "spend_today_usd": agent_spend,
            "budget_usd": budget,
            "pct": round(pct, 1),
            "level": level,
        })
    return {"agents": result, "workspace_daily_budget_usd": workspace_budget}


@router.get("/workspaces/{workspace_id}/observability/events")
def run_events(
    workspace: dict = Depends(get_current_workspace),
    run_id: Optional[str] = None,
    limit: int = Query(default=200, ge=1, le=2000),
):
    """Persisted run events (structured logs) for a run or the whole workspace."""
    query = "SELECT run_id, seq, event, data, ts FROM run_events WHERE workspace_id = ?"
    params: list = [workspace["id"]]
    if run_id:
        query += " AND run_id = ?"
        params.append(run_id)
    query += " ORDER BY seq DESC LIMIT ?"
    params.append(limit)

    conn = db.get_db()
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    events = []
    for row in rows:
        try:
            data = json.loads(row["data"])
        except (json.JSONDecodeError, TypeError):
            data = {}
        events.append({"run_id": row["run_id"], "seq": row["seq"], "event": row["event"],
                       "data": data, "ts": row["ts"]})
    return {"events": events}


@router.get("/workspaces/{workspace_id}/observability/alerts")
def alerts(workspace: dict = Depends(get_current_workspace), limit: int = Query(default=50, ge=1, le=200)):
    """Recent budget alert rows (warn / exceeded)."""
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM budget_alerts WHERE workspace_id = ? ORDER BY created_at DESC LIMIT ?",
            (workspace["id"], limit),
        ).fetchall()
    finally:
        conn.close()
    return {"alerts": [dict(r) for r in rows]}


# --------------------------------------------------------------------------
# Helpers used by the runtime
# --------------------------------------------------------------------------

def record_budget_alert(workspace_id: str, agent_id: str, run_id: str, level: str, message: str) -> None:
    """Insert a budget alert row (called from the runtime at run end)."""
    import uuid

    conn = db.get_db()
    try:
        conn.execute(
            """
            INSERT INTO budget_alerts (id, workspace_id, agent_id, run_id, level, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (uuid.uuid4().hex, workspace_id, agent_id, run_id, level, message, _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()
