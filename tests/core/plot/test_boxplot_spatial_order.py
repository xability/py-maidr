"""Horizontal boxes export top-to-bottom rows and matching artists (#911)."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402
from maidr.core.figure_manager import FigureManager  # noqa: E402


DATA = [[1, 2, 3, 4, 5], [10, 20, 30, 40, 50]]
LABELS = ["Africa", "Europe"]


def _draw(library: str, horizontal: bool) -> tuple[plt.Figure, plt.Axes]:
    """Draw the same two categories through either plotting library."""
    fig, ax = plt.subplots()
    if library == "seaborn":
        categories = [label for label in LABELS for _ in range(5)]
        values = [value for group in DATA for value in group]
        sns.boxplot(
            x=values if horizontal else categories,
            y=categories if horizontal else values,
            order=LABELS,
            orient="h" if horizontal else "v",
            ax=ax,
        )
    else:
        ax.boxplot(DATA, vert=not horizontal)
        set_ticks = ax.set_yticks if horizontal else ax.set_xticks
        set_ticks([1, 2], LABELS)
    return fig, ax


@pytest.mark.parametrize("library", ["matplotlib", "seaborn"])
@pytest.mark.parametrize("invert", [False, True])
@pytest.mark.parametrize("horizontal", [False, True])
def test_box_rows_follow_axis_direction(
    library: str, invert: bool, horizontal: bool
) -> None:
    """Pair rows and artists on first render and after a layer re-render."""
    fig, ax = _draw(library, horizontal)
    if invert:
        ax.invert_yaxis()
    plot = FigureManager.get_maidr(fig).plots[0]

    # Re-render after changing the direction, too: seaborn inverts its category
    # axis after the patched bxp call, so registration-time direction is stale.
    for render_index in range(2):
        if render_index:
            ax.invert_yaxis()
        layer = plot.render()
        rows, selectors = layer["data"], layer["selectors"]
        expected = [0, 1]
        if horizontal and not ax.yaxis_inverted():
            expected.reverse()
        assert [row["z"] for row in rows] == [LABELS[i] for i in expected]
        assert [row["q2"] for row in rows] == [DATA[i][2] for i in expected]
        assert len(rows) == len(selectors) == 2

        boxes = plot._bxp_stats["boxes"]
        medians = plot._bxp_stats["medians"]
        for selector, index in zip(selectors, expected):
            assert selector["iq"] == f"g[id='{boxes[index].get_gid()}'] > path"
            assert selector["q2"] == f"g[id='{medians[index].get_gid()}'] > path"

        if horizontal:
            fig.canvas.draw()
            centers = [
                boxes[index].get_window_extent().y0
                + boxes[index].get_window_extent().height / 2
                for index in expected
            ]
            # Matplotlib display coordinates increase upward.
            assert centers[0] > centers[1]
