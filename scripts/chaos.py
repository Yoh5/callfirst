"""Courier visits through an unreliable webhook pipe, counted.

    .venv/Scripts/python scripts/chaos.py [households] [seed]

Starts the emulator in its "delivery" chaos mode - each webhook has a 10%
chance to be dropped, 25% to be duplicated, and up to 1.8 s of delay - gives
each household its own doorbell, chime and door sensor, and plays one courier
visit at every door at once: someone is seen, rings, the door opens.

Counted: how many reminders played (duplicates must not ring twice), how many
families were told, and what was lost on the way.
"""
from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from pathlib import Path

import httpx
from cryptography.fernet import Fernet

sys.path.insert(0, str(Path(__file__).resolve().parent))
from live import APP, PYTHON, RING, ROOT, SANDBOX, wait  # noqa: E402


def main() -> int:
    homes = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    seed = sys.argv[2] if len(sys.argv) > 2 else "7"
    signing, admin = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    data = ROOT / "data" / "chaos"
    data.mkdir(parents=True, exist_ok=True)
    (data / "callfirst.db").unlink(missing_ok=True)
    env = dict(os.environ, CALLFIRST_KEY=Fernet.generate_key().decode(), RING_WEBHOOK_KEY=signing,
               CALLFIRST_ADMIN_TOKEN=admin, RING_API_BASE=RING, RING_TOKEN="sandbox",
               CALLFIRST_DATA=str(data), CALLFIRST_TICK="1")
    servers = [
        subprocess.Popen([str(SANDBOX), "serve", "--port", "8787", "--chaos", "delivery",
                          "--chaos-seed", seed],
                         stdout=open(data / "ring.log", "w"), stderr=subprocess.STDOUT),
        subprocess.Popen([str(PYTHON), "-m", "uvicorn", "callfirst.app:app", "--port", "8100"],
                         cwd=ROOT, env=env, stdout=open(data / "app.log", "w"),
                         stderr=subprocess.STDOUT),
    ]
    try:
        wait(f"{RING}/_sandbox/health")
        wait(f"{APP}/health")
        return run(homes, signing, {"x-admin-token": admin}, seed)
    finally:
        for server in servers:
            server.terminate()


