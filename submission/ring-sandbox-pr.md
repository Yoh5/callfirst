# Contribution to ring-sandbox — the Open Source mini-challenge

**Opened on 1 October 2026:**
**https://github.com/josepha-mayo/ring-sandbox/pull/10**

That is the link the Devpost form wants for the Open Source mini-challenge.

Base `main` on the upstream repository, three files, +225 / −7, mergeable with
no conflicts. Upstream `josepha-mayo/ring-sandbox` at 0.4.1; its own 58 tests
plus the 3 added all pass, `ruff check` and `ruff format --check` clean.

The hackathon rules say a pull request need not be merged, so this counts as it
stands. The text below is what was sent, kept for the record.

---

## Title

    Make a seeded chaos run reproducible when deliveries overlap

## Body

`Chaos` says in its own docstring that *"`seed` makes the fault stream
deterministic so chaos runs are reproducible in tests"*. I built a webhook
receiver against the `delivery` preset for a week, ran it at 20 doors at once,
and found that it does not hold for a run.

It is not an obvious break, because the test that looks like it covers this —
`test_seeded_fault_streams_are_reproducible` — checks that two fresh
`Chaos.rng()` objects yield the same sequence. That is a property of
`random.Random`, not of the emulator. Nothing covered a run.

**What happens.** `inject` and `_fire` both end in
`asyncio.create_task(deliver(payload))`, so deliveries overlap. Inside
`deliver()`, `await asyncio.sleep(delay)` sat between two draws from the single
`rng` that every delivery shares. Which coroutine drew next therefore depended
on the event loop's scheduling, and the same seed injected a different number of
faults from one run to the next. Seed 7 gave me 8 drops on one run and 9 on the
next, on the same machine.

**What this changes.** Every draw for a delivery is taken before the first
await, so the stream is consumed in whole per-delivery chunks. *Which* delivery
gets dropped still depends on the order they start in, and it cannot not:
`meta.request_id` is a fresh `uuid4`, so a delivery has no identity that
survives a restart. What is restored is the part a measurement rests on — the
same seed and the same number of deliveries give the same counts. The README now
says which of the two the seed fixes, since I had assumed it was both.

**Second thing, and it is why I noticed the first.** Both call sites kept no
handle on the tasks they created, so there is no way to know when the delivery
queue has drained. With the `delivery` preset a delivery is held up to
`delay_ms + jitter_ms` = 1.8 s, so my batch runner slept a fixed six seconds and
hoped. On a loaded machine that guess is short: the run ended with deliveries
still out and reported 58 of 60 receivers notified, where a longer wait gave 60.
A measurement that moves with the load of the machine is not a measurement.

`GET /_sandbox/chaos` now reports `pending`, the number still in flight, so a
consumer can poll it to zero instead of sleeping. Holding the reference also
stops a task being garbage-collected mid-flight, which is the other reason to
keep it.

**Docs.** Two lines in the README for things I learned the slow way: count
faults from `/_sandbox/chaos` and not from `/_sandbox/state`, which truncates
`delivered` to its last 50 entries and so undercounts silently on any run of
size; and poll `pending` rather than sleeping.

**Tests.** `tests/test_chaos_concurrency.py`, three of them, in the style of
`tests/test_chaos.py`:

- a seeded run is reproducible when deliveries overlap — **this one fails
  without the change**, verified by reintroducing a single `await` between the
  draws;
- the seed still decides something, over three seeds, so a fix that made every
  seed behave alike could not pass quietly;
- `pending` reaches zero only once nothing is in flight.

An earlier version of the first test compared *which* delivery got which fault,
keyed by `request_id`. It could never have passed, for the `uuid4` reason above.
It compares counts now.

**Not verified against the real API.** Per CONTRIBUTING, I should say so
plainly: this is entirely about the emulator's own behaviour under concurrency.
I have no Playground access to confirm anything about real delivery ordering or
retry semantics, and nothing here assumes any.

Thank you for publishing this — Ring ships no simulator, and a whole
integration was testable because you wrote one.
