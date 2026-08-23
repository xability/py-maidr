from __future__ import annotations

import math

import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list


def _plotly_round_up(val: float, array: list[float], reverse: bool = False) -> float:
    """Binary search matching Plotly.js ``Lib.roundUp``.

    With *reverse* False (default) returns the smallest element in *array*
    that is >= *val*.  With *reverse* True returns the largest element <=
    *val*.
    """
    lo, hi = 0, len(array) - 1
    while lo < hi:
        if reverse:
            mid = math.ceil((lo + hi) / 2)
        else:
            mid = math.floor((lo + hi) / 2)
        if array[mid] <= val:
            lo = mid + (0 if reverse else 1)
        else:
            hi = mid - (1 if reverse else 0)
    return array[lo]


def _plotly_default_size0(arr: np.ndarray) -> float:
    """Compute the default rough bin size when ``nbinsx`` is not given.

    Mirrors the logic in Plotly.js ``axes.autoBin`` (the ``else`` branch
    where ``nbins`` is falsy)::

        distinctData = Lib.distinctVals(data)
        msexp = 10 ** floor(log(minDiff) / LN10)
        minSize = msexp * roundUp(minDiff / msexp, [0.9, 1.9, 4.9, 9.9], true)
        size0 = max(minSize, 2 * stdev(data) / n^0.4)
    """
    sorted_arr = np.sort(arr)
    n = len(sorted_arr)
    if n < 2:
        return 1.0

    data_range = float(sorted_arr[-1] - sorted_arr[0])
    if data_range == 0:
        return 1.0

    # distinctVals: find minimum spacing between distinct values
    err_diff = data_range / (n - 1) / 10000
    diffs = np.diff(sorted_arr)
    significant = diffs[diffs > err_diff]
    min_diff = float(significant.min()) if len(significant) > 0 else data_range

    # msexp and minSize
    msexp = 10 ** math.floor(math.log10(min_diff))
    min_size = msexp * _plotly_round_up(
        min_diff / msexp, [0.9, 1.9, 4.9, 9.9], reverse=True
    )

    # size0 = max(minSize, 2 * stdev / n^0.4)
    stdev = float(np.std(arr, ddof=0))
    size0 = max(min_size, 2 * stdev / (n ** 0.4))

    if not np.isfinite(size0) or size0 <= 0:
        return 1.0
    return size0


def _plotly_dtick(size0: float) -> float:
    """Compute a 'nice' tick/bin size the same way Plotly.js does.

    Plotly's ``autoTicks`` for linear axes works as follows::

        base = 10 ** floor(log10(size0))
        dtick = base * roundUp(size0 / base, [2, 5, 10])

    where ``roundUp(v, seq)`` returns the first element in *seq* that
    is >= *v*.

    Parameters
    ----------
    size0 : float
        Raw (rough) bin size, typically ``data_range / nbinsx``.
    """
    if size0 <= 0:
        return 1.0
    base = 10 ** math.floor(math.log10(size0))
    ratio = size0 / base
    for nice in (2, 5, 10):
        if nice >= ratio * (1 - 1e-9):  # small tolerance for FP
            return base * nice
    return base * 10  # fallback


