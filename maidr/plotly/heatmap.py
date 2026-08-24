from __future__ import annotations

from typing import Any

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list, colorbar_title

class PlotlyHeatmapPlot(PlotlyPlot):
    """Extract data from a Plotly heatmap trace."""

    def __init__(
        self,
        trace: dict,
        layout: dict,
        *,
        layer_position: int = 0,
        **kwargs: str,
    ) -> None:
        """
        Parameters
        ----------
        trace : dict
            A plotly ``heatmap`` (or ``histogram2d``) trace dictionary.
        layout : dict
            The figure's layout dictionary.
        layer_position : int, optional
            This trace's zero-based position among the traces sharing the
            subplot's ``heatmaplayer``, from
            :func:`~maidr.plotly.candlestick.layer_position`. Defaults to the
            first, which is what a subplot with one image has.
        **kwargs : str
            Axis names and other options passed to :class:`PlotlyPlot`.
        """
        self._layer_position = layer_position
        super().__init__(trace, layout, PlotType.HEAT, **kwargs)

    def _get_selector(self) -> str:
        """Return the selector for this trace's own image.

        Plotly appends one ``<g class="hm">`` per image-drawing trace to the
        subplot's ``heatmaplayer``, in declaration order, and each holds
        exactly one ``<image>``. Until #647 this named
        ``.heatmaplayer image`` -- the first image on the subplot rather than
        this trace's -- so a subplot holding two of them had both layers
        outlining the first: a highlight that resolves to a real element and
        the wrong one.

        The group is what carries the position, not the image.
        ``image:nth-of-type(N)`` counts among an element's *siblings*, and
        each image is the only one inside its own ``g.hm``, so measured in
        Chromium on a subplot with two:
        ``image:nth-of-type(1)`` matched **both** and ``:nth-of-type(2)``
        matched none. ``g.hm:nth-of-type(N) image`` matched exactly one each.

        ``:nth-of-type`` counts by tag among all siblings rather than among
        the ones matching the class beside it, so it is exact only where the
        siblings are homogeneous -- the caution :meth:`contour's selector
        <maidr.plotly.contour.PlotlyContourPlot._get_selector>` spells out.
        Measured across five configurations (two heatmaps, either order of a
        heatmap and a ``histogram2d``, two ``histogram2d``, and a heatmap
        beside a contour), a ``heatmaplayer`` held nothing but ``g.hm``.
        """
        return (
            f"{self._subplot_css_prefix()}.heatmaplayer > "
            f"g.hm:nth-of-type({self._layer_position + 1}) image"
        )

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

        x_labels = [self._to_native(v) for v in as_list(x)] if x is not None else None
        y_labels = [self._to_native(v) for v in as_list(y)] if y is not None else None

        width = len(points[0]) if points else 0
        # A ragged grid has no column to move a value to, so nothing touches
        # its columns -- neither the sort below nor the reversal. Plotly would
        # not draw a rectangle from it either.
        rectangular = all(len(row) == width for row in points)

        y_backwards = self._axis_runs_backwards(self._yaxis_name)
        x_backwards = self._axis_runs_backwards(self._xaxis_name)

        # The trace's order is not necessarily the drawn one: ``categoryorder``
        # sorts an axis and leaves ``x``, ``y`` and ``z`` alone (#489). Both of
        # these count from the axis origin -- bottom for y, left for x.
        rows = list(range(len(points)))
        if y_labels is not None and len(y_labels) == len(rows):
            resolved = self._drawn_category_order(self._yaxis_name, y_labels)
            if resolved is not None:
                rows = resolved

        cols = list(range(width))
        if rectangular:
            if x_labels is not None and len(x_labels) == width:
                resolved = self._drawn_category_order(self._xaxis_name, x_labels)
                if resolved is not None:
                    cols = resolved
            # Inside the guard with the sort: reversing a ragged grid's columns
            # would index past the end of its short rows.
            if x_backwards:
                cols.reverse()

        # The schema's rows run top-first, and the core reverses them so its
        # own row 0 is the bottom of the drawn grid -- which is what makes
        # ArrowUp move visually up. So the rows turn over unless the y axis is
        # drawn reversed and already counts from the top (#487); the columns,
        # which start at the left, turn over only when the x axis is (#489).
        if not y_backwards:
            rows.reverse()

        # A row whose columns do not move keeps the list already built for it.
        columns_moved = any(col != index for index, col in enumerate(cols))
        points = [
            [points[row][col] for col in cols] if columns_moved else points[row]
            for row in rows
        ]

        result: dict = {MaidrKey.POINTS: points}

        # A label list that does not describe the grid cannot be permuted onto
        # it, so it keeps the plain reversal it would have had.
        if x_labels is not None:
            if len(x_labels) == width:
                result[MaidrKey.X] = [x_labels[col] for col in cols]
            elif x_backwards:
                result[MaidrKey.X] = list(reversed(x_labels))
            else:
                result[MaidrKey.X] = x_labels
        if y_labels is not None:
            if len(y_labels) == len(rows):
                result[MaidrKey.Y] = [y_labels[row] for row in rows]
            elif y_backwards:
                result[MaidrKey.Y] = y_labels
            else:
                result[MaidrKey.Y] = list(reversed(y_labels))

        return result

    def _extract_axes_data(self) -> dict:
        """Extract per-axis ``AxisConfig`` objects, including ``z`` for heatmaps.

        The ``z`` axis label is sourced from the trace's colorbar title
        (formerly emitted as ``axes.fill``). Emitted as a canonical
        ``AxisConfig`` dict ``{"label": ...}``.
        """
        base = super()._extract_axes_data()
        z_label = colorbar_title(self._trace)
        if z_label:
            base[MaidrKey.Z] = self._axis_config(label=z_label)
        return base
