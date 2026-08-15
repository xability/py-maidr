"""A plotly area chart was announced as a line chart (#392).

`px.area` produces a `Scatter`, and the only thing separating it from a line
is `stackgroup`. The adapter had no area handling at all -- `maidr/plotly/`
carried bar, box, heatmap, histogram, line, pie, scatter and step, and no
`area` -- so every one of them fell through to `line`.

The numbers were right, which is why this is a parity gap rather than a wrong
reading: plotly keeps each series' own values in `trace.y` and stacks in the
browser, so a stacked area announced `1, 2, 3` and `10, 20, 30` rather than
running totals. That is the opposite of the matplotlib and ggplot2 hazard,
where the built data holds the cumulative top.

What was missing is the name and the relationship. A filled, stacked band was
announced as a line, so a reader was not told the bands are filled, that they
stack, or what the total at each x is -- which is the reason someone draws
this chart rather than a multi-line one.

Plotly's own calcdata carries both numbers and agrees about which is which:
`s` holds the band's own value and `y` the running total. For series of
`1,2,3` and `10,20,30` the second's `y` comes back `11,22,33`, so `trace["y"]`
is the band's own value and needs no un-accumulating. The total stays the
core's to derive, as it is for `stackplot`.

Every selector below was resolved against real Plotly.js output in Chromium:
9 of 9 matched exactly one element, including the mixed area-and-line figures
where the scatter positions interleave.
"""

from __future__ import annotations

import pytest

plotly = pytest.importorskip("plotly")

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.area import (  # noqa: E402
    area_plot_type,
    area_stack_groups,
    is_area_trace,
)
from maidr.plotly.area import PlotlyAreaPlot  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

X = [1, 2, 3]
LOW = [1, 2, 3]
HIGH = [10, 20, 30]


def frame() -> pd.DataFrame:
    return pd.DataFrame({"x": X * 2, "y": LOW + HIGH, "g": ["a"] * 3 + ["b"] * 3})


def layers(fig) -> list[dict]:
    return PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"]


def only_layer(fig) -> dict:
    return layers(fig)[0]


def band(fig, index: int = 0) -> list[tuple]:
    series = only_layer(fig)["data"][index]
    return [(point["x"], point["y"], point["z"]) for point in series]


class TestIsAreaTrace:
    """`stackgroup` is the whole signal, and it is structural."""

    def test_a_stackgroup_makes_a_scatter_an_area(self):
        assert is_area_trace({"type": "scatter", "stackgroup": "one"}) is True

    def test_an_empty_stackgroup_is_a_line(self):
        # Plotly's own default. `""` is what a plain scatter resolves to, and
        # it means "do not stack" rather than "stack with the unnamed group".
        assert is_area_trace({"type": "scatter", "stackgroup": ""}) is False

    def test_no_stackgroup_at_all_is_a_line(self):
        assert is_area_trace({"type": "scatter", "y": LOW}) is False

    def test_a_markers_only_trace_with_a_stackgroup_is_still_an_area(self):
        # Plotly fills from `stackgroup` alone -- `mode` chooses whether the
        # boundary is drawn as a line or as points, not whether the band is
        # filled. Pinned so the classifier is not later narrowed to require
        # `"lines"` in `mode`, which would drop a real filled band back onto
        # the scatter path.
        assert (
            is_area_trace(
                {"type": "scatter", "stackgroup": "one", "mode": "markers"}
            )
            is True
        )

    def test_a_bar_with_a_stackgroup_is_not_an_area(self):
        # Guards the scatter-family half of the test: `stackgroup` alone is
        # not enough, or a mislabelled trace of another type would be filled.
        assert is_area_trace({"type": "bar", "stackgroup": "one"}) is False

    def test_a_webgl_trace_is_not_an_area_even_carrying_a_stackgroup(self):
        # Plotly does not stack one, at either level. `scattergl` has no
        # `stackgroup` attribute -- `go.Scattergl(stackgroup="one")` raises
        # `Bad property path` on plotly 6.7.0 -- and plotly.js ignores the key
        # on a raw dict that carries it anyway: measured in Chromium, the gl
        # trace came back `fill: "none"`, with no `stackgroup` in `_fullData`
        # and nothing accumulated, while the svg trace beside it stacked
        # normally. Reading it as an area would announce a filled, stacked
        # band where plotly draws a plain line -- and, since a WebGL layer can
        # carry no selectors, silently take the highlight away too.
        assert is_area_trace({"type": "scattergl", "stackgroup": "one"}) is False


