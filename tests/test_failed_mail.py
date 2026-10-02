"""An alert that was raised, and an email that never arrived.

The whole product reduces to one sentence: when the door opens for someone
unexpected, **somebody is told**. Everything else — the chime, the window, the
heightened week — exists to decide whether to send that message.

A send can fail. The journal records `alert email FAILED`, which is right and
is where it belongs. But nobody reads the journal: the resident's page shows
alerts and reminders, and the alert sits in her list looking exactly like one
that arrived. She is told her daughter was told.

That is the same shape as a bug found this morning in another project — a
feedback form whose storage did not exist, which answered `success: true` for
weeks. The failure was written down somewhere nobody looked, and the interface
kept promising. Writing a failure where nobody reads it is a half-step: it
clears the engineer and leaves the user exactly where they were.

So the alert carries whether it reached anyone, and the page says so. Not as a
notice that scrolls away — as part of the alert itself, forever, because
somebody may ask in six months who was told about that visit.
"""

from .conftest import DOORBELL, SENSOR
from .test_app import world  # noqa: F401  — le monde de test vit là-bas


class PostierEnPanne:
    """Un facteur qui refuse tout, comme un SMTP qui tombe."""

    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return False

    def to(self, email):
        return self


def visite(world):
    world.send("motion_detected", DOORBELL, 0, "human")
    world.send("button_press", DOORBELL, 2)
    world.send("contact_sensor_faulted", SENSOR, 5)


# ── Ce qui marchait déjà ────────────────────────────────────────────────

def test_l_echec_est_bien_enregistre_au_journal(world):
    """Le point de départ : ce n'est pas perdu, c'est juste rangé là où
    personne ne regarde."""
    world.app.state.mailer_broken = True   # repère pour le test suivant
    world.mailer.send = lambda m: False

    visite(world)

    journal = [t for _, t in world.store.journal("home-1")]
    assert any("FAILED" in t for t in journal)


# ── Ce qui manquait ─────────────────────────────────────────────────────

def test_l_alerte_dit_si_elle_a_atteint_quelqu_un(world):
    """Elle a l'air, dans la liste, exactement comme une alerte arrivée."""
    world.mailer.send = lambda m: False

    visite(world)

    alertes = world.resident.get("/api/resident").json()["alerts"]
    repondue = next(a for a in alertes if a["reason"] == "answered")
    assert repondue.get("delivered") is False, \
        "une alerte qui n'est arrivée nulle part doit le dire"


def test_une_alerte_qui_arrive_le_dit_aussi(world):
    """Sans la réciproque, l'absence du drapeau ne voudrait rien dire."""
    visite(world)

    alertes = world.resident.get("/api/resident").json()["alerts"]
    repondue = next(a for a in alertes if a["reason"] == "answered")
    assert repondue.get("delivered") is True


def test_le_fait_reste_au_dossier(world):
    """Quelqu'un demandera dans six mois qui a été prévenu de cette visite-là.
    Une notification passagère ne répond pas à cette question."""
    world.mailer.send = lambda m: False
    visite(world)

    # Deuxième lecture : tout revient du stockage, rien n'est en mémoire.
    alertes = world.resident.get("/api/resident").json()["alerts"]

    assert any(a.get("delivered") is False for a in alertes)


def test_la_famille_voit_la_meme_chose(world):
    """Le proche qui ouvre son lien doit voir qu'une alerte ne lui est pas
    parvenue — c'est lui qui peut agir dessus."""
    world.mailer.send = lambda m: False
    visite(world)

    alertes = world.family.get("/api/family").json()["alerts"]

    assert any(a.get("delivered") is False for a in alertes)
