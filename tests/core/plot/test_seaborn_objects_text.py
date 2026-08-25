"""
``so.Text`` wrote a label at each observation and registered nothing (#670).

It is the last of the thirteen marks `seaborn.objects` defines, and the only
one that draws no artist any other reading's holder names. Measured on
``seaborn 0.13.2``, twelve observations::

    ax.lines        []
    ax.collections  []
    ax.patches      []
    ax.texts        12 Text artists, 'a' at (8.0, 5.12), ...

So a figure whose only layer was a `so.Text()` had no layers at all and fell
back to a static image. The reading needs no new mechanism -- ``_held``
reaches a holder by name, and ``Axes.texts`` is a holder like any other.

**A label with nothing in it is not a point.** ``so.Text()`` written without
a ``text=`` variable still draws one artist per observation, each holding an
empty string. Nothing is on the page, so the layer is declined *before it
registers* rather than by the reading refusing later: a registered layer
that cannot extract raises, and an ``ExtractionError`` takes the whole
figure to a static image.
"""

from __future__ import annotations

import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
import seaborn.objects as so

import maidr
from maidr.core.enum import MaidrKey, PlotType
from maidr.core.figure_manager import FigureManager


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    """Twelve named observations."""
    rng = np.random.default_rng(7)
    return pd.DataFrame(
        {
            "x": rng.integers(1, 9, 12),
            "y": rng.normal(5, 2, 12),
            "name": list("abcdefghijkl"),
        }
    )


def _layers(plot) -> list[dict]:
    return [layer.schema for layer in FigureManager.get_maidr(plot.plot()._figure).plots]


def _only(plot) -> dict:
    schemas = _layers(plot)
    assert len(schemas) == 1, f"expected one layer, got {len(schemas)}"
    return schemas[0]


def _labelled(**kwargs):
    return so.Plot(_frame(), x="x", y="y", text="name", **kwargs).add(so.Text())


def test_a_text_mark_is_read_rather_than_registering_nothing():
    schema = _only(_labelled())

    assert schema[MaidrKey.TYPE] is PlotType.SCATTER
    assert len(schema[MaidrKey.DATA]) == 12


def test_the_label_is_the_payload_and_not_a_decoration():
    """A reader told "x is 8, y is 5.1" has been handed the two numbers they
    can hear the shape of already and withheld the one thing the chart was
    drawn to show. `ScatterPoint.label` is the field xability/maidr#1106
    added for exactly this."""
    frame = _frame()
    points = _only(_labelled())[MaidrKey.DATA]

    assert {point[MaidrKey.LABEL] for point in points} == set(frame["name"])


def test_each_label_is_read_where_it_was_written():
    frame = _frame()
    points = _only(_labelled())[MaidrKey.DATA]

    written = {
        (float(x), round(float(y), 6)): name
        for x, y, name in zip(frame["x"], frame["y"], frame["name"])
    }
    for point in points:
        key = (point[MaidrKey.X], round(point[MaidrKey.Y], 6))
        assert written[key] == point[MaidrKey.LABEL]


def test_a_selector_resolves_to_the_element_the_label_was_written_as():
    """matplotlib writes each `Text` as a group of its own, so a label has an
    element to name — and the gid has to be assigned before the SVG is, since
    matplotlib stamps one at draw time and the schema is built first."""
    figure = plt.figure()
    _labelled().on(figure).plot()
    selectors = FigureManager.get_maidr(figure).plots[0].schema[MaidrKey.SELECTOR]

    html = maidr.render(figure)._repr_html_()
    found = [
        selector
        for selector in selectors
        if re.search(
            r"<g id=\"" + re.escape(re.search(r"id='([^']+)'", selector).group(1)) + r"\"",
            html,
        )
    ]

    assert len(selectors) == 12
    assert len(found) == 12


def test_a_text_mark_with_nothing_written_registers_nothing():
    """Twelve empty strings are twelve marks a sighted reader cannot see.

    Declined *before* registration, not by the reading refusing afterwards:
    a registered layer that then cannot extract raises, and that takes the
    whole figure to a static image rather than this one layer.
    """
    from maidr.patch.seaborn_objects import _handovers, _READINGS

    figure = plt.figure()
    so.Plot(_frame(), x="x", y="y").add(so.Text()).on(figure).plot()
    axes = figure.axes[0]

    assert len(axes.texts) == 12, "seaborn draws an artist per observation"
    assert all(not artist.get_text() for artist in axes.texts)
    assert _handovers(_READINGS["Text"], axes, list(axes.texts)) == []


def test_a_text_beside_a_dot_reads_as_two_layers():
    schemas = _layers(
        so.Plot(_frame(), x="x", y="y", text="name").add(so.Dot()).add(so.Text())
    )

    assert [schema[MaidrKey.TYPE] for schema in schemas] == [
        PlotType.SCATTER,
        PlotType.SCATTER,
    ]
    # Only one of them carries the names: the `Dot` draws markers, which have
    # no text to read.
    assert MaidrKey.LABEL not in schemas[0][MaidrKey.DATA][0]
    assert MaidrKey.LABEL in schemas[1][MaidrKey.DATA][0]


def test_a_blank_label_among_written_ones_is_dropped():
    """A gap in the text variable draws an artist with an empty string.

    Announced it would be a point with no name at a position; dropped, the
    selectors still point at the right elements because they are numbered
    against the artists rather than against the announced points.
    """
    from maidr.core.plot.textplot import DRAWN_LABELS, TextPlot

    _, axes = plt.subplots()
    written = [
        axes.text(0.0, 1.0, "a"),
        axes.text(1.0, 2.0, ""),
        axes.text(2.0, 3.0, "c"),
    ]

    plot = TextPlot(axes, **{DRAWN_LABELS: written})
    points = plot._extract_plot_data()

    assert [point[MaidrKey.LABEL] for point in points] == ["a", "c"]
    # The middle artist keeps its place in the document, so the second
    # announced label must address the third element rather than the second.
    assert plot._get_selector() == [
        f"g[id='{written[0].get_gid()}']",
        f"g[id='{written[2].get_gid()}']",
    ]
    assert written[1].get_gid() is None


def test_a_label_written_at_no_coordinate_is_dropped():
    """`json.dumps` writes `NaN` as a bare token, which `JSON.parse` rejects.

    One of them stops the chart initialising at all (#427), so the label is
    dropped rather than announced -- and a point with no position has
    nothing left to say, unlike a bar that keeps its category.

    No `so.Text()` spelling reaches this: seaborn drops a row with a
    non-finite coordinate before it draws, the same way it does for a
    scatter. So the guard is tested against artists built to have the case,
    rather than left as an unreachable claim.
    """
    from maidr.core.plot.textplot import DRAWN_LABELS, TextPlot

    _, axes = plt.subplots()
    written = [
        axes.text(0.0, 1.0, "a"),
        axes.text(float("nan"), 2.0, "b"),
        axes.text(2.0, float("nan"), "c"),
        axes.text(3.0, 4.0, "d"),
    ]

    points = TextPlot(axes, **{DRAWN_LABELS: written})._extract_plot_data()

    assert [point[MaidrKey.LABEL] for point in points] == ["a", "d"]
