"""
IT Audit Intelligence — FastAPI backend

Startup
───────
    uvicorn api.main:app --reload --port 8000

Endpoints
─────────
    GET  /health                → service status + LLM mode
    POST /api/pbc/generate      → run Module A, return xlsx base64
    POST /api/send-email        → dispatch xlsx via Resend
    GET  /api/pbc/history       → list recent runs (no blob)
    GET  /api/pbc/runs/{id}     → fetch run + xlsx base64
    DELETE /api/pbc/runs/{id}   → remove run from history

    GET  /                      → serves frontend/index.html (production)
    GET  /{page}.html           → serves frontend HTML files

CORS is open (allow_origins=["*"]) for local dev.
Tighten this in production.
"""

from __future__ import annotations

import os
import sys
import types

from dotenv import load_dotenv

# ── load .env before anything else ───────────────────────────────────────────
_ROOT = os.path.dirname(os.path.dirname(__file__))
load_dotenv(os.path.join(_ROOT, ".env"))

# ── langgraph stub ────────────────────────────────────────────────────────────
try:
    import langgraph  # noqa: F401
except ModuleNotFoundError:
    _fake = types.ModuleType("langgraph")
    _fake.graph = types.ModuleType("langgraph.graph")                           # type: ignore[attr-defined]
    _fake.graph.message = types.ModuleType("langgraph.graph.message")           # type: ignore[attr-defined]
    _fake.graph.message.add_messages = lambda x: x                              # type: ignore[attr-defined]
    sys.modules["langgraph"]               = _fake
    sys.modules["langgraph.graph"]         = _fake.graph                        # type: ignore[attr-defined]
    sys.modules["langgraph.graph.message"] = _fake.graph.message                # type: ignore[attr-defined]

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_FRONTEND_DIR = pathlib.Path(_ROOT) / "frontend"

import pathlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes.pbc     import router as pbc_router
from api.routes.email   import router as email_router
from api.routes.history import router as history_router
from api.routes.config  import router as config_router
from api.routes.review        import router as review_router
from api.routes.understanding import router as understanding_router
from api.schemas        import HealthResponse
from api.checkpointer  import checkpointer_info
from core.llm           import has_real_key

# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "IT Audit Intelligence API",
    description = "Module A — PBC Checklist Generator backend",
    version     = "0.1.0",
    docs_url    = "/docs",
    redoc_url   = "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],   # tighten for production
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

app.include_router(pbc_router)
app.include_router(email_router)
app.include_router(history_router)
app.include_router(config_router)
app.include_router(review_router)
app.include_router(understanding_router)

# ── serve frontend static files (for production/Railway) ─────────────────────
# In local dev you still open files directly or via `python -m http.server`.
# In production (Railway), everything is served from this single FastAPI process.
if _FRONTEND_DIR.is_dir():
    app.mount("/frontend", StaticFiles(directory=str(_FRONTEND_DIR)), name="frontend")

    @app.get("/", include_in_schema=False)
    async def root() -> FileResponse:
        return FileResponse(str(_FRONTEND_DIR / "index.html"))

    @app.get("/{page}", include_in_schema=False)
    async def page(page: str) -> FileResponse:
        target = _FRONTEND_DIR / page
        if target.suffix == "" :
            target = target.with_suffix(".html")
        if target.exists() and target.parent == _FRONTEND_DIR:
            return FileResponse(str(target))
        from fastapi import HTTPException as _HTTPException
        raise _HTTPException(404, f"Page not found: {page}")


# ─────────────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["meta"])
async def health() -> HealthResponse:
    """Service liveness + LLM mode indicator."""
    cp = checkpointer_info()
    return HealthResponse(
        status                = "ok",
        version               = "0.1.0",
        llm_mode              = "real" if has_real_key() else "mock",
        checkpointer          = cp["type"],
        checkpoint_persistent = cp["persistent"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Dev entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=True)
