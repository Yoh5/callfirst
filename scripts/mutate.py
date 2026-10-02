"""Break each rule that matters on purpose; a test must fail every time.

    .venv/Scripts/python scripts/mutate.py

**This edits the source tree in place**, so nothing else may run against the
working copy while it does — a test suite started alongside reads half-mutated
files and fails for reasons that have nothing to do with it.

And because it edits production source, it has to survive its own death. A
mutation left behind is a sabotaged file sitting in the working tree waiting to
be committed — a worse outcome than any bug this script was written to find.

The first attempt at that was an exit hook and a signal handler. **It was not
enough, and it was proved not enough the same day**: the process was killed
outright, no handler ran, and `rules.py` kept an `if False:` until the next test
run tripped over it. Nothing in the process can be relied on, because `SIGKILL`
reaches no code.

So the originals go **to disk** first, under `.mutate-restore/`, before a single
file is touched. That directory surviving is the signal: the next run finds it,
puts every file back, and says so before doing anything else. The exit hook and
the signal handler are kept — they make the common cases tidy — but the
guarantee lives in the filesystem, which is the only thing that outlives the
process.

Nothing else may run against the working copy while this does.
"""
from __future__ import annotations

import atexit
import shutil
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MUTATIONS = [
    # A window whose end precedes its start runs past midnight -- the night
    # carer, the one visitor who comes while she is asleep. Reading it as
    # start <= t < end covers nothing, so the chime announces her carer every
    # night and the way that ends is the protection switched off.
    ("callfirst/household.py", "        if heure >= debut:", "        if False:",
     "a night window covers nothing"),
    # The whole product reduces to: when the door opens for someone
    # unexpected, somebody is told. A send can fail, and the journal recorded
    # it -- where nobody reads. The alert sat in her list looking exactly like
    # one that arrived, and she was told her daughter was told.
    ("callfirst/app.py", "                store.mark_delivered(h.id, sent_id, manques or [])",
     "                pass", "an alert that reached nobody looks delivered"),
    # The last trusted person can leave. After that the protection is still on,
    # the reminder still plays, and every alert is addressed to nobody. Not an
    # attack -- a daughter changes her address -- and nothing said the alarm
    # was now wired to nothing.
    ("callfirst/app.py", '            "nobody_listening": not h.trusted,', '',
     "a protection with nobody on the other end"),
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
    # Recipients are computed before the removal, so the person leaving is
    # told too. Swapping the two lines takes that away, silently.
    ("callfirst/rules.py",
     "    alert = _change(h, now, texte)\n    h.trusted = [t for t in h.trusted if t.email != email]",
     "    h.trusted = [t for t in h.trusted if t.email != email]\n    alert = _change(h, now, texte)",
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


JOURNAL = ROOT / ".mutate-restore"


def _rendre(intacts: dict[Path, bytes]) -> None:
    """Put every file back as it was found, byte for byte.

    Bytes rather than text throughout, because a restore must not interpret
    anything. Reading as text normalises line endings and writing them back
    depends on the platform: on Windows the round trip happened to come out
    right, which is not a property to rely on. A restore that rewrites every
    line ending turns one changed function into a whole file changed, and the
    diff that was supposed to show the bug shows nothing but noise.
    """
    for file, original in intacts.items():
        try:
            if file.read_bytes() != original:
                file.write_bytes(original)
        except OSError:
            pass


def _repartir_de_zero() -> bool:
    """Undo whatever a previous run was killed in the middle of.

    The directory existing at all means a run started and did not finish on
    its own terms. Restoring from it is unconditional: the alternative is a
    sabotaged file that nothing will mention again.
    """
    if not JOURNAL.is_dir():
        return False
    remis = []
    for sauvegarde in sorted(JOURNAL.glob("*.bak")):
        cible = ROOT / sauvegarde.stem.replace("__", "/")
        original = sauvegarde.read_bytes()
        if cible.exists() and cible.read_bytes() != original:
            cible.write_bytes(original)
            remis.append(str(cible.relative_to(ROOT)))
    print("A previous run was killed before it could put things back."
          + (f" Restored: {', '.join(remis)}." if remis else " Nothing had changed."))
    shutil.rmtree(JOURNAL, ignore_errors=True)
    return True


def main() -> int:
    _repartir_de_zero()

    fichiers = {ROOT / path for path, *_ in MUTATIONS}
    intacts = {f: f.read_bytes() for f in fichiers}

    # To disk before anything is touched. A handler cannot run after SIGKILL;
    # a file on disk does not need to.
    JOURNAL.mkdir(exist_ok=True)
    for file, original in intacts.items():
        nom = str(file.relative_to(ROOT)).replace("\\", "/").replace("/", "__")
        (JOURNAL / f"{nom}.bak").write_bytes(original)

    # Every pattern, checked before a single file is touched. A pattern that
    # has drifted costs fifteen minutes to discover otherwise — the run has to
    # reach it — and that happened twice in one day: once because a refactor
    # moved the code under the mutation, once because a change here stopped
    # normalising line endings. Both were silent until the end. One second now
    # beats a quarter of an hour then, and the score at the end is about the
    # tests rather than about the catalogue.
    derive = []
    for path, before, after, name in MUTATIONS:
        texte = intacts[ROOT / path].decode("utf-8").replace("\r\n", "\n")
        if texte.count(before) != 1:
            laisse = after and after in texte
            derive.append(f"  {name} ({path}): " + (
                "a previous run left this file mutated" if laisse
                else f"found {texte.count(before)} times, expected 1"))
    if derive:
        print("These mutations no longer match the code they were written for:")
        print("\n".join(derive))
        print("\nNothing was run. Point them at the code as it is now, or drop them:")
        print("a mutation that matches nothing proves nothing, and a catalogue")
        print("that quietly shrinks is the failure this script exists to prevent.")
        shutil.rmtree(JOURNAL, ignore_errors=True)
        return 2

    # The tidy paths, for the cases where code does get to run.
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
        # Two views of the same file, and they do different jobs. `texte` is
        # normalised to "\n" so a pattern written with "\n" matches a file
        # saved with CRLF — eight patterns stopped matching the moment this
        # read bytes instead of text, and the harness said so rather than
        # counting them caught. `original` stays the untouched bytes, because
        # that is what gets written back.
        crlf = b"\r\n" in original
        texte = original.decode("utf-8").replace("\r\n", "\n")
        if texte.count(before) != 1:
            # Two very different causes behind one symptom, and saying which
            # saves the next person an hour: the code moved under the mutation,
            # or a killed run left this file mutated and nobody noticed.
            laisse = after and after in texte
            raison = ("a previous run was interrupted and left this file mutated"
                      if laisse else
                      f"pattern not found once (found {texte.count(before)})")
            print(f"??    {name}: {raison}")
            survived.append(name)
            continue
        mute = texte.replace(before, after)
        file.write_bytes((mute.replace("\n", "\r\n") if crlf else mute).encode("utf-8"))
        try:
            result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", "-p",
                                     "no:warnings", "tests"], cwd=ROOT, capture_output=True)
        finally:
            file.write_bytes(original)
        # Read it back. A restore that silently failed would poison every
        # mutation after it, and the run would still print a tidy score.
        if file.read_bytes() != original:
            print(f"\nFAIL  {path} could not be restored. Check it before committing.")
            return 2
        caught = result.returncode != 0
        print(f"{'caught' if caught else 'MISSED'}  {name}")
        if not caught:
            survived.append(name)

    _rendre(intacts)
    shutil.rmtree(JOURNAL, ignore_errors=True)
    print(f"\n{len(MUTATIONS) - len(survived)}/{len(MUTATIONS)} mutations caught")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
