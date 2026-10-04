"""A hyperparameter sweep's parallel coordinates are driven from the keyboard.

The lines are drawn on axes scaled one by one and registered as a layer that
carries the unscaled values, naming each session's line by its gid. This opens
the sweep: Right moves along one session's axes, announcing each value in its
own units, Up moves to another session, and the session's line is outlined.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

SWEEP = Path(__file__).parent.parent / "tensorboard" / "fixtures" / "hparams_sweep"

_BUNDLE_READY = "() => window.maidrLive !== undefined"
_TEXT = "#maidr-text-container"
_OUTLINED = "() => document.querySelectorAll('[id^=maidr-highlight]').length"


@pytest.fixture
def page_path(tmp_path) -> Path:
    import maidr

    parallel, matrix = maidr.read_tensorboard_hparams(SWEEP)
    path = tmp_path / "sweep.html"
    maidr.save_html(parallel, file=str(path), use_cdn=False)
    maidr.close(parallel)
    maidr.close(matrix)
    return path


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(400)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def test_a_session_is_walked_across_its_axes(browser, page_path):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    page.goto(page_path.as_uri(), wait_until="load")
    page.wait_for_function(_BUNDLE_READY, timeout=30_000)
    page.click("svg[maidr]", force=True)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1_500)
    try:
        spoken = _step(page, "ArrowRight")
        assert "learning_rate" in spoken and "0.1" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1
        spoken = _step(page, "ArrowRight")
        assert "optimizer" in spoken, spoken
        spoken = _step(page, "ArrowUp")
        assert "session" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1
        assert not errors, errors
    finally:
        page.close()
