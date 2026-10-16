"""A ``seaborn.clustermap`` is walked from the keyboard, heatmap and tree.

The bundled maidr.js is handed a clustermap's figure: the clustered heatmap,
and each dendrogram as a ``tree`` layer. This opens it, enters the heatmap
and reads a cell, then enters the row dendrogram and walks it from the root
down to a leaf -- the tree navigated by parent, child and sibling -- and the
column dendrogram's root. Each node the reader stands on is outlined where
seaborn drew it: a merge at the apex of its link, a leaf at its tip.
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


#: How far, as a share of the figure's width or height, an outline's centre
#: may lie from the node it marks -- about six pixels on this page.
_NEAR = 0.006


@pytest.fixture
def page(tmp_path) -> tuple[Path, dict[str, tuple[float, float]]]:
    """
    The page, and where each node the test visits is drawn.

    Each node is placed from the links seaborn drew, not from the marks the
    highlight uses, as a share of the figure from its top-left corner.
    """
    import numpy as np
    import pandas as pd
    import seaborn as sns

    import maidr

    rng = np.random.default_rng(0)
    frame = pd.DataFrame(
        rng.normal(size=(5, 4)),
        index=pd.Index(list("abcde"), name="gene"),
        columns=pd.Index(list("WXYZ"), name="sample"),
    )
    grid = sns.clustermap(frame)

    def share(ax, x: float, y: float) -> tuple[float, float]:
        fx, fy = grid.figure.transFigure.inverted().transform(
            ax.transData.transform((x, y))
        )
        return float(fx), float(1 - fy)

    def apex(ax, along: list, height: list, at: int, rotated: bool):
        x, y = (along[at][1] + along[at][2]) / 2, height[at][1]
        return share(ax, *((y, x) if rotated else (x, y)))

    rows, cols = grid.dendrogram_row, grid.dendrogram_col
    row_heights = [link[1] for link in rows.dependent_coord]
    order = list(grid.data2d.index)
    expected = {
        # The root merges last, at the greatest distance.
        "row root": apex(
            grid.ax_row_dendrogram,
            rows.independent_coord,
            rows.dependent_coord,
            int(np.argmax(row_heights)),
            rotated=True,
        ),
        "c to e": apex(
            grid.ax_row_dendrogram,
            rows.independent_coord,
            rows.dependent_coord,
            int(np.argmin([abs(h - 2.1) for h in row_heights])),
            rotated=True,
        ),
        # A leaf is at its tip, on the baseline at distance 0.
        "d": share(grid.ax_row_dendrogram, 0, 5 + 10 * order.index("d")),
        "c": share(grid.ax_row_dendrogram, 0, 5 + 10 * order.index("c")),
        "column root": apex(
            grid.ax_col_dendrogram,
            cols.independent_coord,
            cols.dependent_coord,
            int(np.argmax([link[1] for link in cols.dependent_coord])),
            rotated=False,
        ),
    }
    path = tmp_path / "clustermap.html"
    # Bundled rather than CDN: the shipped bundle is the thing under test.
    maidr.save_html(grid, file=str(path), use_cdn=False)
    maidr.close(grid.figure)
    return path, expected


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(500)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def _outlined(page) -> tuple[float, float, float]:
    """
    The centre of the one outline on the page, as a share of the figure, and
    its width in pixels.
    """
    boxes = page.evaluate(
        """() => {
          const figure = document.querySelector('svg[maidr]').getBoundingClientRect();
          return Array.from(document.querySelectorAll('[id^=maidr-highlight]'))
            .map(element => element.getBoundingClientRect())
            .map(box => [
              (box.x + box.width / 2 - figure.x) / figure.width,
              (box.y + box.height / 2 - figure.y) / figure.height,
              box.width,
            ]);
        }"""
    )
    assert len(boxes) == 1, boxes
    return tuple(boxes[0])


def _assert_outlined_at(page, where: tuple[float, float]) -> None:
    x, y, width = _outlined(page)
    # A dot on the node, not an outline of the whole tree.
    assert 0 < width < 20, width
    assert abs(x - where[0]) < _NEAR and abs(y - where[1]) < _NEAR, (
        (x, y),
        where,
    )


def test_the_heatmap_and_its_trees_are_walked_and_outlined(browser, page):
    page_path, expected = page
    tab = browser.new_page()
    errors: list[str] = []
    tab.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    tab.goto(page_path.as_uri(), wait_until="load")
    tab.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
    tab.click("svg[maidr]", force=True)
    tab.wait_for_timeout(1_000)
    try:
        # The panels in reading order: the colorbar's corner, the column
        # dendrogram, then the row dendrogram and the heatmap below them.
        spoken = _step(tab, "ArrowRight")
        assert "Subplot 1 of 4" in spoken, spoken
        spoken = _step(tab, "ArrowDown")
        assert "Row dendrogram" in spoken and "tree plot" in spoken, spoken
        spoken = _step(tab, "ArrowRight")
        assert "Clustered heatmap" in spoken and "heat plot" in spoken, spoken

        _step(tab, "Enter")
        spoken = _step(tab, "ArrowRight")
        # The bottom-left cell: the last row in clustered order, `e`.
        assert "sample is W, gene is e, Z is -0.54" in spoken, spoken
        assert tab.evaluate("document.querySelectorAll('[id^=maidr-highlight]').length")

        _step(tab, "Escape")
        spoken = _step(tab, "ArrowLeft")
        assert "Row dendrogram" in spoken, spoken
        _step(tab, "Enter")

        spoken = _step(tab, "ArrowRight")
        assert "gene is d to e (distance 2.99), Children is 2" in spoken, spoken
        _assert_outlined_at(tab, expected["row root"])
        spoken = _step(tab, "ArrowDown")
        assert spoken.startswith("gene is d"), spoken
        _assert_outlined_at(tab, expected["d"])
        spoken = _step(tab, "ArrowRight")
        assert "gene is c to e (distance 2.1)" in spoken, spoken
        _assert_outlined_at(tab, expected["c to e"])
        spoken = _step(tab, "ArrowDown")
        assert "gene is c, Path is d to e (distance 2.99) > c to e" in spoken, spoken
        _assert_outlined_at(tab, expected["c"])

        _step(tab, "Escape")
        spoken = _step(tab, "ArrowUp")
        assert "Subplot 1 of 4" in spoken, spoken
        spoken = _step(tab, "ArrowRight")
        assert "Column dendrogram" in spoken, spoken
        _step(tab, "Enter")
        spoken = _step(tab, "ArrowRight")
        assert "Children is 2" in spoken, spoken
        _assert_outlined_at(tab, expected["column root"])
        assert errors == []
    finally:
        tab.close()
