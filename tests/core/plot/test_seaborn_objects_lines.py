"""
`so.Lines` and `so.Paths` registered nothing (#670).

The many-series spelling of `so.Line` and `so.Path`. Measured on
`seaborn 0.13.2`, the difference is the artist and nothing else::

    so.Line(color=)    ax.lines        one Line2D per group
    so.Lines(color=)   ax.collections  ONE LineCollection, one segment per group

`MultiLinePlot` walks `Line2D` objects, so a collection reached no reading at
all and the whole chart fell back to a picture -- while the identical chart
written with the singular mark was navigable.

Two things follow, and each is a fact about the artist rather than a choice:

  - **The segments are the series.** One collection carries one per group, in
    the order the groups were drawn, with a colour each -- and the colour is
    what pairs a series with its legend entry, which is the pairing #582
    exists for.

  - **A series is a path inside one group, not a group of its own.** Measured
    against a real SVG export, a three-group collection writes three `<path>`
    elements as direct children of its `<g>`, in segment order. The inherited
    selector says `g[id=…] path`, which would outline every series at once.

An empty segment is not a case to handle: `LineCollection` refuses to hold
one -- matplotlib raises "'vertices' must be 2D" -- so the paths and the
series stay one to one. A single-point group *is* drawn, and keeps its place
in both.

Related: #672, which had to land first. A `so.Plot`'s legend is the figure's,
and until that was read a colour split arrived as unnamed series -- the shape
xability/maidr#828 exists to prevent.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import pytest
import seaborn.objects as so

import maidr
from maidr.core.figure_manager import FigureManager


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    """Two groups over the same positions, sharing no value between them."""
    return pd.DataFrame(
        {
            "x": [0.0, 1.0, 2.0, 0.0, 1.0, 2.0],
            "y": [1.0, 3.0, 2.0, 7.0, 9.0, 8.0],
            "g": ["p", "p", "p", "q", "q", "q"],
        }
    )


def _schema(build) -> dict:
    """The first layer's schema, after a real render."""
    figure = plt.figure()
    build(figure)
    maidr.render(figure)._repr_html_()
    return FigureManager.get_maidr(figure).plots[0].schema


def _split(mark, frame: pd.DataFrame | None = None) -> dict:
    data = _frame() if frame is None else frame
    return _schema(
        lambda fig: so.Plot(data, x="x", y="y", color="g").add(mark).on(fig).plot()
    )


MARKS = [pytest.param(so.Lines(), id="Lines"), pytest.param(so.Paths(), id="Paths")]


@pytest.mark.parametrize("mark", MARKS)
def test_a_collection_of_segments_reads_as_the_series_it_draws(mark):
    # The reproduction: before this the chart registered nothing at all and
    # fell back to a static image.
    schema = _split(mark)

    assert schema["type"] == "line"
    assert [[(point["x"], point["y"]) for point in series] for series in schema["data"]] == [
        [(0.0, 1.0), (1.0, 3.0), (2.0, 2.0)],
        [(0.0, 7.0), (1.0, 9.0), (2.0, 8.0)],
    ]


@pytest.mark.parametrize("mark", MARKS)
def test_each_series_carries_the_group_it_was_drawn_for(mark):
    # The colour a segment was drawn in is what pairs it with its legend
    # entry. Pairing by position instead gets two groups the wrong way round
    # whenever the legend is not in the drawn order (#582).
    schema = _split(mark)

    readings = {
        series[0]["z"]: [point["y"] for point in series] for series in schema["data"]
    }
    assert readings == {"p": [1.0, 3.0, 2.0], "q": [7.0, 9.0, 8.0]}


@pytest.mark.parametrize("mark", MARKS)
def test_the_variable_the_series_are_split_by_is_named(mark):
    schema = _split(mark)

    assert schema["axes"]["z"] == {"label": "g"}


@pytest.mark.parametrize("mark", MARKS)
def test_each_series_addresses_its_own_path_inside_the_one_group(mark):
    # One collection is one SVG group holding one `<path>` per segment, in
    # segment order. The inherited selector says `g[id=…] path`, which would
    # hand every series every other one's line.
    schema = _split(mark)
    selectors = schema["selectors"]

    assert len(selectors) == 2
    gid = selectors[0].split("'")[1]
    assert gid.startswith("maidr-")
    assert selectors == [
        f"g[id='{gid}'] > path:nth-of-type(1)",
        f"g[id='{gid}'] > path:nth-of-type(2)",
    ]


