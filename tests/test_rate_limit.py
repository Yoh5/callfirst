"""The rate limiter, and the two ways it was not one.

The demo is the only endpoint a stranger reaches without a link, and each call
creates a household on a free instance. It is limited per address, with a
global cap behind it. Two defects made the first of those limits optional.

**The address came from the half of the header the caller writes.**
`X-Forwarded-For` reads *claimed, …, observed*: the client writes the first
entry, each proxy appends what it saw. Taking the first entry takes the
caller's own claim — a different value on every request, and the limit never
binds. The last entry is what our own proxy observed, and it is the only part
of that header we did not get from the person being limited.

**And the dictionary only ever pruned the caller.** Every address seen kept its
list for the life of the process, so the same rotating header that bypassed the
limit also grew memory without bound. One request, both problems.

The global cap was what actually held the line. Defence in depth is meant to be
the second line, not the first.
"""

from datetime import timedelta

from fastapi.testclient import TestClient

from callfirst import demo

from .conftest import T0
from .test_app import hosted  # noqa: F401  — le monde de la démo vit là-bas


def demarre(client, entete=None):
    return client.post("/api/demo/start",
                       headers={"x-forwarded-for": entete} if entete else {})


# ── La limite tient ─────────────────────────────────────────────────────

def test_la_limite_par_adresse_tient(hosted):
    app, _clock, _emulator = hosted
    visiteur = TestClient(app)

    codes = [demarre(visiteur, "203.0.113.7").status_code
             for _ in range(demo.STARTS_PER_HOUR + 2)]

    assert 429 in codes, "la limite doit finir par mordre"


def test_un_en_tete_tournant_ne_la_contourne_pas(hosted):
    """Le cœur du sujet : c'est l'appelant qui écrit la première valeur. S'il
    suffit d'en changer, il n'y a pas de limite."""
    app, _clock, _emulator = hosted
    visiteur = TestClient(app)

    codes = [demarre(visiteur, f"10.0.0.{i}, 203.0.113.7").status_code
             for i in range(demo.STARTS_PER_HOUR + 2)]

    assert 429 in codes, "la dernière valeur décide, pas celle qu'on nous donne"


def test_deux_adresses_vraiment_distinctes_ne_se_genent_pas(hosted):
    """La réciproque, et elle compte autant : deux personnes derrière deux
    proxys différents ne doivent pas se bloquer l'une l'autre."""
    app, _clock, _emulator = hosted

    assert demarre(TestClient(app), "198.51.100.1").status_code == 204
    assert demarre(TestClient(app), "198.51.100.2").status_code == 204


def test_sans_en_tete_la_limite_tient_aussi(hosted):
    """Une connexion directe, ou un test : on retombe sur la socket."""
    app, _clock, _emulator = hosted
    visiteur = TestClient(app)

    codes = [demarre(visiteur).status_code for _ in range(demo.STARTS_PER_HOUR + 2)]

    assert 429 in codes


# ── Et elle ne garde rien ───────────────────────────────────────────────

def test_le_journal_ne_grossit_pas_sans_fin(hosted):
    """Une entrée par adresse jamais revue, c'est une fuite — et c'est la même
    requête qui contournait la limite qui la provoquait."""
    app, clock, _emulator = hosted
    visiteur = TestClient(app)
    # Quarante adresses RÉELLEMENT distinctes — en dernière position, celle
    # que le proxy observe. Une première version faisait tourner la première
    # valeur, qui n'est plus la clé depuis le correctif : elle créait une seule
    # entrée et ne prouvait rien. La mutation l'a dit, pas la relecture.
    for i in range(40):
        demarre(visiteur, f"10.0.0.1, 192.0.2.{i}")

    clock.now = T0 + timedelta(hours=2)
    demarre(visiteur, "203.0.113.9")

    assert len(app.state.starts) == 1, \
        "les adresses expirées sont oubliées, pas seulement celle qui appelle"


def test_la_limite_se_relache_apres_une_heure(hosted):
    """Sinon ce n'est pas une limite horaire, c'est un bannissement."""
    app, clock, _emulator = hosted
    visiteur = TestClient(app)
    for _ in range(demo.STARTS_PER_HOUR + 2):
        demarre(visiteur, "203.0.113.11")

    clock.now = T0 + timedelta(hours=2)

    assert demarre(visiteur, "203.0.113.11").status_code == 204
