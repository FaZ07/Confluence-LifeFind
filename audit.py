"""
LifeFind — append-only, hash-chained audit trail.

Every analyst action in a case (a lead approved or rejected, a footage source
worked, two entities merged, a report filed) is written here as an immutable
event with a UTC timestamp and a SHA-256 hash that chains to the previous entry.
Tampering with any past event breaks the chain, so the log is verifiable — the
"who saw what, and when" record an investigation needs to stand up to scrutiny.

Deterministic and self-contained: no keys, no external service. Persists to the
same SQLite database as cases; degrades to an in-memory log when there is no
writable disk (serverless), so an append never hard-fails.
"""
from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from datetime import UTC, datetime

import settings

log = logging.getLogger("lifefind.audit")

_LOCK = threading.Lock()
_MEM: dict[str, list[dict]] = {}          # case_id -> events (fallback / serverless)
_GENESIS = "0" * 64                        # hash that the first entry chains from


def _enabled() -> bool:
    return settings.PERSIST


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(settings.DB_PATH, timeout=5)
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init() -> None:
    """Create the audit table (no-op when there's no writable disk)."""
    if not _enabled():
        return
    try:
        with _conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS audit(
                       seq      INTEGER PRIMARY KEY AUTOINCREMENT,
                       case_id  TEXT NOT NULL,
                       ts       TEXT NOT NULL,
                       actor    TEXT NOT NULL,
                       action   TEXT NOT NULL,
                       detail   TEXT NOT NULL,
                       prev     TEXT NOT NULL,
                       hash     TEXT NOT NULL)"""
            )
            c.execute("CREATE INDEX IF NOT EXISTS audit_case ON audit(case_id, seq)")
    except Exception as e:  # noqa: BLE001 — never let logging infra break the app
        log.warning("audit init failed, using memory log: %s", e)


def _digest(prev: str, ts: str, actor: str, action: str, detail: dict) -> str:
    payload = json.dumps(
        {"prev": prev, "ts": ts, "actor": actor, "action": action, "detail": detail},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _last_hash(case_id: str) -> str:
    if _enabled():
        try:
            with _conn() as c:
                row = c.execute(
                    "SELECT hash FROM audit WHERE case_id=? ORDER BY seq DESC LIMIT 1",
                    (case_id,),
                ).fetchone()
                if row:
                    return row[0]
        except Exception:  # noqa: BLE001
            pass
    mem = _MEM.get(case_id)
    return mem[-1]["hash"] if mem else _GENESIS


def append(case_id: str, action: str, detail: dict | None = None,
           actor: str = "analyst") -> dict:
    """Append one immutable, hash-chained event. Returns the stored entry."""
    detail = detail or {}
    with _LOCK:
        prev = _last_hash(case_id)
        ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        h = _digest(prev, ts, actor, action, detail)
        entry = {"ts": ts, "actor": actor, "action": action,
                 "detail": detail, "prev": prev, "hash": h}
        stored = False
        if _enabled():
            try:
                with _conn() as c:
                    c.execute(
                        "INSERT INTO audit(case_id,ts,actor,action,detail,prev,hash) "
                        "VALUES(?,?,?,?,?,?,?)",
                        (case_id, ts, actor, action,
                         json.dumps(detail, ensure_ascii=False), prev, h),
                    )
                stored = True
            except Exception as e:  # noqa: BLE001
                log.warning("audit persist failed (%s): %s", case_id, e)
        if not stored:
            _MEM.setdefault(case_id, []).append(entry)
    return entry


def events(case_id: str, limit: int = 500) -> list[dict]:
    """Return the case's events, oldest first."""
    if _enabled():
        try:
            with _conn() as c:
                rows = c.execute(
                    "SELECT ts,actor,action,detail,prev,hash FROM audit "
                    "WHERE case_id=? ORDER BY seq ASC LIMIT ?",
                    (case_id, limit),
                ).fetchall()
            if rows:
                return [{"ts": r[0], "actor": r[1], "action": r[2],
                         "detail": json.loads(r[3] or "{}"), "prev": r[4], "hash": r[5]}
                        for r in rows]
        except Exception:  # noqa: BLE001
            pass
    return list(_MEM.get(case_id, []))[:limit]


def verify(case_id: str) -> dict:
    """Recompute the hash chain end-to-end; report whether it's intact."""
    evs = events(case_id)
    prev = _GENESIS
    for i, e in enumerate(evs):
        if e.get("prev") != prev:
            return {"intact": False, "broken_at": i, "count": len(evs)}
        if _digest(prev, e["ts"], e["actor"], e["action"], e["detail"]) != e["hash"]:
            return {"intact": False, "broken_at": i, "count": len(evs)}
        prev = e["hash"]
    return {"intact": True, "broken_at": None, "count": len(evs)}
