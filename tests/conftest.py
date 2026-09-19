from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from callfirst import webhooks
from callfirst.household import Household, Trusted

KEY = "test-signing-key"
# A Tuesday, 15:00 in New York.
T0 = datetime(2026, 9, 22, 19, 0, tzinfo=UTC)

DOORBELL, CHIME, SENSOR = "db-1", "ch-1", "cs-1"


def payload(kind: str, device: str, at: datetime, sub_type: str | None = None,
            sent: datetime | None = None, request_id: str | None = None) -> bytes:
    """A v1.1 webhook body, the shape Ring (and ring-sandbox) sends."""
    attributes = {"source": device, "source_type": "devices",
                  "timestamp": int(at.timestamp() * 1000)}
    if sub_type:
        attributes["sub_type"] = sub_type
    body = {
        "meta": {"version": "1.1", "time": (sent or at).isoformat().replace("+00:00", "Z"),
                 "request_id": request_id or str(uuid.uuid4()), "account_id": "acct"},
        "data": {"id": f"{device}_{kind}", "type": kind, "attributes": attributes},
    }
    return json.dumps(body, separators=(",", ":"), sort_keys=True).encode()


def event(kind: str, device: str, at: datetime, sub_type: str | None = None) -> webhooks.Event:
    raw = payload(kind, device, at, sub_type)
    return webhooks.read(KEY, raw, webhooks.sign(KEY, raw), at)


def ring(at): return event("button_press", DOORBELL, at)
def person(at): return event("motion_detected", DOORBELL, at, "human")
def door(at): return event("contact_sensor_faulted", SENSOR, at)
def offline(at): return event("device_offline", DOORBELL, at)


def seconds(n: float) -> timedelta:
    return timedelta(seconds=n)


@pytest.fixture
def home() -> Household:
    """Sensor mode, switched on, one trusted person."""
    return Household(id="h1", doorbell=DOORBELL, chime=CHIME, sensor=SENSOR, enabled=True,
                     trusted=[Trusted("Sarah", "sarah@example.com")])


@pytest.fixture
def bell_only(home) -> Household:
    home.sensor = None
    return home