def _auto_shift_bins(
    bin_start: float,
    data: np.ndarray,
    dtick: float,
    data_min: float,
    data_max: float,
) -> float:
    """Shift bin start to avoid data clustering at bin edges.

    Exact port of Plotly.js ``autoShiftNumericBins`` from
    ``src/plots/cartesian/axes.js``.

    *bin_start* need only be **some** multiple of *dtick* within one *dtick*
    of the true unshifted start -- not one particular formula. The two callers
    rely on that: the autobin path passes
    ``ceil(data_min / dtick) * dtick - dtick`` and the explicit-size path
    ``floor(data_min / size) * size``. Those agree except when ``data_min`` is
    itself a multiple of the width, where they differ by exactly one bin, and
    the branches below then correct both to the same answer -- ``near_edge``
    is trivially true of a seed equal to ``data_min``, so the no-shift
    fallback cannot fire for it either.

    That convergence is a property of the branches rather than of the
    arithmetic that produced the seed, so it is worth keeping deliberate:
    ``test_plotly_histogram_bins.py`` asserts the two seeds land on the same
    start across a spread of samples and widths, which would otherwise be
    rediscovered by hand the next time this function is touched.

    Parameters
    ----------
    bin_start : float
        A multiple of *dtick* within one *dtick* of the unshifted start.
    data : np.ndarray
        Raw data values.
    dtick : float
        Bin width.
    data_min : float
        Minimum data value.
    data_max : float
        Maximum data value.
    """
    edge_count = 0
    mid_count = 0
    int_count = 0

    def near_edge(v: float) -> bool:
        return (1 + (v - bin_start) * 100 / dtick) % 100 < 2

    for v in data:
        if v % 1 == 0:
            int_count += 1
        if near_edge(v):
            edge_count += 1
        if near_edge(v + dtick / 2):
            mid_count += 1

    n = len(data)
    if n == 0:
        return bin_start

    # Case 1: All values are integers.
    if int_count == n:
        if dtick < 1:
            return data_min - 0.5 * dtick
        else:
            shifted = bin_start - 0.5
            if shifted + dtick < data_min:
                shifted += dtick
            return shifted

    # Case 2: Few values land at midpoints — check edge clustering.
    if mid_count < n * 0.1:
        if (
            edge_count > n * 0.3
            or near_edge(data_min)
            or near_edge(data_max)
        ):
            binshift = dtick / 2
            if bin_start + binshift < data_min:
                return bin_start + binshift
            else:
                return bin_start - binshift

    return bin_start


#: Plotly's spelling of a horizontal trace.
_HORIZONTAL = "h"

#: ``histfunc`` values that aggregate a second array rather than counting.
#: ``count`` is plotly's default and is what the bin populations already are.
_AGGREGATING = frozenset({"sum", "avg", "min", "max"})

#: Of those, the ones with no answer for a bin nothing landed in. Plotly emits
#: no point at all for such a bin under these, where ``count`` and ``sum`` emit
#: a zero -- measured in Chromium over a sample with a two-bin gap in the
#: middle: ``count`` and ``sum`` return six points, ``avg``/``min``/``max``
#: return four, the interior empties dropped rather than zeroed.
_UNDEFINED_WHEN_EMPTY = frozenset({"avg", "min", "max"})


def aggregate_bins(
    assignment: np.ndarray, values: np.ndarray, n_bins: int, histfunc: str
) -> tuple[np.ndarray, np.ndarray]:
    """Reduce each bin's values the way ``histfunc`` does.

    ``histfunc`` decides what a bar *measures*. Ignoring it announced the bin
    populations for every mode, so a chart drawn at ``12, 15, 18`` was read out
    as ``3, 3, 3`` (#405).

    Parameters
    ----------
    assignment : np.ndarray
        Bin index per observation; ``-1`` for observations outside every bin,
        which plotly discards rather than clipping into an edge bin.
    values : np.ndarray
        The value array, aligned with *assignment*.
    n_bins : int
        How many bins the grid holds.
    histfunc : str
        One of ``sum``, ``avg``, ``min``, ``max``.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        The per-bin values, and a mask of which bins hold an observation.
        Bins outside the mask carry ``0`` and are the caller's to drop or
        keep, since ``count`` and ``sum`` announce a zero there while the
        other three announce nothing.
    """
    aggregated = np.zeros(n_bins, dtype=float)
    present = np.zeros(n_bins, dtype=bool)

    for index in range(n_bins):
        in_bin = values[assignment == index]
        # A value that is not a number is not an observation, rather than an
        # observation of zero. Measured: a bin holding ``['z', 'w', 8]``
        # averages to **8**, not 8/3, and its min and max are 8 as well --
        # so the strings are dropped, not counted. A bin left with nothing
        # numeric is empty, which the caller then treats exactly as it treats
        # a bin nothing landed in.
        in_bin = in_bin[np.isfinite(in_bin)]
        if not in_bin.size:
            continue
        present[index] = True
        if histfunc == "sum":
            aggregated[index] = float(in_bin.sum())
        elif histfunc == "avg":
            aggregated[index] = float(in_bin.mean())
        elif histfunc == "min":
            aggregated[index] = float(in_bin.min())
        else:  # max
            aggregated[index] = float(in_bin.max())

    return aggregated, present


