"""
GET /api/pbc/history        — list recent runs (newest first, no xlsx blob)
GET /api/pbc/runs/{run_id}  — fetch full run including xlsx base64
DELETE /api/pbc/runs/{run_id} — remove a run from history
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from api.database import db
from api.schemas import HistoryResponse, RunDetail, RunSummary, ScopeChangeSummary

router = APIRouter()


@router.get("/api/pbc/history", response_model=HistoryResponse, tags=["history"])
async def list_history(
    limit: int = Query(default=50, ge=1, le=200, description="Max rows to return"),
) -> HistoryResponse:
    """Return recent PBC generation runs, newest first."""
    rows = db.list_runs(limit=limit)
    summaries = [_to_summary(r) for r in rows]
    return HistoryResponse(runs=summaries, total=len(summaries))


@router.get("/api/pbc/runs/{run_id}", response_model=RunDetail, tags=["history"])
async def get_run(run_id: int) -> RunDetail:
    """Return a single run with the xlsx included as base64."""
    row = db.get_run(run_id)
    if row is None:
        raise HTTPException(404, f"Run {run_id} not found.")
    return _to_detail(row)


@router.delete("/api/pbc/runs/{run_id}", tags=["history"])
async def delete_run(run_id: int) -> dict:
    """Remove a run from history (irreversible)."""
    deleted = db.delete_run(run_id)
    if not deleted:
        raise HTTPException(404, f"Run {run_id} not found.")
    return {"deleted": True, "run_id": run_id}


# ── helpers ───────────────────────────────────────────────────────────────────

def _to_summary(row: dict) -> RunSummary:
    raw_changes = row.get("scope_changes") or []
    return RunSummary(
        id              = row["id"],
        client_name     = row["client_name"],
        audit_period    = row["audit_period"],
        item_count      = row.get("item_count"),
        llm_mode        = row.get("llm_mode"),
        elapsed_secs    = row.get("elapsed_secs"),
        xlsx_filename   = row.get("xlsx_filename"),
        scope_changes   = [
            ScopeChangeSummary(
                change_type         = c.get("change_type", ""),
                description         = c.get("description", ""),
                affected_categories = c.get("affected_categories", []),
            )
            for c in raw_changes
        ],
        status_breakdown = row.get("status_breakdown"),
        created_at       = row.get("created_at"),
    )


def _to_detail(row: dict) -> RunDetail:
    summary = _to_summary(row)
    return RunDetail(**summary.model_dump(), xlsx_base64=row.get("xlsx_base64"))
