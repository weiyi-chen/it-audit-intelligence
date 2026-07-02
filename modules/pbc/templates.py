"""
Standard PBC item templates per ITGC control category.

Each category has a list of template dicts — partial PBCItem shapes that
lack item_id, period, status, and last_year_id (those are set at
instantiation time when a new system enters scope).

Public API
──────────
    CATEGORIES          : list of all supported category strings
    get_templates(cat)  : List[dict] for a given category key
    instantiate_items(
        category,
        system_name,
        audit_period,
        *,
        start_seq=1,
    ) → List[PBCItem]

Category keys accepted (case-insensitive, spaces/hyphens normalised):
    "IT Systems Understanding"
    "ITGC - JML"  (Joiner / Mover / Leaver)
    "ITGC - UAR"  (User Access Review)
    "ITGC - ChangeMgmt"
    "ITGC - PrivAccess"
    "ITGC - ProgramDev"
    "ITGC - Backup"

When a new system is added to scope (ScopeChange.change_type == "system_added"),
update_items_node calls instantiate_items for every affected_category listed in
the ScopeChange, generating correctly prefixed, status="new" PBCItems.
"""

from __future__ import annotations

import re
from typing import Dict, List

from core.state import PBCItem

# ─────────────────────────────────────────────────────────────────────────────
# Category code mapping (used to build item_id prefixes)
# ─────────────────────────────────────────────────────────────────────────────

_CATEGORY_CODE: Dict[str, str] = {
    "IT Systems Understanding": "SYS",
    "ITGC - JML":               "JML",
    "ITGC - UAR":               "UAR",
    "ITGC - ChangeMgmt":        "CHG",
    "ITGC - PrivAccess":        "PVA",
    "ITGC - ProgramDev":        "PGD",
    "ITGC - Backup":            "BKP",
}

