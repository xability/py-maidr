"""Even curve resampling.

Thins a curve by spreading the points it keeps evenly, rather than by where
the curve bends.  :class:`~maidr.core.plot.regplot.SmoothPlot` needs that: its
points are navigated and auto-played one at a time at a fixed rate, so the
spacing between them is what a reader hears, and
:func:`~maidr.util.rdp_utils.simplify_curve` would collapse a straight fit to
its two endpoints.

r-maidr has no counterpart, since its smooth processor emits every vertex the
plot was built with.
"""

from __future__ import annotations

import numpy as np


def resample_curve(points: np.ndarray, target: int) -> np.ndarray:
    """
    Thin a 2-D curve down to *target* evenly spaced vertices.

    Unlike :func:`simplify_curve`, this keeps the retained vertices spread
    evenly along the curve rather than clustering them where the curve bends.
    A straight line therefore survives as *target* points instead of
    collapsing to its two endpoints, and a curved line keeps a steady step
    size.  The first and last vertices are always kept.

    Spacing is measured along x whenever x increases monotonically, which
    covers every curve seaborn fits.  Sampling by vertex index instead would
    only be even in x when the source grid already was — true of a plain
    ``regplot`` fit or a KDE, but not of a ``lowess=True`` fit, which lands on
    the observed x values and inherits their clustering.  Anything else — a
    curve that doubles back, or one running right to left — falls back to
    index sampling.

    Spacing is even in whatever space the caller hands over, so a caller that
    wants evenness on screen rather than in raw data has to convert before
    calling and back afterwards.

    Interpolated points sit on the drawn line, which matters because they are
    what the highlight ring lands on.  Matplotlib renders the curve as straight
    segments between its vertices, so interpolating in scale space — an affine
    map away from the display — walks exactly that path.  That exactness is
    the caller's to earn, though: handing over data coordinates for a
    nonlinear axis instead leaves the points a fraction of a pixel off the
    segment.

    Parameters
    ----------
    points : np.ndarray, shape (N, 2)
        Ordered (x, y) points.
    target : int
        Desired number of retained points.  Values below 2 are raised to 2,
        since the endpoints alone already describe a segment.

    Returns
    -------
    np.ndarray, shape (M, 2)
        The resampled points, where ``M == min(N, max(target, 2))``.  A curve
        that already fits the budget comes back as *points* itself, not a
        copy, so callers that intend to mutate the result should copy it.
    """
    n = len(points)
    count = max(int(target), 2)
    if n <= count:
        return points

    x, y = points[:, 0], points[:, 1]
    if np.all(np.diff(x) > 0):
        grid = np.linspace(x[0], x[-1], count)
        return np.column_stack([grid, np.interp(grid, x, y)])

    # Left-to-right is the only order worth special-casing, since it is the one
    # every fit produces; a decreasing or self-crossing curve falls through to
    # even spacing by vertex index rather than growing a case for each shape.
    # ``n > count >= 2`` puts the step ``(n - 1) / (count - 1)`` strictly above
    # 1, so rounding can never land two samples on the same vertex: the result
    # always holds exactly ``count`` distinct points.
    idx = np.rint(np.linspace(0, n - 1, count)).astype(int)
    return points[idx]
