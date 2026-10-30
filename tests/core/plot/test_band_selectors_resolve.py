"""A filled band's selector names what matplotlib drew for it.

matplotlib writes a collection of one filled path with an edge colour through
its single-path shortcut: the path goes into the group's ``<defs>``, offset by
the height of the figure, and a ``<use>`` draws it. A stackplot or
``fill_between`` band under a seaborn theme or with ``edgecolor=`` is such a
collection, and so are a seaborn KDE fill and a violin body. Selectors of the
form ``g[id=...] path`` named the template, which draws nothing:

- an area layer's markers went into ``<defs>``, at 0,0, and never drew
  (py-gallery-files#1);
- a filled KDE named the template outright (``> defs > path``), with the same
  result;
- a violin named the template and the ``<use>`` both, and only worked because
  maidr.js prefers a ``<use>``.

An area layer needs more than the drawn element: maidr.js reads its points
from the vertices of the ``<path>`` named -- the first one per point, out
along the samples -- and ``fill_between`` starts its polygon at a corner on
its second bound and walks the first bound out. A stackplot band's samples,
its top, are on the second bound, so a band drawn as a plain path was
highlighted along its lower edge, and a ``fill_between(x, y)`` area one sample
behind. ``AreaPlot.finish_svg`` writes each band as one path that starts along
its samples.

These resolve every emitted selector against the exported SVG. The highlight
itself is measured in a browser by ``tests/browser/test_area_highlight.py``.
"""

from __future__ import annotations

import datetime
import io
import re

import numpy as np
import pytest

pytest.importorskip("lxml")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from lxml import etree  # noqa: E402
from lxml.cssselect import CSSSelector  # noqa: E402
from matplotlib.dates import date2num  # noqa: E402

import maidr  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402

#: Four positions and two series. No series' value equals the other's
#: running total, so a highlight on the wrong edge cannot coincide with the
#: right one.
X = [2019, 2020, 2021, 2022]
A = [10.0, 20.0, 25.0, 30.0]
B = [5.0, 8.0, 12.0, 14.0]
RAIN = [78.0, 62.0, 71.0, 55.0, 48.0, 39.0]
DATES = [datetime.date(2024, month, 1) for month in range(1, 7)]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _tops(base: np.ndarray) -> list[list[float]]:
    """Each stackplot band's top: the base plus the running total."""
    return [list(base + np.array(A)), list(base + np.array(A) + np.array(B))]


#: Area charts, keyed by a readable name: what to draw, and the position and
#: value of each band's samples, in data coordinates.
AREAS = {
    "stackplot": (
        lambda ax: ax.stackplot(X, A, B),
        [list(zip(X, top)) for top in _tops(np.zeros(4))],
    ),
    "stackplot edgecolor": (
        lambda ax: ax.stackplot(X, A, B, edgecolor="white"),
        [list(zip(X, top)) for top in _tops(np.zeros(4))],
    ),
    "stackplot categories edgecolor": (
        lambda ax: ax.stackplot(["Q1", "Q2", "Q3", "Q4"], A, B, edgecolor="k"),
        [list(zip(range(4), top)) for top in _tops(np.zeros(4))],
    ),
    "stackplot sym baseline edgecolor": (
        lambda ax: ax.stackplot(X, A, B, baseline="sym", edgecolor="w"),
        [
            list(zip(X, top))
            for top in _tops(-(np.array(A) + np.array(B)) / 2)
        ],
    ),
    "fill_between": (
        lambda ax: ax.fill_between(range(6), RAIN),
        [list(zip(range(6), RAIN))],
    ),
    "fill_between edgecolor": (
        lambda ax: ax.fill_between(range(6), RAIN, edgecolor="k"),
        [list(zip(range(6), RAIN))],
    ),
    "fill_between signed edgecolor": (
        lambda ax: ax.fill_between(range(4), [3, -2, 4, -1], edgecolor="k"),
        [list(zip(range(4), [3, -2, 4, -1]))],
    ),
    "fill_between dates edgecolor": (
        lambda ax: ax.fill_between(DATES, RAIN, edgecolor="k"),
        [list(zip(date2num(DATES), RAIN))],
    ),
}

#: A band drawn as `fill_betweenx` runs down the page: its samples are at
#: (value, position).
SIDEWAYS = {
    "fill_betweenx edgecolor": (
        lambda ax: ax.fill_betweenx(range(6), RAIN, edgecolor="k"),
        [list(zip(RAIN, range(6)))],
    ),
}


def _render(draw):
    """Draw a chart, render it, and return the figure, axes, layers and SVG."""
    figure, ax = plt.subplots()
    draw(ax)
    html = maidr.render(figure)._repr_html_()
    svg = re.search(r"<svg.*?</svg>", html, re.S)
    assert svg is not None
    root = etree.fromstring(svg.group(0).encode(), etree.XMLParser(recover=True))
    for element in root.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]
    plots = FigureManager.get_maidr(figure)._plots
    return figure, ax, plots, root


def _in_defs(element) -> bool:
    return any(ancestor.tag == "defs" for ancestor in element.iterancestors())


def _vertices(element) -> list[tuple[float, float]]:
    """The vertices of an ``M x y L x y ... z`` path, in drawing order."""
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", element.get("d"))]
    return list(zip(numbers[0::2], numbers[1::2]))


def _to_svg(figure, ax, points) -> np.ndarray:
    """Data coordinates to the SVG's points, y running down from the top."""
    at = ax.transData.transform(np.asarray(points, dtype=float)) * 72 / figure.dpi
    at[:, 1] = figure.get_figheight() * 72 - at[:, 1]
    return at


