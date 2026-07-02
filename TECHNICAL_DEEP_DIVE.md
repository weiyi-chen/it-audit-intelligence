# Technical Deep Dive — Full-Stack Explained

> For interviewers who want to see you understand *why* you made each choice, not just *what* you built.

---

## Part 1: State Management — Why Unified TypedDict?

### The Problem: Three Modules, One Data Source

Without unified state:
```python
# ✗ Naive approach: separate state per module
class PBCState:
    prior_items: List[PBCItem]
    current_items: List[PBCItem]
    scope_changes: List[ScopeChange]

class UnderstandingState:
    entities: List[ITEntity]
    relationships: List[EntityRelationship]

class WalkthroughState:
    topics: List[WalkthroughTopic]
    coverage: Dict[str, str]

# Problem: Data between modules must be manually passed
pbc_state = run_pbc_graph(pbc_input)
understanding_state = run_understanding_graph(
    evidence_paths=pbc_input["evidence_paths"],  # ← Manual passing
    client_name=pbc_input["client_name"]         # ← Manual passing
)
walkthrough_state = run_walkthrough_graph(
    topics=???  # Where do these come from?
    # No clear data source
)
```

With unified state:
```python
# ✓ Unified approach: one State, each module reads its slice
class State(TypedDict):
    # Shared
    client_name: str
    audit_period: str
    
    # Module A slice
    prior_year_items: List[PBCItem]
    current_year_items: List[PBCItem]
    scope_changes: List[ScopeChange]
    
    # Module B slice
    extracted_entities: List[ITEntity]
    entity_relationships: List[EntityRelationship]
    
    # Module C slice
    walkthrough_topics: List[WalkthroughTopic]
    current_topic_id: Optional[str]

# Module C directly uses Module B's output
def suggest_questions_node(state: State):
    # Read Module B's output
    entities = state["extracted_entities"]
    relationships = state["entity_relationships"]
    
    # Use as context for Claude
    context = render_knowledge_graph_context(entities, relationships)
    # ...
    return {"suggested_next_questions": [...]}
```

### The Trade-off

**Pro:**
- Downstream modules automatically see upstream outputs
- No manual data passing or orchestration
- Clear provenance: "where did this data come from?" → look at state history

**Con:**
- State is large (54 fields)
- TypedDict doesn't enforce required fields at runtime
  - Mitigation: `default_state()` factory function ensures all fields exist
- Schema evolution is tricky (if you add a field, old states from DB lack it)
  - Mitigation: use `state.get("new_field", default_value)`

### Code Example: Accessing State

```python
# In any node, you can access any field:
def some_node(state: State) -> State:
    # Read from Module A output
    items = state["current_year_items"]  # ← from Module A
    
    # Read from Module B output
    entities = state["extracted_entities"]  # ← from Module B
    
    # Use both
    context = f"Items: {items}. Entities: {entities}."
    result = claude.messages.create(..., messages=[...])
    
    # Update your module's slice only
    return {"suggested_next_questions": [...]}
```

---

## Part 2: LangGraph StateGraph — Why Conditional Edges?

### The Problem: Complex Workflows with Decisions

Workflow for Module A:
```
ingest → scope_diff → [decision] → update or output? → review → [decision] → output or loop?
```

LCEL can't express this:
```python
# ✗ LCEL is stateless and linear
chain = (
    ingest_runnable
    | scope_diff_runnable
    # ← Can't conditionally skip update_runnable based on scope_changes
    | update_runnable
    | review_runnable
    # ← Can't loop back on rejection
    | output_runnable
)
result = chain.invoke(input_data)
```

