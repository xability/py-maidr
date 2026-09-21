"""Right walks a matplotlib pie clockwise, and the outline follows.

``Axes.pie`` draws counterclockwise unless ``counterclock=False``, while the
core steps Right through a pie in data order and lays its audio pan and its
clock-position announcement out on the assumption that the order runs
clockwise. ``maidr/core/plot/pieplot.py`` therefore emits a counterclockwise
pie in reverse, and ``Maidr._get_svg`` puts the wedge groups into that order
so the positional selector still lands on the slice being read.

This is what would catch either half regressing: a reader enters the docs
page's pie, steps Right, and hears the slice drawn *last* -- the first one
clockwise from 12 o'clock -- with the outline on that wedge and not on the
one drawn first; ``p`` places the last stop where it is drawn.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

#: Installed on `window` by the bundle once the inlined JavaScript has parsed.
_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000

#: Where the core writes what it announces for the current point.
_TEXT = "#maidr-text-container"

#: The outline the core draws for the current point: a clone of the wedge's
#: own path, so its `d` says which wedge it copies.
_HIGHLIGHTED = """() => [...document.querySelectorAll("[id^=maidr-highlight]")]
  .map((e) => e.getAttribute("d"))"""

#: The docs page's pie: tips per day, largest first, from 12 o'clock.
DAYS = ["Sat", "Sun", "Thur", "Fri"]
TIPS = [87, 76, 62, 19]


@pytest.fixture
def docs_pie(tmp_path) -> tuple[Path, list[str]]:
    """The page and, in draw order, the gid of each wedge's ``<g>``."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    import maidr

    fig, ax = plt.subplots(figsize=(8, 8))
    wedges, _ = ax.pie(TIPS, labels=DAYS, startangle=90)
    ax.set_xlabel("Day")
    ax.set_ylabel("Number of tips")
    path = tmp_path / "docs_pie.html"
    try:
        # Bundled rather than CDN: the shipped bundle is the thing under test.
        maidr.save_html(fig, file=str(path), use_cdn=False)
        # Minted while the SVG was written, and what its `<g id>` carries.
        gids = [str(wedge.get_gid()) for wedge in wedges]
    finally:
        plt.close("all")
    return path, gids


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(500)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def _drawn(page, gid: str) -> str:
    """The `d` of the wedge matplotlib drew under this gid."""
    return page.evaluate(
        "(gid) => document.getElementById(gid).querySelector('path').getAttribute('d')",
        gid,
    )


def test_right_walks_the_pie_clockwise(browser, docs_pie):
    path, gids = docs_pie
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    try:
        page.goto(path.as_uri(), wait_until="load")
        page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
        page.click("svg[maidr]", force=True)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1_500)

        # Four wedges with four distinct outlines, so a `d` names a wedge.
        drawn = [_drawn(page, gid) for gid in gids]
        assert len(set(drawn)) == 4

        # Clockwise from 12 o'clock is the reverse of the draw order: Fri,
        # the last drawn, is the first stop, and its own wedge is outlined
        # -- not Sat's, the one drawn first.
        for day, tips, d in zip(reversed(DAYS), reversed(TIPS), reversed(drawn)):
            spoken = _step(page, "ArrowRight")
            assert day in spoken and str(tips) in spoken, spoken
            assert page.evaluate(_HIGHLIGHTED) == [d], (
                f"the outline for {day} is on another wedge: the document "
                "order and the data order have come apart."
            )

        # Sat is drawn from 12 o'clock down to about 8, and that is where
        # the last stop is placed.
        spoken = _step(page, "p")
        assert "4 of 4" in spoken and "8 o'clock to 12 o'clock" in spoken, spoken

        # And back the other way.
        spoken = _step(page, "ArrowLeft")
        assert "Sun" in spoken, spoken
        assert page.evaluate(_HIGHLIGHTED) == [drawn[1]]
        assert not errors, errors
    finally:
        page.close()
