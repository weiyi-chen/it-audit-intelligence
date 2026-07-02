# 程序执行流程详解

## 用户与系统交互流

```
┌─────────────────────────────────────────────────────────────────────┐
│                         用户（IT 审计师）                           │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
            ┌────────────────────────────────────┐
            │   浏览器打开                        │
            │   http://localhost:8080/pbc.html   │
            └────────┬─────────────────────────┘
                     │
              ┌──────▼──────┐
              │ 选择上年文件 │
              │ 输入今年范围 │
              └──────┬──────┘
                     │
                     ▼
    ┌────────────────────────────────────┐
    │  前端 JavaScript                   │
    │  fetch POST /api/pbc/generate      │
    │  {                                 │
    │    "client_name": "ABC Corp",      │
    │    "audit_period": "FY2025",       │
    │    "prior_year_pbc_path": "...",   │
    │    "current_year_scope_text": "..."│
    │  }                                 │
    └──────────────────┬─────────────────┘
                       │ HTTP
                       ▼
    ┌────────────────────────────────────┐
    │  FastAPI (api/main.py)             │
    │  routes/pbc.py:generate_pbc()      │
    └──────────────────┬─────────────────┘
                       │
        ┌──────────────▼──────────────┐
        │  创建初始 State:             │
        │  State(                    │
        │    client_name="ABC Corp" │
        │    audit_period="FY2025"  │
        │    prior_year_pbc_path="..│
        │    ...所有字段初始化       │
        │  )                        │
        └──────────────┬────────────┘
                       │
        ┌──────────────▼────────────────────┐
        │  编译 Module A 图                 │
        │  graph = build_compiled_graph(    │
        │      checkpointer=get_checkpointer│
        │  )                               │
        └──────────────┬────────────────────┘
                       │
        ┌──────────────▼────────────────────┐
        │  执行：graph.invoke(state, config)│
        └──────────────┬────────────────────┘
                       │
═══════════════════════╩═════════════════════════════════════════════════
                       │
                 ┌─────▼─────────────────────────────────────────┐
                 │      📊 Module A 执行流（StateGraph）        │
                 └────────────────────────────────────────────────┘
                       │
         ┌─────────────▼─────────────────┐
         │  Node: ingest_node            │
         │  ─────────────────────        │
         │  输入：                       │
         │    - prior_year_pbc_path      │
         │    - current_year_scope_text  │
         │                              │
         │  处理：                       │
         │    xlsx = read_xlsx(path)     │
         │    items = parse(xlsx)        │
         │                              │
         │  输出更新：                   │
         │    state.prior_year_items = items
         └────────┬────────────────────┘
                  │ state 传递给下一个节点
                  ▼
         ┌─────────────────────────────┐
         │  Node: scope_diff_node       │
         │  ───────────────────────    │
         │                            │
         │  LLM 调用：                 │
         │  messages = [               │
         │    {role: "user", content:  │
         │      f"""                   │
         │      去年项目：{items}       │
         │      今年范围：{scope_text}  │
         │      识别差异变化          │
         │      返回 JSON:             │
         │      [{                     │
         │        "change_type":       │
         │        "description":       │
         │        "affected_categories"│
         │      }]                     │
         │      """                    │
         │    }                        │
         │  ]                          │
         │                            │
         │  response = claude.messages │
         │    .create(model="...",     │
         │             messages=...)   │
         │                            │
         │  scope_changes =            │
         │    json.parse(response)     │
         │                            │
         │  输出更新：                  │
         │    state.scope_changes =    │
         │      scope_changes          │
         └────────┬────────────────────┘
                  │
                  ▼
         ┌─────────────────────────────┐
         │  条件路由：scope_diff_router │
         │  ─────────────────────────  │
         │                            │
         │  if state.scope_changes:  │
         │    → update_items_node     │
         │  else:                     │
         │    → output_node           │
         │                            │
         │  （跳过无变化情况的更新）   │
         └────────┬────────────────────┘
                  │
                  ├─ 有变化 ─→ ┌──────────────────────────┐
                  │           │  Node: update_items_node  │
                  │           │  ───────────────────────│
                  │           │                        │
                  │           │  for item in items:    │
                  │           │    status = claude(    │
                  │           │      f"""              │
                  │           │      项目：{item}       │
                  │           │      变化：{changes}    │
                  │           │      保留/更新/删除？  │
                  │           │      """               │
                  │           │    )                   │
                  │           │                        │
                  │           │  for change in changes:│
                  │           │    new_items +=        │
                  │           │      templates.get()   │
                  │           │                        │
                  │           │  输出更新：            │
                  │           │   current_year_items   │
                  │           └──────────┬─────────────┘
                  │                      │
                  │                      ▼
                  │           ┌──────────────────────────┐
                  │           │  Node: review_node       │
                  │           │  ──────────────────────│
                  │           │                        │
                  │           │  graph.interrupt()     │
                  │           │  ↓                     │
                  │           │  等待人工审查...        │
                  │           │                        │
                  │           │  [此时状态持久化到DB] │
                  │           │                        │
                  │           │  return {              │
                  │           │    "__interrupt__": ... │
                  │           │  }                     │
                  │           │                        │
                  │           │  ≈ HTTP 立即返回给前端 │
                  │           │    status: "awaiting"   │
                  │           │    thread_id: "..."     │
                  │           └──────────────────────────┘
                  │
                  └─ 无变化 ──→ 跳过更新直接→ output_node
                              
     ┌────────────────────────────────────────────────────────────┐
     │ [此时] 前端显示：等待审查，可下载临时 xlsx 或提交审查意见  │
     │                                                            │
     │ 用户操作：在浏览器中点击「批准」或「拒绝+备注」              │
     │                                                            │
     │ 前端 POST /api/review/approve/{thread_id}                 │
     │         or /api/review/reject/{thread_id}                 │
     └────────────────┬──────────────────────────────────────────┘
                      │
        ┌─────────────▼──────────────┐
        │  FastAPI (routes/review.py)│
        │  resume 图执行             │
        │                           │
        │  graph.invoke(            │
        │    Command(               │
        │      resume={             │
        │        "approved": True,  │
        │        "notes": "..."     │
        │      }                    │
        │    )                      │
        │  )                        │
        └─────────────┬──────────────┘
                      │
           ┌──────────▼─────────────────────┐
           │  review_node 恢复运行            │
           │                               │
           │  if resume["approved"]:      │
           │    state.review_passed=True  │
           │    → 下一步：output_node      │
           │  else:                       │
           │    state.review_passed=False │
           │    → 回到：update_items_node │
           │       (修改循环)             │
           └──────────┬────────────────────┘
                      │
          ┌───────────▼────────────────────┐
          │  Node: output_node             │
          │  ──────────────────────────   │
          │                              │
          │  xlsx_bytes = write_xlsx(    │
          │    current_year_items        │
          │  )                           │
          │                              │
          │  b64_str = base64.encode(    │
          │    xlsx_bytes                │
          │  )                           │
          │                              │
          │  输出更新：                    │
          │    state.pbc_output_xlsx_b64 │
          │    = b64_str                 │
          └──────────┬────────────────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │  graph.invoke 返回   │
          │  最终 state          │
          └──────────┬───────────┘
                     │
                     ▼
    ┌─────────────────────────────────────┐
    │  FastAPI 路由返回 JSON:             │
    │  {                                 │
    │    "status": "complete",           │
    │    "xlsx_base64": "JVBLAw4KAA...", │
    │    "filename": "ABC_FY2025_pbc..." │
    │  }                                 │
    └─────────────────┬───────────────────┘
                      │ HTTP response
                      ▼
    ┌──────────────────────────────────┐
    │  前端 JavaScript                 │
    │  - 隐藏加载旋转圈               │
    │  - 解码 base64                   │
    │  - 触发下载 xlsx                 │
    │  - 显示"下载完成"               │
    └────────────────────────────────┘
```

