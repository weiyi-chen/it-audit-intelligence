# Full-Stack Engineer Interview — Quick Reference (Cheat Sheet)

> Read this 5 minutes before the interview to refresh your memory on key points.

---

## 🎯 30-Second Pitch

"I built an **AI-powered IT audit platform** using LangGraph + FastAPI. It automates three high-touch audit workflows:
1. **PBC list generation** — goes from 4 hours to 30 minutes
2. **IT environment mapping** — goes from 2 days to 2 hours  
3. **Walkthrough coverage** — reduces control miss-rate from 12% to 3%

The system uses stateful AI workflows (LangGraph StateGraph), persistent state with interrupt/resume (human-in-the-loop), and measurable ROI ($75k/year across 50 engagements)."

---

## 🏗️ Architecture Cheat Sheet

```
┌─────────────────────────────────────────────┐
│             FastAPI Backend                 │
│  (handles requests, manages checkpointer)   │
└──────────────────┬──────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │   Unified State     │
        │   (TypedDict)       │
        └──────────┬──────────┘
                   │
        ┌──────────┴──────────────────────┐
        │                                 │
        ▼                                 ▼
    Module A                          Module B & C
    StateGraph                        StateGraph
    (PBC Gen)                         (Knowledge Map & Walkthrough)
    - 5 nodes                         - 3 nodes each
    - 2 conditional edges             - Reuse Module A output
    - 1 interrupt point               - RAG + LLM
```

**Key Decision Matrix:**

| What | Why | Alternative |
|------|-----|-------------|
| LangGraph | Cycles + persistent state + interrupt/resume | LCEL (no cycles), Celery (no LLM native) |
| Unified State | Downstream modules reuse upstream outputs | Separate State per module (data passing) |
| SQLite Checkpointer | Persist state between HTTP requests | In-memory (state lost on restart) |
| FastAPI | Secure credential storage + stateless HTTP | Direct graph invocation (no HTTP layer) |
| Task-level testing | No mocking; test contracts | Mocking Claude (too fragile) |

---

## 💻 Code Patterns to Know

### Pattern 1: Node Function (Reads + Updates State)

```python
def scope_diff_node(state: State) -> State:
    # Read from state
    prior_items = state["prior_year_items"]
    scope_text = state["current_year_scope_text"]
    
    # Call Claude
    changes = call_claude_for_scope_diff(prior_items, scope_text)
    
    # Return updated state subset (LangGraph merges it)
    return {"scope_changes": changes}
```

**Key point:** Node returns dict, LangGraph auto-merges into full state.

### Pattern 2: Conditional Routing

```python
def scope_diff_router(state: State) -> str:
    if state.get("scope_changes"):
        return "update_items_node"
    else:
        return "output_node"  # Skip update if no changes

g.add_conditional_edges(
    "scope_diff_node",
    scope_diff_router,
    {"update_items_node": "update_items_node", "output_node": "output_node"}
)
```

**Key point:** Router function decides next node based on state.

### Pattern 3: Interrupt + Resume

```python
# Inside review_node
def review_node(state: State) -> State:
    from langgraph.types import interrupt
    
    resume_value = interrupt("Awaiting review...")
    # Execution pauses here; state persists to DB
    
    approved = resume_value.get("approved")
    return {"review_passed": approved}

# In FastAPI handler (later)
from langgraph.types import Command

result = graph.invoke(
    Command(resume={"approved": True}),
    config={"configurable": {"thread_id": thread_id}}
)
# Graph resumes from interrupt() and continues
```

**Key point:** `interrupt()` pauses graph; `Command(resume=...)` resumes it.

### Pattern 4: Claude with Retry + Validation

```python
def call_claude_safe(prompt: str, schema: type, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model="claude-opus-4-7",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            text = response.content[0].text
            data = json.loads(text)
            # Validate schema
            schema.parse_obj(data)  # Pydantic validation
            return data
        except (json.JSONDecodeError, ValidationError):
            if attempt == max_retries - 1:
                raise
            # Retry with more explicit instruction
    return None
```

**Key point:** Parse JSON, validate, retry on failure.

### Pattern 5: Testing (Task-Level, No Mocks)

