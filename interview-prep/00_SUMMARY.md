# IT Audit Intelligence Platform — Interview Summary (1-2 pages)

## 🎯 30-Second Pitch

"I built an **AI-powered IT audit platform** (LangGraph + FastAPI) that automates three high-touch audit workflows:
- **PBC list generation**: 4 hours → 30 minutes
- **IT environment mapping**: 2 days → 2 hours  
- **Walkthrough coverage**: 12% miss-rate → 3%

**ROI**: $75k/year in freed consultant capacity (50 engagements/year)"

---

## 🏗️ Architecture (5 min)

### Three Modules, One State
```
┌──────────────────────────────────────┐
│   Unified State (TypedDict)          │
│   - Module A: PBC items + xlsx       │
│   - Module B: Entities + relationships
│   - Module C: Topics + coverage      │
└──────────────────────────────────────┘
       ↑              ↑              ↑
       │              │              │
   Module A       Module B        Module C
  StateGraph    StateGraph      StateGraph
  5 nodes, 2    Entity extract   RAG +
  conditional   Relation infer   agent loop
  edges,        Visualize
  rejection
  loop
```

### Why LangGraph (NOT LCEL)?
- **Cycles**: Rejection loop (review → update → review)
- **Conditional routing**: Skip update_items if no scope changes
- **Interrupt/Resume**: review_node pauses, HTTP resumes later
- **Persistent state**: SqliteSaver checkpointer (state survives HTTP requests)

LCEL is stateless, linear DAG. Can't express cycles or persistence natively.

---

## 💻 Key Code Patterns

### Pattern 1: Node Function
```python
def scope_diff_node(state: State) -> State:
    prior_items = state["prior_year_items"]
    scope_text = state["current_year_scope_text"]
    
    changes = call_claude(prior_items, scope_text)  # LLM call
    
    return {"scope_changes": changes}  # LangGraph merges this
```

### Pattern 2: Conditional Routing
```python
def scope_diff_router(state: State) -> str:
    if state.get("scope_changes"):
        return "update_items_node"  # Has changes → update
    else:
        return "output_node"        # No changes → skip
```

### Pattern 3: Interrupt/Resume
```python
# Inside review_node
def review_node(state: State) -> State:
    resume_value = interrupt("Awaiting review...")  # Pauses here
    approved = resume_value.get("approved")
    return {"review_passed": approved}

# Later, HTTP POST /api/review/approve/{thread_id}
result = graph.invoke(
    Command(resume={"approved": True}),
    config={"configurable": {"thread_id": thread_id}}
)  # Resumes from interrupt()
```

---

## 🧪 Testing & Quality

### Task-Level Testing (NO MOCKING)
```python
def test_scope_diff_detects_new_system():
    state = default_state()
    state["current_year_scope_text"] = "SAP newly in scope..."
    result = scope_diff_node(state)  # Calls REAL Claude
    
    assert any(
        c["change_type"] == "system_added" and "SAP" in c["description"]
        for c in result["scope_changes"]
    )
```

**Why**: Tests Claude's actual behavior, not mocks. If Claude breaks, test breaks (good!).

### Golden Dataset (Precision/Recall)
- 10 hand-curated (input, expected_output) pairs
- Run full pipeline on each
- Measure: "Did we detect all scope changes?" (recall)
- Measure: "Did we avoid false positives?" (precision)
- Baseline: 90%+ on both metrics

---

## 📊 Module A Flow (Detailed)

```
1. ingest_node
   Read prior_year.xlsx → prior_year_items

2. scope_diff_node
   Claude: "What changed between last year and scope memo?"
   Output: scope_changes (new systems, period changes, etc.)

3. [Router Decision]
   if scope_changes → go to update_items_node
   else             → skip to output_node

4. update_items_node
   For each prior item: Claude decides "keep/update/remove"
   For each scope change: Generate new items from templates
   Output: current_year_items (with status flags)

5. review_node
   INTERRUPT: Persist state to DB, return to HTTP
   [User approves/rejects in browser]
   HTTP resumes: graph.invoke(Command(resume=...))

6. [Router Decision]
   if approved → output_node
   else        → update_items_node (rejection loop!)

7. output_node
   Write current_year_items → xlsx
   Encode → Base64 (for HTTP download)
```

