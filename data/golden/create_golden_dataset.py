"""
Creates the golden dataset for Module A precision/recall evaluation.

Run once:  python data/golden/create_golden_dataset.py

Produces three triples under data/golden/:
  case_01/ — no-change: scope identical to prior year → expect []
  case_02/ — system_added: SAP newly in scope
  case_03/ — mixed: system_added + sample_size_change + system_removed

Each case folder contains:
  prior_pbc.xlsx      — prior year PBC list (input to ingest_node)
  scope_memo.txt      — current year scope text (input to scope_diff_node)
  expected_changes.json — ground-truth List[ScopeChange] (used by eval script)
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.state import PBCItem, ScopeChange
from modules.pbc.xlsx_io import write_pbc_xlsx

GOLDEN_DIR = os.path.dirname(__file__)


# ─── shared prior-year items (Oracle EBS) ────────────────────────────────────

ORACLE_ITEMS = [
    PBCItem(item_id="SYS-ORA-001", category="IT Systems Understanding",
            description="System overview for Oracle EBS: version, hosting, owner.",
            in_scope=True, period="FY2024", sample_size=None,
            status="carried_over", last_year_id=None, notes=""),
    PBCItem(item_id="JML-ORA-001", category="ITGC - JML",
            description="Population of users created in Oracle EBS during FY2024.",
            in_scope=True, period="FY2024", sample_size="25",
            status="carried_over", last_year_id=None, notes=""),
    PBCItem(item_id="JML-ORA-002", category="ITGC - JML",
            description="Leaver account disable evidence for Oracle EBS.",
            in_scope=True, period="FY2024", sample_size="25",
            status="carried_over", last_year_id=None, notes=""),
    PBCItem(item_id="UAR-ORA-001", category="ITGC - UAR",
            description="UAR documentation for Oracle EBS FY2024.",
            in_scope=True, period="FY2024", sample_size="25",
            status="carried_over", last_year_id=None, notes=""),
    PBCItem(item_id="CHG-ORA-001", category="ITGC - ChangeMgmt",
            description="Change population for Oracle EBS FY2024.",
            in_scope=True, period="FY2024", sample_size="25",
            status="carried_over", last_year_id=None, notes=""),
    PBCItem(item_id="BKP-ORA-001", category="ITGC - Backup",
            description="Backup schedule for Oracle EBS.",
            in_scope=True, period="FY2024", sample_size=None,
            status="carried_over", last_year_id=None, notes=""),
    PBCItem(item_id="PVA-ORA-001", category="ITGC - PrivAccess",
            description="Privileged account list for Oracle EBS.",
            in_scope=True, period="FY2024", sample_size=None,
            status="carried_over", last_year_id=None, notes=""),
]


def _write_case(case_dir: str, scope_memo: str,
                expected_changes: list[ScopeChange]) -> None:
    os.makedirs(case_dir, exist_ok=True)
    write_pbc_xlsx(ORACLE_ITEMS, os.path.join(case_dir, "prior_pbc.xlsx"))
    with open(os.path.join(case_dir, "scope_memo.txt"), "w") as f:
        f.write(scope_memo)
    with open(os.path.join(case_dir, "expected_changes.json"), "w") as f:
        json.dump(expected_changes, f, indent=2)


# ─── Case 01: no change ───────────────────────────────────────────────────────
_write_case(
    os.path.join(GOLDEN_DIR, "case_01"),
    scope_memo=(
        "FY2025 IT Audit Scope — ACME Corp\n\n"
        "Scope for FY2025 is unchanged from FY2024. Oracle EBS remains the "
        "only in-scope application. Sample sizes, audit period, and control "
        "areas are identical to the prior year. No regulatory changes affect "
        "the scope."
    ),
    expected_changes=[],
)

# ─── Case 02: system added ────────────────────────────────────────────────────
_write_case(
    os.path.join(GOLDEN_DIR, "case_02"),
    scope_memo=(
        "FY2025 IT Audit Scope — ACME Corp\n\n"
        "Effective 1 January 2025, SAP S/4HANA has replaced the legacy Oracle EBS "
        "for all core finance processes. SAP S/4HANA is now in scope for FY2025 "
        "ITGC testing across all control areas (JML, UAR, Change Management, "
        "Privileged Access, Backup). Oracle EBS will remain in scope as it "
        "continues to process legacy transactions through Q1 2025."
    ),
    expected_changes=[
        ScopeChange(
            change_type="system_added",
            description="SAP S/4HANA newly in scope effective January 2025",
            affected_categories=[
                "IT Systems Understanding",
                "ITGC - JML",
                "ITGC - UAR",
                "ITGC - ChangeMgmt",
                "ITGC - PrivAccess",
                "ITGC - Backup",
            ],
        ),
    ],
)

# ─── Case 03: mixed changes ───────────────────────────────────────────────────
_write_case(
    os.path.join(GOLDEN_DIR, "case_03"),
    scope_memo=(
        "FY2025 IT Audit Scope — ACME Corp\n\n"
        "1. SAP S/4HANA is newly in scope from 1 March 2025 following the "
        "ERP migration. All standard ITGC areas apply.\n\n"
        "2. The legacy payroll system (HR-Legacy) has been decommissioned "
        "as of 31 December 2024 and is no longer in scope.\n\n"
        "3. Per the FY2025 audit plan, UAR sample sizes have been increased "
        "from 25 to 40 to align with the firm's updated sampling methodology.\n\n"
        "Oracle EBS otherwise remains in scope with no other changes."
    ),
    expected_changes=[
        ScopeChange(
            change_type="system_added",
            description="SAP S/4HANA newly in scope from 1 March 2025",
            affected_categories=[
                "IT Systems Understanding",
                "ITGC - JML",
                "ITGC - UAR",
                "ITGC - ChangeMgmt",
                "ITGC - PrivAccess",
                "ITGC - Backup",
            ],
        ),
        ScopeChange(
            change_type="system_removed",
            description="HR-Legacy decommissioned, removed from scope",
            affected_categories=["IT Systems Understanding", "ITGC - JML"],
        ),
        ScopeChange(
            change_type="sample_size_change",
            description="UAR sample size increased from 25 to 40",
            affected_categories=["ITGC - UAR"],
        ),
    ],
)

print("✅ Golden dataset created:")
for case in ["case_01", "case_02", "case_03"]:
    case_dir = os.path.join(GOLDEN_DIR, case)
    files = os.listdir(case_dir)
    changes = json.load(open(os.path.join(case_dir, "expected_changes.json")))
    print(f"  {case}/  ({len(files)} files, {len(changes)} expected change(s))")
