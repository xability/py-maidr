"""A plotly box plot is walked and outlined the way it is drawn.

A horizontal layer's boxes were emitted bottom first, the order plotly draws
them up the page; maidr.js expects them top first and reverses them, so the
reader started on the top box and Up moved down. And every statistic named
the one path plotly draws a whole box as, so Minimum, 25%, 50%, 75% and
Maximum all outlined the whole box. Boxes grouped at one category were walked
trace by trace, and under a ``categoryorder`` named the box drawn somewhere
else. These drive the shipped bundle over a saved page, hold Up to moving the
outline up the page and Right to moving it across, and hold each statistic's
outline to a line where plotly draws that value.

plotly.js is linked from ``cdn.plot.ly``; the page is handed the copy the
installed ``plotly`` package ships instead, so nothing here needs a network.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

plotly = pytest.importorskip("plotly")

#: The plotly.js the installed package ships.
_PLOTLY_JS = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"

_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000

#: Where the core writes what it announces for the current point.
_TEXT = "#maidr-text-container"

#: The visible outlines the core draws: their screen boxes.
_OUTLINED = """() => [...document.querySelectorAll("svg [data-maidr-owned]")]
  .filter((e) => getComputedStyle(e).visibility !== "hidden"
    && e.getAttribute("visibility") !== "hidden")
  .map((e) => {
    const r = e.getBoundingClientRect();
    return {x: r.x, y: r.y, width: r.width, height: r.height};
  })"""

#: Where plotly draws a value of one axis, on screen: the plot area's offset
#: in the svg and the axis's own linear mapping, as plotly places marks.
_SCREEN_VALUE = """([letter, value]) => {
  const svg = document.querySelector("svg[maidr]");
  const gd = svg.closest(".js-plotly-plot")
    || document.querySelector(".js-plotly-plot");
  const axis = gd._fullLayout[letter + "axis"];
  const box = svg.getBoundingClientRect();
  return (letter === "x" ? box.x : box.y) + axis._offset + axis.l2p(value);
}"""

#: The boxes the payload describes, as the page holds it.
_BOXES = """() => JSON.parse(document.querySelector("svg[maidr]")
  .getAttribute("maidr")).subplots[0][0].layers[0].data"""

#: How far, in CSS pixels, an outline may sit from its value. Plotly keeps a
#: median at least a pixel inside the box, so it is not drawn exactly there.
_TOLERANCE_PX = 1.5

#: The sections of a box a reader steps through, by what they are announced
#: as, and the statistic each reads.
_SECTIONS = {
    "Minimum": "min",
    "25%": "q1",
    "50%": "q2",
    "75%": "q3",
    "Maximum": "max",
}

GROUPS = ["Group 1", "Group 2", "Group 3"]


def _boxes(tmp_path: Path, orientation: str) -> Path:
    """Three boxes, one trace each, saved with the bundled maidr.js."""
    import numpy as np
    import plotly.graph_objects as go

    import maidr

    rng = np.random.default_rng(7)
    samples = "x" if orientation == "h" else "y"
    fig = go.Figure(
        [
            go.Box(**{samples: rng.normal(50 + 20 * i, 5, 40).tolist()}, name=name)
            for i, name in enumerate(GROUPS)
        ]
    )
    path = tmp_path / f"plotly_box_{orientation}.html"
    maidr.save_html(fig, file=str(path), use_cdn=False)
    return path


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
    page.keyboard.press("Tab")
    page.wait_for_timeout(400)
    return page, errors


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(400)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def _outline(page) -> dict:
    """The one visible outline."""
    outlined = page.evaluate(_OUTLINED)
    assert len(outlined) == 1, outlined
    return outlined[0]


def _centre_y(box: dict) -> float:
    return box["y"] + box["height"] / 2


def _group(spoken: str) -> str:
    found = re.search(r"Group (\d)", spoken)
    assert found, spoken
    return f"Group {found.group(1)}"


def test_up_walks_horizontal_boxes_up_the_page(browser, tmp_path):
    page, errors = _open(browser, _boxes(tmp_path, "h"))
    try:
        # Onto a statistic, which has a mark to outline.
        for _ in range(4):
            spoken = _step(page, "ArrowRight")
            if "50%" in spoken:
                break
        assert _group(spoken) == "Group 1", "did not start on the bottom box"
        below = _centre_y(_outline(page))

        spoken = _step(page, "ArrowUp")
        assert _group(spoken) == "Group 2", spoken
        middle = _centre_y(_outline(page))
        assert middle < below, "ArrowUp moved the outline down the page"

        spoken = _step(page, "ArrowUp")
        assert _group(spoken) == "Group 3", spoken
        assert _centre_y(_outline(page)) < middle

        spoken = _step(page, "ArrowDown")
        assert _group(spoken) == "Group 2", spoken
        assert _centre_y(_outline(page)) == pytest.approx(middle, abs=0.5)
        assert not errors, errors
    finally:
        page.close()


@pytest.mark.parametrize("orientation", ["v", "h"])
def test_each_statistic_outlines_its_own_mark(browser, tmp_path, orientation):
    page, errors = _open(browser, _boxes(tmp_path, orientation))
    # The value axis, and the outline's extent across it, which for a line
    # drawn across the box is its stroke alone. A box's statistics run along
    # the value axis, so they are stepped through with Up on a vertical box
    # and with Right on a horizontal one.
    letter, across = ("y", "height") if orientation == "v" else ("x", "width")
    key = "ArrowUp" if orientation == "v" else "ArrowRight"
    try:
        boxes = {box["z"]: box for box in page.evaluate(_BOXES)}
        seen: dict[str, float] = {}
        for _ in range(8):
            spoken = _step(page, key)
            section = next((s for s in _SECTIONS if f"{s} " in spoken), None)
            if section is None:
                continue
            statistic = _SECTIONS[section]
            outline = _outline(page)
            centre = outline[letter] + outline[across] / 2
            want = page.evaluate(
                _SCREEN_VALUE, [letter, boxes[_group(spoken)][statistic]]
            )
            assert outline[across] < 8, (spoken, outline)
            assert centre == pytest.approx(want, abs=_TOLERANCE_PX), (spoken, outline)
            seen[statistic] = centre

        assert set(seen) == set(_SECTIONS.values()), seen
        # Five marks, at five places: the outline moved at every step.
        assert len({round(centre) for centre in seen.values()}) == 5, seen
        assert not errors, errors
    finally:
        page.close()


#: Two traces grouped at three days, the second written in another order,
#: drawn in the order the category array gives.
_DAYS = ["Sat", "Fri", "Thu"]
_GROUPED_ORDER = [f"{day}, {who}" for day in _DAYS for who in ("Male", "Female")]


def _grouped_boxes(tmp_path: Path) -> Path:
    """Grouped boxes under a ``categoryarray``, saved with the bundled maidr.js."""
    import plotly.graph_objects as go

    import maidr

    def trace(days: list[str], bases: list[int], name: str) -> go.Box:
        return go.Box(
            x=[day for day in days for _ in range(7)],
            y=[base + step for base in bases for step in range(7)],
            name=name,
        )

    fig = go.Figure(
        [
            trace(["Thu", "Fri", "Sat"], [10, 20, 30], "Male"),
            trace(["Sat", "Thu", "Fri"], [35, 15, 25], "Female"),
        ],
        layout={
            "boxmode": "group",
            "xaxis": {"categoryorder": "array", "categoryarray": _DAYS},
        },
    )
    path = tmp_path / "plotly_box_grouped.html"
    maidr.save_html(fig, file=str(path), use_cdn=False)
    return path


def test_right_walks_grouped_boxes_across_the_page(browser, tmp_path):
    page, errors = _open(browser, _grouped_boxes(tmp_path))
    try:
        boxes = {box["z"]: box for box in page.evaluate(_BOXES)}
        for _ in range(4):
            spoken = _step(page, "ArrowUp")
            if "50%" in spoken:
                break
        lefts: list[float] = []
        for index, name in enumerate(_GROUPED_ORDER):
            if index:
                spoken = _step(page, "ArrowRight")
            assert name in spoken, (name, spoken)
            outline = _outline(page)
            # On the announced box's median, and right of the box before it.
            want = page.evaluate(_SCREEN_VALUE, ["y", boxes[name]["q2"]])
            assert _centre_y(outline) == pytest.approx(want, abs=_TOLERANCE_PX), (
                name,
                outline,
            )
            lefts.append(outline["x"])
        assert lefts == sorted(lefts) and len(set(lefts)) == len(lefts), lefts
        assert not errors, errors
    finally:
        page.close()
