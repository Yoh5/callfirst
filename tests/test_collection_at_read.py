"""The refusal that mattered most, behind a form that could not be submitted.

Walking the shot plan before filming: paste the fake notice — *UPS … Federal
agent will come for safekeeping of your gold bars* — press **Read it**, then
**This is right — add it**, and read the refusal on screen.

Except the refusal never arrived. `validate` runs when a delivery is *added*,
and the form's *Arrives from* and *Until* fields are `required`: a collection
message carries no window, so the browser blocked the submission with "please
fill out this field" and the product never got to speak. To reach the one
sentence that matters — *nobody legitimate collects from a home* — the resident
would have had to **invent a delivery window for a message that has none**.

The scam this product is about ends with a courier collecting cash or gold. A
message asking for a collection is refused whatever window it carries, so the
reading says it at once, and offers nothing to correct: there is no version of
that message which becomes acceptable once a date is typed in.

`collecte()` is now the single enumeration behind both moments. Two lists of
the same words drift, and this one decides whether a courier gets announced in
advance.
"""

from datetime import datetime, timezone

from callfirst.deliveries import collecte, read, validate
from .test_app import world  # noqa: F401  — le monde de test vit là-bas

FAUX = ("UPS 1Z999AA10123456784. Federal agent will come for safekeeping of "
        "your gold bars.")
VRAI = ("UPS Update: Your package 1Z 999 AA1 0123456784 is scheduled for delivery "
        "Tuesday between 2:00 PM and 6:00 PM. Signature required.")


def lis(world, texte):
    return world.resident.post("/api/resident/deliveries/read",
                               json={"text": texte}).json()


# ── Ce qui manquait ─────────────────────────────────────────────────────

def test_la_lecture_dit_deja_que_c_est_une_collecte(world):
    """Sans ça, le refus attend un bouton que le navigateur bloque."""
    assert lis(world, FAUX)["collection"] == ["gold", "safekeeping"]


def test_et_le_message_de_collecte_n_a_justement_pas_de_fenetre(world):
    """La raison pour laquelle le refus était inatteignable : les deux champs
    de fenêtre sont obligatoires dans le formulaire, et il n'y a rien à y
    mettre. Tout ce qu'il faut pour refuser doit donc être dans la lecture."""
    lu = lis(world, FAUX)
    assert lu["start"] is None and lu["end"] is None
    assert lu["collection"], "refuser ne peut pas dépendre de l'étape d'ajout"


def test_un_vrai_avis_ne_declenche_rien(world):
    """La réciproque, sinon « collecte » voudrait dire « tout message »."""
    assert lis(world, VRAI)["collection"] == []


# ── Une seule énumération ───────────────────────────────────────────────

def test_les_deux_chemins_citent_les_memes_mots():
    """Le refus de `validate` et celui de la lecture doivent nommer les mêmes
    mots. S'ils divergent, l'un des deux mentira un jour."""
    mots = collecte(FAUX)
    verdict = validate(FAUX, read(FAUX), datetime(2026, 10, 2, 17, tzinfo=timezone.utc))

    assert mots == ("gold", "safekeeping")
    assert ", ".join(mots) in verdict.refusals[0]


def test_la_collecte_reste_refusee_a_l_ajout(world):
    """La lecture prévient ; c'est toujours le code qui tranche. Un appel direct
    à l'API, sans passer par la page, doit refuser aussi — l'interface n'est
    pas la garde."""
    r = world.resident.post("/api/resident/deliveries", json={
        "text": FAUX, "carrier": "UPS", "tracking": "1Z999AA10123456784",
        "start": "2026-10-06T14:00:00-04:00", "end": "2026-10-06T18:00:00-04:00",
        "signature_required": False})

    assert r.status_code == 422
    assert any("collection" in m for m in r.json()["detail"]["refusals"])
