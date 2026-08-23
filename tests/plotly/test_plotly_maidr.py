from __future__ import annotations

import pytest

plotly = pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402


class TestPlotlyMaidr:
    """Integration tests for PlotlyMaidr."""

    def test_creates_plots_from_bar_fig(self, plotly_bar_fig):
        pm = PlotlyMaidr(plotly_bar_fig)
        assert len(pm._plots) == 1

    def test_creates_plots_from_scatter_fig(self, plotly_scatter_fig):
        pm = PlotlyMaidr(plotly_scatter_fig)
        assert len(pm._plots) == 1

    def test_creates_plots_from_line_fig(self, plotly_line_fig):
        pm = PlotlyMaidr(plotly_line_fig)
        assert len(pm._plots) == 1

    def test_creates_plots_from_box_fig(self, plotly_box_fig):
        pm = PlotlyMaidr(plotly_box_fig)
        assert len(pm._plots) == 1

    def test_creates_plots_from_heatmap_fig(self, plotly_heatmap_fig):
        pm = PlotlyMaidr(plotly_heatmap_fig)
        assert len(pm._plots) == 1

    def test_creates_plots_from_histogram_fig(self, plotly_histogram_fig):
        pm = PlotlyMaidr(plotly_histogram_fig)
        assert len(pm._plots) == 1

    def test_flatten_maidr_schema_structure(self, plotly_bar_fig):
        pm = PlotlyMaidr(plotly_bar_fig)
        schema = pm._flatten_maidr()

        assert "id" in schema
        assert "subplots" in schema
        assert len(schema["subplots"]) == 1
        assert len(schema["subplots"][0]) == 1
        assert "layers" in schema["subplots"][0][0]

    def test_render_returns_tag(self, plotly_bar_fig):
        pm = PlotlyMaidr(plotly_bar_fig)
        tag = pm.render()
        assert tag is not None

    def test_render_contains_plotly_js(self, plotly_bar_fig):
        pm = PlotlyMaidr(plotly_bar_fig)
        tag = pm.render()
        html_str = str(tag.get_html_string())
        assert "plotly" in html_str.lower()

    def test_render_contains_maidr_schema(self, plotly_bar_fig):
        pm = PlotlyMaidr(plotly_bar_fig)
        tag = pm.render()
        html_str = str(tag.get_html_string())
        assert "maidrSchema" in html_str
        assert "maidr.js" in html_str

    def test_save_html(self, plotly_bar_fig, tmp_path):
        pm = PlotlyMaidr(plotly_bar_fig)
        output = tmp_path / "test_plotly.html"
        result = pm.save_html(str(output))
        assert result is not None

    def test_multi_trace_figure(self):
        fig = go.Figure()
        fig.add_trace(go.Bar(x=["A", "B"], y=[1, 2]))
        fig.add_trace(go.Scatter(x=[1, 2], y=[3, 4], mode="markers"))
        fig.update_layout(title="Multi")

        pm = PlotlyMaidr(fig)
        assert len(pm._plots) == 2

    def test_creates_plots_from_pie_fig(self, plotly_pie_fig):
        pm = PlotlyMaidr(plotly_pie_fig)
        assert len(pm._plots) == 1

    def test_unsupported_trace_skipped(self):
        # A trace maidr cannot read is skipped without taking its neighbours
        # with it. `go.Sunburst` stands in for that here; the test used to use
        # `go.Violin`, which is now read as a `violin_box` + `violin_kde` pair
        # -- so it was pinning "violin is unsupported" rather than the
        # behaviour this test is named for.
        fig = go.Figure()
        fig.add_trace(go.Sunburst(labels=["a", "b"], parents=["", ""], values=[1, 2]))
        fig.add_trace(go.Bar(x=["A"], y=[1]))

        pm = PlotlyMaidr(fig)
        assert len(pm._plots) == 1

    def test_a_violin_beside_a_bar_is_read(self):
        # The other half of the change above: the violin that used to be
        # skipped now contributes its own pair of layers, and the bar beside
        # it is unaffected.
        fig = go.Figure()
        fig.add_trace(go.Violin(y=[1.0, 2.0, 3.0, 4.0]))
        fig.add_trace(go.Bar(x=["A"], y=[1]))

        types = [plot.type.value for plot in PlotlyMaidr(fig)._plots]

        assert types == ["violin_box", "violin_kde", "bar"]

    def test_dodged_bar_detection(self, plotly_dodged_fig):
        from maidr.core.enum.plot_type import PlotType
        from maidr.plotly.grouped_bar import PlotlyGroupedBarPlot

        pm = PlotlyMaidr(plotly_dodged_fig)
        assert len(pm._plots) == 1
        assert isinstance(pm._plots[0], PlotlyGroupedBarPlot)
        assert pm._plots[0].type == PlotType.DODGED

    def test_stacked_bar_detection(self, plotly_stacked_fig):
        from maidr.core.enum.plot_type import PlotType
        from maidr.plotly.grouped_bar import PlotlyGroupedBarPlot

        pm = PlotlyMaidr(plotly_stacked_fig)
        assert len(pm._plots) == 1
        assert isinstance(pm._plots[0], PlotlyGroupedBarPlot)
        assert pm._plots[0].type == PlotType.STACKED

    def test_multiline_merged_into_single_plot(self, plotly_multiline_fig):
        """Multiple line traces are merged into one PlotlyMultiLinePlot."""
        from maidr.plotly.multiline import PlotlyMultiLinePlot

        pm = PlotlyMaidr(plotly_multiline_fig)
        assert len(pm._plots) == 1
        assert isinstance(pm._plots[0], PlotlyMultiLinePlot)

        # Data should be list-of-lists with both lines
        data = pm._plots[0].schema["data"]
        assert len(data) == 2  # two lines

    def test_multibox_merged_into_single_plot(self):
        """Multiple box traces are merged into one PlotlyMultiBoxPlot."""
        import plotly.graph_objects as go
        from maidr.plotly.multibox import PlotlyMultiBoxPlot

        fig = go.Figure()
        fig.add_trace(go.Box(y=[1, 2, 3, 4, 5], name="A"))
        fig.add_trace(go.Box(y=[2, 3, 4, 5, 6], name="B"))
        fig.add_trace(go.Box(y=[3, 4, 5, 6, 7], name="C"))

        pm = PlotlyMaidr(fig)
        assert len(pm._plots) == 1
        assert isinstance(pm._plots[0], PlotlyMultiBoxPlot)

        data = pm._plots[0].schema["data"]
        assert len(data) == 3
        assert data[0]["z"] == "A"
        assert data[1]["z"] == "B"
        assert data[2]["z"] == "C"

    def test_single_box_not_merged(self, plotly_box_fig):
        """A single box trace should remain a regular PlotlyBoxPlot."""
        from maidr.plotly.box import PlotlyBoxPlot

        pm = PlotlyMaidr(plotly_box_fig)
        assert len(pm._plots) == 1
        assert isinstance(pm._plots[0], PlotlyBoxPlot)

    def test_single_bar_not_grouped(self, plotly_bar_fig):
        """A single bar trace should remain a regular BarPlot, not grouped."""
        from maidr.plotly.bar import PlotlyBarPlot

        pm = PlotlyMaidr(plotly_bar_fig)
        assert len(pm._plots) == 1
        assert isinstance(pm._plots[0], PlotlyBarPlot)


