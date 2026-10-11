"""Charts written into a page Quarto renders work as they did in frames (#895).

``tests/core/test_quarto_inline.py`` pins the markup. This opens it: a page
shaped like what Quarto's Jupyter engine writes, with the two charts' cell
outputs in it, as a reader's browser does. The page has what a real one has
that a frame kept from the chart:

* an AMD ``define`` in the head, as require.js puts there, which takes the
  UMD ``maidr.js`` for a module and never runs it unless kept from it;
* a deck that moves on ArrowRight unless its ``keyboardCondition`` says no,
  with a search plugin on Ctrl+Shift+F, as reveal.js does, and a search
  that opens on ``s`` through ``window.quartoOpenSearch``, as a Quarto
  website's does;
* a stylesheet that takes every focus ring away.

A second page is the same without the deck, where Ctrl+Shift+F and Shift+Tab
are the page's and the browser's. On a third, a chart is in a card shown full
screen, which Escape pressed anywhere leaves, as a Quarto dashboard's is.

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

_AMD = """
  // require.js, as far as a UMD bundle can tell: takes it, never runs it.
  window.__amdCalls = 0;
  window.define = function () { window.__amdCalls += 1; };
  window.define.amd = {};
"""

_DECK = """
  // A deck: ArrowRight moves on unless keyboardCondition says no. It has
  // reveal.js's search plugin, which opens on Ctrl+Shift+F.
  window.Reveal = (function () {
    var config = {}, ready = false, onReady = [];
    window.__slide = 0;
    window.__configured = 0;
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
      configure: function (c) {
        window.__configured += 1;
        for (var k in c) config[k] = c[k];
      },
      getConfig: function () { return config; },
      hasPlugin: function (id) { return id === 'search'; },
      isReady: function () { return ready; },
      isFocused: function () { return true; },
      on: function (name, f) { if (name === 'ready') onReady.push(f); }
    };
  })();
"""

_PAGE_KEYS = """
  // Ctrl+Shift+F, from a listener of its own: reveal.js's search plugin in a
  // deck, any page's shortcut elsewhere.
  window.__ctrlShiftF = 0;
  document.addEventListener('keydown', function (event) {
    if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'f') {
      window.__ctrlShiftF += 1;
    }
  });

  // A Quarto website's search: opens on s, looked up when the key is let go.
  window.__searches = 0;
  window.quartoOpenSearch = window.__pageSearch = function () {
    window.__searches += 1;
  };
  document.addEventListener('keyup', function (event) {
    if (event.key === 's') window.quartoOpenSearch();
  });

  // Whether anything took Shift+Tab from the browser.
  document.addEventListener('keydown', function (event) {
    if (event.key === 'Tab') window.__tabPrevented = event.defaultPrevented;
  });
"""

# A maidr.js that keeps the page's shortcuts off a chart's keys itself says
# so in ``maidrLive.features``. The bundled one is made to say it, and
# ``__bundleGuards`` is whether it said so already.
_NATIVE_GUARDS = """
  (function () {
    var live;
    Object.defineProperty(window, 'maidrLive', {
      configurable: true,
      get: function () { return live; },
      set: function (value) {
        window.__bundleGuards = !!(value.features && value.features.hostGuards >= 1);
        value.features = Object.freeze({ hostGuards: 1 });
        live = value;
      }
    });
  })();
"""

_CARD = """
  // A card shown full screen, as bslib's: Escape pressed anywhere leaves it,
  // through a listener on the document the card keeps on its instance.
  window.__escapes = 0;
  window.__card = {
    _exitFullScreenOnEscape: function (event) {
      if (event.key === 'Escape') window.__escapes += 1;
    }
  };
  window.__cardEscape = window.__card._exitFullScreenOnEscape;
  document.addEventListener('keydown', window.__cardEscape, false);
  window.bslib = { Card: { getInstance: function (element) {
    return element.matches('.bslib-card') ? window.__card : undefined;
  } } };
"""

# What a maidr.js that guards the page itself has wrapped, which it marks.
_MARKED = """
  Reveal.__maidrHostGuard = true;
  window.quartoOpenSearch.__maidrHostGuard = true;
  window.__card.__maidrHostGuard = true;
