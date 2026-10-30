from __future__ import annotations

import logging
from typing import Any

import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.box import (
    _build_box_selector,
    box_key,
    first_samples,
    _compute_stats,
    _has_precomputed_stats,
    _precomputed_box,
    _precomputed_labels,
    _precomputed_positions,
    _trace_is_horizontal,
    drawn_positions,
    in_drawn_order,
    named_with_trace,
    order_box_rows,
    placed_at,
)
from maidr.plotly.plotly_plot import PlotlyPlot, as_list

_logger = logging.getLogger(__name__)


class PlotlyMultiBoxPlot(PlotlyPlot):
    """Extract data from multiple Plotly box traces as one layer.

    Mirrors the matplotlib ``BoxPlot`` which collects all boxes on the
    same axes into a single MAIDR layer with a list of box stat dicts.

    Parameters
    ----------
    traces : list[dict]
        All box trace dicts belonging to the multi-box plot.
    layout : dict
        The Plotly figure layout.
    """

    def __init__(
        self,
        traces: list[dict],
        layout: dict,
        layer_positions: list[int] | None = None,
        **kwargs: str,
    ) -> None:
        super().__init__(traces[0], layout, PlotType.BOX, **kwargs)
        self._traces = traces
        # Each trace's zero-based group position in the boxlayer. Defaulted
        # to declaration order for the factory, which cannot see what else
        # shares the layer; `PlotlyMaidr` passes the measured ones.
        self._layer_positions = (
            list(layer_positions)
            if layer_positions is not None
            else list(range(len(traces)))
        )
        # All populated by _extract_plot_data before _get_selector runs: each
        # box's outlier counts and its trace and the key its marks are found
        # by (see `box_key`), in the order of the data, and how many boxes
        # each trace drew.
        self._outlier_counts: list[tuple[int, int]] = []
        self._marks: list[tuple[int, str]] = []
        self._boxes_per_trace: list[int] = []

    def _get_selector(self) -> list[dict]:
        """Return one structured selector per box, in the order of the data.

        Two indices per box, and both were wrong before (#395). A box is
        addressed by its trace's group in the ``boxlayer`` *and* by its
        position inside that group, because a trace with a categorical axis
        draws all of its boxes into one group.

        Numbering by trace alone also emitted the wrong *number* of
        selectors: two traces of two categories each produced four boxes of
        data and two selectors, so half the boxes addressed nothing while
        the frontend paired the rest positionally.

        Each box carries its trace and its key from :meth:`_extract_plot_data`,
        since the data is in the order the boxes are drawn across the layer,
        not trace by trace, and the key finds the box within its trace's group
        by its own samples (see :func:`box_key`).
        """
        prefix = self._subplot_css_prefix()
        selectors = []
        for (trace_index, key), (lower, upper) in zip(
            self._marks, self._outlier_counts
        ):
            group = (
                self._layer_positions[trace_index]
                if trace_index < len(self._layer_positions)
                else trace_index
            ) + 1
            selectors.append(_build_box_selector(prefix, group, key, lower, upper))
        return selectors

    def _is_horizontal(self) -> bool:
        """Detect if box traces are horizontal.

        Any one horizontal trace makes the layer horizontal; each is judged
        by its own form, precomputed or raw -- see `_trace_is_horizontal`.
        """
        return any(_trace_is_horizontal(trace) for trace in self._traces)

    def render(self) -> dict:
        schema = super().render()
        horizontal = self._is_horizontal()
        schema[MaidrKey.ORIENTATION] = "horz" if horizontal else "vert"
        order_box_rows(
            schema,
            horizontal=horizontal,
            y_reversed=self._axis_runs_backwards(self._yaxis_name),
        )
        return schema

    def _extract_plot_data(self) -> list[dict]:
        """Return box stats for all traces, in the order plotly draws them.

        Plotly gives each trace one group and draws that trace's boxes inside
        it, in the order they stand along the axis (see
        :func:`drawn_positions`), and grouped traces stand their boxes side by
        side at each category, the first trace's nearest the axis origin. The
        layer is read in that order, category by category, where it was read
        trace by trace: two traces grouped at Thu and Fri were walked Thu,
        Fri, Thu, Fri, the highlight jumping back across the chart halfway.
        Each box keeps its trace and its key (see :func:`box_key`) for its
        selector, and how many each trace drew is recorded for the callers
        that count them.

        A box grouped at a category is named with its trace as well,
        ``"Thu, Male"`` (see :func:`named_with_trace`), since the category
        alone named two boxes the same.
        """
        axis_name = self._yaxis_name if self._is_horizontal() else self._xaxis_name
        labels = [label for trace in self._traces for label in placed_at(trace)]
        drawn = drawn_positions(self, axis_name, labels)
        several = len(self._traces) > 1
        placed: list[tuple] = []
        self._boxes_per_trace = []

        for trace_index, trace in enumerate(self._traces):
            boxes = self._trace_boxes(trace, drawn, several)
            placed.extend(
                (stats, position, trace_index, box_key(first, place))
                for place, (stats, position, first) in enumerate(boxes, start=1)
            )
            self._boxes_per_trace.append(len(boxes))

        placed = in_drawn_order(placed, drawn)
        self._marks = [(trace_index, within) for _, _, trace_index, within in placed]
        all_boxes = [stats for stats, *_ in placed]

        # Record outlier counts so _get_selector can split them.
        self._outlier_counts = [
            (
                len(d.get(MaidrKey.LOWER_OUTLIER.value, [])),
                len(d.get(MaidrKey.UPPER_OUTLIER.value, [])),
            )
            for d in all_boxes
        ]
        return all_boxes

    def _trace_boxes(
        self, trace: dict, drawn: list | None, several: bool
    ) -> list[tuple]:
        """
        One trace's boxes, in the order plotly draws them in its group.

        Parameters
        ----------
        trace : dict
            The plotly box trace.
        drawn : list or None
            The layer's positions in drawn order, from
            :func:`drawn_positions`.
        several : bool
            Whether the layer holds more than one trace, so a box at a
            category is named with its trace too.

        Returns
        -------
        list of tuple
            ``(stats, position, first sample)`` for each box; the position is
            ``None`` for a lone box with no name to stand at, and the first
            sample ``None`` for a precomputed one.
        """
        y = trace.get("y", None)
        x = trace.get("x", None)
        name = trace.get("name", "")
        quartilemethod = trace.get("quartilemethod")

        # Pre-computed stats, drawn in the order the trace lists them. A box
        # announced as its category is named with its trace as well; one
        # named by number, `Sales 2`, already says which trace it is.
        if _has_precomputed_stats(trace):
            boxes = self._extract_precomputed(trace)
            for stats, position, _ in boxes:
                if several and stats.get(MaidrKey.Z.value) == str(position):
                    stats[MaidrKey.Z.value] = named_with_trace(position, name)
            return boxes

        # Grouped by position: `y` places a horizontal trace's boxes, `x`
        # a vertical one's, and the other array holds the samples.
        if x is not None and y is not None:
            positions, samples = (y, x) if _trace_is_horizontal(trace) else (x, y)
            boxes = self._extract_grouped(
                positions, samples, quartilemethod=quartilemethod, drawn=drawn
            )
            if several:
                for stats, position, _ in boxes:
                    stats[MaidrKey.Z.value] = named_with_trace(position, name)
            return boxes

        # Single box — data may be in y (vertical) or x (horizontal)
        data = y if y is not None else x
        if data is None:
            return []
        values = as_list(data)
        arr = np.array(values, dtype=float)
        stats = _compute_stats(arr, label=name, quartilemethod=quartilemethod)
        first = first_samples([None] * len(values), values).get(None)
        return [] if stats is None else [(stats, name or None, first)]

    def _extract_precomputed(self, trace: dict) -> list[tuple]:
        """
        Extract box stats from pre-computed values.

        Each box comes with where it stands (see `_precomputed_positions`),
        in the order the trace lists them, which is the order plotly draws
        them in.

        Only as many boxes are described as every statistic has a value for.
        The five arrays are decoded independently, so one of them failing --
        a corrupt typed-array spec comes back empty -- would otherwise leave
        the loop indexing past the end of it. A short layer is the same answer
        the rest of this module gives to data it cannot read; a crash would
        take the whole figure with it.

        A box whose quartiles are missing or out of order is dropped too,
        because plotly draws none there -- see `_precomputed_box`.
        """
        q1_vals = as_list(trace.get("q1"))
        median_vals = as_list(trace.get("median"))
        q3_vals = as_list(trace.get("q3"))
        lowerfence = as_list(trace.get("lowerfence")) or q1_vals
        upperfence = as_list(trace.get("upperfence")) or q3_vals

        count = min(
            len(q1_vals),
            len(median_vals),
            len(q3_vals),
            len(lowerfence),
            len(upperfence),
        )
        if count < len(median_vals):
            _logger.warning(
                "maidr: box has %d medians but only %d complete boxes; "
                "describing those and dropping the rest.",
                len(median_vals),
                count,
            )

        name = trace.get("name") or "box"
        announced = _precomputed_labels(trace, count)
        stands_at = _precomputed_positions(trace, count)
        results = []
        for i in range(count):
            box = _precomputed_box(
                self._to_native(q1_vals[i]),
                self._to_native(median_vals[i]),
                self._to_native(q3_vals[i]),
                self._to_native(lowerfence[i]),
                self._to_native(upperfence[i]),
                label=f"{name} {i + 1}",
                z=announced[i],
            )
            if box is not None:
                results.append((box, stands_at[i], None))
        return results

    def _extract_grouped(
        self,
        positions: Any,
        samples: Any,
        quartilemethod: str | None = None,
        drawn: list | None = None,
    ) -> list[tuple]:
        """
        Extract one box's stats per position -- see `PlotlyBoxPlot._extract_grouped`.

        Parameters
        ----------
        positions : Any
            Where each sample's box stands: ``x`` for a vertical trace, ``y``
            for a horizontal one.
        samples : Any
            The samples, from the other array.
        quartilemethod : str or None
            The trace's ``quartilemethod``.
        drawn : list or None
            The layer's positions in drawn order, from
            :func:`drawn_positions`, or ``None`` to keep the order they first
            appear in.

        Returns
        -------
        list of tuple
            ``(stats, position, first sample)`` for each position, in drawn
            order.
        """
        position_list = as_list(positions)
        sample_list = as_list(samples)
        first = first_samples(position_list, sample_list)
        groups: dict[Any, list] = {cat: [] for cat in dict.fromkeys(position_list)}
        for position, sample in zip(position_list, sample_list):
            groups[position].append(sample)
        categories = list(groups)
        if drawn is not None:
            categories = [position for position in drawn if position in groups]

        results = []
        for cat in categories:
            arr = np.array(groups[cat], dtype=float)
            stats = _compute_stats(arr, label=str(cat), quartilemethod=quartilemethod)
            if stats is not None:
                results.append((stats, cat, first.get(cat)))
        return results
