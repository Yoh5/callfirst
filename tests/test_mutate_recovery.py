"""The mutation harness putting the tree back after it has been killed.

`scripts/mutate.py` edits production source in place. The first attempt at
making that safe was an exit hook and a signal handler, and it was proved
insufficient the same day it was written: the process was killed outright, no
handler ran, and `callfirst/rules.py` kept an `if False:` until the next test
run tripped over it. Nothing inside a process survives `SIGKILL`.

So the originals go to disk under `.mutate-restore/` **before** a file is
touched, and the next run restores from there. The directory existing at all is
the signal that a run did not finish on its own terms.

Two properties, and the second is the one that makes it usable:

- a killed run is undone, **byte for byte**. Reading as text normalises line
  endings and writing them back depends on the platform; a restore that
  rewrites every line ending turns one changed function into a whole file
  changed, and then the diff meant to show the bug shows nothing but noise;
- the journal is cleared afterwards, so its presence keeps meaning what it
  means.
"""

import hashlib
import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture
def banc():
    """Le script lui-même, importé sans l'exécuter."""
    spec = importlib.util.spec_from_file_location("mutate", RACINE / "scripts" / "mutate.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["mutate"] = module
    spec.loader.exec_module(module)
    yield module
    shutil.rmtree(module.JOURNAL, ignore_errors=True)
    sys.modules.pop("mutate", None)


@pytest.fixture
def cible(banc):
    """Un fichier réel du produit, remis en place quoi qu'il arrive."""
    chemin = RACINE / "callfirst" / "rules.py"
    original = chemin.read_bytes()
    yield chemin, original
    chemin.write_bytes(original)


def tue_en_plein_milieu(banc, chemin: Path, original: bytes) -> None:
    """Le journal écrit, la mutation posée, et plus personne pour nettoyer."""
    banc.JOURNAL.mkdir(exist_ok=True)
    nom = str(chemin.relative_to(RACINE)).replace("\\", "/").replace("/", "__")
    (banc.JOURNAL / f"{nom}.bak").write_bytes(original)
    chemin.write_bytes(original.replace(b"    if h.heightened(now):", b"    if False:", 1))


def test_une_execution_tuee_est_defaite_au_demarrage_suivant(banc, cible):
    chemin, original = cible
    tue_en_plein_milieu(banc, chemin, original)
    assert chemin.read_bytes() != original, "la mutation est bien posée"

    banc._repartir_de_zero()

    assert chemin.read_bytes() == original


def test_la_restauration_est_octet_pour_octet(banc, cible):
    """Pas « équivalent » : identique. Sinon le dépôt entier se marque modifié
    à chaque passage et plus personne ne lit les diffs."""
    chemin, original = cible
    tue_en_plein_milieu(banc, chemin, original)

    banc._repartir_de_zero()

    assert hashlib.sha256(chemin.read_bytes()).hexdigest() == \
        hashlib.sha256(original).hexdigest()


def test_le_journal_est_efface_apres_la_reprise(banc, cible):
    """Sinon sa présence ne veut plus rien dire, et le signal se perd."""
    chemin, original = cible
    tue_en_plein_milieu(banc, chemin, original)

    banc._repartir_de_zero()

    assert not banc.JOURNAL.exists()


def test_sans_journal_il_ne_se_passe_rien(banc, cible):
    """Le cas normal, de loin le plus fréquent : ne rien toucher."""
    chemin, original = cible
    shutil.rmtree(banc.JOURNAL, ignore_errors=True)

    assert banc._repartir_de_zero() is False
    assert chemin.read_bytes() == original


def test_la_reprise_le_dit(banc, cible, capsys):
    """Une réparation silencieuse laisse croire que rien n'était cassé."""
    chemin, original = cible
    tue_en_plein_milieu(banc, chemin, original)

    banc._repartir_de_zero()

    dit = capsys.readouterr().out
    assert "killed" in dit
    assert "rules.py" in dit
