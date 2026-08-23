"""A plotly funnelarea chart produced a figure with no layers at all.

`go.Funnelarea` is a funnel drawn as nested trapezoids rather than as bars.
`maidr/plotly/` had no handling for it, so the trace fell through
`_extract_plots` to `PlotlyPlotFactory`, which returned `None` and left the
figure with nothing to navigate (#627).

It is *stated* the way a pie is -- `labels` and `values`, placed by a
`domain` rectangle rather than by an axis pair -- so it inherits the pie's
slice builder rather than growing a second copy that could drift from it.
Every rule was measured against `gd.calcdata` in Chromium and matched:

===========================  ===============================================
written                      drawn
===========================  ===============================================
`labels=[a, b, a]`           two slices; `a` holds the sum, at its first
                             position
`values=[10, 0, 5]`          three slices; the zero is kept
`values=[10, -5, 5]`         two slices; the negative is dropped
no `values`                  every entry weighs 1
no `labels`                  slices named `0`, `1`, `2`
an empty label               the entry's own index
`layout.hiddenlabels`        the named slice is not drawn
===========================  ===============================================

With exactly one exception, which is the whole reason the two cannot be one
class: a funnelarea has no `sort` attribute and never reorders.
`values=[40, 100, 60]` stayed in that order, where a pie draws 100, 60, 40.

That is not a detail. A funnel's axis *is* its sequence, so reusing the pie's
sorting default would reorder the stages of a funnel by size and announce a
conversion path nobody drew.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
plotly = pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

STAGES = ["visited", "signed up", "paid"]
COUNTS = [100, 60, 40]


def _layers(figure: go.Figure) -> list[dict]:
    """Every emitted layer of a figure, flattened across its subplot grid."""
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell.get("layers", [])]


def _pairs(layer: dict) -> list[tuple]:
    """Each slice as ``(label, value)``, in the order it is emitted."""
    return [(point["x"], point["y"]) for point in layer["data"]]


def test_a_funnelarea_chart_is_read_at_all() -> None:
    """The reproduction: a whole chart that announced nothing."""
    layers = _layers(go.Figure([go.Funnelarea(labels=STAGES, values=COUNTS)]))

    assert [layer["type"] for layer in layers] == [PlotType.FUNNEL]


def test_a_funnelarea_is_read_as_the_funnel_it_draws() -> None:
    """Not as a pie, which is what it is written like.

    `FunnelTrace` pitches the retention between adjacent stages, which is the
    number this chart exists to show. A pie layer has no notion of it: it
    would announce each slice's share of the whole, which is a different
    question and one the trapezoids are not drawn to answer.
    """
    (layer,) = _layers(go.Figure([go.Funnelarea(labels=STAGES, values=COUNTS)]))

    assert layer["type"] == PlotType.FUNNEL
    assert _pairs(layer) == list(zip(STAGES, COUNTS))


def test_a_funnelarea_keeps_the_stages_in_the_order_written() -> None:
    """The one rule a funnelarea does not share with a pie.

    Measured: `values=[40, 100, 60]` drew in that order, and
    `gd._fullData[0].sort` is undefined -- the attribute does not exist on
    the trace. A pie with the same numbers draws 100, 60, 40.
    """
    (layer,) = _layers(
        go.Figure([go.Funnelarea(labels=["a", "b", "c"], values=[40, 100, 60])])
    )

    assert _pairs(layer) == [("a", 40), ("b", 100), ("c", 60)]


def test_a_pie_beside_it_still_sorts() -> None:
    """The control for the rule above: the hook must not change the pie.

    Both layers come out of one slice builder, so a flag applied to the wrong
    side would reorder every pie in the world and pass a funnelarea-only
    test.
    """
    pie, funnelarea = _layers(
        go.Figure(
            [
                go.Pie(labels=["a", "b", "c"], values=[40, 100, 60]),
                go.Funnelarea(labels=["a", "b", "c"], values=[40, 100, 60]),
            ]
        )
    )

    assert _pairs(pie) == [("b", 100), ("c", 60), ("a", 40)]
    assert _pairs(funnelarea) == [("a", 40), ("b", 100), ("c", 60)]


@pytest.mark.parametrize(
    ("trace", "expected"),
    [
        (go.Funnelarea(labels=["a", "b", "a"], values=[10, 5, 7]), [("a", 17), ("b", 5)]),
        (go.Funnelarea(labels=["a", "b", "c"], values=[10, 0, 5]),
         [("a", 10), ("b", 0), ("c", 5)]),
        (go.Funnelarea(labels=["a", "b", "c"], values=[10, -5, 5]),
         [("a", 10), ("c", 5)]),
        (go.Funnelarea(labels=["a", "b", "c"]), [("a", 1), ("b", 1), ("c", 1)]),
        (go.Funnelarea(values=[10, 5, 2]), [("0", 10), ("1", 5), ("2", 2)]),
        (go.Funnelarea(labels=["", "b"], values=[10, 5]), [("0", 10), ("b", 5)]),
    ],
)
def test_the_slice_rules_are_the_pies(trace: go.Funnelarea, expected: list) -> None:
    """Each row measured against ``gd.calcdata`` in Chromium.

    These are the rules the inheritance is *for*. A second copy of them would
    be a second thing to keep in step with plotly, and the pie's own
    docstring already records why that matters: the selector is positional,
    so the first divergence lands every later slice on another wedge.
    """
    (layer,) = _layers(go.Figure([trace]))

    assert _pairs(layer) == expected


def test_a_hidden_label_is_not_emitted() -> None:
    """`layout.hiddenlabels` applies here too.

    Measured: with `hiddenlabels=["b"]` the funnelarea drew 2 slices of 3.
    Emitting the hidden one would slide every later slice onto the wrong
    trapezoid.
    """
    figure = go.Figure([go.Funnelarea(labels=["a", "b", "c"], values=[10, 5, 2])])
    figure.update_layout(hiddenlabels=["b"])

    (layer,) = _layers(figure)

    assert _pairs(layer) == [("a", 10), ("c", 2)]


def test_the_selector_is_scoped_to_the_funnelarea_layer() -> None:
    """Plotly draws it into its own figure-level layer, not the pie's.

    Measured on a figure holding one of each: `.pielayer .trace .slice
    path.surface` matched the pie's 2 slices and `.funnelarealayer ...` the
    funnelarea's 3, with neither reaching the other.
    """
    (layer,) = _layers(go.Figure([go.Funnelarea(labels=STAGES, values=COUNTS)]))

    assert ".funnelarealayer" in layer["selectors"]
    assert ".pielayer" not in layer["selectors"]


def test_two_funnelareas_address_their_own_slices() -> None:
    """The position stands in for a subplot prefix.

    Both layers sit directly under `main-svg` rather than inside a
    `.subplot.xy` group. Measured on two funnelareas: `> .trace:nth-child(1)`
    resolved to 3 slices and `nth-child(2)` to 2, against 5 for the
    unpositioned form.
    """
    first, second = _layers(
        go.Figure(
            [
                go.Funnelarea(labels=STAGES, values=COUNTS, domain={"x": [0, 0.45]}),
                go.Funnelarea(labels=["m", "n"], values=[9, 4], domain={"x": [0.55, 1]}),
            ]
        )
    )

    assert "nth-child(1)" in first["selectors"]
    assert "nth-child(2)" in second["selectors"]


def test_a_pie_does_not_shift_a_funnelareas_position() -> None:
    """The two layers are siblings, so they number independently.

    Measured on a figure holding one of each: each layer held exactly its own
    trace at `nth-child(1)`.
    """
    layers = _layers(
        go.Figure(
            [
                go.Pie(labels=["p", "q"], values=[1, 2], domain={"x": [0, 0.45]}),
                go.Funnelarea(labels=STAGES, values=COUNTS, domain={"x": [0.55, 1]}),
            ]
        )
    )
    (funnelarea,) = [layer for layer in layers if layer["type"] == PlotType.FUNNEL]
    (pie,) = [layer for layer in layers if layer["type"] == PlotType.PIE]

    assert "nth-child(1)" in funnelarea["selectors"]
    assert "nth-child(1)" in pie["selectors"]


def test_the_stages_are_named_as_stages() -> None:
    """The generic fallback pair, said in this chart's own words.

    A funnelarea draws no axes, so an author who wants them named says so
    through the layout's axis titles. "Category" and "Value" would be true of
    a pie and vague here; a funnel's two dimensions are its stages and their
    counts.
    """
    (layer,) = _layers(go.Figure([go.Funnelarea(labels=STAGES, values=COUNTS)]))

    assert layer["axes"]["x"]["label"] == "Stage"
    assert layer["axes"]["y"]["label"] == "Count"


def test_a_pie_keeps_its_own_fallback_pair() -> None:
    """The control: the fallbacks are per class, not swapped globally."""
    (layer,) = _layers(go.Figure([go.Pie(labels=["a", "b"], values=[1, 2])]))

    assert layer["axes"]["x"]["label"] == "Category"
    assert layer["axes"]["y"]["label"] == "Value"


def test_a_funnelarea_says_which_field_holds_the_stage() -> None:
    """`FunnelTrace` reads the stage off `point.x` when the layer is vertical.

    A funnelarea has no axes to be drawn along, so there is no second
    arrangement for it to be in -- but the payload says what it holds rather
    than leaving it to the default, which is what xability/maidr#947 asks of
    a producer.
    """
    (layer,) = _layers(go.Figure([go.Funnelarea(labels=STAGES, values=COUNTS)]))

    assert layer["orientation"] == "vert"
