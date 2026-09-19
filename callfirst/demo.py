"""The hosted demo: a front door you can play from the browser.

Only mounted when CALLFIRST_DEMO=1. Each visitor gets their own household,
with its own emulated doorbell, chime and door sensor inside ring-sandbox,
which listens on 127.0.0.1 only: its /_sandbox control plane is never
reachable from outside. The visitor presses "someone rings"; the emulator
sends a signed webhook to Call First like Ring would; Call First decides
exactly as it does for a real household.

Demo households are deleted after DEMO_LIFETIME, and there are never more than
MAX_DEMOS at once.
"""
from __future__ import annotations

from datetime import timedelta

import httpx

DEMO_LIFETIME = timedelta(hours=2)
MAX_DEMOS = 150
STARTS_PER_HOUR = 6          # per client address

# What each button on the demo panel sends, as the emulator's inject body.
DOOR = {
    "ring": [("motion_detected", "doorbell", "human"), ("button_press", "doorbell", None)],
    "stay": [("motion_detected", "doorbell", "human")],
    "open": [("contact_sensor_faulted", "sensor", None)],
    "close": [("contact_sensor_cleared", "sensor", None)],
    "offline": [("device_offline", "doorbell", None)],
    "online": [("device_online", "doorbell", None)],
}


class Emulator:
    """The few control-plane calls the demo needs, against ring-sandbox."""

    def __init__(self, base_url: str, client: httpx.Client | None = None):
        self.base = base_url.rstrip("/")
        self._http = client or httpx.Client(timeout=10)

    def register(self, url: str, signing_key: str) -> None:
        self._http.post(f"{self.base}/_sandbox/webhooks",
                        json={"url": url, "signing_key": signing_key}).raise_for_status()

    def add(self, kind: str, name: str) -> str:
        r = self._http.post(f"{self.base}/_sandbox/devices", json={"kind": kind, "name": name})
        r.raise_for_status()
        return r.json()["data"]["id"]

    def inject(self, kind: str, device: str, sub_type: str | None = None) -> None:
        self._http.post(f"{self.base}/_sandbox/events",
                        json={"type": kind, "device_id": device, "sub_type": sub_type}
                        ).raise_for_status()

    def healthy(self) -> bool:
        try:
            return self._http.get(f"{self.base}/_sandbox/health").status_code == 200
        except httpx.HTTPError:
            return False
