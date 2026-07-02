"""
GET /config.js
──────────────
Returns a tiny JS snippet that sets window.API_BASE.

When served from Railway, the frontend fetches this to discover the backend URL.
In local dev (files opened directly in browser), this endpoint isn't reached and
the fallback `http://localhost:8000` in pbc.html is used instead.
"""

from __future__ import annotations

import os
from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter()


@router.get("/config.js", include_in_schema=False)
async def config_js() -> Response:
    """
    Inject the backend URL into the frontend at runtime.
    Railway sets RAILWAY_PUBLIC_DOMAIN automatically.
    """
    railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
    if railway_domain:
        api_base = f"https://{railway_domain}"
    else:
        # Fallback for local dev (this endpoint is served by the same process)
        port = os.getenv("PORT", "8000")
        api_base = f"http://localhost:{port}"

    js = f"window.API_BASE = {repr(api_base)};\n"
    return Response(content=js, media_type="application/javascript")
