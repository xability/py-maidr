"""Tests that box plots report the orientation they were actually drawn with.

The orientation reaches the MAIDR JSON as ``orientation`` and drives two
user-visible things: the announced plot type ("vertical box" / "horizontal
box") and which axis the extractor reads the Tukey statistics off. Matplotlib
3.9 deprecated ``vert`` in favour of ``orientation`` and ``Axes.boxplot``
forwards both to ``Axes.bxp``, so the detection has to read them the way
matplotlib itself does.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import packaging.version as version  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.patch.boxplot import _resolve_bxp_orientation  # noqa: E402


DATA = [[1, 2, 3, 4, 9], [2, 3, 4, 5, 6]]

# `orientation` arrived in matplotlib 3.9; older releases only accept `vert`.
# The resolver's handling of the keyword is covered version-independently by
# ``test_resolve_bxp_orientation``.
_HAS_ORIENTATION_KWARG = version.parse(matplotlib.__version__) >= version.parse("3.9")

_needs_orientation_kwarg = pytest.mark.skipif(
    not _HAS_ORIENTATION_KWARG,
    reason="matplotlib < 3.9 has no `orientation` parameter",
)


def _schema(fig) -> dict:
    """Return the first layer's schema with plain string keys."""
    plot = FigureManager.get_maidr(fig)._plots[0]
    return {(k.value if hasattr(k, "value") else k): v for k, v in plot.schema.items()}


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, "vert"),
        ({"vert": True}, "vert"),
        ({"vert": False}, "horz"),
        pytest.param(
            {"orientation": "vertical"}, "vert", marks=_needs_orientation_kwarg
        ),
        pytest.param(
            {"orientation": "horizontal"}, "horz", marks=_needs_orientation_kwarg
        ),
    ],
)
def test_matplotlib_boxplot_orientation(kwargs: dict, expected: str) -> None:
    fig, ax = plt.subplots()
    try:
        ax.boxplot(DATA, **kwargs)
        assert _schema(fig)["orientation"] == expected
    finally:
        plt.close(fig)


def test_matplotlib_vertical_boxplot_reads_statistics_off_the_y_axis() -> None:
    """A vertical box plot read as horizontal yields positions, not values."""
    fig, ax = plt.subplots()
    try:
        ax.boxplot(DATA)
        first_box = _schema(fig)["data"][0]
    finally:
        plt.close(fig)

    assert first_box["min"] == 1.0
    assert first_box["q1"] == 2.0
    assert first_box["q2"] == 3.0
    assert first_box["q3"] == 4.0
    assert first_box["max"] == 4.0
    assert first_box["upperOutliers"] == [9.0]


@pytest.mark.parametrize(
    ("orient", "expected"),
    [(None, "vert"), ("h", "horz")],
)
def test_seaborn_boxplot_orientation(orient: str | None, expected: str) -> None:
    fig, ax = plt.subplots()
    try:
        if orient is None:
            sns.boxplot(data=DATA, ax=ax)
        else:
            sns.boxplot(data=DATA, orient=orient, ax=ax)
        assert _schema(fig)["orientation"] == expected
    finally:
        plt.close(fig)


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        # `Axes.boxplot` forwards `vert=None` whenever the caller omits it, so
        # an absent `vert` must not be read as horizontal.
        ({"vert": None, "orientation": "vertical"}, "vert"),
        ({"vert": None, "orientation": "horizontal"}, "horz"),
        # An explicitly set `vert` still wins while matplotlib supports it.
        ({"vert": False, "orientation": "vertical"}, "horz"),
        ({"vert": True, "orientation": "horizontal"}, "vert"),
        # Pre-3.9 matplotlib passes `vert` alone.
        ({"vert": True}, "vert"),
        ({"vert": False}, "horz"),
        ({}, "vert"),
    ],
)
def test_resolve_bxp_orientation(kwargs: dict, expected: str) -> None:
    assert _resolve_bxp_orientation(kwargs) == expected
