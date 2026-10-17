"""A chart in a Shiny app takes the size its output is given.

Shiny's stylesheet makes a UI output a pass-through container once it has
children (``display: contents``), so the size ``output_maidr`` put on it went
with its box as soon as a chart arrived; ``render_maidr``'s size was never
read outside Express; and the chart's frame was the figure's canvas plus the
page margins, whatever the output: a 390px phone scrolled the whole page
sideways by 300px, a card was filled to half, and a Plotly figure collapsed
to 134px, then grew 50px with every key.

These hold what a reader sees, in Chromium, for each way of sizing a chart
(``apps/shiny_size_app.py``):

* nothing scrolls the page sideways on a phone;
* an output's height is honoured, the chart fitted inside it, maidr's text
  line inside it too;
* a fillable card is filled, the chart scaled up to it and centred, and
  follows full screen and a narrower window without the server drawing it
  again;
* ``render_maidr(width=500, height=300)`` gives a 500x300 box, as
  ``render.plot`` does;
* a Plotly figure is as tall as plotly.js draws one, and stays so;

and that after each of these the chart still takes the focus, with a ring
that shows, announces what ArrowRight moves to, and highlights that mark.
"""

from __future__ import annotations

import time

import pytest

pytestmark = pytest.mark.browser

CHART = "[role=img], [role=application]"

#: The default figure's chart as a notebook shows the plain figure: 6.4 by
#: 4.8 inches at 100 dpi, cut to what is drawn.
_OWN = (557, 463)

#: The bars, in the order ArrowRight walks them.
_FRUIT = ("Apples", "Bananas", "Cherries", "Dates", "Elderberries")

#: Where everything about the output is measured, in page pixels.
_GEOMETRY = r"""(oid) => {
  const R = (r, dx = 0, dy = 0) => r && ({
    left: r.left + dx, top: r.top + dy, right: r.right + dx,
    bottom: r.bottom + dy, width: r.width, height: r.height});
  const out = document.getElementById(oid || 'm');
  const frame = out.querySelector('iframe');
  const box = out.querySelector('.maidr-shiny-box') || out;
  const doc = frame && frame.contentDocument;
  const f = frame && frame.getBoundingClientRect();
  const svg = doc && doc.querySelector('svg.maidr-frame-svg, svg.main-svg, figure svg');
  const text = doc && doc.getElementById('maidr-text-container');
  const page = document.scrollingElement;
  return {
    pageScroll: page.scrollWidth - page.clientWidth,
    viewport: window.innerWidth,
    out: R(out.getBoundingClientRect()),
    box: R(box.getBoundingClientRect()),
    boxClient: [box.clientWidth, box.clientHeight],
    boxScroll: [box.scrollWidth, box.scrollHeight],
    boxShown: R({left: box.getBoundingClientRect().left + box.clientLeft,
                 top: box.getBoundingClientRect().top + box.clientTop,
                 right: box.getBoundingClientRect().left + box.clientLeft + box.clientWidth,
                 bottom: box.getBoundingClientRect().top + box.clientTop + box.clientHeight,
                 width: box.clientWidth, height: box.clientHeight}),
    frame: R(f),
    frameInner: frame && [frame.contentWindow.innerWidth, frame.contentWindow.innerHeight],
    svg: svg && R(svg.getBoundingClientRect(), f.left, f.top),
    text: text && text.textContent.trim() ? R(text.getBoundingClientRect(), f.left, f.top) : null,
    src: frame && frame.getAttribute('src'),
    scrollY: window.scrollY,
  };
}"""

#: What the reader is told and shown once ArrowRight has moved them. The
#: bars are the chart's ``g[maidr]`` groups, left to right; the highlight is
#: drawn inside the one it lights.
_READING = r"""() => {
  const alert = document.querySelector('#maidr-text-container [role=alert], [role=alert]');
  const lit = document.querySelector('[id^=maidr-highlight]');
  const box = e => { const r = e.getBoundingClientRect();
                     return [r.left, r.top, r.right, r.bottom]; };
  const bars = [...document.querySelectorAll('svg g[maidr]')]
    .sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left);
  const owner = lit && lit.closest('g[maidr]');
  const focused = document.activeElement;
  const ring = focused && getComputedStyle(focused);
  return {
    said: alert ? alert.textContent.trim() : '',
    lit: lit && box(lit), mark: owner && box(owner),
    litBar: owner ? bars.indexOf(owner) : -1,
    focused: focused ? (focused.getAttribute('role') || focused.tagName) : null,
    ring: ring ? [ring.outlineStyle, parseFloat(ring.outlineWidth)] : null,
  };
}"""


def _open(browser, url: str, width: int, height: int = 900, oid: str = "m"):
    page = browser.new_page(viewport={"width": width, "height": height})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url)
    page.wait_for_selector(f"#{oid} iframe", timeout=30_000)
    # Attached rather than visible: maidr.js's focusable element for a
    # Plotly chart has no height of its own.
    page.frame_locator(f"#{oid} iframe").locator(CHART).first.wait_for(
        state="attached", timeout=30_000
    )
    _settle(page, oid=oid)
    page.errors = errors  # type: ignore[attr-defined]
    return page


def _settle(
    page, quiet_ms: int = 1200, timeout_ms: int = 15_000, oid: str = "m"
) -> dict:
    """Wait until the output's geometry stops changing, and return it."""
    last, still, waited = None, 0, 0
    while waited < timeout_ms:
        seen = page.evaluate(_GEOMETRY, oid)
        key = repr({k: seen[k] for k in ("box", "frame", "svg")})
        still = still + 200 if key == last else 0
        if still >= quiet_ms:
            return seen
        last = key
        page.wait_for_timeout(200)
        waited += 200
    return page.evaluate(_GEOMETRY, oid)


def _chart_frame(page, oid: str | None = None):
    if oid is not None:
        return page.query_selector(f"#{oid} iframe").content_frame()
    for frame in page.frames[1:]:
        if frame.locator(CHART).count():
            return frame
    raise AssertionError("no chart frame on the page")


def _read(page, presses: int = 1, oid: str | None = None) -> dict:
    """Focus the chart, press ArrowRight, and say what the reader got."""
    frame = _chart_frame(page, oid)
    frame.locator(CHART).first.focus()
    page.wait_for_timeout(400)
    for _ in range(presses):
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(300)
    page.wait_for_timeout(600)
    return frame.evaluate(_READING)


def _assert_reads(page, where: str, oid: str | None = None) -> None:
    reading = _read(page, oid=oid)
    assert reading["focused"] in ("img", "application"), (where, reading)
    assert reading["ring"][0] != "none" and reading["ring"][1] >= 2, (where, reading)
    # The first press says the first bar; a later one, the bar it moves to.
    said = [
        i for i, fruit in enumerate(_FRUIT) if f"Fruit is {fruit}" in reading["said"]
    ]
    assert said, (where, reading)
    assert reading["lit"] is not None, f"{where}: nothing is highlighted"
    # The bar announced is the one lit, and the highlight covers it.
    assert reading["litBar"] == said[0], (where, reading)
    assert reading["lit"] == pytest.approx(reading["mark"], abs=1), where


def _inside(inner: dict, outer: dict, slack: float = 1) -> bool:
    return (
        inner["left"] >= outer["left"] - slack
        and inner["top"] >= outer["top"] - slack
        and inner["right"] <= outer["right"] + slack
        and inner["bottom"] <= outer["bottom"] + slack
    )


def _ratio(rect: dict) -> float:
    return rect["width"] / rect["height"]


@pytest.mark.parametrize("case", ["default", "wide"])
def test_a_phone_never_scrolls_the_page_sideways(browser, shiny_size_app_url, case):
    """At 390px the chart shrinks to the output, keeping its shape."""
    page = _open(browser, f"{shiny_size_app_url}/{case}/", 390)
    try:
        seen = page.evaluate(_GEOMETRY)
        assert seen["pageScroll"] == 0, seen
        assert seen["frame"]["right"] <= seen["viewport"], seen
        assert _inside(seen["svg"], seen["out"]), seen
        assert seen["svg"]["width"] == pytest.approx(seen["out"]["width"], abs=1)
        _assert_reads(page, f"{case} at 390px")
        assert page.evaluate(_GEOMETRY)["pageScroll"] == 0
    finally:
        page.close()


def test_a_wide_page_shows_the_chart_at_its_own_size(browser, shiny_size_app_url):
    """With room to spare, the chart is the plain figure's size, not stretched."""
    page = _open(browser, f"{shiny_size_app_url}/default/", 1280)
    try:
        seen = page.evaluate(_GEOMETRY)
        assert (seen["svg"]["width"], seen["svg"]["height"]) == pytest.approx(
            _OWN, abs=2
        )
        assert seen["box"]["height"] == pytest.approx(seen["frame"]["height"], abs=1)
    finally:
        page.close()


@pytest.mark.parametrize("height", [300, 600])
@pytest.mark.parametrize("width", [1280, 390])
def test_an_outputs_height_is_honoured(browser, shiny_size_app_url, height, width):
    """The chart is fitted inside the output, maidr's text line with it."""
    page = _open(browser, f"{shiny_size_app_url}/h{height}/", width)
    try:
        seen = page.evaluate(_GEOMETRY)
        assert seen["out"]["height"] == pytest.approx(height, abs=1), seen
        assert seen["pageScroll"] == 0, seen
        assert _inside(seen["svg"], seen["box"]), seen
        # The shape kept, as large as the box allows.
        assert _ratio(seen["svg"]) == pytest.approx(_OWN[0] / _OWN[1], rel=0.01)
        assert (
            seen["svg"]["width"] == pytest.approx(seen["box"]["width"], abs=1)
            or seen["svg"]["height"] >= height - 60
        ), seen

        _assert_reads(page, f"h{height} at {width}px")
        _chart_frame(page).locator(CHART).first.focus()
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(800)
        seen = page.evaluate(_GEOMETRY)
        assert seen["text"] is not None, "maidr's text is not shown"
        assert _inside(seen["text"], seen["box"]), (
            "maidr's text line is cut off by the output",
            seen,
        )
        # Nothing needed scrolling to: the line was kept for it.
        assert seen["boxScroll"][1] <= seen["boxClient"][1] + 1, seen
        assert seen["out"]["height"] == pytest.approx(height, abs=1), seen
    finally:
        page.close()


def _full_screen(page, enter: bool) -> None:
    page.evaluate(
        """(enter) => {
          const button = enter
            ? document.querySelector('#card .bslib-full-screen-enter')
            : document.querySelector('.bslib-full-screen-exit');
          button.click();
        }""",
        enter,
    )
    page.wait_for_timeout(600)


def _assert_fills(seen: dict, where: str) -> None:
    """Fitted as object-fit: contain fits an image, a line kept below."""
    box, svg = seen["box"], seen["svg"]
    assert _inside(svg, box), (where, seen)
    assert _ratio(svg) == pytest.approx(_OWN[0] / _OWN[1], rel=0.01), where
    # As large as the box allows: its width, or its height less the line.
    width_bound = svg["width"] >= box["width"] - 2
    height_bound = svg["height"] >= box["height"] - 60
    assert width_bound or height_bound, (where, seen)
    # Centred across it.
    assert svg["left"] - box["left"] == pytest.approx(
        box["right"] - svg["right"], abs=2
    ), (where, seen)


def test_a_card_is_filled_and_followed_without_drawing_again(
    browser, shiny_size_app_url
):
    """Full screen and a narrower window refit the chart, with no new render."""
    page = _open(browser, f"{shiny_size_app_url}/card/", 1280)
    try:
        seen = page.evaluate(_GEOMETRY)
        src = seen["src"]
        _assert_fills(seen, "in the card")
        # Scaled up past its own size: the card is larger.
        assert seen["svg"]["width"] > _OWN[0] + 100, seen
        _assert_reads(page, "in the card")

        _full_screen(page, True)
        full = _settle(page)
        _assert_fills(full, "full screen")
        assert full["box"]["width"] > seen["box"]["width"], full
        _assert_reads(page, "full screen")
        _full_screen(page, False)
        back = _settle(page)
        assert back["svg"] == pytest.approx(seen["svg"], abs=1)

        page.set_viewport_size({"width": 700, "height": 900})
        narrow = _settle(page)
        _assert_fills(narrow, "at 700px")
        assert narrow["svg"]["width"] < seen["svg"]["width"], narrow
        assert narrow["pageScroll"] == 0, narrow
        _assert_reads(page, "at 700px")

        assert page.evaluate(_GEOMETRY)["src"] == src, "the chart was drawn again"
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


def test_render_maidrs_size_is_the_charts_box(browser, shiny_size_app_url):
    """``@render_maidr(width=500, height=300)``, as ``@render.plot(...)``."""
    page = _open(browser, f"{shiny_size_app_url}/renderer/", 1280)
    try:
        seen = page.evaluate(_GEOMETRY)
        assert (seen["box"]["width"], seen["box"]["height"]) == pytest.approx(
            (500, 300), abs=1
        ), seen
        _assert_fills(seen, "in a 500x300 box")
        _assert_reads(page, "in a 500x300 box")
    finally:
        page.close()


