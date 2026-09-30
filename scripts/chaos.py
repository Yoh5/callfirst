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
    ring = httpx.Client(base_url=RING, headers={"Authorization": "Bearer sandbox"}, timeout=10)
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

    def visit(door):
        ids, _ = door
        for kind, device, sub in (("motion_detected", "doorbell", "human"),
                                  ("button_press", "doorbell", None),
                                  ("contact_sensor_faulted", "contact_sensor", None)):
            ring.post("/_sandbox/events", json={"type": kind, "device_id": ids[device],
                                                "sub_type": sub})
            time.sleep(2)

    with ThreadPoolExecutor(max_workers=homes) as pool:
        list(pool.map(visit, doors))

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

    precedent, calme = comptes(), 0
    for _ in range(30):           # 30 x 1 s, largement au-delà de 1,8 s par webhook
        time.sleep(1)
        actuel = comptes()
        calme = calme + 1 if actuel == precedent else 0
        precedent = actuel
        if calme >= 2:
            break

    # The emulator's /_sandbox/state keeps only the last 50 entries; its chaos
    # log and its HTTP access log keep everything.
    faults = ring.get("/_sandbox/chaos").json()
    actions = faults.get("actions") or faults.get("log") or []
    count = lambda kind: sum(1 for a in actions if a.get("kind") == kind)
    log = (ROOT / "data" / "chaos" / "ring.log").read_text(errors="replace")
    chimes = re.findall(r"POST /v1/devices/([^/]+)/media/audio/playback HTTP/1.1\" 204", log)
    told = sum(1 for _, s in doors
               if any(a["reason"] == "answered" for a in s.get("/api/resident").json()["alerts"]))
    rung_twice = len(chimes) - len(set(chimes))

    print(f"{homes} courier visits ({3 * homes} door events), chaos preset 'delivery', seed {seed}")
    print(f"  webhooks dropped {count('webhook.dropped')}, duplicated "
          f"{count('webhook.duplicated')}, delayed {count('webhook.delayed')}")
    print(f"  reminders played {len(set(chimes))}/{homes}, played twice {rung_twice}")
    print(f"  families told {told}/{homes}")

    # The headline number of the whole submission is "every family was told".
    # It used to be printed and not checked: 58 out of 60 exited 0, in silence,
    # and a harness whose central number is not asserted will eventually
    # publish a wrong one. A missed reminder is a published limitation — a lost
    # doorbell press cannot be recovered — but a family not told is not.
    manques = []
    if rung_twice:
        manques.append(f"{rung_twice} reminder(s) played twice")
    if told < homes:
        manques.append(f"only {told} of {homes} families told")
    if manques:
        print("\nFAIL  " + "; ".join(manques))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
