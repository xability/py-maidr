"""A box matplotlib could not compute is dropped rather than read as NaN (#697).

``cbook.boxplot_stats`` does not drop a missing value: a group holding one
``NaN`` -- a pandas column with a gap, not only an empty or all-``NaN``
group -- gets every statistic as ``NaN``, and ``Axes.bxp`` draws nothing for
it. The extractor cast each with a bare ``float()`` and emitted::

    {min: nan, q1: nan, q2: nan, q3: nan, max: nan}

``json.dumps`` writes that as bare ``NaN`` tokens, which ``JSON.parse`` in
the core refuses, so one such group stopped the whole figure initialising --
the finite boxes beside it included.

``null`` is not the answer the bar family gave (#429): the grammar types the
five statistics as numbers, and ``Number(null)`` is ``0`` in the core, which
would announce a false floor. Nothing is on screen for the box, so nothing
is announced for it: the row, its artists and its level go together, leaving
data, selectors and levels one per box that is there to be read.

seaborn drops missing values itself before drawing, so ``sns.boxplot`` was
never affected; ``ax.boxplot`` is the path measured here.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.cbook import boxplot_stats  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402

FINITE = [2.0, 3.0, 5.0]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _reject_constant(token: str):
    raise ValueError(token)


def draw(groups: list) -> plt.Figure:
    fig, ax = plt.subplots()
    ax.boxplot(groups)
    return fig


def _layer(fig) -> dict:
    """The first layer's schema with plain string keys."""
    plot = FigureManager.get_maidr(fig).plots[0]
    return {(k.value if hasattr(k, "value") else k): v for k, v in plot.schema.items()}


def parses_as_strict_json(fig) -> None:
    """Assert the payload survives what the core actually runs on it.

    ``json.loads`` accepts the bare tokens ``json.dumps`` emits, so a plain
    round trip passes while ``JSON.parse`` in the browser fails.
    """
    schema = FigureManager.get_maidr(fig)._flatten_maidr()

    json.loads(json.dumps(schema), parse_constant=_reject_constant)


# (groups, the tick of the one box matplotlib drew)
CASES = {
    "a NaN inside a group": ([[1.0, 2.0, np.nan, 4.0], FINITE], "2"),
    "an empty group": ([FINITE, []], "1"),
    "an all-NaN group": ([FINITE, [np.nan, np.nan]], "1"),
}

parametrised = pytest.mark.parametrize(
    ("groups", "drawn"), CASES.values(), ids=CASES.keys()
)


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
class TestABoxWithNoStatistics:
    @parametrised
    def test_only_the_drawn_box_is_read(self, groups, drawn):
        rows = _layer(draw(groups))["data"]

        assert len(rows) == 1
        assert rows[0]["z"] == drawn

    @parametrised
    def test_the_drawn_box_keeps_its_statistics(self, groups, drawn):
        (row,) = _layer(draw(groups))["data"]
        (stats,) = boxplot_stats(FINITE)

        assert row["min"] == stats["whislo"]
        assert row["q1"] == stats["q1"]
        assert row["q2"] == stats["med"]
        assert row["q3"] == stats["q3"]
        assert row["max"] == stats["whishi"]
        assert row["lowerOutliers"] == row["upperOutliers"] == []

    @parametrised
    def test_the_selectors_stay_one_per_row(self, groups, drawn):
        layer = _layer(draw(groups))

        assert len(layer["selectors"]) == len(layer["data"]) == 1

    @parametrised
    def test_the_selector_names_the_drawn_box(self, groups, drawn):
        # Dropping the row without its artists would leave the surviving
        # selector pointing at whichever box came first, drawn or not.
        fig = draw(groups)
        plot = FigureManager.get_maidr(fig).plots[0]
        plot.schema  # noqa: B018  # extraction runs on first access
        boxes = plot._bxp_stats["boxes"]
        drawn_box = boxes[int(drawn) - 1]

        assert plot.elements_map["boxes"] == [drawn_box.get_gid()]
        assert [box.get_gid() for box in boxes if box is not drawn_box] == [None]

    @parametrised
    def test_the_payload_is_loadable(self, groups, drawn):
        parses_as_strict_json(draw(groups))

    def test_an_extra_tick_does_not_shift_the_surviving_boxes(self):
        # The labels are the ticks inside the data limits, and a box that
        # drew nothing contributes nothing to those -- so here the NaN box's
        # own tick `a` drops out while the box-less tick `c` stays, leaving
        # three labels for three boxes that do not line up. Filtering the
        # labels by the kept indices would read the survivors as `c, d`;
        # each is named by the tick nearest it instead.
        fig, ax = plt.subplots()
        ax.set_xticks([1, 2, 3, 4], ["a", "b", "c", "d"])
        ax.boxplot(
            [[np.nan, np.nan], FINITE, FINITE], positions=[1, 2, 4], manage_ticks=False
        )

        rows = _layer(fig)["data"]

        assert [row["z"] for row in rows] == ["b", "d"]


class TestWhatMustNotChange:
    def test_a_chart_with_no_gaps_is_unchanged(self):
        groups = [[1.0, 2.0, 4.0], FINITE]
        rows = _layer(draw(groups))["data"]

        assert [row["z"] for row in rows] == ["1", "2"]
        for row, stats in zip(rows, boxplot_stats(groups)):
            assert row["q2"] == stats["med"]
            assert row["min"] == stats["whislo"]
            assert row["max"] == stats["whishi"]
        parses_as_strict_json(draw(groups))
