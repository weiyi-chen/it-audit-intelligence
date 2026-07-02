"""
Shared LLM interface for the IT Audit Intelligence Platform.

Design goals
────────────
* Single call surface: call_claude(prompt, *, system, model, max_tokens) → str
* Transparent mock: when ANTHROPIC_API_KEY is absent or still set to the
  placeholder value the entire pipeline runs with deterministic fake responses
  so tests / demos work without burning API credits.
* Mock routing is keyword-based — patterns must stay in sync with the
  prompt templates used in modules/pbc/nodes.py.
* Real calls use the official Anthropic SDK imported lazily (not imported
  at module level) so the module can be imported even when the anthropic
  package isn't installed in lightweight test environments.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

# The placeholder value written into .env.example / .env by default.
_PLACEHOLDER_KEY = "sk-ant-..."


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def call_claude(
    prompt: str,
    *,
    system: str = "",
    model: str = "claude-sonnet-4-6",
    max_tokens: int = 4096,
) -> str:
    """
    Call Claude and return the raw text response.

    Falls back to a deterministic mock when no real API key is configured.

    Parameters
    ----------
    prompt     : user-turn message content
    system     : optional system prompt
    model      : Anthropic model string
    max_tokens : hard cap on output tokens

    Returns
    -------
    str — model text (or mock text)
    """
    if _has_real_key():
        return _real_call(prompt, system=system, model=model, max_tokens=max_tokens)
    return _mock_call(prompt)


def has_real_key() -> bool:
    """True when a non-placeholder ANTHROPIC_API_KEY is present in the env."""
    return _has_real_key()


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _has_real_key() -> bool:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    return bool(key) and key != _PLACEHOLDER_KEY


def _real_call(
    prompt: str,
    *,
    system: str,
    model: str,
    max_tokens: int,
) -> str:
    """Make a live call to the Anthropic Messages API."""
    import anthropic  # lazy — only needed when a real key exists

    client = anthropic.Anthropic()  # picks up ANTHROPIC_API_KEY automatically
    kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system

    response = client.messages.create(**kwargs)
    return "".join(
        block.text for block in response.content if hasattr(block, "text")
    )


# ─────────────────────────────────────────────────────────────────────────────
# Mock responses (no API key required)
# ─────────────────────────────────────────────────────────────────────────────

def _mock_call(prompt: str) -> str:
    """
    Return a deterministic mock response shaped to match what each node
    expects, routing purely by keywords found in the prompt.
    """
    p = prompt.lower()

    # ── scope_diff_node ───────────────────────────────────────────────────
    # Prompt contains "scope change" or ("identify" + "change" + "scope")
    if _matches_scope_diff(p):
        return _mock_scope_diff(prompt)

    # ── update_items_node ─────────────────────────────────────────────────
    # Prompt asks for a keep/update/remove decision per item
    if _matches_update_items(p):
        return _mock_update_items(prompt)

    # Fallback — empty array is safe for any JSON-parsing caller
    return json.dumps([])


def _matches_scope_diff(p: str) -> bool:
    return (
        ("scope change" in p)
        or ("list of scope changes" in p)
        or ("identify" in p and "scope" in p and "change" in p)
        or ("extract" in p and "scope" in p)
    )


def _matches_update_items(p: str) -> bool:
    return (
        ("keep" in p and "update" in p and "remove" in p)
        or ("decision" in p and "item_id" in p)
        or ("carried_over" in p or "pbc item" in p)
    )


def _mock_scope_diff(prompt: str) -> str:
    """
    Inspect the scope text embedded in the prompt and return a plausible
    list of ScopeChange objects.  Falls back to a single generic change so
    the downstream nodes always have something to work with.
    """
    changes: list[dict[str, Any]] = []

    p_lower = prompt.lower()

    # Detect "system added" hints
    # Patterns match the system name BEFORE optional "is" + "newly/now in scope".
    # Group 1 stops at the boundary word; trailing " is" is stripped afterward.
    # Capture group starts with a letter so list-item numbers ("1. SAP") are excluded.
    # Use [ \t] (not \s) to avoid crossing newlines into adjacent lines.
    added_patterns = [
        r"([A-Za-z][A-Za-z0-9 /\-\.]*?)(?:[ \t]+is)?[ \t]+(?:newly|now)[ \t]+in[ \t]+scope",
        r"added[:\s]+([A-Za-z][A-Za-z0-9 /\-\.]*?)[ \t]+(?:to|in)[ \t]+scope",
        r"new[ \t]+system[:\s]+([A-Za-z][A-Za-z0-9 /\-\.]*)",
    ]
    for pat in added_patterns:
        # Search original prompt (IGNORECASE) to preserve exact source casing
        # e.g. "SAP S/4HANA" rather than the .title() mangling "Sap S/4Hana"
        m = re.search(pat, prompt, flags=re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            raw = re.sub(r"[ \t]+is$", "", raw, flags=re.IGNORECASE).strip()
            sys_name = raw  # keep the casing exactly as written in the scope text
            changes.append({
                "change_type": "system_added",
                "description": f"{sys_name} newly in scope",
                "affected_categories": [
                    "IT Systems Understanding",
                    "ITGC - JML",
                    "ITGC - UAR",
                    "ITGC - PrivAccess",
                    "ITGC - ChangeMgmt",
                ],
            })
            break

    # Detect "system removed" hints
    if "removed" in p_lower or "out of scope" in p_lower or "decommission" in p_lower:
        changes.append({
            "change_type": "system_removed",
            "description": "A legacy system has been removed from scope",
            "affected_categories": ["IT Systems Understanding"],
        })

    # Detect sample size changes
    if "sample size" in p_lower or "sample" in p_lower and "raised" in p_lower:
        changes.append({
            "change_type": "sample_size_change",
            "description": "Sample size requirements updated per current audit plan",
            "affected_categories": ["ITGC - UAR", "ITGC - JML"],
        })

    # Detect period changes
    if "period" in p_lower and ("change" in p_lower or "extend" in p_lower):
        changes.append({
            "change_type": "period_change",
            "description": "Audit period has changed",
            "affected_categories": [
                "IT Systems Understanding",
                "ITGC - JML",
                "ITGC - UAR",
            ],
        })

    # If nothing detected but the prompt doesn't say "no change", add a
    # generic placeholder so downstream nodes are exercised.
    if not changes and "no change" not in p_lower and "same as" not in p_lower:
        changes.append({
            "change_type": "system_added",
            "description": "SAP S/4HANA newly in scope (mock default)",
            "affected_categories": [
                "IT Systems Understanding",
                "ITGC - JML",
                "ITGC - UAR",
                "ITGC - PrivAccess",
            ],
        })

    return json.dumps(changes)


def _mock_update_items(prompt: str) -> str:
    """
    Extract item_ids from the prompt JSON and return a keep/update/remove
    decision for each.  The mock keeps the first 80 % and marks the rest
    for update — purely so the output xlsx has visual variety.
    """
    ids: list[str] = re.findall(r'"item_id"\s*:\s*"([^"]+)"', prompt)

    if not ids:
        return json.dumps([])

    decisions: list[dict[str, Any]] = []
    for idx, item_id in enumerate(ids):
        # Give every 5th item an "updated" decision for colour variety
        if (idx + 1) % 5 == 0:
            decisions.append({
                "item_id": item_id,
                "decision": "update",
                "updated_description": (
                    f"[UPDATED] Please provide the requested evidence for "
                    f"the current audit period — updated per scope review."
                ),
                "notes": "Mock: minor wording refresh to align with current period",
            })
        else:
            decisions.append({
                "item_id": item_id,
                "decision": "keep",
                "updated_description": None,
                "notes": "Mock: no change required",
            })

    return json.dumps(decisions)
