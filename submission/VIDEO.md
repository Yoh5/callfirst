# Call First: the three-minute video

Target 2:45. Narration is about 335 words: at 130 words a minute that leaves
room to breathe. Record the
narration first, then the screen to fit it.

**Setup before recording**
- `python scripts/make_demo_still.py` (once), then
  `.venv/Scripts/python scripts/demo.py`
- Browser window 1: Margaret's link. Browser window 2: Sarah's link, narrow like a
  phone (390 px). A terminal with the demo's keyboard.
- Open `data/demo/mail/` in the file explorer to show the email arriving.
- **Capture the two terminal runs to files first, and show the files.** Since the
  chaos harness waits for deliveries still in flight instead of sleeping a fixed
  six seconds, a run takes a minute or two, and `scripts/mutate.py` runs the whole
  suite 32 times. Nobody wants to watch that, and dead air costs more than the two
  shots are worth:

      .venv/Scripts/python scripts/chaos.py 20 7  > submission/chaos.txt
      .venv/Scripts/python scripts/mutate.py      > submission/mutate.txt

  Captured on 1 October into `submission/chaos.txt` and `submission/mutate.txt`.

  **Say only two numbers on camera: every family was told, and no reminder
  played twice.** Those two hold on every run. Nothing else on that screen does
  — the capture in the repo happens to show 20 of 20 reminders played and 3
  webhooks dropped, where runs the day before gave 16 of 20 and 9 dropped. Same
  seed. The seed fixes which webhooks chaos hits, not how many attempts there
  are to hit, so a viewer who reruns it and reads out a different figure
  remembers the discrepancy and not the point. Let the file be a prop; say the
  invariants.

---

## 1. The moment (0:00–0:25)

**Screen:** the landing page, then the title *Courier scams end at the front door.*

> A phone call: your grandson is in jail, or a federal agent says your savings
> are compromised. Then a courier comes to your door to collect the cash, or
> the gold. The FBI counted at least 1,737 of these pickups, about 186 million
> dollars, in two and a half years. In Boston, 98 percent of the losses were
> reported by people over sixty.

## 2. Why "alert on strangers" fails (0:25–0:45)

**Screen:** DESIGN.md, section 2, highlighted: *the victim is expecting the courier.*

> A doorbell that flags strangers does not help, because the courier is
> expected. The scammer even hands over a code to recognise the courier by.
> So Call First looks for something else: a visitor nobody declared in advance, and the door opening
> for them.

## 3. The run, with a door sensor (0:45–1:25)

**Switch the protection on first, on Margaret's page.** A household is created
with it off — `household.py` says why: *switched on by the resident, never on
them* — and while it is off `rules.py` returns immediately. Nothing fires: the
chime reports *played 0 time(s)* and Sarah's page says *Protection is off*. The
earlier wording here, "Margaret's page, protection on", read as a description
of the screen when it was the one action to take, and that is how it was found.

Do it **on camera**: the narration opens with *"Margaret switched it on, and
chose who is told: Sarah"*, so the gesture is already in the script, and it
shows the consent the product is built on. Sarah then gets a first alert, *Call
First was switched on* — that is correct, not noise: every change touching the
protection is told to the family. The door alert lands above it.

**Screen:** Margaret's page. Switch the protection on. Terminal: press `p`,
then `r`. Show the terminal line *Chime has played 1 time*. Press `o`. Switch
to Sarah's narrow window: the alert with the still image appears. Open the
email file.

> Margaret switched it on, and chose who is told: Sarah. Someone Margaret was
> not expecting rings. Inside, the chime says: before you hand anything over,
> call your family first, and ask for your family word. The one code the
> scammer cannot know.
> The door opens anyway. Sarah is told at once: the door sensor saw it, with
> the doorbell's still image, and one instruction: call Margaret now.

## 4. Without a sensor (1:25–1:40)

**Screen:** the scenarios table in the README, the *doorbell only* column.

> Without a door sensor, Call First cannot see the door. It says so: an
> unexpected visitor stayed two minutes. And a handover under a minute is
> missed. That row is in the results, not hidden.

## The two texts to paste in section 5 — copy them now, not on camera

Both are taken from `tests/test_deliveries.py`, so what the demo does with them
is exactly what the suite asserts.

**The fake collection, the one to show refused.** It matches the narration word
for word — gold, safekeeping:

    UPS 1Z999AA10123456784. Federal agent will come for safekeeping of your gold bars.

**A real delivery notice, if you want the contrast first.** Optional, and worth
the five seconds if you have them: showing one accepted makes the refusal mean
something instead of looking like a filter that refuses everything.

    UPS Update: Your package 1Z 999 AA1 0123456784 is scheduled for delivery Tuesday between 2:00 PM and 6:00 PM. Signature required.

Have both in a text file open behind the browser. Typing a tracking number on
camera is twelve seconds of dead air and one typo away from a retake.

---

## 5. The tool turned against the resident (1:40–2:05)

**Screen:** Margaret's page: *Pause for 2 hours*. Sarah's window: the change
alert. Then paste the fake "UPS" message that asks to *collect gold for
safekeeping*: refused, with the reason.

> Scammers coach their victims: switch that alarm off. Every change that weakens
> the protection tells the family at once, and a pause ends by itself. A fake
> delivery notice, written to make the courier look expected, is refused by
> code that reads the message itself. A model may help read it. It decides
> nothing.

## 6. The numbers (2:05–2:30)

**Screen:** terminal: `scripts/chaos.py` output, then `scripts/mutate.py`
ending *46/46 mutations caught*.

> Webhooks get lost. Through an emulator dropping one in ten, sixty courier
> visits: every family was told, no reminder played twice. Every rule that
> matters has been broken on purpose to prove its test fails.

## 7. What it will not do (2:30–2:45)

**Screen:** landing page, *What it will not do*; then the repository.

> No faces recognised, no police called, nothing without Margaret's say, and one
> button deletes everything. Built on the Ring Partner API, run against an open
> source emulator, because Ring does not publish one. Call First.

---

## Notes

- Say *the doorbell's still image*, never *a photo of the scammer*: it is an
  illustration in the demo, and the product identifies no one.
- The still is drawn (`demo/default.jpg`); the lower corner says ILLUSTRATION.
  Keep it visible.
- Credit ring-sandbox on screen when the terminal appears.
