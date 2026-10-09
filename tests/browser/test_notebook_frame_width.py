"""The notebook frame is as wide as the chart in it (#893).

In a notebook, py-maidr shows a matplotlib or seaborn chart in a frame it
sizes to its content. It read the width from the frame body's
``scrollWidth``. That value is measured from the body's own edge, so it
leaves out the 8px margin a browser gives ``<body>``, and the frame came out
8px narrower than its document. The frame does not scroll, so the right 8px
of the chart were cut off, and with them the right side of the focus outline
a keyboard user sees on it.

This opens a page shaped like a notebook in a window wider than the chart.
The page has the bundle stashed on the parent, then the frame. The test
checks the frame from both sides:

* it leaves the body's margin to the right of the chart, so nothing is cut;
* it is no wider than that, so it still shrinks to the chart rather than
  keeping the width of the page.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

import matplotlib.pyplot as plt
import pytest

import maidr
from maidr.util.environment import Environment

if TYPE_CHECKING:
    from playwright.sync_api import Browser

pytestmark = pytest.mark.browser

#: The article ``maidr.js`` wraps a chart in once it has taken the chart over.
_CHART_READY = "() => document.querySelector('article[id^=maidr-article-]') !== null"
_PARSE_TIMEOUT_MS = 30_000

#: How long the frame is given to settle at its final size once the chart is
#: in it: the resize runs again on the frame's load and resize events.
_SETTLE_MS = 1_500

#: Read in the chart's frame: the frame's width, where the chart ends, and
#: the body's right margin.
_FIT = """() => {
  const plot = document.querySelector('figure[id^="maidr-figure-"] > [tabindex]');
  return {
    width: document.documentElement.clientWidth,
    right: plot.getBoundingClientRect().right,
    margin: parseFloat(getComputedStyle(document.body).marginRight),
  };
}"""


def _notebook(tmp_path: Path) -> str:
    """
    A page shaped like a notebook: the parent stash, then a srcdoc frame.

    Parameters
    ----------
    tmp_path : pathlib.Path
        Where to write the page.

    Returns
    -------
    str
        The page's ``file://`` URL.
    """
    source = json.dumps(maidr.read_bundled_js()).replace("</", "<\\/")
    try:
        with mock.patch.object(Environment, "is_notebook", return_value=True):
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.bar(["a", "b", "c"], [1, 3, 2])
            frame = str(maidr.render(fig, use_cdn=False))
    finally:
        plt.close("all")
    out = tmp_path / "notebook.html"
    out.write_text(
        f"<!doctype html><html><body><script>window.__maidrJsSource = {source};"
        f"</script>{frame}</body></html>",
        encoding="utf-8",
    )
    return out.as_uri()


def test_frame_holds_the_whole_chart(browser: Browser, tmp_path: Path) -> None:
    """The frame ends one body margin past the chart, no nearer and no further."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    try:
        page.goto(_notebook(tmp_path), wait_until="load")
        chart = page.frames[-1]
        chart.wait_for_function(_CHART_READY, timeout=_PARSE_TIMEOUT_MS)
        page.wait_for_timeout(_SETTLE_MS)
        fit = chart.evaluate(_FIT)
    finally:
        page.close()

    needed = fit["right"] + fit["margin"]
    assert fit["width"] >= needed - 0.5, (
        f"the frame is {fit['width']}px wide but the chart and the body's "
        f"margin after it need {needed}px: the chart's right edge, and its "
        "focus outline, are cut off (#893)"
    )
    assert fit["width"] <= needed + 1, (
        f"the frame is {fit['width']}px wide where {needed}px holds the "
        "chart: it no longer shrinks to its content"
    )
