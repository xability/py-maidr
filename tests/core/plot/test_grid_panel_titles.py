"""
Every panel of a ``pairplot`` announced itself as ``Subplot N`` (#660).

A layer's title is the axes title, and seaborn titles neither grid's cells --
it labels the grid's outer edge with axis labels instead. So the figure
lobby, which reads back the focused subplot's title, had nothing to read::

    Subplot 1 of 9: This is a hist plot.  Press 'ENTER' to select this subplot.
    Subplot 2 of 9: This is a point plot. Press 'ENTER' to select this subplot.
    Subplot 3 of 9: This is a point plot. Press 'ENTER' to select this subplot.

Six of the nine were ``point`` and three were ``hist``, and nothing told them
apart. A reader looking for "flipper length against bill depth" had to enter
each panel, read a data point for its axis labels, and back out -- nine
times, on a chart whose entire purpose is that its panels are comparable.

The names are **looked up, not inferred**: ``PairGrid`` declares its
``x_vars``, ``y_vars`` and ``diag_vars``, and ``JointGrid`` names its three
axes structurally, so nothing here reads a panel's meaning off where it sits.
That distinction is the one #516 drew when it removed the
axis-label-from-position heuristic.

Measured on seaborn 0.13.2, and the reason the diagonal needs its own pass:

    diag_axes[0] is axes[0][0]?  False

``map_diag`` draws a pairplot's univariate panels on **twin** axes, so a
title recorded against the grid cell never reaches the histogram.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
import seaborn as sns
from seaborn.axisgrid import PairGrid

import maidr
from maidr.core.figure_manager import FigureManager


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "alpha": rng.normal(size=30),
            "beta": rng.normal(size=30) + 1,
            "gamma": rng.normal(size=30) + 2,
        }
    )


def _titles(fig) -> list[tuple[str, str]]:
    """Every layer as ``(type, title)``, after a real render."""
    maidr.render(fig)._repr_html_()
    return [
        (plot.type.value, plot.schema.get("title"))
        for plot in FigureManager.get_maidr(fig).plots
    ]


def test_a_pairplots_panels_name_the_variables_they_draw():
    titles = _titles(sns.pairplot(_frame(), vars=["alpha", "beta"]).figure)

    # "y vs x", in the order the panel's own axis labels announce once a
    # reader is inside it, so the lobby and the panel agree.
    assert sorted(titles) == sorted(
        [
            ("hist", "alpha"),
            ("point", "alpha vs beta"),
            ("point", "beta vs alpha"),
            ("hist", "beta"),
        ]
    )


def test_every_panel_of_a_three_variable_pairplot_is_distinct():
    # The cost this fixes, stated as the property that was missing: nine
    # panels, and no two announcing the same thing.
    titles = _titles(sns.pairplot(_frame()).figure)

    assert len(titles) == 9
    assert len({title for _, title in titles}) == 9
    assert all(title for _, title in titles)


def test_a_diagonal_panel_is_named_though_it_is_drawn_on_a_twin():
    # `map_diag` puts the univariate panel on a twin of the grid cell, so a
    # title recorded against the cell reaches nothing. Asserted directly:
    # without the `map_diag` pass these three come back empty.
    titles = _titles(sns.pairplot(_frame()).figure)

    assert sorted(t for kind, t in titles if kind == "hist") == [
        "alpha",
        "beta",
        "gamma",
    ]


def test_a_jointplots_three_panels_are_named():
    # Each panel is pinned by its own axis labels rather than by a sorted bag
    # of titles: both marginals are `hist` and both are named after one of
    # the same two variables, so a bag cannot tell the top marginal from the
    # right one -- and naming them after each other is exactly the mistake
    # worth catching. The top marginal draws x against a count; the right
    # marginal is the same figure turned on its side.
    grid = sns.jointplot(data=_frame(), x="alpha", y="beta")
    maidr.render(grid.figure)._repr_html_()
    panels = [
        (
            plot.type.value,
            plot.schema.get("title"),
            plot.schema["axes"]["x"]["label"],
            plot.schema["axes"]["y"]["label"],
        )
        for plot in FigureManager.get_maidr(grid.figure).plots
    ]

    assert sorted(panels) == sorted(
        [
            ("hist", "alpha", "alpha", "Count"),
            ("point", "beta vs alpha", "alpha", "beta"),
            ("hist", "beta", "Count", "beta"),
        ]
    )


def test_an_authors_own_title_wins():
    # The generated name is a fallback for a panel with none, never an
    # override -- a caller who titled the panel has said what it is called.
    grid = sns.pairplot(_frame(), vars=["alpha", "beta"])
    grid.axes[0][1].set_title("author said so")
    grid.diag_axes[0].set_title("and here too")

    titles = _titles(grid.figure)

    assert sorted(titles) == sorted(
        [
            ("hist", "and here too"),
            ("point", "author said so"),
            ("point", "beta vs alpha"),
            ("hist", "beta"),
        ]
    )


def test_a_corner_pairplot_names_the_half_it_draws():
    # `corner=True` leaves the upper triangle's cells as None, which the
    # naming pass has to walk past rather than trip over.
    titles = _titles(sns.pairplot(_frame(), corner=True).figure)

    assert sorted(titles) == sorted(
        [
            ("hist", "alpha"),
            ("hist", "beta"),
            ("hist", "gamma"),
            ("point", "beta vs alpha"),
            ("point", "gamma vs alpha"),
            ("point", "gamma vs beta"),
        ]
    )


def test_a_grid_with_different_row_and_column_variables_is_named():
    # `x_vars` and `y_vars` need not match, and then there is no diagonal at
    # all -- so the row/column lookup has to be by its own index rather than
    # by a shared variable list.
    grid = PairGrid(_frame(), x_vars=["alpha"], y_vars=["beta", "gamma"])
    grid.map(sns.scatterplot)

    assert sorted(_titles(grid.figure)) == sorted(
        [
            ("point", "beta vs alpha"),
            ("point", "gamma vs alpha"),
        ]
    )


def test_a_diagonal_cell_mapped_as_a_scatter_says_so():
    # `PairGrid.map` draws every cell including the diagonal, and there the
    # panel really is one variable against itself. "alpha vs alpha" is what
    # it draws, so it is what it is called.
    grid = PairGrid(_frame(), vars=["alpha", "beta"])
    grid.map(sns.scatterplot)

    assert ("point", "alpha vs alpha") in _titles(grid.figure)


def test_a_jointplot_of_unnamed_vectors_keeps_its_position():
    # Nothing named the variables, so there is no name to announce. Falling
    # back to the bare position is what a panel that knows no name should do,
    # rather than inventing one from the numbers.
    rng = np.random.default_rng(1)
    grid = sns.jointplot(x=rng.normal(size=30), y=rng.normal(size=30))

    assert {title for _, title in _titles(grid.figure)} == {""}


def test_an_ordinary_chart_is_untouched():
    # Every chart that is not a grid panel, which is nearly all of them.
    fig, ax = plt.subplots()
    ax.scatter([1, 2, 3], [4, 5, 6])

    assert _titles(fig) == [("point", "")]


def test_an_ordinary_chart_keeps_the_title_it_was_given():
    fig, ax = plt.subplots()
    ax.scatter([1, 2, 3], [4, 5, 6])
    ax.set_title("a chart of its own")

    assert _titles(fig) == [("point", "a chart of its own")]


def test_a_facet_grids_own_titles_are_untouched():
    # seaborn *does* title a `FacetGrid`'s panels -- "g = x", "g = y" -- and
    # a FacetGrid is neither of the two grids named here. Asserted so that
    # naming pair and joint panels cannot start overwriting the one grid that
    # already says what its panels are.
    frame = _frame()
    frame["g"] = ["x"] * 15 + ["y"] * 15
    grid = sns.relplot(data=frame, x="alpha", y="beta", col="g")

    assert sorted(_titles(grid.figure)) == [("point", "g = x"), ("point", "g = y")]
