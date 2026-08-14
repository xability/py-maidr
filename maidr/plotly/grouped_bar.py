from __future__ import annotations

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list


class PlotlyGroupedBarPlot(PlotlyPlot):
    """Extract data from multiple Plotly bar traces (dodged, stacked or
    normalised).

    The class does not branch on *plot_type*: every combination hands the
    traces' own ``x``/``y``/``fill`` through unchanged, and the type decides
    only how the MAIDR core reads them. Which one applies is worked out from
    ``layout.barmode`` and ``layout.barnorm`` by
    :meth:`~maidr.plotly.plotly_maidr.PlotlyMaidr._extract_plots`.

    Parameters
    ----------
    traces : list[dict]
        All bar trace dicts belonging to the group.
    layout : dict
        The Plotly figure layout.
    plot_type : PlotType
        ``PlotType.DODGED``, ``PlotType.STACKED`` or
        ``PlotType.NORMALIZED``.
    """

    def __init__(
        self,
        traces: list[dict],
        layout: dict,
        plot_type: PlotType,
        **kwargs: str,
    ) -> None:
        # Use the first trace for base class init (title / axes)
        super().__init__(traces[0], layout, plot_type, **kwargs)
        self._traces = traces

    def _get_selector(self) -> str:
        return f"{self._subplot_css_prefix()}.trace.bars .point > path"

    def _extract_plot_data(self) -> list[list[dict]]:
        """Return grouped bar data as a list-of-lists.

        Each inner list represents one group (hue value).  Every item has
        ``x``, ``fill`` (group name), and ``y`` keys.
        """
        data: list[list[dict]] = []

        for trace in self._traces:
            x_vals = as_list(trace.get("x"))
            y_vals = as_list(trace.get("y"))
            fill = trace.get("name", "")

            group: list[dict] = []
            for xv, yv in zip(x_vals, y_vals):
                group.append(
                    {
                        MaidrKey.X.value: self._to_native(xv),
                        MaidrKey.Z.value: str(fill),
                        MaidrKey.Y.value: self._to_native(yv),
                    }
                )
            data.append(group)

        return data
