import os

MCP_SERVERS = {
    "filesystem": os.getenv("MCP_FILESYSTEM_URL", "https://filesystem-mcp.onrender.com"),
    "fetch": os.getenv("MCP_FETCH_URL", "https://fetch-mcp.onrender.com"),
    "github": os.getenv("MCP_GITHUB_URL", "https://github-mcp.onrender.com"),
    "sqlite": os.getenv("MCP_SQLITE_URL", "https://sqlite-mcp.onrender.com"),
}
