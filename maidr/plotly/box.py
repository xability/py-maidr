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

#: Draws each box's parts again as hidden elements of their own, for the box
#: selectors to name. Run in the page by the init script, after plotly has
#: drawn and before the payload is attached; see :func:`_build_box_selector`.
#:
#: Plotly draws a box -- median, body, both whiskers and both caps -- as the
#: subpaths of one ``path.box``, in that order (``plotBoxAndWhiskers`` in
#: plotly.js): ``M`` starts each, the body is the one closed with ``Z`` and
#: takes its notches as ``L`` segments, the whisker to the lower fence comes
#: before the one to the upper fence, and so do the caps. A trace drawn
#: ``whiskerwidth=0`` has no caps, one drawn ``showwhiskers=False`` neither
#: whiskers nor caps.
#:
#: Each part is a hidden sibling of its box carrying ``data-maidr-box-part``:
#: the box's position among its trace's ``path.box`` elements, a space, and
#: the statistic it marks. ``iq`` is the body; ``q1`` and ``q3`` are the
#: body's two edges across the box, ``q2`` the median, and ``min`` and
#: ``max`` the caps, or the whiskers where no caps are drawn. A box drawn in
#: no shape this knows gets a copy of the whole path for every statistic,
#: which is the highlight every statistic had before.
SPLIT_BOXES_JS = r"""
    function maidrSplitBoxes(svg) {
        // Scoped as the selectors are: a range slider's copy of the plot
        // holds a box layer too, and no selector names it.
        var groups = svg.querySelectorAll('.subplot .boxlayer > g');
        for (var g = 0; g < groups.length; g++) {
            var index = 0;
            var children = Array.prototype.slice.call(groups[g].children);
            for (var c = 0; c < children.length; c++) {
                var box = children[c];
                if (box.tagName.toLowerCase() === 'path'
                        && box.classList.contains('box')) {
                    index += 1;
                    maidrSplitBox(box, index);
                }
            }
        }
    }

    function maidrNumbers(text) {
        return (text.match(/-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?/g) || [])
            .map(Number);
    }

    // One subpath drawn as a single straight segment, `M x,y H x2` or
    // `M x,y V y2`: its ends and the command that drew it.
    function maidrSegment(subpath) {
        var found = /^M([^HV]*)([HV])([^HV]*)$/.exec(subpath);
        if (!found) return null;
        var start = maidrNumbers(found[1]);
        var to = maidrNumbers(found[3]);
        if (start.length !== 2 || to.length !== 1) return null;
        var end = found[2] === 'H' ? [to[0], start[1]] : [start[0], to[0]];
        return {command: found[2], ends: [start[0], start[1], end[0], end[1]]};
    }

    // The segments a closed subpath draws with one command, in order.
    function maidrSegmentsBy(subpath, command) {
        var out = [];
        var x = 0, y = 0, startX = 0, startY = 0;
        var parts = subpath.match(/[MHVLZ][^MHVLZ]*/g) || [];
        for (var i = 0; i < parts.length; i++) {
            var n = maidrNumbers(parts[i].slice(1));
            switch (parts[i].charAt(0)) {
                case 'M': x = startX = n[0]; y = startY = n[1]; break;
                case 'L': x = n[0]; y = n[1]; break;
                case 'H':
                    if (command === 'H') out.push([x, y, n[0], y]);
                    x = n[0];
                    break;
                case 'V':
                    if (command === 'V') out.push([x, y, x, n[0]]);
                    y = n[0];
                    break;
                default: x = startX; y = startY;
            }
        }
        return out;
    }

    // The parts of one box by the statistic each marks, or null when the
    // path is not in a shape plotly draws a box in.
    function maidrBoxParts(d) {
        if (!/^(?:[MHVLZ][-+\d.,eE\s]*)+$/.test(d)) return null;
        var subpaths = d.match(/M[^M]*/g) || [];
        if ([2, 4, 6].indexOf(subpaths.length) < 0) return null;
        var median = maidrSegment(subpaths[0]);
        if (!median || !/Z\s*$/.test(subpaths[1])) return null;
        // The median runs across the box, and so do the body's two edges.
        var edges = maidrSegmentsBy(subpaths[1], median.command);
        if (edges.length !== 2) return null;
        var parts = {iq: subpaths[1], q1: edges[0], q2: median.ends, q3: edges[1]};
        if (subpaths.length > 2) {
            var low = maidrSegment(subpaths[subpaths.length - 2]);
            var high = maidrSegment(subpaths[subpaths.length - 1]);
            if (!low || !high) return null;
            parts.min = low.ends;
            parts.max = high.ends;
        }
        return parts;
    }

    function maidrSplitBox(box, index) {
        var svgNS = 'http://www.w3.org/2000/svg';
        var d = box.getAttribute('d') || '';
        var parts = maidrBoxParts(d);
        var names = ['iq', 'min', 'q1', 'q2', 'q3', 'max'];
        var after = box;
        for (var i = 0; i < names.length; i++) {
            var shape = parts ? parts[names[i]] : d;
            if (shape === undefined) continue;
            var part;
            if (typeof shape === 'string') {
                part = document.createElementNS(svgNS, 'path');
                part.setAttribute('d', shape);
            } else {
                part = document.createElementNS(svgNS, 'line');
                part.setAttribute('x1', shape[0]);
                part.setAttribute('y1', shape[1]);
                part.setAttribute('x2', shape[2]);
                part.setAttribute('y2', shape[3]);
            }
            part.setAttribute('style', box.getAttribute('style') || '');
            part.setAttribute('visibility', 'hidden');
            part.setAttribute('data-maidr-box-part', index + ' ' + names[i]);
            after.insertAdjacentElement('afterend', part);
            after = part;
        }
    }
"""


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

    Every other statistic names its own part of the box. Plotly draws the
    whole box as one ``path.box``, and naming that for all of them -- which
    this did -- outlined the whole box at Minimum, 25%, 50%, 75% and Maximum
    alike, so the outline never showed which statistic was being read. The
    init script draws each part again, hidden, beside the box (see
    :data:`SPLIT_BOXES_JS`), and these name them by the box's position among
    its trace's boxes and the statistic: the caps, or the whiskers where none
    are drawn, for the minimum and maximum, the body's two edges for the
    quartiles, the median line for the median. ``iq`` names the body, which
    maidr.js joins the caps to when it draws the box's shape.

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
    base = f"{group_sel} > :nth-child({box} of g.points)"

    def part(statistic: str) -> str:
        return f'{group_sel} > [data-maidr-box-part="{box} {statistic}"]'

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
        "min": part("min"),
        "max": part("max"),
        "q2": part("q2"),
        "iq": part("iq"),
        "q1": part("q1"),
        "q3": part("q3"),
        "upperOutliers": upper_sel,
    }


