from __future__ import annotations

from maidr.plotly.plotly_plot import PlotlyPlot


class PlotlyPlotFactory:
    """
    Factory that maps Plotly trace types to PlotlyPlot subclasses.

    For scatter traces, uses the ``mode`` attribute to disambiguate
    between scatter (markers) and line (lines) plots.
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
            mode = trace.get("mode", "markers")
            if "lines" in mode and "markers" not in mode:
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

        if trace_type == "candlestick":
            from maidr.plotly.candlestick import PlotlyCandlestickPlot

            return PlotlyCandlestickPlot(trace, layout, **axis_kwargs)

        return None
