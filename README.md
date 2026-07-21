# IT Audit Intelligence Platform

AI-assisted IT audit workflow platform for annual ITGC planning, PBC generation, IT understanding mapping, and walkthrough coverage tracking.

## Live Website

**Project website:** https://weiyi-chen.github.io/it-audit-intelligence/

Direct demos:

- PBC Checklist Generator: https://weiyi-chen.github.io/it-audit-intelligence/pbc.html
- IT Understanding Map: https://weiyi-chen.github.io/it-audit-intelligence/it_understanding.html
- Walkthrough Tracker: https://weiyi-chen.github.io/it-audit-intelligence/audit_tracker.html

## Modules

- **Module A — PBC Checklist Generator**
  - Reads prior-year PBC Excel files.
  - Uses Claude or deterministic mock mode to detect current-year scope changes.
  - Retrieves effective approved audit guidance using metadata filters and BM25-style ranking.
  - Adds requirement-level citations and deterministic methodology updates to generated requests.
  - Generates a colour-coded current-year PBC workbook with `carried_over`, `updated`, `new`, and `removed` rows.
  - Supports synchronous generation and a checkpointed LangGraph human-review API.
  - Exposed through CLI, FastAPI, and the frontend demo.

- **Module B — IT Understanding Map**
  - Maps in-scope financial systems, business processes, stakeholders, vendors, data flows, and ITGC areas.
  - Includes an interactive IT landscape, system drill-down, stakeholder coverage map, and organisation chart.

- **Module C — Walkthrough Tracker**
  - Tracks stakeholder walkthrough questions, prior-year findings, new current-year questions, notes, and coverage progress.
  - Links from Module B with system / area / stakeholder context.

## Stack

- Python, FastAPI, LangGraph
- Anthropic Claude API with mock fallback
- BM25-based regulatory RAG with effective-date and metadata filtering
- SQLite audit history
- openpyxl for Excel read/write
- D3.js / static HTML frontend prototypes
- Railway-ready deployment config

## Module A Workflow

```text
Prior-year PBC workbook
        -> scope-change extraction
        -> approved-guidance retrieval
        -> checklist update and deterministic rules
        -> reviewer validation
        -> cited Excel output
```

The approved-guidance corpus is versioned in
`modules/pbc/regulatory_guidance.json`. Retrieval filters guidance by audit
period, jurisdiction, industry, and control area before applying BM25-style
ranking. The API and frontend expose the retrieved requirement ID, version,
citation, and retrieval score. Generated methodology-driven PBC items also
carry their source citation in the workbook notes.

This is currently a lexical RAG baseline. It does **not** claim dense
embeddings, a vector database, hybrid search, or automated ingestion of live
regulatory websites. Those are planned scale-out options once the corpus and
labelled retrieval evaluation set are large enough to demonstrate a measurable
benefit over BM25.

## Testing

```bash
pytest tests -q
```

The suite covers scope parsing, checklist decisions, template generation,
batch fallback behaviour, Excel round trips, graph behaviour, effective-date
filtering, guidance retrieval, citation propagation, and deterministic sample
size updates. The current suite has 155 passing tests.

## Quick Start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

Open:

- `http://localhost:8000/pbc.html`
- `http://localhost:8000/it_understanding.html`
- `http://localhost:8000/audit_tracker.html`

## CLI Demo

```bash
python demo_run.py
```

This runs Module A in mock mode if `ANTHROPIC_API_KEY` is not configured.
