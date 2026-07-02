"""
Unified State schema for the IT Audit Intelligence Platform.

Covers all three modules:
    A — PBC Checklist Generator
    B — IT Understanding Knowledge Map
    C — Walkthrough Assistant

Each module reads/writes its own slice of the State, but all three share
client_name, audit_period, active_module, and messages. This makes it
possible for downstream modules to reuse upstream artifacts (e.g. Module B's
knowledge graph feeds Module C's "related questions" engine).

NOTE: TypedDict gives us static type-checking + IDE auto-complete + a
single source of truth for "what fields exist". It does NOT enforce
required-vs-optional at runtime — use `default_state()` to produce a
fully-populated default for tests / new graph runs.
"""

from typing import TypedDict, List, Dict, Any, Annotated, Optional
from langgraph.graph.message import add_messages


# ─────────────────────────────────────────────────────────────────────────
# Module A — PBC Checklist
# ─────────────────────────────────────────────────────────────────────────

class PBCItem(TypedDict):
    """A single line on the Provided-By-Client request list."""
    item_id: str
    category: str           # e.g. "IT Systems Understanding", "ITGC - JML", "ITGC - UAR"
    description: str        # the actual evidence ask sent to client
    in_scope: bool
    period: str             # e.g. "FY2025"
    sample_size: Optional[str]
    status: str             # "carried_over" | "updated" | "new" | "removed"
    last_year_id: Optional[str]   # back-reference for traceability
    notes: str


class ScopeChange(TypedDict):
    """One delta detected between last year's audit scope and this year's."""
    change_type: str        # "system_added" | "system_removed" | "period_change"
                            # | "regulation_change" | "sample_size_change"
    description: str
    affected_categories: List[str]   # which PBC categories this change touches


# ─────────────────────────────────────────────────────────────────────────
# Module B — IT Understanding Map
# ─────────────────────────────────────────────────────────────────────────

class ITEntity(TypedDict):
    """A node in the knowledge graph."""
    entity_id: str
    entity_type: str        # "system" | "process" | "person" | "vendor"
                            # | "location" | "control"
    name: str
    attributes: Dict[str, Any]   # type-specific (system has hosting/criticality/owner_id, ...)


class EntityRelationship(TypedDict):
    """An edge in the knowledge graph."""
    source_id: str
    target_id: str
    relation: str           # "owns" | "runs_on" | "processes" | "depends_on"
                            # | "reviewed_by" | "managed_by"
    confidence: float       # 0–1, from the LLM that inferred this
    evidence_quote: str     # snippet from the source document for traceability


# ─────────────────────────────────────────────────────────────────────────
# Module C — Walkthrough
# ─────────────────────────────────────────────────────────────────────────

class WalkthroughTopic(TypedDict):
    """One control area being walked through (JML, UAR, ChangeMgmt, ...)."""
    topic_id: str
    area: str               # "JML" | "UAR" | "ChangeMgmt" | "PrivilegedAccess"
                            # | "ProgramDev" | "Backup"
    system_in_scope: str
    standard_questions: List[str]
    related_topic_ids: List[str]    # cross-references (e.g. UAR ↔ JML)
    coverage_status: str    # "not_started" | "in_progress" | "completed"
    last_year_findings: str
    auditor_notes: str


# ─────────────────────────────────────────────────────────────────────────
# Unified State
# ─────────────────────────────────────────────────────────────────────────

class State(TypedDict):
    # ── shared input ──────────────────────────────────────────
    client_name: str
    audit_period: str

    # ── Module A — PBC ────────────────────────────────────────
    prior_year_pbc_path: str
    current_year_scope_text: str
    prior_year_items: List[PBCItem]
    scope_changes: List[ScopeChange]
    current_year_items: List[PBCItem]
    pbc_output_xlsx_path: str
    pbc_output_xlsx_b64: str

    # ── Module B — Understanding Map ──────────────────────────
    evidence_paths: List[str]
    extracted_entities: List[ITEntity]
    entity_relationships: List[EntityRelationship]
    map_output_html_path: str

    # ── Module C — Walkthrough ────────────────────────────────
    walkthrough_topics: List[WalkthroughTopic]
    current_topic_id: Optional[str]
    suggested_next_questions: List[str]

    # ── control flow flags ────────────────────────────────────
    review_passed: bool
    walkthrough_complete: bool

    # ── metadata ──────────────────────────────────────────────
    active_module: str      # "A" | "B" | "C"
    thread_id: str
    error: Optional[str]

    # ── message history (LangGraph reducer-merged) ───────────
    messages: Annotated[List[Dict], add_messages]


def default_state(
    *,
    client_name: str = "",
    audit_period: str = "",
    active_module: str = "A",
    thread_id: str = "",
) -> State:
    """Produce a fully-populated default State.

    Useful for:
      - tests (so each test doesn't have to spell out every field)
      - graph entry points (LangGraph happily merges partial dicts, but
        downstream nodes that read `state.get(...)` are simpler if every
        key exists)
    """
    return State(
        client_name=client_name,
        audit_period=audit_period,
        # Module A
        prior_year_pbc_path="",
        current_year_scope_text="",
        prior_year_items=[],
        scope_changes=[],
        current_year_items=[],
        pbc_output_xlsx_path="",
        pbc_output_xlsx_b64="",
        # Module B
        evidence_paths=[],
        extracted_entities=[],
        entity_relationships=[],
        map_output_html_path="",
        # Module C
        walkthrough_topics=[],
        current_topic_id=None,
        suggested_next_questions=[],
        # control flow
        review_passed=False,
        walkthrough_complete=False,
        # meta
        active_module=active_module,
        thread_id=thread_id,
        error=None,
        messages=[],
    )
