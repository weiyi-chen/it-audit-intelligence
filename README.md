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
  - Generates a colour-coded current-year PBC workbook with `carried_over`, `updated`, `new`, and `removed` rows.
  - Exposed through CLI, FastAPI, and frontend demo.

- **Module B — IT Understanding Map**
  - Maps in-scope financial systems, business processes, stakeholders, vendors, data flows, and ITGC areas.
  - Includes an interactive IT landscape, system drill-down, stakeholder coverage map, and organisation chart.

- **Module C — Walkthrough Tracker**
  - Tracks stakeholder walkthrough questions, prior-year findings, new current-year questions, notes, and coverage progress.
  - Links from Module B with system / area / stakeholder context.

## Stack

- Python, FastAPI, LangGraph
- Anthropic Claude API with mock fallback
- SQLite audit history
- openpyxl for Excel read/write
- D3.js / static HTML frontend prototypes
- Railway-ready deployment config

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
