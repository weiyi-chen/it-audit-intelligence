"""
Shared pytest fixtures for all Module A (PBC) tests.

Import in any test file with:
    from tests.conftest import *   # (implicit via conftest autodiscovery)

All fixtures that write files use tmp_path so they are cleaned up automatically.
"""

from __future__ import annotations

import json
import os
from typing import List

import pytest

from core.state import PBCItem, ScopeChange


# ─────────────────────────────────────────────────────────────────────────────
# PBCItem fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_prior_items() -> List[PBCItem]:
    """18-item Oracle EBS prior-year PBC list covering all ITGC categories."""
    return [
        # IT Systems Understanding
        PBCItem(item_id="SYS-ORA-001", category="IT Systems Understanding",
                description="Provide system overview for Oracle EBS: version, hosting, owner.",
                in_scope=True, period="FY2024", sample_size=None,
                status="carried_over", last_year_id=None, notes=""),
        PBCItem(item_id="SYS-ORA-002", category="IT Systems Understanding",
                description="Provide data-flow diagram for Oracle EBS.",
                in_scope=True, period="FY2024", sample_size=None,
                status="carried_over", last_year_id=None, notes=""),
        # JML
        PBCItem(item_id="JML-ORA-001", category="ITGC - JML",
                description="Population of users created in Oracle EBS during FY2024.",
                in_scope=True, period="FY2024", sample_size="25",
                status="carried_over", last_year_id=None, notes=""),
        PBCItem(item_id="JML-ORA-002", category="ITGC - JML",
                description="Joiner approval evidence for Oracle EBS.",
                in_scope=True, period="FY2024", sample_size="25",
                status="carried_over", last_year_id=None, notes=""),
        PBCItem(item_id="JML-ORA-003", category="ITGC - JML",
                description="Population of users disabled in Oracle EBS during FY2024.",
                in_scope=True, period="FY2024", sample_size="25",
                status="carried_over", last_year_id=None, notes=""),
        PBCItem(item_id="JML-ORA-004", category="ITGC - JML",
                description="Leaver account disable evidence for Oracle EBS.",
                in_scope=True, period="FY2024", sample_size="25",
                status="carried_over", last_year_id=None, notes=""),
        # UAR
        PBCItem(item_id="UAR-ORA-001", category="ITGC - UAR",
                description="UAR documentation for Oracle EBS FY2024.",
                in_scope=True, period="FY2024", sample_size="1 review cycle",
                status="carried_over", last_year_id=None, notes=""),
        PBCItem(item_id="UAR-ORA-002", category="ITGC - UAR",
                description="Active user population for Oracle EBS UAR.",
                in_scope=True, period="FY2024", sample_size="25",
                status="carried_over", last_year_id=None, notes=""),
        PBCItem(item_id="UAR-ORA-003", category="ITGC - UAR",
                description="Manager certification for Oracle EBS UAR sample.",
                in_scope=True, period="FY2024", sample_size="25",
                status="carried_over", last_year_id=None, notes=""),
        # ChangeMgmt
        PBCItem(item_id="CHG-ORA-001", category="ITGC - ChangeMgmt",
                description="Change population for Oracle EBS FY2024.",
                in_scope=True, period="FY2024", sample_size="25",
                status="carried_over", last_year_id=None, notes=""),
        PBCItem(item_id="CHG-ORA-002", category="ITGC - ChangeMgmt",
                description="Change approval evidence for Oracle EBS.",
                in_scope=True, period="FY2024", sample_size="25",
                status="carried_over", last_year_id=None, notes=""),
        PBCItem(item_id="CHG-ORA-003", category="ITGC - ChangeMgmt",
                description="Separation of duties evidence for Oracle EBS deployments.",
                in_scope=True, period="FY2024", sample_size="25",
                status="carried_over", last_year_id=None, notes=""),
        # PrivAccess
        PBCItem(item_id="PVA-ORA-001", category="ITGC - PrivAccess",
                description="Privileged account list for Oracle EBS.",
                in_scope=True, period="FY2024", sample_size=None,
                status="carried_over", last_year_id=None, notes=""),
        PBCItem(item_id="PVA-ORA-002", category="ITGC - PrivAccess",
                description="Privileged access review evidence for Oracle EBS.",
                in_scope=True, period="FY2024", sample_size="1 review cycle",
                status="carried_over", last_year_id=None, notes=""),
        # ProgramDev
        PBCItem(item_id="PGD-ORA-001", category="ITGC - ProgramDev",
                description="SDLC project list for Oracle EBS FY2024.",
                in_scope=True, period="FY2024", sample_size="2 projects",
                status="carried_over", last_year_id=None, notes=""),
        # Backup
        PBCItem(item_id="BKP-ORA-001", category="ITGC - Backup",
                description="Backup schedule and policy for Oracle EBS.",
                in_scope=True, period="FY2024", sample_size=None,
                status="carried_over", last_year_id=None, notes=""),
        PBCItem(item_id="BKP-ORA-002", category="ITGC - Backup",
                description="Backup completion logs for Oracle EBS (3-month window).",
                in_scope=True, period="FY2024", sample_size="3 months",
                status="carried_over", last_year_id=None, notes=""),
        PBCItem(item_id="BKP-ORA-003", category="ITGC - Backup",
                description="Restoration test evidence for Oracle EBS.",
                in_scope=True, period="FY2024", sample_size="1 restoration test",
                status="carried_over", last_year_id=None, notes=""),
    ]


