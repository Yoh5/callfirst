"""Reading *when* out of a carrier's message — and refusing to guess it.

A delivery window is not an ordinary field. Inside one, a visitor is
**expected**, so the reminder does not play and nobody is told. Every other
field is a label that can be corrected after the fact; this one decides whether
the product speaks at all. A window placed on the wrong day produces silence on
the day it mattered, and silence is the one error nobody notices.

So the rule here is narrower than "parse a date":

**Read what is unambiguous. Offer the readings when there is more than one.
Never pick.**

Three kinds of text, three behaviours:

- ``Tuesday 7 October, 2:00 PM to 6:00 PM`` — one reading. Filled in.
- ``Tuesday between 2 and 6 PM`` — which Tuesday? The one coming, or the week
  after? Two readings, and the resident says which. Resolving it by "the
  message must be fresh" assumes she pastes it the day it arrives; she pastes
  it three days later, and the window lands a week away while she believes she
  is covered.
- ``7/10`` — 7 October or 10 July? The product is American-facing and most of
  the world is not. Two readings.

Offering two buttons is not a worse experience than guessing: it is one click
instead of typing a date, and it is the same move the rest of this codebase
makes when a choice is not ours — ask, rather than write the wrong thing into
somebody's protection.

Rule-based on purpose, like ``deliveries.read``. A model may propose; this
proposes too, and ``deliveries.validate`` still decides.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

MOIS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
JOURS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
         "friday": 4, "saturday": 5, "sunday": 6}

#: An hour only counts as a time when it carries a colon or am/pm. Without that
#: a tracking number donates digits: "1Z 999 AA1 0123456784" is full of them.
HEURE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b"
                   r"|\b(\d{1,2}):(\d{2})\b", re.IGNORECASE)

#: *between 2 and 6 PM*, *2:00 PM to 6:00 PM*, *14:00 - 18:00*. One marker
#: for two times is the common case, which is why this is read before
#: `HEURE`: on its own, a bare "2" is not a time at all.
PLAGE = re.compile(
    r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?\s*"
    r"(?:and|to|until|-|\u2013)\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?\b",
    re.IGNORECASE,
)

ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_NOMS = "|".join(sorted(MOIS, key=len, reverse=True))
JOUR_MOIS = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_NOMS})\b", re.IGNORECASE)
MOIS_JOUR = re.compile(rf"\b({_NOMS})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.IGNORECASE)
CHIFFRES = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
JOUR_SEUL = re.compile(r"\b(" + "|".join(JOURS) + r")\b", re.IGNORECASE)

#: Beyond this, `deliveries.validate` refuses the window anyway, so a reading
#: that lands there is not worth offering.
HORIZON = timedelta(days=14)


@dataclass(frozen=True)
class Lecture:
    """One way the text can be read. ``quoi`` is what the resident sees."""

    quoi: str
    debut: datetime
    fin: datetime


@dataclass(frozen=True)
class Quand:
    """What the text settles, and what it leaves open.

    One reading means it was unambiguous: fill the form in. Two or more means
    a question, and ``demande`` is the question to put to the resident. None
    means the text did not say, and the fields stay empty — which is not a
    failure, it is the default this module existed to protect.
    """

    lectures: tuple[Lecture, ...] = ()
    demande: str = ""

    @property
    def certain(self) -> "Lecture | None":
        return self.lectures[0] if len(self.lectures) == 1 else None


def _applique(heure: int, marque: str | None) -> int:
    if not marque:
        return heure
    marque = marque.lower().replace(".", "")
    if marque == "pm" and heure != 12:
        return heure + 12
    if marque == "am" and heure == 12:
        return 0
    return heure


def _heures(texte: str) -> tuple[time, time] | None:
    """The two times of the window, in the order written.

    The range form is read first, because that is how carriers write it and
    because the first hour often carries no marker: *between 2 and 6 PM* has
    one "PM" for two times. It is inherited — and if inheriting it puts the
    start after the end, as in *between 10 and 2 PM*, the start takes the other
    half of the day. That is a rule rather than a guess: a window that ends
    before it begins is not a reading at all.
    """
    plage = PLAGE.search(texte)
    if plage:
        h1, m1, p1, h2, m2, p2 = plage.groups()
        fin = _applique(int(h2), p2)
        debut = _applique(int(h1), p1 or p2)
        if debut > fin and not p1 and p2:
            debut = _applique(int(h1), "am" if p2.lower().startswith("p") else "pm")
        if debut <= 23 and fin <= 23 and debut < fin:
            return time(debut, int(m1 or 0)), time(fin, int(m2 or 0))

    trouves: list[time] = []
    for m in HEURE.finditer(texte):
        if m.group(1) is not None:
            heure = _applique(int(m.group(1)), m.group(3))
            minute = int(m.group(2) or 0)
        else:
            heure, minute = int(m.group(4)), int(m.group(5))
        if heure > 23 or minute > 59:
            continue
        trouves.append(time(heure, minute))
        if len(trouves) == 2:
            return trouves[0], trouves[1]
    return None


def _dans_l_horizon(jour: date, aujourdhui: date) -> bool:
    return aujourdhui <= jour <= aujourdhui + HORIZON


def _jour_dit(valeur: int, mois: int, annee: int) -> date | None:
    try:
        return date(annee, mois, valeur)
    except ValueError:
        return None


def _prochaine(mois: int, jour: int, aujourdhui: date) -> date | None:
    """The next occurrence of a day and month, this year or the next."""
    for annee in (aujourdhui.year, aujourdhui.year + 1):
        quand = _jour_dit(jour, mois, annee)
        if quand and quand >= aujourdhui:
            return quand
    return None


def _candidats(texte: str, aujourdhui: date) -> tuple[list[date], str]:
    """The dates the text can mean, and the question when there are several.

    Ordered by how little they assume: a full date settles it, a bare weekday
    settles nothing.
    """
    iso = ISO.search(texte)
    if iso:
        quand = _jour_dit(int(iso.group(3)), int(iso.group(2)), int(iso.group(1)))
        return ([quand] if quand else []), ""

    for motif, ordre in ((JOUR_MOIS, ("jour", "mois")), (MOIS_JOUR, ("mois", "jour"))):
        trouve = motif.search(texte)
        if trouve:
            a, b = trouve.group(1), trouve.group(2)
            jour, mois = (int(a), MOIS[b.lower()]) if ordre[0] == "jour" \
                else (int(b), MOIS[a.lower()])
            quand = _prochaine(mois, jour, aujourdhui)
            return ([quand] if quand else []), ""

    chiffres = CHIFFRES.search(texte)
    if chiffres:
        a, b = int(chiffres.group(1)), int(chiffres.group(2))
        # Both readings, unless one of them is not a date at all. 25/12 can
        # only be the 25th of December; 7/10 is genuinely two days.
        lectures = []
        for jour, mois in ((a, b), (b, a)):
            quand = _prochaine(mois, jour, aujourdhui) if 1 <= mois <= 12 else None
            if quand and quand not in lectures:
                lectures.append(quand)
        demande = ""
        if len(lectures) > 1:
            demande = (f"The message says {a}/{b}. Day first or month first? "
                       "They are different days.")
        return lectures, demande

    jour = JOUR_SEUL.search(texte)
    if jour:
        vise = JOURS[jour.group(1).lower()]
        avance = (vise - aujourdhui.weekday()) % 7 or 7
        premier = aujourdhui + timedelta(days=avance)
        return ([premier, premier + timedelta(days=7)],
                f"The message says {jour.group(1).capitalize()}. "
                "Which one? A message pasted a few days late means the week after.")

    return [], ""


def lis(texte: str, aujourdhui: date) -> Quand:
    """What the message says about when, as one reading or as a question.

    ``aujourdhui`` is the resident's today, not the server's: a window is read
    against the day she is living.
    """
    heures = _heures(texte)
    if not heures:
        # One time does not make a window, and a duration is exactly the kind
        # of thing this module refuses to invent.
        return Quand()

    debut, fin = heures
    jours, demande = _candidats(texte, aujourdhui)
    lectures = [
        Lecture(
            quoi=f"{quand.strftime('%A %d %B')}, "
                 f"{debut.strftime('%H:%M')} to {fin.strftime('%H:%M')}",
            debut=datetime.combine(quand, debut),
            fin=datetime.combine(quand, fin),
        )
        for quand in jours
        if _dans_l_horizon(quand, aujourdhui)
    ]
    if len(lectures) < 2:
        demande = ""
    return Quand(tuple(lectures), demande)
