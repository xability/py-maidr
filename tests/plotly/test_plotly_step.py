from __future__ import annotations

import pytest

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.line import PlotlyLinePlot
from maidr.plotly.multiline import PlotlyMultiLinePlot
from maidr.plotly.plotly_maidr import PlotlyMaidr
from maidr.plotly.plotly_plot_factory import PlotlyPlotFactory
from maidr.plotly.step import PlotlyStepPlot
from maidr.plotly.step_shape import group_by_direction, step_direction_of

plotly = pytest.importorskip("plotly")
import plotly.graph_objects as go  # noqa: E402


def _step_trace(shape: str, name: str = "", y=None) -> dict:
    """
    Build a minimal plotly staircase trace dict.

    Parameters
    ----------
    shape : str
        The ``line.shape`` to author.
    name : str, optional
        Trace name, emitted as the series' ``z``.
    y : list, optional
        Y values; defaults to a three-point run.

    Returns
    -------
    dict
        A scatter/lines trace dict.
    """
    return {
        "type": "scatter",
        "mode": "lines",
        "x": [0, 1, 2],
        "y": [1, 2, 3] if y is None else y,
        "line": {"shape": shape},
        **({"name": name} if name else {}),
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


class TestStepShapeClassification:
    """A staircase is a scatter trace; only ``line.shape`` separates it."""

    @pytest.mark.parametrize("shape", ["hv", "vh", "hvh", "vhv"])
    def test_stepping_shapes_bind_as_step(self, shape):
        plot = PlotlyPlotFactory.create(_step_trace(shape), {})

        assert isinstance(plot, PlotlyStepPlot)
        assert plot.type == PlotType.STEP

    @pytest.mark.parametrize("shape", ["linear", "spline"])
    def test_interpolating_shapes_stay_a_line(self, shape):
        plot = PlotlyPlotFactory.create(_step_trace(shape), {})

        assert isinstance(plot, PlotlyLinePlot)
        assert plot.type == PlotType.LINE

    def test_a_trace_with_no_shape_stays_a_line(self):
        trace = {"type": "scatter", "mode": "lines", "x": [0], "y": [1]}

        assert isinstance(PlotlyPlotFactory.create(trace, {}), PlotlyLinePlot)

    def test_a_non_dict_line_does_not_raise(self):
        # Hand-built trace dicts reach this code, so `line` is not guaranteed
        # to be the dict plotly itself would produce.
        trace = {"type": "scatter", "mode": "lines", "x": [0], "y": [1], "line": "hv"}

        assert isinstance(PlotlyPlotFactory.create(trace, {}), PlotlyLinePlot)

    def test_markers_mode_is_still_a_scatter(self):
        trace = dict(_step_trace("hv"), mode="lines+markers")

        assert not isinstance(PlotlyPlotFactory.create(trace, {}), PlotlyStepPlot)


class TestStepDirection:
    """``stepDirection`` mirrors the upstream adapter's shape mapping."""

    @pytest.mark.parametrize(
        ("shape", "expected"),
        [("hv", "hv"), ("vh", "vh"), ("hvh", "mid")],
    )
    def test_shape_maps_to_its_convention(self, shape, expected):
        schema = PlotlyPlotFactory.create(_step_trace(shape), {}).schema

        assert schema[MaidrKey.STEP_DIRECTION] == expected

    def test_vhv_binds_as_step_but_claims_no_direction(self):
        # vhv is the one shape whose horizontal segments do not sit at a
        # sample's own value, so it has no StepDirection equivalent. The data
        # is still piecewise constant, so it is still a step.
        schema = PlotlyPlotFactory.create(_step_trace("vhv"), {}).schema

        assert schema[MaidrKey.TYPE] == PlotType.STEP
        assert MaidrKey.STEP_DIRECTION not in schema

    def test_direction_is_withheld_when_traces_disagree(self):
        # Guards a caller that skipped group_by_direction: better to say
        # nothing than to describe one of the series wrongly.
        plot = PlotlyStepPlot(
            [_step_trace("hv"), _step_trace("vh")], {}, scatter_positions=[0, 1]
        )

        assert MaidrKey.STEP_DIRECTION not in plot.schema


class TestStepPayload:
    """The emitted layer matches the MAIDR step contract."""

    def test_data_is_a_list_of_series_with_one_point_per_sample(self):
        schema = PlotlyPlotFactory.create(_step_trace("hv", "Night 1"), {}).schema
        data = schema[MaidrKey.DATA]

        assert len(data) == 1
        # One point per data sample, never one per stairstep vertex: the
        # frontend rebuilds the risers itself.
        assert len(data[0]) == 3
        assert data[0][0] == {
            MaidrKey.X: 0,
            MaidrKey.Y: 1,
            MaidrKey.Z: "Night 1",
        }

    def test_an_unnamed_trace_emits_no_z(self):
        schema = PlotlyPlotFactory.create(_step_trace("hv"), {}).schema

        assert MaidrKey.Z not in schema[MaidrKey.DATA][0][0]

    def test_one_selector_per_series(self):
        schema = PlotlyPlotFactory.create(_step_trace("hv"), {}).schema

        assert len(schema[MaidrKey.SELECTOR]) == len(schema[MaidrKey.DATA])


class TestDirectionGrouping:
    """A layer carries one ``stepDirection``, so conventions cannot merge."""

    def test_groups_split_by_convention_preserving_order(self):
        traces = [
            _step_trace("hv", "A"),
            _step_trace("vh", "B"),
            _step_trace("hv", "C"),
        ]

        groups = group_by_direction(traces)

        assert [[t["name"] for t in g] for g in groups] == [["A", "C"], ["B"]]

    def test_directionless_shapes_group_together(self):
        traces = [_step_trace("vhv", "A"), _step_trace("hv", "B"), _step_trace("vhv", "C")]

        groups = group_by_direction(traces)

        assert [[t["name"] for t in g] for g in groups] == [["A", "C"], ["B"]]
        assert step_direction_of(traces[0]) is None

    def test_mixed_conventions_emit_one_layer_each(self):
        fig = go.Figure()
        fig.add_scatter(**_step_trace("hv", "A"))
        fig.add_scatter(**_step_trace("hv", "B"))
        fig.add_scatter(**_step_trace("vh", "C"))

        layers = _layers(fig)

        assert [layer[MaidrKey.TYPE] for layer in layers] == [
            PlotType.STEP,
            PlotType.STEP,
        ]
        assert [layer.get(MaidrKey.STEP_DIRECTION) for layer in layers] == ["hv", "vh"]
        assert [len(layer[MaidrKey.DATA]) for layer in layers] == [2, 1]

    def test_selectors_index_the_subplot_not_the_layer(self):
        # `nth-child` counts within the subplot's scatterlayer. Two layers
        # both numbering from 1 would highlight the same two elements, so the
        # vh layer's single trace must resolve to the third child.
        fig = go.Figure()
        fig.add_scatter(**_step_trace("hv", "A"))
        fig.add_scatter(**_step_trace("hv", "B"))
        fig.add_scatter(**_step_trace("vh", "C"))

        hv_layer, vh_layer = _layers(fig)

        assert "nth-child(1)" in hv_layer[MaidrKey.SELECTOR][0]
        assert "nth-child(2)" in hv_layer[MaidrKey.SELECTOR][1]
        assert "nth-child(3)" in vh_layer[MaidrKey.SELECTOR][0]


class _TypelessTraceFigure:
    """
    A minimal figure whose trace dict omits ``type``.

    ``Figure.to_dict()`` always emits ``type``, so this shape is only
    reachable by building the dict by hand — which the internals accept and
    which is how these classifiers get exercised directly.
    """

    def __init__(self, line_shape: str | None = None) -> None:
        trace: dict = {"mode": "lines", "x": [0, 1, 2], "y": [1, 2, 3]}
        if line_shape is not None:
            trace["line"] = {"shape": line_shape}
        self._trace = trace

    def to_dict(self) -> dict:
        return {"layout": {}, "data": [self._trace]}


class TestClassificationAndSelectorIndexAgree:
    """
    Whatever counts as a line or a step must also have a selector position.

    The line/step classifier and the scatter-family index are two separate
    filters over the same traces. When they disagreed on the default for a
    missing ``type``, a trace could be classified as a line while being absent
    from the position map, and the selector lookup raised ``KeyError`` rather
    than emitting a layer. They now share ``is_scatter_family_trace``.
    """

    def test_a_typeless_line_trace_still_resolves_its_position(self):
        layers = _layers(_TypelessTraceFigure())

        assert len(layers) == 1
        assert layers[0][MaidrKey.TYPE] == PlotType.LINE
        assert "nth-child(1)" in layers[0][MaidrKey.SELECTOR][0]

    def test_a_typeless_step_trace_still_resolves_its_position(self):
        layers = _layers(_TypelessTraceFigure(line_shape="hv"))

        assert len(layers) == 1
        assert layers[0][MaidrKey.TYPE] == PlotType.STEP
        assert layers[0][MaidrKey.STEP_DIRECTION] == "hv"
        assert "nth-child(1)" in layers[0][MaidrKey.SELECTOR][0]


class TestAModelessStaircaseStillBinds:
    """
    A staircase authored without ``mode`` must not fall through to scatter.

    ``to_dict()`` omits ``mode`` when the author never set one, and plotly's
    default draws lines regardless ("lines+markers" under 20 points, "lines"
    at or above). Reading that as markers-only sent a chart plotly draws as a
    staircase to a scatter layer — announced as loose points, with the
    piecewise-constant reading lost.

    A declared stepping shape is decisive on its own, checked before the mode
    default is resolved at all: plotly draws the risers whatever the mode
    turns out to be. Traces with no shape go on to
    ``tests/plotly/test_plotly_mode_default.py``, which covers how an absent
    mode resolves.
    """

    def _one_layer(self, **trace_kwargs):
        fig = go.Figure()
        fig.add_scatter(x=list(range(6)), y=[1, 2, 3, 2, 1, 2], **trace_kwargs)
        layers = _layers(fig)
        assert len(layers) == 1
        return layers[0]

    def test_a_modeless_step_binds_as_step(self):
        layer = self._one_layer(line={"shape": "hv"})

        assert layer[MaidrKey.TYPE] == PlotType.STEP
        assert layer[MaidrKey.STEP_DIRECTION] == "hv"

    def test_a_modeless_trace_without_a_shape_is_not_a_step(self):
        # No shape, so nothing here claims the data is piecewise constant.
        # This six-point trace lands on SCATTER because plotly's own default
        # adds markers below 20 points -- not because an absent mode reads as
        # markers-only. See test_plotly_mode_default.py for that boundary.
        assert self._one_layer()[MaidrKey.TYPE] == PlotType.SCATTER

    def test_an_explicit_markers_mode_still_wins(self):
        layer = self._one_layer(mode="markers", line={"shape": "hv"})

        assert layer[MaidrKey.TYPE] == PlotType.SCATTER

    def test_an_explicit_lines_markers_mode_is_unchanged(self):
        layer = self._one_layer(mode="lines+markers", line={"shape": "hv"})

        assert layer[MaidrKey.TYPE] == PlotType.SCATTER


class TestStepDoesNotDisturbLines:
    """The regression that matters most: plain lines are untouched."""

    def test_a_step_beside_lines_leaves_the_multiline_layer_intact(self):
        fig = go.Figure()
        fig.add_scatter(**_step_trace("hv", "step"))
        fig.add_scatter(x=[0, 1, 2], y=[3, 2, 1], mode="lines", name="line 1")
        fig.add_scatter(x=[0, 1, 2], y=[2, 3, 4], mode="lines", name="line 2")

        layers = _layers(fig)
        by_type = {layer[MaidrKey.TYPE]: layer for layer in layers}

        assert set(by_type) == {PlotType.LINE, PlotType.STEP}
        # The two plain lines still merge into one multiline layer; the step
        # is not swallowed into it.
        assert len(by_type[PlotType.LINE][MaidrKey.DATA]) == 2
        assert len(by_type[PlotType.STEP][MaidrKey.DATA]) == 1

    def test_lines_after_a_step_are_indexed_past_it(self):
        # Splitting steps out of the multiline layer breaks the assumption
        # that a line layer owns every scatter trace on its subplot, so the
        # line layer must count from the step's position, not from 1. Getting
        # this wrong made the LINE layer claim nth-child(1) — the step's own
        # element — and shifted every line onto its predecessor.
        fig = go.Figure()
        fig.add_scatter(**_step_trace("hv", "step"))
        fig.add_scatter(x=[0, 1, 2], y=[3, 2, 1], mode="lines", name="line 1")
        fig.add_scatter(x=[0, 1, 2], y=[2, 3, 4], mode="lines", name="line 2")

        by_type = {layer[MaidrKey.TYPE]: layer for layer in _layers(fig)}

        assert "nth-child(1)" in by_type[PlotType.STEP][MaidrKey.SELECTOR][0]
        assert "nth-child(2)" in by_type[PlotType.LINE][MaidrKey.SELECTOR][0]
        assert "nth-child(3)" in by_type[PlotType.LINE][MaidrKey.SELECTOR][1]

    def test_a_lone_line_beside_a_step_is_scoped_to_its_own_trace(self):
        # A single line used to emit the unscoped `.trace.scatter
        # path.js-line`, which was safe only while it was the subplot's one
        # line path. A step renders as path.js-line too, so that form now
        # matches both elements.
        fig = go.Figure()
        fig.add_scatter(**_step_trace("hv", "step"))
        fig.add_scatter(x=[0, 1, 2], y=[3, 2, 1], mode="lines", name="only")

        by_type = {layer[MaidrKey.TYPE]: layer for layer in _layers(fig)}
        line_selector = by_type[PlotType.LINE][MaidrKey.SELECTOR][0]

        assert "nth-child(2)" in line_selector
        assert "nth-child(1)" in by_type[PlotType.STEP][MaidrKey.SELECTOR][0]

    def test_lines_alone_still_number_from_the_first_child(self):
        # The no-step case must be untouched: with no step carved out, the
        # subplot-relative positions are exactly the layer-relative ones.
        fig = go.Figure()
        fig.add_scatter(x=[0, 1], y=[1, 2], mode="lines", name="a")
        fig.add_scatter(x=[0, 1], y=[2, 1], mode="lines", name="b")

        selectors = _layers(fig)[0][MaidrKey.SELECTOR]

        assert "nth-child(1)" in selectors[0]
        assert "nth-child(2)" in selectors[1]

    def test_lines_alone_still_produce_a_single_multiline_layer(self):
        fig = go.Figure()
        fig.add_scatter(x=[0, 1], y=[1, 2], mode="lines", name="a")
        fig.add_scatter(x=[0, 1], y=[2, 1], mode="lines", name="b")

        plots = PlotlyMaidr(fig)._plots

        assert len(plots) == 1
        assert isinstance(plots[0], PlotlyMultiLinePlot)
        assert plots[0].type == PlotType.LINE
