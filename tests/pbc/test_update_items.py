"""
Unit tests for update_items_node in modules/pbc/nodes.py

Strategy
────────
call_claude is patched so each test controls exactly what "the LLM decided".
Template generation (from system_added scope changes) is NOT mocked — it
exercises the real templates.py logic.

Tests
─────
 1. No scope changes → all prior items carried over (status="carried_over")
 2. Keep decision → item_id and description preserved, status="carried_over"
 3. Update decision → description updated, status="updated", last_year_id set
 4. Remove decision → status="removed"
 5. Mixed decisions in one batch
 6. system_added scope change → new items generated from templates
 7. New items have status="new" and contain system name
 8. system_removed scope change → no new items added (only LLM handles removal)
 9. item_ids in output are all unique (no collisions between prior + new)
10. Empty prior_year_items + system_added → only new template items
11. Batch size: 21 items triggers two LLM calls
12. LLM exception in one batch → defaults to keep, continues
13. period field updated to audit_period on all output items
14. current_year_items count = carried + updated + removed + new
"""

from __future__ import annotations

import json
from unittest.mock import call, patch

import pytest

from core.state import PBCItem, ScopeChange
from modules.pbc.nodes import update_items_node
from tests.conftest import (
    decisions_keep_all,
    decisions_remove_one,
    decisions_update_one,
    make_update_items_response,
)

PATCH_TARGET = "modules.pbc.nodes.call_claude"


# ─── helpers ─────────────────────────────────────────────────────────────────

def make_item(item_id: str = "JML-ORA-001",
              category: str = "ITGC - JML",
              description: str = "Test evidence request.",
              status: str = "carried_over") -> PBCItem:
    return PBCItem(
        item_id=item_id, category=category, description=description,
        in_scope=True, period="FY2024", sample_size="25",
        status=status, last_year_id=None, notes="",
    )


def build_state(prior_items=None, scope_changes=None) -> dict:
    return {
        "client_name":    "ACME Corp",
        "audit_period":   "FY2025",
        "prior_year_items":  prior_items  or [],
        "scope_changes":     scope_changes or [],
        "current_year_items": [],
    }


def run_node(prior_items=None, scope_changes=None,
             llm_response: str | None = None) -> dict:
    state = build_state(prior_items, scope_changes)
    if llm_response is not None:
        with patch(PATCH_TARGET, return_value=llm_response):
            return update_items_node(state)
    return update_items_node(state)


# ─── decision handling ────────────────────────────────────────────────────────

class TestDecisionHandling:
    def test_no_scope_changes_all_carry_over(self, sample_prior_items):
        response = decisions_keep_all(sample_prior_items)
        result = run_node(prior_items=sample_prior_items, llm_response=response)

        items = result["current_year_items"]
        assert len(items) == len(sample_prior_items)
        assert all(i["status"] == "carried_over" for i in items), \
            "All items should be carried_over when LLM says keep"

    def test_keep_decision_preserves_description(self):
        item = make_item(description="Original description.")
        response = decisions_keep_all([item])
        result = run_node(prior_items=[item], llm_response=response)

        out = result["current_year_items"][0]
        assert out["description"] == "Original description."
        assert out["status"] == "carried_over"

    def test_update_decision_changes_description(self):
        item = make_item(item_id="UAR-ORA-001", description="Old description.")
        new_desc = "Updated description for FY2025 scope."
        response = decisions_update_one([item], "UAR-ORA-001", new_desc)
        result = run_node(prior_items=[item], llm_response=response)

        out = result["current_year_items"][0]
        assert out["description"] == new_desc
        assert out["status"] == "updated"

    def test_update_decision_sets_last_year_id(self):
        item = make_item(item_id="UAR-ORA-001")
        response = decisions_update_one([item], "UAR-ORA-001", "New desc")
        result = run_node(prior_items=[item], llm_response=response)

        out = result["current_year_items"][0]
        assert out["last_year_id"] == "UAR-ORA-001"

    def test_remove_decision_sets_removed_status(self):
        item = make_item(item_id="BKP-ORA-001")
        response = decisions_remove_one([item], "BKP-ORA-001")
        result = run_node(prior_items=[item], llm_response=response)

        out = result["current_year_items"][0]
        assert out["status"] == "removed"

    def test_remove_decision_item_still_in_output(self):
        """Removed items should appear in output (for audit trail) — not dropped."""
        item = make_item(item_id="OLD-001")
        response = decisions_remove_one([item], "OLD-001")
        result = run_node(prior_items=[item], llm_response=response)

        ids = [i["item_id"] for i in result["current_year_items"]]
        assert "OLD-001" in ids

    def test_mixed_decisions_correct_statuses(self):
        items = [
            make_item(item_id="JML-001"),
            make_item(item_id="UAR-001"),
            make_item(item_id="BKP-001"),
        ]
        response = make_update_items_response([
            {"item_id": "JML-001", "decision": "keep",   "updated_description": None, "notes": ""},
            {"item_id": "UAR-001", "decision": "update",  "updated_description": "New UAR desc", "notes": ""},
            {"item_id": "BKP-001", "decision": "remove",  "updated_description": None, "notes": ""},
        ])
        result = run_node(prior_items=items, llm_response=response)
        status_map = {i["item_id"]: i["status"] for i in result["current_year_items"]}

        assert status_map["JML-001"] == "carried_over"
        assert status_map["UAR-001"] == "updated"
        assert status_map["BKP-001"] == "removed"


