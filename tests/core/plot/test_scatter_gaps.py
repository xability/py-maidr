"""A scatter emitted a marker matplotlib never drew (#429).

A point with a non-finite coordinate is not rendered — there is nowhere to put
it — so emitting one leaves the layer with more entries than the selector
resolves to ``<use>`` elements. Every point after it is then highlighted at its
neighbour's marker, and the last has none left.

That is the failure worth prioritising over a crash: a reader is shown a mark
that does not correspond to the value being announced, and nothing in the
output says so.

Dropping is the *whole* answer here, unlike the bar case in
``test_bar_gaps.py``. A bar with no height keeps its category and reports a
missing value; a marker with no coordinates has neither a position to navigate
to nor a value to announce.

It also keeps the payload loadable: ``json.dumps`` writes ``NaN`` as a bare
token, which is legal JavaScript and invalid JSON, and the core parses the
SVG's ``maidr`` attribute with ``JSON.parse`` (#427).
"""

from __future__ import annotations

import json

import numpy as np
import pytest

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _reject_constant(token: str):
    raise ValueError(token)


def points_of(collection) -> list[dict]:
    maidr = FigureManager.get_maidr(collection.axes.get_figure())
    return maidr._plots[0].schema["data"]


def parses_as_strict_json(collection) -> None:
    schema = FigureManager.get_maidr(
        collection.axes.get_figure()
    )._flatten_maidr()

    json.loads(json.dumps(schema), parse_constant=_reject_constant)


def drawn_count(collection) -> int:
    """How many markers matplotlib will actually render."""
    offsets = np.ma.getdata(collection.get_offsets())
    return int(np.sum(np.isfinite(offsets).all(axis=1)))


class TestAPointThatWasNotDrawn:
    def test_it_is_not_emitted(self):
        collection = plt.scatter([1, 2, np.nan, 4], [10, 20, np.nan, 40])

        assert len(points_of(collection)) == drawn_count(collection) == 3

    def test_the_drawn_points_survive_intact(self):
        # Stronger than the count: dropping the wrong entry would keep the
        # count right and every reading wrong.
        collection = plt.scatter([1, 2, np.nan, 4], [10, 20, np.nan, 40])
        pairs = [(point["x"], point["y"]) for point in points_of(collection)]

        assert pairs == [(1.0, 10.0), (2.0, 20.0), (4.0, 40.0)]

    def test_the_payload_is_loadable(self):
        collection = plt.scatter([1, 2, np.nan, 4], [10, 20, np.nan, 40])

        parses_as_strict_json(collection)

    def test_a_half_missing_point_goes_too(self):
        # matplotlib renders nothing for a marker with one usable coordinate
        # either, so "finite x and finite y" is the test rather than "both
        # missing".
        collection = plt.scatter([1, 2, 3], [10, np.nan, 30])

        assert len(points_of(collection)) == drawn_count(collection) == 2

    def test_a_masked_point_takes_the_same_path(self):
        # A mask arrives as NaN through `getdata`, so it reaches the defect by
        # a different route.
        collection = plt.scatter(
            np.ma.masked_invalid([1.0, np.nan, 3.0]), [10, 20, 30]
        )

        parses_as_strict_json(collection)
        assert len(points_of(collection)) == 2


class TestWhatMustNotChange:
    def test_a_clean_scatter_keeps_every_point(self):
        collection = plt.scatter([1, 2, 3], [10, 20, 30])

        assert len(points_of(collection)) == 3

    def test_a_point_at_the_origin_is_a_real_reading(self):
        # Zero is finite. The filter tests finiteness, not truthiness — an
        # `if x and y` would silently delete it.
        collection = plt.scatter([0, 1], [0, 1])

        assert (points_of(collection)[0]["x"], points_of(collection)[0]["y"]) == (
            0.0,
            0.0,
        )
        assert len(points_of(collection)) == 2

    def test_negative_coordinates_are_kept(self):
        collection = plt.scatter([-1, -2], [-10, -20])

        assert len(points_of(collection)) == 2


class TestWhereADrawnPointSits:
    def test_a_group_member_after_a_gap_is_numbered_by_what_was_drawn(self):
        # Two indices run through extraction and they are not the same one: a
        # hue group's membership is written in *offset* order, and the SVG is
        # numbered in *drawn* order, so a dropped row between two members
        # pulls the two apart. `_drawn_positions` is the drawn one, and it is
        # what the selector addresses a marker by -- so a reading that
        # numbered by offset would highlight the neighbour. Pinned because
        # #715 stopped counting the drawn points up one by one and read the
        # count off an array instead.
        from maidr.core.plot.scatterplot import DRAWN_POINTS, HUE_GROUP, ScatterPlot

        _, ax = plt.subplots()
        collection = ax.scatter([1, 2, np.nan, 4, 5], [10, 20, 30, np.nan, 50])
        layer = ScatterPlot(
            ax, **{DRAWN_POINTS: collection, HUE_GROUP: ("g", [{0, 2, 4}])}
        )

        samples = layer._extract_plot_data()

        assert [(s["x"], s["y"]) for s in samples] == [(1.0, 10.0), (5.0, 50.0)]
        assert layer._drawn_positions == [(0, 0), (0, 2)]
