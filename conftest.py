"""
Root-level conftest.py — applied before any test collection.

Patches out langgraph so the test suite runs in environments where it is
not installed (e.g. CI, the Cowork sandbox).  The real langgraph package
(installed in the project venv) takes priority when present.
"""

import sys
import types


def _patch_langgraph_if_missing() -> None:
    try:
        import langgraph  # noqa: F401 — already installed, nothing to do
    except ModuleNotFoundError:
        fake_lg = types.ModuleType("langgraph")
        fake_lg.graph = types.ModuleType("langgraph.graph")  # type: ignore[attr-defined]
        fake_lg.graph.message = types.ModuleType("langgraph.graph.message")  # type: ignore[attr-defined]
        fake_lg.graph.message.add_messages = lambda x: x  # type: ignore[attr-defined]
        sys.modules["langgraph"]              = fake_lg
        sys.modules["langgraph.graph"]        = fake_lg.graph  # type: ignore[attr-defined]
        sys.modules["langgraph.graph.message"] = fake_lg.graph.message  # type: ignore[attr-defined]


_patch_langgraph_if_missing()