---

## 关键状态转换

### State 对象如何从头到尾流转

```python
# T0: 初始化（FastAPI 收到请求）
state = {
    "client_name": "ABC Corp",
    "audit_period": "FY2025",
    "prior_year_pbc_path": "/data/abc_fy24.xlsx",
    "current_year_scope_text": "FY2025 scope: SAP newly in scope...",
    "prior_year_items": [],          # ← 待 ingest 填充
    "scope_changes": [],             # ← 待 scope_diff 填充
    "current_year_items": [],        # ← 待 update 填充
    "pbc_output_xlsx_path": "",      # ← 待 output 填充
    "pbc_output_xlsx_b64": "",       # ← 待 output 填充
    "review_passed": False,          # ← 待 review 改变
    # ... 其他字段
}

# T1: ingest_node 执行后
state.prior_year_items = [
    {"item_id": "JML-001", "category": "ITGC - JML", ...},
    {"item_id": "JML-002", ...},
    ...
]

# T2: scope_diff_node 执行后
state.scope_changes = [
    {"change_type": "system_added", "description": "SAP S/4HANA", ...},
    ...
]

# T3: scope_diff_router 决策
if state.scope_changes:  # True
    route_to = "update_items_node"

# T4: update_items_node 执行后
state.current_year_items = [
    {"item_id": "JML-001", "status": "carried_over", ...},
    {"item_id": "JML-002", "status": "updated", ...},
    {"item_id": "SAP-JML-001", "status": "new", ...},
    ...
]

# T5: review_node 执行后
graph.interrupt()
# State 此时持久化到数据库
# HTTP 立即返回 {"status": "awaiting_review", ...}

# [用户在浏览器中点击「批准」]

# T6: review_node 恢复后
state.review_passed = True

# T7: review_router 决策
route_to = "output_node"

# T8: output_node 执行后
state.pbc_output_xlsx_path = "/tmp/output_abc_fy25.xlsx"
state.pbc_output_xlsx_b64 = "JVBLAw4KAAo..."

# T9: 图结束
# 最终 state 返回给 FastAPI 路由
# 路由提取 pbc_output_xlsx_b64，发送给前端
```

---

## LangGraph 核心概念

### 什么是 StateGraph？