class TestPlotlyPieFigures:
    """A pie's selector is scoped by its position among the figure's pies.

    Plotly draws every pie into one figure-level ``pielayer`` rather than into
    a subplot group, so only ``PlotlyMaidr`` — which sees the whole figure —
    can say which trace group a given pie is. The factory cannot, which is why
    these go through ``PlotlyMaidr`` rather than the factory.
    """

    def test_pie_layer_data_is_flat(self, plotly_pie_fig):
        from maidr.core.enum.maidr_key import MaidrKey
        from maidr.plotly.pie import PlotlyPiePlot

        pm = PlotlyMaidr(plotly_pie_fig)
        assert isinstance(pm._plots[0], PlotlyPiePlot)

        data = pm._plots[0].schema[MaidrKey.DATA]
        assert all(isinstance(point, dict) for point in data)
        # Largest first: `sort` is plotly's default.
        assert [point[MaidrKey.X] for point in data] == [
            "Bananas",
            "Apples",
            "Cherries",
        ]

    def test_two_pies_get_their_own_positions(self):
        fig = go.Figure()
        fig.add_trace(go.Pie(labels=["A", "B"], values=[1, 2], domain={"x": [0, 0.5]}))
        fig.add_trace(go.Pie(labels=["C", "D"], values=[3, 4], domain={"x": [0.5, 1]}))

        pm = PlotlyMaidr(fig)
        selectors = [plot._get_selector() for plot in pm._plots]

        assert len(pm._plots) == 2
        assert "nth-child(1)" in selectors[0]
        assert "nth-child(2)" in selectors[1]

    def test_a_bar_does_not_shift_the_pie_position(self):
        # The bar is drawn into `.subplot.xy`, not into `.pielayer`, so it
        # occupies no trace group the pie's selector counts.
        fig = go.Figure()
        fig.add_trace(go.Bar(x=["A"], y=[1]))
        fig.add_trace(go.Pie(labels=["A", "B"], values=[1, 2]))

        pm = PlotlyMaidr(fig)
        pie = next(plot for plot in pm._plots if plot.type.value == "pie")

        assert len(pm._plots) == 2
        assert "nth-child(1)" in pie._get_selector()

    def test_donut_is_a_pie_layer(self):
        from maidr.plotly.pie import PlotlyPiePlot

        fig = go.Figure(go.Pie(labels=["A", "B"], values=[1, 2], hole=0.4))

        pm = PlotlyMaidr(fig)
        assert len(pm._plots) == 1
        assert isinstance(pm._plots[0], PlotlyPiePlot)

    def test_render_contains_the_pie_schema(self, plotly_pie_fig):
        pm = PlotlyMaidr(plotly_pie_fig)
        html_str = str(pm.render().get_html_string())

        assert '"type": "pie"' in html_str


