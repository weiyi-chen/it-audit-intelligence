"""
Module A — StateGraph

Flow:
                    ┌──────────────┐
                    │   ingest     │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │ scope_diff   │
                    └──────┬───────┘
                           │
              ┌────────────┴───────────┐
              │ scope_diff_router      │
              │  changes? → update     │
              │  no chg? → output      │
              └────────────┬───────────┘
                           │
                    ┌──────▼───────┐
              ┌────►│ update_items │
              │     └──────┬───────┘
              │            │
              │     ┌──────▼───────┐
              │     │   review     │
              │     └──────┬───────┘
              │            │
              │     ┌──────┴────────┐
              │     │ review_router │
              └─────┤ rejected → loop
                    │ passed → output
                    └──────┬────────┘
                           │
                    ┌──────▼───────┐
                    │   output     │
                    └──────┬───────┘
                           │
                          END
"""

from __future__ import annotations

from typing import Any, Optional

from langgraph.graph import StateGraph, END

from core.state import State
from modules.pbc.nodes import (
    ingest_node,
    scope_diff_node,
    retrieve_regulatory_guidance_node,
    update_items_node,
    review_node,
    output_node,
)


# ─── conditional routers ────────────────────────────────────────────────

def scope_diff_router(state: State) -> str:
    """If no scope changes detected, skip the update step entirely —
    the prior year list carries forward as-is."""
    return (
        "update_items_node"
        if state.get("scope_changes") or state.get("regulatory_guidance")
        else "output_node"
    )


def review_router(state: State) -> str:
    """After review_node: output if approved, else loop back to update."""
    return "output_node" if state.get("review_passed") else "update_items_node"


# ─── graph builder ──────────────────────────────────────────────────────

def build_pbc_graph() -> StateGraph:
    """Return an *uncompiled* StateGraph for Module A.

    Caller is responsible for `.compile()` (and optionally attaching a
    checkpointer). Returning the uncompiled graph keeps test surface
    flexible — tests can inspect node/edge structure before compiling.
    """
    g = StateGraph(State)

    # nodes
    g.add_node("ingest_node",       ingest_node)
    g.add_node("scope_diff_node",   scope_diff_node)
    g.add_node(
        "retrieve_regulatory_guidance_node",
        retrieve_regulatory_guidance_node,
    )
    g.add_node("update_items_node", update_items_node)
    g.add_node("review_node",       review_node)
    g.add_node("output_node",       output_node)

    # entry
    g.set_entry_point("ingest_node")

    # linear edges
    g.add_edge("ingest_node",       "scope_diff_node")
    g.add_edge("scope_diff_node", "retrieve_regulatory_guidance_node")
    g.add_edge("update_items_node", "review_node")
    g.add_edge("output_node",       END)

    # conditional edges
    g.add_conditional_edges(
        "retrieve_regulatory_guidance_node",
        scope_diff_router,
        {
            "update_items_node": "update_items_node",
            "output_node":       "output_node",
        },
    )
    g.add_conditional_edges(
        "review_node",
        review_router,
        {
            "output_node":       "output_node",
            "update_items_node": "update_items_node",   # rejection loop
        },
    )

    return g


def build_compiled_graph(checkpointer: Optional[Any] = None):
    """
    Compile the Module A graph with an optional checkpointer.

    This is the entry point for the async review flow.  Passing a checkpointer
    enables LangGraph's interrupt/resume — the graph can be paused at
    review_node, serialised to storage, and resumed from a different HTTP
    request (or even a different process if using SqliteSaver/PostgresSaver).

    Usage
    ─────
        from api.checkpointer import get_checkpointer
        app = build_compiled_graph(get_checkpointer())

        # First call — runs until interrupt() inside review_node
        config = {"configurable": {"thread_id": "eng-001-fy25"}}
        result = app.invoke(initial_state, config)
        # result["__interrupt__"] is present if paused

        # Resume — approve
        from langgraph.types import Command
        final = app.invoke(Command(resume={"approved": True}), config)

        # Resume — reject with notes
        revised = app.invoke(
            Command(resume={"approved": False, "notes": "add JML items for SAP"}),
            config,
        )
        # graph loops back through update_items_node → review_node (pauses again)

    Without checkpointer
    ────────────────────
    The graph compiles and runs fine; interrupt() is a no-op and review_node
    auto-approves.  This is the existing /api/pbc/generate behaviour.
    """
    graph = build_pbc_graph()
    if checkpointer is not None:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()