def as_numeric(values: list) -> np.ndarray:
    """Coerce a value array to floats, with non-numbers as ``nan``.

    The value array is not guaranteed numeric: ``go.Histogram(y=cats,
    x=vals, histfunc="sum")`` bins ``x`` and hands the *category strings* to
    the aggregate. Plotly does not error on that -- it drops them -- so a
    plain ``np.array(..., dtype=float)`` would raise where the chart renders.

    ``nan`` rather than ``0`` because that is the measured behaviour:
    :func:`aggregate_bins` drops them, and a bin holding ``['z', 'w', 8]``
    averages to 8.
    """
    coerced = np.empty(len(values), dtype=float)
    for index, value in enumerate(values):
        try:
            coerced[index] = float(value)
        except (TypeError, ValueError):
            coerced[index] = np.nan
    return coerced


def paired_arrays(trace: dict, binned: str) -> tuple[list | None, list | None]:
    """The binned sample and its value array, cut to their common length.

    Plotly pairs the two arrays positionally and reads only as far as the
    shorter one, **including for the binning** -- and it does so whatever
    ``histfunc`` says. Measured: ``go.Histogram(x=[1..9], y=[10..50])`` draws
    three bins spanning 1 to 5, not the two spanning 1 to 9 that binning all
    of ``x`` gives, and the same figure with ``histfunc="sum"`` sums only the
    five pairs.

    Truncating here rather than at the point of use is what makes the bins and
    the values agree: slicing only the value array left it shorter than the
    bin assignment when ``y`` was the shorter of the two, which raised an
    ``IndexError`` out of a rendering path for a figure plotly draws without
    complaint.

    Parameters
    ----------
    trace : dict
        A ``histogram`` trace dict.
    binned : str
        ``"x"`` or ``"y"``, the axis being binned.

    Returns
    -------
    tuple[list | None, list | None]
        The binned sample, and the other axis's array when the trace carries
        one. Both ``None`` when the binned axis is absent.
    """
    raw = trace.get(binned)
    if raw is None:
        return None, None
    sample = as_list(raw)

    other_raw = trace.get("y" if binned == "x" else "x")
    if other_raw is None:
        return sample, None

    other = as_list(other_raw)
    shared = min(len(sample), len(other))
    return sample[:shared], other[:shared]


def value_array(trace: dict, binned: str) -> list | None:
    """The array ``histfunc`` aggregates, or ``None`` when there is none.

    A histogram that aggregates carries both arrays: one is binned and the
    other supplies the values. Which is which is not "the numeric one" --
    ``go.Histogram(x=cats, y=vals, histfunc="sum")`` and
    ``go.Histogram(y=cats, x=vals, histfunc="sum")`` both resolve to
    ``orientation: v`` in Plotly.js, so plotly bins ``x`` in *both*. The
    binned axis is settled by :func:`binned_axis`; this is simply the other.

    Parameters
    ----------
    trace : dict
        A ``histogram`` trace dict.
    binned : str
        ``"x"`` or ``"y"``, the axis being binned.

    Returns
    -------
    list | None
        The value array, or ``None`` when the trace only counts.
    """
    if trace.get("histfunc") not in _AGGREGATING:
        return None
    return paired_arrays(trace, binned)[1]


