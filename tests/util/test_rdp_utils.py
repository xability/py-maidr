"""``simplify_curve`` finds its tolerance without re-running RDP for every probe.

A violin's KDE layer thins each outline to a handful of levels by bisecting
for the smallest RDP tolerance that keeps at most ``target`` points. Every
probe of that bisection used to run :func:`~maidr.util.rdp_utils.rdp` from
scratch -- about 45 probes per violin, each measuring the same segments
again -- and on a 100-category ``sns.violinplot`` that search was 0.93 s of a
1.64 s render.

But ``rdp`` picks each segment's split point, the farthest one, before it
compares that distance with the tolerance, so a segment splits at the same
point whatever the tolerance; only whether the walk goes on below it
changes. So the probes share what they measure: each segment is measured
the first time a probe reaches it and looked up after that.

What is pinned here: the masks are the ones the old search found, compared
on the curves where a rewrite could quietly differ -- ties, NaN, collinear
and closed curves, and targets at and around the edges -- and no segment is
measured twice. A straight line pins the other direction: measuring every
segment up front, rather than as probes reach them, would be quadratic in
its points, since every distance on it is zero and its splits peel one point
off at a time. Both are counted rather than timed, so nothing depends on how
busy the machine is.
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
    """Shared splits give ``rdp``'s mask whatever tolerances asked before.

    The comparison is strict -- a point is kept when its distance *exceeds*
    the tolerance -- so the places a shared walk could part from ``rdp`` are
    the tolerances equal to a split's distance. Each is tried exactly and one
    representable step either side of it, in a shuffled order, all through
    one set of splits.
    """
    points = CURVES[name]
    measured: dict = {}
    rdp_utils._kept(points, -np.inf, measured)
    distances = np.unique(
        [distance for _, distance in measured.values() if np.isfinite(distance)]
    )
    tolerances = [
        eps
        for value in distances
        for eps in (np.nextafter(value, -np.inf), value, np.nextafter(value, np.inf))
    ]
    np.random.default_rng(0).shuffle(tolerances)

    shared: dict = {}
    for eps in tolerances:
        assert np.array_equal(
            rdp_utils._kept(points, eps, shared), rdp(points, eps)
        ), f"{name}: masks differ at eps={eps!r}"


def _measuring(monkeypatch) -> list:
    """Record every segment ``_perpendicular_distance`` is asked to measure."""
    asked: list = []
    measure = rdp_utils._perpendicular_distance

    def recording(points, start, end):
        asked.append((len(points), tuple(start), tuple(end)))
        return measure(points, start, end)

    monkeypatch.setattr(rdp_utils, "_perpendicular_distance", recording)
    return asked


def test_no_segment_is_measured_twice(monkeypatch) -> None:
    """Each segment is measured once, whatever the number of probes.

    A bisection that runs ``rdp`` per probe measures the root segment, and
    every segment near it, again on every probe: on this 200-point curve,
    more than a thousand passes for well under two hundred segments.
    """
    asked = _measuring(monkeypatch)
    points = CURVES["walk"]

    simplify_curve(points, 15)

    assert asked, "nothing was measured"
    assert len(asked) == len(set(asked)), (
        f"{len(asked) - len(set(asked))} of {len(asked)} measurements repeated "
        "a segment already measured"
    )


def test_a_straight_line_costs_one_pass_over_its_points(monkeypatch) -> None:
    """Segments are measured as probes reach them, not all up front.

    Every distance on a straight line is zero, so no tolerance the search
    tries keeps anything but the ends, and nothing below the root is ever
    reached. Measuring the whole split tree regardless would cost about
    ``n**2 / 2`` -- 12.5 million points here -- because each split of a line
    peels one point off; re-measuring the root on every probe cost about 50
    passes. One is what it takes.
    """
    asked = _measuring(monkeypatch)
    n = 5000
    points = np.column_stack([np.arange(float(n)), 2.0 * np.arange(float(n)) + 1.0])

    kept = simplify_curve(points, 15)

    assert kept[0] and kept[-1] and kept.sum() == 2
    measured = sum(length for length, _, _ in asked)
    assert measured <= n, f"{measured} points measured for a {n}-point line"
