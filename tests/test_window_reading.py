"""The delivery window, read through the whole path — page, API, validation.

`when.py` tests the reading on its own. These test that it reaches the
resident's page and that nothing on the way loosens what decides.

Two properties, and the second is the one worth having:

- what the message settles is **filled in**, so she does not retype what the
  carrier already wrote — a form that asks for what it just read is a form
  people stop filling in;
- what the message leaves open is **offered, never chosen**. The readings
  travel beside `Proposal` rather than inside it, on purpose: `Proposal` is
  what `validate` is handed, and the boundary that decides is not widened for
  a convenience of the page.

The case that matters is the one from the shot plan — the real UPS notice,
which names a weekday and no date.
"""

from datetime import timedelta

from .conftest import DOORBELL, T0
from .test_app import world  # noqa: F401  — le monde de test vit là-bas


UPS = ("UPS Update: Your package 1Z 999 AA1 0123456784 is scheduled for "
       "delivery Tuesday between 2:00 PM and 6:00 PM. Signature required.")


def lire(world, texte):
    return world.resident.post("/api/resident/deliveries/read",
                               json={"text": texte}).json()


# ── Ce que le message règle lui-même ────────────────────────────────────

def test_une_date_complete_remplit_la_fenetre(world):
    """Elle n'a pas à retaper ce que le transporteur a déjà écrit."""
    jour = (T0 + timedelta(days=2)).strftime("%d %B")
    p = lire(world, f"UPS 1Z999AA10123456784 arriving {jour} between 2:00 PM and 6:00 PM")

    assert p["start"] and p["end"], "la fenêtre est lue"
    assert p["readings"] == [], "rien à demander"
    assert p["question"] == ""


def test_le_transporteur_et_le_numero_restent_lus(world):
    """Le changement n'enlève rien à ce qui marchait."""
    p = lire(world, UPS)

    assert p["carrier"] == "UPS"
    assert p["tracking"] == "1Z999AA10123456784"
    assert p["signature_required"] is True


# ── Ce qu'il laisse ouvert ──────────────────────────────────────────────

def test_un_jour_sans_date_est_propose_jamais_choisi(world):
    """Le message du plan de tournage. Une fenêtre rend un visiteur attendu,
    donc personne n'est prévenu tant qu'elle dure : un jour deviné de travers
    est un silence le jour où ça comptait."""
    p = lire(world, UPS)

    assert p["start"] is None and p["end"] is None, "rien n'est choisi"
    assert len(p["readings"]) == 2
    assert p["question"]


def test_chaque_lecture_porte_de_quoi_remplir_le_formulaire(world):
    p = lire(world, UPS)

    for lecture in p["readings"]:
        assert lecture["label"]
        assert lecture["start"] and lecture["end"]
        assert lecture["start"] < lecture["end"]


def test_les_deux_lectures_sont_a_une_semaine_d_ecart(world):
    p = lire(world, UPS)

    jours = sorted(l["start"][:10] for l in p["readings"])
    assert jours[0] != jours[1], "deux jours différents, pas deux fois le même"


# ── Ce que ça ne doit pas relâcher ──────────────────────────────────────

def test_une_fenetre_proposee_passe_quand_meme_par_la_validation(world):
    """Elle revient comme n'importe quelle fenêtre et se fait juger pareil. Le
    texte reste une collecte : il est refusé, quelle que soit la lecture."""
    collecte = ("UPS 1Z999AA10123456784. Our agent will collect your gold "
                "Tuesday between 2:00 PM and 6:00 PM.")
    p = lire(world, collecte)
    lecture = (p["readings"] or [{"start": None, "end": None}])[0]

    r = world.resident.post("/api/resident/deliveries", json={
        "text": collecte, "carrier": "UPS", "tracking": "1Z999AA10123456784",
        "start": (lecture["start"] or "")[:16], "end": (lecture["end"] or "")[:16]})

    assert r.status_code == 422
    assert any("collection" in x for x in r.json()["detail"]["refusals"])


def test_un_visiteur_reste_inattendu_tant_que_rien_n_est_confirme(world):
    """Lire n'est pas déclarer. Tant que la personne n'a pas validé une
    fenêtre, le rappel joue — sinon coller un message suffirait à se taire."""
    lire(world, UPS)

    world.send("button_press", DOORBELL, 10)

    assert world.ring.played, "le visiteur n'est pas devenu attendu par une lecture"