"""


# A reader's 40-cell braille display, the commonest size, saved as maidr's
# settings dialog saves it.
_FORTY_CELLS = """
  try {
    localStorage.setItem('maidr-settings', JSON.stringify(
      { general: { brailleDisplayKind: 'manual', brailleDisplaySize: 40 } }));
  } catch (e) {}
"""


def _head(*scripts: str) -> str:
    """The scripts, and a stylesheet that takes every focus ring away."""
    return (
        f"<script>{''.join(scripts)}</script>"
        "<style>*:focus { outline: none !important; }</style>"
    )


_HEAD = _head(_AMD, _DECK, _PAGE_KEYS)
#: A page that is not a deck: no reveal.js.
_PLAIN_HEAD = _head(_AMD, _PAGE_KEYS)


def _deck(outputs: list[str]) -> str:
    """Each output on a slide of its own, as reveal.js lays a deck out."""
    slides = "".join(f"<section>{html}</section>" for html in outputs)
    return f"<div class='reveal'><div class='slides'>{slides}</div></div>"


def _carded(outputs: list[str]) -> str:
    """A deck whose first chart is in a card shown full screen."""
    card = f"<div class='bslib-card card' data-full-screen='true'>{outputs[0]}</div>"
    return _deck([card, *outputs[1:]])


def _line(title: str):
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot([1, 2, 3], [3.0, 1.0, 2.0], gid="series")
    ax.set_title(title)
    return fig


class _Kernel:
    """The part of a kernel's IPython shell a render reads and writes."""

    def __init__(self) -> None:
        self.user_ns: dict = {}

    def push(self, variables: dict, interactive: bool = True) -> None:
        self.user_ns.update(variables)


def _outputs(tmp_path: Path, *, same_figure: bool = False) -> list[str]:
    """Two charts, rendered as the kernel of a Quarto ``html`` render does.

    With ``same_figure``, one figure rendered twice, as ``show()`` called on
    it twice renders it.
    """
    info = tmp_path / "info.json"
    info.write_text(
        json.dumps(
            {"format": {"pandoc": {"to": "html"}, "execute": {"fig-format": "retina"}}}
        )
    )
    kernel = _Kernel()
    env = {"QUARTO_FIG_FORMAT": "png", "QUARTO_EXECUTE_INFO": str(info)}
    outputs = []
    with (
        mock.patch.dict("os.environ", env),
        mock.patch.object(Environment, "is_notebook", return_value=True),
        mock.patch("IPython.get_ipython", return_value=kernel),
    ):
        if same_figure:
            fig = _line("Twice")
            try:
                for _ in range(2):
                    outputs.append(
                        str(FigureManager.get_maidr(fig).render(use_cdn=False))
                    )
            finally:
                plt.close(fig)
        for title in () if same_figure else ("First", "Second"):
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


def _page(browser: Browser, tmp_path: Path, body: str, head: str = _HEAD) -> Page:
    path = tmp_path / "doc.html"
    path.write_text(
        f"<!doctype html><html lang='en'><head>{head}</head><body>{body}"
        "<button id='after'>After</button></body></html>",
        encoding="utf-8",
    )
    page = browser.new_page(viewport={"width": 1100, "height": 900})
    page.on("console", lambda m: page.__dict__.setdefault("logs", []).append(m.text))
    page.goto(path.as_uri(), wait_until="load")
    page.wait_for_function(
        "() => document.querySelectorAll('.maidr-inline[data-maidr-inline]').length"
        " === 0"
        " && document.querySelectorAll('article[id^=maidr-article-]').length > 0",
        timeout=_PARSE_TIMEOUT_MS,
    )
    return page


@pytest.fixture
def page(browser, tmp_path, outputs):
    page = _page(browser, tmp_path, _deck(outputs))
    yield page
    page.close()


@pytest.fixture
def plain_page(browser, tmp_path, outputs):
    """The same charts on a page that is not a deck."""
    body = "".join(f"<section>{html}</section>" for html in outputs)
    page = _page(browser, tmp_path, body, head=_PLAIN_HEAD)
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