def test_a_plotly_chart_keeps_its_height(browser, shiny_size_app_url):
    """As tall as plotly.js draws a figure, through a dozen key presses."""
    page = _open(browser, f"{shiny_size_app_url}/plotly/", 1280)
    try:
        frame = _chart_frame(page)
        frame.locator(CHART).first.focus()
        page.wait_for_timeout(400)
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(800)
        first = page.evaluate(_GEOMETRY)
        assert first["svg"]["height"] == pytest.approx(450, abs=2), first
        assert "Apples" in frame.evaluate(_READING)["said"]
        heights = []
        for _ in range(12):
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(350)
            heights.append(page.evaluate(_GEOMETRY)["frame"]["height"])
        assert max(heights) - min(heights) <= 1, heights
        assert heights[-1] <= first["frame"]["height"] + 1, heights
        assert page.evaluate(_GEOMETRY)["pageScroll"] == 0
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


def test_a_bokeh_plot_wider_than_a_phone_is_reached_by_scrolling_its_box(
    browser, shiny_size_app_url
):
    """A 600px canvas at 390px: the output scrolls to it, the page does not.

    The frame was as wide as the output and did not scroll, so the right
    half of the canvas could not be reached at all.
    """
    page = _open(browser, f"{shiny_size_app_url}/bokeh/", 390)
    try:
        page.wait_for_timeout(1500)
        seen = page.evaluate(_GEOMETRY)
        assert seen["pageScroll"] == 0, seen
        assert seen["frame"]["width"] >= 600, seen
        assert seen["boxScroll"][0] >= 600 > seen["boxClient"][0], seen
        frame = _chart_frame(page)
        frame.locator(CHART).first.focus()
        page.wait_for_timeout(400)
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(800)
        assert "Apples" in frame.evaluate(_READING)["said"]
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


# ---------------------------------------------------------------------------
# maidr's dialogs, scrollbars that take room, long announcements
# ---------------------------------------------------------------------------

#: maidr's open dialog, in page pixels, with its Close button and how much of
#: its text it shows.
_DIALOG = r"""() => {
  const frame = document.querySelector('#m iframe');
  const doc = frame.contentDocument;
  const paper = doc.querySelector('.MuiDialog-paper');
  if (!paper) return null;
  const f = frame.getBoundingClientRect();
  const R = r => ({left: r.left + f.left, top: r.top + f.top,
                   right: r.right + f.left, bottom: r.bottom + f.top});
  const close = [...paper.querySelectorAll('button')]
    .find(b => b.textContent.trim() === 'Close');
  const text = paper.querySelector('.MuiDialogContent-root') || paper;
  return {paper: R(paper.getBoundingClientRect()),
          close: close && R(close.getBoundingClientRect()),
          text: text.clientHeight};
}"""


#: How the output and its box are laid out, and the chart's size in the frame
#: against its own.
_LAID_OUT = r"""() => {
  const out = document.getElementById('m');
  const box = out.querySelector('.maidr-shiny-box');
  const frame = out.querySelector('iframe');
  const svg = frame.contentDocument.querySelector('svg.maidr-frame-svg');
  const r = svg.getBoundingClientRect();
  return {out: getComputedStyle(out).display, box: getComputedStyle(box).display,
          frame: frame.getBoundingClientRect().height,
          frameWidth: frame.getBoundingClientRect().width,
          svg: [r.width, r.height],
          own: [svg.width.baseVal.value, svg.height.baseVal.value]};
}"""


def _assert_as_before_fitting(page, where: str) -> dict:
    """The output and its box pass-through containers, the chart its own size.

    As every output was before charts were fitted to their outputs: Shiny
    makes a UI output that has children ``display: contents``. The frame is
    laid out as a notebook's: the chart at its own size, or as wide as the
    frame where that is narrower, keeping its shape, and the frame at least
    as tall as the chart.
    """
    laid = page.evaluate(_LAID_OUT)
    assert laid["out"] == "contents" and laid["box"] == "contents", (where, laid)
    width = min(laid["own"][0], laid["frameWidth"])
    shape = laid["own"][1] / laid["own"][0]
    assert laid["svg"] == pytest.approx([width, width * shape], abs=1), (where, laid)
    assert laid["frame"] >= laid["svg"][1], (where, laid)
    return laid


@pytest.mark.parametrize("width", [1280, 390])
def test_a_dialog_has_the_room_it_had_before_charts_were_fitted(
    browser, shiny_size_app_url, width
):
    """Help in a 300px output: while it is open, the output is not fitted.

    Kept to the box, help showed 104px of its text in a 300px output; room,
    placement and scrolling of its own for a dialog in a fitted box cut
    another dialog off, or moved the page as it closed. While a dialog is
    open, the output is set aside, as before charts were fitted, and the
    frame laid out as a notebook's: help shows at least the 349px of its
    text it did then; the output is fitted again as it closes.
    """
    page = _open(browser, f"{shiny_size_app_url}/h300/", width, height=900)
    try:
        _read(page)
        page.keyboard.press("Control+/")
        page.wait_for_timeout(1500)
        _settle(page)
        dialog = page.evaluate(_DIALOG)
        assert dialog is not None, "no dialog opened"
        _assert_as_before_fitting(page, "help open")
        # As much of its text as before charts were fitted (349px), all of
        # it and its Close button in the window, the output being at the
        # page's top.
        assert dialog["text"] >= 340, dialog
        for part in ("paper", "close"):
            assert dialog[part]["top"] >= 0 and dialog[part]["bottom"] <= 900, dialog

        page.keyboard.press("Escape")
        page.wait_for_timeout(1200)
        back = _settle(page)
        assert page.evaluate(_DIALOG) is None
        laid = page.evaluate(_LAID_OUT)
        assert laid["out"] == "flex" and laid["box"] == "block", laid
        assert back["out"]["height"] == pytest.approx(300, abs=1), back
        assert back["box"]["height"] == pytest.approx(300, abs=1), back
        assert back["frame"]["height"] <= 300, back
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


#: How much of an element in the chart's frame is shown, in page pixels:
#: cut by the frame, by every container of it that clips, and, unless
#: ``inPage`` (what scrolling the page would show), by the window.
_SHOWN = r"""([selector, inPage]) => {
  const frame = document.querySelector('#m iframe');
  const el = frame.contentDocument.querySelector(selector);
  if (!el) return null;
  const f = frame.getBoundingClientRect();
  const r = el.getBoundingClientRect();
  let top = Math.max(r.top + f.top, f.top, inPage ? -Infinity : 0);
  let bottom = Math.min(
    r.bottom + f.top, f.bottom, inPage ? Infinity : window.innerHeight);
  for (let a = frame.parentElement; a && a !== document.body; a = a.parentElement) {
    const style = getComputedStyle(a);
    // A pass-through container has no box of its own to clip with.
    if (style.overflowY === 'visible' || style.display === 'contents') continue;
    const ar = a.getBoundingClientRect();
    top = Math.max(top, ar.top + a.clientTop);
    bottom = Math.min(bottom, ar.top + a.clientTop + a.clientHeight);
  }
  return {height: r.height, shown: Math.max(0, bottom - top)};
}"""


@pytest.mark.parametrize(
    ("case", "width"),
    [
        ("card_fluid_h300", 1280),
        ("card_fluid_h300", 390),
        ("card", 390),
        ("sidebar", 390),
    ],
)
@pytest.mark.parametrize("key", ["Control+/", "Control+,"])
def test_a_dialog_is_shown_whole_in_a_card_that_follows_its_content(
    browser, shiny_size_app_url, case, width, key
):
    """Help and settings in a card, or a sidebar layout, as tall as its content.

    A card's body clips the output and grows with it. The dialog was kept
    to the body's height, which was the chart's own: help showed 104px of
    its text in a 300px output, in a card of a page that is not fillable,
    and on a phone, where bslib gives up filling, in every card (110px) and
    sidebar layout (65px); settings' Close button was below what showed.
    The output is set aside while it is open, the frame laid out as a
    notebook's, and the dialog is all in view.
    """
    page = _open(browser, f"{shiny_size_app_url}/{case}/", width, height=800)
    try:
        _read(page)
        own = _settle(page)["box"]["height"]
        page.keyboard.press(key)
        page.wait_for_timeout(1500)
        _settle(page)
        dialog = page.evaluate(_DIALOG)
        assert dialog is not None, "no dialog opened"
        _assert_as_before_fitting(page, f"{key} open")
        assert dialog["text"] >= (300 if key == "Control+/" else 250), dialog
        page.evaluate(
            "() => [...document.querySelector('#m iframe').contentDocument"
            ".querySelectorAll('.MuiDialog-paper button')]"
            ".find(b => b.textContent.trim() === 'Close')"
            ".setAttribute('data-close', '')"
        )
        for part in (".MuiDialog-paper", "[data-close]"):
            shown = page.evaluate(_SHOWN, [part, False])
            assert shown["shown"] >= shown["height"] - 1, (part, shown, dialog)

        page.keyboard.press("Escape")
        page.wait_for_timeout(1200)
        back = _settle(page)
        assert page.evaluate(_DIALOG) is None
        assert back["box"]["height"] == pytest.approx(own, abs=1), (own, back)
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


#: The window's part of the chart's frame, and whether the focus is in it.
_IN_VIEW = r"""() => {
  const frame = document.querySelector('#m iframe');
  const f = frame.getBoundingClientRect();
  const doc = frame.contentDocument;
  const a = doc.activeElement;
  return {top: f.top, bottom: f.bottom, height: f.height, window: innerHeight,
          scrollY: window.scrollY,
          focused: document.activeElement === frame && a && a.getAttribute('role')};
}"""


def _assert_in_view(page, where: str) -> dict:
    """The chart's frame wholly in the window, and the focus in the chart."""
    seen = page.evaluate(_IN_VIEW)
    assert seen["top"] >= -1 and seen["bottom"] <= seen["window"] + 1, (where, seen)
    assert seen["focused"] in ("img", "application"), (where, seen)
    return seen


@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("key", ["Control+/", "Control+,"])
def test_closing_a_dialog_halfway_down_a_long_page_leaves_the_chart_in_view(
    browser, shiny_size_app_url, width, key
):
    """The frame is centred in the window while a dialog is open.

    It is as tall as the window while the dialog is open, as a notebook's
    frame is, and goes back to its box as it closes, the page with it to
    where it was: the chart, which has the focus back, is in view, its box
    its own height again.
    """
    page = _open(browser, f"{shiny_size_app_url}/tall_page/", width, height=800)
    try:
        page.evaluate(
            "() => document.querySelector('#m iframe')"
            ".scrollIntoView({block: 'center', behavior: 'instant'})"
        )
        page.wait_for_timeout(400)
        _read(page)
        before = _settle(page)
        assert before["scrollY"] > 100, before
        page.keyboard.press(key)
        page.wait_for_timeout(1500)
        _settle(page)
        assert page.evaluate(_DIALOG) is not None, "no dialog opened"

        page.keyboard.press("Escape")
        page.wait_for_timeout(1200)
        back = _settle(page)
        assert page.evaluate(_DIALOG) is None
        _assert_in_view(page, "after the dialog closed")
        assert back["box"]["height"] == pytest.approx(300, abs=1), back
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


#: The page's scroll position, the frame's top, and the highlighted mark's
#: top in the window and the share of it on screen.
_LIT = r"""() => {
  const frame = document.querySelector('#m iframe');
  const f = frame.getBoundingClientRect();
  const lit = frame.contentDocument.querySelector('[id^=maidr-highlight]');
  const r = lit && lit.getBoundingClientRect();
  const top = r && r.top + f.top, bottom = r && r.bottom + f.top;
  const shown = r && r.height
    ? Math.max(0, Math.min(bottom, innerHeight) - Math.max(top, 0)) / r.height : null;
  return {scrollY: window.scrollY, frameTop: f.top, litTop: top, litShown: shown,
          focused: document.activeElement === frame};
}"""


#: The page scrolled so that the chart's frame's top is this far down the
#: window.
_FRAME_TOP_AT = (
    "(at) => window.scrollBy({top: document.querySelector('#m iframe')"
    ".getBoundingClientRect().top - at, behavior: 'instant'})"
)


