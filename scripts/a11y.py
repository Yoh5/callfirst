"""Contrast, measured rather than asserted.

This service is used by people with low vision -- that is why the typeface is
Atkinson Hyperlegible, and it is also why "we thought about accessibility" is
not a claim worth making without numbers behind it. Every colour pair the
stylesheet actually puts on screen is checked here, in both themes, against
WCAG 2.1: 4.5:1 for body text, 3:1 for large text and for the borders and
focus rings a reader needs to find.

    python scripts/a11y.py

Exits non-zero if any pair falls short, so the test suite can hold the line.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "callfirst" / "static" / "style.css"

BODY_TEXT = 4.5
LARGE_TEXT = 3.0

#: Reported but not enforced: a card is already told apart by its surface
#: colour, its shadow and its padding, so its border is decoration rather than
#: "non-text content required to understand the content". Darkening eleven
#: borders to satisfy a rule that does not bind would help nobody.
INFORMATIONAL: list[tuple[str, str, str]] = [
    ("line", "bg", "the border of a card against the page"),
    ("line", "surface", "the rule inside a card"),
]

#: (foreground token, background token, minimum, what it is)
PAIRS: list[tuple[str, str, float, str]] = [
    ("ink", "bg", BODY_TEXT, "body text on the page"),
    ("ink", "surface", BODY_TEXT, "body text on a card"),
    ("ink", "soft", BODY_TEXT, "body text on a soft panel"),
    ("muted", "bg", BODY_TEXT, "hints and secondary text on the page"),
    ("muted", "surface", BODY_TEXT, "hints and secondary text on a card"),
    ("brand", "bg", BODY_TEXT, "links on the page"),
    ("brand", "surface", BODY_TEXT, "links on a card"),
    ("brand-ink", "brand", BODY_TEXT, "the label of the main button"),
    ("ok", "ok-soft", BODY_TEXT, "the armed status"),
    ("warn", "warn-soft", BODY_TEXT, "the paused status"),
    ("alarm", "alarm-soft", BODY_TEXT, "a refusal, and the heightened status"),
    ("alarm", "surface", BODY_TEXT, "the label of the destructive button"),
    ("accent-ink", "accent-soft", BODY_TEXT, "an accented note"),
    ("accent", "bg", LARGE_TEXT, "the focus ring on the page"),
    ("accent", "surface", LARGE_TEXT, "the focus ring on a card"),
]


def _tokens(block: str) -> dict[str, str]:
    return {name: value for name, value in re.findall(r"--([a-z-]+):\s*(#[0-9a-fA-F]{3,8})", block)}


def themes(css: str) -> dict[str, dict[str, str]]:
    """The light theme, and the dark theme with the light one underneath it."""
    light_block = css.split(":root {", 1)[1].split("}", 1)[0]
    dark_block = css.split('prefers-color-scheme: dark', 1)[1].split("}", 1)[0]
    light = _tokens(light_block)
    return {"light": light, "dark": {**light, **_tokens(dark_block)}}


def _channel(value: float) -> float:
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    raw = hex_colour.lstrip("#")
    if len(raw) == 3:
        raw = "".join(c * 2 for c in raw)
    r, g, b = (int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(foreground: str, background: str) -> float:
    a, b = luminance(foreground), luminance(background)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def failures() -> list[str]:
    css = CSS.read_text(encoding="utf-8")
    problems: list[str] = []
    for theme, tokens in themes(css).items():
        for fg, bg, minimum, what in PAIRS:
            ratio = contrast(tokens[fg], tokens[bg])
            if ratio < minimum:
                problems.append(
                    f"{theme}: {what} -- --{fg} on --{bg} is {ratio:.2f}:1, needs {minimum}:1"
                )
    return problems


def main() -> int:
    css = CSS.read_text(encoding="utf-8")
    for theme, tokens in themes(css).items():
        print(f"\n{theme}")
        print("-" * 72)
        for fg, bg, minimum, what in PAIRS:
            ratio = contrast(tokens[fg], tokens[bg])
            mark = "ok  " if ratio >= minimum else "FAIL"
            print(f"  {mark} {ratio:5.2f}:1  (needs {minimum})  {what}")

    print("\n  reported, not enforced (decoration, not information)")
    for theme, tokens in themes(css).items():
        for fg, bg, what in INFORMATIONAL:
            print(f"       {contrast(tokens[fg], tokens[bg]):5.2f}:1  {theme}: {what}")

    problems = failures()
    print()
    if problems:
        for problem in problems:
            print(f"FAIL  {problem}")
        return 1
    print(f"{len(PAIRS) * 2} colour pairs checked in two themes: all above the WCAG minimum.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