def apply_histnorm(
    values: np.ndarray, widths: np.ndarray, histnorm: str | None
) -> np.ndarray:
    """Rescale a histogram's bar values the way ``histnorm`` does.

    ``histnorm`` decides what a bar *measures*, and ignoring it left the
    values contradicting the axis label beside them: a ``histnorm="percent"``
    histogram whose axis reads "percent" announced ``2`` for a bar plotly
    draws at ``3.33`` (#404).

    Every form below is checked against ``gd.calcdata[0][i].s`` after
    ``Plotly.newPlot`` in Chromium:

    =========================  ==============
    ``histnorm``               value
    =========================  ==============
    *(unset)*                  ``v``
    ``percent``                ``v / T * 100``
    ``probability``            ``v / T``
    ``density``                ``v / w``
    ``probability density``    ``v / (T * w)``
    =========================  ==============

    ``T`` is the total of the bars' own values, **not** the number of
    observations. Those coincide under the default ``histfunc="count"``, which
    is why the distinction is easy to miss and worth stating: measured with
    ``histfunc="sum"`` and ``histfunc="avg"`` over the same data,
    ``histnorm="percent"`` returns *identical* output -- impossible if the
    denominator were the sample size, since the two aggregates differ by a
    constant factor, and required if it is their own total.

    So this takes the values it is given rather than recomputing anything from
    the sample: when ``histfunc`` support lands (#405) the aggregate flows
    through unchanged.

    Parameters
    ----------
    values : np.ndarray
        Per-bin values, before rescaling.
    widths : np.ndarray
        Per-bin widths, aligned with *values*.
    histnorm : str | None
        Plotly's ``histnorm``. Anything falsy or unrecognised leaves the
        values alone, matching plotly's own handling of an unset attribute.

    Returns
    -------
    np.ndarray
        The rescaled values.
    """
    if not histnorm:
        return values

    total = float(values.sum())
    per_width = values / widths

    if histnorm == "density":
        return per_width

    # The remaining three all divide by the total, so an empty trace would
    # divide by zero. It cannot reach here -- an all-empty histogram returns
    # before this -- but the guard keeps that a property of the caller rather
    # than an assumption made here.
    if total == 0:
        return values

    if histnorm == "percent":
        return values / total * 100
    if histnorm == "probability":
        return values / total
    if histnorm == "probability density":
        return per_width / total
    return values


def _occupied_span(counts: np.ndarray) -> tuple[int | None, int | None]:
    """Return the first and last bin index that anything landed in.

    Plotly emits bins from the first that holds an observation to the last,
    and keeps every empty bin between them. It does **not** emit the empty
    ones outside that span, however the grid came to reach past the data
    (#402).

    The rule is exactly that -- trim the ends, keep the middle -- and it took
    a figure narrower than its data on both sides to establish it. The reading
    it replaced was "span the data, clamped to the caller's ``[start, end)``",
    which fits every wider window and predicts one bin too many here:

    ==========================================  ==============  ============
    ``xbins`` on ``[-2.8, -1.2, .3, 1.1, 2.4, 3.3]``  Plotly.js       clamping
    ==========================================  ==============  ============
    ``start=-1, end=2, size=1``                 ``(0,1) (1,2)`` adds ``(-1,0)``
    ==========================================  ==============  ============

    Data exists below ``start``, so clamping keeps bin ``(-1, 0)``; plotly
    drops it because nothing landed *in* it, discarding the out-of-window
    values rather than piling them into the edge bin.

    Trimming subsumes the other half of #402 as well. The explicit-size path
    computed ``end`` one bin past plotly's, and that surplus bin is empty and
    at the end, so it goes without the arithmetic needing to be reasoned about
    separately.

    Empty bins matter beyond the announced values: plotly draws no ``.point``
    element for one, and the layer's selector resolves positionally, so a
    phantom bin shifts the highlight of every bin after it.

    Parameters
    ----------
    counts : np.ndarray
        Per-bin counts, in bin order.

    Returns
    -------
    tuple[int | None, int | None]
        Inclusive first and last occupied index, or ``(None, None)`` when
        every bin is empty.
    """
    occupied = np.flatnonzero(counts)
    if not occupied.size:
        return None, None
    return int(occupied[0]), int(occupied[-1])


