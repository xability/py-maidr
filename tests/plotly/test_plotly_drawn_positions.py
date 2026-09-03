"""A trace after an empty one highlighted the wrong element (#412).

A scatter-family trace with nothing to plot gets **no DOM node at all** from
plotly -- it does not get an empty one. Every trace after it therefore moves
up a position in the `scatterlayer`, while py-maidr numbered selectors by the
trace's *declared* index.

Measured in Chromium: three line traces with an empty one in the middle
produce **two** `.trace.scatter` nodes, and the emitted selectors were
`nth-child(1)` and `nth-child(3)` -- so the second surviving line was
announced correctly and highlighted nothing, while `nth-child(2)` reached it
instead. Correct audio, braille and text; no visible highlight; no warning.

This is the empty sibling of the hidden-trace rule `is_drawn` already
implements for #400. Both end the same way -- no group in the layer -- so the
fix numbers by what plotly *draws* rather than by what was declared.

An undrawn trace is numbered after the drawn ones rather than skipped. Its
index is never rendered, because `_line_series_with_positions` drops the
series and its position together, but the layer classes validate the list
they are handed and a gap or a duplicate would fail that check. Counting them
from the end keeps every index unique, which is what the WebGL numbering
beside it already does for the same reason.

Every selector below was resolved against real Plotly.js output in Chromium:
10 of 10 matched exactly one element, across an empty band first, in the
middle, two in a row, an area stack, and an empty trace beside a hidden one.
"""

from __future__ import annotations

import pytest

pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402
from maidr.plotly.plotly_plot import draws_marks  # noqa: E402

X = [1, 2, 3]


def selectors(fig) -> list[str]:
    found: list[str] = []
    for layer in PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"]:
        # A WebGL layer omits the key entirely rather than carrying an empty
        # list -- `render()` drops it, which is the documented answer for a
        # layer with no highlightable geometry.
        entry = layer.get("selectors")
        if entry is None:
            continue
        found += entry if isinstance(entry, list) else [entry]
    return [s for s in found if isinstance(s, str)]


def line(name: str, y: list | None = None) -> go.Scatter:
    if y is None:
        return go.Scatter(x=[], y=[], mode="lines", name=name)
    return go.Scatter(x=X, y=y, mode="lines", name=name)


class TestDrawsMarks:
    def test_a_trace_with_both_arrays_draws(self):
        assert draws_marks({"x": [1, 2], "y": [3, 4]}) is True

    def test_an_empty_trace_does_not(self):
        assert draws_marks({"x": [], "y": []}) is False

    def test_a_trace_missing_one_array_still_draws(self):
        # Agrees with the extraction after #418: plotly generates the absent
        # array, so such a trace has a group and must take a position.
        assert draws_marks({"y": [1, 2, 3]}) is True
        assert draws_marks({"x": [1, 2, 3]}) is True

    def test_a_trace_with_one_empty_array_does_not(self):
        # `y: []` is explicitly empty rather than absent, and plotly draws
        # nothing for it -- the distinction #418 turned on.
        assert draws_marks({"x": [1, 2], "y": []}) is False

    def test_a_trace_with_no_arrays_at_all_does_not(self):
        assert draws_marks({}) is False


