"""SQLite persistence (历史记录 / 埋点 / 术语表).

A thin, dependency-free store. One connection guarded by a lock keeps it safe for
the handful of WebSocket worker threads the app runs. Pass ``":memory:"`` for tests.

Tables: ``sessions``, ``segments`` (transcript + translation), ``events``
(analytics / 埋点), ``glossary``, ``metrics`` (periodic QoS snapshots).
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Optional

from models import Segment

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    source_lang TEXT,
    mode        TEXT,
    started_at  REAL,
    ended_at    REAL
);
CREATE TABLE IF NOT EXISTS segments (
    session_id   TEXT,
    seg_id       INTEGER,
    source       TEXT,
    translation  TEXT,
    status       TEXT,
    version      INTEGER,
    corrected    INTEGER,
    glossary_hits INTEGER,
    t_audio      REAL,
    t_recognized REAL,
    t_translated REAL,
    PRIMARY KEY (session_id, seg_id)
);
CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    name       TEXT,
    ts         REAL,
    meta       TEXT
);
CREATE TABLE IF NOT EXISTS glossary (
    term        TEXT PRIMARY KEY,
    translation TEXT
);
CREATE TABLE IF NOT EXISTS metrics (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    ts         REAL,
    snapshot   TEXT
);
"""


class Store:
    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        if db_path not in (":memory:", "") and os.path.dirname(db_path):
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---------------------------------------------------------------- sessions
    def create_session(self, session_id: str, source_lang: str, mode: str,
                       started_at: Optional[float] = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO sessions(id, source_lang, mode, started_at, ended_at)"
                " VALUES (?,?,?,?,?)",
                (session_id, source_lang, mode, started_at or time.time(), None))
            self._conn.commit()

    def end_session(self, session_id: str, ended_at: Optional[float] = None) -> None:
        with self._lock:
            self._conn.execute("UPDATE sessions SET ended_at=? WHERE id=?",
                               (ended_at or time.time(), session_id))
            self._conn.commit()

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT s.*, (SELECT COUNT(*) FROM segments g WHERE g.session_id=s.id) AS segment_count"
                " FROM sessions s ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ---------------------------------------------------------------- segments
    def upsert_segment(self, seg: Segment) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO segments(session_id, seg_id, source, translation,"
                " status, version, corrected, glossary_hits, t_audio, t_recognized, t_translated)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (seg.session_id, seg.id, seg.source, seg.translation, seg.status,
                 seg.version, int(seg.corrected), seg.glossary_hits,
                 seg.t_audio, seg.t_recognized, seg.t_translated))
            self._conn.commit()

    def get_segments(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM segments WHERE session_id=? ORDER BY seg_id", (session_id,)).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ events
    def log_event(self, session_id: str, name: str, meta: Optional[dict] = None,
                  ts: Optional[float] = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events(session_id, name, ts, meta) VALUES (?,?,?,?)",
                (session_id, name, ts or time.time(),
                 json.dumps(meta or {}, ensure_ascii=False)))
            self._conn.commit()

    def event_counts(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT name, COUNT(*) AS c FROM events GROUP BY name").fetchall()
        return {r["name"]: r["c"] for r in rows}

    # ---------------------------------------------------------------- glossary
    def save_glossary(self, terms: dict[str, str]) -> None:
        with self._lock:
            for term, tr in terms.items():
                self._conn.execute(
                    "INSERT OR REPLACE INTO glossary(term, translation) VALUES (?,?)",
                    (term, tr))
            self._conn.commit()

    def load_glossary(self) -> dict[str, str]:
        with self._lock:
            rows = self._conn.execute("SELECT term, translation FROM glossary").fetchall()
        return {r["term"]: r["translation"] for r in rows}

    def delete_glossary_term(self, term: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM glossary WHERE term=?", (term,))
            self._conn.commit()

    # ------------------------------------------------------------------ metrics
    def save_metrics(self, session_id: str, snapshot: dict,
                     ts: Optional[float] = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO metrics(session_id, ts, snapshot) VALUES (?,?,?)",
                (session_id, ts or time.time(), json.dumps(snapshot, ensure_ascii=False)))
            self._conn.commit()

    def latest_metrics(self) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT snapshot FROM metrics ORDER BY id DESC LIMIT 1").fetchone()
        return json.loads(row["snapshot"]) if row else None
