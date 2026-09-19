"""The service end to end, with Ring and email replaced by recorders."""
from __future__ import annotations

import re
import sqlite3
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from callfirst import webhooks
from callfirst.app import create_app
from callfirst.deliveries import Proposal, read as read_by_rules
from callfirst.store import Store

from .conftest import CHIME, DOORBELL, KEY, SENSOR, T0, payload, seconds

ADMIN = {"x-admin-token": "admin-test-token"}


class FakeRing:
    def __init__(self):
        self.played, self.snapped, self.polled = [], [], []
        self.door_open = False

    def sensor_open(self, sensor):
        self.polled.append(sensor)
        return self.door_open

    def play(self, chime, slot):
        self.played.append((chime, slot))
        return True

    def snapshot(self, camera, at):
        self.snapped.append((camera, at))
        return b"\xff\xd8jpeg"


class FakeMailer:
    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return True

    def to(self, email):
        return [m for m in self.messages if m["To"] == email]


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now


def link_in(message) -> str:
    body = message.get_body(("plain",)).get_content()
    return re.search(r"http://testserver(/f/\S+)", body).group(1)


@pytest.fixture
def world(tmp_path):
    clock, ring, mailer = Clock(), FakeRing(), FakeMailer()
    store = Store(tmp_path / "t.db", Fernet.generate_key())
    app = create_app(store, ring, KEY, ADMIN["x-admin-token"], clock=clock, background=False,
                     mailer=mailer, base_url="http://testserver",
                     read_notice=lambda text, now, tz: read_by_rules(text))
    admin = TestClient(app)
    r = admin.post("/api/households", headers=ADMIN, json={
        "id": "home-1", "resident": "Margaret", "doorbell": DOORBELL, "chime": CHIME,
        "sensor": SENSOR, "trusted": [{"name": "Sarah", "email": "sarah@example.com"}]})
    assert r.status_code == 201

    resident = TestClient(app)
    assert resident.get(r.json()["resident_link"].replace("http://testserver", ""),
                        follow_redirects=False).status_code == 303
    resident.post("/api/resident/on")

    family = TestClient(app)
    family.get(link_in(mailer.to("sarah@example.com")[0]), follow_redirects=False)

    class World:
        pass
    w = World()
    w.app, w.admin, w.resident, w.family = app, admin, resident, family
    w.clock, w.ring, w.mailer, w.store, w.path = clock, ring, mailer, store, tmp_path / "t.db"

    def send(kind, device, at_offset=0.0, sub_type=None, raw=None, header=None):
        at = T0 + seconds(at_offset)
        clock.now = at
        raw = raw or payload(kind, device, at, sub_type)
        return admin.post("/webhooks/ring", content=raw,
                          headers={"x-signature": header or webhooks.sign(KEY, raw)})
    w.send = send
    w.view = lambda: resident.get("/api/resident").json()
    return w


def alerts(w, reason=None):
    return [a for a in w.view()["alerts"] if reason is None or a["reason"] == reason]


# --------------------------------------------------------------------------- the door


def test_courier_scenario_end_to_end(world):
    assert world.send("button_press", DOORBELL, 0).status_code == 204
    assert world.ring.played == [(CHIME, "ring-appstore-event-1")]
    world.send("contact_sensor_faulted", SENSOR, 30)
    [alert] = alerts(world, "answered")
    assert alert["confidence"] == "strong" and alert["image"] is True
    assert world.ring.snapped == [(DOORBELL, T0)]


