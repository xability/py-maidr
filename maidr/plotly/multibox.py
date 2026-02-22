from __future__ import annotations

from typing import Any

import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot


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

    def __init__(self, traces: list[dict], layout: dict) -> None:
        super().__init__(traces[0], layout, PlotType.BOX)
        self._traces = traces

    def _get_selector(self) -> str:
        return ".trace.boxes > path.box"

    def _is_horizontal(self) -> bool:
        """Detect if box traces are horizontal."""
        for trace in self._traces:
            if trace.get("orientation") == "h":
                return True
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
        """Return box stats for all traces as a flat list."""
        all_boxes: list[dict] = []

        for trace in self._traces:
            y = trace.get("y", None)
            x = trace.get("x", None)
            name = trace.get("name", "")

            # Pre-computed stats
            if "q1" in trace and "median" in trace:
                all_boxes.extend(self._extract_precomputed(trace))
                continue

            # Grouped by x
            if x is not None and y is not None:
                all_boxes.extend(self._extract_grouped(x, y))
                continue

            # Single box — data may be in y (vertical) or x (horizontal)
            data = y if y is not None else x
            if data is not None:
                arr = np.array(data, dtype=float)
                all_boxes.append(self._compute_stats(arr, label=name))

        return all_boxes

    def _extract_precomputed(self, trace: dict) -> list[dict]:
        """Extract box stats from pre-computed values."""
        q1_vals = trace.get("q1", [])
        median_vals = trace.get("median", [])
        q3_vals = trace.get("q3", [])
        lowerfence = trace.get("lowerfence", q1_vals)
        upperfence = trace.get("upperfence", q3_vals)

        results = []
        for i in range(len(median_vals)):
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

    def _extract_grouped(
        self, x: list[Any], y: list[Any]
    ) -> list[dict]:
        """Extract stats grouped by x categories."""
        x_list = list(x)
        y_list = list(y)
        categories = list(dict.fromkeys(x_list))
        groups: dict[Any, list] = {cat: [] for cat in categories}
        for xi, yi in zip(x_list, y_list):
            groups[xi].append(yi)

        results = []
        for cat in categories:
            arr = np.array(groups[cat], dtype=float)
            results.append(self._compute_stats(arr, label=str(cat)))
        return results

    def _compute_stats(self, arr: np.ndarray, label: str = "") -> dict:
        """Compute box plot statistics for a numeric array."""
        q1 = float(np.percentile(arr, 25))
        q2 = float(np.percentile(arr, 50))
        q3 = float(np.percentile(arr, 75))
        iqr = q3 - q1
        lower_fence = q1 - 1.5 * iqr
        upper_fence = q3 + 1.5 * iqr

        min_val = (
            float(np.min(arr[arr >= lower_fence]))
            if np.any(arr >= lower_fence)
            else q1
        )
        max_val = (
            float(np.max(arr[arr <= upper_fence]))
            if np.any(arr <= upper_fence)
            else q3
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
            result[MaidrKey.FILL.value] = label
        return result
