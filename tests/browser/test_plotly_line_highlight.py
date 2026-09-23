"""A plotly line is outlined at the point being announced.

With ``use_cdn=False`` the bundle is a ``<script src>`` in the head, so
``maidr.js`` scanned the page before the init script had attached the
payload. Finding none, it adopted the plotly chart itself and moved the drawn
svg out of the document while it mounted; the init script, looking up the
first ``svg.main-svg`` on the page, then found plotly's overlay svg -- hover
and zoom layers, no trace -- and put the payload there. The reader drove the
chart ``maidr.js`` had adopted, and a line reads its path once when built:
every point announced, nothing ever outlined.

The init script now waits for ``Plotly.newPlot`` to resolve, binds this
chart's own drawn svg, and claims the div from auto-detection. These drive the
shipped bundle over a saved page, one series and two, and hold the outline to
the screen position plotly maps the announced point to.

plotly.js is linked from ``cdn.plot.ly``; the page is handed the copy the
installed ``plotly`` package ships instead, so nothing here needs a network.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

plotly = pytest.importorskip("plotly")

#: The plotly.js the installed package ships -- the build its ``to_html``
#: links to on the CDN, integrity hash included.
_PLOTLY_JS = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"

#: Installed on `window` by the bundle once it has parsed.
_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000

#: Where the core writes what it announces for the current point.
_TEXT = "#maidr-text-container"

#: The svg the payload landed on: how many there are, and how many drawn
#: line paths each holds.
_BOUND = """() => [...document.querySelectorAll("svg[maidr]")]
  .map((s) => s.querySelectorAll("path.js-line").length)"""

#: How many MAIDR instances the page mounted.
_INSTANCES = """() => document
  .querySelectorAll('article[id^="maidr-article"]').length"""

#: The visible outlines the core draws, as screen centres.
_OUTLINED = """() => [...document.querySelectorAll("svg [data-maidr-owned]")]
  .filter((e) => getComputedStyle(e).visibility !== "hidden"
    && e.getAttribute("visibility") !== "hidden")
  .map((e) => {
    const r = e.getBoundingClientRect();
    return [r.x + r.width / 2, r.y + r.height / 2];
  })"""

#: Where plotly draws a data point on screen. ``_fullLayout`` axes are how
#: plotly itself places marks: ``_offset`` is the plot area's position in
#: the svg and ``l2p`` maps a linear-axis value to pixels within it.
_SCREEN_POINT = """([x, y]) => {
  const svg = document.querySelector("svg[maidr]");
  const gd = svg.closest(".js-plotly-plot") || document.querySelector(".js-plotly-plot");
  const { xaxis, yaxis } = gd._fullLayout;
  const box = svg.getBoundingClientRect();
  return [box.x + xaxis._offset + xaxis.l2p(x), box.y + yaxis._offset + yaxis.l2p(y)];
}"""

#: How far, in CSS pixels, an outline's centre may sit from its point.
_TOLERANCE_PX = 1.5


def _save(fig, path: Path) -> Path:
    import maidr

    # Bundled rather than CDN: the shipped bundle is the thing under test,
    # and this is the mode that loads it ahead of the init script.
    maidr.save_html(fig, file=str(path), use_cdn=False)
    return path


@pytest.fixture
def one_line(tmp_path) -> Path:
    import plotly.graph_objects as go

    fig = go.Figure(go.Scatter(x=[1, 2, 3, 4], y=[3, 5, 2, 6], mode="lines"))
    return _save(fig, tmp_path / "plotly_line.html")


@pytest.fixture
def two_lines(tmp_path) -> Path:
    import plotly.graph_objects as go

    # Apart everywhere, so moving between series always lands on the other.
    fig = go.Figure(
        [
            go.Scatter(x=[1, 2, 3, 4], y=[1, 2, 1, 2], mode="lines", name="low"),
            go.Scatter(x=[1, 2, 3, 4], y=[8, 9, 8, 9], mode="lines", name="high"),
        ]
    )
    return _save(fig, tmp_path / "plotly_multiline.html")


def _open(browser, chart: Path):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    page.route(
        re.compile(r"^https://cdn\.plot\.ly/"),
        lambda route: route.fulfill(
            path=str(_PLOTLY_JS), content_type="application/javascript"
        ),
    )
    page.goto(chart.as_uri(), wait_until="load")
    page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
    page.wait_for_selector("svg[maidr]", state="attached", timeout=_PARSE_TIMEOUT_MS)
    page.wait_for_timeout(500)
    return page, errors


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(400)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def _announced_point(spoken: str) -> tuple[float, float]:
    x = re.search(r"X is (-?[\d.]+)", spoken)
    y = re.search(r"Y is (-?[\d.]+)", spoken)
    assert x and y, spoken
    return float(x.group(1)), float(y.group(1))


def _assert_outlined_at(page, spoken: str) -> None:
    """One visible outline, on the screen point the announcement names."""
    outlined = page.evaluate(_OUTLINED)
    assert len(outlined) == 1, (
        f"{spoken!r} is announced but {len(outlined)} outlines are visible: "
        "the line was built without its path"
    )
    want = page.evaluate(_SCREEN_POINT, list(_announced_point(spoken)))
    (cx, cy) = outlined[0]
    assert abs(cx - want[0]) <= _TOLERANCE_PX, (spoken, outlined[0], want)
    assert abs(cy - want[1]) <= _TOLERANCE_PX, (spoken, outlined[0], want)


def test_the_payload_is_on_the_drawn_svg(browser, one_line):
    page, errors = _open(browser, one_line)
    try:
        # One bound svg, and the one holding the line -- not plotly's overlay.
        assert page.evaluate(_BOUND) == [1]
        # Claimed, so `maidr.js` did not adopt the chart a second time.
        assert page.evaluate(_INSTANCES) == 1
        assert not errors, errors
    finally:
        page.close()


def test_a_line_outlines_the_point_it_announces(browser, one_line):
    page, errors = _open(browser, one_line)
    try:
        page.keyboard.press("Tab")
        page.wait_for_timeout(400)

        spoken = _step(page, "ArrowRight")
        assert _announced_point(spoken) == (1, 3), spoken
        _assert_outlined_at(page, spoken)
        first = page.evaluate(_OUTLINED)[0]

        spoken = _step(page, "ArrowRight")
        assert _announced_point(spoken) == (2, 5), spoken
        _assert_outlined_at(page, spoken)
        assert page.evaluate(_OUTLINED)[0] != first, "the outline did not move"
        assert not errors, errors
    finally:
        page.close()


def test_two_lines_outline_the_series_being_read(browser, two_lines):
    page, errors = _open(browser, two_lines)
    try:
        page.keyboard.press("Tab")
        page.wait_for_timeout(400)

        spoken = _step(page, "ArrowRight")
        start = _announced_point(spoken)
        assert start[0] == 1, spoken
        _assert_outlined_at(page, spoken)

        # To the other series at the same x: the outline follows it.
        spoken = _step(page, "ArrowUp" if start[1] < 5 else "ArrowDown")
        moved = _announced_point(spoken)
        assert moved[0] == 1 and moved[1] != start[1], spoken
        _assert_outlined_at(page, spoken)

        spoken = _step(page, "ArrowRight")
        assert _announced_point(spoken)[0] == 2, spoken
        _assert_outlined_at(page, spoken)
        assert not errors, errors
    finally:
        page.close()
