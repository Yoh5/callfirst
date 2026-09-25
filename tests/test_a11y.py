"""Contrast is a promise this service makes to the people who use it.

The audience is older adults, many with low vision. A regression here is not a
cosmetic slip, it is the product failing the group it was built for -- so it
fails the suite like any other broken behaviour.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from a11y import PAIRS, contrast, failures, themes  # noqa: E402


def test_every_enforced_pair_meets_its_wcag_minimum():
    assert failures() == []


def test_the_focus_ring_is_findable_in_both_themes():
    # SC 1.4.11: 3:1. A keyboard user with low vision navigates by this ring,
    # and it measured 1.88:1 in the light theme until it was fixed.
    css = (Path(__file__).resolve().parent.parent / "callfirst" / "static" / "style.css").read_text(
        encoding="utf-8"
    )
    for tokens in themes(css).values():
        assert contrast(tokens["accent"], tokens["bg"]) >= 3.0
        assert contrast(tokens["accent"], tokens["surface"]) >= 3.0


def test_the_checked_pairs_are_the_ones_the_stylesheet_actually_uses():
    # A checker that measures colours nobody puts on screen proves nothing.
    css = (Path(__file__).resolve().parent.parent / "callfirst" / "static" / "style.css").read_text(
        encoding="utf-8"
    )
    for fg, bg, _minimum, _what in PAIRS:
        assert f"var(--{fg})" in css
        assert f"var(--{bg})" in css
