"""Each scatter layer reads the collection its own call drew (#426).

``ScatterPlot`` took the *first* ``PathCollection`` on the axes, under an
assumption ``extract_collection`` states outright: "We assume only one
collection of each type is present". A layer is one collection only while
nothing draws two, and two things routinely do -- seaborn's categorical
scatters draw one per category, and two ``ax.scatter()`` calls draw one each.

Every layer then re-read collection 0, which is the failure worth pinning
rather than a crash: the chart is not empty and does not error. A
three-category strip plot announced category "a" three times, once per layer
switch with nothing to tell the layers apart, and never announced b or c at
all -- 60 of 90 drawn points absent, with nothing in the output saying so.

Measured before the fix::

    stripplot: 3 scatter layers, sizes=[30, 30, 30], distinct payloads=1
    two ax.scatter calls -> layer sizes [10, 10]   (the second drew 80)

The collection is handed over by the patch through ``DRAWN_POINTS``, the
mechanism #380 introduced for ``Axes.bar``. ``seaborn.scatterplot`` is wrapped
through the same function and returns an ``Axes`` rather than a collection, so
it falls back to the sweep -- correct for it, and asserted below rather than
assumed, since it draws a single collection of every point even under ``hue``.
"""

from __future__ import annotations

import numpy as np
import pytest

sns = pytest.importorskip("seaborn")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.collections import PathCollection  # noqa: E402

from maidr.core.figure_manager import FigureManager  # noqa: E402

CATEGORIES = ["a", "b", "c"]
PER_CATEGORY = 30


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def frame() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    size = PER_CATEGORY * len(CATEGORIES)
    return pd.DataFrame(
        {
            "x": rng.normal(size=size),
            "y": rng.normal(size=size),
            "g": np.repeat(CATEGORIES, PER_CATEGORY),
        }
    )


def scatter_layers(ax) -> list[list[dict]]:
    maidr = FigureManager.get_maidr(ax.get_figure())
    return [
        plot.schema["data"]
        for plot in maidr._plots
        if str(plot.type).endswith("SCATTER")
    ]


def drawn_points(ax) -> set[tuple[float, float]]:
    """Every point matplotlib actually put on the axes.

    Sound on a numeric axis, where the position a point is drawn at *is* its
    value. The categorical charts use :func:`drawn_values` instead.
    """
    return {
        (round(float(x), 9), round(float(y), 9))
        for collection in ax.collections
        if isinstance(collection, PathCollection)
        for x, y in collection.get_offsets()
    }


def drawn_values(ax) -> set[float]:
    """Every observation matplotlib actually put on the axes.

    Identified by its ``y`` alone, which on these charts is the measurement --
    the ``x`` a strip or swarm point is drawn at is a jitter or a packing
    offset chosen by the renderer, and #439 stopped announcing it. Comparing
    against the drawn ``x`` would now be comparing against the artefact, and
    snapping it here as well would only restate the implementation.
    """
    return {
        round(float(y), 9)
        for collection in ax.collections
        if isinstance(collection, PathCollection)
        for _, y in collection.get_offsets()
    }


def drawn_values_on_x(ax) -> set[float]:
    """:func:`drawn_values` for a chart turned on its side."""
    return {
        round(float(x), 9)
        for collection in ax.collections
        if isinstance(collection, PathCollection)
        for x, _ in collection.get_offsets()
    }


def announced_points(ax) -> list[tuple[float, float]]:
    return [
        (round(float(point["x"]), 9), round(float(point["y"]), 9))
        for layer in scatter_layers(ax)
        for point in layer
    ]