LangGraph can:
```python
# ✓ LangGraph StateGraph with conditional edges
g = StateGraph(State)

g.add_node("ingest_node", ingest_node)
g.add_node("scope_diff_node", scope_diff_node)
g.add_node("update_items_node", update_items_node)
g.add_node("review_node", review_node)
g.add_node("output_node", output_node)

g.set_entry_point("ingest_node")
g.add_edge("ingest_node", "scope_diff_node")
g.add_edge("update_items_node", "review_node")
g.add_edge("output_node", END)

# Conditional edges: router functions return target node name
g.add_conditional_edges(
    "scope_diff_node",
    scope_diff_router,  # Returns "update_items_node" or "output_node"
    {
        "update_items_node": "update_items_node",
        "output_node": "output_node",
    },
)

g.add_conditional_edges(
    "review_node",
    review_router,  # Returns "output_node" or "update_items_node" (rejection loop)
    {
        "output_node": "output_node",
        "update_items_node": "update_items_node",
    },
)

compiled = g.compile()
result = compiled.invoke(state)
```

### Code Example: Router Function

```python
def scope_diff_router(state: State) -> str:
    """
    Conditional routing: if scope has changes, update items.
    Otherwise, carry forward prior items unchanged.
    
    This is a **state-dependent** decision that LCEL can't express.
    """
    
    scope_changes = state.get("scope_changes", [])
    
    # Business logic: no changes → no need to update
    if not scope_changes:
        # Skip update_items entirely; go straight to output
        return "output_node"
    
    # Has changes → need to regenerate items
    return "update_items_node"
```

### Why This Matters

1. **Rejection loop:** Auditor rejects PBC list → goes back to update_items → gets reviewed again → loop until approved.
   - LCEL: would need custom orchestration code to re-invoke nodes
   - LangGraph: `add_conditional_edges` handles it natively

2. **Conditional skipping:** If scope unchanged, skip update_items entirely.
   - LCEL: would execute update_items with empty scope_changes, wasting LLM calls
   - LangGraph: router decides, saving compute

3. **Interrupt/resume:** review_node calls `interrupt()`, pauses execution.
   - LCEL: no built-in support; you'd have to implement checkpointing yourself
   - LangGraph: `SqliteSaver` checkpointer handles it

---

## Part 3: Interrupt/Resume — State Persistence Across HTTP Requests

### The Challenge

```
Request 1 (HTTP):
  generate_pbc(prior_pbc_path, scope_text)
  → graph.invoke(state)
  → Pauses at review_node, calls interrupt()
  → HTTP returns: {"status": "awaiting_review", "thread_id": "abc-fy25"}

[User goes to browser, clicks "Approve"]

Request 2 (HTTP):
  approve_review(thread_id="abc-fy25", approved=True)
  → graph.invoke(Command(resume={approved: True}))
  → ??? How does the graph remember the state from Request 1?
```

### The Solution: Checkpointer

```python
# Setup (once, in FastAPI app startup)
from langgraph.checkpoint.sqlite import SqliteSaver

checkpointer = SqliteSaver("checkpoints.db")

def build_compiled_graph(checkpointer):
    g = StateGraph(State)
    # ... add nodes, edges ...
    compiled = g.compile(checkpointer=checkpointer)  # ← Attach checkpointer
    return compiled

# Request 1: First invocation
graph = build_compiled_graph(checkpointer)
config = {"configurable": {"thread_id": "abc-fy25"}}

try:
    result = graph.invoke(initial_state, config)
except GraphInterrupt:
    # Execution paused at interrupt()
    # LangGraph automatically saves state to checkpointer
    # checkpoints.db now has a row: {thread_id: "abc-fy25", state: {...}}
    return {"status": "awaiting_review", "thread_id": "abc-fy25"}

# Request 2: Resume
graph = build_compiled_graph(checkpointer)  # Same checkpointer instance!
config = {"configurable": {"thread_id": "abc-fy25"}}  # Same thread_id!

result = graph.invoke(
    Command(resume={"approved": True}),
    config
)
# LangGraph retrieves saved state from checkpointer
# Continues execution from the interrupt() point
# Finishes normally and returns final state
```

