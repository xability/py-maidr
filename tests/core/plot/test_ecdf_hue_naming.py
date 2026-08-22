"""A hue-grouped ECDF names each curve from its own colour (#582).

seaborn draws an ECDF's hue levels in the reverse of its legend order, so
pairing the two by position gives every curve the other group's name. The
groups here are chosen so that cannot be argued with: `low` is 1-5 and
`high` is 100-500, with no overlap, so which curve holds which data is a
fact about the numbers rather than about the order they were drawn in.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import pytest
import seaborn as sns

from maidr.core.enum import MaidrKey
from maidr.core.figure_manager import FigureManager

LOW = [1, 2, 3, 4, 5]
HIGH = [100, 200, 300, 400, 500]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"x": LOW + HIGH, "grp": ["low"] * 5 + ["high"] * 5})


def _named_series(fig) -> list:
    """Each series as (announced name, whether it holds the `low` data)."""
    out = []
    for plot in FigureManager.get_maidr(fig).plots:
        for series in plot.schema[MaidrKey.DATA]:
            xs = [
                point[MaidrKey.X]
                for point in series
                if isinstance(point.get(MaidrKey.X), (int, float))
            ]
            out.append((series[0].get(MaidrKey.Z), max(xs) <= 50))
    return out


def test_each_ecdf_curve_is_named_for_the_data_it_holds() -> None:
    fig, ax = plt.subplots()
    sns.ecdfplot(_frame(), x="x", hue="grp", ax=ax)

    assert sorted(_named_series(fig)) == sorted([("low", True), ("high", False)])


def test_the_legend_really_does_run_the_other_way() -> None:
    """What makes the test above a test. If seaborn ever draws an ECDF in
    legend order this stops holding, and pairing by position would no longer
    be wrong -- so the reason for the fix would be worth re-reading."""
    fig, ax = plt.subplots()
    sns.ecdfplot(_frame(), x="x", hue="grp", ax=ax)

    assert [text.get_text() for text in ax.legend_.get_texts()] == ["low", "high"]
    first = ax.lines[0].get_xydata()[:, 0]
    drawn_first_is_low = max(value for value in first if value < float("inf")) <= 50
    assert not drawn_first_is_low


def test_a_three_group_ecdf_names_every_curve_for_its_own_data() -> None:
    frame = pd.DataFrame(
        {
            "x": LOW + HIGH + [1000, 2000, 3000, 4000, 5000],
            "grp": ["low"] * 5 + ["high"] * 5 + ["huge"] * 5,
        }
    )
    fig, ax = plt.subplots()
    sns.ecdfplot(frame, x="x", hue="grp", ax=ax)

    by_name = {}
    for plot in FigureManager.get_maidr(fig).plots:
        for series in plot.schema[MaidrKey.DATA]:
            xs = [
                point[MaidrKey.X]
                for point in series
                if isinstance(point.get(MaidrKey.X), (int, float))
            ]
            by_name[series[0].get(MaidrKey.Z)] = max(xs)

    assert by_name["low"] == 5
    assert by_name["high"] == 500
    assert by_name["huge"] == 5000


def test_an_ungrouped_ecdf_is_left_unnamed() -> None:
    """One curve needs nothing to be told apart from."""
    fig, ax = plt.subplots()
    sns.ecdfplot(pd.DataFrame({"x": LOW}), x="x", ax=ax)

    assert [name for name, _ in _named_series(fig)] == [None]
