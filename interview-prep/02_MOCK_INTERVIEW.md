# 模拟面试 — 真实问答练习

> 我会模拟面试官，问你真实的 Full-Stack Engineer 面试问题。每个问题后面是标准答案。你应该：
> 1. 先自己回答（覆盖纸，想清楚）
> 2. 然后看标准答案
> 3. 改进你的回答

---

## 面试 1：开场（5 分钟）

### 面试官："Tell me about your most recent full-stack project."

#### 你的答案应该包含：
- [ ] 项目名称和域名（IT Audit Intelligence）
- [ ] 问题陈述（为什么要做这个）
- [ ] 你的角色（一个人全栈开发）
- [ ] 关键技术（LangGraph, FastAPI, React/vanilla JS）
- [ ] 可衡量的结果（ROI，时间节省）

#### 标准答案（2 分钟）：

"I built **IT Audit Intelligence**, a full-stack platform that automates IT auditors' annual workflows. Let me give you the context first:

**The Problem:** Every year, IT auditors spend:
- 4 hours manually regenerating a 'Provided By Client' evidence checklist (Excel)
- 2 days reading scattered documents to understand the client's IT environment
- Lots of time during fieldwork remembering all the control questions they should ask

**My Solution:** A three-module AI system:
1. **Module A (PBC Generator)**: Automates checklist regeneration. Takes last year's xlsx + this year's scope memo → Claude analyzes scope changes → generates new xlsx in 30 minutes (was 4 hours)
2. **Module B (IT Understanding)**: Extracts entities (systems, people, vendors) and relationships from evidence files → generates interactive knowledge graph (2 hours instead of 2 days)
3. **Module C (Walkthrough Assistant)**: During fieldwork, RAG retrieves context + Claude suggests cross-cutting questions → auditor logs answers → coverage tracker updates

**Tech Stack:**
- Backend: Python, FastAPI (REST API), LangGraph (stateful AI workflows)
- Frontend: HTML5 + vanilla JavaScript (simple, no framework needed)
- Database: SQLite (dev), PostgreSQL (prod)
- LLM: Anthropic Claude Opus

**Measurable Impact:**
- Per engagement: saves 175 hours/year on PBC, 200 hours/year on IT understanding
- Across 50 engagements/year: $75k in freed consultant capacity
- Walkthrough coverage: 12% miss-rate → 3%

**Why This Project Matters for Full-Stack:** It demonstrates three core competencies:
1. **Architecture:** I chose LangGraph because I need stateful workflows with cycles (rejection loop) and interrupt/resume for human-in-the-loop. LCEL is stateless, couldn't do it.
2. **Systematic Design:** Unified State TypedDict shared across all three modules; each module is independently testable.
3. **Production Readiness:** Persistent state via checkpointer, error handling, task-level testing with golden dataset, no over-engineering.

The platform is deployed and I'd actually use it on real audits."

---

## 面试 2：系统设计（10 分钟）

### 面试官："Walk me through the architecture. Why did you choose LangGraph over LCEL or Celery?"

#### 你的答案应该包含：
- [ ] 架构图（或能口头描述）
- [ ] 三个模块的职责
- [ ] 为什么 LangGraph（不是 LCEL 或 Celery）
- [ ] 数据流（State 如何流动）

#### 标准答案（4 分钟）：

"Sure. Let me start with the architecture.

**High-Level Architecture:**

There are three modules, and they all operate on a **unified State** (a TypedDict with ~54 fields). This is important — Module B's knowledge graph and Module C's walkthrough can directly use Module A's outputs because they're all in the same State object.

```
┌──────────────────────────┐
│   Unified State          │
│   (all 54 fields)        │
└──────────┬───────────────┘
           │
    ┌──────┼──────┐
    ▼      ▼      ▼
 ModA   ModB   ModC
```

**Module A (my focus today) is a StateGraph with:**
- 5 nodes: ingest → scope_diff → update_items → review → output
- 2 conditional edges: scope_diff_router (if changes? → update or skip?), review_router (if approved? → output or loop back?)
- 1 interrupt point: review_node pauses, waits for human approval