@pytest.mark.parametrize(
    ("case", "size", "scrolled"),
    [
        ("tall_plotly_h400", (844, 390), None),
        ("tall_plotly", (1280, 900), None),
        ("tall_plotly", (1280, 900), -200),
        ("tall_plotly_auto", (844, 390), -30),
    ],
    ids=["phone-turned", "tall-figure", "tall-figure-read", "phone-turned-read"],
)
def test_closing_a_dialog_over_a_plotly_chart_taller_than_the_window_leaves_it_be(
    browser, shiny_size_app_url, case, size, scrolled
):
    """Help opens and closes over a Plotly chart the window cannot show whole.

    Help is scrolled into view as it opens, as a notebook's is, and kept to
    the window's height in the frame's middle, which scrolls the line a
    Plotly chart takes the focus on, at its top, above the window. As help
    closes, the chart is given the focus back, and the browser scrolled
    the page to that line, centring it: the chart 450px down a 900px
    window, 195px down a phone's, the mark the reader had highlighted 18-45%
    shown, and none of it after the next key. Nothing scrolls as help
    closes now: the page stays where help had it, and the mark is in view.
    """
    page = _open(browser, f"{shiny_size_app_url}/{case}/", *size)
    try:
        page.evaluate(_FRAME_TOP_AT, 10)
        page.wait_for_timeout(400)
        _read(page, presses=2)
        if scrolled is not None:
            page.evaluate(_FRAME_TOP_AT, scrolled)
            page.wait_for_timeout(600)
        before = page.evaluate(_LIT)
        assert before["litShown"] is not None and before["litShown"] > 0, before
        page.keyboard.press("Control+/")
        page.wait_for_timeout(1500)
        _settle(page)
        _assert_dialog_whole(page, "help open")
        opened = page.evaluate(_LIT)

        page.keyboard.press("Escape")
        page.wait_for_timeout(1500)
        _settle(page)
        back = page.evaluate(_LIT)
        assert page.evaluate(_DIALOG) is None
        assert back["focused"], back
        assert back["scrollY"] == pytest.approx(opened["scrollY"], abs=1), (
            opened,
            back,
        )
        assert back["litShown"] >= min(before["litShown"], 0.95), (before, back)
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(700)
        moved = page.evaluate(_LIT)
        assert moved["litShown"] >= 0.95, (before, back, moved)
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


def _open_help_halfway_down(page) -> dict:
    """The tall page's chart in the middle of the window, help open over it."""
    page.evaluate(
        "() => document.querySelector('#m iframe')"
        ".scrollIntoView({block: 'center', behavior: 'instant'})"
    )
    page.wait_for_timeout(400)
    _read(page)
    before = _settle(page)
    assert before["scrollY"] > 100, before
    page.keyboard.press("Control+/")
    page.wait_for_timeout(1500)
    _settle(page)
    assert page.evaluate(_DIALOG) is not None, "no dialog opened"
    return before


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ((390, 800), (800, 390)),
        ((1280, 900), (640, 450)),
        ((1280, 900), (853, 600)),
        ((1280, 900), (1280, 500)),
        ((1280, 800), (390, 800)),
    ],
    ids=["phone-turned", "zoom-200", "zoom-150", "shorter", "narrower"],
)
def test_closing_a_dialog_after_the_window_changed_size_shows_the_chart(
    browser, shiny_size_app_url, start, end
):
    """The window changes size while help is open, then the reader closes it.

    The page was put back to the offsets it had as help opened, measured in
    a layout the new size had replaced, and the chart, which still had the
    focus, was left partly or wholly off screen: its frame's top at 324px
    of a 450px window zoomed to 200%, at 561px of an 800px one narrowed to
    390px, and at -902px on a longer page. An arrow key did not bring it
    back. Nothing is put back now: the chart, its box its own height again,
    is where help left it, in view, and so is the mark the reader had
    highlighted.
    """
    page = _open(browser, f"{shiny_size_app_url}/tall_page/", *start)
    try:
        page.evaluate(
            "() => document.querySelector('#m iframe')"
            ".scrollIntoView({block: 'center', behavior: 'instant'})"
        )
        page.wait_for_timeout(400)
        _read(page, presses=2)
        page.keyboard.press(_HELP)
        page.wait_for_timeout(1500)
        _settle(page)
        assert page.evaluate(_DIALOG) is not None, "no dialog opened"
        page.set_viewport_size({"width": end[0], "height": end[1]})
        page.wait_for_timeout(1500)
        _settle(page)

        page.keyboard.press("Escape")
        page.wait_for_timeout(1200)
        back = _settle(page)
        assert page.evaluate(_DIALOG) is None
        lit = page.evaluate(_LIT)
        assert lit["litShown"] is not None and lit["litShown"] >= 0.95, (end, lit)
        assert back["box"]["height"] == pytest.approx(300, abs=1), back
        focused = _chart_frame(page, "m").evaluate(
            "() => document.activeElement && document.activeElement.getAttribute('role')"
        )
        assert focused in ("img", "application"), focused
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


def _replaced(page, change, oid: str = "m") -> None:
    """Do ``change``, and wait for the output's new frame to show its chart."""
    page.evaluate(
        "(oid) => document.querySelector(`#${oid} iframe`).dataset.old = ''", oid
    )
    change()
    page.wait_for_selector(f"#{oid} iframe:not([data-old])", timeout=15_000)
    page.frame_locator(f"#{oid} iframe").locator(CHART).first.wait_for(
        state="attached", timeout=30_000
    )


@pytest.mark.parametrize("width", [1280, 390])
def test_a_chart_drawn_again_under_a_dialog_does_not_move_the_page(
    browser, shiny_size_app_url, width
):
    """The output is drawn again while help is open, as live data would.

    The output goes back to its own height at once, as it does when the
    dialog closes, and nothing is put back: the page had been put back,
    later, by the next frame in the output, from places kept for it that
    never expired. The page moves only as the browser keeps what the window
    shows in place round the output that changed height, and the chart is
    in view.
    """
    page = _open(browser, f"{shiny_size_app_url}/tall_drawn_again/", width, 800)
    try:
        _open_help_halfway_down(page)
        _replaced(
            page,
            lambda: page.evaluate(
                "() => Shiny.setInputValue('again', 1, {priority: 'event'})"
            ),
        )
        page.wait_for_timeout(1200)
        back = _settle(page)
        assert back["box"]["height"] == pytest.approx(300, abs=1), back
        assert back["out"]["height"] == pytest.approx(300, abs=1), back
        frame = back["frame"]
        assert frame["top"] >= -1 and frame["bottom"] <= 801, back
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


@pytest.mark.parametrize("width", [1280, 390])
def test_a_chart_emptied_under_a_dialog_lets_its_output_go(
    browser, shiny_size_app_url, width
):
    """The output is emptied while help is open, and the chart comes back later.

    The output was held at the dialog's height, 800px of blank page, until
    a chart came back; and the chart that came back, after the reader had
    gone on to read elsewhere, put the page back to where it was as help
    opened, 1123px away.
    """
    page = _open(browser, f"{shiny_size_app_url}/tall_emptied/", width, 800)
    try:
        _open_help_halfway_down(page)
        page.evaluate("() => Shiny.setInputValue('shown', 0)")
        page.wait_for_function(
            "() => !document.querySelector('#m iframe')", timeout=15_000
        )
        page.wait_for_timeout(1000)
        out = page.evaluate(
            "() => document.getElementById('m').getBoundingClientRect().height"
        )
        assert out == pytest.approx(300, abs=1), out

        page.evaluate("() => window.scrollTo({top: 0, behavior: 'instant'})")
        page.wait_for_timeout(400)
        page.evaluate("() => Shiny.setInputValue('shown', 1)")
        page.wait_for_selector("#m iframe", timeout=15_000)
        page.frame_locator("#m iframe").locator(CHART).first.wait_for(
            state="attached", timeout=30_000
        )
        page.wait_for_timeout(1200)
        back = _settle(page)
        assert back["scrollY"] == 0, back
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


#: How much of maidr's open dialog, and of its Close button, is on screen:
#: cut by the frame, every container of it that clips, and the window, both
#: ways. With the dialog's width, and its text shown and in all.
_DIALOG_SHOWN = r"""() => {
  const frame = document.querySelector('#m iframe');
  const doc = frame.contentDocument;
  const paper = doc.querySelector('.MuiDialog-paper');
  if (!paper) return null;
  const close = [...paper.querySelectorAll('button')]
    .find(b => b.textContent.trim() === 'Close');
  const f = frame.getBoundingClientRect();
  const shown = (el) => {
    const r = el.getBoundingClientRect();
    let top = Math.max(r.top + f.top, f.top, 0);
    let bottom = Math.min(r.bottom + f.top, f.bottom, innerHeight);
    let left = Math.max(r.left + f.left, f.left, 0);
    let right = Math.min(r.right + f.left, f.right, innerWidth);
    for (let a = frame.parentElement; a && a !== document.body; a = a.parentElement) {
      const s = getComputedStyle(a);
      if (s.display === 'contents') continue;
      const ar = a.getBoundingClientRect();
      if (s.overflowY !== 'visible') {
        top = Math.max(top, ar.top + a.clientTop);
        bottom = Math.min(bottom, ar.top + a.clientTop + a.clientHeight);
      }
      if (s.overflowX !== 'visible') {
        left = Math.max(left, ar.left + a.clientLeft);
        right = Math.min(right, ar.left + a.clientLeft + a.clientWidth);
      }
    }
    return Math.max(0, bottom - top) * Math.max(0, right - left) / (r.width * r.height);
  };
  const text = paper.querySelector('.MuiDialogContent-root') || paper;
  // The rows of the paper on screen that something of the page's is drawn
  // over, down its middle: a header fixed or sticky at the window's top.
  const p = paper.getBoundingClientRect();
  let covered = 0;
  for (let y = Math.ceil(Math.max(p.top + f.top, 0));
       y < Math.min(p.bottom + f.top, innerHeight); y += 2) {
    if (document.elementFromPoint(p.left + f.left + p.width / 2, y) !== frame) {
      covered += 2;
    }
  }
  return {paper: shown(paper), close: close ? shown(close) : null,
          covered: covered,
          width: paper.getBoundingClientRect().width,
          text: text.clientHeight, textAll: text.scrollHeight,
          sideways: document.scrollingElement.scrollWidth
            - document.scrollingElement.clientWidth};
}"""

#: How far the page, and the box that scrolls round the chart, are scrolled.
_SCROLLED = r"""() => {
  const box = document.getElementById('scroller');
  return {page: window.scrollY, box: box ? box.scrollTop : null};
}"""

#: Where the chart's frame is put in the window before a dialog opens.
_PLACE = r"""(where) => {
  const frame = document.querySelector('#m iframe');
  const box = document.getElementById('scroller');
  const r = frame.getBoundingClientRect();
  if (box && where === 'boxtop') {
    box.scrollTop = 0;
    box.scrollIntoView({block: 'center', behavior: 'instant'});
    return;
  }
  if (box) {
    const b = box.getBoundingClientRect();
    box.scrollBy({top: r.top + r.height / 2 - (b.top + b.height / 2),
                  behavior: 'instant'});
    box.scrollIntoView({block: 'center', behavior: 'instant'});
    return;
  }
  const by = where === 'bottom' ? r.bottom - innerHeight + 10
    : where === 'top' ? r.top - 10
    : where === 'end' ? document.scrollingElement.scrollHeight
    : r.top + r.height / 2 - innerHeight / 2;
  window.scrollBy({top: by, behavior: 'instant'});
}"""


def _assert_dialog_whole(page, where: str) -> dict:
    """maidr's dialog, and its Close button, wholly on screen."""
    shown = page.evaluate(_DIALOG_SHOWN)
    assert shown is not None, (where, "no dialog opened")
    assert shown["paper"] >= 0.99 and shown["close"] >= 0.99, (where, shown)
    assert shown["sideways"] == 0, (where, shown)
    assert shown["covered"] == 0, (where, shown)
    return shown


#: Every scroll position the page and the boxes round the chart's frame
#: take from now on, frame by frame, but where one only went as far as it
#: still can: the frame, fitted to its output again, is shorter than it is
#: while a dialog is open, and a page scrolled to its end ends higher.
_WATCH_CLOSE = r"""() => {
  const frame = document.querySelector('#m iframe');
  const scrollers = [document.scrollingElement];
  for (let a = frame.parentElement; a && a !== document.body; a = a.parentElement) {
    scrollers.push(a);
  }
  const at = scrollers.map(el => el.scrollTop);
  window.maidrClose = {at: at.map(Math.round), moved: []};
  const note = () => {
    scrollers.forEach((el, i) => {
      const end = el.scrollHeight - el.clientHeight;
      const clamped = el.scrollTop < at[i] && el.scrollTop >= end - 1;
      if (Math.abs(el.scrollTop - at[i]) > 1 && !clamped) {
        window.maidrClose.moved.push([i, Math.round(el.scrollTop)]);
      }
    });
    requestAnimationFrame(note);
  };
  note();
}"""


def _assert_nothing_scrolled(page, where: str) -> None:
    """Neither the page nor a box round the frame moved since _WATCH_CLOSE."""
    close = page.evaluate("() => window.maidrClose")
    assert close["moved"] == [], (where, close)


_HELP, _SETTINGS = "Control+/", "Control+,"


