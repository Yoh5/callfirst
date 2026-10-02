"""The question came after the fields it was meant to fill.

The reading offers two days when a notice says "Tuesday" and nothing more, and
the page is supposed to put them one click away. The first person to use it
reported: *"les boutons de quoi ?"* — he had filled *Arrives from* and *Until*
by hand and never seen the choice, because it rendered in `#d-result`, which
sits **below** the form.

Nothing was broken. The endpoint returned both readings, the markup was valid,
the suite was green, and the feature was invisible: the fields it fills were
above it, so they got filled before anyone scrolled. It is the same shape as
the alert whose failure went to a journal nobody reads — the information
existed and never reached the person who needed it.

A browser is needed to prove the rendering, and there is none here. What can be
pinned without one is the order: the container the question renders into comes
before the form, in the document. That is the part that was wrong.
"""

import re
from pathlib import Path

PAGE = (Path(__file__).resolve().parent.parent / "callfirst" / "static"
        / "resident.html").read_text(encoding="utf-8")
SCRIPT = (Path(__file__).resolve().parent.parent / "callfirst" / "static"
          / "resident.js").read_text(encoding="utf-8")


def test_la_question_precede_les_champs_qu_elle_remplit():
    assert PAGE.index('id="d-choice"') < PAGE.index('id="add-delivery"')


def test_et_c_est_bien_la_que_les_lectures_sont_rendues():
    """Sinon le conteneur serait au bon endroit et vide."""
    rendu = SCRIPT[SCRIPT.index("if (p.readings"):]
    assert '$("d-choice").replaceChildren(' in rendu[:400]


def test_le_refus_de_collecte_reste_sous_le_formulaire():
    """Lui n'a rien à remplir : le formulaire est caché, donc il s'affiche juste
    sous le bouton « Read it ». Les deux blocs ne doivent pas se marcher
    dessus — une lecture efface l'autre."""
    assert PAGE.index('id="add-delivery"') < PAGE.index('id="d-result"')
    lecture = SCRIPT[SCRIPT.index("const p = await api"):]
    assert '$("d-choice").replaceChildren();' in SCRIPT[:SCRIPT.index("const p = await api")][-300:]
    assert '$("d-result").replaceChildren(' in lecture


def test_les_deux_conteneurs_parlent_aux_lecteurs_d_ecran():
    """Le public de ce produit lit mal les petits caractères ; une zone qui
    change sans être annoncée n'existe pas pour une liseuse d'écran."""
    for bloc in re.findall(r'<div id="d-(?:choice|result)"[^>]*>', PAGE):
        assert 'aria-live="polite"' in bloc