**Now, the key question: Why LangGraph and not LCEL or Celery?**

LCEL is great for simple chains, but I have three problems it can't solve:
1. **Cycles:** After review_node, if the auditor rejects, I need to go back to update_items_node, then back through review_node again. LCEL is a linear DAG — no cycles.
2. **Conditional Routing:** If there are no scope changes, I want to skip update_items entirely and go straight to output. LCEL can't conditionally skip nodes based on state.
3. **Interrupt/Resume:** review_node calls interrupt(), which pauses the graph and saves state to a database. Later, when the user approves via HTTP, I resume from that checkpoint. LCEL has no native support for this.

LCEL could hack around these with custom Python, but it's fighting the framework.

**Why not Celery?** Celery is a task queue. It's great for "run this job in the background." But it's not LLM-native — I'd have to manually manage message history, token counting, tool use loops. LangGraph has all of that built-in.

**Data Flow in Module A:**

```
1. ingest_node:
   - Read xlsx from file
   - Parse rows into PBCItem list
   - Output: state.prior_year_items

2. scope_diff_node:
   - Claude reads: prior items + scope memo
   - Claude outputs: JSON array of scope changes
   - Output: state.scope_changes

3. scope_diff_router:
   - if state.scope_changes? → route to update_items_node
   - else → skip to output_node

4. update_items_node:
   - For each prior item: Claude decides keep/update/remove
   - For each scope change: generate new items from template
   - Output: state.current_year_items (with status field)

5. review_node:
   - Call interrupt()
   - State is persisted to database
   - HTTP returns: {status: 'awaiting_review', thread_id: '...'}
   - [User approves in browser]
   - graph.invoke(Command(resume={approved: True}), config) resumes

6. review_router:
   - if state.review_passed? → output_node
   - else → update_items_node (rejection loop!)

7. output_node:
   - Write state.current_year_items to xlsx
   - Base64 encode
   - Output: state.pbc_output_xlsx_b64
```

The rejection loop (step 6 routing back to step 4) is the killer feature. Try doing that in LCEL — you'd need to wrap the graph in a while loop or something ugly. LangGraph makes it native."

---

## 面试 3：数据持久化（8 分钟）

### 面试官："I see you use interrupt/resume. How does that work? What happens if my backend crashes?"

#### 你的答案应该包含：
- [ ] 解释 interrupt() 做了什么
- [ ] Checkpointer 如何工作（thread_id + 数据库）
- [ ] 后端 crash 后恢复的流程
- [ ] 为什么这样设计

#### 标准答案（3 分钟）：

"Great question. This is actually one of the trickier parts, and I had a gotcha moment with it.

**How interrupt/resume works:**

In review_node, I call `interrupt()`. This tells LangGraph: 'Stop here. Don't continue. Save the state. I'll resume later.'

```python
def review_node(state: State) -> State:
    from langgraph.types import interrupt
    
    # Pauses here ↓
    resume_value = interrupt('Awaiting human review...')
    
    # Does NOT execute past here until resumed
    approved = resume_value.get('approved')
    return {'review_passed': approved}
```

When interrupt() is called:
1. LangGraph serializes the entire State dict to JSON
2. Passes it to the **checkpointer**
3. Checkpointer (SqliteSaver) writes to checkpoints.db with the thread_id as key
4. Returns control to the FastAPI handler
5. Handler immediately returns HTTP 202: {status: 'awaiting_review', thread_id: 'abc-fy25'}

**Later, when the user approves:**

Frontend sends: `POST /api/review/approve/abc-fy25` with body `{approved: true}`

```python
@router.post('/api/review/approve/{thread_id}')
async def approve_review(thread_id: str, req: ReviewRequest):
    # Recreate the same checkpointer
    checkpointer = get_checkpointer()
    graph = build_compiled_graph(checkpointer=checkpointer)
    
    config = {'configurable': {'thread_id': thread_id}}
    
    # Key: use Command(resume=...), not state
    result = graph.invoke(
        Command(resume={'approved': req.approved}),
        config  # Same thread_id!
    )
```

