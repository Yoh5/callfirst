"""Install the Ring emulator in its own virtualenv, pinned by hash.

ring-sandbox (MIT, https://github.com/josepha-mayo/ring-sandbox) was read in
full before use. It registers a pytest plugin on install, so it lives in
.sandbox/ and never in the application's environment: our test runs must not
load third-party code we did not ask for.

    python scripts/setup_sandbox.py
    .sandbox/env/Scripts/ring-sandbox serve --port 8787      (Windows)
    .sandbox/env/bin/ring-sandbox serve --port 8787          (elsewhere)
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import urllib.request
import venv
from pathlib import Path

VERSION = "0.1.0"
WHEEL = f"ring_sandbox-{VERSION}-py3-none-any.whl"
SHA256 = "134d9e00c9e07b71de08d52df40e182f02100f7f3ed914afc466a09a484407e0"
URL = f"https://files.pythonhosted.org/packages/py3/r/ring-sandbox/{WHEEL}"

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / ".sandbox"


def main() -> None:
    TARGET.mkdir(exist_ok=True)
    wheel = TARGET / WHEEL
    if not wheel.exists():
        with urllib.request.urlopen(URL) as response:
            wheel.write_bytes(response.read())
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if digest != SHA256:
        wheel.unlink()
        sys.exit(f"hash mismatch for {WHEEL}: got {digest}; refusing to install")

    venv.create(TARGET / "env", with_pip=True)
    python = TARGET / "env" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.run([str(python), "-m", "pip", "install", "--quiet", f"{wheel}[server]"], check=True)
    print(f"ring-sandbox {VERSION} installed in {TARGET / 'env'} (hash verified)")


if __name__ == "__main__":
    main()
