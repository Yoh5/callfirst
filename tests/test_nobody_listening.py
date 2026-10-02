"""Protection with nobody on the other end.

The resident names the trusted people, and a trusted person can stop receiving
alerts — "they can stop receiving alerts; the others are told." When there are
others, that is sound: the removal is announced to everyone, the person leaving
included, computed before they go.

But the last one can leave. After that the protection is still switched on, the
reminder still plays at the chime, and every alert is addressed to nobody. The
resident believes she is covered, and the one thing this product exists to do —
tell somebody — cannot happen.

It is not an attack, which is what makes it worth testing. A daughter changes
her email, unsubscribes from the wrong thing, or simply leaves; nobody is being
manipulated, and nobody is told that the alarm is now wired to nothing.

The product's own rule covers it, as usual: say it. The resident sees it on her
own page, and the alert that empties the list says what it empties.
"""

from .conftest import DOORBELL, SENSOR
from .test_app import world  # noqa: F401  — le monde de test vit là-bas


def retire(world, email: str):
    return world.resident.request("DELETE", f"/api/resident/trusted/{email}")


# ── Ce qui marche quand il reste quelqu'un ──────────────────────────────

def test_retirer_une_personne_quand_il_en_reste_previent_tout_le_monde(world):
    world.resident.post("/api/resident/trusted",
                        json={"name": "Tom", "email": "tom@example.com"})

    r = retire(world, "sarah@example.com")

    assert r.status_code == 200, r.text
    destinataires = [e for groupe in r.json().get("told", []) for e in groupe]
    assert "sarah@example.com" in destinataires, "celle qui part l'apprend aussi"
    assert "tom@example.com" in destinataires


# ── Ce qui se passe quand il ne reste personne ──────────────────────────

def test_la_page_dit_que_plus_personne_n_ecoute(world):
    """Sans ça, la maison est « protégée » et l'alarme n'est reliée à rien."""
    retire(world, "sarah@example.com")

    vue = world.resident.get("/api/resident").json()

    assert vue["trusted"] == []
    assert vue.get("nobody_listening") is True, \
        "la page doit pouvoir le dire, pas laisser croire que c'est protégé"


def test_l_alerte_de_depart_dit_ce_qu_elle_vide(world):
    """« Sarah ne recevra plus d'alertes » et « plus personne ne recevra
    d'alertes » n'appellent pas la même réaction."""
    r = retire(world, "sarah@example.com")

    detail = " ".join(a.get("detail", "") for a in
                      world.resident.get("/api/resident").json()["alerts"])

    assert "nobody" in detail.lower() or "no one" in detail.lower(), \
        f"le départ du dernier doit se dire, reçu : {detail[-200:]}"
    assert r.status_code == 200


def test_la_protection_reste_allumee_mais_le_produit_le_dit(world):
    """On n'éteint pas à sa place — on lui dit. C'est la règle partout
    ailleurs dans ce produit."""
    retire(world, "sarah@example.com")

    vue = world.resident.get("/api/resident").json()

    assert vue["enabled"] is True, "on ne décide pas d'éteindre à sa place"
    assert vue.get("nobody_listening") is True


def test_une_visite_reelle_n_est_alors_dite_a_personne(world):
    """Le fait brut, pour qu'il soit au dossier : c'est ce que la mention
    évite de laisser découvrir."""
    retire(world, "sarah@example.com")
    # On compte APRÈS le départ : l'alerte de départ, elle, est bien partie —
    # à celle qui s'en va, destinataires calculés avant son retrait.
    avant = len(world.mailer.messages)

    world.send("motion_detected", DOORBELL, 0, "human")
    world.send("button_press", DOORBELL, 2)
    world.send("contact_sensor_faulted", SENSOR, 5)

    alertes = world.resident.get("/api/resident").json()["alerts"]
    assert [a for a in alertes if a["reason"] == "answered"], "l'alerte est bien levée"
    assert len(world.mailer.messages) == avant, "et elle ne part nulle part"