class TestPlotlyPieAxisTitles:
    """A pie only borrows ``layout.xaxis``/``yaxis`` titles when it owns them.

    A pie has no axis pair, so it shares the default group with any cartesian
    trace that declares none either. Those titles describe that trace's axes,
    and announcing a bar's "Month" against a pie's slice labels is worse than
    the generic pair — it is confidently wrong rather than merely vague.
    """

    @staticmethod
    def _labels(fig, plot_type: str) -> tuple[str, str]:
        plot = next(
            plot for plot in PlotlyMaidr(fig)._plots if plot.type.value == plot_type
        )
        axes = plot.schema["axes"]
        return axes["x"]["label"], axes["y"]["label"]

    def test_a_lone_pie_takes_the_layout_titles(self):
        fig = go.Figure(go.Pie(labels=["A", "B"], values=[1, 2]))
        fig.update_layout(xaxis_title="Fruit", yaxis_title="Units")

        assert self._labels(fig, "pie") == ("Fruit", "Units")

    def test_another_domain_trace_does_not_take_the_titles_away(self):
        # A sunburst lands in the same default group as the pie for the same
        # reason the pie does -- neither names an axis -- so it has no claim
        # on those titles, and falling back here would lose a label the
        # author did write.
        fig = go.Figure()
        fig.add_trace(go.Pie(labels=["A", "B"], values=[1, 2]))
        fig.add_trace(
            go.Sunburst(labels=["a", "b"], parents=["", ""], values=[1, 2])
        )
        fig.update_layout(xaxis_title="Fruit", yaxis_title="Units")

        assert self._labels(fig, "pie") == ("Fruit", "Units")

    def test_a_pie_sharing_a_figure_with_a_bar_keeps_the_generic_pair(self):
        fig = go.Figure()
        fig.add_trace(go.Bar(x=["a", "b"], y=[1, 2]))
        fig.add_trace(go.Pie(labels=["A", "B"], values=[1, 2]))
        fig.update_layout(xaxis_title="Month", yaxis_title="Revenue")

        assert self._labels(fig, "pie") == ("Category", "Value")

    def test_the_bar_still_keeps_the_titles_that_are_its_own(self):
        fig = go.Figure()
        fig.add_trace(go.Bar(x=["a", "b"], y=[1, 2]))
        fig.add_trace(go.Pie(labels=["A", "B"], values=[1, 2]))
        fig.update_layout(xaxis_title="Month", yaxis_title="Revenue")

        assert self._labels(fig, "bar") == ("Month", "Revenue")


