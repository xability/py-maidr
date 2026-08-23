from __future__ import annotations

from maidr.plotly.plotly_plot import PlotlyPlot
from maidr.plotly.step_shape import is_connected_line_trace, is_step_trace


class PlotlyPlotFactory:
    """
    Factory that maps Plotly trace types to PlotlyPlot subclasses.

    For scatter traces, the drawing mode disambiguates loose markers from a
    connected line. That is resolved through
    :func:`maidr.plotly.step_shape.is_connected_line_trace` rather than read
    off the trace, because ``Figure.to_dict()`` omits ``mode`` when the author
    never set one — and an absent ``mode`` still draws a line.
    """

    @staticmethod
    def create(
        trace: dict,
        layout: dict,
        *,
        xaxis_name: str = "xaxis",
        yaxis_name: str = "yaxis",
    ) -> PlotlyPlot | None:
        """
        Create a PlotlyPlot instance from a Plotly trace dict.

        Parameters
        ----------
        trace : dict
            The Plotly trace dictionary (must include a "type" key).
        layout : dict
            The Plotly layout dictionary.
        xaxis_name : str
            Layout key for the x-axis (e.g., "xaxis", "xaxis2").
        yaxis_name : str
            Layout key for the y-axis (e.g., "yaxis", "yaxis2").

        Returns
        -------
        PlotlyPlot or None
            A concrete PlotlyPlot subclass, or None if the trace type
            is not supported.
        """
        axis_kwargs = {"xaxis_name": xaxis_name, "yaxis_name": yaxis_name}
        trace_type = trace.get("type", "scatter")

        if trace_type == "bar":
            from maidr.plotly.bar import PlotlyBarPlot

            return PlotlyBarPlot(trace, layout, **axis_kwargs)

        if trace_type in ("scatter", "scattergl"):
            if is_connected_line_trace(trace):
                # NOTE: this whole lines-mode branch is unreachable from
                # ``PlotlyMaidr``. ``_extract_plots`` consumes every
                # scatter/lines trace itself — steps, multi-line groups and a
                # lone line alike — because only it knows each trace's
                # position among its subplot's scatter traces, which the
                # selector needs. The branch is kept for direct/standalone
                # construction, and is exercised that way by the tests.
                #
                # The "is this a connected line" test is shared with
                # ``_extract_plots`` through ``is_connected_line_trace`` rather
                # than spelled out twice, so the two cannot drift apart.
                #
                # A staircase is a scatter trace too — plotly varies
                # ``line.shape``, not the trace type — so the shape is the only
                # thing separating piecewise-constant data from an
                # interpolated line.
                #
                # Position 0 is passed explicitly rather than left to a
                # default. This factory sees one trace with no idea what else
                # is on its subplot, so 0 — "assume it is the only scatter
                # trace" — is the only assumption available, and it belongs
                # here, visible, rather than hidden inside the three classes
                # where every other caller would inherit it silently.
                #
                # What it costs when the assumption is wrong: a direct caller
                # handing this factory one trace out of a multi-trace figure
                # used to get an unscoped selector that over-matched — wrong,
                # but visibly so. It now gets a confidently wrong one bound to
                # position 0. That is the failure mode this parameter exists
                # to remove, surviving in the single place that cannot know
                # better; `PlotlyMaidr` never reaches here precisely because
                # it does know, and passes real positions.
                if is_step_trace(trace):
                    from maidr.plotly.step import PlotlyStepPlot

                    return PlotlyStepPlot(
                        [trace], layout, scatter_positions=[0], **axis_kwargs
                    )

                from maidr.plotly.line import PlotlyLinePlot

                return PlotlyLinePlot(trace, layout, scatter_position=0, **axis_kwargs)

            from maidr.plotly.scatter import PlotlyScatterPlot

            return PlotlyScatterPlot(trace, layout, **axis_kwargs)

        if trace_type == "box":
            from maidr.plotly.box import PlotlyBoxPlot

            return PlotlyBoxPlot(trace, layout, **axis_kwargs)

        if trace_type in ("candlestick", "ohlc"):
            from maidr.plotly.candlestick import PlotlyCandlestickPlot

            # ``layer_position`` is left at its default for the same reason
            # the lines branch leaves ``scatter_position`` at 0: this factory
            # sees one trace with no idea what else shares its DOM layer, and
            # "assume it is the only one" is the only assumption available.
            # ``PlotlyMaidr`` never reaches here precisely because it does
            # know, and passes real positions.
            return PlotlyCandlestickPlot(trace, layout, **axis_kwargs)

        if trace_type == "heatmap":
            from maidr.plotly.heatmap import PlotlyHeatmapPlot

            return PlotlyHeatmapPlot(trace, layout, **axis_kwargs)

        if trace_type == "histogram":
            from maidr.plotly.histogram import PlotlyHistogramPlot

            return PlotlyHistogramPlot(trace, layout, **axis_kwargs)

        if trace_type == "sankey":
            from maidr.plotly.sankey import PlotlySankeyPlot

            # ``addressable`` is left at its default: this factory sees one
            # trace with no idea whether the figure holds a second sankey,
            # and "assume it is the only one" is the only assumption
            # available -- the same one the pie branch makes about position.
            return PlotlySankeyPlot(trace, layout, **axis_kwargs)

        if trace_type in ("treemap", "sunburst", "icicle"):
            from maidr.plotly.hierarchy import PlotlyHierarchyPlot, has_one_root

            # A many-rooted hierarchy is one plotly invents a parent for;
            # see `has_one_root`.
            if not has_one_root(trace):
                return None

            return PlotlyHierarchyPlot(trace, layout, **axis_kwargs)

        if trace_type == "indicator":
            from maidr.plotly.gauge import PlotlyGaugePlot, draws_a_dial

            # An indicator that draws no dial -- `mode="number"` -- or one
            # whose computed range runs backwards is not a chart this can
            # state; see `draws_a_dial`. Declined here rather than emitted
            # with a range invented for it.
            if not draws_a_dial(trace):
                return None

            # ``gauge_position`` is left at its default for the reason the
            # pie branch leaves its own: plotly draws every indicator into
            # one figure-level ``indicatorlayer``.
            return PlotlyGaugePlot(trace, layout, **axis_kwargs)

        if trace_type == "funnelarea":
            from maidr.plotly.funnelarea import PlotlyFunnelareaPlot

            # ``pie_position`` is left at its default for the reason the pie
            # branch below leaves its own: plotly draws every funnelarea into
            # one figure-level ``funnelarealayer``, and this factory sees one
            # trace with no idea what else the figure holds.
            return PlotlyFunnelareaPlot(trace, layout, **axis_kwargs)

        if trace_type == "funnel":
            from maidr.plotly.funnel import PlotlyFunnelPlot

            # ``layer_position`` is left at its default for the reason the
            # waterfall branch below leaves its own: this factory sees one
            # trace with no idea what else draws into the subplot's
            # ``funnellayer``.
            return PlotlyFunnelPlot(trace, layout, **axis_kwargs)

        if trace_type == "waterfall":
            from maidr.plotly.waterfall import PlotlyWaterfallPlot

            # ``layer_position`` is left at its default for the same reason
            # the candlestick branch leaves its own: this factory sees one
            # trace with no idea what else draws into the subplot's
            # ``waterfalllayer``, and "assume it is the only one" is the only
            # assumption available. ``PlotlyMaidr`` never reaches here
            # precisely because it does know, and passes real positions.
            return PlotlyWaterfallPlot(trace, layout, **axis_kwargs)

        if trace_type == "pie":
            from maidr.plotly.pie import PlotlyPiePlot

            # ``pie_position`` is left at its default here. Plotly draws every
            # pie into one figure-level ``pielayer``, so a pie's selector is
            # scoped by its position among *those* traces; this factory sees
            # one trace with no idea what else the figure holds, so "assume it
            # is the only pie" is the only assumption available — the same one
            # the lines branch above makes about scatter positions.
            # ``PlotlyMaidr`` never reaches here precisely because it does
            # know, and passes real positions.
            return PlotlyPiePlot(trace, layout, **axis_kwargs)

        return None
