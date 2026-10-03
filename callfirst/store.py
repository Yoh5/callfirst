"""SQLite, with every household encrypted at rest.

A household record says when an older person is expected to be alone and who
their family is (threat (d) in DESIGN.md). It is stored as one Fernet token;
the key lives in the environment, never in the database or the repository.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
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
create table if not exists access (
    token_hash text primary key, household text not null, role text not null,
    email_key text, email blob);
create table if not exists journal (
    id integer primary key autoincrement, household text, at text not null, text blob not null);
"""


class _Rows:
    def __init__(self, rows: list, lastrowid: int | None):
        self.rows, self.lastrowid = rows, lastrowid

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class _Serialized:
    """One sqlite3 connection shared by request threads, the tick thread and
    the action threads. sqlite3 does not make that safe by itself: under load
    it raised spurious constraint errors and returned half-read rows (found by
    scripts/chaos.py). Every statement now runs, and is read to the end, under
    one lock."""

    def __init__(self, connection: sqlite3.Connection):
        self._connection = connection
        self._lock = threading.Lock()

    def execute(self, sql: str, params: tuple = ()) -> _Rows:
        with self._lock:
            cursor = self._connection.execute(sql, params)
            return _Rows(cursor.fetchall(), cursor.lastrowid)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Store:
    def __init__(self, path: str | Path, key: str | bytes):
        self._fernet = Fernet(key)
        # Keyed, so a copy of the database cannot confirm a guessed address.
        self._pepper = hashlib.sha256(b"callfirst-email:" + (key if isinstance(key, bytes)
                                                              else key.encode())).digest()
        # A second keyed secret, for the one link that has to work without a
        # session: the report sheet in an alert email. Separate from the e-mail
        # pepper, so that neither can be made to answer the other's question.
        self._link_pepper = hashlib.sha256(
            b"callfirst-report-link:" + (key if isinstance(key, bytes) else key.encode())
        ).digest()
        connection = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        connection.executescript(SCHEMA)
        self._db = _Serialized(connection)
        self._lock = threading.RLock()     # groups of statements that belong together

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
                                  ("outbox", "household"), ("journal", "household"),
                                  ("access", "household")):
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

    def send(self, household_id: str, at: str, kind: str, body: dict) -> int:
        blob = self._fernet.encrypt(json.dumps(body).encode())
        cursor = self._db.execute(
            "insert into outbox (household, at, kind, body) values (?, ?, ?, ?)",
            (household_id, at, kind, blob))
        return cursor.lastrowid

    def sent(self, household_id: str) -> list[dict]:
        rows = self._db.execute("select id, at, kind, body from outbox where household = ? "
                                "order by id", (household_id,))
        return [{"id": id_, "at": at, "kind": kind, **json.loads(self._fernet.decrypt(body))}
                for id_, at, kind, body in rows]

    def mark_delivered(self, household_id: str, sent_id: int,
                       manques: list[str]) -> None:
        """Record, on the alert itself, who it did not reach.

        The alert is written before the send is attempted, which is the right
        order: a message that crashes the process still leaves a record. But
        the outcome then has to come back and land on it, or the alert sits in
        the resident's list looking exactly like one that arrived. The journal
        already said `alert email FAILED`; nobody reads the journal.
        """
        with self._lock:
            row = self._db.execute(
                "select body from outbox where household = ? and id = ?",
                (household_id, sent_id)).fetchone()
            if not row:
                return
            corps = json.loads(self._fernet.decrypt(row[0]))
            # An alert with no recipients at all had nothing to fail, so
            # `not manques` was True and it reported itself as delivered. That
            # is the purest form of the thing this flag exists to prevent: the
            # last trusted person leaves, the door keeps working, every alert
            # is addressed to nobody, and the list says they all arrived.
            # `renderAlerts` has had the message for this state from the start
            # -- "This reached nobody. Call them." for an empty
            # `not_delivered` -- and the server could never produce it.
            corps["delivered"] = bool(corps.get("recipients")) and not manques
            corps["not_delivered"] = manques
            self._db.execute("update outbox set body = ? where household = ? and id = ?",
                             (self._fernet.encrypt(json.dumps(corps).encode()),
                              household_id, sent_id))

    def one_sent(self, household_id: str, sent_id: int) -> dict | None:
        """Scoped to the household: an id from another household reads as missing."""
        row = self._db.execute("select id, at, kind, body from outbox where household = ? "
                               "and id = ?", (household_id, sent_id)).fetchone()
        if not row:
            return None
        return {"id": row[0], "at": row[1], "kind": row[2],
                **json.loads(self._fernet.decrypt(row[3]))}

    # ------------------------------------------------------------------ who may look

    def grant(self, household_id: str, role: str, email: str | None = None) -> str:
        """A new access link token. Only its hash is kept: a stolen database
        opens no page."""
        token = secrets.token_urlsafe(32)
        with self._lock:
            if email:
                self.revoke(household_id, email)
            self._db.execute("insert into access values (?, ?, ?, ?, ?)",
                             (_hash(token), household_id, role, self._email_key(email),
                              self._fernet.encrypt(email.encode()) if email else None))
        return token

    def report_key(self, household_id: str, sent_id: int, email: str) -> str:
        """An unguessable key for one alert and one recipient, stored nowhere.

        The alert email's only link went to `/family/report/{id}`, which needs
        a session. The daughter opens the invitation on her laptop and reads
        the alert on her phone, where that cookie has never existed: the one
        artifact the submission calls printable answered "open the link you
        were sent", on the device the alert arrived on.

        A key derived from the household, the alert and the address. Nothing is
        stored, so there is nothing extra to leak and nothing to clean up; it
        opens that one report and no other page; and it dies with the key, not
        with a session. The access tokens cannot serve here -- `grant()`
        revokes the previous one, so putting a fresh link in every alert would
        log her out of the page she may have open.
        """
        mac = hmac.new(self._link_pepper,
                       f"{household_id}:{sent_id}:{email.lower()}".encode(),
                       hashlib.sha256).digest()
        return base64.urlsafe_b64encode(mac[:16]).decode().rstrip("=")

    def one_sent_by_id(self, sent_id: int) -> tuple[str, dict] | None:
        """The alert with this id, and the household it belongs to.

        `id` is `integer primary key autoincrement`, so it is unique across
        households: a link needs to carry nothing but the number, and the
        household never appears in an email's URL.
        """
        row = self._db.execute("select household, kind, body from outbox where id = ?",
                               (sent_id,)).fetchone()
        if not row or row[1] != "alert":
            return None
        return row[0], json.loads(self._fernet.decrypt(row[2])) | {"id": sent_id}

    def resolve(self, token: str) -> tuple[str, str, str | None] | None:
        row = self._db.execute("select household, role, email from access where token_hash = ?",
                               (_hash(token),)).fetchone()
        if not row:
            return None
        return row[0], row[1], self._fernet.decrypt(row[2]).decode() if row[2] else None

    def revoke(self, household_id: str, email: str) -> None:
        self._db.execute("delete from access where household = ? and email_key = ?",
                         (household_id, self._email_key(email)))

    def _email_key(self, email: str | None) -> str | None:
        if not email:
            return None
        return hmac.new(self._pepper, email.lower().encode(), hashlib.sha256).hexdigest()

    def note(self, household_id: str | None, at: str, text: str) -> None:
        # Encrypted too: a journal line like "visit added: carer" is the schedule.
        self._db.execute("insert into journal (household, at, text) values (?, ?, ?)",
                         (household_id, at, self._fernet.encrypt(text.encode())))

    def journal(self, household_id: str | None = None) -> list[tuple[str, str]]:
        rows = self._db.execute("select at, text from journal where household is ? order by id",
                                (household_id,))
        return [(at, self._fernet.decrypt(text).decode()) for at, text in rows]
