from __future__ import annotations

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, paired_axes


class PlotlyFunnelPlot(PlotlyPlot):
    """Extract data from a Plotly funnel trace.

    A funnel is a population shrinking across ordered stages, and the core
    reads it as a bar layer with one difference that decides whether the
    chart is legible: the number pitched is the **retention** between
    adjacent stages rather than the count. `FunnelTrace` computes that from
    `barValues`, so the payload here is a bar's -- one point per stage, plus
    the `orientation` that says which field holds the stage name.

    Which way a funnel is drawn is not the same question plotly's bar traces
    answer. Measured in Chromium against ``gd._fullData[0].orientation``:

    ==========================  =========================================
    written                     plotly draws
    ==========================  =========================================
    ``y=stages, x=counts``      ``h``
    ``x=stages, y=counts``      ``h`` -- the stage names land on the value
                                axis and the chart is nonsense, but that is
                                plotly's reading of it, not ours to correct
    ``x=counts`` alone          ``h``
    ``y=counts`` alone          ``v``
    ==========================  =========================================

    So the default is horizontal whenever the trace carries an ``x`` at all,
    which is the opposite of the vertical default a bar layer takes.
    """

    def __init__(
        self, trace: dict, layout: dict, *, layer_position: int = 0, **kwargs: str
    ) -> None:
        super().__init__(trace, layout, PlotType.FUNNEL, **kwargs)
        self._layer_position = layer_position

    def _get_selector(self) -> str:
        """Address this trace's stages inside the subplot's funnel layer.

        ``.funnellayer`` rather than ``.trace.bars`` alone: plotly draws a
        funnel into its own ``mlayer`` and reuses the same inner class names
        there, so the bare form matched a bar chart's bars as well (#628).

        ``nth-of-type`` picks this trace out of the layer. Measured on two
        funnels sharing a subplot, ``.funnellayer .trace .point > path``
        resolved to 4 -- both traces' stages together -- so a layer without
        the position would claim its neighbour's.
        """
        return (
            f"{self._subplot_css_prefix()}.funnellayer "
            f".trace.bars:nth-of-type({self._layer_position + 1}) .point > path"
        )

    def render(self) -> dict:
        """Add ``orientation`` to the base schema.

        `FunnelTrace` extends the bar trace, so it reads the stage name off
        ``point.x`` when the layer is vertical and ``point.y`` when it is
        horizontal. Without the key the layer defaults to vertical, and a
        horizontal funnel -- which is what plotly draws unless told otherwise
        -- would announce the count as the stage's identity and the stage
        name as its value, the same failure #480 was about for bars.
        """
        schema = super().render()
        schema[MaidrKey.ORIENTATION] = "horz" if self._is_horizontal() else "vert"
        return schema

    def _is_horizontal(self) -> bool:
        """Report whether plotly draws this funnel across the page.

        Read from the trace when the author set it, and otherwise from
        whether the trace carries an ``x`` at all -- the rule measured above.
        A bar's ``get("orientation") == "h"`` test cannot be reused, because
        its "absent means vertical" default is the wrong way round here.
        """
        orientation = self._trace.get("orientation")
        if orientation is not None:
            return orientation == "h"
        return self._trace.get("x") is not None

    def _extract_plot_data(self) -> list[dict]:
        """One point per stage, in the order plotly draws them.

        `paired_axes` is symmetric, so a horizontal funnel's counts already
        arrive in ``x`` and its stage names in ``y`` -- which is the
        arrangement the core wants once it has been told the layer is
        horizontal.

        The stages are read in the trace's own order rather than through
        ``_drawn_category_order``. A funnel's axis is its sequence: the whole
        chart is "this many entered, this many got to the next step", and
        sorting the stages by name would be sorting away the thing it says.
        """
        x, y = paired_axes(self._trace)
        return [
            {MaidrKey.X: self._to_native(xv), MaidrKey.Y: self._to_native(yv)}
            for xv, yv in zip(x, y)
        ]
