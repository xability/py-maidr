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
_GEOMETRY = r"""() => {
  const R = (r, dx = 0, dy = 0) => r && ({
    left: r.left + dx, top: r.top + dy, right: r.right + dx,
    bottom: r.bottom + dy, width: r.width, height: r.height});
  const out = document.getElementById('m');
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
    frame: R(f),
    svg: svg && R(svg.getBoundingClientRect(), f.left, f.top),
    text: text && text.textContent.trim() ? R(text.getBoundingClientRect(), f.left, f.top) : null,
    src: frame && frame.getAttribute('src'),
  };
}"""

#: What the reader is told and shown once ArrowRight has moved them.
_READING = r"""() => {
  const alert = document.querySelector('#maidr-text-container [role=alert], [role=alert]');
  const lit = document.querySelector('[id^=maidr-highlight]');
  const mark = lit && lit.previousElementSibling;
  const box = e => { const r = e.getBoundingClientRect();
                     return [r.left, r.top, r.right, r.bottom]; };
  const focused = document.activeElement;
  const ring = focused && getComputedStyle(focused);
  return {
    said: alert ? alert.textContent.trim() : '',
    lit: lit && box(lit), mark: mark && box(mark),
    focused: focused ? (focused.getAttribute('role') || focused.tagName) : null,
    ring: ring ? [ring.outlineStyle, parseFloat(ring.outlineWidth)] : null,
  };
}"""


def _open(browser, url: str, width: int, height: int = 900):
    page = browser.new_page(viewport={"width": width, "height": height})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(url)
    page.wait_for_selector("#m iframe", timeout=30_000)
    # Attached rather than visible: maidr.js's focusable element for a
    # Plotly chart has no height of its own.
    page.frame_locator("#m iframe").locator(CHART).first.wait_for(
        state="attached", timeout=30_000
    )
    _settle(page)
    page.errors = errors  # type: ignore[attr-defined]
    return page


def _settle(page, quiet_ms: int = 1200, timeout_ms: int = 15_000) -> dict:
    """Wait until the output's geometry stops changing, and return it."""
    last, still, waited = None, 0, 0
    while waited < timeout_ms:
        seen = page.evaluate(_GEOMETRY)
        key = repr({k: seen[k] for k in ("box", "frame", "svg")})
        still = still + 200 if key == last else 0
        if still >= quiet_ms:
            return seen
        last = key
        page.wait_for_timeout(200)
        waited += 200
    return page.evaluate(_GEOMETRY)


def _chart_frame(page):
    for frame in page.frames[1:]:
        if frame.locator(CHART).count():
            return frame
    raise AssertionError("no chart frame on the page")


def _read(page, presses: int = 1) -> dict:
    """Focus the chart, press ArrowRight, and say what the reader got."""
    frame = _chart_frame(page)
    frame.locator(CHART).first.focus()
    page.wait_for_timeout(400)
    for _ in range(presses):
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(300)
    page.wait_for_timeout(600)
    return frame.evaluate(_READING)


def _assert_reads(page, where: str) -> None:
    reading = _read(page)
    assert reading["focused"] in ("img", "application"), (where, reading)
    assert reading["ring"][0] != "none" and reading["ring"][1] >= 2, (where, reading)
    # The first press says the first bar; a later one, the bar it moves to.
    assert any(f"Fruit is {fruit}" in reading["said"] for fruit in _FRUIT), (
        where,
        reading,
    )
    assert reading["lit"] is not None, f"{where}: nothing is highlighted"
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
