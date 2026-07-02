"""
Module A — CLI entry point (Phase 2)

Usage
─────
# Dry-run with built-in defaults (no xlsx required):
    python run_pbc.py

# Full run with a prior-year xlsx and scope memo:
    python run_pbc.py \\
        --prior  data/sample_client_FY2024/pbc_list.xlsx \\
        --scope  "FY2025 audit scope: SAP S/4HANA newly in scope. UAR sample size raised to 40." \\
        --client "ACME Corp" \\
        --period FY2025

# Write output to a specific path:
    python run_pbc.py --prior ... --scope ... --out /tmp/acme_pbc_fy2025.xlsx
"""

from __future__ import annotations

import argparse
import os
import sys

from core.llm import has_real_key
from core.state import default_state
from modules.pbc.graph import build_pbc_graph


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="IT Audit Intelligence — Module A: PBC Checklist Generator"
    )
    p.add_argument("--prior",  default="", help="Path to prior-year PBC xlsx")
    p.add_argument("--scope",  default="", help="Current-year scope memo text")
    p.add_argument("--client", default="ACME Corp", help="Client name")
    p.add_argument("--period", default="FY2025",    help="Audit period, e.g. FY2025")
    p.add_argument("--out",    default="",
                   help="Output xlsx path (default: data/output/<client>_<period>_pbc.xlsx)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print("=" * 65)
    print("  IT Audit Intelligence — Module A: PBC Checklist Generator")
    print("=" * 65)
    print(f"  Client   : {args.client}")
    print(f"  Period   : {args.period}")
    print(f"  Prior PBC: {args.prior or '(none — starting fresh)'}")
    print(f"  LLM mode : {'🟢 real (Anthropic API)' if has_real_key() else '🟡 mock (no API key)'}")
    print()

    # ── compile graph ────────────────────────────────────────────────────────
    graph = build_pbc_graph()
    app   = graph.compile()
    print("✅ Graph compiled successfully")

    nodes = list(graph.nodes.keys())
    print(f"   Nodes ({len(nodes)}): {', '.join(nodes)}\n")

    # ── build initial state ──────────────────────────────────────────────────
    scope_text = args.scope or (
        "FY2025 audit scope: SAP S/4HANA is newly in scope starting January 2025. "
        "Oracle EBS remains in scope. UAR sample size raised to 40 per updated audit plan."
    )

    initial = default_state(
        client_name  = args.client,
        audit_period = args.period,
        thread_id    = "cli_run_001",
    )
    initial["prior_year_pbc_path"]     = args.prior
    initial["current_year_scope_text"] = scope_text
    if args.out:
        initial["pbc_output_xlsx_path"] = args.out

    # ── run ──────────────────────────────────────────────────────────────────
    print("─" * 65)
    print("Running graph…")
    print("─" * 65)

    final = app.invoke(initial)

    # ── results ──────────────────────────────────────────────────────────────
    print()
    print("─" * 65)
    print("RESULTS")
    print("─" * 65)

    out_path = final.get("pbc_output_xlsx_path", "")
    n_items  = len(final.get("current_year_items", []))
    changes  = final.get("scope_changes", [])
    error    = final.get("error", "")

    if error:
        print(f"  ⚠️  Error recorded: {error}")

    print(f"  Scope changes detected : {len(changes)}")
    for c in changes:
        print(f"    • [{c['change_type']}] {c['description']}")

    print(f"  Current-year items     : {n_items}")

    if out_path and os.path.exists(out_path):
        print(f"  Output xlsx            : {out_path}")
        print(f"\n✅ Module A completed successfully")
    elif out_path:
        print(f"  ⚠️  Output path set but file not found: {out_path}")
    else:
        print("  ⚠️  No output xlsx path recorded (output_node may have failed)")


if __name__ == "__main__":
    main()
