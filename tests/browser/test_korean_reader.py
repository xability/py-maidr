"""A non-English reader of the bundled ``maidr.js`` hears their language (#819).

``tests/util/test_locale_pack.py`` asserts the declaration is in the emitted
markup, ahead of the bundle. That cannot tell whether ``maidr.js`` reads it
from the window it actually runs in -- a notebook frame evaluates the bundle
from a string the parent page stashed, and a declaration left in the parent
would be emitted, well-formed, and never seen.

The request for the pack is asserted whatever the network does; that the
chart then speaks Korean needs jsDelivr, and is skipped when the runner
cannot reach it rather than failed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest import mock

import matplotlib.pyplot as plt
import pytest

import maidr
from maidr.util.environment import Environment

pytestmark = pytest.mark.browser

_HANGUL = re.compile(r"[가-힣]")


def _chart():
    fig, ax = plt.subplots()
    ax.bar(["a", "b", "c"], [1, 2, 3])
    ax.set_title("Sales")
    return fig


def _saved(tmp_path: Path) -> str:
    """A ``use_cdn=False`` document with its ``lib/`` folder."""
    out = tmp_path / "chart.html"
    maidr.save_html(_chart(), str(out), use_cdn=False)
    return out.as_uri()


def _notebook(tmp_path: Path) -> str:
    """A page shaped like a notebook: the parent stash, then a srcdoc frame."""
    source = json.dumps(maidr.read_bundled_js()).replace("</", "<\\/")
    with mock.patch.object(Environment, "is_notebook", return_value=True):
        frame = str(maidr.render(_chart(), use_cdn=False))
    out = tmp_path / "notebook.html"
    out.write_text(
        f"<!doctype html><html><body><script>window.__maidrJsSource = {source};"
        f"</script>{frame}</body></html>",
        encoding="utf-8",
    )
    return out.as_uri()


def _visit(browser, url: str, locale: str):
    """Load ``url`` in ``locale``; return external requests, statuses, text."""
    context = browser.new_context(locale=locale)
    page = context.new_page()
    requests: list[str] = []
    statuses: dict[str, int | None] = {}
    page.on("request", lambda r: requests.append(r.url))
    page.on("response", lambda r: statuses.update({r.url: r.status}))
    page.goto(url, wait_until="load")
    page.wait_for_timeout(8_000)
    text = " ".join(
        frame.evaluate(
            "document.body ? document.body.innerText + ' ' + "
            "Array.from(document.querySelectorAll('[aria-label]'))"
            ".map(e => e.getAttribute('aria-label')).join(' ') : ''"
        )
        for frame in page.frames
    )
    context.close()
    external = [u for u in requests if not u.startswith(("file:", "about:", "data:"))]
    return external, statuses, text


@pytest.mark.parametrize("build", [_saved, _notebook], ids=["save_html", "notebook"])
def test_a_korean_reader_is_sent_to_the_bundled_versions_pack(
    browser, tmp_path, build
):
    pack = (
        f"https://cdn.jsdelivr.net/npm/maidr@{maidr.maidr_js_version()}"
        "/dist/locale-ko.js"
    )
    external, statuses, text = _visit(browser, build(tmp_path), "ko-KR")

    assert external == [pack], external
    if statuses.get(pack) != 200:
        pytest.skip(f"jsDelivr unreachable from this runner ({statuses})")
    assert _HANGUL.search(text), text[:300]


@pytest.mark.parametrize("build", [_saved, _notebook], ids=["save_html", "notebook"])
def test_an_english_reader_makes_no_request(browser, tmp_path, build):
    external, _, text = _visit(browser, build(tmp_path), "en-US")

    assert external == []
    assert "maidr plot" in text
