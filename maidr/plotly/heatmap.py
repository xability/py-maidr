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

    def _axis_runs_backwards(self, axis_name: str) -> bool:
        """Whether plotly draws an axis from its high end to its low one.

        True only when the author asked for a reversed axis. On y that means
        the first category is drawn at the top -- the idiom for showing a
        matrix in reading order -- where plotly ordinarily numbers a heatmap's
        rows from the bottom. On x it means the columns run right to left.

        Read from the declared layout rather than a resolved one, because
        there is no browser here to resolve it. That is why ``autorange`` is
        usable: it still carries the author's ``"reversed"`` verbatim, where
        the rendered figure would report a plain ``True`` for both the
        default and the reversed case.

        Parameters
        ----------
        axis_name : str
            The layout key for the axis, e.g. ``"yaxis"`` or ``"xaxis2"``.

        Returns
        -------
        bool
            True when the axis runs backwards.
        """
        axis = self._layout.get(axis_name, {})
        if not isinstance(axis, dict):
            return False

        if axis.get("autorange") == "reversed":
            return True

        axis_range = axis.get("range")
        if isinstance(axis_range, (list, tuple)) and len(axis_range) >= 2:
            try:
                return float(axis_range[0]) > float(axis_range[1])
            except (TypeError, ValueError):
                return False

        return False

    def _drawn_category_order(self, axis_name: str, labels: list) -> list[int] | None:
        """Where each of an axis's drawn categories sits in the trace's labels.

        ``categoryorder`` sorts a categorical axis and leaves the trace's own
        ``x``, ``y`` and ``z`` exactly as the author wrote them, so the labels
        alone do not say what the chart shows. This resolves the sort from the
        declared layout, in the order plotly lays the categories out from the
        axis origin -- left for x, bottom for y. It says nothing about a
        reversed axis, which flips the drawn direction without touching the
        order; :meth:`_axis_runs_backwards` answers that.

        Only the forms a declared spec can answer exactly are resolved:
        ``"array"`` with a ``categoryarray`` (which is what plotly express's
        ``category_orders`` compiles to) and the two ``"category"`` sorts. The
        aggregate orders -- ``total``, ``sum``, ``mean``, ``min``, ``max``,
        ``median`` -- are declined. They do apply to a heatmap, measured, but
        resolving them means reimplementing plotly's own aggregation and
        tie-breaking offline, and a sort that is subtly not plotly's would
        leave the chart confidently wrong in the same way reading the trace's
        order does. Leaving the sort unapplied is the smaller error.

        Parameters
        ----------
        axis_name : str
            The layout key for the axis, e.g. ``"xaxis"``.
        labels : list
            The labels the trace carries, in its own order.

        Returns
        -------
        list[int] | None
            Indices into ``labels`` in drawn order, or None to decline.
        """
        axis = self._layout.get(axis_name, {})
        if not isinstance(axis, dict):
            return None

        order = axis.get("categoryorder")
        declared = axis.get("categoryarray")
        # Measured: plotly resolves ``categoryorder`` to ``"array"`` whenever
        # ``categoryarray`` is non-empty and no order was declared, and draws
        # in it -- so a figure that sets only the array is still sorted. An
        # order that *was* declared wins over the array, empty or not.
        if order is None and isinstance(declared, (list, tuple)) and len(declared) > 0:
            order = "array"

        if order == "array":
            if not isinstance(declared, (list, tuple)):
                return None
            drawn = [str(v) for v in declared]
        elif order in ("category ascending", "category descending"):
            drawn = sorted(str(v) for v in labels)
            if order == "category descending":
                drawn.reverse()
        else:
            return None

        if len(drawn) != len(labels):
            # A ``categoryarray`` naming categories the trace does not carry
            # makes plotly draw empty columns, which ``points`` has no way to
            # say. Inventing or dropping one would be worse than leaving the
            # sort unapplied.
            return None

        position: dict[str, int] = {}
        for index, label in enumerate(labels):
            position.setdefault(str(label), index)
        # A repeated label leaves no unambiguous cell to send a category to.
        if len(position) != len(labels):
            return None

        resolved = []
        for name in drawn:
            index = position.get(name)
            if index is None:
                return None
            resolved.append(index)

        # A ``categoryarray`` that repeats an entry can name every label the
        # right number of times without being a permutation of them, which
        # would emit one column's values twice and lose another's.
        if len(set(resolved)) != len(labels):
            return None

        return resolved

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
