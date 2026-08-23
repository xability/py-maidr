"""A plotly gauge produced a figure with no layers at all.

`go.Indicator` is plotly's gauge and bullet chart, and `maidr/plotly/` had
no handling for it: the trace fell through `_extract_plots` to
`PlotlyPlotFactory`, which returned `None` (#627). The core has drawn gauges
since xability/maidr#827.

A gauge is one measure against a dial, so its payload is a single
`GaugePoint` rather than a list of them -- the one plot type here whose
`data` is an object.

Three things separate an indicator this can read from one it cannot, and
all three were measured against `gd._fullData[0]` in Chromium:

  * `mode="number"` draws no dial at all. A `GaugePoint` needs a range to
    place its measure in, and a bare number is not a chart to navigate.
  * a gauge with no explicit `axis.range` still gets one, computed from the
    value: `[0, 1.5 * value]`, with `value = 0` a special case at `[-1, 1]`.
    Measured across 42 -> [0, 63], 100 -> [0, 150], 7 -> [0, 10.5],
    3.5 -> [0, 5.25], 0 -> [-1, 1].
  * that rule runs backwards for a negative value: -20 -> `[0, -30]`, a
    dial whose upper end is below its lower one. `GaugePoint` names its two
    ends "lower" and "upper", so that pair is outside what the grammar
    describes.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
plotly = pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402


def _layers(figure: go.Figure) -> list[dict]:
    """Every emitted layer of a figure, flattened across its subplot grid."""
    grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
    return [layer for row in grid for cell in row for layer in cell.get("layers", [])]


def _gauge(**kwargs: object) -> go.Figure:
    """A figure holding one indicator."""
    return go.Figure([go.Indicator(**kwargs)])


def test_a_gauge_is_read_at_all() -> None:
    """The reproduction: a whole chart that announced nothing."""
    layers = _layers(
        _gauge(mode="gauge+number", value=42, gauge={"axis": {"range": [0, 100]}})
    )

    assert [layer["type"] for layer in layers] == [PlotType.GAUGE]


def test_a_gauge_carries_its_measure_and_its_dial() -> None:
    """One point, not a list of them -- a gauge states a single measure."""
    (layer,) = _layers(
        _gauge(
            mode="gauge+number",
            value=42,
            gauge={"axis": {"range": [0, 100]}},
            title={"text": "Speed"},
        )
    )

    assert layer["data"] == {"value": 42.0, "min": 0.0, "max": 100.0, "label": "Speed"}


def test_a_threshold_becomes_the_target() -> None:
    """What a bullet chart's marker is.

    The core announces it alongside the measure precisely so "220 against a
    target of 270" is one sentence rather than two navigations. Dropping it
    would leave the marker drawn and unmentioned.
    """
    (layer,) = _layers(
        _gauge(
            mode="gauge+number",
            value=220,
            gauge={
                "shape": "bullet",
                "axis": {"range": [0, 300]},
                "threshold": {"value": 270},
            },
        )
    )

    assert layer["data"]["target"] == 270.0


def test_colour_steps_do_not_become_bands() -> None:
    """A `GaugeBand` needs a name and a plotly step has none.

    `bands` exists so a reader hears "in the 'ok' band"; a plotly step is a
    colour over a range with no label at all. Synthesising one would
    announce a name the chart does not carry, and the reader would have no
    way to know the word was ours.
    """
    (layer,) = _layers(
        _gauge(
            mode="gauge+number",
            value=220,
            gauge={
                "axis": {"range": [0, 300]},
                "steps": [
                    {"range": [0, 150], "color": "lightgray"},
                    {"range": [150, 250], "color": "gray"},
                ],
            },
        )
    )

    assert "bands" not in layer["data"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [(42, (0.0, 63.0)), (100, (0.0, 150.0)), (7, (0.0, 10.5)), (3.5, (0.0, 5.25)),
     (0, (-1.0, 1.0))],
)
def test_an_unstated_range_follows_what_plotly_computes(
    value: float, expected: tuple[float, float]
) -> None:
    """Each row measured against ``gd._fullData[0].gauge.axis.range``.

    `Figure.to_dict()` omits `gauge` entirely when the author set nothing
    inside it, so these traces arrive with no `gauge` key at all -- and they
    draw a full dial. Reading the *mode* rather than the presence of that
    key is what makes them reachable.
    """
    (layer,) = _layers(_gauge(mode="gauge+number", value=value))

    assert (layer["data"]["min"], layer["data"]["max"]) == expected


def test_a_bare_number_is_declined() -> None:
    """`mode="number"` draws no dial, and plotly's default mode is `number`.

    There is no range to place a measure in, so there is no `GaugePoint` to
    build. Emitting one with a range invented for it would announce a dial
    nobody drew.
    """
    assert _layers(_gauge(mode="number", value=7)) == []
    assert _layers(_gauge(value=7)) == []


def test_a_backwards_default_range_is_declined() -> None:
    """Measured: value -20 with no explicit range draws `[0, -30]`.

    `GaugePoint` names its two ends "lower" and "upper", so a pair whose
    upper end is below its lower one is outside what the grammar describes.
    Declined rather than emitted inverted.
    """
    assert _layers(_gauge(mode="gauge+number", value=-20)) == []


def test_a_negative_value_reads_when_the_author_gives_a_range() -> None:
    """The control for the decline above: it is about the *default* rule.

    An author who states the dial has said which end is which, and a
    negative measure on it is an ordinary chart.
    """
    (layer,) = _layers(
        _gauge(mode="gauge+number", value=-20, gauge={"axis": {"range": [-50, 50]}})
    )

    assert (layer["data"]["min"], layer["data"]["max"]) == (-50.0, 50.0)
    assert layer["data"]["value"] == -20.0


def test_the_selector_addresses_the_value_arc() -> None:
    """The mark that moves with the measure.

    Measured in Chromium: the background arc, the outline and the tick
    marks are all frame; `.value-arc` is the one that is drawn to the
    measure.
    """
    (layer,) = _layers(
        _gauge(mode="gauge+number", value=42, gauge={"axis": {"range": [0, 100]}})
    )

    assert layer["selectors"] == ".indicatorlayer > .trace:nth-child(1) .value-arc"


def test_a_bare_number_still_takes_its_place_in_the_layer() -> None:
    """The position counts every indicator, not only the readable ones.

    Plotly appends a `.trace` group for a `mode="number"` indicator too --
    it has a number to draw, just no dial. Numbering only the dial-drawing
    ones put the second gauge of `[gauge, number, gauge]` on
    `nth-child(2)`, which is the bare number's group and holds no arc:
    measured, that selector resolved to **0** elements. The same lesson
    #395 records for boxes and candlesticks sharing a layer.
    """
    figure = go.Figure(
        [
            go.Indicator(
                mode="gauge+number", value=42,
                gauge={"axis": {"range": [0, 100]}}, domain={"x": [0, 0.45]},
            ),
            go.Indicator(mode="number", value=7, domain={"x": [0.5, 0.6]}),
            go.Indicator(
                mode="gauge+number", value=80,
                gauge={"axis": {"range": [0, 100]}}, domain={"x": [0.65, 1]},
            ),
        ]
    )

    first, second = _layers(figure)

    assert "nth-child(1)" in first["selectors"]
    assert "nth-child(3)" in second["selectors"]


def test_a_gauge_names_its_two_dimensions() -> None:
    """An indicator draws no cartesian axes, so the generic pair stands in.

    The core reads `this.xAxis` for what the measure is called and
    `this.yAxis` for the measure itself, and plotly names neither.
    """
    (layer,) = _layers(
        _gauge(mode="gauge+number", value=42, gauge={"axis": {"range": [0, 100]}})
    )

    assert layer["axes"]["x"]["label"] == "Measure"
    assert layer["axes"]["y"]["label"] == "Value"
