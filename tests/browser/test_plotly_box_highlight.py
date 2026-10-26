"""A plotly box plot is walked and outlined the way it is drawn.

A horizontal layer's boxes were emitted bottom first, the order plotly draws
them up the page; maidr.js expects them top first and reverses them, so the
reader started on the top box and Up moved down. These drive the shipped
bundle over a saved page and hold Up to moving the outline up the page.

plotly.js is linked from ``cdn.plot.ly``; the page is handed the copy the
installed ``plotly`` package ships instead, so nothing here needs a network.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

plotly = pytest.importorskip("plotly")

#: The plotly.js the installed package ships.
_PLOTLY_JS = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"

_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000

#: Where the core writes what it announces for the current point.
_TEXT = "#maidr-text-container"

#: The visible outlines the core draws: their screen boxes.
_OUTLINED = """() => [...document.querySelectorAll("svg [data-maidr-owned]")]
  .filter((e) => getComputedStyle(e).visibility !== "hidden"
    && e.getAttribute("visibility") !== "hidden")
  .map((e) => {
    const r = e.getBoundingClientRect();
    return {x: r.x, y: r.y, width: r.width, height: r.height};
  })"""

GROUPS = ["Group 1", "Group 2", "Group 3"]


def _boxes(tmp_path: Path, orientation: str) -> Path:
    """Three boxes, one trace each, saved with the bundled maidr.js."""
    import numpy as np
    import plotly.graph_objects as go

    import maidr

    rng = np.random.default_rng(7)
    samples = "x" if orientation == "h" else "y"
    fig = go.Figure(
        [
            go.Box(**{samples: rng.normal(50 + 20 * i, 5, 40).tolist()}, name=name)
            for i, name in enumerate(GROUPS)
        ]
    )
    path = tmp_path / f"plotly_box_{orientation}.html"
    maidr.save_html(fig, file=str(path), use_cdn=False)
    return path


def _open(browser, chart: Path):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    page.route(
        re.compile(r"^https://cdn\.plot\.ly/"),
        lambda route: route.fulfill(
            path=str(_PLOTLY_JS), content_type="application/javascript"
        ),
    )
    page.goto(chart.as_uri(), wait_until="load")
    page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
    page.wait_for_selector("svg[maidr]", state="attached", timeout=_PARSE_TIMEOUT_MS)
    page.wait_for_timeout(500)
    page.keyboard.press("Tab")
    page.wait_for_timeout(400)
    return page, errors


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(400)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def _outline(page) -> dict:
    """The one visible outline."""
    outlined = page.evaluate(_OUTLINED)
    assert len(outlined) == 1, outlined
    return outlined[0]


def _centre_y(box: dict) -> float:
    return box["y"] + box["height"] / 2


def _group(spoken: str) -> str:
    found = re.search(r"Group (\d)", spoken)
    assert found, spoken
    return f"Group {found.group(1)}"


def test_up_walks_horizontal_boxes_up_the_page(browser, tmp_path):
    page, errors = _open(browser, _boxes(tmp_path, "h"))
    try:
        # Onto a statistic, which has a mark to outline.
        for _ in range(4):
            spoken = _step(page, "ArrowRight")
            if "50%" in spoken:
                break
        assert _group(spoken) == "Group 1", "did not start on the bottom box"
        below = _centre_y(_outline(page))

        spoken = _step(page, "ArrowUp")
        assert _group(spoken) == "Group 2", spoken
        middle = _centre_y(_outline(page))
        assert middle < below, "ArrowUp moved the outline down the page"

        spoken = _step(page, "ArrowUp")
        assert _group(spoken) == "Group 3", spoken
        assert _centre_y(_outline(page)) < middle

        spoken = _step(page, "ArrowDown")
        assert _group(spoken) == "Group 2", spoken
        assert _centre_y(_outline(page)) == pytest.approx(middle, abs=0.5)
        assert not errors, errors
    finally:
        page.close()
