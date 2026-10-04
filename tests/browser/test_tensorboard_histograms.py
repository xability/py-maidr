"""A TensorBoard histogram is driven from the keyboard as a ridgeline.

``maidr.read_tensorboard_histograms`` draws one ridge per step and registers a
ridgeline layer naming each ridge by its gid. This opens the weights of a
PyTorch run: Right moves along the values, Up moves to a later step while
holding the value, so the count heard is the same bin's a step later, and the
step's own ridge is the one outlined.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

LOGDIR = Path(__file__).parent.parent / "tensorboard" / "fixtures" / "torch_histograms"

#: Installed on `window` by the bundle once the inlined JavaScript has parsed.
_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000

#: Where the core writes what it announces for the current point.
_TEXT = "#maidr-text-container"
_OUTLINED = "() => document.querySelectorAll('[id^=maidr-highlight]').length"


@pytest.fixture
def page_path(tmp_path) -> Path:
    import maidr

    (chart,) = maidr.read_tensorboard_histograms(LOGDIR)
    path = tmp_path / "weights.html"
    # Bundled rather than CDN: the shipped bundle is the thing under test.
    maidr.save_html(chart, file=str(path), use_cdn=False)
    maidr.close(chart)
    return path


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(400)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def test_up_moves_to_a_later_step_holding_the_value(browser, page_path):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    page.goto(page_path.as_uri(), wait_until="load")
    page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
    page.click("svg[maidr]", force=True)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1_500)
    try:
        for _ in range(15):
            spoken = _step(page, "ArrowRight")
        assert "Step 0" in spoken and "Count is" in spoken, spoken
        value = spoken.split(",")[0]
        assert value.startswith("weights is"), spoken

        spoken = _step(page, "ArrowUp")
        assert spoken.startswith(value) and "Step 1" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        spoken = _step(page, "ArrowUp")
        assert spoken.startswith(value) and "Step 2" in spoken, spoken

        spoken = _step(page, "ArrowDown")
        assert "Step 1" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1
        assert not errors, errors
    finally:
        page.close()