When graph.invoke() is called with Command(resume=...):
1. LangGraph asks the checkpointer: 'Do you have state for thread_id="abc-fy25"?'
2. Checkpointer retrieves from database ✓
3. LangGraph restores the State
4. LangGraph finds the interrupt() call and resumes from there
5. review_node continues, gets approved=true
6. Graph continues through review_router → output_node → END

**The gotcha I ran into:**

First time testing, I created a new SqliteSaver() in each HTTP handler:

```python
# ✗ Wrong
@router.post('/api/review/approve/{thread_id}')
async def approve_review(...):
    checkpointer = SqliteSaver('checkpoints.db')  # New instance!
    # ...
```

Problem: each SqliteSaver instance had its own file handle, so the second one couldn't see the state written by the first instance.

**Fix:** Cache the checkpointer as a singleton.

```python
# ✓ Correct
@lru_cache(maxsize=1)
def get_checkpointer():
    return SqliteSaver('checkpoints.db')  # Reuse instance

@router.post('/api/pbc/generate')
async def generate_pbc(...):
    checkpointer = get_checkpointer()  # Same instance
    # ...

@router.post('/api/review/approve/{thread_id}')
async def approve_review(...):
    checkpointer = get_checkpointer()  # Same instance
    # ...
```

**What happens if backend crashes?**

```
Request 1: POST /api/pbc/generate
  ↓ Graph runs, review_node calls interrupt()
  ↓ State written to database ✓
  ↓ HTTP response: {status: 'awaiting_review', thread_id: 'abc-fy25'}

[Backend process crashes]

[Backend restarts (new process)]

Request 2: POST /api/review/approve/abc-fy25
  ↓ New process instantiates get_checkpointer()
  ↓ Opens checkpoints.db (same file)
  ↓ Queries: 'State for thread_id="abc-fy25"?'
  ↓ Finds it in database ✓
  ↓ Resumes graph execution ✓
  ↓ Completes and returns result
```

User has no idea the backend crashed. They just see: "Awaiting review... [REST API returns] Complete!"

This is the power of persistent state."

---

## 面试 4：前后端数据流（7 分钟）

### 面试官："Walk me through a request from the frontend all the way to the backend. What does the HTTP request look like? What about the response?"

#### 你的答案应该包含：
- [ ] 前端的 JavaScript 代码（fetch）
- [ ] HTTP 请求的具体格式（URL, method, headers, body）
- [ ] 后端接收和处理
- [ ] HTTP 响应的格式
- [ ] 前端接收响应后的处理

#### 标准答案（4 分钟）：

"Perfect. Let me trace through a real request.

**Frontend (JavaScript):**

```javascript
async function generatePBC() {
    const clientName = 'ABC Corp';
    const auditPeriod = 'FY2025';
    const scopeText = '...';
    
    const requestBody = {
        client_name: clientName,
        audit_period: auditPeriod,
        prior_year_pbc_path: '/data/sample/pbc.xlsx',
        current_year_scope_text: scopeText
    };
    
    const response = await fetch('http://localhost:8000/api/pbc/generate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestBody)
    });
    
    const data = await response.json();
    
    if (data.status === 'complete') {
        handleComplete(data);
    } else if (data.status === 'awaiting_review') {
        handleAwaitingReview(data);
    }
}
```

**What the HTTP request looks like:**

```
POST /api/pbc/generate HTTP/1.1
Host: localhost:8000
Content-Type: application/json
Content-Length: 245

{
  \"client_name\": \"ABC Corp\",
  \"audit_period\": \"FY2025\",
  \"prior_year_pbc_path\": \"/data/sample/pbc.xlsx\",
  \"current_year_scope_text\": \"FY2025 scope: SAP newly in scope...\"
}
```

**Backend (FastAPI) receives it:**

```python
@router.post('/api/pbc/generate')
async def generate_pbc(req: GeneratePBCRequest):
    # FastAPI automatically parses JSON → GeneratePBCRequest object
    # Pydantic validates: is client_name a string? Is it non-empty? Etc.
    
    client_name = req.client_name  # 'ABC Corp'
    audit_period = req.audit_period  # 'FY2025'
    scope_text = req.current_year_scope_text  # 'FY2025 scope: ...'
    
    # Create state, run graph, etc.
    state = default_state(client_name=client_name, ...)
    graph = build_compiled_graph(...)
    result = graph.invoke(state, config)
    
    # Return response (Python dict automatically → JSON)
    return {
        'status': 'complete',
        'xlsx_base64': result['pbc_output_xlsx_b64'],
        'filename': f'{client_name}_{audit_period}_pbc.xlsx'
    }
```

