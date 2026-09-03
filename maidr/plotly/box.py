from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list
from maidr.plotly.violin_stats import QUANTILE_METHOD

_logger = logging.getLogger(__name__)


def _build_box_selector(
    prefix: str,
    group: int,
    box: int,
    lower_count: int,
    upper_count: int,
) -> dict:
    """Build a ``BoxSelector``-compatible dict with split outlier selectors.

    A box needs *two* indices, not one. Plotly gives each trace one
    ``<g>`` in the ``boxlayer`` and draws that trace's boxes as direct
    ``path.box`` children of it, so a categorical trace puts every one of
    its boxes inside a single group. Numbering boxes as though each were
    its own group -- which this did -- made box 1 match all of them and
    boxes 2..n match nothing (#395).

    Measured in Chromium: one ``go.Box`` over three categories produces one
    group in the ``boxlayer`` holding three ``path.box`` children and three
    ``g.points`` children, and the *j*-th of each pair up positionally --
    including an empty ``g.points`` for a category with no outliers, which
    is what keeps the pairing positional rather than a count of which
    categories happen to have any.

    The group is matched by position rather than by class. A candlestick's
    group in this layer is built the same way, so a class would not tell the
    two apart; ``layer_position`` counts both types for that reason, and the
    index it returns is what distinguishes them.

    Plotly renders outlier ``path.point`` elements in value-sorted order
    (ascending). Lower outliers come first, upper outliers last. We use
    CSS ``:nth-child(An+B of S)`` to address each group separately, the
    same technique matplotlib uses.

    Parameters
    ----------
    prefix : str
        The subplot CSS prefix.
    group : int
        One-based position of the trace's ``<g>`` among the ``boxlayer``'s
        children -- ``layer_position`` + 1, so a candlestick sharing the
        layer is counted.
    box : int
        One-based position of this box among its own trace's boxes.
    lower_count, upper_count : int
        How many outliers fall below and above the whiskers.
    """
    group_sel = f"{prefix}.boxlayer > g:nth-child({group})"
    box_sel = f"{group_sel} > :nth-child({box} of path.box)"
    base = f"{group_sel} > :nth-child({box} of g.points)"

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


def _has_precomputed_stats(trace: dict) -> bool:
    """Return whether *trace* carries its quartiles rather than its samples.

    Plotly's own signature for the form (``_hasPreCompStats``): ``q1``,
    ``median`` and ``q3`` all present and non-empty; a trace missing any of
    the three is read as a raw sample. Both extractors branch on it in more
    than one place, so it is spelled once.
    """
    for key in ("q1", "median", "q3"):
        value = trace.get(key)
        # Sized rather than truthy: a numpy array raises on ``bool()``.
        if value is None or not hasattr(value, "__len__") or len(value) == 0:
            return False
    return True