def binned_axis(trace: dict) -> str:
    """Return which of ``x``/``y`` plotly bins for *trace*.

    A histogram bins one axis and counts into the other, and which one is not
    always stated: ``px.histogram(y=...)`` writes ``orientation`` onto the
    trace, but ``go.Histogram(y=...)`` writes nothing and lets Plotly.js infer
    it. Reading only ``x`` therefore left every horizontal histogram with no
    data at all (#401).

    The rule below is Plotly.js's own, measured rather than assumed --
    ``gd._fullData[i].orientation`` read back out of Chromium for each shape:

    ==================================================  ===========  ======
    trace                                               orientation  binned
    ==================================================  ===========  ======
    ``go.Histogram(x=v)``                               ``v``        ``x``
    ``go.Histogram(y=v)``                               ``h``        ``y``
    ``px.histogram(y="v")``                             ``h``        ``y``
    ``go.Histogram(x=cats, y=vals, histfunc="sum")``    ``v``        ``x``
    ``go.Histogram(y=cats, x=vals, histfunc="sum")``    ``v``        ``x``
    ``go.Histogram(x=v, orientation="h")``              ``h``        ``y``
    ==================================================  ===========  ======

    So an explicit ``orientation`` wins outright, and only in its absence does
    the presence of the arrays decide. The last row is the one that settles
    the precedence: plotly honours the attribute and bins the *absent* ``y``,
    drawing an empty trace rather than falling back to ``x``.

    Parameters
    ----------
    trace : dict
        A ``histogram`` trace dict.

    Returns
    -------
    str
        ``"x"`` or ``"y"``.
    """
    orientation = trace.get("orientation")
    if orientation is not None:
        return "y" if orientation == _HORIZONTAL else "x"
    if trace.get("y") is not None and trace.get("x") is None:
        return "y"
    return "x"


