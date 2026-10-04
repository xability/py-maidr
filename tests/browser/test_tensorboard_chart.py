"""A TensorBoard scalar chart is driven from the keyboard.

``maidr.read_tensorboard_scalars`` draws a tag's runs with matplotlib, and the
markup tests cannot tell whether the page a reader gets from it works. This
opens the loss chart of a Keras run: Right moves along the epochs, where the
logged and smoothed curves start at the same value and are announced as
meeting there, Up reaches every other line at the same epoch -- the smoothed
curve, and the validation run logged and smoothed -- and the point being read
is outlined.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

LOGDIR = Path(__file__).parent.parent / "tensorboard" / "fixtures" / "keras"

#: Installed on `window` by the bundle once the inlined JavaScript has parsed.
_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000

#: Where the core writes what it announces for the current point.
_TEXT = "#maidr-text-container"
_OUTLINED = "() => document.querySelectorAll('[id^=maidr-highlight]').length"


@pytest.fixture
def page_path(tmp_path) -> Path:
    import maidr

    (chart,) = maidr.read_tensorboard_scalars(LOGDIR, tags=["epoch_loss"])
    path = tmp_path / "loss.html"
    # Bundled rather than CDN: the shipped bundle is the thing under test.
    maidr.save_html(chart, file=str(path), use_cdn=False)
    maidr.close(chart)
    return path


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(500)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def test_the_epochs_and_runs_of_a_loss_chart_are_read(browser, page_path):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    page.goto(page_path.as_uri(), wait_until="load")
    page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
    page.click("svg[maidr]", force=True)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1_500)
    try:
        # Smoothing starts at the first value, so the two curves meet there.
        spoken = _step(page, "ArrowRight")
        assert "Step is 0" in spoken and "epoch_loss is 0.76" in spoken, spoken
        assert "intersection at (train, train (smoothed))" in spoken, spoken

        spoken = _step(page, "ArrowRight")
        assert "Step is 1" in spoken and "train" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        # Up moves to the next line above at this step, whichever run it is.
        groups = set()
        for _ in range(3):
            spoken = _step(page, "ArrowUp")
            assert "Step is 1" in spoken, spoken
            groups.add(spoken.rsplit("Group is ", 1)[-1])
        assert groups == {"train (smoothed)", "validation", "validation (smoothed)"}
        assert page.evaluate(_OUTLINED) == 1
        assert not errors, errors
    finally:
        page.close()
