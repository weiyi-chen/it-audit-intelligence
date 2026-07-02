"""
Async PBC review flow — LangGraph interrupt/resume endpoints.

Endpoints
─────────
  POST /api/pbc/async/start          → launch graph, pause at review_node
  GET  /api/pbc/async/{tid}/status   → inspect current checkpoint state
  POST /api/pbc/async/{tid}/approve  → resume with approved=True
  POST /api/pbc/async/{tid}/reject   → resume with approved=False + notes

This is the difference between the existing /api/pbc/generate (fire-and-forget,
auto-approve) and this flow (pause, let the auditor review a draft, then resume).

Architecture
────────────
  ┌─────────────┐   /start    ┌───────────┐  interrupt()  ┌──────────────┐
  │  Auditor    │ ──────────► │ FastAPI   │ ─────────────► │ MemorySaver  │
  │  (browser)  │             │           │               │ (checkpoint)  │
  │             │ ◄────────── │ thread_id │ ◄───────────── │              │
  └─────────────┘  pending    └───────────┘  state saved  └──────────────┘
        │
        │  reviews draft xlsx
        │
        │   /approve        ┌───────────┐  Command(resume)  ┌──────────────┐
        └─────────────────► │ FastAPI   │ ────────────────► │ MemorySaver  │
                            │           │                   │  (resume)    │
                            │ xlsx_b64  │ ◄──────────────── │ output_node  │
                            └───────────┘  completed        └──────────────┘

Production swap
───────────────
  Change one line in api/checkpointer.py to use SqliteSaver instead of
  MemorySaver — state survives server restarts, multiple workers, etc.
"""

from __future__ import annotations

import base64
import os
import sys
import tempfile
import time
import types
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

# ── langgraph stub (if main module not installed) ─────────────────────────────
try:
    import langgraph  # noqa: F401
except ModuleNotFoundError:
    _fake = types.ModuleType("langgraph")
    _fake.graph = types.ModuleType("langgraph.graph")                             # type: ignore
    _fake.graph.message = types.ModuleType("langgraph.graph.message")             # type: ignore
    _fake.graph.message.add_messages = lambda x: x                                # type: ignore
    sys.modules["langgraph"]               = _fake
    sys.modules["langgraph.graph"]         = _fake.graph                          # type: ignore
    sys.modules["langgraph.graph.message"] = _fake.graph.message                  # type: ignore

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from api.checkpointer import checkpointer_info, get_checkpointer
from api.schemas import (
    AsyncResumeResponse,
    AsyncStartResponse,
    AsyncStatusResponse,
    ResumeRequest,
    ScopeChangeSummary,
)
from core.llm import has_real_key
from core.state import default_state
from modules.pbc.graph import build_compiled_graph

router = APIRouter(prefix="/api/pbc/async", tags=["async-review"])

# ── module-level compiled graph (shares checkpointer singleton) ───────────────
_app = build_compiled_graph(get_checkpointer())

