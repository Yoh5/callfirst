"""The figures on the public page have to be the figures that were measured.

This file exists because they were not. The landing page claimed *32 / 32
rules broken on purpose* for as long as it took to add sixteen more mutations
and never look at the page again. `scripts/mutate.py` had 48, `submission/
mutate.txt` recorded 48/48, and the one surface a visitor actually reads said
32 — understating the work, which is the harmless direction, and still a
number on a public page that the repository contradicts.

Nothing caught it because nothing was looking. A judge checking one claim
against the repo would have found a product whose own page disagreed with its
own evidence, and after that every other figure is worth checking too.

So the page is pinned to the sources it is quoting: the mutation list itself,
and the two committed measurement files. Change the measurement, and this
test tells you which sentence on the page is now a lie.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
PAGE = RACINE / "callfirst" / "static" / "index.html"
CHAOS = RACINE / "submission" / "chaos.txt"
MUTATE = RACINE / "submission" / "mutate.txt"


def page() -> str:
    return PAGE.read_text(encoding="utf-8")


def stat(page_html: str, legende: str) -> str:
    """La valeur en gras dont la légende contient `legende`."""
    for valeur, texte in re.findall(
            r"<b>([^<]+)</b><span>([^<]+)</span>", page_html):
        if legende.lower() in " ".join(texte.split()).lower():
            return valeur.strip()
    raise AssertionError(f"aucune statistique dont la légende contient {legende!r}")


def test_le_nombre_de_mutations_annonce_est_celui_du_script():
    """`48 / 48` doit compter les mutations qui existent, pas celles d'un jour."""
    source = (RACINE / "scripts" / "mutate.py").read_text(encoding="utf-8")
    n = len(re.findall(r"^\s{4}\(", source[source.index("MUTATIONS"):], re.M))
    assert n > 0, "la liste MUTATIONS n'a pas été trouvée — ce test doit être adapté"
    assert stat(page(), "rules broken on purpose") == f"{n} / {n}"


def test_la_derniere_ligne_mesuree_dit_la_meme_chose():
    source = (RACINE / "scripts" / "mutate.py").read_text(encoding="utf-8")
    n = len(re.findall(r"^\s{4}\(", source[source.index("MUTATIONS"):], re.M))
    derniere = MUTATE.read_text(encoding="utf-8").strip().splitlines()[-1]
    assert derniere == f"{n}/{n} mutations caught", (
        f"submission/mutate.txt se termine par {derniere!r} : la course enregistrée "
        "ne couvre plus la liste de mutations. La relancer avant de publier.")


def test_les_familles_prevenues_viennent_du_fichier_de_chaos():
    mesure = re.search(r"families told (\d+)/(\d+)",
                       CHAOS.read_text(encoding="utf-8"))
    assert mesure, "submission/chaos.txt ne porte plus la ligne « families told »"
    prevenues, total = mesure.group(1), mesure.group(2)
    assert stat(page(), "families told") == f"{prevenues} / {total}"


def test_aucun_rappel_joue_deux_fois():
    """Le seul chiffre de la page qui soit un zéro revendiqué."""
    mesure = re.search(r"played twice (\d+)", CHAOS.read_text(encoding="utf-8"))
    assert mesure, "submission/chaos.txt ne porte plus la ligne « played twice »"
    assert stat(page(), "reminders played twice") == mesure.group(1)


@pytest.mark.parametrize("promesse", [
    "false alerts and the misses are published",
    "without a door sensor a handover under a minute is missed",
])
def test_la_page_continue_de_publier_ses_ratees(promesse: str):
    """Retirer le raté de la page serait la seule façon de la rendre fausse
    sans changer un chiffre."""
    assert promesse in " ".join(page().split())
