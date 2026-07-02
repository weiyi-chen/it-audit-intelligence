"""
One-time script: generate data/sample_client_FY2024/pbc_list.xlsx
with realistic prior-year PBC items across all ITGC categories.

Run once:  python create_sample_data.py
"""

import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from modules.pbc.xlsx_io import write_pbc_xlsx
from core.state import PBCItem

SAMPLE_ITEMS = [
    # ── IT Systems Understanding ─────────────────────────────────────────────
    PBCItem(item_id="SYS-ORA-001", category="IT Systems Understanding",
            description="Provide a system overview for Oracle EBS, including version, hosting, and owner.",
            in_scope=True, period="FY2024", sample_size=None,
            status="carried_over", last_year_id=None, notes=""),
    PBCItem(item_id="SYS-ORA-002", category="IT Systems Understanding",
            description="Provide the data-flow diagram for Oracle EBS showing key integrations.",
            in_scope=True, period="FY2024", sample_size=None,
            status="carried_over", last_year_id=None, notes=""),
    PBCItem(item_id="SYS-ORA-003", category="IT Systems Understanding",
            description="Confirm number of active users in Oracle EBS as at period end.",
            in_scope=True, period="FY2024", sample_size=None,
            status="carried_over", last_year_id=None, notes=""),

    # ── JML ──────────────────────────────────────────────────────────────────
    PBCItem(item_id="JML-ORA-001", category="ITGC - JML",
            description="Provide the complete population of user accounts created in Oracle EBS during FY2024.",
            in_scope=True, period="FY2024", sample_size="25",
            status="carried_over", last_year_id=None, notes=""),
    PBCItem(item_id="JML-ORA-002", category="ITGC - JML",
            description="For each sampled joiner in Oracle EBS: provide approval evidence prior to account creation.",
            in_scope=True, period="FY2024", sample_size="25",
            status="carried_over", last_year_id=None, notes=""),
    PBCItem(item_id="JML-ORA-003", category="ITGC - JML",
            description="Provide the population of user accounts disabled or deleted in Oracle EBS during FY2024.",
            in_scope=True, period="FY2024", sample_size="25",
            status="carried_over", last_year_id=None, notes=""),
    PBCItem(item_id="JML-ORA-004", category="ITGC - JML",
            description="For each sampled leaver in Oracle EBS: provide evidence that account was disabled within SLA.",
            in_scope=True, period="FY2024", sample_size="25",
            status="carried_over", last_year_id=None, notes=""),

    # ── UAR ──────────────────────────────────────────────────────────────────
    PBCItem(item_id="UAR-ORA-001", category="ITGC - UAR",
            description="Provide documentation of the formal UAR conducted for Oracle EBS during FY2024.",
            in_scope=True, period="FY2024", sample_size="1 review cycle",
            status="carried_over", last_year_id=None, notes=""),
    PBCItem(item_id="UAR-ORA-002", category="ITGC - UAR",
            description="Provide the full population of active Oracle EBS users as at UAR review date.",
            in_scope=True, period="FY2024", sample_size="25",
            status="carried_over", last_year_id=None, notes="UAR sample size was 25 in FY2024."),
    PBCItem(item_id="UAR-ORA-003", category="ITGC - UAR",
            description="For sampled Oracle EBS users: provide manager certification of access appropriateness.",
            in_scope=True, period="FY2024", sample_size="25",
            status="carried_over", last_year_id=None, notes=""),

    # ── Change Management ─────────────────────────────────────────────────────
    PBCItem(item_id="CHG-ORA-001", category="ITGC - ChangeMgmt",
            description="Provide population of all changes deployed to Oracle EBS during FY2024.",
            in_scope=True, period="FY2024", sample_size="25",
            status="carried_over", last_year_id=None, notes=""),
    PBCItem(item_id="CHG-ORA-002", category="ITGC - ChangeMgmt",
            description="For sampled Oracle EBS changes: provide change request showing testing and approvals.",
            in_scope=True, period="FY2024", sample_size="25",
            status="carried_over", last_year_id=None, notes=""),
    PBCItem(item_id="CHG-ORA-003", category="ITGC - ChangeMgmt",
            description="Provide evidence of separation of duties for Oracle EBS production deployments.",
            in_scope=True, period="FY2024", sample_size="25",
            status="carried_over", last_year_id=None, notes=""),

    # ── Privileged Access ─────────────────────────────────────────────────────
    PBCItem(item_id="PVA-ORA-001", category="ITGC - PrivAccess",
            description="Provide list of all privileged/admin accounts in Oracle EBS as at period end.",
            in_scope=True, period="FY2024", sample_size=None,
            status="carried_over", last_year_id=None, notes=""),
    PBCItem(item_id="PVA-ORA-002", category="ITGC - PrivAccess",
            description="Provide evidence of formal privileged access review for Oracle EBS during FY2024.",
            in_scope=True, period="FY2024", sample_size="1 review cycle",
            status="carried_over", last_year_id=None, notes=""),

    # ── Backup ────────────────────────────────────────────────────────────────
    PBCItem(item_id="BKP-ORA-001", category="ITGC - Backup",
            description="Provide the backup schedule and policy for Oracle EBS.",
            in_scope=True, period="FY2024", sample_size=None,
            status="carried_over", last_year_id=None, notes=""),
    PBCItem(item_id="BKP-ORA-002", category="ITGC - Backup",
            description="Provide backup completion logs for Oracle EBS for a representative 3-month window.",
            in_scope=True, period="FY2024", sample_size="3 months",
            status="carried_over", last_year_id=None, notes=""),
    PBCItem(item_id="BKP-ORA-003", category="ITGC - Backup",
            description="Provide evidence of at least one restoration test for Oracle EBS during FY2024.",
            in_scope=True, period="FY2024", sample_size="1 restoration test",
            status="carried_over", last_year_id=None, notes=""),
]

if __name__ == "__main__":
    out = os.path.join("data", "sample_client_FY2024", "pbc_list.xlsx")
    write_pbc_xlsx(SAMPLE_ITEMS, out)
    print(f"✅ Created sample data: {out}  ({len(SAMPLE_ITEMS)} items)")
