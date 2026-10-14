# Le reste du formulaire Devpost — réponses à coller

⚠️ **Les réponses 3 et 5 dérivent de `FRICTION.md`**, qui est la source. Si une
entrée y change, cette page change aussi — c'est une copie nécessaire (le
formulaire veut du texte autonome), pas une seconde vérité.

---

## Open Source Mini Challenge

### Contribution URL

```
https://github.com/josepha-mayo/ring-sandbox/pull/10
```

### Project Repository URL

```
https://github.com/josepha-mayo/ring-sandbox
```

C'est le dépôt du **projet open source auquel on a contribué**, qui est ce que
le mini-challenge demande : *"a contribution to an open-source project
repository during the hackathon window, alongside your primary track
submission"*. Si l'infobulle du champ parle de **ton** dépôt, mets
`https://github.com/Yoh5/callfirst` à la place — mais la lecture naturelle de la
règle est celle du projet contribué, puisque l'URL de ton propre dépôt est déjà
demandée ailleurs dans le formulaire.

### GitHub Username

```
Yoh5
```

### Description of what you did, how it works, and why it matters

```
Ring publishes no simulator for the Partner API, so Call First was built and
measured against ring-sandbox (MIT), a community emulator written by another
entrant. A week of real use against its chaos mode turned up a defect in the
one property a measurement rests on, and the pull request fixes it.

What I did. Chaos.rng() promises in its own docstring that a seed "makes the
fault stream deterministic so chaos runs are reproducible in tests". It does
not hold for a run. inject() and _fire() both end in asyncio.create_task, so
deliveries overlap, and inside deliver() an `await asyncio.sleep(delay)` sat
between two draws from the single rng every delivery shares. Which coroutine
drew next depended on the event loop, so the same seed injected a different
number of faults from one run to the next: seed 7 gave me 8 drops on one run
and 9 on the next, on the same machine.

How it works. Every draw for a delivery is now taken before the first await, so
the stream is consumed in whole per-delivery chunks. The same seed and the same
number of deliveries give the same counts. Which delivery gets dropped still
depends on start order and cannot not: meta.request_id is a fresh uuid4, so a
delivery has no identity that survives a restart. The README now says which of
the two the seed fixes, because I had assumed it was both.

Second change, and it is why I noticed the first: neither call site kept a
handle on the tasks it created, so nothing could tell when the delivery queue
had drained. GET /_sandbox/chaos now reports `pending`, the number still in
flight, so a consumer can poll it to zero instead of sleeping. Holding the
reference also stops a task being garbage-collected mid-flight.

Why it matters. The existing test that looks like it covers this —
test_seeded_fault_streams_are_reproducible — checks that two fresh Chaos.rng()
objects yield the same sequence. That is a property of random.Random, not of
the emulator; nothing covered a run. And the second bug cost me a wrong
published number before I found it: my batch runner slept a fixed six seconds
and hoped, so on a loaded machine the run ended with deliveries still out and
reported 58 of 60 receivers notified, where a longer wait gave 60. A
measurement that moves with the load of the machine is not a measurement.

Three files, +225 / -7, against upstream 0.4.1. Its own 58 tests plus 3 added
all pass; ruff check and ruff format --check are clean. Mergeable, no conflicts.
```

---

## Feedback Question 1 — Which developer tools, APIs, and SDKs did you use and for what?

```
Ring Partner API — the whole product. Webhooks for button_press,
motion_detected with sub_type: human, contact_sensor_faulted and
device_online/offline; chime audio playback to play the reminder at the door;
one still image fetched only when an alert is sent; and the contact sensor's
status endpoint, polled while an unexpected visitor is at the door to recover a
lost "door opened" webhook.

ring-sandbox (MIT, community emulator) — every test and every measurement. Ring
publishes no simulator, so this is what the 261 tests, the scenario table and
the sixty-household chaos run are built on. We read it in full and pinned it by
hash in its own virtualenv.

FastAPI, uvicorn, pydantic — the webhook receiver and the two pages' API. The
signature is verified over the raw body before anything is parsed.

cryptography (Fernet) — households, alerts and the journal are encrypted at
rest; access links are stored as hashes.

SQLite — storage. One file, no server, which is also why a test can grep the
raw database for anything stored in clear.

pytest — 261 tests, plus a mutation harness we wrote ourselves that breaks 48
rules one at a time and checks a test fails for each.

OpenAI and Anthropic HTTP APIs — optional reading of a delivery notice the
resident pastes. No SDK: both are called over httpx with one strict function
that can only return fields, and code validates the result against the pasted
text. A model may read; it decides nothing.

Render — the hosted demo, where each visitor gets their own household and a
front door to play.
```