class TestStackGroups:
    def test_traces_sharing_a_group_stack_together(self):
        traces = [
            {"type": "scatter", "stackgroup": "one"},
            {"type": "scatter", "stackgroup": "one"},
        ]
        assert len(area_stack_groups(traces)) == 1

    def test_different_groups_are_separate_stacks(self):
        # Measured: with `stackgroup='one'` and `'two'`, each series' calcdata
        # `y` equals its own `s` -- plotly accumulates nothing across them.
        traces = [
            {"type": "scatter", "stackgroup": "one"},
            {"type": "scatter", "stackgroup": "two"},
        ]
        assert len(area_stack_groups(traces)) == 2

    def test_groups_come_back_in_first_seen_order(self):
        traces = [
            {"type": "scatter", "stackgroup": "b", "name": "first"},
            {"type": "scatter", "stackgroup": "a", "name": "second"},
        ]
        assert [g[0]["name"] for g in area_stack_groups(traces)] == [
            "first",
            "second",
        ]


class TestPlotType:
    def test_a_lone_band_is_a_plain_area(self):
        # Nothing is stacked on it, the same distinction the matplotlib path
        # draws for a single `stackplot` band.
        assert area_plot_type([{"stackgroup": "one"}]) == PlotType.AREA

    def test_two_bands_stack(self):
        assert (
            area_plot_type([{"stackgroup": "one"}, {"stackgroup": "one"}])
            == PlotType.STACKED_AREA
        )

    @pytest.mark.parametrize("groupnorm", ["percent", "fraction"])
    def test_groupnorm_normalises(self, groupnorm):
        traces = [
            {"stackgroup": "one", "groupnorm": groupnorm},
            {"stackgroup": "one"},
        ]
        assert area_plot_type(traces) == PlotType.NORMALIZED_AREA

    def test_the_normalised_type_reads_naturally_to_a_user(self):
        # The wire value is `stacked_normalized_area`, which is not what
        # anyone would call it out loud. Asserted here because every other
        # user-facing name for this layer family is.
        assert PlotType.NORMALIZED_AREA.display_name == "100% stacked area"
        assert PlotType.STACKED_AREA.display_name == "stacked area"

    def test_an_unrecognised_groupnorm_is_left_alone(self):
        traces = [{"stackgroup": "one", "groupnorm": ""}, {"stackgroup": "one"}]
        assert area_plot_type(traces) == PlotType.STACKED_AREA


class TestTheEmittedLayer:
    def test_a_stacked_area_says_so(self):
        assert only_layer(px.area(frame(), x="x", y="y", color="g"))["type"] == (
            PlotType.STACKED_AREA.value
        )

    def test_a_single_band_is_an_area(self):
        single = frame()[lambda d: d.g == "a"]
        assert only_layer(px.area(single, x="x", y="y"))["type"] == (
            PlotType.AREA.value
        )

    def test_groupnorm_reaches_the_layer(self):
        layer = only_layer(
            px.area(frame(), x="x", y="y", color="g", groupnorm="percent")
        )
        assert layer["type"] == PlotType.NORMALIZED_AREA.value

    def test_each_band_carries_its_own_values_not_the_running_total(self):
        # The distinction the area type exists for. Plotly's calcdata has the
        # second band's total at 11, 22, 33; its own values are 10, 20, 30 and
        # those are what a reader needs, with the total derived from them.
        fig = px.area(frame(), x="x", y="y", color="g")
        assert band(fig, 1) == [(1, 10, "b"), (2, 20, "b"), (3, 30, "b")]

    def test_each_band_carries_its_name(self):
        fig = px.area(frame(), x="x", y="y", color="g")
        assert {point[2] for point in band(fig, 0)} == {"a"}

    def test_two_stack_groups_become_two_layers(self):
        fig = go.Figure(
            [
                go.Scatter(x=X, y=LOW, stackgroup="one"),
                go.Scatter(x=X, y=HIGH, stackgroup="two"),
            ]
        )
        emitted = layers(fig)
        assert [layer["type"] for layer in emitted] == [
            PlotType.AREA.value,
            PlotType.AREA.value,
        ]


