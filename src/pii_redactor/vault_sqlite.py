"""Persistent vault backed by SQLite — survives process restarts.

Drop-in replacement for Vault when you need durability.

Usage:
    vault = SqliteVault("session_abc", db_path="~/.pii-redactor/vault.db")
    # Same API as Vault: get_or_create_token, rehydrate, etc.
"""

from __future__ import annotations
import os
import sqlite3
from collections import defaultdict
from pathlib import Path


_TOKEN_FMT = "«{type}_{idx:03d}»"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS mappings (
    session_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    original TEXT NOT NULL,
    token TEXT NOT NULL,
    created_at REAL NOT NULL DEFAULT (julianday('now')),
    PRIMARY KEY (session_id, entity_type, original)
);
CREATE INDEX IF NOT EXISTS idx_mappings_token
    ON mappings(session_id, token);
CREATE TABLE IF NOT EXISTS counters (
    session_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, entity_type)
);
"""


class SqliteVault:
    """Persistent bidirectional PII ↔ token store."""

    __slots__ = ("_session_id", "_db", "_cache_pii", "_cache_token", "_counters")

    def __init__(self, session_id: str, *, db_path: str | Path = "vault.db") -> None:
        self._session_id = session_id
        db_path = Path(db_path).expanduser()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(db_path), check_same_thread=False)
        self._db.executescript(_SCHEMA)

        # In-memory caches (loaded from DB on init)
        self._cache_pii: dict[str, str] = {}   # "TYPE::original" → token
        self._cache_token: dict[str, str] = {}  # token → original
        self._counters: dict[str, int] = defaultdict(int)
        self._load()

    def _load(self) -> None:
        """Load existing mappings from DB into memory."""
        rows = self._db.execute(
            "SELECT entity_type, original, token FROM mappings WHERE session_id = ?",
            (self._session_id,),
        ).fetchall()
        for etype, orig, token in rows:
            key = f"{etype}::{orig}"
            self._cache_pii[key] = token
            self._cache_token[token] = orig

        crows = self._db.execute(
            "SELECT entity_type, count FROM counters WHERE session_id = ?",
            (self._session_id,),
        ).fetchall()
        for etype, count in crows:
            self._counters[etype] = count

    def get_or_create_token(self, entity_type: str, original: str) -> str:
        key = f"{entity_type}::{original}"
        if key in self._cache_pii:
            return self._cache_pii[key]

        self._counters[entity_type] += 1
        token = _TOKEN_FMT.format(type=entity_type, idx=self._counters[entity_type])

        self._db.execute(
            "INSERT OR REPLACE INTO counters (session_id, entity_type, count) VALUES (?, ?, ?)",
            (self._session_id, entity_type, self._counters[entity_type]),
        )
        self._db.execute(
            "INSERT INTO mappings (session_id, entity_type, original, token) VALUES (?, ?, ?, ?)",
            (self._session_id, entity_type, original, token),
        )
        self._db.commit()

        self._cache_pii[key] = token
        self._cache_token[token] = original
        return token

    def rehydrate(self, text: str) -> str:
        result = text
        for token in sorted(self._cache_token, key=len, reverse=True):
            if token in result:
                result = result.replace(token, self._cache_token[token])
        return result

    def lookup_token(self, token: str) -> str | None:
        return self._cache_token.get(token)

    def lookup_pii(self, entity_type: str, original: str) -> str | None:
        return self._cache_pii.get(f"{entity_type}::{original}")

    @property
    def size(self) -> int:
        return len(self._cache_token)

    def dump(self) -> dict[str, str]:
        return dict(self._cache_token)

    def clear(self) -> None:
        self._db.execute("DELETE FROM mappings WHERE session_id = ?", (self._session_id,))
        self._db.execute("DELETE FROM counters WHERE session_id = ?", (self._session_id,))
        self._db.commit()
        self._cache_pii.clear()
        self._cache_token.clear()
        self._counters.clear()

    def close(self) -> None:
        self._db.close()

    def list_sessions(self) -> list[str]:
        """List all session IDs in the database."""
        rows = self._db.execute("SELECT DISTINCT session_id FROM mappings").fetchall()
        return [r[0] for r in rows]

    def delete_session(self, session_id: str) -> None:
        """Delete all mappings for a session."""
        self._db.execute("DELETE FROM mappings WHERE session_id = ?", (session_id,))
        self._db.execute("DELETE FROM counters WHERE session_id = ?", (session_id,))
        self._db.commit()
        if session_id == self._session_id:
            self._cache_pii.clear()
            self._cache_token.clear()
            self._counters.clear()
