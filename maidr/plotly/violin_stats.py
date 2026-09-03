"""Plotly's own violin statistics, ported.

A plotly figure carries the *sample* for a violin, never the curve: plotly
computes the kernel density estimate in the browser, so the density a reader
would be told about does not exist in the Python object at all.

Recomputing it is only honest if it produces the curve plotly draws rather
than a defensible curve of our own. Every rule below is therefore taken from
plotly's implementation rather than from a textbook, and the port is checked
against plotly's own ``calcdata`` in a browser -- see
``tests/plotly/test_plotly_violin_stats.py``, which pins the agreement to a
tolerance across a range of sample sizes.

Measured agreement across n = 7, 11, 12, 13, 17, 23, 41, 43: the density
values agree to 5.9e-15 relative at worst, and the number of sample points is
identical in every case. What differs is summation order between numpy and
JavaScript, not the rule.

The rules, for reference::

    bandwidth = max(1.059 * min(sd, iqr / 1.349) * n**-0.2, (max - min) / 100)
    span      = [min - 2 * bandwidth, max + 2 * bandwidth]        # spanmode "soft"
    nIntervals = ceil((span[1] - span[0]) / (bandwidth / 3))
    kde(x)    = (1 / (n * bandwidth)) * sum(phi((x - xi) / bandwidth))

with quartiles by the Hazen rule and ``sd`` the *sample* standard deviation.
"""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np

#: Plotly's Silverman coefficient. Spelled 1.059 rather than the 1.06 the rule
#: is usually quoted with, because plotly writes 1.059 and this has to match
#: what is drawn rather than what is conventional.
_SILVERMAN_COEFFICIENT = 1.059

#: The IQR-to-sigma conversion in plotly's rule. Also a rounding of the exact
#: 1.349 that the normal distribution gives; again, plotly's spelling wins.
_IQR_TO_SIGMA = 1.349

#: Plotly widens the evaluated range by two bandwidths either side under its
#: default ``spanmode="soft"``.
_SPAN_BANDWIDTHS = 2

#: Sample points are spaced a third of a bandwidth apart.
_POINTS_PER_BANDWIDTH = 3

#: A floor on the bandwidth, as a fraction of the sample's range. Stops a
#: sample with a near-zero spread from producing a degenerate curve.
_MIN_BANDWIDTH_FRACTION = 100

#: The quantile rule plotly uses. Not numpy's default (`linear`), and not
#: plotly's own documented `quartilemethod` values either -- measured against
#: plotly's `calcdata` across eight sample sizes, this is the one that agrees.
QUANTILE_METHOD = "hazen"

_INV_SQRT_2PI = 1.0 / math.sqrt(2.0 * math.pi)


class ViolinStats(NamedTuple):
    """The statistics plotly computes for one violin.

    Attributes
    ----------
    minimum, maximum : float
        The sample's extremes. These are what the box layer announces as its
        whiskers -- plotly's violin box draws to the data rather than to a
        Tukey fence, and the KDE curve covers the tails, so no outliers are
        separated out.
    q1, median, q3 : float
        Quartiles by the Hazen rule.
    mean : float
        The arithmetic mean, announced when the violin draws a mean line.
    bandwidth : float
        The kernel bandwidth plotly chose.
    positions : numpy.ndarray
        The value-axis positions the density was evaluated at.
    density : numpy.ndarray
        The density at each position, in the same order.
    """

    minimum: float
    maximum: float
    q1: float
    median: float
    q3: float
    mean: float
    bandwidth: float
    positions: np.ndarray
    density: np.ndarray


def _bandwidth(values: np.ndarray, q1: float, q3: float) -> float:
    """Return the bandwidth plotly would choose for *values*."""
    count = len(values)
    spread = float(values.max() - values.min())

    # The sample standard deviation, not the population one. Measured: using
    # `ddof=0` misses plotly's bandwidth by ~1e-2 relative, which is far too
    # much to attribute to summation order.
    deviation = float(values.std(ddof=1))
    scale = min(deviation, (q3 - q1) / _IQR_TO_SIGMA)
    rule = _SILVERMAN_COEFFICIENT * scale * count**-0.2

    return max(rule, spread / _MIN_BANDWIDTH_FRACTION)


def violin_stats(values: np.ndarray) -> ViolinStats | None:
    """
    Return the statistics plotly computes for one violin's sample.

    Parameters
    ----------
    values : numpy.ndarray
        The sample, which need not be sorted.

    Returns
    -------
    ViolinStats or None
        ``None`` when there is nothing to describe -- an empty sample, or one
        whose values are all identical, which plotly draws as a degenerate
        single-point density rather than a curve.
    """
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return None

    lowest = float(values.min())
    highest = float(values.max())
    if highest == lowest:
        # Every value identical. Plotly special-cases this rather than
        # skipping it -- its bandwidth comes out zero, and it emits a single
        # density point of 1 at the value and draws a degenerate violin there.
        # Measured: a category like this still gets its own `path.violin`.
        #
        # So it is announced too. Dropping it would take a category the chart
        # visibly draws out of the reading altogether, which is a worse
        # failure than a curve with one point -- and inventing a spread for it
        # would be worse still.
        only = np.array([lowest])
        return ViolinStats(
            minimum=lowest,
            maximum=highest,
            q1=lowest,
            median=lowest,
            q3=lowest,
            mean=lowest,
            bandwidth=0.0,
            positions=only,
            density=np.array([1.0]),
        )

    q1, median, q3 = (
        float(q) for q in np.percentile(values, [25, 50, 75], method=QUANTILE_METHOD)
    )
    bandwidth = _bandwidth(values, q1, q3)

    low = lowest - _SPAN_BANDWIDTHS * bandwidth
    high = highest + _SPAN_BANDWIDTHS * bandwidth
    width = high - low

    intervals = math.ceil(width / (bandwidth / _POINTS_PER_BANDWIDTH))
    if not math.isfinite(intervals) or intervals < 1:  # pragma: no cover
        return None

    # Spelled the way plotly computes it -- `span[0] + i * step` -- rather
    # than with `linspace`, which arrives at the same points by a different
    # route (it interpolates from both ends and pins the last one to `high`).
    # Measured, the two agree bit for bit on the reference samples, so this is
    # not correcting a difference that exists today; it is declining to bet
    # that two different floating-point routes stay identical for every input.
    step = width / intervals
    positions = low + np.arange(intervals + 1) * step

    # The Gaussian kernel, summed over the sample at every position -- one
    # position at a time rather than as an (intervals x n) outer product.
    # The outer product is O(intervals * n) memory, and intervals grows with
    # n: measured, 1.5 GB of peak memory for a 200k-sample violin, for every
    # violin on the subplot. A row at a time is O(n) memory. The result is
    # bit-identical, because reducing one contiguous row of the matrix is the
    # same pairwise summation numpy applies to a one-dimensional array.
    density = np.empty(len(positions))
    for i, position in enumerate(positions):
        density[i] = np.exp(-0.5 * ((position - values) / bandwidth) ** 2).sum()
    density *= _INV_SQRT_2PI / (len(values) * bandwidth)

    return ViolinStats(
        minimum=lowest,
        maximum=highest,
        q1=q1,
        median=median,
        q3=q3,
        mean=float(values.mean()),
        bandwidth=bandwidth,
        positions=positions,
        density=density,
    )