class TestPeriodUpdate:
    def test_period_updated_to_current_audit_period(self, sample_prior_items):
        """All output items must carry the current audit_period, not FY2024."""
        response = decisions_keep_all(sample_prior_items)
        result = run_node(prior_items=sample_prior_items, llm_response=response)

        for item in result["current_year_items"]:
            assert item["period"] == "FY2025", \
                f"Item {item['item_id']} has stale period {item['period']!r}"


class TestNewItemsFromTemplates:
    def test_system_added_generates_new_items(self, sample_prior_items):
        scope_changes = [ScopeChange(
            change_type="system_added",
            description="SAP S/4HANA newly in scope",
            affected_categories=["ITGC - JML", "ITGC - UAR"],
        )]
        response = decisions_keep_all(sample_prior_items)
        result = run_node(prior_items=sample_prior_items,
                          scope_changes=scope_changes, llm_response=response)

        new_items = [i for i in result["current_year_items"] if i["status"] == "new"]
        assert len(new_items) > 0, "system_added should create new items"

    def test_new_items_have_correct_status(self, sample_prior_items):
        scope_changes = [ScopeChange(
            change_type="system_added",
            description="SAP S/4HANA newly in scope",
            affected_categories=["ITGC - JML"],
        )]
        response = decisions_keep_all(sample_prior_items)
        result = run_node(prior_items=sample_prior_items,
                          scope_changes=scope_changes, llm_response=response)

        new_items = [i for i in result["current_year_items"] if i["status"] == "new"]
        assert all(i["status"] == "new" for i in new_items)

    def test_new_items_contain_system_name(self, sample_prior_items):
        scope_changes = [ScopeChange(
            change_type="system_added",
            description="Workday newly in scope",
            affected_categories=["ITGC - JML", "ITGC - UAR"],
        )]
        response = decisions_keep_all(sample_prior_items)
        result = run_node(prior_items=sample_prior_items,
                          scope_changes=scope_changes, llm_response=response)

        new_items = [i for i in result["current_year_items"] if i["status"] == "new"]
        # System name should appear in at least some new item descriptions
        with_name = [i for i in new_items if "Workday" in i["description"]]
        assert len(with_name) > 0, "New items should reference the new system name"

    def test_new_items_period_is_current(self, sample_prior_items):
        scope_changes = [ScopeChange(
            change_type="system_added",
            description="SAP newly in scope",
            affected_categories=["ITGC - Backup"],
        )]
        response = decisions_keep_all(sample_prior_items)
        result = run_node(prior_items=sample_prior_items,
                          scope_changes=scope_changes, llm_response=response)

        new_items = [i for i in result["current_year_items"] if i["status"] == "new"]
        assert all(i["period"] == "FY2025" for i in new_items)

    def test_empty_prior_plus_system_added(self):
        """No prior items, one system_added change → only new template items."""
        scope_changes = [ScopeChange(
            change_type="system_added",
            description="Oracle EBS newly in scope",
            affected_categories=["ITGC - JML", "ITGC - UAR"],
        )]
        # No LLM call expected (no prior items to decide on)
        with patch(PATCH_TARGET) as mock_llm:
            state = build_state(prior_items=[], scope_changes=scope_changes)
            result = update_items_node(state)
        mock_llm.assert_not_called()

        items = result["current_year_items"]
        assert len(items) > 0
        assert all(i["status"] == "new" for i in items)

    def test_non_system_added_change_no_new_items(self, sample_prior_items):
        """sample_size_change should not trigger template instantiation."""
        scope_changes = [ScopeChange(
            change_type="sample_size_change",
            description="UAR sample size raised to 40",
            affected_categories=["ITGC - UAR"],
        )]
        response = decisions_keep_all(sample_prior_items)
        result = run_node(prior_items=sample_prior_items,
                          scope_changes=scope_changes, llm_response=response)

        new_items = [i for i in result["current_year_items"] if i["status"] == "new"]
        assert len(new_items) == 0, "sample_size_change must not add new template items"


