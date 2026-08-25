"""
``so.Bars`` drew a histogram and registered nothing (#670).

`so.Bar` is the categorical bar and `so.Bars` the continuous-x one seaborn
draws for a histogram. They leave different artists, and that is the whole of
why one was read and the other was not — measured on ``seaborn 0.13.2``::

    so.Bar(), so.Count()   Rectangle patches + a BarContainer   read as bar
    so.Bars(), so.Hist()   one PatchCollection of rectangles    --

``HistPlot`` looks a ``BarContainer`` up and finds none, which is the same
decline ``element="step"`` hit before ``SteppedHistPlot`` (#522).

Every bin is read off its own rectangle and nothing is reconstructed: a path
carries both edges and the count.

Two things had to be measured rather than assumed.

**The path winding is not the same in both orientations.** The first two
vertices span the *bin* when the chart is vertical and the *count* when it is
not, so no fixed pair of vertices names the edges. The reading takes the
rectangle's extent per axis instead, and the orientation comes from the fact
that bins advance while the baseline does not.

**A colour split overlays every level in one collection**, contiguous by
colour, where a classic ``seaborn.histplot(hue=...)`` draws a container per
level. Read whole it would announce two distributions' bins as one — the same
edge twice with two different counts. Split, it matches the classic reading.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
import seaborn.objects as so

import maidr
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    """Two groups over one continuous variable, far enough apart to tell."""
    rng = np.random.default_rng(3)
    return pd.DataFrame(
        {
            "v": np.concatenate([rng.normal(0, 1, 120), rng.normal(6, 1, 120)]),
            "g": ["a"] * 120 + ["b"] * 120,
        }
    )


def _layers(plot) -> list[dict]:
    """Every layer the drawn plot registered, as schemas."""
    return [layer.schema for layer in FigureManager.get_maidr(plot.plot()._figure).plots]


def _only(plot) -> dict:
    schemas = _layers(plot)
    assert len(schemas) == 1, f"expected one layer, got {len(schemas)}"
    return schemas[0]


def _bars(**kwargs):
    return so.Plot(_frame(), **kwargs).add(so.Bars(), so.Hist(bins=6))


def test_a_bars_mark_is_read_as_a_histogram_rather_than_registering_nothing():
    # The reproduction. Before this the mark fell through `_READINGS` and the
    # chart was a static image with nothing to navigate.
    schema = _only(_bars(x="v"))

    assert schema["type"] is PlotType.HIST
    assert len(schema["data"]) == 6


def test_every_bin_carries_both_edges_and_its_count():
    # All three are in the drawing -- a rectangle's path is
    # `[left, 0] [right, 0] [right, count] [left, count]` -- so nothing is
    # reconstructed from spacing the way a `poly` outline has to be.
    bins = _only(_bars(x="v"))["data"]

    assert all(point["xMin"] < point["xMax"] for point in bins)
    assert all(point["y"] >= 0 for point in bins)
    assert sum(point["y"] for point in bins) == 240


def test_the_bins_are_contiguous_and_in_order():
    # A histogram's bins abut. Reading them out of order, or dropping one,
    # would leave a reader walking a distribution with a hole in it.
    bins = _only(_bars(x="v"))["data"]

    for earlier, later in zip(bins, bins[1:]):
        assert earlier["xMax"] == pytest.approx(later["xMin"])


def test_a_vertical_chart_says_so():
    assert _only(_bars(x="v"))["orientation"] == "vert"


def test_a_sideways_chart_puts_the_bins_on_the_axis_it_drew_them_on():
    # The measured trap: the first two vertices differ on `x` in *both*
    # orientations, so a reading that named them would call this vertical and
    # put the bin edges where the counts belong.
    schema = _only(_bars(y="v"))

    assert schema["orientation"] == "horz"
    assert all(point["yMin"] < point["yMax"] for point in schema["data"])
    assert all(point["x"] >= 0 for point in schema["data"])


def test_one_bin_is_still_a_histogram():
    # No neighbour to read the advance from, so the orientation falls back to
    # the baseline: a histogram's bars grow from zero.
    schema = _only(so.Plot(_frame(), x="v").add(so.Bars(), so.Hist(bins=1)))

    assert schema["orientation"] == "vert"
    assert len(schema["data"]) == 1
    assert schema["data"][0]["y"] == 240


def test_a_colour_split_becomes_one_layer_per_level():
    # What the classic spelling already gives: `seaborn.histplot(hue=...)`
    # draws a container per level and reads as one layer each. This mark
    # overlays them in one collection, so the split happens here instead.
    schemas = _layers(_bars(x="v", color="g"))

    assert len(schemas) == 2
    assert [schema["name"] for schema in schemas] == ["a", "b"]


def test_each_level_gets_its_own_distribution_rather_than_both():
    # The fixture puts the groups six units apart, so a layer holding both
    # would show it in the counts rather than only in the label.
    first, second = _layers(_bars(x="v", color="g"))

    assert sum(point["y"] for point in first["data"]) == 120
    assert sum(point["y"] for point in second["data"]) == 120


def test_each_level_outlines_its_own_bars_and_not_its_neighbours():
    # Both levels' rectangles are in one collection, so a layer numbering its
    # selectors from one would outline the first level's bins whichever level
    # a reader was on. They are numbered against the collection instead.
    first, second = _layers(_bars(x="v", color="g"))
    positions = [
        int(selector.rsplit("(", 1)[1].rstrip(")"))
        for schema in (first, second)
        for selector in schema["selectors"]
    ]

    assert len(set(positions)) == len(positions)
    assert max(int(s.rsplit("(", 1)[1].rstrip(")")) for s in first["selectors"]) < min(
        int(s.rsplit("(", 1)[1].rstrip(")")) for s in second["selectors"]
    )


def test_a_selector_resolves_to_exactly_one_drawn_rectangle():
    # The half a schema cannot check: the group is really there, and it holds
    # one path per bin across both levels.
    import io

    from lxml import etree

    plot = _bars(x="v", color="g").plot()
    figure = plot._figure
    maidr.render(figure)._repr_html_()
    schemas = [layer.schema for layer in FigureManager.get_maidr(figure).plots]

    buffer = io.BytesIO()
    figure.savefig(buffer, format="svg")
    root = etree.fromstring(buffer.getvalue())
    namespaces = {"s": "http://www.w3.org/2000/svg"}
    gid = schemas[0]["selectors"][0].split("'")[1]
    group = root.xpath(f"//s:g[@id='{gid}']", namespaces=namespaces)

    assert len(group) == 1
    drawn = len(group[0].xpath("./s:path", namespaces=namespaces))
    assert drawn == sum(len(schema["selectors"]) for schema in schemas)


def test_the_categorical_bar_is_still_read_as_a_bar():
    # `so.Bar` and `so.Bars` are one letter apart and are different charts.
    # Claiming the categorical one as a histogram would announce bin edges
    # for categories that have none.
    schema = _only(so.Plot(_frame(), x="g").add(so.Bar(), so.Count()))

    assert schema["type"] is PlotType.BAR
    assert [point["x"] for point in schema["data"]] == ["a", "b"]

def test_a_stacked_level_is_announced_with_its_own_count():
    # `so.Stack()` lifts the later segments off the baseline -- measured, a
    # second level's bar runs from 1 to 41 -- so reading the top would
    # announce 41 where that level counted 40, and every level but the first
    # would carry its neighbours' counts. `HistPlot`'s own path reads the
    # segment for the same reason: matplotlib stacks by moving the bottom.
    schemas = _layers(
        so.Plot(_frame(), x="v", color="g").add(so.Bars(), so.Hist(bins=4), so.Stack())
    )

    assert len(schemas) == 2
    assert sum(point["y"] for point in schemas[0]["data"]) == 120
    assert sum(point["y"] for point in schemas[1]["data"]) == 120


def test_a_stack_does_not_disturb_the_orientation():
    # The baseline rule holds through a stack because the first segment still
    # sits on it. The sideways case is the one that would break if it did
    # not: the bins would be read as counts.
    upright = _layers(
        so.Plot(_frame(), x="v", color="g").add(so.Bars(), so.Hist(bins=4), so.Stack())
    )
    sideways = _layers(
        so.Plot(_frame(), y="v", color="g").add(so.Bars(), so.Hist(bins=4), so.Stack())
    )

    assert {schema["orientation"] for schema in upright} == {"vert"}
    assert {schema["orientation"] for schema in sideways} == {"horz"}


def test_each_selector_resolves_to_exactly_one_drawn_rectangle():
    # Numbering, not just ordering. `nth-of-type` counts from one, and a
    # selector numbered from zero matches nothing at all -- which a schema
    # cannot show and an ordering assertion passes straight over.
    import io

    from lxml import etree

    plot = _bars(x="v").plot()
    figure = plot._figure
    maidr.render(figure)._repr_html_()
    schema = FigureManager.get_maidr(figure).plots[0].schema

    buffer = io.BytesIO()
    figure.savefig(buffer, format="svg")
    root = etree.fromstring(buffer.getvalue())
    namespaces = {"s": "http://www.w3.org/2000/svg"}
    gid = schema["selectors"][0].split("'")[1]
    group = root.xpath(f"//s:g[@id='{gid}']", namespaces=namespaces)
    assert len(group) == 1

    paths = group[0].xpath("./s:path", namespaces=namespaces)
    for selector in schema["selectors"]:
        position = int(selector.rsplit("(", 1)[1].rstrip(")"))
        assert 1 <= position <= len(paths)



def test_a_collection_given_fewer_colours_than_rectangles_still_splits():
    """
    Grouping reads a collection's colours cyclically, as matplotlib draws them.

    ``PatchCollection.get_facecolors()`` returns exactly what was set, and a
    collection given fewer colours than it has paths cycles them at draw
    time -- measured, four rectangles and two colours come back as a ``(2, 4)``
    array while all four are drawn. Indexed straight, the third rectangle
    would fall off the end of the array.

    No ``so.Bars`` chart is in that position: seaborn sets one colour per
    rectangle, measured 8 for 8 bins and 16 for a two-level split. The cycle
    is here for the collection contract rather than for a spelling of the
    mark, so it is tested against a collection built to have it.
    """
    from matplotlib.patches import Patch, Rectangle
    from matplotlib.collections import PatchCollection

    from maidr.core.plot.bars_histogram import hist_groups

    red, blue = (1.0, 0.0, 0.0, 1.0), (0.0, 0.0, 1.0, 1.0)
    _, ax = plt.subplots()
    collection = PatchCollection(
        [Rectangle((index, 0), 1, 1) for index in range(4)],
        facecolors=[red, blue],
    )
    ax.add_collection(collection)
    ax.legend(
        handles=[Patch(facecolor=red, label="a"), Patch(facecolor=blue, label="b")]
    )

    assert len(collection.get_facecolors()) == 2, "the fixture must be short of colours"
    assert hist_groups(ax, collection) == [("a", [0, 2]), ("b", [1, 3])]


def test_a_rectangle_of_no_width_is_not_announced_as_a_bin():
    """
    A degenerate rectangle spans no bin, so it is skipped rather than read.

    No ``so.Bars`` spelling reaches this -- a bin the binner produced has a
    width whether or not anything landed in it, measured across ``Hist``,
    ``Count``, ``Agg`` and a raw ``y`` -- so the guard is tested against a
    collection built to have one. Announced, it would put both edges of a
    bin at the same place and claim a boundary the chart never drew.
    """
    from matplotlib.collections import PatchCollection
    from matplotlib.patches import Rectangle

    from maidr.core.plot.bars_histogram import DRAWN_BINS, BarsHistPlot

    _, ax = plt.subplots()
    collection = PatchCollection(
        [Rectangle((0, 0), 2, 5), Rectangle((2, 0), 0, 5), Rectangle((2, 0), 2, 3)]
    )
    ax.add_collection(collection)

    points = BarsHistPlot(ax, **{DRAWN_BINS: collection})._extract_plot_data()

    assert len(points) == 2, f"the degenerate rectangle was read: {points}"
    assert [point["xMin"] for point in points] == [0, 2]
    assert [point["xMax"] for point in points] == [2, 4]
