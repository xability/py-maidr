"""A tick a rounding error outside the data is not furniture.

``_ticks_in_view`` keeps the ticks that fall inside the data limits, so a
tick drawn past the data -- furniture -- is not read as a category. The
edge of a bar meant to sit on a tick can land a float hair past it: seaborn
dodges two hue levels to ``+-0.2`` and draws each ``0.4`` wide, so the
second level's first bar starts at ``0.2 - 0.2``, which arrives as
``5.6e-17``. When that bar was the only one at the first category, the
tick at ``0`` sat outside its own data by that much and the category was
dropped -- and with two labels left for two bars, a grouped layer paired
its bars by position and announced the first category as the second
(#752).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402

from maidr.core.enum import MaidrKey  # noqa: E402
from maidr.util.mixin import LevelExtractorMixin  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _labels(ax, key=MaidrKey.X) -> list[str]:
    return [label for _, label in LevelExtractorMixin._ticks_in_view(ax, key)]


#: A centre one float past 0.2: with a width of 0.4 the bar's edge is one
#: float past the tick at 0, which is where seaborn's offset arithmetic
#: lands it. Spelled outright rather than as `0.2`, because matplotlib's own
#: `0.2 - 0.2` is exactly zero and the premise below would not hold.
A_HAIR_PAST = float(np.nextafter(0.2, 1))


def test_a_bar_edge_a_hair_past_the_tick_keeps_the_tick() -> None:
    # The only bar at the first category is the second hue level's, and
    # matplotlib's data limits start at its edge rather than at 0.
    fig, ax = plt.subplots()
    ax.bar([A_HAIR_PAST, 0.8, 1.8], [1.0, 2.0, 3.0], width=0.4)
    ax.set_xticks([0, 1, 2], ["a", "b", "c"])

    assert ax.dataLim.x0 > 0, "the premise: the edge really is past the tick"
    assert _labels(ax) == ["a", "b", "c"]


def test_a_tick_past_the_data_is_still_dropped() -> None:
    # The filter's reason to exist, which the slack must not swallow.
    fig, ax = plt.subplots()
    ax.bar([1, 2], [1.0, 2.0])
    ax.set_xticks([0, 1, 2, 3], ["off", "a", "b", "off"])

    assert _labels(ax) == ["a", "b"]


def test_the_y_axis_reads_the_same_way() -> None:
    fig, ax = plt.subplots()
    ax.barh([A_HAIR_PAST, 0.8, 1.8], [1.0, 2.0, 3.0], height=0.4)
    ax.set_yticks([0, 1, 2], ["a", "b", "c"])

    assert ax.dataLim.y0 > 0
    assert _labels(ax, MaidrKey.Y) == ["a", "b", "c"]
