from __future__ import annotations

import math
from datetime import date
from typing import Any

import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list


def _plotly_round_up(val: float, array: list[float], reverse: bool = False) -> float:
    """Binary search matching Plotly.js ``Lib.roundUp``.

    With *reverse* False (default) returns the first element of *array*
    **strictly greater** than *val*, clamped to the last element when there
    is none. With *reverse* True it returns the largest element <= *val*.

    Strictly, not "greater than or equal" -- the search advances on
    ``array[mid] <= val``, which steps past an exact match, and that is what
    plotly does. The distinction only shows on the boundary, and there it
    decides a whole bin grid: see :func:`_plotly_dtick` for what an exact 2
    costs (#646).
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


def _plotly_default_size0(
    arr: np.ndarray, *, is_2d: bool = False, sample_size: int | None = None
) -> float:
    """Compute the default rough bin size when ``nbinsx`` is not given.

    Mirrors the logic in Plotly.js ``axes.autoBin`` (the ``else`` branch
    where ``nbins`` is falsy)::

        distinctData = Lib.distinctVals(data)
        msexp = 10 ** floor(log(minDiff) / LN10)
        minSize = msexp * roundUp(minDiff / msexp, [0.9, 1.9, 4.9, 9.9], true)
        size0 = max(minSize, 2 * stdev(data) / n^(is2d ? 0.25 : 0.4))

    Parameters
    ----------
    arr : np.ndarray
        The finite data values.
    is_2d : bool, default False
        Bin an axis of a **two-dimensional** histogram, which plotly bins
        more coarsely: the sample-size exponent is ``0.25`` rather than
        ``0.4``, which is `autoBin`'s own ``is2d`` flag and the only thing
        that differs between the two. Measured against the browser on eight
        axes across four figures -- gaussian, uniform, a six-value sample and
        a normalised one -- ``0.4`` matched none of them and ``0.25`` matched
        all eight.
    sample_size : int, optional
        How long the sample was *before* its blanks were dropped, for the
        exponent alone. That is the one place plotly reads the whole array:
        ``distinctVals`` sorts the blanks to the end and stops short of them,
        and ``stdev`` divides by the numeric count, but the ``n`` in
        ``n ** 0.4`` is ``data.length`` as given. Defaults to the length of
        *arr*, which is the same number for a sample with no blanks.
    """
    sorted_arr = np.sort(arr)
    n = len(sorted_arr)
    n_total = sample_size or n
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

    # size0 = max(minSize, 2 * stdev / n^(is2d ? 0.25 : 0.4))
    stdev = float(np.std(arr, ddof=0))
    size0 = max(min_size, 2 * stdev / (n_total ** (0.25 if is_2d else 0.4)))

    if not np.isfinite(size0) or size0 <= 0:
        return 1.0
    return size0


def _plotly_dtick(size0: float) -> float:
    """Compute a 'nice' tick/bin size the same way Plotly.js does.

    Plotly's ``autoTicks`` for linear axes works as follows::

        base = 10 ** floor(log10(size0))
        dtick = base * roundUp(size0 / base, [2, 5, 10])

    where ``roundUp(v, seq)`` returns the first element of *seq* **strictly
    greater** than *v*. Strictly, not "greater than or equal": ``Lib.roundUp``
    binary-searches with ``arrayIn[mid] <= val``, which steps past an exact
    match.

    That is the whole of the difference and it is not a rounding detail. The
    two readings agree everywhere except where ``size0 / base`` lands exactly
    on 2, 5 or 10, and there the loose one picks the width *below* the one
    plotly draws -- twice as many bins, half as wide, every count wrong to
    match. Measured in Chromium, with ``nbins`` used to make the ratio exact
    on demand:

    ==========================================  =====  ==========  =========
    trace                                       ratio  plotly      loose
    ==========================================  =====  ==========  =========
    ``x=linspace(0, 30, 61), nbinsx=15``        2.0    **5**       2
    ``x=linspace(0, 75, 76), nbinsx=15``        5.0    **10**      5
    ``x=linspace(0, 28.5, 58), nbinsx=15``      1.9    2           2
    ``x=linspace(0, 31.5, 64), nbinsx=15``      2.1    5           5
    ==========================================  =====  ==========  =========

    The same comparison decides a contour's automatic levels, which run
    through the same ``autoTicks``: a field spanning ``0 .. 3`` gives a rough
    step of exactly ``0.2``, and plotly draws ``0.5`` (#642, #646).

    Parameters
    ----------
    size0 : float
        Raw (rough) bin size, typically ``data_range / nbinsx``.
    """
    if size0 <= 0:
        return 1.0
    base = 10 ** math.floor(math.log10(size0))
    # The same `Lib.roundUp` the bin-width floor above already goes through,
    # rather than a second hand-rolled copy of it. The copy is where the
    # strictness was lost: this call site read the sequence with `>=` while
    # the helper next to it had the search right all along.
    return base * _plotly_round_up(size0 / base, [2, 5, 10])


#: How far a bin count may overshoot a whole number and still be read as one.
#: ``(end - start) / size`` decides how many bins a spec asks for, and the
#: division rarely comes out even in binary -- ``(8 - 0) / 2`` is exact but a
#: hair over on other spellings, and rounding that up would add a bin the
#: chart does not draw.
_BIN_COUNT_TOLERANCE = 1e-9


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


def is_temporal_sample(values: Any) -> bool:
    """Whether plotly would bin *values* along a date axis.

    Plotly bins a date axis by rules of its own -- a width from the date
    branch of ``autoTicks`` (day multiples, then months), no anti-clustering
    shift, date labels -- and none of that is ported yet. Run through the
    numeric arithmetic instead, six days of ``px.histogram`` came out as bin
    bounds around ``1.704e15`` on a grid of ``1e11`` microseconds, which is
    no number on the chart (#699). Until the date rules are measured, a
    temporal sample forms no layer, which is what #636 settled for every
    other reading this cannot make right, and what the two-dimensional path
    already does with one.

    Read off the trace's array as ``to_dict`` handed it over, rather than
    after :func:`~maidr.plotly.plotly_plot.as_list` has spelled a
    ``datetime64`` array as ISO strings. A sample the author wrote as date
    *strings* is not caught here, and takes the categorical path as before.

    Parameters
    ----------
    values : Any
        A trace's binned array: a numpy array, a list, a typed-array spec,
        or ``None``.

    Returns
    -------
    bool
        True for a ``datetime64`` array, or any list holding a ``date``, a
        ``datetime`` (``pandas.Timestamp`` is one) or a ``datetime64``.
    """
    if values is None or isinstance(values, (dict, str)):
        return False
    if isinstance(values, np.ndarray):
        if values.dtype.kind == "M":
            return True
        # Only an object array can hold a date; the check per entry below is
        # not worth walking a numeric one for.
        if values.dtype.kind != "O":
            return False
    try:
        return any(isinstance(value, (date, np.datetime64)) for value in values)
    except TypeError:
        return False


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

        Every bin is half-open, ``[low, high)``, **including the last**. That
        is measured rather than obliging: with a window running to 6, plotly
        drops the samples sitting exactly on it rather than folding them into
        the bin below, and the two-dimensional reading of the same binning
        settled it the same way (#645).

        It costs nothing where the window is plotly's own, since a derived end
        is a whole bin past the last value and no sample can sit on it. It
        matters where the window is the author's, which is where a closed
        final bin announced ``[4, 6)`` holding seven of a chart's five.

        Values outside every bin get ``-1``: plotly discards those rather
        than clipping them into an edge bin, both sides.
        """
        assignment = np.searchsorted(bin_edges, arr, side="right") - 1
        # A value that is not a number is not an observation rather than an
        # observation of zero (#405), and it has to be said here rather than
        # left to the comparisons below: NaN answers False to both of them,
        # while `searchsorted` sorts it past the last edge -- so it would
        # come back as a bin one past the end, and the counts below would
        # then be one longer than the grid they belong to.
        outside = (
            ~np.isfinite(arr) | (arr < bin_edges[0]) | (arr >= bin_edges[-1])
        )
        assignment[outside] = -1
        return assignment

    @staticmethod
    def _bin_counts(arr: np.ndarray, bin_edges: np.ndarray) -> np.ndarray:
        """How many observations landed in each bin.

        Counted off :meth:`_bin_assignment` rather than ``np.histogram``, so
        the counts and the assignment cannot disagree about which bin an
        observation is in -- ``np.histogram`` closes its final bin and this
        does not.
        """
        assignment = PlotlyHistogramPlot._bin_assignment(arr, bin_edges)
        return np.bincount(
            assignment[assignment >= 0], minlength=len(bin_edges) - 1
        )

    def _extract_plot_data(self) -> list[dict]:
        values, _ = paired_arrays(self._trace, self._binned)
        if values is None:
            return []

        if is_temporal_sample(self._trace.get(self._binned)):
            return []

        # Detect categorical (string) data — Plotly renders these as
        # count bar charts.  Mirror how seaborn countplot is handled:
        # produce type "bar" data with category counts.
        try:
            arr = np.array(values, dtype=float)
        except (ValueError, TypeError):
            return self._extract_categorical_data(values)

        bin_edges = self._compute_bin_edges(arr)
        if len(bin_edges) < 2:
            return []
        counts = self._bin_counts(arr, bin_edges)

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
    arr: np.ndarray,
    bins: dict | None = None,
    nbins: int | None = None,
    *,
    is_2d: bool = False,
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

    A blank in the sample -- a ``None`` or a ``NaN``, which plotly draws
    around -- is no observation, and the grid is worked out from the values
    that are. ``min``/``max``, ``distinctVals`` and ``stdev`` all skip a blank
    in plotly.js, and ``autoShiftNumericBins`` **subtracts the blanks from
    its length** before every threshold it tests: the bundle counts them in
    the same pass as the integers (``t[c]%1===0?s++:zh(t[c])||l++``), takes
    ``f=t.length-l``, and reads ``s===f``, ``f*.1`` and ``f*.3`` off that
    ``f``. So the finite sample is what it is handed here, and the one term
    that does see the whole length is the automatic width's exponent -- see
    :func:`_plotly_default_size0`. Read off the whole array instead, the
    minimum was ``NaN`` and the first ``ceil`` of it raised out of a figure
    plotly draws (#699). For a sample with no blanks every intermediate is
    the same number, so its grid is unchanged. A sample of nothing but blanks
    draws no bars, and comes back as no edges at all.

    Parameters
    ----------
    arr : np.ndarray
        The raw data values, blanks included.
    is_2d : bool, default False
        Bin one axis of a ``histogram2d``, which changes only the sample-size
        exponent of the automatic width -- see :func:`_plotly_default_size0`.
        An explicit ``size`` or ``nbins`` is honoured identically either way,
        which is why this reaches no further than that one branch.

    Returns
    -------
    np.ndarray
        Bin edges matching what Plotly renders; empty when it renders none.
    """
    named = bins if isinstance(bins, dict) else {}
    finite = arr[np.isfinite(arr)]
    if not finite.size:
        return np.array([])
    data_min, data_max = float(finite.min()), float(finite.max())
    data_range = data_max - data_min
    # A sample with no spread and nothing said about it: one bin around the
    # single value, which is what plotly draws (measured -- a run of 3s is
    # binned from 2.5 to 3.5). With something said about it there is a spec
    # to honour, and the width below answers 1 for a zero range anyway.
    if data_range == 0 and not named:
        return np.array([data_min - 0.5, data_max + 0.5])

    # 1. The width: the author's, the one an `nbins` hint rounds up to, or
    #    the automatic one -- see :func:`_bin_size`.
    size = _bin_size(
        finite, named, nbins, data_range, is_2d=is_2d, sample_size=arr.size
    )
    if size <= 0:
        # Only a *negative* explicit width reaches here -- a zero one is read
        # as an absence above. Plotly draws something for it rather than
        # nothing (measured: a width of -2 over twenty integers draws ten
        # bars, one per distinct value), by a route worth neither guessing at
        # nor reproducing for a spec that cannot be meant. Declining costs the
        # layer; announcing one bin holding everything would misreport a chart
        # drawing ten, which is the outcome #636 settled against.
        return np.array([])

    # 2. The start. An explicit one is honoured verbatim -- and honoured
    #    *whether or not* a size came with it, which is what #650 was about:
    #    reading it only alongside a size left `xbins={"start": 0.5}` binned
    #    from the automatic -0.5, five bars announced as six and not one of
    #    the numbers a number on the chart.
    #
    #    Without one, plotly runs an anti-clustering shift, which the round
    #    multiple alone does not reproduce: `go.Histogram(x=[0, 1, 2, 3, 4],
    #    xbins=dict(size=2))` is drawn from -0.5, not 0, because every value
    #    is an integer and they would otherwise sit on the bin edges.
    if "start" in named:
        start = float(named["start"])
    else:
        start = _auto_shift_bins(
            math.ceil(data_min / size) * size - size,
            finite,
            size,
            data_min,
            data_max,
        )

    # 3. How many bins. Plotly steps from `start` while the *bin's own*
    #    start is below `end`, so a range that is not a whole number of bins
    #    still gets the part-bin at the top: measured on `start=0.5, end=9,
    #    size=2`, which draws five bars and not the four that rounding the
    #    span down gives.
    #
    #    Without an `end`, one bin past the last value, so a value sitting
    #    exactly on a grid multiple has a bin of its own to land in rather
    #    than falling outside every bin -- see
    #    :meth:`PlotlyHistogramPlot._bin_assignment`, where the last bin is
    #    half-open like the rest. Any bin that reaches past the data is
    #    empty, and `_occupied_span` trims it back off.
    if "end" in named:
        span = (float(named["end"]) - start) / size
        count = math.ceil(span - _BIN_COUNT_TOLERANCE)
    else:
        count = 1 + math.floor((data_max - start) / size)
    # A spec that leaves no bin at all -- a `start` past the last value, or
    # an `end` at or below it -- comes out as a count of zero or less, and
    # `np.arange` answers that with an empty array on its own. Plotly draws
    # nothing for such a spec (measured), and every caller reads fewer than
    # two edges as nothing to bin, so no guard of its own is needed here.
    return start + size * np.arange(count + 1)


def _bin_size(
    arr: np.ndarray,
    named: dict,
    nbins: int | None,
    data_range: float,
    *,
    is_2d: bool,
    sample_size: int | None = None,
) -> float:
    """The bin width plotly settles on, before any start or end is applied.

    An explicit ``size`` is used as given, without the 'nice' rounding an
    ``nbins`` hint goes through. A zero one is not a width but an absence:
    measured, ``xbins=dict(size=0)`` draws the automatic bins, and plotly's
    own test for it is falsiness.

    Writing ``size`` at all -- even as that zero -- also **discards an
    ``nbins`` hint**, which is the one place the two interact. Measured:
    ``xbins=dict(size=0)`` with ``nbinsx`` of 4 and of 12 both draw the same
    fully automatic bins, while ``xbins=dict(start=0)`` with ``nbinsx=4``
    draws the width the hint asks for. So the hint is read when ``size`` is
    absent rather than when it is unusable.

    A sample with no spread gets a width of **1**, not the 2 that rounding
    one up would give: measured, a run of 3s is binned from 2.5 to 3.5 with
    ``size`` reported as 1, whether or not the author named a start.
    """
    if named.get("size"):
        return float(named["size"])
    if data_range == 0:
        return 1.0
    # `not in` rather than falsy: a `size` of 0 is a width plotly cannot use
    # *and* an `nbins` it will not fall back to. The two questions have
    # different answers for the same key, which is why they are asked
    # differently.
    if nbins is not None and "size" not in named:
        return _plotly_dtick(data_range / max(1, nbins))
    return _plotly_dtick(
        _plotly_default_size0(arr, is_2d=is_2d, sample_size=sample_size)
    )