---

## Feedback Question 2 — For each tool, API, or SDK used in your project, what worked well?

```
Ring Partner API — the event taxonomy is the right granularity, and it is the
single thing that made this product possible without any vision work:
motion_detected with sub_type: human distinguishes a person from a car at the
API level. The HMAC signature over the raw body is unambiguous and cheap to
verify before parsing, which is the correct order and not always how webhook
APIs are designed. Chime playback is one POST and a 204.

ring-sandbox — the best part of the week. Its chaos presets found two real
defects in OUR code that no unit test would have: one SQLite connection shared
between threads returning errors under load, and a measurement harness that
printed "families told" without asserting it. An emulator that can drop,
duplicate and delay deliveries is not a convenience, it is the only way to find
out what your rules do when the network misbehaves.

FastAPI and pydantic — request validation at the boundary meant the rules
engine never sees a malformed payload, and the dependency system made "which
session is this" a single declaration rather than a check repeated in every
route.

SQLite — being a plain file is a feature for a privacy argument: a test opens
the bytes and greps them. That test found the schedule, then e-mail addresses,
stored in clear. Both are encrypted now.

Fernet — the right default for a project that should not be inventing
cryptography.
```

---

## Feedback Question 3 — For each tool, API, or SDK used in your project, what needs work?

```
Ring Partner API, in the order the gaps cost us time. A friction log kept as we
went is in the repository as FRICTION.md.

1. No simulator. The hackathon rules point entrants to one; none is published.
The official starter needs real devices and a Playground token that lasts 30
minutes. We built on a community emulator instead, and at least two others
exist — which is a signal. Fix: an official emulator with a scripted-event
control plane, or a long-lived sandbox account with virtual devices.

2. Chime audio slot provisioning is undocumented. The docs say slots are
visible and read-only and that playback picks one; they do not say how a
partner puts audio into a slot, the format, or the length limit. This decided a
product question for us: per-family recorded messages are not possible, so the
reminder is a prepared recording. Fix: document provisioning (console upload?
per app or per install?) with formats and limits.

3. No signed timestamp header. The signature covers the body, so replay
protection has to come from meta.time and meta.request_id inside it. That
works, but the docs do not say either field is guaranteed, nor how long Ring
retries. Fix: state the retry window, and that request_id is unique per
delivery (or per event across retries).

4. Delivery is undocumented. Nothing says whether webhooks are retried, for how
long, or whether delivery is at-least-once. We measured against 10% drops: a
lost "door opened" is recoverable by polling the sensor, a lost button press is
not. Between four and eight of sixty reminders therefore do not play, and we
publish that.

5. No queryable last ding. This is the one gap with a measurable product cost.
Event history covers camera events; there is no "when did this doorbell last
ring" in device status. If there were, the figure above would be zero. Fix:
expose it.

6. No ordering guarantee is stated. A sensor event can arrive before the press
that preceded it. Our rules handle it and the emulator reproduces it on
purpose. Fix: one sentence in the webhook docs.

7. app_integration_removed is listed as a webhook but its payload is not
documented — which account or device it names. An integration must delete a
household's data on removal, so the payload matters. Until it is documented,
Call First deletes on the resident's request only.

8. Contact sensors are Early Access. They are the one signal that makes "the
door was opened" a fact rather than an inference, so the product has a second,
weaker mode for doorbell-only homes.

ring-sandbox — one defect, and we sent the fix upstream rather than working
around it: a seeded chaos run was not reproducible once deliveries overlapped,
and nothing reported how many were still in flight. See pull request 10.
```

---

## Feedback Question 4 — For each tool, API, or SDK used in your project, how was your onboarding experience?

