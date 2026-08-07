"""WebGL traces have no element to highlight, and must not claim one.

A ``scattergl`` trace is painted into a shared ``<canvas>`` rather than drawn
as SVG. It was still given ``path.js-line`` / ``.point`` selectors, which
resolved to zero elements: correct audio, braille and text, no visible
highlight, and nothing in the output to say why.

The DOM facts asserted here were confirmed by rendering plotly's own bundle in
Chromium. With a ``scattergl`` trace declared before a ``scatter`` one, the
subplot's ``scatterlayer`` holds exactly **one** child — the SVG trace — so
``nth-child(1)`` matches the SVG line and ``nth-child(2)`` matches nothing.
That is why a gl trace must not occupy a position in the index either: doing
so pushed every SVG sibling one place along, onto a selector matching nothing.
"""

from __future__ import annotations

import pytest

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_maidr import PlotlyMaidr
from maidr.plotly.step_shape import renders_through_webgl

plotly = pytest.importorskip("plotly")
import plotly.graph_objects as go  # noqa: E402


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


class TestTheWebglPredicate:
    """Only the canvas-painted trace types report True."""

    def test_scattergl_renders_through_webgl(self):
        assert renders_through_webgl({"type": "scattergl"}) is True

    @pytest.mark.parametrize("trace_type", ["scatter", "bar", "box", "heatmap"])
    def test_svg_types_do_not(self, trace_type):
        assert renders_through_webgl({"type": trace_type}) is False

    def test_a_missing_type_reads_as_svg_scatter(self):
        # plotly's own default for an absent type is "scatter".
        assert renders_through_webgl({}) is False


class TestAWebglLayerClaimsNoHighlight:
    """The layer still carries data; it just does not promise a highlight."""

    def test_a_gl_line_emits_no_selector(self):
        fig = go.Figure()
        fig.add_scattergl(x=[0, 1, 2], y=[1, 2, 3], mode="lines")

        (layer,) = _layers(fig)

        assert layer[MaidrKey.TYPE] == PlotType.LINE
        assert MaidrKey.SELECTOR not in layer

    def test_a_gl_line_still_carries_its_data(self):
        # The point of dropping the selector is that the other three
        # modalities keep working -- this would be a regression, not a fix,
        # if the layer came out empty.
        fig = go.Figure()
        fig.add_scattergl(x=[0, 1, 2], y=[1, 2, 3], mode="lines")

        (layer,) = _layers(fig)

        assert len(layer[MaidrKey.DATA][0]) == 3

    def test_a_gl_step_emits_no_selector_but_keeps_its_direction(self):
        fig = go.Figure()
        fig.add_scattergl(
            x=[0, 1, 2], y=[1, 2, 3], mode="lines", line={"shape": "hv"}
        )

        (layer,) = _layers(fig)

        assert layer[MaidrKey.TYPE] == PlotType.STEP
        assert layer[MaidrKey.STEP_DIRECTION] == "hv"
        assert MaidrKey.SELECTOR not in layer

    def test_a_gl_scatter_emits_no_selector(self):
        # `.point` is as unmatched as `path.js-line` -- markers are painted to
        # the same canvas.
        fig = go.Figure()
        fig.add_scattergl(x=[0, 1, 2], y=[1, 2, 3], mode="markers")

        (layer,) = _layers(fig)

        assert layer[MaidrKey.TYPE] == PlotType.SCATTER
        assert MaidrKey.SELECTOR not in layer

    def test_two_gl_traces_on_one_subplot_do_not_collide(self):
        # Regression: gl traces are excluded from the SVG scatterlayer index,
        # and were once padded with a placeholder 0. Two of them on a subplot
        # therefore both got position 0 -- a duplicate, which the position
        # validator rejects, so the figure raised instead of exporting.
        # Numbering each renderer from its own zero makes them well-formed
        # without inventing an scatterlayer position a canvas trace has not
        # got.
        fig = go.Figure()
        fig.add_scattergl(x=[0, 1], y=[1, 2], mode="lines", name="a")
        fig.add_scattergl(x=[0, 1], y=[2, 1], mode="lines", name="b")

        (layer,) = _layers(fig)

        assert len(layer[MaidrKey.DATA]) == 2

    def test_three_gl_steps_of_one_convention_do_not_collide(self):
        # Same shape through the step path, which numbers per direction group.
        fig = go.Figure()
        for i in range(3):
            fig.add_scattergl(
                x=[0, 1],
                y=[i, i + 1],
                mode="lines",
                line={"shape": "hv"},
                name=f"s{i}",
            )

        (layer,) = _layers(fig)

        assert layer[MaidrKey.TYPE] == PlotType.STEP
        assert len(layer[MaidrKey.DATA]) == 3
        assert MaidrKey.SELECTOR not in layer

    def test_a_gl_multiline_emits_no_selectors(self):
        fig = go.Figure()
        fig.add_scattergl(x=[0, 1], y=[1, 2], mode="lines", name="a")
        fig.add_scattergl(x=[0, 1], y=[2, 1], mode="lines", name="b")

        (layer,) = _layers(fig)

        assert layer[MaidrKey.TYPE] == PlotType.LINE
        assert len(layer[MaidrKey.DATA]) == 2
        assert MaidrKey.SELECTOR not in layer


