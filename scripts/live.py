"""Run Call First against the Ring emulator, for real: two servers, signed
webhooks over HTTP, the chime played inside the emulator.

    python scripts/setup_sandbox.py     (once)
    .venv/Scripts/python scripts/live.py

Keys are generated for the run and never printed.
"""
from __future__ import annotations

import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import httpx
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parent.parent
WIN = sys.platform == "win32"
SANDBOX = ROOT / ".sandbox" / "env" / ("Scripts/ring-sandbox.exe" if WIN else "bin/ring-sandbox")
PYTHON = ROOT / ".venv" / ("Scripts/python.exe" if WIN else "bin/python")
RING, APP = "http://127.0.0.1:8787", "http://127.0.0.1:8100"


def wait(url: str) -> None:
    for _ in range(100):
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    sys.exit(f"{url} did not come up")


def main() -> int:
    signing, admin = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    data = ROOT / "data" / "live"
    data.mkdir(parents=True, exist_ok=True)
    (data / "callfirst.db").unlink(missing_ok=True)
    env = dict(os.environ, CALLFIRST_KEY=Fernet.generate_key().decode(),
               RING_WEBHOOK_KEY=signing, CALLFIRST_ADMIN_TOKEN=admin,
               RING_API_BASE=RING, RING_TOKEN="sandbox", CALLFIRST_DATA=str(data))
    servers = [
        subprocess.Popen([str(SANDBOX), "serve", "--port", "8787"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
        subprocess.Popen([str(PYTHON), "-m", "uvicorn", "callfirst.app:app", "--port", "8100"],
                         cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
    ]
    try:
        wait(f"{RING}/_sandbox/health")
        wait(f"{APP}/health")
        return run(signing, {"x-admin-token": admin})
    finally:
        for server in servers:
            server.terminate()


def run(signing: str, admin: dict) -> int:
    ring = httpx.Client(base_url=RING, headers={"Authorization": "Bearer sandbox"})
    app = httpx.Client(base_url=APP, headers=admin)
    devices = {d["attributes"]["name"]: d["id"] for d in ring.get("/v1/devices").json()["data"]}
    doorbell, chime = devices["Front Door"], devices["Kitchen Chime"]
    sensor = devices["Front Door Sensor"]
    ring.post("/_sandbox/webhooks", json={"url": f"{APP}/webhooks/ring", "signing_key": signing})

    app.post("/api/households", json={
        "id": "live", "doorbell": doorbell, "chime": chime, "sensor": sensor,
        "timezone": "UTC", "trusted": [{"name": "Sarah", "email": "sarah@example.com"}]}
    ).raise_for_status()
    app.post("/api/households/live/on").raise_for_status()

    def inject(kind, device, sub_type=None):
        ring.post("/_sandbox/events", json={"type": kind, "device_id": device,
                                            "sub_type": sub_type}).raise_for_status()
        time.sleep(0.4)     # the emulator delivers webhooks in a background task

    inject("motion_detected", doorbell, "human")
    inject("button_press", doorbell)
    inject("contact_sensor_faulted", sensor)

    played = [d for d in ring.get("/_sandbox/state").json().get("delivered", [])
              if d.get("kind") == "chime.play"]
    hooks = [d for d in ring.get("/_sandbox/state").json().get("delivered", [])
             if d.get("kind") == "webhook"]
    state = app.get("/api/households/live").json()
    alerts = [s for s in state["sent"] if s["kind"] == "alert" and s["reason"] == "answered"]

    # A forged webhook, straight at the service, without Ring's key.
    forged = httpx.post(f"{APP}/webhooks/ring", content=b'{"meta":{},"data":{}}',
                        headers={"x-signature": "sha256=" + "0" * 64})

    checks = {
        "webhooks delivered and accepted (204)": hooks and all(h["status"] == 204 for h in hooks),
        "reminder played on the emulator's chime": [p["event"] for p in played]
            == ["ring-appstore-event-1"],
        "one strong alert, with the doorbell's still": len(alerts) == 1
            and alerts[0]["confidence"] == "strong" and alerts[0]["image"],
        "forged webhook refused (401)": forged.status_code == 401,
    }
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
