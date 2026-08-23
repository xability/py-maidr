"""
Every ``seaborn.objects`` mark registered nothing at all (#615).

`seaborn.objects` is seaborn's declarative interface, and py-maidr read none
of it. Not one plot type missing -- the whole front door. Measured before the
fix, each row one `.add()`::

    so.Plot(frame, x=, y=).add(so.Dot())    NOTHING REGISTERED
                          .add(so.Line())   NOTHING REGISTERED
                          .add(so.Bar())    NOTHING REGISTERED
    sns.scatterplot(...)                    ['point']
    sns.lineplot(...)                       ['line']
    sns.barplot(...)                        ['bar']

The same charts, written the way seaborn now teaches, going silent.

`maidr/patch/` wraps the *user-facing* drawing calls -- `Axes.scatter`,
`Axes.plot`, `Axes.bar`. A `Mark` calls none of them; it draws through the
artist API (`ax.add_collection`, `ax.add_line`, `ax.add_patch`), so nothing
was there to fire.

`Plotter._plot_layer` runs once per `.add()` and draws that layer across
every panel, which makes it the one place where "which artists belong to
which layer" is still answerable. Taking each axes' artists before and after
answers it without predicting how many a mark makes -- `so.Line(color=)`
draws one `Line2D` per level, and a faceted layer draws on some panels and
not others.

Three marks needed no new extraction: `ScatterPlot` already takes a
collection, `LinePlot` a list of lines, and `BarPlot` a container.
"""

from __future__ import annotations

import re

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
    # Values chosen so no two are equal and none is a position: a reading
    # that paired a magnitude with the wrong category is then visible rather
    # than hidden behind a coincidence.
    return pd.DataFrame(
        {
            "cat": ["a", "b", "c"],
            "val": [4.0, 9.0, 2.0],
            "t": [1.0, 2.0, 3.0],
            "m": [10.0, 30.0, 20.0],
            "g": ["p", "p", "q"],
        }
    )


def _drawn(build) -> plt.Figure:
    """Draw a ``so.Plot`` onto a figure the caller can hand to maidr."""
    figure = plt.figure()
    build(figure)
    return figure


def _layers(figure) -> list[tuple[str, dict]]:
    """Every layer as ``(type, schema)``, after a real render."""
    maidr.render(figure)._repr_html_()
    return [
        (plot.type.value, plot.schema) for plot in FigureManager.get_maidr(figure).plots
    ]


def _kinds(figure) -> list[str]:
    return [kind for kind, _ in _layers(figure)]


def _registers_nothing(figure) -> bool:
    """Whether the figure reaches maidr as no chart at all.

    Asked of the ``FigureManager`` rather than of ``render``, because
    ``render`` no longer raises for an unsupported figure -- it warns and
    emits a static image instead (#443), which is a fallback rather than an
    answer to this question.
    """
    from maidr.exception.unsupported_plot_error import UnsupportedPlotError

    try:
        return not FigureManager.get_maidr(figure).plots
    except UnsupportedPlotError:
        return True


def test_a_dot_mark_reads_as_the_scatter_it_draws():
    """The chart the seaborn tutorial opens with."""
    figure = _drawn(
        lambda fig: so.Plot(_frame(), x="t", y="m").add(so.Dot()).on(fig).plot()
    )
    kind, schema = _layers(figure)[0]

    assert kind == "point"
    assert [(point["x"], point["y"]) for point in schema["data"]] == [
        (1.0, 10.0),
        (2.0, 30.0),
        (3.0, 20.0),
    ]


def test_a_dots_mark_reads_the_same_way():
    """`so.Dots` is the many-points spelling and draws the same artist."""
    figure = _drawn(
        lambda fig: so.Plot(_frame(), x="t", y="m").add(so.Dots()).on(fig).plot()
    )

    assert _kinds(figure) == ["point"]


