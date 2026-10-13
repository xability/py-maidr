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


@pytest.mark.parametrize("width", [1280, 390])
def test_a_dialog_is_shown_whole_in_a_short_output(browser, shiny_size_app_url, width):
    """Help in a 300px output: the box grows to the window while it is open.

    It was kept to the box: 104px of its text showed in a 300px output, and
    20px in a 200px one.
    """
    page = _open(browser, f"{shiny_size_app_url}/h300/", width, height=800)
    try:
        _read(page)
        page.keyboard.press("Control+/")
        page.wait_for_timeout(1500)
        seen = _settle(page)
        dialog = page.evaluate(_DIALOG)
        assert dialog is not None, "no dialog opened"
        shown = seen["boxShown"]
        view = {"left": 0, "top": 0, "right": width, "bottom": 800}
        for part in ("paper", "close"):
            assert _inside(dialog[part], shown), (part, dialog, seen)
            assert _inside(dialog[part], view), (part, dialog, seen)
        assert dialog["text"] >= 400, dialog
        assert seen["pageScroll"] == 0, seen

        page.keyboard.press("Escape")
        page.wait_for_timeout(1200)
        back = _settle(page)
        assert page.evaluate(_DIALOG) is None
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
    if (getComputedStyle(a).overflowY === 'visible') continue;
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
        assert dialog["text"] >= 400, dialog
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


@pytest.mark.parametrize("width", [1280, 390])
@pytest.mark.parametrize("key", ["Control+/", "Control+,"])
def test_closing_a_dialog_leaves_the_page_where_the_reader_had_it(
    browser, shiny_size_app_url, width, key
):
    """Halfway down a long page: the page scrolls back once the dialog goes.

    The frame is scrolled to the middle of the window while a dialog is
    open, which held the box at the window's height. Closing it left the
    page scrolled by half of that, 250px, the chart at the window's top
    rather than where the reader had it.
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
        assert back["scrollY"] == pytest.approx(before["scrollY"], abs=1), (
            before,
            back,
        )
        assert back["frame"]["top"] == pytest.approx(before["frame"]["top"], abs=1)
        assert back["box"]["height"] == pytest.approx(300, abs=1), back
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