@pytest.mark.parametrize("chart", list(AREAS) + list(SIDEWAYS))
def test_each_band_selector_names_one_drawn_path(chart):
    draw, _ = {**AREAS, **SIDEWAYS}[chart]
    _, _, plots, root = _render(draw)
    (layer,) = [plot.schema for plot in plots]

    for selector in layer["selectors"]:
        found = CSSSelector(selector)(root)
        assert len(found) == 1, f"{selector!r} matched {len(found)} elements"
        assert found[0].tag == "path"
        assert not _in_defs(found[0]), "the selector named a template in <defs>"


@pytest.mark.parametrize("chart", list(AREAS))
def test_a_bands_first_vertices_are_its_samples(chart):
    # maidr.js keeps a band's first vertex per point and drops the way back,
    # so those vertices are where it puts the highlight.
    draw, samples = AREAS[chart]
    figure, ax, plots, root = _render(draw)
    (layer,) = [plot.schema for plot in plots]

    for selector, band in zip(layer["selectors"], samples):
        (path,) = CSSSelector(selector)(root)
        drawn = np.array(_vertices(path)[: len(band)])
        assert np.allclose(drawn, _to_svg(figure, ax, band), atol=0.01), (
            f"{chart}: the band's first vertices are not its samples"
        )


@pytest.mark.parametrize("chart", list(SIDEWAYS))
def test_a_sideways_bands_first_vertices_are_its_samples(chart):
    draw, samples = SIDEWAYS[chart]
    figure, ax, plots, root = _render(draw)
    (layer,) = [plot.schema for plot in plots]

    (path,) = CSSSelector(layer["selectors"][0])(root)
    drawn = np.array(_vertices(path)[: len(samples[0])])
    assert np.allclose(drawn, _to_svg(figure, ax, samples[0]), atol=0.01)


@pytest.mark.parametrize("chart", list(AREAS) + list(SIDEWAYS))
def test_a_band_is_the_polygon_matplotlib_drew(chart):
    # Started elsewhere or run the other way round, a closed polygon fills
    # and strokes the same; it must have the same vertices in the same cycle.
    draw, _ = {**AREAS, **SIDEWAYS}[chart]
    figure, ax, plots, root = _render(draw)
    (plot,) = plots

    for band, selector in zip(plot.elements, plot.schema["selectors"]):
        (path,) = CSSSelector(selector)(root)
        written = np.array(_vertices(path))
        polygon = _to_svg(figure, ax, band.get_paths()[0].vertices[:-1])
        assert written.shape == polygon.shape
        cycles = [
            np.roll(order, -k, axis=0)
            for order in (polygon, polygon[::-1])
            for k in range(len(polygon))
        ]
        assert any(np.allclose(written, cycle, atol=0.01) for cycle in cycles)


@pytest.mark.parametrize("chart", [name for name in AREAS if "edgecolor" in name])
def test_a_band_drawn_through_the_shortcut_keeps_no_template(chart):
    draw, _ = AREAS[chart]
    _, _, plots, root = _render(draw)
    (plot,) = plots

    for band in plot.elements:
        (group,) = root.xpath("//g[@id=$gid]", gid=band.get_gid())
        assert group.xpath(".//use") == []
        assert group.xpath(".//defs") == []


def test_a_band_of_another_shape_is_left_as_drawn():
    # A stepped fill has two vertices a position, so it is not the polygon
    # the rewrite reads; its path is written exactly as matplotlib wrote it.
    figure, ax = plt.subplots()
    band = ax.fill_between(range(6), RAIN, step="pre")
    rendered = maidr.render(figure)._repr_html_()
    plain = io.StringIO()
    figure.savefig(plain, format="svg")

    group = r'<g id="%s"[^>]*>\s*<path d="([^"]+)"' % band.get_gid()
    drawn = re.search(group, plain.getvalue()).group(1)
    assert re.search(group, rendered).group(1).split() == drawn.split()


#: Filled KDEs and violin bodies, keyed by a readable name.
FILLS = {
    "sns.kdeplot fill": lambda ax: _sns().kdeplot(_sample(0), fill=True, ax=ax),
    "sns.kdeplot fill, no edge": lambda ax: _sns().kdeplot(
        _sample(0), fill=True, linewidth=0, ax=ax
    ),
    "sns.kdeplot fill hue": lambda ax: _sns().kdeplot(
        data=_frame(), x="v", hue="g", fill=True, ax=ax
    ),
    "sns.violinplot": lambda ax: _sns().violinplot(
        data=_frame(), x="g", y="v", ax=ax
    ),
    "sns.violinplot horizontal": lambda ax: _sns().violinplot(
        data=_frame(), x="v", y="g", ax=ax
    ),
    "ax.violinplot": lambda ax: ax.violinplot([_sample(0), _sample(1)]),
}


def _sns():
    return pytest.importorskip("seaborn")


def _sample(seed: int) -> np.ndarray:
    return np.random.default_rng(seed).normal(seed, 1, 150)


def _frame():
    import pandas as pd

    return pd.DataFrame(
        {"v": np.r_[_sample(0), _sample(1)], "g": ["a"] * 150 + ["b"] * 150}
    )


@pytest.mark.parametrize("chart", list(FILLS))
def test_each_fill_selector_names_the_drawn_fill(chart):
    _, _, plots, root = _render(FILLS[chart])
    layers = [
        plot.schema
        for plot in plots
        if plot.schema["type"] in ("smooth", "violin_kde")
    ]
    assert layers

    for layer in layers:
        for selector in layer["selectors"]:
            found = CSSSelector(selector)(root)
            assert len(found) == 1, f"{selector!r} matched {len(found)} elements"
            assert found[0].tag in ("path", "use")
            assert not _in_defs(found[0]), "the selector named a template in <defs>"
