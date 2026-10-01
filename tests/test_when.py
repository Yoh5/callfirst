"""Reading *when*, and refusing to guess it.

A delivery window is not an ordinary field. Inside one a visitor is expected,
so the reminder does not play and nobody is told. Every other field is a label
that can be corrected afterwards; this one decides whether the product speaks
at all, and a window on the wrong day produces silence on the day it mattered.

Two halves, and the second matters more: what is unambiguous is read, so the
resident does not retype what the carrier already wrote; what is ambiguous is
**offered, never resolved**.

**One finding worth stating, because it was not designed and it does most of
the work.** `validate` refuses any window beyond fourteen days, so a reading
that lands outside that horizon is not a candidate at all. On 1 October, `7/10`
is 7 October one way and 10 July the next year the other — and nobody is told
about a delivery nine months out. The horizon dissolves nearly every numeric
ambiguity on its own, without anyone choosing a locale. What it does **not**
dissolve is a bare weekday: *Tuesday* means two dates that are both a week
apart and both plausible, and that one stays a question.
"""

from datetime import date, datetime

import pytest

from callfirst.when import lis

#: A Thursday, so "Tuesday" is five days away and the week after is twelve —
#: both inside the horizon, which is what makes that case the real one.
JEUDI = date(2026, 10, 1)


# ── Ce qui se lit sans rien supposer ────────────────────────────────────

@pytest.mark.parametrize("texte", [
    "Delivery Tuesday 6 October, 2:00 PM to 6:00 PM.",
    "Arriving October 6, between 2:00 PM and 6:00 PM.",
    "Window 2026-10-06, 14:00 - 18:00.",
    "Out for delivery on 6th October between 2pm and 6pm",
    "Delivery 6 October between 2 and 6 PM",
])
def test_une_date_complete_est_lue(texte):
    quand = lis(texte, JEUDI)

    assert quand.certain is not None, "rien à demander, le texte le dit"
    assert quand.certain.debut == datetime(2026, 10, 6, 14, 0)
    assert quand.certain.fin == datetime(2026, 10, 6, 18, 0)


def test_la_lecture_se_relit_en_clair():
    """Ce que la personne voit avant de confirmer."""
    quand = lis("Tuesday 6 October, 2:00 PM to 6:00 PM.", JEUDI)

    assert "06" in quand.certain.quoi
    assert "October" in quand.certain.quoi
    assert "14:00" in quand.certain.quoi


# ── Un seul marqueur pour deux heures ───────────────────────────────────

def test_un_seul_PM_vaut_pour_les_deux_heures():
    """« between 2 and 6 PM » est la façon dont les transporteurs écrivent. Un
    « 2 » seul n'est pas une heure ; dans une plage, il en devient une."""
    quand = lis("Delivery 6 October between 2 and 6 PM", JEUDI)

    assert (quand.certain.debut.hour, quand.certain.fin.hour) == (14, 18)


def test_le_marqueur_herite_ne_retourne_pas_la_fenetre():
    """« between 10 and 2 PM » : hériter le PM donnerait 22h → 14h, une fenêtre
    qui finit avant de commencer. Le début prend alors l'autre moitié du jour.
    C'est une règle, pas une supposition."""
    quand = lis("Delivery 6 October between 10 and 2 PM", JEUDI)

    assert (quand.certain.debut.hour, quand.certain.fin.hour) == (10, 14)


# ── Ce qui ne se devine pas ─────────────────────────────────────────────

def test_un_jour_seul_propose_les_deux_semaines():
    """Résoudre « mardi » par « le message vient d'arriver » suppose qu'elle le
    colle le jour même. Elle le colle trois jours plus tard, et la fenêtre part
    une semaine trop loin pendant qu'elle se croit couverte."""
    quand = lis("Delivery Tuesday between 2 and 6 PM", JEUDI)

    assert [l.debut.date() for l in quand.lectures] == [date(2026, 10, 6),
                                                        date(2026, 10, 13)]
    assert quand.certain is None


def test_le_message_reel_de_UPS_pose_la_question():
    """Celui du plan de tournage : transporteur et numéro lus, jour demandé."""
    texte = ("UPS Update: Your package 1Z 999 AA1 0123456784 is scheduled for "
             "delivery Tuesday between 2:00 PM and 6:00 PM. Signature required.")

    quand = lis(texte, JEUDI)

    assert len(quand.lectures) == 2
    assert quand.demande


def test_la_question_dit_pourquoi_on_demande():
    """« Choisissez une date » n'explique rien. La personne doit comprendre ce
    que le produit n'a pas su lire."""
    quand = lis("Delivery Tuesday between 2 and 6 PM", JEUDI)

    assert "Tuesday" in quand.demande
    assert "week after" in quand.demande


# ── L'horizon désambiguïse ce qu'on croyait devoir trancher ─────────────

def test_une_date_en_chiffres_se_lit_sans_choisir_de_pays():
    """7/10 est le 7 octobre pour une moitié du monde et le 10 juillet pour
    l'autre — mais personne n'annonce une livraison à neuf mois. Au-delà de
    quatorze jours `validate` refuse la fenêtre, donc cette lecture-là n'est
    pas candidate, et il n'y a rien à demander."""
    quand = lis("Delivery 7/10 between 2:00 PM and 6:00 PM", JEUDI)

    assert quand.certain is not None
    assert quand.certain.debut.date() == date(2026, 10, 7)
    assert quand.demande == ""


def test_une_date_en_chiffres_hors_horizon_ne_donne_rien():
    """25/12 ne peut être que le 25 décembre, et le 25 décembre est à trois
    mois. Proposer une fenêtre que `validate` refusera serait promettre ce qui
    sera refusé."""
    assert lis("Delivery 25/12 between 2:00 PM and 6:00 PM", JEUDI).lectures == ()


# ── Ce qui ne donne aucune fenêtre ──────────────────────────────────────

def test_sans_heures_il_n_y_a_pas_de_fenetre():
    """Une seule heure ne fait pas une fenêtre, et inventer une durée est
    exactement ce que ce module refuse."""
    assert lis("Delivery Tuesday 6 October, from 2:00 PM.", JEUDI).lectures == ()


def test_sans_date_il_n_y_a_pas_de_fenetre():
    assert lis("Delivery between 2:00 PM and 6:00 PM.", JEUDI).lectures == ()


def test_un_numero_de_suivi_ne_fabrique_pas_une_heure():
    """« 1Z 999 AA1 0123456784 » est plein de chiffres. Une heure n'en est une
    que si elle porte deux points, am/pm, ou si elle est l'une des bornes d'une
    plage."""
    quand = lis("UPS 1Z 999 AA1 0123456784 arriving Tuesday 6 October.", JEUDI)

    assert quand.lectures == ()


def test_une_date_trop_lointaine_n_est_pas_proposee():
    quand = lis("Delivery 20 November between 2:00 PM and 6:00 PM", JEUDI)

    assert quand.lectures == ()


def test_une_seule_lecture_ne_pose_aucune_question():
    """Une question sans alternative est du bruit."""
    assert lis("Delivery 6 October, 2:00 PM to 6:00 PM.", JEUDI).demande == ""
