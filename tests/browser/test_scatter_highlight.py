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

A swarm plot rides the same contract with one more step in front of it:
seaborn packs the markers at draw time through a ``draw`` bound onto each
collection, which bypassed the highlight wrapper, so its groups were written
without the ``maidr`` attribute its selectors name and nothing was outlined.
The swarm cases hold the outline to the packed marker at the announced value.
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


def _swarm(tmp_path, *, horizontal: bool):
    """Save a three-category swarm; return its page and a value-to-SVG map.

    The map takes a value on the value axis to the SVG coordinate a marker
    for it is drawn at -- ``x`` for a horizontal swarm, ``y`` otherwise --
    in the points the SVG is written in, y running down from the top. The
    other coordinate is seaborn's packing, which the data does not predict.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import seaborn as sns

    import maidr

    rng = np.random.default_rng(3)
    frame = pd.DataFrame(
        {
            "g": np.repeat(["a", "b", "c"], 12),
            "v": np.round(rng.normal(10, 3, 36), 1),
        }
    )
    fig, ax = plt.subplots()
    if horizontal:
        sns.swarmplot(data=frame, x="v", y="g", ax=ax)
    else:
        sns.swarmplot(data=frame, x="g", y="v", ax=ax)
    path = tmp_path / ("swarm_h.html" if horizontal else "swarm.html")
    try:
        maidr.save_html(fig, file=str(path), use_cdn=False)
        scale = 72 / fig.dpi
        height = fig.get_figheight() * 72
        if horizontal:

            def at(value: float) -> float:
                return float(ax.transData.transform((value, 0))[0] * scale)

        else:

            def at(value: float) -> float:
                return float(height - ax.transData.transform((0, value))[1] * scale)

    finally:
        plt.close("all")
    return path, at


#: The markers one layer's selector names, as (x, y) of each `<use>`.
_LAYER_MARKERS = """(selector) => [...document.querySelectorAll(selector)]
  .filter((u) => !u.hasAttribute("data-maidr-owned"))
  .map((u) => [Number(u.getAttribute("x")), Number(u.getAttribute("y"))])"""

#: The first layer's selector, read off the payload the page carries.
_FIRST_SELECTOR = """() => JSON.parse(document.querySelector("svg[maidr]")
  .getAttribute("maidr")).subplots[0][0].layers[0].selectors"""


def _first_number(spoken: str) -> float:
    import re

    found = re.search(r"-?\d+(?:\.\d+)?", spoken)
    assert found, spoken
    return float(found.group(0))


def test_a_swarm_outlines_the_packed_marker_it_announces(browser, tmp_path):
    # Horizontal, so each step announces one value: the x a marker is drawn
    # at names it, whatever the packing did to its y.
    chart, at = _swarm(tmp_path, horizontal=True)
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    try:
        _enter(page, chart)
        group_a = page.evaluate(_LAYER_MARKERS, page.evaluate(_FIRST_SELECTOR))
        assert len(group_a) == 12, "the first layer's selector names no markers"

        previous = None
        for _ in range(3):
            spoken = _step(page, "ArrowRight")
            outlined = page.evaluate(_HIGHLIGHTED)
            assert len(outlined) == 1, (
                f"{spoken!r} is announced but {len(outlined)} markers are "
                "outlined: the swarm's markers carry no maidr attribute"
            )
            # A copy of one of this group's own markers, as seaborn drew it,
            # at the value just announced.
            assert outlined[0] in group_a
            assert abs(outlined[0][0] - at(_first_number(spoken))) < 0.01, spoken
            assert outlined[0] != previous
            previous = outlined[0]
        assert not errors, errors
    finally:
        page.close()


def test_a_vertical_swarm_outlines_the_point_it_announces(browser, tmp_path):
    # Vertical: a step across enters the category's column, and a step up
    # moves point by point within it; the value is then the marker's y.
    chart, at = _swarm(tmp_path, horizontal=False)
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    try:
        _enter(page, chart)
        group_a = page.evaluate(_LAYER_MARKERS, page.evaluate(_FIRST_SELECTOR))
        assert len(group_a) == 12

        _step(page, "ArrowRight")
        assert page.evaluate(_HIGHLIGHTED), "the column is announced, not outlined"
        for _ in range(2):
            spoken = _step(page, "ArrowUp")
            outlined = page.evaluate(_HIGHLIGHTED)
            assert len(outlined) == 1, spoken
            assert outlined[0] in group_a
            assert abs(outlined[0][1] - at(_first_number(spoken))) < 0.01, spoken
        assert not errors, errors
    finally:
        page.close()


def _inline(tmp_path, draw, name: str):
    """Save a chart whose markers matplotlib writes as inline ``<path>``s.

    Returns the page and a map from a data point to the SVG coordinate of
    its marker's centre, in the points the SVG is written in.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    import maidr

    fig, ax = plt.subplots()
    draw(ax)
    path = tmp_path / f"{name}.html"
    try:
        maidr.save_html(fig, file=str(path), use_cdn=False)
        scale = 72 / fig.dpi
        height = fig.get_figheight() * 72

        def at(x: float, y: float) -> tuple[float, float]:
            px, py = ax.transData.transform((x, y))
            return float(px * scale), float(height - py * scale)

    finally:
        plt.close("all")
    return path, at


#: The centre of each visible outline the core draws, by its bounding box.
_HIGHLIGHTED_CENTRES = """() => [...document.querySelectorAll("svg [data-maidr-owned]")]
  .filter((e) => getComputedStyle(e).visibility !== "hidden")
  .map((e) => { const b = e.getBBox(); return [b.x + b.width / 2, b.y + b.height / 2]; })"""


def _hue_style(ax):
    import pandas as pd
    import seaborn as sns

    frame = pd.DataFrame(
        {
            "x": [1, 2, 3, 4, 5, 6],
            "y": [6, 1, 5, 2, 4, 3],
            "g": ["a", "b", "a", "b", "a", "b"],
        }
    )
    sns.scatterplot(data=frame, x="x", y="y", hue="g", style="g", ax=ax)


def _sized(ax):
    ax.scatter([1, 2, 3, 4, 5], [5, 1, 4, 2, 3], s=[20, 60, 100, 140, 180])


@pytest.mark.parametrize(
    ("draw", "first_layer"),
    [
        (_hue_style, [(1, 6), (3, 5), (5, 4)]),
        (_sized, [(1, 5), (2, 1), (3, 4), (4, 2), (5, 3)]),
    ],
    ids=["seaborn hue style", "ax.scatter s=array"],
)
def test_inline_markers_outline_the_point_announced(
    browser, tmp_path, draw, first_layer
):
    # A marker that varies per point is written as an inline `<path>`, not a
    # `<use>` of one shared marker; the selectors named only the latter, so
    # these announced every point and outlined none.
    chart, at = _inline(tmp_path, draw, draw.__name__.strip("_"))
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    try:
        _enter(page, chart)
        for x, y in first_layer:
            spoken = _step(page, "ArrowRight")
            assert str(x) in spoken and str(y) in spoken, spoken
            outlined = page.evaluate(_HIGHLIGHTED_CENTRES)
            assert len(outlined) == 1, (
                f"{spoken!r} is announced but {len(outlined)} markers are "
                "outlined: the inline markers are not named by the selectors"
            )
            want = at(x, y)
            assert abs(outlined[0][0] - want[0]) < 1, (spoken, outlined, want)
            assert abs(outlined[0][1] - want[1]) < 1, (spoken, outlined, want)
        assert not errors, errors
    finally:
        page.close()