@pytest.mark.parametrize(
    ("case", "where", "size", "key"),
    [
        ("tall_page", "bottom", (1280, 900), _HELP),
        ("tall_page", "bottom", (1280, 900), _SETTINGS),
        ("tall_page", "bottom", (390, 844), _HELP),
        ("tall_page", "bottom", (390, 844), _SETTINGS),
        # Settings is taller than this window: MUI squeezes it, as it did.
        ("tall_page", "centre", (640, 450), _HELP),
        ("page_end", "end", (1280, 900), _HELP),
        ("page_end", "end", (1280, 900), _SETTINGS),
        ("page_end_plotly", "end", (1280, 900), _HELP),
        ("page_end_plotly", "end", (1280, 900), _SETTINGS),
        ("scroll_box", "centre", (1280, 900), _HELP),
        ("scroll_box", "centre", (1280, 900), _SETTINGS),
        ("scroll_box", "boxtop", (1280, 900), _HELP),
        ("tall_plotly_h400", "top", (844, 390), _HELP),
        # A Bokeh plot of a fixed width wider than a phone.
        ("bokeh", "centre", (390, 844), _HELP),
        ("fixed_navbar", "centre", (1280, 900), _HELP),
        ("fixed_navbar", "bottom", (390, 844), _HELP),
        ("fixed_navbar_plotly", "centre", (1280, 700), _HELP),
        ("fixed_navbar", "centre", (1280, 900), _SETTINGS),
    ],
    ids=[
        "bottom-1280-help",
        "bottom-1280-settings",
        "bottom-phone-help",
        "bottom-phone-settings",
        "short-window-help",
        "page-end-help",
        "page-end-settings",
        "page-end-plotly-help",
        "page-end-plotly-settings",
        "scroll-box-help",
        "scroll-box-settings",
        "scroll-box-at-its-top-help",
        "plotly-phone-turned-help",
        "bokeh-fixed-width-phone-help",
        "fixed-navbar-help",
        "fixed-navbar-phone-help",
        "fixed-navbar-plotly-help",
        "fixed-navbar-settings",
    ],
)
def test_a_dialog_is_shown_whole_wherever_the_chart_is(
    browser, shiny_size_app_url, case, where, size, key
):
    """Help and settings, the chart where a reader leaves it, shown whole.

    The chart fitted to its output, a reader scrolls just far enough to see
    it, or reads it at the page's end, in a box that scrolls, or in a
    window shorter than the chart's frame is while a dialog is open. Laid
    out as before fitting, but from where the fitted chart was, the frame
    grew down past the window: help showed 47% of itself and none of its
    Close button with the chart's bottom at the window's, 33% at the page's
    end, where the page jumped up 67-269px as it opened; in a box that
    scrolls its Close button was 0-56% shown; over a Bokeh plot wider than
    a phone the frame was the plot's width, and the dialog, centred in it,
    64% across the window. The frame is laid out as a
    notebook's while a dialog is open, its room and its scrolling into
    view included, as before charts were fitted, below a navbar fixed at
    the window's top, which covered the top 24px of help's title. On
    closing it, the chart is fitted again, with its highlight in view, and
    the focus back in it, and nothing is scrolled: neither the page nor the
    box moves from where help had them.
    """
    page = _open(browser, f"{shiny_size_app_url}/{case}/", *size)
    try:
        page.evaluate(
            "() => document.querySelector('#m iframe')"
            ".scrollIntoView({block: 'center', behavior: 'instant'})"
        )
        page.wait_for_timeout(300)
        _read(page, presses=2)
        own = _settle(page)
        page.evaluate(_PLACE, where)
        page.wait_for_timeout(500)
        page.keyboard.press(key)
        page.wait_for_timeout(1500)
        _settle(page)
        _assert_dialog_whole(page, f"{key} open")
        page.evaluate(_WATCH_CLOSE)

        page.keyboard.press("Escape")
        page.wait_for_timeout(1500)
        back = _settle(page)
        assert page.evaluate(_DIALOG) is None
        _assert_nothing_scrolled(page, "as it closed")
        lit = page.evaluate(_LIT)
        assert lit["focused"], lit
        # A Bokeh plot's highlight is drawn on its canvas, not in the page.
        if not case.startswith("bokeh"):
            assert lit["litShown"] is not None and lit["litShown"] >= 0.95, lit
        assert back["box"]["height"] == pytest.approx(own["box"]["height"], abs=1)
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


@pytest.mark.parametrize(
    "size", [(1280, 500), (640, 450), (844, 390)], ids=["short", "zoom-200", "phone"]
)
def test_closing_a_dialog_leaves_the_page_where_it_is(
    browser, shiny_size_app_url, size
):
    """A chart whose bottom is below the window, focused there, and read.

    Help opens, scrolled into view, and closes. The page went back to where
    it was, and the browser, giving the chart the focus back, then scrolled
    on to show the chart's bottom: 24-40px further down than the reader had
    left it. Nothing scrolls as help closes now: the page stays where help
    had it, the chart's highlight in view there.
    """
    page = _open(browser, f"{shiny_size_app_url}/tall_page/", *size)
    try:
        page.evaluate(_PLACE, "bottom")
        page.wait_for_timeout(500)
        _read(page, presses=2)
        page.wait_for_timeout(600)
        before = page.evaluate(_LIT)
        page.keyboard.press(_HELP)
        page.wait_for_timeout(1500)
        _settle(page)
        _assert_dialog_whole(page, "help open")
        page.evaluate(_WATCH_CLOSE)

        page.keyboard.press("Escape")
        page.wait_for_timeout(1500)
        _settle(page)
        back = page.evaluate(_LIT)
        assert page.evaluate(_DIALOG) is None
        assert back["focused"], back
        _assert_nothing_scrolled(page, "as help closed")
        # As much of it as help left in view: on a phone turned on its
        # side the frame was taller than the window under help.
        assert back["litShown"] >= min(before["litShown"], 0.95), (before, back)
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


@pytest.mark.parametrize("size", [(1280, 900), (390, 844)], ids=["1280", "phone"])
def test_help_over_a_plotly_chart_reached_with_tab_is_shown_whole(
    browser, shiny_size_app_url, size
):
    """A reader Tabs into a default Plotly output on a long page and asks for help.

    The browser shows as much of the chart as fits as the focus comes to
    it; help, centred in the frame, had its Close button below the window,
    at 1280px and on a phone. Closing it scrolls nothing, the highlight in
    view.
    """
    page = _open(browser, f"{shiny_size_app_url}/tall_plotly_auto/", *size)
    try:
        page.evaluate(
            "() => { const b = document.createElement('button'); b.id = 'pre';"
            " b.textContent = 'Before'; const card = document.getElementById('m')"
            ".closest('.card'); card.parentElement.insertBefore(b, card);"
            " window.scrollTo({top: 0, behavior: 'instant'});"
            " b.focus({preventScroll: true}); }"
        )
        page.wait_for_timeout(400)
        page.keyboard.press("Tab")
        page.wait_for_timeout(1000)
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(800)
        _settle(page)
        before = page.evaluate(_LIT)
        page.keyboard.press("Control+/")
        page.wait_for_timeout(1500)
        _settle(page)
        _assert_dialog_whole(page, "help open")
        page.evaluate(_WATCH_CLOSE)
        page.keyboard.press("Escape")
        page.wait_for_timeout(1500)
        _settle(page)
        # Where help left the page, the highlight as much in view as it was.
        lit = page.evaluate(_LIT)
        assert lit["focused"], lit
        _assert_nothing_scrolled(page, "as help closed")
        assert lit["litShown"] >= before["litShown"] - 0.01, (before, lit)
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


@pytest.mark.parametrize("how", ["wheel", "script"])
def test_a_scroll_just_after_a_dialog_closes_is_kept(browser, shiny_size_app_url, how):
    """The page is scrolled 300ms after help closes, by the reader or the app.

    For a second after a dialog closed, the page was put back to where it
    was as the dialog opened whenever something scrolled it that no wheel,
    touch, key or pointer of the reader's had started: an app's own
    ``window.scrollBy`` snapped back at once, and so would a link to an
    anchor or a screen reader's cursor. Nothing about the page is kept as a
    dialog opens now, so nothing is put back, and the reader's own wheel
    is kept as it was.
    """
    page = _open(browser, f"{shiny_size_app_url}/tall_page/", 1280, 900)
    try:
        _open_help_halfway_down(page)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        closed = page.evaluate("() => window.scrollY")
        if how == "wheel":
            page.mouse.move(8, 450)
            page.mouse.wheel(0, -250)
        else:
            page.evaluate("() => window.scrollBy({top: -250, behavior: 'instant'})")
        page.wait_for_timeout(1500)
        assert page.evaluate(_DIALOG) is None
        scrolled = page.evaluate("() => window.scrollY")
        slack = 50 if how == "wheel" else 1
        assert scrolled == pytest.approx(closed - 250, abs=slack), (closed, scrolled)
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


#: A block this tall put above the chart's card, or below it, as a live log,
#: a chat or a table that grows would.
_GROW = r"""([where, px]) => {
  const block = document.createElement('div');
  block.style.height = px + 'px';
  const out = document.getElementById('m');
  const card = out.closest('.card');
  if (where === 'above') card.parentElement.insertBefore(block, card);
  else if (where === 'inbox') out.after(block);
  else document.body.appendChild(block);
}"""


@pytest.mark.parametrize("case", ["tall_page", "tall_plotly_auto"])
def test_content_growing_above_the_chart_under_a_dialog_leaves_the_chart_be(
    browser, shiny_size_app_url, case
):
    """600px are added above the chart's card while help is open over it.

    The browser keeps what the window shows where it is as the page above it
    grows. As help closed, the page was put back to the offset it had as
    help opened: the chart 600px further down than it had been, its
    highlight off screen. The chart stays where it was now, its highlight
    in view.
    """
    page = _open(browser, f"{shiny_size_app_url}/{case}/", 1280, 900)
    try:
        # Room below the chart: a page that ends close below it ends higher
        # once the frame is fitted again, and its end moves the chart.
        page.evaluate(_GROW, ["below", 1500])
        page.evaluate(
            "() => document.querySelector('#m iframe')"
            ".scrollIntoView({block: 'center', behavior: 'instant'})"
        )
        page.wait_for_timeout(400)
        _read(page, presses=2)
        page.keyboard.press(_HELP)
        page.wait_for_timeout(1500)
        _settle(page)
        _assert_dialog_whole(page, "help open")
        page.evaluate(_GROW, ["above", 600])
        page.wait_for_timeout(600)
        during = page.evaluate(_LIT)

        page.keyboard.press("Escape")
        page.wait_for_timeout(1500)
        _settle(page)
        back = page.evaluate(_LIT)
        assert page.evaluate(_DIALOG) is None
        assert back["focused"], back
        assert back["frameTop"] == pytest.approx(during["frameTop"], abs=2), (
            during,
            back,
        )
        assert back["litShown"] >= 0.95, (during, back)
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


#: The chart's frame against the window and, where there is one, the box
#: ``#scroller`` that scrolls round it: whether any of it shows, and how much
#: of what could show does, the whole frame or as tall a part of it as the
#: window and the box are.
_FRAME_SHOWN = r"""() => {
  const f = document.querySelector('#m iframe').getBoundingClientRect();
  const box = document.getElementById('scroller');
  const b = box ? box.getBoundingClientRect() : null;
  const bounds = [[0, innerHeight]];
  if (b) bounds.push([b.top + box.clientTop, b.top + box.clientTop + box.clientHeight]);
  const top = Math.max(f.top, ...bounds.map(([t]) => t));
  const bottom = Math.min(f.bottom, ...bounds.map(([, e]) => e));
  const most = Math.min(f.height, ...bounds.map(([t, e]) => e - t));
  return {any: bottom > top, share: Math.max(0, bottom - top) / most};
}"""


@pytest.mark.parametrize("case", ["tall_page", "scroll_box"])
def test_a_chart_out_of_view_as_its_dialog_closes_is_brought_into_view(
    browser, shiny_size_app_url, case
):
    """Help is open, and something scrolls the chart wholly out of view.

    A block added below the chart, and the page, or the box that scrolls
    round it, scrolled to its end, as a script or a reader would. As help
    closes, the chart has the focus back and none of its frame shows: it
    is scrolled into view, the nearest way, as much of it as the window,
    and the box, can show.
    """
    page = _open(browser, f"{shiny_size_app_url}/{case}/", 1280, 900)
    try:
        page.evaluate(_PLACE, "centre")
        page.wait_for_timeout(400)
        _read(page, presses=2)
        page.keyboard.press(_HELP)
        page.wait_for_timeout(1500)
        _settle(page)
        _assert_dialog_whole(page, "help open")
        if case == "scroll_box":
            page.evaluate(_GROW, ["inbox", 1500])
            page.evaluate(
                "() => { const box = document.getElementById('scroller');"
                " box.scrollTo({top: box.scrollHeight, behavior: 'instant'}); }"
            )
        else:
            page.evaluate(_GROW, ["below", 2000])
            page.evaluate(
                "() => window.scrollTo({top: document.scrollingElement.scrollHeight,"
                " behavior: 'instant'})"
            )
        page.wait_for_timeout(600)
        assert not page.evaluate(_FRAME_SHOWN)["any"], "the chart is still in view"

        page.keyboard.press("Escape")
        page.wait_for_timeout(1500)
        _settle(page)
        assert page.evaluate(_DIALOG) is None
        shown = page.evaluate(_FRAME_SHOWN)
        assert shown["share"] >= 0.99, shown
        lit = page.evaluate(_LIT)
        assert lit["focused"], lit
        assert lit["litShown"] >= 0.95, lit
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