class TestAStandaloneLineIsGuardedToo:
    """
    The guard has to sit in ``PlotlyLinePlot`` itself, not only in the layer.

    A lone line is the one case that does not go through
    ``_scatter_line_selectors``, so its WebGL check is a separate line of
    code — and separate code is what drifts. Both directions are pinned here.

    These two previously exercised the unscoped ``scatter_position is None``
    fallback, which #311 removed: the parameter is required now, so there is
    no second path left to guard. They construct with a position instead.
    """

    def test_a_standalone_gl_line_emits_nothing(self):
        from maidr.plotly.line import PlotlyLinePlot

        plot = PlotlyLinePlot(
            {"type": "scattergl", "mode": "lines", "x": [0, 1], "y": [1, 2]},
            {},
            scatter_position=0,
        )

        assert plot._get_selector() == []
        assert MaidrKey.SELECTOR not in plot.schema

    def test_a_standalone_svg_line_still_gets_its_scoped_selector(self):
        from maidr.plotly.line import PlotlyLinePlot

        plot = PlotlyLinePlot(
            {"type": "scatter", "mode": "lines", "x": [0, 1], "y": [1, 2]},
            {},
            scatter_position=2,
        )

        (selector,) = plot._get_selector()

        assert "nth-child(3)" in selector
        assert selector.endswith("path.js-line")


class TestSvgTracesAreUnaffected:
    """The pre-existing SVG behaviour is untouched."""

    def test_an_svg_line_still_gets_its_selector(self):
        fig = go.Figure()
        fig.add_scatter(x=[0, 1, 2], y=[1, 2, 3], mode="lines")

        (layer,) = _layers(fig)

        assert "nth-child(1)" in layer[MaidrKey.SELECTOR][0]

    def test_an_svg_scatter_still_gets_its_selector(self):
        fig = go.Figure()
        fig.add_scatter(x=[0, 1, 2], y=[1, 2, 3], mode="markers")

        (layer,) = _layers(fig)

        assert layer[MaidrKey.SELECTOR].endswith(".point")


