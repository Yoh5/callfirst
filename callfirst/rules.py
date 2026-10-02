"""What the code decides. No model is consulted anywhere in this file.

``on_event`` takes one verified Ring event, updates the household and returns
the actions to take. ``tick`` closes visits nobody is at any more. The
functions under "Changes to the protection" are the only ways to weaken
protection, and each one tells the trusted people.

States, per visit:  calm -> reminded -> told, and the household enters
heightened watch after an alert. See DESIGN.md, section 6.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .household import (DWELL, HEIGHTENED, MAX_PAUSE, VISIT_GAP, Delivery, ExpectedVisit,
                        Household, Trusted, Visit, clock, hhmm, iso, today_or_tomorrow)
from .webhooks import Event

REMINDER = "ring-appstore-event-1"             # "call your family first..."
HEIGHTENED_REMINDER = "ring-appstore-event-2"  # "your family has been told..."


@dataclass(frozen=True)
class Chime:
    slot: str


@dataclass(frozen=True)
class Alert:
    """Something the trusted people are told now.

    reason: answered | heightened | blind | change
    confidence: "strong" (a sensor saw the door open), "weak" (inferred from
    how long someone stayed), or None when there is nothing to be confident about.
    """
    reason: str
    at: str
    confidence: str | None = None
    detail: str = ""
    snapshot_at: str | None = None
    recipients: tuple[str, ...] = ()


@dataclass(frozen=True)
class Note:
    text: str


@dataclass
class Outcome:
    actions: list = field(default_factory=list)

    def add(self, action) -> None:
        self.actions.append(action)


def _everyone(h: Household) -> tuple[str, ...]:
    return tuple(t.email for t in h.trusted)


def _at(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


# --------------------------------------------------------------------------- the door


def tick(h: Household, now: datetime) -> list:
    """Close the visit in progress once nobody has been seen for VISIT_GAP."""
    if h.visit and now - _at(h.visit.last_seen) > VISIT_GAP:
        h.visit = None
        return [Note("visit closed")]
    return []


def on_event(h: Household, event: Event, now: datetime) -> list:
    out = Outcome()
    if not h.enabled:
        return [Note("protection is off")]
    out.actions += tick(h, event.at)

    if event.device_id == h.doorbell and event.kind in ("device_offline", "device_online"):
        _health(h, event, out)
    elif event.device_id == h.doorbell and (event.kind == "button_press" or event.is_person):
        _someone(h, event, out)
    elif event.device_id == h.sensor and event.kind == "contact_sensor_faulted":
        _door_opened(h, event, out)
    return out.actions


def _health(h: Household, event: Event, out: Outcome) -> None:
    h.doorbell_online = event.kind == "device_online"
    visit = h.visit
    if h.doorbell_online or not visit:
        return
    visit.blind = True
    # The door stopped seeing while an unexpected visitor was there. Saying
    # nothing would read as "nothing happened"; it is "we could not see".
    if visit.expected is None and not visit.told and not h.paused(event.at):
        visit.told.append("blind")
        out.add(Alert("blind", iso(event.at), None,
                      "The doorbell went offline while an unexpected visitor was at the door.",
                      visit.started, _everyone(h)))


def _someone(h: Household, event: Event, out: Outcome) -> None:
    at = event.at
    if h.visit is None:
        h.visit = Visit(started=iso(at), last_seen=iso(at), expected=h.expectation(at))
        # A door-open webhook can arrive before the ring that preceded it.
        opened = _at(h.door_opened_at)
        if opened and timedelta(0) <= opened - at <= VISIT_GAP:
            h.visit.answered = "sensor"
    visit = h.visit
    if at > _at(visit.last_seen):
        visit.last_seen = iso(at)
    if event.kind == "button_press" and not visit.rang_at:
        visit.rang_at = iso(at)

    if visit.expected is not None or h.paused(at):
        return

    if h.heightened(at) and not visit.told:
        visit.told.append("heightened")
        out.add(Alert("heightened", iso(at), None,
                      "An unexpected visitor is at the door, days after an alert.",
                      iso(at), _everyone(h)))
    if visit.rang_at and not visit.reminded and h.chime:
        visit.reminded = True
        out.add(Chime(HEIGHTENED_REMINDER if h.heightened(at) else REMINDER))

    if h.mode == "doorbell" and not visit.answered and visit.rang_at:
        if _at(visit.last_seen) - _at(visit.rang_at) >= DWELL:
            visit.answered = "dwell"
    _maybe_alert(h, at, out)


def _door_opened(h: Household, event: Event, out: Outcome) -> None:
    h.door_opened_at = iso(event.at)
    visit = h.visit
    if not visit or visit.answered:
        return
    # The visitor has to still be there. A visit nobody has been seen at for
    # VISIT_GAP was closed by tick() before we got here, so opening the door to
    # fetch a parcel after the driver left finds no visit. A door event that
    # arrives late, but happened before the visitor did, is not an answer either.
    if event.at >= _at(visit.started):
        visit.answered = "sensor"
        if not h.paused(event.at):
            _maybe_alert(h, event.at, out)


def _maybe_alert(h: Household, at: datetime, out: Outcome) -> None:
    visit = h.visit
    if not visit or not visit.answered or visit.expected is not None:
        return
    h.heightened_until = iso(at + HEIGHTENED)
    # Told already that someone is there (heightened watch) is not the same as
    # told that the door was opened: the second one is still sent.
    if "answered" in visit.told:
        return
    visit.told.append("answered")
    if visit.answered == "sensor":
        detail, confidence = "The door was opened for an unexpected visitor.", "strong"
    else:
        seconds = int((_at(visit.last_seen) - _at(visit.started)).total_seconds())
        detail = (f"An unexpected visitor rang and stayed {seconds // 60} min {seconds % 60} s "
                  "at the door. The doorbell cannot see whether the door was opened.")
        confidence = "weak"
    out.add(Alert("answered", iso(at), confidence, detail, visit.started, _everyone(h)))


# --------------------------------------------------------------------------- changes to the protection
#
# Scammers demand secrecy: "don't tell your family, turn off that alarm".
# Every change that weakens protection today is therefore told to the trusted
# people at once. That is the whole defence against threat (a) in DESIGN.md.


def _change(h: Household, now: datetime, detail: str) -> Alert:
    return Alert("change", iso(now), None, detail, None, _everyone(h))


def switch_on(h: Household, now: datetime) -> list:
    h.enabled = True
    return [_change(h, now, "Call First was switched on. You will be told when an unexpected "
                            "visitor is let in.")]


def switch_off(h: Household, now: datetime) -> list:
    alert = _change(h, now, "Call First was switched off.")
    h.enabled = False
    h.visit = None
    return [alert]


def pause(h: Household, until: datetime, now: datetime) -> list:
    until = min(until, now + MAX_PAUSE)
    h.paused_until = iso(until)
    local = f"{h.local(until):%A} {clock(h.local(until))}"
    return [_change(h, now, f"Protection was paused until {local}. If this was not planned, "
                            "call now.")]


def resume(h: Household, now: datetime) -> list:
    h.paused_until = None
    return [Note("protection resumed")]


def next_start(visit: ExpectedVisit, h: Household, now: datetime) -> datetime | None:
    """The next time this recurring window opens, within the coming week."""
    local = h.local(now)
    hour, minute = map(int, visit.start.split(":"))
    for days in range(8):
        day = local + timedelta(days=days)
        start = day.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if day.weekday() in visit.weekdays and start + _length(visit) > local:
            return start
    return None


def _length(visit: ExpectedVisit) -> timedelta:
    h1, m1 = map(int, visit.start.split(":"))
    h2, m2 = map(int, visit.end.split(":"))
    return timedelta(hours=h2 - h1, minutes=m2 - m1)


def _se_dit(h: Household, start: datetime | None, now: datetime) -> bool:
    """Does declaring something for ``start`` have to reach the family?

    Today or tomorrow, always: that is the window a scammer needs, and the
    reason this product exists.

    **And anything at all during the heightened week.** After an alert the
    household watches for seven days because couriers come back, and a declared
    window makes a visitor expected — `alert` returns before anything else.
    Those two met badly: a delivery declared for day four was announced to
    nobody *and* silenced the watch over its window, in the exact days the
    product says it is watching hardest.

    It is reachable by the threat the design names first — the victim coached
    against their own tool. Someone whose first attempt raised an alert knows
    the family is watching now, and the cheapest counter is not technical: it
    is *"declare the delivery so it doesn't bother your daughter."*

    The answer is this product's existing rule rather than a new one. Refusing
    the declaration would decide for her, which it does not do anywhere else.
    It tells the family.
    """
    if h.heightened(now):
        return True
    return bool(start and today_or_tomorrow(start, now))


def _depuis_l_alerte(h: Household, now: datetime) -> str:
    """The half-sentence that turns a notice into a reason to telephone."""
    return (" This is during the week of closer watch that followed an alert."
            if h.heightened(now) else "")


def add_visit(h: Household, visit: ExpectedVisit, now: datetime) -> list:
    h.visits.append(visit)
    start = next_start(visit, h, now)
    if _se_dit(h, start, now):
        quand = (f"{h.local(start):%A} {clock(h.local(start))} to {hhmm(visit.end)}"
                 if start else "no upcoming date")
        return [_change(h, now, f"A visit was added: {visit.label}, {quand}. "
                                "Visitors in that window will not trigger the "
                                "reminder." + _depuis_l_alerte(h, now))]
    return [Note(f"visit added: {visit.label}")]


def add_delivery(h: Household, delivery: Delivery, now: datetime) -> list:
    h.deliveries.append(delivery)
    start = datetime.fromisoformat(delivery.start)
    if _se_dit(h, start, now):
        return [_change(h, now, f"A {delivery.carrier} delivery was declared for "
                                f"{h.local(start):%A} {clock(h.local(start))}. Visitors in that window "
                                "will not trigger the reminder."
                                + _depuis_l_alerte(h, now))]
    return [Note(f"delivery added: {delivery.carrier}")]


def add_trusted(h: Household, person: Trusted, now: datetime) -> list:
    # "Add my colleague's email, he will help you" is a script too. The people
    # already trusted hear about the newcomer before the newcomer hears anything.
    alert = _change(h, now, f"{person.name} ({person.email}) was added as a trusted person.")
    h.trusted.append(person)
    return [alert] if alert.recipients else []


def farewell(h: Household, now: datetime) -> list:
    """Deleting everything also switches protection off, so it is told first."""
    return [_change(h, now, "Call First was removed and everything it held was deleted.")]


def remove_trusted(h: Household, email: str, now: datetime) -> list:
    removed = [t for t in h.trusted if t.email == email]
    if not removed:
        return []
    dernier = len(h.trusted) == 1
    # "Sarah will no longer receive alerts" and "nobody will receive alerts"
    # do not call for the same reaction, and the second is the one that leaves
    # a switched-on alarm wired to nothing. It is not an attack: a daughter
    # changes her address or simply leaves, and nothing says the house is now
    # protected in name only.
    texte = (f"{removed[0].name} will no longer receive alerts."
             + (" **Nobody is receiving alerts now.** Call First is still on and "
                "the reminder still plays, but there is no one left to tell. "
                "Add someone to put that right." if dernier else ""))
    alert = _change(h, now, texte)
    h.trusted = [t for t in h.trusted if t.email != email]
    return [alert]    # recipients computed before removal: they are told too
