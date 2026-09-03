"""Tests for area charts.

``Axes.stackplot`` registered nothing at all before this, so an area chart
carried no data. It is emitted as an area layer rather than a line one because
a stacked area draws **two** numbers at each point that a line would conflate:
the band's height is the series' own value, and its top edge is the running
total. A reader told one of them has nothing to say which they heard.

The values are read from the caller's arguments rather than from the drawn
polygons, which is the opposite of how the error bar and point plot layers
work -- and these tests are written to hold that choice honest, since the
arguments are only the right source while ``stackplot`` is the thing doing the
accumulating.
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.core.plot.areaplot import AreaPlot  # noqa: E402


#: Two series over four years. Every value is distinct and no series' value
#: equals another's running total, so a reading that took the band's top edge
#: instead of its height cannot coincide with the right answer.
X = [2019, 2020, 2021, 2022]
SUBS = [10, 20, 25, 30]
SERVICES = [5, 8, 12, 14]


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _plots(fig):
    """
    Return the MAIDR plots registered for a figure, or an empty list.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure to read.

    Returns
    -------
    list
        The registered plots.
    """
    maidr_instance = FigureManager.figs.get(fig)
    return list(maidr_instance._plots) if maidr_instance else []


def _schema(fig) -> dict:
    """
    Return the layer schema of a figure's only plot.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure to read.

    Returns
    -------
    dict
        The MAIDR layer schema.
    """
    return _plots(fig)[0].render()


def _values(schema: dict, index: int) -> list[float]:
    """
    Pull one series' magnitudes out of an emitted schema.

    Parameters
    ----------
    schema : dict
        The layer schema.
    index : int
        Which series.

    Returns
    -------
    list of float
        The series' values, in order.
    """
    return [point["y"] for point in schema["data"][index]]


def test_a_stackplot_registers_at_all():
    """
    The gap this closes: nothing was registered for an area chart.

    ``Axes.stackplot`` draws `FillBetweenPolyCollection`s, which no patch
    intercepted, so the figure carried no layer and the chart was unreadable.
    """
    fig, ax = plt.subplots()
    ax.stackplot(X, SUBS, SERVICES, labels=["Subscriptions", "Services"])

    plots = _plots(fig)

    assert len(plots) == 1
    assert isinstance(plots[0], AreaPlot)
    assert plots[0].type == PlotType.STACKED_AREA


def test_a_band_carries_its_own_value_not_the_running_total():
    """
    The reason this is an area layer rather than a line one.

    The consumer sums the series to reach the running total, so handing it a
    cumulative number would make the totals grow with the number of series
    rather than with the data. `stackplot` is given the per-series values and
    accumulates them itself, which is what makes its arguments the right source
    and its polygons the wrong one.
    """
    fig, ax = plt.subplots()
    ax.stackplot(X, SUBS, SERVICES, labels=["Subscriptions", "Services"])

    schema = _schema(fig)

    assert _values(schema, 0) == [10, 20, 25, 30]
    assert _values(schema, 1) == [5, 8, 12, 14]
    # Not the drawn top edges, which are 15, 28, 37, 44.
    assert _values(schema, 1) != [15, 28, 37, 44]


def test_one_band_is_an_area_and_several_are_stacked():
    """
    A single band has nothing stacked on it.

    Announcing a running total equal to the value at every point would be
    noise, so it reads as the plain area it is.
    """
    fig_one, one = plt.subplots()
    one.stackplot(X, SUBS)

    fig_two, two = plt.subplots()
    two.stackplot(X, SUBS, SERVICES)

    assert _schema(fig_one)["type"] == PlotType.AREA.value
    assert _schema(fig_two)["type"] == PlotType.STACKED_AREA.value


def test_a_two_dimensional_y_means_the_same_as_several_arrays():
    """
    ``stackplot(x, y)`` with a 2-D ``y`` stacks its rows.

    The same chart as ``stackplot(x, y1, y2)``, written the other way, so it
    has to read the same -- and it is the form a caller with a matrix reaches
    for.
    """
    fig_rows, rows = plt.subplots()
    rows.stackplot(X, np.array([SUBS, SERVICES]), labels=["a", "b"])

    fig_args, separate = plt.subplots()
    separate.stackplot(X, SUBS, SERVICES, labels=["a", "b"])

    assert _schema(fig_rows)["data"] == _schema(fig_args)["data"]


@pytest.mark.parametrize(
    "columns",
    [
        pytest.param(None, id="positional-labels"),
        pytest.param(["a", "b", "c", "d"], id="named-labels"),
    ],
)
def test_a_data_frame_of_series_is_read_by_row_like_matplotlib_reads_it(columns):
    """
    A ``DataFrame`` handed to ``stackplot`` is rows, not columns.

    Both of the obvious ways to split one give the columns instead. ``df[0]``
    is the column *labelled* zero, so it raises for named columns and picks
    the wrong axis when a column happens to be called that; iterating a frame
    yields the labels themselves and no data at all. Matplotlib reads the
    rows, and a description that disagreed with the drawing would be a
    different chart -- reported without an error either way, which is the
    reason to pin it.

    Parameterised over both label kinds because the two mistakes fail
    differently: named columns silently collapse to a single series, and
    integer ones survive far enough to produce nonsense.
    """
    frame = pd.DataFrame([SUBS, SERVICES], columns=columns)

    fig_frame, from_frame = plt.subplots()
    from_frame.stackplot(X, frame, labels=["a", "b"])

    fig_args, separate = plt.subplots()
    separate.stackplot(X, SUBS, SERVICES, labels=["a", "b"])

    assert _plots(fig_frame)[0].type == PlotType.STACKED_AREA
    assert _schema(fig_frame)["data"] == _schema(fig_args)["data"]


def test_each_band_is_named_after_its_label():
    """
    Without the name a reader hears two sets of numbers with nothing to say
    which series either belongs to -- what the legend gives a sighted reader.
    """
    fig, ax = plt.subplots()
    ax.stackplot(X, SUBS, SERVICES, labels=["Subscriptions", "Services"])

    schema = _schema(fig)

    assert schema["data"][0][0]["z"] == "Subscriptions"
    assert schema["data"][1][0]["z"] == "Services"


def test_an_unlabelled_chart_emits_no_series_name():
    """A caller who named nothing gets no invented names."""
    fig, ax = plt.subplots()
    ax.stackplot(X, SUBS, SERVICES)

    assert "z" not in _schema(fig)["data"][0][0]


def test_a_streamgraph_reads_as_the_stacked_area_it_is():
    """
    ``baseline='wiggle'`` floats the stack rather than sitting it on zero.

    That moves where the bands sit on the value axis without changing what any
    band measures, so the reading -- and the layer type -- are the same. A
    streamgraph is a stacked area drawn around a moving centre.
    """
    fig, ax = plt.subplots()
    ax.stackplot(X, SUBS, SERVICES, baseline="wiggle", labels=["a", "b"])

    schema = _schema(fig)

    assert schema["type"] == PlotType.STACKED_AREA.value
    assert _values(schema, 0) == [10, 20, 25, 30]


def test_every_band_is_tagged_for_highlighting():
    """
    One drawn element per series, in series order.

    The consumer resolves the selector to one element per series and discards
    the result outright when the count disagrees, so a partial list would
    silently highlight nothing.
    """
    fig, ax = plt.subplots()
    ax.stackplot(X, SUBS, SERVICES, labels=["a", "b"])

    plot = _plots(fig)[0]
    schema = plot.render()

    assert plot._support_highlighting is True
    assert len(plot.elements) == 2
    assert len(schema["selectors"]) == len(schema["data"])


def test_the_nth_selector_points_at_the_band_the_nth_series_drew():
    """
    Which band is which, asserted rather than assumed.

    The count matching is not the same claim: two selectors and two series
    pass that test whichever way round they are paired, and a reader whose
    highlight lands on the neighbouring band is told the wrong task by a
    chart that reports no error. Everything this layer says about a band --
    its value, its name, its running total -- is wrong for the band actually
    lit up.

    Order is checked through geometry rather than through the returned list,
    because the list is the assumption under test. A stacked band is drawn
    between the running total below it and the running total including it, so
    band *i*'s drawn extent is a fact about series 0..i that no other band
    shares.
    """
    fig, ax = plt.subplots()
    collections = ax.stackplot(X, SUBS, SERVICES, labels=["a", "b"])

    plot = _plots(fig)[0]
    schema = plot.render()
    tagged = [element.get_gid() for element in plot.elements]

    # Band 0 runs from the baseline to its own values; band 1 from band 0's
    # values to the pair's totals.
    lower = [np.zeros(len(X)), np.array(SUBS, dtype=float)]
    upper = [np.array(SUBS, dtype=float), np.array(SUBS) + np.array(SERVICES)]

    for index, collection in enumerate(collections):
        extent = collection.get_paths()[0].get_extents()

        assert extent.y0 == pytest.approx(lower[index].min())
        assert extent.y1 == pytest.approx(upper[index].max())
        # The element carrying that geometry is the one the schema names at
        # the same index, so the selector and the series agree.
        assert collection.get_gid() == tagged[index]
        assert collection.get_gid() in schema["selectors"][index]


def test_rendering_twice_does_not_double_the_elements():
    """
    A layer is rendered more than once -- ``set_id`` renders again when the
    schema is not yet cached -- and the tagged elements have to stay one per
    series or the highlight lands on the wrong band.
    """
    fig, ax = plt.subplots()
    ax.stackplot(X, SUBS, SERVICES)

    plot = _plots(fig)[0]
    plot.render()
    plot.render()

    assert len(plot.elements) == 2


def test_no_plot_type_is_named_to_a_user_with_an_underscore_in_it():
    """
    ``display_name`` exists because the wire value is not the user's word.

    ``_show_fallback`` lists these in one sentence, so a member with no
    override sits beside "stacked bar" and "dodged bar" reading
    "stacked_area" -- a schema token shown to someone who wrote
    ``ax.stackplot``.

    Asserted over every member rather than over the one this branch adds,
    because the gap is a class of mistake: a new multi-word type is
    registered in the enum and the override is a separate line to remember.
    """
    for plot_type in PlotType:
        assert "_" not in plot_type.display_name, plot_type.name

    assert PlotType.STACKED_AREA.display_name == "stacked area"
    assert PlotType.AREA.display_name == "area"


def test_the_axis_labels_travel():
    """The layer carries the chart's own axis labels, as every layer does."""
    fig, ax = plt.subplots()
    ax.stackplot(X, SUBS, SERVICES)
    ax.set_xlabel("Year")
    ax.set_ylabel("Revenue")

    axes = _schema(fig)["axes"]

    assert axes["x"]["label"] == "Year"
    assert axes["y"]["label"] == "Revenue"


