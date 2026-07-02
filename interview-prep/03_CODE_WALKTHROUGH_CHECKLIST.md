# 代码讲解检查清单 — 如何在面试中讲代码

> 面试官说："Show me the code."你怎么讲，才能展示出专业度？
> 这个清单帮你在 live coding 或 code walkthrough 时不犯错误。

---

## 📋 通用讲解原则

### ❌ 不要做这些

| 错误 | 为什么错 | 正确做法 |
|------|--------|---------|
| "这个函数做的是..." | 描述代码在做什么（面试官能读） | "这个函数的目的是...（为什么需要它）" |
| 逐行讲解代码 | 太慢，太无聊 | 讲关键部分，跳过显而易见的部分 |
| "这是我之前写的..." | 显得没有思考 | "这样做是因为..." |
| 一直看屏幕 | 显得紧张 | 看着面试官讲，偶尔指向屏幕 |
| "我不确定为什么..." | 显得不专业 | 如果不记得，说"让我想想...实际上..." |

### ✅ 要做这些

| 好做法 | 为什么好 | 例子 |
|--------|--------|------|
| 讲"为什么"而不是"是什么" | 展示思考深度 | "我在这里用 StateGraph 而不是 LCEL，因为需要处理循环..." |
| 讲关键的 5 行而不是 50 行 | 面试官时间有限 | "关键部分是这里：[指向 interrupt() 调用]" |
| 讲权衡 | 展示你考虑过多个方案 | "我可以用 LCEL，但那样就需要手写状态管理，所以我选了 LangGraph" |
| 讲你犯过的错误 | 展示学习能力 | "第一次我这样做，结果遇到了 X 问题，所以改成了..." |
| 连接到业务价值 | 展示全局思维 | "这个 interrupt 点让用户能审查清单，这很重要，因为..." |

---

## 🎯 讲解 LangGraph 代码

### 场景：面试官问"Show me how the graph is structured"

**准备工作：** 打开 `modules/pbc/graph.py`

```python
from langgraph.graph import StateGraph, END

def build_pbc_graph() -> StateGraph:
    g = StateGraph(State)
    
    # Add nodes
    g.add_node("ingest_node", ingest_node)
    g.add_node("scope_diff_node", scope_diff_node)
    g.add_node("update_items_node", update_items_node)
    g.add_node("review_node", review_node)
    g.add_node("output_node", output_node)
    
    # Edges
    g.set_entry_point("ingest_node")
    g.add_edge("ingest_node", "scope_diff_node")
    g.add_edge("update_items_node", "review_node")
    g.add_edge("output_node", END)
    
    # Conditional edges
    g.add_conditional_edges(
        "scope_diff_node",
        scope_diff_router,
        {"update_items_node": "update_items_node", "output_node": "output_node"}
    )
    g.add_conditional_edges(
        "review_node",
        review_router,
        {"output_node": "output_node", "update_items_node": "update_items_node"}
    )
    
    return g

def scope_diff_router(state: State) -> str:
    return "update_items_node" if state.get("scope_changes") else "output_node"

def review_router(state: State) -> str:
    return "output_node" if state.get("review_passed") else "update_items_node"
```

### ✅ 讲解脚本（30秒）

"So here's the Module A StateGraph. Let me point out the key parts:

**First, the nodes:** [指向 add_node 行]
We have 5 nodes: ingest, scope_diff, update_items, review, output. Each one is a Python function that reads/writes state.

**Second, linear edges:** [指向 add_edge 行]
Straight paths: ingest → scope_diff, update → review, output → END.

**Third, the interesting part — conditional edges:** [指向 add_conditional_edges]
This is where the magic happens. Two conditional routers:

1. **scope_diff_router:** [指向 scope_diff_router 函数]
   After scope_diff_node, we ask: 'Do we have scope changes?' If yes, we go to update_items_node. If no, we skip directly to output_node. This saves work when scope hasn't changed.

2. **review_router:** [指向 review_router 函数]
   After review_node, we ask: 'Did the user approve?' If yes, output. If no, loop back to update_items_node.
   
   This rejection loop is the key reason I chose LangGraph over LCEL. LCEL is a stateless DAG—it can't loop. LangGraph handles it natively with add_conditional_edges.

**Why this matters for the interview?** This shows you understand state machines and conditional logic. It's not just a linear pipeline."

