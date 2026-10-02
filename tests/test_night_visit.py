"""A visit that crosses midnight — the night carer.

`ExpectedVisit.covers` asked `start <= t < end`. For 22:00 to 06:00 no time
satisfies both, so the window covered nothing, and `_length` returned minus
sixteen hours. The form accepted it: the field pattern checks that "22:00"
looks like a time, not that the end follows the start.

The endpoint did not accept it either: it answered 422 "invalid window" and
stopped there. (A first reading of this said the form accepted it silently —
that was inferred from the field pattern without reading the endpoint, and it
was wrong. The refusal is explicit.)

Which leaves the real defect, and it is plain enough: **an older person with a
night carer cannot declare her.** The one visitor who comes while she is asleep
is the one the product has no way to expect, so the chime announces her every
night, and the message says only "invalid window" — not why, not what to do
instead.

So the window is supported rather than refused. A night carer is not an edge
case for this population; a window that ends before it starts is simply one
that runs past midnight.
"""

from datetime import datetime, timedelta

from .conftest import DOORBELL, SENSOR, T0
from .test_app import world  # noqa: F401  — le monde de test vit là-bas


def declare_la_nuit(world, debut="22:00", fin="06:00"):
    return world.resident.post("/api/resident/visits", json={
        "label": "night carer", "weekdays": [0, 1, 2, 3, 4, 5, 6],
        "start": debut, "end": fin})


# ── La fenêtre couvre ce qu'elle doit couvrir ───────────────────────────

def test_une_fenetre_de_nuit_couvre_avant_minuit():
    from callfirst.household import ExpectedVisit
    from zoneinfo import ZoneInfo

    nuit = ExpectedVisit(label="night", weekdays=list(range(7)), start="22:00", end="06:00")

    assert nuit.covers(datetime(2026, 10, 2, 23, 30, tzinfo=ZoneInfo("America/New_York")))


def test_et_apres_minuit():
    from callfirst.household import ExpectedVisit
    from zoneinfo import ZoneInfo

    nuit = ExpectedVisit(label="night", weekdays=list(range(7)), start="22:00", end="06:00")

    assert nuit.covers(datetime(2026, 10, 3, 2, 15, tzinfo=ZoneInfo("America/New_York")))


def test_et_pas_en_plein_apres_midi():
    """La réciproque, sinon « ça couvre » voudrait dire « ça couvre tout »."""
    from callfirst.household import ExpectedVisit
    from zoneinfo import ZoneInfo

    nuit = ExpectedVisit(label="night", weekdays=list(range(7)), start="22:00", end="06:00")

    assert not nuit.covers(datetime(2026, 10, 2, 15, 0, tzinfo=ZoneInfo("America/New_York")))


def test_une_fenetre_ordinaire_est_inchangee():
    from callfirst.household import ExpectedVisit
    from zoneinfo import ZoneInfo

    jour = ExpectedVisit(label="carer", weekdays=[4], start="10:00", end="12:00")
    ny = ZoneInfo("America/New_York")

    assert jour.covers(datetime(2026, 10, 2, 11, 0, tzinfo=ny))
    assert not jour.covers(datetime(2026, 10, 2, 13, 0, tzinfo=ny))
    assert not jour.covers(datetime(2026, 10, 2, 9, 0, tzinfo=ny))


def test_la_duree_d_une_nuit_est_positive():
    from callfirst.household import ExpectedVisit
    from callfirst.rules import _length

    nuit = ExpectedVisit(label="night", weekdays=[1], start="22:00", end="06:00")

    assert _length(nuit) == timedelta(hours=8)


# ── Et de bout en bout ──────────────────────────────────────────────────

def test_la_garde_de_nuit_ne_declenche_pas_le_rappel(world):
    """Le point entier : elle a déclaré sa garde, le produit doit se taire."""
    assert declare_la_nuit(world).status_code == 200

    # `world.send` repositionne l'horloge à T0 + N SECONDES : régler
    # `clock.now` avant ne sert à rien, il est écrasé. Huit heures après T0
    # (19:00 UTC) il est 03:00 UTC, soit 23:00 la veille à New York.
    huit_heures = 8 * 3600
    world.send("motion_detected", DOORBELL, huit_heures, "human")
    world.send("button_press", DOORBELL, huit_heures + 2)

    assert world.ring.played == [], "une garde déclarée ne se fait pas annoncer"


def test_un_inconnu_en_journee_reste_un_inconnu(world):
    """Une fenêtre de nuit ne doit pas couvrir la journée — c'est l'erreur qui
    rendrait le produit inutile sans que personne le remarque."""
    declare_la_nuit(world)

    world.send("motion_detected", DOORBELL, 0, "human")
    world.send("button_press", DOORBELL, 2)

    assert world.ring.played, "à 15:00 locales, personne n'est attendu"
