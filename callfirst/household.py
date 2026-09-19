"""A household: what it declared, and what the door has seen since.

Everything here is plain data that round-trips through JSON, so the store can
encrypt it as one blob. Declared things (visits, deliveries, trusted people)
and runtime state (the visit in progress, heightened watch) live together
because every decision needs both.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

DWELL = timedelta(seconds=60)        # doorbell-only: this long at the door means "answered"
HEIGHTENED = timedelta(days=7)       # watch after an alert; couriers come back
MAX_PAUSE = timedelta(hours=24)      # a pause ends by itself
VISIT_GAP = timedelta(seconds=90)    # no person seen this long: the visitor has left


@dataclass
class Trusted:
    name: str
    email: str


@dataclass
class ExpectedVisit:
    """A recurring window: the carer, Tuesdays and Thursdays, 10:00-12:00."""
    label: str
    weekdays: list[int]              # Monday = 0
    start: str                       # "10:00", household local time
    end: str

    def covers(self, local: datetime) -> bool:
        return (local.weekday() in self.weekdays
                and time.fromisoformat(self.start) <= local.time() < time.fromisoformat(self.end))


@dataclass
class Delivery:
    """A delivery the resident declared, already validated (see deliveries.py)."""
    carrier: str
    tracking: str
    start: str                       # ISO datetimes, UTC
    end: str
    signature_required: bool = False

    def covers(self, at: datetime) -> bool:
        return datetime.fromisoformat(self.start) <= at <= datetime.fromisoformat(self.end)


@dataclass
class Visit:
    """Someone at the door, from the first sign of them until they are gone."""
    started: str
    last_seen: str
    rang_at: str | None = None
    expected: str | None = None      # what made it expected, if anything
    reminded: bool = False
    answered: str | None = None      # "sensor" | "dwell" once known
    told: list[str] = field(default_factory=list)   # alert reasons already sent
    blind: bool = False              # the doorbell went offline during it


@dataclass
class Household:
    id: str
    doorbell: str
    resident: str = "the resident"   # a first name, used in alerts: "call Margaret now"
    chime: str | None = None
    sensor: str | None = None
    timezone: str = "America/New_York"
    trusted: list[Trusted] = field(default_factory=list)
    visits: list[ExpectedVisit] = field(default_factory=list)
    deliveries: list[Delivery] = field(default_factory=list)
    enabled: bool = False            # switched on by the resident, never on them
    paused_until: str | None = None
    heightened_until: str | None = None
    door_opened_at: str | None = None
    doorbell_online: bool = True
    visit: Visit | None = None

    @property
    def mode(self) -> str:
        return "sensor" if self.sensor else "doorbell"

    def local(self, at: datetime) -> datetime:
        return at.astimezone(ZoneInfo(self.timezone))

    def paused(self, at: datetime) -> bool:
        return bool(self.paused_until) and at < datetime.fromisoformat(self.paused_until)

    def heightened(self, at: datetime) -> bool:
        return bool(self.heightened_until) and at < datetime.fromisoformat(self.heightened_until)

    def expectation(self, at: datetime) -> str | None:
        """What makes a visitor at ``at`` expected, or None."""
        local = self.local(at)
        for visit in self.visits:
            if visit.covers(local):
                return visit.label
        for delivery in self.deliveries:
            if delivery.covers(at):
                return f"{delivery.carrier} delivery"
        return None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "Household":
        raw = dict(raw)
        raw["trusted"] = [Trusted(**t) for t in raw.get("trusted", [])]
        raw["visits"] = [ExpectedVisit(**v) for v in raw.get("visits", [])]
        raw["deliveries"] = [Delivery(**d) for d in raw.get("deliveries", [])]
        raw["visit"] = Visit(**raw["visit"]) if raw.get("visit") else None
        return cls(**raw)


def iso(at: datetime) -> str:
    return at.astimezone(UTC).isoformat()


def today_or_tomorrow(start: datetime, now: datetime) -> bool:
    """Whether a change takes effect soon enough to be used against the resident today."""
    return start - now < timedelta(hours=24)


__all__ = [
    "DWELL", "HEIGHTENED", "MAX_PAUSE", "VISIT_GAP", "Trusted", "ExpectedVisit",
    "Delivery", "Visit", "Household", "iso", "today_or_tomorrow",
]
