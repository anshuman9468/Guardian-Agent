"""
sqlite_server.py — Custom MCP server for a SQLite-backed Notes database.

Tools:
  1. create_note(title, content)
  2. read_note(title)
  3. search_notes(keyword)
  4. list_notes()
  5. delete_note(title)

Registered in server_registry.py as a stdio MCP server.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any

from mcp.server.fastmcp import FastMCP

# ── Setup ─────────────────────────────────────────────────────────────────────

mcp = FastMCP("sqlite-notes")

# We'll store the database in the backend directory so it persists
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "notes.db")

def _get_db() -> sqlite3.Connection:
    """Get a database connection and ensure the table exists."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT UNIQUE NOT NULL,
            content TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    return conn


# ── Tool 1: create_note ───────────────────────────────────────────────────────

@mcp.tool()
def create_note(title: str, content: str) -> str:
    """
    Create a new note or update an existing one in the database.

    Args:
        title:   The title of the note. Must be unique.
        content: The body of the note.
    """
    try:
        with _get_db() as conn:
            conn.execute(
                """
                INSERT INTO notes (title, content) 
                VALUES (?, ?)
                ON CONFLICT(title) DO UPDATE SET 
                    content = excluded.content,
                    created_at = CURRENT_TIMESTAMP
                """,
                (title, content)
            )
        return f"✅ Note '{title}' saved successfully."
    except Exception as e:
        return f"❌ Error saving note: {e}"


# ── Tool 2: read_note ─────────────────────────────────────────────────────────

@mcp.tool()
def read_note(title: str) -> str:
    """
    Read the contents of a specific note by title.

    Args:
        title: The exact title of the note to read.
    """
    try:
        with _get_db() as conn:
            cur = conn.execute("SELECT content, created_at FROM notes WHERE title = ?", (title,))
            row = cur.fetchone()
            if not row:
                return f"❌ Note '{title}' not found."
            return (
                f"📝 {title}\n"
                f"🕒 Last updated: {row['created_at']}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{row['content']}"
            )
    except Exception as e:
        return f"❌ Error reading note: {e}"


# ── Tool 3: search_notes ──────────────────────────────────────────────────────

@mcp.tool()
def search_notes(keyword: str) -> str:
    """
    Search the database for notes containing a specific keyword in title or content.

    Args:
        keyword: The word or phrase to search for.
    """
    try:
        with _get_db() as conn:
            # We use LIKE for simple case-insensitive search
            term = f"%{keyword}%"
            cur = conn.execute(
                "SELECT title, content FROM notes WHERE title LIKE ? OR content LIKE ?", 
                (term, term)
            )
            rows = cur.fetchall()
            
            if not rows:
                return f"🔍 No notes found containing '{keyword}'."
                
            lines = [f"🔍 Search results for '{keyword}' ({len(rows)} found):\n"]
            for r in rows:
                # snippet preview
                snippet = r["content"][:60].replace("\n", " ")
                snippet = f"{snippet}..." if len(r["content"]) > 60 else snippet
                lines.append(f"• {r['title']}: {snippet}")
            return "\n".join(lines)
    except Exception as e:
        return f"❌ Error searching notes: {e}"


# ── Tool 4: list_notes ────────────────────────────────────────────────────────

@mcp.tool()
def list_notes() -> str:
    """
    List the titles of all notes currently stored in the database.
    """
    try:
        with _get_db() as conn:
            cur = conn.execute("SELECT title, created_at FROM notes ORDER BY created_at DESC")
            rows = cur.fetchall()
            
            if not rows:
                return "📂 The database is empty."
                
            lines = [f"📂 All Notes ({len(rows)}):\n"]
            for r in rows:
                lines.append(f"• {r['title']}  (Updated: {r['created_at']})")
            return "\n".join(lines)
    except Exception as e:
        return f"❌ Error listing notes: {e}"


# ── Tool 5: delete_note ───────────────────────────────────────────────────────

@mcp.tool()
def delete_note(title: str) -> str:
    """
    Delete a note from the database by its title.

    Args:
        title: The exact title of the note to delete.
    """
    try:
        with _get_db() as conn:
            cur = conn.execute("DELETE FROM notes WHERE title = ?", (title,))
            if cur.rowcount == 0:
                return f"❌ Note '{title}' not found. Nothing deleted."
            return f"🗑️ Note '{title}' deleted permanently."
    except Exception as e:
        return f"❌ Error deleting note: {e}"


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="sse", port=8002)