class TestPlotlyPieSubplotGrid:
    """A pie takes its grid cell from its own ``domain`` rectangle.

    Every pie in a figure shares one trace group, because a pie carries no
    axis pair to be grouped by — which is what its selector needs (see
    :class:`TestPlotlyPieFigures`) and what its *position* must not be taken
    from. Reading the group's cell instead collapsed a whole grid of pies into
    one subplot holding all of them as layers.
    """

    @staticmethod
    def _cells(fig) -> list[tuple[int, int]]:
        return [(plot.row_index, plot.col_index) for plot in PlotlyMaidr(fig)._plots]

    @staticmethod
    def _cell_of(fig, plot_type: str) -> tuple[int, int]:
        plot = next(
            plot for plot in PlotlyMaidr(fig)._plots if plot.type.value == plot_type
        )
        return plot.row_index, plot.col_index

    def test_two_pies_side_by_side_are_two_subplots(self):
        from plotly.subplots import make_subplots

        fig = make_subplots(
            rows=1, cols=2, specs=[[{"type": "domain"}, {"type": "domain"}]]
        )
        fig.add_trace(go.Pie(labels=["A", "B"], values=[1, 2]), row=1, col=1)
        fig.add_trace(go.Pie(labels=["C", "D"], values=[3, 4]), row=1, col=2)

        assert self._cells(fig) == [(0, 0), (0, 1)]

        subplots = PlotlyMaidr(fig)._flatten_maidr()["subplots"]
        assert len(subplots) == 1
        assert [len(cell["layers"]) for cell in subplots[0]] == [1, 1]

    def test_a_two_by_two_grid_of_pies_fills_every_cell(self):
        from plotly.subplots import make_subplots

        fig = make_subplots(rows=2, cols=2, specs=[[{"type": "domain"}] * 2] * 2)
        for row in (1, 2):
            for col in (1, 2):
                fig.add_trace(
                    go.Pie(labels=["A", "B"], values=[1, 2]), row=row, col=col
                )

        assert self._cells(fig) == [(0, 0), (0, 1), (1, 0), (1, 1)]

    def test_the_grid_still_numbers_the_pielayer_across_subplots(self):
        # `pie_position` counts the figure's pie traces, not its subplots:
        # plotly draws all four into one `pielayer` however they are placed.
        from plotly.subplots import make_subplots

        fig = make_subplots(rows=2, cols=2, specs=[[{"type": "domain"}] * 2] * 2)
        for row in (1, 2):
            for col in (1, 2):
                fig.add_trace(
                    go.Pie(labels=["A", "B"], values=[1, 2]), row=row, col=col
                )

        selectors = [plot._get_selector() for plot in PlotlyMaidr(fig)._plots]

        assert len(selectors) == 4
        assert all(
            f"nth-child({position})" in selector
            for position, selector in enumerate(selectors, start=1)
        )

    def test_a_pie_is_ordered_against_a_cartesian_subplot(self):
        # The pie is placed by a trace domain and the bar by an axis domain;
        # the two are fractions of the same figure, so the columns have to be
        # ordered against each other rather than each within its own kind.
        from plotly.subplots import make_subplots

        fig = make_subplots(
            rows=1, cols=2, specs=[[{"type": "domain"}, {"type": "xy"}]]
        )
        fig.add_trace(go.Pie(labels=["A", "B"], values=[1, 2]), row=1, col=1)
        fig.add_trace(go.Bar(x=["a", "b"], y=[1, 2]), row=1, col=2)

        assert self._cell_of(fig, "pie") == (0, 0)
        assert self._cell_of(fig, "bar") == (0, 1)

    def test_a_pie_right_of_a_cartesian_subplot_keeps_its_column(self):
        from plotly.subplots import make_subplots

        fig = make_subplots(
            rows=1, cols=2, specs=[[{"type": "xy"}, {"type": "domain"}]]
        )
        fig.add_trace(go.Bar(x=["a", "b"], y=[1, 2]), row=1, col=1)
        fig.add_trace(go.Pie(labels=["A", "B"], values=[1, 2]), row=1, col=2)

        assert self._cell_of(fig, "pie") == (0, 1)
        assert self._cell_of(fig, "bar") == (0, 0)

    def test_a_lone_pie_stays_in_the_first_cell(self):
        # An unplaced pie covers the whole figure, and a single-cell grid is
        # not a grid: it must not gain a subplot selector.
        fig = go.Figure(go.Pie(labels=["A", "B"], values=[1, 2]))

        assert self._cells(fig) == [(0, 0)]

        subplots = PlotlyMaidr(fig)._flatten_maidr()["subplots"]
        assert len(subplots) == 1 and len(subplots[0]) == 1
        assert "selector" not in subplots[0][0]


