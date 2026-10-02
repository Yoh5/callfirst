"""A hands-on demo: the emulator and the service, a household, and a keyboard
that plays the front door.

    .venv/Scripts/python scripts/demo.py

It prints Margaret's link and Sarah's link. Open both, then press:

    r  someone rings            p  a person is seen at the door
    o  the door opens           c  the door closes
    x  the doorbell goes offline
    n  the doorbell comes back  q  quit

Alert emails land in data/demo/mail/ as .eml files. The doorbell's still is
demo/default.jpg, an illustration drawn by scripts/make_demo_still.py.
"""
from __future__ import annotations

import email
import email.policy
import os
import re
import time
import secrets
import subprocess
import sys
from pathlib import Path

import httpx
from cryptography.fernet import Fernet

sys.path.insert(0, str(Path(__file__).resolve().parent))
from live import APP, PYTHON, RING, SANDBOX, ROOT, wait  # noqa: E402

# Only the ring plays a reminder: the rules play it when a visit has rung, so
# motion alone and a door opening never do. Printing "nothing played -- switch
# the protection on" after a door opening blames the resident for behaviour
# that is exactly right, and sends whoever is watching looking for a fault that
# is not there. Each key says what it actually did.
APRES = {
    "p": "a person is at the door. The reminder plays when they ring.",
    "o": "the door opened. The family is told by email, not by the chime — "
         "look in data/demo/mail/.",
    "c": "the door closed.",
    "x": "the doorbell is offline. Margaret's page says so, and the family is told "
         "if it happens while an unexpected visitor is there.",
    "n": "the doorbell is back.",
}

KEYS = {"r": ("button_press", "Front Door", None), "p": ("motion_detected", "Front Door", "human"),
        "o": ("contact_sensor_faulted", "Front Door Sensor", None),
        "c": ("contact_sensor_cleared", "Front Door Sensor", None),
        "x": ("device_offline", "Front Door", None), "n": ("device_online", "Front Door", None)}


def main() -> None:
    signing, admin = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    data = ROOT / "data" / "demo"
    data.mkdir(parents=True, exist_ok=True)
    (data / "callfirst.db").unlink(missing_ok=True)
    for old in (data / "mail").glob("*.eml"):
        old.unlink()
    env = dict(os.environ, CALLFIRST_KEY=Fernet.generate_key().decode(), RING_WEBHOOK_KEY=signing,
               CALLFIRST_ADMIN_TOKEN=admin, RING_API_BASE=RING, RING_TOKEN="sandbox",
               CALLFIRST_DATA=str(data))
    serve = [str(SANDBOX), "serve", "--port", "8787"]
    media = ROOT / "demo"
    if (media / "default.jpg").exists():
        serve += ["--media-dir", str(media)]
    servers = [subprocess.Popen(serve, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
               subprocess.Popen([str(PYTHON), "-m", "uvicorn", "callfirst.app:app", "--port",
                                 "8100"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)]
    try:
        wait(f"{RING}/_sandbox/health")
        wait(f"{APP}/health")
        ring = httpx.Client(base_url=RING, headers={"Authorization": "Bearer sandbox"})
        devices = {d["attributes"]["name"]: d["id"]
                   for d in ring.get("/v1/devices").json()["data"]}
        ring.post("/_sandbox/webhooks", json={"url": f"{APP}/webhooks/ring",
                                              "signing_key": signing})
        created = httpx.post(f"{APP}/api/households", headers={"x-admin-token": admin}, json={
            "id": "margaret", "resident": "Margaret", "doorbell": devices["Front Door"],
            "chime": devices["Kitchen Chime"], "sensor": devices["Front Door Sensor"],
            "timezone": "America/New_York",
            "trusted": [{"name": "Sarah", "email": "sarah@example.com"}]}).json()
        eml = sorted((data / "mail").glob("*.eml"))[0].read_bytes()
        invite = email.message_from_bytes(eml, policy=email.policy.default)
        family = re.search(r"(http://\S+/f/\S+)", invite.get_body().get_content()).group(1)
        print(f"\nMargaret (resident): {created['resident_link']}")
        print(f"Sarah (family):      {family}\n")
        print("Open Margaret's link first and press Switch on. Nothing plays and")
        print("nobody is told while the protection is off — which is the point, and")
        print("it is also the first thing that looks like a bug.\n")
        print(__doc__.split("then press:")[1].split("Alert emails")[0])
        if "--no-input" in sys.argv:        # drive it from elsewhere; stop with Ctrl+C
            while True:
                time.sleep(3600)
        def chimes() -> list[tuple]:
            """The chime plays the emulator has seen, as comparable keys.

            Two bugs lived in the line this replaces. It counted
            `/_sandbox/state`, which keeps **the last fifty entries only**: past
            twenty-odd keypresses the count went *down*, which reads as a
            product that stopped working. And it read the count in the same
            breath as posting the event, before the emulator had delivered the
            webhook and the service had called back — so the first thing anyone
            sees, including on camera, is "played 0 time(s)".
            """
            return [(d.get("device_id"), d.get("event"), d.get("at"))
                    for d in ring.get("/_sandbox/state").json()["delivered"]
                    if d.get("kind") == "chime.play"]

        while (key := input("> ").strip().lower()) != "q":
            if key in KEYS:
                kind, device, sub = KEYS[key]
                avant = set(chimes())
                ring.post("/_sandbox/events", json={"type": kind, "device_id": devices[device],
                                                    "sub_type": sub})
                if key in APRES:
                    print(f"  {kind}. {APRES[key]}")
                    continue
                # Wait on the thing itself rather than on a guess about how fast
                # this machine is, and stop as soon as it happens.
                nouveau = []
                for _ in range(12):
                    time.sleep(0.25)
                    nouveau = [c for c in chimes() if c not in avant]
                    if nouveau:
                        break
                if nouveau:
                    print(f"  {kind}. The reminder played ({nouveau[-1][1]}).")
                else:
                    print(f"  {kind}. Nothing played — switch the protection on from "
                          "Margaret's page, or the visitor is expected, or the reminder "
                          "already played for this visitor.")
    finally:
        for server in servers:
            server.terminate()


if __name__ == "__main__":
    main()
