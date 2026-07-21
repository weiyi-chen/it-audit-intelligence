"""
Module A — PBC Checklist Generator nodes (Phase 2 real logic).

Node contracts
──────────────
ingest_node       : reads prior year xlsx → state["prior_year_items"]
scope_diff_node   : Claude extracts List[ScopeChange] from scope text
retrieve_guidance : retrieves effective approved methodology requirements
update_items_node : Claude decides keep/update/remove per prior item;
                    new items generated from templates and retrieved guidance
review_node       : auto-approve placeholder (Phase 4 wires to FastAPI interrupt)
output_node       : writes current_year_items → xlsx; sets pbc_output_xlsx_path

LLM calls
──────────
All LLM calls go through core.llm.call_claude which transparently falls back
to a deterministic mock when ANTHROPIC_API_KEY is absent/placeholder.
This lets the entire pipeline run in test/demo mode without API credits.

Error handling
──────────────
Each node catches exceptions and sets state["error"] rather than crashing
the graph.  The graph continues to output_node even on partial errors so
auditors always get an output xlsx (possibly with fewer items).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, List

from core.llm import call_claude
from core.state import PBCItem, ScopeChange, State
from modules.pbc.regulatory_rag import RetrievalQuery, retrieve_guidance
from modules.pbc.templates import CATEGORIES, instantiate_items
from modules.pbc.xlsx_io import read_pbc_xlsx, write_pbc_xlsx

# ─────────────────────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────────────────────

_SCOPE_DIFF_SYSTEM = """\
You are an expert IT auditor specialising in ITGC (IT General Controls).
Your task is to analyse a scope memo and identify all changes relative to a
standard prior-year audit scope.

Respond ONLY with a valid JSON array — no markdown fences, no explanation.
Each element must conform to this shape:
{
  "change_type": "<system_added|system_removed|period_change|regulation_change|sample_size_change>",
  "description": "<one sentence describing the change>",
  "affected_categories": ["<category name>", ...]
}

Valid category names:
  "IT Systems Understanding"
  "ITGC - JML"
  "ITGC - UAR"
  "ITGC - ChangeMgmt"
  "ITGC - PrivAccess"
  "ITGC - ProgramDev"
  "ITGC - Backup"

If NO changes are detected, return an empty array: []
"""

_SCOPE_DIFF_USER = """\
Audit period: {audit_period}
Client: {client_name}

Scope memo:
\"\"\"
{scope_text}
\"\"\"

Identify all scope changes relative to a standard prior-year ITGC audit.
Return the JSON array of ScopeChange objects.
"""

_UPDATE_ITEMS_SYSTEM = """\
You are an expert IT auditor. For each PBC (Provided By Client) item from
last year's audit, decide what to do this year given the detected scope changes.

Respond ONLY with a valid JSON array — no markdown fences, no explanation.
Each element must conform to this shape:
{
  "item_id": "<original item_id>",
  "decision": "<keep|update|remove>",
  "updated_description": "<new description if decision=update, else null>",
  "notes": "<brief reason>"
}

Decision rules:
  keep   — item is still relevant and wording needs no change
  update — item is still relevant but description or sample size needs revision
  remove — item is no longer applicable (system out of scope, control retired, etc.)

Return one decision object for EVERY item_id in the input — do not omit any.
"""

_UPDATE_ITEMS_USER = """\
Audit period: {audit_period}
Client: {client_name}

Detected scope changes:
{scope_changes_json}

Retrieved approved methodology and regulatory guidance:
{regulatory_guidance_json}

Prior year PBC items (batch):
{items_json}

Return the JSON array of decisions.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Helper: parse JSON safely
# ─────────────────────────────────────────────────────────────────────────────

def _parse_json_array(raw: str, context: str = "") -> list:
    """
    Extract and parse the first JSON array from *raw*.

    Strips markdown code fences if present.  Returns [] on parse failure
    and logs a warning so the graph continues rather than crashing.
    """
    # Strip ```json ... ``` or ``` ... ```
    stripped = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()

    # If the string contains multiple top-level JSON values, grab the first array.
    # Locate the first '[' and find its matching ']'.
    start = stripped.find("[")
    if start == -1:
        print(f"[{context}] ⚠️  No JSON array found in LLM response — returning []")
        return []

    depth = 0
    end = start
    for i, ch in enumerate(stripped[start:], start=start):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i
                break

    try:
        return json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as exc:
        print(f"[{context}] ⚠️  JSON parse error: {exc} — returning []")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Helper: generate a new item_id
