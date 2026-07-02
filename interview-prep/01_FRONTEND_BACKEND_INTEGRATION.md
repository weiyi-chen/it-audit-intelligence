# 前后端集成完全讲解 — 从代码看数据流

> 目标：真正理解一个 HTTP 请求从前端发出，到后端处理，再返回的整个过程

---

## 第 1 部分：前端 HTML + JavaScript（看这个就够）

### 前端文件：`frontend/pbc.html`

```html
<!DOCTYPE html>
<html>
<head>
    <title>IT Audit Intelligence - PBC Generator</title>
</head>
<body>
    <h1>Module A: PBC Checklist Generator</h1>
    
    <!-- ── 步骤 1：用户输入 ────────────────────────────────── -->
    <div id="input-section">
        <label>Client Name:</label>
        <input type="text" id="clientName" placeholder="e.g., ABC Corp">
        
        <label>Audit Period:</label>
        <input type="text" id="auditPeriod" placeholder="e.g., FY2025">
        
        <label>Prior Year PBC (xlsx):</label>
        <input type="file" id="priorPbcFile" accept=".xlsx">
        
        <label>Current Year Scope (memo):</label>
        <textarea id="scopeText" placeholder="Paste the scope memo here..."></textarea>
        
        <button onclick="generatePBC()">Generate PBC</button>
    </div>
    
    <!-- ── 步骤 2：进度显示 ────────────────────────────────── -->
    <div id="progress-section" style="display:none;">
        <p>⏳ Processing... <span id="status">Initializing graph...</span></p>
        <div id="progressBar"></div>
    </div>
    
    <!-- ── 步骤 3：结果显示 ────────────────────────────────── -->
    <div id="result-section" style="display:none;">
        <div id="review-section" style="display:none;">
            <h2>⚠️ Awaiting Review</h2>
            <p>The PBC list has been generated. Please review:</p>
            <button onclick="approvePBC()">✅ Approve & Download</button>
            <button onclick="rejectPBC()">❌ Reject & Edit</button>
            <textarea id="reviewNotes" placeholder="Add notes..."></textarea>
        </div>
        
        <div id="complete-section" style="display:none;">
            <h2>✅ Complete!</h2>
            <button onclick="downloadXLSX()">📥 Download PBC List</button>
            <button onclick="emailPBC()">📧 Send Email</button>
        </div>
    </div>

    <script>
// ═══════════════════════════════════════════════════════════════════════════
// 核心函数 1：生成 PBC 清单
// ═══════════════════════════════════════════════════════════════════════════

async function generatePBC() {
    // ── 第 1 步：读取用户输入 ────────────────────────────────
    const clientName = document.getElementById("clientName").value;
    const auditPeriod = document.getElementById("auditPeriod").value;
    const scopeText = document.getElementById("scopeText").value;
    const priorPbcFile = document.getElementById("priorPbcFile").files[0];
    
    // 验证输入
    if (!clientName || !auditPeriod || !scopeText || !priorPbcFile) {
        alert("Please fill in all fields");
        return;
    }
    
    // ── 第 2 步：读取 xlsx 文件（浏览器端） ───────────────────
    // 注意：我们这里只是读取文件名，实际的解析在后端做
    // （前端可以用 xlsx.js 库解析，但为了简单我们让后端处理）
    
    console.log("📤 Sending request to backend...");
    console.log("  Client:", clientName);
    console.log("  Period:", auditPeriod);
    console.log("  Scope text length:", scopeText.length);
    
    // ── 第 3 步：构建请求体 ────────────────────────────────
    const requestBody = {
        client_name: clientName,
        audit_period: auditPeriod,
        prior_year_pbc_path: "/data/sample_client_FY2024/pbc_list.xlsx",  // 实际上应该上传文件，这里简化
        current_year_scope_text: scopeText
    };
    
    console.log("📋 Request body:", JSON.stringify(requestBody, null, 2));
    
    // ── 第 4 步：显示进度条 ────────────────────────────────
    document.getElementById("input-section").style.display = "none";
    document.getElementById("progress-section").style.display = "block";
    
    // ── 第 5 步：发送 HTTP POST 请求到后端 ─────────────────
    try {
        const response = await fetch("http://localhost:8000/api/pbc/generate", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(requestBody)
        });
        
        console.log("📥 Response status:", response.status);
        
        // ── 第 6 步：解析后端响应 ────────────────────────────
        const data = await response.json();
        
        console.log("📦 Response data:", data);
        
        // ── 第 7 步：根据状态显示不同的 UI ──────────────────
        if (data.status === "complete") {
            // 图执行完成，返回了 xlsx
            console.log("✅ Graph execution complete!");
            handleComplete(data);
        } else if (data.status === "awaiting_review") {
            // 图在 review_node 中断了，等待人工审查
            console.log("⏸️ Graph paused at review_node");
            handleAwaitingReview(data);
        } else {
            console.error("❌ Unknown status:", data.status);
            alert("Unexpected response status: " + data.status);
        }
    } catch (error) {
        console.error("❌ Error:", error);
        alert("Error: " + error.message);
        document.getElementById("progress-section").style.display = "none";
        document.getElementById("input-section").style.display = "block";
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// 核心函数 2：处理"等待审查"状态（图中断了）
// ═══════════════════════════════════════════════════════════════════════════

function handleAwaitingReview(data) {
    // data = { status: "awaiting_review", thread_id: "ABC Corp_FY2025" }
    
    // 保存 thread_id 到全局变量（后面恢复用）
    window.currentThreadId = data.thread_id;
    
    // 隐藏进度条，显示审查界面
    document.getElementById("progress-section").style.display = "none";
    document.getElementById("result-section").style.display = "block";
    document.getElementById("review-section").style.display = "block";
    document.getElementById("complete-section").style.display = "none";
    
    console.log("🔄 Waiting for user review. Thread ID:", data.thread_id);
}

// ═══════════════════════════════════════════════════════════════════════════
// 核心函数 3：用户批准 PBC 清单
// ═══════════════════════════════════════════════════════════════════════════

async function approvePBC() {
    // ── 第 1 步：读取用户的审查意见 ──────────────────────────
    const notes = document.getElementById("reviewNotes").value;
    
    console.log("✅ User approved! Notes:", notes);
    
    // ── 第 2 步：构建"恢复"请求体 ──────────────────────────
    const requestBody = {
        approved: true,
        notes: notes
    };
    
    // ── 第 3 步：发送 HTTP POST 请求到 /api/review/approve ──
    // 注意：URL 中包含 thread_id，所以后端知道恢复哪个图
    try {
        const response = await fetch(
            `http://localhost:8000/api/review/approve/${window.currentThreadId}`,
            {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(requestBody)
            }
        );
        
        const data = await response.json();
        console.log("📦 Response:", data);
        
        // ── 第 4 步：显示完成状态，允许下载 ──────────────────
        if (data.status === "complete") {
            // 后端恢复了图，现在返回最终的 xlsx_base64
            window.xlsxData = {
                base64: data.xlsx_base64,
                filename: data.filename
            };
            
            handleComplete(data);
        } else {
            alert("Unexpected status: " + data.status);
        }
    } catch (error) {
        console.error("❌ Error:", error);
        alert("Error during approval: " + error.message);
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// 核心函数 4：处理"完成"状态
// ═══════════════════════════════════════════════════════════════════════════

function handleComplete(data) {
    // data = {
    //   status: "complete",
    //   xlsx_base64: "JVBLAw4KAAo...",
    //   filename: "ABC Corp_FY2025_pbc.xlsx"
    // }
    
    // 保存 xlsx 数据到全局变量
    window.xlsxData = {
        base64: data.xlsx_base64,
        filename: data.filename
    };
    
    // 显示完成界面
    document.getElementById("progress-section").style.display = "none";
    document.getElementById("review-section").style.display = "none";
    document.getElementById("complete-section").style.display = "block";
    document.getElementById("result-section").style.display = "block";
    
    console.log("🎉 Complete! Ready to download:", data.filename);
}

// ═══════════════════════════════════════════════════════════════════════════
// 核心函数 5：下载 XLSX 文件
// ═══════════════════════════════════════════════════════════════════════════

function downloadXLSX() {
    if (!window.xlsxData) {
        alert("No data to download");
        return;
    }
    
    // ── 第 1 步：解码 Base64 为二进制 ───────────────────────
    const binaryString = atob(window.xlsxData.base64);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    
    // ── 第 2 步：创建 Blob（浏览器可下载的二进制对象） ────
    const blob = new Blob([bytes], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    });
    
    // ── 第 3 步：创建临时下载链接并触发 ──────────────────
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = window.xlsxData.filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    console.log("📥 Downloaded:", window.xlsxData.filename);
}

// ═══════════════════════════════════════════════════════════════════════════
// 辅助函数：拒绝并编辑
// ═══════════════════════════════════════════════════════════════════════════

async function rejectPBC() {
    const notes = document.getElementById("reviewNotes").value;
    
    console.log("❌ User rejected. Notes:", notes);
    
    const requestBody = {
        approved: false,
        notes: notes
    };
    
    try {
        const response = await fetch(
            `http://localhost:8000/api/review/approve/${window.currentThreadId}`,
            {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(requestBody)
            }
        );
        
        const data = await response.json();
        
        if (data.status === "awaiting_review") {
            // 图回到了 update_items_node，已经修改，再等待审查
            console.log("🔄 Graph loop: back to update_items, awaiting next review");
            alert("PBC has been updated. Awaiting next review...");
            // 保持审查界面，用户可以再次审查
        } else if (data.status === "complete") {
            handleComplete(data);
        }
    } catch (error) {
        console.error("❌ Error:", error);
        alert("Error during rejection: " + error.message);
    }
}

    </script>
</body>
</html>
```

---

## 第 2 部分：后端 FastAPI（重要）

### 后端文件：`api/routes/pbc.py`

```python
"""
后端路由：处理 HTTP 请求，调用 LangGraph
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import os
import logging

# ── 导入 LangGraph 相关 ───────────────────────────────────
from modules.pbc.graph import build_compiled_graph
from api.checkpointer import get_checkpointer
from core.state import State, default_state
from langgraph.types import Command

logger = logging.getLogger(__name__)
router = APIRouter()

# ═══════════════════════════════════════════════════════════════════════════
# 定义请求和响应的数据结构
# ═══════════════════════════════════════════════════════════════════════════

class GeneratePBCRequest(BaseModel):
    """前端发送的请求"""
    client_name: str
    audit_period: str
    prior_year_pbc_path: str
    current_year_scope_text: str

class GeneratePBCResponse(BaseModel):
    """后端返回的响应"""
    status: str  # "complete" or "awaiting_review"
    xlsx_base64: Optional[str] = None
    thread_id: Optional[str] = None
    filename: Optional[str] = None

# ═══════════════════════════════════════════════════════════════════════════
# 端点 1：POST /api/pbc/generate
#
# 前端流程：
#   1. 用户填表、点击"Generate"
#   2. 前端 fetch POST /api/pbc/generate
#   3. 后端处理（这个函数）
#   4. 后端返回：要么"complete"，要么"awaiting_review"
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/api/pbc/generate")
async def generate_pbc(req: GeneratePBCRequest) -> GeneratePBCResponse:
    """
    生成 PBC 清单。
    
    请求体：{client_name, audit_period, prior_year_pbc_path, scope_text}
    响应：
      - status="complete" + xlsx_base64 + filename
      - status="awaiting_review" + thread_id
    """
    
    print(f"🔵 [POST /api/pbc/generate] Received request")
    print(f"   client_name={req.client_name}")
    print(f"   audit_period={req.audit_period}")
    
    try:
        # ── 第 1 步：验证输入 ────────────────────────────────
        if not os.path.exists(req.prior_year_pbc_path):
            raise HTTPException(
                status_code=400,
                detail=f"File not found: {req.prior_year_pbc_path}"
            )
        
        print(f"✅ Input validation passed")
        
        # ── 第 2 步：创建初始 State ──────────────────────────
        state = default_state(
            client_name=req.client_name,
            audit_period=req.audit_period,
            thread_id=f"{req.client_name}_{req.audit_period}",
        )
        
        state["prior_year_pbc_path"] = req.prior_year_pbc_path
        state["current_year_scope_text"] = req.current_year_scope_text
        
        print(f"✅ State initialized: {list(state.keys())}")
        
        # ── 第 3 步：编译 LangGraph ──────────────────────────
        checkpointer = get_checkpointer()  # 获取持久化器
        graph = build_compiled_graph(checkpointer=checkpointer)
        
        print(f"✅ Graph compiled")
        
        # ── 第 4 步：运行 LangGraph ──────────────────────────
        config = {
            "configurable": {
                "thread_id": state["thread_id"]
            }
        }
        
        print(f"🟢 [Graph Invocation] Invoking graph with thread_id={state['thread_id']}")
        
        # 关键：调用 graph.invoke()
        # 这会运行所有节点，直到遇到 interrupt() 或 END
        result = graph.invoke(state, config)
        
        print(f"✅ Graph execution completed without interrupt")
        
        # ── 第 5 步：处理"完成"状态 ──────────────────────────
        # 如果到这里，说明图完成了（没有中断）
        return GeneratePBCResponse(
            status="complete",
            xlsx_base64=result.get("pbc_output_xlsx_b64"),
            filename=f"{req.client_name}_{req.audit_period}_pbc.xlsx",
        )
    
    except Exception as e:
        # ── 异常情况：Graph 在 review_node 中断了 ──────────
        if "interrupt" in str(type(e)).lower() or "GraphInterrupt" in str(type(e)):
            print(f"⚠️ [Graph Interrupt] Graph paused at review_node")
            
            # 这里我们不返回异常，而是返回"awaiting_review"状态
            # 实际上，LangGraph 会自动处理中断，不会抛异常
            # 我们直接返回响应
            
            return GeneratePBCResponse(
                status="awaiting_review",
                thread_id=state.get("thread_id"),
            )
        else:
            # 真正的错误
            print(f"❌ [Error] {str(e)}")
            logger.error(f"Error in generate_pbc: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

# ═══════════════════════════════════════════════════════════════════════════
# 端点 2：POST /api/review/approve/{thread_id}
#
# 前端流程：
#   1. 图在 review_node 中断，显示审查界面
#   2. 用户点击"批准"或"拒绝"
#   3. 前端 fetch POST /api/review/approve/{thread_id}
#   4. 后端恢复图执行
#   5. 后端返回最终结果
# ═══════════════════════════════════════════════════════════════════════════

class ReviewRequest(BaseModel):
    """用户的审查决定"""
    approved: bool
    notes: Optional[str] = None

@router.post("/api/review/approve/{thread_id}")
async def approve_review(thread_id: str, req: ReviewRequest) -> GeneratePBCResponse:
    """
    恢复图执行。
    
    请求体：{approved: bool, notes: str}
    响应：
      - status="complete" + xlsx_base64（如果批准）
      - status="awaiting_review" + thread_id（如果拒绝，图回到 update）
    """
    
    print(f"🔵 [POST /api/review/approve/{thread_id}]")
    print(f"   approved={req.approved}")
    print(f"   notes={req.notes[:50] if req.notes else 'None'}...")
    
    try:
        # ── 第 1 步：获取持久化器并重新编译图 ──────────────
        checkpointer = get_checkpointer()
        graph = build_compiled_graph(checkpointer=checkpointer)
        
        # ── 第 2 步：构建"恢复"命令 ──────────────────────────
        resume_value = {
            "approved": req.approved,
            "notes": req.notes or "",
        }
        
        # ── 第 3 步：恢复图执行 ──────────────────────────────
        config = {
            "configurable": {
                "thread_id": thread_id  # 关键：使用相同的 thread_id
            }
        }
        
        print(f"🟢 [Graph Resume] Resuming graph with thread_id={thread_id}")
        print(f"   LangGraph 会从 checkpointer 恢复之前保存的状态")
        
        # 关键：使用 Command(resume=...) 而不是普通的 state
        result = graph.invoke(
            Command(resume=resume_value),
            config
        )
        
        print(f"✅ Graph resumed and completed")
        
        # ── 第 4 步：返回最终结果 ────────────────────────────
        return GeneratePBCResponse(
            status="complete",
            xlsx_base64=result.get("pbc_output_xlsx_b64"),
            filename=f"{thread_id}_pbc.xlsx",
        )
    
    except Exception as e:
        # 如果图又中断了（拒绝情况）
        if "interrupt" in str(type(e)).lower():
            print(f"⚠️ [Graph Interrupt Again] Graph loop back to update_items")
            return GeneratePBCResponse(
                status="awaiting_review",
                thread_id=thread_id,
            )
        else:
            print(f"❌ [Error] {str(e)}")
            logger.error(f"Error in approve_review: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
```

---

## 第 3 部分：前后端连接流程图

### 场景 A：正常流程（审查通过）

```
┌────────────────────────────────────────────────────────────────┐
│                         浏览器（前端）                          │
└────────────────────────────────────────────────────────────────┘

用户填表 → 点击"Generate"

    ▼

function generatePBC() {
  const requestBody = {
    client_name: "ABC Corp",
    audit_period: "FY2025",
    scope_text: "..."
  }
  
  fetch("http://localhost:8000/api/pbc/generate", {
    method: "POST",
    body: JSON.stringify(requestBody)
  })
}

    │ HTTP POST /api/pbc/generate
    │ (JSON 请求体)
    ▼

┌────────────────────────────────────────────────────────────────┐
│                      FastAPI 后端服务                           │
│                  (localhost:8000)                              │
└────────────────────────────────────────────────────────────────┘

@router.post("/api/pbc/generate")
async def generate_pbc(req: GeneratePBCRequest):
    
    ① 创建初始 State:
       state = default_state(
           client_name="ABC Corp",
           audit_period="FY2025",
           prior_year_items=[],
           scope_changes=[],
           ...
       )
    
    ② 获取 checkpointer（持久化器）
       checkpointer = get_checkpointer()
    
    ③ 编译图
       graph = build_compiled_graph(checkpointer=checkpointer)
    
    ④ 执行图
       result = graph.invoke(state, config)
       
       ┌─────────────────────────────────────────┐
       │      LangGraph 执行节点序列              │
       │                                         │
       │  ingest_node                           │
       │    读 prior_year.xlsx                  │
       │    输出：prior_year_items              │
       │       ▼                                 │
       │  scope_diff_node                       │
       │    Claude 分析范围变化                 │
       │    输出：scope_changes                 │
       │       ▼                                 │
       │  scope_diff_router                     │
       │    有变化？→ update_items_node         │
       │       ▼                                 │
       │  update_items_node                     │
       │    Claude 更新清单项                   │
       │    输出：current_year_items            │
       │       ▼                                 │
       │  review_node                           │
       │    CALL interrupt()  ← 图暂停！        │
       │    state 持久化到 checkpointer         │
       │    返回给 HTTP 处理器                  │
       └─────────────────────────────────────────┘
    
    ⑤ 返回响应
       return {
           status: "awaiting_review",
           thread_id: "ABC Corp_FY2025"
       }

    │ HTTP 200 (JSON 响应)
    │ ← 前端收到
    ▼

┌────────────────────────────────────────────────────────────────┐
│                      浏览器（前端）                             │
└────────────────────────────────────────────────────────────────┘

handleAwaitingReview(data) {
  // data.thread_id = "ABC Corp_FY2025"
  
  显示审查界面：
  - "PBC 清单已生成，请审查"
  - 按钮："✅ Approve"  "❌ Reject"
}

用户阅读 PBC，点击"✅ Approve"

    ▼

function approvePBC() {
  const requestBody = {
    approved: true,
    notes: "LGTM"
  }
  
  fetch(
    "http://localhost:8000/api/review/approve/ABC Corp_FY2025",
    {
      method: "POST",
      body: JSON.stringify(requestBody)
    }
  )
}

    │ HTTP POST /api/review/approve/{thread_id}
    │ (JSON 请求体)
    ▼

┌────────────────────────────────────────────────────────────────┐
│                      FastAPI 后端服务                           │
└────────────────────────────────────────────────────────────────┘

@router.post("/api/review/approve/{thread_id}")
async def approve_review(thread_id, req):
    
    ① 获取 checkpointer
       checkpointer = get_checkpointer()
    
    ② 重新编译图（相同的图）
       graph = build_compiled_graph(checkpointer=checkpointer)
    
    ③ 从 checkpointer 恢复之前的状态
       config = {
           "configurable": {"thread_id": "ABC Corp_FY2025"}
       }
       
       ┌─────────────────────────────────────────┐
       │      LangGraph 恢复执行                  │
       │                                         │
       │  从数据库读取保存的 state               │
       │  找到 review_node 中的 interrupt()     │
       │  从那里继续执行                        │
       │       ▼                                 │
       │  review_node 恢复                      │
       │    approved = True                     │
       │    输出：review_passed=True            │
       │       ▼                                 │
       │  review_router                         │
       │    review_passed=True? → output_node   │
       │       ▼                                 │
       │  output_node                           │
       │    将 current_year_items 写为 xlsx    │
       │    编码为 Base64                       │
       │    输出：pbc_output_xlsx_b64          │
       │       ▼                                 │
       │      END                               │
       └─────────────────────────────────────────┘
    
    ④ 返回最终响应
       return {
           status: "complete",
           xlsx_base64: "JVBLAw4KAAo...",  ← 实际的 xlsx 数据
           filename: "ABC Corp_FY2025_pbc.xlsx"
       }

    │ HTTP 200 (JSON 响应)
    │ ← 前端收到
    ▼

┌────────────────────────────────────────────────────────────────┐
│                      浏览器（前端）                             │
└────────────────────────────────────────────────────────────────┘

handleComplete(data) {
  // data.xlsx_base64 = "JVBLAw4KAAo..."
  
  window.xlsxData = {
    base64: data.xlsx_base64,
    filename: data.filename
  }
  
  显示完成界面：
  - "✅ Complete!"
  - 按钮："📥 Download PBC List"  "📧 Send Email"
}

用户点击"📥 Download"

    ▼

function downloadXLSX() {
  // ① 解码 Base64 为二进制
  const binaryString = atob(window.xlsxData.base64);
  
  // ② 创建 Blob（浏览器的二进制对象）
  const blob = new Blob([bytes], {
    type: "application/vnd.openxmlformats-..."
  });
  
  // ③ 触发下载
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  
  ← 浏览器下载对话框弹出
  ← 文件保存到本地
}

完成！ ✅
```

### 场景 B：拒绝流程（用户拒绝）

```
[同上，直到用户点击"❌ Reject"]

    ▼

function rejectPBC() {
  const requestBody = {
    approved: false,
    notes: "需要添加 SAP JML 检查项"
  }
  
  fetch(
    "http://localhost:8000/api/review/approve/ABC Corp_FY2025",
    {
      method: "POST",
      body: JSON.stringify(requestBody)
    }
  )
}

    │ HTTP POST /api/review/approve/{thread_id}
    ▼

@router.post("/api/review/approve/{thread_id}")
async def approve_review(...):
    
    从 checkpointer 恢复状态
    
    ┌─────────────────────────────────────────┐
    │      LangGraph 恢复执行                  │
    │                                         │
    │  review_node 恢复                      │
    │    approved = False  ← 关键！          │
    │    输出：review_passed=False           │
    │       ▼                                 │
    │  review_router                         │
    │    review_passed=False?                │
    │    → update_items_node  ← 回到这里！   │
    │                         (拒绝循环)      │
    │       ▼                                 │
    │  update_items_node                     │
    │    Claude 使用 notes="需要添加 SAP..."  │
    │    重新生成清单项                      │
    │    输出：current_year_items(更新)      │
    │       ▼                                 │
    │  review_node                           │
    │    CALL interrupt() ← 再次暂停！        │
    │    state(新的) 持久化到 checkpointer    │
    │    返回给 HTTP 处理器                  │
    └─────────────────────────────────────────┘
    
    return {
        status: "awaiting_review",
        thread_id: "ABC Corp_FY2025"  ← 相同的 thread_id
    }

    ▼

前端显示审查界面（再次）
用户看到更新后的 PBC
用户再次点击"✅ Approve"

    ▼

[流程循环，直到 approved=true]
```

---

## 第 4 部分：数据流细节（关键概念）

### 问题 1：为什么前端不能直接读 xlsx 文件？

```
前端 (JavaScript):
  - 运行在浏览器沙箱中
  - 无法访问客户端的本地文件（安全限制）
  - 无法调用 Python 库（openpyxl）
  - 无法访问模型（Claude API）

所以：
  前端的职责 = UI 和用户交互
  后端的职责 = 业务逻辑（读 xlsx、调 Claude、写 xlsx）
```

### 问题 2：Thread ID 的作用是什么？

```
ThreadId = "ABC Corp_FY2025"

作用 1：标识一次审计
  │
  ├─ ingest_node 运行，state → checkpointer
  ├─ scope_diff_node 运行，state → checkpointer
  ├─ update_items_node 运行，state → checkpointer
  ├─ review_node 中断，最终 state → checkpointer
  │
  └─ HTTP 请求 1 返回："awaiting_review"，但状态在数据库里

作用 2：恢复点
  │
  └─ HTTP 请求 2：POST /api/review/approve/{thread_id}
     
     使用 thread_id 从数据库找到之前保存的 state
     从 review_node 的 interrupt() 处恢复
```

### 问题 3：为什么要用 Base64 编码 xlsx？

```
XLSX 文件 = 二进制格式（.zip 压缩的 XML）

HTTP JSON 不能直接传输二进制数据：
  ✗ {"xlsx": <binary bytes>}  ← JSON 无法表示二进制

解决方案：Base64 编码
  ① 二进制 → Base64 字符串（在后端）
  ② 通过 JSON 传输：{"xlsx_base64": "JVBLAw4K..."}
  ③ 前端接收 Base64 字符串（在浏览器）
  ④ 解码：Base64 → 二进制
  ⑤ 触发浏览器下载
```

### 问题 4：如果用户中断呢？

```
场景：用户关闭浏览器

    ① 前端 HTTP 请求 1：POST /api/pbc/generate
       └─ 后端：graph 运行，review_node 中断
       └─ State 持久化到 checkpointer 数据库 ✅
       └─ 后端返回"awaiting_review" + thread_id
       └─ 前端收到响应

    ② 用户关闭浏览器（窗口关闭）
       └─ HTTP 连接断开
       └─ 但数据库中的 state 仍然存在 ✅

    ③ 用户第二天重新打开浏览器
       └─ 如果我们有数据库查询接口（GET /api/pbc/history）
       └─ 就能恢复之前的 thread_id
       └─ POST /api/review/approve/{old_thread_id}
       └─ 图继续执行，完成最终流程 ✅

这就是"持久化状态"的价值！
```

---

## 第 5 部分：生产问题（面试时可能问）

### Q: 如果后端 crash 了怎么办？

```
后端进程 A（运行 graph）
  │
  ├─ review_node 中断
  │  state 持久化到数据库 ✅
  │
  └─ HTTP 响应返回给前端 ✅

[后端 crash]

后端进程 B（重启）
  │
  └─ 数据库中的 state 仍然存在 ✅
  │
  ├─ 前端 POST /api/review/approve/{thread_id}
  │  进程 B 从数据库恢复 state
  │  继续执行 ✅
  
→ 用户无感知，图自动恢复
```

### Q: 如果多个请求同时修改同一个 thread_id？

```
请求 1：POST /api/review/approve/{thread_id}  (approved=true)
请求 2：POST /api/review/approve/{thread_id}  (approved=false)

竞争条件 (Race Condition)

解决方案：数据库事务 + 锁
  ① Checkpointer 使用 Postgres 的行级锁
  ② 第一个请求获得锁，执行，释放
  ③ 第二个请求等待，然后尝试（但 thread_id 已改变状态）
```

---

## 总结：你现在理解了什么

✅ **前端的职责**
- HTML 输入表单
- JavaScript 构建请求体
- fetch() 发送 HTTP 请求
- 接收响应，显示不同 UI（进度、审查、完成）
- Base64 解码，触发下载

✅ **后端的职责**
- 接收前端的 JSON 请求
- 创建初始 State
- 编译并运行 LangGraph
- 处理 interrupt（暂停）
- 恢复图执行（resume）
- 返回 JSON 响应

✅ **连接点**
- Thread ID = 审计的唯一标识
- Checkpointer = 持久化 State 到数据库
- Base64 = 在 JSON 中传输二进制数据
- interrupt/resume = 跨 HTTP 请求保持图状态

✅ **为什么这样设计**
- 前后端分离：关注点分开
- 持久化状态：用户关闭浏览器也不丢失
- 异步友好：HTTP 请求可以快速返回
- 可扩展：多个用户、多个 thread_id 互不干扰

