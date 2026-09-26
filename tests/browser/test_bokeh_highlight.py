"""A Bokeh chart is read from the keyboard, and highlights what it reads.

Bokeh draws to a ``<canvas>``, so MAIDR's CSS-selector highlight cannot
reach it. The page answers MAIDR's ``onNavigate`` instead, by selecting the
announced row of the renderer's data source, or by moving a cursor glyph
onto a line. These drive the shipped bundle over saved pages and read both
halves back: what MAIDR announces, and what the Bokeh document now shows.

BokehJS is linked from ``cdn.bokeh.org``; the page is handed the copy the
installed ``bokeh`` package ships instead -- the same build, since the page
links the installed version -- so nothing here needs a network.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

bokeh = pytest.importorskip("bokeh")

#: The BokehJS bundles the installed package ships, by name.
_BOKEH_JS = Path(bokeh.__file__).parent / "server" / "static" / "js"
_BOKEH_CDN = re.compile(
    r"^https://cdn\.bokeh\.org/bokeh/release/(bokeh[a-z-]*)-[^/]+\.min\.js$"
)

_BUNDLE_READY = "() => window.maidrLive !== undefined"
_PARSE_TIMEOUT_MS = 30_000

#: Where the core writes what it announces for the current point.
_TEXT = "#maidr-text-container"

#: How many MAIDR instances the page mounted.
_INSTANCES = """() => document
  .querySelectorAll('article[id^="maidr-article"]').length"""

#: A renderer's selected source rows, by model id.
_SELECTED = """(id) => {
  for (const doc of Bokeh.documents) {
    const model = doc.get_model_by_id(id);
    if (model) return [...model.data_source.selected.indices];
  }
  return null;
}"""

#: Where the highlight cursor sits, or null when it is not drawn.
_CURSOR = """() => {
  for (const doc of Bokeh.documents) {
    for (const model of doc.all_models) {
      if (model.name === 'maidr-highlight-cursor') {
        const data = model.data_source.data;
        return data.x.length ? [data.x[0], data.y[0]] : null;
      }
    }
  }
  return undefined;
}"""


def _save(model, path: Path) -> Path:
    import maidr

    # Bundled rather than CDN: the shipped bundle is the thing under test.
    maidr.save_html(model, str(path), use_cdn=False)
    return path


def _open(browser, page_path: Path):
    page = browser.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e).splitlines()[0]))

    def local_bokeh(route):
        name = _BOKEH_CDN.match(route.request.url).group(1)
        route.fulfill(
            path=str(_BOKEH_JS / f"{name}.min.js"),
            content_type="application/javascript",
        )

    page.route(_BOKEH_CDN, local_bokeh)
    page.goto(page_path.as_uri(), wait_until="load")
    page.wait_for_function(_BUNDLE_READY, timeout=_PARSE_TIMEOUT_MS)
    page.wait_for_selector('article[id^="maidr-article"]', timeout=_PARSE_TIMEOUT_MS)
    # The callback is handed over a couple of frames after the chart mounts.
    page.wait_for_timeout(500)
    page.keyboard.press("Tab")
    page.wait_for_timeout(400)
    return page, errors


def _step(page, key: str) -> str:
    page.keyboard.press(key)
    page.wait_for_timeout(300)
    return page.evaluate(f"document.querySelector('{_TEXT}')?.innerText") or ""


def test_a_bar_selects_the_bar_it_announces(browser, tmp_path):
    from bokeh.plotting import figure

    p = figure(x_range=["a", "b", "c"], x_axis_label="Store", y_axis_label="Units")
    # Source rows out of the drawn order, so a highlight keyed on the wrong
    # one would land on a neighbour.
    renderer = p.vbar(x=["c", "a", "b"], top=[3, 1, 2], width=0.9)
    page, errors = _open(browser, _save(p, tmp_path / "bar.html"))
    try:
        assert page.evaluate(_INSTANCES) == 1

        assert _step(page, "ArrowRight") == "Store is a, Units is 1"
        assert page.evaluate(_SELECTED, renderer.id) == [1]

        assert _step(page, "ArrowRight") == "Store is b, Units is 2"
        assert page.evaluate(_SELECTED, renderer.id) == [2]

        assert _step(page, "ArrowRight") == "Store is c, Units is 3"
        assert page.evaluate(_SELECTED, renderer.id) == [0]
        assert not errors, errors
    finally:
        page.close()


def test_a_line_cursor_follows_the_series_being_read(browser, tmp_path):
    from bokeh.plotting import figure

    p = figure()
    p.line([1, 2, 3], [1, 2, 3], legend_label="up")
    p.line([1, 2, 3], [8, 7, 6], legend_label="down")
    renderers_before = list(p.renderers)
    page, errors = _open(browser, _save(p, tmp_path / "line.html"))
    try:
        # The cursor was only lent to the document for serializing.
        assert list(p.renderers) == renderers_before

        assert _step(page, "ArrowRight") == "X is 1, Y is 1, Group is up"
        assert page.evaluate(_CURSOR) == [1, 1]

        assert _step(page, "ArrowRight") == "X is 2, Y is 2, Group is up"
        assert page.evaluate(_CURSOR) == [2, 2]

        assert _step(page, "ArrowUp") == "X is 2, Y is 7, Group is down"
        assert page.evaluate(_CURSOR) == [2, 7]
        assert not errors, errors
    finally:
        page.close()


def test_a_scatter_selects_the_points_it_announces(browser, tmp_path):
    from bokeh.plotting import figure

    p = figure()
    renderer = p.scatter([3, 1, 2], [6, 4, 5])
    page, errors = _open(browser, _save(p, tmp_path / "scatter.html"))
    try:
        assert _step(page, "ArrowRight") == "X is 1, Y is 4"
        assert page.evaluate(_SELECTED, renderer.id) == [1]

        assert _step(page, "ArrowRight") == "X is 2, Y is 5"
        assert page.evaluate(_SELECTED, renderer.id) == [2]
        assert not errors, errors
    finally:
        page.close()


def test_a_heatmap_selects_the_cell_it_announces(browser, tmp_path):
    import pandas as pd
    from bokeh.plotting import figure
    from bokeh.transform import linear_cmap

    frame = pd.DataFrame(
        {"x": ["a", "b", "a", "b"], "y": ["u", "u", "v", "v"], "rate": [1, 2, 3, 4]}
    )
    p = figure(x_range=["a", "b"], y_range=["u", "v"])
    renderer = p.rect(
        x="x", y="y", width=1, height=1, source=frame,
        fill_color=linear_cmap("rate", "Viridis256", 1, 4),
    )
    page, errors = _open(browser, _save(p, tmp_path / "heat.html"))
    try:
        assert _step(page, "ArrowRight") == "X is a, Y is u, rate is 1"
        assert page.evaluate(_SELECTED, renderer.id) == [0]

        # Up is towards ``v``, the upper factor: source row 2.
        assert _step(page, "ArrowUp") == "X is a, Y is v, rate is 3"
        assert page.evaluate(_SELECTED, renderer.id) == [2]
        assert not errors, errors
    finally:
        page.close()


def test_a_stacked_bar_selects_the_segment_it_announces(browser, tmp_path):
    from bokeh.plotting import figure

    p = figure(x_range=["Apples", "Pears"])
    low, high = p.vbar_stack(
        ["2015", "2016"], x="fruit", width=0.9,
        source={"fruit": ["Apples", "Pears"], "2015": [2, 1], "2016": [5, 3]},
        legend_label=["2015", "2016"],
    )
    page, errors = _open(browser, _save(p, tmp_path / "stacked.html"))
    try:
        assert _step(page, "ArrowRight") == "X is Apples, Y is 2, Level is 2015"
        assert page.evaluate(_SELECTED, low.id) == [0]
        assert page.evaluate(_SELECTED, high.id) == []

        assert _step(page, "ArrowUp") == "X is Apples, Y is 5, Level is 2016"
        assert page.evaluate(_SELECTED, low.id) == []
        assert page.evaluate(_SELECTED, high.id) == [0]
        assert not errors, errors
    finally:
        page.close()


def test_leaving_a_subplot_clears_the_highlight(browser, tmp_path):
    from bokeh.layouts import gridplot
    from bokeh.plotting import figure

    left = figure(x_range=["a", "b"], title="left")
    bars = left.vbar(x=["a", "b"], top=[1, 2], width=0.8)
    right = figure(title="right")
    right.line([1, 2, 3], [3, 1, 2])
    grid = _save(gridplot([[left, right]]), tmp_path / "grid.html")
    page, errors = _open(browser, grid)
    try:
        assert page.evaluate(_INSTANCES) == 1
        assert _step(page, "Enter").startswith("Entered subplot 1 of 2, left")
        assert _step(page, "ArrowRight") == "X is a, Y is 1"
        assert page.evaluate(_SELECTED, bars.id) == [0]

        # Back to the figure overview: MAIDR reports ``null``, and the
        # highlight must not follow the reader to the other panel.
        _step(page, "Escape")
        assert page.evaluate(_SELECTED, bars.id) == []

        _step(page, "ArrowRight")
        assert _step(page, "ArrowRight").startswith("Subplot 2 of 2, right")
        assert _step(page, "Enter").startswith("Entered subplot 2 of 2, right")
        assert _step(page, "ArrowRight") == "X is 1, Y is 3"
        assert page.evaluate(_CURSOR) == [1, 3]
        assert not errors, errors
    finally:
        page.close()
