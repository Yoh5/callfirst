"""A hands-on demo: the emulator and the service, a household, and a keyboard
that plays the front door.

    .venv/Scripts/python scripts/demo.py

It prints Margaret's link and Sarah's link. Open both, then press:

    r  someone rings            p  a person is seen at the door
    o  the door opens           x  the doorbell goes offline
    n  the doorbell comes back  q  quit

Alert emails land in data/demo/mail/ as .eml files. Put a doorstep photo at
demo/default.jpg to make the still image real; otherwise the emulator's
placeholder is used.
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

KEYS = {"r": ("button_press", "Front Door", None), "p": ("motion_detected", "Front Door", "human"),
        "o": ("contact_sensor_faulted", "Front Door Sensor", None),
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
        print(__doc__.split("then press:")[1].split("Alert emails")[0])
        if "--no-input" in sys.argv:        # drive it from elsewhere; stop with Ctrl+C
            while True:
                time.sleep(3600)
        while (key := input("> ").strip().lower()) != "q":
            if key in KEYS:
                kind, device, sub = KEYS[key]
                ring.post("/_sandbox/events", json={"type": kind, "device_id": devices[device],
                                                    "sub_type": sub})
                played = [d["event"] for d in ring.get("/_sandbox/state").json()["delivered"]
                          if d.get("kind") == "chime.play"]
                print(f"  {kind}. Chime has played {len(played)} time(s).")
    finally:
        for server in servers:
            server.terminate()


if __name__ == "__main__":
    main()
