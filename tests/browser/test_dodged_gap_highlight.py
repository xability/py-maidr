"""A gap in a dodged series does not shift the highlight of the bars after it.

``sns.barplot(hue=)`` drops a ``NaN`` cell before drawing, so the series that
lacks it is a rectangle short; the schema fills the cell with ``null`` (#752)
and keeps one flat selector. That only reads right if the core, pairing the
series' cells with the rectangles it finds in the DOM, hands the ``null`` a
placeholder *without* taking a rectangle for it -- otherwise every bar after
the gap is outlined one to the left, and the last one not at all.

``maidr/core/plot/grouped_barplot.py`` quotes the shipped bundle's cursor to
say that it does. This is what would catch a bundle bump changing it: a
reader steps onto the missing cell, hears it named as missing, steps on, and
the outline lands on the bar drawn for that cell.
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

#: The rectangles matplotlib drew, in document order. The core stands a hidden
#: clone beside each one when it initialises (`Svg.cloneHidden`), marked
#: `data-maidr-owned`; those are not bars.
_DRAWN_BARS = """() => [...document.querySelectorAll(
  "g[maidr] > path:not([data-maidr-owned])"
)].map((p) => p.getAttribute("d"))"""

#: The outline the core draws for the current point: a clone of the bar's own
#: path, so its `d` says which bar it copies.
_HIGHLIGHTED = """() => [...document.querySelectorAll("[id^=maidr-highlight]")]
  .map((e) => e.getAttribute("d"))"""


@pytest.fixture
def gapped_hue_chart(tmp_path) -> Path:
    """``a``, ``b``, ``c`` split by ``g1``/``g2``, with ``(b, g2)`` NaN."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import seaborn as sns

    import maidr

    frame = pd.DataFrame(
        {
            "cat": ["a", "b", "c"] * 2,
            "grp": ["g1"] * 3 + ["g2"] * 3,
            "val": [1.0, 2.0, 3.0, 4.0, np.nan, 6.0],
        }
    )
    fig, ax = plt.subplots()
    sns.barplot(data=frame, x="cat", y="val", hue="grp", ax=ax)
    path = tmp_path / "gapped_hue.html"
    try:
        # Bundled rather than CDN: the shipped bundle is the thing under test.
        maidr.save_html(fig, file=str(path), use_cdn=False)
    finally:
        plt.close("all")
    return path


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(500)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def test_the_bar_after_a_gap_is_the_one_highlighted(browser, gapped_hue_chart):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    try:
        page.goto(gapped_hue_chart.as_uri(), wait_until="load")
        page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
        page.click("svg[maidr]", force=True)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1_500)

        # The premise: five rectangles, g1's three then g2's two, and none
        # for (b, g2). Their `d` attributes differ, so a `d` names a bar.
        bars = page.evaluate(_DRAWN_BARS)
        assert len(bars) == 5 and len(set(bars)) == 5
        a_g2, c_g2 = bars[3], bars[4]

        # Onto (a, g1), then up onto the g2 series.
        _step(page, "ArrowRight")
        spoken = _step(page, "ArrowUp")
        assert "g2" in spoken and "4" in spoken, spoken
        assert page.evaluate(_HIGHLIGHTED) == [a_g2]

        # The gap: named as missing, and no rectangle is outlined for it,
        # since none was drawn.
        spoken = _step(page, "ArrowRight")
        assert "b" in spoken and "missing" in spoken, spoken
        assert a_g2 not in page.evaluate(_HIGHLIGHTED)

        # Past it: the rectangle for (c, g2), not (a, g2) again and not none.
        spoken = _step(page, "ArrowRight")
        assert "c" in spoken and "6" in spoken, spoken
        assert page.evaluate(_HIGHLIGHTED) == [c_g2], (
            "the outline after the gap is on the wrong bar: the core took a "
            "rectangle for the null cell, so every bar after it is shifted."
        )
        assert not errors, errors
    finally:
        page.close()
