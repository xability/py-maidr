"""`Axes.stairs` is matplotlib's pre-binned histogram, and it was read as nothing.

`ax.step` already read as `step` and `ax.hist` as `hist`, so of the three ways
matplotlib draws a staircase this was the one that left the chart silent -- and
it is the one its own documentation reaches for once the binning has already
happened::

    counts, edges = np.histogram(values, bins=8)
    ax.stairs(counts, edges)

Nothing has to be inferred. `StepPatch.get_data()` returns the counts and the
bin edges unrounded, which is exactly the pair `hist` recovers from its bars --
so the two spellings of one chart are held to emitting the *same* payload here
rather than two that merely resemble each other.

What a staircase cannot do is highlight. It renders as one `<path>` covering
every bin where `ax.hist` renders one per bar, so there is no per-bin element
for a selector to name. That limit is asserted below rather than described,
so it turns red the day a renderer starts emitting per-bin elements.
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.exception import UnsupportedPlotError  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _layers(fig):
    """The layers registered for a figure, or an empty list when there are none."""
    try:
        return FigureManager.get_maidr(fig).plots
    except UnsupportedPlotError:
        return []


def _data(fig, index: int = 0):
    """One layer's point payload."""
    return _layers(fig)[index].schema[MaidrKey.DATA]


def _parse_as_a_browser_would(schema) -> None:
    """
    Serialise a layer and parse it back the way the core does.

    Python's ``json.loads`` accepts the bare ``NaN``, ``Infinity`` and
    ``-Infinity`` tokens ``json.dumps`` writes, so a round trip through it
    proves nothing about the payload the browser has to read: ``JSON.parse``
    rejects all three, and one of them stops the chart initialising at all
    (#427). ``parse_constant`` is the hook that makes the two agree.
    """

    def reject(token: str):
        raise AssertionError(f"{token} is not JSON; JSON.parse would reject it")

    json.loads(json.dumps(schema), parse_constant=reject)


def test_a_staircase_is_read_as_a_histogram():
    fig, ax = plt.subplots()

    ax.stairs([1, 3, 2], [0, 1, 2, 3])

    assert [layer.type for layer in _layers(fig)] == [PlotType.HIST]


def test_counts_and_bin_edges_come_off_the_artist_exactly():
    # `StepPatch` keeps both halves, so nothing here is measured from pixels
    # or reconstructed from bar spacing.
    fig, ax = plt.subplots()

    ax.stairs([1, 3, 2], [0, 1, 2, 3])

    assert _data(fig) == [
        {"y": 1.0, "x": 0.5, "xMin": 0.0, "xMax": 1.0, "yMin": 0, "yMax": 1.0},
        {"y": 3.0, "x": 1.5, "xMin": 1.0, "xMax": 2.0, "yMin": 0, "yMax": 3.0},
        {"y": 2.0, "x": 2.5, "xMin": 2.0, "xMax": 3.0, "yMin": 0, "yMax": 2.0},
    ]


def test_the_two_spellings_of_one_histogram_emit_the_same_payload():
    # Six observations binned into [0, 1, 2, 3] give counts 1, 3, 2 -- the same
    # chart the `stairs` call above draws from the counts directly. Parity is
    # the point of the change, so it is asserted rather than assumed.
    stairs_figure, stairs_ax = plt.subplots()
    stairs_ax.stairs([1, 3, 2], [0, 1, 2, 3])

    hist_figure, hist_ax = plt.subplots()
    hist_ax.hist([0.5, 1.5, 1.5, 1.5, 2.5, 2.5], bins=[0, 1, 2, 3])

    assert _data(stairs_figure) == _data(hist_figure)


def test_a_horizontal_staircase_runs_its_bins_up_the_y_axis():
    fig, ax = plt.subplots()

    ax.stairs([1, 3, 2], [0, 1, 2, 3], orientation="horizontal")

    schema = _layers(fig)[0].schema
    assert schema[MaidrKey.ORIENTATION] == "horz"
    # The bin edges move to y and the count to x, which is what the core's
    # histogram trace reads on a horizontal chart.
    assert _data(fig)[1] == {
        "x": 3.0,
        "y": 1.5,
        "yMin": 1.0,
        "yMax": 2.0,
        "xMin": 0,
        "xMax": 3.0,
    }


def test_a_horizontal_staircase_matches_a_horizontal_hist():
    stairs_figure, stairs_ax = plt.subplots()
    stairs_ax.stairs([1, 3, 2], [0, 1, 2, 3], orientation="horizontal")

    hist_figure, hist_ax = plt.subplots()
    hist_ax.hist(
        [0.5, 1.5, 1.5, 1.5, 2.5, 2.5], bins=[0, 1, 2, 3], orientation="horizontal"
    )

    assert _data(stairs_figure) == _data(hist_figure)