def test_a_selector_resolves_to_exactly_one_drawn_path():
    # The half a schema cannot check on its own: that the group is really
    # there and really holds one path per series.
    import io

    from lxml import etree

    figure = plt.figure()
    so.Plot(_frame(), x="x", y="y", color="g").add(so.Lines()).on(figure).plot()
    maidr.render(figure)._repr_html_()
    schema = FigureManager.get_maidr(figure).plots[0].schema

    buffer = io.BytesIO()
    figure.savefig(buffer, format="svg")
    root = etree.fromstring(buffer.getvalue())
    namespaces = {"s": "http://www.w3.org/2000/svg"}
    gid = schema["selectors"][0].split("'")[1]
    group = root.xpath(f"//s:g[@id='{gid}']", namespaces=namespaces)

    assert len(group) == 1
    assert len(group[0].xpath("./s:path", namespaces=namespaces)) == 2


def test_an_ungrouped_collection_reads_as_the_one_series_it_draws():
    # Nothing to split by draws a single polyline through every row, sorted
    # along the orient axis -- one segment, and one series.
    schema = _schema(
        lambda fig: so.Plot(_frame(), x="x", y="y").add(so.Lines()).on(fig).plot()
    )

    assert len(schema["data"]) == 1
    assert "z" not in schema["axes"]
    assert len(schema["selectors"]) == 1


def test_a_group_of_one_point_keeps_its_place_in_both_lists():
    # Measured, a single-point group still leaves a segment and a degenerate
    # path of its own -- so dropping it would shift every later series onto
    # its neighbour's line.
    lonely = pd.DataFrame(
        {
            "x": [0.0, 1.0, 2.0, 5.0],
            "y": [1.0, 3.0, 2.0, 9.0],
            "g": ["p", "p", "p", "q"],
        }
    )
    schema = _split(so.Lines(), lonely)

    assert [len(series) for series in schema["data"]] == [3, 1]
    assert [series[0]["z"] for series in schema["data"]] == ["p", "q"]
    assert len(schema["selectors"]) == 2


def test_a_series_stands_in_for_its_segment_and_carries_its_colour():
    # The stand-ins are what `MultiLinePlot` walks, and the colour is the
    # half that is not obvious: it is what pairs a series with its legend
    # entry, and pairing by position instead gets two groups the wrong way
    # round whenever the legend is not in the drawn order (#582). Asserted
    # directly, because a `so.Plot` always draws its groups in legend order
    # and so cannot tell the two rules apart on its own.
    figure = plt.figure()
    so.Plot(_frame(), x="x", y="y", color="g").add(so.Lines()).on(figure).plot()
    maidr.render(figure)._repr_html_()
    plot = FigureManager.get_maidr(figure).plots[0]
    collection = figure.axes[0].collections[0]

    stand_ins = plot._series()
    assert len(stand_ins) == len(collection.get_segments())
    assert [line.get_xydata().tolist() for line in stand_ins] == [
        segment.tolist() for segment in collection.get_segments()
    ]
    assert [tuple(line.get_color()) for line in stand_ins] == [
        tuple(colour) for colour in collection.get_colors()
    ]


def test_one_colour_over_many_segments_is_cycled_the_way_it_is_drawn():
    # Matplotlib does not expand a short colour list: measured, a collection
    # drawn in one colour reports exactly one however many segments it
    # holds -- and that is the *default*. Reading it by position would raise
    # on the second segment.
    from matplotlib.collections import LineCollection

    from maidr.core.plot.segment_lineplot import SegmentLinePlot

    figure, ax = plt.subplots()
    collection = LineCollection(
        [[(0.0, 0.0), (1.0, 1.0)], [(0.0, 1.0), (1.0, 2.0)], [(0.0, 2.0), (1.0, 3.0)]],
        colors="red",
    )
    ax.add_collection(collection)
    ax.autoscale()

    stand_ins = SegmentLinePlot(ax, collection)._series()

    assert len(collection.get_colors()) == 1
    assert len(stand_ins) == 3
    assert {tuple(line.get_color()) for line in stand_ins} == {
        tuple(collection.get_colors()[0])
    }


def test_the_collection_is_what_gets_tagged_rather_than_the_stand_ins():
    # `plot.elements` is the list the highlight machinery writes a `maidr`
    # attribute onto. The stand-ins were never added to the axes, so tagging
    # them would write onto nothing and the drawn group would carry none.
    figure = plt.figure()
    so.Plot(_frame(), x="x", y="y", color="g").add(so.Lines()).on(figure).plot()
    maidr.render(figure)._repr_html_()
    plot = FigureManager.get_maidr(figure).plots[0]

    assert plot.elements == [figure.axes[0].collections[0]]


def test_the_singular_mark_still_reads_the_way_it_did():
    # What this is being brought into line *with*, asserted here so a change
    # that broke the `Line2D` path to serve the collection is caught.
    schema = _split(so.Line())

    assert schema["type"] == "line"
    assert [series[0]["z"] for series in schema["data"]] == ["p", "q"]
    assert schema["axes"]["z"] == {"label": "g"}
