"""Break each rule that matters on purpose; a test must fail every time.

    .venv/Scripts/python scripts/mutate.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MUTATIONS = [
    ("callfirst/rules.py", "    if visit.expected is not None or h.paused(at):\n        return",
     "    if visit.expected is not None:\n        return", "pause ignored at the door"),
    ("callfirst/rules.py", ">= DWELL:", "> DWELL * 3:", "dwell threshold"),
    ("callfirst/rules.py", "    if event.at >= _at(visit.started):",
     "    if True:", "door opened before the visitor came"),
    ("callfirst/rules.py", "    if h.visit and now - _at(h.visit.last_seen) > VISIT_GAP:",
     "    if h.visit and now - _at(h.visit.last_seen) > VISIT_GAP * 10:",
     "door opened after the visitor left"),
    ("callfirst/rules.py", "    if not visit or not visit.answered or visit.expected is not None:",
     "    if not visit or not visit.answered:", "expected visitor alerted"),
    ("callfirst/rules.py", "HEIGHTENED_REMINDER if h.heightened(at) else REMINDER",
     "REMINDER", "heightened reminder slot"),
    ("callfirst/rules.py", "until = min(until, now + MAX_PAUSE)", "", "unbounded pause"),
    ("callfirst/rules.py", "    if \"answered\" in visit.told:", "    if visit.told:",
     "answer after heightened alert swallowed"),
    ("callfirst/rules.py", "        if opened and timedelta(0) <= opened - at <= VISIT_GAP:",
     "        if False:", "out-of-order door event"),
    ("callfirst/rules.py", "    h.heightened_until = iso(at + HEIGHTENED)\n", "",
     "no heightened watch"),
    ("callfirst/rules.py", "    if h.doorbell_online or not visit:", "    if True:",
     "blind door unreported"),
    ("callfirst/rules.py", "    if start and today_or_tomorrow(start, now):", "    if False:",
     "silent visit added today"),
    ("callfirst/rules.py", "    alert = _change(h, now, f\"{removed[0].name} will no longer receive alerts.\")\n    h.trusted = [t for t in h.trusted if t.email != email]",
     "    h.trusted = [t for t in h.trusted if t.email != email]\n    alert = _change(h, now, f\"{removed[0].name} will no longer receive alerts.\")",
     "removed person not told"),
    ("callfirst/webhooks.py", "    if not verify(key, raw, header):", "    if False:",
     "signature not checked"),
    ("callfirst/webhooks.py", "    if now - event.sent_at > MAX_AGE:", "    if False:",
     "stale accepted"),
    ("callfirst/store.py", "                return False", "                return True",
     "replays acted on"),
    ("callfirst/deliveries.py", "    elif _compact(proposal.tracking) not in _compact(text):",
     "    elif False:", "invented tracking number"),
    ("callfirst/deliveries.py", "    if words:", "    if False:", "collections accepted"),
    ("callfirst/store.py", "(household_id, at, self._fernet.encrypt(text.encode())))",
     "(household_id, at, text.encode()))", "journal in clear"),
    ("callfirst/app.py", "        if not admin_token or not hmac.compare_digest(",
     "        if False and not hmac.compare_digest(", "admin API open"),
]


def main() -> int:
    survived = []
    for path, before, after, name in MUTATIONS:
        file = ROOT / path
        original = file.read_text(encoding="utf-8")
        if original.count(before) != 1:
            print(f"??    {name}: pattern not found once")
            survived.append(name)
            continue
        file.write_text(original.replace(before, after), encoding="utf-8")
        try:
            result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p",
                                     "no:warnings", "tests"], cwd=ROOT, capture_output=True)
        finally:
            file.write_text(original, encoding="utf-8")
        caught = result.returncode != 0
        print(f"{'caught' if caught else 'MISSED'}  {name}")
        if not caught:
            survived.append(name)
    print(f"\n{len(MUTATIONS) - len(survived)}/{len(MUTATIONS)} mutations caught")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
