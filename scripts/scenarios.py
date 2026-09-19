"""The measured scenarios of DESIGN.md section 11, in both modes, as a table.

    .venv/Scripts/python scripts/scenarios.py

Each scenario is a sequence of events at the door plus the outcome it should
have. The table reports what actually happened - false alerts included, since
they are part of the result.
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from callfirst import deliveries, rules, webhooks  # noqa: E402
from callfirst.household import Delivery, ExpectedVisit, Household, Trusted, iso  # noqa: E402

T0 = datetime(2026, 9, 22, 19, 0, tzinfo=UTC)          # Tuesday 15:00 in New York
DB, CH, CS = "db", "ch", "cs"


def ev(kind, device, s, sub=None):
    at = T0 + timedelta(seconds=s)
    return webhooks.Event("x", at, kind, device, at, sub)


def ring(s): return ev("button_press", DB, s)
def person(s): return ev("motion_detected", DB, s, "human")
def door(s): return ev("contact_sensor_faulted", CS, s)
def blind(s): return ev("device_offline", DB, s)


def household(sensor: bool) -> Household:
    return Household(id="h", doorbell=DB, chime=CH, sensor=CS if sensor else None, enabled=True,
                     trusted=[Trusted("Sarah", "sarah@example.com")])


def run(h, events, before=None):
    actions = list(before(h) if before else [])
    for e in events:
        if e.kind == "contact_sensor_faulted" and not h.sensor:
            continue          # no sensor: the door opening is simply not seen
        actions += rules.on_event(h, e, e.at)
    reminded = any(isinstance(a, rules.Chime) for a in actions)
    told = [a.reason for a in actions if isinstance(a, rules.Alert)]
    return reminded, told


def courier(h):
    return run(h, [person(0), ring(3), person(25), door(40), person(70), person(95)])


def quick_handover(h):
    return run(h, [person(0), ring(2), door(12), person(25)])


def carer(h):
    h.visits.append(ExpectedVisit("carer", [1], "14:00", "16:00"))
    return run(h, [ring(0), door(20), person(40), person(80)])


def signature_delivery(h):
    h.deliveries.append(Delivery("UPS", "1Z999AA10123456784", iso(T0 - timedelta(hours=1)),
                                 iso(T0 + timedelta(hours=3)), True))
    return run(h, [person(0), ring(2), door(15), person(30), person(75)])


def parcel_drop(h):
    return run(h, [person(0), ring(2), person(20)])


def neighbour(h):
    return run(h, [ring(0), door(10), person(30), person(60), person(90)])


def courier_returns(h):
    courier(h)
    rules.tick(h, T0 + timedelta(minutes=30))
    two_days = 2 * 86400
    return run(h, [person(two_days), ring(two_days + 3)])


def paused(h):
    return run(h, [], before=lambda h: rules.pause(h, T0 + timedelta(hours=4), T0))


def collection_notice(h):
    text = "UPS 1Z999AA10123456784: an agent will collect your gold for safekeeping at 3pm"
    proposal = deliveries.Proposal("UPS", "1Z999AA10123456784", T0 - timedelta(hours=1),
                                   T0 + timedelta(hours=2))
    verdict = deliveries.validate(text, proposal, T0)
    if verdict.accepted:
        h.deliveries.append(verdict.delivery)
    return courier(h)


def forged(h):
    raw = b'{"meta":{"time":"2026-09-22T19:00:00Z","request_id":"f"},"data":{}}'
    try:
        webhooks.read("key", raw, "sha256=" + "0" * 64, T0)
        return False, ["ACCEPTED"]
    except webhooks.Rejected:
        return False, ["rejected"]


def offline_visit(h):
    return run(h, [person(0), ring(3), blind(20)])


SCENARIOS = [
    ("Courier pickup: rings, door opens, stays 95 s", courier, (True, ["answered"])),
    ("Quick handover: door opens, gone in 25 s", quick_handover,
     ((True, ["answered"]), (True, []))),          # doorbell only: missed, and said so
    ("Carer inside their declared window", carer, (False, [])),
    ("Signature delivery inside its declared window", signature_delivery, (False, [])),
    ("Unannounced parcel drop, door never opened", parcel_drop, (True, [])),
    ("Neighbour drops by, door opens (false alert)", neighbour, (True, ["answered"])),
    ("Courier returns two days after an alert", courier_returns, (True, ["heightened"])),
    ("Protection paused during the day", paused, (False, ["change"])),
    ("Pasted 'delivery' that is really a collection", collection_notice, (True, ["answered"])),
    ("Forged webhook without a valid signature", forged, (False, ["rejected"])),
    ("Doorbell offline during a visit", offline_visit, (True, ["blind"])),
]


def main() -> int:
    print("| Scenario | Sensor: reminder / told | Doorbell only: reminder / told |")
    print("|---|---|---|")
    failures = 0
    for name, scenario, expected in SCENARIOS:
        cells = []
        for sensor in (True, False):
            got = scenario(household(sensor))
            want = expected if isinstance(expected[0], bool) else expected[0 if sensor else 1]
            ok = got == want
            failures += not ok
            cells.append(f"{'yes' if got[0] else 'no'} / {', '.join(got[1]) or '-'}"
                         + ("" if ok else f"  **expected {want}**"))
        print(f"| {name} | {cells[0]} | {cells[1]} |")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