### What's Inside `checkpoints.db`

```sql
-- SQLite schema (simplified)
CREATE TABLE checkpoints (
    thread_id TEXT,
    checkpoint_id TEXT,
    checkpoint_ns TEXT,
    values JSON,  -- The full State dict
    metadata JSON,
    created_at TIMESTAMP,
    PRIMARY KEY (thread_id, checkpoint_id)
);

-- Example row:
INSERT INTO checkpoints VALUES (
    'abc-fy25',
    'checkpoint_abc123',
    'default',
    '{
        "client_name": "ABC Corp",
        "prior_year_items": [...],
        "scope_changes": [...],
        "current_year_items": [...],
        "review_passed": false,
        ...
    }',
    '...',
    '2025-05-19 14:32:00'
);
```

### Code Example: Review Node with Interrupt

```python
def review_node(state: State) -> State:
    """
    Pause execution and wait for human review.
    """
    from langgraph.types import interrupt
    
    # Prepare a summary for the auditor
    summary = render_pbc_summary(state["current_year_items"])
    
    # Pause execution
    # This saves the current state to checkpointer
    resume_value = interrupt(f"Review the PBC list:\n{summary}")
    
    # Execution does NOT continue past this point
    # Instead, HTTP handler returns immediately
    # [User goes to browser, approves/rejects]
    # [Later HTTP request calls graph.invoke(Command(resume=...))]
    # [Execution resumes HERE]
    
    # Now we have the user's decision
    approved = resume_value.get("approved")
    notes = resume_value.get("notes")
    
    return {
        "review_passed": approved,
        # ...audit notes...
    }
```

### Why This Is Better Than Polling

**Bad approach (polling):**
```python
# Client polls the server
def check_status(thread_id):
    result = db.query(f"SELECT status FROM runs WHERE thread_id={thread_id}")
    if result["status"] == "awaiting_review":
        return {"status": "awaiting_review"}  # Still waiting...
    elif result["status"] == "complete":
        return {"status": "complete", "xlsx": "..."}

# Client: "Is it done yet?" (poll every 2 seconds)
for i in range(100):
    status = check_status("abc-fy25")
    if status["status"] == "complete":
        break
    sleep(2)  # Inefficient
```

**Good approach (interrupt/resume):**
```python
# Client initiates graph, graph pauses immediately
result = graph.invoke(state, config)
# Returns immediately (no waiting in graph)

# Client submits review form
graph.invoke(Command(resume={...}), config)
# Graph resumes from paused state
# No polling, no wasted requests
```

---

## Part 4: Testing Without Mocking Claude

### The Problem with Mocking

```python
# ✗ Mock approach (fragile)
from unittest.mock import patch

@patch("anthropic.Anthropic.messages.create")
def test_scope_diff_node(mock_claude):
    mock_claude.return_value = MagicMock(
        content=[MagicMock(text='[{"change_type": "system_added", ...}]')]
    )
    
    result = scope_diff_node(state)
    assert result["scope_changes"][0]["change_type"] == "system_added"

# Problem: if Claude's actual behavior changes, this test still passes!
# You're testing your mock, not Claude.
```

### The Solution: Task-Level Testing