# ── constants ─────────────────────────────────────────────────────────────────
_INTERRUPT_KEY = "__interrupt__"


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/pbc/async/start
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/start", response_model=AsyncStartResponse)
async def async_start(
    scope_text:   str        = Form(...,         description="Current-year scope memo"),
    client_name:  str        = Form("Client",    description="Client name"),
    audit_period: str        = Form("FY2025",    description="Audit period"),
    prior_xlsx:   Optional[UploadFile] = File(None, description="Prior-year PBC xlsx"),
) -> AsyncStartResponse:
    """
    Launch the Module A pipeline with checkpointing.

    The graph runs:  ingest → scope_diff → update_items → [INTERRUPT at review_node]

    Returns a thread_id.  The auditor then calls /status to inspect the draft
    and /approve or /reject to resume the graph.
    """
    t0 = time.time()

    prior_path = ""
    tmp_in: Optional[str] = None

    if prior_xlsx and prior_xlsx.filename:
        content = await prior_xlsx.read()
        if content:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
                f.write(content)
                tmp_in = f.name
            prior_path = tmp_in

    # Generate a deterministic-ish thread_id
    safe_client = client_name.lower().replace(" ", "_")
    safe_period = audit_period.lower().replace(" ", "_")
    thread_id   = f"{safe_client}_{safe_period}_{int(t0)}"

    # Temp output path (may not be written yet — output_node hasn't run)
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        tmp_out = f.name

    try:
        state = default_state(
            client_name  = client_name,
            audit_period = audit_period,
            thread_id    = thread_id,
        )
        state["prior_year_pbc_path"]     = prior_path
        state["current_year_scope_text"] = scope_text
        state["pbc_output_xlsx_path"]    = tmp_out

        config = {"configurable": {"thread_id": thread_id}}

        # ── invoke — graph pauses at review_node ──────────────────────────────
        result = _app.invoke(state, config)

        # If no interrupt occurred (e.g. running without real checkpointer support),
        # the graph completed fully — treat as completed and redirect to output.
        if _INTERRUPT_KEY not in result:
            # Fallback: return a "completed" response (same as sync endpoint)
            items    = result.get("current_year_items", [])
            changes  = result.get("scope_changes", [])
            by_status: dict[str, int] = {}
            for item in items:
                s = item.get("status", "carried_over")
                by_status[s] = by_status.get(s, 0) + 1
            return AsyncStartResponse(
                thread_id        = thread_id,
                status           = "completed_no_interrupt",
                client_name      = client_name,
                audit_period     = audit_period,
                item_count       = len(items),
                status_breakdown = by_status,
                scope_changes    = _extract_scope_changes(changes),
                llm_mode         = "real" if has_real_key() else "mock",
                elapsed_seconds  = round(time.time() - t0, 2),
                checkpointer_type = checkpointer_info()["type"],
                message          = "Graph completed without interrupt (checkpointer not active).",
            )

        # ── interrupted at review_node ────────────────────────────────────────
        interrupt_payload = result[_INTERRUPT_KEY][0].value
        items   = result.get("current_year_items", [])
        changes = result.get("scope_changes", [])
        by_status = interrupt_payload.get("status_breakdown", {})

        return AsyncStartResponse(
            thread_id        = thread_id,
            status           = "pending_review",
            client_name      = client_name,
            audit_period     = audit_period,
            item_count       = interrupt_payload.get("item_count", len(items)),
            status_breakdown = by_status,
            scope_changes    = _extract_scope_changes(changes),
            llm_mode         = "real" if has_real_key() else "mock",
            elapsed_seconds  = round(time.time() - t0, 2),
            checkpointer_type = checkpointer_info()["type"],
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Async start error: {exc}") from exc
    finally:
        for p in [tmp_in]:
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/pbc/async/{thread_id}/status
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{thread_id}/status", response_model=AsyncStatusResponse)
async def async_status(thread_id: str) -> AsyncStatusResponse:
    """
    Inspect the current LangGraph checkpoint for a thread.

    Returns state values + which node executes next (useful for the UI to
    know whether the graph is still paused or has completed).
    """
    config = {"configurable": {"thread_id": thread_id}}
    try:
        snapshot = _app.get_state(config)
    except Exception as exc:
        raise HTTPException(500, f"get_state error: {exc}") from exc

    if snapshot is None or not snapshot.values:
        return AsyncStatusResponse(thread_id=thread_id, status="not_found")

    values   = snapshot.values
    items    = values.get("current_year_items", [])
    changes  = values.get("scope_changes", [])
    next_nodes = list(snapshot.next) if snapshot.next else []

    by_status: dict[str, int] = {}
    for item in items:
        s = item.get("status", "carried_over")
        by_status[s] = by_status.get(s, 0) + 1

    # Determine status from graph position
    has_pending_interrupt = bool(getattr(snapshot, "tasks", None))
    if "output_node" in next_nodes or (not next_nodes and values.get("pbc_output_xlsx_path")):
        status = "completed"
    elif next_nodes:
        status = "pending_review"
    else:
        status = "pending_review" if not values.get("review_passed") else "completed"

    return AsyncStatusResponse(
        thread_id        = thread_id,
        status           = status,
        item_count       = len(items),
        status_breakdown = by_status,
        scope_changes    = _extract_scope_changes(changes),
        next_node        = next_nodes[0] if next_nodes else None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/pbc/async/{thread_id}/approve
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{thread_id}/approve", response_model=AsyncResumeResponse)
async def async_approve(
    thread_id: str,
    req: ResumeRequest = ResumeRequest(),
) -> AsyncResumeResponse:
    """
    Resume a paused graph run with approval.

    Command(resume={"approved": True}) is injected into the checkpoint.
    The graph continues from review_node → output_node → END.
    Returns the final xlsx as base64.
    """
    return await _resume(thread_id, approved=True, notes=req.notes)


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/pbc/async/{thread_id}/reject
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{thread_id}/reject", response_model=AsyncResumeResponse)
async def async_reject(
    thread_id: str,
    req: ResumeRequest = ResumeRequest(),
) -> AsyncResumeResponse:
    """
    Resume a paused graph run with rejection.

    Command(resume={"approved": False, "notes": "..."}) causes review_node
    to set review_passed=False → review_router → update_items_node (loop).
    The graph runs update_items again (with real LLM, it can incorporate the
    rejection notes), then hits review_node interrupt again.
    Response status="pending_review" with the revised draft.
    """
    return await _resume(thread_id, approved=False, notes=req.notes)


# ─────────────────────────────────────────────────────────────────────────────
# Internal resume helper
# ─────────────────────────────────────────────────────────────────────────────

async def _resume(
    thread_id: str,
    approved: bool,
    notes: str,
) -> AsyncResumeResponse:
    from langgraph.types import Command  # type: ignore[import]

    t0     = time.time()
    config = {"configurable": {"thread_id": thread_id}}

    # Temp output path for approve path
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        tmp_out = f.name

    # Update the output path in state so output_node writes there
    try:
        snapshot = _app.get_state(config)
        if snapshot is None or not snapshot.values:
            raise HTTPException(404, f"Thread {thread_id!r} not found in checkpointer.")

        # Inject the output path into state before resuming
        _app.update_state(config, {"pbc_output_xlsx_path": tmp_out})

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"get_state/update_state error: {exc}") from exc

    try:
        decision = {"approved": approved}
        if notes:
            decision["notes"] = notes

        result = _app.invoke(Command(resume=decision), config)

        items   = result.get("current_year_items", [])
        changes = result.get("scope_changes", [])
        by_status: dict[str, int] = {}
        for item in items:
            s = item.get("status", "carried_over")
            by_status[s] = by_status.get(s, 0) + 1

        # ── still paused (rejection → loop → paused again) ───────────────────
        if _INTERRUPT_KEY in result:
            return AsyncResumeResponse(
                thread_id        = thread_id,
                status           = "pending_review",
                item_count       = len(items),
                status_breakdown = by_status,
                scope_changes    = _extract_scope_changes(changes),
                message          = "Draft revised — awaiting approval.",
                elapsed_seconds  = round(time.time() - t0, 2),
            )

        # ── graph completed (approve path) ────────────────────────────────────
        xlsx_b64 = None
        xlsx_filename = None
        if os.path.exists(tmp_out):
            with open(tmp_out, "rb") as f:
                xlsx_b64 = base64.b64encode(f.read()).decode()
            safe_client = result.get("client_name", "client").lower().replace(" ", "_")
            safe_period = result.get("audit_period", "fy").lower()
            xlsx_filename = f"{safe_client}_{safe_period}_pbc.xlsx"

        return AsyncResumeResponse(
            thread_id        = thread_id,
            status           = "completed",
            item_count       = len(items),
            status_breakdown = by_status,
            scope_changes    = _extract_scope_changes(changes),
            xlsx_base64      = xlsx_b64,
            xlsx_filename    = xlsx_filename,
            llm_mode         = "real" if has_real_key() else "mock",
            elapsed_seconds  = round(time.time() - t0, 2),
            message          = "PBC list approved and finalised.",
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Resume error: {exc}") from exc
    finally:
        if os.path.exists(tmp_out):
            try:
                os.unlink(tmp_out)
            except OSError:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _extract_scope_changes(changes: list) -> list:
    from api.schemas import ScopeChangeSummary
    return [
        ScopeChangeSummary(
            change_type         = c.get("change_type", ""),
            description         = c.get("description", ""),
            affected_categories = c.get("affected_categories", []),
        )
        for c in changes
        if isinstance(c, dict)
    ]
