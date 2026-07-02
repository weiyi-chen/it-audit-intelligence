"""
demo_run.py — Module A end-to-end demo (no LangGraph dependency)

Directly chains the five PBC nodes without StateGraph so it works in any
Python environment that has openpyxl (and optionally anthropic).

Usage
─────
# Default demo — uses built-in sample data, mock LLM:
    python demo_run.py

# With your own prior xlsx and a real scope memo:
    python demo_run.py \\
        --prior  data/sample_client_FY2024/pbc_list.xlsx \\
        --scope  "FY2025: SAP S/4HANA newly in scope. UAR sample size raised to 40." \\
        --client "ACME Corp" \\
        --period FY2025

# Force real LLM (requires ANTHROPIC_API_KEY in .env):
    ANTHROPIC_API_KEY=sk-ant-... python demo_run.py --prior ... --scope ...
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import types

# ── langgraph stub (allows import without the package installed) ─────────────
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

# ── project imports ──────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(__file__))

from core.llm import has_real_key
from core.state import default_state
from modules.pbc.nodes import (
    ingest_node,
    scope_diff_node,
    update_items_node,
    review_node,
    output_node,
)

# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="IT Audit Intelligence — Module A Demo"
    )
    p.add_argument("--prior",  default="data/sample_client_FY2024/pbc_list.xlsx",
                   help="Prior-year PBC xlsx path")
    p.add_argument("--scope",  default="",
                   help="Current-year scope memo text (leave blank for built-in demo)")
    p.add_argument("--client", default="ACME Corp")
    p.add_argument("--period", default="FY2025")
    p.add_argument("--out",    default="",
                   help="Output xlsx path (default: data/output/<client>_<period>_pbc.xlsx)")
    return p.parse_args()


# ─────────────────────────────────────────────────────────────────────────────
# Pretty-print helpers
# ─────────────────────────────────────────────────────────────────────────────

W = 68

def banner(title: str) -> None:
    print("\n" + "═" * W)
    print(f"  {title}")
    print("═" * W)

def section(title: str) -> None:
    print(f"\n{'─' * W}")
    print(f"  {title}")
    print("─" * W)

def step(n: int, label: str) -> None:
    print(f"\n  [{n}/5] {label}…", flush=True)

def ok(msg: str) -> None:
    print(f"  ✅  {msg}")

def info(label: str, value: str) -> None:
    print(f"  {'':2}{label:<28}{value}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    scope_text = args.scope or (
        "FY2025 IT Audit Scope — ACME Corp\n\n"
        "1. SAP S/4HANA is newly in scope from 1 January 2025 following the ERP "
        "migration from Oracle EBS. All ITGC areas apply (JML, UAR, Change "
        "Management, Privileged Access, Backup).\n\n"
        "2. Oracle EBS remains in scope through FY2025 as legacy transactions "
        "continue to be processed in parallel.\n\n"
        "3. Per the FY2025 audit plan, UAR sample sizes have been increased from "
        "25 to 40 to align with the firm's updated sampling methodology.\n\n"
        "No other changes to scope."
    )

    out_path = args.out or os.path.join(
        "data", "output",
        f"{args.client.lower().replace(' ', '_')}_{args.period.lower()}_pbc.xlsx",
    )

    # ── header ───────────────────────────────────────────────────────────────
    banner("IT Audit Intelligence  —  Module A: PBC Checklist Generator")
    info("Client  :", args.client)
    info("Period  :", args.period)
    info("Prior PBC :", args.prior if os.path.exists(args.prior) else f"{args.prior}  ⚠️ not found")
    info("LLM mode :", "🟢 real (Anthropic API)" if has_real_key() else "🟡 mock (keyword-based)")
    info("Output  :", out_path)

    # ── build state ───────────────────────────────────────────────────────────
    state = default_state(
        client_name  = args.client,
        audit_period = args.period,
        thread_id    = "demo_run_001",
    )
    state["prior_year_pbc_path"]     = args.prior
    state["current_year_scope_text"] = scope_text
    state["pbc_output_xlsx_path"]    = out_path

    # ── node 1: ingest ────────────────────────────────────────────────────────
    section("Pipeline execution")
    t0 = time.time()

    step(1, "ingest_node  — reading prior-year PBC xlsx")
    state = {**state, **ingest_node(state)}
    n_prior = len(state.get("prior_year_items", []))
    ok(f"Loaded {n_prior} prior-year items")

    # ── node 2: scope_diff ────────────────────────────────────────────────────
    step(2, "scope_diff_node  — detecting scope changes")
    state = {**state, **scope_diff_node(state)}
    changes = state.get("scope_changes", [])
    ok(f"Detected {len(changes)} scope change(s)")
    for c in changes:
        print(f"       • [{c['change_type']}]  {c['description'][:70]}")

    # ── node 3: update_items ──────────────────────────────────────────────────
    if changes:
        step(3, "update_items_node  — applying decisions + generating new items")
    else:
        step(3, "update_items_node  — carrying all items forward (no scope changes)")
    state = {**state, **update_items_node(state)}
    items   = state.get("current_year_items", [])
    by_status: dict[str, int] = {}
    for i in items:
        s = i.get("status", "?")
        by_status[s] = by_status.get(s, 0) + 1
    ok(f"Produced {len(items)} current-year items:")
    for s in ("new", "updated", "carried_over", "removed"):
        if s in by_status:
            colour = {"new": "🟢", "updated": "🟡", "carried_over": "⬜", "removed": "🔴"}.get(s, "")
            print(f"       {colour}  {s:<20} {by_status[s]}")

    # ── node 4: review ────────────────────────────────────────────────────────
    step(4, "review_node  — auto-approving (Phase 4 will wire to UI interrupt)")
    state = {**state, **review_node(state)}
    ok("Review passed — proceeding to output")

    # ── node 5: output ────────────────────────────────────────────────────────
    step(5, "output_node  — writing colour-coded xlsx")
    state = {**state, **output_node(state)}
    elapsed = time.time() - t0

    # ── results ───────────────────────────────────────────────────────────────
    section("Results")
    final_path = state.get("pbc_output_xlsx_path", out_path)
    if os.path.exists(final_path):
        size_kb = os.path.getsize(final_path) / 1024
        ok(f"Output xlsx written: {final_path}  ({size_kb:.1f} KB)")
    else:
        print(f"  ⚠️  Output file not found at {final_path!r}")

    error = state.get("error", "")
    if error:
        print(f"\n  ⚠️  Error recorded: {error}")

    print(f"\n  Total wall time: {elapsed:.1f}s")
    print(f"\n{'═' * W}")
    print("  ✅  Module A completed successfully")
    print(f"{'═' * W}\n")

    # ── legend reminder ───────────────────────────────────────────────────────
    print("  Colour coding in the output xlsx:")
    print("    ⬜  carried_over — unchanged from prior year")
    print("    🟡  updated      — wording or scope revised")
    print("    🟢  new          — new item (added system / template)")
    print("    🔴  removed      — out of scope, kept for audit trail")
    print()


if __name__ == "__main__":
    main()
