"""
sqlite_server.py — Standalone FastAPI service for a SQLite-backed Notes database.

Run standalone:
  uvicorn custom_mcp.sqlite_server:app --host 0.0.0.0 --port 10002
"""

import os
import sqlite3
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="SQLite Service")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "notes.db")

def _get_db() -> sqlite3.Connection:
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

class NoteCreate(BaseModel):
    title: str
    content: str

@app.post("/notes/create")
def create_note(note: NoteCreate):
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
                (note.title, note.content)
            )
        return {"text": f"✅ Note '{note.title}' saved successfully."}
    except Exception as e:
        return {"error": f"Error saving note: {e}"}

@app.get("/notes/read")
def read_note(title: str):
    try:
        with _get_db() as conn:
            cur = conn.execute("SELECT content, created_at FROM notes WHERE title = ?", (title,))
            row = cur.fetchone()
            if not row:
                return {"error": f"Note '{title}' not found."}
            return {
                "text": (
                    f"📝 {title}\n"
                    f"🕒 Last updated: {row['created_at']}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{row['content']}"
                )
            }
    except Exception as e:
        return {"error": f"Error reading note: {e}"}

@app.get("/notes/search")
def search_notes(keyword: str):
    try:
        with _get_db() as conn:
            term = f"%{keyword}%"
            cur = conn.execute(
                "SELECT title, content FROM notes WHERE title LIKE ? OR content LIKE ?", 
                (term, term)
            )
            rows = cur.fetchall()
            
            if not rows:
                return {"text": f"🔍 No notes found containing '{keyword}'."}
                
            lines = [f"🔍 Search results for '{keyword}' ({len(rows)} found):\n"]
            for r in rows:
                snippet = r["content"][:60].replace("\n", " ")
                snippet = f"{snippet}..." if len(r["content"]) > 60 else snippet
                lines.append(f"• {r['title']}: {snippet}")
            return {"text": "\n".join(lines)}
    except Exception as e:
        return {"error": f"Error searching notes: {e}"}

@app.get("/notes/list")
def list_notes():
    try:
        with _get_db() as conn:
            cur = conn.execute("SELECT title, created_at FROM notes ORDER BY created_at DESC")
            rows = cur.fetchall()
            
            if not rows:
                return {"text": "📂 The database is empty."}
                
            lines = [f"📂 All Notes ({len(rows)}):\n"]
            for r in rows:
                lines.append(f"• {r['title']}  (Updated: {r['created_at']})")
            return {"text": "\n".join(lines)}
    except Exception as e:
        return {"error": f"Error listing notes: {e}"}

@app.delete("/notes/delete")
def delete_note(title: str):
    try:
        with _get_db() as conn:
            cur = conn.execute("DELETE FROM notes WHERE title = ?", (title,))
            if cur.rowcount == 0:
                return {"error": f"Note '{title}' not found. Nothing deleted."}
            return {"text": f"🗑️ Note '{title}' deleted permanently."}
    except Exception as e:
        return {"error": f"Error deleting note: {e}"}
