"""An area band is outlined at the point being announced.

maidr.js reads an area series from the vertices of the ``<path>`` its
selector names, the first one per point, and puts a marker on the vertex of
the point the reader is on. Two things kept that marker off the point:

- A band with an edge colour -- a seaborn theme's white edge, an Excel
  chart's, any ``edgecolor=`` -- is written by matplotlib as a template in
  ``<defs>`` and a ``<use>`` of it. The selector named the template, the
  markers went into ``<defs>``, and nothing was outlined at all
  (py-gallery-files#1).
- ``fill_between`` starts its polygon at a corner on its second bound and
  walks the first bound out. A stackplot band's samples, its top, are on the
  second bound, so the marker walked the band's lower edge; a
  ``fill_between(x, y)`` area's are on the first, one vertex in, so the
  marker sat one sample behind the one announced.

``AreaPlot.finish_svg`` now writes each band as one path that starts along
its samples. This drives the shipped bundle: a reader steps along a band and
up to the next, and the marker is held to where the announced sample is
drawn.
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

#: The marker the core shows for the current point: a visible copy of one of
#: the hidden circles it stood along the band, marked `data-maidr-owned`.
_MARKED = """() => [...document.querySelectorAll("svg circle[data-maidr-owned]")]
  .filter((e) => getComputedStyle(e).visibility !== "hidden")
  .map((e) => [Number(e.getAttribute("cx")), Number(e.getAttribute("cy"))])"""


def _save(tmp_path, draw, samples) -> tuple[Path, list]:
    """Draw a chart and save it; return the page and each band's samples.

    The samples come back in the SVG's points, y running down from the top,
    which is where the core places a marker.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    import maidr

    fig, ax = plt.subplots()
    draw(ax)
    path = tmp_path / "area.html"
    try:
        # Bundled rather than CDN: the shipped bundle is the thing under test.
        maidr.save_html(fig, file=str(path), use_cdn=False)
        drawn = []
        for band in samples:
            at = ax.transData.transform(np.asarray(band, dtype=float)) * 72 / fig.dpi
            at[:, 1] = fig.get_figheight() * 72 - at[:, 1]
            drawn.append([tuple(point) for point in at.tolist()])
    finally:
        plt.close("all")
    return path, drawn


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(500)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def _enter(page, chart: Path) -> None:
    page.goto(chart.as_uri(), wait_until="load")
    page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
    page.click("svg[maidr]", force=True)
    page.keyboard.press("Enter")
    page.wait_for_timeout(1_500)


def _marked_at(page, point: tuple[float, float]) -> None:
    marked = page.evaluate(_MARKED)
    assert len(marked) == 1, f"{len(marked)} markers shown for one point"
    assert marked[0] == pytest.approx(point, abs=0.5), (
        f"the marker is at {marked[0]}, the announced point at {point}"
    )


def test_an_edged_stack_marks_each_band_at_its_top(browser, tmp_path):
    # The lower band carries the smaller values, so Up reaches the band drawn
    # above it however the core picks the next band: by drawing order, or by
    # the series' own values, which is what it compares today.
    years = [2019, 2020, 2021, 2022]
    subs, services = [5, 8, 12, 14], [10, 20, 25, 30]
    chart, (bottom, top) = _save(
        tmp_path,
        lambda ax: ax.stackplot(
            years, subs, services, labels=["Subs", "Services"], edgecolor="white"
        ),
        [
            list(zip(years, subs)),
            list(zip(years, [a + b for a, b in zip(subs, services)])),
        ],
    )

    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    try:
        _enter(page, chart)

        spoken = _step(page, "ArrowRight")
        assert "2019" in spoken and "5" in spoken, spoken
        _marked_at(page, bottom[0])

        spoken = _step(page, "ArrowRight")
        assert "2020" in spoken and "8" in spoken, spoken
        _marked_at(page, bottom[1])

        # Up to the band above, at the same year: its top is the total.
        spoken = _step(page, "ArrowUp")
        assert "Services" in spoken and "2020" in spoken, spoken
        _marked_at(page, top[1])

        spoken = _step(page, "ArrowRight")
        assert "2021" in spoken and "25" in spoken, spoken
        _marked_at(page, top[2])
        assert not errors, errors
    finally:
        page.close()


def test_a_filled_curve_marks_the_value_announced(browser, tmp_path):
    rain = [78, 62, 71, 55, 48, 39]
    chart, (curve,) = _save(
        tmp_path,
        lambda ax: ax.fill_between(range(1, 7), rain),
        [list(zip(range(1, 7), rain))],
    )

    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))
    try:
        _enter(page, chart)
        for month, value in zip(range(1, 4), rain):
            spoken = _step(page, "ArrowRight")
            assert f"{month}" in spoken and f"{value}" in spoken, spoken
            _marked_at(page, curve[month - 1])
        assert not errors, errors
    finally:
        page.close()