class TestNumberingFollowsWhatIsDrawn:
    def test_an_empty_trace_in_the_middle_does_not_shift_the_rest(self):
        found = selectors(
            go.Figure([line("a", [1, 2, 3]), line("e"), line("c", [7, 8, 9])])
        )
        assert len(found) == 2
        assert "nth-child(1)" in found[0]
        assert "nth-child(2)" in found[1]

    def test_an_empty_trace_first_does_not_shift_the_rest(self):
        found = selectors(
            go.Figure([line("e"), line("a", [1, 2, 3]), line("c", [7, 8, 9])])
        )
        assert "nth-child(1)" in found[0]
        assert "nth-child(2)" in found[1]

    def test_two_empty_traces_in_a_row(self):
        found = selectors(
            go.Figure(
                [line("a", [1, 2, 3]), line("e1"), line("e2"), line("c", [7, 8, 9])]
            )
        )
        assert len(found) == 2
        assert "nth-child(1)" in found[0]
        assert "nth-child(2)" in found[1]

    def test_no_two_selectors_collide(self):
        found = selectors(
            go.Figure([line("a", [1, 2, 3]), line("e"), line("c", [7, 8, 9])])
        )
        assert len(set(found)) == len(found)

    def test_a_figure_with_nothing_empty_is_unchanged(self):
        found = selectors(
            go.Figure(
                [line("a", [1, 2, 3]), line("b", [4, 5, 6]), line("c", [7, 8, 9])]
            )
        )
        assert [f"nth-child({n})" in found[n - 1] for n in (1, 2, 3)] == [True] * 3


class TestTheSameRuleReachesEveryScatterLayer:
    def test_an_area_band_after_an_empty_one(self):
        fig = go.Figure(
            [
                go.Scatter(x=X, y=[1, 2, 3], stackgroup="one", name="a"),
                go.Scatter(x=[], y=[], stackgroup="one", name="empty"),
                go.Scatter(x=X, y=[7, 8, 9], stackgroup="one", name="c"),
            ]
        )
        found = selectors(fig)
        assert "nth-child(1)" in found[0]
        assert "nth-child(2)" in found[1]

    def test_a_step_after_an_empty_one(self):
        fig = go.Figure(
            [
                go.Scatter(x=X, y=[1, 2, 3], line=dict(shape="hv"), name="a"),
                go.Scatter(x=[], y=[], line=dict(shape="hv"), name="empty"),
                go.Scatter(x=X, y=[7, 8, 9], line=dict(shape="hv"), name="c"),
            ]
        )
        found = selectors(fig)
        assert "nth-child(1)" in found[0]
        assert "nth-child(2)" in found[1]


class TestItComposesWithTheHiddenTraceRule:
    """#400 removes hidden traces; this removes empty ones. Both shift."""

    def test_a_hidden_and_an_empty_trace_together(self):
        fig = go.Figure(
            [
                line("a", [1, 2, 3]),
                go.Scatter(x=X, y=[4, 5, 6], mode="lines", name="h", visible=False),
                line("e"),
                line("c", [7, 8, 9]),
            ]
        )
        found = selectors(fig)
        # Two drawn traces, so two DOM nodes -- measured -- and the second
        # must be `nth-child(2)` despite being declared fourth.
        assert len(found) == 2
        assert "nth-child(1)" in found[0]
        assert "nth-child(2)" in found[1]


class TestTheGlSideStaysWellFormed:
    """The indices that are validated but never rendered.

    A WebGL layer emits no selectors at all, so a gl trace's position is never
    turned into CSS. It is still handed to the layer classes, which validate
    the list -- a duplicate or a negative index raises. Numbering gl traces
    from their own zero, and undrawn ones after the drawn ones, keeps that
    true by construction; this asserts it rather than leaving it reasoned
    about, since nothing downstream would complain if it broke.
    """

    def gl(self, name: str, y: list | None = None) -> go.Scattergl:
        if y is None:
            return go.Scattergl(x=[], y=[], mode="lines", name=name)
        return go.Scattergl(x=X, y=y, mode="lines", name=name)

    def test_an_empty_gl_trace_between_two_drawn_ones_does_not_raise(self):
        fig = go.Figure(
            [self.gl("a", [1, 2, 3]), self.gl("e"), self.gl("c", [7, 8, 9])]
        )
        layers = PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"]
        # A WebGL layer carries no selectors, so the assertion is that it
        # builds at all -- construction is where the validation lives.
        assert layers
        assert selectors(fig) == []

    def test_gl_and_svg_traces_are_numbered_independently(self):
        fig = go.Figure(
            [
                self.gl("gl-empty"),
                line("svg-a", [1, 2, 3]),
                self.gl("gl-b", [4, 5, 6]),
                line("svg-c", [7, 8, 9]),
            ]
        )
        found = selectors(fig)
        # Only the two svg traces are addressable, and they take the first
        # two positions in the `scatterlayer` -- the gl traces draw into the
        # canvas and occupy none of it.
        assert len(found) == 2
        assert "nth-child(1)" in found[0]
        assert "nth-child(2)" in found[1]