def test_a_line_mark_reads_as_one_series():
    """A `Line2D` per group, and one group here."""
    figure = _drawn(
        lambda fig: so.Plot(_frame(), x="t", y="m").add(so.Line()).on(fig).plot()
    )
    kind, schema = _layers(figure)[0]

    assert kind == "line"
    assert [(point["x"], point["y"]) for point in schema["data"][0]] == [
        (1.0, 10.0),
        (2.0, 30.0),
        (3.0, 20.0),
    ]


def test_a_path_mark_reads_as_a_line_too():
    """`so.Path` is `so.Line` without the sort, and draws the same artist."""
    figure = _drawn(
        lambda fig: so.Plot(_frame(), x="t", y="m").add(so.Path()).on(fig).plot()
    )

    assert _kinds(figure) == ["line"]


def test_a_bar_mark_reads_its_categories_and_magnitudes():
    figure = _drawn(
        lambda fig: so.Plot(_frame(), x="cat", y="val").add(so.Bar()).on(fig).plot()
    )
    kind, schema = _layers(figure)[0]

    assert kind == "bar"
    assert schema["orientation"] == "vert"
    assert [(bar["x"], bar["y"]) for bar in schema["data"]] == [
        ("a", 4.0),
        ("b", 9.0),
        ("c", 2.0),
    ]


def test_a_bar_drawn_the_other_way_round_says_so():
    """`x=` the magnitude and `y=` the category is a horizontal bar.

    The orientation comes off the `BarContainer` seaborn builds, which is
    also where `Axes.barh` leaves it -- so the two spellings of a horizontal
    bar reach the reader identically, magnitude on x and label on y.
    """
    figure = _drawn(
        lambda fig: so.Plot(_frame(), y="cat", x="val").add(so.Bar()).on(fig).plot()
    )
    _, schema = _layers(figure)[0]

    assert schema["orientation"] == "horz"
    assert [(bar["x"], bar["y"]) for bar in schema["data"]] == [
        (4.0, "a"),
        (9.0, "b"),
        (2.0, "c"),
    ]


def test_a_binned_bar_reads_the_bins_the_stat_made():
    """`so.Hist()` bins before the mark draws, so what is read is the counts.

    The point of asking: the layer's own `data` frame still holds the raw
    rows at this stage, so a reading taken from seaborn's frame rather than
    from the artists would announce three observations where three bins were
    drawn.
    """
    figure = _drawn(
        lambda fig: so.Plot(_frame(), x="m")
        .add(so.Bar(), so.Hist(bins=3))
        .on(fig)
        .plot()
    )
    _, schema = _layers(figure)[0]

    assert [bar["y"] for bar in schema["data"]] == [1.0, 1.0, 1.0]


def test_two_marks_read_as_two_layers_in_the_order_they_were_added():
    figure = _drawn(
        lambda fig: so.Plot(_frame(), x="t", y="m")
        .add(so.Dot())
        .add(so.Line())
        .on(fig)
        .plot()
    )

    assert _kinds(figure) == ["point", "line"]


def test_a_colour_split_line_is_one_layer_of_several_series():
    """`color=` draws one `Line2D` per level.

    All of them belong to the one `.add()`, so they are one layer with a
    series each -- not a layer apiece, which would announce a single mark as
    two charts.
    """
    figure = _drawn(
        lambda fig: so.Plot(_frame(), x="t", y="m", color="g")
        .add(so.Line())
        .on(fig)
        .plot()
    )
    kind, schema = _layers(figure)[0]

    assert kind == "line"
    assert [len(series) for series in schema["data"]] == [2, 1]


def test_each_facet_panel_reads_its_own_rows():
    """One layer per panel, holding that panel's data and no other's."""
    figure = _drawn(
        lambda fig: so.Plot(_frame(), x="t", y="m")
        .facet(col="g")
        .add(so.Dot())
        .on(fig)
        .plot()
    )
    layers = _layers(figure)

    assert [kind for kind, _ in layers] == ["point", "point"]
    assert [[point["x"] for point in schema["data"]] for _, schema in layers] == [
        [1.0, 2.0],
        [3.0],
    ]


