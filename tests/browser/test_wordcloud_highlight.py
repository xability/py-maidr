"""Arrow keys move an outline from word to word of a word cloud.

``imshow`` draws a cloud as one picture, so the layer gives each term a box
of its own over the word, hidden in the SVG until maidr.js outlines it
(``maidr/core/plot/wordcloudplot.py``). This drives the shipped bundle to
check what the markup tests cannot: that the outline appears at all, that
it is the term being announced, and that nothing shows before it does.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000
_TEXT = "#maidr-text-container"

#: maidr's copies of the boxes that can be seen, as the `d` of each.
_SHOWN = """() => [...document.querySelectorAll("svg [data-maidr-owned]")]
  .filter((e) => getComputedStyle(e).visibility !== "hidden")
  .map((e) => e.getAttribute("d"))"""

#: The boxes the page itself draws that can be seen: none, until highlighted.
_BOXES_SHOWN = """(gids) => gids.filter((gid) => {
  const path = document.getElementById(gid).querySelector("path");
  return getComputedStyle(path).visibility !== "hidden";
})"""

COUNTS = {"data": 250, "machine": 412, "model": 120, "learning": 300}
BY_WEIGHT = ["machine", "learning", "data", "model"]


@pytest.fixture
def cloud_page(tmp_path) -> tuple[Path, list[str]]:
    """The page and each term's box gid, heaviest term first."""
    pytest.importorskip("wordcloud")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from wordcloud import WordCloud

    import maidr
    from maidr.core.figure_manager import FigureManager

    cloud = WordCloud(
        width=600, height=300, background_color="white", random_state=1
    ).generate_from_frequencies(COUNTS)
    fig, ax = plt.subplots()
    ax.imshow(cloud)
    path = tmp_path / "cloud.html"
    try:
        (layer,) = FigureManager.get_maidr(fig).plots
        selectors = layer.schema["selectors"]
        gids = [selector.split("'")[1] for selector in selectors]
        maidr.save_html(fig, file=str(path), use_cdn=False)
    finally:
        plt.close("all")
    return path, gids


def _drawn(page, gid: str) -> str:
    return page.evaluate(
        "(gid) => document.getElementById(gid).querySelector('path')"
        ".getAttribute('d')",
        gid,
    )


def test_the_outline_follows_the_term_read(browser, cloud_page):
    path, gids = cloud_page
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    try:
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
        assert page.evaluate(_BOXES_SHOWN, gids) == []

        page.click("svg[maidr]", force=True)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1_500)

        for term, gid in zip(BY_WEIGHT, gids):
            page.keyboard.press("ArrowRight")
            page.wait_for_timeout(500)
            spoken = page.evaluate(f"document.querySelector('{_TEXT}')?.innerText")
            assert term in (spoken or ""), spoken
            assert page.evaluate(_SHOWN) == [
                _drawn(page, gid)
            ], f"the outline for {term} is not on its own box"

        # The page's own boxes stay hidden throughout; only maidr's copy shows.
        assert page.evaluate(_BOXES_SHOWN, gids) == []
        assert not errors, errors
    finally:
        page.close()
