"""The one visit nobody is told about, and why that is the right answer.

A sixty-household chaos run read "59 of 60 families told" and the harness was
right to fail: the central claim of the whole project is that when the door
opens for someone unexpected, somebody is told. The silent household had
`reminders 0, alerts change` — the system had never seen a visitor at all.

Both of its doorbell webhooks had been dropped, the motion and the press. All
that arrived was the door opening, and `_door_opened` returns at once when
there is no visit in progress. That is deliberate, and it has to stay: a door
that opens with nobody at it is the resident fetching the post, letting the cat
in, going out to the bins. A product that alerted the family on every one of
those would be switched off within a week, and then it protects nobody.

So the limit is real and it is narrow: **losing one doorbell webhook costs
nothing, losing both loses the visit.** At one webhook in ten, that is about
one visit in a hundred. Nothing in the Ring Partner API lets us ask the
doorbell what it saw a minute ago — `sensor_open` exists for the sensor and
has no equivalent for motion — so this one cannot be recovered the way a lost
door-opening is. It is published, it is the first item of product feedback to
Ring, and the chaos harness now asserts the claim that is actually true: every
family whose doorbell was seen is told.
"""

from .conftest import DOORBELL, SENSOR
from .test_app import world  # noqa: F401  — le monde de test vit là-bas


# ── Le cas perdu ────────────────────────────────────────────────────────

def test_les_deux_webhooks_du_portier_perdus_personne_n_est_prevenu(world):
    """La porte s'ouvre seule : ce n'est pas une visite, c'est un habitant."""
    world.send("contact_sensor_faulted", SENSOR, 0)

    # Pas « aucune alerte » : la mise en route en produit une, et c'est voulu.
    # Ce qui ne doit pas exister, c'est une alerte « la porte a été ouverte ».
    alertes = world.resident.get("/api/resident").json()["alerts"]
    assert not any(a["reason"] == "answered" for a in alertes)
    assert world.ring.played == []


# ── Les cas qui doivent survivre, sinon la limite serait bien plus large ─

def test_la_sonnerie_perdue_mais_le_mouvement_vu_la_famille_est_prevenue(world):
    """Le mouvement suffit à ouvrir la visite : perdre UN webhook ne coûte rien.
    C'est ce qui rend la limite étroite plutôt que béante."""
    world.send("motion_detected", DOORBELL, 0, "human")
    world.send("contact_sensor_faulted", SENSOR, 5)

    alertes = world.resident.get("/api/resident").json()["alerts"]
    assert any(a["reason"] == "answered" for a in alertes), \
        "sans la sonnerie, l'ouverture de la porte doit quand même alerter"


def test_le_mouvement_perdu_mais_la_sonnerie_vue_aussi(world):
    """La réciproque, pour le même prix."""
    world.send("button_press", DOORBELL, 0)
    world.send("contact_sensor_faulted", SENSOR, 5)

    alertes = world.resident.get("/api/resident").json()["alerts"]
    assert any(a["reason"] == "answered" for a in alertes)


def test_l_ouverture_livree_avant_la_sonnerie_compte_quand_meme(world):
    """Les webhooks arrivent dans le désordre. Ici l'ouverture est **livrée**
    d'abord alors qu'elle a eu lieu après la sonnerie : le code garde
    `door_opened_at` et la visite qui suit de peu est « répondue ». Sans ça, le
    retard du réseau deviendrait un silence.

    Premier jet de ce test : ouverture *survenue* à t+0, sonnerie à t+3, et
    j'attendais une alerte. Le produit a eu raison de refuser — une porte
    ouverte avant que le visiteur arrive n'est pas une réponse à sa sonnerie,
    et `_door_opened` le dit en toutes lettres. Ce qui se rattrape, c'est
    l'ordre de livraison, pas l'ordre des faits."""
    world.send("contact_sensor_faulted", SENSOR, 5)
    world.send("button_press", DOORBELL, 3)

    alertes = world.resident.get("/api/resident").json()["alerts"]
    assert any(a["reason"] == "answered" for a in alertes)