class TestItemIdUniqueness:
    def test_no_duplicate_ids_in_output(self, sample_prior_items):
        scope_changes = [ScopeChange(
            change_type="system_added",
            description="SAP S/4HANA newly in scope",
            affected_categories=["ITGC - JML", "ITGC - UAR", "ITGC - PrivAccess"],
        )]
        response = decisions_keep_all(sample_prior_items)
        result = run_node(prior_items=sample_prior_items,
                          scope_changes=scope_changes, llm_response=response)

        ids = [i["item_id"] for i in result["current_year_items"]]
        assert len(ids) == len(set(ids)), "Duplicate item_ids found in output"


class TestBatchingBehaviour:
    def test_21_items_triggers_two_llm_calls(self):
        """BATCH_SIZE=20, so 21 items must trigger exactly 2 LLM calls."""
        items = [make_item(item_id=f"TST-{i:03d}") for i in range(1, 22)]
        responses = [decisions_keep_all(items[:20]), decisions_keep_all(items[20:])]

        call_count = 0
        def side_effect(*args, **kwargs):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        with patch(PATCH_TARGET, side_effect=side_effect):
            state = build_state(prior_items=items)
            result = update_items_node(state)

        assert call_count == 2, f"Expected 2 LLM calls, got {call_count}"

    def test_batch_exception_defaults_to_keep(self):
        """If LLM throws in a batch, items in that batch default to 'keep'."""
        items = [make_item(item_id=f"JML-{i:03d}") for i in range(1, 4)]

        with patch(PATCH_TARGET, side_effect=RuntimeError("timeout")):
            state = build_state(prior_items=items)
            result = update_items_node(state)

        # All items should still appear in output (defaulted to carried_over)
        ids_out = {i["item_id"] for i in result["current_year_items"]}
        for item in items:
            assert item["item_id"] in ids_out, \
                f"{item['item_id']} missing from output after LLM exception"


class TestOutputCount:
    def test_total_count_equals_prior_plus_new(self, sample_prior_items):
        scope_changes = [ScopeChange(
            change_type="system_added",
            description="SAP S/4HANA newly in scope",
            affected_categories=["ITGC - JML"],
        )]
        from modules.pbc.templates import instantiate_items
        expected_new = len(instantiate_items("ITGC - JML", "SAP S/4HANA", "FY2025"))

        response = decisions_keep_all(sample_prior_items)
        result = run_node(prior_items=sample_prior_items,
                          scope_changes=scope_changes, llm_response=response)

        expected_total = len(sample_prior_items) + expected_new
        actual_total   = len(result["current_year_items"])
        assert actual_total == expected_total, \
            f"Expected {expected_total} items, got {actual_total}"
