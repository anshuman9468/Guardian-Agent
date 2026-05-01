import axios from "axios";

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const api = axios.create({ baseURL: BASE });

export const getRules           = ()     => api.get("/policy/rules");
export const blockTool          = (tool) => api.post("/policy/block",    { tool_name: tool });
export const unblockTool        = (tool) => api.post("/policy/unblock",  { tool_name: tool });
export const approveTool        = (tool) => api.post("/policy/approve",  { tool_name: tool });
export const unapproveTool      = (tool) => api.post("/policy/unapprove",{ tool_name: tool });
export const getTools           = ()     => api.get("/tools");
export const sendChat = (message, history = [], model) =>
  api.post("/chat", { message, history, model });

// Approval workflow
export const getPendingApprovals = ()          => api.get("/approvals/pending");
export const approveRequest      = (request_id)=> api.post("/approve", { request_id });
export const denyRequest         = (request_id)=> api.post("/deny",    { request_id });

// ── Directory Allowlist ──────────────────────────────────────────────────────
export const getDirectories    = ()     => api.get("/directories");
export const addDirectory      = (path) => api.post("/directories/add", { path });
export const removeDirectory   = (path) => api.post("/directories/remove", { path });
