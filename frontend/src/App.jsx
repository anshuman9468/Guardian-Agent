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
import "./index.css";

// ── Helpers ───────────────────────────────────────────────────────────────────

const now = () =>
  new Date().toLocaleTimeString("en-US", { hour12: false });

const classifyResponse = (text) => {
  if (!text) return "";
  if (text.startsWith("❌")) return "blocked";
  if (text.startsWith("⏳")) return "approval";
  if (text.startsWith("⚠️")) return "approval";
  return "";
};

// ── Sub-components ────────────────────────────────────────────────────────────

function StatusDot({ syncing }) {
  return <span className={`pulse-dot ${syncing ? "syncing" : ""}`} />;
}

function ToolRow({ name, status, onBlock, onUnblock, onApprove, onUnapprove }) {
  const rowClass =
    status === "blocked"  ? "tool-row blocked"  :
    status === "approval" ? "tool-row approval"  : "tool-row allowed";

  const badge =
    status === "blocked"  ? <span className="status-badge badge-blocked">BLOCKED</span>  :
    status === "approval" ? <span className="status-badge badge-approval">APPROVAL</span> :
                            <span className="status-badge badge-allowed">ALLOWED</span>;

  return (
    <div className={rowClass}>
      <div className="tool-name">{name}{badge}</div>
      <div className="tool-actions">
        {status === "blocked" ? (
          <button className="btn btn-allow" onClick={() => onUnblock(name)}>Allow</button>
        ) : (
          <button className="btn btn-block" onClick={() => onBlock(name)}>Block</button>
        )}
        {status === "approval" ? (
          <button className="btn btn-allow" onClick={() => onUnapprove(name)}>Remove</button>
        ) : status !== "blocked" ? (
          <button className="btn btn-approve" onClick={() => onApprove(name)}>Approve</button>
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
    ? JSON.stringify(req.args, null, 2)
    : "no arguments";

  const age = Math.floor(
    (Date.now() - new Date(req.created_at).getTime()) / 1000
  );

  return (
    <div className="approval-card">
      <div className="approval-card-header">
        <span className="approval-tool-name">⏳ {req.tool}</span>
        <span className="approval-meta">{age}s ago</span>
      </div>
      <div className="approval-args">{argsStr}</div>
      <div style={{ fontSize: 11, color: "var(--muted)", fontFamily: "monospace" }}>
        ID: {req.request_id.slice(0, 8)}…
      </div>
      <div className="approval-btns">
        <button className="btn btn-approve-action" onClick={() => onApprove(req.request_id)}>
          ✅ Approve &amp; Run
        </button>
        <button className="btn btn-deny-action" onClick={() => onDeny(req.request_id)}>
          🚫 Deny
        </button>
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
    { role: "system", content: "Guardian Agent is ready. Policy engine active 🛡️", ts: now() }
  ]);
  const [input, setInput]         = useState("");
  const [loading, setLoading]     = useState(false);
  const messagesEnd               = useRef(null);

  const [logs, setLogs]           = useState([]);
  const [tab, setTab]             = useState("chat");

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
      setLastSync(now());
    } catch (_) { /* backend offline */ } finally {
      setSyncing(false);
    }
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

  const getStatus = (name) => {
    if (rules.blocked_tools.includes(name))  return "blocked";
    if (rules.approval_tools.includes(name)) return "approval";
    return "allowed";
  };

  const addLog = (type, tool, action, result) =>
    setLogs((l) => [{ ts: now(), type, tool, action, result }, ...l].slice(0, 100));

  // ── Policy actions ────────────────────────────────────────────────────────────

  const handleBlock     = async (n) => { await blockTool(n);     fetchAll(); addLog("BLOCKED",  n, "block",     `'${n}' blocked`); };
  const handleUnblock   = async (n) => { await unblockTool(n);   fetchAll(); addLog("ALLOWED",  n, "unblock",   `'${n}' unblocked`); };
  const handleApprove   = async (n) => { await approveTool(n);   fetchAll(); addLog("APPROVAL", n, "approve",   `'${n}' needs approval`); };
  const handleUnapprove = async (n) => { await unapproveTool(n); fetchAll(); addLog("ALLOWED",  n, "unapprove", `Approval removed for '${n}'`); };

  // ── Approval actions ──────────────────────────────────────────────────────────

  const handleApproveRequest = async (request_id) => {
    try {
      const res = await approveRequest(request_id);
      const d = res.data;
      addLog("ALLOWED", d.tool, "approved", `✅ Executed: ${d.result}`);
      setMessages((m) => [...m, {
        role: "agent",
        content: `✅ Approved & executed '${d.tool}': ${d.result}`,
        ts: now(),
      }]);
    } catch {
      addLog("BLOCKED", "?", "approve-error", "Approval failed — request may have expired");
    }
    fetchAll();
  };

  const handleDenyRequest = async (request_id) => {
    try {
      const res = await denyRequest(request_id);
      addLog("BLOCKED", res.data.tool, "denied", `🚫 Denied execution of '${res.data.tool}'`);
      setMessages((m) => [...m, {
        role: "agent",
        content: `🚫 Request denied — '${res.data.tool}' was not executed.`,
        ts: now(),
      }]);
    } catch { /* noop */ }
    fetchAll();
  };

  // ── Chat ──────────────────────────────────────────────────────────────────────

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text, ts: now() }]);
    setLoading(true);
    try {
      const res = await sendChat(text);
      const { response: reply, pending_request_id } = res.data;
      setMessages((m) => [...m, { role: "agent", content: reply, ts: now() }]);

      const cls = classifyResponse(reply);
      if (cls === "blocked")  addLog("BLOCKED",  "?", "chat", reply);
      if (cls === "approval") addLog("APPROVAL", "?", "chat", reply);
      if (pending_request_id) {
        addLog("APPROVAL", "?", "pending", `New approval request: ${pending_request_id.slice(0,8)}…`);
      }
      if (!cls && reply.includes("via tool")) addLog("ALLOWED", "?", "chat", reply);
      fetchAll(); // refresh pending list immediately
    } catch {
      setMessages((m) => [...m, {
        role: "agent",
        content: "❌ Request failed — check that the backend is running.",
        ts: now(),
      }]);
    } finally {
      setLoading(false);
    }
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
      {/* Header */}
      <header className="header">
        <div className="header-logo">
          <span className="shield">🛡️</span>
          <span className="logo-gradient">Guardian Agent</span>
        </div>
        <div className="header-status">
          <StatusDot syncing={syncing} />
          {syncing ? "Syncing…" : `Synced ${lastSync || "—"}`}
          {pending.length > 0 && (
            <span className="approval-badge" style={{ marginLeft: 12 }}>
              ⏳ {pending.length} pending
            </span>
          )}
        </div>
      </header>

      {/* Sidebar */}
      <aside className="sidebar">
        {/* Stats */}
        <div className="stats">
          <div className="stat"><div className="stat-val red">{blockedCount}</div><div className="stat-label">Blocked</div></div>
          <div className="stat"><div className="stat-val yellow">{approvalCount}</div><div className="stat-label">Approval</div></div>
          <div className="stat"><div className="stat-val green">{allowedCount}</div><div className="stat-label">Allowed</div></div>
        </div>

        {/* Pending Approvals Panel */}
        {pending.length > 0 && (
          <div className="panel">
            <div className="panel-header">
              <span className="icon">⏳</span>
              Pending Approvals
              <span className="approval-badge" style={{ marginLeft: "auto" }}>{pending.length}</span>
            </div>
            <div style={{ padding: 10, display: "flex", flexDirection: "column", gap: 8 }}>
              {pending.map((req) => (
                <ApprovalCard
                  key={req.request_id}
                  req={req}
                  onApprove={handleApproveRequest}
                  onDeny={handleDenyRequest}
                />
              ))}
            </div>
          </div>
        )}

        {/* Tool Policies */}
        <div className="panel">
          <div className="panel-header"><span className="icon">⚙️</span> Tool Policies</div>
          <div className="tool-list">
            {toolNames.length === 0 && (
              <div style={{ padding: "12px", color: "var(--muted)", fontSize: 13 }}>Loading tools…</div>
            )}
            {toolNames.map((name) => (
              <ToolRow key={name} name={name} status={getStatus(name)}
                onBlock={handleBlock} onUnblock={handleUnblock}
                onApprove={handleApprove} onUnapprove={handleUnapprove} />
            ))}
          </div>
        </div>

        {/* Legend */}
        <div className="panel">
          <div className="panel-header"><span className="icon">📖</span> Legend</div>
          <div style={{ padding: "12px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
            {[
              ["🚫", "Blocked",  "Tool is completely forbidden"],
              ["⏳", "Approval", "Requires human sign-off"],
              ["✅", "Allowed",  "Tool executes freely"],
            ].map(([icon, label, desc]) => (
              <div key={label} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                <span style={{ fontSize: 15 }}>{icon}</span>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600 }}>{label}</div>
                  <div style={{ fontSize: 11, color: "var(--muted)" }}>{desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="main">
        <div className="tabs">
          {["chat", "logs"].map((t) => (
            <button key={t} className={`tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
              {t === "chat" ? "💬 Chat" : `📋 Activity Log (${logs.length})`}
            </button>
          ))}
        </div>

        {/* Chat Tab */}
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
                        {" · "}{m.ts}
                      </div>
                      <div className={`msg-content ${cls} ${m.role === "user" ? "user-msg" : ""}`}>
                        {m.content}
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
                placeholder='Try "What time is it?" or "What is 5 plus 3?"'
                value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKey}
              />
              <button className="btn btn-primary" onClick={handleSend} disabled={loading || !input.trim()}>
                Send ↑
              </button>
            </div>
          </div>
        )}

        {/* Logs Tab */}
        {tab === "logs" && (
          <div className="logs-area">
            {logs.length === 0 ? (
              <div className="empty-state">
                <div className="icon">📋</div>
                <p>No activity yet. Interact with the agent or change policies.</p>
              </div>
            ) : (
              logs.map((l, i) => (
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
              ))
            )}
          </div>
        )}
      </main>
    </div>
  );
}
