"""The violin statistics MAIDR computes must be the ones plotly draws.

A plotly figure carries the *sample* for a violin, never the curve — plotly
runs the kernel density estimate in the browser. So MAIDR has to recompute it,
and that is only honest if the result is plotly's curve rather than a
defensible curve of our own. A KDE computed with different defaults is not
wrong in any way a reader could detect; it just describes a shape the chart
does not draw.

`maidr.plotly.violin_stats` therefore ports plotly's own rules rather than
using a library default, and this file pins the port against real plotly
output. `plotly_violin_reference.json` holds three samples together with the
`bandwidth`, `span`, point count, quartiles and density values plotly itself
computed for them, captured from `calcdata` in Chromium.

The comparison is to a tolerance rather than exact, and that is a measured
fact rather than a hedge. numpy and JavaScript sum in different orders, so the
last bits differ: across eight sample sizes the worst disagreement was 5.9e-15
relative on a density value. An equality assertion would fail on most inputs
while the rule was perfectly correct.

`_TOLERANCE` sits three orders of magnitude above that worst case — loose
enough that summation order never trips it, tight enough that every *rule*
this module could get wrong is caught. Reverting the sample standard deviation
to the population one, for instance, moves the bandwidth by 1.3e-2.
"""

from __future__ import annotations

import json
import math
import pathlib
import tracemalloc

import numpy as np
import pytest

from maidr.plotly.violin_stats import violin_stats

#: Comfortably above the 5.9e-15 worst case measured across eight samples,
#: and far below the ~1e-2 a wrong rule moves things by.
_TOLERANCE = 1e-12

_REFERENCE = json.loads(
    (pathlib.Path(__file__).parent / "plotly_violin_reference.json").read_text()
)

#: Every eighth density point was stored, so the fixture pins the whole curve
#: without carrying hundreds of numbers.
_DENSITY_STRIDE = 8

CASES = sorted(_REFERENCE, key=int)


def _relative(ours: float, theirs: float) -> float:
    """Relative difference, guarding the case where plotly's value is zero."""
    return abs(ours - theirs) / max(abs(theirs), 1e-300)


@pytest.mark.parametrize("size", CASES)
def test_the_bandwidth_is_plotlys(size: str) -> None:
    """The choice everything else follows from.

    A KDE's bandwidth is what decides whether the curve shows two modes or
    one, so getting it from a different rule changes what the chart is
    announced to say — not by a rounding error but by a shape.
    """
    reference = _REFERENCE[size]
    stats = violin_stats(np.array(reference["sample"]))

    assert stats is not None
    assert _relative(stats.bandwidth, reference["bandwidth"]) < _TOLERANCE


@pytest.mark.parametrize("size", CASES)
def test_the_curve_is_sampled_at_plotlys_points(size: str) -> None:
    """Same count, same positions.

    The point count follows from the span and the bandwidth together —
    `ceil(width / (bandwidth / 3))` — so it is the single assertion that
    catches a mistake in either. It is checked exactly, because a count is an
    integer and has no summation order to differ by.
    """
    reference = _REFERENCE[size]
    stats = violin_stats(np.array(reference["sample"]))

    assert stats is not None
    assert len(stats.positions) == reference["npts"]
    assert _relative(stats.positions[0], reference["span"][0]) < _TOLERANCE
    assert _relative(stats.positions[-1], reference["span"][1]) < _TOLERANCE


@pytest.mark.parametrize("size", CASES)
def test_the_density_is_plotlys(size: str) -> None:
    """The curve itself, at every stored point.

    This is the assertion the module exists to satisfy: what a reader is told
    the density is, at a position, must be what plotly drew there.
    """
    reference = _REFERENCE[size]
    stats = violin_stats(np.array(reference["sample"]))

    assert stats is not None
    for offset, (position, density) in enumerate(reference["density_every_8th"]):
        index = offset * _DENSITY_STRIDE
        assert _relative(stats.positions[index], position) < _TOLERANCE
        assert _relative(stats.density[index], density) < _TOLERANCE


@pytest.mark.parametrize("size", CASES)
def test_the_quartiles_are_plotlys(size: str) -> None:
    """Hazen, not numpy's default.

    These are announced directly rather than smoothed, so unlike the density
    a reader hears the difference as a number. `numpy.percentile`'s default
    `linear` method disagrees with plotly in the third significant figure.
    """
    reference = _REFERENCE[size]
    stats = violin_stats(np.array(reference["sample"]))

    assert stats is not None
    assert _relative(stats.q1, reference["q1"]) < _TOLERANCE
    assert _relative(stats.median, reference["med"]) < _TOLERANCE
    assert _relative(stats.q3, reference["q3"]) < _TOLERANCE


