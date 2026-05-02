"""
main.py — Guardian Agent FastAPI application.

Architecture (Chunk 5 — Real MCP):
  - FastAPI lifespan connects to MCP servers on startup.
  - Tools are discovered live from MCP servers each request.
  - Hardcoded tools act as fallback when MCP has no match.
  - Policy engine gates every tool call.
  - Approval store holds pending approvals.
"""

from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG", "").lower() in ("1", "true") else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

from agent.agent_loop import run_agent
from agent.llm_client import DEFAULT_MODEL
from agent.tools import TOOL_DEFINITIONS as HARDCODED_TOOL_DEFS
from agent.tools import tool_executor as hardcoded_executor
from mcp_servers.server_registry import MCP_SERVERS
from policy import approval_store, rule_store


# ── Async tool executor ───────────────────────────────────────────────────────

async def unified_tool_executor(tool_name: str, args: dict[str, Any]) -> str:
    """Execute a tool using the HTTP services defined in tools.py."""
    logger.info("Routing to tool handler | tool=%s", tool_name)
    return await hardcoded_executor(tool_name, args)


# ── FastAPI lifespan ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Guardian Agent Backend")
    yield
    logger.info("Shutting down Guardian Agent Backend")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "Guardian Agent",
    description = "Guarded AI agent with external HTTP services and policy enforcement.",
    version     = "0.2.0",
    docs_url    = "/docs",
    redoc_url   = "/redoc",
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    history: list[dict[str, str]] = Field(default_factory=list)
    model:   str = Field(default=DEFAULT_MODEL)


class ChatResponse(BaseModel):
    response:           str
    model:              str
    pending_request_id: str | None = None


class HealthResponse(BaseModel):
    status:  str
    version: str


class PolicyActionRequest(BaseModel):
    tool_name: str = Field(..., description="Name of the tool.")


class ApproveRequest(BaseModel):
    request_id: str = Field(..., description="UUID of the pending approval request.")


# ── Meta endpoints ────────────────────────────────────────────────────────────

@app.get("/", tags=["Meta"])
async def root() -> dict[str, str]:
    return {"message": "Guardian Agent Backend is running successfully!"}

@app.get("/health", response_model=HealthResponse, tags=["Meta"])
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version=app.version)


@app.get("/tools", tags=["Meta"])
async def list_tools() -> dict[str, Any]:
    """Tools available from all microservices."""
    all_tools = []
    for t in HARDCODED_TOOL_DEFS:
        t_copy = dict(t)
        t_copy["_server"] = t.get("_server", "built-in")
        all_tools.append(t_copy)
        
    return {"tools": all_tools, "count": len(all_tools), "mcp_count": len(all_tools)}


@app.get("/mcp/status", tags=["Meta"])
async def mcp_status() -> dict[str, Any]:
    """Show HTTP MCP services."""
    return {"connected": True, "servers": list(MCP_SERVERS.keys()), "registry_type": "http"}


# ── Policy endpoints ──────────────────────────────────────────────────────────

@app.get("/policy/rules", tags=["Policy"])
async def get_policy_rules() -> dict[str, Any]:
    return rule_store.get_rules()


@app.post("/policy/block", tags=["Policy"])
async def block_tool(req: PolicyActionRequest) -> dict[str, str]:
    rule_store.block_tool(req.tool_name)
    logger.info("Policy: BLOCKED tool=%s", req.tool_name)
    return {"status": "ok", "message": f"Tool '{req.tool_name}' is now BLOCKED."}


@app.post("/policy/unblock", tags=["Policy"])
async def unblock_tool(req: PolicyActionRequest) -> dict[str, str]:
    rule_store.unblock_tool(req.tool_name)
    logger.info("Policy: UNBLOCKED tool=%s", req.tool_name)
    return {"status": "ok", "message": f"Tool '{req.tool_name}' is now UNBLOCKED."}


