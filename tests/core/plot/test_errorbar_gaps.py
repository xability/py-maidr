"""An error bar emitted an estimate matplotlib never drew (#429).

The last of the three extractors that shipped a bare ``NaN``. It differs from
the bar and the scatter, and the difference is what the tests are about.

An error bar carries *two* things that can go missing, and only one of them is
a gap:

* a missing **bound** leaves a real estimate with no interval around it. That
  is a reading, not an absence -- ``_extract_bounds`` already returns ``None``
  and the point is emitted without ``yMin``/``yMax``. Nothing to fix, and
  pinned here so nothing "fixes" it.
* a missing **estimate** leaves nothing at all: matplotlib renders neither a
  marker nor a bar, so the sample is dropped.

The subtle part is the bounds lookup. It addresses the line segments
matplotlib built for the *whole* series, so its index has to keep counting
over the dropped samples. Renumbering it against the survivors would pair each
remaining estimate with the next one's interval -- a wrong interval on a real
reading, which is worse than either failure this fix is for.
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


def points() -> list[dict]:
    maidr = FigureManager.get_maidr(plt.gcf())
    return maidr._plots[0].schema["data"]


def parses_as_strict_json() -> None:
    schema = FigureManager.get_maidr(plt.gcf())._flatten_maidr()

    json.loads(json.dumps(schema), parse_constant=_reject_constant)


class TestAnEstimateThatWasNotDrawn:
    def test_the_sample_is_dropped(self):
        plt.errorbar([1, 2, 3], [1, np.nan, 3], yerr=[0.1, 0.1, 0.1])

        assert [point["x"] for point in points()] == [1.0, 3.0]

    def test_the_payload_is_loadable(self):
        plt.errorbar([1, 2, 3], [1, np.nan, 3], yerr=[0.1, 0.1, 0.1])

        parses_as_strict_json()

    def test_the_survivors_keep_their_own_bounds(self):
        # The assertion this file exists for. The bounds come from the
        # segments matplotlib built for the whole series, so the lookup index
        # must keep counting over the dropped sample. If it were renumbered
        # against the survivors, the point at x=3 would be handed the
        # *dropped* sample's interval -- 1.9 to 2.1 -- and announce a real
        # reading with somebody else's uncertainty.
        plt.errorbar([1, 2, 3], [1, np.nan, 3], yerr=[0.1, 0.1, 0.1])
        emitted = points()

        assert (emitted[0]["yMin"], emitted[0]["yMax"]) == (
            pytest.approx(0.9),
            pytest.approx(1.1),
        )
        assert (emitted[1]["yMin"], emitted[1]["yMax"]) == (
            pytest.approx(2.9),
            pytest.approx(3.1),
        )


class TestAMissingBoundIsNotAGap:
    """An estimate with no interval is a reading, and must stay one."""

    def test_the_estimate_survives(self):
        plt.errorbar([1, 2, 3], [1, 2, 3], yerr=[0.1, np.nan, 0.1])
        emitted = points()

        assert len(emitted) == 3
        assert emitted[1]["y"] == 2.0

    def test_it_simply_carries_no_interval(self):
        plt.errorbar([1, 2, 3], [1, 2, 3], yerr=[0.1, np.nan, 0.1])
        emitted = points()

        assert "yMin" not in emitted[1]
        assert "yMax" not in emitted[1]
        parses_as_strict_json()

    def test_its_neighbours_keep_theirs(self):
        plt.errorbar([1, 2, 3], [1, 2, 3], yerr=[0.1, np.nan, 0.1])
        emitted = points()

        assert "yMin" in emitted[0]
        assert "yMin" in emitted[2]


class TestWhatMustNotChange:
    def test_a_clean_error_bar_is_untouched(self):
        plt.errorbar([1, 2, 3], [1, 2, 3], yerr=[0.1, 0.1, 0.1])
        emitted = points()

        assert len(emitted) == 3
        assert [point["y"] for point in emitted] == [1.0, 2.0, 3.0]
        assert all("yMin" in point and "yMax" in point for point in emitted)

    def test_an_estimate_of_zero_is_a_real_reading(self):
        # Finiteness, not truthiness.
        plt.errorbar([1, 2], [0, 2], yerr=[0.1, 0.1])

        assert len(points()) == 2
        assert points()[0]["y"] == 0.0
