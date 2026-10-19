"""Environment-driven application settings shared across API routes."""

from __future__ import annotations

import os


def public_demo_enabled() -> bool:
    return os.getenv("PUBLIC_DEMO", "false").strip().lower() in {"1", "true", "yes", "on"}