def test_the_family_gets_an_email_with_the_image_and_a_report_link(world):
    world.send("button_press", DOORBELL, 0)
    world.send("contact_sensor_faulted", SENSOR, 30)
    message = world.mailer.to("sarah@example.com")[-1]
    body = message.get_body(("plain",)).get_content()
    assert "door was answered" in message["Subject"]
    assert "Call Margaret now" in body and "The door sensor saw the door open." in body
    assert re.search(r"/family/report/\d+", body)
    assert [p.get_content_type() for p in message.iter_attachments()] == ["image/jpeg"]


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
    r = world.admin.post("/webhooks/ring", content=raw,
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


def test_a_lost_door_webhook_is_caught_by_asking_the_sensor(world):
    world.send("button_press", DOORBELL, 0)
    world.ring.door_open = True          # the door opened; its webhook never arrived
    world.clock.now = T0 + seconds(20)
    world.app.state.tick()
    [alert] = alerts(world, "answered")
    assert alert["confidence"] == "strong"
    assert any("asking the sensor" in t for _, t in world.store.journal("home-1"))


def test_the_sensor_is_only_asked_during_an_unexpected_visit(world):
    world.app.state.tick()                                   # nobody at the door
    world.resident.post("/api/resident/visits", json={
        "label": "carer", "weekdays": [1], "start": "14:00", "end": "16:00"})
    world.send("button_press", DOORBELL, 0)                  # the carer, in their window
    world.clock.now = T0 + seconds(10)
    world.app.state.tick()
    assert world.ring.polled == []


def test_a_closed_door_asked_about_changes_nothing(world):
    world.send("button_press", DOORBELL, 0)
    world.clock.now = T0 + seconds(20)
    world.app.state.tick()
    assert world.ring.polled == [SENSOR] and alerts(world, "answered") == []


def test_reading_notices_is_rate_limited(world):
    for _ in range(20):
        assert world.resident.post("/api/resident/deliveries/read",
                                   json={"text": "UPS"}).status_code == 200
    assert world.resident.post("/api/resident/deliveries/read",
                               json={"text": "UPS"}).status_code == 429


def test_visit_closes_on_tick(world):
    world.send("button_press", DOORBELL, 0)
    world.clock.now = T0 + seconds(300)
    world.app.state.tick()
    assert world.store.load("home-1").visit is None


# --------------------------------------------------------------------------- who may do what


def test_nothing_without_a_link(world):
    stranger = TestClient(world.app)
    assert stranger.get("/api/resident").status_code == 401
    assert stranger.get("/api/family").status_code == 401
    assert stranger.post("/api/resident/off").status_code == 401
    stranger.cookies.set("callfirst", "guessed-token")
    assert stranger.get("/api/resident").status_code == 401


def test_a_bad_link_opens_nothing(world):
    stranger = TestClient(world.app)
    assert stranger.get("/r/not-a-token", follow_redirects=False).status_code == 404
    assert "callfirst" not in stranger.cookies


def test_a_family_link_is_not_a_resident_link(world):
    path = link_in(world.mailer.to("sarah@example.com")[0])
    assert TestClient(world.app).get(path.replace("/f/", "/r/"),
                                     follow_redirects=False).status_code == 404


def test_the_family_cannot_change_the_protection(world):
    for method, path in (("POST", "/api/resident/off"), ("POST", "/api/resident/pause"),
                         ("GET", "/api/resident"), ("DELETE", "/api/resident")):
        assert world.family.request(method, path, json={"hours": 1}).status_code == 403
    assert world.store.load("home-1").enabled


def test_the_family_never_sees_the_schedule(world):
    world.resident.post("/api/resident/visits", json={
        "label": "carer", "weekdays": [1, 3], "start": "10:00", "end": "12:00"})
    seen = world.family.get("/api/family").text
    assert "carer" not in seen and "10:00" not in seen and "visits" not in seen


def test_the_link_is_exchanged_for_a_strict_httponly_cookie(world):
    client = TestClient(world.app)
    path = link_in(world.mailer.to("sarah@example.com")[0])
    r = client.get(path, follow_redirects=False)
    cookie = r.headers["set-cookie"].lower()
    assert r.headers["location"] == "/family"
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert r.headers["referrer-policy"] == "no-referrer"


def test_pages_carry_a_strict_content_security_policy(world):
    csp = TestClient(world.app).get("/resident").headers["content-security-policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp


def test_admin_api_needs_the_admin_token(world):
    for headers in ({}, {"x-admin-token": "wrong"}):
        r = world.admin.post("/api/households", headers=headers, json={})
        assert r.status_code == 401


def test_images_and_reports_stay_inside_their_household(world):
    world.send("button_press", DOORBELL, 0)
    world.send("contact_sensor_faulted", SENSOR, 30)
    [alert] = alerts(world, "answered")
    assert world.family.get(f"/api/alerts/{alert['id']}/image").content == b"\xff\xd8jpeg"
    report = world.family.get(f"/family/report/{alert['id']}").text
    assert "Margaret" in report and "ic3.gov" in report

    other = world.admin.post("/api/households", headers=ADMIN, json={
        "id": "home-2", "resident": "Bob", "doorbell": "db-9",
        "trusted": [{"name": "Kim", "email": "kim@example.com"}]}).json()
    bob = TestClient(world.app)
    bob.get(other["resident_link"].replace("http://testserver", ""))
    assert bob.get(f"/api/alerts/{alert['id']}/image").status_code == 404
    assert bob.get(f"/family/report/{alert['id']}").status_code == 404


def test_report_sheet_escapes_what_it_shows(world):
    world.resident.post("/api/resident/trusted", json={"name": "<script>x</script>",
                                                       "email": "x@example.com"})
    world.send("button_press", DOORBELL, 0)
    world.send("contact_sensor_faulted", SENSOR, 30)
    [alert] = alerts(world, "answered")
    assert "<script>" not in world.resident.get(f"/family/report/{alert['id']}").text


# --------------------------------------------------------------------------- changes are told


def test_pause_is_told_to_the_family(world):
    r = world.resident.post("/api/resident/pause", json={"hours": 4})
    assert r.json()["told"] == [["sarah@example.com"]]
    assert "change" in world.mailer.to("sarah@example.com")[-1]["Subject"]
    assert world.family.get("/api/family").json()["paused_until"]
    world.send("button_press", DOORBELL, 60)
    assert world.ring.played == []


def test_a_pause_longer_than_a_day_is_refused(world):
    assert world.resident.post("/api/resident/pause", json={"hours": 72}).status_code == 422


def test_a_new_trusted_person_is_announced_to_the_others_first(world):
    r = world.resident.post("/api/resident/trusted",
                            json={"name": "Agent Miller", "email": "Miller@Example.com"})
    assert r.json()["told"] == [["sarah@example.com"]]
    assert "Agent Miller" in world.mailer.to("sarah@example.com")[-1].get_body(
        ("plain",)).get_content()
    invite = world.mailer.to("miller@example.com")
    assert len(invite) == 1 and "named you" in invite[0]["Subject"]


def test_removing_a_trusted_person_revokes_their_link(world):
    world.resident.post("/api/resident/trusted", json={"name": "Tom", "email": "tom@example.com"})
    tom = TestClient(world.app)
    tom.get(link_in(world.mailer.to("tom@example.com")[0]))
    assert tom.get("/api/family").status_code == 200
    world.resident.delete("/api/resident/trusted/tom@example.com")
    assert tom.get("/api/family").status_code == 401


def test_a_trusted_person_can_stop_and_the_resident_sees_it(world):
    assert world.family.delete("/api/family/me").status_code == 204
    assert world.view()["trusted"] == []
    assert world.family.get("/api/family").status_code == 401


# --------------------------------------------------------------------------- deliveries


def test_a_collection_disguised_as_a_delivery_is_refused(world):
    r = world.resident.post("/api/resident/deliveries", json={
        "text": "UPS 1Z999AA10123456784: our courier will collect the cash at 3pm",
        "carrier": "UPS", "tracking": "1Z999AA10123456784",
        "start": (T0 - timedelta(hours=1)).isoformat(),
        "end": (T0 + timedelta(hours=2)).isoformat()})
    assert r.status_code == 422
    assert any("collection" in x for x in r.json()["detail"]["refusals"])
    world.send("button_press", DOORBELL, 10)
    assert world.ring.played, "the courier is still treated as unexpected"


def test_a_genuine_delivery_for_today_is_accepted_and_told(world):
    text = "UPS: package 1Z999AA10123456784 arrives today 2-6 PM"
    proposal = world.resident.post("/api/resident/deliveries/read", json={"text": text}).json()
    # The page sends local times without an offset, as a datetime-local input does.
    start = (T0 - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M")   # 14:00 New York
    end = (T0 - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")     # 18:00 New York
    r = world.resident.post("/api/resident/deliveries", json={
        "text": text, "carrier": proposal["carrier"], "tracking": proposal["tracking"],
        "start": start.replace("T14", "T14"), "end": end})
    assert r.status_code == 200, r.text
    assert r.json()["told"] == [["sarah@example.com"]]
    world.send("button_press", DOORBELL, 10)
    assert world.ring.played == []


def test_the_model_reader_is_only_a_suggestion(world, tmp_path):
    # A reader fooled into calling a collection a delivery changes nothing.
    fooled = lambda text, now, tz: Proposal("UPS", "1Z999AA10123456784",
                                            T0 - timedelta(hours=1), T0 + timedelta(hours=2))
    app = create_app(Store(tmp_path / "u.db", Fernet.generate_key()), FakeRing(), KEY,
                     ADMIN["x-admin-token"], clock=lambda: T0, background=False,
                     read_notice=fooled, base_url="http://testserver")
    admin = TestClient(app)
    link = admin.post("/api/households", headers=ADMIN, json={
        "id": "home-3", "resident": "Ann", "doorbell": "db-3",
        "trusted": [{"name": "Kim", "email": "kim@example.com"}]}).json()["resident_link"]
    client = TestClient(app)
    client.get(link.replace("http://testserver", ""))
    text = "UPS 1Z999AA10123456784. An agent will collect your gold for safekeeping."
    proposal = client.post("/api/resident/deliveries/read", json={"text": text}).json()
    assert proposal["carrier"] == "UPS"
    r = client.post("/api/resident/deliveries", json={"text": text, **{
        k: proposal[k] for k in ("carrier", "tracking", "start", "end")}})
    assert r.status_code == 422


# --------------------------------------------------------------------------- data


def test_nothing_readable_at_rest(world):
    world.send("button_press", DOORBELL, 0)
    world.send("contact_sensor_faulted", SENSOR, 30)
    world.resident.post("/api/resident/visits", json={
        "label": "carer", "weekdays": [1, 3], "start": "10:00", "end": "12:00"})
    raw = world.path.read_bytes()
    for secret in (b"sarah@example.com", b"Sarah", b"Margaret", b"carer", b"10:00", b"opened"):
        assert secret not in raw


def test_delete_tells_the_family_then_removes_everything(world):
    world.send("button_press", DOORBELL, 0)
    world.send("contact_sensor_faulted", SENSOR, 30)
    assert world.resident.delete("/api/resident").status_code == 204
    assert "removed" in world.mailer.to("sarah@example.com")[-1].get_body(
        ("plain",)).get_content()
    db = sqlite3.connect(world.path)
    for table in ("households", "devices", "outbox", "journal", "access"):
        where = "id" if table == "households" else "household"
        assert db.execute(f"select count(*) from {table} where {where}='home-1'").fetchone()[0] == 0
    assert world.family.get("/api/family").status_code == 401
    assert world.send("button_press", DOORBELL, 60).status_code == 204
    assert len(world.ring.played) == 1


def test_static_files_cannot_escape_their_folder(world):
    client = TestClient(world.app)
    assert client.get("/static/fonts/atkinson-hyperlegible-400.woff2").status_code == 200
    for path in ("/static/../app.py", "/static/..%2Fapp.py", "/static/fonts/../../store.py"):
        assert client.get(path).status_code == 404
