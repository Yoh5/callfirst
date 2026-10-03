"""The last person told stops receiving — from her own link, not the resident's.

`test_nobody_listening.py` covers the resident removing someone. Every one of
its five tests goes through `DELETE /api/resident/trusted/{email}`. The path
nobody tested is the realistic one: **the daughter unsubscribes herself**, from
the link at the bottom of an alert, because she changed address or changed job.

It runs through the same rule, so it ought to behave the same. "Ought to" is
what this file replaces, because the consequence is the worst state the product
has: protection on, the reminder still playing, and every alert addressed to
nobody. No attacker is needed.

One asymmetry stays, and it is a limit rather than a defect: the resident has
no address in this product — only the people she trusts do — so when the last
of them leaves, the only notice reaches the person who just left. The resident
learns it from the standing line on her own page, which is why that line had to
exist. The family page says so in as many words: *"If you stop, Margaret sees
it on the Call First page and the others are told."*
"""

from .conftest import DOORBELL, SENSOR
from .test_app import world  # noqa: F401  — le monde de test vit là-bas


def visite(world):
    world.send("motion_detected", DOORBELL, 0, "human")
    world.send("button_press", DOORBELL, 2)
    world.send("contact_sensor_faulted", SENSOR, 5)


# ── Le départ par son propre lien ───────────────────────────────────────

def test_la_page_de_la_residente_dit_que_plus_personne_n_ecoute(world):
    assert world.family.delete("/api/family/me").status_code == 204

    vue = world.view()
    assert vue["trusted"] == []
    assert vue["nobody_listening"] is True
    assert vue["enabled"] is True, "la protection ne s'éteint pas toute seule"


def test_le_depart_laisse_une_trace_qui_dit_ce_qu_il_vide(world):
    """Pas une notification qui défile : une alerte au dossier, parce que la
    question « depuis quand mes alertes ne partaient-elles plus ? » se pose
    après coup."""
    world.family.delete("/api/family/me")

    alertes = world.view()["alerts"]
    assert any("Nobody is receiving alerts now" in a["detail"] for a in alertes)


def test_la_personne_qui_part_est_la_seule_prevenue_et_c_est_dit(world):
    """La résidente n'a pas d'adresse dans ce produit. Le courriel ne peut donc
    aller qu'à celle qui s'en va — ce test fixe cette limite pour qu'elle ne
    soit pas découverte par quelqu'un d'autre."""
    avant = len(world.mailer.messages)

    world.family.delete("/api/family/me")

    envoyes = world.mailer.messages[avant:]
    assert len(envoyes) == 1
    assert "sarah@example.com" in envoyes[0]["To"]


def test_la_porte_continue_de_fonctionner_pour_rien(world):
    """Le carillon joue, l'alerte est levée, et elle n'atteint personne. C'est
    l'état que la ligne permanente de la page existe pour dire."""
    world.family.delete("/api/family/me")

    visite(world)

    assert world.ring.played, "le rappel joue encore : c'est ce qui trompe"
    alertes = world.view()["alerts"]
    repondue = next(a for a in alertes if a["reason"] == "answered")
    # Premier jet de cette assertion : `delivered is False or not_delivered
    # == []`, un « ou » qui passait dans les deux cas — exactement le défaut
    # que ce projet traque ailleurs. En la resserrant, la vraie réponse est
    # apparue : `delivered` valait **True**. Une alerte sans aucun destinataire
    # n'avait rien à échouer, donc `not manques` était vrai et elle se
    # déclarait arrivée. `renderAlerts` avait le message pour cet état depuis
    # le début — « This reached nobody. Call them. » quand `not_delivered` est
    # vide — et le serveur ne pouvait pas le produire.
    assert repondue["delivered"] is False, \
        "une alerte adressée à personne ne doit pas se dire arrivée"
    assert repondue["not_delivered"] == [], \
        "et il n'y a personne à rappeler : c'est le cas que la page nomme"


def test_et_une_nouvelle_personne_remet_les_choses_en_place(world):
    """Sans la réciproque, « plus personne n'écoute » pourrait rester collé."""
    world.family.delete("/api/family/me")

    world.resident.post("/api/resident/trusted",
                        json={"name": "Tom", "email": "tom@example.com"})

    assert world.view()["nobody_listening"] is False
