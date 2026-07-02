"""
Pydantic request / response models for the IT Audit Intelligence API.
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Shared
# ─────────────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    llm_mode: str            # "real" | "mock"
    checkpointer: str = ""   # "memory" | "sqlite"
    checkpoint_persistent: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Module A — PBC Checklist Generator
# ─────────────────────────────────────────────────────────────────────────────

class ScopeChangeSummary(BaseModel):
    change_type: str
    description: str
    affected_categories: List[str]


class PBCItemSummary(BaseModel):
    item_id: str
    category: str
    description: str
    status: str   # carried_over | updated | new | removed
    period: str
    sample_size: Optional[str] = None


class PBCGenerateResponse(BaseModel):
    """
    Response from POST /api/pbc/generate.

    The generated xlsx is returned as a base64-encoded string so the browser
    can trigger a client-side download without a separate file-serving endpoint.
    """
    client_name: str
    audit_period: str
    scope_changes: List[ScopeChangeSummary]
    item_count: int
    status_breakdown: dict  # {"new": 5, "updated": 2, ...}
    xlsx_base64: str         # base64-encoded .xlsx bytes
    xlsx_filename: str       # suggested download filename
    llm_mode: str            # "real" | "mock"
    elapsed_seconds: float


# ─────────────────────────────────────────────────────────────────────────────
# Audit history
# ─────────────────────────────────────────────────────────────────────────────

class RunSummary(BaseModel):
    """One row in the audit history list (no xlsx blob)."""
    id: int
    client_name: str
    audit_period: str
    item_count: Optional[int] = None
    llm_mode: Optional[str] = None
    elapsed_secs: Optional[float] = None
    xlsx_filename: Optional[str] = None
    scope_changes: Optional[List[ScopeChangeSummary]] = None
    status_breakdown: Optional[dict] = None
    created_at: Optional[str] = None


class RunDetail(RunSummary):
    """Full run including base64 xlsx for re-download."""
    xlsx_base64: Optional[str] = None


class HistoryResponse(BaseModel):
    runs: List[RunSummary]
    total: int


# ─────────────────────────────────────────────────────────────────────────────
# Email dispatch
# ─────────────────────────────────────────────────────────────────────────────

class SendEmailRequest(BaseModel):
    to_email: str = Field(..., description="Recipient email address")
    client_name: str
    audit_period: str
    xlsx_base64: str   = Field(..., description="Base64-encoded xlsx attachment")
    filename: str      = Field("pbc_list.xlsx", description="Attachment filename")
    message: str       = Field("", description="Optional custom message body")


class SendEmailResponse(BaseModel):
    status: str   # "sent"
    to: str
    message_id: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Module A — Async review flow (LangGraph interrupt/resume)
# ─────────────────────────────────────────────────────────────────────────────

class AsyncStartRequest(BaseModel):
    """POST /api/pbc/async/start"""
    scope_text:   str = Field(...,        description="Current-year scope memo text")
    client_name:  str = Field("Client",   description="Client name")
    audit_period: str = Field("FY2025",   description="Audit period, e.g. FY2025")
    # prior_xlsx is sent as multipart — handled separately


class AsyncStartResponse(BaseModel):
    """
    Returned when the graph hits review_node and pauses.
    The auditor reviews the draft via GET /api/pbc/async/{thread_id}/status,
    then approves or rejects via the respective POST endpoints.
    """
    thread_id: str
    status: str                          # "pending_review"
    client_name: str
    audit_period: str
    item_count: int
    status_breakdown: dict               # {"new": 5, "carried_over": 13, ...}
    scope_changes: List[ScopeChangeSummary]
    llm_mode: str
    elapsed_seconds: float
    checkpointer_type: str               # "memory" | "sqlite"
    message: str = "Draft PBC ready — awaiting auditor approval."


class AsyncStatusResponse(BaseModel):
    """GET /api/pbc/async/{thread_id}/status"""
    thread_id: str
    status: str          # "pending_review" | "approved" | "completed" | "not_found"
    item_count: Optional[int] = None
    status_breakdown: Optional[dict] = None
    scope_changes: Optional[List[ScopeChangeSummary]] = None
    next_node: Optional[str] = None      # which node executes next


class ResumeRequest(BaseModel):
    """POST /api/pbc/async/{thread_id}/approve or /reject"""
    notes: str = Field("", description="Auditor notes (rejection reason, revision instructions)")


class AsyncResumeResponse(BaseModel):
    """
    Returned after approve/reject.
    - Approved: status="completed", xlsx_base64 is present
    - Rejected + loop: status="pending_review", thread_id same, new draft ready
    """
    thread_id: str
    status: str          # "completed" | "pending_review"
    item_count: Optional[int] = None
    status_breakdown: Optional[dict] = None
    scope_changes: Optional[List[ScopeChangeSummary]] = None
    xlsx_base64: Optional[str] = None    # present when status="completed"
    xlsx_filename: Optional[str] = None
    llm_mode: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    message: str = ""