def test_reveal_search_stays_shut_while_a_chart_has_the_keys(page):
    _press_in(page, 0, "Control+Shift+F")
    assert page.evaluate("window.__ctrlShiftF") == 0

    page.locator("#after").focus()
    page.keyboard.press("Control+Shift+F")
    assert page.evaluate("window.__ctrlShiftF") == 1


def test_a_full_screen_card_stays_open_while_a_chart_has_the_keys(
    browser, tmp_path, outputs
):
    """Escape in a chart closes maidr's own modes, not the card's full screen."""
    head = _head(_AMD, _DECK, _PAGE_KEYS, _CARD)
    page = _page(browser, tmp_path, _carded(outputs), head=head)
    try:
        _press_in(page, 0, "Escape")
        assert page.evaluate("window.__escapes") == 0

        page.locator("#after").focus()
        page.keyboard.press("Escape")
        assert page.evaluate("window.__escapes") == 1
    finally:
        page.close()


def test_ctrl_shift_f_is_the_pages_where_it_is_not_a_decks_search(plain_page):
    """Kept from a page, it is kept from maidr.js, where a reader may bind it."""
    _press_in(plain_page, 0, "Control+Shift+F")
    assert plain_page.evaluate("window.__ctrlShiftF") == 1


def test_the_charts_stylesheets_are_in_the_head_once(page):
    """Not in the slide, where reveal.js's search rewrites the words it finds."""
    placed = page.evaluate(
        """() => ({
             inCharts: document.querySelectorAll('.maidr-inline style').length,
             shared: document.head.querySelectorAll('style[data-maidr-inline-css]').length,
           })"""
    )
    assert placed == {"inCharts": 0, "shared": 1}


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
    # The wrapper's stand-in name went once maidr.js named the chart.
    assert page.evaluate(
        "[...document.querySelectorAll('.maidr-inline')]"
        ".map(w => w.getAttribute('role') || w.getAttribute('aria-label'))"
    ) == [None, None]


def test_shift_tab_from_the_first_chart_hands_the_reader_to_its_slide(page):
    """Not to the browser's own controls, where no key reaches the deck."""
    page.locator(_PLOT).first.focus()
    page.keyboard.press("Shift+Tab")
    assert page.evaluate("document.activeElement.tagName") == "SECTION"


def test_shift_tab_is_the_browsers_on_a_page_that_is_not_a_deck(plain_page):
    """There the elements above a chart are its wrappers or the page's."""
    plain_page.locator(_PLOT).first.focus()
    plain_page.keyboard.press("Shift+Tab")
    after = plain_page.evaluate(
        """() => ({
             prevented: window.__tabPrevented,
             active: document.activeElement.tagName,
             given: document.querySelectorAll('section[tabindex]').length,
           })"""
    )
    assert after["prevented"] is False
    assert after["active"] != "SECTION"
    assert after["given"] == 0


_BODY_COLOURS = (
    "() => { const s = getComputedStyle(document.body);"
    " return [s.backgroundColor, s.color]; }"
)

# Walks up from the plot to the first element with a background of its own.
_BEHIND_THE_PLOT = """plot => {
  const clear = ['rgba(0, 0, 0, 0)', 'transparent'];
  let node = plot;
  while (node && clear.includes(getComputedStyle(node).backgroundColor)) {
    node = node.parentElement;
  }
  return {
    inChart: !!node && plot.closest('.maidr-inline').contains(node),
    colour: node ? getComputedStyle(node).backgroundColor : '',
  };
}"""


def test_high_contrast_paints_the_chart_not_the_page(page):
    """What the reader sees, whichever element maidr.js paints.

    maidr.js 4.14 paints the body, and inline.js gives the page its colours
    back and the chart's wrapper maidr's; a maidr.js that paints the chart's
    own article leaves inline.js nothing to do.
    """
    page.add_style_tag(
        content="body { background: rgb(250, 240, 230); color: rgb(20, 20, 20); }"
    )
    page_colours = page.evaluate(_BODY_COLOURS)
    _press_in(page, 0, "c")

    assert page.evaluate(_BODY_COLOURS) == page_colours
    behind = page.locator(_PLOT).first.evaluate(_BEHIND_THE_PLOT)
    assert behind["inChart"], behind
    assert behind["colour"] != page_colours[0]

    page.locator("#after").focus()
    page.wait_for_timeout(500)
    assert page.evaluate(_BODY_COLOURS) == page_colours
    still_painted = page.evaluate(
        """() => [...document.querySelectorAll(
             '.maidr-inline, article[id^="maidr-article-"]')]
           .filter(e => e.style.backgroundColor || e.style.color).length"""
    )
    assert still_painted == 0


