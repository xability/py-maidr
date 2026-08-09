from __future__ import annotations

import logging
from typing import Any

import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list

_logger = logging.getLogger(__name__)


def _build_box_selector(
    prefix: str,
    nth_child: int,
    box_sel: str,
    lower_count: int,
    upper_count: int,
) -> dict:
    """Build a ``BoxSelector``-compatible dict with split outlier selectors.

    Plotly renders outlier ``path.point`` elements in value-sorted order
    (ascending).  Lower outliers come first, upper outliers last.  We use
    CSS ``:nth-child(An+B of S)`` to address each group separately, the
    same technique matplotlib uses.
    """
    base = f"{prefix}.boxlayer > g:nth-child({nth_child}) .points"

    if lower_count > 0:
        lower_sel = [
            f"{base} > :nth-child(-n+{lower_count} of path.point)"
        ]
    else:
        lower_sel = []

    if upper_count > 0:
        upper_sel = [
            f"{base} > :nth-child(n+{lower_count + 1} of path.point)"
        ]
    else:
        upper_sel = []

    return {
        "lowerOutliers": lower_sel,
        "min": box_sel,
        "max": box_sel,
        "q2": box_sel,
        "iq": box_sel,
        "q1": box_sel,
        "q3": box_sel,
        "upperOutliers": upper_sel,
    }


