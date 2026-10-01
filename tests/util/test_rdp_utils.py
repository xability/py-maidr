"""``simplify_curve`` finds its tolerance without re-running RDP for every probe.

A violin's KDE layer thins each outline to a handful of levels by bisecting
for the smallest RDP tolerance that keeps at most ``target`` points. Every
probe of that bisection used to run :func:`~maidr.util.rdp_utils.rdp` from
scratch -- about 45 probes per violin, each walking the curve again -- and on
a 100-category ``sns.violinplot`` that search was 0.93 s of a 1.64 s render.

But ``rdp`` picks each segment's split point, the farthest one, before it
compares that distance with the tolerance, so the tree of splits is the same
for every tolerance; only how deep it is followed changes. Walking the tree
once and recording, per point, the smallest distance on its path from the
root answers every probe at once: a point is kept exactly when that
threshold exceeds the tolerance.

That claim is what these tests pin. The masks are compared with the old
search, kept here as the reference, on the curves where a rewrite could
quietly differ -- ties, NaN, collinear and closed curves, and targets at and
around the edges -- and one test counts the walk itself, without timing
anything on a shared machine.
"""

from __future__ import annotations

import numpy as np
import pytest

from maidr.util import rdp_utils
from maidr.util.rdp_utils import rdp, simplify_curve


def _bisect_with_rdp(
    points: np.ndarray,
    target: int,
    *,
    min_epsilon: float = 0.0,
    max_iterations: int = 50,
) -> np.ndarray:
    """The search ``simplify_curve`` ran before: a full ``rdp`` per probe."""
    n = len(points)
    if n <= target:
        return np.ones(n, dtype=bool)

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


def _curves() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(0)
    levels = np.linspace(-3.0, 3.0, 100)
    # The shape a violin hands over: KDE width against level, two bumps.
    violin = np.column_stack(
        [levels, np.exp(-((levels + 1) ** 2)) + 0.6 * np.exp(-((levels - 1.2) ** 2))]
    )
    walk = np.column_stack([np.arange(200.0), rng.normal(size=200).cumsum()])
    # Every interior point equally far from the chord, so `argmax` ties at
    # every split and the first of them has to win both ways.
    zigzag = np.column_stack(
        [np.arange(41.0), np.where(np.arange(41) % 2 == 0, 0.0, 1.0)]
    )
    zigzag[-1, 1] = 0.0
    straight = np.column_stack([np.arange(30.0), 2.0 * np.arange(30.0) + 1.0])
    angles = np.linspace(0.0, 2.0 * np.pi, 60)
    # Closed: the two ends coincide, so the chord has no length and distance
    # falls back to the distance from the start point.
    closed = np.column_stack([np.cos(angles), np.sin(angles)])
    closed[-1] = closed[0]
    gappy = walk[:80].copy()
    gappy[[5, 40], 1] = np.nan
    repeated = np.repeat(walk[:30], 3, axis=0)
    return {
        "violin": violin,
        "walk": walk,
        "zigzag": zigzag,
        "straight": straight,
        "closed": closed,
        "nan": gappy,
        "repeated": repeated,
        "integer-grid": np.column_stack(
            [np.arange(25.0), rng.integers(0, 4, size=25).astype(float)]
        ),
        "three": walk[:3],
        "two": walk[:2],
        "one": walk[:1],
    }


CURVES = _curves()


@pytest.mark.parametrize("name", list(CURVES))
@pytest.mark.parametrize("target", [0, 1, 2, 3, 5, 15, 29])
def test_the_mask_is_the_one_the_old_search_found(name: str, target: int) -> None:
    points = CURVES[name]

    got = simplify_curve(points, target)
    want = _bisect_with_rdp(points, target)

    assert got.dtype == want.dtype == bool
    assert np.array_equal(got, want)


@pytest.mark.parametrize("name", list(CURVES))
def test_a_target_at_or_beyond_the_length_keeps_every_point(name: str) -> None:
    points = CURVES[name]

    for target in (len(points), len(points) + 1):
        got = simplify_curve(points, target)
        assert got.all()
        assert np.array_equal(got, _bisect_with_rdp(points, target))


@pytest.mark.parametrize("name", ["violin", "walk", "zigzag", "closed", "nan"])
def test_every_tolerance_keeps_what_rdp_keeps(name: str) -> None:
    """``rdp(points, eps)`` and the thresholds agree on both sides of each one.

    The comparison is strict -- a point is kept when its distance *exceeds*
    the tolerance -- so the one place a threshold-based reading could part
    from ``rdp`` is a tolerance equal to a threshold. Each is tried exactly,
    and one representable step either side of it.
    """
    points = CURVES[name]
    thresholds = rdp_utils._keep_thresholds(points)

    finite = thresholds[np.isfinite(thresholds)]
    for value in np.unique(finite):
        for eps in (np.nextafter(value, -np.inf), value, np.nextafter(value, np.inf)):
            assert np.array_equal(
                rdp_utils._kept(thresholds, eps), rdp(points, eps)
            ), f"{name}: masks differ at eps={eps!r}"


def test_the_split_tree_is_walked_once(monkeypatch) -> None:
    """Each interior point is measured as a split point once, whatever the probes.

    A bisection that runs ``rdp`` per probe measures the same segments again
    on every probe -- on this 200-point curve, more than a thousand distance
    passes. Walking the tree once takes at most one per interior point.
    """
    calls = 0
    measure = rdp_utils._perpendicular_distance

    def counting(*args):
        nonlocal calls
        calls += 1
        return measure(*args)

    monkeypatch.setattr(rdp_utils, "_perpendicular_distance", counting)
    points = CURVES["walk"]

    simplify_curve(points, 15)

    assert calls <= len(points) - 2, (
        f"{calls} distance passes for {len(points)} points: the split tree is "
        "being walked again for every probe of the search"
    )