def test_settings_has_the_width_it_had_before_charts_were_fitted(
    browser, shiny_size_app_url
):
    """Settings over a chart in a 300px output, in a wide window.

    The frame was the chart's width under the dialog, 557px, and the dialog
    493px, narrower than the 574px it had before charts were fitted: its
    controls took 384px to show, where they had taken 285px, and had to be
    scrolled to. A notebook frame gives a dialog MUI's 600px.
    """
    page = _open(browser, f"{shiny_size_app_url}/h300/", 1280)
    try:
        _read(page)
        page.keyboard.press("Control+,")
        page.wait_for_timeout(1500)
        _settle(page)
        shown = _assert_dialog_whole(page, "settings open")
        assert shown["width"] >= 574, shown
        assert shown["text"] >= shown["textAll"] - 1, shown
        page.keyboard.press("Escape")
        page.wait_for_timeout(1200)
        assert page.evaluate(_DIALOG) is None
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


@pytest.mark.parametrize(
    ("case", "start", "end"),
    [
        ("plotly", (1280, 900), (390, 844)),
        ("plotly_card", (844, 390), (390, 844)),
    ],
    ids=["narrower", "phone-turned"],
)
def test_a_dialog_follows_a_narrower_window(
    browser, shiny_size_app_url, case, start, end
):
    """Help is open over a Plotly chart, and the window narrows.

    The frame kept the width it had as help opened, 1256px in a 390px
    window: the page scrolled sideways and 8% of the dialog showed across
    the window. It follows the window now, as a notebook's frame does.
    """
    page = _open(browser, f"{shiny_size_app_url}/{case}/", *start)
    try:
        _read(page)
        page.keyboard.press("Control+/")
        page.wait_for_timeout(1500)
        _settle(page)
        page.set_viewport_size({"width": end[0], "height": end[1]})
        page.wait_for_timeout(1500)
        _settle(page)
        _assert_dialog_whole(page, "after the window narrowed")
        page.keyboard.press("Escape")
        page.wait_for_timeout(1500)
        back = _settle(page)
        assert back["pageScroll"] == 0, back
    finally:
        page.close()


#: The page's scroll position, and where the slider below the chart and the
#: chart's frame are in the window.
_UNDER = r"""() => {
  const frame = document.querySelector('#m iframe');
  const slider = document.querySelector('#n').closest('.shiny-input-container');
  const f = frame.getBoundingClientRect();
  const s = slider.getBoundingClientRect();
  return {scrollY: window.scrollY, frameTop: f.top, sliderTop: s.top,
          sliderBottom: s.bottom, window: innerHeight,
          value: document.querySelector('#n').value};
}"""

#: Every scroll position the page takes from now on, frame by frame.
_WATCH_SCROLL = r"""() => {
  window.maidrSeenScroll = new Set();
  const note = () => {
    window.maidrSeenScroll.add(Math.round(window.scrollY));
    requestAnimationFrame(note);
  };
  note();
}"""

_SIZES = [(640, 450), (390, 844), (1280, 900)]
_SIZE_IDS = ["zoom-200", "phone", "wide"]


def _slider_near_the_top(page) -> dict:
    """The slider 120px below the window's top, the chart above it."""
    page.evaluate(
        "() => { const s = document.querySelector('#n')"
        ".closest('.shiny-input-container').getBoundingClientRect();"
        " window.scrollBy({top: s.top - 120, behavior: 'instant'}); }"
    )
    page.wait_for_timeout(600)
    before = page.evaluate(_UNDER)
    assert before["frameTop"] < 0, ("the chart's top is in the window", before)
    page.evaluate(_WATCH_SCROLL)
    return before


def _assert_still(page, before: dict, where: str) -> None:
    seen = page.evaluate(_UNDER)
    assert seen["scrollY"] == pytest.approx(before["scrollY"], abs=1), (
        where,
        before,
        seen,
    )
    assert seen["sliderTop"] >= 0 and seen["sliderBottom"] <= seen["window"], (
        where,
        seen,
    )
    moved = page.evaluate("() => [...window.maidrSeenScroll]")
    assert all(abs(y - before["scrollY"]) <= 1 for y in moved), (where, moved)


@pytest.mark.parametrize("size", _SIZES, ids=_SIZE_IDS)
@pytest.mark.parametrize("kind", ["mpl", "plotly", "bokeh", "bokeh_scaled", "altair"])
def test_a_chart_drawn_again_above_the_window_leaves_the_page_still(
    browser, shiny_size_app_url, kind, size
):
    """The reader moves a slider below a chart whose top is above the window.

    The page moved with every redraw, 300-450px at 640x450 (the browser at
    200%), taking the slider and the chart off screen, and crept further
    with each one: the output collapsed as Shiny put the new frame in, the
    frame was measured at no height and at 4000px, and the page was
    scrolled back by what the frame had grown. A Bokeh plot scaled both
    ways, held at the height Bokeh first drew it at, moved the page 497px
    on its first redraw.
    """
    page = _open(browser, f"{shiny_size_app_url}/slider_{kind}/", *size)
    try:
        before = _slider_near_the_top(page)
        for value in (3, 4, 5):
            _replaced(
                page,
                lambda value=value: page.evaluate(
                    "(v) => $('#n').data('ionRangeSlider').update({from: v})", value
                ),
            )
            _settle(page)
            _assert_still(page, before, f"drawn again at {value}")
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


@pytest.mark.parametrize("kind", ["mpl", "plotly", "bokeh", "altair"])
def test_a_slider_moved_with_the_keyboard_stays_where_it_is(
    browser, shiny_size_app_url, kind
):
    """The same with the keyboard, the browser at 200%: ArrowRight, twice.

    The focused slider was taken off screen on the first key, and stayed
    there.
    """
    page = _open(browser, f"{shiny_size_app_url}/slider_{kind}/", 640, 450)
    try:
        before = _slider_near_the_top(page)
        page.focus(".irs-line")
        for value in ("3", "4"):
            _replaced(page, lambda: page.keyboard.press("ArrowRight"))
            _settle(page)
            assert page.evaluate(_UNDER)["value"] == value
            _assert_still(page, before, f"moved to {value}")
        focused = page.evaluate("() => document.activeElement.className")
        assert "irs-line" in focused, focused
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


#: Where the slider's top is in the window from now on, frame by frame.
_WATCH_SLIDER = r"""() => {
  const slider = document.querySelector('#n').closest('.shiny-input-container');
  window.maidrSeenSlider = [];
  const note = () => {
    window.maidrSeenSlider.push(Math.round(slider.getBoundingClientRect().top));
    requestAnimationFrame(note);
  };
  note();
}"""


@pytest.mark.parametrize("kind", ["mpl", "plotly"])
def test_charts_drawn_again_faster_than_they_are_measured_leave_the_slider_still(
    browser, shiny_size_app_url, kind
):
    """Values come faster than each new chart is measured, on a slow device.

    A chart drawn again before the frame drawn last had measured its own
    held the output at that frame's 150px: the slider below it went
    300px up, off screen, for 0.4s (matplotlib) to 3s (Plotly), the
    processor slowed six times, as a phone's is.
    """
    page = _open(browser, f"{shiny_size_app_url}/slider_{kind}/", 640, 450)
    cdp = page.context.new_cdp_session(page)
    try:
        before = _slider_near_the_top(page)
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": 6})
        page.evaluate(_WATCH_SLIDER)
        for value in (3, 4, 5, 6):
            page.evaluate(
                "(v) => Shiny.setInputValue('n', v, {priority: 'event'})", value
            )
            page.wait_for_timeout(250)
        # The last chart is in the page with the text Shiny sends with it,
        # and has let go of its output once measured.
        page.wait_for_function(
            "() => document.getElementById('said').textContent === 'Scale 6'"
            " && !document.getElementById('m').maidrHolds",
            timeout=30_000,
        )
        cdp.send("Emulation.setCPUThrottlingRate", {"rate": 1})
        _settle(page)
        seen = page.evaluate("() => window.maidrSeenSlider")
        assert min(seen) >= 0, (before, sorted(set(seen)))
        _assert_still(page, before, "drawn again four times")
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        cdp.detach()
        page.close()


def test_an_output_not_in_the_page_leaves_the_others_to_update(
    browser, shiny_size_app_url
):
    """An output Shiny computes but has no place for comes first in each update.

    Shiny sends its value to the document itself, and the frame's script,
    holding the output drawn again, threw on it inside Shiny's message
    loop: Shiny reported an error on the client, and neither the chart nor
    the text after it was updated.
    """
    page = _open(browser, f"{shiny_size_app_url}/slider_nowhere/", 1280, 900)
    errors: list[str] = []
    page.on(
        "console", lambda m: errors.append(m.text) if m.type == "error" else None
    )
    try:
        for value in (3, 4):
            _replaced(
                page,
                lambda value=value: page.evaluate(
                    "(v) => $('#n').data('ionRangeSlider').update({from: v})", value
                ),
            )
            page.wait_for_function(
                "(v) => document.getElementById('said').textContent === 'Scale ' + v",
                arg=value,
                timeout=15_000,
            )
        assert errors == [], errors
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


#: The fitted chart, and the element its focus ring is drawn on, against what
#: of the frame shows: its window, and the box's room beside its scrollbar.
_CUT = r"""() => {
  const frame = document.querySelector('#m iframe');
  const box = frame.parentElement;
  const doc = frame.contentDocument;
  const f = frame.getBoundingClientRect();
  const chart = doc.querySelector('svg.maidr-frame-svg').getBoundingClientRect();
  const ring = doc.querySelector('figure[id^="maidr-figure"] > div[tabindex]')
    .getBoundingClientRect();
  return {
    chart: chart.right, ring: ring.right,
    window: frame.contentWindow.innerWidth,
    box: box.getBoundingClientRect().left + box.clientLeft + box.clientWidth - f.left,
    scrollbar: box.offsetWidth - box.clientWidth,
  };
}"""


@pytest.mark.parametrize(
    ("case", "width", "key"),
    [("h360", 390, "b"), ("h360", 390, "r"), ("card", 1280, "b")],
)
def test_a_scrollbar_never_cuts_a_fitted_chart(
    classic_scrollbar_browser, shiny_size_app_url, case, width, key
):
    """With scrollbars that take room, as Windows' do, nothing is cut.

    The braille or review field makes the box scroll; its scrollbar
    narrowed the frame by 15px under a chart fitted to the wider box, which
    kept its width: its right edge, and its focus ring's, were cut off.
    """
    page = _open(classic_scrollbar_browser, f"{shiny_size_app_url}/{case}/", width)
    try:
        frame = _chart_frame(page)

        def assert_whole(when: str) -> dict:
            _settle(page)
            cut = page.evaluate(_CUT)
            for edge in ("chart", "ring"):
                assert cut[edge] <= min(cut["window"], cut["box"]) + 0.5, (
                    when,
                    edge,
                    cut,
                )
            return cut

        frame.locator(CHART).first.focus()
        page.wait_for_timeout(600)
        assert_whole("on focus")
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(600)
        page.keyboard.press(key)
        page.wait_for_timeout(1200)
        cut = assert_whole(f"with {key} open")
        # The braille field is taller than the room kept for the text; the
        # review field, in a box fitted to the opening announcement's three
        # lines, now fits in it, and nothing scrolls to cut.
        if key == "b":
            assert cut["scrollbar"] > 0, ("the box does not scroll", cut)
        page.keyboard.press(key)
        page.wait_for_timeout(1200)
        assert_whole(f"with {key} closed")
    finally:
        page.close()


def test_a_long_announcement_is_shown_in_its_box(browser, shiny_size_app_url):
    """Three lines of text below a chart fitted to a 300px output.

    They are shown whole, in the box, and the page does not move.
    """
    page = _open(browser, f"{shiny_size_app_url}/long_text/", 320)
    try:
        before = page.evaluate(_GEOMETRY)
        _read(page, presses=2)
        seen = _settle(page)
        assert seen["text"] is not None
        assert seen["text"]["height"] > 40, ("the text is one line", seen)
        assert _inside(seen["text"], seen["boxShown"]), seen
        assert seen["scrollY"] == before["scrollY"], "the page moved"
    finally:
        page.close()