def test_a_panel_the_layer_never_drew_on_registers_nothing():
    """A `col`/`row` grid allocates a panel per combination whether the data
    holds one or not.

    Registering the empty ones would offer the reader a layer to walk into
    and find nothing in -- the phantom-layer shape of #421. Here `p` has no
    `y` row and `q` no `x` row, so two of the four panels are empty.
    """
    frame = _frame().assign(row=["x", "x", "y"])
    figure = _drawn(
        lambda fig: so.Plot(frame, x="t", y="m")
        .facet(col="g", row="row")
        .add(so.Dot())
        .on(fig)
        .plot()
    )

    assert len(_layers(figure)) == 2


@pytest.mark.parametrize(
    "mark",
    [
        pytest.param(so.Area(), id="Area"),
        pytest.param(so.Bars(), id="Bars"),
        pytest.param(so.Lines(), id="Lines"),
        pytest.param(so.Paths(), id="Paths"),
        pytest.param(so.Dash(), id="Dash"),
        pytest.param(so.Text(), id="Text"),
    ],
)
def test_a_mark_this_does_not_read_still_registers_nothing(mark):
    """The additive guarantee, asserted rather than assumed.

    Each of these registered nothing before and must register nothing now: a
    mark whose artists no existing plot class can read is left alone, not
    guessed at. `Dash` and `Paths` matter most -- see the test below.
    """
    figure = _drawn(
        lambda fig: so.Plot(_frame(), x="t", y="m").add(mark).on(fig).plot()
    )

    assert _registers_nothing(figure)


def test_the_marks_are_matched_by_name_and_not_by_ancestry():
    """seaborn's mark hierarchy does not track what a mark draws::

        Line  < Path  < Mark      Line2D
        Dash  < Paths < Mark      LineCollection
        Range < Paths < Mark      LineCollection

    So dispatching on ancestry would claim `Dash` and `Range` as lines and
    read a `LineCollection` through `LinePlot`, which cannot see it. This
    pins the hierarchy itself, so the seaborn release that changes it fails
    here rather than silently widening what gets claimed.
    """
    assert issubclass(so.Line, so.Path)
    assert issubclass(so.Dash, so.Paths)
    assert issubclass(so.Range, so.Paths)

    figure = _drawn(
        lambda fig: so.Plot(_frame(), x="t", ymin="val", ymax="m")
        .add(so.Range())
        .on(fig)
        .plot()
    )

    assert _registers_nothing(figure)


def test_a_mark_that_is_read_still_reads_beside_one_that_is_not():
    """An unclaimed layer must not take the chart down with it.

    That is the whole-chart-to-a-picture failure of xability/r-maidr#225,
    from the side where declining is the right answer: the `Area` is not
    read, and the `Dot` beside it is unaffected.
    """
    figure = _drawn(
        lambda fig: so.Plot(_frame(), x="t", y="m")
        .add(so.Dot())
        .add(so.Area())
        .on(fig)
        .plot()
    )

    assert _kinds(figure) == ["point"]


def test_a_plot_drawn_onto_an_existing_chart_reads_only_its_own_marks():
    """`so.Plot.on()` takes a figure that may already hold a chart.

    The before-and-after diff is what keeps the two apart: the scatter drawn
    by `Axes.scatter` registered itself, and the `so.Dot` layer must describe
    the collection *it* drew rather than both.
    """
    figure = plt.figure()
    axes = figure.subplots()
    axes.scatter([0.0, 1.0], [5.0, 6.0])
    so.Plot(_frame(), x="t", y="m").add(so.Dot()).on(axes).plot()

    layers = _layers(figure)

    assert [kind for kind, _ in layers] == ["point", "point"]
    assert [len(schema["data"]) for _, schema in layers] == [2, 3]


def test_the_axis_labels_are_the_ones_the_plot_was_given():
    figure = _drawn(
        lambda fig: so.Plot(_frame(), x="t", y="m")
        .label(x="Time", y="Mass")
        .add(so.Dot())
        .on(fig)
        .plot()
    )
    _, schema = _layers(figure)[0]

    assert schema["axes"]["x"]["label"] == "Time"
    assert schema["axes"]["y"]["label"] == "Mass"