### ❌ 不要讲

- 逐行讲解 add_node 的语法（太基础）
- "StateGraph 是什么"（面试官会问，但不要主动讲）
- 过多的 Python 细节（"dict 是..."）

### 如果面试官追问

Q: "Why not use a simpler approach, like a while loop with if/else?"

A: "Good question. I could do that in regular Python:

```python
while True:
    state = ingest(state)
    state = scope_diff(state)
    if state['scope_changes']:
        state = update_items(state)
    state = review(state)
    if state['review_passed']:
        break
    # loop back
```

But then I lose:
1. **Persistence:** If my backend crashes during review_node, the state is lost. With LangGraph + checkpointer, it's saved to a database.
2. **Human-in-the-loop:** review_node calls interrupt(), which pauses the entire graph and returns control to HTTP. Later, a different HTTP request resumes it. A while loop can't do that—it'd block the entire thread.
3. **Observability:** LangGraph tracks which node I'm in, the state at each step. A while loop is a black box.

So the added complexity of LangGraph is worth it."

---

## 🎯 讲解 FastAPI 路由代码

### 场景：面试官问"Walk me through a request from frontend to backend"

**准备工作：** 打开 `api/routes/pbc.py`

```python
@router.post("/api/pbc/generate")
async def generate_pbc(req: GeneratePBCRequest) -> GeneratePBCResponse:
    # Validate
    if not os.path.exists(req.prior_year_pbc_path):
        raise HTTPException(400, f"File not found: ...")
    
    # Create state
    state = default_state(
        client_name=req.client_name,
        audit_period=req.audit_period,
        thread_id=f"{req.client_name}_{req.audit_period}",
    )
    state["prior_year_pbc_path"] = req.prior_year_pbc_path
    state["current_year_scope_text"] = req.current_year_scope_text
    
    # Compile graph
    checkpointer = get_checkpointer()
    graph = build_compiled_graph(checkpointer=checkpointer)
    
    # Run
    config = {"configurable": {"thread_id": state["thread_id"]}}
    result = graph.invoke(state, config)
    
    return GeneratePBCResponse(
        status="complete",
        xlsx_base64=result.get("pbc_output_xlsx_b64"),
        filename=f"{req.client_name}_{req.audit_period}_pbc.xlsx",
    )
```

### ✅ 讲解脚本（1 分钟）

"Let's trace a request. Frontend sends JSON to POST /api/pbc/generate.

**Step 1: Type validation** [指向 req: GeneratePBCRequest]
FastAPI + Pydantic automatically parse the JSON and validate it. If the JSON is malformed, Pydantic rejects it with a 422 error before we even run code.

**Step 2: File check** [指向 os.path.exists]
Simple safety: does the xlsx file exist? If not, fail fast.

**Step 3: Create state** [指向 default_state]
I initialize the State with the user's input. All 54 fields are populated. This is important—I'm not leaving any field uninitialized.

**Step 4: Get checkpointer** [指向 get_checkpointer()]
This is a cached singleton. Every HTTP request uses the SAME checkpointer instance, so state can be persisted and later retrieved.

**Step 5: Compile graph** [指向 build_compiled_graph]
I create the StateGraph and compile it with the checkpointer. Compiling just means LangGraph validates the graph structure.

**Step 6: Run graph** [指向 graph.invoke]
Here's where the magic happens. graph.invoke(state, config) runs all the nodes sequentially until one of three things:
1. We hit END → graph completes normally
2. We hit interrupt() → graph pauses and saves state
3. An exception is raised

**Step 7: Return response** [指向 return GeneratePBCResponse]
If the graph completed (no interrupt), we extract the xlsx_base64 and return it in JSON. Frontend decodes the Base64 and downloads the file.

Key insight: The entire flow is asynchronous. Frontend sends request, waits for response. Backend doesn't block other HTTP requests. This scales."

### ❌ 不要讲

- HTTPException 的细节
- Pydantic 的内部如何工作
- "async/await 是..."

### 如果面试官追问

Q: "What happens if graph.invoke() throws an exception?"

A: "Good. Right now, my code just lets it bubble up, and FastAPI catches it and returns a 500 error. In production, I'd add more specific exception handling:

