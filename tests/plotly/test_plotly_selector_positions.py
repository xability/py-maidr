"""The three line-family classes require a selector position.

They previously disagreed about what to do when nobody supplied one, and the
two fallbacks failed in different ways. ``PlotlyLinePlot`` fell back to an
unscoped ``.trace.scatter path.js-line``, which over-matched — a step trace
renders as ``path.js-line`` too. ``PlotlyStepPlot`` and
``PlotlyMultiLinePlot`` fell back to leading order, which is *silently* wrong:
constructed for traces that are not the subplot's first scatter children, it
emitted ``nth-child(1), nth-child(2), …`` pointing at whichever elements
happened to sit there, with no error and nothing visibly amiss.

Both fallbacks are gone. A caller that cannot supply a real position now has
to say so at the call site.
"""

from __future__ import annotations

import pytest

from maidr.core.enum.maidr_key import MaidrKey
from maidr.plotly.line import PlotlyLinePlot
from maidr.plotly.multiline import PlotlyMultiLinePlot
from maidr.plotly.plotly_plot_factory import PlotlyPlotFactory
from maidr.plotly.step import PlotlyStepPlot

plotly = pytest.importorskip("plotly")


def _line(name: str = "") -> dict:
    """
    Build a minimal plotly line trace dict.

    Parameters
    ----------
    name : str, optional
        Trace name.

    Returns
    -------
    dict
        A scatter/lines trace dict.
    """
    return {
        "type": "scatter",
        "mode": "lines",
        "x": [0, 1, 2],
        "y": [1, 2, 3],
        **({"name": name} if name else {}),
    }


def _step(shape: str = "hv") -> dict:
    """
    Build a minimal plotly staircase trace dict.

    Parameters
    ----------
    shape : str, optional
        The ``line.shape`` to author.

    Returns
    -------
    dict
        A scatter/lines trace dict carrying a stepping shape.
    """
    return dict(_line(), line={"shape": shape})


class TestAPositionIsRequired:
    """Omitting one is a TypeError, not a silently wrong default."""

    def test_line_requires_a_position(self):
        with pytest.raises(TypeError):
            PlotlyLinePlot(_line(), {})

    def test_multiline_requires_positions(self):
        with pytest.raises(TypeError):
            PlotlyMultiLinePlot([_line("a"), _line("b")], {})

    def test_step_requires_positions(self):
        with pytest.raises(TypeError):
            PlotlyStepPlot([_step()], {})


class TestAPositionListMustDescribeItsTraces:
    """
    Requiring positions closes one hole; a wrong list is the other.

    The emitted selector list is positional, so a length mismatch slides every
    later series onto another element, a negative index builds
    ``nth-child(0)`` and matches nothing, and a repeat points two series at
    one element. None of those raise on their own — they highlight the wrong
    geometry, which is exactly what requiring positions was meant to end.
    """

    def test_too_few_positions_is_rejected(self):
        with pytest.raises(ValueError, match="expected 2 scatter position"):
            PlotlyStepPlot([_step(), _step()], {}, scatter_positions=[0])

    def test_too_many_positions_is_rejected(self):
        with pytest.raises(ValueError, match="expected 1 scatter position"):
            PlotlyMultiLinePlot([_line("a")], {}, scatter_positions=[0, 1])

    def test_a_negative_position_is_rejected(self):
        with pytest.raises(ValueError, match="must be >= 0"):
            PlotlyStepPlot([_step()], {}, scatter_positions=[-1])

    def test_a_negative_position_is_rejected_for_a_lone_line(self):
        with pytest.raises(ValueError, match="must be >= 0"):
            PlotlyLinePlot(_line(), {}, scatter_position=-1)

    def test_duplicate_positions_are_rejected(self):
        with pytest.raises(ValueError, match="must be unique"):
            PlotlyMultiLinePlot(
                [_line("a"), _line("b")], {}, scatter_positions=[2, 2]
            )

    @pytest.mark.parametrize(
        "cls", [PlotlyStepPlot, PlotlyMultiLinePlot], ids=["step", "multiline"]
    )
    def test_an_empty_trace_list_is_rejected(self, cls):
        # Would otherwise die on `traces[0]` inside the parent constructor.
        with pytest.raises(ValueError, match="at least one trace"):
            cls([], {}, scatter_positions=[])

    @pytest.mark.parametrize(
        "cls", [PlotlyStepPlot, PlotlyMultiLinePlot], ids=["step", "multiline"]
    )
    def test_mutating_the_caller_s_list_afterwards_changes_nothing(self, cls):
        # Stored by value, not aliased. A validated list that the caller then
        # mutates would otherwise slip past validation and reach render() --
        # the wrong-element failure, arrived at after the guard rather than
        # around it.
        positions = [2, 4]
        plot = cls([_step(), _step()], {}, scatter_positions=positions)

        positions[0] = 99
        positions.append(7)

        first, second = plot.schema[MaidrKey.SELECTOR]

        assert "nth-child(3)" in first
        assert "nth-child(5)" in second

    def test_mutating_the_caller_s_trace_list_afterwards_changes_nothing(self):
        traces = [_step(), _step()]
        plot = PlotlyStepPlot(traces, {}, scatter_positions=[0, 1])

        traces.append(_step())

        assert len(plot.schema[MaidrKey.DATA]) == 2

    def test_a_valid_out_of_order_list_is_accepted(self):
        # Positions need not be sorted or contiguous -- only well-formed.
        plot = PlotlyStepPlot([_step(), _step()], {}, scatter_positions=[5, 1])
        first, second = plot.schema[MaidrKey.SELECTOR]

        assert "nth-child(6)" in first
        assert "nth-child(2)" in second


