"""A seaborn median with a percentile interval is walked as a percentile band.

``sns.lineplot(estimator="median", errorbar=("pi", 80))`` is read as a
``percentile_band``: each x is entered on the median, Up moves to the 90th
percentile and Down to the 10th, each announced with the band it bounds and
with the band outlined in the chart.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000
_TEXT = "#maidr-text-container"
_OUTLINED = "() => document.querySelectorAll('[id^=maidr-highlight]').length"


@pytest.fixture
def page_path(tmp_path) -> Path:
    sns = pytest.importorskip("seaborn")
    import numpy as np
    import pandas as pd

    import maidr

    rng = np.random.default_rng(0)
    frame = pd.DataFrame({"week": np.repeat(np.arange(1, 7), 200)})
    frame["sales"] = rng.normal(frame["week"], frame["week"] / 2)
    ax = sns.lineplot(
        data=frame, x="week", y="sales", estimator="median", errorbar=("pi", 80)
    )
    path = tmp_path / "band.html"
    # Bundled rather than CDN: the shipped bundle is the thing under test.
    maidr.save_html(ax.figure, file=str(path), use_cdn=False)
    maidr.close(ax.figure)
    return path


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(500)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def test_the_median_and_its_bounds_are_read_and_outlined(browser, page_path):
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
        assert "week is 1, Median sales is 1.02" in spoken, spoken
        assert "Middle 80% is 0.36 to 1.66" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        spoken = _step(page, "ArrowUp")
        assert "90th percentile sales is 1.66" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        _step(page, "ArrowDown")
        spoken = _step(page, "ArrowDown")
        assert "10th percentile sales is 0.36" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        spoken = _step(page, "ArrowRight")
        assert "week is 2" in spoken, spoken
        assert not errors, errors
    finally:
        page.close()
