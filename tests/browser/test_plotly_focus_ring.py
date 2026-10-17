"""A Plotly chart's focus ring is seen whole in its frame.

maidr.js draws a Plotly chart's ring around plotly's own container
(``.svg-container:focus-within``), 2px outside it, and takes the ring off the
focused element inside. In a frame that fits its output -- a notebook's, a
Quarto page's, a Shiny app's, all of which ``maidr/assets/frame.css`` styles
-- the container starts at the frame's edge, which cut the ring off: a
quarter of it showed in a Shiny app, its bottom edge, and none of it in an
output with a height of its own. The frame's stylesheet draws it inside.

Read off the screen rather than the stylesheet: a ring inside the container
whose outline the stylesheet asks for was painted under plotly's layers.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest import mock

import pytest

pytestmark = pytest.mark.browser

#: The ring's colour, frame.css's.
_RING = (0x1A, 0x5F, 0xB4)

CHART = "[role=img], [role=application]"

#: plotly's container, in page pixels.
_CONTAINER = r"""() => {
  const frame = document.querySelector('iframe');
  const f = frame.getBoundingClientRect();
  const r = frame.contentDocument.querySelector('.js-plotly-plot .svg-container')
    .getBoundingClientRect();
  return {left: f.left + r.left, top: f.top + r.top,
          right: f.left + r.right, bottom: f.top + r.bottom};
}"""


def _ring_shown(page) -> dict[str, float]:
    """How much of each edge of plotly's container the ring is painted along."""
    from PIL import Image

    box = page.evaluate(_CONTAINER)
    shot = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
    width, height = shot.size

    def share(points) -> float:
        hits = 0
        for x, y in points:
            if 0 <= x < width and 0 <= y < height:
                pixel = shot.getpixel((int(x), int(y)))
                hits += all(abs(a - b) < 40 for a, b in zip(pixel, _RING))
        return hits / len(points)

    n = 24
    xs = [box["left"] + (box["right"] - box["left"]) * (i + 0.5) / n for i in range(n)]
    ys = [box["top"] + (box["bottom"] - box["top"]) * (i + 0.5) / n for i in range(n)]
    return {
        "left": share([(box["left"] + 1, y) for y in ys]),
        "top": share([(x, box["top"] + 1) for x in xs]),
        "right": share([(box["right"] - 2, y) for y in ys]),
        "bottom": share([(x, box["bottom"] - 2) for x in xs]),
    }


def _focus_and_read(page, frame) -> None:
    frame.locator(CHART).first.focus()
    page.wait_for_timeout(400)
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(1000)


@pytest.mark.parametrize("case", ["plotly", "plotly_h400"])
def test_the_ring_is_seen_whole_in_a_shiny_app(browser, shiny_size_app_url, case):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    try:
        page.goto(f"{shiny_size_app_url}/{case}/")
        page.wait_for_selector("#m iframe", timeout=30_000)
        frame = page.query_selector("#m iframe").content_frame()
        frame.locator(CHART).first.wait_for(state="attached", timeout=30_000)
        page.wait_for_timeout(2000)
        _focus_and_read(page, frame)
        shown = _ring_shown(page)
        assert min(shown.values()) >= 0.9, shown
        # Only while the chart has the focus.
        page.evaluate("() => document.activeElement.blur()")
        page.mouse.click(5, 895)
        page.wait_for_timeout(400)
        assert max(_ring_shown(page).values()) < 0.2
    finally:
        page.close()


def _notebook(tmp_path: Path) -> str:
    """A page shaped like a notebook holding a Plotly chart's frame."""
    go = pytest.importorskip("plotly.graph_objects")
    import maidr
    from maidr.util.environment import Environment

    source = json.dumps(maidr.read_bundled_js()).replace("</", "<\\/")
    fig = go.Figure(go.Bar(x=["Apples", "Bananas", "Cherries"], y=[3, 5, 2]))
    with mock.patch.object(Environment, "is_notebook", return_value=True):
        frame = str(maidr.render(fig, use_cdn=False))
    out = tmp_path / "notebook.html"
    out.write_text(
        f"<!doctype html><html><body><script>window.__maidrJsSource = {source};"
        f"</script>{frame}</body></html>",
        encoding="utf-8",
    )
    return out.as_uri()


def test_the_ring_is_seen_whole_in_a_notebook(browser, tmp_path: Path):
    """A notebook's frame, and a Quarto page's, share the stylesheet."""
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    try:
        page.goto(_notebook(tmp_path), wait_until="load")
        frame = page.frames[-1]
        frame.locator(CHART).first.wait_for(state="attached", timeout=30_000)
        page.wait_for_timeout(2500)
        _focus_and_read(page, frame)
        shown = _ring_shown(page)
        assert min(shown.values()) >= 0.9, shown
    finally:
        page.close()
