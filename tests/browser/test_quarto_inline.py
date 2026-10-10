"""Charts written into a page Quarto renders work as they did in frames (#895).

``tests/core/test_quarto_inline.py`` pins the markup. This opens it: a page
shaped like what Quarto's Jupyter engine writes, with the two charts' cell
outputs in it, as a reader's browser does. The page has what a real one has
that a frame kept from the chart:

* an AMD ``define`` in the head, as require.js puts there, which takes the
  UMD ``maidr.js`` for a module and never runs it unless kept from it;
* a deck that moves on ArrowRight unless its ``keyboardCondition`` says no,
  as reveal.js does, and a search that opens on ``s`` through
  ``window.quartoOpenSearch``, as a Quarto website's does;
* a stylesheet that takes every focus ring away.

Both charts draw a line with the same ``gid``, so a selector that named it
unchanged would find the other chart's line. Built with ``use_cdn=False``,
so the page needs no network.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

import matplotlib.pyplot as plt
import pytest

from maidr.core.figure_manager import FigureManager
from maidr.util.environment import Environment

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page

pytestmark = pytest.mark.browser

_PARSE_TIMEOUT_MS = 30_000
_PLOT = 'figure[id^="maidr-figure"] > [tabindex]'

_HEAD = """
<script>
  // require.js, as far as a UMD bundle can tell: takes it, never runs it.
  window.__amdCalls = 0;
  window.define = function () { window.__amdCalls += 1; };
  window.define.amd = {};

  // A deck: ArrowRight moves on unless keyboardCondition says no.
  window.Reveal = (function () {
    var config = {}, ready = false, onReady = [];
    window.__slide = 0;
    document.addEventListener('keydown', function (event) {
      var condition = config.keyboardCondition;
      if (typeof condition === 'function' && condition(event) === false) return;
      if (event.key === 'ArrowRight') window.__slide += 1;
    });
    window.addEventListener('load', function () {
      ready = true;
      onReady.forEach(function (f) { f(); });
    });
    return {
      configure: function (c) { for (var k in c) config[k] = c[k]; },
      getConfig: function () { return config; },
      isReady: function () { return ready; },
      isFocused: function () { return true; },
      on: function (name, f) { if (name === 'ready') onReady.push(f); }
    };
  })();

  // A Quarto website's search: opens on s, looked up when the key is let go.
  window.__searches = 0;
  window.quartoOpenSearch = function () { window.__searches += 1; };
  document.addEventListener('keyup', function (event) {
    if (event.key === 's') window.quartoOpenSearch();
  });
