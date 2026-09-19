"""Ring webhooks: signature, shape, freshness.

Ring signs the raw body with HMAC-SHA256 and sends ``X-Signature: sha256=<hex>``.
There is no timestamp header, so freshness has to come from inside the signed
body: ``meta.time`` says when Ring sent it, ``meta.request_id`` is unique per
delivery. A replay is either stale or a request_id already seen - the caller
checks the second against its store.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

PREFIX = "sha256="
# How old a delivery may be when it arrives. Ring retries and delays exist; a
# replayed capture from yesterday does not get in.
MAX_AGE = timedelta(minutes=10)
MAX_SKEW = timedelta(minutes=1)

KINDS = {
    "button_press", "motion_detected", "device_online", "device_offline",
    "contact_sensor_faulted", "contact_sensor_cleared",
}


class Rejected(ValueError):
    """The request is not a genuine, fresh Ring webhook. ``reason`` is loggable."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class Event:
    request_id: str
    sent_at: datetime
    kind: str
    device_id: str
    at: datetime
    sub_type: str | None = None

    @property
    def is_person(self) -> bool:
        return self.kind == "motion_detected" and self.sub_type == "human"


def sign(key: str, raw: bytes) -> str:
    return PREFIX + hmac.new(key.encode(), raw, hashlib.sha256).hexdigest()


def verify(key: str, raw: bytes, header: str | None) -> bool:
    if not key or not header:
        return False
    try:
        received = header.strip().encode("ascii")
    except UnicodeEncodeError:
        return False
    return hmac.compare_digest(sign(key, raw).encode("ascii"), received)


def _ms(value) -> datetime:
    return datetime.fromtimestamp(int(value) / 1000, tz=UTC)


def _iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def read(key: str, raw: bytes, header: str | None, now: datetime) -> Event | None:
    """Verify then parse. Returns None for event kinds this product ignores.

    Signature first, before anything in the body is looked at: an unsigned body
    is not parsed at all.
    """
    if not verify(key, raw, header):
        raise Rejected("bad signature")
    try:
        body = json.loads(raw)
        meta, data = body["meta"], body["data"]
        attributes = data["attributes"]
        sent_at = _iso(meta["time"])
        event = Event(
            request_id=str(meta["request_id"]),
            sent_at=sent_at,
            kind=str(data["type"]),
            device_id=str(attributes["source"]),
            at=_ms(attributes["timestamp"]),
            sub_type=attributes.get("sub_type"),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise Rejected(f"malformed payload: {error.__class__.__name__}") from None
    if now - event.sent_at > MAX_AGE:
        raise Rejected("stale delivery")
    if event.sent_at - now > MAX_SKEW:
        raise Rejected("delivery from the future")
    return event if event.kind in KINDS else None