def test_the_default_quantile_rule_would_not_pass() -> None:
    """The control for the test above, so it cannot pass by coincidence.

    If plotly's quartiles happened to agree with numpy's default for these
    samples, `test_the_quartiles_are_plotlys` would pass whichever rule the
    module used and would be pinning nothing. This shows the two disagree by
    far more than the tolerance, so that test has something to catch.
    """
    disagreements = []
    for reference in _REFERENCE.values():
        sample = np.array(reference["sample"])
        linear_q1 = float(np.percentile(sample, 25, method="linear"))
        disagreements.append(_relative(linear_q1, reference["q1"]))

    assert max(disagreements) > _TOLERANCE * 1000


def test_a_constant_sample_keeps_plotlys_single_point() -> None:
    """Plotly special-cases it rather than skipping it.

    Its bandwidth comes out zero, so plotly emits one density point of 1 at
    the value and draws a degenerate violin there -- measured in Chromium, the
    category still gets its own `path.violin`. Returning `None` here would
    take a category the chart visibly draws out of the reading altogether,
    which is worse than a curve with one point; inventing a spread for it
    would be worse still.
    """
    stats = violin_stats(np.array([5.0, 5.0, 5.0]))

    assert stats is not None
    assert stats.bandwidth == 0.0
    assert list(stats.positions) == [5.0]
    assert list(stats.density) == [1.0]
    assert (stats.minimum, stats.q1, stats.median, stats.q3, stats.maximum) == (
        5.0,
        5.0,
        5.0,
        5.0,
        5.0,
    )


def test_an_empty_sample_has_no_curve() -> None:
    """Nothing to describe, and nothing to divide by."""
    assert violin_stats(np.array([])) is None


def test_non_finite_values_are_dropped() -> None:
    """A gap is not a value at zero.

    Plotly ignores a `None` in the sample. Letting a `NaN` through instead
    would poison every density point via the kernel sum, and letting it become
    a zero would put an observation at a place nothing was measured.
    """
    with_gaps = violin_stats(np.array([1.0, np.nan, 2.0, 3.0, np.inf]))
    without = violin_stats(np.array([1.0, 2.0, 3.0]))

    assert with_gaps is not None and without is not None
    assert with_gaps.bandwidth == without.bandwidth
    assert np.allclose(with_gaps.density, without.density)


@pytest.mark.parametrize("size", CASES)
def test_the_density_is_a_density(size: str) -> None:
    """It integrates to about one, and never goes negative.

    A property check rather than a comparison, so it holds even for samples
    the fixture does not carry. The tails are cut two bandwidths out, so the
    integral is a little under one rather than exactly one.
    """
    stats = violin_stats(np.array(_REFERENCE[size]["sample"]))

    assert stats is not None
    assert (stats.density >= 0).all()

    area = float(np.trapezoid(stats.density, stats.positions))
    assert 0.9 < area <= 1.0, area


def test_the_kernel_is_evaluated_in_linear_memory() -> None:
    """One row of the kernel at a time, never the whole (points x n) matrix.

    The outer product costs `intervals * n` doubles three times over, and
    `intervals` grows with `n`: measured, 260 MB at n=50,000 and 1.5 GB at
    n=200,000 -- for every violin on the subplot. Evaluating position by
    position is O(n) and, because each row of that matrix is reduced by the
    same pairwise summation as a one-dimensional array, bit-identical; the
    reference tests above are what guard the values.
    """
    sample = np.random.default_rng(0).normal(size=50_000)

    tracemalloc.start()
    try:
        stats = violin_stats(sample)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert stats is not None
    assert peak < 16 * 1024 * 1024, f"peak {peak / 1e6:.0f} MB"


def test_a_shifted_sample_shifts_its_curve() -> None:
    """Adding a constant moves the curve and changes nothing else.

    Catches an absolute value that should have been relative — a span or a
    bandwidth computed from the raw numbers rather than from their spread
    would survive every fixture comparison above and fail here.
    """
    sample = np.array(_REFERENCE[CASES[0]]["sample"])
    shift = 1000.0

    original = violin_stats(sample)
    shifted = violin_stats(sample + shift)

    assert original is not None and shifted is not None
    assert math.isclose(original.bandwidth, shifted.bandwidth, rel_tol=1e-12)
    assert np.allclose(original.positions + shift, shifted.positions)
    assert np.allclose(original.density, shifted.density)
