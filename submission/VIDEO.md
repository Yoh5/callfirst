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

**Screen:** Margaret's page, protection on. Terminal: press `p`, then `r`.
Show the terminal line *Chime has played 1 time*. Press `o`. Switch to Sarah's
narrow window: the alert with the still image appears. Open the email file.

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
ending *29/29 mutations caught*.

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
