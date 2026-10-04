# Call First: Devpost submission text

Track: **Ring**. Images: `cover.png` (1500×1000, 3:2 thumbnail), `cover-wide.png`
(1280×640, GitHub social preview), `logo.png`, `logo-mark-512.png`.

---

## Tagline (under 60 characters)

> Courier scams end at the front door. So does this.

50 characters.

## Short description (under 255 characters)

> Courier scams end with a courier at an older person's door. Call First turns the
> Ring doorbell already there into a speed bump: a reminder at the chime, the
> family told when the door opens, and every attempt to switch it off told too.

234 characters.

## Long description (under 1,600 characters)

> A courier scam starts on the phone (a grandchild in jail, a federal agent) and
> ends when a courier collects cash or gold at the victim's door. The FBI counted
> 1,737 such pickups, about $186 million, from 2023 to May 2025.
>
> Alerting on strangers fails: the victim expects the courier. Call First watches
> for something else, a visitor nobody declared in advance and the door opening for
> them. Visits and deliveries are declared calmly, beforehand.
>
> When an unexpected visitor rings, the Ring chime says: "Before you hand anything
> over, call your family first, and ask for your family word." If the door opens,
> trusted family members are emailed at once with the doorbell's still image and
> how sure the system is: a door sensor saw it, or only how long the visitor
> stayed. For a week after, they are told as soon as anyone unexpected appears.
>
> Scammers coach victims to switch protection off. Every change that weakens it
> alerts the family, and a pause ends by itself. A fake "delivery" message is
> refused by code reading the text itself; a model may help read it, never decide.
>
> Measured: through an emulator dropping, duplicating and delaying webhooks, 60
> courier visits, every family whose doorbell was seen told, no reminder played
> twice. 261 tests; 48 rules broken on purpose, each caught. The misses are
> published: lose both doorbell webhooks for one visit and nobody is told; a
> neighbour let in is a false alert; without a sensor a quick handover is missed.
>
> No faces recognised, no police called, nothing without the resident's consent.

1,541 characters. Recount after any edit.

---

## Story — le champ « About the project »

Les sept titres ci-dessous sont **exactement** ceux du gabarit Devpost, dans son
ordre. Coller depuis « Inspiration » jusqu'à la fin de la dernière section, en
remontant les `###` en `##`. Rien d'autre ne va dans ce champ : la frise de
construction est entrée dans « How we built it », là où un juré la cherche.

### Inspiration

Courier scams are the one kind of elder fraud that has to come to the house. The
call, the fear and the secrecy all happen at a distance; the handover does not. The
FBI warned about this pattern in 2024 (IC3 PSA240129), and Boston's field office
reported that 98% of the losses were reported by people over 60. A Scottish council
(East Renfrewshire) installs video doorbells in older residents' homes to fight
doorstep scams.
Those doorbells show who is there, and nothing more. We wanted the doorbell to say
something at the one moment it matters.

### What it does

- **An unexpected visitor rings**: not a recurring visit (a carer, Tuesdays 10 to
  12) and not a delivery declared in advance. The chime plays a reminder that points
  to the family's code word, the one code the scammer cannot know.
- **The door opens for them**: the trusted people are emailed at once, with the
  doorbell's still image, a printable report sheet for IC3 and the FTC, and the
  confidence: a contact sensor saw the door open, or, without one, the visitor stayed
  over a minute.
- **The courier comes back**: for seven days the family is told as soon as anyone
  unexpected appears, before the door opens.
- **The resident is talked into switching it off**: pausing, switching off, adding a
  visit or a delivery for today, adding a new "trusted" person: each one is told to
  the family first. A pause ends by itself after 24 hours.

The resident switches it on, chooses who is told, and can delete everything in one
step. Family members see alerts, never the schedule.

### How we built it