```python
except GraphInterrupt as e:
    # Expected: graph paused at interrupt()
    return GeneratePBCResponse(
        status="awaiting_review",
        thread_id=state["thread_id"]
    )
except ValueError as e:
    # Bad input
    raise HTTPException(400, str(e))
except Exception as e:
    # Unexpected error
    logger.error(f'Error: {e}', exc_info=True)
    raise HTTPException(500, 'Internal server error')
```

This gives better error messages to the frontend and logs for debugging."

---

## 🎯 讲解测试代码

### 场景：面试官问"How do you test this? Show me a test"

**准备工作：** 打开 `tests/pbc/test_scope_diff.py`

```python
def test_scope_diff_detects_new_system():
    state = default_state(
        client_name="ABC Corp",
        audit_period="FY2025",
    )
    
    state["current_year_scope_text"] = """
    FY2025 Audit Scope:
    - Existing: Oracle EBS, Active Directory
    - NEW: SAP S/4HANA implemented January 2025
    - All systems in audit scope
    """
    
    state["prior_year_items"] = [
        {
            "item_id": "JML-001",
            "category": "ITGC - JML",
            "description": "Evidence of joiner/mover/leaver controls",
            "in_scope": True,
            "period": "FY2024",
            "sample_size": "25",
            "status": "carried_over",
            "last_year_id": None,
            "notes": "",
        }
    ]
    
    # Call the REAL node
    result = scope_diff_node(state)
    
    # Assert
    assert "scope_changes" in result
    changes = result["scope_changes"]
    
    sap_change = next(
        (c for c in changes 
         if c["change_type"] == "system_added" and "SAP" in c["description"]),
        None
    )
    
    assert sap_change is not None, "Should detect SAP as new system"
    assert "ITGC - JML" in sap_change["affected_categories"]
```

### ✅ 讲解脚本（1 分钟）

"Here's a test. Key thing to notice: **I'm NOT mocking Claude.**

[指向 scope_diff_node(state) 调用]
I call the REAL node, which calls the REAL Claude. This is different from typical unit tests that mock everything.

Why? Because if Claude's behavior changes (new model version, prompt tweak), I want the test to fail and alert me. If I mock Claude, the test passes even though the real system is broken.

[指向 result["scope_changes"] 部分]
I'm testing the contract: given input X (scope memo mentioning SAP), does the output have expected structure (scope_changes list) and content (system_added for SAP)?

[指向 assert sap_change is not None]
This assertion does the heavy lifting. It checks: 'Did Claude correctly identify SAP as a new system?'

If Claude breaks—maybe it's having an off day, or I changed the prompt—this test fails. That's the point.

**Golden Dataset:**
I also have 10 hand-curated (input, expected_output) pairs. For each pair, I run the full Module A pipeline and measure precision/recall. This gives me a quantified baseline: 'My system is 90%+ precise and recall on these cases.'

If I refactor and recall drops to 80%, I know something broke."

### ❌ 不要讲

- pytest 的语法细节
- 如何运行测试
- "assert 是一个..."

### 如果面试官追问

Q: "But calling Claude in every test is slow and expensive, right?"

A: "Yes, 100%. Each test takes 2-5 seconds (waiting for Claude) and costs a few cents per run. So I wouldn't run these tests 100 times per day during development.

Instead:
1. **Fast unit tests:** Test the node's internal logic without Claude (if I refactored the prompting logic)
2. **Task-level tests (slower):** Test the full node with Claude (run once per day or before commit)
3. **Golden dataset (slowest):** Run the full pipeline on 10 test cases (run once per day)

In CI/CD, I'd run all three before merging. In local development, I'd run fast tests frequently and slower tests before pushing.

Trade-off: slower test suite, but actual confidence that Claude isn't broken."

---

## 🎯 讲解前端代码

### 场景：面试官问"How does the frontend work?"

**准备工作：** 打开 `frontend/pbc.html`

```javascript
async function generatePBC() {
    const requestBody = {
        client_name: document.getElementById("clientName").value,
        audit_period: document.getElementById("auditPeriod").value,
        prior_year_pbc_path: "/data/sample_client_FY2024/pbc_list.xlsx",
        current_year_scope_text: document.getElementById("scopeText").value
    };
    
    const response = await fetch("http://localhost:8000/api/pbc/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody)
    });
    
    const data = await response.json();
    
    if (data.status === "complete") {
        handleComplete(data);
    } else if (data.status === "awaiting_review") {
        handleAwaitingReview(data);
    }
}

function handleAwaitingReview(data) {
    window.currentThreadId = data.thread_id;
    document.getElementById("review-section").style.display = "block";
}

async function approvePBC() {
    const response = await fetch(
        `http://localhost:8000/api/review/approve/${window.currentThreadId}`,
        {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ approved: true, notes: "" })
        }
    );
    
    const data = await response.json();
    if (data.status === "complete") {
        handleComplete(data);
    }
}

