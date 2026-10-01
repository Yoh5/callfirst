"""A declared delivery inside the heightened week, and who hears about it.

After an alert the household is heightened for seven days, because couriers
come back — the README says so, and so does the narration. During that week an
unexpected visitor alerts the family before the door even opens.

A declared delivery makes a visitor expected, and `rules.alert` returns before
anything else when a visit is expected. That is right in general: a parcel the
resident is waiting for should not alert her daughter.

**But the two meet badly.** Declaring a delivery only tells the family when the
window is today or tomorrow; further out it is a silent note. So a delivery
declared for day four of the heightened week is not announced to anyone *and*
silences the watch for its window — in the exact days the product says it is
watching hardest.

It is reachable by the threat the design names first: *"the victim is coached
against their own tool"*. A scammer whose first attempt raised an alert knows
the family is now watching. The cheapest counter is not technical — it is
"declare the delivery so it doesn't bother your daughter."

The answer is the product's own rule rather than a new one: refusing would
decide for her, which this product does not do. **Every declaration made during
the heightened week tells the family, whatever its date.**
"""

from datetime import timedelta

from .conftest import DOORBELL, SENSOR, T0, seconds
from .test_app import world  # noqa: F401  — le monde de test vit là-bas


def declare(world, jours: int):
    """Déclare une livraison à N jours, et rend ce que la famille a reçu."""
    debut = (T0 + timedelta(days=jours)).strftime("%Y-%m-%dT%H:%M")
    fin = (T0 + timedelta(days=jours, hours=3)).strftime("%Y-%m-%dT%H:%M")
    texte = "UPS: package 1Z999AA10123456784 arrives then, 2-6 PM"
    return world.resident.post("/api/resident/deliveries", json={
        "text": texte, "carrier": "UPS", "tracking": "1Z999AA10123456784",
        "start": debut, "end": fin})


def declenche_une_alerte(world):
    """Un visiteur inattendu, la porte s'ouvre : la maison passe en vigilance."""
    world.send("motion_detected", DOORBELL, 0, "human")
    world.send("button_press", DOORBELL, 2)
    world.send("contact_sensor_faulted", SENSOR, 5)
    assert world.view()["heightened_until"], "la vigilance doit être enclenchée"


# ── Hors vigilance, le silence est normal ───────────────────────────────

def test_hors_vigilance_une_livraison_lointaine_ne_derange_personne(world):
    """Déclarer le colis de la semaine prochaine n'a rien de suspect."""
    r = declare(world, jours=4)

    assert r.status_code == 200, r.text
    assert r.json()["told"] == [], "personne n'est dérangé pour ça"


def test_hors_vigilance_une_livraison_du_jour_est_annoncee(world):
    """Celle-ci peut servir à faire passer un coursier pour attendu."""
    r = declare(world, jours=0)

    assert r.json()["told"], "une fenêtre pour aujourd'hui se dit"


# ── Pendant la vigilance, tout se dit ───────────────────────────────────

def test_pendant_la_vigilance_meme_une_livraison_lointaine_se_dit(world):
    """Le trou. Elle n'est annoncée à personne et elle fait taire la veille
    sur sa fenêtre, dans les jours mêmes où le produit dit veiller le plus."""
    declenche_une_alerte(world)

    r = declare(world, jours=4)

    assert r.status_code == 200, r.text
    assert r.json()["told"], \
        "pendant la semaine qui suit une alerte, une déclaration se dit"


def test_la_famille_apprend_que_c_est_pendant_la_vigilance(world):
    """« Une livraison a été déclarée » et « une livraison a été déclarée
    pendant la semaine qui suit une alerte » ne demandent pas le même coup de
    téléphone."""
    declenche_une_alerte(world)
    declare(world, jours=4)

    alertes = world.resident.get("/api/resident").json()["alerts"]
    recentes = " ".join(a["detail"] for a in alertes if a["reason"] == "change")

    assert "alert" in recentes.lower() or "watch" in recentes.lower()


def test_la_declaration_est_acceptee_quand_meme(world):
    """On ne décide pas à sa place : on le dit. Refuser serait lui retirer le
    contrôle que ce produit lui laisse partout ailleurs."""
    declenche_une_alerte(world)
    declare(world, jours=4)

    assert world.resident.get("/api/resident").json()["deliveries"], \
        "la livraison est bien enregistrée"