def test_maidrs_settings_fields_keep_room_for_their_text(page):
    """MUI's own, sized with content-box: the braille field's rule is not theirs."""
    _press_in(page, 0, "Control+Comma")
    field = page.locator('[role="dialog"] input.MuiInputBase-input').first
    field.wait_for(state="visible")
    size = field.evaluate(
        """f => {
             const s = getComputedStyle(f);
             return {
               sizing: s.boxSizing,
               text: f.clientHeight
                 - parseFloat(s.paddingTop) - parseFloat(s.paddingBottom),
               font: parseFloat(s.fontSize),
             };
           }"""
    )
    assert size["sizing"] == "content-box"
    assert size["text"] >= size["font"], size


def test_the_braille_and_review_fields_keep_to_a_narrow_column(
    browser, tmp_path, outputs
):
    """At the 320px a page reflows to (WCAG 1.4.10), with a 40-cell display.

    Each field is wider than the chart's column there without inline.css.
    """
    head = _head(_FORTY_CELLS, _AMD, _DECK, _PAGE_KEYS)
    page = _page(browser, tmp_path, f"<section>{outputs[0]}</section>", head=head)
    try:
        page.set_viewport_size({"width": 320, "height": 740})
        for key, field, cols in (
            ("b", 'textarea[id^="maidr-braille-textarea"]', 40),
            ("r", 'input[id^="maidr-review-input"]', None),
        ):
            _press_in(page, 0, key)
            fits = page.locator(field).evaluate(
                """f => {
                     const wrapper = f.closest('.maidr-inline');
                     const page = document.documentElement;
                     return {
                       cols: f.cols || null,
                       inWrapper: f.getBoundingClientRect().right
                         <= wrapper.getBoundingClientRect().right + 0.5,
                       noScroll: page.scrollWidth <= window.innerWidth,
                     };
                   }"""
            )
            expected = {"cols": cols, "inWrapper": True, "noScroll": True}
            assert fits == expected, (key, fits)
            page.keyboard.press(key)
    finally:
        page.close()


def test_a_maidr_js_that_guards_the_page_itself_is_left_to_it(
    browser, tmp_path, outputs
):
    """Told so by ``maidrLive.features``, inline.js wraps nothing of the page's.

    What is wrapped, if anything, is maidr.js's own, which marks it. A
    bundled maidr.js that only says so, guarding nothing, leaves every key to
    the page: inline.js neither stops Ctrl+Shift+F nor hands Shift+Tab to the
    slide.
    """
    head = _head(_NATIVE_GUARDS, _AMD, _DECK, _PAGE_KEYS, _CARD)
    page = _page(browser, tmp_path, _carded(outputs), head=head)
    try:
        assert page.evaluate("window.maidrLive.features.hostGuards") == 1
        for key in ("ArrowRight", "s", "Escape", "Control+Shift+F", "Shift+Tab"):
            _press_in(page, 0, key)
        wrapped_here = page.evaluate(
            """() => ({
                 configured: window.__configured,
                 reveal: !!Reveal.__maidrInline && !Reveal.__maidrHostGuard,
                 search: window.quartoOpenSearch !== window.__pageSearch
                   && !window.quartoOpenSearch.__maidrHostGuard,
                 card: __card._exitFullScreenOnEscape !== __cardEscape
                   && !__card.__maidrHostGuard,
               })"""
        )
        assert wrapped_here == {
            "configured": 0,
            "reveal": False,
            "search": False,
            "card": False,
        }
        if not page.evaluate("window.__bundleGuards"):
            reached = page.evaluate(
                """() => ({
                     slide: window.__slide,
                     searches: window.__searches,
                     escapes: window.__escapes,
                     ctrlShiftF: window.__ctrlShiftF,
                     tabPrevented: window.__tabPrevented,
                   })"""
            )
            assert reached == {
                "slide": 1,
                "searches": 1,
                "escapes": 1,
                "ctrlShiftF": 1,
                "tabPrevented": False,
            }
    finally:
        page.close()


