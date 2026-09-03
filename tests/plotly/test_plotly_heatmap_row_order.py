"""
A plotly heatmap has to be emitted top row first (#487).

The MAIDR grammar's heatmap data runs top-first, and the core reverses it so
its own row 0 is the bottom of the drawn grid -- which is what makes ArrowUp,
incrementing the row index, move visually up. Plotly numbers a heatmap's rows
from the *bottom*, so passing ``z`` and ``y`` through unchanged stood the chart
on its head: the cursor entered at the top row and ArrowUp walked down it.

Measured on plotly.js 3.7.0 rendered in Chromium, for
``y=['first','second','third']`` -- ``yaxis.c2p(0) = 266.67`` against
``c2p(2) = 53.33``, and a smaller pixel is higher on screen, so 'first' is the
bottom row.

The selector names one ``<image>``, because plotly rasterises the grid, so
the core synthesises its own overlay rects. That code used to place its row 0
on the top band -- an error that cancelled this one, leaving the highlight
accidentally right while navigation ran inverted. maidr#972 corrected it, so
from maidr 4.4.0 the two no longer cancel and this fix is what keeps the
highlight on the announced cell.

The matplotlib path needs no equivalent: seaborn draws its row 0 at the top
(measured ``ylim == (3.0, 0.0)``, inverted) and ``HeatPlot`` emits it first, so
it is already top-first.
"""

from __future__ import annotations

import warnings

import pytest

pytest.importorskip("plotly")
import plotly.graph_objects as go  # noqa: E402

from maidr.plotly.heatmap import PlotlyHeatmapPlot  # noqa: E402

warnings.filterwarnings("ignore")

#: Row labels in plotly's own order, which runs bottom-up.
Y = ["first", "second", "third"]
#: ``z[0]`` is 'first', the row plotly draws at the bottom.
Z = [[1, 2], [3, 4], [5, 6]]


def _emit(layout: dict | None = None) -> dict:
    """The plot data a three-row heatmap converts to.

    Parameters
    ----------
    layout : dict, optional
        The figure layout, for declaring a reversed y axis.

    Returns
    -------
    dict
        The extracted plot data, keyed by raw strings.
    """
    fig = go.Figure(go.Heatmap(x=["c1", "c2"], y=Y, z=Z))
    trace = fig.to_dict()["data"][0]
    data = PlotlyHeatmapPlot(trace, layout or {})._extract_plot_data()
    return {str(getattr(key, "value", key)): value for key, value in data.items()}


class TestOrdinaryAxis:
    """Plotly counts from the bottom, so the rows are turned over."""

    def test_emits_the_top_row_first(self) -> None:
        # 'third' is the row plotly draws at the top, so it leads.
        # Before the fix this was ['first', 'second', 'third'].
        assert _emit()["y"] == ["third", "second", "first"]

    def test_turns_the_values_over_with_their_labels(self) -> None:
        assert _emit()["points"] == [[5.0, 6.0], [3.0, 4.0], [1.0, 2.0]]

    def test_leaves_the_columns_alone(self) -> None:
        assert _emit()["x"] == ["c1", "c2"]


class TestReversedAxis:
    """A reversed axis already counts from the top and is left alone."""

    @pytest.mark.parametrize(
        "layout",
        [
            {"yaxis": {"autorange": "reversed"}},
            {"yaxis": {"range": [2.5, -0.5]}},
        ],
        ids=["autorange", "explicit-range"],
    )
    def test_passes_the_rows_through(self, layout: dict) -> None:
        # Reversing here would put the chart back upside down.
        emitted = _emit(layout)

        assert emitted["y"] == Y
        assert emitted["points"] == [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]

    def test_an_ascending_explicit_range_is_not_reversed(self) -> None:
        # A declared range that runs low to high is the ordinary case spelled
        # out, not a reversed one.
        assert _emit({"yaxis": {"range": [-0.5, 2.5]}})["y"] == [
            "third",
            "second",
            "first",
        ]


class TestPairing:
    """The half that was never broken, and must stay that way."""

    @pytest.mark.parametrize(
        "layout",
        [{}, {"yaxis": {"autorange": "reversed"}}],
        ids=["ordinary", "reversed"],
    )
    def test_every_value_stays_on_its_own_label(self, layout: dict) -> None:
        # Both arrays were reversed together even before the fix, so the
        # pairing survived; it is what a fix must not break.
        emitted = _emit(layout)
        labels, points = emitted["y"], emitted["points"]

        assert points[labels.index("first")] == [1.0, 2.0]
        assert points[labels.index("second")] == [3.0, 4.0]
        assert points[labels.index("third")] == [5.0, 6.0]


class TestRowsWithoutLabels:
    """A trace that names no rows still has them turned over."""

    def test_reverses_the_grid_when_y_is_absent(self) -> None:
        fig = go.Figure(go.Heatmap(z=Z))
        trace = fig.to_dict()["data"][0]
        data = PlotlyHeatmapPlot(trace, {})._extract_plot_data()
        points = data[next(k for k in data if str(getattr(k, "value", k)) == "points")]

        assert points == [[5.0, 6.0], [3.0, 4.0], [1.0, 2.0]]