def _is_finite_number(value: Any) -> bool:
    """Return whether *value* is a number plotly's ``isNumeric`` would take."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def _precomputed_box(
    q1: Any,
    median: Any,
    q3: Any,
    lowerfence: Any,
    upperfence: Any,
    label: str = "",
) -> dict | None:
    """
    Build one box's stats from its precomputed values, the way plotly reads them.

    Plotly's calc keeps a precomputed box only when ``q1``, ``median`` and
    ``q3`` are all numeric and in order; otherwise it draws nothing there.
    Such a box is dropped here for the same reason the sample path drops a
    box with no finite samples: a ``None`` or NaN sent straight through
    became a bare ``null``/``NaN`` in the schema, and plotly's ``boxlayer``
    has no ``path.box`` for it, so leaving it in would also shift every
    later box's positional selector off the element it describes.

    A fence plotly rejects -- non-numeric, or a lower fence above ``q1`` /
    an upper fence below ``q3`` -- does not cost it the box: with no sample
    points to fall back on it uses the quartile itself, and so does this.

    Parameters
    ----------
    q1, median, q3, lowerfence, upperfence : Any
        The box's precomputed values, as native scalars.
    label : str
        The box's name: announced as ``z`` when it is not empty, the way
        ``_compute_stats`` announces a raw box's category, and named in
        the warning when the box is dropped.
    """
    if not (
        _is_finite_number(q1)
        and _is_finite_number(median)
        and _is_finite_number(q3)
        and q1 <= median <= q3
    ):
        _logger.warning(
            "maidr: box %r has no complete quartiles; dropping it.",
            label or "<unnamed>",
        )
        return None

    min_val = lowerfence if _is_finite_number(lowerfence) and lowerfence <= q1 else q1
    max_val = upperfence if _is_finite_number(upperfence) and upperfence >= q3 else q3

    result = {
        MaidrKey.LOWER_OUTLIER.value: [],
        MaidrKey.MIN.value: min_val,
        MaidrKey.Q1.value: q1,
        MaidrKey.Q2.value: median,
        MaidrKey.Q3.value: q3,
        MaidrKey.MAX.value: max_val,
        MaidrKey.UPPER_OUTLIER.value: [],
    }
    if label:
        result[MaidrKey.Z.value] = label
    return result


def _trace_is_horizontal(trace: dict) -> bool:
    """Return whether plotly draws *trace*'s boxes horizontally.

    An explicit ``orientation="h"`` wins. Otherwise a precomputed trace reads
    its arrays the other way round from a raw one. Raw samples in ``x`` alone
    are the values of a horizontal box; but once ``q1``/``median``/``q3``
    carry the values, a lone ``x`` is the *positions* of vertical boxes and a
    lone ``y`` the positions of horizontal ones -- plotly's box defaults,
    case ``"10"`` -> ``v`` and case ``"01"`` -> ``h``. Applying the raw rule
    to both swapped the announced value axis for every precomputed trace
    with one array.

    With both a 1-D ``x`` and ``y`` (plotly's case ``"11"``) a precomputed
    trace sets no orientation at all: plotly hides it and draws nothing, so
    the ``False`` it gets here is a default, not a match.
    """
    if trace.get("orientation") == "h":
        return True
    if _has_precomputed_stats(trace):
        return trace.get("y") is not None and trace.get("x") is None
    # Plotly uses x for horizontal when y is absent
    return trace.get("x") is not None and trace.get("y") is None


def _compute_stats(
    arr: np.ndarray,
    label: str = "",
    quartilemethod: str | None = None,
) -> dict | None:
    """
    Compute box plot statistics for a numeric array.

    The statistics are the ones plotly draws, not a textbook's: non-finite
    samples are skipped, and the quartiles follow the trace's
    ``quartilemethod`` the way plotly's box calc reads it. Shared by
    ``PlotlyBoxPlot`` and ``PlotlyMultiBoxPlot``, which describe the same
    boxes and must not describe them two different ways.

    Answers None for an array with no finite samples. Every quartile of a
    box with no samples is undefined -- `np.percentile` raises rather than
    inventing one -- and an array arrives empty when the samples behind it
    could not be read, a corrupt typed-array spec being the way that
    happens. The caller drops the box; letting the raise through would take
    the whole figure with it, including the layers that read perfectly
    well. The precomputed path bounds its loop for the same reason.

    Parameters
    ----------
    arr : numpy.ndarray
        The box's samples, as floats.
    label : str
        The box's name, for the warning when it is dropped.
    quartilemethod : str or None
        The trace's ``quartilemethod``; ``None`` or ``"linear"`` is plotly's
        default.
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
    q2 = float(np.percentile(arr, 50, method=QUANTILE_METHOD))
    # `quartilemethod="exclusive"`/`"inclusive"` only change plotly's
    # answer for an odd sample size: the median is left out of, or shared
    # by, the two halves whose medians become q1 and q3. An even sample
    # is Hazen whatever the method says. So is a single sample under
    # `exclusive`: its halves are empty, and plotly's `Lib.interp` on an
    # empty array answers `undefined` -- there is no drawn quartile to
    # match, and a NaN in the schema is worse than the value itself.
    halves = None
    if arr.size % 2 and quartilemethod in ("exclusive", "inclusive"):
        middle = arr.size // 2
        ordered = np.sort(arr)
        if quartilemethod == "exclusive":
            halves = ordered[:middle], ordered[middle + 1 :]
        else:
            halves = ordered[: middle + 1], ordered[middle:]
    if halves is not None and all(half.size for half in halves):
        q1, q3 = (float(np.median(half)) for half in halves)
    else:
        q1, q3 = (
            float(q) for q in np.percentile(arr, [25, 75], method=QUANTILE_METHOD)
        )
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


class PlotlyBoxPlot(PlotlyPlot):
    """Extract data from a Plotly box trace."""

    def __init__(
        self,
        trace: dict,
        layout: dict,
        *,
        layer_position: int = 0,
        **kwargs: str,
    ) -> None:
        super().__init__(trace, layout, PlotType.BOX, **kwargs)
        # Zero-based position of this trace's group among the boxlayer's
        # children. Defaulted for the factory, which sees one trace and has
        # no idea what shares its layer -- the same reason
        # `PlotlyCandlestickPlot` defaults it. `PlotlyMaidr` passes the real
        # one, and a `go.Candlestick` declared first is exactly what makes it
        # non-zero.
        self._layer_position = layer_position
        # Populated by _extract_plot_data before _get_selector runs.
        self._outlier_counts: list[tuple[int, int]] = []

    def _get_selector(self) -> list[dict]:
        """Return structured per-box selectors with split outliers.

        One trace, so every box shares a group and is told apart by its
        position *within* that group. A categorical `go.Box` draws one box
        per category into one `<g>`, which is why the group index alone
        cannot address them (#395).
        """
        prefix = self._subplot_css_prefix()
        group = self._layer_position + 1
        return [
            _build_box_selector(prefix, group, index + 1, lower, upper)
            for index, (lower, upper) in enumerate(
                self._outlier_counts or [(0, 0)]
            )
        ]

    def _is_horizontal(self) -> bool:
        """Detect if this box trace is horizontal -- see `_trace_is_horizontal`."""
        return _trace_is_horizontal(self._trace)

    def render(self) -> dict:
        schema = super().render()
        schema[MaidrKey.ORIENTATION] = (
            "horz" if self._is_horizontal() else "vert"
        )
        return schema

    def _extract_plot_data(self) -> list[dict]:
        # Plotly box traces can have pre-computed stats or raw data
        if _has_precomputed_stats(self._trace):
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

    def _extract_precomputed(self) -> list[dict]:
        """
        Extract box stats from pre-computed values in the trace.

        Only as many boxes are described as every statistic has a value for.
        The five arrays are decoded independently, so one of them failing --
        a corrupt typed-array spec comes back empty -- would otherwise leave
        the loop indexing past the end of it. A short layer is the same answer
        the rest of this module gives to data it cannot read; a crash would
        take the whole figure with it.

        A box whose quartiles are missing or out of order is dropped too,
        because plotly draws none there -- see `_precomputed_box`.
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

        name = self._trace.get("name") or "box"
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
            stats = _compute_stats(
                arr,
                label=self._trace.get("name", ""),
                quartilemethod=self._trace.get("quartilemethod"),
            )
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
            stats = _compute_stats(
                arr,
                label=str(cat),
                quartilemethod=self._trace.get("quartilemethod"),
            )
            if stats is not None:
                results.append(stats)
        return results