class TestPlotlyUnrenderedDomainTraces:
    """A domain trace maidr draws nothing for occupies no grid cell.

    Pies are placed by their own ``domain`` rectangle, and plotly gives one to
    every domain trace — ``go.Table``, ``go.Sunburst``, ``go.Treemap``,
    ``go.Indicator`` — including the ones maidr renders no layer for. Folding
    *their* rectangles into the figure's column universe would move the
    cartesian subplots beside them, changing where maidr places a figure that
    contains no pie at all. The grid describes what maidr can describe.
    """

    @staticmethod
    def _cells(fig) -> list[tuple[int, int]]:
        return [(plot.row_index, plot.col_index) for plot in PlotlyMaidr(fig)._plots]

    @pytest.mark.parametrize(
        "trace",
        [
            pytest.param(
                go.Table(header={"values": ["a"]}, cells={"values": [[1, 2]]}),
                id="table",
            ),
            pytest.param(go.Sunburst(labels=["a"], parents=[""]), id="sunburst"),
            pytest.param(go.Treemap(labels=["a"], parents=[""]), id="treemap"),
            # A `mode="number"` indicator only. One that draws a dial *is*
            # rendered as of #627's gauge tranche, so it takes a cell like
            # a pie -- asserted by the test below rather than here.
            pytest.param(go.Indicator(value=42, mode="number"), id="indicator"),
        ],
    )
    def test_it_does_not_shift_the_cartesian_subplot_beside_it(self, trace):
        # Without the scoping this bar lands in column 1, behind an empty
        # cell -- a placement change for a figure holding no pie.
        from plotly.subplots import make_subplots

        fig = make_subplots(
            rows=1, cols=2, specs=[[{"type": "domain"}, {"type": "xy"}]]
        )
        fig.add_trace(trace, row=1, col=1)
        fig.add_trace(go.Bar(x=["a", "b"], y=[1, 2]), row=1, col=2)

        assert self._cells(fig) == [(0, 0)]

    def test_an_indicator_that_draws_a_dial_does_take_a_cell(self):
        # The control for the `indicator` row above: the scoping is about
        # what maidr *renders*, not about the trace type. A gauge is a
        # domain trace maidr does draw a layer for, so its rectangle joins
        # the column universe and the bar beside it lands in column 1.
        from plotly.subplots import make_subplots

        fig = make_subplots(
            rows=1, cols=2, specs=[[{"type": "domain"}, {"type": "xy"}]]
        )
        fig.add_trace(
            go.Indicator(
                value=42, mode="gauge+number", gauge={"axis": {"range": [0, 100]}}
            ),
            row=1,
            col=1,
        )
        fig.add_trace(go.Bar(x=["a", "b"], y=[1, 2]), row=1, col=2)

        assert self._cells(fig) == [(0, 0), (0, 1)]

    def test_a_pie_beside_it_is_still_placed_by_its_own_domain(self):
        # The scoping is by trace type, not by "ignore trace domains": a pie
        # sharing a figure with an unrendered domain trace still gets its own
        # cell, and the two renderable layers are still ordered against each
        # other.
        from plotly.subplots import make_subplots

        fig = make_subplots(
            rows=1,
            cols=3,
            specs=[[{"type": "domain"}, {"type": "domain"}, {"type": "xy"}]],
        )
        fig.add_trace(
            go.Table(header={"values": ["a"]}, cells={"values": [[1, 2]]}),
            row=1,
            col=1,
        )
        fig.add_trace(go.Pie(labels=["A", "B"], values=[1, 2]), row=1, col=2)
        fig.add_trace(go.Bar(x=["a", "b"], y=[1, 2]), row=1, col=3)

        assert self._cells(fig) == [(0, 0), (0, 1)]


