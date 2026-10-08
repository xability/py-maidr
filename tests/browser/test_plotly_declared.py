"""A declared plotly fan chart and PR curve, driven from the keyboard.

Every selector the declared layers emit has to find exactly one element of
the chart plotly drew -- a band's ``tonexty`` fill in the group of the trace
it fills to, the median's and each curve's line -- and the reader hears the
quantiles and thresholds the declaration names.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

plotly = pytest.importorskip("plotly")

_PLOTLY_JS = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
_TEXT = "#maidr-text-container"

#: Each selector of the first layer, with how many elements it matches.
_MATCHES = """() => {
  const payload = JSON.parse(document.querySelector("svg[maidr]").getAttribute("maidr"));
  const layer = payload.subplots[0][0].layers[0];
  return [layer.type, layer.selectors.map((s) => document.querySelectorAll(s).length)];
}"""


def _fan():
    import plotly.graph_objects as go

    x = [0, 1, 2, 3, 4]
    median = [1, 2, 3, 4, 5]

    def edge(offset, name, fill=None):
        y = [m + offset for m in median]
        return go.Scatter(x=x, y=y, name=name, mode="lines", line_width=0, fill=fill)

    return go.Figure(
        [
            edge(-2, "p5"),
            edge(2, "p5-95", "tonexty"),
            edge(-1, "p25"),
            edge(1, "p25-75", "tonexty"),
            go.Scatter(
                x=x,
                y=median,
                name="median",
                mode="lines",
                meta={
                    "maidr": {
                        "type": "percentile_band",
                        "bands": [
                            {"series": "p5-95", "lower": 0.05, "upper": 0.95},
                            {"series": "p25-75", "lower": 0.25, "upper": 0.75},
                        ],
                    }
                },
            ),
        ]
    )


def _pr_curves():
    import plotly.graph_objects as go

    recall = [0, 0.2, 0.5, 0.8, 1]
    precision = [1, 0.9, 0.8, 0.6, 0.4]
    return go.Figure(
        [
            go.Scatter(
                x=recall,
                y=precision,
                name="A",
                mode="lines",
                customdata=[{"threshold": t} for t in (0.9, 0.7, 0.5, 0.3, 0.1)],
                meta={"maidr": {"type": "pr_curve", "prevalence": 0.3}},
            ),
            go.Scatter(
                x=recall, y=[p * 0.9 for p in precision], name="B", mode="lines"
            ),
        ]
    )


def _open(browser, fig, path: Path):
    import maidr

    maidr.save_html(fig, file=str(path), use_cdn=False)
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    page.route(
        re.compile(r"^https://cdn\.plot\.ly/"),
        lambda route: route.fulfill(
            path=str(_PLOTLY_JS), content_type="application/javascript"
        ),
    )
    page.goto(path.as_uri(), wait_until="load")
    page.wait_for_function("() => window.maidrLive !== undefined", timeout=30_000)
    page.wait_for_selector("svg[maidr]", state="attached", timeout=30_000)
    page.wait_for_timeout(500)
    page.keyboard.press("Tab")
    page.wait_for_timeout(400)
    return page, errors


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(400)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def test_a_declared_fan_reads_its_bands(browser, tmp_path):
    page, errors = _open(browser, _fan(), tmp_path / "fan.html")
    try:
        assert page.evaluate(_MATCHES) == ["percentile_band", [1, 1, 1]]
        assert "Median Y is 1" in _step(page, "ArrowRight")
        assert "75th percentile Y is 2" in _step(page, "ArrowUp")
        assert "95th percentile Y is 3" in _step(page, "ArrowUp")
        assert not errors, errors
    finally:
        page.close()


def test_a_declared_pr_curve_reads_its_thresholds(browser, tmp_path):
    page, errors = _open(browser, _pr_curves(), tmp_path / "pr.html")
    try:
        assert page.evaluate(_MATCHES) == ["pr_curve", [1, 1]]
        spoken = _step(page, "ArrowRight")
        assert "Threshold is 0.9" in spoken, spoken
        assert "Above baseline is 0.7" in spoken, spoken
        assert not errors, errors
    finally:
        page.close()
