"""Start the hosted demo: the Ring emulator on localhost, Call First on $PORT.

    python scripts/hosted.py        (after python scripts/setup_sandbox.py)

The emulator binds to 127.0.0.1 only, with a bearer token generated at boot,
so neither its Partner API nor its /_sandbox control plane is reachable from
the internet. Call First is the only thing listening publicly.
"""
from __future__ import annotations

import atexit
import os
import secrets
import subprocess
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent.parent
WIN = sys.platform == "win32"
SANDBOX = ROOT / ".sandbox" / "env" / ("Scripts/ring-sandbox.exe" if WIN else "bin/ring-sandbox")
RING_PORT = "8787"


def main() -> None:
    token = secrets.token_urlsafe(24)
    emulator = subprocess.Popen([str(SANDBOX), "serve", "--host", "127.0.0.1", "--port", RING_PORT,
                                 "--token", token, "--media-dir", str(ROOT / "demo")])
    atexit.register(emulator.terminate)

    os.environ.update(CALLFIRST_DEMO="1", RING_API_BASE=f"http://127.0.0.1:{RING_PORT}",
                      RING_TOKEN=token)
    sys.path.insert(0, str(ROOT))
    uvicorn.run("callfirst.app:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8100")),
                proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
