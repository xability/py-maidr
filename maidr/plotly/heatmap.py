from __future__ import annotations

from typing import Any

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list


class PlotlyHeatmapPlot(PlotlyPlot):
    """Extract data from a Plotly heatmap trace."""

    def __init__(self, trace: dict, layout: dict, **kwargs: str) -> None:
        super().__init__(trace, layout, PlotType.HEAT, **kwargs)

    def _get_selector(self) -> str:
        return f"{self._subplot_css_prefix()}.heatmaplayer image"

    @staticmethod
    def _to_native(val: Any) -> Any:
        """Convert numpy scalars to native Python types.

        Extends the base implementation to also convert numeric strings
        and non-numpy numeric types to floats.
        """
        if hasattr(val, "item"):
            return val.item()
        if isinstance(val, str):
            return val
        try:
            return float(val)
        except (TypeError, ValueError):
            return val

    def _draws_first_row_at_top(self) -> bool:
        """Whether plotly draws this trace's first row at the top.

        True only when the author asked for a reversed y axis, the idiom for
        showing a matrix in reading order. Ordinarily plotly numbers a
        heatmap's rows from the bottom.

        Read from the declared layout rather than a resolved one, because
        there is no browser here to resolve it. That is why ``autorange`` is
        usable: it still carries the author's ``"reversed"`` verbatim, where
        the rendered figure would report a plain ``True`` for both the
        default and the reversed case.

        Returns
        -------
        bool
            True when row 0 is already the top row.
        """
        yaxis = self._layout.get(self._yaxis_name, {})
        if not isinstance(yaxis, dict):
            return False

        if yaxis.get("autorange") == "reversed":
            return True

        axis_range = yaxis.get("range")
        if isinstance(axis_range, (list, tuple)) and len(axis_range) >= 2:
            try:
                return float(axis_range[0]) > float(axis_range[1])
            except (TypeError, ValueError):
                return False

        return False

    def _extract_plot_data(self) -> dict:
        # ``z`` is the one two-dimensional array a trace carries, so it is
        # also the one whose exported spec names a ``shape``; decoding it
        # restores the rows the loop below reads.
        z = as_list(self._trace.get("z"))
        x = self._trace.get("x", None)
        y = self._trace.get("y", None)

        # Convert z matrix to list of lists of native floats
        points = []
        for row in z:
            points.append([self._to_native(v) for v in row])

        # The schema's rows run top-first, and the core reverses them so its
        # own row 0 is the bottom of the drawn grid -- which is what makes
        # ArrowUp move visually up. Plotly numbers a heatmap's rows from the
        # bottom, so they are turned over here, unless the axis is drawn
        # reversed and already counts from the top (#487).
        top_first = self._draws_first_row_at_top()
        if not top_first:
            points.reverse()

        result: dict = {MaidrKey.POINTS: points}

        if x is not None:
            result[MaidrKey.X] = [self._to_native(v) for v in as_list(x)]
        if y is not None:
            y_labels = [self._to_native(v) for v in as_list(y)]
            if not top_first:
                y_labels.reverse()
            result[MaidrKey.Y] = y_labels

        return result

    def _extract_axes_data(self) -> dict:
        """Extract per-axis ``AxisConfig`` objects, including ``z`` for heatmaps.

        The ``z`` axis label is sourced from the trace's colorbar title
        (formerly emitted as ``axes.fill``). Emitted as a canonical
        ``AxisConfig`` dict ``{"label": ...}``.
        """
        base = super()._extract_axes_data()
        # Add z label from colorbar title if available
        colorbar = self._trace.get("colorbar", {})
        z_label = ""
        if isinstance(colorbar, dict):
            title = colorbar.get("title", "")
            if isinstance(title, dict):
                z_label = title.get("text", "")
            elif title:
                z_label = str(title)
        if z_label:
            base[MaidrKey.Z] = self._axis_config(label=z_label)
        return base
