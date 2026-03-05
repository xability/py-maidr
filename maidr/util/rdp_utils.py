"""Ramer-Douglas-Peucker curve simplification utilities.

These helpers reduce the number of points on a curve while preserving its
shape.  They are used by :class:`~maidr.core.plot.violin_kde_plot.ViolinKdePlot`
and :class:`~maidr.core.plot.regplot.SmoothPlot` to keep the MAIDR JSON
payload compact.
"""

from __future__ import annotations

import numpy as np


def _perpendicular_distance(points: np.ndarray, start: np.ndarray, end: np.ndarray) -> np.ndarray:
    """
    Compute perpendicular distances from *points* to the line defined by
    *start* → *end*.

    Parameters
    ----------
    points : np.ndarray, shape (N, 2)
        The points to measure.
    start, end : np.ndarray, shape (2,)
        Endpoints of the reference line segment.

    Returns
    -------
    np.ndarray, shape (N,)
        Perpendicular distance of each point to the line.
    """
    line_vec = end - start
    line_len = np.linalg.norm(line_vec)
    if line_len == 0:
        return np.linalg.norm(points - start, axis=1)
    line_unit = line_vec / line_len
    diff = points - start
    cross = np.abs(diff[:, 0] * line_unit[1] - diff[:, 1] * line_unit[0])
    return cross


def rdp(points: np.ndarray, epsilon: float) -> np.ndarray:
    """
    Ramer-Douglas-Peucker algorithm for 2-D polylines.

    Parameters
    ----------
    points : np.ndarray, shape (N, 2)
        Ordered (x, y) points describing the curve.
    epsilon : float
        Maximum allowed perpendicular distance.  Larger values yield
        fewer retained points.

    Returns
    -------
    np.ndarray
        Boolean mask of length N — ``True`` for points to keep.
    """
    n = len(points)
    if n <= 2:
        return np.ones(n, dtype=bool)

    mask = np.zeros(n, dtype=bool)
    mask[0] = True
    mask[-1] = True

    # Iterative stack-based implementation (avoids Python recursion limit).
    stack: list[tuple[int, int]] = [(0, n - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi - lo <= 1:
            continue
        segment = points[lo + 1 : hi]
        dists = _perpendicular_distance(segment, points[lo], points[hi])
        max_rel = int(np.argmax(dists))
        idx = max_rel + lo + 1
        if dists[max_rel] > epsilon:
            mask[idx] = True
            stack.append((lo, idx))
            stack.append((idx, hi))

    return mask


def simplify_curve(
    points: np.ndarray,
    target: int,
    *,
    min_epsilon: float = 0.0,
    max_iterations: int = 50,
) -> np.ndarray:
    """
    Adaptively apply RDP to reduce a 2-D curve to *target* points.

    Uses binary search on *epsilon* to find the smallest tolerance that
    yields at most *target* retained points.

    Parameters
    ----------
    points : np.ndarray, shape (N, 2)
        Ordered (x, y) points.
    target : int
        Desired maximum number of retained points.
    min_epsilon : float, optional
        Lower bound for epsilon search (default ``0.0``).
    max_iterations : int, optional
        Maximum binary-search iterations (default ``50``).

    Returns
    -------
    np.ndarray
        Boolean mask of length N.
    """
    n = len(points)
    if n <= target:
        return np.ones(n, dtype=bool)

    # Estimate a reasonable upper bound for epsilon from the data extent.
    extent = np.ptp(points, axis=0)
    eps_hi = max(float(np.linalg.norm(extent)), 1e-10)
    eps_lo = min_epsilon
    best_mask = rdp(points, eps_hi)

    for _ in range(max_iterations):
        eps_mid = (eps_lo + eps_hi) / 2.0
        mask = rdp(points, eps_mid)
        count = int(np.sum(mask))
        if count <= target:
            best_mask = mask
            eps_hi = eps_mid
        else:
            eps_lo = eps_mid
        if eps_hi - eps_lo < 1e-12:
            break

    return best_mask
