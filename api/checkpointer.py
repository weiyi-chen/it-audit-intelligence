"""
Shared LangGraph checkpointer for the IT Audit Intelligence platform.

Checkpointer hierarchy (swap by changing one line in production):
─────────────────────────────────────────────────────────────────
  Development  →  MemorySaver      (built-in, process-lifetime)
  Staging/Prod →  SqliteSaver      (pip install langgraph-checkpoint-sqlite)
  Scale-out    →  PostgresSaver    (pip install langgraph-checkpoint-postgres)

Why this matters
────────────────
The checkpointer is what makes LangGraph's human-in-the-loop possible:

1. graph.invoke(state, config) runs until interrupt() is hit
2. Checkpointer snapshots the *entire* graph state to storage
3. Process can restart; state is NOT lost
4. graph.invoke(Command(resume=decision), config) loads the snapshot and resumes

Without a checkpointer compile() still works but state lives only in RAM —
interrupted graphs are lost on process restart (fine for demos, not prod).
"""

from __future__ import annotations

import os
from pathlib import Path

# ── try SqliteSaver first (needs: pip install langgraph-checkpoint-sqlite) ────
_checkpointer = None

try:
    from langgraph.checkpoint.sqlite import SqliteSaver  # type: ignore[import]

    _ROOT = Path(__file__).resolve().parent.parent
    _CP_DB = Path(os.getenv("CHECKPOINT_DB", str(_ROOT / "checkpoints.db")))
    _checkpointer = SqliteSaver.from_conn_string(str(_CP_DB))
    _CHECKPOINTER_TYPE = "sqlite"

except ImportError:
    # Fallback: MemorySaver (always available, process-lifetime only)
    from langgraph.checkpoint.memory import MemorySaver

    _checkpointer = MemorySaver()
    _CHECKPOINTER_TYPE = "memory"


def get_checkpointer():
    """Return the singleton checkpointer instance."""
    return _checkpointer


def checkpointer_info() -> dict:
    return {
        "type": _CHECKPOINTER_TYPE,
        "persistent": _CHECKPOINTER_TYPE != "memory",
        "note": (
            "Install langgraph-checkpoint-sqlite for persistent checkpoints"
            if _CHECKPOINTER_TYPE == "memory"
            else "Checkpoints persist across restarts"
        ),
    }