class TestTheConstructorRefusesPositionsItCannotDescribe:
    """The same guard `PlotlyMultiLinePlot` and `PlotlyStepPlot` enforce.

    Selectors are emitted positionally -- the frontend pairs selector *i* with
    series *i* -- so a length mismatch slides every later band onto another
    element, a negative index builds `nth-child(0)` and matches nothing, and a
    repeat points two bands at one element. None of those raise on their own;
    they highlight the wrong geometry, which is what the guard exists to stop.
    An area trace shares `scatterlayer` with the lines beside it, so it is
    exposed to exactly the failure mode the other two were hardened against.
    """

    def build(self, positions, count=1):
        traces = [{"type": "scatter", "x": X, "y": LOW, "stackgroup": "one"}] * count
        return PlotlyAreaPlot(traces, {}, PlotType.AREA, positions)

    def test_no_traces_is_refused(self):
        with pytest.raises(ValueError):
            PlotlyAreaPlot([], {}, PlotType.AREA, [])

    def test_a_length_mismatch_is_refused(self):
        with pytest.raises(ValueError):
            self.build([0, 1], count=1)

    def test_a_negative_position_is_refused(self):
        with pytest.raises(ValueError):
            self.build([-1])

    def test_a_repeated_position_is_refused(self):
        with pytest.raises(ValueError):
            self.build([0, 0], count=2)

    def test_a_non_list_is_refused(self):
        with pytest.raises(TypeError):
            self.build(None)

    def test_well_formed_positions_are_accepted(self):
        assert self.build([0]) is not None

    def test_the_lists_are_copied_not_aliased(self):
        # A caller mutating its list afterwards would otherwise silently
        # change this layer's selectors on the next render.
        traces = [{"type": "scatter", "x": X, "y": LOW, "stackgroup": "one"}]
        positions = [0]
        plot = PlotlyAreaPlot(traces, {}, PlotType.AREA, positions)
        positions.append(7)
        traces.append({"type": "scatter", "x": X, "y": HIGH, "stackgroup": "one"})
        assert len(plot._scatter_positions) == 1
        assert len(plot._traces) == 1


