"""
Unit tests for scope_diff_node in modules/pbc/nodes.py

Strategy
────────
call_claude is patched via unittest.mock.patch so tests run with zero
API cost and are fully deterministic.  Each test controls the exact JSON
the mock returns, which is what scope_diff_node would receive from the LLM.

Tests
─────
1.  Detects system_added when scope text mentions new system
2.  Detects system_removed
3.  Detects sample_size_change
4.  Detects period_change
5.  Detects multiple changes in one scope text
6.  Returns [] when LLM returns [] (no changes)
7.  Empty scope text → returns [] without calling LLM
8.  Missing scope text key → returns [] without crash
9.  LLM raises exception → sets state["error"], returns []
10. LLM returns malformed JSON → returns [] gracefully
11. LLM returns JSON object instead of array → handled gracefully
12. ScopeChange dicts have all required keys
13. affected_categories is always a list
14. change_type value is preserved from LLM response
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from modules.pbc.nodes import scope_diff_node
from tests.conftest import make_scope_diff_response


PATCH_TARGET = "modules.pbc.nodes.call_claude"


# ─── helpers ─────────────────────────────────────────────────────────────────

def run_node(scope_text: str, extra_state: dict | None = None) -> dict:
    state = {
        "client_name":             "ACME Corp",
        "audit_period":            "FY2025",
        "current_year_scope_text": scope_text,
        "prior_year_items":        [],
        "scope_changes":           [],
    }
    if extra_state:
        state.update(extra_state)
    return scope_diff_node(state)


# ─── detection tests ─────────────────────────────────────────────────────────

class TestChangeDetection:
    def test_detects_system_added(self):
        mock_response = make_scope_diff_response([{
            "change_type": "system_added",
            "description": "SAP S/4HANA newly in scope",
            "affected_categories": ["IT Systems Understanding", "ITGC - JML", "ITGC - UAR"],
        }])
        with patch(PATCH_TARGET, return_value=mock_response):
            result = run_node("SAP S/4HANA is newly in scope for FY2025.")

        changes = result["scope_changes"]
        assert len(changes) == 1
        assert changes[0]["change_type"] == "system_added"
        assert "SAP" in changes[0]["description"]

    def test_detects_system_removed(self):
        mock_response = make_scope_diff_response([{
            "change_type": "system_removed",
            "description": "Legacy payroll system removed from scope",
            "affected_categories": ["IT Systems Understanding"],
        }])
        with patch(PATCH_TARGET, return_value=mock_response):
            result = run_node("Legacy payroll system is no longer in scope.")

        changes = result["scope_changes"]
        assert any(c["change_type"] == "system_removed" for c in changes)

    def test_detects_sample_size_change(self):
        mock_response = make_scope_diff_response([{
            "change_type": "sample_size_change",
            "description": "UAR sample size raised to 40",
            "affected_categories": ["ITGC - UAR"],
        }])
        with patch(PATCH_TARGET, return_value=mock_response):
            result = run_node("UAR sample size raised to 40 for FY2025.")

        changes = result["scope_changes"]
        assert any(c["change_type"] == "sample_size_change" for c in changes)

    def test_detects_period_change(self):
        mock_response = make_scope_diff_response([{
            "change_type": "period_change",
            "description": "Audit period extended to 15 months",
            "affected_categories": ["IT Systems Understanding", "ITGC - JML"],
        }])
        with patch(PATCH_TARGET, return_value=mock_response):
            result = run_node("Audit period extended to cover 15 months ending Dec 2025.")

        changes = result["scope_changes"]
        assert any(c["change_type"] == "period_change" for c in changes)

    def test_detects_multiple_changes(self):
        mock_response = make_scope_diff_response([
            {"change_type": "system_added",
             "description": "SAP newly in scope",
             "affected_categories": ["ITGC - JML", "ITGC - UAR"]},
            {"change_type": "sample_size_change",
             "description": "UAR sample size raised to 40",
             "affected_categories": ["ITGC - UAR"]},
            {"change_type": "system_removed",
             "description": "Legacy HR system removed",
             "affected_categories": ["IT Systems Understanding"]},
        ])
        with patch(PATCH_TARGET, return_value=mock_response):
            result = run_node("Mixed scope changes for FY2025.")

        assert len(result["scope_changes"]) == 3
        types = {c["change_type"] for c in result["scope_changes"]}
        assert "system_added"      in types
        assert "sample_size_change" in types
        assert "system_removed"    in types


class TestNoChanges:
    def test_returns_empty_list_when_llm_returns_empty(self):
        with patch(PATCH_TARGET, return_value="[]"):
            result = run_node("FY2025 scope: same as FY2024, no changes.")

        assert result["scope_changes"] == []
        assert result.get("error") is None

    def test_no_llm_call_for_empty_scope_text(self):
        with patch(PATCH_TARGET) as mock_llm:
            result = run_node("")

        mock_llm.assert_not_called()
        assert result["scope_changes"] == []

    def test_no_llm_call_for_whitespace_only_scope(self):
        with patch(PATCH_TARGET) as mock_llm:
            result = run_node("   \n  ")

        mock_llm.assert_not_called()
        assert result["scope_changes"] == []


class TestErrorHandling:
    def test_llm_exception_sets_error_key(self):
        with patch(PATCH_TARGET, side_effect=RuntimeError("API down")):
            result = run_node("Some scope text.")

        assert result["scope_changes"] == []
        assert result.get("error") is not None
        assert "API down" in result["error"]

    def test_malformed_json_returns_empty_list(self):
        with patch(PATCH_TARGET, return_value="not json at all }{"):
            result = run_node("Some scope text.")

        assert result["scope_changes"] == []
        # Should not raise; error key may or may not be set

    def test_json_object_instead_of_array(self):
        """LLM accidentally returns {} instead of [] — should not crash."""
        with patch(PATCH_TARGET, return_value='{"change_type": "system_added"}'):
            result = run_node("Some scope text.")

        assert isinstance(result["scope_changes"], list)

    def test_markdown_fenced_json_parsed(self):
        """LLM wraps response in ```json ... ``` fences — still parseable."""
        payload = [{"change_type": "system_added",
                    "description": "SAP newly in scope",
                    "affected_categories": ["ITGC - JML"]}]
        fenced = f"```json\n{json.dumps(payload)}\n```"
        with patch(PATCH_TARGET, return_value=fenced):
            result = run_node("SAP newly in scope.")

        assert len(result["scope_changes"]) == 1
        assert result["scope_changes"][0]["change_type"] == "system_added"

    def test_missing_scope_text_key(self):
        """Node receives state without current_year_scope_text — no crash."""
        state = {"client_name": "X", "audit_period": "FY2025"}
        with patch(PATCH_TARGET) as mock_llm:
            result = scope_diff_node(state)
        mock_llm.assert_not_called()
        assert result["scope_changes"] == []


class TestOutputShape:
    def test_scope_changes_is_list(self):
        with patch(PATCH_TARGET, return_value="[]"):
            result = run_node("No changes.")
        assert isinstance(result["scope_changes"], list)

    def test_each_change_has_required_keys(self):
        mock_response = make_scope_diff_response([{
            "change_type": "system_added",
            "description": "SAP newly in scope",
            "affected_categories": ["ITGC - JML"],
        }])
        with patch(PATCH_TARGET, return_value=mock_response):
            result = run_node("SAP newly in scope.")

        for change in result["scope_changes"]:
            assert "change_type"         in change
            assert "description"         in change
            assert "affected_categories" in change

    def test_affected_categories_is_list(self):
        mock_response = make_scope_diff_response([{
            "change_type": "sample_size_change",
            "description": "UAR raised to 40",
            "affected_categories": ["ITGC - UAR"],
        }])
        with patch(PATCH_TARGET, return_value=mock_response):
            result = run_node("UAR sample size raised.")

        for change in result["scope_changes"]:
            assert isinstance(change["affected_categories"], list)

    def test_change_type_preserved_verbatim(self):
        """change_type string is passed through exactly as the LLM returned it."""
        for ct in ["system_added", "system_removed", "period_change",
                   "regulation_change", "sample_size_change"]:
            mock_response = make_scope_diff_response([{
                "change_type": ct, "description": "test", "affected_categories": [],
            }])
            with patch(PATCH_TARGET, return_value=mock_response):
                result = run_node("scope text")
            assert result["scope_changes"][0]["change_type"] == ct

    def test_extra_llm_fields_dont_crash(self):
        """LLM returns extra keys in the change object — node should not crash."""
        mock_response = json.dumps([{
            "change_type": "system_added",
            "description": "SAP newly in scope",
            "affected_categories": [],
            "confidence": 0.95,   # extra field
            "source": "memo line 3",
        }])
        with patch(PATCH_TARGET, return_value=mock_response):
            result = run_node("SAP newly in scope.")
        assert len(result["scope_changes"]) == 1