function handleComplete(data) {
    window.xlsxData = {
        base64: data.xlsx_base64,
        filename: data.filename
    };
    document.getElementById("complete-section").style.display = "block";
}

function downloadXLSX() {
    const binaryString = atob(window.xlsxData.base64);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    
    const blob = new Blob([bytes], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    });
    
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = window.xlsxData.filename;
    a.click();
}
```

### ✅ 讲解脚本（1 分钟）

"The frontend is vanilla JavaScript—no framework. I kept it simple.

**Three main flows:**

[指向 generatePBC]
1. User fills form and clicks 'Generate'. JavaScript reads form inputs, creates JSON request body, POSTs to backend. We await the response and check status.

[指向 handleAwaitingReview]
2. If status='awaiting_review', the graph paused at review_node. We save the thread_id globally and show the review UI.

[指向 approvePBC]
3. User reviews and clicks 'Approve'. We POST to /api/review/approve/{thread_id}. The backend resumes the graph and returns the final result.

[指向 handleComplete]
4. If status='complete', we save the xlsx_base64 data and show the download button.

[指向 downloadXLSX]
5. User clicks 'Download'. We decode Base64 to binary, create a Blob, and trigger the browser's download.

**Key design decision: No framework**
I could have used React, but it would add webpack config, build step, dependencies. For this MVP, vanilla JS is faster to build and easier to deploy (single HTML file). If this grew to 10+ pages, I'd add a framework."

### ❌ 不要讲

- HTML/CSS 细节
- "async/await 是..."
- "Why not React?" (unless they ask)

### 如果面试官追问

Q: "What if the backend crashes while the user is reviewing?"

A: "[指向 window.currentThreadId]
We saved the thread_id in JavaScript. If the backend crashes and user refreshes the page, the thread_id is lost from memory. But in production, we'd have a GET /api/pbc/history endpoint that lists all pending reviews. User can see 'ABC Corp FY2025 - awaiting review' and click to resume."

---

## 📋 通用讲解检查清单

在讲任何代码时，确保你：

### 前 5 分钟

- [ ] 讲**为什么**这个代码存在，不是**是什么**
- [ ] 指向关键的 5-10 行，不是全部代码
- [ ] 讲这个部分如何连接到整个系统
- [ ] 提到你考虑过的替代方案和为什么没选它们

### 讲解过程中

- [ ] 看着面试官，不是一直看屏幕
- [ ] 用手指指向代码的关键部分
- [ ] 停顿让面试官提问（不要一直讲）
- [ ] 如果面试官问，解释变量名或函数名的来源

### 回答追问时

- [ ] "That's a good question. Let me think..." （买时间，不用急）
- [ ] 讲你在这部分犯过的错误或学到的东西
- [ ] 连接到业务价值（"这很重要，因为..."）
- [ ] 如果不确定，说"让我看一下代码..." 而不是编造答案

### 总体

- [ ] 代码讲解应该花 10-15 分钟的面试时间，不是 30 分钟
- [ ] 如果面试官没有问追问，主动给出一两个有趣的权衡（"我也考虑过..."）
- [ ] 最后 1-2 句总结：这部分代码为什么重要

---

## 🎯 你应该准备讲这 4 个部分

1. **LangGraph 图结构** （modules/pbc/graph.py）
   - 关键：条件边 + 拒绝循环

2. **FastAPI 路由** （api/routes/pbc.py）
   - 关键：请求 → State → 图执行 → 响应

3. **测试** （tests/pbc/test_scope_diff.py）
   - 关键：不 mock Claude，golden dataset

4. **前端** （frontend/pbc.html）
   - 关键：fetch，interrupt/resume，Base64 下载

**最后一次提醒：** 在实际面试前，在镜子前或对着朋友讲 2-3 遍。时间应该在 15 分钟以内。

