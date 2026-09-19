"""SQLite, with every household encrypted at rest.

A household record says when an older person is expected to be alone and who
their family is (threat (d) in DESIGN.md). It is stored as one Fernet token;
the key lives in the environment, never in the database or the repository.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet

from .household import Household

SCHEMA = """
create table if not exists households (id text primary key, blob blob not null);
create table if not exists devices (device_id text primary key, household text not null);
create table if not exists seen (request_id text primary key, at text not null);
create table if not exists outbox (
    id integer primary key autoincrement, household text not null, at text not null,
    kind text not null, body blob not null);
create table if not exists journal (
    id integer primary key autoincrement, household text, at text not null, text blob not null);
"""


class Store:
    def __init__(self, path: str | Path, key: str | bytes):
        self._fernet = Fernet(key)
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.executescript(SCHEMA)
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ households

    def save(self, h: Household) -> None:
        blob = self._fernet.encrypt(json.dumps(h.to_dict()).encode())
        with self._lock:
            self._db.execute("insert or replace into households values (?, ?)", (h.id, blob))
            self._db.execute("delete from devices where household = ?", (h.id,))
            for device in filter(None, (h.doorbell, h.chime, h.sensor)):
                self._db.execute("insert or replace into devices values (?, ?)", (device, h.id))

    def load(self, household_id: str) -> Household | None:
        row = self._db.execute("select blob from households where id = ?",
                               (household_id,)).fetchone()
        return Household.from_dict(json.loads(self._fernet.decrypt(row[0]))) if row else None

    def owner_of(self, device_id: str) -> str | None:
        row = self._db.execute("select household from devices where device_id = ?",
                               (device_id,)).fetchone()
        return row[0] if row else None

    def delete(self, household_id: str) -> None:
        """Ring's policy: one action removes everything held for a household."""
        with self._lock:
            for table, column in (("households", "id"), ("devices", "household"),
                                  ("outbox", "household"), ("journal", "household")):
                self._db.execute(f"delete from {table} where {column} = ?", (household_id,))

    def all_ids(self) -> list[str]:
        return [r[0] for r in self._db.execute("select id from households")]

    # ------------------------------------------------------------------ replays

    def first_time(self, request_id: str, now: datetime) -> bool:
        """True once per request_id. Ring re-delivers; attackers replay."""
        with self._lock:
            # Anything older than the freshness window is rejected as stale
            # anyway, so the table only needs to remember a day.
            self._db.execute("delete from seen where at < ?",
                             ((now - timedelta(days=1)).isoformat(),))
            try:
                self._db.execute("insert into seen values (?, ?)", (request_id, now.isoformat()))
                return True
            except sqlite3.IntegrityError:
                return False

    # ------------------------------------------------------------------ what was said

    def send(self, household_id: str, at: str, kind: str, body: dict) -> None:
        blob = self._fernet.encrypt(json.dumps(body).encode())
        self._db.execute("insert into outbox (household, at, kind, body) values (?, ?, ?, ?)",
                         (household_id, at, kind, blob))

    def sent(self, household_id: str) -> list[dict]:
        rows = self._db.execute("select at, kind, body from outbox where household = ? "
                                "order by id", (household_id,))
        return [{"at": at, "kind": kind, **json.loads(self._fernet.decrypt(body))}
                for at, kind, body in rows]

    def note(self, household_id: str | None, at: str, text: str) -> None:
        # Encrypted too: a journal line like "visit added: carer" is the schedule.
        self._db.execute("insert into journal (household, at, text) values (?, ?, ?)",
                         (household_id, at, self._fernet.encrypt(text.encode())))

    def journal(self, household_id: str | None = None) -> list[tuple[str, str]]:
        rows = self._db.execute("select at, text from journal where household is ? order by id",
                                (household_id,))
        return [(at, self._fernet.decrypt(text).decode()) for at, text in rows]
