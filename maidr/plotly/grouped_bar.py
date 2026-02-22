from __future__ import annotations

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot


class PlotlyGroupedBarPlot(PlotlyPlot):
    """Extract data from multiple Plotly bar traces (dodged or stacked).

    Parameters
    ----------
    traces : list[dict]
        All bar trace dicts belonging to the group.
    layout : dict
        The Plotly figure layout.
    plot_type : PlotType
        Either ``PlotType.DODGED`` or ``PlotType.STACKED``.
    """

    def __init__(
        self,
        traces: list[dict],
        layout: dict,
        plot_type: PlotType,
    ) -> None:
        # Use the first trace for base class init (title / axes)
        super().__init__(traces[0], layout, plot_type)
        self._traces = traces

    def _extract_plot_data(self) -> list[list[dict]]:
        """Return grouped bar data as a list-of-lists.

        Each inner list represents one group (hue value).  Every item has
        ``x``, ``fill`` (group name), and ``y`` keys.
        """
        data: list[list[dict]] = []

        for trace in self._traces:
            x_vals = trace.get("x", [])
            y_vals = trace.get("y", [])
            fill = trace.get("name", "")

            group: list[dict] = []
            for xv, yv in zip(x_vals, y_vals):
                group.append(
                    {
                        MaidrKey.X.value: _to_native(xv),
                        MaidrKey.FILL.value: str(fill),
                        MaidrKey.Y.value: _to_native(yv),
                    }
                )
            data.append(group)

        return data


def _to_native(val):
    """Convert numpy scalars to native Python types."""
    if hasattr(val, "item"):
        return val.item()
    return val
