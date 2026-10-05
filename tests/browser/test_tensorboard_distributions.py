"""TensorBoard's distributions are driven from the keyboard.

``maidr.read_tensorboard_distributions`` emits a ``percentile_band`` layer,
which only a maidr.js carrying that trace can read, and the markup tests
cannot tell whether the bundled one does. This opens the distribution of a
TensorFlow layer's activations: the reader enters on the median, each step
saying the band around it, Up walks the quantiles at that step to the
maximum, naming the band each one bounds, and Right moves to the next step
on the same quantile, with the band being read outlined.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

LOGDIR = Path(__file__).parent.parent / "tensorboard" / "fixtures" / "tf_histograms"

#: Installed on `window` by the bundle once the inlined JavaScript has parsed.
_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000

#: Where the core writes what it announces for the current point.
_TEXT = "#maidr-text-container"
_OUTLINED = "() => document.querySelectorAll('[id^=maidr-highlight]').length"


@pytest.fixture
def page_path(tmp_path) -> Path:
    import maidr

    charts = maidr.read_tensorboard_distributions(LOGDIR)
    path = tmp_path / "distribution.html"
    # Bundled rather than CDN: the shipped bundle is the thing under test.
    maidr.save_html(charts[0], file=str(path), use_cdn=False)
    for chart in charts:
        maidr.close(chart)
    return path


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(500)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def test_the_steps_and_quantiles_of_a_distribution_are_read(browser, page_path):
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
        assert "Step is 0, Median activations is -0.06" in spoken, spoken
        assert "Middle 68% is -1.06 to 0.94" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        # Up walks TensorBoard's basis points above the median, in order.
        heard = [_step(page, "ArrowUp") for _ in range(4)]
        assert [spoken.split(" activations")[0] for spoken in heard] == [
            "Step is 0, 69.2th percentile",
            "Step is 0, 84.1th percentile",
            "Step is 0, 93.3th percentile",
            "Step is 0, Maximum",
        ], heard
        assert "Full range is -2.69 to 3.06" in heard[-1], heard[-1]
        assert page.evaluate(_OUTLINED) == 1

        spoken = _step(page, "ArrowRight")
        assert "Step is 4, Maximum activations is 3.62" in spoken, spoken
        assert not errors, errors
    finally:
        page.close()