def run(homes: int, signing: str, admin: dict, seed: str) -> int:
    # Thirty seconds, not ten, and the reason is worth writing down: at sixty
    # homes the run died with `httpx.ReadTimeout` on an event POST. Nothing was
    # wrong with the product — sixty threads were asking a single-process
    # emulator to accept an event while it was also delivering webhooks, and
    # ten seconds was not enough patience for the queue. A harness that falls
    # over at the scale the submission claims is how a measurement ends up
    # being quoted at three times its real size.
    ring = httpx.Client(base_url=RING, headers={"Authorization": "Bearer sandbox"}, timeout=30)
    ring.post("/_sandbox/webhooks", json={"url": f"{APP}/webhooks/ring", "signing_key": signing})
    doors = []
    for n in range(homes):
        ids = {kind: ring.post("/_sandbox/devices", json={"kind": kind, "name": f"{kind} {n}"}
                               ).json()["data"]["id"]
               for kind in ("doorbell", "chime", "contact_sensor")}
        link = httpx.post(f"{APP}/api/households", headers=admin, json={
            "id": f"home-{n:02d}", "resident": f"Resident {n}", "doorbell": ids["doorbell"],
            "chime": ids["chime"], "sensor": ids["contact_sensor"], "timezone": "UTC",
            "trusted": [{"name": "Family", "email": f"family{n}@example.com"}]}
        ).json()["resident_link"]
        session = httpx.Client(base_url=APP)
        session.get(link.removeprefix(APP))
        session.post("/api/resident/on").raise_for_status()
        doors.append((ids, session))

    # Which webhook belonged to which home. The emulator's fault log records a
    # dropped delivery by request_id and nothing else, so without this map a
    # run can only say "59 of 60 families told" -- not which home, and not
    # whether the silence was a lost webhook or a rule that declined to fire.
    # The inject endpoint hands back the payload it built, request_id included.
    envois: dict[tuple[int, str], str] = {}
    verrou = Lock()

    def visit(item):
        n, (ids, _) = item
        for kind, device, sub in (("motion_detected", "doorbell", "human"),
                                  ("button_press", "doorbell", None),
                                  ("contact_sensor_faulted", "contact_sensor", None)):
            r = ring.post("/_sandbox/events", json={"type": kind, "device_id": ids[device],
                                                    "sub_type": sub})
            rid = (r.json().get("webhook") or {}).get("meta", {}).get("request_id")
            if rid:
                with verrou:
                    envois[(n, kind)] = rid
            time.sleep(2)

    with ThreadPoolExecutor(max_workers=homes) as pool:
        list(pool.map(visit, list(enumerate(doors))))

    # A fixed six-second sleep was a guess about someone else's machine. Each
    # webhook can be held up to 1.8 s, dropped ones are recovered by a sensor
    # question, and the two compound; on a loaded laptop the run ended while
    # deliveries were still in flight, and the published figure came out 58/60
    # instead of 60/60. A measurement that moves with the load of the machine
    # is not a measurement.
    #
    # So we wait on the thing itself: keep counting until it stops changing,
    # and cap it. Quiet twice in a row is the end of the queue.
    def comptes() -> tuple[int, int]:
        chimes = re.findall(
            r"POST /v1/devices/([^/]+)/media/audio/playback HTTP/1.1\" 204",
            (ROOT / "data" / "chaos" / "ring.log").read_text(errors="replace"),
        )
        told = sum(
            1 for _, s in doors
            if any(a["reason"] == "answered" for a in s.get("/api/resident").json()["alerts"])
        )
        return told, len(set(chimes))

    # Two quiet seconds were enough at twenty homes and not at sixty: with a
    # hundred and sixty webhooks each held up to 1.8 s, plus the sensor
    # questions that recover the dropped ones, the queue goes quiet in the
    # middle of the run. The first sixty-home measurement read 59 of 60
    # families told, and the sixtieth was still in flight. Three quiet seconds,
    # and a minute of patience instead of thirty seconds.
    precedent, calme = comptes(), 0
    for _ in range(60):
        time.sleep(1)
        actuel = comptes()
        calme = calme + 1 if actuel == precedent else 0
        precedent = actuel
        if calme >= 3:
            break

    # The emulator's /_sandbox/state keeps only the last 50 entries; its chaos
    # log and its HTTP access log keep everything.
    faults = ring.get("/_sandbox/chaos").json()
    actions = faults.get("actions") or faults.get("log") or []
    count = lambda kind: sum(1 for a in actions if a.get("kind") == kind)
    log = (ROOT / "data" / "chaos" / "ring.log").read_text(errors="replace")
    chimes = re.findall(r"POST /v1/devices/([^/]+)/media/audio/playback HTTP/1.1\" 204", log)
    # Name the households that were not told. "59 of 60" sends you looking
    # through sixty logs; "home-37" sends you to the one that matters.
    muets = [f"home-{n:02d}" for n, (_, s) in enumerate(doors)
             if not any(a["reason"] == "answered"
                        for a in s.get("/api/resident").json()["alerts"])]
    told = homes - len(muets)
    rung_twice = len(chimes) - len(set(chimes))

    # A visit whose motion AND press were both dropped was never seen at all:
    # the door opening alone raises nothing, deliberately, because a door that
    # opens with nobody at it is the resident fetching the post. Nothing in the
    # Partner API lets us ask the doorbell what it saw, so this one is not
    # recoverable -- and it is the only case where a family is not told.
    perdus = {a.get("request_id") for a in actions if a.get("kind") == "webhook.dropped"}
    aveugles = {n for n in range(homes)
                if envois.get((n, "motion_detected")) in perdus
                and envois.get((n, "button_press")) in perdus}

    print(f"{homes} courier visits ({3 * homes} door events), chaos preset 'delivery', seed {seed}")
    print(f"  webhooks dropped {count('webhook.dropped')}, duplicated "
          f"{count('webhook.duplicated')}, delayed {count('webhook.delayed')}")
    print(f"  reminders played {len(set(chimes))}/{homes}, played twice {rung_twice}")
    print(f"  families told {told}/{homes}; "
          f"visits never seen (both doorbell webhooks dropped) {len(aveugles)}")

    # The headline number of the whole submission is "every family was told".
    # It used to be printed and not checked: 58 out of 60 exited 0, in silence,
    # and a harness whose central number is not asserted will eventually
    # publish a wrong one. A missed reminder is a published limitation — a lost
    # doorbell press cannot be recovered — but a family not told is not.
    # The claim is not "every family, whatever happens" -- that would be a
    # promise the Partner API cannot keep. It is: every family whose doorbell
    # was seen. Measured against the emulator's own fault log, so a regression
    # fails here and a lost pair of webhooks does not.
    inattendus = [m for m in muets if int(m.removeprefix("home-")) not in aveugles]
    manques = []
    if rung_twice:
        manques.append(f"{rung_twice} reminder(s) played twice")
    if inattendus:
        manques.append("families not told although the doorbell was seen: "
                       + ", ".join(inattendus))
    if manques:
        print("\nFAIL  " + "; ".join(manques))
        # And say what the system saw for each silent household. A failure
        # that reports only a count sends you through sixty logs; this says
        # whether the home heard a reminder and what alerts it did raise, and
        # therefore whether a webhook was lost or a rule declined to fire.
        for nom in inattendus:
            n = int(nom.removeprefix("home-"))
            vue = doors[n][1].get("/api/resident").json()
            raisons = [a["reason"] for a in vue["alerts"]] or ["none"]
            print(f"  {nom}: reminders {len(vue['reminders'])}, "
                  f"alerts {', '.join(raisons)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
