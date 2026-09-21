"""A point layer's marks are outlined, on the point being announced.

The core reads a ``point`` layer's ``selectors`` as one string and nothing
else: ``scatter.ts`` hands it to ``querySelectorAll`` and pairs the matches
with the points by where they were drawn, and ``Svg.isUsableSelector``
accepts strings only. A list -- the one-element list every plain scatter
emitted, or the one-selector-per-point list a hue-grouped scatter, a strip
plot, an event plot and a grouped rug emit -- is not a selector to it, so
those layers announced every point and outlined nothing, on every chart
(#316 in r-maidr, the same bundle contract). ``Maidr._flatten_maidr`` now
joins the list into that one string on the way out.

This drives the shipped bundle: a reader steps onto a point, and the outline
the core draws is a clone of the marker at that point's own coordinates, for
a plain scatter and for a hue-grouped one whose layer names a third of the
markers on the chart.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

#: Installed on `window` by the bundle once the inlined JavaScript has parsed.
_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000

#: Where the core writes what it announces for the current point.
_TEXT = "#maidr-text-container"

#: The markers matplotlib drew, in document order, as (x, y) of each `<use>`.
#: The core stands a hidden clone beside each one it can pair, marked
#: `data-maidr-owned`; those are not markers.
_DRAWN_MARKERS = """() => [...document.querySelectorAll(
  "g[maidr] > g > use:not([data-maidr-owned])"
)].map((u) => [Number(u.getAttribute("x")), Number(u.getAttribute("y"))])"""

#: The outline the core draws for the current point: a visible clone of the
#: marker, so its `x`/`y` say which marker it copies.
_HIGHLIGHTED = """() => [...document.querySelectorAll("svg [data-maidr-owned]")]
  .filter((e) => getComputedStyle(e).visibility !== "hidden")
  .map((e) => [Number(e.getAttribute("x")), Number(e.getAttribute("y"))])"""


@pytest.fixture
def plain_scatter(tmp_path) -> Path:
    """Four points whose x and y both rise, so a marker's position names it."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    import maidr

    fig, ax = plt.subplots()
    ax.scatter([1, 2, 3, 4], [3, 5, 2, 4])
    path = tmp_path / "scatter.html"
    try:
        # Bundled rather than CDN: the shipped bundle is the thing under test.
        maidr.save_html(fig, file=str(path), use_cdn=False)
    finally:
        plt.close("all")
    return path


@pytest.fixture
def hue_scatter(tmp_path) -> Path:
    """Six points in two named groups, so a layer owns three of six markers."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd
    import seaborn as sns

    import maidr

    frame = pd.DataFrame(
        {
            "x": [1, 2, 3, 1.5, 2.5, 3.5],
            "y": [1, 2, 3, 4, 5, 6],
            "g": ["a", "a", "a", "b", "b", "b"],
        }
    )
    fig, ax = plt.subplots()
    sns.scatterplot(data=frame, x="x", y="y", hue="g", ax=ax)
    path = tmp_path / "scatter_hue.html"
    try:
        maidr.save_html(fig, file=str(path), use_cdn=False)
    finally:
        plt.close("all")
    return path


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(500)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def _enter(page, chart: Path) -> None:
    page.goto(chart.as_uri(), wait_until="load")
    page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
    page.click("svg[maidr]", force=True)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1_500)


def test_a_plain_scatter_outlines_the_point_it_announces(browser, plain_scatter):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    try:
        _enter(page, plain_scatter)

        markers = page.evaluate(_DRAWN_MARKERS)
        assert len(markers) == 4 and len({tuple(m) for m in markers}) == 4

        # The points are walked by x; the first is (1, 3), the leftmost marker.
        spoken = _step(page, "ArrowRight")
        assert "1" in spoken and "3" in spoken, spoken
        leftmost = min(markers, key=lambda m: m[0])
        assert page.evaluate(_HIGHLIGHTED) == [leftmost], (
            "the point is announced but its marker is not outlined: the "
            "selectors reached the core as a list, which it does not read"
        )

        spoken = _step(page, "ArrowRight")
        assert "2" in spoken and "5" in spoken, spoken
        second = sorted(markers, key=lambda m: m[0])[1]
        assert page.evaluate(_HIGHLIGHTED) == [second]
        assert not errors, errors
    finally:
        page.close()


def test_a_hue_grouped_scatter_outlines_its_own_group_only(browser, hue_scatter):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    try:
        _enter(page, hue_scatter)

        markers = page.evaluate(_DRAWN_MARKERS)
        assert len(markers) == 6

        # The first layer is group `a`: x = 1, 2, 3 -- the three markers
        # lowest on the chart, and the first of them the leftmost of those.
        spoken = _step(page, "ArrowRight")
        assert "1" in spoken, spoken
        outlined = page.evaluate(_HIGHLIGHTED)
        assert len(outlined) == 1, (
            "one point announced, one marker outlined; a grouped layer that "
            "names its points one by one must still reach the core as a string"
        )
        # The lowest three markers are group `a`, in SVG y (larger is lower).
        group_a = sorted(markers, key=lambda m: -m[1])[:3]
        assert outlined[0] == min(group_a, key=lambda m: m[0])
        assert not errors, errors
    finally:
        page.close()