class TestAreasAndLinesCoexist:
    """An area is a scatter trace, so the two compete for the same positions."""

    def test_a_line_beside_an_area_is_still_a_line(self):
        fig = go.Figure(
            [
                go.Scatter(x=X, y=LOW, stackgroup="one"),
                go.Scatter(x=X, y=[5, 5, 5], mode="lines"),
            ]
        )
        assert sorted(layer["type"] for layer in layers(fig)) == sorted(
            [PlotType.AREA.value, PlotType.LINE.value]
        )

    def test_the_area_is_not_also_emitted_as_a_line(self):
        # An area passes every structural test for a connected line, so left
        # in the line grouping it would be emitted twice -- once as its own
        # layer and once inside the multi-line one.
        fig = go.Figure(
            [
                go.Scatter(x=X, y=LOW, stackgroup="one"),
                go.Scatter(x=X, y=HIGH, stackgroup="one"),
            ]
        )
        assert len(layers(fig)) == 1

    @pytest.mark.parametrize("area_first", [True, False])
    def test_every_band_gets_a_selector_of_its_own(self, area_first):
        traces = [
            go.Scatter(x=X, y=LOW, stackgroup="one"),
            go.Scatter(x=X, y=[5, 5, 5], mode="lines"),
        ]
        fig = go.Figure(traces if area_first else traces[::-1])

        area = next(
            layer for layer in layers(fig) if layer["type"] == PlotType.AREA.value
        )
        selectors = area["selectors"]
        assert isinstance(selectors, list)
        assert len(selectors) == 1
        # Scoped by position among the subplot's scatter traces, so the two
        # layers cannot both claim `nth-child(1)`.
        assert "nth-child" in selectors[0]

    def test_an_unnamed_band_omits_z_rather_than_sending_it_blank(self):
        # `px.area` with no `color=` is the ordinary way to draw one band, and
        # its trace carries `name: ""`. Every sibling extractor omits the key
        # in that case -- `PlotlyPlot._line_series_with_positions` guards with
        # `if name:`, the matplotlib `AreaPlot` with `if label:`.
        #
        # Not a mis-announcement either way: maidr's `LineTrace`, which
        # `AreaTrace` extends, reads `z` through a truthiness guard
        # (`point.z ? ... : {}`), so `""` already degrades to the absent-key
        # behaviour. This keeps the emitted schema free of a key whose value
        # carries nothing.
        single = frame()[lambda d: d.g == "a"]
        point = only_layer(px.area(single, x="x", y="y"))["data"][0][0]
        assert "z" not in point
        assert point["x"] == 1

    def test_a_named_band_still_carries_z(self):
        fig = px.area(frame(), x="x", y="y", color="g")
        assert only_layer(fig)["data"][0][0]["z"] == "a"

    def test_a_band_with_no_points_is_dropped_from_data_and_selectors(self):
        # Not merely cosmetic. Plotly gives an empty trace no DOM node at
        # all, so every later band shifts up one in the `scatterlayer`.
        # Measured in Chromium with an empty band between two drawn ones:
        # the layer holds two `.trace.scatter` nodes, `nth-child(2)` resolves
        # to the *third* band and `nth-child(3)` to nothing. Emitting the
        # phantom series would hand band 2's selector to band 3 and leave
        # band 3 pointing at no element -- #316's misalignment exactly.
        fig = go.Figure(
            [
                go.Scatter(x=X, y=LOW, stackgroup="one", name="a"),
                go.Scatter(x=[], y=[], stackgroup="one", name="empty"),
                go.Scatter(x=X, y=HIGH, stackgroup="one", name="c"),
            ]
        )
        layer = only_layer(fig)
        assert [len(series) for series in layer["data"]] == [3, 3]
        assert len(layer["selectors"]) == 2

    def test_a_band_after_an_empty_one_is_still_numbered_by_declaration(self):
        """Pins a pre-existing defect this layer shares with lines and steps.

        Dropping the empty band from `data` and `selectors` is only half the
        problem. The positions that survive are the *declared* indices among
        the subplot's scatter traces, and plotly numbers the DOM by what it
        actually draws -- measured in Chromium, three traces with an empty one
        in the middle produce two `.trace.scatter` nodes, so the third band is
        `nth-child(2)` and `nth-child(3)` matches nothing.

        Not introduced here, and not specific to areas: the same figure built
        from `mode="lines"` traces already emits `nth-child(1)` and
        `nth-child(3)` on `main`, because `_drawn_line_series` filters the
        position *list* without renumbering what remains. Fixing it means
        compacting positions across the whole subplot -- one layer cannot do
        it alone, since an empty trace in another layer shifts this one too --
        so it is filed separately rather than folded into #392.

        Asserting the wrong-but-current value deliberately, so whoever takes
        that issue sees this test fail rather than having to discover it.
        """
        fig = go.Figure(
            [
                go.Scatter(x=X, y=LOW, stackgroup="one", name="a"),
                go.Scatter(x=[], y=[], stackgroup="one", name="empty"),
                go.Scatter(x=X, y=HIGH, stackgroup="one", name="c"),
            ]
        )
        selectors = only_layer(fig)["selectors"]
        assert "nth-child(1)" in selectors[0]
        assert "nth-child(3)" in selectors[1]

    def test_the_surviving_bands_keep_their_own_names(self):
        fig = go.Figure(
            [
                go.Scatter(x=X, y=LOW, stackgroup="one", name="a"),
                go.Scatter(x=[], y=[], stackgroup="one", name="empty"),
                go.Scatter(x=X, y=HIGH, stackgroup="one", name="c"),
            ]
        )
        names = [series[0]["z"] for series in only_layer(fig)["data"]]
        assert names == ["a", "c"]

    def test_the_two_layers_do_not_share_a_position(self):
        fig = go.Figure(
            [
                go.Scatter(x=X, y=LOW, stackgroup="one"),
                go.Scatter(x=X, y=[5, 5, 5], mode="lines"),
            ]
        )
        emitted = []
        for layer in layers(fig):
            found = layer["selectors"]
            emitted += found if isinstance(found, list) else [found]
        assert len(emitted) == len(set(emitted))