class PlotlyBoxPlot(PlotlyPlot):
    """Extract data from a Plotly box trace."""

    def __init__(self, trace: dict, layout: dict, **kwargs: str) -> None:
        super().__init__(trace, layout, PlotType.BOX, **kwargs)
        # Populated by _extract_plot_data before _get_selector runs.
        self._outlier_counts: list[tuple[int, int]] = []

    def _get_selector(self) -> list[dict]:
        """Return structured per-box selectors with split outliers.

        Plotly renders outlier points in sorted ascending order, so lower
        outliers appear first in the DOM.  CSS ``:nth-child`` selectors
        split them the same way matplotlib does.
        """
        prefix = self._subplot_css_prefix()
        selectors: list[dict] = []
        num_boxes = max(len(self._outlier_counts), 1)
        for i in range(num_boxes):
            n = i + 1
            box_sel = f"{prefix}.boxlayer > g:nth-child({n}) > path.box"
            lower_count, upper_count = (
                self._outlier_counts[i]
                if i < len(self._outlier_counts)
                else (0, 0)
            )
            selectors.append(
                _build_box_selector(prefix, n, box_sel, lower_count, upper_count)
            )
        return selectors

    def _is_horizontal(self) -> bool:
        """Detect if this box trace is horizontal."""
        if self._trace.get("orientation") == "h":
            return True
        # Plotly uses x for horizontal when y is absent
        return self._trace.get("x") is not None and self._trace.get("y") is None

    def render(self) -> dict:
        schema = super().render()
        schema[MaidrKey.ORIENTATION] = (
            "horz" if self._is_horizontal() else "vert"
        )
        return schema

    def _extract_plot_data(self) -> list[dict]:
        # Plotly box traces can have pre-computed stats or raw data
        if self._has_precomputed_stats():
            data = self._extract_precomputed()
        else:
            data = self._extract_from_raw_data()
        # Record outlier counts so _get_selector can split them.
        self._outlier_counts = [
            (
                len(d.get(MaidrKey.LOWER_OUTLIER.value, [])),
                len(d.get(MaidrKey.UPPER_OUTLIER.value, [])),
            )
            for d in data
        ]
        return data

    def _has_precomputed_stats(self) -> bool:
        """Check if the trace has pre-computed quartile values."""
        return "q1" in self._trace and "median" in self._trace

    def _extract_precomputed(self) -> list[dict]:
        """
        Extract box stats from pre-computed values in the trace.

        Only as many boxes are described as every statistic has a value for.
        The five arrays are decoded independently, so one of them failing --
        a corrupt typed-array spec comes back empty -- would otherwise leave
        the loop indexing past the end of it. A short layer is the same answer
        the rest of this module gives to data it cannot read; a crash would
        take the whole figure with it.
        """
        q1_vals = as_list(self._trace.get("q1"))
        median_vals = as_list(self._trace.get("median"))
        q3_vals = as_list(self._trace.get("q3"))
        lowerfence = as_list(self._trace.get("lowerfence")) or q1_vals
        upperfence = as_list(self._trace.get("upperfence")) or q3_vals

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

        results = []
        for i in range(count):
            results.append(
                {
                    MaidrKey.LOWER_OUTLIER.value: [],
                    MaidrKey.MIN.value: self._to_native(lowerfence[i]),
                    MaidrKey.Q1.value: self._to_native(q1_vals[i]),
                    MaidrKey.Q2.value: self._to_native(median_vals[i]),
                    MaidrKey.Q3.value: self._to_native(q3_vals[i]),
                    MaidrKey.MAX.value: self._to_native(upperfence[i]),
                    MaidrKey.UPPER_OUTLIER.value: [],
                }
            )
        return results

    def _extract_from_raw_data(self) -> list[dict]:
        """Compute box plot statistics from raw data.

        Handles both vertical (data in ``y``) and horizontal (data in
        ``x``) orientations.
        """
        y = self._trace.get("y", None)
        x = self._trace.get("x", None)

        # If there's a grouping variable x, group by unique x values
        if x is not None and y is not None:
            return self._extract_grouped(x, y)

        # Single box — data may be in y (vertical) or x (horizontal)
        data = y if y is not None else x
        if data is not None:
            arr = np.array(as_list(data), dtype=float)
            stats = self._compute_stats(arr, label=self._trace.get("name", ""))
            return [stats] if stats is not None else []

        return []

    def _extract_grouped(self, x: list[Any], y: list[Any]) -> list[dict]:
        """Extract stats grouped by x categories."""
        x = as_list(x)
        y = as_list(y)
        # Preserve order of appearance
        categories = list(dict.fromkeys(x))
        groups: dict[Any, list] = {cat: [] for cat in categories}
        for xi, yi in zip(x, y):
            groups[xi].append(yi)

        results = []
        for cat in categories:
            arr = np.array(groups[cat], dtype=float)
            stats = self._compute_stats(arr, label=str(cat))
            if stats is not None:
                results.append(stats)
        return results

    def _compute_stats(self, arr: np.ndarray, label: str = "") -> dict | None:
        """
        Compute box plot statistics for a numeric array.

        Answers None for an empty array. Every quartile of a box with no
        samples is undefined -- `np.percentile` raises rather than inventing
        one -- and an array arrives empty when the samples behind it could not
        be read, a corrupt typed-array spec being the way that happens. The
        caller drops the box; letting the raise through would take the whole
        figure with it, including the layers that read perfectly well. The
        precomputed path bounds its loop for the same reason.
        """
        if arr.size == 0:
            _logger.warning(
                "maidr: box %r has no samples to summarise; dropping it.",
                label or "<unnamed>",
            )
            return None

        q1 = float(np.percentile(arr, 25))
        q2 = float(np.percentile(arr, 50))
        q3 = float(np.percentile(arr, 75))
        iqr = q3 - q1
        lower_fence = q1 - 1.5 * iqr
        upper_fence = q3 + 1.5 * iqr

        min_val = (
            float(np.min(arr[arr >= lower_fence])) if np.any(arr >= lower_fence) else q1
        )
        max_val = (
            float(np.max(arr[arr <= upper_fence])) if np.any(arr <= upper_fence) else q3
        )

        lower_outliers = sorted(float(v) for v in arr[arr < lower_fence])
        upper_outliers = sorted(float(v) for v in arr[arr > upper_fence])

        result = {
            MaidrKey.LOWER_OUTLIER.value: lower_outliers,
            MaidrKey.MIN.value: min_val,
            MaidrKey.Q1.value: q1,
            MaidrKey.Q2.value: q2,
            MaidrKey.Q3.value: q3,
            MaidrKey.MAX.value: max_val,
            MaidrKey.UPPER_OUTLIER.value: upper_outliers,
        }
        if label:
            result[MaidrKey.Z.value] = label
        return result
