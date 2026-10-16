"""A ``seaborn.clustermap`` is walked from the keyboard, heatmap and tree.

The bundled maidr.js is handed a clustermap's figure: the clustered heatmap,
and each dendrogram as a ``tree`` layer. This opens it, enters the heatmap
and reads a cell, then enters the row dendrogram and walks it from the root
down to a leaf -- the tree navigated by parent, child and sibling.
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


@pytest.fixture
def page_path(tmp_path) -> Path:
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
    path = tmp_path / "clustermap.html"
    # Bundled rather than CDN: the shipped bundle is the thing under test.
    maidr.save_html(grid, file=str(path), use_cdn=False)
    maidr.close(grid.figure)
    return path


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(500)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def test_the_heatmap_and_its_row_tree_are_walked(browser, page_path):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    page.goto(page_path.as_uri(), wait_until="load")
    page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
    page.click("svg[maidr]", force=True)
    page.wait_for_timeout(1_000)
    try:
        spoken = _step(page, "ArrowRight")
        assert "Row dendrogram" in spoken and "tree plot" in spoken, spoken
        spoken = _step(page, "ArrowRight")
        assert "Clustered heatmap" in spoken and "heat plot" in spoken, spoken

        _step(page, "Enter")
        spoken = _step(page, "ArrowRight")
        # The bottom-left cell: the last row in clustered order, `e`.
        assert "sample is W, gene is e, Z is -0.54" in spoken, spoken
        assert page.evaluate(
            "document.querySelectorAll('[id^=maidr-highlight]').length"
        )

        _step(page, "Escape")
        spoken = _step(page, "ArrowLeft")
        assert "Row dendrogram" in spoken, spoken
        _step(page, "Enter")

        spoken = _step(page, "ArrowRight")
        assert "gene is d to e (distance 2.99), Children is 2" in spoken, spoken
        spoken = _step(page, "ArrowDown")
        assert spoken.startswith("gene is d"), spoken
        spoken = _step(page, "ArrowRight")
        assert "gene is c to e (distance 2.1)" in spoken, spoken
        spoken = _step(page, "ArrowDown")
        assert "gene is c, Path is d to e (distance 2.99) > c to e" in spoken, spoken
        assert errors == []
    finally:
        page.close()
