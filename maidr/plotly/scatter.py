from __future__ import annotations

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot


class PlotlyScatterPlot(PlotlyPlot):
    """Extract data from a Plotly scatter trace with mode='markers'."""

    def __init__(self, trace: dict, layout: dict, **kwargs: str) -> None:
        super().__init__(trace, layout, PlotType.SCATTER, **kwargs)

    def _get_selector(self) -> str:
        return f"{self._subplot_css_prefix()}.trace.scatter .point"

    def _extract_axes_data(self) -> dict:
        """Extract axes data as canonical per-axis ``AxisConfig`` objects.

        Always returns per-axis objects with ``label`` (and ``format`` when
        available). When the grid navigation preconditions hold (linear
        scales, uniform ticks, valid bounds), ``min``, ``max``, and
        ``tickStep`` are additionally included on both axes. If any
        precondition fails, those numeric fields are omitted (silently
        disabling grid navigation) while still complying with the canonical
        axes shape.
        """
        xaxis = self._layout.get(self._xaxis_name, {})
        yaxis = self._layout.get(self._yaxis_name, {})

        # Get labels
        x_label = self._get_axis_label(xaxis, "X")
        y_label = self._get_axis_label(yaxis, "Y")

        # Per-axis format (nested into each AxisConfig).
        format_config = self._extract_format(xaxis, yaxis) or {}
        x_fmt = format_config.get("x")
        y_fmt = format_config.get("y")

        # Get range: explicit from layout OR compute from trace data
        x_data = self._trace.get("x", [])
        y_data = self._trace.get("y", [])
        x_min, x_max = self._get_axis_range(xaxis, x_data)
        y_min, y_max = self._get_axis_range(yaxis, y_data)

        # Get tick step from dtick (linear mode) or tickvals (array mode)
        x_tick_step = self._get_tick_step(xaxis)
        y_tick_step = self._get_tick_step(yaxis)

        # If grid config is invalid, emit bare AxisConfig objects (no
        # min/max/tickStep). This keeps the canonical per-axis shape.
        if not self._is_valid_grid_config(
            xaxis, yaxis, x_min, x_max, x_tick_step, y_min, y_max, y_tick_step
        ):
            return {
                MaidrKey.X: self._axis_config(label=x_label, format=x_fmt),
                MaidrKey.Y: self._axis_config(label=y_label, format=y_fmt),
            }

        return {
            MaidrKey.X: self._axis_config(
                label=x_label,
                min=float(x_min),
                max=float(x_max),
                tick_step=float(x_tick_step),
                format=x_fmt,
            ),
            MaidrKey.Y: self._axis_config(
                label=y_label,
                min=float(y_min),
                max=float(y_max),
                tick_step=float(y_tick_step),
                format=y_fmt,
            ),
        }

    @staticmethod
    def _get_axis_label(axis: dict, default: str) -> str:
        """Extract axis label from Plotly axis config."""
        title = axis.get("title", "")
        if isinstance(title, dict):
            title = title.get("text", "")
        return str(title) if title else default

    @staticmethod
    def _get_axis_range(axis: dict, data: list) -> tuple[float | None, float | None]:
        """Get axis range from layout or compute from data.

        Parameters
        ----------
        axis : dict
            Plotly axis configuration dict.
        data : list
            Data points for this axis from the trace.

        Returns
        -------
        tuple[float | None, float | None]
            (min, max) tuple, or (None, None) if unavailable.
        """
        # Try explicit range from layout first
        axis_range = axis.get("range")
        if axis_range and len(axis_range) >= 2:
            try:
                return float(axis_range[0]), float(axis_range[1])
            except (TypeError, ValueError):
                pass

        # Fall back to data min/max
        if data:
            try:
                numeric_data = [float(v) for v in data if v is not None]
                if numeric_data:
                    return min(numeric_data), max(numeric_data)
            except (TypeError, ValueError):
                pass

        return None, None

    @staticmethod
    def _get_tick_step(axis: dict) -> float | None:
        """Compute tick step from Plotly axis configuration.

        Parameters
        ----------
        axis : dict
            Plotly axis configuration dict.

        Returns
        -------
        float | None
            The tick interval if determinable, otherwise None.
        """
        # Method 1: dtick (if tickmode is 'linear' or dtick is explicitly set)
        dtick = axis.get("dtick")
        if dtick is not None:
            try:
                return float(dtick)
            except (TypeError, ValueError):
                pass

        # Method 2: Compute from tickvals (if tickmode is 'array')
        tickvals = axis.get("tickvals")
        if tickvals and len(tickvals) >= 2:
            try:
                vals = [float(v) for v in tickvals]
                diffs = [vals[i + 1] - vals[i] for i in range(len(vals) - 1)]
                # Check if uniformly spaced
                if diffs and all(abs(d - diffs[0]) < 1e-9 for d in diffs):
                    return diffs[0]
            except (TypeError, ValueError, IndexError):
                pass

        return None

    def _is_valid_grid_config(
        self,
        xaxis: dict,
        yaxis: dict,
        x_min: float | None,
        x_max: float | None,
        x_tick_step: float | None,
        y_min: float | None,
        y_max: float | None,
        y_tick_step: float | None,
    ) -> bool:
        """Validate that all grid navigation parameters are present and sane.

        Checks:
        - Both axes must be linear (not 'log', 'date', 'category').
        - All 6 numeric values present (not None).
        - min < max for both axes.
        - tickStep > 0 for both axes.
        - tickStep <= (max - min) for both axes (at least 1 bin).
        """
        # Both axes must be linear scale
        x_type = xaxis.get("type", "linear")
        y_type = yaxis.get("type", "linear")
        if x_type not in (None, "-", "linear") or y_type not in (None, "-", "linear"):
            return False

        # All values must be present
        if any(v is None for v in [x_min, x_max, x_tick_step, y_min, y_max, y_tick_step]):
            return False

        # min < max
        if x_min >= x_max or y_min >= y_max:
            return False

        # tickStep > 0
        if x_tick_step <= 0 or y_tick_step <= 0:
            return False

        # tickStep <= range (at least 1 bin)
        if x_tick_step > (x_max - x_min) or y_tick_step > (y_max - y_min):
            return False

        return True

    def _extract_plot_data(self) -> list[dict]:
        x = self._trace.get("x", [])
        y = self._trace.get("y", [])

        return [
            {MaidrKey.X: self._to_native(xv), MaidrKey.Y: self._to_native(yv)}
            for xv, yv in zip(x, y)
        ]