def order_box_rows(schema: dict, *, horizontal: bool, y_reversed: bool) -> None:
    """
    Put a horizontal layer's boxes in the order maidr.js reads them: top first.

    maidr.js reverses the boxes of a horizontal layer, so that the reader
    starts on the bottom box and Up moves up the page, and expects them top
    to bottom for that. Plotly draws a horizontal layer's boxes from the
    bottom up in the order the traces list them, and that order was emitted
    as it was: the reader started on the top box, and Up moved down the
    page to the box below. matplotlib's reader reverses the rows for the
    same reason (``BoxPlot._order_box_rows``).

    A y axis that runs backwards already draws the first box at the top, so
    it is left alone. The data and the selectors are reversed together, so
    each box keeps its own marks.

    Parameters
    ----------
    schema : dict
        The layer schema, with ``data`` and, when there are any, ``selectors``
        in the order the traces list the boxes. Changed in place.
    horizontal : bool
        Whether the boxes lie on their side.
    y_reversed : bool
        Whether the y axis runs from its high end to its low one.
    """
    if not horizontal or y_reversed:
        return
    schema[MaidrKey.DATA] = list(reversed(schema[MaidrKey.DATA]))
    if MaidrKey.SELECTOR in schema:
        schema[MaidrKey.SELECTOR] = list(reversed(schema[MaidrKey.SELECTOR]))


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
    z: str = "",
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
        The box's name for the warning when it is dropped.
    z : str
        What a reader hears the box called: announced as ``z`` when it is
        not empty, the way ``_compute_stats`` announces a raw box's
        category. Kept apart from ``label`` because the warning wants a
        name for every box, ``box 3``, where a reader wants only the ones
        the chart carries -- see `_precomputed_labels`.
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
    if z:
        result[MaidrKey.Z.value] = z
    return result


