"""A plotnine chart is driven from the keyboard and outlines what it announces.

plotnine draws a panel's bars, bins or tiles into one collection whose rows
are in plotnine's order, not the reader's, so every point names its own
element: ``g[id='<gid>'] > path:nth-of-type(k)``, one per bar, one per cell of
a stacked chart's grid, one per heatmap cell (#814). Those are only right if
the shipped bundle resolves them before it inserts its hidden clones, and
reads a heatmap's grid bottom row first. This drives the bundle and holds each
outline to the element drawn for the value announced.
"""

from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

#: Installed on `window` by the bundle once the inlined JavaScript has parsed.
_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000

#: Where the core writes what it announces for the current point.
_TEXT = "#maidr-text-container"

#: The schema the page embeds, for the gids its selectors name.
_SCHEMA = "() => document.querySelector('svg[maidr]').getAttribute('maidr')"

#: The paths plotnine drew into one collection, with where each sits on the
#: page. The core stands a hidden clone beside each (`data-maidr-owned`);
#: those are not marks.
_DRAWN = """(gid) => [...document.querySelectorAll(
  `g[id='${gid}'] > path:not([data-maidr-owned])`
)].map((p) => {
  const b = p.getBoundingClientRect();
  return {d: p.getAttribute('d'), x: b.x + b.width / 2, y: b.y + b.height / 2};
})"""

#: The outline the core draws for the current point: a copy of the element's
#: own path, so its `d` says which element it copies.
_HIGHLIGHTED = """() => [...document.querySelectorAll("[id^=maidr-highlight]")]
  .map((e) => e.getAttribute("d"))"""


def _save(plot, tmp_path: Path, name: str) -> Path:
    import maidr

    path = tmp_path / f"{name}.html"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # Bundled rather than CDN: the shipped bundle is the thing under test.
        maidr.save_html(plot, str(path), use_cdn=False)
    return path


def _open(browser, chart: Path):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    page.goto(chart.as_uri(), wait_until="load")
    page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
    page.click("svg[maidr]", force=True)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1_500)
    return page, errors


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(500)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def _gids(page) -> list[str]:
    """Every gid the embedded schema's selectors name, in order of first use."""
    return list(dict.fromkeys(re.findall(r"g\[id='([^']+)'\]", page.evaluate(_SCHEMA))))


@pytest.fixture
def frames():
    pytest.importorskip("plotnine")
    import pandas as pd

    return {
        # Rows not in category order: drawn b, a, c, read a, b, c.
        "sales": pd.DataFrame({"c": ["b", "a", "c"], "v": [5.0, 3.0, 2.0]}),
        "split": pd.DataFrame(
            {"cat": ["a", "a", "b", "b"], "g": ["p", "q", "p", "q"],
             "v": [1.0, 2.0, 3.0, 4.0]}
        ),
        "tiles": pd.DataFrame(
            {"a": ["x", "x", "y", "y"], "b": ["u", "v", "u", "v"], "z": [1, 2, 3, 4]}
        ),
        "boxes": pd.DataFrame(
            {"g": ["p"] * 7, "y": [1, 2, 3, 4, 5, 20, -10]}
        ),
        # Two curves as `precision_recall_curve` answers them: high recall
        # first, so the path is drawn right to left.
        "pr": pd.DataFrame(
            {
                "recall": [1.0, 0.5, 0.0] * 2,
                "precision": [0.4, 0.8, 1.0, 0.3, 0.6, 0.9],
                "model": ["a"] * 3 + ["b"] * 3,
            }
        ),
        # 0..10 at each step, shifted: the 10th, 50th and 90th percentiles
        # are 1, 5 and 9 above the shift.
        "spread": pd.DataFrame(
            {
                "step": [s for s in (1, 2) for _ in range(11)],
                "v": [float(v + shift) for shift in (0, 5) for v in range(11)],
            }
        ),
    }


def test_a_column_chart_outlines_the_bar_it_announces(browser, frames, tmp_path):
    from plotnine import aes, geom_col, ggplot

    chart = _save(ggplot(frames["sales"], aes("c", "v")) + geom_col(), tmp_path, "col")
    page, errors = _open(browser, chart)
    try:
        (gid,) = _gids(page)
        bars = sorted(page.evaluate(_DRAWN, gid), key=lambda bar: bar["x"])
        assert len(bars) == 3

        for (category, value), bar in zip([("a", "3"), ("b", "5"), ("c", "2")], bars):
            spoken = _step(page, "ArrowRight")
            assert f"is {category}" in spoken and value in spoken, spoken
            assert page.evaluate(_HIGHLIGHTED) == [bar["d"]], (
                f"{category} is announced but another bar is outlined"
            )
        assert not errors, errors
    finally:
        page.close()


