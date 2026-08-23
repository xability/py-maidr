from __future__ import annotations

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list

#: What the columns are, and what the numbers on them are. A parallel
#: coordinates plot draws no cartesian axes, so neither name can be read off
#: the layout -- and these are the trace's own vocabulary: `ParallelTrace`
#: holds an `axisMin`/`axisMax` per column and asks where each value sits on
#: *its own axis*.
_AXIS_FALLBACKS = ("Axis", "Value")


class PlotlyParcoordsPlot(PlotlyPlot):
    """Extract data from a Plotly ``parcoords`` trace.

    One polyline per observation crossing a row of vertical axes, each axis a
    different variable. The core builds `ParallelTrace` on `LineTrace`, so the
    payload is a line's -- a list of series, each a list of
    ``{x: axis name, y: value}`` -- and navigation, braille and text all
    transfer.

    What the trace adds is the reason the chart exists: **the columns are not
    one scale.** Miles per gallon beside horsepower beside weight share
    nothing except each value's position within its own axis, so
    `ParallelTrace` pitches each column against its own extent. That is a
    property of the trace type rather than of this payload -- all this has to
    do is hand over the columns in the order they are drawn, and name them.
    """

    def __init__(self, trace: dict, layout: dict, **kwargs: str) -> None:
        super().__init__(trace, layout, PlotType.PARALLEL, **kwargs)

    def _get_selector(self) -> list[str]:
        """No selector: plotly draws the observations to a WebGL canvas.

        Measured in Chromium on a two-axis ``go.Parcoords``: the page holds
        three ``<canvas>`` elements and the ``.parcoords`` group contains two
        ``<path>`` elements, neither of them an observation -- the axes, their
        ticks and their brush handles are the only SVG the chart draws.

        There is therefore nothing to point at. A `ParallelTrace` resolves one
        selector per observation, and no element in the document corresponds
        to one, so the layer ships without a highlight and keeps its audio,
        braille and text -- the outcome #145 established for a layer with
        nothing to point at.
        """
        return []

    def _extract_axes_data(self) -> dict:
        """Name the columns and the numbers on them.

        A ``parcoords`` has no cartesian axes, so ``layout.xaxis`` holds
        neither name -- reading it would take some other trace's titles, or
        the generic fallback where the author had in fact named these. Each
        column carries its own name on the point, which is what a reader is
        told when they arrive at it; these two say what those names and those
        numbers *are*.
        """
        x_label, y_label = _AXIS_FALLBACKS
        return {
            MaidrKey.X: self._axis_config(label=x_label),
            MaidrKey.Y: self._axis_config(label=y_label),
        }

    def _extract_plot_data(self) -> list[list[dict]]:
        """One series per observation, across the axes the chart draws.

        Two things decide which values are in it, and both were measured
        rather than assumed:

        * **A hidden dimension is not a column.** ``visible: False`` makes
          plotly draw no axis for it -- measured, the drawn axis titles were
          ``["A", "B"]`` with the middle dimension hidden -- so including it
          would announce a variable that is not on the chart.
        * **Ragged dimensions are truncated to the shortest.** Given columns
          of 3 and 2 values, plotly reported ``_length: 2`` for *both* and
          scaled the longer axis to its first two values only. So the third
          observation is not drawn at all, and reading it would announce a
          line that is not there.
        """
        columns = [
            dimension
            for dimension in as_list(self._trace.get("dimensions"))
            if isinstance(dimension, dict) and dimension.get("visible") is not False
        ]
        if not columns:
            return []

        values = [as_list(column.get("values")) for column in columns]
        rows = min(len(column) for column in values)
        if rows == 0:
            return []

        labels = [_column_name(column, index) for index, column in enumerate(columns)]
        return [
            [
                {
                    MaidrKey.X: label,
                    MaidrKey.Y: self._to_native(column[row]),
                }
                for label, column in zip(labels, values)
            ]
            for row in range(rows)
        ]


def is_parcoords_trace(trace: dict) -> bool:
    """Report whether a trace is a parallel coordinates plot."""
    return trace.get("type") == "parcoords"


def _column_name(dimension: dict, index: int) -> str:
    """Name one axis, falling back to its position when the author named none.

    ``label`` is optional and may be written empty, and plotly draws an
    unnamed axis with a blank title. A blank name reaches the reader as the
    one thing they cannot navigate by, so the position stands in -- the same
    answer a `dotchart` with no labels gives.
    """
    label = dimension.get("label")
    if label is None:
        return str(index + 1)
    label = str(label)
    return label if label else str(index + 1)
