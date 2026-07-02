# IT Audit Intelligence Platform — 程序员视角的整体逻辑

## 🎯 核心定位

这是一个**三模块 LangGraph 系统**，专为 IT 审计师自动化年度审计的三个高耗时流程：

1. **Module A：PBC 清单生成器** — 自动化生成年度审计证据请求清单
2. **Module B：IT 理解知识图谱** — 从散乱的证据文件自动提取 IT 环境实体和关系
3. **Module C：审计访谈助手** — 实时提示审计师交叉验证问题，跟踪覆盖率

---

## 📊 数据流架构（最重要）

```
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI 后端                              │
│                    (api/main.py + routes)                       │
└──────────────────────────────┬──────────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────────┐
        ▼                      ▼                          ▼
┌───────────────┐      ┌───────────────┐      ┌───────────────┐
│   Module A    │      │   Module B    │      │   Module C    │
│  PBC Graph    │      │  Understanding│      │  Walkthrough  │
│               │      │  Knowledge Map│      │  Assistant    │
│ (LangGraph)   │      │ (LangGraph)   │      │ (LangGraph)   │
└───────┬───────┘      └───────┬───────┘      └───────┬───────┘
        │                      │                      │
        ▼                      ▼                      ▼
    State ◄──────────────────  State ◄───────────── State
    (PBC Items,     (Entities +           (Topics + Questions
     xlsx)          Relations +            + Coverage)
                    HTML Map)
```

**关键点**：三个模块都操作同一个 `State` 对象（TypedDict），但各自只读写自己的字段切片。

---

## 🏗️ 代码组织

```
it-audit-intelligence/
│
├── core/
│   ├── state.py              ← 统一的 State TypedDict（所有模块共享）
│   └── llm.py                ← Anthropic 客户端包装
│
├── modules/
│   ├── pbc/                  ← Module A — PBC 生成
│   │   ├── graph.py          ← StateGraph + 节点定义
│   │   ├── nodes.py          ← 5 个节点的实现
│   │   ├── templates.py      ← 标准 PBC 模板（系统类型）
│   │   └── xlsx_io.py        ← Excel 读写（openpyxl）
│   │
│   ├── understanding/        ← Module B — 知识图谱
│   │   ├── graph.py
│   │   ├── nodes.py          ← 实体提取 + 关系推断
│   │   └── render.py         ← vis-network HTML 渲染
│   │
│   └── walkthrough/          ← Module C — 审计访谈
│       ├── graph.py
│       ├── nodes.py          ← RAG + 问题建议 + 答案日志
│       └── rag.py            ← 分块 + 向量检索
│
├── api/
│   ├── main.py               ← FastAPI 应用 + 路由注册
│   ├── schemas.py            ← Pydantic 请求/响应
│   ├── checkpointer.py       ← LangGraph 状态存储
│   ├── database.py           ← 审计运行历史（SQLite/PostgreSQL）
│   └── routes/
│       ├── pbc.py            ← POST /api/pbc/generate
│       ├── understanding.py  ← POST /api/understanding/build
│       ├── email.py          ← 通过 Resend 发送 xlsx
│       ├── history.py        ← 运行历史管理
│       ├── review.py         ← 人工审查 API
│       └── config.py         ← LLM 配置开关
│
├── tools/                    ← MCP 工具（未来扩展）
│   └── __init__.py
│
├── frontend/
│   ├── index.html            ← 登陆页面（三个模块切换）
│   ├── pbc.html              ← Module A UI
│   ├── understanding.html    ← Module B UI
│   └── walkthrough.html      ← Module C UI
│
├── data/
│   ├── sample_client_FY2024/ ← 演示数据
│   ├── golden/               ← 黄金数据集（精准度评估）
│   └── output/               ← 运行输出
│
└── tests/
    ├── pbc/                  ← Module A 单元测试
    └── e2e/                  ← 端到端测试
```