def test_a_stacked_bar_outlines_the_segment_it_announces(browser, frames, tmp_path):
    from plotnine import aes, geom_col, ggplot

    chart = _save(
        ggplot(frames["split"], aes("cat", "v", fill="g")) + geom_col(),
        tmp_path,
        "stack",
    )
    page, errors = _open(browser, chart)
    try:
        (gid,) = _gids(page)
        drawn = page.evaluate(_DRAWN, gid)
        leftmost = min(bar["x"] for bar in drawn)
        # Page y grows downwards: the bottom segment of `a` has the larger y.
        bottom, top = sorted(
            (bar for bar in drawn if bar["x"] == leftmost), key=lambda b: -b["y"]
        )

        spoken = _step(page, "ArrowRight")
        assert "is a" in spoken and "is q" in spoken and "2" in spoken, spoken
        assert page.evaluate(_HIGHLIGHTED) == [bottom["d"]]

        spoken = _step(page, "ArrowUp")
        assert "is a" in spoken and "is p" in spoken and "1" in spoken, spoken
        assert page.evaluate(_HIGHLIGHTED) == [top["d"]]
        assert not errors, errors
    finally:
        page.close()


def test_a_heatmap_outlines_the_cell_it_announces(browser, frames, tmp_path):
    from plotnine import aes, geom_tile, ggplot

    chart = _save(
        ggplot(frames["tiles"], aes("a", "b", fill="z")) + geom_tile(),
        tmp_path,
        "tile",
    )
    page, errors = _open(browser, chart)
    try:
        (gid,) = _gids(page)
        drawn = page.evaluate(_DRAWN, gid)
        left = min(cell["x"] for cell in drawn)
        column = sorted((c for c in drawn if c["x"] == left), key=lambda c: -c["y"])
        bottom_left, top_left = column

        # The core starts on its row 0, which it keys to the bottom row.
        spoken = _step(page, "ArrowRight")
        assert "is x" in spoken and "is u" in spoken and "1" in spoken, spoken
        assert page.evaluate(_HIGHLIGHTED) == [bottom_left["d"]], (
            "the cell is announced but another is outlined: the selector grid "
            "is not keyed in the order the core reads it"
        )

        spoken = _step(page, "ArrowUp")
        assert "is v" in spoken and "2" in spoken, spoken
        assert page.evaluate(_HIGHLIGHTED) == [top_left["d"]]
        assert not errors, errors
    finally:
        page.close()


def test_a_box_outlines_the_whisker_it_announces(browser, frames, tmp_path):
    from plotnine import aes, geom_boxplot, ggplot

    chart = _save(
        ggplot(frames["boxes"], aes("g", "y")) + geom_boxplot(), tmp_path, "box"
    )
    page, errors = _open(browser, chart)
    try:
        # The whiskers are the collection the `min` selector names; which of
        # its two paths is the lower one is read off the page, not assumed.
        schema = json.loads(page.evaluate(_SCHEMA))
        (layer,) = schema["subplots"][0][0]["layers"]
        (gid,) = re.findall(r"g\[id='([^']+)'\]", layer["selectors"][0]["min"])
        lower, upper = sorted(page.evaluate(_DRAWN, gid), key=lambda p: -p["y"])

        spoken = _step(page, "ArrowRight")
        assert "-10" in spoken, spoken
        spoken = _step(page, "ArrowUp")
        assert "Minimum" in spoken and "1" in spoken, spoken
        assert page.evaluate(_HIGHLIGHTED) == [lower["d"]]

        for _ in range(4):
            spoken = _step(page, "ArrowUp")
        assert "Maximum" in spoken and "5" in spoken, spoken
        assert page.evaluate(_HIGHLIGHTED) == [upper["d"]]
        assert not errors, errors
    finally:
        page.close()


#: How many outlines the core is showing.
_OUTLINED = "() => document.querySelectorAll('[id^=maidr-highlight]').length"


def test_a_pr_curve_is_walked_from_low_recall_up(browser, frames, tmp_path):
    from plotnine import aes, geom_path, ggplot

    chart = _save(
        ggplot(frames["pr"], aes("recall", "precision", color="model"))
        + geom_path(),
        tmp_path,
        "pr",
    )
    page, errors = _open(browser, chart)
    try:
        spoken = _step(page, "ArrowRight")
        assert "recall is 0," in spoken and "precision is 1" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        spoken = _step(page, "ArrowRight")
        assert "recall is 0.5" in spoken and "precision is 0.8" in spoken, spoken

        spoken = _step(page, "ArrowDown")
        assert "is b" in spoken and "precision is 0.6" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1
        assert not errors, errors
    finally:
        page.close()


def test_a_median_hilow_band_is_entered_on_its_median(browser, frames, tmp_path):
    import numpy as np
    from plotnine import aes, ggplot, stat_summary

    chart = _save(
        ggplot(frames["spread"], aes("step", "v"))
        + stat_summary(
            fun_data="median_hilow",
            fun_args={"confidence_interval": 0.8},
            geom="ribbon",
            alpha=0.3,
        )
        + stat_summary(fun_y=np.median, geom="line"),
        tmp_path,
        "band",
    )
    page, errors = _open(browser, chart)
    try:
        spoken = _step(page, "ArrowRight")
        assert "step is 1, Median v is 5" in spoken, spoken
        assert "Middle 80% is 1 to 9" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        spoken = _step(page, "ArrowUp")
        assert "90th percentile v is 9" in spoken, spoken
        assert page.evaluate(_OUTLINED) == 1

        _step(page, "ArrowDown")
        spoken = _step(page, "ArrowDown")
        assert "10th percentile v is 1" in spoken, spoken

        spoken = _step(page, "ArrowRight")
        assert "step is 2" in spoken and "is 10" in spoken, spoken
        assert not errors, errors
    finally:
        page.close()
