"""A heatmap drawn as an image outlines the cell being announced.

``ax.imshow`` draws a heatmap as one ``<image>``, and the layer had no
selectors: every cell was announced and none was outlined (py-example-a#7).
maidr.js lays a rectangle over each cell of a single ``<image>`` from the
image's ``x``, ``y``, ``width`` and ``height``, which ``HeatPlot.finish_svg``
now makes the image's box on the page.

This drives the shipped bundle: a reader steps right and up through the grid,
and the outline is held to the box of the cell whose value is announced.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

#: Installed on `window` by the bundle once the inlined JavaScript has parsed.
_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000

#: Where the core writes what it announces for the current point.
_TEXT = "#maidr-text-container"

#: The outline the core draws for the current cell: a copy of the rectangle
#: it laid over that cell.
_OUTLINE = """() => [...document.querySelectorAll('[id^="maidr-highlight"]')]
  .map((e) => ["x", "y", "width", "height"].map((a) => Number(e.getAttribute(a))))"""


@pytest.fixture
def heatmap(tmp_path) -> tuple[Path, object, list]:
    """A 3 x 4 grid of distinct values; return the page, the grid, and the
    box of each cell in the SVG's points, row by row from the top."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    import maidr

    grid = 100 + np.arange(12).reshape(3, 4)
    fig, ax = plt.subplots()
    image = ax.imshow(grid)
    ax.set_xticks(range(4), labels=["a", "b", "c", "d"])
    ax.set_yticks(range(3), labels=["top", "middle", "bottom"])
    path = tmp_path / "heatmap.html"
    try:
        # Bundled rather than CDN: the shipped bundle is the thing under test.
        maidr.save_html(fig, file=str(path), use_cdn=False)
        left, right, bottom, top = image.get_extent()
        corners = ax.transData.transform([(left, top), (right, bottom)])
        corners = corners * 72 / fig.dpi
        corners[:, 1] = fig.get_figheight() * 72 - corners[:, 1]
    finally:
        plt.close("all")
    (x0, y0), (x1, y1) = corners.min(axis=0), corners.max(axis=0)
    width, height = (x1 - x0) / 4, (y1 - y0) / 3
    boxes = [
        [(x0 + c * width, y0 + r * height, width, height) for c in range(4)]
        for r in range(3)
    ]
    return path, grid, boxes


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(500)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def _cell_of(spoken: str, grid) -> tuple[int, int]:
    """The row and column of the one value of the grid the text names."""
    named = {int(token) for token in re.findall(r"\d+", spoken)}
    found = [(r, c) for (r, c), value in _cells(grid) if value in named]
    assert len(found) == 1, spoken
    return found[0]


def _cells(grid):
    for r, row in enumerate(grid.tolist()):
        for c, value in enumerate(row):
            yield (r, c), value


def test_the_announced_cell_is_outlined(browser, heatmap):
    chart, grid, boxes = heatmap
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    try:
        page.goto(chart.as_uri(), wait_until="load")
        page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
        page.click("svg[maidr]", force=True)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1_500)

        visited = []
        for key in ("ArrowRight", "ArrowRight", "ArrowUp", "ArrowUp"):
            row, column = _cell_of(_step(page, key), grid)
            visited.append((row, column))
            outline = page.evaluate(_OUTLINE)
            assert len(outline) == 1, f"{len(outline)} outlines for one cell"
            assert outline[0] == pytest.approx(boxes[row][column], abs=1.0), (
                f"cell {row, column} is outlined at {outline[0]}, drawn at "
                f"{boxes[row][column]}"
            )
        # The walk moved: right along the bottom row, then up its column.
        assert len(set(visited)) >= 3, visited
        assert not errors, errors
    finally:
        page.close()
