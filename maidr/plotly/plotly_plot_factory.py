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
                # construction (and is exercised that way by the tests), the
                # same role the unscoped fallback plays in
                # ``PlotlyLinePlot._get_selector``.
                #
                # The "is this a connected line" test is shared with
                # ``_extract_plots`` through ``is_connected_line_trace`` rather
                # than spelled out twice, so the two cannot drift apart.
                #
                # A staircase is a scatter trace too — plotly varies
                # ``line.shape``, not the trace type — so the shape is the only
                # thing separating piecewise-constant data from an
                # interpolated line.
                if is_step_trace(trace):
                    from maidr.plotly.step import PlotlyStepPlot

                    return PlotlyStepPlot([trace], layout, **axis_kwargs)

                from maidr.plotly.line import PlotlyLinePlot

                return PlotlyLinePlot(trace, layout, **axis_kwargs)

            from maidr.plotly.scatter import PlotlyScatterPlot

            return PlotlyScatterPlot(trace, layout, **axis_kwargs)

        if trace_type == "box":
            from maidr.plotly.box import PlotlyBoxPlot

            return PlotlyBoxPlot(trace, layout, **axis_kwargs)

        if trace_type == "heatmap":
            from maidr.plotly.heatmap import PlotlyHeatmapPlot

            return PlotlyHeatmapPlot(trace, layout, **axis_kwargs)

        if trace_type == "histogram":
            from maidr.plotly.histogram import PlotlyHistogramPlot

            return PlotlyHistogramPlot(trace, layout, **axis_kwargs)

        return None
