"""
A horizontal plotly bar chart was silent and announced inside out (#480).

`go.Bar(y=cats, x=vals, orientation="h")` emits its points in the horizontal
arrangement -- the measure in ``x``, which is what the core wants -- but never
emitted the ``orientation`` key that says to read them that way. The core
defaults a missing orientation to vertical and then takes ``point.y`` as the
magnitude, which on these layers is the category name. Measured against a real
``BarTrace``, that gives ``freq.raw = null``: no magnitude to pitch, so every
bar sounded nothing, and the announcement offered ``30`` as the point's
identity and ``"apple"`` as its value.

`PlotlyHistogramPlot` already carried the same override for the same reason,
and its trace extends this one in the core, so the pattern was in the file next
door the whole time.

These assert on the emitted schema. The arrangement of the data was never
wrong -- ``paired_axes`` is symmetric and hands back the horizontal pairing
correctly -- so what has to be pinned is the declaration, and that it agrees
with the arrangement.
"""

from __future__ import annotations

import warnings

import plotly.graph_objects as go
import pytest

from maidr.core.enum.maidr_key import MaidrKey
from maidr.plotly.plotly_maidr import PlotlyMaidr

warnings.filterwarnings("ignore")

CATS = ["apple", "banana", "cherry"]
VALUES = [30, 70, 50]
SECOND = [20, 40, 35]


def _layer(fig) -> dict:
    """The first emitted layer of a figure, keyed by raw strings."""
    schema = PlotlyMaidr(fig)._flatten_maidr()
    layer = schema["subplots"][0][0]["layers"][0]
    return {str(getattr(key, "value", key)): value for key, value in layer.items()}


def _first_point(layer: dict) -> dict:
    points = layer["data"]
    if points and isinstance(points[0], list):
        points = points[0]
    return {str(getattr(key, "value", key)): value for key, value in points[0].items()}


def _bar(horizontal: bool):
    if horizontal:
        return go.Figure(go.Bar(y=CATS, x=VALUES, orientation="h"))
    return go.Figure(go.Bar(x=CATS, y=VALUES))


def _grouped(horizontal: bool, barmode: str, barnorm: str | None = None):
    if horizontal:
        traces = [
            go.Bar(y=CATS, x=VALUES, orientation="h", name="u"),
            go.Bar(y=CATS, x=SECOND, orientation="h", name="v"),
        ]
    else:
        traces = [
            go.Bar(x=CATS, y=VALUES, name="u"),
            go.Bar(x=CATS, y=SECOND, name="v"),
        ]
    fig = go.Figure(traces)
    if barnorm is None:
        fig.update_layout(barmode=barmode)
    else:
        fig.update_layout(barmode=barmode, barnorm=barnorm)
    return fig


CHARTS = {
    "bar": _bar,
    "stacked": lambda h: _grouped(h, "stack"),
    "dodged": lambda h: _grouped(h, "group"),
    # One class serves all three grouped types, so the 100% stacked bar rides
    # on the same override -- pinned rather than assumed.
    "normalized": lambda h: _grouped(h, "stack", barnorm="percent"),
}


@pytest.mark.parametrize("name", sorted(CHARTS))
class TestTheLayerSaysWhichWayRoundItIs:
    def test_a_horizontal_chart_declares_horz(self, name) -> None:
        # The key was absent entirely, which the core reads as vertical.
        layer = _layer(CHARTS[name](True))

        assert layer.get(str(MaidrKey.ORIENTATION.value)) == "horz"

    def test_a_vertical_chart_declares_vert(self, name) -> None:
        layer = _layer(CHARTS[name](False))

        assert layer.get(str(MaidrKey.ORIENTATION.value)) == "vert"

    def test_the_declaration_matches_the_arrangement(self, name) -> None:
        # The pairing is the whole contract: `horz` means the magnitude is in
        # `x`. A declaration that disagreed with the payload would be the same
        # silent chart, reached from the other side -- which is what
        # xability/r-maidr#184 was.
        #
        # By kind rather than by value, because a `barnorm` layer's magnitudes
        # are shares of its column rather than the numbers passed in. What has
        # to hold for every one of these is which field carries a number and
        # which carries the category name.
        horizontal = _first_point(_layer(CHARTS[name](True)))
        vertical = _first_point(_layer(CHARTS[name](False)))

        assert isinstance(horizontal["x"], (int, float))
        assert horizontal["y"] == "apple"
        assert vertical["x"] == "apple"
        assert isinstance(vertical["y"], (int, float))


class TestTheNeighboursAreUnchanged:
    def test_a_histogram_still_declares_its_orientation(self) -> None:
        # It always did; this is the case the fix was copied from, pinned so
        # the two cannot drift apart.
        for fig, expected in (
            (go.Figure(go.Histogram(y=[1, 2, 2, 3])), "horz"),
            (go.Figure(go.Histogram(x=[1, 2, 2, 3])), "vert"),
        ):
            assert _layer(fig).get(str(MaidrKey.ORIENTATION.value)) == expected

    def test_a_box_still_declares_its_orientation(self) -> None:
        layer = _layer(go.Figure(go.Box(x=[1, 2, 2, 3, 4])))

        assert layer.get(str(MaidrKey.ORIENTATION.value)) is not None
