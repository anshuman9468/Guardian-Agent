"""
server_registry.py — Manages multiple MCP server connections.

Responsibilities:
  - Starts/stops all configured MCP servers (called from FastAPI lifespan).
  - Aggregates tool lists across all connected servers.
  - Routes tool calls to the correct server.
  - Falls back to hardcoded tools when no MCP server has the tool.

Adding a new MCP server:
  Append an MCPServerConfig to CONFIGURED_SERVERS.
  The agent picks up the new tools automatically on next startup.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from mcp_servers.mcp_client import MCPClient

logger = logging.getLogger(__name__)


# ── Server Configuration ──────────────────────────────────────────────────────

@dataclass
class MCPServerConfig:
    name:    str
    command: str
    args:    list[str]
    enabled: bool = True
    env:     dict[str, str] | None = None


def _build_server_configs() -> list[MCPServerConfig]:
    """
    Build the list of MCP servers to connect to.
    Current servers:
      1. filesystem  — local file ops (sandbox dir)
      2. fetch       — fetch any public URL (remote, no API key)
      3. github      — GitHub repo analyzer (custom, built by us)
    """
    import sys

    sandbox = os.path.abspath(os.getenv(
        "MCP_FILESYSTEM_ROOT",
        os.path.join(os.path.dirname(__file__), "..", "..", "guardian-sandbox"),
    ))

    _backend_dir       = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    github_server_path = os.path.join(_backend_dir, "custom_mcp", "github_server.py")

    return [
        # ── 1. Filesystem MCP (local sandbox) ─────────────────────────────────
        MCPServerConfig(
            name    = "filesystem",
            command = "npx",
            args    = ["-y", "@modelcontextprotocol/server-filesystem", "/home/anshumandutta"],
            enabled = os.getenv("MCP_FILESYSTEM_ENABLED", "true").lower() == "true",
        ),

        # ── 2. Fetch MCP (remote — fetches any public URL) ────────────────────
        # Uses the Python mcp-server-fetch package (pip install mcp-server-fetch)
        MCPServerConfig(
            name    = "fetch",
            command = sys.executable,
            args    = ["-m", "mcp_server_fetch"],
            enabled = os.getenv("MCP_FETCH_ENABLED", "true").lower() == "true",
        ),

        # ── 3. GitHub Analyzer MCP (custom Python server) ─────────────────────
        MCPServerConfig(
            name    = "github",
            command = sys.executable,
            args    = [github_server_path],
            enabled = os.getenv("MCP_GITHUB_ENABLED", "true").lower() == "true",
            env     = {
                "GITHUB_TOKEN": os.getenv("GITHUB_TOKEN", ""),
                "PYTHONPATH":   _backend_dir,
            },
        ),

        # ── 4. SQLite Notes MCP (custom Python server) ────────────────────────
        MCPServerConfig(
            name    = "sqlite",
            command = sys.executable,
            args    = [os.path.join(_backend_dir, "custom_mcp", "sqlite_server.py")],
            enabled = os.getenv("MCP_SQLITE_ENABLED", "true").lower() == "true",
            env     = {
                "PYTHONPATH": _backend_dir,
            },
        ),
    ]


# ── Registry ──────────────────────────────────────────────────────────────────

class MCPServerRegistry:
    """
    Central registry for all MCP server connections.

    Tool discovery is live — calling get_openai_tools() returns whatever
    the connected servers expose right now.
    """

    def __init__(self) -> None:
        self._clients:    list[MCPClient] = []
        # Cache: tool_name → MCPClient that owns it
        self._tool_map:   dict[str, MCPClient] = {}

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def startup(self) -> None:
        """Connect to all enabled MCP servers. Called from FastAPI lifespan."""
        configs = _build_server_configs()
        for cfg in configs:
            if not cfg.enabled:
                logger.info("MCP server disabled | name=%s", cfg.name)
                continue
            client = MCPClient(cfg.name, cfg.command, cfg.args, cfg.env)
            try:
                await client.connect()
                self._clients.append(client)
            except Exception as exc:
                logger.error(
                    "Failed to connect to MCP server '%s': %s. Skipping.", cfg.name, exc
                )
            except BaseException as exc:   # CancelledError etc.
                logger.error(
                    "MCP server '%s' failed with non-Exception: %s. Skipping.", cfg.name, type(exc).__name__
                )

        await self._refresh_tool_map()
        logger.info(
            "MCP registry ready | servers=%d | tools=%d",
            len(self._clients),
            len(self._tool_map),
        )

    async def shutdown(self) -> None:
        """Disconnect from all MCP servers. Called from FastAPI lifespan."""
        for client in self._clients:
            try:
                await client.disconnect()
            except Exception as exc:
                logger.warning("Error disconnecting '%s': %s", client.name, exc)
        self._clients.clear()
        self._tool_map.clear()

    async def _refresh_tool_map(self) -> None:
        """Rebuild the tool_name → client mapping from all live servers."""
        self._tool_map.clear()
        for client in self._clients:
            if not client.connected:
                continue
            try:
                tools = await client.list_tools()
                for tool in tools:
                    self._tool_map[tool.name] = client
                    logger.debug("Tool registered | name=%s | server=%s", tool.name, client.name)
            except Exception as exc:
                logger.error("Could not list tools from '%s': %s", client.name, exc)

    # ── Tool discovery ────────────────────────────────────────────────────────

    async def get_openai_tools(self) -> list[dict]:
        """
        Return all MCP tools as OpenAI function-calling definitions.
        Called before each agent turn so the LLM always sees live tools.
        """
        await self._refresh_tool_map()
        openai_tools = []
        for client in self._clients:
            if not client.connected:
                continue
            try:
                for tool in await client.list_tools():
                    openai_tools.append(_mcp_to_openai(tool))
            except Exception as exc:
                logger.warning("Tool discovery failed for '%s': %s", client.name, exc)
        return openai_tools

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._tool_map

    # ── Tool execution ────────────────────────────────────────────────────────

    async def call_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        """
        Route a tool call to the owning MCP server.

        Raises:
            KeyError:   If no connected server exposes this tool.
            RuntimeError: If the tool call itself fails.
        """
        client = self._tool_map.get(tool_name)
        if client is None:
            raise KeyError(
                f"Tool '{tool_name}' not found in any connected MCP server. "
                f"Available: {list(self._tool_map.keys())}"
            )
        return await client.call_tool(tool_name, args)

    # ── Status ────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        return {
            "servers": [
                {"name": c.name, "connected": c.connected}
                for c in self._clients
            ],
            "tool_count": len(self._tool_map),
            "tools": list(self._tool_map.keys()),
        }


# ── Converter: MCP Tool → OpenAI function definition ─────────────────────────

def _mcp_to_openai(tool) -> dict:
    """Convert an MCP Tool object to the OpenAI function-calling schema."""
    schema = tool.inputSchema if tool.inputSchema else {
        "type": "object", "properties": {}, "required": []
    }
    return {
        "type": "function",
        "function": {
            "name":        tool.name,
            "description": tool.description or f"MCP tool: {tool.name}",
            "parameters":  schema,
        },
    }


# ── Module-level singleton ────────────────────────────────────────────────────

registry = MCPServerRegistry()
