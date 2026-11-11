"""A precision-recall curve drawn as a staircase keeps a vertex for each point.

maidr.js outlines a ``pr_curve`` point at its own vertex of the path the
layer's selector names, a staircase's corners skipped, in the order the
points are listed, or the other way round under ``domMapping.pointOrder:
"reverse"``. ``PrecisionRecallDisplay`` draws each curve with
``drawstyle="steps-post"`` from high recall down, and a curve drawn by hand
with ``ax.step`` is the same staircase. matplotlib merged the vertices of a
long one as it drew it -- the gallery's 151-point curves were written with 62
-- and the display's curve was read from low recall up with nothing saying it
was drawn the other way, so the outline ran backwards along the display's
curve and never left the first vertex of the hand-drawn one.
"""

from __future__ import annotations

import re

import numpy as np
import pytest

pytest.importorskip("lxml")
sklearn_metrics = pytest.importorskip("sklearn.metrics")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from lxml import etree  # noqa: E402
from lxml.cssselect import CSSSelector  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

import maidr  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402

PrecisionRecallDisplay = sklearn_metrics.PrecisionRecallDisplay


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _scores(seed: int, signal: float) -> tuple[np.ndarray, np.ndarray]:
    """Labels and scores with a few hundred distinct thresholds."""
    rng = np.random.default_rng(seed)
    labels = rng.integers(0, 2, 300)
    return labels, labels * signal + rng.random(300)


def _rendered(figure) -> tuple[dict, etree._Element]:
    """Render a figure of one layer; return the layer's schema and the SVG."""
    html = maidr.render(figure)._repr_html_()
    svg = re.search(r"<svg.*?</svg>", html, re.S)
    assert svg is not None
    root = etree.fromstring(svg.group(0).encode(), etree.XMLParser(recover=True))
    for element in root.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]
    (layer,) = [plot.schema for plot in FigureManager.get_maidr(figure)._plots]
    return layer, root


def _point_vertices(layer: dict, root, curve: int) -> np.ndarray:
    """
    The vertices of a curve's path that its points are drawn at.

    A ``steps-post`` staircase through N points has ``2N - 1`` vertices, the
    points at the even ones, in the order the line is drawn.
    """
    (path,) = CSSSelector(layer["selectors"][curve])(root)
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", path.get("d"))]
    vertices = np.array(numbers).reshape(-1, 2)
    points = len(layer["data"][curve])
    assert len(vertices) == 2 * points - 1, (
        f"the path has {len(vertices)} vertices for {points} points"
    )
    return vertices[::2]


def _miss(vertices: np.ndarray, points: list[dict]) -> float:
    """
    How far vertices are from the points, one each, in order.

    On linear axes the vertices drawn at the points are their affine image;
    this is the largest distance, in SVG units, of a vertex from the best
    such image.
    """
    worst = 0.0
    for key, drawn in (("x", vertices[:, 0]), ("y", vertices[:, 1])):
        values = np.array([point[key] for point in points], dtype=float)
        design = np.column_stack([values, np.ones(len(values))])
        fit = np.linalg.lstsq(design, drawn, rcond=None)[0]
        worst = max(worst, float(np.abs(design @ fit - drawn).max()))
    return worst


def test_a_display_curve_keeps_its_vertices_and_says_it_is_drawn_reversed():
    fig, ax = plt.subplots()
    good, poor = _scores(0, 0.6), _scores(1, 0.2)
    PrecisionRecallDisplay.from_predictions(*good, ax=ax, name="good")
    PrecisionRecallDisplay.from_predictions(*poor, ax=ax, name="poor")

    layer, root = _rendered(fig)

    assert layer["type"] == "pr_curve"
    assert layer["domMapping"] == {"pointOrder": "reverse"}
    for curve, points in enumerate(layer["data"]):
        assert len(points) >= 128
        assert [p["x"] for p in points] == sorted(p["x"] for p in points)
        # Drawn from high recall down, so read back to front.
        assert _miss(_point_vertices(layer, root, curve)[::-1], points) < 0.01


def test_a_curve_drawn_by_hand_with_step_keeps_its_vertices():
    precision, recall, _ = sklearn_metrics.precision_recall_curve(*_scores(0, 0.6))
    fig, ax = plt.subplots()
    ax.step(recall, precision, where="post")
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")

    layer, root = _rendered(fig)

    assert layer["type"] == "pr_curve"
    ((points,),) = [layer["data"]]
    assert len(points) >= 128
    # Listed as drawn, from high recall down: maidr.js turns it round.
    assert "domMapping" not in layer
    assert _miss(_point_vertices(layer, root, 0), points) < 0.01


