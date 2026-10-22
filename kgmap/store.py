from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .core import ROOT, utcnow


class Store:
    """SQLite HTTP cache, transactional snapshot and independent durable reviews."""

    def __init__(self, path=None):
        self.path = Path(path or ROOT / "data/map.sqlite")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS cache
                    (key TEXT PRIMARY KEY, url TEXT, fetched_at TEXT, body BLOB, content_type TEXT);
                CREATE TABLE IF NOT EXISTS snapshots
                    (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS reviews
                    (id TEXT PRIMARY KEY, status TEXT, note TEXT, updated_at TEXT);
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=15)

    def load(self):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM snapshots WHERE id=1").fetchone()
        if row:
            return json.loads(row[0])
        snapshot = self.path.parent / "snapshot.json"
        return json.loads(snapshot.read_text()) if snapshot.exists() else None

    def save(self, snapshot):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO snapshots VALUES (1,?,?)",
                       (json.dumps(snapshot, ensure_ascii=False), utcnow()))

    def reviews(self):
        with self.connect() as db:
            rows = db.execute("SELECT id,status,note,updated_at FROM reviews ORDER BY id").fetchall()
        return {r[0]: {"status": r[1], "note": r[2], "updated_at": r[3]} for r in rows}

    def review(self, edge_id, status, note=""):
        if status not in {"unreviewed", "accepted", "rejected", "corrected"}:
            raise ValueError("Review status must be unreviewed, accepted, rejected or corrected")
        if status == "corrected" and not note.strip():
            raise ValueError("A correction needs an explanatory note")
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO reviews VALUES (?,?,?,?)", (edge_id, status, note, utcnow()))

    def import_reviews(self, records):
        # Validate the whole file before making any changes.
        for key, r in records.items():
            if not isinstance(key, str) or r.get("status") not in {"unreviewed", "accepted", "rejected", "corrected"}:
                raise ValueError("Invalid review file")
            if r["status"] == "corrected" and not r.get("note", "").strip():
                raise ValueError("A correction needs a note")
        with self.connect() as db:
            for key, r in records.items():
                db.execute("INSERT OR REPLACE INTO reviews VALUES (?,?,?,?)",
                           (key, r["status"], r.get("note", ""), r.get("updated_at") or utcnow()))
