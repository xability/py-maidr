from __future__ import annotations

from typing import Any

import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.plotly.contour import PlotlyContourPlot
from maidr.plotly.histogram2d import binned_cells, cell_name
from maidr.plotly.plotly_plot import colorbar_title


class PlotlyHistogram2dContourPlot(PlotlyContourPlot):
    """Extract data from a Plotly ``histogram2dcontour`` trace.

    The last of #627's fifteen, and the one type that is two readings at
    once: it bins samples the way a ``histogram2d`` does and then draws the
    curves along which the *counts* are constant, the way a ``contour`` does.
    Both halves already exist, so this is where they meet -- the binning from
    :func:`~maidr.plotly.histogram2d.binned_cells`, everything after it from
    :class:`~maidr.plotly.contour.PlotlyContourPlot`, whose only overridable
    step is which grid the curves run through.

    Two things differ from a ``histogram2d`` reading the same samples, both
    measured against the browser:

    - **The grid is one bin wider at each automatic edge.** A contour needs
      somewhere for its curves to close, so plotly puts an empty bin outside
      the range it binned into. See
      :func:`~maidr.plotly.histogram2d.extended_edges`.
    - **The curves run through the bin centres**, not the edges. Plotly's own
      ``calcdata`` for this trace carries centres where a ``histogram2d``
      carries edges -- 5 coordinates for 5 bins rather than 4 edges for 3.

    The levels are then whatever :func:`~maidr.plotly.contour.levels_of`
    says, run over the binned counts: a default trace over counts of 0 .. 10
    draws levels 1 .. 9, which is the automatic rule applied to that range
    (measured, and the same nine plotly draws).
    """

    def _binned(self) -> tuple[list[list], Any, Any] | None:
        """The binning, worked out once.

        Both halves of the reading want it -- the curves want it with its
        gaps at zero and the levels want it with its gaps left out -- and
        the aggregating `histfunc`s reduce their cells in Python, so binning
        a large sample twice is real work for no answer that differs.
        """
        if getattr(self, "_binned_grid", None) is None:
            self._binned_grid = (binned_cells(self._trace, extended=True),)
        return self._binned_grid[0]

    def _field(self) -> tuple[list[float], list[float], Any] | None:
        """Bin the samples, and hand the counts over as the field.

        Returns
        -------
        tuple or None
            ``(x, y, z)`` with ``x`` and ``y`` the bin centres and ``z``
            the counts, bottom row first and zero where a cell has no answer
            -- see :func:`_traced`. None when there is nothing to bin, or
            when what was binned is too small to trace: marching squares
            needs a cell, which needs two rows and two columns.
        """
        binned = self._binned()
        if binned is None:
            return None

        cells, x_edges, y_edges = binned
        z = np.array(
            [[_traced(value) for value in row] for row in cells], dtype=float
        )
        if z.shape[0] < 2 or z.shape[1] < 2:
            return None

        return _centres(x_edges), _centres(y_edges), z

    def _level_field(self, z: Any) -> Any:
        """The binned cells with their gaps left out, not filled with zeros.

        The tracer reads a gap as zero (see :func:`_traced`), but plotly does
        not let those zeros decide the levels: measured on a sparse
        ``histfunc="avg"`` grid whose four filled cells run 3.5 .. 19, plotly
        reports a range of exactly 3.5 to 19 and draws levels 4 .. 18. Handing
        the filled grid to the level rule instead puts the range at 0 .. 19
        and draws 2 .. 16 -- eight levels, none of which is a level on the
        chart, on a reading whose curves would then be right.
        """
        binned = self._binned()
        if binned is None:
            return z

        cells, _, _ = binned
        return np.array(
            [
                [np.nan if value is None else value for value in row]
                for row in cells
            ],
            dtype=float,
        )

    def _extract_axes_data(self) -> dict:
        """Name the third axis for what the levels actually count.

        A plain ``contour``'s levels are the author's own numbers, so only
        the author can say what they are and the parent emits no ``z`` unless
        they titled the colour bar. These levels are computed here, so their
        name is known -- and leaving it unsaid would announce a chart of bare
        numbers with no word for what they count. The same reading a
        ``histogram2d`` settled for its cells, and the same order of
        precedence: the author's colour bar title first.
        """
        axes = super()._extract_axes_data()
        label = colorbar_title(self._trace) or cell_name(self._trace)
        axes.setdefault(MaidrKey.Z, self._axis_config(label=label))
        return axes


def is_histogram2dcontour_trace(trace: dict) -> bool:
    """Report whether a trace is a two-dimensional histogram's contour."""
    return trace.get("type") == "histogram2dcontour"


def _traced(value: Any) -> float:
    """One cell as the tracer reads it: a missing one is **zero**.

    An aggregating ``histfunc`` leaves a cell nothing landed in with no
    answer, and the heatmap reading of the same binning announces that as
    ``None`` -- there is no average of nothing (#645). The contour reading
    cannot: plotly hands the grid straight to a tracer written in JavaScript,
    where a ``null`` compares as below every level and adds as zero, so the
    curves are the curves of a field with zeros in the gaps.

    Measured rather than assumed, and it is not a small difference. A sparse
    ``histfunc="avg"`` grid whose four filled cells run 3.5 .. 19 draws ten
    curves across eight levels in the browser; read as a field with holes in
    it, ``contourpy`` finds five and misses the top three levels entirely.
    With the gaps at zero the two agree, curve for curve -- on that grid, on
    the same grid negated, and on a ``min`` of negative values, where zero is
    *above* every level rather than below and the agreement holds anyway.

    Note that this is the tracer's reading, not the chart's: plotly does
    interpolate a hole in a ``go.Contour``'s own ``z`` before tracing it
    (measured -- a punched cell comes back filled in ``calcdata``), but a
    ``histogram2dcontour``'s grid never goes through that step. Its
    ``_emptypoints`` is empty and its ``calcdata`` keeps the nulls.
    """
    return 0.0 if value is None or not np.isfinite(value) else float(value)


def _centres(edges: np.ndarray) -> list[float]:
    """The middle of each bin, which is where plotly puts the grid's points."""
    return [
        float((edges[index] + edges[index + 1]) / 2)
        for index in range(len(edges) - 1)
    ]