**HTTP Response:**

```
HTTP/1.1 200 OK
Content-Type: application/json
Content-Length: 2841

{
  \"status\": \"complete\",
  \"xlsx_base64\": \"JVBLAw4KAAoAAAAIAA...[long base64 string]...=\",
  \"filename\": \"ABC Corp_FY2025_pbc.xlsx\"
}
```

**Frontend processes response:**

```javascript
// data = {status: 'complete', xlsx_base64: 'JVBLAw4K...', filename: '...'}

function handleComplete(data) {
    window.xlsxData = {
        base64: data.xlsx_base64,
        filename: data.filename
    };
    
    // Show download button
    document.getElementById('complete-section').style.display = 'block';
}

function downloadXLSX() {
    // Decode Base64 to binary
    const binaryString = atob(window.xlsxData.base64);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    
    // Create Blob
    const blob = new Blob([bytes], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    });
    
    // Trigger download
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = window.xlsxData.filename;
    a.click();
}
```

**Key points:**

1. **HTTP is stateless:** Frontend doesn't maintain a connection. It sends a request, backend processes, returns response. Done.

2. **JSON for text, Base64 for binary:** XLSX is binary (ZIP format). Can't fit directly in JSON. So backend encodes as Base64 string. Frontend decodes back to binary.

3. **Async/await pattern:** Frontend doesn't block. It sends request, waits for response, updates UI. User can still interact.

4. **Type safety (Pydantic):** FastAPI uses Pydantic to automatically validate the request. If client sends {client_name: 123} (integer instead of string), Pydantic rejects it with 422 error.

---

## 面试 5：测试策略（6 分钟）

### 面试官："How do you test this? Do you mock Claude?"

#### 你的答案应该包含：
- [ ] 为什么 NOT mocking Claude
- [ ] 任务级测试的定义
- [ ] 黄金数据集的例子
- [ ] 精准度/召回率的计算

#### 标准答案（3 分钟）：

"Good question. My testing approach is different because mocking Claude is fragile.

**Why NOT mock Claude?**

If I mock Claude:

```python
# ✗ Bad approach
@patch('anthropic.Anthropic.messages.create')
def test_scope_diff_node(mock_claude):
    mock_claude.return_value = MagicMock(
        content=[MagicMock(text='[{\"change_type\": \"system_added\", ...}]')]
    )
    
    result = scope_diff_node(state)
    assert result['scope_changes'][0]['change_type'] == 'system_added'
```

Problem: I'm testing my mock, not Claude. If Claude's actual behavior changes (new model, different prompt interpretation), my test still passes. Silent regression.

**My Approach: Task-Level Testing (No Mocking)**

```python
def test_scope_diff_detects_new_system():
    '''
    Task: Given a scope memo mentioning 'SAP newly in scope',
    scope_diff_node should return a ScopeChange with change_type='system_added'.
    
    Input: realistic scope memo
    Call: REAL scope_diff_node (calls REAL Claude)
    Assert: output has expected structure and content
    '''
    
    state = default_state()
    state['current_year_scope_text'] = '''
    FY2025 Audit Scope:
    - Legacy: Oracle EBS, Active Directory
    - NEW: SAP S/4HANA implemented January 2025
    - All systems in scope for ITGC
    '''
    state['prior_year_items'] = [...]
    
    # Call REAL node
    result = scope_diff_node(state)
    
    # Assert structure
    assert 'scope_changes' in result
    changes = result['scope_changes']
    assert isinstance(changes, list)
    
    # Assert content
    sap_change = next(
        (c for c in changes 
         if c['change_type'] == 'system_added' and 'SAP' in c['description']),
        None
    )
    assert sap_change is not None
    assert 'ITGC - JML' in sap_change['affected_categories']
```