---

## 🔧 Module A（PBC 生成）— 核心逻辑

### State 切片

```python
class State(TypedDict):
    # ── 输入
    prior_year_pbc_path: str         # 去年的 xlsx 文件路径
    current_year_scope_text: str     # 今年的审计范围备忘录（纯文本）
    
    # ── 处理结果
    prior_year_items: List[PBCItem]  # 解析的去年清单
    scope_changes: List[ScopeChange] # Claude 识别的范围变化
    current_year_items: List[PBCItem]# 最终的今年清单
    
    # ── 输出
    pbc_output_xlsx_path: str
    pbc_output_xlsx_b64: str         # Base64，用于 HTTP 下载
    
    # ── 流程控制
    review_passed: bool              # 人工审查是否通过
```

### 5 个节点的数据流

```
ingest_node
  输入：prior_year_pbc_path, current_year_scope_text
  输出：prior_year_items, current_year_scope_text（验证）
  实现：xlsx_io.read_pbc_xlsx() 解析去年清单
       
         ▼
         
scope_diff_node
  输入：prior_year_items, current_year_scope_text
  输出：scope_changes: List[ScopeChange]
  实现：Claude 分析今年范围备忘录 vs 去年，识别：
       - 新增系统 (system_added)
       - 删除系统 (system_removed)
       - 审计期变化 (period_change)
       - 监管变化 (regulation_change)
       - 样本量变化 (sample_size_change)
  
  路由逻辑：
    if scope_changes 非空 → update_items_node
    else                → output_node (直接使用去年清单)
    
         ▼
         
update_items_node
  输入：prior_year_items, scope_changes
  输出：current_year_items (每项带 status 标记)
  实现：对每个去年项目，Claude 决策：
       - "carried_over" — 保留
       - "updated"      — 更新描述
       - "removed"      — 删除
       
       对每个 scope_change，从 templates.py 生成新项：
       - 新系统 → 加载该系统类型的标准 PBC 模板
       - 每个影响类别 → 新增 PBC 项
       
         ▼
         
review_node
  输入：current_year_items
  实现：中断点 (LangGraph interrupt)
       如果有 checkpointer，暂停并等待：
       - HTTP 请求：{"approved": True}  → 继续
       - HTTP 请求：{"approved": False, "notes": "..."} → 回到 update_items
       
       无 checkpointer 时：auto-approve
       
  路由逻辑：
    if review_passed     → output_node
    else review_rejected → update_items_node (修改循环)
    
         ▼
         
output_node
  输入：current_year_items
  输出：pbc_output_xlsx_path, pbc_output_xlsx_b64
  实现：xlsx_io.write_pbc_xlsx() 写回 xlsx
       - 去年项目加上 status 色码
       - 新项加上 "NEW" 标记
       - 删除项加上 "REMOVED" 标记
```

### 为什么要 LangGraph？

- **有状态**：从 review_node 中断，稍后恢复 → 需要序列化状态
- **有循环**：rejection → loop back to update → 条件路由
- **有人工干预点**：review 中的 interrupt() 不是 LCEL 能表达的

---

## 📦 Module B（知识图谱）— 逻辑

### State 切片

```python
class State(TypedDict):
    evidence_paths: List[str]               # docx/pdf 路径
    extracted_entities: List[ITEntity]      # 节点：系统、人员、过程等
    entity_relationships: List[EntityRelationship]  # 边：谁拥有什么、依赖关系
    map_output_html_path: str               # vis-network 可视化
```

### 3 个节点