```python
# ✓ Task-level testing (robust)
def test_scope_diff_detects_new_system():
    """
    Task: Given a scope memo mentioning SAP, 
    scope_diff_node should return a ScopeChange with change_type="system_added".
    
    This is an **input/output contract test**:
    - We provide realistic input (a real scope memo mentioning SAP)
    - We call the real node (which calls the real Claude)
    - We assert the output has the expected structure
    
    If Claude breaks, this test breaks. That's the point!
    """
    
    state = default_state()
    state["current_year_scope_text"] = """
    FY2025 Audit Scope:
    - Legacy systems: Oracle EBS (finance), AD (identity)
    - NEW: SAP S/4HANA implemented January 2025
    - Scope includes all systems processing financial data
    """
    state["prior_year_items"] = [
        {
            "item_id": "JML-001",
            "category": "ITGC - JML",
            "description": "Joiner/mover/leaver controls",
            "in_scope": True,
            "period": "FY2024",
            "sample_size": "25",
            "status": "carried_over",
            "last_year_id": None,
            "notes": "",
        }
    ]
    
    # Call the REAL node, which calls the REAL Claude
    result = scope_diff_node(state)
    
    # Assertions: is the structure valid?
    assert "scope_changes" in result
    changes = result["scope_changes"]
    assert isinstance(changes, list)
    
    # Assertion: did Claude detect SAP as system_added?
    sap_change = next(
        (c for c in changes 
         if c["change_type"] == "system_added" and "SAP" in c["description"]),
        None
    )
    assert sap_change is not None, "Should detect SAP as new system"
    assert "ITGC - JML" in sap_change["affected_categories"]
```

### The Golden Dataset: Precision/Recall Baseline

```python
# data/golden/case_01/
# ├── input_prior_pbc.xlsx
# ├── input_scope_memo.txt
# └── expected_current_pbc.xlsx

def test_precision_recall_on_golden_dataset():
    """
    For each of 10 hand-curated golden cases:
    1. Run Module A (ingest → scope_diff → update → output)
    2. Compare output.xlsx to expected.xlsx
    3. Compute precision/recall on scope change detection
    """
    
    golden_cases = [
        ("case_01", "SAP added, UAR sample size change"),
        ("case_02", "No changes, carry-forward entire list"),
        ("case_03", "System removed, Oracle decommissioned"),
        # ... 7 more cases ...
    ]
    
    for case_id, description in golden_cases:
        print(f"Testing {case_id}: {description}")
        
        # Load inputs
        prior_xlsx = read_xlsx(f"data/golden/{case_id}/input_prior_pbc.xlsx")
        scope_memo = read_text(f"data/golden/{case_id}/input_scope_memo.txt")
        expected_xlsx = read_xlsx(f"data/golden/{case_id}/expected_current_pbc.xlsx")
        
        # Run full pipeline
        state = default_state()
        state["prior_year_items"] = parse_xlsx(prior_xlsx)
        state["current_year_scope_text"] = scope_memo
        
        graph = build_pbc_graph().compile()
        result = graph.invoke(state)
        
        actual_xlsx = parse_xlsx(result["pbc_output_xlsx_path"])
        
        # Compare
        expected_changes = identify_scope_changes(expected_xlsx, prior_xlsx)
        actual_changes = result["scope_changes"]
        
        # Precision: of the changes we detected, how many are correct?
        correct = sum(
            1 for c in actual_changes
            if any(
                e["change_type"] == c["change_type"] and
                e["description"] in c["description"]
                for e in expected_changes
            )
        )
        precision = correct / len(actual_changes) if actual_changes else 1.0
        
        # Recall: of the true changes, how many did we detect?
        detected = sum(
            1 for e in expected_changes
            if any(
                c["change_type"] == e["change_type"] and
                e["description"] in c["description"]
                for c in actual_changes
            )
        )
        recall = detected / len(expected_changes) if expected_changes else 1.0
        
        print(f"  Precision: {precision:.2%}")
        print(f"  Recall: {recall:.2%}")
        
        assert precision >= 0.9, f"Precision too low: {precision}"
        assert recall >= 0.9, f"Recall too low: {recall}"

# Output:
# Testing case_01: SAP added, UAR sample size change
#   Precision: 100%
#   Recall: 100%
# Testing case_02: No changes, carry-forward entire list
#   Precision: 100%
#   Recall: 100%
# ...
# Summary: 10/10 cases passed ✓
```

### Why This Approach Works