@pytest.mark.parametrize("plot", ["stripplot", "swarmplot"])
class TestACategoricalScatter:
    def test_each_layer_is_a_different_category(self, plot):
        # The defect's signature: three layers holding one category's points.
        ax = getattr(sns, plot)(data=frame(), x="g", y="y")
        layers = scatter_layers(ax)

        assert len(layers) == len(CATEGORIES)
        assert len({repr(layer) for layer in layers}) == len(CATEGORIES)

    def test_every_drawn_point_is_announced_exactly_once(self, plot):
        # Stronger than "the layers differ": it is what the reader loses.
        # A layer set that is distinct but still misses a category would
        # satisfy the case above and fail this one.
        ax = getattr(sns, plot)(data=frame(), x="g", y="y")
        announced = announced_points(ax)

        assert len(announced) == PER_CATEGORY * len(CATEGORIES)
        assert {y for _, y in announced} == drawn_values(ax)
        assert len(set(announced)) == len(announced)

    def test_the_points_sit_on_the_ticks_rather_than_where_jitter_put_them(self, plot):
        # The other half of #439. Both charts scatter their points sideways so
        # overlapping observations stay separable -- randomly for a strip, by a
        # packing algorithm for a swarm -- and that offset was announced as the
        # value of an axis whose ticks read a, b and c.
        ax = getattr(sns, plot)(data=frame(), x="g", y="y")

        assert {x for x, _ in announced_points(ax)} == {0.0, 1.0, 2.0}

    def test_the_layers_sit_at_the_three_category_positions(self, plot):
        # Each category is drawn around its own tick, so the layers' x values
        # must land in three separate unit-wide bands. Reading collection 0
        # three times puts all three in the first band.
        ax = getattr(sns, plot)(data=frame(), x="g", y="y")
        bands = {
            round(float(np.mean([point["x"] for point in layer])))
            for layer in scatter_layers(ax)
        }

        assert bands == {0, 1, 2}


class TestTwoScatterCallsOnOneAxes:
    def test_each_call_reads_its_own_points(self):
        # Pure matplotlib, no seaborn involved: the same defect, and the
        # reason this is not filed as a seaborn issue.
        data = frame()
        first = plt.scatter(data.x[:10], data.y[:10])
        second = plt.scatter(data.x[10:], data.y[10:])
        sizes = [len(layer) for layer in scatter_layers(second.axes)]

        assert first is not second
        assert sizes == [10, len(data) - 10]

    def test_no_point_is_announced_twice(self):
        data = frame()
        plt.scatter(data.x[:10], data.y[:10])
        second = plt.scatter(data.x[10:], data.y[10:])
        announced = announced_points(second.axes)

        assert len(set(announced)) == len(announced)
        assert set(announced) == drawn_points(second.axes)


class TestTheSingleCollectionCasesAreUnchanged:
    """What the sweep was right about, and must stay right about.

    These are the shapes the existing tests cover, which is why the defect
    stayed invisible -- so they are the ones a fix has to leave alone.
    """

    def test_a_numeric_axis_keeps_every_coordinate_exactly(self):
        # The guard on #439's snapping. On a numeric axis the position a point
        # is drawn at *is* its value, so snapping it to a tick would round 90
        # measurements onto a handful of gridlines -- silently, and with the
        # payload still looking like a scatter plot.
        data = frame()
        collection = plt.scatter(data.x, data.y)
        announced = announced_points(collection.axes)

        assert set(announced) == drawn_points(collection.axes)

    def test_a_horizontal_strip_snaps_the_category_axis_not_the_values(self):
        # Categories sit on y when the chart is turned on its side, and the
        # axis carrying them is the one to snap. Asking about x alone was
        # exactly the defect #353 fixed for lines, so it is pinned here rather
        # than left to the helper being symmetric.
        ax = sns.stripplot(data=frame(), y="g", x="y")
        announced = announced_points(ax)

        assert {y for _, y in announced} == {0.0, 1.0, 2.0}
        assert {x for x, _ in announced} == drawn_values_on_x(ax)

    def test_a_plain_scatter_is_one_layer_of_every_point(self):
        data = frame()
        collection = plt.scatter(data.x, data.y)
        layers = scatter_layers(collection.axes)

        assert len(layers) == 1
        assert len(layers[0]) == len(data)

    def test_seaborn_scatterplot_under_hue_is_one_collection_split_by_group(self):
        # Two halves of one fact, and they pull in opposite directions.
        #
        # seaborn draws every point as a *single* collection even under
        # `hue`, which is why the seaborn binding keeps the sweep: the
        # fallback finds exactly the right artist. Asserted rather than
        # assumed, so that if it ever changes this fails rather than the
        # reading going quietly wrong.
        #
        # One collection is not one layer, though. The grouping is the chart
        # here, and it survives only in the per-point colours and the legend
        # that names them, so the layer count follows the groups rather than
        # the artists (#544). Together they still account for every point --
        # a split that lost one would be worse than no split at all.
        data = frame()
        ax = sns.scatterplot(data=data, x="x", y="y", hue="g")

        assert len([c for c in ax.collections if isinstance(c, PathCollection)]) == 1

        layers = scatter_layers(ax)
        assert len(layers) == data["g"].nunique()
        assert sum(len(layer) for layer in layers) == len(data)
