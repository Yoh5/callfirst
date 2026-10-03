"""The instruction that disappeared one minute after it was needed.

The family page shows one block above everything else — *What to do now* —
with the call to make and the report sheet. It took `alerts[0]`: the most
recent alert, whatever it was.

Now read the sequence the design names as threat (c), in order. The courier is
let in, so an `answered` alert goes out: *"Call Margaret now."* The scammer's
next move is to have the protection switched off, and that produces a `change`
alert a minute later. `change` has no instruction, so `TODO[latest.reason]` is
undefined, `recent` is false, and the block **hides** — at the exact moment the
situation got worse. The daughter opens her link and sees a status card and a
list, with nothing telling her to pick up the telephone.

No test could see it: the choice lived in the page. It lives in `status()` now,
which is why this file can exist, and the page only renders what it is handed.

Six hours, unchanged, because an instruction to call about this morning's
visit is wrong by the evening.
"""

from datetime import timedelta

from .conftest import DOORBELL, SENSOR, T0
from .test_app import seconds, world  # noqa: F401  — le monde de test vit là-bas


def visite(world, decalage=0.0):
    world.send("motion_detected", DOORBELL, decalage, "human")
    world.send("button_press", DOORBELL, decalage + 2)
    world.send("contact_sensor_faulted", SENSOR, decalage + 5)


def famille(world):
    return world.family.get("/api/family").json()


def raison_de(vue, ident):
    return next(a["reason"] for a in vue["alerts"] if a["id"] == ident)


# ── La séquence de l'escroc ─────────────────────────────────────────────

def test_une_pause_juste_apres_ne_cache_pas_l_appel_a_faire(world):
    """Le cas trouvé : l'alerte la plus récente est le changement, et c'est
    l'ouverture de la porte qu'il faut traiter."""
    visite(world)
    world.clock.now = T0 + seconds(60)
    world.resident.post("/api/resident/pause", json={"hours": 2})

    vue = famille(world)

    assert vue["alerts"][0]["reason"] == "change", "le changement est bien le plus récent"
    assert raison_de(vue, vue["what_to_do"]) == "answered", \
        "c'est la porte ouverte qu'il faut traiter, pas la pause"


def test_sans_rien_a_faire_le_bloc_ne_s_affiche_pas(world):
    """La réciproque : un simple changement ne demande pas d'appeler."""
    world.resident.post("/api/resident/pause", json={"hours": 2})

    vue = famille(world)

    assert vue["alerts"], "il y a bien des alertes"
    assert vue["what_to_do"] is None


def test_la_plus_recente_des_alertes_qui_demandent_quelque_chose(world):
    """Deux visites : c'est la seconde qu'on traite."""
    visite(world)
    premiere = famille(world)["what_to_do"]
    visite(world, 200)

    seconde = famille(world)["what_to_do"]

    assert seconde != premiere
    assert seconde > premiere, "les identifiants montent avec le temps"


def test_passe_six_heures_il_n_y_a_plus_rien_a_faire(world):
    """Une consigne d'appeler au sujet de la visite de ce matin est fausse le
    soir — et la page n'a aucun moyen de le savoir toute seule."""
    visite(world)
    assert famille(world)["what_to_do"] is not None

    world.clock.now = T0 + timedelta(hours=7)

    assert famille(world)["what_to_do"] is None


def test_la_residente_recoit_la_meme_reponse(world):
    """Les deux pages partagent `status()` : si le champ manquait d'un côté,
    la page correspondante retomberait silencieusement sur rien."""
    visite(world)

    assert world.view()["what_to_do"] == famille(world)["what_to_do"]


# ── Et la page s'en sert ────────────────────────────────────────────────

def test_la_page_famille_ne_prend_plus_la_premiere_alerte():
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "callfirst" / "static"
          / "family.js").read_text(encoding="utf-8")
    bloc = js[js.index("function todo("):][:600]

    assert "s.what_to_do" in bloc
    assert "s.alerts[0]" not in bloc
