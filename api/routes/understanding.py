"""
POST /api/understanding/build
─────────────────────────────
Accepts evidence files (IT memo, system inventory, walkthrough notes) and
scope text, runs the Module B pipeline, and returns:
  • extracted_entities  — structured list of IT entities
  • entity_relationships — inferred connections with confidence scores
  • network_json         — {nodes, edges} ready for vis-network / D3 rendering
  • map_html_base64      — standalone HTML file as base64 (client-side download)

Form fields
───────────
  scope_text   : str            — scope memo / IT understanding memo text
  client_name  : str
  audit_period : str
  evidence_files: UploadFile[]  — optional evidence docs (docx, xlsx, txt, pdf)
"""

from __future__ import annotations

import base64
import os
import sys
import tempfile
import time
import types
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

# ── langgraph stub ────────────────────────────────────────────────────────────
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

from core.llm import has_real_key
from core.state import default_state
from modules.understanding.nodes import (
    extract_entities_node,
    infer_relations_node,
    render_map_node,
)

router = APIRouter(tags=["understanding"])


# ─────────────────────────────────────────────────────────────────────────────
# Response schema (inline — avoids circular imports)
# ─────────────────────────────────────────────────────────────────────────────

class EntityOut(BaseModel):
    entity_id:   str
    entity_type: str
    name:        str
    attributes:  dict = {}


class RelationOut(BaseModel):
    source_id:     str
    target_id:     str
    relation:      str
    confidence:    float
    evidence_quote: str = ""


class UnderstandingBuildResponse(BaseModel):
    client_name:          str
    audit_period:         str
    entity_count:         int
    relation_count:       int
    extracted_entities:   List[EntityOut]
    entity_relationships: List[RelationOut]
    network_json:         dict            # {nodes: [...], edges: [...]}
    map_html_base64:      Optional[str]   # standalone HTML file
    llm_mode:             str
    elapsed_seconds:      float


# ─────────────────────────────────────────────────────────────────────────────
# Route
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/api/understanding/build", response_model=UnderstandingBuildResponse)
async def build_understanding(
    scope_text:     str = Form("", description="Scope memo / IT understanding memo text"),
    client_name:    str = Form("Client", description="Client name"),
    audit_period:   str = Form("FY2025", description="Audit period"),
    evidence_files: List[UploadFile] = File(default=[], description="Evidence documents"),
) -> UnderstandingBuildResponse:
    """
    Run the Module B pipeline:
      1. extract_entities  — Claude reads documents, returns structured entities
      2. infer_relations   — Claude infers connections between entities
      3. render_map        — generates vis-network JSON + standalone HTML

    Works in both real LLM mode (ANTHROPIC_API_KEY set) and mock mode.
    In mock mode, returns a sample ACME Corp entity set for demo purposes.
    """
    t0 = time.time()

    # ── save uploaded files to temp paths ────────────────────────────────────
    tmp_paths: list[str] = []
    tmp_files_to_clean: list[str] = []

    for uf in evidence_files:
        if not uf.filename:
            continue
        content = await uf.read()
        if not content:
            continue
        suffix = os.path.splitext(uf.filename)[1] or ".txt"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(content)
            tmp_paths.append(f.name)
            tmp_files_to_clean.append(f.name)

    # ── output HTML path ─────────────────────────────────────────────────────
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        tmp_html = f.name
    tmp_files_to_clean.append(tmp_html)

    try:
        # ── build state ───────────────────────────────────────────────────────
        state = default_state(client_name=client_name, audit_period=audit_period)
        state["current_year_scope_text"] = scope_text
        state["evidence_paths"]          = tmp_paths
        state["map_output_html_path"]    = tmp_html

        # ── run pipeline (direct node calls — no graph overhead) ──────────────
        state = {**state, **extract_entities_node(state)}
        state = {**state, **infer_relations_node(state)}
        state = {**state, **render_map_node(state)}

        entities  = state.get("extracted_entities", [])
        relations = state.get("entity_relationships", [])
        net_json  = state.get("network_json", {"nodes": [], "edges": []})

        # ── read HTML → base64 ────────────────────────────────────────────────
        html_b64: Optional[str] = None
        if os.path.exists(tmp_html):
            with open(tmp_html, "rb") as f:
                html_b64 = base64.b64encode(f.read()).decode()

        return UnderstandingBuildResponse(
            client_name          = client_name,
            audit_period         = audit_period,
            entity_count         = len(entities),
            relation_count       = len(relations),
            extracted_entities   = [EntityOut(**e)   for e in entities],
            entity_relationships = [RelationOut(**r) for r in relations],
            network_json         = net_json,
            map_html_base64      = html_b64,
            llm_mode             = "real" if has_real_key() else "mock",
            elapsed_seconds      = round(time.time() - t0, 2),
        )

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, f"Module B pipeline error: {exc}") from exc
    finally:
        for p in tmp_files_to_clean:
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass
