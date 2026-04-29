"""
main.py — Guardian Agent FastAPI application entry point.

Endpoints:
  POST /chat        — Main agent chat endpoint.
  GET  /health      — Health / readiness probe.
  GET  /tools       — List available tools and their schemas.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent.agent_loop import run_agent
from agent.tools import TOOL_DEFINITIONS, tool_executor

# ── Bootstrap ────────────────────────────────────────────────────────────────

load_dotenv()  # Load .env BEFORE anything tries to read env vars.

logging.basicConfig(
    level=logging.DEBUG if os.getenv("DEBUG", "").lower() in ("1", "true") else logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── App factory ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Guardian Agent",
    description=(
        "An agentic AI backend powered by OpenAI function-calling. "
        "The agent reasons through multi-step tool use to answer user queries."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten in production.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic schemas ─────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The user's message / query.")
    model: str = Field(
        default="google/gemini-2.5-flash",
        description="OpenRouter model string (e.g. google/gemini-2.5-flash, openai/gpt-4o).",
    )


class ChatResponse(BaseModel):
    response: str
    model: str


class HealthResponse(BaseModel):
    status: str
    version: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Meta"])
async def health() -> HealthResponse:
    """Readiness / liveness probe."""
    return HealthResponse(status="ok", version=app.version)


@app.get("/tools", tags=["Meta"])
async def list_tools() -> dict[str, Any]:
    """Return the currently registered tool definitions."""
    return {"tools": TOOL_DEFINITIONS, "count": len(TOOL_DEFINITIONS)}


@app.post("/chat", response_model=ChatResponse, tags=["Agent"])
async def chat(req: ChatRequest) -> ChatResponse:
    """
    Send a message to the Guardian Agent.

    The agent will:
    - Reason about the query.
    - Call tools if needed (possibly multiple times).
    - Return a final natural-language answer.
    """
    logger.info("POST /chat | model=%s | message=%r", req.model, req.message[:80])

    try:
        answer = run_agent(
            user_input=req.message,
            tools=TOOL_DEFINITIONS,
            tool_executor=tool_executor,
            model=req.model,
        )
    except EnvironmentError as exc:
        # Missing API key — surface clearly.
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except RuntimeError as exc:
        # Max iterations exceeded or similar agent error.
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in agent loop")
        raise HTTPException(status_code=500, detail=f"Internal agent error: {exc}") from exc

    return ChatResponse(response=answer, model=req.model)