def test_curves_drawn_both_ways_are_read_without_an_outline():
    fig, ax = plt.subplots()
    PrecisionRecallDisplay(
        precision=np.array([0.5, 0.8, 1.0]), recall=np.array([1.0, 0.5, 0.0])
    ).plot(ax=ax, name="down")
    PrecisionRecallDisplay(
        precision=np.array([1.0, 0.7, 0.4]), recall=np.array([0.0, 0.5, 1.0])
    ).plot(ax=ax, name="up")

    layer, _ = _rendered(fig)

    assert "selectors" not in layer
    assert "domMapping" not in layer
    for points in layer["data"]:
        assert [p["x"] for p in points] == [0.0, 0.5, 1.0]


def test_a_curve_with_a_missing_rate_is_read_without_an_outline():
    # The missing precision is left out of the reading and breaks the line
    # where it falls, so the path's vertices no longer stand one for each
    # point read.
    fig, ax = plt.subplots()
    PrecisionRecallDisplay(
        precision=np.array([0.5, np.nan, 0.8, 1.0]),
        recall=np.array([1.0, 0.7, 0.5, 0.0]),
    ).plot(ax=ax)

    layer, _ = _rendered(fig)

    assert "selectors" not in layer
    assert "domMapping" not in layer
    ((points,),) = [layer["data"]]
    assert [p["x"] for p in points] == [0.0, 0.5, 1.0]


def test_reading_a_hand_drawn_curve_again_keeps_every_vertex():
    precision, recall, _ = sklearn_metrics.precision_recall_curve(*_scores(0, 0.6))
    fig, ax = plt.subplots()
    (line,) = ax.step(recall, precision, where="post")
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    (plot,) = FigureManager.get_maidr(fig)._plots

    first, root = _rendered(fig)
    kept = type(line)
    plot.render()
    again, root_again = _rendered(fig)

    # Written before and after the layer is read again, the path has a vertex
    # for every point with a corner between, and the line's class was swapped
    # once.
    assert _miss(_point_vertices(first, root, 0), first["data"][0]) < 0.01
    assert _miss(_point_vertices(again, root_again, 0), again["data"][0]) < 0.01
    assert kept is not Line2D
    assert type(line) is kept


def test_a_curve_whose_recall_never_changes_is_read_as_drawn():
    # Every step of its recall is 0, so it neither rises nor falls.
    fig, ax = plt.subplots()
    PrecisionRecallDisplay(
        precision=np.array([0.4, 0.6, 0.9]), recall=np.array([0.5, 0.5, 0.5])
    ).plot(ax=ax)

    layer, _ = _rendered(fig)

    assert "domMapping" not in layer
    assert len(layer["selectors"]) == 1
    ((points,),) = [layer["data"]]
    assert [p["y"] for p in points] == [0.4, 0.6, 0.9]


def test_a_vertical_drop_is_read_from_its_top_along_the_line():
    # precision_recall_curve holds a recall of 0.6 at three thresholds, its
    # precision rising from 0.6 to 1 as they rise; read from low recall up,
    # the line drops there from 1 to 0.6.
    y_true = np.array([0, 0, 1, 1, 0, 1, 0, 1, 1, 0])
    y_score = np.array([0.1, 0.4, 0.35, 0.8, 0.2, 0.9, 0.6, 0.7, 0.3, 0.05])
    fig, ax = plt.subplots()
    PrecisionRecallDisplay.from_predictions(y_true, y_score, ax=ax)

    layer, root = _rendered(fig)

    assert layer["domMapping"] == {"pointOrder": "reverse"}
    ((points,),) = [layer["data"]]
    read = [(p["x"], p["y"]) for p in points]
    assert [y for x, y in read if x == pytest.approx(0.6)] == [1.0, 0.75, 0.6]
    # The higher precision first where a recall repeats, as the sorted
    # reading had it, and each point on its own vertex.
    assert read == sorted(read, key=lambda point: (point[0], -point[1]))
    assert _miss(_point_vertices(layer, root, 0)[::-1], points) < 0.01


def test_a_one_point_curve_beside_a_reversed_one_keeps_the_reversed_reading():
    # One point has no recall step either way, so it does not tell against
    # the other curve's direction.
    fig, ax = plt.subplots()
    PrecisionRecallDisplay(
        precision=np.array([0.4, 0.7, 1.0]), recall=np.array([1.0, 0.5, 0.0])
    ).plot(ax=ax, name="curve")
    PrecisionRecallDisplay(precision=np.array([0.9]), recall=np.array([0.2])).plot(
        ax=ax, name="point"
    )

    layer, _ = _rendered(fig)

    assert layer["domMapping"] == {"pointOrder": "reverse"}
    assert len(layer["selectors"]) == 2
    assert [p["x"] for p in layer["data"][0]] == [0.0, 0.5, 1.0]