# ─────────────────────────────────────────────────────────────────────────────

def _next_id(existing_ids: set[str], prefix: str) -> str:
    """
    Find the next available sequential id for a given prefix.
    e.g. prefix='JML' → 'JML-001' if unused, else 'JML-002', etc.
    """
    seq = 1
    while True:
        candidate = f"{prefix}-{seq:03d}"
        if candidate not in existing_ids:
            return candidate
        seq += 1


# ─────────────────────────────────────────────────────────────────────────────
# Node 1 — ingest_node
# ─────────────────────────────────────────────────────────────────────────────

def ingest_node(state: State) -> dict:
    """
    Read the prior year PBC xlsx and load it into state["prior_year_items"].

    Also captures current_year_scope_text from state (it arrives via the
    initial graph invocation — set by the CLI / API caller).

    State mutations
    ───────────────
    prior_year_items  ← parsed PBCItem list ([] if path not provided)
    error             ← set on file read failure (prior items stay [])
    """
    print("[ingest_node] starting")

    path = state.get("prior_year_pbc_path", "")
    scope_text = state.get("current_year_scope_text", "")

    if not path:
        print("[ingest_node] no prior_year_pbc_path provided — starting with empty list")
        return {"prior_year_items": [], "current_year_scope_text": scope_text}

    try:
        items = read_pbc_xlsx(path)
        print(f"[ingest_node] loaded {len(items)} prior-year items from {path!r}")
        return {
            "prior_year_items": items,
            "current_year_scope_text": scope_text,
        }
    except FileNotFoundError as exc:
        msg = f"[ingest_node] ❌ file not found: {exc}"
        print(msg)
        return {"prior_year_items": [], "error": str(exc)}
    except Exception as exc:
        msg = f"[ingest_node] ❌ unexpected error reading xlsx: {exc}"
        print(msg)
        return {"prior_year_items": [], "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Node 2 — scope_diff_node
# ─────────────────────────────────────────────────────────────────────────────

def scope_diff_node(state: State) -> dict:
    """
    Call Claude to extract List[ScopeChange] from the current_year_scope_text.

    State mutations
    ───────────────
    scope_changes ← List[ScopeChange] ([] if no changes or on error)
    error         ← set on LLM / parse failure (scope_changes stays [])
    """
    print("[scope_diff_node] starting")

    scope_text = state.get("current_year_scope_text", "").strip()
    if not scope_text:
        print("[scope_diff_node] no scope text — returning empty change list")
        return {"scope_changes": []}

    prompt = _SCOPE_DIFF_USER.format(
        audit_period=state.get("audit_period", ""),
        client_name =state.get("client_name",  ""),
        scope_text  =scope_text,
    )

    try:
        raw = call_claude(prompt, system=_SCOPE_DIFF_SYSTEM)
        changes_raw = _parse_json_array(raw, context="scope_diff_node")

        # Coerce each element into a valid ScopeChange dict
        changes: List[ScopeChange] = []
        for item in changes_raw:
            if not isinstance(item, dict):
                continue
            changes.append(
                ScopeChange(
                    change_type         = str(item.get("change_type", "unknown")),
                    description         = str(item.get("description", "")),
                    affected_categories = list(item.get("affected_categories", [])),
                )
            )

        print(f"[scope_diff_node] detected {len(changes)} scope change(s):")
        for c in changes:
            print(f"  • [{c['change_type']}] {c['description']}")

        return {"scope_changes": changes}

    except Exception as exc:
        msg = f"[scope_diff_node] ❌ error: {exc}"
        print(msg)
        return {"scope_changes": [], "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Node 3 — retrieve_regulatory_guidance_node
# ─────────────────────────────────────────────────────────────────────────────

def retrieve_regulatory_guidance_node(state: State) -> dict:
    """Retrieve approved guidance applicable to this preliminary audit scope.

    The scope memo is short and remains direct LLM context. RAG is used only for
    the larger, versioned methodology corpus where effective dates, metadata,
    ranking, and source citations matter.
    """
    scope_changes = state.get("scope_changes", [])
    control_areas = sorted({
        category
        for change in scope_changes
        for category in change.get("affected_categories", [])
    })
    prior_context = " ".join(
        f"{item.get('category', '')} {item.get('description', '')}"
        for item in state.get("prior_year_items", [])[:30]
    )
    query_text = " ".join([
        "current effective audit methodology regulatory requirements",
        state.get("current_year_scope_text", ""),
        prior_context,
        " ".join(control_areas),
    ])
    try:
        guidance = retrieve_guidance(
            RetrievalQuery(
                text=query_text,
                audit_period=state.get("audit_period", ""),
                jurisdiction=str(state.get("jurisdiction", "*")),
                industry=str(state.get("industry", "*")),
                control_areas=tuple(control_areas),
            )
        )
        print(
            "[retrieve_regulatory_guidance_node] retrieved "
            f"{len(guidance)} approved requirement(s)"
        )
        return {"regulatory_guidance": guidance}
    except Exception as exc:
        print(f"[retrieve_regulatory_guidance_node] error: {exc}")
        return {"regulatory_guidance": [], "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Node 4 — update_items_node
# ─────────────────────────────────────────────────────────────────────────────

_BATCH_SIZE = 20  # items per Claude call


def update_items_node(state: State) -> dict:
    """
    Produce current_year_items by:
      1. Asking Claude (in batches) to decide keep/update/remove for each
         prior year item.
      2. For each system_added scope change, instantiating new PBCItems from
         the standard templates in modules/pbc/templates.py.

    State mutations
    ───────────────
    current_year_items ← List[PBCItem] with updated status fields
    error              ← set on partial failure (items already processed are kept)
    """
    print("[update_items_node] starting")

    prior_items  : List[PBCItem]   = state.get("prior_year_items",  [])
    scope_changes: List[ScopeChange] = state.get("scope_changes",   [])
    regulatory_guidance = state.get("regulatory_guidance", [])
    audit_period : str             = state.get("audit_period",       "")
    client_name  : str             = state.get("client_name",        "")

    current_items: List[PBCItem] = []
    used_ids: set[str] = {item["item_id"] for item in prior_items}

    # ── Step 1: per-item decisions from Claude ─────────────────────────────
    if prior_items:
        print(f"[update_items_node] processing {len(prior_items)} prior items "
              f"in batches of {_BATCH_SIZE}")

        decisions_map: dict[str, dict[str, Any]] = {}

        for batch_start in range(0, len(prior_items), _BATCH_SIZE):
            batch = prior_items[batch_start : batch_start + _BATCH_SIZE]
            batch_num = batch_start // _BATCH_SIZE + 1
            print(f"[update_items_node]   batch {batch_num}: items "
                  f"{batch_start + 1}–{batch_start + len(batch)}")

            prompt = _UPDATE_ITEMS_USER.format(
                audit_period      = audit_period,
                client_name       = client_name,
                scope_changes_json= json.dumps(scope_changes, indent=2),
                regulatory_guidance_json=json.dumps(
                    [
                        {
                            "requirement_id": requirement.get("requirement_id"),
                            "content": requirement.get("content"),
                            "citation": requirement.get("citation"),
                        }
                        for requirement in regulatory_guidance
                    ],
                    indent=2,
                ),
                items_json        = json.dumps(batch, indent=2),
            )

            try:
                raw = call_claude(prompt, system=_UPDATE_ITEMS_SYSTEM)
                raw_decisions = _parse_json_array(raw, context="update_items_node")
                for d in raw_decisions:
                    if isinstance(d, dict) and "item_id" in d:
                        decisions_map[d["item_id"]] = d
            except Exception as exc:
                print(f"[update_items_node] ⚠️  batch {batch_num} error: {exc} "
                      f"— defaulting all items in batch to 'keep'")

        # Apply decisions to prior items
        for item in prior_items:
            iid = item["item_id"]
            decision_obj = decisions_map.get(iid, {})
            decision = decision_obj.get("decision", "keep").lower().strip()
            notes    = decision_obj.get("notes", "")

            if decision == "remove":
                updated = PBCItem(
                    **{**item,
                       "status": "removed",
                       "period": audit_period,
                       "notes":  f"{item.get('notes', '')} | {notes}".strip(" |"),
                    }
                )
                current_items.append(updated)

            elif decision == "update":
                new_desc = decision_obj.get("updated_description") or item["description"]
                updated = PBCItem(
                    **{**item,
                       "status":      "updated",
                       "description": new_desc,
                       "period":      audit_period,
                       "last_year_id": iid,
                       "notes":       f"{item.get('notes', '')} | {notes}".strip(" |"),
                    }
                )
                current_items.append(updated)

            else:  # keep (default)
                updated = PBCItem(
                    **{**item,
                       "status": "carried_over",
                       "period": audit_period,
                    }
                )
                current_items.append(updated)

    # Apply explicit sample-size deltas deterministically. The LLM may explain
    # relevance, but a numeric methodology update should not depend on prose.
    for change in scope_changes:
        if change.get("change_type") != "sample_size_change":
            continue
        numbers = re.findall(r"\b\d+\b", change.get("description", ""))
        if not numbers:
            continue
        new_size = numbers[-1]
        affected_categories = set(change.get("affected_categories", []))
        for item in current_items:
            if item["category"] in affected_categories and item.get("sample_size"):
                item["sample_size"] = new_size
                item["status"] = "updated"
                item["notes"] = (
                    f"{item.get('notes', '')} | Sample size updated from scope memo"
                ).strip(" |")

    # ── Step 2: new items from system_added scope changes ──────────────────
    added_systems: list[str] = []
    for change in scope_changes:
        if change["change_type"] != "system_added":
            continue

        # Try to extract system name from the description
        desc  = change["description"]
        match = re.search(
            r"([\w\s/\-\.]+?)\s+(?:newly|now)\s+in\s+scope|"
            r"added[:\s]+([\w\s/\-\.]+?)\s+(?:to|in)\s+scope|"
            r"^([\w\s/\-\.]+?)\s+(?:system|platform|application)",
            desc, re.IGNORECASE,
        )
        if match:
            system_name = next(g for g in match.groups() if g).strip().rstrip(".")
        else:
            # Fallback: use the first noun phrase in the description
            words = desc.split()
            system_name = " ".join(words[:3]) if len(words) >= 3 else desc

        if system_name in added_systems:
            continue  # de-duplicate
        added_systems.append(system_name)

        # Generate items for every affected category
        affected = change.get("affected_categories") or CATEGORIES
        print(f"[update_items_node] generating new items for system: {system_name!r}")

        seq_counters: dict[str, int] = {}
        for cat in affected:
            seq_start = seq_counters.get(cat, 1)
            new_items = instantiate_items(cat, system_name, audit_period, start_seq=seq_start)
            if new_items:
                # Ensure item_ids are unique across the whole output
                for ni in new_items:
                    while ni["item_id"] in used_ids:
                        # Append suffix to de-duplicate
                        ni = PBCItem(**{**ni, "item_id": ni["item_id"] + "X"})
                    used_ids.add(ni["item_id"])
                    current_items.append(ni)
                seq_counters[cat] = seq_start + len(new_items)
                print(f"[update_items_node]   {cat}: +{len(new_items)} new items")

    # Add approved mandatory discovery questions from retrieved guidance.
    existing_descriptions = {
        re.sub(r"\s+", " ", item["description"]).strip().lower()
        for item in current_items
    }
    for requirement in regulatory_guidance:
        if not requirement.get("mandatory_discovery"):
            continue
        citation = requirement.get("citation", requirement.get("requirement_id", ""))
        for question in requirement.get("proposed_questions", []):
            normalized = re.sub(r"\s+", " ", question).strip().lower()
            if not normalized or normalized in existing_descriptions:
                continue
            item_id = _next_id(used_ids, "REG")
            used_ids.add(item_id)
            current_items.append(PBCItem(
                item_id=item_id,
                category=(requirement.get("control_areas") or ["IT Systems Understanding"])[0],
                description=question,
                in_scope=True,
                period=audit_period,
                sample_size=None,
                status="new",
                last_year_id=None,
                notes=f"Added from approved guidance: {citation}",
            ))
            existing_descriptions.add(normalized)

    print(f"[update_items_node] total current_year_items: {len(current_items)}")
    return {"current_year_items": current_items}


# ─────────────────────────────────────────────────────────────────────────────
# Node 5 — review_node
# ─────────────────────────────────────────────────────────────────────────────

def review_node(state: State) -> dict:
    """
    Human-in-the-loop checkpoint (Phase 4 — real interrupt/resume).

    Behaviour depends on whether the graph was compiled with a checkpointer:

    ┌─────────────────────────────────────────────────────────────────┐
    │  With checkpointer (async review flow via /api/pbc/async/*)     │
    │  ─────────────────────────────────────────────────────────────  │
    │  1. interrupt() pauses graph execution and saves full state.    │
    │  2. Caller receives {**state, "__interrupt__": [...]}           │
    │  3. Auditor reviews draft xlsx at /api/pbc/async/{tid}/status   │
    │  4. Approve → POST /api/pbc/async/{tid}/approve                 │
    │     → Command(resume={"approved": True})                        │
    │     → interrupt() returns {"approved": True}                    │
    │     → review_passed=True → router → output_node                 │
    │  5. Reject  → POST /api/pbc/async/{tid}/reject                  │
    │     → Command(resume={"approved": False, "notes": "..."})       │
    │     → review_passed=False → router → update_items_node (loop)   │
    │                                                                  │
    │  Without checkpointer (sync /api/pbc/generate endpoint)         │
    │  ─────────────────────────────────────────────────────────────  │
    │  interrupt() is a no-op stub → auto-approves (backward-compat)  │
    └─────────────────────────────────────────────────────────────────┘

    State mutations
    ───────────────
    review_passed ← True (approved) | False (rejected, triggers loop)
    """
    items = state.get("current_year_items", [])
    n_items = len(items)

    # Build a breakdown for the interrupt payload so the auditor sees a summary
    by_status: dict[str, int] = {}
    for item in items:
        s = item.get("status", "carried_over")
        by_status[s] = by_status.get(s, 0) + 1

    print(f"[review_node] {n_items} items ready — surfacing interrupt for human review")

    # ── LangGraph interrupt ───────────────────────────────────────────────────
    # interrupt() raises GraphInterrupt on first call; graph state is checkpointed.
    # On resume, interrupt() returns whatever value was passed via Command(resume=...).
    # If the graph has no checkpointer (sync endpoint), this call is a no-op
    # because LangGraph 1.x only surfaces interrupts when a checkpointer is attached.
    try:
        from langgraph.types import interrupt as lg_interrupt  # type: ignore[import]
        decision = lg_interrupt({
            "message": "PBC draft ready for review. Approve or reject?",
            "item_count": n_items,
            "status_breakdown": by_status,
            "scope_changes": state.get("scope_changes", []),
            "client_name": state.get("client_name", ""),
            "audit_period": state.get("audit_period", ""),
        })
    except Exception:
        # langgraph stub or no checkpointer — fall back to auto-approve
        decision = {"approved": True}

    # ── interpret the decision ────────────────────────────────────────────────
    if isinstance(decision, dict):
        approved = bool(decision.get("approved", True))
        notes    = str(decision.get("notes", ""))
    else:
        # Simple boolean resume value
        approved = bool(decision)
        notes    = ""

    verb = "✅ approved" if approved else f"❌ rejected — notes: {notes!r}"
    print(f"[review_node] auditor decision: {verb}")

    return {
        "review_passed":    approved,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Node 5 — output_node
# ─────────────────────────────────────────────────────────────────────────────

def output_node(state: State) -> dict:
    """
    Write current_year_items to an xlsx workbook and set pbc_output_xlsx_path.

    Output path resolution (first non-empty wins):
      1. state["pbc_output_xlsx_path"]  (caller-supplied explicit path)
      2. Auto-generated: data/output/{client_name}_{audit_period}_pbc.xlsx

    State mutations
    ───────────────
    pbc_output_xlsx_path ← absolute path of written file
    error                ← set on write failure
    """
    print("[output_node] starting")

    items: List[PBCItem] = state.get("current_year_items", [])

    # If no items at all (e.g., no prior year + no scope changes), carry prior
    # year items forward unchanged so the auditor always gets an output file.
    if not items:
        prior: List[PBCItem] = state.get("prior_year_items", [])
        audit_period = state.get("audit_period", "")
        items = [PBCItem(**{**p, "status": "carried_over", "period": audit_period})
                 for p in prior]
        print(f"[output_node] no current_year_items — carrying {len(items)} prior items forward")

    # Resolve output path
    out_path = state.get("pbc_output_xlsx_path", "").strip()
    if not out_path:
        client_safe = re.sub(r"[^\w\-]", "_", state.get("client_name", "client"))
        period_safe = re.sub(r"[^\w\-]", "_", state.get("audit_period",  "period"))
        out_path = os.path.join("data", "output", f"{client_safe}_{period_safe}_pbc.xlsx")

    out_path = os.path.abspath(out_path)

    try:
        write_pbc_xlsx(items, out_path)
        # Status summary
        from collections import Counter
        counts = Counter(i.get("status", "?") for i in items)
        print(f"[output_node] ✅ wrote {len(items)} items to {out_path}")
        print(f"[output_node]    status breakdown: {dict(counts)}")
        return {"pbc_output_xlsx_path": out_path}
    except Exception as exc:
        msg = f"[output_node] ❌ failed to write xlsx: {exc}"
        print(msg)
        return {"pbc_output_xlsx_path": "", "error": str(exc)}
