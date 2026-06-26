"""
LifeFind — case persistence (SQLite).

Cases survive restarts and can be shared by URL. Fully optional and defensive:
if the filesystem is read-only (e.g. serverless) or anything fails, the store
degrades to a no-op and the app keeps running from its in-memory working set.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time

import settings

log = logging.getLogger("lifefind.store")

_lock = threading.Lock()
_enabled = False


def init() -> bool:
    """Create the DB/table. Returns True if persistence is available."""
    global _enabled
    if not settings.PERSIST:
        log.info("persistence disabled by config")
        return False
    try:
        with _connect() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS cases ("
                "  id TEXT PRIMARY KEY,"
                "  data TEXT NOT NULL,"
                "  created_at REAL NOT NULL,"
                "  updated_at REAL NOT NULL)"
            )
        _enabled = True
        log.info("persistence ready at %s", settings.DB_PATH)
    except Exception as e:  # noqa: BLE001 — read-only fs etc. -> run in-memory only
        _enabled = False
        log.warning("persistence unavailable (%s) — running in-memory only", e)
    return _enabled


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(settings.DB_PATH, timeout=5, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    return con


def enabled() -> bool:
    return _enabled


def save(case: dict) -> None:
    if not _enabled:
        return
    try:
        now = time.time()
        payload = json.dumps(case, default=str)
        with _lock, _connect() as con:
            con.execute(
                "INSERT INTO cases (id, data, created_at, updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                (case["id"], payload, now, now),
            )
    except Exception as e:  # noqa: BLE001 — never let persistence break a search
        log.warning("save failed for case %s: %s", case.get("id"), e)


def load(case_id: str) -> dict | None:
    if not _enabled:
        return None
    try:
        with _lock, _connect() as con:
            row = con.execute("SELECT data FROM cases WHERE id=?", (case_id,)).fetchone()
        return json.loads(row[0]) if row else None
    except Exception as e:  # noqa: BLE001
        log.warning("load failed for case %s: %s", case_id, e)
        return None


def recent(limit: int = 200) -> list[dict]:
    """Most-recently-updated cases (for reverse search). [] if unavailable."""
    if not _enabled:
        return []
    try:
        with _lock, _connect() as con:
            rows = con.execute("SELECT data FROM cases ORDER BY updated_at DESC LIMIT ?",
                               (limit,)).fetchall()
        return [json.loads(r[0]) for r in rows]
    except Exception as e:  # noqa: BLE001
        log.warning("recent failed: %s", e)
        return []


def purge_expired() -> int:
    """Delete cases older than CASE_TTL_DAYS. Returns rows removed."""
    if not _enabled:
        return 0
    try:
        cutoff = time.time() - settings.CASE_TTL_DAYS * 86400
        with _lock, _connect() as con:
            cur = con.execute("DELETE FROM cases WHERE updated_at < ?", (cutoff,))
            return cur.rowcount or 0
    except Exception as e:  # noqa: BLE001
        log.warning("purge failed: %s", e)
        return 0
