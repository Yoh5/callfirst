"""Removing a visit by position, from a page drawn twenty seconds ago.

The resident's page re-reads the list every twenty seconds, and *Remove* sent
the row's position. Between the render and the click the list can shift —
another device, another tab, a daughter helping from her own copy of the link —
and the position then points at whatever moved into it.

The consequence is not an error message. The wrong window is deleted, and the
page says *"Carer was removed"*, using the label from its own stale view. For a
night carer it means the chime announces her every night from then on, and
nothing ever said so. A confirmation that names the thing you still have is
worse than no confirmation.

So the caller says what it believes it is removing. The page has the label and
both times on screen already, so this costs nothing and turns a silent wrong
deletion into a refusal that tells her to look again.
"""

from .test_app import world  # noqa: F401  — le monde de test vit là-bas


def declare(world, label, debut, fin, jours=(0, 1, 2, 3, 4)):
    return world.resident.post("/api/resident/visits", json={
        "label": label, "weekdays": list(jours), "start": debut, "end": fin})


def visites(world):
    return [v["label"] for v in world.resident.get("/api/resident").json()["visits"]]


# ── Ce qui marchait, et doit continuer ──────────────────────────────────

def test_supprimer_ce_qu_on_voit(world):
    declare(world, "Carer", "10:00", "12:00")
    declare(world, "Night carer", "22:00", "06:00")

    r = world.resident.delete(
        "/api/resident/visits/0?label=Carer&start=10:00&end=12:00")

    assert r.status_code == 200
    assert visites(world) == ["Night carer"]


def test_une_position_qui_n_existe_pas_reste_un_404(world):
    assert world.resident.delete("/api/resident/visits/7").status_code == 404


# ── Ce qui manquait ─────────────────────────────────────────────────────

def test_une_liste_qui_a_bouge_refuse_au_lieu_de_deviner(world):
    """La page montre encore « Carer » en position 0 ; le foyer, lui, n'a plus
    que la garde de nuit. Le clic ne doit pas la supprimer."""
    declare(world, "Carer", "10:00", "12:00")
    declare(world, "Night carer", "22:00", "06:00")
    world.resident.delete("/api/resident/visits/0?label=Carer&start=10:00&end=12:00")

    # Le même clic, rejoué depuis la page d'avant : position 0, « Carer ».
    r = world.resident.delete(
        "/api/resident/visits/0?label=Carer&start=10:00&end=12:00")

    assert r.status_code == 409
    assert visites(world) == ["Night carer"], \
        "la garde de nuit ne doit pas disparaître à la place de l'autre"


def test_le_refus_est_une_phrase_que_la_page_affiche(world):
    """La page montre `detail` quand c'est une chaîne et retombe sinon sur
    « That did not work », qui n'apprend rien."""
    declare(world, "Carer", "10:00", "12:00")

    r = world.resident.delete(
        "/api/resident/visits/0?label=Cleaner&start=10:00&end=12:00")

    assert isinstance(r.json()["detail"], str)
    assert "look again" in r.json()["detail"]


def test_les_heures_comptent_aussi_pas_seulement_le_nom(world):
    """Deux visites peuvent porter le même nom à des heures différentes : c'est
    le cas ordinaire d'une aide qui vient matin et soir."""
    declare(world, "Carer", "10:00", "12:00")
    declare(world, "Carer", "18:00", "19:00")

    r = world.resident.delete(
        "/api/resident/visits/1?label=Carer&start=10:00&end=12:00")

    assert r.status_code == 409
    assert len(world.resident.get("/api/resident").json()["visits"]) == 2
