"""Break each rule that matters on purpose; a test must fail every time.

    .venv/Scripts/python scripts/mutate.py

**This edits the source tree in place**, so nothing else may run against the
working copy while it does — a test suite started alongside reads half-mutated
files and fails for reasons that have nothing to do with it.

And because it edits production source, it has to survive its own death. The
`finally` below covers an exception; it does not cover Ctrl-C landing between
the write and the restore, or the process being killed outright — which is not
hypothetical, it is how a background run ends when it hits a time limit. A
mutation left behind is a sabotaged file sitting in the working tree waiting to
be committed, which is a worse outcome than any bug this script was written to
find. So every original is held from the start, restored from an exit hook and
from a signal handler as well as from the `finally`, and every restore is read
back and checked.
"""
from __future__ import annotations

import atexit
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MUTATIONS = [
    # A declared window makes a visitor expected, and the heightened week after
    # an alert exists because couriers come back. Declaring something for day
    # four of that week used to tell nobody and silence the watch over its
    # window -- reachable by the threat the design names first, the victim
    # coached against their own tool.
    ("callfirst/rules.py",
     "    if h.heightened(now):\n        return True",
     "    if False:\n        return True",
     "declaration during the heightened week kept quiet"),
    # The demo is the only door a stranger reaches without a link, and each
    # call creates a household. X-Forwarded-For reads *claimed, …, observed*:
    # taking the first entry takes what the caller wrote, so a fresh value on
    # every request and the per-address limit never binds.
    ("callfirst/app.py", "            return transmis[-1]", "            return transmis[0]",
     "the caller chooses its own rate-limit key"),
    # And pruning only the caller left a list behind for every address ever
    # seen — the same rotating request that bypassed the limit also grew the
    # process without bound.
    ("callfirst/app.py",
     "        for adresse in list(journal):", "        for adresse in [qui]:",
     "rate-limit log pruned only for the caller"),
    # A window makes a visitor expected, so while one lasts the reminder does
    # not play and nobody is told. Guessing which Tuesday a message meant is
    # therefore not a convenience that fails gracefully: it is silence on the
    # day it mattered, and silence is the one failure nobody reports.
    ("callfirst/when.py", "    if len(lectures) < 2:\n        demande = \"\"",
     "    lectures = lectures[:1]", "a guessed delivery window"),
    ("callfirst/deliveries.py", "    seule = when.lis(text, today).certain if today else None",
     "    seule = (when.lis(text, today).lectures or [None])[0] if today else None",
     "the first reading taken as the reading"),
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
    ("callfirst/rules.py",
     "    return bool(start and today_or_tomorrow(start, now))",
     "    return False", "silent visit added today"),
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
    ("callfirst/app.py", "            if who[1] == role:", "            if True:",
     "family can change the protection"),
    ("callfirst/app.py", "            if who and who[1] == role:", "            if who:",
     "a family token works as a resident cookie"),
    ("callfirst/app.py", "            if not household_id.startswith(\"demo-\"):", "            if False:",
     "any household's door playable"),
    ("callfirst/app.py",
     "            if not compte(starts, appelant(request), now, demo.STARTS_PER_HOUR):",
     "            if False:", "demo starts unbounded"),
    ("callfirst/app.py", "        if not found or found[1] != role:", "        if not found:",
     "family link opens the resident page"),
    ("callfirst/store.py", "outbox where household = ? \"\n                               \"and id = ?\", (household_id, sent_id))",
     "outbox where ? is not null and \"\n                               \"id = ?\", (household_id, sent_id))",
     "alerts readable across households"),
    ("callfirst/store.py", "                              self._fernet.encrypt(email.encode()) if email else None))",
     "                              email.encode() if email else None))", "emails in clear"),
    ("callfirst/app.py", "        change(household_id, rules.farewell)\n", "",
     "deletion not told"),
    ("callfirst/rules.py", "    h.trusted.append(person)\n    return [alert] if alert.recipients else []",
     "    h.trusted.append(person)\n    alert = _change(h, now, alert.detail)\n    return [alert] if alert.recipients else []",
     "newcomer told instead of the others"),
    ("callfirst/app.py", "                if opened:", "                if False:",
     "lost door webhook stays lost"),
    ("callfirst/app.py", "                    and visit.expected is None and not visit.answered):",
     "                    and True):", "sensor asked during expected visits"),
    ("callfirst/app.py",
     "        if not compte(reads, household_id, now, READS_PER_HOUR):",
     "        if False:", "model reads unbounded"),
    ("callfirst/app.py", "        if not admin_token or not hmac.compare_digest(",
     "        if False and not hmac.compare_digest(", "admin API open"),
]


def _rendre(intacts: dict[Path, str]) -> None:
    """Put every file back as it was found. Safe to call more than once."""
    for file, original in intacts.items():
        try:
            if file.read_text(encoding="utf-8") != original:
                file.write_text(original, encoding="utf-8")
        except OSError:
            pass


def main() -> int:
    fichiers = {ROOT / path for path, *_ in MUTATIONS}
    intacts = {f: f.read_text(encoding="utf-8") for f in fichiers}

    # Three ways out, all of them covered. A killed run must not leave a
    # sabotaged file in the tree.
    atexit.register(_rendre, intacts)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, lambda *_: sys.exit(130))
        except (ValueError, OSError):   # not the main thread, or not supported
            pass

    survived = []
    for path, before, after, name in MUTATIONS:
        file = ROOT / path
        original = intacts[file]
        if original.count(before) != 1:
            # Two very different causes behind one symptom, and saying which
            # saves the next person an hour: the code moved under the mutation,
            # or a killed run left this file mutated and nobody noticed.
            laisse = after and after in original
            raison = ("a previous run was interrupted and left this file mutated"
                      if laisse else
                      f"pattern not found once (found {original.count(before)})")
            print(f"??    {name}: {raison}")
            survived.append(name)
            continue
        file.write_text(original.replace(before, after), encoding="utf-8")
        try:
            result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p",
                                     "no:warnings", "tests"], cwd=ROOT, capture_output=True)
        finally:
            file.write_text(original, encoding="utf-8")
        # Read it back. A restore that silently failed would poison every
        # mutation after it, and the run would still print a tidy score.
        if file.read_text(encoding="utf-8") != original:
            print(f"\nFAIL  {path} could not be restored. Check it before committing.")
            return 2
        caught = result.returncode != 0
        print(f"{'caught' if caught else 'MISSED'}  {name}")
        if not caught:
            survived.append(name)

    _rendre(intacts)
    print(f"\n{len(MUTATIONS) - len(survived)}/{len(MUTATIONS)} mutations caught")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