```python
from langgraph.graph import StateGraph

# 1. 创建图
g = StateGraph(State)  # State 是 TypedDict，定义了图内流转的数据结构

# 2. 添加节点（每个节点是一个 Python 函数）
g.add_node("ingest_node", ingest_node)      # 函数签名：State → State
g.add_node("scope_diff_node", scope_diff_node)
# ...

# 3. 设置入口
g.set_entry_point("ingest_node")

# 4. 添加边（节点间的连接）
g.add_edge("ingest_node", "scope_diff_node")  # 线性连接

# 5. 条件边（根据 State 决定下一步）
g.add_conditional_edges(
    "scope_diff_node",           # 源节点
    scope_diff_router,           # 路由函数：State → str（目标节点名）
    {
        "update_items_node": "update_items_node",
        "output_node": "output_node",
    }
)

# 6. 编译成可执行的图
compiled = g.compile(checkpointer=SqliteSaver("checkpoints.db"))

# 7. 运行
result = compiled.invoke(initial_state, config={"configurable": {"thread_id": "..."}})
```

### 节点函数怎么写？

```python
def scope_diff_node(state: State) -> State:
    """
    节点函数必须：
      输入：State
      输出：State（或其子集 dict，LangGraph 自动合并）
    
    LangGraph 负责：
      - 从 state 中提取这个节点需要的字段
      - 节点返回后，merge 返回值回到 state
      - 传递给下一个节点
    """
    
    # 从 state 中读取
    scope_text = state["current_year_scope_text"]
    prior_items = state["prior_year_items"]
    
    # 调用 LLM
    response = claude.messages.create(
        model="claude-opus-4-5",
        messages=[
            {
                "role": "user",
                "content": f"""
                    Prior year items: {prior_items}
                    Current year scope: {scope_text}
                    Identify scope changes (new systems, removed systems, etc.)
                    Return as JSON: [...]
                """
            }
        ]
    )
    
    scope_changes = parse_json_response(response)
    
    # 返回更新的 state 子集
    return {
        "scope_changes": scope_changes,
        # 无需返回其他字段，LangGraph 会自动保留
    }
```

### interrupt/resume 是怎样的？

```python
# 在 review_node 中
def review_node(state: State) -> State:
    # 模拟人工审查暂停
    from langgraph.types import interrupt
    
    resume_value = interrupt(
        "Awaiting user review. Approve or reject with notes."
    )
    # 函数在这里挂起，不返回
    # State 持久化到 checkpointer（数据库）
    
    # [外部：用户在浏览器提交批准/拒绝]
    # [FastAPI 调用 graph.invoke(Command(resume=...))]
    # [LangGraph 从数据库恢复 state，继续执行]
    
    # 继续执行（从 interrupt 的地方）
    approved = resume_value.get("approved")
    
    return {
        "review_passed": approved,
    }
```

---

## MCP（Model Context Protocol）目前的位置

```
tools/
  __init__.py
  # 还未实现真正的 MCP server

在 Module C 审计访谈中，如果要启用 MCP：

def suggest_questions_node(state: State) -> State:
    
    client = anthropic.Anthropic()
    
    # Step 1: 第一次请求，告诉 Claude 有哪些工具可用
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=3000,
        tools=[
            {
                "type": "web_search_20250305",  # Anthropic 内置
                "name": "web_search"
            },
            # ... 其他自定义工具
        ],
        messages=[
            {
                "role": "user",
                "content": """
                当前 UAR 访谈：...
                标准问题库：...
                相关人员（知识图）：...
                建议下一个问题。如需要，可以查询标准。
                """
            }
        ]
    )
    
    # Step 2: 工具循环
    while response.stop_reason == "tool_use":
        # Claude 决定调用某个工具
        tool_use_block = next(block for block in response.content if block.type == "tool_use")
        
        # 执行工具
        if tool_use_block.name == "web_search":
            tool_result = web_search(tool_use_block.input["query"])
        elif tool_use_block.name == "standards_lookup":
            tool_result = standards_lookup(...)
        
        # 继续对话，告诉 Claude 工具的结果
        messages.append({"role": "assistant", "content": response.content})
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_block.id,
                    "content": tool_result
                }
            ]
        })
        
        # 再次请求
        response = client.messages.create(...)
    
    # Step 3: Claude 最终回复（不再需要工具）
    final_answer = next(
        block.text for block in response.content 
        if hasattr(block, "text")
    )
    
    return {
        "suggested_next_questions": final_answer.split("\n")
    }
```

---

## 总结：代码执行的三个关键时刻

| 时刻 | 发生什么 | 代码位置 |
|------|---------|---------|
| **请求进入** | 用户上传文件，FastAPI 创建初始 State，编译图 | `api/routes/pbc.py` |
| **图执行** | LangGraph 按节点顺序运行，State 经过管道；可能在 review_node 中断 | `modules/pbc/nodes.py` + `graph.py` |
| **响应返回** | 最终 State 的 pbc_output_xlsx_b64 发送给前端，前端下载 xlsx | `api/routes/pbc.py` + 前端 JS |