class TestPlotlyPieSubplotTitles:
    """``subplot_titles`` reach a pie, which has no axis pair to match on.

    ``make_subplots`` stores per-subplot titles as paper-referenced
    annotations centred over each subplot. The base class finds the right one
    by matching against the rectangle the subplot's axis domains describe —
    and a pie has no axes, so every pie in a figure reads the same default
    ``[0, 1]`` domain, anchors itself at the middle of the figure, and matches
    none of them.
    """

    @staticmethod
    def _titles(fig) -> list[str]:
        return [plot._get_title() for plot in PlotlyMaidr(fig)._plots]

    def test_each_pie_of_a_row_gets_its_own_title(self):
        from plotly.subplots import make_subplots

        fig = make_subplots(
            rows=1,
            cols=2,
            specs=[[{"type": "domain"}, {"type": "domain"}]],
            subplot_titles=("Q1", "Q2"),
        )
        fig.add_trace(go.Pie(labels=["A", "B"], values=[1, 2]), row=1, col=1)
        fig.add_trace(go.Pie(labels=["C", "D"], values=[3, 4]), row=1, col=2)

        assert self._titles(fig) == ["Q1", "Q2"]

    def test_each_pie_of_a_grid_gets_its_own_title(self):
        # Two columns and two rows: the row a title belongs to is as much a
        # part of the match as the column.
        from plotly.subplots import make_subplots

        fig = make_subplots(
            rows=2,
            cols=2,
            specs=[[{"type": "domain"}] * 2] * 2,
            subplot_titles=("Q1", "Q2", "Q3", "Q4"),
        )
        for row in (1, 2):
            for col in (1, 2):
                fig.add_trace(
                    go.Pie(labels=["A", "B"], values=[1, 2]), row=row, col=col
                )

        assert self._titles(fig) == ["Q1", "Q2", "Q3", "Q4"]

    def test_a_pie_beside_a_bar_takes_the_title_over_its_own_column(self):
        from plotly.subplots import make_subplots

        fig = make_subplots(
            rows=1,
            cols=2,
            specs=[[{"type": "xy"}, {"type": "domain"}]],
            subplot_titles=("Sales", "Share"),
        )
        fig.add_trace(go.Bar(x=["a", "b"], y=[1, 2]), row=1, col=1)
        fig.add_trace(go.Pie(labels=["A", "B"], values=[1, 2]), row=1, col=2)

        titles = {
            plot.type.value: plot._get_title() for plot in PlotlyMaidr(fig)._plots
        }
        assert titles == {"bar": "Sales", "pie": "Share"}

    def test_a_lone_pie_still_falls_back_to_the_figure_title(self):
        # An unplaced pie covers the whole figure and there are no subplot
        # annotations to match, so the figure-level title is the answer.
        fig = go.Figure(go.Pie(labels=["A", "B"], values=[1, 2]))
        fig.update_layout(title="Market share")

        assert self._titles(fig) == ["Market share"]


