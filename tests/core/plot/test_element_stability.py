"""Every layer tags the same artists however many times it is rendered.

``MaidrPlot._elements`` is the ordered list the highlight machinery tags, and
the frontend indexes into the resolved selection *by point index*. A list that
grew leaves point *n* pointing at the artist for point *n mod count*, so the
outline lands on a different mark from the one being announced. Nothing
errors, no announcement changes, and no assertion on the emitted data can see
it (#354).

A layer is rendered more than once as a matter of course: ``schema``,
``elements`` and ``set_id`` each render when nothing is cached, and three
types re-ran their extraction inside their own ``render()`` besides -- so for
those the list doubled within a *single* render.

These tests render twice and compare, which is the shape of the defect rather
than a count nobody can check. They also assert a count against something
independent -- the artists matplotlib actually drew -- because a list that is
merely *stable* could still be stably wrong.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402


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


# --------------------------------------------------------------------------
# One builder per layer type. Each draws a chart and returns its figure.
# --------------------------------------------------------------------------


def _bar():
    fig, ax = plt.subplots()
    ax.bar(["a", "b", "c"], [4.0, 5.0, 6.0])
    return fig


def _box():
    fig, ax = plt.subplots()
    ax.boxplot([[1, 2, 3, 10], [4, 5, 6, 20], [7, 8, 9, 30]])
    return fig


def _pie():
    fig, ax = plt.subplots()
    ax.pie([30, 50, 20], labels=["a", "b", "c"])
    return fig


def _hist():
    fig, ax = plt.subplots()
    ax.hist([1, 1, 2, 3, 3, 3, 4, 5, 5, 9], bins=4)
    return fig


def _line():
    fig, ax = plt.subplots()
    ax.plot([0, 1, 2, 3], [4.0, 5.0, 3.0, 6.0])
    return fig


def _scatter():
    fig, ax = plt.subplots()
    ax.scatter([1.0, 2.0, 3.0], [4.0, 5.0, 6.0])
    return fig


def _heat():
    fig, ax = plt.subplots()
    sns.heatmap(np.array([[1.0, 2.0], [3.0, 4.0]]), ax=ax)
    return fig


def _errorbar():
    fig, ax = plt.subplots()
    ax.errorbar([1, 2, 3], [4.0, 5.0, 6.0], yerr=[0.4, 0.6, 0.3], fmt="o")
    return fig


def _grouped_bar():
    frame = pd.DataFrame(
        {
            "group": ["a", "a", "b", "b", "c", "c"],
            "half": ["x", "y", "x", "y", "x", "y"],
            "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        }
    )
    fig, ax = plt.subplots()
    sns.barplot(frame, x="group", y="value", hue="half", ax=ax)
    return fig


def _regplot():
    fig, ax = plt.subplots()
    sns.regplot(
        x=np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
        y=np.array([2.0, 4.0, 5.0, 4.0, 6.0]),
        ax=ax,
    )
    return fig


def _pointplot():
    frame = pd.DataFrame(
        {
            "group": ["a"] * 4 + ["b"] * 4 + ["c"] * 4,
            "value": [1.0, 2.0, 3.0, 9.0, 20.0, 21.0, 22.0, 30.0, 5.0, 6.0, 7.0, 8.0],
        }
    )
    fig, ax = plt.subplots()
    sns.pointplot(frame, x="group", y="value", ax=ax)
    return fig


def _violin():
    frame = pd.DataFrame(
        {
            "group": ["a"] * 6 + ["b"] * 6,
            "value": [1.0, 2.0, 3.0, 4.0, 5.0, 9.0, 4.0, 5.0, 6.0, 7.0, 8.0, 12.0],
        }
    )
    fig, ax = plt.subplots()
    sns.violinplot(frame, x="group", y="value", ax=ax)
    return fig


def _area():
    fig, ax = plt.subplots()
    ax.stackplot([0, 1, 2], [[1.0, 2.0, 3.0], [3.0, 2.0, 1.0]], labels=["a", "b"])
    return fig


def _step():
    fig, ax = plt.subplots()
    ax.step([0.0, 1.0, 2.0, 3.0], [4, 2, 1, 3], where="post")
    return fig


#: Every layer type whose extraction appends to ``_elements``. The names are
#: the parameter ids, so a failure says which layer rather than which index.
BUILDERS = {
    "bar": _bar,
    "box": _box,
    "pie": _pie,
    "hist": _hist,
    "line": _line,
    "scatter": _scatter,
    "heat": _heat,
    "errorbar": _errorbar,
    "grouped_bar": _grouped_bar,
    "regplot": _regplot,
    "pointplot": _pointplot,
    "violin": _violin,
    "area": _area,
    "step": _step,
}


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_rendering_twice_tags_the_same_artists(name):
    """
    A second render must not add a second set of artists.

    This is the whole defect: the frontend pairs element *i* with point *i*,
    so a list that doubled points the highlight at the wrong mark for every
    point past the first set, while the data and the announcements stay
    correct. Rendering is not idempotent by accident -- ``schema``,
    ``elements`` and ``set_id`` each render when nothing is cached.
    """
    fig = BUILDERS[name]()
    plots = _plots(fig)
    assert plots, f"{name} registered no layer"

    for plot in plots:
        plot.render()
        after_first = list(plot.elements)
        plot.render()
        after_second = list(plot.elements)

        assert after_second == after_first


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_rendering_repeatedly_never_grows_the_list(name):
    """
    The count is flat, not merely equal between two renders.

    A fix that cleared on alternate renders would satisfy the pair above.
    Five renders is enough to catch a period-two mistake and cheap enough to
    run for every type.
    """
    fig = BUILDERS[name]()
    plots = _plots(fig)
    assert plots

    counts = []
    for _ in range(5):
        for plot in plots:
            plot.render()
        counts.append([len(plot.elements) for plot in plots])

    assert counts[1:] == counts[:-1]


@pytest.mark.parametrize("name", sorted(BUILDERS))
def test_rendering_twice_emits_the_same_selectors(name):
    """
    `_elements` is not the only list the selectors are built from.

    A layer may keep its own gid bookkeeping beside it, and those lists
    accumulated too. `BoxPlot` kept four — one per element role plus the
    outlier counts — so a second render emitted **twice as many selectors as
    there are boxes**, and because the same loop re-stamps a fresh gid on each
    artist every time, the first half named gids no artist carried any more.
    Those selectors resolve to nothing at all.

    The assertion is on how many, not on which. Several layers mint a fresh
    gid per artist on every render and name the new one, which stays
    consistent -- the artist carries the gid the selector asks for. What must
    not change is the count, because that is what the frontend pairs with the
    data.
    """
    fig = BUILDERS[name]()
    plots = _plots(fig)
    assert plots

    for plot in plots:
        first = plot.render().get("selectors")
        second = plot.render().get("selectors")

        assert isinstance(second, type(first))
        if isinstance(first, list):
            assert len(second) == len(first)


def test_a_box_layer_emits_one_selector_per_box():
    """
    Counted against the chart, so stable-but-wrong does not pass.

    Three distributions, three selectors, three points -- however many times
    the layer is rendered.
    """
    fig = _box()
    plot = _plots(fig)[0]

    for _ in range(3):
        schema = plot.render()

        assert len(schema["selectors"]) == 3
        assert len(schema["data"]) == 3


def test_a_bar_layer_tags_one_artist_per_bar():
    """
    Stable is not the same as right.

    Every assertion above passes on a list that is consistently twice as long
    as it should be, so at least one type is checked against something drawn
    rather than against itself: three bars, three patches, three points.
    """
    fig = _bar()
    plot = _plots(fig)[0]

    schema = plot.render()

    assert len(plot.elements) == 3
    assert len(schema["data"]) == 3


#: Eight sessions, enough for a 3-period moving average to be drawn and for
#: the volume-bar count to be checkable by eye.
OHLCV = pd.DataFrame(
    {
        "Open": [10.0, 11.0, 12.0, 11.0, 13.0, 14.0, 13.0, 15.0],
        "High": [11.0, 12.0, 13.0, 12.0, 14.0, 15.0, 14.0, 16.0],
        "Low": [9.0, 10.0, 11.0, 10.0, 12.0, 13.0, 12.0, 14.0],
        "Close": [11.0, 12.0, 11.0, 13.0, 14.0, 13.0, 15.0, 16.0],
        "Volume": [100.0, 120.0, 90.0, 130.0, 110.0, 140.0, 95.0, 150.0],
    },
    index=pd.date_range("2024-01-01", periods=8, freq="D"),
)


def _mplfinance_figure():
    """
    Draw a candlestick chart with volume and a moving average.

    Returns
    -------
    matplotlib.figure.Figure
        The figure, carrying a candlestick, a volume bar and a line layer.
    """
    mpf = pytest.importorskip("mplfinance")
    fig, _ = mpf.plot(OHLCV, type="candle", volume=True, mav=3, returnfig=True)
    return fig


def test_the_mplfinance_layers_extract_once_per_render():
    """
    Three layers re-ran their own extraction inside ``render()``.

    ``CandlestickPlot``, ``MplfinanceBarPlot`` and ``MplfinanceLinePlot`` each
    called ``super().render()`` -- which extracts -- and then overwrote
    ``data`` and ``selector`` with a second extraction, to refresh the axes.
    Only the axes needed refreshing; the second call appended another full set
    of artists, so these three doubled within a *single* render rather than
    across two. Clearing in ``render()`` cannot see that, because the second
    call comes after the clear.

    The counts are checked against the chart: eight sessions means eight
    volume bars, one moving average is one line, and a candlestick is drawn as
    a body collection and a wick collection.
    """
    from maidr.core.plot.candlestick import CandlestickPlot
    from maidr.core.plot.mplfinance_barplot import MplfinanceBarPlot
    from maidr.core.plot.mplfinance_lineplot import MplfinanceLinePlot

    fig = _mplfinance_figure()
    plots = {type(plot).__name__: plot for plot in _plots(fig)}

    assert set(plots) == {
        CandlestickPlot.__name__,
        MplfinanceBarPlot.__name__,
        MplfinanceLinePlot.__name__,
    }

    expected = {
        CandlestickPlot.__name__: 2,
        MplfinanceBarPlot.__name__: len(OHLCV),
        MplfinanceLinePlot.__name__: 1,
    }
    for name, plot in plots.items():
        plot.render()
        assert len(plot.elements) == expected[name], name
        plot.render()
        assert len(plot.elements) == expected[name], name


def test_a_horizontal_violin_keeps_its_selectors_paired_with_its_data():
    """
    The KDE layer reversed a list it did not own.

    A horizontal violin emits its series in the reverse of the drawn order, to
    match the box layer's convention. The data is rebuilt each render so
    reversing it is idempotent, but the gid list comes from the constructor
    and persists -- and it was reversed **in place**, so it was back in drawn
    order on every second render while the data was still reversed. Selector
    *i* then pointed at a different violin from point *i*, and the highlight
    landed on a neighbour. Silently, with no error and no change to anything
    announced: the same failure this file exists for, one list further along.

    Rendering an even number of times is exactly what the cases above do for
    every other layer, and none of them is horizontal.
    """
    from maidr.core.plot.violin_kde_plot import ViolinKdePlot

    fig, ax = plt.subplots()
    ax.violinplot(
        [[1.0, 2.0, 3.0, 9.0], [20.0, 21.0, 22.0, 30.0], [5.0, 6.0, 7.0, 8.0]],
        vert=False,
    )
    plot = [p for p in _plots(fig) if isinstance(p, ViolinKdePlot)][0]
    assert plot._orientation == "horz"

    drawn = list(plot._poly_gids)
    selectors = [plot.render()["selectors"] for _ in range(4)]

    # Every render agrees, rather than alternating between two orders.
    assert selectors[1:] == selectors[:-1]

    # And they agree on the *right* order: the reverse of the drawn one,
    # which is the order the data comes out in.
    assert all(
        gid in selector
        for gid, selector in zip(reversed(drawn), selectors[0])
    )

    # The constructor's list is left as it was found.
    assert plot._poly_gids == drawn


def test_a_vertical_violin_addresses_its_violins_in_drawn_order():
    """
    The counterpart: no reversal where none is due.

    A fix that reversed unconditionally would satisfy the stability check
    above and pair every vertical violin with the wrong body.
    """
    from maidr.core.plot.violin_kde_plot import ViolinKdePlot

    fig, ax = plt.subplots()
    ax.violinplot(
        [[1.0, 2.0, 3.0, 9.0], [20.0, 21.0, 22.0, 30.0], [5.0, 6.0, 7.0, 8.0]]
    )
    plot = [p for p in _plots(fig) if isinstance(p, ViolinKdePlot)][0]
    assert plot._orientation == "vert"

    drawn = list(plot._poly_gids)
    selectors = plot.render()["selectors"]

    assert all(
        gid in selector for gid, selector in zip(drawn, selectors)
    )


def test_a_violin_keeps_its_bodies_as_well_as_its_curves():
    """
    ``ViolinKdePlot`` registered its bodies in ``__init__``.

    That is why the fix could not be a clear in ``render()`` alone: clearing
    would have dropped the ``PolyCollection`` for each violin and left the
    bodies untagged, which is a *worse* failure than the doubling -- the
    highlight would disappear rather than land on a neighbour. The bodies now
    come from extraction, so both survive a second render.
    """
    from maidr.core.plot.violin_kde_plot import ViolinKdePlot

    fig = _violin()
    kde = [plot for plot in _plots(fig) if isinstance(plot, ViolinKdePlot)]
    assert kde, "no KDE layer was registered"

    plot = kde[0]
    plot.render()
    first = list(plot.elements)
    plot.render()

    # Two violins: a body and a curve each.
    assert len(first) == 4
    assert list(plot.elements) == first
    assert all(poly in plot.elements for poly in plot._poly_collections)
