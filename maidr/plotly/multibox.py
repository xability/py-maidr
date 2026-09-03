from __future__ import annotations

import logging
from typing import Any

import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.box import _build_box_selector
from maidr.plotly.plotly_plot import PlotlyPlot, as_list
from maidr.plotly.violin_stats import _QUANTILE_METHOD

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
            if "q1" in trace and "median" in trace:
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
            if "q1" in trace and "median" in trace:
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
                stats = self._compute_stats(
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
            stats = self._compute_stats(
                arr, label=str(cat), quartilemethod=quartilemethod
            )
            if stats is not None:
                results.append(stats)
        return results

    def _compute_stats(
        self,
        arr: np.ndarray,
        label: str = "",
        quartilemethod: str | None = None,
    ) -> dict | None:
        """
        Compute box plot statistics for a numeric array.

        The statistics are the ones plotly draws, not a textbook's: non-finite
        samples are skipped, and the quartiles follow the trace's
        ``quartilemethod`` the way plotly's box calc reads it.

        Answers None for an array with no finite samples. Every quartile of a
        box with no samples is undefined -- `np.percentile` raises rather than
        inventing one -- and an array arrives empty when the samples behind it
        could not be read, a corrupt typed-array spec being the way that
        happens. The caller drops the box; letting the raise through would take
        the whole figure with it, including the layers that read perfectly
        well. The precomputed path bounds its loop for the same reason.
        """
        # Plotly's box calc skips every sample that is not a number (its
        # `isNumeric` guard), so a `None` gap in the sample leaves the box it
        # draws untouched. Left in, the NaN it became would poison every
        # statistic and land as a bare `NaN` token in the schema. A box with
        # nothing finite in it is the same "no samples" case as an empty one.
        arr = arr[np.isfinite(arr)]
        if arr.size == 0:
            _logger.warning(
                "maidr: box %r has no samples to summarise; dropping it.",
                label or "<unnamed>",
            )
            return None

        # Hazen quartiles, the rule plotly's `Lib.interp` applies -- the same
        # constant the violin uses, measured there against plotly's calcdata.
        # numpy's default `linear` disagrees in the third significant figure,
        # and the fences and outliers all follow from q1/q3.
        q1, q2, q3 = (
            float(q) for q in np.percentile(arr, [25, 50, 75], method=_QUANTILE_METHOD)
        )
        # `quartilemethod="exclusive"`/`"inclusive"` only change plotly's
        # answer for an odd sample size: the median is left out of, or shared
        # by, the two halves whose medians become q1 and q3. An even sample
        # is Hazen whatever the method says. So is a single sample under
        # `exclusive`: its halves are empty, and plotly's `Lib.interp` on an
        # empty array answers `undefined` -- there is no drawn quartile to
        # match, and a NaN in the schema is worse than the value itself.
        if arr.size % 2 and quartilemethod in ("exclusive", "inclusive"):
            middle = arr.size // 2
            ordered = np.sort(arr)
            if quartilemethod == "exclusive":
                lower_half, upper_half = ordered[:middle], ordered[middle + 1 :]
            else:
                lower_half, upper_half = ordered[: middle + 1], ordered[middle:]
            if lower_half.size and upper_half.size:
                q1 = float(np.median(lower_half))
                q3 = float(np.median(upper_half))
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
            result[MaidrKey.Z.value] = label
        return result