If Claude breaks, this test breaks. That's the point!

**Golden Dataset: Precision/Recall Baseline**

I hand-curated 10 (input, expected_output) pairs:

```
data/golden/
├── case_01/
│   ├── input_scope_memo.txt
│   ├── input_prior_pbc.xlsx
│   └── expected_current_pbc.xlsx
├── case_02/
│   ├── input_scope_memo.txt
│   ├── input_prior_pbc.xlsx
│   └── expected_current_pbc.xlsx
└── ... (8 more cases)
```

Test:

```python
def test_precision_recall_golden_dataset():
    for case_id in ['case_01', 'case_02', ...]:
        # Load input
        scope_memo = read_text(f'data/golden/{case_id}/input_scope_memo.txt')
        prior_pbc = read_xlsx(f'data/golden/{case_id}/input_prior_pbc.xlsx')
        expected_pbc = read_xlsx(f'data/golden/{case_id}/expected_current_pbc.xlsx')
        
        # Run full Module A pipeline
        state = default_state()
        state['current_year_scope_text'] = scope_memo
        state['prior_year_items'] = parse_pbc(prior_pbc)
        
        graph = build_pbc_graph().compile()
        result = graph.invoke(state)
        
        actual_pbc = parse_pbc(result['pbc_output_xlsx_path'])
        
        # Calculate precision: of our detected changes, how many are correct?
        true_changes = identify_changes(expected_pbc, prior_pbc)
        detected_changes = result['scope_changes']
        
        correct = sum(
            1 for d in detected_changes
            if any(
                t['change_type'] == d['change_type'] and
                t['description'] in d['description']
                for t in true_changes
            )
        )
        precision = correct / len(detected_changes) if detected_changes else 1.0
        
        # Calculate recall: of true changes, how many did we find?
        found = sum(
            1 for t in true_changes
            if any(
                d['change_type'] == t['change_type'] and
                t['description'] in d['description']
                for d in detected_changes
            )
        )
        recall = found / len(true_changes) if true_changes else 1.0
        
        print(f'{case_id}: Precision={precision:.1%}, Recall={recall:.1%}')
        assert precision >= 0.9
        assert recall >= 0.9
```

Output:
```
case_01: Precision=100%, Recall=100%
case_02: Precision=100%, Recall=100%
...
case_10: Precision=90%, Recall=95%

Summary: All 10 cases passed ✓
```

**Why this works:**

1. **Regression detection:** If I change a prompt and it breaks quality, the golden dataset catches it immediately.

2. **Quantified baselines:** I know my system achieves 90%+ precision/recall. If I refactor and drop to 85%, I know something broke.

3. **No mocking:** I'm testing Claude's real behavior. It's a bit slower (each test calls Claude), but worth it for confidence."

---

## 面试 6：你会怎么改进？（5 分钟）

### 面试官："If you built this again, what would you do differently?"

#### 你的答案应该包含：
- [ ] 2-3 个真实的改进
- [ ] 解释为什么这些改进重要
- [ ] 展示你有反思能力

#### 标准答案（2-3 分钟）：

"Good question. Two things:

**1. Parallel Module Development**

I built sequentially: Module A → B → C. But B and C don't depend on each other; they only depend on A finishing. So I could have:
- Week 1: Start Module A + Module B in parallel
- Week 2: Complete both, start Module C
- Week 3: Integrate all three

Instead I did:
- Week 1: Complete Module A
- Week 2: Complete Module B
- Week 3: Complete Module C

This cost me ~1 week. Lesson: Look for parallelizable work earlier.

**2. Token Cost Visibility from Day 1**

I didn't measure token usage until late in development. Then I discovered:
- scope_diff_node: ~400 tokens per audit
- update_items_node: ~600 tokens per audit
- Total per engagement: ~1000 tokens = $0.015 (Opus pricing)
- Per 50 engagements: $0.75 😂

So token cost is negligible. But I wish I'd measured this from day one because it would have informed my prompt design. Like: 'Is this verbose example worth 100 extra tokens?' Now I can answer that.

**Architecture-wise, I'd keep it the same.** LangGraph + FastAPI + unified State turned out to be the right choice. Zero regrets there."