@pytest.mark.parametrize(
    "mark, x, y",
    [
        pytest.param(so.Dot(), "t", "m", id="Dot"),
        pytest.param(so.Line(), "t", "m", id="Line"),
        pytest.param(so.Bar(), "cat", "val", id="Bar"),
    ],
)
def test_every_selector_resolves_in_the_page_it_was_built_from(mark, x, y):
    """A layer that announces correctly and outlines nothing is the blind
    spot xability/maidr#814 names.

    Asserted against the emitted HTML rather than against a written-down
    shape, because the ids are generated per render.
    """
    figure = _drawn(lambda fig: so.Plot(_frame(), x=x, y=y).add(mark).on(fig).plot())
    html = maidr.render(figure)._repr_html_()
    schema = FigureManager.get_maidr(figure).plots[0].schema

    selectors = schema.get("selectors") or schema.get("selector")
    flat = selectors if isinstance(selectors, list) else [selectors]
    assert flat

    for selector in flat:
        found = re.findall(r"'([^']+)'", str(selector))
        assert found, selector
        for identifier in found:
            assert identifier in html


# --------------------------------------------------------------------------
# The two guards below are each unobservable through a chart *while the other
# holds*, and that is why they are asked of the helpers directly.
#
# `_reading_for` declines a mark that is not in the table; `_held` keeps only
# the artist class that reading reads. Every unread mark measured draws into a
# holder no reading reads, or draws a class the filter removes -- so dropping
# either one alone changes nothing any chart can show. Dropping *both* reads a
# `so.Dash`'s `LineCollection` through `ScatterPlot`, which cannot see it,
# silently falls back to sweeping the whole axes, and announces a neighbouring
# layer's points as this one's.
#
# Measured, mutating the live code one change at a time against the tests
# above: claiming every mark, and removing the class filter, each left all 24
# green. Both are pinned here so that removing either is a failing test rather
# than a silent widening.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mark",
    [
        pytest.param(so.Area(), id="Area"),
        pytest.param(so.Bars(), id="Bars"),
        pytest.param(so.Dash(), id="Dash"),
        pytest.param(so.Range(), id="Range"),
        pytest.param(so.Text(), id="Text"),
    ],
)
def test_a_mark_outside_the_table_is_declined_rather_than_defaulted(mark):
    """The lookup returns nothing for a mark it does not name."""
    from maidr.patch.seaborn_objects import _reading_for

    assert _reading_for({"mark": mark}) is None


def test_a_reading_takes_only_its_own_artist_class_from_a_holder():
    """``Axes.collections`` and ``Axes.containers`` are heterogeneous.

    A holder can carry several artist classes at once, and handing the wrong
    one over is not an error anywhere downstream: ``ScatterPlot`` filters what
    it is given to ``PathCollection`` and, finding none, sweeps the axes
    instead -- so the layer would describe every point on the panel rather
    than raise.
    """
    from matplotlib.collections import LineCollection

    from maidr.patch.seaborn_objects import _READINGS, _held

    _, axes = plt.subplots()
    points = axes.scatter([0.0, 1.0], [0.0, 1.0])
    axes.add_collection(LineCollection([[(0.0, 0.0), (1.0, 1.0)]]))
    bars = axes.bar(["a"], [1.0])
    axes.errorbar([0.0], [0.0], yerr=[0.5])

    assert _held(axes, _READINGS["Dot"]) == [points]
    assert _held(axes, _READINGS["Bar"]) == [bars]


def test_the_hook_still_takes_the_layer_as_its_second_argument():
    """`_plot_layer(p, layer)` is a private method of a private module.

    Nothing else in this file would notice a seaborn release that reordered
    those two: the layer would read as `None`, `_reading_for` would decline
    it, and every chart would go back to registering nothing -- silently,
    because that is also what a mark outside the table does. Pinned so the
    failure is one loud test rather than a whole interface quietly going dark
    again.
    """
    import inspect

    from seaborn._core.plot import Plotter

    assert list(inspect.signature(Plotter._plot_layer).parameters) == [
        "self",
        "p",
        "layer",
    ]