class TestTheFallbacksAreGone:
    """Neither old default can be reached any more."""

    def test_a_line_never_emits_the_unscoped_selector(self):
        # The old fallback. It matched every `path.js-line` on the subplot,
        # including any step trace's.
        plot = PlotlyLinePlot(_line(), {}, scatter_position=3)
        (selector,) = plot.schema[MaidrKey.SELECTOR]

        assert "nth-child(4)" in selector
        assert selector != ".subplot.xy .trace.scatter path.js-line"

    def test_a_step_layer_honours_positions_past_the_leading_ones(self):
        # Under the old leading-order default this emitted nth-child(1) and
        # (2) regardless -- the silent failure the issue describes.
        plot = PlotlyStepPlot([_step(), _step()], {}, scatter_positions=[2, 4])
        first, second = plot.schema[MaidrKey.SELECTOR]

        assert "nth-child(3)" in first
        assert "nth-child(5)" in second

    def test_a_multiline_layer_honours_positions_past_the_leading_ones(self):
        plot = PlotlyMultiLinePlot(
            [_line("a"), _line("b")], {}, scatter_positions=[1, 3]
        )
        first, second = plot.schema[MaidrKey.SELECTOR]

        assert "nth-child(2)" in first
        assert "nth-child(4)" in second


class TestTheFactoryStatesItsAssumption:
    """
    The one caller that cannot know a position now says so out loud.

    ``PlotlyPlotFactory`` sees a single trace with no idea what else is on its
    subplot, so position 0 is the only assumption available. Passing it
    explicitly keeps that assumption at the one call site that has to make it,
    instead of in a default every other caller would inherit silently.
    """

    def test_a_factory_built_line_is_scoped_to_the_first_child(self):
        plot = PlotlyPlotFactory.create(_line(), {})
        (selector,) = plot.schema[MaidrKey.SELECTOR]

        assert "nth-child(1)" in selector
        assert ".scatterlayer" in selector

    def test_a_factory_built_step_is_scoped_to_the_first_child(self):
        plot = PlotlyPlotFactory.create(_step(), {})
        (selector,) = plot.schema[MaidrKey.SELECTOR]

        assert "nth-child(1)" in selector

    def test_a_factory_built_line_still_carries_its_data(self):
        # The constructor signature changed; the layer must not have.
        plot = PlotlyPlotFactory.create(_line("Series A"), {})
        data = plot.schema[MaidrKey.DATA]

        assert len(data) == 1
        assert len(data[0]) == 3
        assert data[0][0][MaidrKey.Z] == "Series A"


class TestPlotlyMaidrStillSuppliesRealPositions:
    """The production path was already correct and must stay that way."""

    def test_a_step_and_two_lines_each_get_their_own_index(self):
        import plotly.graph_objects as go

        from maidr.core.enum.plot_type import PlotType
        from maidr.plotly.plotly_maidr import PlotlyMaidr

        fig = go.Figure()
        fig.add_scatter(**_step(), name="step")
        fig.add_scatter(**_line("line 1"))
        fig.add_scatter(**_line("line 2"))

        layers = [plot.schema for plot in PlotlyMaidr(fig)._plots]
        lines = next(x for x in layers if x[MaidrKey.TYPE] == PlotType.LINE)
        step = next(x for x in layers if x[MaidrKey.TYPE] == PlotType.STEP)

        assert "nth-child(1)" in step[MaidrKey.SELECTOR][0]
        assert "nth-child(2)" in lines[MaidrKey.SELECTOR][0]
        assert "nth-child(3)" in lines[MaidrKey.SELECTOR][1]
