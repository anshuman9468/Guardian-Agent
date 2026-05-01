import os
import sqlite3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx

app = FastAPI(title="Unified MCP Microservice")

# ==========================================
# 1. FILESYSTEM SERVICE
# ==========================================
BASE_DIR = "/opt/render/project/src"

def is_safe_path(path):
    return os.path.abspath(path).startswith(BASE_DIR)

@app.get("/filesystem/read")
def read_file(path: str):
    if not is_safe_path(path):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    with open(path, "r") as f:
        return {"content": f.read()}

# ==========================================
# 2. FETCH SERVICE
# ==========================================
@app.get("/fetch")
async def fetch(url: str):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    async with httpx.AsyncClient() as client:
        res = await client.get(url)
        return {"content": res.text}

# ==========================================
# 3. GITHUB SERVICE
# ==========================================
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
github_headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

@app.get("/github/repo")
async def get_repo(owner: str, repo: str):
    url = f"https://api.github.com/repos/{owner}/{repo}"
    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=github_headers)
        return res.json()

@app.get("/github/issues")
async def get_issues(owner: str, repo: str, limit: int = 5):
    url = f"https://api.github.com/repos/{owner}/{repo}/issues?per_page={limit}"
    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=github_headers)
        return res.json()

@app.get("/github/languages")
async def get_languages(owner: str, repo: str):
    url = f"https://api.github.com/repos/{owner}/{repo}/languages"
    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=github_headers)
        return res.json()

@app.get("/github/search")
async def search_repos(query: str, limit: int = 5):
    url = f"https://api.github.com/search/repositories?q={query}&per_page={limit}"
    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=github_headers)
        return res.json()

# ==========================================
# 4. SQLITE SERVICE
# ==========================================
DB_PATH = "notes.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
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
    conn.close()

init_db()

class NoteCreate(BaseModel):
    title: str
    content: str

@app.post("/sqlite/notes/create")
def create_note(note: NoteCreate):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO notes (title, content) VALUES (?, ?) ON CONFLICT(title) DO UPDATE SET content=?",
            (note.title, note.content, note.content)
        )
        conn.commit()
        return {"text": f"Note '{note.title}' saved."}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

@app.get("/sqlite/notes/read")
def read_note(title: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT content FROM notes WHERE title = ?", (title,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"text": row["content"]}
    return {"error": "Note not found."}

@app.get("/sqlite/notes/list")
def list_notes():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT title FROM notes")
    rows = cur.fetchall()
    conn.close()
    return {"text": "\n".join([r["title"] for r in rows]) if rows else "No notes found."}

@app.get("/sqlite/notes/search")
def search_notes(keyword: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT title FROM notes WHERE content LIKE ?", (f"%{keyword}%",))
    rows = cur.fetchall()
    conn.close()
    return {"text": "\n".join([r["title"] for r in rows]) if rows else "No matching notes."}

@app.delete("/sqlite/notes/delete")
def delete_note(title: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM notes WHERE title = ?", (title,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return {"text": "Note deleted." if deleted else "Note not found."}
