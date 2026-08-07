"""Classifying a plotly trace that never authored a ``mode``.

``Figure.to_dict()`` omits ``mode`` unless it was set, so the exported dict
cannot be read literally: an absent ``mode`` is not "no drawing mode", it is
"whatever plotly's default resolves to". plotly documents that default on
``scatter.mode`` as "If there are less than 20 points and the trace is not
stacked then the default is 'lines+markers'. Otherwise, 'lines'."

Reading absent-as-markers therefore described a chart plotly draws as a
connected line as scattered points.
"""

from __future__ import annotations

import pytest

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_maidr import PlotlyMaidr
from maidr.plotly.step_shape import default_mode, is_connected_line_trace

plotly = pytest.importorskip("plotly")
import plotly.graph_objects as go  # noqa: E402


def _trace(n: int, **overrides) -> dict:
    """
    Build a mode-less scatter trace dict of ``n`` points.

    Parameters
    ----------
    n : int
        Number of points on both axes.
    **overrides
        Extra trace keys merged in.

    Returns
    -------
    dict
        A scatter trace dict with no ``mode``.
    """
    return {
        "type": "scatter",
        "x": list(range(n)),
        "y": list(range(n)),
        **overrides,
    }


def _layers(fig) -> list[dict]:
    """
    Render a figure through PlotlyMaidr and return its layer schemas.

    Parameters
    ----------
    fig : plotly.graph_objects.Figure
        The figure to export.

    Returns
    -------
    list of dict
        One schema per emitted layer, in emission order.
    """
    return [plot.schema for plot in PlotlyMaidr(fig)._plots]


class TestPlotlysOwnDefault:
    """``default_mode`` must reproduce the rule plotly documents."""

    @pytest.mark.parametrize("n", [0, 1, 5, 19])
    def test_a_short_trace_defaults_to_lines_and_markers(self, n):
        assert default_mode(_trace(n)) == "lines+markers"

    @pytest.mark.parametrize("n", [20, 21, 100])
    def test_a_long_trace_defaults_to_lines(self, n):
        assert default_mode(_trace(n)) == "lines"

    def test_the_boundary_is_exclusive_at_twenty(self):
        # "less than 20 points" -- 19 keeps markers, 20 drops them.
        assert default_mode(_trace(19)) == "lines+markers"
        assert default_mode(_trace(20)) == "lines"

    @pytest.mark.parametrize("n", [1, 5, 19])
    def test_a_stacked_trace_defaults_to_lines_at_any_size(self, n):
        # plotly excludes stacked traces from the marker default explicitly.
        assert default_mode(_trace(n, stackgroup="one")) == "lines"

    def test_the_count_is_the_points_actually_drawn(self):
        # x and y are zipped, so the shorter axis is what reaches the chart.
        assert default_mode({"x": list(range(50)), "y": [1, 2, 3]}) == (
            "lines+markers"
        )

    def test_a_y_only_trace_counts_its_own_length(self):
        # plotly generates x as 0..n-1 when only y is supplied.
        assert default_mode({"y": list(range(25))}) == "lines"

    def test_a_trace_with_no_sequence_does_not_raise(self):
        assert default_mode({}) == "lines+markers"
        assert default_mode({"x": 3, "y": 4}) == "lines+markers"


class TestModelessClassification:
    """The classifier resolves the absent mode before deciding."""

    def test_a_long_modeless_trace_is_a_connected_line(self):
        assert is_connected_line_trace(_trace(25)) is True

    def test_a_short_modeless_trace_is_not(self):
        assert is_connected_line_trace(_trace(5)) is False

    def test_an_explicit_mode_still_wins_over_the_default(self):
        # A 25-point trace defaults to "lines", but an explicit markers mode
        # is what the author asked for.
        assert is_connected_line_trace(_trace(25, mode="markers")) is False
        assert is_connected_line_trace(_trace(5, mode="lines")) is True

    def test_a_short_modeless_staircase_is_still_connected(self):
        # The step rescue is checked before the default, so a staircase short
        # enough to default to markers still reads as piecewise constant.
        assert (
            is_connected_line_trace(_trace(5, line={"shape": "hv"})) is True
        )

    def test_a_non_scatter_trace_is_never_connected(self):
        assert is_connected_line_trace(_trace(25, type="bar")) is False


class TestTheExportedLayer:
    """End to end: what a mode-less figure actually emits."""

    def _types(self, n: int, **kwargs) -> list:
        fig = go.Figure()
        fig.add_scatter(x=list(range(n)), y=list(range(n)), **kwargs)
        return [layer[MaidrKey.TYPE] for layer in _layers(fig)]

    def test_a_modeless_line_chart_is_exported_as_a_line(self):
        # The bug: this announced as loose points while plotly drew a line.
        assert self._types(25) == [PlotType.LINE]

    def test_a_short_modeless_chart_stays_a_scatter(self):
        # Unchanged, and deliberately so: plotly draws markers here, and an
        # explicit "lines+markers" is classified the same way.
        assert self._types(6) == [PlotType.SCATTER]

    def test_a_stacked_modeless_chart_is_a_line_at_any_size(self):
        assert self._types(6, stackgroup="one") == [PlotType.LINE]

    def test_the_rescued_line_gets_a_scoped_selector(self):
        # Reclassifying is only half the job -- the layer has to carry a
        # selector that resolves, which means a position among the subplot's
        # scatter traces rather than the unscoped fallback.
        fig = go.Figure()
        fig.add_scatter(x=list(range(25)), y=list(range(25)))
        (layer,) = _layers(fig)

        assert layer[MaidrKey.TYPE] == PlotType.LINE
        assert "nth-child(1)" in layer[MaidrKey.SELECTOR][0]

    def test_a_modeless_line_after_a_step_is_indexed_past_it(self):
        # The reclassified line now competes for scatterlayer positions with
        # a step, which is exactly where a wrong index highlights the wrong
        # element.
        fig = go.Figure()
        fig.add_scatter(
            x=[0, 1, 2],
            y=[1, 2, 3],
            mode="lines",
            line={"shape": "hv"},
            name="step",
        )
        fig.add_scatter(x=list(range(25)), y=list(range(25)), name="line")

        layers = _layers(fig)
        line = next(x for x in layers if x[MaidrKey.TYPE] == PlotType.LINE)
        step = next(x for x in layers if x[MaidrKey.TYPE] == PlotType.STEP)

        assert "nth-child(1)" in step[MaidrKey.SELECTOR][0]
        assert "nth-child(2)" in line[MaidrKey.SELECTOR][0]