```
extract_entities_node
  输入：evidence_paths
  输出：extracted_entities
  实现：Claude 读取所有证据文件，提取：
       - 系统（SAP、Oracle、Azure）
       - 人员（CIO、系统所有者）
       - 过程（JML、UAR、变更）
       - 供应商（AWS、Microsoft）
       - 地点（数据中心）
       
         ▼
         
infer_relations_node
  输入：extracted_entities + 证据原文
  输出：entity_relationships
  实现：Claude 读取实体 + 原文，推断边：
       - owns, runs_on, processes, depends_on, reviewed_by
       - 每条边带 confidence: 0-1 和 evidence_quote
       
         ▼
         
render_map_node
  输入：extracted_entities + entity_relationships
  输出：map_output_html_path
  实现：vis-network 库生成单文件 HTML，在浏览器中交互探索知识图
```

---

## 💬 Module C（审计访谈）— 逻辑

### State 切片

```python
class State(TypedDict):
    walkthrough_topics: List[WalkthroughTopic]  # 6 个审计领域（JML、UAR等）
    current_topic_id: Optional[str]
    suggested_next_questions: List[str]
```

### 核心流程

```
retrieve_context_node
  输入：current_topic_id + evidence files（通过 RAG）
  输出：相关证据块 + 去年发现
  实现：
    - 证据按审计领域分块
    - 嵌入向量 → 检索 top-k 块
    
         ▼
         
suggest_questions_node
  输入：retrieved context + ITGC 标准问题库 + Module B 知识图
  输出：suggested_next_questions
  实现：Claude 代理读取：
       - 上下文（今年访谈进度、去年发现）
       - 标准 ITGC 问题清单
       - 知识图中的相关实体（"UAR 操作员是 Bob，他也管理...")
       → 建议下一步问题
       
         ▼
         
log_answer_node
  输入：auditor_answer（从前端输入）
  输出：更新 coverage_status，进度跟踪
  实现：记录答案 + 更新 WalkthroughTopic.coverage_status
       → 回到 retrieve_context（下一个话题）
       
  路由逻辑：
    if walkthrough_complete → END
    else                   → retrieve_context (下一话题)
```

---

## 🔌 API 层（FastAPI）

### 请求 → 图运行 → 响应

```python
# POST /api/pbc/generate
{
  "client_name": "ABC Corp",
  "audit_period": "FY2025",
  "prior_year_pbc_path": "/data/abc_fy24.xlsx",
  "current_year_scope_text": "FY2025 audit scope: SAP newly in scope..."
}

↓ 路由 (routes/pbc.py)

async def generate_pbc(req: GeneratePBCRequest):
    state = default_state(
        client_name=req.client_name,
        audit_period=req.audit_period,
        prior_year_pbc_path=req.prior_year_pbc_path,
        current_year_scope_text=req.current_year_scope_text,
    )
    
    graph = build_compiled_graph(checkpointer=get_checkpointer())
    config = {"configurable": {"thread_id": req.client_name + "_" + req.audit_period}}
    
    try:
        result = graph.invoke(state, config)
    except GraphInterrupt:
        # review_node 中断 → 存储到数据库
        save_run_to_db(thread_id, state)
        return {"status": "awaiting_review", "thread_id": thread_id}
    
    # 运行完成
    xlsx_b64 = result["pbc_output_xlsx_b64"]
    return {
        "status": "complete",
        "xlsx_base64": xlsx_b64,
        "filename": f"{req.client_name}_{req.audit_period}_pbc.xlsx"
    }

↓ 前端

下载 xlsx 或继续审查
```

### 人工审查流（interrupt/resume）

```python
# POST /api/review/approve/{thread_id}
{
  "approved": True,
  "notes": "LGTM"
}

↓

graph.invoke(Command(resume=result), config)
# → review_node 恢复 → 继续 output_node

# POST /api/review/reject/{thread_id}
{
  "approved": False,
  "notes": "请加入 SAP JML 检查项"
}

↓

graph.invoke(Command(resume=result), config)
# → review_node 恢复 → 回到 update_items_node（修改循环）
```

---

## 🛠️ MCP 现状（Model Context Protocol）

**当前状态**：`tools/` 目录已定义但未集成