@pytest.mark.parametrize(
    ("case", "width", "scrollbars"),
    [
        ("h300", 390, "overlay"),
        ("h300", 390, "classic"),
        ("long_text", 320, "overlay"),
        ("renderer", 1280, "classic"),
    ],
)
def test_the_chart_and_its_text_are_both_shown_as_it_takes_the_focus(
    browser, classic_scrollbar_browser, shiny_size_app_url, case, width, scrollbars
):
    """The chart is fitted above the lines its text takes, not one line.

    What maidr says as the chart takes the focus is two or three lines
    long. Below a chart fitted above one line, the box scrolled 18-36px to
    show it, and the top of the chart, and of its focus ring, went out of
    sight. Kept to the most its text has taken, the chart is not resized
    with each announcement after that.
    """
    chosen = classic_scrollbar_browser if scrollbars == "classic" else browser
    page = _open(chosen, f"{shiny_size_app_url}/{case}/", width)
    try:
        frame = _chart_frame(page)
        frame.locator(CHART).first.focus()
        page.wait_for_timeout(1200)
        seen = _settle(page)
        assert seen["text"] is not None and seen["text"]["height"] > 30, seen
        # The ring is drawn on the svg, inside its edge.
        assert _inside(seen["svg"], seen["boxShown"]), ("ring cut", seen)
        assert _inside(seen["text"], seen["boxShown"]), ("text cut", seen)
        assert seen["boxScroll"][1] <= seen["boxClient"][1] + 1, seen
        focused = seen["svg"]
        for _ in range(3):
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(400)
        seen = _settle(page)
        assert seen["svg"] == pytest.approx(focused, abs=1), (focused, seen)
        assert _inside(seen["svg"], seen["boxShown"]), seen
        assert _inside(seen["text"], seen["boxShown"]), seen
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


# ---------------------------------------------------------------------------
# Plotly and Bokeh in a box with a height of its own
# ---------------------------------------------------------------------------


def _plot_height(page) -> float:
    return _chart_frame(page).evaluate(
        "() => document.querySelector('.js-plotly-plot').getBoundingClientRect().height"
    )


def test_a_plotly_chart_fills_a_card_and_full_screen(browser, shiny_size_app_url):
    """As tall as the card less a line for the text, as main had it.

    It stayed 450px in a 778px card, and in full screen, where main had
    filled them; the height is the card's, not the frame's, so nothing it
    draws grows it, through a dozen key presses.
    """
    page = _open(browser, f"{shiny_size_app_url}/plotly_card/", 1280)
    try:
        seen = page.evaluate(_GEOMETRY)
        assert _plot_height(page) >= seen["box"]["height"] - 60, seen
        assert _plot_height(page) > 600, _plot_height(page)
        _full_screen(page, True)
        full = _settle(page)
        assert _plot_height(page) >= full["box"]["height"] - 60, full
        heights = []
        frame = _chart_frame(page)
        frame.locator(CHART).first.focus()
        page.wait_for_timeout(400)
        for _ in range(12):
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(350)
            seen = page.evaluate(_GEOMETRY)
            heights.append((seen["frame"]["height"], _plot_height(page)))
        assert len(set(heights)) == 1, heights
        seen = _settle(page)
        assert _inside(seen["text"], seen["boxShown"]), seen
        # Past the last bar, maidr says there is no more.
        assert "No more data" in frame.evaluate(_READING)["said"]
        _full_screen(page, False)
        back = _settle(page)
        assert _plot_height(page) >= back["box"]["height"] - 60, back
        # plotly.js throws ("reading 'mo'") when it draws the chart again
        # with a bar highlighted: once, as it leaves full screen, the one
        # redraw here that changes its size.
        errors = page.errors  # type: ignore[attr-defined]
        assert all("'mo'" in error for error in errors), errors
        assert len(errors) <= 1, errors
    finally:
        page.close()


@pytest.mark.parametrize("width", [1280, 390])
def test_a_plotly_charts_frame_follows_its_box(browser, shiny_size_app_url, width):
    """Full screen and back, and a window made shorter and taller.

    plotly.js draws the chart at its new height after a debounce, and the
    frame was measured before it had: entering full screen at 390px left
    the text line below the frame, out of sight, a taller window at 1280px
    likewise, and leaving full screen left the frame as tall as the full
    screen chart had been, 276px of it blank.
    """
    page = _open(browser, f"{shiny_size_app_url}/plotly_card/", width)
    try:
        frame = _chart_frame(page)
        frame.locator(CHART).first.focus()
        page.wait_for_timeout(400)
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(800)

        def assert_text_shown(when: str) -> None:
            seen = _settle(page)
            shown = page.evaluate(_SHOWN, ["#maidr-text-container", True])
            assert shown is not None, when
            assert shown["shown"] >= shown["height"] - 1, (when, shown, seen)
            # And no more: the frame is the chart and its line.
            assert seen["frame"]["height"] <= _plot_height(page) + 60, (when, seen)

        assert_text_shown("in the card")
        _full_screen(page, True)
        assert_text_shown("full screen")
        _full_screen(page, False)
        assert_text_shown("back from full screen")
        page.set_viewport_size({"width": width, "height": 500})
        assert_text_shown("in a 500px window")
        page.set_viewport_size({"width": width, "height": 900})
        assert_text_shown("in a 900px window")
        assert "Apples" in frame.evaluate(_READING)["said"]
    finally:
        page.close()


#: The width plotly.js drew the chart at.
_PLOT_WIDTH = (
    "() => document.querySelector('.js-plotly-plot').getBoundingClientRect().width"
)


@pytest.mark.parametrize(("case", "width"), [("plotly_h400", 390), ("plotly_card", 1280)])
def test_a_plotly_chart_is_not_drawn_again_as_its_box_scrolls(
    classic_scrollbar_browser, shiny_size_app_url, case, width
):
    """With scrollbars that take room, braille and review come and go.

    Each made the box scroll, then stop, narrowing and widening the chart
    by the scrollbar's 15px, and plotly.js drew it again at each width,
    throwing ("reading 'mo'") while a bar was highlighted: four to eight
    times here. The box keeps the scrollbar's room instead.
    """
    page = _open(classic_scrollbar_browser, f"{shiny_size_app_url}/{case}/", width)
    try:
        frame = _chart_frame(page)
        frame.locator(CHART).first.focus()
        page.wait_for_timeout(800)
        widths = {frame.evaluate(_PLOT_WIDTH)}
        for key in ["ArrowRight"] * 3 + ["b", "b", "r", "r"] + ["ArrowRight"] * 3:
            page.keyboard.press(key)
            page.wait_for_timeout(700)
            widths.add(frame.evaluate(_PLOT_WIDTH))
        assert len(widths) == 1, widths
        assert page.errors == []  # type: ignore[attr-defined]
        seen = _settle(page)
        assert _inside(seen["text"], seen["boxShown"]), seen
    finally:
        page.close()


def test_a_plotly_chart_fills_an_outputs_height(browser, shiny_size_app_url):
    page = _open(browser, f"{shiny_size_app_url}/plotly_h400/", 1280)
    try:
        _read(page)
        seen = _settle(page)
        assert _plot_height(page) == pytest.approx(400 - 52, abs=4), seen
        assert seen["boxScroll"][1] <= seen["boxClient"][1] + 1, seen
        assert _inside(seen["text"], seen["boxShown"]), seen
    finally:
        page.close()


def test_a_plotly_chart_without_autosize_keeps_its_width(browser, shiny_size_app_url):
    """``autosize=False``: plotly.js draws it 700px wide whatever its div is.

    It was taken for a chart that fills its container, so the frame never
    widened to it, and at 390px its right half could not be reached.
    """
    page = _open(browser, f"{shiny_size_app_url}/plotly_fixed/", 390)
    try:
        seen = page.evaluate(_GEOMETRY)
        assert seen["frame"]["width"] >= 700, seen
        assert seen["boxScroll"][0] >= 700 > seen["boxClient"][0], seen
        assert seen["pageScroll"] == 0, seen
    finally:
        page.close()


#: How tall Bokeh drew the plot: its root's box, in its shadow DOM's host.
_BOKEH = r"""() => {
  const host = [...document.querySelectorAll('div')].find(e => e.shadowRoot);
  return host ? host.getBoundingClientRect().height : 0;
}"""


@pytest.mark.parametrize("case", ["bokeh_stretched", "bokeh_stretched_card"])
def test_a_stretched_bokeh_plot_is_given_a_height(browser, shiny_size_app_url, case):
    """``sizing_mode="stretch_both"`` collapsed: a 51px frame, no plot.

    Its frame took its height from the plot and the plot from the frame.
    It is now as tall as a box with a height of its own allows, or 450px.
    """
    page = _open(browser, f"{shiny_size_app_url}/{case}/", 1280)
    try:
        page.wait_for_timeout(1500)
        seen = _settle(page)
        drawn = _chart_frame(page).evaluate(_BOKEH)
        assert drawn >= 400, (drawn, seen)
        assert seen["frame"]["height"] >= drawn, seen
        frame = _chart_frame(page)
        frame.locator(CHART).first.focus()
        page.wait_for_timeout(400)
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(800)
        seen = _settle(page)
        assert "Apples" in frame.evaluate(_READING)["said"]
        assert seen["text"] is not None and _inside(
            seen["text"], seen["boxShown"]
        ), seen
    finally:
        page.close()


#: Where Bokeh drew the plot, and what is painted at the middle of maidr's
#: text, in the frame's own pixels.
_BOKEH_DRAWN = r"""() => {
  const host = [...document.querySelectorAll('div')].find(e => e.shadowRoot);
  const text = document.getElementById('maidr-text-container');
  const r = host.getBoundingClientRect();
  const t = text && text.textContent.trim() ? text.getBoundingClientRect() : null;
  const hit = t && document.elementFromPoint(
    (t.left + t.right) / 2, (t.top + t.bottom) / 2);
  return {
    plot: {left: r.left, top: r.top, right: r.right, bottom: r.bottom,
           width: r.width, height: r.height},
    text: t && {top: t.top, bottom: t.bottom},
    textOnTop: !!(hit && text.contains(hit)),
    window: [window.innerWidth, window.innerHeight],
  };
}"""


@pytest.mark.parametrize(
    ("case", "width"),
    [("bokeh_scaled", 1280), ("bokeh_scaled_card", 1280), ("bokeh_scaled", 390)],
)
def test_a_bokeh_plot_scaled_both_ways_fits_its_box(
    browser, shiny_size_app_url, case, width
):
    """``sizing_mode="scale_both"``: its shape kept, within the box's height.

    Bokeh takes such a plot's size from its container's width alone. Given
    the box's height, it was as tall as it was wide -- 1256px in a 450px
    plot, 1198px in a 778px card -- and its canvas painted over maidr's
    text, below what the focus ring outlined; on a phone it left a blank
    band above the text.
    """
    page = _open(browser, f"{shiny_size_app_url}/{case}/", width)
    try:
        frame = _chart_frame(page)
        frame.locator(CHART).first.focus()
        page.wait_for_timeout(400)
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(800)
        seen = _settle(page)
        drawn = frame.evaluate(_BOKEH_DRAWN)
        plot = drawn["plot"]
        # Its shape, square, kept.
        assert plot["width"] == pytest.approx(plot["height"], abs=2), drawn
        # Within the frame, above maidr's text, which nothing paints over.
        assert plot["right"] <= drawn["window"][0] + 1, drawn
        assert plot["bottom"] <= drawn["text"]["top"] + 1, drawn
        assert drawn["textOnTop"], drawn
        # Right below it, with no band left blank where a phone's width,
        # not the height, limits it (366px in a 450px plot).
        assert drawn["text"]["top"] - plot["bottom"] <= 20, drawn
        assert _inside(seen["text"], seen["boxShown"]), seen
        # As large as the box allows: its width, or its height less the line.
        room = seen["box"]["height"] - 60 if case.endswith("card") else 450 - 2
        assert (
            plot["width"] >= drawn["window"][0] - 2 or plot["height"] >= room
        ), (drawn, seen)
        assert "Apples" in frame.evaluate(_READING)["said"]
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


#: The Bokeh plot's edges, in page pixels.
_BOKEH_PLOT = r"""() => {
  const frame = document.querySelector('#m iframe');
  const f = frame.getBoundingClientRect();
  const plot = frame.contentDocument.querySelector(
    '[id^="maidr-bokeh-"][id$="-plot"]').getBoundingClientRect();
  return {left: plot.left + f.left, top: plot.top + f.top,
          right: plot.right + f.left, bottom: plot.bottom + f.top};
}"""

#: The focus ring's colour (``maidr/assets/frame.css``).
_RING = (0x1A, 0x5F, 0xB4)