class PlotlyHistogramPlot(PlotlyPlot):
    """Extract data from a Plotly histogram trace."""

    def __init__(self, trace: dict, layout: dict, **kwargs: str) -> None:
        super().__init__(trace, layout, PlotType.HIST, **kwargs)
        self._binned = binned_axis(trace)

    @property
    def _horizontal(self) -> bool:
        """Whether the bins run along the y axis."""
        return self._binned == "y"

    def render(self) -> dict:
        """Add ``orientation`` to the base schema.

        The core reads a histogram's bin bounds from ``xMin``/``xMax`` or from
        ``yMin``/``yMax`` depending on this, so a horizontal layer that did not
        carry it would have its counts announced as the bin range.
        """
        schema = super().render()
        schema[MaidrKey.ORIENTATION] = "horz" if self._horizontal else "vert"
        return schema

    def _get_selector(self) -> str:
        return f"{self._subplot_css_prefix()}.barlayer .trace.bars .point > path"

    @staticmethod
    def _bin_assignment(arr: np.ndarray, bin_edges: np.ndarray) -> np.ndarray:
        """Which bin each observation falls in, or ``-1`` for none.

        Matches how ``np.histogram`` fills the same edges, so the assignment
        and the counts cannot disagree about which bin an observation is in:
        half-open ``[low, high)`` throughout except the last bin, which is
        closed so the maximum has somewhere to go.

        Values outside every bin get ``-1``. Plotly discards those rather than
        clipping them into an edge bin -- an explicit window narrower than the
        data drops what falls beyond it, both sides -- and ``np.histogram``
        already does the same for the counts.
        """
        assignment = np.searchsorted(bin_edges, arr, side="right") - 1
        assignment[arr == bin_edges[-1]] = len(bin_edges) - 2
        outside = (arr < bin_edges[0]) | (arr > bin_edges[-1])
        assignment[outside] = -1
        return assignment

    def _extract_plot_data(self) -> list[dict]:
        values, _ = paired_arrays(self._trace, self._binned)
        if values is None:
            return []

        # Detect categorical (string) data — Plotly renders these as
        # count bar charts.  Mirror how seaborn countplot is handled:
        # produce type "bar" data with category counts.
        try:
            arr = np.array(values, dtype=float)
        except (ValueError, TypeError):
            return self._extract_categorical_data(values)

        bin_edges = self._compute_bin_edges(arr)
        counts, bin_edges = np.histogram(arr, bins=bin_edges)

        # Trimmed on the raw counts rather than the rescaled values, because
        # that is what "a bin nothing landed in" means. Every rescaling below
        # maps zero to zero, so the two agree -- but only the counts say it
        # without depending on that.
        first, last = _occupied_span(counts)
        if first is None:
            return []

        histfunc = self._trace.get("histfunc") or "count"
        raw_values = value_array(self._trace, self._binned)
        present = counts > 0

        if raw_values is None:
            measured = counts.astype(float)
        else:
            measured, present = aggregate_bins(
                self._bin_assignment(arr, bin_edges),
                as_numeric(raw_values),
                len(counts),
                histfunc,
            )

        bar_values = apply_histnorm(
            measured,
            np.diff(bin_edges),
            self._trace.get("histnorm"),
        )

        # `avg`, `min` and `max` have no answer for an empty bin, and plotly
        # emits no point for one -- interior ones included, not just at the
        # edges. `count` and `sum` do have one and announce a zero.
        #
        # Unless a `histnorm` is set, which brings the empty bins back as
        # zeros. Measured across all three functions and all four norms:
        # `avg` alone gives four points over a sample with a two-bin gap,
        # `avg` with any `histnorm` gives six. Rescaling evidently runs over
        # the whole bin array and does not carry the "no answer" marker
        # through, so the composition is not simply one step after the other.
        drop_empty = histfunc in _UNDEFINED_WHEN_EMPTY and not self._trace.get(
            "histnorm"
        )

        # The binned axis carries the bin, the other one the count. Naming the
        # keys off the orientation rather than hardcoding ``x`` keeps the
        # announced extent on the axis the bins are actually drawn along.
        binned, counted = (
            (MaidrKey.Y, MaidrKey.X) if self._horizontal else (MaidrKey.X, MaidrKey.Y)
        )
        bounds = {
            MaidrKey.X: (MaidrKey.X_MIN, MaidrKey.X_MAX),
            MaidrKey.Y: (MaidrKey.Y_MIN, MaidrKey.Y_MAX),
        }
        bin_min, bin_max = bounds[binned]
        count_min, count_max = bounds[counted]

        data = []
        for i, value in enumerate(bar_values[first : last + 1], start=first):
            if drop_empty and not present[i]:
                continue
            low = float(bin_edges[i])
            high = float(bin_edges[i + 1])
            # A count is announced as the integer it is; a rescaled value is
            # not one, and rounding it to look like one would put a 3.33%
            # share on the chart as 3.
            height = int(value) if value == int(value) else float(value)
            data.append(
                {
                    binned.value: (low + high) / 2,
                    counted.value: height,
                    bin_min.value: low,
                    bin_max.value: high,
                    count_min.value: 0,
                    count_max.value: height,
                }
            )
        return data

    def _extract_categorical_data(self, values: list) -> list[dict]:
        """Count occurrences of categorical values and return bar-format data.

        Mirrors how seaborn ``countplot`` produces ``type: "bar"`` schemas.
        The plot type is switched from HIST to BAR so the JS side renders
        it as a bar chart with proper categorical navigation.

        Parameters
        ----------
        values : list
            The binned axis's sample -- ``trace["y"]`` on a horizontal trace,
            ``trace["x"]`` on a vertical one. Named for the role rather than
            the axis, since either can be the one that holds it.
        """
        # Preserve order of first appearance. Grouped rather than counted, so
        # an aggregating `histfunc` has the members to reduce -- plotly bins
        # categories onto integer positions and then applies `histfunc`
        # exactly as it does for a numeric sample.
        grouped: dict[str, list[int]] = {}
        for position, val in enumerate(values):
            grouped.setdefault(str(val), []).append(position)

        raw_values = value_array(self._trace, self._binned)
        histfunc = self._trace.get("histfunc") or "count"

        if raw_values is None:
            measured = [float(len(members)) for members in grouped.values()]
        else:
            numeric = as_numeric(raw_values)
            assignment = np.empty(len(values), dtype=int)
            for index, members in enumerate(grouped.values()):
                assignment[members] = index
            reduced, _ = aggregate_bins(assignment, numeric, len(grouped), histfunc)
            measured = list(reduced)

        # Every category holds at least one observation by construction, so
        # the empty-bin question the numeric path answers cannot arise here.
        measured = list(
            apply_histnorm(
                np.array(measured, dtype=float),
                np.ones(len(measured)),
                self._trace.get("histnorm"),
            )
        )

        # Switch schema type from "hist" to "bar".
        self.type = PlotType.BAR

        # As above, the category belongs on whichever axis plotly binned. A
        # horizontal count bar chart with its categories on ``x`` would be
        # announced with the counts and the labels swapped.
        category, count_key = (
            (MaidrKey.Y, MaidrKey.X) if self._horizontal else (MaidrKey.X, MaidrKey.Y)
        )
        return [
            {
                category.value: cat,
                count_key.value: int(value) if value == int(value) else value,
            }
            for cat, value in zip(grouped, measured)
        ]

    def _compute_bin_edges(self, arr: np.ndarray) -> np.ndarray:
        """This trace's own bin edges. See :func:`compute_bin_edges`."""
        return compute_bin_edges(
            arr,
            self._trace.get(f"{self._binned}bins", None),
            self._trace.get(f"nbins{self._binned}", None),
        )


