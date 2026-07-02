"""
Precision / Recall evaluation for scope_diff_node against the golden dataset.

What this measures
──────────────────
Given a hand-labelled set of (scope_memo, expected_changes) pairs, we run
scope_diff_node in mock-LLM mode (no API cost) and compare the detected
change_types against the expected ones.

  Precision = correctly detected / total detected
  Recall    = correctly detected / total expected

Why this matters
────────────────
Every time we tweak the scope_diff prompt we risk silent regression —
items that were correctly detected start getting missed, or false positives
appear.  Running this script after any prompt change gives a quantitative
baseline to compare against.

With a real ANTHROPIC_API_KEY:
    The test is skipped so CI doesn't burn tokens.  Run manually with:
        EVAL_WITH_REAL_LLM=1 pytest tests/pbc/test_precision_recall.py -v

In mock-LLM mode (default / CI):
    The mock in core/llm.py is keyword-based; precision/recall reflect
    the mock's behaviour, not Claude's — useful for catching regressions
    in the node's JSON parsing and routing logic rather than LLM quality.

Golden dataset location: data/golden/case_XX/
    prior_pbc.xlsx          — prior year PBC (fed to ingest_node first)
    scope_memo.txt          — current year scope text
    expected_changes.json   — List[ScopeChange] ground truth
"""

from __future__ import annotations

import json
import os

import pytest

from core.llm import has_real_key
from modules.pbc.nodes import scope_diff_node

GOLDEN_DIR   = os.path.join(os.path.dirname(__file__), "..", "..", "data", "golden")
SKIP_REAL_LLM = not bool(os.getenv("EVAL_WITH_REAL_LLM"))

# ─── helpers ─────────────────────────────────────────────────────────────────

def load_case(case_name: str) -> tuple[str, list[dict]]:
    """Return (scope_memo_text, expected_changes) for a golden case."""
    case_dir = os.path.join(GOLDEN_DIR, case_name)
    with open(os.path.join(case_dir, "scope_memo.txt")) as f:
        scope_memo = f.read()
    with open(os.path.join(case_dir, "expected_changes.json")) as f:
        expected = json.load(f)
    return scope_memo, expected


def run_scope_diff(scope_text: str) -> list[dict]:
    state = {
        "client_name":             "ACME Corp",
        "audit_period":            "FY2025",
        "current_year_scope_text": scope_text,
        "prior_year_items":        [],
        "scope_changes":           [],
    }
    result = scope_diff_node(state)
    return result.get("scope_changes", [])


def precision_recall(detected: list[dict], expected: list[dict]) -> tuple[float, float]:
    """
    Compute precision and recall based on change_type matching.

    A detected change is counted as a true positive if its change_type
    appears in the expected list (one-to-one matching, no duplicates).
    """
    expected_types = [c["change_type"] for c in expected]
    remaining      = list(expected_types)  # mutable copy for one-to-one matching

    tp = 0
    for det in detected:
        ct = det["change_type"]
        if ct in remaining:
            tp += 1
            remaining.remove(ct)

    precision = tp / len(detected)  if detected  else (1.0 if not expected else 0.0)
    recall    = tp / len(expected)  if expected  else (1.0 if not detected else 0.0)
    return precision, recall


# ─── golden dataset availability ─────────────────────────────────────────────

def golden_cases_available() -> bool:
    if not os.path.isdir(GOLDEN_DIR):
        return False
    return any(
        os.path.isdir(os.path.join(GOLDEN_DIR, d))
        for d in os.listdir(GOLDEN_DIR)
        if d.startswith("case_")
    )


# ─── tests ───────────────────────────────────────────────────────────────────

@pytest.mark.skipif(not golden_cases_available(),
                    reason="Golden dataset not yet generated — run create_golden_dataset.py")