@pytest.mark.parametrize(
    ("case", "width"),
    [
        ("bokeh", 1280),
        ("bokeh_stretched_card", 1280),
        ("bokeh_stretched_card", 390),
        ("bokeh_scaled", 1280),
        ("bokeh_scaled", 390),
    ],
)
def test_a_bokeh_plots_focus_ring_is_drawn_over_it(
    browser, shiny_size_app_url, case, width
):
    """The ring shows on every edge of the plot, as the reader sees it.

    The ring was drawn on the focused element round the plot, and Bokeh's
    canvas, in a positioned element, covered it: a 1px sliver showed on the
    top and left edges and none on the others, none at all in a card, and
    a plot scaled both ways had it only beside the plot, in the margins.
    """
    from io import BytesIO

    from PIL import Image

    page = _open(browser, f"{shiny_size_app_url}/{case}/", width)
    try:
        page.evaluate(
            "() => document.querySelector('#m iframe')"
            ".scrollIntoView({block: 'center', behavior: 'instant'})"
        )
        frame = _chart_frame(page)
        frame.locator(CHART).first.focus()
        page.wait_for_timeout(800)
        plot = page.evaluate(_BOKEH_PLOT)
        shot = Image.open(BytesIO(page.screenshot())).convert("RGB")
        # The middle of the ring's 3px on each edge, at five points along it.
        x0, y0 = round(plot["left"]) + 1, round(plot["top"]) + 1
        x1, y1 = round(plot["right"]) - 2, round(plot["bottom"]) - 2
        along = [i / 6 for i in range(1, 6)]
        points = {
            "top": [(x0 + (x1 - x0) * t, y0) for t in along],
            "bottom": [(x0 + (x1 - x0) * t, y1) for t in along],
            "left": [(x0, y0 + (y1 - y0) * t) for t in along],
            "right": [(x1, y0 + (y1 - y0) * t) for t in along],
        }
        for edge, spots in points.items():
            for x, y in spots:
                pixel = shot.getpixel((int(x), int(y)))
                assert max(abs(a - b) for a, b in zip(pixel, _RING)) <= 40, (
                    edge,
                    (x, y),
                    pixel,
                    plot,
                )
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


#: How tall Vega drew the chart.
_VEGA_HEIGHT = (
    "() => document.querySelector('.vega-embed svg').getBoundingClientRect().height"
)


@pytest.mark.parametrize("case", ["altair_container", "altair_container_card"])
def test_an_altair_chart_as_tall_as_its_container_is_given_a_height(
    browser, shiny_size_app_url, case
):
    """``height="container"``: the box's height less the text line, or 450px.

    Vega reads the height of the element it is embedded in, which had none:
    the chart was drawn 0px tall in a 16px frame, and grew by thousands of
    pixels once maidr's text came.
    """
    page = _open(browser, f"{shiny_size_app_url}/{case}/", 1280)
    try:
        frame = _chart_frame(page)
        page.wait_for_timeout(1500)
        seen = _settle(page)
        drawn = frame.evaluate(_VEGA_HEIGHT)
        if case.endswith("card"):
            assert drawn >= seen["box"]["height"] - 60, (drawn, seen)
        else:
            assert drawn == pytest.approx(450, abs=2), (drawn, seen)
        frame.locator(CHART).first.focus()
        page.wait_for_timeout(400)
        heights = []
        for _ in range(4):
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(400)
            heights.append(page.evaluate(_GEOMETRY)["frame"]["height"])
        assert max(heights) - min(heights) <= 1, heights
        seen = _settle(page)
        assert frame.evaluate(_VEGA_HEIGHT) == pytest.approx(drawn, abs=1)
        assert seen["text"] is not None and _inside(seen["text"], seen["boxShown"]), seen
        assert "fruit is dates" in frame.evaluate(_READING)["said"].lower()
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


def test_an_altair_chart_as_tall_as_its_card_follows_a_shorter_window(
    browser, shiny_size_app_url
):
    """The card shorter, the chart drawn shorter, and the frame with it.

    Vega draws the chart again some time after its container's height
    changes. The frame was measured before it had, and nothing measured it
    again: it kept its old height, 400px of blank below the text that the
    card scrolled over, until the next key.
    """
    page = _open(browser, f"{shiny_size_app_url}/altair_container_card/", 1280)
    try:
        page.wait_for_timeout(1500)
        tall = _settle(page)
        page.set_viewport_size({"width": 1280, "height": 500})
        page.wait_for_timeout(1500)
        seen = _settle(page)
        drawn = _chart_frame(page).evaluate(_VEGA_HEIGHT)
        assert seen["box"]["height"] < tall["box"]["height"] - 300, (tall, seen)
        assert drawn >= seen["box"]["height"] - 60, (drawn, seen)
        assert seen["frame"]["height"] <= seen["boxClient"][1] + 1, seen
        assert seen["boxScroll"][1] <= seen["boxClient"][1] + 1, seen
        # And no further: measured again, it is not resized.
        page.wait_for_timeout(2000)
        assert page.evaluate(_GEOMETRY)["frame"] == seen["frame"]
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


# ---------------------------------------------------------------------------
# The renderer's own size, under Express too; outputs written other ways
# ---------------------------------------------------------------------------


def test_a_renderers_height_is_a_box_at_the_top_of_a_card(browser, shiny_size_app_url):
    """``@render_maidr(height=300)`` in a fillable card, as ``render.plot``."""
    page = _open(browser, f"{shiny_size_app_url}/renderer_card/", 1280)
    try:
        seen = page.evaluate(_GEOMETRY)
        assert seen["out"]["height"] > 500, ("the output fills the card", seen)
        assert seen["box"]["height"] == pytest.approx(300, abs=1), seen
        assert seen["box"]["top"] == pytest.approx(seen["out"]["top"], abs=1), seen
        assert _inside(seen["svg"], seen["box"]), seen
        _assert_reads(page, "a 300px box in a card")
    finally:
        page.close()


def test_express_gives_a_renderers_height_to_its_box(
    browser, shiny_size_express_app_url
):
    """Beside ``@render.plot(height=300)``: a 300px box at the top, likewise.

    Express gave the height to the output it places, which then filled the
    card, and the chart was centred in all of it.
    """
    page = _open(browser, shiny_size_express_app_url, 1280, oid="n")
    try:
        page.wait_for_selector("#p img", timeout=30_000)
        sized = _settle(page, oid="n")
        plot = page.evaluate(
            "() => { const r = document.querySelector('#p img').getBoundingClientRect();"
            " const o = document.getElementById('p').getBoundingClientRect();"
            " return {height: r.height, offset: r.top - o.top}; }"
        )
        assert plot["height"] == pytest.approx(300, abs=1), plot
        assert sized["box"]["height"] == pytest.approx(300, abs=1), sized
        assert sized["box"]["top"] - sized["out"]["top"] == pytest.approx(
            plot["offset"], abs=1
        ), (sized, plot)
        assert _inside(sized["svg"], sized["box"]), sized
        _assert_reads(page, "Express, height 300", oid="n")
    finally:
        page.close()


def test_express_fills_a_card_with_an_unsized_chart(
    browser, shiny_size_express_app_url
):
    """The output Express places for ``@render_maidr`` fills its card."""
    page = _open(browser, shiny_size_express_app_url, 1280, oid="m")
    try:
        seen = _settle(page, oid="m")
        _assert_fills(seen, "Express card")
        assert seen["box"]["height"] > 500, seen
        _assert_reads(page, "Express card", oid="m")
    finally:
        page.close()


@pytest.mark.parametrize("case", ["as_str", "as_html_string"])
def test_a_frame_made_into_a_string_is_sized(browser, shiny_size_app_url, case):
    """``ui.HTML(str(maidr.render(fig)))``, alone on its page.

    ``str()`` drops the dependency that serves the frame's sizing script,
    and with no other chart on the page nothing loaded it: the frame stayed
    150px tall and cut a 463px chart off.
    """
    page = _open(browser, f"{shiny_size_app_url}/{case}/", 1280)
    try:
        seen = page.evaluate(_GEOMETRY)
        assert (seen["svg"]["width"], seen["svg"]["height"]) == pytest.approx(
            _OWN, abs=2
        ), seen
        assert seen["frame"]["height"] >= seen["svg"]["height"], seen
        _assert_reads(page, "a frame made into a string")
        seen = _settle(page)
        assert seen["text"] is not None and _inside(seen["text"], seen["frame"]), seen
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


def test_a_frame_kept_as_a_string_is_sized_in_a_later_session(
    browser, shiny_size_app_url
):
    """A string made by one session, shown once that session has ended.

    The frame loaded its script from a route of the session that made it,
    which answered 404 once that session had ended: a string an app kept
    and showed again stayed 150px tall and cut the chart off.
    """
    first = _open(browser, f"{shiny_size_app_url}/kept_str/", 1280)
    first.close()
    # The first session ends as its websocket closes.
    time.sleep(1.5)
    page = _open(browser, f"{shiny_size_app_url}/kept_str/", 1280)
    try:
        seen = page.evaluate(_GEOMETRY)
        assert (seen["svg"]["width"], seen["svg"]["height"]) == pytest.approx(
            _OWN, abs=2
        ), seen
        assert seen["frame"]["height"] >= seen["svg"]["height"], seen
        _assert_reads(page, "a frame kept as a string")
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


def test_a_frame_made_into_a_string_in_an_express_page_is_sized(
    browser, shiny_string_express_app_url
):
    """``ui.HTML(str(maidr.render(ax)))`` in a Shiny Express app's page.

    Express builds the page with a stand-in session, which serves nothing:
    the frame had no URL to load its script from, and stayed 150px tall,
    the chart cut by 291px.
    """
    page = _open(browser, shiny_string_express_app_url, 1280)
    try:
        seen = page.evaluate(_GEOMETRY)
        assert (seen["svg"]["width"], seen["svg"]["height"]) == pytest.approx(
            _OWN, abs=2
        ), seen
        assert seen["frame"]["height"] >= seen["svg"]["height"], seen
        _assert_reads(page, "a frame made into a string in an Express page")
        seen = _settle(page)
        assert seen["text"] is not None and _inside(seen["text"], seen["frame"]), seen
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


def _assert_shows_all_of_it(page, where: str) -> None:
    """The chart and its text shown whole: the frame as tall as they are."""
    seen = page.evaluate(_GEOMETRY)
    assert seen["frame"]["height"] >= seen["svg"]["height"], (where, seen)
    assert _inside(seen["svg"], seen["frame"]), (where, seen)
    _assert_reads(page, where)
    seen = _settle(page)
    assert seen["text"] is not None and _inside(seen["text"], seen["frame"]), (
        where,
        seen,
    )


def _without_the_served_script(browser, url: str, width: int = 1280, **launch):
    """A page whose ``maidr-shiny-frame`` script answers 404, noting each ask."""
    page = browser.new_page(viewport={"width": width, "height": 900}, **launch)
    page.asked = []  # type: ignore[attr-defined]

    def refuse(route):
        page.asked.append(route.request.url)  # type: ignore[attr-defined]
        route.fulfill(status=404, body="Not Found")

    page.route("**/maidr-shiny-frame-*/frame.js", refuse)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.errors = errors  # type: ignore[attr-defined]
    page.goto(url)
    page.wait_for_selector("#m iframe", timeout=30_000)
    page.frame_locator("#m iframe").locator(CHART).first.wait_for(
        state="attached", timeout=30_000
    )
    return page


@pytest.mark.parametrize("case", ["as_str", "kept_str"])
def test_a_string_frame_needs_nothing_served(browser, shiny_size_app_url, case):
    """A string frame carries its script: nothing it asks the app for.

    It named the served script's URL, and where that was not served -- a
    restarted server, another process -- it guessed at its own size, which
    resized it without end at the classic scrollbars' threshold. It asks
    for nothing now, and is sized as ``render_maidr``'s frame is.
    """
    page = _without_the_served_script(browser, f"{shiny_size_app_url}/{case}/")
    try:
        _settle(page)
        seen = page.evaluate(_GEOMETRY)
        assert (seen["svg"]["width"], seen["svg"]["height"]) == pytest.approx(
            _OWN, abs=2
        ), seen
        _assert_shows_all_of_it(page, f"{case}, nothing served")
        assert page.asked == []  # type: ignore[attr-defined]
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


#: A browser that has no ``DecompressionStream`` (Safari before 16.4,
#: Firefox before 113), or one that cannot unpack ``deflate-raw`` (Chrome and
#: Edge before 103).
_CANNOT_UNPACK = {
    "none": "delete window.DecompressionStream; delete window.CompressionStream;",
    "old": "window.DecompressionStream = function (format) {"
    " throw new TypeError('Unsupported compression format: ' + format); };",
}


