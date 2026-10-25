"""A panel of a shared-axis grid is read with the title of the axis it matches.

``make_subplots(shared_xaxes=True)`` points each panel's x axis at one other
through ``matches``; the panels share that axis's scale, plotly hides every
tick label but its own, and the author titles that one axis. Each panel's own
axis was read on its own, found no title and announced the placeholder: in
the gallery's 2x2 facet grid the top panels read "X is A" and the right-hand
ones "Y is 15.6", where the chart says Categories and Values, as an audit
that drove every example with the keyboard found. matplotlib's reader
recovers the same labels through ``sharex``/``sharey``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402
from maidr.plotly.plotly_plot import axis_title, shared_axes  # noqa: E402


def _labels(fig: go.Figure) -> list[tuple[str, str]]:
    """Each panel's x and y labels, in reading order."""
    grid = PlotlyMaidr(fig)._flatten_maidr()["subplots"]
    return [
        (
            layer[MaidrKey.AXES][MaidrKey.X][MaidrKey.LABEL],
            layer[MaidrKey.AXES][MaidrKey.Y][MaidrKey.LABEL],
        )
        for row in grid
        for cell in row
        for layer in cell["layers"]
    ]


def _facet_bars() -> go.Figure:
    """The gallery's 2x2 facet grid: titles only on the outer axes."""
    fig = make_subplots(rows=2, cols=2, shared_xaxes=True, shared_yaxes=True)
    for i in range(4):
        fig.add_trace(
            go.Bar(x=["A", "B"], y=[i + 1, i + 2]), row=i // 2 + 1, col=i % 2 + 1
        )
    fig.update_xaxes(title_text="Categories", row=2, col=1)
    fig.update_xaxes(title_text="Categories", row=2, col=2)
    fig.update_yaxes(title_text="Values", row=1, col=1)
    fig.update_yaxes(title_text="Values", row=2, col=1)
    return fig


def test_every_panel_of_a_shared_grid_reads_the_titles_it_is_drawn_against():
    assert _labels(_facet_bars()) == [("Categories", "Values")] * 4


def test_a_row_shared_y_reads_its_own_row_s_title():
    # The gallery's combined facet: `shared_yaxes="rows"`, a title on each
    # row's left axis, and an x axis shared by nothing.
    fig = make_subplots(rows=2, cols=2, shared_yaxes="rows")
    for row in (1, 2):
        for col in (1, 2):
            fig.add_trace(go.Bar(x=[0, 1], y=[1, 2]), row=row, col=col)
        fig.update_yaxes(title_text=f"Values (Row {row})", row=row, col=1)

    assert [y for _, y in _labels(fig)] == [
        "Values (Row 1)",
        "Values (Row 1)",
        "Values (Row 2)",
        "Values (Row 2)",
    ]
    # Unshared, so nothing to recover: the chart draws no title there.
    assert {x for x, _ in _labels(fig)} == {"X"}


def test_a_scatter_panel_reads_the_matched_title_too():
    fig = make_subplots(rows=1, cols=2, shared_yaxes=True)
    fig.add_trace(go.Scatter(x=[1, 2], y=[3, 4], mode="markers"), row=1, col=1)
    fig.add_trace(go.Scatter(x=[1, 2], y=[5, 6], mode="markers"), row=1, col=2)
    fig.update_yaxes(title_text="Height", row=1, col=1)

    assert [y for _, y in _labels(fig)] == ["Height", "Height"]


def test_an_axis_s_own_title_wins_over_the_one_it_matches():
    layout = {
        "xaxis": {"title": {"text": "Shared"}},
        "xaxis2": {"matches": "x", "title": {"text": "Own"}},
    }

    assert axis_title(layout, "xaxis2") == "Own"


def test_a_chain_of_matches_is_followed_to_the_end():
    layout = {
        "xaxis": {"matches": "x2"},
        "xaxis2": {"matches": "x3"},
        "xaxis3": {"title": {"text": "Time<br>(s)"}},
    }

    assert axis_title(layout, "xaxis") == "Time (s)"


def test_a_cycle_ends_rather_than_looping():
    layout = {"xaxis": {"matches": "x2"}, "xaxis2": {"matches": "x"}}

    assert [axis is layout["xaxis"] for axis in shared_axes(layout, "xaxis")] == [
        True,
        False,
    ]
    assert axis_title(layout, "xaxis") == ""


@pytest.mark.parametrize("matches", [None, "", 3, "x2 domain", "paper"])
def test_a_matches_that_names_no_axis_stops_the_chain(matches):
    layout = {"xaxis": {"matches": matches}, "xaxis2": {"title": "Elsewhere"}}

    assert len(shared_axes(layout, "xaxis")) == 1