def test_what_maidr_js_has_guarded_is_not_guarded_again(browser, tmp_path, outputs):
    """An object marked ``__maidrHostGuard`` is maidr.js's, whatever it says."""
    head = _head(_AMD, _DECK, _PAGE_KEYS, _CARD, _MARKED)
    page = _page(browser, tmp_path, _carded(outputs), head=head)
    try:
        for key in ("ArrowRight", "s", "Escape"):
            _press_in(page, 0, key)
        left = page.evaluate(
            """() => ({
                 configured: window.__configured,
                 search: window.quartoOpenSearch === window.__pageSearch,
                 card: __card._exitFullScreenOnEscape === __cardEscape,
               })"""
        )
        assert left == {"configured": 0, "search": True, "card": True}
    finally:
        page.close()


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


def _highlights_own(page: Page, charts: int) -> None:
    for chart in range(charts):
        _press_in(page, chart, "ArrowRight")
        owner = page.evaluate(
            """() => {
                 const svgs = [...document.querySelectorAll('figure[id^="maidr-figure"] svg')];
                 return [...document.querySelectorAll('[id^="maidr-highlight-"]')]
                   .map(m => svgs.indexOf(m.closest('svg')));
               }"""
        )
        assert owner and set(owner) == {chart}, f"chart {chart} highlighted {owner}"


def test_an_output_shown_twice_gets_ids_of_its_own(browser, tmp_path, outputs):
    """One cell's output twice on a page: each copy highlights its own marks."""
    body = f"<section>{outputs[0]}</section><section>{outputs[0]}</section>"
    page = _page(browser, tmp_path, body)
    try:
        ids = page.evaluate(
            "[...document.querySelectorAll('figure[id^=maidr-figure] svg')].map(s => s.id)"
        )
        assert len(ids) == 2 and ids[0] != ids[1]
        _highlights_own(page, 2)
        assert not [log for log in getattr(page, "logs", []) if "resolved to no" in log]
    finally:
        page.close()


def test_an_output_added_again_after_load_gets_ids_of_its_own(page, outputs):
    """Its scripts do not run then; the copy is renamed as it arrives."""
    page.evaluate(
        "(html) => document.body.insertAdjacentHTML('beforeend', html)", outputs[0]
    )
    page.wait_for_function(
        "() => document.querySelectorAll('article[id^=maidr-article-]').length === 3",
        timeout=_PARSE_TIMEOUT_MS,
    )
    _highlights_own(page, 3)


def test_a_preview_of_a_figure_on_another_page_keeps_what_it_draws_with(
    browser, tmp_path, outputs
):
    """Quarto fetches that page; its definitions are nowhere else on this one."""
    page = _page(browser, tmp_path, f"<section>{outputs[0]}</section>")
    try:
        page.evaluate(
            """(html) => {
                 const root = document.createElement('div');
                 root.setAttribute('data-tippy-root', '');
                 root.innerHTML = html;
                 document.body.appendChild(root);
               }""",
            outputs[1],
        )
        page.wait_for_timeout(500)
        copy = page.evaluate(
            """() => {
                 const root = document.querySelector('[data-tippy-root]');
                 const refs = [...root.querySelectorAll('use')]
                   .map(u => u.getAttribute('xlink:href') || u.getAttribute('href'));
                 return {
                   inert: root.hasAttribute('inert'),
                   bound: root.querySelectorAll('[maidr], [tabindex]').length,
                   resolved: refs.length > 0 && refs.every(r => root.querySelector(r)),
                   charts: document.querySelectorAll('article[id^=maidr-article-]').length,
                 };
               }"""
        )
        assert copy == {"inert": True, "bound": 0, "resolved": True, "charts": 1}
    finally:
        page.close()


def test_one_figure_shown_twice_highlights_in_each_output(browser, tmp_path):
    """py-maidr mints a figure's group ids once, not each time it renders it."""
    twice = _outputs(tmp_path, same_figure=True)
    page = _page(
        browser, tmp_path, "".join(f"<section>{html}</section>" for html in twice)
    )
    try:
        _highlights_own(page, 2)
    finally:
        page.close()