---

## 面试 7：生产问题（7 分钟）

### 面试官："How would you deploy this to production? What about scaling to 500 engagements instead of 50?"

#### 你的答案应该包含：
- [ ] 当前部署（SQLite）
- [ ] 扩展方案（Postgres）
- [ ] 异步/并发处理
- [ ] 监控和日志

#### 标准答案（3-4 分钟）：

"Good. Currently I'm on SQLite, which works for 50 engagements but doesn't scale.

**Current (Dev):**
- FastAPI running locally
- SQLite checkpointer (single file)
- Synchronous graph.invoke()

Limitation: SQLite is file-based. With 10 concurrent HTTP requests trying to resume graphs, file locking becomes bottleneck.

**Production (Scaled to 500):**

Three changes:

**1. Async Task Queue**

Currently, HTTP request waits for graph.invoke() to complete. For 500 engagements, I don't want HTTP threads blocked.

```python
# Before (synchronous)
@router.post('/api/pbc/generate')
async def generate_pbc(req):
    result = graph.invoke(state, config)  # Blocks!
    return result

# After (async with Celery)
from celery import shared_task

@shared_task
def run_graph_task(thread_id, state):
    # Run in background worker
    result = graph.invoke(state, config)
    # Save result to database
    db.update_run(thread_id, result)

@router.post('/api/pbc/generate')
async def generate_pbc(req):
    # Immediately queue the task
    task = run_graph_task.delay(thread_id, state)
    # Return task_id to frontend
    return {'status': 'processing', 'task_id': task.id}

@router.get('/api/status/{task_id}')
async def check_status(task_id):
    task = run_graph_task.AsyncResult(task_id)
    if task.ready():
        return {'status': 'complete', 'result': task.result}
    else:
        return {'status': 'processing'}
```

Frontend polls GET /api/status/{task_id} every 5 seconds until complete.

**2. PostgreSQL Checkpointer**

```python
# Before (SQLite)
from langgraph.checkpoint.sqlite import SqliteSaver
checkpointer = SqliteSaver('checkpoints.db')

# After (PostgreSQL)
from langgraph.checkpoint.postgres import PostgresCheckpointer
checkpointer = PostgresCheckpointer(
    conn_string='postgresql://user:pass@db.example.com/audit_db'
)
```

PostgreSQL supports:
- Concurrent writes (multiple workers writing checkpoints)
- Transactions + row-level locking
- Connection pooling (efficient)

**3. Monitoring & Logging**

```python
import logging
import structlog

logger = structlog.get_logger()

@router.post('/api/pbc/generate')
async def generate_pbc(req):
    thread_id = f'{req.client_name}_{req.audit_period}'
    
    logger.info(
        'pbc_generate_start',
        thread_id=thread_id,
        client_name=req.client_name,
        scope_text_length=len(req.current_year_scope_text)
    )
    
    start_time = time.time()
    
    try:
        task = run_graph_task.delay(thread_id, state)
        elapsed = time.time() - start_time
        
        logger.info(
            'pbc_generate_queued',
            thread_id=thread_id,
            task_id=task.id,
            elapsed_ms=elapsed * 1000
        )
        
        return {'status': 'processing', 'task_id': task.id}
    
    except Exception as e:
        logger.error(
            'pbc_generate_error',
            thread_id=thread_id,
            error=str(e),
            exc_info=True
        )
        raise
```

Send logs to Datadog/CloudWatch. Monitor:
- Task queue length (backlog?)
- Graph execution time by node
- Token usage per engagement
- Error rates
- User feedback (add feedback button to UI)

**Deployment:**

```
Load Balancer (nginx)
  ├─ API Instance 1 (FastAPI)
  ├─ API Instance 2 (FastAPI)
  └─ API Instance 3 (FastAPI)
       ↓ (all instances point to same DB)
  PostgreSQL (RDS)
    └─ checkpoints table (concurrent access)
  
Celery Workers (3-5 instances)
  └─ Queue broker (Redis)
       ↓
  Graph execution (background)
    └─ Calls Claude, reads/writes files
```