class TestPlotlyFigureMetadata:
    """Figure-wide layout title/subtitle mapped onto the top-level schema.

    The matplotlib counterpart lives in ``tests/core/test_figure_metadata.py``;
    the paths are asymmetric by design — matplotlib maps
    ``suptitle``/``supxlabel``/``supylabel`` to top-level ``title``/``axes``,
    while Plotly maps ``layout.title``/``layout.title.subtitle`` to
    ``title``/``subtitle`` (it has no figure-margin axis label artists).
    """

    def test_layout_title_and_subtitle_emitted(self):
        fig = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))
        fig.update_layout(
            title={
                "text": "Sales by Region",
                "subtitle": {"text": "Fiscal year 2025"},
            }
        )

        pm = PlotlyMaidr(fig)
        schema = pm._flatten_maidr()

        assert schema["title"] == "Sales by Region"
        assert schema["subtitle"] == "Fiscal year 2025"

    def test_title_without_subtitle(self):
        fig = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))
        fig.update_layout(title="Overview")

        pm = PlotlyMaidr(fig)
        schema = pm._flatten_maidr()

        assert schema["title"] == "Overview"
        assert "subtitle" not in schema

    def test_no_layout_title_omits_metadata(self):
        fig = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))

        pm = PlotlyMaidr(fig)
        schema = pm._flatten_maidr()

        assert "title" not in schema
        assert "subtitle" not in schema
        assert "id" in schema
        assert "subplots" in schema

    def test_whitespace_only_title_counts_as_unauthored(self):
        fig = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))
        fig.update_layout(
            title={"text": "   ", "subtitle": {"text": " \t "}}
        )

        pm = PlotlyMaidr(fig)
        schema = pm._flatten_maidr()

        assert "title" not in schema
        assert "subtitle" not in schema

    def test_multi_subplot_title_and_subtitle_emitted(self):
        """The lobby motivation case: layout title/subtitle on a
        make_subplots figure land at the top level next to the grid."""
        from plotly.subplots import make_subplots

        fig = make_subplots(rows=1, cols=2)
        fig.add_trace(go.Bar(x=["a", "b"], y=[1, 2]), row=1, col=1)
        fig.add_trace(go.Bar(x=["a", "b"], y=[3, 4]), row=1, col=2)
        fig.update_layout(
            title={
                "text": "Sales by Region",
                "subtitle": {"text": "Fiscal year 2025"},
            }
        )

        pm = PlotlyMaidr(fig)
        schema = pm._flatten_maidr()

        assert schema["title"] == "Sales by Region"
        assert schema["subtitle"] == "Fiscal year 2025"
        assert len(schema["subplots"]) == 1
        assert len(schema["subplots"][0]) == 2

    def test_figure_metadata_survives_html_embedding(self):
        """The top-level title/subtitle must round-trip through the
        `var maidrSchema = {...}` JSON embedded in the init script,
        which is the path the JS engine actually consumes for Plotly."""
        import json

        fig = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))
        fig.update_layout(
            title={
                "text": "Sales by Region",
                "subtitle": {"text": "Fiscal year 2025"},
            }
        )

        pm = PlotlyMaidr(fig)
        html_str = str(pm.render().get_html_string())

        marker = "var maidrSchema = "
        start = html_str.index(marker) + len(marker)
        embedded, _ = json.JSONDecoder().raw_decode(html_str[start:])

        assert embedded["title"] == "Sales by Region"
        assert embedded["subtitle"] == "Fiscal year 2025"
        assert embedded["id"] == pm.maidr_id

    def test_legacy_title_without_subtitle_attribute(self):
        """The getattr guard must handle plotly versions whose Title
        object predates the `subtitle` attribute (plotly.js < 2.35)."""
        from types import SimpleNamespace

        from maidr.core.enum.maidr_key import MaidrKey

        fig = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))
        pm = PlotlyMaidr(fig)

        class _LegacyTitle:
            text = "Overview"
            # deliberately no `subtitle` attribute

        pm._fig = SimpleNamespace(layout=SimpleNamespace(title=_LegacyTitle()))

        metadata = pm._figure_metadata()

        assert metadata == {MaidrKey.TITLE: "Overview"}
