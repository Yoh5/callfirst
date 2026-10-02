"""An installation that cannot send email at all, reporting alerts as delivered.

Trying the hosted demo to answer "does *Try it* work?": it does, end to end —
the chime plays, the alert is raised with the sensor's confidence, the still
image comes back, the report sheet names IC3 and the FTC. And the alert says
`delivered: true`.

It is not. Without `SMTP_HOST` the service falls back to `FileMailer`, which
writes `.eml` files into its own data directory and returns `True`. That is
exactly right for `scripts/demo.py`, where the folder *is* the mailbox and the
script tells you to look in it. On anything deployed it means every alert is
recorded as delivered because the mailer accepted it — and the flag added
yesterday, which exists to stop an alert that reached nobody from looking like
one that arrived, says nothing at all about a send that was never possible.

Worse than nobody listening, and the same shape: the product is running, there
are people on the list, and it has no way to reach them. So it goes beside the
other two standing facts on the resident's page — the doorbell being offline,
and nobody being on the list.

The hosted demo is exempt, and deliberately: its trusted address is
`@example.invalid` so no stranger is ever mailed, and the demo page says to
open Sarah's view instead of waiting for an email.
"""

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from callfirst import notify
from callfirst.app import create_app
from callfirst.store import Store
from .conftest import CHIME, DOORBELL, SENSOR
from .test_app import ADMIN, KEY, Clock, FakeRing, world  # noqa: F401


def vue(world):
    return world.resident.get("/api/resident").json()


def foyer(mailer, tmp_path, household_id="home-1"):
    """Un foyer monté sur le facteur donné, et la session de la résidente.

    Premier jet de ce fichier : je posais `world.app.state.mailer` puis
    j'affirmais `isinstance(...)` -- un test qui ne pouvait pas échouer, et qui
    ne touchait jamais le drapeau qu'il prétendait couvrir. C'est le défaut que
    ce projet passe deux jours à traquer ailleurs.
    """
    store = Store(tmp_path / f"{household_id}.db", Fernet.generate_key())
    app = create_app(store, FakeRing(), KEY, ADMIN["x-admin-token"], clock=Clock(),
                     background=False, mailer=mailer, base_url="http://testserver")
    admin = TestClient(app)
    r = admin.post("/api/households", headers=ADMIN, json={
        "id": household_id, "resident": "Margaret", "doorbell": DOORBELL, "chime": CHIME,
        "sensor": SENSOR, "trusted": [{"name": "Sarah", "email": "sarah@example.com"}]})
    assert r.status_code == 201
    resident = TestClient(app)
    resident.get(r.json()["resident_link"].replace("http://testserver", ""),
                 follow_redirects=False)
    resident.post("/api/resident/on")
    return resident


# ── Le cas trouvé ───────────────────────────────────────────────────────

def test_un_facteur_sur_disque_le_dit(tmp_path):
    """Le facteur que le service choisit tout seul quand SMTP_HOST manque."""
    resident = foyer(notify.FileMailer(tmp_path / "mail"), tmp_path)

    assert resident.get("/api/resident").json()["mail_goes_nowhere"] is True


def test_un_vrai_envoi_ne_le_dit_pas(tmp_path):
    """La réciproque, sinon le drapeau voudrait dire « toujours »."""
    resident = foyer(PostierSmtp(), tmp_path, "home-2")

    assert resident.get("/api/resident").json()["mail_goes_nowhere"] is False


def test_un_foyer_de_demo_sur_le_meme_service_se_tait(tmp_path):
    """Même facteur sur disque, mais un foyer `demo-` : son adresse est
    injoignable par construction et la page de démo dit d'ouvrir la vue de
    Sarah. Le signaler serait du bruit."""
    resident = foyer(notify.FileMailer(tmp_path / "mail2"), tmp_path, "demo-1-abc")

    assert resident.get("/api/resident").json()["mail_goes_nowhere"] is False


class PostierSmtp:
    """Un facteur qui part vraiment, du point de vue du drapeau."""

    def __init__(self):
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return True

    def to(self, email):
        return self


def test_le_drapeau_existe_et_est_un_booleen(world):
    """Il doit être présent dans toutes les réponses, sinon la page ne peut pas
    s'y fier : une clé absente et une clé fausse ne se distinguent pas."""
    assert isinstance(vue(world)["mail_goes_nowhere"], bool)


def test_la_page_le_place_avec_les_deux_autres_faits_du_meme_genre():
    """« Le portier est hors ligne » et « personne ne reçoit les alertes » sont
    déjà des faits permanents, pas des notifications qui défilent. Le troisième
    doit l'être aussi."""
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "callfirst" / "static"
          / "resident.js").read_text(encoding="utf-8")

    assert js.index("nobody_listening") < js.index("mail_goes_nowhere")
    bloc = js[js.index("if (s.mail_goes_nowhere"):][:400]
    assert 'kind = "blind"' in bloc, "le même habillage que les deux autres"
    assert "cannot send email" in bloc
