"""The service: Ring webhooks in, reminders and alerts out, two small pages.

    uvicorn callfirst.app:app --port 8100

Who can do what:
- Ring, with the webhook signing key: report what happens at the door.
- The resident, through their own link: everything - switch on and off, pause,
  declare visits and deliveries, choose who is told, delete it all.
- A trusted person, through their own link: see the protection and the
  alerts, open a report sheet, stop receiving alerts. Nothing else. They
  never see the schedule.
- The operator, with the admin token: create a household. In production this
  is Ring's account linking; here it is how the demo starts.

A link is exchanged once for an HttpOnly, SameSite=Strict cookie and the page
redirects, so the token leaves the address bar and never reaches a Referer.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import html
import os
import secrets
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from cryptography.fernet import Fernet
from pydantic import BaseModel, Field

from . import deliveries, demo, notify, reader, rules, webhooks, when
from .household import ExpectedVisit, Household, Trusted, clock, iso
from .ring import Ring
from .store import Store

TICK_SECONDS = float(os.environ.get("CALLFIRST_TICK", "5"))
READS_PER_HOUR = 20          # pasted notices read by a model, per household (OWASP LLM10)
# One cookie per role, so a resident and a trusted person can use the same
# browser (and the demo can show both views side by side).
COOKIES = {"resident": "callfirst_resident", "family": "callfirst_family"}
STATIC = Path(__file__).parent / "static"
HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; "
                               "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
    # A year of HTTPS-only, so a first-party navigation cannot be downgraded
    # on a network the resident does not control. No `preload`: that is a
    # commitment made to browser vendors, not a header to set in passing.
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    # A product whose subject is a doorbell camera says, in a header a browser
    # enforces, that its own pages reach no camera, microphone or location.
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), "
                          "payment=(), usb=(), interest-cohort=()",
}


class TrustedIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)


class HouseholdIn(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]{3,40}$")
    resident: str = Field(min_length=1, max_length=60)
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


class DoorIn(BaseModel):
    action: str = Field(pattern="^(" + "|".join(demo.DOOR) + ")$")


class PauseIn(BaseModel):
    hours: float = Field(gt=0, le=24)


def _now() -> datetime:
    return datetime.now(tz=UTC)


def create_app(store: Store, ring: Ring | None, webhook_key: str, admin_token: str,
               clock: Callable[[], datetime] = _now, background: bool = True,
               mailer=None, base_url: str = "http://127.0.0.1:8100",
               sender: str = "Call First <alerts@callfirst.invalid>",
               read_notice: Callable = reader.read, secure_cookies: bool = False,
               emulator: "demo.Emulator | None" = None, self_url: str = "") -> FastAPI:
    lock = threading.Lock()    # one household decision at a time: load, decide, save
    reads: dict[str, list[datetime]] = {}
    starts: dict[str, list[datetime]] = {}

    def appelant(request: Request) -> str:
        """Who is calling, as far as a forwarded header can be trusted.

        ``X-Forwarded-For`` is written by the client and appended to by each
        proxy, so it reads *claimed, …, observed*. Taking the **first** entry —
        which is what this did — takes the half the caller wrote: a different
        value on every request and the per-address limit never binds. The
        **last** entry is the address our own proxy saw, and it is the only one
        in that header we did not get from the person we are limiting.

        No header at all, as in a direct connection or a test, falls back to
        the socket.
        """
        transmis = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",")]
        transmis = [p for p in transmis if p]
        if transmis:
            return transmis[-1]
        return request.client.host if request.client else "?"

    def compte(journal: dict[str, list[datetime]], qui: str, now: datetime,
               combien: int) -> bool:
        """One more call from ``qui``: is it still under ``combien`` an hour?

        Prunes **every** address, not only this one. Pruning just the caller
        left a list behind for each address ever seen, so a caller rotating the
        forwarded header grew the dictionary without bound — the limit it was
        bypassing and a slow leak, from the same request.
        """
        depuis = now - timedelta(hours=1)
        for adresse in list(journal):
            reste = [t for t in journal[adresse] if t > depuis]
            if reste:
                journal[adresse] = reste
            else:
                del journal[adresse]
        recent = journal.get(qui, [])
        if len(recent) >= combien:
            return False
        journal[qui] = recent + [now]
        return True

    # ------------------------------------------------------------------ doing what was decided

    def mail(h: Household, alert: dict, image: bytes | None, report_id: int | None) -> None:
        if not mailer:
            return
        # One message per person: trusted people do not see each other's addresses.
        for email in alert["recipients"]:
            message = notify.compose(alert | {"recipients": [email]}, h.resident, h.timezone,
                                     sender, base_url, image, report_id)
            if not mailer.send(message):
                store.note(h.id, alert["at"], "alert email FAILED")

    def act(h: Household, actions: list, at: str) -> None:
        for action in actions:
            if isinstance(action, rules.Chime):
                played = bool(ring and h.chime and ring.play(h.chime, action.slot))
                store.note(h.id, at, f"chime {action.slot}: {'played' if played else 'FAILED'}")
            elif isinstance(action, rules.Alert):
                body, image = asdict(action), None
                if ring and action.snapshot_at and action.reason != "change":
                    image = ring.snapshot(h.doorbell, datetime.fromisoformat(action.snapshot_at))
                    body["image"] = base64.b64encode(image).decode() if image else None
                sent_id = store.send(h.id, action.at, "alert", body)
                mail(h, body, image, None if action.reason == "change" else sent_id)
            elif isinstance(action, rules.Note):
                store.note(h.id, at, action.text)

    def invite(h: Household, person: Trusted, token: str) -> None:
        if mailer:
            mailer.send(notify.invitation(person, h.resident, sender, f"{base_url}/f/{token}"))

    def tick() -> None:
        """Every few seconds: ask the door sensor while an unexpected visitor is
        there (a lost webhook must not mean a silent door), then close visits
        nobody is at any more."""
        now = clock()
        if emulator:
            expire_demos(now)
        for household_id in store.all_ids():
            h = store.load(household_id)
            if not h or not h.visit:
                continue
            visit = h.visit
            opened = None
            if (ring and h.sensor and h.enabled and not h.paused(now)
                    and visit.expected is None and not visit.answered):
                opened = ring.sensor_open(h.sensor)
            with lock:
                h = store.load(household_id)
                if not h or not h.visit:
                    continue
                actions = []
                if opened:
                    seen = webhooks.Event(f"poll:{iso(now)}", now, "contact_sensor_faulted",
                                          h.sensor, now)
                    actions += rules.on_event(h, seen, now)
                    actions.append(rules.Note("door open seen by asking the sensor"))
                actions += rules.tick(h, now)
                store.save(h)
            act(h, actions, iso(now))

    def connect_emulator() -> None:
        """The emulator starts alongside; tell it where to send webhooks."""
        for _ in range(120):
            if emulator.healthy():
                emulator.register(f"{self_url}/webhooks/ring", webhook_key)
                return
            time.sleep(0.5)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if emulator:
            await asyncio.to_thread(connect_emulator)

        async def loop():
            while True:
                await asyncio.sleep(TICK_SECONDS)
                await asyncio.to_thread(tick)
        task = asyncio.create_task(loop()) if background else None
        yield
        if task:
            task.cancel()

    app = FastAPI(title="Call First", lifespan=lifespan, docs_url=None, redoc_url=None,
                  openapi_url=None)
    # Exposés pour être observables : une fuite qu'aucun test ne peut regarder
    # n'est pas une fuite qu'on corrige, c'est une fuite qu'on espère.
    app.state.starts, app.state.reads = starts, reads
    app.state.tick = tick

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        for name, value in HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    # ------------------------------------------------------------------ Ring

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

    # ------------------------------------------------------------------ sessions

    def sessions(request: Request) -> list[tuple[str, str, str | None]]:
        """Every valid session this browser holds, each checked against its role."""
        found = []
        for role, name in COOKIES.items():
            token = request.cookies.get(name)
            who = store.resolve(token) if token else None
            if who and who[1] == role:
                found.append(who)
        return found

    def as_role(request: Request, role: str) -> tuple[str, str, str | None]:
        held = sessions(request)
        for who in held:
            if who[1] == role:
                return who
        if held:
            raise HTTPException(403, "only the resident can change this" if role == "resident"
                                else "this page is for trusted people")
        raise HTTPException(401, "open the link you were sent")

    def any_session(request: Request) -> list[tuple[str, str, str | None]]:
        held = sessions(request)
        if not held:
            raise HTTPException(401, "open the link you were sent")
        return held

    def resident(request: Request) -> str:
        return as_role(request, "resident")[0]

    def family(request: Request) -> tuple[str, str]:
        household_id, _, email = as_role(request, "family")
        return household_id, email

    def enter(token: str, role: str, page: str) -> Response:
        found = store.resolve(token)
        if not found or found[1] != role:
            return HTMLResponse("<p>This link is not valid any more.</p>", status_code=404)
        response = RedirectResponse(page, status_code=303)
        response.set_cookie(COOKIES[role], token, httponly=True, samesite="strict",
                            secure=secure_cookies, max_age=180 * 86400)
        return response

    @app.get("/r/{token}")
    def resident_link(token: str) -> Response:
        return enter(token, "resident", "/resident")

    @app.get("/f/{token}")
    def family_link(token: str) -> Response:
        return enter(token, "family", "/family")

    # ------------------------------------------------------------------ helpers

    def load(household_id: str) -> Household:
        h = store.load(household_id)
        if h is None:
            raise HTTPException(404, "no such household")
        return h

    def change(household_id: str, apply: Callable[[Household, datetime], list]) -> dict:
        now = clock()
        with lock:
            h = load(household_id)
            actions = apply(h, now)
            store.save(h)
        act(h, actions, iso(now))
        return {"told": [list(a.recipients) for a in actions if isinstance(a, rules.Alert)]}

    def local(h: Household, value: str | None) -> str | None:
        return h.local(datetime.fromisoformat(value)).isoformat() if value else None

    def alerts_of(h: Household) -> list[dict]:
        return [{"id": s["id"], "reason": s["reason"], "at": local(h, s["at"]),
                 "detail": s["detail"], "confidence": s.get("confidence"),
                 "image": bool(s.get("image"))}
                for s in reversed(store.sent(h.id)) if s["kind"] == "alert"][:30]

    def status(h: Household, now: datetime) -> dict:
        return {"resident": h.resident, "timezone": h.timezone, "mode": h.mode,
                "enabled": h.enabled,
                "paused_until": local(h, h.paused_until) if h.paused(now) else None,
                "heightened_until": local(h, h.heightened_until) if h.heightened(now) else None,
                "doorbell_online": h.doorbell_online, "alerts": alerts_of(h)}

    # ------------------------------------------------------------------ the resident

    @app.get("/api/resident")
    def resident_view(household_id: str = Depends(resident)) -> dict:
        h, now = load(household_id), clock()
        reminders = [at for at, text in store.journal(h.id)
                     if text.startswith("chime") and text.endswith("played")]
        return status(h, now) | {
            "demo": bool(emulator) and h.id.startswith("demo-"),
            "reminders": [local(h, at) for at in reminders[-5:]][::-1],
            "trusted": [asdict(t) for t in h.trusted],
            # Not a one-off notice that scrolls away: a standing fact on her
            # own page. A protection with nobody on the other end still plays
            # the reminder and still raises alerts; the only thing it cannot
            # do is the one thing it is for.
            "nobody_listening": not h.trusted,
            "visits": [asdict(v) | {"index": i} for i, v in enumerate(h.visits)],
            "deliveries": [asdict(d) | {"index": i, "start": local(h, d.start),
                                        "end": local(h, d.end)}
                           for i, d in enumerate(h.deliveries)
                           if datetime.fromisoformat(d.end) > now],
        }

    @app.post("/api/resident/on")
    def on(household_id: str = Depends(resident)) -> dict:
        return change(household_id, rules.switch_on)

    @app.post("/api/resident/off")
    def off(household_id: str = Depends(resident)) -> dict:
        return change(household_id, rules.switch_off)

    @app.post("/api/resident/pause")
    def pause(body: PauseIn, household_id: str = Depends(resident)) -> dict:
        return change(household_id,
                      lambda h, now: rules.pause(h, now + timedelta(hours=body.hours), now))

    @app.post("/api/resident/resume")
    def resume(household_id: str = Depends(resident)) -> dict:
        return change(household_id, rules.resume)

    @app.post("/api/resident/visits")
    def add_visit(body: VisitIn, household_id: str = Depends(resident)) -> dict:
        if body.end <= body.start or any(not 0 <= d <= 6 for d in body.weekdays):
            raise HTTPException(422, "invalid window")
        visit = ExpectedVisit(body.label, sorted(set(body.weekdays)), body.start, body.end)
        return change(household_id, lambda h, now: rules.add_visit(h, visit, now))

    @app.delete("/api/resident/visits/{index}")
    def remove_visit(index: int, household_id: str = Depends(resident)) -> dict:
        # Removing an expected visit only makes the door stricter: no alert.
        def apply(h, now):
            if not 0 <= index < len(h.visits):
                raise HTTPException(404, "no such visit")
            return [rules.Note(f"visit removed: {h.visits.pop(index).label}")]
        return change(household_id, apply)

    @app.post("/api/resident/deliveries/read")
    def read_delivery(body: NoticeIn, household_id: str = Depends(resident)) -> dict:
        h, now = load(household_id), clock()
        if not compte(reads, household_id, now, READS_PER_HOUR):
            raise HTTPException(429, "too many messages read this hour; fill in the form by hand")
        proposal = read_notice(body.text, now, h.timezone)
        fields = asdict(proposal)
        for key in ("start", "end"):
            fields[key] = h.local(fields[key]).isoformat() if fields[key] else None

        # What the message could mean, when it does not settle it. These do not
        # travel through `Proposal`: that is what `validate` is handed, and the
        # boundary that decides is not widened for a convenience. The page
        # offers them; whichever the resident picks comes back as an ordinary
        # window and is validated like any other.
        quand = when.lis(body.text, h.local(now).date())
        fields["readings"] = [
            {"label": l.quoi,
             "start": l.debut.replace(tzinfo=h.local(now).tzinfo).isoformat(),
             "end": l.fin.replace(tzinfo=h.local(now).tzinfo).isoformat()}
            for l in quand.lectures
        ] if len(quand.lectures) > 1 else []
        fields["question"] = quand.demande
        return fields

    @app.post("/api/resident/deliveries")
    def add_delivery(body: DeliveryIn, household_id: str = Depends(resident)) -> dict:
        h = load(household_id)
        zone = h.local(clock()).tzinfo
        start, end = (d if d.tzinfo else d.replace(tzinfo=zone) for d in (body.start, body.end))
        proposal = deliveries.Proposal(body.carrier, body.tracking, start, end,
                                       body.signature_required)
        verdict = deliveries.validate(body.text, proposal, clock())
        if not verdict.accepted:
            store.note(household_id, iso(clock()),
                       "delivery refused: " + "; ".join(verdict.refusals))
            raise HTTPException(422, {"refusals": list(verdict.refusals)})
        return change(household_id, lambda h, now: rules.add_delivery(h, verdict.delivery, now))

    @app.post("/api/resident/trusted")
    def add_trusted(body: TrustedIn, household_id: str = Depends(resident)) -> dict:
        person = Trusted(body.name, body.email.lower())

        def apply(h, now):
            if any(t.email == person.email for t in h.trusted) or len(h.trusted) >= 3:
                raise HTTPException(409, "already trusted, or three people already")
            return rules.add_trusted(h, person, now)
        told = change(household_id, apply)
        invite(load(household_id), person, store.grant(household_id, "family", person.email))
        return told

    @app.delete("/api/resident/trusted/{email}")
    def remove_trusted(email: str, household_id: str = Depends(resident)) -> dict:
        told = change(household_id, lambda h, now: rules.remove_trusted(h, email.lower(), now))
        store.revoke(household_id, email.lower())
        return told

    @app.delete("/api/resident")
    def delete_everything(household_id: str = Depends(resident)) -> Response:
        change(household_id, rules.farewell)
        with lock:
            store.delete(household_id)
        response = Response(status_code=204)
        response.delete_cookie(COOKIES["resident"])
        return response

    # ------------------------------------------------------------------ trusted people

    @app.get("/api/family")
    def family_view(who: tuple[str, str] = Depends(family)) -> dict:
        h = load(who[0])
        return status(h, clock()) | {"you": who[1]}

    @app.delete("/api/family/me")
    def stop_receiving(who: tuple[str, str] = Depends(family)) -> Response:
        household_id, email = who
        change(household_id, lambda h, now: rules.remove_trusted(h, email, now))
        store.revoke(household_id, email)
        response = Response(status_code=204)
        response.delete_cookie(COOKIES["family"])
        return response

    # ------------------------------------------------------------------ evidence

    def sent_or_404(held: list, sent_id: int) -> tuple[str, dict]:
        for household_id, _, _ in held:
            found = store.one_sent(household_id, sent_id)
            if found and found["kind"] == "alert":
                return household_id, found
        raise HTTPException(404, "not found")

    @app.get("/api/alerts/{sent_id}/image")
    def alert_image(sent_id: int, held=Depends(any_session)) -> Response:
        _, found = sent_or_404(held, sent_id)
        if not found.get("image"):
            raise HTTPException(404, "no image")
        image = base64.b64decode(found["image"])
        return Response(image, media_type=f"image/{notify.image_type(image)}")

    @app.get("/family/report/{sent_id}", response_class=HTMLResponse)
    def report(sent_id: int, held=Depends(any_session)) -> str:
        household_id, found = sent_or_404(held, sent_id)
        return report_sheet(load(household_id), found)

    # ------------------------------------------------------------------ the hosted demo

    def demo_started(household_id: str) -> datetime | None:
        try:
            return datetime.fromtimestamp(int(household_id.split("-")[1]) * 60, tz=UTC)
        except (IndexError, ValueError):
            return None

    def expire_demos(now: datetime) -> None:
        for household_id in store.all_ids():
            started = demo_started(household_id) if household_id.startswith("demo-") else None
            if started and now - started > demo.DEMO_LIFETIME:
                with lock:
                    store.delete(household_id)

    @app.get("/try")
    def try_page() -> Response:
        if not emulator:
            return RedirectResponse("/", status_code=303)
        return FileResponse(STATIC / "try.html")

    if emulator:

        @app.post("/api/demo/start")
        def start_demo(request: Request) -> Response:
            now = clock()
            if not compte(starts, appelant(request), now, demo.STARTS_PER_HOUR):
                raise HTTPException(429, "Too many demos from here this hour.")
            expire_demos(now)
            if sum(1 for i in store.all_ids() if i.startswith("demo-")) >= demo.MAX_DEMOS:
                raise HTTPException(503, "The demo is full right now. Try again in a while.")

            n = secrets.token_hex(4)
            h = Household(
                id=f"demo-{int(now.timestamp() // 60)}-{n}", resident="Margaret",
                doorbell=emulator.add("doorbell", f"Front Door {n}"),
                chime=emulator.add("chime", f"Kitchen Chime {n}"),
                sensor=emulator.add("contact_sensor", f"Front Door Sensor {n}"),
                trusted=[Trusted("Sarah", f"sarah+{n}@example.invalid")])
            with lock:
                store.save(h)
            change(h.id, rules.switch_on)
            response = Response(status_code=204)
            for role, email in (("resident", None), ("family", h.trusted[0].email)):
                response.set_cookie(COOKIES[role], store.grant(h.id, role, email),
                                    httponly=True, samesite="strict", secure=secure_cookies,
                                    max_age=int(demo.DEMO_LIFETIME.total_seconds()))
            return response

        @app.post("/api/demo/door")
        def play_door(body: DoorIn, household_id: str = Depends(resident)) -> dict:
            if not household_id.startswith("demo-"):
                raise HTTPException(403, "only demo households have a playable door")
            h = load(household_id)
            before = len(store.journal(h.id))
            devices = {"doorbell": h.doorbell, "sensor": h.sensor}
            for kind, device, sub_type in demo.DOOR[body.action]:
                emulator.inject(kind, devices[device], sub_type)
            # The webhook comes back through the emulator; wait briefly for the
            # decision so the page can say (and speak) what the chime did.
            chime = None
            for _ in range(30 if body.action == "ring" else 0):
                new = [t for _, t in store.journal(h.id)[before:] if t.startswith("chime")]
                if new:
                    chime = new[0].split()[1].rstrip(":")
                    break
                time.sleep(0.1)
            return {"chime": chime}

    # ------------------------------------------------------------------ operator

    def admin(x_admin_token: str = Header(default="")) -> None:
        if not admin_token or not hmac.compare_digest(x_admin_token.encode(),
                                                      admin_token.encode()):
            raise HTTPException(401, "admin token required")

    @app.post("/api/households", dependencies=[Depends(admin)], status_code=201)
    def create(body: HouseholdIn) -> dict:
        """Returns the resident's link. Protection starts off: the resident
        switches it on, from that link."""
        if store.load(body.id):
            raise HTTPException(409, "household exists")
        h = Household(id=body.id, resident=body.resident, doorbell=body.doorbell,
                      chime=body.chime, sensor=body.sensor, timezone=body.timezone,
                      trusted=[Trusted(t.name, t.email.lower()) for t in body.trusted])
        with lock:
            store.save(h)
        for person in h.trusted:
            invite(h, person, store.grant(h.id, "family", person.email))
        return {"id": h.id, "mode": h.mode, "enabled": h.enabled,
                "resident_link": f"{base_url}/r/{store.grant(h.id, 'resident')}"}

    # ------------------------------------------------------------------ pages

    @app.get("/")
    def home() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    for page in ("resident", "family", "privacy"):
        app.add_api_route(f"/{page}", (lambda p=page: FileResponse(STATIC / f"{p}.html")),
                          methods=["GET"])

    @app.get("/static/{name:path}")
    def static(name: str) -> FileResponse:
        path = (STATIC / name).resolve()
        if not path.is_relative_to(STATIC.resolve()) or not path.is_file():
            raise HTTPException(404, "not found")
        headers = {"Cache-Control": "public, max-age=86400"} if name.startswith("fonts/") else None
        return FileResponse(path, headers=headers)

    @app.get("/favicon.ico")
    def favicon() -> RedirectResponse:
        return RedirectResponse("/static/favicon.svg", status_code=301)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    return app


def report_sheet(h: Household, alert: dict) -> str:
    """A printable page with what the door recorded, for IC3 and the FTC. The
    family files it; Call First never sends it anywhere."""
    e = html.escape
    at = h.local(datetime.fromisoformat(alert["at"]))
    started = h.local(datetime.fromisoformat(alert["snapshot_at"])) \
        if alert.get("snapshot_at") else None
    image = (f'<img src="/api/alerts/{alert["id"]}/image" alt="Still image from the doorbell">'
             if alert.get("image") else "<p>No image was available.</p>")
    confidence = notify.CONFIDENCE.get(alert.get("confidence") or "", "Not applicable.")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Report sheet</title><link rel="icon" href="/static/favicon.svg">
<link rel="stylesheet" href="/static/style.css"></head>
<body class="sheet"><main>
<h1>Doorstep incident report</h1>
<p class="lede">Prepared by Call First from what the front door recorded. Nothing here has
been sent to anyone.</p>
<table>
<tr><th>Resident</th><td>{e(h.resident)}</td></tr>
<tr><th>Date</th><td>{at:%A %d %B %Y}</td></tr>
<tr><th>Visitor first seen</th><td>{clock(started, seconds=True) if started else "-"}</td></tr>
<tr><th>Alert sent</th><td>{clock(at, seconds=True)} ({e(h.timezone)})</td></tr>
<tr><th>What happened</th><td>{e(alert["detail"])}</td></tr>
<tr><th>How sure</th><td>{e(confidence)}</td></tr>
</table>
<figure>{image}</figure>
<h2>Where to report it</h2>
<ul>
<li><strong>FBI Internet Crime Complaint Center</strong>: <a href="https://www.ic3.gov">ic3.gov</a>.
Courier and "government impersonation" scams belong here.</li>
<li><strong>Federal Trade Commission</strong>:
<a href="https://reportfraud.ftc.gov">reportfraud.ftc.gov</a>.</li>
<li><strong>Local police</strong>, if money or valuables were handed over, or if the courier
is expected to come back.</li>
<li><strong>The bank</strong>, at once, if a withdrawal was made.</li>
</ul>
<p class="hint">Write down anything the caller said: names, badge numbers, phone numbers,
the "code" given for the courier.</p>
<p class="noprint"><a href="/family">Back</a></p>
</main></body></html>"""