class TestAGlTraceDoesNotDisplaceItsSvgNeighbours:
    """
    The second half of the defect: a gl trace broke everyone else's highlight.

    Because a gl trace never enters the ``scatterlayer``, counting it in the
    position index shifted every SVG sibling one place along -- so declaring
    one ``scattergl`` trace silently disabled highlighting for the ordinary
    SVG traces beside it.
    """

    def test_an_svg_line_after_a_gl_line_is_still_the_first_child(self):
        fig = go.Figure()
        fig.add_scattergl(x=[0, 1, 2], y=[1, 2, 3], mode="lines", name="gl")
        fig.add_scatter(x=[0, 1, 2], y=[3, 2, 1], mode="lines", name="svg")

        layers = _layers(fig)
        svg = [x for x in layers if MaidrKey.SELECTOR in x]

        assert len(svg) == 1
        assert "nth-child(1)" in svg[0][MaidrKey.SELECTOR][0]

    def test_two_svg_lines_after_a_gl_line_number_from_one(self):
        fig = go.Figure()
        fig.add_scattergl(x=[0, 1], y=[1, 2], mode="lines", name="gl")
        fig.add_scatter(x=[0, 1], y=[2, 1], mode="lines", name="svg a")
        fig.add_scatter(x=[0, 1], y=[1, 3], mode="lines", name="svg b")

        layers = _layers(fig)
        multiline = next(
            x
            for x in layers
            if MaidrKey.SELECTOR in x and len(x[MaidrKey.SELECTOR]) == 2
        )

        assert "nth-child(1)" in multiline[MaidrKey.SELECTOR][0]
        assert "nth-child(2)" in multiline[MaidrKey.SELECTOR][1]

    def test_steps_of_one_convention_still_split_across_renderers(self):
        # Both steps share the `hv` convention, so grouping by convention
        # alone would merge them -- and the merged layer, holding a gl trace,
        # could then only claim a highlight for both or for neither. Splitting
        # by renderer first keeps the SVG step's highlight working.
        fig = go.Figure()
        fig.add_scattergl(
            x=[0, 1], y=[1, 2], mode="lines", line={"shape": "hv"}, name="gl"
        )
        fig.add_scatter(
            x=[0, 1], y=[2, 1], mode="lines", line={"shape": "hv"}, name="svg"
        )

        layers = _layers(fig)

        assert len(layers) == 2
        assert [x[MaidrKey.STEP_DIRECTION] for x in layers] == ["hv", "hv"]

        with_selector = [x for x in layers if MaidrKey.SELECTOR in x]
        assert len(with_selector) == 1
        assert "nth-child(1)" in with_selector[0][MaidrKey.SELECTOR][0]

    def test_a_gl_and_an_svg_step_of_different_conventions_split_cleanly(self):
        # Convention splitting still applies within a renderer, so this is
        # two layers for two reasons at once.
        fig = go.Figure()
        fig.add_scattergl(
            x=[0, 1], y=[1, 2], mode="lines", line={"shape": "hv"}, name="gl"
        )
        fig.add_scatter(
            x=[0, 1], y=[2, 1], mode="lines", line={"shape": "vh"}, name="svg"
        )

        layers = _layers(fig)
        gl_layer = next(x for x in layers if x[MaidrKey.STEP_DIRECTION] == "hv")
        svg_layer = next(x for x in layers if x[MaidrKey.STEP_DIRECTION] == "vh")

        assert MaidrKey.SELECTOR not in gl_layer
        assert "nth-child(1)" in svg_layer[MaidrKey.SELECTOR][0]

    def test_layers_follow_the_order_the_traces_were_declared_in(self):
        # Renderer groups are built in first-seen order, not svg-then-gl, so a
        # figure declaring its gl trace first keeps that ordering. Grouping in
        # a fixed order would pull MAIDR's navigation order out of step with
        # plotly's own trace and legend order.
        gl_first = go.Figure()
        gl_first.add_scattergl(x=[0, 1], y=[1, 2], mode="lines", name="gl")
        gl_first.add_scatter(x=[0, 1], y=[2, 1], mode="lines", name="svg")

        svg_first = go.Figure()
        svg_first.add_scatter(x=[0, 1], y=[2, 1], mode="lines", name="svg")
        svg_first.add_scattergl(x=[0, 1], y=[1, 2], mode="lines", name="gl")

        def names(fig):
            return [
                layer[MaidrKey.DATA][0][0][MaidrKey.Z] for layer in _layers(fig)
            ]

        assert names(gl_first) == ["gl", "svg"]
        assert names(svg_first) == ["svg", "gl"]

    def test_alternating_traces_group_coarsely_and_that_is_expected(self):
        # `svg, gl, svg` emits [svg, svg] then [gl] -- the gl trace does not
        # keep its middle position, because both svg traces belong to one
        # merged layer. That is inherent to merging at all, not a defect of
        # first-seen ordering, and `group_by_direction` already behaves the
        # same way for alternating step conventions. Pinned so the limitation
        # is explicit rather than discovered.
        fig = go.Figure()
        fig.add_scatter(x=[0, 1], y=[1, 2], mode="lines", name="svg a")
        fig.add_scattergl(x=[0, 1], y=[2, 1], mode="lines", name="gl")
        fig.add_scatter(x=[0, 1], y=[1, 3], mode="lines", name="svg b")

        layers = _layers(fig)
        series_names = [
            [series[0][MaidrKey.Z] for series in layer[MaidrKey.DATA]]
            for layer in layers
        ]

        assert series_names == [["svg a", "svg b"], ["gl"]]
        assert MaidrKey.SELECTOR in layers[0]
        assert MaidrKey.SELECTOR not in layers[1]

    def test_the_svg_pair_still_numbers_from_the_first_svg_child(self):
        # The consequence that actually matters: the gl trace sits between
        # them in declaration order but occupies no scatterlayer position, so
        # the two svg lines are children 1 and 2, not 1 and 3.
        fig = go.Figure()
        fig.add_scatter(x=[0, 1], y=[1, 2], mode="lines", name="svg a")
        fig.add_scattergl(x=[0, 1], y=[2, 1], mode="lines", name="gl")
        fig.add_scatter(x=[0, 1], y=[1, 3], mode="lines", name="svg b")

        svg_layer = _layers(fig)[0]

        assert "nth-child(1)" in svg_layer[MaidrKey.SELECTOR][0]
        assert "nth-child(2)" in svg_layer[MaidrKey.SELECTOR][1]

    def test_gl_lines_do_not_merge_into_the_svg_multiline_layer(self):
        # Two SVG lines still merge with each other; the gl line becomes its
        # own layer rather than joining them.
        fig = go.Figure()
        fig.add_scattergl(x=[0, 1], y=[1, 2], mode="lines", name="gl")
        fig.add_scatter(x=[0, 1], y=[2, 1], mode="lines", name="svg a")
        fig.add_scatter(x=[0, 1], y=[1, 3], mode="lines", name="svg b")

        layers = _layers(fig)
        svg_layer = next(x for x in layers if MaidrKey.SELECTOR in x)
        gl_layer = next(x for x in layers if MaidrKey.SELECTOR not in x)

        assert len(layers) == 2
        assert len(svg_layer[MaidrKey.DATA]) == 2
        assert len(gl_layer[MaidrKey.DATA]) == 1