```python
def test_scope_diff_detects_new_system():
    state = default_state()
    state["current_year_scope_text"] = "SAP newly in scope..."
    state["prior_year_items"] = [...]
    
    result = scope_diff_node(state)
    
    assert any(
        c["change_type"] == "system_added" and "SAP" in c["description"]
        for c in result["scope_changes"]
    )
```

**Key point:** Test the node's input/output contract, not Claude's internals.

---

## 🎤 Answer Template for Common Q's

### "Why LangGraph?"

**Template:** "LangGraph is built for [**stateful, cyclic**] workflows. Module A has a [**rejection loop**]: review_node → update_items_node → review_node. LangGraph's [**StateGraph**] and [**conditional edges**] express this naturally. Plus, [**interrupt/resume**] for human-in-the-loop is natively supported via checkpointer."

**Alternatives to mention:** LCEL (stateless DAG, can't do cycles), Celery (no LLM native), simple orchestration (over-engineered).

### "How do you handle Claude's non-determinism?"

**Template:** "Three layers: [**retry logic**] (parse JSON, validate schema, retry on failure); [**task-level testing**] (no mocking; test contracts); [**golden dataset**] (10 hand-curated input/output pairs to catch regressions)."

### "What's the biggest gotcha?"

**Template:** "Checkpointer persistence. First time I tested interrupt/resume, I created a new `SqliteSaver()` in each HTTP handler, so resumed graphs couldn't find the saved state. Fix: cache the checkpointer instance and reuse across handlers."

### "How do you measure success?"

**Template:** "Three metrics: [**PBC time**] 4h → 30min (175h/year saved); [**IT understanding**] 2d → 2h (200h/year); [**control coverage**] 12% miss-rate → 3%. Total: $75k/year recovered capacity."

### "How would you scale to 500 engagements?"

**Template:** "Three changes: [**async**] wrap graph.invoke() in Celery/Redis for parallel runs; [**checkpointer**] swap SQLite → Postgres (supports concurrent writes); [**caching**] add Anthropic's prompt caching for duplicate memos."

---

## 📋 Key Files to Reference

| File | What | Interview Use |
|------|------|------------------|
| `core/state.py` | Unified State TypedDict (54 fields across 3 modules) | Show data model; explain why one State |
| `modules/pbc/graph.py` | StateGraph with 5 nodes, 2 conditional edges | Show the loop (rejection loop), conditional routing |
| `modules/pbc/nodes.py` | Node implementations (ingest, scope_diff, update, review, output) | Walk through one node (scope_diff is simplest) |
| `api/main.py` | FastAPI app, route registration | Show HTTP layer + checkpointer setup |
| `api/routes/pbc.py` | POST /api/pbc/generate handler | Show request → graph.invoke → response cycle |
| `api/routes/review.py` | POST /api/review/approve handler | Show Command(resume=...) for interrupt/resume |
| `tests/pbc/test_scope_diff.py` | Task-level test (no mocks) | Show testing approach |
| `data/golden/case_01/` | Golden dataset (input/output pair) | Show precision/recall validation |

---

## 🎬 Live Demo Sequence (10 minutes)

```
1. Open frontend (pbc.html)
   → "Here's the UI. Upload prior xlsx, paste scope memo."

2. Show request in DevTools
   → "POST /api/pbc/generate sends the state to FastAPI."

3. Show modules/pbc/graph.py
   → "Behind the scenes, this StateGraph runs."
   → Point to nodes: ingest → scope_diff → [router] → update/output → review → output → END
   → Point to rejection loop: review can go back to update

4. Show modules/pbc/nodes.py (focus on scope_diff_node)
   → "Here's one node. Read from state, call Claude, return updated state."

5. Show test (test_scope_diff.py)
   → "Task-level testing. No mocking. Given input X, does node produce valid output?"

6. Show golden dataset
   → "10 (input, expected_output) pairs. We run the full pipeline on each."

7. Show response in DevTools
   → "Graph finishes, returns xlsx_base64."
   → "Or, if paused at review_node, returns 'awaiting_review' + thread_id."

8. Optionally: trigger /api/review/approve endpoint
   → "User approves in browser, sends POST /api/review/approve/thread_id."
   → "Graph resumes from interrupt() and finishes."
```

---

## 🚨 Gotchas to Mention (If Asked)

1. **Checkpointer persistence:** "I initially created a new SqliteSaver() per request, which lost state between resume calls. Now I cache it."

2. **LLM token cost:** "Didn't track token usage until late. scope_diff_node uses ~400 tokens/audit. Should have measured from day one."

3. **Async/concurrency:** "Currently synchronous. For 500 engagements, would need async task queue (Celery) to avoid blocking HTTP requests."

4. **Prompt engineering:** "Claude's output quality is sensitive to examples in the prompt. Golden dataset tests catch when a prompt change causes regression."

5. **State schema evolution:** "If I add a new field to State (e.g., `new_field`), all code that reads old states from the database must handle missing `new_field`. No ORM-style migrations."

---

## ✅ Checklist Before Interview

- [ ] Understand **why LangGraph** (cycles + interrupt/resume + checkpointing)
- [ ] Know the **5 nodes in Module A** and their responsibilities
- [ ] Remember the **rejection loop** (review → update → review)
- [ ] Explain **interrupt/resume** (graph pauses, state persists, later resumed)
- [ ] Describe the **unified State** (one TypedDict for all 3 modules)
- [ ] Be ready for **"biggest gotcha"** (checkpointer persistence)
- [ ] Have **ROI numbers memorized** ($75k/year)
- [ ] Know **how to scale** (async, Postgres, prompt caching)
- [ ] Practice **live demo** (pbc.html → graph → response)
- [ ] Prepare **code snippets** (node function, routing, testing)

---

## 🎓 Last-Minute Tips

1. **Speak like a domain expert:** "As an auditor, I know this pain point..." (sets you apart from generic full-stack devs)

2. **Emphasize measurable ROI:** Not "cool AI system," but "freed up $75k/year in consultant capacity."

3. **Own your trade-offs:** "I chose SQLite for simplicity, not scalability. For 500 engagements, I'd switch to Postgres." (shows you've thought ahead)

4. **Test coverage:** "I use task-level testing, not mocking. The golden dataset gives me a precision/recall baseline." (demonstrates rigor)

5. **Deployment story:** "It's ready to deploy to Railway/Heroku. The FastAPI backend serves static files; the checkpointer uses SQLite in dev, Postgres in prod." (shows production readiness)

6. **If stuck on a question:** "That's a great question. Let me think... [pause]. What I'd do is [reasoning]. Any follow-ups?" (buys time, shows thinking)

---

## 📞 Common Follow-Up Questions (Prepare Answers)

Q: "How do you handle concurrent requests to the same graph?"
A: "Thread ID ensures each request has its own execution thread. LangGraph's checkpointer serializes state per thread_id, so concurrent requests don't interfere."

Q: "What if Claude returns partial JSON (cutoff at max_tokens)?"
A: "I increase `max_tokens` and retry. If it happens repeatedly, I split the task (e.g., ask Claude to analyze 10 items at a time, not 100)."

Q: "How do you version the State schema?"
A: "Currently, I don't. For production with many users, I'd add a schema_version field and migration logic. But for this 50-engagement MVP, it's premature."

Q: "What monitoring would you add in production?"
A: "Structured logging (Datadog): token usage, execution time by node, error rates, user satisfaction (feedback button)."

Q: "Why not use Langsmith for tracing?"
A: "Good idea. I'd integrate it for production to trace graph execution, see node latencies, and catch regressions."

---

## 🎬 Opening & Closing

**Opening (before technical deep-dive):**
"I'm excited to walk you through this project. It's a full-stack system—LangGraph for AI workflows, FastAPI for backend, SQLite for state persistence, and a simple frontend. I'll start with the architecture overview, then dive into specific code if you're interested."

**Closing (after Q&A):**
"This project taught me how to build domain-specific AI applications that are production-ready, measurable, and actually solve real problems. I'm eager to bring these skills to [company name]'s challenges."

---

## 🚀 You're Ready!

You understand:
- ✅ Why LangGraph (cycles + interrupt/resume)
- ✅ How State flows through modules
- ✅ Node responsibilities and testing
- ✅ FastAPI + checkpointer interaction
- ✅ ROI and measurable impact
- ✅ Common gotchas and trade-offs
- ✅ How to scale to 500 engagements

**Go crush the interview!** 🎤

