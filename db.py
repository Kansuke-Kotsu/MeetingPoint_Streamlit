import sqlite3
from pathlib import Path
from typing import List, Dict

class MinutesDB:
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("""CREATE TABLE IF NOT EXISTS minutes
            (id INTEGER PRIMARY KEY AUTOINCREMENT,
             title TEXT,
             transcript TEXT,
             minutes_md TEXT,
             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        self.conn.commit()

    def save_minutes(self, title: str, transcript: str, minutes_md: str):
        self.conn.execute(
            "INSERT INTO minutes (title, transcript, minutes_md) VALUES (?,?,?)",
            (title, transcript, minutes_md))
        self.conn.commit()

    def fetch_all_minutes(self) -> List[Dict]:
        cur = self.conn.execute("SELECT title, minutes_md FROM minutes ORDER BY created_at DESC")
        return [dict(title=row[0], minutes_md=row[1]) for row in cur.fetchall()]

    def fetch_latest_minutes(self):
        cur = self.conn.execute("SELECT title, minutes_md FROM minutes ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        return dict(title=row[0], minutes_md=row[1]) if row else None
