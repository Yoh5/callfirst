"""The report sheet, opened on the phone the alert arrived on.

The alert email carries one link: the report sheet, which the submission calls
printable and ready for IC3 and the FTC. It went to `/family/report/{id}`,
which needs a session.

Picture how it is actually read. The invitation arrives once and is opened on a
laptop, which is where the cookie lives. The alert arrives at three in the
afternoon and is read on a phone. She taps the link and the product answers
*"open the link you were sent"* — on the device the alert came to, about the
incident it came about. The recovery exists (scroll back to the invitation
email) and it is the worst possible moment to ask for it.

So the email carries a key of its own: derived from the household, the alert
and her address, stored nowhere, opening that one report and no other page.
The access tokens could not serve, because `grant()` revokes the previous one
— a fresh link in every alert would log her out of the page she may have open.

What the key must not become is a way in. These tests fix that: no key, a wrong
key, another alert's key, and a key that has been tampered with by one
character all get the same refusal as before.
"""

from .conftest import DOORBELL, SENSOR
from .test_app import TestClient, world  # noqa: F401  — le monde de test vit là-bas


def visite(world, decalage=0.0):
    world.send("motion_detected", DOORBELL, decalage, "human")
    world.send("button_press", DOORBELL, decalage + 2)
    world.send("contact_sensor_faulted", SENSOR, decalage + 5)


def lien_du_courriel(world, email="sarah@example.com"):
    """Le lien tel qu'il est écrit dans le dernier courriel reçu."""
    import re
    corps = world.mailer.to(email)[-1].get_body(("plain",)).get_content()
    trouve = re.search(r"/family/report/(\d+)\?k=([\w-]+)", corps)
    assert trouve, f"pas de lien signé dans le courriel :\n{corps}"
    return f"/family/report/{trouve.group(1)}?k={trouve.group(2)}"


def telephone(world):
    """Un appareil qui n'a jamais ouvert l'invitation."""
    return TestClient(world.app)


# ── Ce qui manquait ─────────────────────────────────────────────────────

def test_le_lien_du_courriel_ouvre_la_feuille_sans_session(world):
    visite(world)

    r = telephone(world).get(lien_du_courriel(world))

    assert r.status_code == 200
    assert "Doorstep incident report" in r.text


def test_la_feuille_ainsi_ouverte_est_la_vraie(world):
    """Pas une page de courtoisie : le contenu qu'on apporte à la police."""
    visite(world)

    texte = telephone(world).get(lien_du_courriel(world)).text

    assert "ic3.gov" in texte and "reportfraud.ftc.gov" in texte
    assert "Margaret" in texte


# ── Ce que la clé ne doit pas devenir ───────────────────────────────────

def test_sans_cle_c_est_toujours_refuse(world):
    visite(world)
    lien = lien_du_courriel(world)

    r = telephone(world).get(lien.split("?")[0])

    assert r.status_code == 401


def test_une_cle_fausse_est_refusee(world):
    visite(world)
    lien = lien_du_courriel(world)

    r = telephone(world).get(lien.split("?")[0] + "?k=" + "A" * 22)

    assert r.status_code == 401


def test_une_cle_modifiee_d_un_caractere_est_refusee(world):
    visite(world)
    lien = lien_du_courriel(world)
    base, cle = lien.split("?k=")
    truque = ("B" if cle[0] != "B" else "C") + cle[1:]

    assert telephone(world).get(f"{base}?k={truque}").status_code == 401


def test_la_cle_d_une_alerte_n_ouvre_pas_une_autre(world):
    """Deux visites, deux rapports. La clé de la première ne doit pas servir
    pour la seconde : sinon une seule fuite ouvrirait tout l'historique."""
    visite(world)
    premier = lien_du_courriel(world)
    visite(world, 200)
    second = lien_du_courriel(world)
    assert premier != second

    cle_du_premier = premier.split("?k=")[1]
    base_du_second = second.split("?k=")[0]

    assert telephone(world).get(f"{base_du_second}?k={cle_du_premier}").status_code == 401


def test_la_cle_n_ouvre_rien_d_autre_que_cette_feuille(world):
    """Elle n'est pas une session : les pages de la résidente et de la famille
    restent fermées."""
    visite(world)
    cle = lien_du_courriel(world).split("?k=")[1]
    tel = telephone(world)

    assert tel.get(f"/api/family?k={cle}").status_code == 401
    assert tel.get(f"/api/resident?k={cle}").status_code == 401


def test_une_cle_non_ascii_est_refusee_et_ne_casse_rien(world):
    """`hmac.compare_digest` lève TypeError sur une chaîne non-ASCII : `?k=é`
    était un 500 que n'importe quel passant pouvait produire."""
    visite(world)
    base = lien_du_courriel(world).split("?k=")[0]

    r = telephone(world).get(f"{base}?k=éclair")

    assert r.status_code == 401


def test_un_changement_n_a_pas_de_feuille_et_donc_pas_de_cle(world):
    """Une alerte de changement ne porte pas de rapport ; son courriel ne doit
    pas inventer un lien."""
    world.resident.post("/api/resident/pause", json={"hours": 2})

    corps = world.mailer.to("sarah@example.com")[-1].get_body(("plain",)).get_content()

    assert "/family/report/" not in corps
