"""Ramer-Douglas-Peucker curve simplification utilities.

These helpers reduce the number of points on a curve while preserving its
*shape*, dropping vertices that already sit close to the chord between their
neighbours.  :class:`~maidr.core.plot.violin_kde_plot.ViolinKdePlot` uses them
to pick the levels that outline a violin.

Shape is the wrong objective for a curve that is navigated and sonified one
point at a time, where the steps have to stay evenly spaced instead; see
:func:`~maidr.util.resample_utils.resample_curve` for that.

This module mirrors r-maidr's ``R/rdp_utils.R``, so a change to either
belongs in both.
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


def _kept(points: np.ndarray, epsilon: float, splits: dict) -> np.ndarray:
    """
    The mask ``rdp(points, epsilon)`` returns, reusing the splits measured so far.

    :func:`rdp` chooses each segment's split point -- the farthest one --
    before it compares that distance with ``epsilon``, so a segment splits at
    the same point whatever the tolerance; only whether the walk goes on
    below it changes. The search in :func:`simplify_curve` asks that of the
    same segments at every probe, so each one is measured the first time a
    probe reaches it and looked up after that.

    The walk is otherwise :func:`rdp`'s own, and that is what keeps it from
    costing more than :func:`rdp` ever did: a segment is measured only once a
    probe reaches it, so a curve that splits no further than its root -- a
    straight line, whose every distance is zero -- costs one pass over its
    points however many probes ask. Measuring every segment up front would be
    quadratic in the points for such a curve, since its splits peel one point
    off at a time.

    Parameters
    ----------
    points : np.ndarray, shape (N, 2)
        Ordered (x, y) points describing the curve.
    epsilon : float
        Maximum allowed perpendicular distance, as for :func:`rdp`.
    splits : dict
        ``(lo, hi)`` to ``(index, distance)`` for every segment measured so
        far, added to as new ones are reached. Pass the same dict for every
        tolerance asked of one curve.

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

    stack: list[tuple[int, int]] = [(0, n - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi - lo <= 1:
            continue
        split = splits.get((lo, hi))
        if split is None:
            segment = points[lo + 1 : hi]
            dists = _perpendicular_distance(segment, points[lo], points[hi])
            max_rel = int(np.argmax(dists))
            split = splits[(lo, hi)] = (max_rel + lo + 1, dists[max_rel])
        idx, distance = split
        if distance > epsilon:
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

    # Every probe of the search below walks the splits the probes before it
    # walked, so each segment is measured once rather than once per probe:
    # the masks are exactly the ones `rdp(points, eps)` returns.
    splits: dict = {}
    best_mask = _kept(points, eps_hi, splits)

    for _ in range(max_iterations):
        eps_mid = (eps_lo + eps_hi) / 2.0
        mask = _kept(points, eps_mid, splits)
        count = int(np.sum(mask))
        if count <= target:
            best_mask = mask
            eps_hi = eps_mid
        else:
            eps_lo = eps_mid
        if eps_hi - eps_lo < 1e-12:
            break

    return best_mask