1. **Catches real regressions:** If you change a prompt, the golden dataset tests immediately show impact.
2. **Quantifies quality:** Precision/recall gives you a baseline. "Is 90% recall good enough?" (Answer: depends on audit risk.)
3. **No mocking:** You're testing Claude's actual behavior, not your mock.
4. **Repeatable:** Golden dataset is version-controlled. Same input always produces same expected output.

---

## Part 5: FastAPI + Checkpointer Integration

### The Full Request/Response Cycle

```python
# routes/pbc.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from langgraph.types import GraphInterrupt, Command

router = APIRouter()

class GeneratePBCRequest(BaseModel):
    client_name: str
    audit_period: str
    prior_year_pbc_path: str
    current_year_scope_text: str

class GeneratePBCResponse(BaseModel):
    status: str  # "complete" or "awaiting_review"
    xlsx_base64: Optional[str] = None
    thread_id: Optional[str] = None
    filename: Optional[str] = None

@router.post("/api/pbc/generate")
async def generate_pbc(req: GeneratePBCRequest) -> GeneratePBCResponse:
    """
    Full-stack flow:
    1. Create initial state from request
    2. Build and compile graph with checkpointer
    3. Invoke graph
    4. Handle interrupt (paused at review_node)
    5. Return response
    """
    
    try:
        # ── Step 1: Validate input ──────────────────────────────
        if not os.path.exists(req.prior_year_pbc_path):
            raise HTTPException(400, f"File not found: {req.prior_year_pbc_path}")
        
        if len(req.current_year_scope_text.strip()) < 10:
            raise HTTPException(400, "Scope text too short (min 10 chars)")
        
        # ── Step 2: Create state ────────────────────────────────
        state = default_state(
            client_name=req.client_name,
            audit_period=req.audit_period,
            thread_id=f"{req.client_name}_{req.audit_period}",
        )
        
        state["prior_year_pbc_path"] = req.prior_year_pbc_path
        state["current_year_scope_text"] = req.current_year_scope_text
        
        # ── Step 3: Build graph ────────────────────────────────
        from modules.pbc.graph import build_compiled_graph
        from api.checkpointer import get_checkpointer
        
        checkpointer = get_checkpointer()  # Singleton
        graph = build_compiled_graph(checkpointer=checkpointer)
        
        # ── Step 4: Invoke graph ───────────────────────────────
        config = {
            "configurable": {
                "thread_id": state["thread_id"]
            }
        }
        
        try:
            result = graph.invoke(state, config)
            
            # Graph completed without interrupt
            return GeneratePBCResponse(
                status="complete",
                xlsx_base64=result["pbc_output_xlsx_b64"],
                filename=f"{req.client_name}_{req.audit_period}_pbc.xlsx",
            )
        
        except GraphInterrupt as e:
            # Graph paused at review_node
            # State is automatically saved by checkpointer
            
            # Also save run metadata to database for history
            from api.database import save_run
            save_run(
                thread_id=state["thread_id"],
                client_name=req.client_name,
                audit_period=req.audit_period,
                status="awaiting_review",
                state_snapshot=result,  # Partial state at interrupt
            )
            
            return GeneratePBCResponse(
                status="awaiting_review",
                thread_id=state["thread_id"],
            )
    
    except Exception as e:
        logger.error(f"Error in generate_pbc: {e}", exc_info=True)
        raise HTTPException(500, f"Internal error: {str(e)}")


class ReviewRequest(BaseModel):
    approved: bool
    notes: Optional[str] = None

@router.post("/api/review/approve/{thread_id}")
async def approve_review(thread_id: str, req: ReviewRequest) -> GeneratePBCResponse:
    """
    Resume interrupted graph.
    """
    
    try:
        # ── Step 1: Retrieve run from database ──────────────────
        from api.database import get_run
        run = get_run(thread_id)
        
        if not run or run["status"] != "awaiting_review":
            raise HTTPException(404, f"Run not found or already completed: {thread_id}")
        
        # ── Step 2: Resume graph ────────────────────────────────
        from modules.pbc.graph import build_compiled_graph
        from api.checkpointer import get_checkpointer
        
        checkpointer = get_checkpointer()  # SAME checkpointer instance
        graph = build_compiled_graph(checkpointer=checkpointer)
        
        config = {
            "configurable": {
                "thread_id": thread_id  # SAME thread_id
            }
        }
        
        # Resume with user's decision
        resume_value = {
            "approved": req.approved,
            "notes": req.notes or "",
        }
        
        result = graph.invoke(
            Command(resume=resume_value),
            config
        )
        
        # ── Step 3: Update database ────────────────────────────
        from api.database import update_run
        update_run(
            thread_id=thread_id,
            status="complete",
            result=result,
        )
        
        # ── Step 4: Return response ────────────────────────────
        return GeneratePBCResponse(
            status="complete",
            xlsx_base64=result["pbc_output_xlsx_b64"],
            filename=f"{run['client_name']}_{run['audit_period']}_pbc.xlsx",
        )
    
    except Exception as e:
        logger.error(f"Error in approve_review: {e}", exc_info=True)
        raise HTTPException(500, f"Internal error: {str(e)}")
```

