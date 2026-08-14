"""A regression line in one panel was deleting a line chart in another.

``regplot`` draws its fit through ``ax.plot``, so one curve registers both a
``LINE`` and a ``SMOOTH``. ``smooth`` is what it is and the ``line`` is the
duplicate — that much was right. What was wrong is that the question was asked
of the whole figure:

    has_smooth = any(plot.type == PlotType.SMOOTH for plot in plots)
    if has_smooth:
        return [plot for plot in plots if plot.type != PlotType.LINE]

*Any* smooth anywhere, then drop *every* line anywhere. The same shape of
defect as #376, one function call below the code that fixed it.

Two things followed, and neither errored:

    a regplot in panel 0      panel 1's line chart deleted, and the grid
                              collapsed from 1x2 to 1x1, since no surviving
                              layer carried the second column index
    a line drawn first        every kept layer inherited its predecessor's
                              selector id, so the highlight landed one layer
                              off

The second is the quieter one and only bites when the dropped layer is not
last, which is why it survived: `selector_ids` was never filtered alongside
`_plots`, and the two are paired by index in both directions (#378).
"""

from __future__ import annotations

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    """Two numeric columns, enough for a regression fit."""
    rng = np.random.default_rng(20260814)
    return pd.DataFrame({"a": rng.normal(size=40), "b": rng.normal(size=40)})


def _emitted(fig) -> list[list[list[str]]]:
    """The layer types of every subplot cell, as a row-major grid."""
    grid = FigureManager.get_maidr(fig)._flatten_maidr()["subplots"]
    return [
        [[layer["type"].value for layer in cell.get("layers", [])] for cell in row]
        for row in grid
    ]


def test_a_panel_with_no_fit_keeps_its_line() -> None:
    """The headline: a fit in one panel deleted a line chart in another.

    Panel 1 is written identically in both halves. Adding a ``regplot`` to
    panel 0 used to delete panel 1's line — and with it panel 1, since the
    grid's column count comes from the surviving layers' indices and nothing
    left carried column 1.
    """
    fig, axes = plt.subplots(1, 2)
    axes[0].scatter([1, 2, 3], [1, 2, 3])
    axes[1].plot([1, 2, 3], [3, 2, 1])

    assert _emitted(fig) == [[["point"], ["line"]]]
    plt.close(fig)

    fig, axes = plt.subplots(1, 2)
    sns.regplot(data=_frame(), x="a", y="b", ax=axes[0])
    axes[1].plot([1, 2, 3], [3, 2, 1])

    assert _emitted(fig) == [[["point", "smooth"], ["line"]]]


def test_a_fit_still_supersedes_the_line_it_drew() -> None:
    """The behaviour that was right, and has to stay right.

    ``regplot`` draws its fit through ``ax.plot``, so the curve arrives twice.
    Scoping the rule per axes must not stop it firing on the axes it belongs
    to — otherwise the fitted curve is announced once as a fit and again as
    though it were data.
    """
    fig, ax = plt.subplots()
    sns.regplot(data=_frame(), x="a", y="b", ax=ax)

    types = [plot.type for plot in FigureManager.get_maidr(fig).plots]
    assert PlotType.LINE not in types

    assert _emitted(fig) == [[["point", "smooth"]]]


def test_a_deliberate_line_over_a_fit_is_kept() -> None:
    """A reference line on the same axes as a fit is not the fit's duplicate.

    This is the case the per-axes scoping cannot distinguish and does not try
    to: both layers are on one axes, so the line is dropped. Pinned rather
    than left to be discovered — the rule is "a fit supersedes the lines on
    its axes", and an annotation drawn there is collateral.

    Naming it here means the day it is fixed, this test fails and has to be
    rewritten, rather than the behaviour quietly changing.
    """
    fig, ax = plt.subplots()
    sns.regplot(data=_frame(), x="a", y="b", ax=ax)
    ax.plot([-2, 2], [0, 0], label="zero")

    assert _emitted(fig) == [[["point", "smooth"]]]


def test_every_kept_layer_keeps_its_own_selector_id() -> None:
    """The quiet half, and the one that needs the dropped layer not to be last.

    ``_plots`` and ``selector_ids`` are paired by index in both directions:
    the artists are tagged with ``selector_ids[i]`` and the schema stamps the
    same index into the layer's selector string. The old dedup filtered one
    list and not the other, so every layer after the dropped one inherited its
    predecessor's id and the highlight landed one layer off, with nothing
    raised.

    The line is drawn *first* here so it is not the last registration —
    filtering only ``_plots`` is invisible when the drop is at the end.
    """
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [3, 2, 1])
    sns.regplot(data=_frame(), x="a", y="b", ax=ax)

    figure_maidr = FigureManager.get_maidr(fig)
    issued = list(figure_maidr.selector_ids)
    dropped = [plot.type for plot in figure_maidr.plots].index(PlotType.LINE)
    assert dropped == 0, "the line must not be the last registration"

    figure_maidr._flatten_maidr()

    assert len(figure_maidr.selector_ids) == len(figure_maidr.plots)
    assert figure_maidr.selector_ids == issued[1:]
