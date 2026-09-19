"""The service: Ring webhooks in, reminders and alerts out.

    uvicorn callfirst.app:app --port 8000

Environment (see .env.example): CALLFIRST_KEY encrypts the database,
RING_WEBHOOK_KEY verifies Ring's signatures, CALLFIRST_ADMIN_TOKEN guards the
household API, RING_API_BASE / RING_TOKEN reach the Partner API (or the
emulator).
"""
from __future__ import annotations

import asyncio
import base64
import hmac
import os
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from . import deliveries, rules, webhooks
from .household import ExpectedVisit, Household, Trusted, iso
from .ring import Ring
from .store import Store

TICK_SECONDS = 15


class TrustedIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)


class HouseholdIn(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]{3,40}$")
    doorbell: str
    chime: str | None = None
    sensor: str | None = None
    timezone: str = "America/New_York"
    trusted: list[TrustedIn] = Field(min_length=1, max_length=3)


class VisitIn(BaseModel):
    label: str = Field(min_length=1, max_length=60)
    weekdays: list[int] = Field(min_length=1, max_length=7)
    start: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class NoticeIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class DeliveryIn(NoticeIn):
    carrier: str | None = None
    tracking: str | None = None
    start: datetime
    end: datetime
    signature_required: bool = False


class PauseIn(BaseModel):
    hours: float = Field(gt=0, le=24)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def create_app(store: Store, ring: Ring | None, webhook_key: str, admin_token: str,
               clock: Callable[[], datetime] = _now, background: bool = True) -> FastAPI:
    lock = threading.Lock()    # one household decision at a time: load, decide, save

    def act(h: Household, actions: list, at: str) -> None:
        for action in actions:
            if isinstance(action, rules.Chime):
                played = bool(ring and h.chime and ring.play(h.chime, action.slot))
                store.note(h.id, at, f"chime {action.slot}: {'played' if played else 'FAILED'}")
            elif isinstance(action, rules.Alert):
                body = asdict(action)
                if ring and action.snapshot_at and action.reason != "change":
                    image = ring.snapshot(h.doorbell, datetime.fromisoformat(action.snapshot_at))
                    body["image"] = base64.b64encode(image).decode() if image else None
                store.send(h.id, action.at, "alert", body)
            elif isinstance(action, rules.Note):
                store.note(h.id, at, action.text)

    def tick() -> None:
        now = clock()
        with lock:
            for household_id in store.all_ids():
                h = store.load(household_id)
                if h and h.visit and rules.tick(h, now):
                    store.save(h)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async def loop():
            while True:
                await asyncio.sleep(TICK_SECONDS)
                await asyncio.to_thread(tick)
        task = asyncio.create_task(loop()) if background else None
        yield
        if task:
            task.cancel()

    app = FastAPI(title="Call First", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.tick = tick

    # ------------------------------------------------------------------ webhooks

    @app.post("/webhooks/ring", status_code=204)
    async def ring_webhook(request: Request) -> Response:
        raw = await request.body()
        now = clock()
        try:
            event = webhooks.read(webhook_key, raw, request.headers.get("x-signature"), now)
        except webhooks.Rejected as rejected:
            store.note(None, iso(now), f"webhook rejected: {rejected.reason}")
            raise HTTPException(401 if rejected.reason == "bad signature" else 400,
                                rejected.reason) from None
        # From here on, always 204: Ring retries anything else, and a genuine
        # event we choose to ignore is not an error.
        if event is None or not store.first_time(event.request_id, now):
            return Response(status_code=204)
        household_id = store.owner_of(event.device_id)
        if household_id is None:
            return Response(status_code=204)
        with lock:
            h = store.load(household_id)
            actions = rules.on_event(h, event, now)
            store.save(h)
        await asyncio.to_thread(act, h, actions, iso(now))
        return Response(status_code=204)

    # ------------------------------------------------------------------ households

    def admin(x_admin_token: str = Header(default="")) -> None:
        if not admin_token or not hmac.compare_digest(x_admin_token.encode(),
                                                      admin_token.encode()):
            raise HTTPException(401, "admin token required")

    def household(household_id: str) -> Household:
        h = store.load(household_id)
        if h is None:
            raise HTTPException(404, "no such household")
        return h

    def change(household_id: str, apply: Callable[[Household, datetime], list]) -> dict:
        now = clock()
        with lock:
            h = household(household_id)
            actions = apply(h, now)
            store.save(h)
        act(h, actions, iso(now))
        return {"told": [a.recipients for a in actions if isinstance(a, rules.Alert)]}

    guarded = [Depends(admin)]

    @app.post("/api/households", dependencies=guarded, status_code=201)
    def create(body: HouseholdIn) -> dict:
        if store.load(body.id):
            raise HTTPException(409, "household exists")
        h = Household(id=body.id, doorbell=body.doorbell, chime=body.chime, sensor=body.sensor,
                      timezone=body.timezone,
                      trusted=[Trusted(t.name, t.email) for t in body.trusted])
        with lock:
            store.save(h)
        return {"id": h.id, "mode": h.mode, "enabled": h.enabled}

    @app.post("/api/households/{household_id}/on", dependencies=guarded)
    def switch_on(household_id: str) -> dict:
        return change(household_id, rules.switch_on)

    @app.post("/api/households/{household_id}/off", dependencies=guarded)
    def switch_off(household_id: str) -> dict:
        return change(household_id, rules.switch_off)

    @app.post("/api/households/{household_id}/pause", dependencies=guarded)
    def pause(household_id: str, body: PauseIn) -> dict:
        return change(household_id,
                      lambda h, now: rules.pause(h, now + timedelta(hours=body.hours), now))

    @app.post("/api/households/{household_id}/resume", dependencies=guarded)
    def resume(household_id: str) -> dict:
        return change(household_id, rules.resume)

    @app.post("/api/households/{household_id}/visits", dependencies=guarded)
    def add_visit(household_id: str, body: VisitIn) -> dict:
        if body.end <= body.start or any(not 0 <= d <= 6 for d in body.weekdays):
            raise HTTPException(422, "invalid window")
        visit = ExpectedVisit(body.label, sorted(set(body.weekdays)), body.start, body.end)
        return change(household_id, lambda h, now: rules.add_visit(h, visit, now))

    @app.post("/api/deliveries/read", dependencies=guarded)
    def read_notice(body: NoticeIn) -> dict:
        return asdict(deliveries.read(body.text))

    @app.post("/api/households/{household_id}/deliveries", dependencies=guarded)
    def add_delivery(household_id: str, body: DeliveryIn) -> dict:
        proposal = deliveries.Proposal(body.carrier, body.tracking, body.start, body.end,
                                       body.signature_required)
        verdict = deliveries.validate(body.text, proposal, clock())
        if not verdict.accepted:
            store.note(household_id, iso(clock()), "delivery refused: " + "; ".join(verdict.refusals))
            raise HTTPException(422, {"refusals": list(verdict.refusals)})
        return change(household_id,
                      lambda h, now: rules.add_delivery(h, verdict.delivery, now))

    @app.delete("/api/households/{household_id}/trusted/{email}", dependencies=guarded)
    def remove_trusted(household_id: str, email: str) -> dict:
        return change(household_id, lambda h, now: rules.remove_trusted(h, email, now))

    @app.get("/api/households/{household_id}", dependencies=guarded)
    def show(household_id: str) -> dict:
        h = household(household_id)
        now = clock()
        return {"id": h.id, "mode": h.mode, "enabled": h.enabled,
                "paused": h.paused(now), "heightened": h.heightened(now),
                "doorbell_online": h.doorbell_online,
                "sent": [{k: v for k, v in s.items() if k != "image"} | {"image": bool(s.get("image"))}
                         for s in store.sent(h.id)],
                "journal": store.journal(h.id)}

    @app.delete("/api/households/{household_id}", dependencies=guarded, status_code=204)
    def delete(household_id: str) -> Response:
        with lock:
            store.delete(household_id)
        return Response(status_code=204)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    return app


def _from_env() -> FastAPI:
    data = Path(os.environ.get("CALLFIRST_DATA", "data"))
    data.mkdir(exist_ok=True)
    store = Store(data / "callfirst.db", os.environ["CALLFIRST_KEY"])
    ring = Ring(os.environ.get("RING_API_BASE", "http://127.0.0.1:8787"),
                os.environ.get("RING_TOKEN", "sandbox"))
    return create_app(store, ring, os.environ["RING_WEBHOOK_KEY"],
                      os.environ.get("CALLFIRST_ADMIN_TOKEN", ""))


def __getattr__(name: str):
    # `uvicorn callfirst.app:app` builds the app from the environment on first
    # access, so importing this module in tests needs no secrets.
    if name == "app":
        return _from_env()
    raise AttributeError(name)
