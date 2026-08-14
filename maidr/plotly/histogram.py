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

    Parameters
    ----------
    bin_start : float
        Initial bin start (a round multiple of *dtick*).
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
        return f"{self._subplot_css_prefix()}.trace.bars .point > path"

    def _extract_plot_data(self) -> list[dict]:
        raw = self._trace.get(self._binned, None)
        if raw is None:
            return []
        values = as_list(raw)

        # Detect categorical (string) data — Plotly renders these as
        # count bar charts.  Mirror how seaborn countplot is handled:
        # produce type "bar" data with category counts.
        try:
            arr = np.array(values, dtype=float)
        except (ValueError, TypeError):
            return self._extract_categorical_data(values)

        bin_edges = self._compute_bin_edges(arr)
        counts, bin_edges = np.histogram(arr, bins=bin_edges)

        # The binned axis carries the bin, the other one the count. Naming the
        # keys off the orientation rather than hardcoding ``x`` keeps the
        # announced extent on the axis the bins are actually drawn along.
        binned, counted = (
            (MaidrKey.Y, MaidrKey.X)
            if self._horizontal
            else (MaidrKey.X, MaidrKey.Y)
        )
        bounds = {
            MaidrKey.X: (MaidrKey.X_MIN, MaidrKey.X_MAX),
            MaidrKey.Y: (MaidrKey.Y_MIN, MaidrKey.Y_MAX),
        }
        bin_min, bin_max = bounds[binned]
        count_min, count_max = bounds[counted]

        data = []
        for i, count in enumerate(counts):
            low = float(bin_edges[i])
            high = float(bin_edges[i + 1])
            data.append(
                {
                    binned.value: (low + high) / 2,
                    counted.value: int(count),
                    bin_min.value: low,
                    bin_max.value: high,
                    count_min.value: 0,
                    count_max.value: int(count),
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
        # Preserve order of first appearance.
        counts: dict[str, int] = {}
        for val in values:
            key = str(val)
            counts[key] = counts.get(key, 0) + 1

        # Switch schema type from "hist" to "bar".
        self.type = PlotType.BAR

        # As above, the category belongs on whichever axis plotly binned. A
        # horizontal count bar chart with its categories on ``x`` would be
        # announced with the counts and the labels swapped.
        category, count_key = (
            (MaidrKey.Y, MaidrKey.X)
            if self._horizontal
            else (MaidrKey.X, MaidrKey.Y)
        )
        return [
            {category.value: cat, count_key.value: count}
            for cat, count in counts.items()
        ]

    def _compute_bin_edges(self, arr: np.ndarray) -> np.ndarray:
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
        bins = self._trace.get(f"{self._binned}bins", None)

        # Explicit bin size — use it directly.
        if bins is not None and "size" in bins:
            size = float(bins["size"])
            start = (
                float(bins["start"])
                if "start" in bins
                else math.floor(arr.min() / size) * size
            )
            end = (
                float(bins["end"])
                if "end" in bins
                else math.ceil(arr.max() / size) * size + size
            )
            return np.arange(start, end + size / 2, size)

        data_min, data_max = float(arr.min()), float(arr.max())
        data_range = data_max - data_min
        if data_range == 0:
            return np.array([data_min - 0.5, data_max + 0.5])

        # 1. Compute nice bin size (mirrors axes.autoTicks + roundDTick)
        nbins = self._trace.get(f"nbins{self._binned}", None)
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