</script>
<style>*:focus { outline: none !important; }</style>
"""


def _line(title: str):
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot([1, 2, 3], [3.0, 1.0, 2.0], gid="series")
    ax.set_title(title)
    return fig


def _outputs(tmp_path: Path) -> list[str]:
    """Two charts, rendered as the kernel of a Quarto ``html`` render does."""
    info = tmp_path / "info.json"
    info.write_text(json.dumps({"format": {"pandoc": {"to": "html"}}}))
    kernel = mock.Mock(user_ns={})
    env = {"QUARTO_FIG_FORMAT": "png", "QUARTO_EXECUTE_INFO": str(info)}
    outputs = []
    with (
        mock.patch.dict("os.environ", env),
        mock.patch.object(Environment, "is_notebook", return_value=True),
        mock.patch("IPython.get_ipython", return_value=kernel),
    ):
        for title in ("First", "Second"):
            fig = _line(title)
            try:
                outputs.append(str(FigureManager.get_maidr(fig).render(use_cdn=False)))
            finally:
                plt.close(fig)
    assert all('class="maidr-inline"' in html for html in outputs)
    return outputs


@pytest.fixture(scope="module")
def outputs(tmp_path_factory) -> list[str]:
    return _outputs(tmp_path_factory.mktemp("render"))


def _page(browser: Browser, tmp_path: Path, body: str) -> Page:
    path = tmp_path / "doc.html"
    path.write_text(
        f"<!doctype html><html lang='en'><head>{_HEAD}</head><body>{body}"
        "<button id='after'>After</button></body></html>",
        encoding="utf-8",
    )
    page = browser.new_page(viewport={"width": 1100, "height": 900})
    page.on("console", lambda m: page.__dict__.setdefault("logs", []).append(m.text))
    page.goto(path.as_uri(), wait_until="load")
    page.wait_for_function(
        "() => document.querySelectorAll('svg[data-maidr-inline]').length === 0"
        " && document.querySelectorAll('article[id^=maidr-article-]').length > 0",
        timeout=_PARSE_TIMEOUT_MS,
    )
    return page


@pytest.fixture
def page(browser, tmp_path, outputs):
    body = "".join(f"<section>{html}</section>" for html in outputs)
    page = _page(browser, tmp_path, body)
    yield page
    page.close()


def _announced(page: Page) -> str:
    return page.evaluate(
        "() => (document.getElementById('maidr-text-container') || {}).innerText || ''"
    )


def _press_in(page: Page, chart: int, key: str) -> None:
    page.locator(_PLOT).nth(chart).focus()
    page.wait_for_timeout(300)
    page.keyboard.press(key)
    page.wait_for_timeout(300)


def test_both_charts_are_bound_by_one_maidr_js_despite_require_js(page):
    """The UMD bundle ran instead of handing itself to ``define``."""
    assert (
        page.evaluate("document.querySelectorAll('article[id^=maidr-article-]').length")
        == 2
    )
    assert page.evaluate("typeof window.maidrLive") == "object"
    assert page.evaluate("window.__amdCalls") == 0
    assert not [log for log in getattr(page, "logs", []) if "redefined" in log]


def test_each_chart_highlights_its_own_line(page):
    """Both used ``gid="series"``: each selector must still find its own."""
    for chart in (0, 1):
        _press_in(page, chart, "ArrowRight")
        owner = page.evaluate(
            """(chart) => {
                 const svgs = [...document.querySelectorAll('figure[id^="maidr-figure"] svg')];
                 const marks = [...document.querySelectorAll('[id^="maidr-highlight-"]')];
                 return marks.map(m => svgs.indexOf(m.closest('svg')));
               }""",
            chart,
        )
        assert owner and set(owner) == {chart}, f"chart {chart} highlighted {owner}"
        assert re.search(r"x is \d, y is \d", _announced(page).lower()), _announced(
            page
        )


def test_the_deck_stays_put_while_a_chart_has_the_keys(page):
    _press_in(page, 0, "ArrowRight")
    assert page.evaluate("window.__slide") == 0

    page.locator("#after").focus()
    page.keyboard.press("ArrowRight")
    assert page.evaluate("window.__slide") == 1


def test_the_sites_search_stays_shut_while_a_chart_has_the_keys(page):
    _press_in(page, 0, "s")
    assert page.evaluate("window.__searches") == 0

    page.locator("#after").focus()
    page.keyboard.press("s")
    assert page.evaluate("window.__searches") == 1


def test_the_focus_ring_survives_a_page_that_removes_them(page):
    page.locator(_PLOT).first.focus()
    outline = page.evaluate(
        "() => { const s = getComputedStyle(document.activeElement);"
        " return [s.outlineStyle, parseFloat(s.outlineWidth)]; }"
    )
    assert outline == ["solid", 3]


def test_maidr_names_the_chart_and_its_title_describes_it(page):
    described = page.evaluate(
        """() => [...document.querySelectorAll('figure[id^="maidr-figure"] > [tabindex]')].map(plot => {
             const svg = plot.querySelector('svg');
             const ids = (plot.getAttribute('aria-describedby') || '').split(' ');
             return {
               label: plot.getAttribute('aria-label') || '',
               description: ids.map(id => (document.getElementById(id) || {}).textContent).join(' '),
               svgHidden: svg.getAttribute('aria-hidden'),
               svgRole: svg.getAttribute('role'),
             };
           })"""
    )
    assert [d["description"] for d in described] == ["First", "Second"]
    for d in described:
        assert d["label"].startswith("This is a maidr plot")
        assert d["svgHidden"] == "true"
        assert d["svgRole"] is None


def test_shift_tab_from_the_first_chart_hands_the_reader_to_its_slide(page):
    """Not to the browser's own controls, where no key reaches the deck."""
    page.locator(_PLOT).first.focus()
    page.keyboard.press("Shift+Tab")
    assert page.evaluate("document.activeElement.tagName") == "SECTION"


def test_high_contrast_paints_the_chart_not_the_page(page):
    page_colour = page.evaluate("getComputedStyle(document.body).backgroundColor")
    _press_in(page, 0, "c")
    painted = page.evaluate(
        "() => [getComputedStyle(document.body).backgroundColor,"
        " document.querySelector('.maidr-inline').style.backgroundColor]"
    )
    assert painted[0] == page_colour
    assert painted[1] not in ("", page_colour)

    page.locator("#after").focus()
    page.wait_for_timeout(500)
    cleared = page.evaluate(
        "() => [getComputedStyle(document.body).backgroundColor,"
        " document.querySelector('.maidr-inline').style.backgroundColor]"
    )
    assert cleared == [page_colour, ""]


def test_a_preview_copy_of_a_chart_is_not_a_chart(page):
    """Quarto copies a figure into a popup when a reference to it is hovered."""
    before = page.evaluate(
        "document.querySelectorAll('article[id^=maidr-article-]').length"
    )
    page.evaluate(
        """() => {
             const root = document.createElement('div');
             root.setAttribute('data-tippy-root', '');
             root.appendChild(document.querySelector('.maidr-inline').cloneNode(true));
             document.body.appendChild(root);
           }"""
    )
    page.wait_for_timeout(500)
    copy = page.evaluate(
        """() => {
             const root = document.querySelector('[data-tippy-root]');
             return {
               inert: root.hasAttribute('inert'),
               marked: root.querySelectorAll('[id], [tabindex], [maidr]').length,
               charts: document.querySelectorAll('article[id^=maidr-article-]').length,
             };
           }"""
    )
    assert copy == {"inert": True, "marked": 0, "charts": before}


def test_a_chart_whose_neighbour_was_hidden_still_works(browser, tmp_path, outputs):
    """A cell can hide its output; the next chart carries all it needs."""
    page = _page(browser, tmp_path, f"<section>{outputs[1]}</section>")
    try:
        assert (
            page.evaluate(
                "document.querySelectorAll('article[id^=maidr-article-]').length"
            )
            == 1
        )
        _press_in(page, 0, "ArrowRight")
        assert _announced(page)
    finally:
        page.close()