def _precomputed_labels(trace: dict, count: int) -> list[str]:
    """
    What each of a precomputed trace's boxes is announced as.

    The same rule the raw path follows: a box drawn at a category carries
    the category, and a trace of one box carries the trace's name. A trace
    of several boxes with a name and no positions is told apart by number,
    ``Sales 1``; one with neither is announced as nothing, the way a lone
    unnamed raw box is.

    Parameters
    ----------
    trace : dict
        The plotly trace.
    count : int
        How many boxes are being described.

    Returns
    -------
    list of str
        One label per box, empty where there is nothing to announce.
    """
    along = "y" if _trace_is_horizontal(trace) else "x"
    positions = as_list(trace.get(along))
    if len(positions) >= count and not any(
        isinstance(position, (list, tuple)) for position in positions[:count]
    ):
        return [str(position) for position in positions[:count]]
    name = trace.get("name") or ""
    if not name:
        return [""] * count
    if count == 1:
        return [name]
    return [f"{name} {i + 1}" for i in range(count)]


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
            "maidr: box %r has no samples to summarize; dropping it.",
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
        horizontal = self._is_horizontal()
        schema[MaidrKey.ORIENTATION] = "horz" if horizontal else "vert"
        order_box_rows(
            schema,
            horizontal=horizontal,
            y_reversed=self._axis_runs_backwards(self._yaxis_name),
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
        announced = _precomputed_labels(self._trace, count)
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
                results.append(box)
        return results

    def _extract_from_raw_data(self) -> list[dict]:
        """Compute box plot statistics from raw data.

        Handles both vertical (data in ``y``) and horizontal (data in
        ``x``) orientations.
        """
        y = self._trace.get("y", None)
        x = self._trace.get("x", None)

        # With both arrays, one places the boxes and the other holds their
        # samples: `y` places a horizontal trace's boxes, `x` a vertical one's.
        if x is not None and y is not None:
            if self._is_horizontal():
                return self._extract_grouped(y, x)
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

    def _extract_grouped(self, positions: Any, samples: Any) -> list[dict]:
        """
        Extract one box's stats per position, from the samples at it.

        Which array is which follows the orientation: a horizontal trace
        stands its boxes along ``y`` and reads its samples from ``x``. Grouped
        the vertical way, a horizontal trace -- what ``px.box(x=..., y=...)``
        draws for a numeric ``x`` and a categorical ``y`` -- took its category
        names for samples, and ``float()`` of one raised ``ValueError``, which
        took the whole figure down.

        Parameters
        ----------
        positions : Any
            Where each sample's box stands: ``x`` for a vertical trace, ``y``
            for a horizontal one.
        samples : Any
            The samples, from the other array.

        Returns
        -------
        list of dict
            One box per position, in order of first appearance.
        """
        positions = as_list(positions)
        samples = as_list(samples)
        # Preserve order of appearance
        categories = list(dict.fromkeys(positions))
        groups: dict[Any, list] = {cat: [] for cat in categories}
        for position, sample in zip(positions, samples):
            groups[position].append(sample)

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