def test_each_call_reads_its_own_staircase():
    # Two `stairs` calls leave two patches on one axes. Looking the artist up
    # on the axes rather than taking the call's own would describe the first
    # staircase twice and lose the second entirely.
    fig, ax = plt.subplots()

    ax.stairs([1, 3, 2], [0, 1, 2, 3])
    ax.stairs([9, 8, 7], [0, 1, 2, 3])

    assert [[point["y"] for point in _data(fig, i)] for i in range(2)] == [
        [1.0, 3.0, 2.0],
        [9.0, 8.0, 7.0],
    ]


def test_the_baseline_is_a_drawing_choice_and_not_a_reading():
    # `baseline` takes None, a scalar or a per-bin array, and `get_data()`
    # returns `values` unchanged in every case -- it decides where the outline
    # is closed, not what the bins hold. Encoded here rather than argued,
    # because a later change could start folding it into the counts and
    # nothing else would notice.
    default_figure, default_ax = plt.subplots()
    default_ax.stairs([1, 3, 2], [0, 1, 2, 3])
    expected = _data(default_figure)

    for baseline in (None, 2, [0, 1, 0]):
        fig, ax = plt.subplots()
        ax.stairs([1, 3, 2], [0, 1, 2, 3], baseline=baseline)

        assert _data(fig) == expected, f"baseline={baseline!r} changed the reading"


def test_a_blank_bin_keeps_its_place_and_reports_no_count():
    # `NaN` is how a staircase leaves a bin blank -- matplotlib draws a gap.
    # The bin has a position the reader can still land on, so it is kept and
    # its count emitted as null rather than dropped, which would silently
    # shorten the chart by a bin.
    fig, ax = plt.subplots()

    ax.stairs([1, np.nan, 2], [0, 1, 2, 3])

    points = _data(fig)
    assert len(points) == 3
    assert points[1]["y"] is None
    assert (points[1]["xMin"], points[1]["xMax"]) == (1.0, 2.0)


def test_a_blank_bin_leaves_the_payload_parseable():
    # `json.dumps` writes a bare `NaN`, which is legal JavaScript and not
    # JSON: `JSON.parse` rejects the whole schema and the chart never
    # initialises at all (#427). Asserted through a real parse rather than by
    # looking for the token.
    fig, ax = plt.subplots()

    ax.stairs([1, np.nan, 2], [0, 1, 2, 3])

    _parse_as_a_browser_would(_layers(fig)[0].schema)


def test_a_bin_with_no_finite_edge_is_dropped():
    # An infinite edge is a real idiom rather than a contrivance: seaborn's
    # `ecdfplot` opens its staircase at -inf so the first step has somewhere
    # to come from, and matplotlib accepts one here (it rejects only NaN).
    # Such a bin has no position to navigate to, and `Infinity` in the payload
    # is not JSON -- `JSON.parse` would reject the whole schema (#427).
    fig, ax = plt.subplots()

    ax.stairs([1, 2, 3], [-np.inf, 1, 2, 3])

    assert [(p["xMin"], p["xMax"]) for p in _data(fig)] == [(1.0, 2.0), (2.0, 3.0)]
    _parse_as_a_browser_would(_layers(fig)[0].schema)


def test_an_empty_staircase_registers_nothing():
    # `ax.stairs([], [0])` is legal and draws nothing. A layer for it would be
    # one the core has to navigate into and cannot read.
    fig, ax = plt.subplots()

    ax.stairs([], [0])

    assert _layers(fig) == []


def test_uneven_bins_keep_the_edges_they_were_given():
    # Nothing is reconstructed from bar spacing here, so author-set thresholds
    # survive exactly rather than being regularised.
    fig, ax = plt.subplots()

    ax.stairs([1, 3, 2], [0, 1, 5, 6])

    assert [(p["xMin"], p["xMax"]) for p in _data(fig)] == [
        (0.0, 1.0),
        (1.0, 5.0),
        (5.0, 6.0),
    ]


def test_a_staircase_announces_its_bins_but_has_nothing_to_highlight():
    # One `<path>` covers every bin, so there is no per-bin element to name.
    # The layer must exist first: a chart that registered nothing would also
    # have no selectors, and would pass this test for the wrong reason.
    fig, ax = plt.subplots()

    ax.stairs([1, 3, 2], [0, 1, 2, 3])

    schema = _layers(fig)[0].schema
    assert len(schema[MaidrKey.DATA]) == 3
    assert MaidrKey.SELECTOR not in schema


def test_the_np_histogram_idiom_reads_end_to_end():
    # The call matplotlib's documentation shows, through the public API.
    rng = np.random.default_rng(0)
    counts, edges = np.histogram(rng.normal(size=200), bins=5)
    fig, ax = plt.subplots()
    ax.stairs(counts, edges)

    html = maidr.render(fig).get_html_string()

    assert "&quot;type&quot;:&quot;hist&quot;" in html.replace(" ", "")
    assert [point["y"] for point in _data(fig)] == [float(c) for c in counts]
