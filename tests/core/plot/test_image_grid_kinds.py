"""
A heat layer assumed every grid it was handed was scalar (#564).

``ax.imshow`` accepts three shapes. ``(M, N)`` of numbers is a heatmap;
``(M, N, 3)`` and ``(M, N, 4)`` are **pictures**, their last axis colour
rather than value. A boolean ``(M, N)`` mask is a fourth case, and the one
``ax.spy()`` draws.

All three of the last ones raised at *render*, after the plotting line had
returned, from one line of ``HeatPlot``::

    [list(map(lambda x: float(format(x, self._fmt)), row)) for row in array]

``self._fmt`` is ``""`` unless seaborn's caller set one, and ``format`` with
an empty spec is ``str``: ``'True'`` for a numpy bool, ``'[0.5 0.5 0.5]'``
for a row of an RGB image. Measured before the fix::

    ax.imshow(np.zeros((2, 2, 3)) + 0.5)
    ValueError: could not convert string to float: '[0.5 0.5 0.5]'

    ax.spy(np.eye(3))
    ValueError: could not convert string to float: 'True'

and it was never confined to that axes -- a bar chart drawn beside the
picture died with it.

The two get different answers, which is the point of this file:

- **a mask is read.** True and False are 1 and 0, and showing where a matrix
  is non-zero is the whole purpose of ``spy()``. It only failed at the
  default format; ``format(np.True_, ".2f")`` was already ``"1.00"``.
- **a colour image is not registered.** There is no number per cell to
  announce and nothing for the colourbar to mean, so the layer is declined
  and the figure renders without it -- what ``ax.quiver`` already does.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pytest

import maidr
from maidr.core.figure_manager import FigureManager


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _points(fig) -> list:
    """Every heat layer's grid of values, in registration order."""
    return [plot.schema["data"]["points"] for plot in FigureManager.get_maidr(fig).plots]


def _types(fig) -> list:
    """Every layer's type, or an empty list when the figure registered none."""
    try:
        return [plot.type.value for plot in FigureManager.get_maidr(fig).plots]
    except Exception:  # noqa: BLE001 - no Maidr at all is the case under test
        return []


# ---------------------------------------------------------------------------
# A boolean grid is read
# ---------------------------------------------------------------------------


def test_a_sparsity_pattern_reads_as_ones_and_zeros():
    fig, ax = plt.subplots()
    ax.spy(np.eye(3))

    maidr.render(fig)._repr_html_()  # must not raise

    assert _points(fig) == [
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    ]


def test_a_boolean_image_reads_the_same_way():
    fig, ax = plt.subplots()
    ax.imshow(np.array([[True, False], [False, True]]))

    assert _points(fig) == [[[1.0, 0.0], [0.0, 1.0]]]


def test_a_boolean_mesh_reads_the_same_way():
    # `pcolormesh` reaches the formatting through a different artist class and
    # a different reshape, so the mask has to be handled where the values are
    # rather than where `imshow` happens to arrive.
    fig, ax = plt.subplots()
    ax.pcolormesh(np.array([[True, False], [False, True]]))

    assert _points(fig) == [[[1.0, 0.0], [0.0, 1.0]]]


def test_a_mask_reads_the_same_under_an_explicit_format():
    # The defect was only ever at the default format -- `format(np.True_,
    # ".2f")` was already "1.00" -- so a fix that special-cased the empty
    # spelling would pass every assertion above and change what a seaborn
    # caller's format produced. Both spellings must give the same 1 and 0.
    import seaborn as sns

    fig, ax = plt.subplots()
    sns.heatmap(np.array([[True, False], [False, True]]), fmt=".2f", ax=ax)

    assert _points(fig) == [[[1.0, 0.0], [0.0, 1.0]]]


def test_a_numeric_grid_is_unchanged():
    fig, ax = plt.subplots()
    ax.imshow(np.arange(4).reshape(2, 2))

    assert _points(fig) == [[[0.0, 1.0], [2.0, 3.0]]]


# ---------------------------------------------------------------------------
# A colour image is not a heatmap
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("channels", [3, 4])
def test_a_colour_image_registers_no_layer(channels):
    fig, ax = plt.subplots()
    ax.imshow(np.zeros((2, 2, channels)) + 0.5)

    assert len(maidr.render(fig)._repr_html_()) > 0  # must not raise
    assert _types(fig) == []


def test_an_integer_colour_image_is_declined_too():
    # `imshow` takes RGB as floats in 0..1 or as uint8 in 0..255, and the
    # dtype is what a value-shaped test would key on. What makes it a picture
    # is the third axis, not what is stored along it.
    fig, ax = plt.subplots()
    ax.imshow(np.zeros((2, 2, 3), dtype=np.uint8))

    assert len(maidr.render(fig)._repr_html_()) > 0
    assert _types(fig) == []


def test_a_chart_beside_a_picture_survives_it():
    # The blind spot the crash really cost: an unreadable image took every
    # other chart in the figure with it, because the render walks all layers.
    fig, (left, right) = plt.subplots(1, 2)
    left.bar(["x", "y"], [1, 2])
    right.imshow(np.zeros((2, 2, 3)) + 0.5)

    assert len(maidr.render(fig)._repr_html_()) > 0
    assert _types(fig) == ["bar"]


def test_a_picture_beside_a_grid_leaves_the_grid_its_own_values():
    # Declining must remove the layer, not shift which artist the surviving
    # one binds to: `_grid_of` falls back to the *last* grid on the axes, and
    # the picture is drawn after the mesh here.
    fig, ax = plt.subplots()
    ax.pcolormesh(np.arange(4).reshape(2, 2))
    ax.imshow(np.zeros((2, 2, 3)) + 0.5)

    assert _types(fig) == ["heat"]
    assert _points(fig) == [[[0.0, 1.0], [2.0, 3.0]]]


def test_a_grayscale_image_is_still_a_heatmap():
    # Two dimensions and no colour axis: a photograph in one channel is read
    # as the grid of intensities it is, which is the pre-existing behaviour
    # and the line the decline must not cross.
    fig, ax = plt.subplots()
    ax.imshow(np.array([[0.0, 0.5], [1.0, 0.25]]))

    assert _points(fig) == [[[0.0, 0.5], [1.0, 0.25]]]
