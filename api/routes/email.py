"""
POST /api/send-email
────────────────────
Dispatches the generated PBC xlsx as an email attachment via Resend.

Requires env vars:
    RESEND_API_KEY   — Resend API key (re_...)
    SENDER_FROM      — verified sender address (e.g. audit@yourdomain.com)
"""

from __future__ import annotations

import base64
import os

from fastapi import APIRouter, HTTPException

from api.schemas import SendEmailRequest, SendEmailResponse

router = APIRouter()


@router.post("/api/send-email", response_model=SendEmailResponse)
async def send_email(req: SendEmailRequest) -> SendEmailResponse:
    """
    Send the PBC xlsx as an email attachment.

    Requires RESEND_API_KEY and SENDER_FROM in environment / .env.
    """
    api_key    = os.getenv("RESEND_API_KEY", "")
    sender     = os.getenv("SENDER_FROM", "")

    if not api_key or api_key.startswith("re_..."):
        raise HTTPException(
            503,
            "Email dispatch is not configured. "
            "Set RESEND_API_KEY and SENDER_FROM in your .env file.",
        )

    try:
        import resend  # lazy import — only required when actually sending
    except ImportError:
        raise HTTPException(
            503,
            "resend package not installed. Run: pip install resend",
        )

    try:
        xlsx_bytes = base64.b64decode(req.xlsx_base64)
    except Exception as exc:
        raise HTTPException(400, f"Invalid xlsx_base64: {exc}") from exc

    body = req.message or (
        f"Dear Team,\n\n"
        f"Please find attached the PBC list for {req.client_name} — {req.audit_period}.\n\n"
        f"Kindly provide the requested evidence at your earliest convenience.\n\n"
        f"Thank you."
    )

    try:
        resend.api_key = api_key
        result = resend.Emails.send({
            "from":    sender,
            "to":      [req.to_email],
            "subject": f"PBC List — {req.client_name} {req.audit_period}",
            "text":    body,
            "attachments": [{
                "filename": req.filename,
                "content":  list(xlsx_bytes),
            }],
        })
        return SendEmailResponse(
            status     = "sent",
            to         = req.to_email,
            message_id = result.get("id"),
        )
    except Exception as exc:
        raise HTTPException(500, f"Resend API error: {exc}") from exc