@pytest.mark.parametrize("unpack", sorted(_CANNOT_UNPACK))
@pytest.mark.parametrize("case", ["as_str", "str_plotly"])
def test_a_string_frame_is_sized_in_a_browser_that_cannot_unpack(
    browser, shiny_size_app_url, case, unpack
):
    """A string frame's script is plain text, which every browser runs.

    It was packed, and unpacked with ``DecompressionStream('deflate-raw')``:
    a browser without it left the frame 150px tall, 313px of a 463px
    matplotlib chart and 300px of a 450px Plotly chart cut off.
    """
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.add_init_script(_CANNOT_UNPACK[unpack])
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(f"{shiny_size_app_url}/{case}/")
        page.wait_for_selector("#m iframe", timeout=30_000)
        page.frame_locator("#m iframe").locator(CHART).first.wait_for(
            state="attached", timeout=30_000
        )
        seen = _settle(page)
        if case == "as_str":
            assert (seen["svg"]["width"], seen["svg"]["height"]) == pytest.approx(
                _OWN, abs=2
            ), seen
        else:
            assert seen["svg"]["height"] == pytest.approx(450, abs=2), seen
        assert seen["frame"]["height"] >= seen["svg"]["height"], seen
        assert _inside(seen["svg"], seen["frame"]), seen
        assert errors == [], errors
    finally:
        page.close()


#: How many times the frame's height has changed, frame by frame, from now.
_COUNT_RESIZES = r"""() => {
  const frame = document.querySelector('#m iframe');
  window.maidrResizes = 0;
  let last = frame.style.height;
  const note = () => {
    if (frame.style.height !== last) { last = frame.style.height; window.maidrResizes++; }
    requestAnimationFrame(note);
  };
  note();
}"""


#: A page's scrollbar 30px wide, as Windows' 17px one is at a browser zoom of
#: 57%, or as an app's stylesheet may make it.
_WIDE_SCROLLBAR = (
    "document.addEventListener('DOMContentLoaded', () => {"
    " const style = document.createElement('style');"
    " style.textContent = 'html::-webkit-scrollbar{width:30px;height:30px;"
    "background:#ddd}html::-webkit-scrollbar-thumb{background:#888}';"
    " document.head.appendChild(style); });"
)


@pytest.mark.parametrize(
    "case,scrollbar",
    [("default", ""), ("as_str", ""), ("default", "wide")],
)
def test_a_frame_at_rest_is_still_at_the_scrollbars_threshold(
    classic_scrollbar_browser, shiny_size_app_url, case, scrollbar
):
    """Classic scrollbars, a page whose height is about the window's.

    The page's scrollbar comes as the frame grows, and narrows it; the chart
    shrinks with it, and the frame with the chart, and the scrollbar goes:
    render_maidr's frame was resized 1079 times in 1.5s at rest. The frame
    keeps the taller of the two heights now, for as long as its box flips
    between the two widths and nothing else changes, however wide the
    scrollbar: one 30px wide was let resize it 240 times in 4s. A string
    frame, whose output has no box of its own, does not flip.
    """
    if case == "as_str":
        page = _without_the_served_script(
            classic_scrollbar_browser, f"{shiny_size_app_url}/{case}/", width=390
        )
    else:
        page = classic_scrollbar_browser.new_page(
            viewport={"width": 390, "height": 900}
        )
        if scrollbar:
            page.add_init_script(_WIDE_SCROLLBAR)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.errors = errors  # type: ignore[attr-defined]
        page.goto(f"{shiny_size_app_url}/{case}/")
        page.wait_for_selector("#m iframe", timeout=30_000)
        page.frame_locator("#m iframe").locator(CHART).first.wait_for(
            state="attached", timeout=30_000
        )
    try:
        page.set_viewport_size({"width": 390, "height": 844})
        _settle(page)
        # A spacer above the chart, as tall as makes the page as tall as the
        # window, give or take: the page's scrollbar comes and goes there.
        even = page.evaluate(
            "() => { const s = document.createElement('div'); s.id = 'spacer';"
            " document.body.insertBefore(s, document.body.firstChild);"
            " const bottom = Math.max(...[...document.body.children].map(e =>"
            " e.getBoundingClientRect().bottom + window.scrollY"
            " + parseFloat(getComputedStyle(e).marginBottom)));"
            " return innerHeight - bottom; }"
        )
        for spacer in range(int(even) - 20, int(even) + 21, 2):
            page.evaluate(
                "(px) => document.getElementById('spacer').style.height = px + 'px'",
                spacer,
            )
            page.wait_for_timeout(1500)
            page.evaluate(_COUNT_RESIZES)
            page.wait_for_timeout(1500)
            resizes = page.evaluate("() => window.maidrResizes")
            assert resizes == 0, (spacer, even, resizes)
            seen = page.evaluate(_GEOMETRY)
            assert _inside(seen["svg"], seen["frame"]), (spacer, seen)
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


def test_a_frame_alone_in_a_scroll_box_is_still_at_its_scrollbars_threshold(
    classic_scrollbar_browser, shiny_size_app_url
):
    """Classic scrollbars, the chart alone in a box of a fixed height that scrolls.

    The box's own scrollbar comes as the frame grows past the box, and
    narrows the chart, which shrinks the frame back inside it, and the
    scrollbar goes. The steady guard counts the box's scrollbar as it does
    the page's: counting the page's alone, the frame was resized 240 times
    in 4s with the box 292-300px tall. Its height is swept across that
    threshold here.
    """
    page = classic_scrollbar_browser.new_page(viewport={"width": 390, "height": 844})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(f"{shiny_size_app_url}/alone_in_box/")
        page.wait_for_selector("#m iframe", timeout=30_000)
        page.frame_locator("#m iframe").locator(CHART).first.wait_for(
            state="attached", timeout=30_000
        )
        _settle(page)
        for height in range(280, 322, 2):
            page.evaluate(
                "(px) => document.getElementById('scroller').style.height = px + 'px'",
                height,
            )
            page.wait_for_timeout(1500)
            page.evaluate(_COUNT_RESIZES)
            page.wait_for_timeout(1500)
            resizes = page.evaluate("() => window.maidrResizes")
            assert resizes == 0, (height, resizes)
            seen = page.evaluate(_GEOMETRY)
            assert _inside(seen["svg"], seen["frame"]), (height, seen)
        assert errors == [], errors
    finally:
        page.close()


#: The height of the chart that takes its container's, and of its frame.
_CONTAINER = r"""() => {
  const frame = document.querySelector('#m iframe');
  const doc = frame.contentDocument;
  const plot = doc.querySelector(
    '.vega-embed, [id^="maidr-bokeh-"][id$="-plot"]');
  const drawn = plot && plot.firstElementChild;
  return {frame: frame.getBoundingClientRect().height,
          plot: plot && plot.getBoundingClientRect().height,
          drawn: drawn && drawn.getBoundingClientRect().height,
          width: plot && plot.getBoundingClientRect().width,
          bottom: plot && plot.getBoundingClientRect().bottom};
}"""


@pytest.mark.parametrize(
    "case", ["altair_container", "bokeh_stretched", "bokeh_scaled"]
)
def test_a_string_frame_gives_a_container_height_as_render_maidr_does(
    browser, shiny_size_app_url, case
):
    """An Altair chart of height "container", Bokeh plots stretched or scaled.

    The same script sizes both frames, so a string frame's chart is as tall,
    and as wide, as ``render_maidr``'s, and stays so: without its script,
    the Altair chart followed the frame, which followed it, and grew 34px a
    second; the stretched Bokeh plot was 51px tall.
    """
    sizes = []
    for url in (f"{case}/", f"str_{case}/"):
        if url.startswith("str_"):
            page = _without_the_served_script(browser, f"{shiny_size_app_url}/{url}")
        else:
            page = _open(browser, f"{shiny_size_app_url}/{url}", 1280)
        try:
            page.wait_for_timeout(2500)
            first = page.evaluate(_CONTAINER)
            page.wait_for_timeout(3000)
            later = page.evaluate(_CONTAINER)
            assert first["plot"] == pytest.approx(450, abs=5), (url, first)
            assert first["drawn"] <= first["plot"] + 1, (url, first)
            assert later == first, (url, first, later)
            assert first["bottom"] <= first["frame"] + 1, (url, first)
            sizes.append((first["plot"], first["width"], first["frame"]))
        finally:
            page.close()
    # The chart alike; the frames within a line's descent, the string
    # frame's document being its srcdoc, render_maidr's one it is served.
    assert sizes[0][:2] == pytest.approx(sizes[1][:2], abs=1), sizes
    assert sizes[0][2] == pytest.approx(sizes[1][2], abs=5), sizes


def test_a_string_frame_written_to_a_file_shows_the_chart(
    browser, shiny_size_app_url, tmp_path
):
    """A download handler writes the string to a file, opened from disk.

    Its script's URL is relative to the app, which a file has none of: the
    frame stayed 150px tall, 313px of the chart cut off.
    """
    first = _open(browser, f"{shiny_size_app_url}/kept_str/", 1280)
    try:
        html = first.request.get(f"{shiny_size_app_url}/kept_str.html").text()
    finally:
        first.close()
    assert "maidrShinyFrame(f," in html and "maidrShinyKinds" in html
    saved = tmp_path / "chart.html"
    saved.write_text(
        "<!doctype html><html><head><meta charset='utf-8'></head>"
        f"<body><div id='m'>{html}</div></body></html>",
        encoding="utf-8",
    )
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(saved.as_uri())
        page.frame_locator("#m iframe").locator(CHART).first.wait_for(
            state="attached", timeout=30_000
        )
        _settle(page)
        _assert_shows_all_of_it(page, "a string written to a file")
        assert errors == []
    finally:
        page.close()


def test_a_hand_written_output_ui_shows_the_chart(browser, shiny_size_app_url):
    """``ui.output_ui`` rather than ``output_maidr``: the plain figure's size."""
    page = _open(browser, f"{shiny_size_app_url}/hand_written/", 1280)
    try:
        seen = page.evaluate(_GEOMETRY)
        assert (seen["svg"]["width"], seen["svg"]["height"]) == pytest.approx(
            _OWN, abs=2
        ), seen
        assert seen["pageScroll"] == 0
        _assert_reads(page, "a hand-written output")
    finally:
        page.close()


#: The chart's frame's height, and its box's.
_HEIGHTS = r"""() => {
  const frame = document.querySelector('#m iframe');
  const box = frame.parentElement;
  return {frame: frame.getBoundingClientRect().height,
          box: box.getBoundingClientRect().height,
          boxClient: box.clientHeight};
}"""


def test_a_card_taken_full_screen_and_back_has_its_chart_s_height_again(
    browser, shiny_size_app_url
):
    """A card in a page that is not fillable, full screen and back, untouched.

    The frame kept the height it had full screen, 678px for a 463px chart,
    215px of blank below the chart and the card that much taller: the two
    heights, A then B then A again, were taken for the classic scrollbars'
    flip, and the taller held until the reader did something in the chart.
    """
    page = _open(browser, f"{shiny_size_app_url}/fs_card/", 1280, 900)
    try:
        first = page.evaluate(_HEIGHTS)
        for _ in range(2):
            _full_screen(page, True)
            _settle(page)
            _full_screen(page, False)
            _settle(page)
            back = page.evaluate(_HEIGHTS)
            assert back["frame"] == pytest.approx(first["frame"], abs=2), (first, back)
            assert back["box"] == pytest.approx(first["box"], abs=2), (first, back)
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


def test_a_chart_follows_a_window_made_shorter_and_taller_again(
    browser, shiny_size_app_url
):
    """A fillable card's chart, the window 900, 700, 900 and 700px tall.

    The second 700px window left the frame 726px tall in a 578px box, which
    scrolled over 148px of blank: the heights were taken for the classic
    scrollbars' flip, and the taller held.
    """
    page = _open(browser, f"{shiny_size_app_url}/card/", 1280, 900)
    try:
        seen = {}
        for height in (700, 900, 700, 900):
            page.set_viewport_size({"width": 1280, "height": height})
            page.wait_for_timeout(1000)
            _settle(page)
            now = page.evaluate(_HEIGHTS)
            assert now["frame"] <= now["boxClient"] + 1, (height, now)
            if height in seen:
                assert now["frame"] == pytest.approx(seen[height], abs=2), (
                    height,
                    seen,
                    now,
                )
            seen[height] = now["frame"]
        assert page.errors == []  # type: ignore[attr-defined]
    finally:
        page.close()


def test_a_bokeh_plot_scaled_both_ways_is_its_own_height_once_loaded(
    browser, shiny_size_app_url
):
    """Untouched after load, the frame is as tall as the plot and its text.

    Bokeh draws the plot at 1256px, then 450px, then 1256px as it loads;
    taken for the classic scrollbars' flip, the frame was held at 1256px
    for a 450px plot, 806px of blank until the reader did something in the
    chart, and the first redraw moved the page 497px.
    """
    for case in ("bokeh_scaled", "str_bokeh_scaled"):
        page = _open(browser, f"{shiny_size_app_url}/{case}/", 1280, 900)
        try:
            page.wait_for_timeout(1500)
            seen = page.evaluate(_CONTAINER)
            assert seen["frame"] <= seen["plot"] + 120, (case, seen)
            assert page.errors == []  # type: ignore[attr-defined]
        finally:
            page.close()
