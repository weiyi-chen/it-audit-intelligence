"""Versioned methodology retrieval for Module A.

This is intentionally a small, dependency-free retrieval layer. Approved
guidance is stored as structured JSON and ranked with BM25-style lexical
scoring after effective-date and metadata filtering. It gives the PBC pipeline
grounded context and citations without treating an open-web result as an
authoritative audit requirement.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable


_CORPUS_PATH = Path(__file__).with_name("regulatory_guidance.json")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class RetrievalQuery:
    text: str
    audit_period: str
    jurisdiction: str = "*"
    industry: str = "*"
    control_areas: tuple[str, ...] = ()
    top_k: int = 5


def load_guidance(path: Path = _CORPUS_PATH) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        records = json.load(handle)
    if not isinstance(records, list):
        raise ValueError("Regulatory guidance corpus must contain a JSON array")
    return [record for record in records if isinstance(record, dict)]


def retrieve_guidance(
    query: RetrievalQuery,
    *,
    records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return effective, applicable guidance ranked by lexical relevance.

    Mandatory discovery requirements are included even when their lexical score
    is low. This is a governance rule, not an LLM decision.
    """
    corpus = records if records is not None else load_guidance()
    effective_on = _period_end(query.audit_period)
    candidates = [
        record for record in corpus
        if _is_effective(record, effective_on)
        and _metadata_matches(record, query.jurisdiction, query.industry)
        and _control_matches(record, query.control_areas)
    ]
    if not candidates:
        return []

    query_tokens = _tokens(query.text)
    document_tokens = [_tokens(_searchable_text(record)) for record in candidates]
    document_frequency: dict[str, int] = {}
    for tokens in document_tokens:
        for token in set(tokens):
            document_frequency[token] = document_frequency.get(token, 0) + 1

    ranked: list[tuple[float, dict[str, Any]]] = []
    average_length = sum(map(len, document_tokens)) / max(len(document_tokens), 1)
    for record, tokens in zip(candidates, document_tokens):
        score = _bm25_score(
            query_tokens,
            tokens,
            document_frequency,
            document_count=len(candidates),
            average_length=average_length,
        )
        if record.get("mandatory_discovery"):
            score += 100.0
        if score > 0:
            ranked.append((score, record))

    ranked.sort(key=lambda pair: (-pair[0], pair[1].get("requirement_id", "")))
    return [
        {
            **record,
            "retrieval_score": round(score, 4),
            "citation": _citation(record),
        }
        for score, record in ranked[: query.top_k]
    ]


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _searchable_text(record: dict[str, Any]) -> str:
    values: Iterable[Any] = (
        record.get("title", ""),
        record.get("content", ""),
        " ".join(record.get("topics", [])),
        " ".join(record.get("control_areas", [])),
    )
    return " ".join(str(value) for value in values)


def _bm25_score(
    query_tokens: list[str],
    document_tokens: list[str],
    document_frequency: dict[str, int],
    *,
    document_count: int,
    average_length: float,
) -> float:
    if not query_tokens or not document_tokens:
        return 0.0
    frequencies: dict[str, int] = {}
    for token in document_tokens:
        frequencies[token] = frequencies.get(token, 0) + 1
    k1, b = 1.5, 0.75
    score = 0.0
    for token in set(query_tokens):
        tf = frequencies.get(token, 0)
        if not tf:
            continue
        df = document_frequency.get(token, 0)
        idf = math.log(1 + (document_count - df + 0.5) / (df + 0.5))
        denominator = tf + k1 * (
            1 - b + b * len(document_tokens) / max(average_length, 1)
        )
        score += idf * (tf * (k1 + 1)) / denominator
    return score


def _period_end(audit_period: str) -> date:
    match = re.search(r"(20\d{2})", audit_period)
    year = int(match.group(1)) if match else date.today().year
    return date(year, 12, 31)


def _is_effective(record: dict[str, Any], effective_on: date) -> bool:
    start = date.fromisoformat(record["effective_from"])
    end_value = record.get("effective_to")
    end = date.fromisoformat(end_value) if end_value else None
    return start <= effective_on and (end is None or effective_on <= end)


def _metadata_matches(
    record: dict[str, Any],
    jurisdiction: str,
    industry: str,
) -> bool:
    jurisdictions = record.get("jurisdictions", ["*"])
    industries = record.get("industries", ["*"])
    return (
        ("*" in jurisdictions or jurisdiction in jurisdictions)
        and ("*" in industries or industry in industries)
    )


def _control_matches(
    record: dict[str, Any],
    control_areas: tuple[str, ...],
) -> bool:
    if not control_areas or record.get("mandatory_discovery"):
        return True
    record_areas = set(record.get("control_areas", []))
    return bool(record_areas.intersection(control_areas))


def _citation(record: dict[str, Any]) -> str:
    return (
        f"{record.get('source', 'Approved guidance')} "
        f"{record.get('version', '')}, {record.get('requirement_id', '')}"
    ).strip(", ")