def test_a_ragged_call_is_refused_rather_than_described():
    """
    A series shorter than the x it is drawn against is not a chart.

    Matplotlib rejects it, so this asserts the rejection happens rather than
    a partial layer being registered from a call that never drew.
    """
    fig, ax = plt.subplots()

    with pytest.raises(Exception):
        ax.stackplot(X, [1, 2])

    assert not _plots(fig)


def _reject_constant(token: str):
    raise ValueError(token)


def _parses_as_strict_json(schema: dict) -> None:
    """
    Assert the layer survives what the core actually runs on it.

    ``json.loads`` accepts the bare ``NaN`` token by default, exactly as
    ``json.dumps`` emits it, so a plain round trip passes while the browser
    fails. ``parse_constant`` is what lets this fail.

    Parameters
    ----------
    schema : dict
        The layer schema.
    """
    json.loads(json.dumps(schema["data"]), parse_constant=_reject_constant)


@pytest.mark.parametrize(
    "draw",
    [
        lambda ax, y: ax.stackplot(X, y, [v + 1 for v in y]),
        lambda ax, y: ax.fill_between(X, y),
        lambda ax, y: ax.stackplot(X, np.ma.masked_invalid(y)),
    ],
    ids=["stackplot", "fill_between", "masked"],
)
def test_a_missing_value_is_a_gap_rather_than_a_nan_token(draw):
    """
    A NaN in a series is a gap, not a reading -- and not a parse error.

    matplotlib draws a hole in the band, and ``json.dumps`` wrote the value
    as a bare ``NaN`` token that ``JSON.parse`` refuses, so the chart never
    initialised (#427). ``null`` is what the core's area trace reads as a
    gap that stays out of the running total.
    """
    fig, ax = plt.subplots()
    draw(ax, [10.0, np.nan, 25.0, 30.0])

    schema = _schema(fig)

    _parses_as_strict_json(schema)
    for series in schema["data"]:
        assert len(series) == 4
    assert _values(schema, 0) == [10.0, None, 25.0, 30.0]


def test_a_point_with_no_position_is_dropped_from_every_series():
    """
    A sample with a NaN position is nowhere a reader could be sent.

    The positions are shared across the series, so every series loses the
    same column and the bands stay the same length -- the consumer sums them
    column by column for the running total.
    """
    fig, ax = plt.subplots()
    ax.stackplot([2019, np.nan, 2021, 2022], SUBS, SERVICES)

    schema = _schema(fig)

    _parses_as_strict_json(schema)
    assert [point["x"] for point in schema["data"][0]] == [2019.0, 2021.0, 2022.0]
    assert _values(schema, 0) == [10, 25, 30]
    assert _values(schema, 1) == [5, 12, 14]
    assert len(schema["data"][0]) == len(schema["data"][1])
