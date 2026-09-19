"""The service end to end, with Ring replaced by a recorder."""
from __future__ import annotations

import sqlite3
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from callfirst import webhooks
from callfirst.app import create_app
from callfirst.store import Store

from .conftest import CHIME, DOORBELL, KEY, SENSOR, T0, payload, seconds

ADMIN = {"x-admin-token": "admin-test-token"}


class FakeRing:
    def __init__(self):
        self.played, self.snapped = [], []

    def play(self, chime, slot):
        self.played.append((chime, slot))
        return True

    def snapshot(self, camera, at):
        self.snapped.append((camera, at))
        return b"\xff\xd8jpeg"


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now


@pytest.fixture
def world(tmp_path):
    clock, ring = Clock(), FakeRing()
    store = Store(tmp_path / "t.db", Fernet.generate_key())
    app = create_app(store, ring, KEY, ADMIN["x-admin-token"], clock=clock, background=False)
    client = TestClient(app)
    r = client.post("/api/households", headers=ADMIN, json={
        "id": "home-1", "doorbell": DOORBELL, "chime": CHIME, "sensor": SENSOR,
        "trusted": [{"name": "Sarah", "email": "sarah@example.com"}]})
    assert r.status_code == 201
    client.post("/api/households/home-1/on", headers=ADMIN)

    class World:
        pass
    w = World()
    w.client, w.clock, w.ring, w.store, w.path, w.app = client, clock, ring, store, \
        tmp_path / "t.db", app

    def send(kind, device, at_offset=0.0, sub_type=None, raw=None, header=None):
        at = T0 + seconds(at_offset)
        clock.now = at
        raw = raw or payload(kind, device, at, sub_type)
        return client.post("/webhooks/ring", content=raw,
                           headers={"x-signature": header or webhooks.sign(KEY, raw)})
    w.send = send
    w.state = lambda: client.get("/api/households/home-1", headers=ADMIN).json()
    return w


def alerts(w, reason=None):
    return [s for s in w.state()["sent"] if s["kind"] == "alert"
            and (reason is None or s["reason"] == reason)]


def test_courier_scenario_end_to_end(world):
    assert world.send("button_press", DOORBELL, 0).status_code == 204
    assert world.ring.played == [(CHIME, "ring-appstore-event-1")]
    world.send("contact_sensor_faulted", SENSOR, 30)
    [alert] = alerts(world, "answered")
    assert alert["confidence"] == "strong" and alert["image"] is True
    assert world.ring.snapped == [(DOORBELL, T0)]


def test_forged_webhook_is_refused_and_does_nothing(world):
    raw = payload("button_press", DOORBELL, T0)
    r = world.send("button_press", DOORBELL, raw=raw, header="sha256=" + "0" * 64)
    assert r.status_code == 401
    assert world.ring.played == []
    assert any("bad signature" in text for _, text in world.store.journal(None))


def test_replayed_webhook_acts_once(world):
    raw = payload("button_press", DOORBELL, T0, request_id="same")
    assert world.send("button_press", DOORBELL, raw=raw).status_code == 204
    # The visit ends; four minutes later, still inside the freshness window,
    # the same delivery comes back. Accepted, it would ring the chime again.
    world.clock.now = T0 + seconds(180)
    world.app.state.tick()
    world.clock.now = T0 + seconds(240)
    r = world.client.post("/webhooks/ring", content=raw,
                          headers={"x-signature": webhooks.sign(KEY, raw)})
    assert r.status_code == 204
    assert len(world.ring.played) == 1


def test_stale_webhook_is_refused(world):
    raw = payload("button_press", DOORBELL, T0 - timedelta(hours=1))
    assert world.send("button_press", DOORBELL, raw=raw).status_code == 400
    assert world.ring.played == []


def test_unknown_device_is_ignored_quietly(world):
    assert world.send("button_press", "someone-elses-doorbell").status_code == 204
    assert world.ring.played == []


def test_household_api_needs_the_admin_token(world):
    for headers in ({}, {"x-admin-token": "wrong"}):
        assert world.client.get("/api/households/home-1", headers=headers).status_code == 401
        assert world.client.post("/api/households/home-1/off",
                                 headers=headers).status_code == 401


def test_pause_is_told_to_the_family(world):
    r = world.client.post("/api/households/home-1/pause", headers=ADMIN, json={"hours": 4})
    assert r.json()["told"] == [["sarah@example.com"]]
    assert world.state()["paused"] is True
    world.send("button_press", DOORBELL, 60)
    assert world.ring.played == []


def test_a_pause_longer_than_a_day_is_refused(world):
    r = world.client.post("/api/households/home-1/pause", headers=ADMIN, json={"hours": 72})
    assert r.status_code == 422


def test_a_collection_disguised_as_a_delivery_is_refused_and_journaled(world):
    r = world.client.post("/api/households/home-1/deliveries", headers=ADMIN, json={
        "text": "UPS 1Z999AA10123456784: our courier will collect the cash at 3pm",
        "carrier": "UPS", "tracking": "1Z999AA10123456784",
        "start": (T0 - timedelta(hours=1)).isoformat(),
        "end": (T0 + timedelta(hours=2)).isoformat()})
    assert r.status_code == 422
    world.send("button_press", DOORBELL, 10)
    assert world.ring.played, "the courier is still treated as unexpected"


def test_a_genuine_delivery_for_today_is_accepted_and_told(world):
    text = "UPS: package 1Z999AA10123456784 arrives today 2-6 PM"
    proposal = world.client.post("/api/deliveries/read", headers=ADMIN, json={"text": text}).json()
    r = world.client.post("/api/households/home-1/deliveries", headers=ADMIN, json={
        "text": text, "carrier": proposal["carrier"], "tracking": proposal["tracking"],
        "start": (T0 - timedelta(hours=1)).isoformat(),
        "end": (T0 + timedelta(hours=3)).isoformat()})
    assert r.status_code == 200 and r.json()["told"] == [["sarah@example.com"]]
    world.send("button_press", DOORBELL, 10)
    assert world.ring.played == []


def test_visit_closes_on_tick(world):
    world.send("button_press", DOORBELL, 0)
    world.clock.now = T0 + seconds(300)
    world.app.state.tick()
    assert world.store.load("home-1").visit is None


def test_nothing_readable_at_rest(world):
    world.send("button_press", DOORBELL, 0)
    world.send("contact_sensor_faulted", SENSOR, 30)
    world.client.post("/api/households/home-1/visits", headers=ADMIN, json={
        "label": "carer", "weekdays": [1, 3], "start": "10:00", "end": "12:00"})
    raw = world.path.read_bytes()
    for secret in (b"sarah@example.com", b"Sarah", b"carer", b"10:00", b"opened"):
        assert secret not in raw


def test_delete_removes_everything(world):
    world.send("button_press", DOORBELL, 0)
    world.send("contact_sensor_faulted", SENSOR, 30)
    assert world.client.delete("/api/households/home-1", headers=ADMIN).status_code == 204
    db = sqlite3.connect(world.path)
    for table in ("households", "devices", "outbox", "journal"):
        where = "id" if table == "households" else "household"
        assert db.execute(f"select count(*) from {table} where {where}='home-1'").fetchone()[0] == 0
    assert world.send("button_press", DOORBELL, 60).status_code == 204
    assert len(world.ring.played) == 1
