"""The pages themselves: they load, they only reference what exists, and they
keep to the Content-Security-Policy (no inline script, nothing from elsewhere)."""
from __future__ import annotations

import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parent.parent / "callfirst" / "static"
PAGES = sorted(STATIC.glob("*.html"))
SCRIPTS = sorted(STATIC.glob("*.js"))

#: The pages that must exist for this file to be checking anything. A glob
#: feeding `parametrize` is a quiet way to lose a whole suite: if this
#: directory is ever moved or renamed, pytest generates zero cases for five
#: tests -- references resolve, nothing loads from another origin, no inline
#: script, ids unique, scripts parse -- and the run stays green having checked
#: none of it. Naming them turns that silence into a failure.
EXPECTED_PAGES = {"family.html", "index.html", "privacy.html", "resident.html", "try.html"}


class Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs, self.inline_scripts, self.inline_handlers, self.ids = [], 0, [], []
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for key in ("src", "href"):
            if a.get(key):
                self.refs.append(a[key])
        if tag == "script":
            self._in_script = not a.get("src")
        self.inline_handlers += [k for k in a if k.startswith("on")]
        if "id" in a:
            self.ids.append(a["id"])

    def handle_data(self, data):
        if self._in_script and data.strip():
            self.inline_scripts += 1

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script = False


def parse(page: Path) -> Refs:
    refs = Refs()
    refs.feed(page.read_text(encoding="utf-8"))
    return refs


def test_the_pages_and_scripts_were_actually_found():
    """Everything below is parametrized over a glob; this is the glob."""
    assert EXPECTED_PAGES <= {p.name for p in PAGES}, f"missing pages under {STATIC}"
    assert SCRIPTS, f"no .js found under {STATIC}"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_pages_reference_only_files_that_exist(page):
    for ref in parse(page).refs:
        if ref.startswith("/static/"):
            assert (STATIC / ref.removeprefix("/static/")).is_file(), ref


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_pages_load_nothing_from_other_origins(page):
    for ref in parse(page).refs:
        if ref.startswith(("http://", "https://", "//")):
            # Outbound links are fine; scripts, styles and images are not.
            assert not re.search(r"\.(js|css|woff2?|png|jpe?g|svg)(\?|$)", ref), ref


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_no_inline_script_or_handler_the_csp_would_block(page):
    refs = parse(page)
    assert refs.inline_scripts == 0 and refs.inline_handlers == []


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_ids_are_unique(page):
    ids = parse(page).ids
    assert len(ids) == len(set(ids))


def test_every_id_a_script_looks_up_exists_on_its_page():
    for script, page in (("resident.js", "resident.html"), ("family.js", "family.html"),
                         ("try.js", "try.html")):
        wanted = set(re.findall(r'\$\("([\w-]+)"\)|getElementById\("([\w-]+)"\)',
                                (STATIC / script).read_text(encoding="utf-8")))
        wanted = {a or b for a, b in wanted}
        # The regex is coupled to how the scripts look elements up. Rename the
        # `$` helper and it quietly matches nothing, leaving `missing` empty
        # and this test passing without having read a single id.
        assert wanted, f"found no element lookups in {script}: the pattern no longer matches"
        missing = wanted - set(parse(STATIC / page).ids)
        assert not missing, f"{script} looks up {missing}, absent from {page}"


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_scripts_parse(script):
    result = subprocess.run(["node", "--check", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
