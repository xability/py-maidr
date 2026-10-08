"""A scikit-learn precision-recall chart is driven from the keyboard.

``PrecisionRecallDisplay`` is read as a ``pr_curve`` layer, which only a
maidr.js carrying that trace can read. This opens two classifiers' curves on
one axes, drawn with the chance level: Right moves along the better curve,
each point saying how far its precision sits above the share of positives,
and Down and Up move between the two curves at the same recall, with the
point being read outlined.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.browser

#: Installed on `window` by the bundle once the inlined JavaScript has parsed.
_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000

#: Where the core writes what it announces for the current point.
_TEXT = "#maidr-text-container"
_OUTLINED = "() => document.querySelectorAll('[id^=maidr-highlight]').length"


@pytest.fixture
def page_path(tmp_path) -> Path:
    metrics = pytest.importorskip("sklearn.metrics")
    import maidr

    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 200)
    good = y * 0.6 + rng.random(200) * 0.6
    poor = y * 0.15 + rng.random(200)
    display = metrics.PrecisionRecallDisplay.from_predictions(
        y, good, name="good", plot_chance_level=True
    )
    metrics.PrecisionRecallDisplay.from_predictions(
        y, poor, name="poor", ax=display.ax_
    )
    path = tmp_path / "pr_curve.html"
    # Bundled rather than CDN: the shipped bundle is the thing under test.
    maidr.save_html(display.figure_, file=str(path), use_cdn=False)
    maidr.close(display.figure_)
    return path


def _step(page, key: str, wait_ms: int = 500) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(wait_ms)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def test_the_points_and_classifiers_of_a_pr_chart_are_read(browser, page_path):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    page.goto(page_path.as_uri(), wait_until="load")
    page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
    page.click("svg[maidr]", force=True)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1_500)
    try:
        spoken = _step(page, "ArrowRight")
        assert "is 0," in spoken and "Above baseline is 0.44" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        for _ in range(59):
            _step(page, "ArrowRight", wait_ms=60)
        spoken = _step(page, "ArrowRight")
        assert "is 0.54" in spoken and "Curve is good" in spoken, spoken
        assert "Above baseline is 0.44" in spoken, spoken

        spoken = _step(page, "ArrowDown")
        assert "is 0.54" in spoken and "Curve is poor" in spoken, spoken
        assert "Above baseline is 0.12" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        spoken = _step(page, "ArrowUp")
        assert "Curve is good" in spoken, spoken
        assert not errors, errors
    finally:
        page.close()