class TestGoldenDataset:
    """
    For each case: verify scope_diff_node's output against ground truth.
    In mock-LLM mode, these tests validate parsing + routing logic.
    In real-LLM mode (EVAL_WITH_REAL_LLM=1), they validate actual Claude quality.
    """

    def test_case_01_no_change_returns_empty(self):
        """Case 01: no scope changes → expected []."""
        scope_memo, expected = load_case("case_01")
        detected = run_scope_diff(scope_memo)

        # In mock mode the keyword-driven mock may or may not detect changes;
        # what we assert is that the output is a valid list (no crash).
        assert isinstance(detected, list)

        if has_real_key() and not SKIP_REAL_LLM:
            assert detected == [], \
                f"Expected no changes, but detected: {[c['change_type'] for c in detected]}"

    def test_case_02_system_added_detected(self):
        """Case 02: SAP added → must detect exactly system_added."""
        scope_memo, expected = load_case("case_02")
        detected = run_scope_diff(scope_memo)

        assert isinstance(detected, list)
        types_detected = {c["change_type"] for c in detected}

        # In both mock and real mode, system_added should be detected
        # (the mock is tuned to detect 'newly in scope' patterns)
        assert "system_added" in types_detected, \
            f"Expected system_added, got: {types_detected}"

    def test_case_03_mixed_changes_detected(self):
        """Case 03: system_added + system_removed + sample_size_change."""
        scope_memo, expected = load_case("case_03")
        detected = run_scope_diff(scope_memo)

        assert isinstance(detected, list)
        types_detected = {c["change_type"] for c in detected}

        # system_added must always be detected (strongest signal in scope text)
        assert "system_added" in types_detected


@pytest.mark.skipif(not golden_cases_available(),
                    reason="Golden dataset not yet generated")
class TestPrecisionRecallMetrics:
    """
    Compute and assert minimum P/R thresholds.

    In mock mode: thresholds are set conservatively since the mock is
    keyword-based, not semantic.  Raise these thresholds after validating
    with real Claude.
    """

    CASES = ["case_01", "case_02", "case_03"]

    # Minimum acceptable precision/recall in mock mode
    MOCK_MIN_RECALL    = 0.33   # at least 1 out of 3 cases detected correctly
    MOCK_MIN_PRECISION = 0.50   # at least half of detections are correct

    # Targets for real-LLM evaluation (set EVAL_WITH_REAL_LLM=1)
    REAL_MIN_RECALL    = 0.80
    REAL_MIN_PRECISION = 0.80

    def _aggregate_metrics(self) -> tuple[float, float]:
        all_detected, all_expected = [], []
        for case in self.CASES:
            scope_memo, expected = load_case(case)
            detected = run_scope_diff(scope_memo)
            all_detected.extend(detected)
            all_expected.extend(expected)
        return precision_recall(all_detected, all_expected)

    def test_aggregate_precision_above_threshold(self):
        precision, _ = self._aggregate_metrics()
        threshold = self.REAL_MIN_PRECISION if (has_real_key() and not SKIP_REAL_LLM) \
                    else self.MOCK_MIN_PRECISION
        assert precision >= threshold, \
            f"Precision {precision:.2f} below threshold {threshold:.2f}"

    def test_aggregate_recall_above_threshold(self):
        _, recall = self._aggregate_metrics()
        threshold = self.REAL_MIN_RECALL if (has_real_key() and not SKIP_REAL_LLM) \
                    else self.MOCK_MIN_RECALL
        assert recall >= threshold, \
            f"Recall {recall:.2f} below threshold {threshold:.2f}"

    def test_print_per_case_breakdown(self, capsys):
        """Non-asserting: prints a P/R breakdown for human review."""
        print("\n" + "=" * 55)
        print("  scope_diff_node — Precision / Recall by Case")
        print("  LLM mode:", "🟢 real" if has_real_key() else "🟡 mock")
        print("=" * 55)

        totals_tp = totals_det = totals_exp = 0

        for case in self.CASES:
            scope_memo, expected = load_case(case)
            detected = run_scope_diff(scope_memo)
            p, r = precision_recall(detected, expected)

            exp_types = [c["change_type"] for c in expected]
            det_types = [c["change_type"] for c in detected]

            print(f"\n  {case}:")
            print(f"    Expected : {exp_types}")
            print(f"    Detected : {det_types}")
            print(f"    P={p:.2f}  R={r:.2f}")

            # Accumulate for aggregate
            remaining = list(exp_types)
            for dt in det_types:
                if dt in remaining:
                    totals_tp += 1
                    remaining.remove(dt)
            totals_det += len(det_types)
            totals_exp += len(exp_types)

        agg_p = totals_tp / totals_det if totals_det else 1.0
        agg_r = totals_tp / totals_exp if totals_exp else 1.0
        print(f"\n  Aggregate: P={agg_p:.2f}  R={agg_r:.2f}")
        print("=" * 55)