```
Honest answer: the documentation was good and the onboarding path was not, and
the gap between those two is the whole story.

Reading the Partner API docs, the event model was clear enough to design
against on day one — the design document was agreed before any code, and it
survived contact with the API. What we could not do was run anything. The
starter needs real devices, the Playground token lasts 30 minutes, and the
simulator the rules point to does not exist. Time to first webhook received was
therefore hours, and not against the real API: it was against a community
emulator found by searching.

That is a strange position to be in for a hackathon track about a device.
Everything we measured — 261 tests, a sixty-household chaos run, 48 mutations —
is measured against someone else's emulator, and we say so in the video and in
the README because the alternative is letting a reader assume we had devices.

The rest onboarded in minutes: FastAPI and pydantic are documented by example,
Fernet has one obvious way to use it, SQLite needs nothing, and ring-sandbox
installs with pip and serves a control plane on localhost.

What would have changed the week: a sandbox account with virtual devices and a
token that outlives a coffee break.
```

---

## Feedback Question 5 — Would you build with these devices and services again?

```
Yes, and specifically with Ring rather than a generic camera API. The doorbell
is the right place for this problem — a courier scam is the one kind of elder
fraud that has to come to the house — and the chime is the rarest thing in
consumer hardware: a speaker already installed where the fraud happens, that
belongs to nobody the scammer is talking to. sub_type: human did the work a
model would otherwise have had to do.

Two conditions for doing it again, and both are documentation or access rather
than engineering:

A sandbox that outlives a 30-minute token, so the next person measures against
Ring rather than against a community emulator.

Chime slot provisioning documented, because it is the only thing standing
between a prepared reminder and one recorded in the family's own voice — and a
grandchild's voice saying "call me first" is a better product than anything we
could write.

And one feature request, with a number attached: expose the last ding in device
status. Four to eight of every sixty reminders are lost today because a dropped
button press cannot be recovered, and that endpoint would make it zero.
```

---

## Which AI tools have you leveraged while working on this project?

Trois usages distincts, et le champ gagne à les séparer : un modèle **dans** le
produit, un assistant **pour** l'écrire, une voix **pour** la vidéo. Mélanger
les trois est ce qui fait qu'un juré ne sait plus ce qui décide quoi.

### Réponse à coller

```
Three different things, kept apart on purpose.

1. A model inside the product, with no authority.

callfirst/reader.py sends a pasted delivery notice to one model — OpenAI
(gpt-5.6-luna) if OPENAI_API_KEY is set, otherwise Anthropic
(claude-haiku-4-5) — through a single tool call whose only effect is to
return fields: carrier, tracking number, delivery window, signature.

It proposes. It never decides. deliveries.validate() reads the pasted text
itself and accepts or refuses, and a message about someone coming to collect
is refused whatever the model said. The model has no other tool, no database,
and no way to take an action. The worst a hostile notice can do (OWASP LLM01)
is propose a wrong carrier or a wrong window, and validation reads the
original text, not the model's answer.

It is also optional. With no API key, a timeout, or an answer that is not the
requested shape, it falls back to a rule-based reader and the resident fills
in what is missing. Every test in the suite passes with no key set, so a judge
needs no account to run the whole thing.

2. An AI coding assistant, as the rules allow.

Claude (Claude Code) was used throughout: application code, the 267-test
suite, the mutation harness that breaks 48 rules on purpose, the chaos
harness, the documentation, and the video renderer. Every design decision,
every published figure and the final submission are mine, and I take
responsibility for them.

It also found two defects in this submission that I had not: the landing page
claimed "32 / 32 rules broken on purpose" after sixteen more were added, and
the keep-awake workflow claimed to ping the demo every fourteen minutes when
GitHub was actually running it every three to six hours. Both are fixed, and
the first is now pinned by tests/test_chiffres_publies.py.

3. A synthetic voice for the demo video.

The narration is edge-tts (en-US-AndrewNeural). No human voice is recorded
and none is implied. submission/video/faire_la_video.py speaks each sentence
first, measures the wav, and holds the matching scene for exactly that long,
so picture and sound cannot drift; it refuses to build if the result reaches
three minutes.

What is NOT AI-generated: the doorbell still image in the demo is drawn with
Pillow by scripts/make_demo_still.py — geometry, not a generated image — so
it shows no real person and carries nobody else's copyright. It is marked
ILLUSTRATION on screen. This product recognises no faces and identifies
nobody.
```
