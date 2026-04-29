"""
mcp_client.py — Persistent MCP client for a single stdio-based server.

Wraps the official MCP Python SDK.
Uses AsyncExitStack to keep the connection alive across requests.

Usage:
    client = MCPClient("filesystem", "npx", ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"])
    await client.connect()
    tools  = await client.list_tools()
    result = await client.call_tool("read_file", {"path": "/tmp/test.txt"})
    await client.disconnect()
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool

logger = logging.getLogger(__name__)


class MCPClient:
    """Persistent connection to one MCP server over stdio."""

    def __init__(
        self,
        name: str,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> None:
        self.name        = name
        self.command     = command
        self.args        = args
        self.env         = env
        self._session:    ClientSession | None = None
        self._exit_stack  = AsyncExitStack()
        self.connected   = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Establish stdio connection and initialise the MCP session."""
        server_params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env=self.env,
        )
        try:
            read, write = await self._exit_stack.enter_async_context(
                stdio_client(server_params)
            )
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await self._session.initialize()
            self.connected = True
            logger.info("MCP connected | server=%s | cmd=%s %s", self.name, self.command, self.args)
        except Exception as exc:
            self.connected = False
            logger.error("MCP connect failed | server=%s | error=%s", self.name, exc)
            raise

    async def disconnect(self) -> None:
        """Tear down the connection gracefully."""
        await self._exit_stack.aclose()
        self.connected = False
        logger.info("MCP disconnected | server=%s", self.name)

    # ── Tool API ──────────────────────────────────────────────────────────────

    async def list_tools(self) -> list[Tool]:
        """Return the list of tools exposed by this server."""
        if not self._session:
            raise RuntimeError(f"MCPClient '{self.name}' is not connected.")
        response = await self._session.list_tools()
        return response.tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """
        Execute a tool and return its text output as a string.

        Args:
            name:      Tool name as advertised by the server.
            arguments: Tool arguments dict.

        Returns:
            String result (concatenated text content from all content blocks).
        """
        if not self._session:
            raise RuntimeError(f"MCPClient '{self.name}' is not connected.")

        logger.debug("MCP call_tool | server=%s | tool=%s | args=%s", self.name, name, arguments)
        result = await self._session.call_tool(name, arguments)

        # MCP results are a list of content blocks (text, image, etc.)
        # We concatenate all text blocks into a single string.
        parts = []
        for block in result.content:
            if hasattr(block, "text"):
                parts.append(block.text)
            else:
                parts.append(str(block))

        output = "\n".join(parts) if parts else "(no output)"
        logger.debug("MCP result | server=%s | tool=%s | output=%r", self.name, name, output[:200])
        return output

    # ── Helpers ───────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"MCPClient(name={self.name!r}, connected={self.connected})"