Python and FastAPI receive Ring webhooks (`button_press`, `motion_detected` with
`sub_type: human`, `contact_sensor_faulted`, `device_online/offline`), verify
Ring's HMAC signature over the raw body before parsing anything, and reject stale or
replayed deliveries. A rules engine, ordinary tested code, decides everything. The
Partner API plays chime slots and fetches one still image, only when an alert is
sent. Households, alerts and the journal are encrypted at rest in SQLite; access
links are stored as hashes. Pasted delivery messages are read by rules, or
optionally by an OpenAI model (GPT-5.6 Luna) with a single strict function that
can only return fields. Either
way, code validates them against the pasted text. Ring publishes no simulator, so
everything runs against [ring-sandbox](https://github.com/josepha-mayo/ring-sandbox),
an MIT emulator we read in full and pinned by hash in its own virtualenv.

**None of this existed before the hackathon**, and the repository's history is the
evidence rather than a claim:

| | |
|---|---|
| First commit | **19 September 2026** — *"Design, agreed before any code"* |
| Commits | 19 September to 4 October 2026 |
| Written before the hackathon | nothing |

The order is the one we would defend, and it is visible in the log: the design
document was agreed first, then the webhook receiver and the rules engine, then
the measurement scripts, then the pages and an accessibility check — which found
a real defect, a focus ring at 1.88:1 on a page whose readers need 3:1.

### Challenges we ran into

- **No simulator**, and chime audio slots whose provisioning is undocumented. That
  decided a product question: the reminder is a prepared recording, not a
  per-family one. Logged in `FRICTION.md`.
- **Webhooks get lost.** The emulator's chaos mode drops one in ten. A lost "door
  opened" is now recovered by asking the sensor while an unexpected visitor is at
  the door. A lost doorbell press cannot be: 52 to 56 of 60 reminders play, and we
  say so.
- **And the claim we assert had to be narrowed, because a run proved it wrong.**
  "Every family is told" read 59 of 60, and the silent household had seen
  nothing: both its doorbell webhooks were dropped, so only the door opening
  arrived, and a door opening with no visitor known is the resident fetching the
  post. The claim is now **every family whose doorbell was seen**, asserted by
  attributing each dropped delivery to its household through the emulator's
  fault log. Losing one of the two webhooks costs nothing; losing both costs the
  visit, about one in a hundred, and the Partner API offers no way to ask the
  doorbell what it saw.
- **Our own bug under load**: one SQLite connection shared by threads returned
  errors. The chaos run found it; every statement is now serialised.
- **Tests that find leaks**: a test that greps the raw database file found the
  schedule, then e-mail addresses, stored in clear. Both are encrypted now.

### Accomplishments that we're proud of

Every number is measured: a scenario table in both modes, a chaos run at sixty
households, and a mutation run that breaks 48 rules one at a time and checks that
a test fails each time. 261 tests. The false alerts and the misses are published
next to the successes — and so is the claim we had to narrow when a run proved
the wider one wrong.

### What we learned

The hardest part of fraud protection is the victim being on the scammer's side, for
now. A system that the scammer can talk the victim out of is not protection. So
every way to weaken it has to be loud.

And something about testing that we did not expect. 261 tests found none of the
last five defects, because all of them call the API — and all five lived in the
part a person touches: a required form field that made the one refusal this
project exists for unreachable; a question rendered below the fields it was meant
to fill, so the first person to use it filled them by hand and never saw it; the
instruction *"Call Margaret now"* hidden behind the `change` alert a scammer's
next move produces a minute later; a report link in the alert e-mail that needed
a session the phone it arrived on had never had; and an installation with no way
to send e-mail at all, reporting its alerts as delivered.

**The suite proves the rules. Walking the screens proves the product.** Reading
the shot plan aloud, one click at a time, found more in two hours than the suite
had in two days.

### What's next for Call First

A real door-sensor household (Ring's sensors are Early Access), the uninstall
webhook once its payload is documented, and a pilot with a council or a senior
centre that already hands out doorbells.

---

## When it was built — archive, HORS formulaire

The rules ask what was done *during* the hackathon when a project already existed.
Call First did not exist before this one, and the repository's history is the
evidence rather than a claim:

| | |
|---|---|
| First commit | **19 September 2026** — *"Design, agreed before any code"* |
| Commits | 19 September to 4 October 2026 |
| Written before the hackathon | nothing |

The order is visible in the log and it is the order we would defend: the design
document was agreed first, then the webhook receiver and the rules engine, then the
measurement scripts, then the design and the accessibility check — which found a
real defect, a focus ring at 1.88:1 against a page where a keyboard user with low
vision needs 3:1.

The last days went to things that are easy to skip and that we did not:

- the contrast of every colour pair the stylesheet puts on screen, measured rather
  than asserted (`scripts/a11y.py`);
- five page checks that were passing without asserting anything;
- running the suite somewhere other than this laptop;
- and the chaos harness itself, which printed "families told" without checking it.
  It waited a fixed six seconds for deliveries still in flight, so on a loaded
  machine it reported 58 of 60 and exited 0. It now waits until the counts stop
  moving, and exits non-zero if a single family is not told. A harness whose
  central number is not asserted will eventually publish a wrong one.

On 1 and 2 October, four things, each of which started as a defect we found
rather than a feature we planned:

- **The window a delivery notice announces is now read.** It used to be left
  entirely to the resident. Half of that was right: *Tuesday* is hers to
  settle, because a message pasted three days late means the week after and no
  parser knows that. The other half was costing her — *6 October, 2 to 6 PM*
  settles itself, and a form that asks for what it just read is a form people
  stop filling in. What is unambiguous is filled in; what is not is **offered
  as a choice, never resolved**. A window makes a visitor expected, so a day
  guessed wrong is silence on the day it mattered.
- **A rate limiter that could be bypassed and that leaked.** It keyed on the
  first `X-Forwarded-For` entry — the half the caller writes — and pruned only
  the caller. One rotating header defeated the limit and grew the process. Both
  are now mutations in the harness.
- **A mutation harness that could sabotage the repository.** It edits
  production source in place; a run killed between the write and the restore
  left a mutated file in the tree. The first fix was an exit hook and a signal
  handler, and it was proved insufficient the same day: the process was killed
  outright, no handler ran, and `rules.py` kept an `if False:` until the next
  test run tripped over it. Nothing inside a process survives `SIGKILL`, so the
  originals now go **to disk** before a file is touched, and the next run finds
  that directory and puts everything back byte for byte. `--check` answers
  "is my tree clean" in a second, and it took four tries to write a version of
  that check which could actually fail.
- **HSTS and a `Permissions-Policy`** that denies camera, microphone and
  location — a product about a doorbell camera saying, in a header a browser
  enforces, that its own pages reach none of them.

On 3 and 4 October, five more, every one of them found by using the product
rather than by reading it — the list above in *What we learned* is that list.
Each is in `DESIGN.md` with what it cost, what it would have cost a household,
and a test that fails without the fix.

Two of them deserve naming here, because they are the product's own promises:
**a night carer could not be declared** (a window from 22:00 to 06:00 covered no
time at all, so the one visitor who comes while she sleeps was announced every
night), and **an alert addressed to nobody reported itself as delivered** — the
last trusted person leaves, the door keeps working, the chime still plays, and
the list says every alert arrived.

> **NE PAS COLLER CE QUI SUIT DANS LE FORMULAIRE — note de travail.**
>
> À confirmer sur la page Devpost avant de soumettre : la date d'ouverture du
> hackathon. Si elle est antérieure ou égale au 19 septembre 2026, toute la
> frise ci-dessus est dans la fenêtre et la section est simplement le relevé.
> Si elle est postérieure, le tableau reste la réponse honnête, et ce qui a été
> fait dans la fenêtre sont les blocs du 1er au 4 octobre.

---

## Built with

Relevé dans `requirements.txt` et dans les imports, pas de mémoire — ce champ est
une affirmation comme une autre, et `openai` y figurait sans `anthropic` alors que
`reader.py` câble les deux derrière le même contrat.

```
python, fastapi, uvicorn, pydantic, httpx, sqlite, cryptography, pytest,
ring-partner-api, ring-sandbox, openai, anthropic, javascript, html, css
```

Deux choix à défendre si on demande :

- **`pytest` y est**, et ce n'est pas du remplissage : 261 tests et 48 mutations
  sont une partie de l'argument du projet, pas un détail d'outillage.
- **aucun SDK de modèle** : les deux fournisseurs sont appelés en HTTP par
  `httpx`, avec une fonction stricte qui ne peut rendre que des champs. C'est ce
  qui rend la lecture d'un avis de livraison testable sans réseau.

## Two entries, one project

The hackathon carries two mini-challenges of $5,000 each, *AWS Builder* and
*Open Source*. Call First is eligible for the **Ring track and the Open Source
mini-challenge with the same work** — tick both on the form.

**Read on 30 September, and it is not what we assumed.** The Open Source
mini-challenge asks for *"a contribution to an open-source project repository
during the hackathon window, alongside your primary track submission"* — a
contribution **beside** the entry, not the entry made public. Making this
repository public does not, on its own, satisfy it.

There is an obvious and honest route, and it is already half-written. Call First
runs against [ring-sandbox](https://github.com/josepha-mayo/ring-sandbox) (MIT),
because Ring publishes no simulator. `FRICTION.md` records what using it taught
us — the undocumented chime audio slots, the webhook fields the emulator omits.
That is a pull request or an issue to ring-sandbox, written from a week of real
use, and the rules say a pull request need not be merged.

The repository question is therefore separate, and simpler than we thought: the
Ring track accepts a private repository, so going public is a choice about how
the work is judged, not a requirement. Public and MIT is still the better choice
for a project whose whole argument is measurement anyone can rerun.

## Links to fill in at submission

- **Open Source mini-challenge:** https://github.com/josepha-mayo/ring-sandbox/pull/10
  (opened 1 October 2026 against the emulator this project runs on — see
  `ring-sandbox-pr.md`)
- GitHub repository (public at submission, MIT)
- YouTube video (public, under 3 minutes)
- Try it: https://callfirst-bgtj.onrender.com/try (each visitor gets a household and a
  front door to play; free instance, first load after idle takes about a minute)