class TestATraceThatDrawsNothingFormsNoLayer:
    """A layer for an undrawn trace is not merely empty -- it crashes (#421).

    Plotly gives such a trace no group, so there is nothing to announce and
    nothing to highlight. The core does worse than ignore the layer: reading
    the state of a series with no points dereferences an undefined point in
    `LineTrace.text` and throws, and a throw out of trace construction
    propagates out of `Figure`, taking the whole render with it rather than
    the one layer (xability/maidr#905).

    The multi-trace paths already reached this answer inside
    `_drawn_line_series`; a lone trace bypassed it through the single-trace
    branches.
    """

    @pytest.mark.parametrize(
        "trace",
        [
            go.Scatter(x=[], y=[], mode="lines", name="a"),
            go.Scatter(x=[], y=[], mode="markers", name="a"),
            go.Scatter(x=[], y=[], stackgroup="one", name="a"),
            go.Scatter(x=[], y=[], line=dict(shape="hv"), name="a"),
        ],
        ids=["line", "markers", "area", "step"],
    )
    def test_a_lone_undrawn_trace_emits_no_layer(self, trace):
        layers = PlotlyMaidr(go.Figure([trace]))._flatten_maidr()["subplots"][0][0][
            "layers"
        ]
        assert layers == []

    def test_a_drawn_neighbour_still_gets_its_layer(self):
        fig = go.Figure([line("a", [1, 2]), line("e")])
        layers = PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"]
        assert len(layers) == 1
        assert len(layers[0]["data"]) == 1

    def test_no_layer_carries_an_empty_series(self):
        # The shape that throws in the core. Asserted over every layer rather
        # than the first, since the fallback factory builds them separately.
        fig = go.Figure([line("a", [1, 2]), line("e1"), line("e2")])
        for layer in PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"]:
            data = layer["data"]
            # `data` is a flat list of points for a single-series layer and a
            # list of series for a multi-series one. Both shapes have to be
            # checked: an empty series is the thing that throws, and in the
            # flat shape "empty" is the whole list.
            assert data, "a layer carries no data at all"
            series = data if isinstance(data[0], list) else [data]
            assert all(s for s in series), "a layer carries an empty series"

    def test_a_pie_is_not_mistaken_for_undrawn(self):
        # `draws_marks` reads `x`/`y`, and a pie carries neither. Scoping the
        # exclusion to the scatter family is what keeps it.
        fig = go.Figure([go.Pie(labels=["a", "b"], values=[1, 2])])
        layers = PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"]
        assert len(layers) == 1
        assert len(layers[0]["data"]) == 2

    def test_a_bar_with_no_data_forms_no_layer_either(self):
        # This exclusion is scatter-family only, so it never reached bars --
        # and the assertion here used to be `len(layers) == 1`, pinned so that
        # a later widening would be a deliberate choice rather than a side
        # effect. #636 is that choice: an empty bar layer is the same ghost
        # #421 named, and it is now dropped by payload rather than by family.
        #
        # The two answers are not interchangeable. `draws_marks()` still runs
        # here, because it does something a later filter cannot: it keeps the
        # *positions* of the surviving series contiguous. This only removes
        # the layer that would otherwise ship empty.
        fig = go.Figure([go.Bar(x=[], y=[], name="a")])
        layers = PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"]
        assert layers == []