With this setup, I can:
- Scale frontend: add more API instances
- Scale background: add more Celery workers
- Scale storage: Postgres handles 1000s of concurrent connections

**Cost estimate:**
- 500 engagements/year = 500 graph runs
- Each run: ~1000 tokens = $0.015
- Total LLM cost/year: $7.50

Not the bottleneck. The bottleneck would be compute (Celery workers) and storage (Postgres)."

---

## 面试 8：关键决策（5 分钟）

### 面试官："Why TypedDict instead of a class? Why unified State instead of separate states?"

#### 你的答案应该包含：
- [ ] TypedDict 的优点（IDE autocomplete, 类型检查）
- [ ] TypedDict 的缺点（无运行时强制）
- [ ] 统一 State 的权衡

#### 标准答案（2-3 分钟）：

"Great architectural question.

**Why TypedDict?**

TypedDict gives me two things:
1. **IDE Autocomplete:** When I type `state['`, my editor suggests all valid keys. Without TypedDict, I'd be flying blind. "Is it scope_changes or scope_change? one_item or items?" etc. This catches typos early.
2. **Static Type Checking:** mypy can catch bugs: 'state['scope_changes'] is a list, but you're accessing state['scope_changes'][0].description without checking length.' 

But TypedDict doesn't enforce required fields at runtime. So if code accidentally doesn't populate a field, Python won't complain until later when some node tries to read it.

**Mitigation:** `default_state()` factory function.

```python
def default_state(...) -> State:
    return State(
        client_name=client_name,
        audit_period=audit_period,
        prior_year_items=[],
        scope_changes=[],
        current_year_items=[],
        # ... all 54 fields initialized
    )
```

Every graph run starts with fully-populated default state. Nodes only update their slices. No field is ever missing.

**Why Unified State instead of Module-Specific States?**

Alternative:

```python
# ✗ Separate states
class PBCState(TypedDict):
    prior_year_items: List[PBCItem]
    current_year_items: List[PBCItem]
    scope_changes: List[ScopeChange]

class UnderstandingState(TypedDict):
    entities: List[ITEntity]
    relationships: List[EntityRelationship]

class WalkthroughState(TypedDict):
    topics: List[WalkthroughTopic]
    coverage: Dict[str, str]

# Problem: Data between modules must be manually passed
pbc_state = run_pbc_graph(input_state)
understanding_state = run_understanding_graph(
    entities=[],  # ← How do you populate this? From where?
)
```

With unified state:

```python
# ✓ Unified state
class State(TypedDict):
    # Module A fields
    prior_year_items: List[PBCItem]
    current_year_items: List[PBCItem]
    scope_changes: List[ScopeChange]
    
    # Module B fields
    entities: List[ITEntity]
    relationships: List[EntityRelationship]
    
    # Module C fields
    topics: List[WalkthroughTopic]
    coverage: Dict[str, str]

# Module C directly reads Module B's output
def suggest_questions_node(state: State):
    entities = state['entities']  # ← Populated by Module B
    topics = state['topics']       # ← Populated by Module A
    # Use both
```

**Trade-off:**

Pro:
- Downstream modules automatically see upstream outputs
- No manual data passing
- Clear data provenance

Con:
- State is large (54 fields)
- Schema evolution is trickier (if I add a field, old states from DB lack it)

Mitigation: `state.get('new_field', default_value)` for new fields.

On balance, unified state was the right call for this project."

---

## 总结：你应该现在能回答这 8 个问题

- [x] 开场：What's your project?
- [x] 架构：Why LangGraph?
- [x] 数据持久化：How does interrupt/resume work?
- [x] 前后端：Walk me through a request.
- [x] 测试：How do you test? Mock Claude?
- [x] 改进：What would you do differently?
- [x] 扩展：How do you scale?
- [x] 设计：Why TypedDict? Why unified State?

**练习方式：**
1. 闭卷回答每一个问题（5-10 分钟）
2. 对照标准答案，看你遗漏了什么
3. 再读一遍标准答案，记住关键点
4. 重复 3-5 遍，直到能自然流畅地讲出来

**面试时的关键：** 不是背答案，而是展示你能清晰地思考和解释。

