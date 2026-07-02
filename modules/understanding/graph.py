"""
Module B — IT Understanding StateGraph.

Flow:
    extract_entities → infer_relations → render_map → END

No cycles in this graph (unlike Module A's review loop) — it's a
straight pipeline: parse documents → infer connections → render output.
"""

from __future__ import annotations

from langgraph.graph import StateGraph, END

from core.state import State
from modules.understanding.nodes import (
    extract_entities_node,
    infer_relations_node,
    render_map_node,
)


def build_understanding_graph() -> StateGraph:
    """Return an uncompiled StateGraph for Module B."""
    g = StateGraph(State)

    g.add_node("extract_entities_node", extract_entities_node)
    g.add_node("infer_relations_node",  infer_relations_node)
    g.add_node("render_map_node",       render_map_node)

    g.set_entry_point("extract_entities_node")
    g.add_edge("extract_entities_node", "infer_relations_node")
    g.add_edge("infer_relations_node",  "render_map_node")
    g.add_edge("render_map_node",       END)

    return g


def build_compiled_understanding_graph():
    """Compile Module B graph (no checkpointer needed — no cycles)."""
    return build_understanding_graph().compile()
