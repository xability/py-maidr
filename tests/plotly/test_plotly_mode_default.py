"""Classifying a plotly trace that never authored a ``mode``.

``Figure.to_dict()`` omits ``mode`` unless it was set, so the exported dict
cannot be read literally: an absent ``mode`` is not "no drawing mode", it is
"whatever Plotly's default resolves to". Plotly documents that default on
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

pytest.importorskip("plotly")
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


class TestTheTranscribedRuleStillMatchesUpstream:
    """
    Guard the one assumption the whole fix rests on.

    ``default_mode`` is a hand transcription of a rule Plotly states only in
    its generated attribute docstring — nothing in the Python package enforces
    it, so a future Plotly release could change the boundary or drop the
    stacked exception and every test here would keep passing against a rule
    that no longer describes what is drawn. Reading the docstring back turns
    that silent drift into a failing build.

    **If one of these fails, check for a wording change before changing any
    code.** They match on the docstring's prose, so a purely cosmetic rewrite
    upstream ("fewer than" for "less than") fails them without the behaviour
    having moved at all. The question to answer first is whether the *rule*
    changed; ``go.Figure``'s resolved ``_fullData[i].mode`` in a browser is
    the ground truth if it is ever unclear.
    """

    @staticmethod
    def _mode_doc() -> str:
        return go.Scatter().__class__.mode.__doc__ or ""

    def test_the_point_boundary_is_still_twenty(self):
        from maidr.plotly.step_shape import _MARKER_DEFAULT_MAX_POINTS

        doc = " ".join(self._mode_doc().split())

        assert f"less than {_MARKER_DEFAULT_MAX_POINTS} points" in doc

    def test_the_stacked_exception_still_exists(self):
        doc = " ".join(self._mode_doc().split())

        assert "not stacked" in doc

    def test_the_two_resolved_modes_are_still_the_documented_ones(self):
        doc = " ".join(self._mode_doc().split())

        assert '"lines+markers"' in doc
        assert '"lines"' in doc


class TestPlotlysOwnDefault:
    """``default_mode`` must reproduce the rule Plotly documents."""

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


class TestScatterglSharesTheRule:
    """
    ``scattergl`` is scatter-family, so the same default has to apply to it.

    Its Python docstring is not evidence either way — unlike ``Scatter``'s, it
    states no default at all, so it can neither confirm nor contradict the
    rule. plotly.js was read instead: the threshold is one shared
    ``PTS_LINESONLY`` constant, and both trace modules coerce with the same
    ``n < PTS_LINESONLY ? "lines+markers" : "lines"``.

    Confirmed by rendering both types in Chromium and reading back plotly's
    own resolved ``gd._fullData[i].mode``, which agreed at every count::

        n=5   scattergl lines+markers   scatter lines+markers
        n=19  scattergl lines+markers   scatter lines+markers
        n=20  scattergl lines           scatter lines
        n=25  scattergl lines           scatter lines
    """

    @pytest.mark.parametrize("n", [5, 19, 20, 25])
    def test_gl_and_svg_resolve_identically(self, n):
        assert default_mode(_trace(n, type="scattergl")) == default_mode(
            _trace(n)
        )

    def test_a_long_gl_trace_is_a_connected_line(self):
        assert is_connected_line_trace(_trace(25, type="scattergl")) is True

    def test_a_short_gl_trace_is_not(self):
        assert is_connected_line_trace(_trace(5, type="scattergl")) is False


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

    def test_a_stacked_modeless_chart_is_connected_at_any_size(self):
        # `stackgroup` makes plotly connect the samples whatever the mode
        # default would have been, so six points is a band rather than the
        # loose markers a mode-less six-point scatter gets. This asserted
        # `LINE` until #392 taught the adapter that a stacked trace is a
        # filled area -- a stricter reading of the same figure, and the
        # property being guarded here is unchanged: not `SCATTER`.
        assert self._types(6, stackgroup="one") == [PlotType.AREA]
        assert self._types(6) == [PlotType.SCATTER]

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
