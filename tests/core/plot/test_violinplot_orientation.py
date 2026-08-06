"""Tests that violin plots report the orientation they were actually drawn with.

``Axes.violinplot`` took the same ``vert`` → ``orientation`` migration as
``Axes.boxplot``, and both of a violin's layers (``violin_box`` and
``violin_kde``) carry the resolved orientation into the MAIDR JSON, where it
decides the announced plot type and which axis the data is read along.
"""

from __future__ import annotations

import inspect

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402


DATA = [[1, 2, 3, 4, 9], [2, 3, 4, 5, 6]]

_needs_orientation_kwarg = pytest.mark.skipif(
    "orientation" not in inspect.signature(Axes.violinplot).parameters,
    reason="this matplotlib has no `orientation` parameter on Axes.violinplot",
)


def _orientations(fig) -> list[str]:
    """Return the orientation of every layer registered for the figure."""
    return [
        {(k.value if hasattr(k, "value") else k): v for k, v in plot.schema.items()}[
            "orientation"
        ]
        for plot in FigureManager.get_maidr(fig).plots
    ]


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
def test_matplotlib_violinplot_orientation(kwargs: dict, expected: str) -> None:
    """Both layers of the violin agree on the orientation it was drawn with."""
    fig, ax = plt.subplots()
    try:
        ax.violinplot(DATA, **kwargs)
        orientations = _orientations(fig)
    finally:
        plt.close(fig)

    assert orientations, "violinplot registered no layers"
    assert orientations == [expected] * len(orientations)


def test_matplotlib_violinplot_orientation_passed_positionally() -> None:
    """`ax.violinplot(dataset, positions, vert)` still binds `vert` by position.

    Unlike `Axes.boxplot`, this patch wraps the call the user made, so the
    positional argument reaches it verbatim.
    """
    fig, ax = plt.subplots()
    try:
        try:
            ax.violinplot(DATA, None, False)
        except TypeError:
            # Matplotlib says these become keyword-only in 3.12.
            pytest.skip("this matplotlib no longer accepts `vert` positionally")
        orientations = _orientations(fig)
    finally:
        plt.close(fig)

    assert orientations, "violinplot registered no layers"
    assert orientations == ["horz"] * len(orientations)


@pytest.mark.parametrize(
    ("orient", "expected"),
    [(None, "vert"), ("h", "horz")],
)
def test_seaborn_violinplot_orientation(orient: str | None, expected: str) -> None:
    fig, ax = plt.subplots()
    try:
        if orient is None:
            sns.violinplot(data=DATA, ax=ax)
        else:
            sns.violinplot(data=DATA, orient=orient, ax=ax)
        orientations = _orientations(fig)
    finally:
        plt.close(fig)

    assert orientations, "violinplot registered no layers"
    assert orientations == [expected] * len(orientations)