def fernet_key(secret: str) -> bytes:
    """A Fernet key as given, or one derived from any other secret (a hosting
    platform's generated value is random but not in Fernet's format)."""
    try:
        Fernet(secret)
        return secret.encode()
    except ValueError:
        return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


def _from_env() -> FastAPI:
    data = Path(os.environ.get("CALLFIRST_DATA", "data"))
    data.mkdir(parents=True, exist_ok=True)
    store = Store(data / "callfirst.db", fernet_key(os.environ["CALLFIRST_KEY"]))
    ring_base = os.environ.get("RING_API_BASE", "http://127.0.0.1:8787")
    ring = Ring(ring_base, os.environ.get("RING_TOKEN", "sandbox"))
    base_url = (os.environ.get("CALLFIRST_BASE_URL") or os.environ.get("RENDER_EXTERNAL_URL")
                or "http://127.0.0.1:8100")
    emulator = demo.Emulator(ring_base) if os.environ.get("CALLFIRST_DEMO") == "1" else None
    port = os.environ.get("PORT", "8100")
    return create_app(store, ring, os.environ["RING_WEBHOOK_KEY"],
                      os.environ.get("CALLFIRST_ADMIN_TOKEN", ""),
                      mailer=notify.from_env(data), base_url=base_url,
                      sender=os.environ.get("CALLFIRST_SENDER",
                                            "Call First <alerts@callfirst.invalid>"),
                      secure_cookies=base_url.startswith("https://"), emulator=emulator,
                      self_url=f"http://127.0.0.1:{port}")


def __getattr__(name: str):
    # `uvicorn callfirst.app:app` builds the app from the environment on first
    # access, so importing this module in tests needs no secrets.
    if name == "app":
        return _from_env()
    raise AttributeError(name)
