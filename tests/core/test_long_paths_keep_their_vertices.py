"""A long contour level or precision-recall curve keeps a vertex per point.

maidr.js puts the highlight of a line-like series' i-th point on the i-th
vertex of the path its selector names. matplotlib drops the vertices it can
merge from an open path of 128 or more as it draws it, which left the path
fewer vertices than the series has points, and maidr.js then placed the
points along the path by their x:

* the gallery's contour labels its levels inline, which opens every ring it
  labels; its outer levels were written with 136 of 202, 114 of 153 and 98 of
  132 vertices, and the highlight stuck on the first point of the 0.15 level
  and crossed the ring on the 0.3 level;
* ``maidr.keras.plot_pr_curve`` draws a curve per model through every
  threshold; the gallery's 275-point curve was written with 4 vertices, and
  most of its points were outlined far from where they are drawn.

The survival curves (``maidr/survival.py``) and plotnine's lines already draw
with every vertex kept; these do now too.
"""

from __future__ import annotations

import re

import numpy as np
import pytest

pytest.importorskip("lxml")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from lxml import etree  # noqa: E402
from lxml.cssselect import CSSSelector  # noqa: E402

import maidr  # noqa: E402
import maidr.keras  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _rendered(figure) -> tuple[list[dict], etree._Element]:
    """Render a figure; return its layers' schemas and its SVG."""
    html = maidr.render(figure)._repr_html_()
    svg = re.search(r"<svg.*?</svg>", html, re.S)
    assert svg is not None
    root = etree.fromstring(svg.group(0).encode(), etree.XMLParser(recover=True))
    for element in root.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]
    layers = [plot.schema for plot in FigureManager.get_maidr(figure)._plots]
    return layers, root


def _vertices(path) -> np.ndarray:
    """The vertices of an SVG ``path``, in the SVG's own coordinates."""
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", path.get("d"))]
    return np.array(numbers).reshape(-1, 2)


def _miss(path, xs: list[float], ys: list[float]) -> float:
    """
    How far a path's vertices are from the points ``(xs, ys)``, in order.

    On linear axes the vertices of a path drawn through the points are their
    affine image, one each, in the same order; this is the largest distance,
    in SVG units, of a vertex from the best such image.
    """
    vertices = _vertices(path)
    assert len(vertices) == len(xs), (
        f"the path has {len(vertices)} vertices for {len(xs)} points"
    )
    worst = 0.0
    for values, drawn in ((xs, vertices[:, 0]), (ys, vertices[:, 1])):
        design = np.column_stack([np.asarray(values, dtype=float), np.ones(len(drawn))])
        fit = np.linalg.lstsq(design, drawn, rcond=None)[0]
        worst = max(worst, float(np.abs(design @ fit - drawn).max()))
    return worst


def test_an_inline_labelled_contour_keeps_a_vertex_per_point() -> None:
    """The gallery's six-level Gaussian, labels and all."""
    x = np.linspace(-3, 3, 80)
    grid_x, grid_y = np.meshgrid(x, x)
    fig, ax = plt.subplots(figsize=(7, 6))
    contours = ax.contour(grid_x, grid_y, np.exp(-(grid_x**2 + grid_y**2) / 2), levels=6)
    ax.clabel(contours, inline=True, fontsize=8)

    (layer,), root = _rendered(fig)
    series = layer["data"]
    assert max(len(points) for points in series) >= 128, "no level long enough"
    for points, selector in zip(series, layer["selectors"]):
        (path,) = CSSSelector(selector)(root)
        xs = [point["x"] for point in points]
        ys = [point["y"] for point in points]
        assert _miss(path, xs, ys) < 0.01


def test_a_keras_pr_curve_keeps_a_vertex_per_threshold() -> None:
    """Three hundred scores, so a curve of more than 128 thresholds."""
    rng = np.random.default_rng(11)
    y_true = rng.integers(0, 2, 300)
    y_pred = np.clip(y_true * 0.3 + rng.random(300) * 0.7, 0, 1)
    figure = maidr.keras.plot_pr_curve(y_true, y_pred)

    (layer,), root = _rendered(figure)
    ((points,),) = [layer["data"]]
    assert len(points) >= 128
    assert "domMapping" not in layer, "the curve is drawn in the order listed"
    (path,) = CSSSelector(layer["selectors"][0])(root)
    xs = [point["x"] for point in points]
    ys = [point["y"] for point in points]
    assert _miss(path, xs, ys) < 0.01