### Checkpointer Setup

```python
# api/checkpointer.py

from langgraph.checkpoint.sqlite import SqliteSaver
import os
from functools import lru_cache

# Path to persistent database
CHECKPOINT_DB = os.getenv("CHECKPOINT_DB", "checkpoints.db")

@lru_cache(maxsize=1)
def get_checkpointer():
    """
    Return a singleton SqliteSaver instance.
    
    The checkpointer persists graph state to checkpoints.db.
    Every graph invocation (whether new or resumed) uses the same
    checkpointer instance, ensuring state can be retrieved.
    """
    return SqliteSaver(CHECKPOINT_DB)
```

---

## Part 6: Why Token Counting Matters

```python
# Prompt for scope_diff_node

SCOPE_DIFF_PROMPT = """
You are an IT audit expert analyzing scope changes.

**Prior Year PBC Items:**
{items_json}

**Current Year Scope Memo:**
{scope_text}

**Your Task:**
...
"""

# For a typical client:
# - prior_year_items: 50-100 items → ~5000 characters → ~1250 tokens
# - scope_text: 500-1000 words → ~400-800 tokens
# - Prompt template: ~200 tokens
# Total input: ~1850 tokens

# Claude response: "change_type", "description", "affected_categories" → ~150 tokens
# Total: ~2000 tokens per scope_diff call

# Per engagement: 1 call
# Per 50 engagements/year: 50 calls → 100k tokens → ~$1.50 (assuming $0.015/K tokens)

# This is cheap! (compared to consultant time saved)
# But if you change the prompt to add more examples (e.g., "provide confidence scores"),
# you might add 500 tokens/call → $7.50/year. Over 500 engagements: $75. Worth it?

# Answer: Measure token usage to make informed trade-offs.
```

---

## Part 7: Production Deployment

### Single-Process (Current)

```
FastAPI app (gunicorn/uvicorn)
  ├── /api/pbc/generate → build_compiled_graph() → graph.invoke()
  ├── /api/review/approve → build_compiled_graph() → graph.invoke(Command(resume=...))
  └── checkpointer (SqliteSaver) ← shared across requests
        └── checkpoints.db (SQLite, single file)
```

**Limitation:** Single file, not concurrent.
**Fix:** SQLite allows concurrent reads, but writes block. For 10 concurrent requests, acceptable. For 100+, need Postgres.

### Multi-Process (Scaled)

```
Load Balancer (nginx)
  ├── API Instance 1 (FastAPI)
  │   └── checkpointer → PostgresCheckpointer(db)
  ├── API Instance 2 (FastAPI)
  │   └── checkpointer → PostgresCheckpointer(db)
  └── API Instance 3 (FastAPI)
      └── checkpointer → PostgresCheckpointer(db)
        ↓
    PostgreSQL (shared)
      └── checkpoints table (concurrent writes supported)
```

