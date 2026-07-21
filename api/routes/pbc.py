"""
POST /api/pbc/generate
──────────────────────
Accepts a multipart form with an optional prior-year xlsx upload plus metadata,
runs the Module A pipeline, and returns a JSON response that includes the
generated xlsx as a base64 string for client-side download.

Form fields
───────────
  prior_xlsx  : UploadFile (optional) — prior-year PBC list (.xlsx)
  scope_text  : str                   — current-year scope memo (plain text)
  client_name : str (default "Client")
  audit_period: str (default "FY2025")

The pipeline is the same five-node chain used by demo_run.py:
    ingest → scope_diff → update_items → review → output
It can run with either a real Anthropic API key or the built-in mock.
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

# ── langgraph stub (if not installed) ────────────────────────────────────────
try:
    import langgraph  # noqa: F401
except ModuleNotFoundError:
    _fake = types.ModuleType("langgraph")
    _fake.graph = types.ModuleType("langgraph.graph")                           # type: ignore[attr-defined]
    _fake.graph.message = types.ModuleType("langgraph.graph.message")           # type: ignore[attr-defined]
    _fake.graph.message.add_messages = lambda x: x                              # type: ignore[attr-defined]
    sys.modules["langgraph"]               = _fake
    sys.modules["langgraph.graph"]         = _fake.graph                        # type: ignore[attr-defined]
    sys.modules["langgraph.graph.message"] = _fake.graph.message                # type: ignore[attr-defined]

# project root on sys.path (api/ is one level below root)
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from core.llm import has_real_key
from core.state import default_state
from modules.pbc.nodes import (
    ingest_node,
    output_node,
    review_node,
    retrieve_regulatory_guidance_node,
    scope_diff_node,
    update_items_node,
)
from api.schemas import (
    PBCGenerateResponse,
    RegulatorySourceSummary,
    ScopeChangeSummary,
)
from api.database import db

router = APIRouter()


@router.post("/api/pbc/generate", response_model=PBCGenerateResponse)
async def generate_pbc(
    scope_text:   str        = Form(...,  description="Current-year scope memo text"),
    client_name:  str        = Form("Client",  description="Client name"),
    audit_period: str        = Form("FY2025",  description="Audit period, e.g. FY2025"),
    jurisdiction: str        = Form("*", description="Jurisdiction code or *"),
    industry: str            = Form("*", description="Industry or *"),
    prior_xlsx:   Optional[UploadFile] = File(None, description="Prior-year PBC xlsx (optional)"),
) -> PBCGenerateResponse:
    """
    Run the Module A PBC generation pipeline and return the result xlsx.
    """
    t0 = time.time()

    # ── save uploaded xlsx to a temp file ────────────────────────────────────
    prior_path = ""
    tmp_in: Optional[str] = None

    if prior_xlsx and prior_xlsx.filename:
        content = await prior_xlsx.read()
        if content:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
                f.write(content)
                tmp_in = f.name
            prior_path = tmp_in

    # ── output temp file ─────────────────────────────────────────────────────
    safe_client = client_name.lower().replace(" ", "_")
    safe_period = audit_period.lower()
    out_filename = f"{safe_client}_{safe_period}_pbc.xlsx"

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        tmp_out = f.name

    try:
        # ── build initial state ───────────────────────────────────────────────
        state = default_state(
            client_name  = client_name,
            audit_period = audit_period,
            thread_id    = f"api_{int(t0)}",
        )
        state["prior_year_pbc_path"]     = prior_path
        state["current_year_scope_text"] = scope_text
        state["pbc_output_xlsx_path"]    = tmp_out
        state["jurisdiction"]             = jurisdiction
        state["industry"]                 = industry

        # ── run five nodes in sequence ────────────────────────────────────────
        # (Same as demo_run.py — bypasses StateGraph so no langgraph needed.)
        # When Phase 4 wires the real graph + checkpointer, swap this block with:
        #   app = build_pbc_graph().compile(checkpointer=...)
        #   final = app.invoke(state, config={"configurable": {"thread_id": ...}})
        state = {**state, **ingest_node(state)}
        state = {**state, **scope_diff_node(state)}
        state = {**state, **retrieve_regulatory_guidance_node(state)}
        state = {**state, **update_items_node(state)}
        state = {**state, **review_node(state)}
        state = {**state, **output_node(state)}

        # ── read generated xlsx → base64 ──────────────────────────────────────
        if not os.path.exists(tmp_out):
            raise HTTPException(500, "Pipeline completed but output xlsx was not created.")

        with open(tmp_out, "rb") as f:
            xlsx_b64 = base64.b64encode(f.read()).decode()

        # ── build response ────────────────────────────────────────────────────
        items   = state.get("current_year_items", [])
        changes = state.get("scope_changes", [])

        by_status: dict[str, int] = {}
        for item in items:
            s = item.get("status", "carried_over")
            by_status[s] = by_status.get(s, 0) + 1

        llm_mode      = "real" if has_real_key() else "mock"
        elapsed_secs  = round(time.time() - t0, 2)

        # ── persist to SQLite ─────────────────────────────────────────────────
        try:
            db.save_run(
                client_name      = client_name,
                audit_period     = audit_period,
                scope_text       = scope_text,
                item_count       = len(items),
                llm_mode         = llm_mode,
                elapsed_secs     = elapsed_secs,
                xlsx_base64      = xlsx_b64,
                xlsx_filename    = out_filename,
                scope_changes    = changes,
                status_breakdown = by_status,
            )
        except Exception:
            pass  # storage failure must never break the main response

        return PBCGenerateResponse(
            client_name      = client_name,
            audit_period     = audit_period,
            scope_changes    = [
                ScopeChangeSummary(
                    change_type         = c.get("change_type", ""),
                    description         = c.get("description", ""),
                    affected_categories = c.get("affected_categories", []),
                )
                for c in changes
            ],
            regulatory_sources = [
                RegulatorySourceSummary(
                    requirement_id=str(g.get("requirement_id", "")),
                    title=str(g.get("title", "")),
                    version=str(g.get("version", "")),
                    citation=str(g.get("citation", "")),
                    retrieval_score=float(g.get("retrieval_score", 0.0)),
                )
                for g in state.get("regulatory_guidance", [])
            ],
            item_count       = len(items),
            status_breakdown = by_status,
            xlsx_base64      = xlsx_b64,
            xlsx_filename    = out_filename,
            llm_mode         = llm_mode,
            elapsed_seconds  = elapsed_secs,
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Pipeline error: {exc}") from exc

    finally:
        # clean up temp files
        for p in [tmp_in, tmp_out]:
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass
