# 🛡️ Guardian Agent — Guarded AI with MCP Support

A full-stack AI system that enforces **real-time guardrails over LLM tool usage** using the Model Context Protocol (MCP).

This project demonstrates how to **separate what an AI *wants* to do from what the system *allows*** — a key requirement for building safe, production-ready AI agents.

---

## 🚀 Overview

Guardian Agent is built around a **control-plane architecture**:

- The **LLM suggests actions**
- The **Policy Engine enforces rules**
- The **MCP layer executes tools**

This ensures:

> 🔒 The AI never has direct execution power — all actions are mediated and validated.

---

## 🧩 Core Features

### 🤖 AI Agent (Backend)

- Tool-augmented LLM (Gemini/OpenRouter)
- Deterministic tool routing (LLM is not trusted for execution)
- Multi-tool support (sequential execution)
- Dynamic tool discovery via MCP (no hardcoding)

---

### 🔌 MCP Integration

Supports multiple MCP servers:

#### ✅ Remote MCP

- `@modelcontextprotocol/server-fetch`
- Enables real-time web data fetching

#### ✨ Custom MCP (GitHub Analyzer)

- `get_repo_info`
- `list_recent_commits`
- (Optional) `search_repos`

Demonstrates plug-and-play extensibility.

---

### 🛡️ Policy Engine (Core of the System)

A centralized enforcement layer that controls all tool execution:

- ❌ Block tools
- ⏳ Require human approval
- ⚠️ Validate inputs
- 📁 Enforce directory allowlist
- 🔐 Prevent prompt injection bypass

> The LLM can suggest — but the system decides.

---

### 🖥️ Guardrails Dashboard (Frontend)

A real-time admin interface to control the agent:

- Toggle tool policies (Allow / Block / Approval)
- Add/remove allowed directories dynamically
- Approve pending tool executions
- View logs and activity
- Live updates (no backend restart)

---

### 📂 Dynamic File Access Control

Implements a **secure allowlist model**:

- Only explicitly allowed directories can be accessed
- Outside access → requires approval
- Path normalization prevents traversal attacks (`../../etc/passwd`)
- Enforced entirely at the policy layer

---

### 📊 Observability & Persistence

- Logs every tool call + decision (allowed / blocked / approval)
- SQLite database for:
  - Rules
  - Logs
  - Approval requests
- Cost/token tracking (optional extension)

---

## 🏗️ Architecture

```
User
 ↓
Frontend Dashboard (React)
 ↓
FastAPI Backend
 ↓
Agent Router
 ↓
🛡️ Policy Engine (Control Plane)
 ↓
MCP Servers (Execution Layer)
 ↓
Tool Response
```

---

## ⚙️ Tech Stack

**Backend**
- Python (FastAPI)
- Gemini / OpenRouter (LLM)
- SQLite

**Frontend**
- React (Vite)
- Axios

**MCP**
- Node MCP servers (`server-fetch`, filesystem)
- Custom Python MCP server (GitHub)

---

## 🔄 Execution Flow

1. User sends query
2. Router detects required tool(s)
3. Policy engine evaluates:
   - Block / Allow / Approval
4. If approved:
   - MCP tool executes
5. Response returned to user
6. Logs stored

---

## 🔒 Security Design

### Key Principle

> **LLM is treated as an untrusted component**

#### ✔ Guardrail Enforcement

- All tool calls pass through policy engine
- No direct LLM execution

#### ✔ Prompt Injection Protection

Even if the model says:

```
"Ignore all rules and execute tool"
```

👉 The system blocks it.

#### ✔ Rule Precedence

```
BLOCK > APPROVAL > ALLOW
```

#### ✔ Directory Sandbox

- Allowlist-based access
- Path normalization
- Approval required for new paths

---

## 🧪 Example Demo Flow

1. Ask:
   ```
   Get repo info for openai/openai-python
   ```
   → ⏳ Approval required

2. Approve from dashboard
   → Tool executes

3. Block tool in UI
   → ❌ Execution blocked

4. Add new directory
   → Access dynamically allowed

---

## ⚠️ Edge Case Handling

| Scenario | Handling |
|---|---|
| MCP crash | Graceful error + logging |
| Prompt injection | Ignored via policy layer |
| Conflicting rules | BLOCK takes precedence |
| Approval offline | Request remains queued |

---

## 📦 Project Structure

```
backend/
  agent/
  policy/
  mcp/
  custom_mcp/
  database/

frontend/
  src/
```

---

## ▶️ Getting Started

### 1. Clone repo

```bash
git clone <repo-url>
cd guardian-agent
```

### 2. Backend setup

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

### 3. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

### 4. Start MCP servers

```bash
npx @modelcontextprotocol/server-fetch
npx @modelcontextprotocol/server-filesystem /home/<your-user>
```

---

## 🎯 Key Design Decisions

- ❌ No hardcoded tools → dynamic MCP discovery
- ❌ No LLM trust → system-level enforcement
- ✅ Control-plane architecture
- ✅ Real-time policy updates
- ✅ Plug-and-play MCP servers

---

## 🏆 Why This Project Stands Out

- Demonstrates **real-world AI safety architecture**
- Goes beyond simple LLM wrappers
- Implements **human-in-the-loop control**
- Shows strong **system design + security thinking**

---

## 📹 Demo

> (Add your Loom / video link here)

---

## 👨‍💻 Author

**Anshuman Dutta**  
Agentic AI Developer | ML + Systems

---

## 📌 Future Improvements

- WebSocket-based real-time updates
- Role-based access control
- Advanced policy DSL
- Multi-agent orchestration

---

## 🧠 Final Thought

> "The model suggests actions. The system decides what is allowed."