**Code change:**
```python
# api/checkpointer.py (multi-process version)

from langgraph.checkpoint.postgres import PostgresCheckpointer
import os

@lru_cache(maxsize=1)
def get_checkpointer():
    """Use Postgres for concurrent access."""
    conn_string = os.getenv("DATABASE_URL")  # postgresql://...
    return PostgresCheckpointer(conn_string)
```

---

## Part 8: Error Handling Edge Cases

### What If Claude Returns Invalid JSON?

```python
def scope_diff_node(state: State) -> State:
    """Handle Claude returning non-JSON."""
    
    for attempt in range(3):
        try:
            response = client.messages.create(...)
            text = response.content[0].text
            data = json.loads(text)  # May raise JSONDecodeError
            
            # Validate schema
            for change in data:
                assert "change_type" in change
                assert "description" in change
                assert "affected_categories" in change
            
            return {"scope_changes": data}
        
        except (json.JSONDecodeError, AssertionError, KeyError) as e:
            if attempt == 2:
                # Last attempt failed; give up
                state["error"] = f"Failed to parse Claude response: {text[:200]}"
                return {"scope_changes": [], "error": state["error"]}
            
            # Retry with more explicit prompt
            # (Anthropic SDK will retry; we just continue loop)
```

### What If Claude Hallucinates?

```python
def update_items_node(state: State) -> State:
    """Handle Claude changing item descriptions incorrectly."""
    
    updated_items = []
    
    for item in state["prior_year_items"]:
        decision = call_claude_for_decision(item, state["scope_changes"])
        
        if decision == "update":
            # Claude provided new description; validate it
            new_description = decision.get("new_description")
            
            # Sanity check: new description should be similar in length
            # and should mention the system name
            if len(new_description) < 10 or len(new_description) > 1000:
                # Suspicious; skip update
                decision = "carry_over"
            
            # Check: does new description contain system/control names?
            system_name = extract_system_name(item["category"])
            if system_name.lower() not in new_description.lower():
                # Hallucination detected; skip
                decision = "carry_over"
        
        # ... rest of logic ...
```

### What If Graph Crashes Mid-Execution?

```python
# Checkpointer handles this!
# If graph.invoke() crashes after some nodes have run,
# the state is still persisted in checkpoints.db at the last
# successful node.

# On retry, you can:
# 1. Resume from last checkpoint (pick up where you left off)
# 2. Or, delete the checkpoint and restart fresh

# Example:
if some_error_occurred:
    # Option 1: Resume
    result = graph.invoke(
        Command(resume=...),  # Resume from last checkpoint
        config
    )
    
    # Option 2: Restart
    from api.checkpointer import get_checkpointer
    checkpointer = get_checkpointer()
    checkpointer.delete(thread_id)  # Clear checkpoint
    
    # Re-run from scratch
    result = graph.invoke(
        initial_state,
        config  # Same thread_id, but no checkpoint to resume
    )
```

---

## Summary: Why This Architecture Wins

| Aspect | Approach | Benefit |
|--------|----------|---------|
| **State** | Unified TypedDict | No manual passing between modules; downstream reuses upstream |
| **Workflow** | LangGraph StateGraph | Cycles + conditional routing natively; not hacky |
| **Persistence** | SqliteSaver checkpointer | Interrupt/resume works across HTTP requests |
| **Testing** | Task-level (no mocking) | Catches real Claude behavior changes |
| **Baseline** | Golden dataset (precision/recall) | Quantifies quality, catches regressions |
| **API** | FastAPI + async/await | Non-blocking, scalable, secure credential storage |
| **Scaling** | AsyncIO + Postgres | Multi-instance support; concurrent writes |

This is **production-ready architecture**, not a prototype.

