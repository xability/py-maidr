from __future__ import annotations

import logging
from typing import Any

import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.box import (
    _build_box_selector,
    _compute_stats,
    _has_precomputed_stats,
    _precomputed_box,
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
        # Both populated by _extract_plot_data before _get_selector runs.
        self._outlier_counts: list[tuple[int, int]] = []
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
        """
        prefix = self._subplot_css_prefix()
        selectors = []
        box = 0
        for trace_index, count in enumerate(self._boxes_per_trace):
            group = (
                self._layer_positions[trace_index]
                if trace_index < len(self._layer_positions)
                else trace_index
            ) + 1
            for within in range(count):
                lower, upper = (
                    self._outlier_counts[box]
                    if box < len(self._outlier_counts)
                    else (0, 0)
                )
                selectors.append(
                    _build_box_selector(prefix, group, within + 1, lower, upper)
                )
                box += 1
        return selectors

    def _is_horizontal(self) -> bool:
        """Detect if box traces are horizontal.

        A precomputed trace reads its arrays the other way round from a raw
        one. Raw samples in ``x`` alone are the values of a horizontal box;
        but once ``q1``/``median``/``q3`` carry the values, a lone ``x`` is
        the *positions* of vertical boxes and a lone ``y`` the positions of
        horizontal ones -- plotly's box defaults, case ``"10"`` -> ``v`` and
        case ``"01"`` -> ``h``. Applying the raw rule to both swapped the
        announced value axis for every precomputed trace with one array.
        """
        for trace in self._traces:
            if trace.get("orientation") == "h":
                return True
            # With both a 1-D `x` and `y` (plotly's case "11") the trace sets no
            # orientation at all: plotly hides it and draws nothing, so the
            # fall-through `vert` below is a default, not a match.
            if _has_precomputed_stats(trace):
                if trace.get("y") is not None and trace.get("x") is None:
                    return True
                continue
            if trace.get("x") is not None and trace.get("y") is None:
                return True
        return False

    def render(self) -> dict:
        schema = super().render()
        schema[MaidrKey.ORIENTATION] = (
            "horz" if self._is_horizontal() else "vert"
        )
        return schema

    def _extract_plot_data(self) -> list[dict]:
        """Return box stats for all traces as a flat list.

        The list is trace-major and so is the DOM: plotly gives each trace
        one group and draws that trace's boxes inside it, in order. How many
        each trace contributed is recorded as it goes, because the selectors
        need it and it cannot be recovered afterwards -- a trace can draw one
        box or one per category, and a flat list of stats no longer says
        which.
        """
        all_boxes: list[dict] = []
        self._boxes_per_trace = []

        for trace in self._traces:
            y = trace.get("y", None)
            x = trace.get("x", None)
            name = trace.get("name", "")
            before = len(all_boxes)

            # Pre-computed stats
            if _has_precomputed_stats(trace):
                all_boxes.extend(self._extract_precomputed(trace))
                self._boxes_per_trace.append(len(all_boxes) - before)
                continue

            # Grouped by x
            if x is not None and y is not None:
                all_boxes.extend(
                    self._extract_grouped(
                        x, y, quartilemethod=trace.get("quartilemethod")
                    )
                )
                self._boxes_per_trace.append(len(all_boxes) - before)
                continue

            # Single box — data may be in y (vertical) or x (horizontal)
            data = y if y is not None else x
            if data is not None:
                arr = np.array(as_list(data), dtype=float)
                stats = _compute_stats(
                    arr, label=name, quartilemethod=trace.get("quartilemethod")
                )
                if stats is not None:
                    all_boxes.append(stats)
            self._boxes_per_trace.append(len(all_boxes) - before)

        # Record outlier counts so _get_selector can split them.
        self._outlier_counts = [
            (
                len(d.get(MaidrKey.LOWER_OUTLIER.value, [])),
                len(d.get(MaidrKey.UPPER_OUTLIER.value, [])),
            )
            for d in all_boxes
        ]
        return all_boxes

    def _extract_precomputed(self, trace: dict) -> list[dict]:
        """
        Extract box stats from pre-computed values.

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
        results = []
        for i in range(count):
            box = _precomputed_box(
                self._to_native(q1_vals[i]),
                self._to_native(median_vals[i]),
                self._to_native(q3_vals[i]),
                self._to_native(lowerfence[i]),
                self._to_native(upperfence[i]),
                label=f"{name} {i + 1}",
            )
            if box is not None:
                results.append(box)
        return results

    def _extract_grouped(
        self, x: list[Any], y: list[Any], quartilemethod: str | None = None
    ) -> list[dict]:
        """Extract stats grouped by x categories."""
        x_list = as_list(x)
        y_list = as_list(y)
        categories = list(dict.fromkeys(x_list))
        groups: dict[Any, list] = {cat: [] for cat in categories}
        for xi, yi in zip(x_list, y_list):
            groups[xi].append(yi)

        results = []
        for cat in categories:
            arr = np.array(groups[cat], dtype=float)
            stats = _compute_stats(arr, label=str(cat), quartilemethod=quartilemethod)
            if stats is not None:
                results.append(stats)
        return results