@pytest.fixture
def single_jml_item() -> PBCItem:
    return PBCItem(
        item_id="JML-ORA-001", category="ITGC - JML",
        description="Population of users created in Oracle EBS during FY2024.",
        in_scope=True, period="FY2024", sample_size="25",
        status="carried_over", last_year_id=None, notes="",
    )


# ─────────────────────────────────────────────────────────────────────────────
# ScopeChange fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def scope_change_system_added() -> ScopeChange:
    return ScopeChange(
        change_type="system_added",
        description="SAP S/4HANA newly in scope starting FY2025",
        affected_categories=[
            "IT Systems Understanding",
            "ITGC - JML",
            "ITGC - UAR",
            "ITGC - PrivAccess",
            "ITGC - ChangeMgmt",
        ],
    )


@pytest.fixture
def scope_change_sample_size() -> ScopeChange:
    return ScopeChange(
        change_type="sample_size_change",
        description="UAR sample size raised to 40",
        affected_categories=["ITGC - UAR"],
    )


@pytest.fixture
def scope_change_system_removed() -> ScopeChange:
    return ScopeChange(
        change_type="system_removed",
        description="Legacy payroll system removed from scope",
        affected_categories=["IT Systems Understanding", "ITGC - JML"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# State fixture
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def base_state(sample_prior_items) -> dict:
    """Minimal valid state dict for node tests."""
    return {
        "client_name":              "ACME Corp",
        "audit_period":             "FY2025",
        "prior_year_pbc_path":      "",
        "current_year_scope_text":  "",
        "prior_year_items":         sample_prior_items,
        "scope_changes":            [],
        "current_year_items":       [],
        "pbc_output_xlsx_path":     "",
        "pbc_output_xlsx_b64":      "",
        "review_passed":            False,
        "active_module":            "A",
        "thread_id":                "test-001",
        "error":                    None,
        "messages":                 [],
        # Module B / C fields (unused in Module A tests)
        "evidence_paths":           [],
        "extracted_entities":       [],
        "entity_relationships":     [],
        "map_output_html_path":     "",
        "walkthrough_topics":       [],
        "current_topic_id":         None,
        "suggested_next_questions": [],
        "walkthrough_complete":     False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# LLM mock helpers  (import in tests that need to patch call_claude)
# ─────────────────────────────────────────────────────────────────────────────

def make_scope_diff_response(changes: list) -> str:
    """Return a JSON string shaped like scope_diff_node expects."""
    return json.dumps(changes)


def make_update_items_response(decisions: list) -> str:
    """Return a JSON string shaped like update_items_node expects."""
    return json.dumps(decisions)


def decisions_keep_all(items: List[PBCItem]) -> str:
    """LLM mock: keep every prior item unchanged."""
    return json.dumps([
        {"item_id": i["item_id"], "decision": "keep",
         "updated_description": None, "notes": "no change"}
        for i in items
    ])


def decisions_update_one(items: List[PBCItem], target_id: str,
                         new_desc: str = "UPDATED description") -> str:
    """LLM mock: update one specific item, keep the rest."""
    return json.dumps([
        {"item_id": i["item_id"],
         "decision": "update" if i["item_id"] == target_id else "keep",
         "updated_description": new_desc if i["item_id"] == target_id else None,
         "notes": "updated" if i["item_id"] == target_id else "no change"}
        for i in items
    ])


def decisions_remove_one(items: List[PBCItem], target_id: str) -> str:
    """LLM mock: remove one specific item, keep the rest."""
    return json.dumps([
        {"item_id": i["item_id"],
         "decision": "remove" if i["item_id"] == target_id else "keep",
         "updated_description": None,
         "notes": "out of scope" if i["item_id"] == target_id else "no change"}
        for i in items
    ])