def compute_bin_edges(
    arr: np.ndarray, bins: dict | None = None, nbins: int | None = None
) -> np.ndarray:
    """Compute bin edges that match Plotly's autobinning algorithm.

    Plotly treats ``nbins`` as a *hint* and rounds the bin size to a
    'nice' number via ``autoTicks`` (sequence ``{2, 5, 10} * 10^n``)
    before aligning the start edge.  When the bin ``size`` is specified
    explicitly, it is used directly without rounding.

    The bin spec is read off the *binned* axis, so a horizontal trace is
    governed by ``ybins``/``nbinsy`` and a vertical one by
    ``xbins``/``nbinsx``. Plotly ignores the other axis's spec outright
    rather than falling back to it -- measured both ways in Chromium:
    ``go.Histogram(y=v, xbins=dict(size=2))`` autobins to 13 bins of 0.5
    exactly as if no spec were given, and ``go.Histogram(x=v,
    ybins=dict(size=2))`` does the same. Reading ``xbins`` for every trace
    would have honoured a spec plotly discards and missed the one it uses.

    Parameters
    ----------
    arr : np.ndarray
        The raw data values.

    Returns
    -------
    np.ndarray
        Bin edges matching what Plotly renders.
    """
    # Explicit bin size — the width is used as given, without the 'nice'
    # rounding an `nbins` hint goes through.
    if bins is not None and "size" in bins:
        size = float(bins["size"])
        data_min, data_max = float(arr.min()), float(arr.max())

        # An explicit `start` is honoured verbatim. Without one, plotly
        # still runs the same anti-clustering shift it applies when
        # autobinning, which the round multiple of `size` alone does not
        # reproduce: `go.Histogram(x=[0, 1, 2, 3, 4], xbins=dict(size=2))`
        # is drawn from -0.5, not 0, because every value is an integer and
        # they would otherwise sit on the bin edges.
        if "start" in bins:
            start = float(bins["start"])
        else:
            start = _auto_shift_bins(
                math.floor(data_min / size) * size,
                arr,
                size,
                data_min,
                data_max,
            )

        # One bin past the last value, so a value sitting exactly on a
        # grid multiple gets the bin starting there rather than being
        # folded into the one below by numpy's closed final interval.
        # Any bin this reaches past the data is empty, and `_occupied_span`
        # trims it back off.
        end = (
            float(bins["end"])
            if "end" in bins
            else math.floor((data_max - start) / size) * size + start + size
        )
        return np.arange(start, end + size / 2, size)

    data_min, data_max = float(arr.min()), float(arr.max())
    data_range = data_max - data_min
    if data_range == 0:
        return np.array([data_min - 0.5, data_max + 0.5])

    # 1. Compute nice bin size (mirrors axes.autoTicks + roundDTick)
    if nbins is not None:
        size0 = data_range / max(1, nbins)
    else:
        size0 = _plotly_default_size0(arr)
    dtick = _plotly_dtick(size0)

    # 2. Initial bin start: one tick below the first tick >= data_min
    #    (mirrors axes.tickFirst → axes.tickIncrement(reverse))
    first_tick = math.ceil(data_min / dtick) * dtick
    bin_start = first_tick - dtick

    # 3. Shift to avoid data clustering at bin edges
    bin_start = _auto_shift_bins(bin_start, arr, dtick, data_min, data_max)

    # 4. Compute bin count and end
    bin_count = 1 + math.floor((data_max - bin_start) / dtick)
    bin_end = bin_start + bin_count * dtick

    return np.arange(bin_start, bin_end + dtick / 2, dtick)

