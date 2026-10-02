"""One action removes everything held for a household.

Ring's content policy asks for it, DESIGN.md claims it, and the README names
`test_app.py` beside the claim. That file tested only that the endpoint refuses
an unauthenticated caller — the deletion itself was never exercised. A row in a
threat table pointing at a test that does not test it is worse than a row with
no test named: it reads as covered.

What has to hold after it, and each one is a different way for data to survive:

- the resident's own link stops working;
- **the family's links stop working too** — they are separate tokens in a
  separate table, and forgetting that table is the easy mistake;
- nothing is left in the database under that household, in any table;
- and the trusted people are told before it happens, because it is the last
  thing this household will ever send them.

The last point is not tidiness. Someone who deletes the household is either
done with the product or has been talked into deleting it, and the second is
the reason the farewell exists.
"""

import sqlite3

from .conftest import DOORBELL, SENSOR
from .test_app import world  # noqa: F401  — le monde de test vit là-bas


def tout_supprimer(world):
    return world.resident.request("DELETE", "/api/resident")


def peuple(world):
    """Un foyer qui a vécu : une visite, une alerte, un journal."""
    world.send("motion_detected", DOORBELL, 0, "human")
    world.send("button_press", DOORBELL, 2)
    world.send("contact_sensor_faulted", SENSOR, 5)
    assert world.resident.get("/api/resident").json()["alerts"], "il y a de quoi supprimer"


# ── Le geste lui-même ───────────────────────────────────────────────────

def test_la_suppression_reussit(world):
    peuple(world)

    assert tout_supprimer(world).status_code == 204


def test_le_lien_de_la_personne_ne_marche_plus(world):
    peuple(world)
    tout_supprimer(world)

    assert world.resident.get("/api/resident").status_code in (401, 403, 404)


def test_les_liens_de_la_famille_non_plus(world):
    """Des jetons distincts, dans une table distincte. L'oublier est l'erreur
    facile, et elle laisserait la famille lire un foyer effacé."""
    peuple(world)
    tout_supprimer(world)

    assert world.family.get("/api/family").status_code in (401, 403, 404)


# ── Et rien ne reste derrière ───────────────────────────────────────────

def test_la_base_ne_garde_rien_de_ce_foyer(world):
    """Table par table, parce qu'une seule oubliée suffit. On regarde le
    fichier, pas l'API : l'API pourrait très bien cacher ce qu'elle garde."""
    peuple(world)
    tout_supprimer(world)

    db = sqlite3.connect(world.path)
    restes = {
        table: db.execute(f"select count(*) from {table} where {colonne} = ?",
                          ("home-1",)).fetchone()[0]
        for table, colonne in (("households", "id"), ("devices", "household"),
                               ("outbox", "household"), ("journal", "household"),
                               ("access", "household"))
    }
    db.close()

    assert restes == {t: 0 for t in restes}, f"il reste quelque chose : {restes}"


def test_les_proches_sont_prevenus_avant(world):
    """C'est la dernière chose que ce foyer leur enverra — et quelqu'un qui
    supprime a pu y être poussé."""
    peuple(world)
    avant = len(world.mailer.messages)

    tout_supprimer(world)

    assert len(world.mailer.messages) > avant, "le départ se dit"


def test_un_webhook_qui_arrive_apres_ne_ressuscite_rien(world):
    """La sonnette continue d'exister chez Ring. Un événement en retard ne
    doit pas recréer le foyer qu'on vient d'effacer."""
    peuple(world)
    tout_supprimer(world)

    world.send("button_press", DOORBELL, 30)

    db = sqlite3.connect(world.path)
    combien = db.execute("select count(*) from households").fetchone()[0]
    db.close()
    assert combien == 0, "rien n'a été recréé"
