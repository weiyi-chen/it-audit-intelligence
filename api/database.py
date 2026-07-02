"""
SQLite storage layer for IT Audit Intelligence.

Schema
──────
    runs
    ────
    id           INTEGER  PRIMARY KEY AUTOINCREMENT
    client_name  TEXT     NOT NULL
    audit_period TEXT     NOT NULL
    scope_text   TEXT
    item_count   INTEGER
    llm_mode     TEXT
    elapsed_secs REAL
    xlsx_bytes   BLOB     -- raw xlsx binary
    xlsx_filename TEXT
    scope_changes_json TEXT  -- JSON array of ScopeChange dicts
    status_breakdown_json TEXT  -- JSON dict
    created_at   TEXT     DEFAULT (datetime('now'))

Usage
─────
    from api.database import db

    run_id = db.save_run(...)
    rows   = db.list_runs(limit=20)
    run    = db.get_run(run_id)
"""

from __future__ import annotations

import base64
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── DB file lives next to the project root ────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
_DB_PATH = Path(os.getenv("AUDIT_DB", str(_ROOT / "audit_history.db")))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id                    INTEGER PRIMARY KEY AUTOINCREMENT,
                client_name           TEXT    NOT NULL,
                audit_period          TEXT    NOT NULL,
                scope_text            TEXT,
                item_count            INTEGER,
                llm_mode              TEXT,
                elapsed_secs          REAL,
                xlsx_bytes            BLOB,
                xlsx_filename         TEXT,
                scope_changes_json    TEXT,
                status_breakdown_json TEXT,
                created_at            TEXT    DEFAULT (datetime('now'))
            )
        """)


# ── init on import ────────────────────────────────────────────────────────────
_init_db()


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

class AuditDatabase:
    """Thin wrapper around the SQLite audit history store."""

    # ── writes ────────────────────────────────────────────────────────────────

    def save_run(
        self,
        *,
        client_name: str,
        audit_period: str,
        scope_text: str,
        item_count: int,
        llm_mode: str,
        elapsed_secs: float,
        xlsx_base64: str,
        xlsx_filename: str,
        scope_changes: List[Dict[str, Any]],
        status_breakdown: Dict[str, int],
    ) -> int:
        """Persist one pipeline run. Returns the new run ID."""
        xlsx_bytes = base64.b64decode(xlsx_base64)
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO runs
                    (client_name, audit_period, scope_text, item_count,
                     llm_mode, elapsed_secs, xlsx_bytes, xlsx_filename,
                     scope_changes_json, status_breakdown_json)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    client_name,
                    audit_period,
                    scope_text,
                    item_count,
                    llm_mode,
                    elapsed_secs,
                    xlsx_bytes,
                    xlsx_filename,
                    json.dumps(scope_changes),
                    json.dumps(status_breakdown),
                ),
            )
            return cur.lastrowid  # type: ignore[return-value]

    # ── reads ─────────────────────────────────────────────────────────────────

    def list_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Return summary rows (no xlsx blob) ordered newest-first.
        """
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, client_name, audit_period, item_count,
                       llm_mode, elapsed_secs, xlsx_filename,
                       scope_changes_json, status_breakdown_json, created_at
                FROM runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_summary(r) for r in rows]

    def get_run(self, run_id: int) -> Optional[Dict[str, Any]]:
        """
        Return full run including xlsx as base64.
        Returns None if not found.
        """
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        d = _row_to_summary(row)
        d["xlsx_base64"] = base64.b64encode(row["xlsx_bytes"]).decode()
        return d

    def delete_run(self, run_id: int) -> bool:
        """Delete a run. Returns True if a row was deleted."""
        with _connect() as conn:
            cur = conn.execute("DELETE FROM runs WHERE id = ?", (run_id,))
            return cur.rowcount > 0


# ── helpers ───────────────────────────────────────────────────────────────────

def _row_to_summary(row: sqlite3.Row) -> Dict[str, Any]:
    keys = row.keys()
    d: Dict[str, Any] = {}
    for k in keys:
        if k in ("xlsx_bytes",):
            continue  # never include raw blob in summary
        v = row[k]
        if k in ("scope_changes_json", "status_breakdown_json") and v:
            d[k.replace("_json", "")] = json.loads(v)
        else:
            d[k] = v
    return d


# ── singleton ─────────────────────────────────────────────────────────────────
db = AuditDatabase()