---

## 🎤 Top 5 Interview Questions (Quick Answers)

### Q1: Why LangGraph?
**A**: "Three reasons: (1) Cycles—rejection loop requires going back to earlier nodes; (2) Conditional routing—skip update_items if no scope changes; (3) Interrupt/resume—review_node pauses, state persists to DB, later HTTP request resumes. LCEL is stateless, can't do any of this."

### Q2: How handle Claude non-determinism?
**A**: "Retry logic + validation. Parse JSON, validate schema. If invalid, retry with explicit instruction. Task-level tests (no mocking) catch real regressions. Golden dataset gives precision/recall baseline—if a prompt change breaks quality, we see it immediately."

### Q3: Biggest gotcha?
**A**: "Checkpointer persistence. First time I tested interrupt/resume, I created new SqliteSaver() each HTTP request, so resumed graphs couldn't find saved state. Fix: cache checkpointer instance, reuse across handlers."

### Q4: How measure success?
**A**: "Three metrics: (1) PBC time 4h → 30min (saves 175h/year); (2) IT understanding 2d → 2h (saves 200h/year); (3) Control coverage 12% miss → 3% miss. Total: $75k/year recovered capacity across 50 engagements."

### Q5: Scale to 500 engagements?
**A**: "Three changes: (1) Async—wrap graph.invoke() in Celery/Redis for parallel; (2) Checkpointer—swap SQLite → PostgreSQL (concurrent writes); (3) Caching—Anthropic's prompt caching for duplicate memos."

---

## 📁 File Structure

```
interview-prep/
├── 00_SUMMARY.md              ← You are here (print this!)
├── INTERVIEW_CHEATSHEET.md    ← 30-sec answers & patterns
├── INTERVIEW_GUIDE.md         ← Full 2-hour walkthrough
├── TECHNICAL_DEEP_DIVE.md     ← Deep: State, LangGraph, testing, checkpointer
└── PROJECT_ARCHITECTURE_CN.md ← Chinese (self-study)
```

**What to read before interview:**
1. This file (SUMMARY) — 5 min
2. INTERVIEW_CHEATSHEET — 10 min (memorize Q&A)
3. INTERVIEW_GUIDE — 20 min (full context)

**What to reference during:**
- INTERVIEW_CHEATSHEET (quick Q&A lookup)

**Deep dives after interview:**
- TECHNICAL_DEEP_DIVE (if you want to truly master it)

---

## ✅ Pre-Interview Checklist

- [ ] Memorize 30-second pitch
- [ ] Know why LangGraph (cycles + interrupt/resume + checkpoint)
- [ ] Remember ROI: $75k/year
- [ ] Understand rejection loop (review → update → review)
- [ ] Know Node pattern: read state, call Claude, return dict
- [ ] Know Router pattern: return target node name based on state
- [ ] Know Interrupt pattern: `interrupt()` + `Command(resume=...)`
- [ ] Know testing: task-level (no mocks) + golden dataset precision/recall
- [ ] Practice live demo: show graph.py, one node, test
- [ ] Prepare for "biggest gotcha" answer

---

## 🎬 Live Demo (10 min)

```
1. Open pbc.html → "This is the UI. Upload prior xlsx, paste scope memo."
2. Show DevTools → "POST /api/pbc/generate request"
3. Show modules/pbc/graph.py → "5 nodes, 2 conditional edges"
4. Point to rejection loop → "review_node routes to update_items_node on rejection"
5. Show one node code → "Read state, call Claude, return dict"
6. Show test → "Task-level, no mocking. Given X, expect Y."
7. Show DevTools response → "Returns xlsx_base64 or 'awaiting_review'"
8. Optional: trigger /api/review/approve → "Resume from interrupt()"
```

---

## 🚀 Closing Statement

"This project demonstrates full-stack maturity: domain expertise (IT audit background), systematic architecture (LangGraph for cycles, FastAPI for stateless HTTP, unified State), practical engineering (golden dataset for quality, task-level testing, no over-engineering), and measurable impact ($75k/year ROI). The code is production-ready, tested, and deployed."

---

**Print this page. Read it 5 minutes before interview. You're ready.** 🎤

