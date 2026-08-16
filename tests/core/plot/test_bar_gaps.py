"""A bar drawn with no height announced one anyway (#429).

matplotlib draws a rectangle for a ``NaN`` height, so a gap in the data
survives as a bar with no magnitude rather than being dropped. Emitting it as
it stood went wrong twice over:

* ``json.dumps`` writes ``NaN`` as a bare token, which is legal JavaScript and
  invalid JSON. The core parses the SVG's ``maidr`` attribute with
  ``JSON.parse``, so one of them stops the chart initialising at all -- audio,
  text, braille and highlight all absent, with a ``console.error`` as the only
  trace (#427).
* Even reaching the model, ``NaN`` is not a reading a listener wants.

``None`` serialises to ``null``, which the core's ``toBarValue`` has read as a
gap since the bar family gained the concept: it becomes ``NaN`` inside the
model, stays out of the range, sounds as the empty tone rather than a floor
tone, and announces as "missing". No release dependency -- that helper is in
the currently published core.
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


def bar_points(ax) -> list[dict]:
    maidr = FigureManager.get_maidr(ax.get_figure())
    return maidr._plots[0].schema["data"]


def parses_as_strict_json(ax) -> None:
    """Assert the payload survives what the core actually runs on it.

    ``json.loads`` accepts the bare tokens by default, exactly as
    ``json.dumps`` emits them, so a plain round trip passes while the browser
    fails. ``parse_constant`` is what lets this fail.
    """
    schema = FigureManager.get_maidr(ax.get_figure())._flatten_maidr()

    json.loads(json.dumps(schema), parse_constant=_reject_constant)


class TestABarWithNoHeight:
    def test_it_is_emitted_as_null_rather_than_nan(self):
        ax = plt.bar(["a", "b", "c"], [1.0, np.nan, 3.0])[0].axes

        assert bar_points(ax)[1]["y"] is None

    def test_the_payload_is_loadable(self):
        ax = plt.bar(["a", "b", "c"], [1.0, np.nan, 3.0])[0].axes

        parses_as_strict_json(ax)

    def test_it_keeps_its_category(self):
        # The bar is kept rather than dropped, which is the difference between
        # "no reading for c" and "c was never in this chart". A category that
        # vanishes cannot be navigated to and cannot be asked about.
        ax = plt.bar(["a", "b", "c"], [1.0, np.nan, 3.0])[0].axes
        points = bar_points(ax)

        assert len(points) == 3
        assert [point["x"] for point in points] == ["a", "b", "c"]

    def test_the_measured_bars_are_untouched(self):
        ax = plt.bar(["a", "b", "c"], [1.0, np.nan, 3.0])[0].axes
        points = bar_points(ax)

        assert points[0]["y"] == 1.0
        assert points[2]["y"] == 3.0

    def test_a_horizontal_bar_is_covered_too(self):
        # A horizontal bar's magnitude is its *width*, read on the other
        # branch of the same method, so it needs its own case rather than
        # inheriting the vertical one's.
        #
        # And the gap lands on **x**, not y. I first asserted `y` here and it
        # failed with `assert 'b' is None`: a horizontal layer emits the
        # magnitude as x and the category as y, which is the layout the
        # renderer reads. The code was right and the expectation was wrong.
        ax = plt.barh(["a", "b", "c"], [1.0, np.nan, 3.0])[0].axes
        points = bar_points(ax)

        assert points[1]["x"] is None
        assert points[1]["y"] == "b"
        parses_as_strict_json(ax)


class TestWhatMustNotChange:
    def test_a_bar_measured_at_zero_is_still_a_reading(self):
        # The distinction the whole change exists to preserve. A zero-height
        # bar was measured; a gap was not.
        ax = plt.bar(["a", "b"], [0.0, 2.0])[0].axes

        assert bar_points(ax)[0]["y"] == 0.0
        assert bar_points(ax)[0]["y"] is not None

    def test_numpy_integer_heights_still_serialise(self):
        # Pinned because it broke. The `float()` cast in the extractor was
        # doing two jobs, and a first version of this fix kept only the
        # finiteness test -- which left matplotlib's numpy types in the
        # payload and raised `TypeError: Object of type int64 is not JSON
        # serializable` on 28 tests. That is the whole render, not one bar.
        ax = plt.bar(["a", "b"], np.array([1, 2], dtype=np.int64))[0].axes

        parses_as_strict_json(ax)
        assert bar_points(ax)[0]["y"] == 1.0

    def test_a_chart_with_no_gaps_is_unchanged(self):
        ax = plt.bar(["a", "b", "c"], [1.0, 2.0, 3.0])[0].axes

        assert [point["y"] for point in bar_points(ax)] == [1.0, 2.0, 3.0]
