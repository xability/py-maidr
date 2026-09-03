"""A plotly funnel chart produced a figure with no layers at all.

`maidr/plotly/` builds its MAIDR schema in Python and had no handling for
`funnel`, so the trace fell through `_extract_plots` to
`PlotlyPlotFactory`, which returned `None`::

    go.Funnel(y=["a", "b", "c"], x=[100, 60, 40])   ->   layers: []

The core has read funnels since `TraceType.FUNNEL` was added, and the bundle
shipped in this wheel names the type, so a funnel written in plotly was
silent only on the Python side (#627).

`FunnelTrace` extends the bar trace: it takes one point per stage and
computes the retention between adjacent stages from `barValues`, which is
the number it pitches. So the payload is a bar's, and the one thing that has
to be right beyond the values is `orientation` -- which decides whether the
core reads the stage name off `point.x` or `point.y`.

Which way plotly draws a funnel is not the question a bar answers. Measured
in Chromium against `gd._fullData[0].orientation`:

===========================  ==========================================
written                      plotly resolves
===========================  ==========================================
`y=stages, x=counts`         `h`
`x=stages, y=counts`         `h`
`x=counts` alone             `h`
`y=counts` alone             `v`
`orientation="v"`            `v`
===========================  ==========================================

So the default is horizontal whenever the trace carries an `x` at all --
the opposite of the vertical default a bar layer takes.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
pytest.importorskip("plotly")

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
    """Each point as ``(x, y)``, in the order it is emitted."""
    return [(point["x"], point["y"]) for point in layer["data"]]


def test_a_funnel_chart_is_read_at_all() -> None:
    """The reproduction: a whole chart that announced nothing.

    Not a crash and not a mislabel -- the figure arrived with an empty layer
    list and MAIDR had nothing to navigate.
    """
    layers = _layers(go.Figure([go.Funnel(y=STAGES, x=COUNTS)]))

    assert [layer["type"] for layer in layers] == [PlotType.FUNNEL]


def test_a_funnel_carries_one_point_per_stage() -> None:
    """The counts and the stage names, in the trace's own order.

    Not sorted. A funnel's axis *is* its sequence -- the chart says "this
    many entered, this many reached the next step" -- so ordering the stages
    by name would order away the thing it is drawn to show.
    """
    (layer,) = _layers(go.Figure([go.Funnel(y=STAGES, x=COUNTS)]))

    assert _pairs(layer) == list(zip(COUNTS, STAGES))


def test_a_horizontal_funnel_says_so() -> None:
    """Without the key the layer defaults to vertical.

    `FunnelTrace` reads the stage name off `point.x` when it is vertical, so
    a horizontal funnel announced as vertical gives the count as the stage's
    identity and the stage name as its value -- the failure #480 was about
    for bars.
    """
    (layer,) = _layers(go.Figure([go.Funnel(y=STAGES, x=COUNTS)]))

    assert layer["orientation"] == "horz"


def test_a_vertical_funnel_says_so_too() -> None:
    """The control for the key above: it must not be constant."""
    (layer,) = _layers(
        go.Figure([go.Funnel(x=STAGES, y=COUNTS, orientation="v")])
    )

    assert layer["orientation"] == "vert"
    assert _pairs(layer) == list(zip(STAGES, COUNTS))


@pytest.mark.parametrize(
    ("trace", "expected"),
    [
        (go.Funnel(y=STAGES, x=COUNTS), "horz"),
        (go.Funnel(x=STAGES, y=COUNTS), "horz"),
        (go.Funnel(x=COUNTS), "horz"),
        (go.Funnel(y=COUNTS), "vert"),
    ],
)
def test_an_unstated_orientation_follows_what_plotly_draws(
    trace: go.Funnel, expected: str
) -> None:
    """Each row measured against ``gd._fullData[0].orientation`` in Chromium.

    The third and fourth rows are what separate this from a bar's rule: a
    funnel written with counts alone is horizontal when they are on ``x``
    and vertical when they are on ``y``, while a bar with no ``orientation``
    is vertical either way.

    The second row is plotly's answer rather than a sensible one -- stage
    names on the value axis draw a chart of nonsense -- but it is what the
    reader is looking at, and announcing the other orientation would
    describe a chart that is not on the screen.
    """
    (layer,) = _layers(go.Figure([trace]))

    assert layer["orientation"] == expected


def test_the_selector_is_scoped_to_the_funnel_layer() -> None:
    """`.trace.bars` is not unique to the bar layer.

    Plotly draws a funnel into its own ``mlayer`` and reuses the same inner
    class names there. Measured in Chromium on a subplot holding a bar trace
    and a funnel, the unscoped ``.trace.bars .point > path`` matched the
    funnel's stages too -- which is the over-match #628 was about, with
    ``funnellayer`` in place of ``waterfalllayer``.
    """
    (layer,) = _layers(go.Figure([go.Funnel(y=STAGES, x=COUNTS)]))

    assert ".funnellayer" in layer["selectors"]


def test_two_funnels_on_one_subplot_address_their_own_stages() -> None:
    """Plotly appends one `.trace.bars` group per trace, in declaration order.

    Measured: ``.funnellayer .trace .point > path`` resolved to 4 on a
    subplot holding a three-stage funnel and a two-stage one -- both traces'
    stages together -- so a layer without the position would claim its
    neighbour's and both highlights would be dropped.
    """
    first, second = _layers(
        go.Figure(
            [
                go.Funnel(y=STAGES, x=COUNTS, name="one"),
                go.Funnel(y=["a", "b"], x=[10, 5], name="two"),
            ]
        )
    )

    assert "nth-of-type(1)" in first["selectors"]
    assert "nth-of-type(2)" in second["selectors"]
    assert len(first["data"]) == 3
    assert len(second["data"]) == 2


def test_a_bar_beside_a_funnel_still_addresses_its_own_bars() -> None:
    """The control that the two layers do not reach into each other.

    Verified in Chromium after this change: the bar's selector resolved to
    its 4 bars and each funnel's to its own stages, on one subplot holding
    all three.
    """
    layers = _layers(
        go.Figure(
            [
                go.Bar(x=["a", "b", "c", "d"], y=[1, 2, 3, 4]),
                go.Funnel(y=STAGES, x=COUNTS),
            ]
        )
    )
    (bar,) = [layer for layer in layers if layer["type"] == PlotType.BAR]

    assert ".barlayer" in bar["selectors"]
    assert ".funnellayer" not in bar["selectors"]
