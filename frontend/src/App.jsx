import { useState, useEffect, useRef, useCallback } from "react";
import {
  getRules, getTools,
  blockTool, unblockTool,
  approveTool, unapproveTool,
  sendChat,
  getPendingApprovals,
  approveRequest,
  denyRequest,
} from "./api";
import ReactMarkdown from "react-markdown";
import "./index.css";

// ── Helpers ───────────────────────────────────────────────────────────────────

const nowStr = () => new Date().toLocaleTimeString("en-US", { hour12: false });

const classifyResponse = (text = "") => {
  if (text.startsWith("❌")) return "blocked";
  if (text.startsWith("⏳") || text.startsWith("⚠️")) return "approval";
  return "";
};

// ── Sub-components ────────────────────────────────────────────────────────────

function ToolRow({ name, status, onBlock, onUnblock, onApprove, onUnapprove }) {
  const badge =
    status === "blocked"  ? <span className="status-badge badge-blocked">BLOCKED</span>  :
    status === "approval" ? <span className="status-badge badge-approval">APPROVAL</span> :
                            <span className="status-badge badge-allowed">ALLOWED</span>;

  return (
    <div className={`tool-row ${status}`}>
      <div className="tool-row-top">
        <span className="tool-name-text" title={name}>{name}</span>
        {badge}
      </div>
      <div className="tool-row-bottom">
        {status === "blocked" ? (
          <button className="btn btn-allow" onClick={() => onUnblock(name)}>✓ Allow</button>
        ) : (
          <button className="btn btn-block" onClick={() => onBlock(name)}>✕ Block</button>
        )}
        {status === "approval" ? (
          <button className="btn btn-allow" onClick={() => onUnapprove(name)}>✓ Remove</button>
        ) : status !== "blocked" ? (
          <button className="btn btn-approve" onClick={() => onApprove(name)}>⏳ Require Approval</button>
        ) : null}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="message">
      <div className="msg-avatar agent">🤖</div>
      <div className="msg-body">
        <div className="msg-role">Guardian Agent</div>
        <div className="msg-content">
          <div className="typing-indicator">
            <div className="typing-dot" /><div className="typing-dot" /><div className="typing-dot" />
          </div>
        </div>
      </div>
    </div>
  );
}

function ApprovalCard({ req, onApprove, onDeny }) {
  const argsStr = Object.keys(req.args || {}).length
    ? JSON.stringify(req.args, null, 2) : "no arguments";
  const age = Math.floor((Date.now() - new Date(req.created_at).getTime()) / 1000);

  return (
    <div className="approval-card">
      <div className="approval-card-header">
        <div className="approval-tool-name">⏳ {req.tool}</div>
        <span className="approval-meta">{age}s ago</span>
      </div>
      <div className="approval-args">{argsStr}</div>
      <div className="approval-id">ID: {req.request_id.slice(0, 12)}…</div>
      <div className="approval-btns">
        <button className="btn-approve-action" onClick={() => onApprove(req.request_id)}>✅ Approve & Run</button>
        <button className="btn-deny-action"    onClick={() => onDeny(req.request_id)}>🚫 Deny</button>
      </div>
    </div>
  );
}

// ── Main App ──────────────────────────────────────────────────────────────────