CATEGORIES: List[str] = list(_CATEGORY_CODE.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Template definitions
# Each entry is a partial PBCItem (no item_id / period / status / last_year_id).
# {system} is a placeholder replaced at instantiation time.
# ─────────────────────────────────────────────────────────────────────────────

_TEMPLATES: Dict[str, List[dict]] = {

    # ── IT Systems Understanding ─────────────────────────────────────────────
    "IT Systems Understanding": [
        {
            "description": (
                "Provide a system overview for {system}, including: system name, "
                "version, hosting environment (on-premise / cloud / hybrid), "
                "primary business purpose, owner name and title."
            ),
            "in_scope": True,
            "sample_size": None,
            "notes": "Typically satisfied by IT inventory or system profile document.",
        },
        {
            "description": (
                "Provide the data-flow diagram or architectural overview for {system}, "
                "showing key integrations with upstream and downstream systems."
            ),
            "in_scope": True,
            "sample_size": None,
            "notes": "",
        },
        {
            "description": (
                "Confirm the number of active users with access to {system} "
                "as at the period end date, broken down by user role / access level."
            ),
            "in_scope": True,
            "sample_size": None,
            "notes": "",
        },
        {
            "description": (
                "Provide contact details for the {system} system owner, IT owner, "
                "and primary business owner."
            ),
            "in_scope": True,
            "sample_size": None,
            "notes": "",
        },
    ],

    # ── JML — Joiner / Mover / Leaver ────────────────────────────────────────
    "ITGC - JML": [
        {
            "description": (
                "Provide the complete population of all user accounts created in {system} "
                "during the audit period, including: username, full name, date of creation, "
                "role/access level granted, and approving manager."
            ),
            "in_scope": True,
            "sample_size": "25",
            "notes": "Used to select joiner sample.",
        },
        {
            "description": (
                "For each sampled joiner in {system}: provide the access request form or "
                "ticket showing manager approval prior to (or on the same day as) "
                "account creation."
            ),
            "in_scope": True,
            "sample_size": "25",
            "notes": "Evidence of authorised provisioning.",
        },
        {
            "description": (
                "Provide the complete population of all user accounts modified (role change, "
                "access change) in {system} during the audit period, including approving manager."
            ),
            "in_scope": True,
            "sample_size": "25",
            "notes": "Used to select mover sample.",
        },
        {
            "description": (
                "For each sampled mover in {system}: provide evidence that the access change "
                "was approved and that previous access was revoked promptly."
            ),
            "in_scope": True,
            "sample_size": "25",
            "notes": "",
        },
        {
            "description": (
                "Provide the complete population of all user accounts disabled or deleted in "
                "{system} during the audit period.  Include: username, termination date, "
                "date account was disabled, and the HR/IT ticket reference."
            ),
            "in_scope": True,
            "sample_size": "25",
            "notes": "Used to select leaver sample.",
        },
        {
            "description": (
                "For each sampled leaver in {system}: provide evidence that the account was "
                "disabled within the organisation's SLA (e.g., same day as termination date)."
            ),
            "in_scope": True,
            "sample_size": "25",
            "notes": "Key risk: terminated users retaining access.",
        },
    ],

    # ── UAR — User Access Review ──────────────────────────────────────────────
    "ITGC - UAR": [
        {
            "description": (
                "Provide documentation of the formal User Access Review (UAR) conducted for "
                "{system} during the audit period, including: review date, reviewer name, "
                "population reviewed, and summary of exceptions found."
            ),
            "in_scope": True,
            "sample_size": "1 review cycle",
            "notes": "At minimum one full UAR cycle must cover the audit period.",
        },
        {
            "description": (
                "Provide the full population of active users in {system} as at the UAR "
                "review date, with their access roles/entitlements."
            ),
            "in_scope": True,
            "sample_size": "40",
            "notes": "Population for auditor re-performance sample.",
        },
        {
            "description": (
                "For sampled {system} users in the UAR: provide evidence of manager "
                "certification (email, tool screenshot, or sign-off form) confirming "
                "access is appropriate."
            ),
            "in_scope": True,
            "sample_size": "40",
            "notes": "",
        },
        {
            "description": (
                "For any exceptions identified during the {system} UAR: provide evidence "
                "of remediation action taken and the date access was removed or corrected."
            ),
            "in_scope": True,
            "sample_size": None,
            "notes": "All exceptions must be tracked to closure.",
        },
    ],

    # ── Change Management ─────────────────────────────────────────────────────
    "ITGC - ChangeMgmt": [
        {
            "description": (
                "Provide the complete population of all changes (patches, releases, "
                "configuration changes) deployed to {system} during the audit period, "
                "including: change ID, description, change date, and category "
                "(normal / emergency / standard)."
            ),
            "in_scope": True,
            "sample_size": "25",
            "notes": "Used to select change management sample.",
        },
        {
            "description": (
                "For each sampled change to {system}: provide the change request / ticket "
                "showing: (a) business justification, (b) technical review/approval, "
                "(c) testing evidence (UAT/SIT sign-off), (d) production deployment approval."
            ),
            "in_scope": True,
            "sample_size": "25",
            "notes": "Key evidence: separation of development, test, and production.",
        },
        {
            "description": (
                "Provide evidence of the separation of duties control for {system}: "
                "demonstrate that the developer who coded the change did NOT deploy "
                "it directly to production."
            ),
            "in_scope": True,
            "sample_size": "25",
            "notes": "",
        },
        {
            "description": (
                "Provide the emergency change log for {system} during the audit period, "
                "including post-implementation reviews for each emergency change."
            ),
            "in_scope": True,
            "sample_size": None,
            "notes": "Emergency changes require retroactive approval.",
        },
    ],

    # ── Privileged Access ─────────────────────────────────────────────────────
    "ITGC - PrivAccess": [
        {
            "description": (
                "Provide a complete list of all privileged / administrative accounts in "
                "{system} as at the period end date, including: account name, role, "
                "assigned user (if applicable), and whether the account is shared."
            ),
            "in_scope": True,
            "sample_size": None,
            "notes": "Privileged accounts include DBA, sysadmin, root, service accounts.",
        },
        {
            "description": (
                "Provide evidence of a formal periodic privileged access review for "
                "{system} conducted during the audit period, including reviewer, date, "
                "and action taken on identified unnecessary privileges."
            ),
            "in_scope": True,
            "sample_size": "1 review cycle",
            "notes": "",
        },
        {
            "description": (
                "Confirm whether any shared / generic privileged accounts exist in {system} "
                "and, if so, provide the compensating controls in place "
                "(e.g., password vault, session recording)."
            ),
            "in_scope": True,
            "sample_size": None,
            "notes": "",
        },
        {
            "description": (
                "Provide evidence that privileged access to {system} is logged and that "
                "logs are retained in accordance with the organisation's log retention policy "
                "(typically ≥ 12 months)."
            ),
            "in_scope": True,
            "sample_size": None,
            "notes": "",
        },
    ],

    # ── Program Development / SDLC ────────────────────────────────────────────
    "ITGC - ProgramDev": [
        {
            "description": (
                "Provide the list of all significant development projects / releases "
                "related to {system} completed during the audit period, including: "
                "project name, go-live date, and project sponsor."
            ),
            "in_scope": True,
            "sample_size": "2 projects",
            "notes": "Select two projects for detailed SDLC testing.",
        },
        {
            "description": (
                "For sampled {system} projects: provide the project charter or requirements "
                "document showing formal sign-off by the business sponsor before development began."
            ),
            "in_scope": True,
            "sample_size": "2 projects",
            "notes": "",
        },
        {
            "description": (
                "For sampled {system} projects: provide User Acceptance Testing (UAT) sign-off "
                "documentation confirming the business accepted the solution before go-live."
            ),
            "in_scope": True,
            "sample_size": "2 projects",
            "notes": "",
        },
        {
            "description": (
                "For sampled {system} projects: provide evidence of post-implementation review "
                "or hypercare period sign-off confirming the system operated as intended "
                "after go-live."
            ),
            "in_scope": True,
            "sample_size": "2 projects",
            "notes": "",
        },
        {
            "description": (
                "Provide documentation confirming that {system} maintains separate "
                "development, testing, and production environments, and that code "
                "cannot be promoted directly from development to production without approval."
            ),
            "in_scope": True,
            "sample_size": None,
            "notes": "Environment separation is a key SDLC ITGC.",
        },
    ],

    # ── Backup & Recovery ─────────────────────────────────────────────────────
    "ITGC - Backup": [
        {
            "description": (
                "Provide the backup schedule / policy for {system}, including: backup "
                "frequency (full / incremental), retention period, storage location "
                "(on-site / off-site / cloud), and responsible team."
            ),
            "in_scope": True,
            "sample_size": None,
            "notes": "",
        },
        {
            "description": (
                "Provide backup completion logs for {system} for the audit period, "
                "demonstrating that scheduled backups completed successfully.  "
                "Highlight any failed backup jobs and the resolution taken."
            ),
            "in_scope": True,
            "sample_size": "3 months",
            "notes": "Select a representative three-month window from the audit period.",
        },
        {
            "description": (
                "Provide evidence of at least one restoration test conducted for "
                "{system} during the audit period, including: date of test, "
                "system/data restored, outcome, and sign-off by IT management."
            ),
            "in_scope": True,
            "sample_size": "1 restoration test",
            "notes": "Restoration testing confirms recoverability.",
        },
        {
            "description": (
                "Confirm the Recovery Time Objective (RTO) and Recovery Point Objective "
                "(RPO) targets for {system} and provide evidence that the last restoration "
                "test result met those targets."
            ),
            "in_scope": True,
            "sample_size": None,
            "notes": "",
        },
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Public helpers
# ─────────────────────────────────────────────────────────────────────────────

def _normalise_category(category: str) -> str:
    """Accept category strings with minor variations in spacing / casing."""
    # Canonical form already present?
    if category in _TEMPLATES:
        return category
    # Try case-insensitive match
    lower = category.lower()
    for key in _TEMPLATES:
        if key.lower() == lower:
            return key
    # Fuzzy: strip punctuation and compare
    def strip_punc(s: str) -> str:
        return re.sub(r"[\s\-_]+", "", s).lower()
    stripped = strip_punc(category)
    for key in _TEMPLATES:
        if strip_punc(key) == stripped:
            return key
    return category  # return as-is; caller handles KeyError


def get_templates(category: str) -> List[dict]:
    """Return the list of template dicts for *category*.

    Raises KeyError if the category is not recognised.
    """
    normalised = _normalise_category(category)
    return _TEMPLATES[normalised]


def _system_code(system_name: str) -> str:
    """'SAP S/4HANA' → 'SAP',  'Oracle EBS' → 'ORA'."""
    words = re.findall(r"[A-Za-z0-9]+", system_name)
    if not words:
        return "SYS"
    code = words[0].upper()[:6]
    return code


def instantiate_items(
    category: str,
    system_name: str,
    audit_period: str,
    *,
    start_seq: int = 1,
) -> List[PBCItem]:
    """
    Instantiate template PBCItems for *system_name* in *category*.

    Parameters
    ----------
    category     : one of CATEGORIES (tolerates minor casing variations)
    system_name  : e.g. "SAP S/4HANA", "Oracle EBS"
    audit_period : e.g. "FY2025"
    start_seq    : first sequence number for item_id generation

    Returns
    -------
    List[PBCItem] with status="new", period=audit_period, last_year_id=None.
    Returns empty list if category is not found (logged, not raised).
    """
    try:
        templates = get_templates(category)
    except KeyError:
        return []

    normalised = _normalise_category(category)
    cat_code   = _CATEGORY_CODE.get(normalised, "UNK")
    sys_code   = _system_code(system_name)

    items: List[PBCItem] = []
    for seq, tmpl in enumerate(templates, start=start_seq):
        item_id = f"{cat_code}-{sys_code}-{seq:03d}"
        description = tmpl["description"].replace("{system}", system_name)
        item = PBCItem(
            item_id      = item_id,
            category     = normalised,
            description  = description,
            in_scope     = tmpl.get("in_scope", True),
            period       = audit_period,
            sample_size  = tmpl.get("sample_size"),
            status       = "new",
            last_year_id = None,
            notes        = tmpl.get("notes", ""),
        )
        items.append(item)

    return items