```python
# tools/__init__.py 中应该定义的
- web_search_tool         # Anthropic web_search_20250305
- doc_parser_tool         # PDF/docx 文本提取
- standards_lookup_tool   # ISO 27001 / NIST 查询
```

**为什么需要 MCP**：
- Module C 审计访谈时，auditor 提起某个控制 → Claude 需要动态查询 NIST CSF 定义
- 硬编码 "if user mentions X, fetch Y" 太脆弱
- MCP 让 Claude **自主决策**何时调用工具

**集成方式**（将来）：

```python
# modules/walkthrough/nodes.py 中

def suggest_questions_node(state: State):
    client = anthropic.Anthropic()
    
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=3000,
        tools=[
            {"type": "web_search_20250305"},
            {"type": "doc_parser"},
            {"type": "standards_lookup"}
        ],
        messages=[...]
    )
    
    # Claude 自主决策何时调用工具
    while response.stop_reason == "tool_use":
        tool_results = [...]
        # 继续循环
```

---

## 📋 关键设计决策

| 决策 | 原因 | 权衡 |
|------|------|------|
| **TypedDict State** | 单一数据源 + IDE 自动完成 | 无运行时强制（用 default_state()） |
| **LangGraph StateGraph** | 显式状态 + 条件路由 + 检查点 | 比 LCEL 更冗长 |
| **SqliteSaver checkpointer** | 持久化中断点 | 多进程需要 PostgresSaver |
| **MCP 工具** | 自主工具调用 | 还未集成；需要异步工具循环 |
| **FastAPI 后端** | 安全存储 API key + 统一接口 | 额外网络跳跃 |
| **3 个独立模块** | 各自可独立运行 + 可重用 | Module B/C 依赖 Module A 的产出 |

---

## 🧪 测试策略

### 单元测试（task-level）

```python
# tests/pbc/test_scope_diff.py

def test_scope_diff_detects_new_system():
    """Task：范围备忘录说 SAP 新加入 → scope_changes 包含 system_added"""
    state = {
        "current_year_scope_text": "SAP S/4HANA 于 1 月新增...",
        "audit_period": "FY2025",
        ...
    }
    result = scope_diff_node(state)
    changes = result["scope_changes"]
    assert any(c["change_type"] == "system_added" and "SAP" in c["description"] for c in changes)
```

### 黄金数据集（precision/recall）

```
data/golden/
  case_01/
    input_prior_pbc.xlsx
    input_scope_memo.txt
    expected_scope_changes.json
    expected_current_pbc.xlsx
  ...
  case_10/
```

运行 `test_precision_recall.py` 对比 Claude 识别 vs 手工标注的准确率。

---

## 🚀 运行命令

```bash
# 后端
uvicorn api.main:app --reload --port 8000

# Module A CLI
python run_pbc.py \
  --prior data/sample_client_FY2024/pbc_list.xlsx \
  --scope "FY2025 audit scope: SAP newly in scope..."

# 前端（开发）
python -m http.server 8080
# open http://localhost:8080/frontend/index.html

# 测试
pytest tests/ -v
```

---

## 💡 面试亮点总结

| 话题 | 简短版本 |
|------|---------|
| **为什么 LangGraph** | "三个模块都有循环和持久化状态需求，LCEL 是无状态的。LangGraph 的 StateGraph + interrupt/resume + checkpointing 完美匹配这个需求。" |
| **统一 State 设计** | "一个 TypedDict 覆盖所有三个模块，下游模块可重用上游的产出（Module B 的知识图成为 Module C 的跨参考）。" |
| **MCP 价值** | "Module C 访谈时需要动态查询标准（ISO 27001 控制定义）。MCP 让 Claude 自主决策何时调用工具，而不是硬编码规则。" |
| **ROI** | "每个审计案例：PBC 准备从 4 小时降到 30 分钟，理解图从 2 天降到 2 小时。50 个案例/年 = 可衡量的顾问产能释放。" |