export default function App() {
  const [rules, setRules]         = useState({ blocked_tools: [], approval_tools: [] });
  const [toolNames, setToolNames] = useState([]);
  const [pending, setPending]     = useState([]);
  const [syncing, setSyncing]     = useState(false);
  const [lastSync, setLastSync]   = useState(null);

  const [messages, setMessages]   = useState([
    { role: "system", content: "Guardian Agent online. Policy engine active · 3 MCP servers connected 🛡️", ts: nowStr() }
  ]);
  const [input, setInput]         = useState("");
  const [loading, setLoading]     = useState(false);
  const messagesEnd               = useRef(null);

  const [logs, setLogs]           = useState([]);
  const [tab, setTab]             = useState("chat");
  // Tracks user/agent turns for multi-turn context
  const chatHistory               = useRef([]);

  // ── Polling ──────────────────────────────────────────────────────────────────

  const fetchAll = useCallback(async () => {
    setSyncing(true);
    try {
      const [rulesRes, toolsRes, pendingRes] = await Promise.all([
        getRules(), getTools(), getPendingApprovals(),
      ]);
      setRules(rulesRes.data);
      setToolNames(toolsRes.data.tools.map((t) => t.function.name));
      setPending(pendingRes.data.pending || []);
      setLastSync(nowStr());
    } catch (_) {}
    finally { setSyncing(false); }
  }, []);

  useEffect(() => {
    fetchAll();
    const id = setInterval(fetchAll, 2000);
    return () => clearInterval(id);
  }, [fetchAll]);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // ── Helpers ───────────────────────────────────────────────────────────────────

  const getStatus = (n) =>
    rules.blocked_tools.includes(n)  ? "blocked"  :
    rules.approval_tools.includes(n) ? "approval" : "allowed";

  const addLog = (type, tool, action, result) =>
    setLogs(l => [{ ts: nowStr(), type, tool, action, result }, ...l].slice(0, 150));

  // ── Policy actions ────────────────────────────────────────────────────────────

  const handleBlock     = async (n) => { await blockTool(n);     fetchAll(); addLog("BLOCKED",  n, "block",     `'${n}' is now blocked`); };
  const handleUnblock   = async (n) => { await unblockTool(n);   fetchAll(); addLog("ALLOWED",  n, "unblock",   `'${n}' is now allowed`); };
  const handleApprove   = async (n) => { await approveTool(n);   fetchAll(); addLog("APPROVAL", n, "approve",   `'${n}' requires approval`); };
  const handleUnapprove = async (n) => { await unapproveTool(n); fetchAll(); addLog("ALLOWED",  n, "unapprove", `Approval removed for '${n}'`); };

  // ── Approval actions ──────────────────────────────────────────────────────────

  const handleApproveRequest = async (id) => {
    try {
      const res = await approveRequest(id);
      addLog("ALLOWED", res.data.tool, "approved", `✅ Executed: ${res.data.result}`);
      setMessages(m => [...m, { role: "agent", content: `✅ Approved & executed '${res.data.tool}':\n${res.data.result}`, ts: nowStr() }]);
    } catch { addLog("BLOCKED", "?", "approve-error", "Approval failed — request may have expired"); }
    fetchAll();
  };

  const handleDenyRequest = async (id) => {
    try {
      const res = await denyRequest(id);
      addLog("BLOCKED", res.data.tool, "denied", `🚫 Denied '${res.data.tool}'`);
      setMessages(m => [...m, { role: "agent", content: `🚫 Request denied — '${res.data.tool}' was not executed.`, ts: nowStr() }]);
    } catch {}
    fetchAll();
  };

  // ── Chat ──────────────────────────────────────────────────────────────────────

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages(m => [...m, { role: "user", content: text, ts: nowStr() }]);
    setLoading(true);
    // Build history to send (only user/agent turns, not system UI msgs)
    const history = chatHistory.current.slice();
    chatHistory.current = [...history, { role: "user", content: text }];
    try {
      const res = await sendChat(text, history);
      const { response: reply, pending_request_id } = res.data;
      chatHistory.current = [...chatHistory.current, { role: "assistant", content: reply }];
      setMessages(m => [...m, { role: "agent", content: reply, ts: nowStr() }]);
      const cls = classifyResponse(reply);
      if (cls === "blocked")       addLog("BLOCKED",  "?", "chat", reply);
      else if (cls === "approval") addLog("APPROVAL", "?", "chat", reply);
      else                         addLog("ALLOWED",  "?", "chat", `Response: ${reply.slice(0, 60)}…`);
      if (pending_request_id) fetchAll();
    } catch {
      setMessages(m => [...m, { role: "agent", content: "❌ Backend unreachable — is uvicorn running on port 8000?", ts: nowStr() }]);
    } finally { setLoading(false); }
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  // ── Stats ─────────────────────────────────────────────────────────────────────

  const blockedCount  = rules.blocked_tools.length;
  const approvalCount = rules.approval_tools.length;
  const allowedCount  = Math.max(0, toolNames.length - blockedCount - approvalCount);

  const logIcon = (t) => t === "BLOCKED" ? "🚫" : t === "APPROVAL" ? "⏳" : "✅";

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="header">
        <div className="header-logo">
          <div className="logo-icon">🛡️</div>
          <span className="logo-text">Guardian Agent</span>
          <span className="logo-badge">v0.2</span>
        </div>
        <div className="header-right">
          {pending.length > 0 && (
            <div className="pending-header-badge">
              ⏳ {pending.length} pending approval{pending.length > 1 ? "s" : ""}
            </div>
          )}
          <div className="header-status">
            <span className={`pulse-dot ${syncing ? "syncing" : ""}`} />
            {syncing ? "Syncing…" : `Live · ${lastSync || "—"}`}
          </div>
        </div>
      </header>

      {/* ── Sidebar ── */}
      <aside className="sidebar">
        {/* Stats */}
        <div className="stats">
          <div className="stat"><div className="stat-val red">{blockedCount}</div><div className="stat-label">Blocked</div></div>
          <div className="stat"><div className="stat-val yellow">{approvalCount}</div><div className="stat-label">Pending</div></div>
          <div className="stat"><div className="stat-val green">{allowedCount}</div><div className="stat-label">Allowed</div></div>
        </div>

        {/* Pending Approvals */}
        {pending.length > 0 && (
          <div className="panel">
            <div className="panel-header">
              ⏳ Pending Approvals
              <span className="panel-header-count">{pending.length}</span>
            </div>
            <div className="approval-panel-list">
              {pending.map(req => (
                <ApprovalCard key={req.request_id} req={req}
                  onApprove={handleApproveRequest} onDeny={handleDenyRequest} />
              ))}
            </div>
          </div>
        )}

        {/* Tool Policies */}
        <div className="panel">
          <div className="panel-header">
            ⚙️ Tool Policies
            <span className="panel-header-count">{toolNames.length}</span>
          </div>
          <div className="tool-list">
            {toolNames.length === 0 && (
              <div style={{ padding: "12px", color: "var(--muted)", fontSize: 12 }}>
                Connecting to MCP servers…
              </div>
            )}
            {toolNames.map(name => (
              <ToolRow key={name} name={name} status={getStatus(name)}
                onBlock={handleBlock} onUnblock={handleUnblock}
                onApprove={handleApprove} onUnapprove={handleUnapprove} />
            ))}
          </div>
        </div>

        {/* Legend */}
        <div className="panel">
          <div className="panel-header">📖 Legend</div>
          <div className="legend-list">
            {[
              ["🚫", "Blocked",  "Tool completely forbidden — hard deny"],
              ["⏳", "Approval", "Requires human sign-off before running"],
              ["✅", "Allowed",  "Tool executes freely without restriction"],
            ].map(([icon, label, desc]) => (
              <div key={label} className="legend-item">
                <span className="legend-icon">{icon}</span>
                <div>
                  <div className="legend-title">{label}</div>
                  <div className="legend-desc">{desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </aside>

      {/* ── Main ── */}
      <main className="main">
        <div className="tabs">
          <button className={`tab ${tab === "chat" ? "active" : ""}`} onClick={() => setTab("chat")}>
            💬 Chat
          </button>
          <button className={`tab ${tab === "logs" ? "active" : ""}`} onClick={() => setTab("logs")}>
            📋 Activity Log {logs.length > 0 && `(${logs.length})`}
          </button>
        </div>

        {/* Chat */}
        {tab === "chat" && (
          <div className="chat-area">
            <div className="messages">
              {messages.map((m, i) => {
                const cls = classifyResponse(m.content);
                return (
                  <div key={i} className="message">
                    <div className={`msg-avatar ${m.role}`}>
                      {m.role === "user" ? "👤" : m.role === "agent" ? "🤖" : "🛡️"}
                    </div>
                    <div className="msg-body">
                      <div className="msg-role">
                        {m.role === "user" ? "You" : m.role === "agent" ? "Guardian Agent" : "System"}
                        <span style={{ opacity: 0.5 }}>·</span>
                        <span>{m.ts}</span>
                      </div>
                      <div className={`msg-content ${cls} ${m.role === "user" ? "user-msg" : ""}`}>
                        {m.role === "agent" ? (
                          <ReactMarkdown>{m.content}</ReactMarkdown>
                        ) : (
                          m.content
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
              {loading && <TypingIndicator />}
              <div ref={messagesEnd} />
            </div>
            <div className="chat-input-row">
              <textarea
                className="chat-input" rows={1}
                placeholder='Try "Get info about microsoft/vscode" or "What time is it?"'
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKey}
              />
              <button className="btn btn-primary" onClick={handleSend} disabled={loading || !input.trim()}>
                Send ↑
              </button>
            </div>
          </div>
        )}

        {/* Logs */}
        {tab === "logs" && (
          <div className="logs-area">
            {logs.length === 0 ? (
              <div className="empty-state">
                <div className="icon">📋</div>
                <p>No activity yet — chat or change policies to see logs.</p>
              </div>
            ) : logs.map((l, i) => (
              <div key={i} className={`log-entry ${l.type}`}>
                <span className="log-time">{l.ts}</span>
                <span className="log-icon">{logIcon(l.type)}</span>
                <div className="log-text">
                  <strong>[{l.type}]</strong>{" "}
                  {l.action === "chat" || l.action === "pending" || l.action === "approved" || l.action === "denied"
                    ? l.result
                    : `${l.action.toUpperCase()} → ${l.tool}: ${l.result}`}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
