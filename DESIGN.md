# Call First — design

*Ring track, Build, Ship, Shape: Amazon Developer Hackathon.
Submission deadline: 23 October 2026, 12:00 PDT.*

This page is agreed before any code is written. Everything below that is a fact
has a source; everything that is a choice says so.

---

## 1. The problem

Courier scams against older people. A scam starts on the phone — a fake
grandchild in trouble, a fake government agent, fake tech support — and ends at
the victim's front door, where a courier collects cash or gold.

- The FBI issued a public warning about exactly this pattern
  ([IC3 PSA240129](https://www.ic3.gov/PSA/2024/PSA240129)).
- From 2023 to May 2025 the FBI documented **at least 1,737 courier pickups
  nationwide, for about $186 million**. In the Boston field office, **98% of
  losses were reported by people over 60**
  ([FBI Boston](https://www.fbi.gov/contact-us/field-offices/boston/news/fbi-boston-warns-of-increase-in-gold-bar-and-bulk-cash-courier-scams)).
- Across all elder fraud, people over 60 lost **$4.8 billion in 2024**, an
  average of **$83,000** each ([AARP, from the FBI IC3 report](https://www.aarp.org/money/scams-fraud/fbi-report-fraud-2024/)).
- Local authorities already install smart doorbells in older people's homes to
  fight scams ([East Renfrewshire Council](https://eastrenfrewshire.gov.uk/article/5794/Installation-of-smart-doorbell-systems-aim-to-protect-residents-from-scams)).
  Those doorbells are passive: they show who is there, nothing more.

**The whole scam happens at a distance except for one moment, and that moment
happens at the door.** That is where a Ring doorbell already is.

## 2. The insight the design rests on

The name is the instruction the whole product exists to deliver, at the one
moment it matters: before you hand anything over, **call first**.

The obvious product — *alert when a stranger comes to the door* — does not work
here, and the reason is the whole point of this project: **the victim is
expecting the courier.** Scammers even give the victim a "code" or "password" to
recognise their courier (FBI Boston, above). To the victim, this is not an
unexpected stranger.

So the signal is not "a stranger". It is: **someone who is neither an expected
visit nor a declared delivery, and the door opens for them.** Expectation is
decided by what the household declared in advance, calmly, not by what the
victim believes in the moment.

## 3. Who uses it, and who decides

- **The resident** — the older person — is the Ring customer. **They switch the
  service on**, choose who is told, and can pause it. It is never set up *on*
  them by their family. This is an ethical condition and also Ring's rule
  (section 9).
- **One or two trusted people** — usually adult children — receive alerts and
  can see the protection state. Their access is revocable in one step.

## 4. What it observes

All from the Ring Partner API. Nothing is inferred from faces.

| Signal | Source | Used for |
|---|---|---|
| Someone rang | webhook `button_press` | a visit has started |
| A person is at the door | webhook `motion_detected` with `sub_type: human` | presence and how long it lasts |
| Door opened / closed | webhooks `contact_sensor_faulted` / `contact_sensor_cleared` (Early Access sensors) | the strong signal, when a sensor exists |
| Device health | webhooks `device_online` / `device_offline`, `GET /v1/devices/{id}/status` | whether an absence of events means anything |
| A still image | `POST /v1/devices/{id}/media/image/download` | evidence, only when an alert is sent |
| Play a sound indoors | `POST /v1/devices/{id}/media/audio/playback` | the reminder |

### Two modes, chosen from what is installed

| | With a door contact sensor | Doorbell only |
|---|---|---|
| "The door was answered" means | the door opened while the visitor was there | the visitor stayed at the door longer than *T* after ringing |
| Confidence | strong — a fact | weaker — they may have waited for nothing |
| Alert wording | "the door was opened for an unexpected visitor" | "an unexpected visitor stayed 2 minutes at the door" |

The system never states what it cannot know. It never says "the door opened"
without a sensor that saw it.

*Choice:* *T* defaults to **60 seconds**, configurable, and the measured
scenarios (section 11) report what that choice costs in false alerts.

## 5. What counts as expected

Declared in advance, by the resident or with them:

- **Expected visits** — recurring windows: *the carer, Tuesdays and Thursdays,
  10:00–12:00*.
- **Expected deliveries** — the resident pastes the carrier's notification. A
  model **extracts** carrier, tracking number, window and whether a signature is
  required. **Code validates** it: a known carrier, a well-formed tracking
  number **that appears word for word in the pasted text** (the model cannot
  invent one), a window within the next 14 days and no longer than 12 hours.
  Inside a declared window a visitor is expected, and so is opening the door to
  them: people take parcels from drivers' hands, and alerting on that would
  teach the family to ignore alerts. A courier cannot know the window. A coached
  resident can be told to declare one, and that is what change alerts are for
  (section 8a).
- A **collection** is never an expected delivery, whatever words it arrives in.
  Nobody legitimate sends a courier to collect cash or gold.

## 6. What the code decides

The model reads notifications and writes plain-language messages. **It decides
nothing.** Every decision below is ordinary, tested code.

```
calm ─(unexpected visitor rings)─▶ reminded ─(door answered)─▶ alerted ─▶ heightened (N days)
  ▲                                   │
  └──────(visitor leaves, door never answered)
```

1. **A visitor rings** and the time is not inside an expected visit or a
   declared delivery window → **play the reminder** indoors (section 7).
2. **The door is answered** for that visitor (section 4, by mode) → **alert the
   trusted people now**, with the still image and the confidence.
3. **After an alert**, the household enters **heightened watch** for *N* days:
   any unexpected visitor alerts the trusted people immediately, without
   waiting for the door. The FBI notes that couriers often come back for a
   second pickup. *Choice:* *N* defaults to 7 days.
4. **Any change to the protection itself** — pausing it, or adding a visit or a
   delivery for today — **tells the trusted people at once** (section 8a). A
   pause ends by itself after 24 hours: protection cannot be switched off
   quietly for good.

## 7. What it does

**The reminder at the door.** A short recorded message, played by the chime
when an unexpected visitor rings:

> *"Before you hand anything over, call your family first, and ask for your
> family word."*

*Decision — prepared, not recorded per family.* The Partner API plays chime
audio only from the app's own slots, and a chime's audio configuration is
read-only to partners
([Partner API](https://developer.amazon.com/docs/ring/api-documentation.html)).
A per-family recording is not something the API allows, so the product does not
pretend to. Two slots, two messages:

| Slot | Plays when | Message |
|---|---|---|
| `ring-appstore-event-1` | an unexpected visitor rings | the reminder above |
| `ring-appstore-event-2` | an unexpected visitor rings during heightened watch | *"Your family has been told someone is at the door. Please call them before you open."* |

The family word itself is never stored and never played. The message only
points to it.

The FBI and FTC advise families to agree a secret word, now that voices can be
cloned ([FTC / FBI guidance](https://www.eyesift.com/blog/ai-voice-cloning-scams-verify-caller/)).
Advice given once is forgotten at the moment it matters. This puts it at the
door, at that moment. The scammer hands the victim a code for the courier; this
reminds them of the one code the scammer cannot know.

It is a one-way recorded message, not an assistant. The equivalent of a note on
the door that speaks at the right time.

**The alert to trusted people.** Immediate, with the still image, the mode and
its confidence, and a plain instruction: *call her now.*

**The report sheet.** After an incident, a sheet with what the door recorded —
date, time, duration, image — ready for the FBI's IC3 and the FTC
([ic3.gov](https://www.ic3.gov), [reportfraud.ftc.gov](https://reportfraud.ftc.gov)).
The family sends it. The system never does.

## 8. Security — the system is a target too

It knows when an older person is alone, who their family is, and whether they
get told. And it faces people who are already manipulating the victim.

| Threat | Mitigation |
|---|---|
| **a) The victim is coached against their own tool** — "turn your alarm off", "add this afternoon's delivery" | Every change to the protection alerts the trusted people at once. Scammers demand secrecy; this breaks it. **During the heightened week after an alert, every declaration is told whatever its date** — see below. |
| **b) Prompt injection through a fake "delivery" notification** (OWASP LLM01) — a crafted SMS that makes the courier look expected | The model only extracts fields. Code validates carrier and tracking format, and refuses anything that reads as a collection. The model's output is never trusted as a decision. |
| **c) Forged or replayed webhooks** — to trigger false alerts, or to hide real ones | Verify Ring's HMAC signature on every webhook; reject stale and replayed events. |
| **d) Exposure of the schedule** — it says when the resident is alone | Encrypted at rest, never shown in an alert, least-privilege Ring scopes, tokens server-side only, family access revocable. |

### The hole threat (a) had, found 2 October

A declared window makes a visitor expected, and `alert` returns before anything
else when a visit is expected. That is right in general: a parcel the resident
is waiting for should not alert her daughter.

But declaring something only told the family when the window was **today or
tomorrow**. Further out it was a silent note. So a delivery declared for day
four of the heightened week was announced to nobody *and* silenced the watch
over its window — in the exact days this design says it watches hardest,
because couriers come back.

It needed no technical attack. Someone whose first attempt raised an alert
knows the family is watching now, and the cheapest counter is a sentence:
*"declare the delivery so it doesn't bother your daughter."* That is threat (a)
exactly, arriving through the one door threat (a) did not cover.

The answer is this design's existing rule rather than a new one. Refusing the
declaration would decide for the resident, which nothing else here does.
**During the heightened week, every declaration tells the family, whatever its
date, and says it is during that week** — because "a delivery was declared" and
"a delivery was declared in the week after an alert" do not call for the same
telephone call.

### A protection with nobody on the other end, found 2 October

The resident names the trusted people, and a trusted person can stop receiving
alerts — the others are told, and the one leaving is told too, because the
recipients are computed before the removal. That is sound while there are
others.

**The last one can leave.** After that the protection is still switched on, the
chime still plays the reminder, alerts are still raised — and every one of them
is addressed to nobody. The house is protected in name only, and nothing said
so.

It takes no attacker, which is why it was worth looking for. A daughter changes
her address, unsubscribes from the wrong thing, or simply stops. Nobody is
being manipulated and nobody is lied to; the product simply stops being able to
do the one thing it exists for, quietly.

Same answer as everywhere else here: it is said, not decided. The alert that
empties the list says what it empties, and the resident's own page carries it
as a standing fact beside "the doorbell is offline" — because they are the same
kind of fact. The system is running and cannot do its job.

### An alert that reached nobody, found 2 October

This whole product reduces to one sentence: when the door opens for someone
unexpected, **somebody is told**. The chime, the declared windows, the
heightened week — all of it exists to decide whether to send that message.

A send can fail. The journal recorded `alert email FAILED`, which is correct
and is where that line belongs. But nobody reads the journal. The alert sat in
the resident's list looking exactly like one that arrived, and she was told her
daughter had been told.

Writing a failure where nobody reads it is a half-step: it clears the engineer
and leaves the person exactly where they were. The alert now carries whether it
reached anyone and who it missed, both pages show it, and it stays on the
record — somebody will ask, six months later, who was told about that visit,
and a notification that scrolled away does not answer.

### The night carer could not be declared, found 2 October

Expected visits are recurring local-time windows: the carer, Tuesdays
10:00–12:00. The endpoint refused any window whose end was not after its start,
with `invalid window`, and `covers` read the window as `start <= t < end`.

Both are right for a daytime window and wrong for the one that matters most
here. An older person with a **night carer** — 22:00 to 06:00, the one visitor
who comes while she is asleep — had no way to declare her. The chime announced
that carer every night, and the message said only "invalid window": not why,
not what to do instead.

Nobody is endangered by that, and that is the trap. She is worn down, and the
way being worn down ends is the protection switched off — threat (a) reached
with no scammer in it.

A window that ends before it starts is simply one that runs past midnight, so
it is supported rather than refused, and the weekday is the day the window
**opens**: a Tuesday night carer is still the Tuesday visit at one on
Wednesday. A window of zero length is still refused — it expects nobody, and
accepting it would only look like it worked.

## 9. Ring's content policy, point by point

From the [Ring Appstore Permitted Content Policy](https://developer.amazon.com/docs/ring/content-policy.html):

| Ring requires | Here |
|---|---|
| No third-party access without the customer's explicit knowledge and consent | The resident names the trusted people and can revoke them |
| Collect only the data the features need | Events and timings; one still image, only when an alert is sent |
| An easy way to delete stored data | One action deletes everything held for the household |
| A privacy policy covering collection, use, sharing, retention | Written and served at [/privacy](https://callfirst-bgtj.onrender.com/privacy): who decides, what is collected and why, what is never done, who sees what, how it is kept, how long |
| No identifying strangers, no tracking individuals | No face recognition, no appearance matching between images |

Ring is currently facing a class action over its own facial recognition
([The Register](https://www.theregister.com/personal-tech/2026/06/03/ring-faces-class-action-over-facial-recognition-feature/5250661)).
Not identifying anyone is a design choice here, not an omission.

### The claim that was one word too wide, found 2 October

The README said "families told: 60 / 60, does not vary". Re-measuring at sixty
households before filming, it read **59 of 60**, and the harness was right to
exit non-zero: this is the one number the whole product is.

The named household had seen nothing at all — `reminders 0, alerts change`.
Both of its doorbell webhooks had been dropped, the motion and the press, so
all that ever arrived was the door opening, and `_door_opened` returns at once
when no visit is in progress. That is deliberate and it has to stay: a door
that opens with nobody at it is the resident fetching the post, letting the cat
in, going out to the bins. Alerting on every one of those is how a protection
gets switched off, and then it protects nobody.

So the defect was in the sentence, not the code. The claim is now **every
family whose doorbell was seen**, and the harness proves it rather than
asserting it: each dropped delivery is attributed to its household through the
emulator's own fault log (the inject endpoint returns the `request_id` it
built), so a run distinguishes "a rule declined to fire" — a failure — from "we
never knew anyone was there" — a published limit. Four tests fix the boundary:
losing **one** of the two webhooks costs nothing, losing both costs the visit,
about one in a hundred at a drop rate of one in ten. It is not recoverable: the
Partner API has `sensor_open` for the contact sensor and nothing that asks the
doorbell what it saw a minute ago. That is the first item of product feedback.

Two harness defects came out of the same hour. The drain condition — wait until
the counts stop changing — was right at twenty households and too eager at
sixty, where two quiet seconds is a lull rather than an empty queue; it now
wants three, and waits a minute. And the client timeout of ten seconds was the
harness's own bottleneck, sixty threads asking a single-process emulator to
accept an event. Neither was the product. Both would have published a wrong
number, which is exactly how the first one got written.

### The refusal that could not be reached, found 2 October

Walking the shot plan before filming: paste the fake notice — *UPS … Federal
agent will come for safekeeping of your gold bars* — press **Read it**, then
**This is right — add it**, and read the refusal on screen.

The refusal never arrived. `validate` runs when a delivery is *added*, and the
form's *Arrives from* and *Until* fields are `required`. A collection message
carries no window, so the browser blocked the submission with "please fill out
this field", and the product never got to speak. To reach the one sentence this
whole project is about — *nobody legitimate collects from a home* — the resident
would have had to **invent a delivery window for a message that has none**.

Three hundred tests and a mutation catalogue did not find it, because every one
of them calls the API. The browser's own validation sits in front of the only
path a person actually takes, and nothing in the suite goes through it. It took
reading the shot plan out loud, one click at a time.

So the reading says it at once and offers nothing to correct: there is no
version of that message which becomes acceptable once a date is typed in. The
collection words live in one function, `collecte()`, called at the reading and
inside `validate` — two lists of the same words drift, and this one decides
whether a courier gets announced in advance. Five tests, including the one that
says why the earlier arrangement could not work (a collection message has no
window, so refusing cannot depend on the add step) and the one that says the
page is not the guard (a direct API call with a window invented by hand is
still refused).

### "Les boutons de quoi ?", found 2 October

The reading offers two days when a notice says *Tuesday* and nothing more, and
the page puts them one click away. The first person to use it asked which
buttons I was talking about. He had filled *Arrives from* and *Until* by hand,
and the declaration email proves it: *a UPS delivery was declared for Friday
2:00 PM*, from a message that said Tuesday.

Nothing was broken. The endpoint returned both readings, the markup was valid,
the suite was green. The choice rendered into `#d-result`, which sits **below**
the form — so the fields it was meant to fill came first, got filled by hand,
and the question was never seen. The feature worked and was invisible.

That is the third time today in a different costume: the alert whose failure
went to a journal nobody reads, the refusal behind a form the browser would not
submit, and now a question printed under its own answer. **Information without
its taker is not information.** Here the cost is specific: a window guessed
wrong is silence on the day it mattered, and silence is the one error nobody
notices.

The question now renders above the form, in its own container, cleared on every
read. Four tests pin what can be pinned without a browser: the container comes
before the form in the document, the readings render into it, the collection
refusal stays below (it has nothing to fill), and both containers are
`aria-live` — this product's readers do not see small print.

### Three refusals that made the reader deduce, found 2–3 October

Auditing the path a person takes, rather than the one the tests take, because
that is where the last two findings came from. Three in a row, all the same
shape:

**A refusal naming two causes names neither.** Adding a trusted person answered
*"already trusted, or three people already"* for both of its refusals. The two
call for opposite actions — nothing to do, or remove someone first. They are
two messages now.

**A visit was removed by its position.** The page re-reads the list every
twenty seconds; a list that shifted between the render and the click deleted
whatever had moved into that slot, and the page then said *"Carer was removed"*
using the label from its own stale view. For a night carer that means the chime
announces her every night from then on. The button now says what it believes it
is removing — the label and both times, already on screen — and a mismatch is
refused with *"this list changed since the page was drawn"*.

**And an installation with no way to send, reporting alerts as delivered.**
Trying the hosted demo to answer whether *Try it* works — it does, end to end:
chime, alert, confidence, still image, report sheet. But without `SMTP_HOST`
the service falls back to `FileMailer`, which writes `.eml` files into its own
data directory and returns `True`. Right for `scripts/demo.py`, where that
folder *is* the mailbox. Wrong anywhere deployed: the flag added the day before,
whose whole purpose is that an alert reaching nobody must not look like one that
arrived, said nothing about a send that was never possible. It is now the third
standing fact on the resident's page, beside the doorbell being offline and
nobody being on the list — and the hosted demo is exempt, because its address is
`@example.invalid` by design so no stranger is ever mailed.

### What the suite cannot see, and what I did to my own harness

Two hundred and forty-one tests reach none of the three. They call the API; the
browser's required fields, the twenty-second refresh and the deployment's
configuration all sit outside it. Reading the shot plan aloud, one click at a
time, found more in two hours than the suite has in two days. That is not an
argument against the suite — it is where to look next.

And a mistake of my own, twice in one hour: I edited `app.py` and then ran the
whole suite **while the mutation harness was running**. The edit was silently
reverted when the harness restored its snapshot, and the test run tripped over a
live mutation and reported a failure that was not real — the rate limiter was
`if False:` at that moment. Both are exactly what the README warns about in its
own words: *nothing else may run against the working copy while it does*. The
warning was mine and I did not follow it. There is nothing to fix in the code.

## 10. What it deliberately does not do

- **Detect an absence of routine.** A different problem, and another entrant's
  project covers it.
- **Recognise faces.**
- **Contact the police.** False alerts exist; the decision belongs to people.
- **Claim to stop scams.** It is a speed bump and a family circuit breaker. A
  well-coached victim can ignore a reminder.

## 11. Measured scenarios

Run against the emulator, in both modes, with the outcome counted — not
demonstrated once.

| Scenario | Expected outcome |
|---|---|
| Courier pickup: rings, door opens, short exchange, leaves | reminder, then alert |
| Carer inside their declared window | nothing |
| Signature delivery inside its declared window | nothing |
| Unannounced parcel drop, door never opened | reminder only |
| Neighbour drops by unannounced, door opens | reminder, then alert — a false alert, counted |
| Courier returns two days after an alert | immediate alert (heightened watch) |
| Protection paused during the day | change alert to family |
| Pasted "delivery" that is really a collection | refused as expected; courier still treated as unexpected |
| Forged webhook without a valid signature | rejected, logged |
| Doorbell offline during a visit | report says the door could not see, instead of reporting nothing |

The false alerts are part of the result, not hidden from it.

## 12. Architecture

- **Python, FastAPI** — webhook receiver, rules engine, API for the pages.
- **SQLite** — households, schedules (encrypted), events, alerts.
- **A small web front** — the resident's consent and settings, the family's
  view, the report sheet.
- **Emulator** — [ring-sandbox](https://github.com/josepha-mayo/ring-sandbox)
  (MIT), read before use, **pinned** to `0.1.0` by hash, installed in **its own
  virtualenv** (it registers a pytest plugin that would load into every test run
  in a shared environment). [ring-partner-sim](https://github.com/jagritvats/ring-partner-sim)
  is a fallback.
- **Alerts** — email for the demo. SMS costs money and adds nothing to the
  argument.

## 13. The three-minute video

1. **The moment.** A courier at an older person's door, on camera. The
   narration gives the FBI's numbers.
2. **Why "alert on strangers" fails.** She is expecting him.
3. **The run.** Rings → the reminder plays indoors → the door opens → the
   family's phone lights up, with the image.
4. **The same run without a sensor.** The wording changes. It does not claim what
   it cannot see.
5. **The tool turned against her.** "Pause your alarm" → the family is told.
6. **The numbers.** The scenario table, false alerts included.
7. **What it will not do**, and where the code is.

## 14. Rules checklist

- [ ] Built after 31 August 2026 — the repository starts on 20 September
- [ ] Uses the Ring Partner API through a simulator — ring-sandbox, credited
- [ ] Video under three minutes, public on YouTube
- [ ] Repository with an open-source licence and run instructions — **private
      until submission**, then public
- [ ] Friction log for the bonus (up to 10%): Ring promises a simulator in the
      rules and ships none; the official starter needs real devices; three
      entrants wrote their own emulators
- [ ] Privacy policy (section 9)

## 15. Plan

| Week | Work |
|---|---|
| 22–28 Sep | emulator set up; webhook receiver with signature checks; rules engine |
| 29 Sep – 5 Oct | chime reminder; expected visits and deliveries; family alerts |
| 6–12 Oct | security mitigations a–d; measured scenarios |
| 13–19 Oct | resident and family pages; report sheet |
| 20–23 Oct | video, README, friction log, submission, slack |

## 16. Decisions

Taken on 19 September 2026, before code.

- **Name: Call First.** It is the advice, not a metaphor. *Threshold* was the
  working name.
- **The reminder's audio: prepared.** Imposed by the API (section 7), and it
  also keeps the family word out of every system.
- **Delivery notifications: pasted only.** Forwarding by email would add an
  inbound mail server — more attack surface for threat (b) — and nothing to the
  demonstration. Pasting keeps the model's only input one visible piece of text.
- **Reading notifications without a model works too.** A rule-based reader
  handles the common carriers; the model is for the messy cases. Either way the
  same code validates the result, so the tests do not depend on a model.