def test_a_seaborn_that_moved_the_hook_warns_rather_than_failing_the_import(
    monkeypatch,
):
    """The branch the "guarded, unlike the other seaborn patches" argument
    rests on, verified rather than reasoned about.

    `maidr/patch/_seaborn_version.py` turns a missing
    `_CategoricalPlotter.plot_bars` into a readable `ImportError`, because
    there is a version floor to state. There is none to state for a
    private-of-private method, so this path must leave `import maidr`
    working -- a rename here would otherwise break every *classic* seaborn
    chart over a mark nobody in that process drew.
    """
    import seaborn._core.plot as plot_module

    from maidr.patch import seaborn_objects

    class Moved:
        """A Plotter that no longer has the method."""

    monkeypatch.setattr(plot_module, "Plotter", Moved)

    with pytest.warns(UserWarning, match=r"_plot_layer"):
        seaborn_objects._wrap()

    assert not hasattr(Moved, "_plot_layer")


@pytest.mark.parametrize(
    "spelling, build",
    [
        pytest.param("plain", lambda plot: plot.add(so.Bar()), id="plain"),
        pytest.param(
            "dodged", lambda plot: plot.add(so.Bar(), so.Dodge()), id="dodged"
        ),
        pytest.param(
            "stacked", lambda plot: plot.add(so.Bar(), so.Stack()), id="stacked"
        ),
    ],
)
def test_a_colour_split_bar_draws_one_container_and_reads_as_one_layer(spelling, build):
    """`DRAWN_BARS` names a single container, so a reading that found several
    would become several layers.

    Measured rather than claimed: every `so.Bar` spelling draws exactly one
    `BarContainer` holding every bar, `color=` and `Dodge()` and `Stack()`
    included -- unlike the classic `seaborn.barplot`, which draws one
    container per hue level. So the branch is real but unreached, and this
    says which of the two is true today.

    What a stacked bar should be *read* as is a separate question and not
    settled here: it reads as a plain `bar` of every segment, which is the
    same shape #615 lists as follow-up work.
    """
    figure = plt.figure()
    build(so.Plot(_frame(), x="cat", y="val", color="g")).on(figure).plot()

    assert len(figure.axes[0].containers) == 1
    assert _kinds(figure) == ["bar"]


@pytest.mark.parametrize(
    "mark, expected",
    [
        pytest.param(so.Dot(), "point", id="Dot"),
        pytest.param(so.Line(), "line", id="Line"),
        pytest.param(so.Bar(), "bar", id="Bar"),
    ],
)
def test_every_mark_reads_one_layer_per_panel_when_faceted(mark, expected):
    """The panel diff is shared, but what each mark draws into it is not.

    `Line` draws one `Line2D` per group and `Bar` one container per panel, so
    a facet case for each is not a repeat of the `Dot` one: it is the only
    place the three handovers meet the per-panel branch.
    """
    frame = _frame()
    figure = _drawn(
        lambda fig: so.Plot(frame, x="t", y="m").facet(col="g").add(mark).on(fig).plot()
    )

    assert _kinds(figure) == [expected, expected]


def test_a_layer_that_drew_several_containers_becomes_several_bar_layers():
    """The ``singular=True`` branch, which no ``so.Bar`` spelling reaches.

    `DRAWN_BARS` names one container, so a layer that drew several has to
    become several layers rather than one truncated to the first -- which is
    also how a hue-grouped bar is read elsewhere (#593, #595), one layer per
    group. Every `so.Bar` measured draws exactly one container, so the branch
    is forward-looking: it would be exercised for the first time, silently,
    by a seaborn release that changed that.

    Asked of `_handovers` directly, because that is the function deciding it
    and no chart can put two containers in front of it today.
    """
    from maidr.core.plot.barplot import DRAWN_BARS
    from maidr.patch.seaborn_objects import _READINGS, _handovers

    _, axes = plt.subplots()
    first = axes.bar(["a"], [4.0])
    second = axes.bar(["b"], [9.0])

    assert _handovers(_READINGS["Bar"], axes, [first, second]) == [
        {DRAWN_BARS: first},
        {DRAWN_BARS: second},
    ]