@app.post("/policy/approve", tags=["Policy"])
async def require_approval(req: PolicyActionRequest) -> dict[str, str]:
    rule_store.require_approval(req.tool_name)
    logger.info("Policy: NEEDS_APPROVAL tool=%s", req.tool_name)
    return {"status": "ok", "message": f"Tool '{req.tool_name}' now requires approval."}


@app.post("/policy/unapprove", tags=["Policy"])
async def remove_approval(req: PolicyActionRequest) -> dict[str, str]:
    rule_store.remove_approval(req.tool_name)
    return {"status": "ok", "message": f"Approval removed for '{req.tool_name}'."}


# ── Directory Allowlist endpoints ───────────────────────────────────────────

class AddDirectoryRequest(BaseModel):
    path: str = Field(..., description="Absolute path to allow")

@app.get("/directories", tags=["Policy"])
async def list_directories() -> dict[str, Any]:
    from policy.directory_store import get_allowed_dirs
    return {"directories": get_allowed_dirs()}

@app.post("/directories/add", tags=["Policy"])
async def add_directory(req: AddDirectoryRequest) -> dict[str, Any]:
    from policy.directory_store import add_allowed_dir
    result = add_allowed_dir(req.path)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@app.post("/directories/remove", tags=["Policy"])
async def remove_directory(req: AddDirectoryRequest) -> dict[str, Any]:
    from policy.directory_store import remove_allowed_dir
    result = remove_allowed_dir(req.path)
    if result["status"] == "error":
        raise HTTPException(status_code=404, detail=result["message"])
    return result

# ── Approval endpoints ────────────────────────────────────────────────────────

@app.get("/approvals/pending", tags=["Approvals"])
async def get_pending_approvals() -> dict[str, Any]:
    return {"pending": approval_store.get_all(), "count": approval_store.count()}


@app.post("/approve", tags=["Approvals"])
async def approve_request(req: ApproveRequest) -> dict[str, Any]:
    task = approval_store.pop_request(req.request_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    logger.info("APPROVED | tool=%s | request_id=%s", task["tool"], req.request_id)
    try:
        result = await unified_tool_executor(task["tool"], task["args"])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Tool execution failed: {exc}") from exc
    return {"status": "APPROVED", "tool": task["tool"], "result": str(result)}


@app.post("/deny", tags=["Approvals"])
async def deny_request(req: ApproveRequest) -> dict[str, Any]:
    task = approval_store.pop_request(req.request_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    logger.info("DENIED | tool=%s | request_id=%s", task["tool"], req.request_id)
    return {"status": "DENIED", "tool": task["tool"]}


# ── Chat endpoint ─────────────────────────────────────────────────────────────

@app.post("/chat", response_model=ChatResponse, tags=["Agent"])
async def chat(req: ChatRequest) -> ChatResponse:
    """Send a message. The agent uses live MCP tools, gated by the policy engine."""
    logger.info("POST /chat | model=%s | msg=%r", req.model, req.message[:80])

    # Use the tools defined in tools.py, but CLEAN them first.
    # AI providers reject requests if the tool definitions contain non-standard keys like '_server'.
    all_tools = []
    for t in HARDCODED_TOOL_DEFS:
        clean_tool = {
            "type": t.get("type", "function"),
            "function": t.get("function", {})
        }
        all_tools.append(clean_tool)

    try:
        answer = await run_agent(
            user_input    = req.message,
            history       = req.history,
            tools         = all_tools,
            tool_executor = unified_tool_executor,
            model         = req.model,
        )
    except EnvironmentError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error in agent loop")
        # Check if it's an OpenAI API error to return gracefully
        if "openai" in str(type(exc)).lower() and hasattr(exc, "status_code"):
            error_msg = f"❌ AI Provider Error: HTTP {exc.status_code} - {getattr(exc, 'message', str(exc))}\n(Check your OpenRouter credits or API key)"
            return ChatResponse(response=error_msg, model=req.model, pending_request_id=None)
        raise HTTPException(status_code=500, detail=f"Internal agent error: {exc}") from exc

    return ChatResponse(
        response           = answer,
        model              = req.model,
        pending_request_id = None,
    )
