from fastapi import FastAPI
import sqlite3

app = FastAPI()

DB = "notes.db"

@app.get("/notes")
def list_notes():
    # Make sure we don't crash if the file doesn't exist
    conn = sqlite3.connect(DB)
    # Create the table if it doesn't exist so we don't error out
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

    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM notes")
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return {"notes": rows}
