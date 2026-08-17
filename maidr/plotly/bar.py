from __future__ import annotations

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, paired_axes


class PlotlyBarPlot(PlotlyPlot):
    """Extract data from a Plotly bar trace."""

    def __init__(self, trace: dict, layout: dict, **kwargs: str) -> None:
        super().__init__(trace, layout, PlotType.BAR, **kwargs)

    def _get_selector(self) -> str:
        return f"{self._subplot_css_prefix()}.trace.bars .point > path"

    def render(self) -> dict:
        """Add ``orientation`` to the base schema.

        `paired_axes` is symmetric, so a horizontal bar's measure already
        arrives in ``x`` -- which is the arrangement the core wants, but only
        once it has been told the layer is horizontal. Without the key it
        defaults to vertical and reads ``point.y``, which here is the category
        name: no magnitude to pitch, so every bar was silent, and the
        announcement gave the measure as the point's identity and the category
        as its value (#480).

        The same override `PlotlyHistogramPlot` carries, for the same reason --
        its trace extends this one in the core.
        """
        schema = super().render()
        schema[MaidrKey.ORIENTATION] = (
            "horz" if self._trace.get("orientation") == "h" else "vert"
        )
        return schema

    def _extract_plot_data(self) -> list[dict]:
        x, y = paired_axes(self._trace)

        return [
            {MaidrKey.X: self._to_native(xv), MaidrKey.Y: self._to_native(yv)}
            for xv, yv in zip(x, y)
        ]
