"""The few Partner API calls Call First makes: play a chime slot, take a still.

Least privilege: nothing here lists history, downloads clips or opens live
video. The snapshot is fetched only when an alert is sent (Ring's data
minimisation rule).
"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urljoin, urlparse

import httpx

MAX_IMAGE = 5 * 1024 * 1024


class Ring:
    def __init__(self, base_url: str, token: str, client: httpx.Client | None = None):
        self.base = base_url.rstrip("/")
        self._http = client or httpx.Client(timeout=10)
        self._auth = {"Authorization": f"Bearer {token}"}

    def play(self, chime: str, slot: str) -> bool:
        r = self._http.post(f"{self.base}/v1/devices/{chime}/media/audio/playback",
                            json={"event": slot}, headers=self._auth)
        return r.status_code in (200, 204)

    def sensor_open(self, sensor: str) -> bool | None:
        """The contact sensor's current state: True open, False closed, None unknown.

        Webhooks can be lost. While an unexpected visitor is at the door this is
        asked every few seconds, so a lost "door opened" still gets through.
        """
        try:
            r = self._http.get(f"{self.base}/v1/devices/{sensor}/status", headers=self._auth)
            if r.status_code != 200:
                return None
            return bool(r.json()["data"]["attributes"]["contact_detection"]["faulted"])
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return None

    def snapshot(self, camera: str, at: datetime) -> bytes | None:
        r = self._http.post(f"{self.base}/v1/devices/{camera}/media/image/download",
                            json={"type": "at_timestamp",
                                  "timestamp": int(at.timestamp() * 1000),
                                  "image_options": {"format": "jpeg"}},
                            headers=self._auth, follow_redirects=False)
        if r.status_code != 303:
            return None
        # The image lives behind a pre-signed URL on another host. The bearer
        # token is not sent there.
        target = urljoin(self.base + "/", r.headers["location"])
        if urlparse(target).scheme not in ("http", "https"):
            return None
        image = self._http.get(target, follow_redirects=False)
        if image.status_code != 200 or len(image.content) > MAX_IMAGE:
            return None
        return image.content
