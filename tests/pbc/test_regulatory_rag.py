"""Tests for Module A's versioned methodology retrieval."""

from __future__ import annotations

from modules.pbc.nodes import (
    retrieve_regulatory_guidance_node,
    update_items_node,
)
from modules.pbc.regulatory_rag import RetrievalQuery, retrieve_guidance


def test_fy2025_retrieves_uar_sampling_guidance():
    results = retrieve_guidance(RetrievalQuery(
        text="UAR sample size increased from 25 to 40",
        audit_period="FY2025",
        control_areas=("ITGC - UAR",),
    ))
    ids = {result["requirement_id"] for result in results}
    assert "FIRM-ITAM-2025-UAR-01" in ids


def test_guidance_is_not_effective_for_fy2024():
    results = retrieve_guidance(RetrievalQuery(
        text="UAR sample size and AI discovery",
        audit_period="FY2024",
    ))
    assert results == []


def test_mandatory_ai_discovery_is_retrieved_without_ai_in_scope_memo():
    state = {
        "audit_period": "FY2025",
        "current_year_scope_text": "Oracle EBS remains in scope.",
        "scope_changes": [],
        "prior_year_items": [],
        "jurisdiction": "*",
        "industry": "*",
    }
    result = retrieve_regulatory_guidance_node(state)
    ids = {item["requirement_id"] for item in result["regulatory_guidance"]}
    assert "FIRM-ITAM-2025-AI-01" in ids


def test_guidance_adds_cited_ai_discovery_question():
    state = {
        "client_name": "ACME Corp",
        "audit_period": "FY2025",
        "prior_year_items": [],
        "scope_changes": [],
        "regulatory_guidance": [{
            "requirement_id": "FIRM-ITAM-2025-AI-01",
            "control_areas": ["IT Systems Understanding"],
            "mandatory_discovery": True,
            "proposed_questions": ["Provide an inventory of AI-enabled systems."],
            "citation": "Approved Firm IT Audit Methodology 2025.1, FIRM-ITAM-2025-AI-01",
        }],
    }
    items = update_items_node(state)["current_year_items"]
    assert len(items) == 1
    assert items[0]["status"] == "new"
    assert "AI-enabled" in items[0]["description"]
    assert "FIRM-ITAM-2025-AI-01" in items[0]["notes"]


def test_scope_memo_sample_size_is_applied_deterministically():
    state = {
        "client_name": "ACME Corp",
        "audit_period": "FY2025",
        "prior_year_items": [{
            "item_id": "UAR-ORA-001",
            "category": "ITGC - UAR",
            "description": "Provide the UAR sample.",
            "in_scope": True,
            "period": "FY2024",
            "sample_size": "25",
            "status": "carried_over",
            "last_year_id": None,
            "notes": "",
        }],
        "scope_changes": [{
            "change_type": "sample_size_change",
            "description": "UAR sample sizes increased from 25 to 40",
            "affected_categories": ["ITGC - UAR"],
        }],
        "regulatory_guidance": [],
    }
    items = update_items_node(state)["current_year_items"]
    assert items[0]["sample_size"] == "40"
    assert items[0]["status"] == "updated"
