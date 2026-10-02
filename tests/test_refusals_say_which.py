"""A refusal that names two causes has told you neither.

Adding a trusted person answered, for both of its refusals, *"already trusted,
or three people already"*. The two call for opposite actions — one is "nothing
to do, she is already on the list", the other is "remove someone first" — and
the reader had to work out which applied.

That is the fourth time this shape has come up in two days: `invalid window`
for a night carer, the chime line offering three causes when one was true, the
alert whose failure went to a journal. The audience for this page reads slowly
and is often being hurried by someone on the telephone. A message that makes
them deduce is a message that gets skipped.

The refusals here must also stay **strings**: the page shows `detail` when it
is a string and falls back to "That did not work. Please try again." when it is
not. A refusal that arrives as a validation structure is a refusal nobody
reads, so the last test pins that too.
"""

from .test_app import world  # noqa: F401  — le monde de test vit là-bas


def ajoute(world, nom, email):
    return world.resident.post("/api/resident/trusted",
                               json={"name": nom, "email": email})


def test_une_personne_deja_prevenue_est_nommee(world):
    """Sarah est déjà dans la liste du foyer de test."""
    r = ajoute(world, "Sarah again", "sarah@example.com")

    assert r.status_code == 409
    assert r.json()["detail"] == "sarah@example.com is already told about alerts"


def test_la_limite_de_trois_dit_quoi_faire(world):
    """Et elle dit l'action, pas seulement l'empêchement."""
    assert ajoute(world, "Tom", "tom@example.com").status_code == 200
    assert ajoute(world, "Ana", "ana@example.com").status_code == 200

    r = ajoute(world, "Joe", "joe@example.com")

    assert r.status_code == 409
    assert r.json()["detail"] == "three people are already told; remove one first"


def test_les_deux_refus_sont_differents(world):
    """Sans quoi les scinder n'aurait servi à rien."""
    ajoute(world, "Tom", "tom@example.com")
    ajoute(world, "Ana", "ana@example.com")

    doublon = ajoute(world, "Sarah again", "sarah@example.com").json()["detail"]
    pleine = ajoute(world, "Joe", "joe@example.com").json()["detail"]

    assert doublon != pleine


def test_un_refus_arrive_en_texte_et_non_en_structure(world):
    """La page n'affiche `detail` que s'il est une chaîne ; sinon elle retombe
    sur « That did not work. Please try again. », qui n'apprend rien."""
    r = ajoute(world, "Sarah again", "sarah@example.com")

    assert isinstance(r.json()["detail"], str)
