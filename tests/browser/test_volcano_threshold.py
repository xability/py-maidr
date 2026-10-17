"""A declared volcano reads through its threshold in the shipped maidr.js.

``maidr.volcano`` emits a ``volcano`` layer: ``VolcanoPoint`` data, the
threshold under ``thresholdOptions`` and the point layer's selector. Each half
is pinned in ``tests/core/plot/test_volcano.py`` against the grammar; this is
what says maidr.js actually reads them -- the rotor offers the points that
clear the threshold, walks them strongest first with each one's name, outlines
each, and the description opens with how many cleared it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000
_TEXT = "#maidr-text-container"
_OUTLINES = "() => document.querySelectorAll('[id^=maidr-highlight]').length"


@pytest.fixture
def volcano_page(tmp_path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    import maidr

    fig, ax = plt.subplots()
    points = ax.scatter([-2.5, 0.1, 3.2, 0.4], [6.0, 0.4, 8.1, 9.0])
    ax.axhline(1.3, linestyle="--")
    ax.set_xlabel("log2 fold change")
    ax.set_ylabel("-log10 p")
    # LOUD clears significance and not the effect cutoff, so it is not a hit.
    maidr.volcano(
        points,
        significance=1.3,
        effect=1.0,
        labels=["TP53", "GAPDH", "MYC", "LOUD"],
    )
    path = tmp_path / "volcano.html"
    try:
        # Bundled rather than CDN: the shipped bundle is the thing under test.
        maidr.save_html(fig, file=str(path), use_cdn=False)
    finally:
        plt.close("all")
    return path


def _press(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(400)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def test_the_rotor_walks_the_named_hits(browser, volcano_page):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    try:
        page.goto(volcano_page.as_uri(), wait_until="load")
        page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
        page.click("svg[maidr]", force=True)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1_500)

        # Grid, point, then the significant points: offered only because a
        # threshold was declared and something clears it.
        for _ in range(3):
            _press(page, "Alt+Shift+ArrowUp")

        spoken = _press(page, "ArrowRight")
        assert "MYC" in spoken and "cleared" in spoken, spoken
        assert page.evaluate(_OUTLINES) == 1
        spoken = _press(page, "ArrowRight")
        assert "TP53" in spoken, spoken
        assert page.evaluate(_OUTLINES) == 1
        spoken = _press(page, "ArrowRight")
        assert "No significant points" in spoken, spoken

        page.keyboard.press("d")
        page.wait_for_timeout(1_000)
        described = page.evaluate("document.querySelector('[role=dialog]')?.innerText")
        assert "Points clearing the threshold: 2 of 4" in described, described
        assert "MYC, TP53" in described, described
        assert not errors, errors
    finally:
        page.close()
