"""TensorBoard's PR curves are driven from the keyboard.

``maidr.read_tensorboard_pr_curves`` emits a ``pr_curve`` layer, which only a
maidr.js carrying that trace can read, and the markup tests cannot tell
whether the bundled one does. This opens the PR curves PyTorch logged for a
good and a poor classifier: Right moves along the good curve, each point
saying its threshold and how far its precision sits above the chance level,
and Down and Up move between the two curves at the cursor's recall -- which
the poor curve reaches only from 0.35 -- with the point being read outlined.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

LOGDIR = Path(__file__).parent.parent / "tensorboard" / "fixtures" / "torch_pr_curves"

#: Installed on `window` by the bundle once the inlined JavaScript has parsed.
_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000

#: Where the core writes what it announces for the current point.
_TEXT = "#maidr-text-container"
_OUTLINED = "() => document.querySelectorAll('[id^=maidr-highlight]').length"


@pytest.fixture
def page_path(tmp_path) -> Path:
    import maidr

    (chart,) = maidr.read_tensorboard_pr_curves(LOGDIR)
    path = tmp_path / "pr_curves.html"
    # Bundled rather than CDN: the shipped bundle is the thing under test.
    maidr.save_html(chart, file=str(path), use_cdn=False)
    maidr.close(chart)
    return path


def _step(page, key: str, wait_ms: int = 500) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(wait_ms)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def test_the_points_and_curves_of_a_pr_chart_are_read(browser, page_path):
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
        assert "Recall is 0.07, Precision is 1, Curve is good" in spoken, spoken
        assert "Threshold is 1" in spoken, spoken
        assert "Above baseline is 0.68" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        # Past recall 0.35, where the poor curve starts, so there is a curve
        # below this one to move to.
        for _ in range(40):
            spoken = _step(page, "ArrowRight", wait_ms=60)
        spoken = _step(page, "ArrowRight")
        assert "Recall is 0.84, Precision is 1, Curve is good" in spoken, spoken

        spoken = _step(page, "ArrowDown")
        assert "Recall is 0.84, Precision is 0.53, Curve is poor" in spoken, spoken
        assert "Above baseline is 0.21" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        spoken = _step(page, "ArrowUp")
        assert "Recall is 0.84, Precision is 1, Curve is good" in spoken, spoken
        assert not errors, errors
    finally:
        page.close()
