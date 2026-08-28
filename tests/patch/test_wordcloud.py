"""A ``wordcloud.WordCloud`` shown with ``imshow`` reads as a word cloud.

Before this, a figure holding only a cloud registered no layer at all and
``FigureManager.get_maidr`` raised ``UnsupportedPlotError``. The cloud
reaches MAIDR through ``Axes.imshow``, the same entry point a heatmap does,
but it is not one -- it rasterises to an ``(M, N, 3)`` colour array, and
``maidr.patch.heatmap`` declines exactly that shape (#564).

So the cloud was unread rather than misread, and the reading is additive.
The tests that matter are therefore less about the happy path than about
what the new wrapper must NOT disturb: a real heatmap, a photograph, and a
chart drawn beside a cloud.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pytest

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.wordcloudplot import TERM_LABEL, WEIGHT_LABEL

wordcloud = pytest.importorskip("wordcloud")

#: Counts whose ratios are distinctive enough to recognise after normalising.
COUNTS = {"machine": 412, "learning": 300, "data": 250, "model": 120}


def cloud(**kwargs):
    """A small deterministic cloud over :data:`COUNTS`."""
    settings = {"width": 300, "height": 150, "max_words": 4, "random_state": 1}
    settings.update(kwargs)
    return wordcloud.WordCloud(**settings).generate_from_frequencies(
        kwargs.pop("frequencies", COUNTS)
    )


def layers(fig):
    """The layer schemas of a figure, in registration order."""
    return [plot.schema for plot in FigureManager.get_maidr(fig).plots]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def test_a_cloud_is_read_rather_than_refused():
    # The reproduction: before this, `get_maidr` raised UnsupportedPlotError
    # because nothing on the figure had registered.
    fig, ax = plt.subplots()
    ax.imshow(cloud())

    schema = layers(fig)[0]

    assert schema[MaidrKey.TYPE] == PlotType.WORD_CLOUD


def test_each_term_is_paired_with_its_weight():
    fig, ax = plt.subplots()
    ax.imshow(cloud())

    data = layers(fig)[0][MaidrKey.DATA]

    assert [point[MaidrKey.X] for point in data] == list(COUNTS)
    # Normalised by the largest count, so the heaviest term is exactly 1.0.
    assert data[0][MaidrKey.Y] == pytest.approx(1.0)
    assert data[1][MaidrKey.Y] == pytest.approx(300 / 412)


def test_the_weight_axis_says_the_weights_are_relative():
    # `WordCloud` divides by the largest frequency and keeps only the ratio;
    # the raw counts are on no attribute of the object. Naming this axis
    # "Occurrences" would hand a reader "machine, 1.0" for a term that
    # occurred 412 times.
    fig, ax = plt.subplots()
    ax.imshow(cloud())

    axes = layers(fig)[0][MaidrKey.AXES]

    assert axes[MaidrKey.X][MaidrKey.LABEL] == TERM_LABEL
    assert axes[MaidrKey.Y][MaidrKey.LABEL] == WEIGHT_LABEL
    assert "requency" in WEIGHT_LABEL and "ccurrence" not in WEIGHT_LABEL


def test_an_authored_axis_label_wins():
    fig, ax = plt.subplots()
    ax.set_xlabel("Keyword")
    ax.set_ylabel("Share of mentions")
    ax.imshow(cloud())

    axes = layers(fig)[0][MaidrKey.AXES]

    assert axes[MaidrKey.X][MaidrKey.LABEL] == "Keyword"
    assert axes[MaidrKey.Y][MaidrKey.LABEL] == "Share of mentions"


def test_a_repeated_term_is_announced_once():
    # `repeat=True` re-places terms to fill space, and `layout_` lists one
    # per placement -- measured, a two-term cloud came back as
    # [(alpha, 1.0), (beta, 0.667), (alpha, 0.667), (beta, 0.444)].
    # Reading that announces alpha twice, at two different weights, for a
    # repetition that is the packer rather than the data. `words_` cannot.
    fig, ax = plt.subplots()
    ax.imshow(
        wordcloud.WordCloud(
            max_words=3, repeat=True, random_state=1, width=200, height=200
        ).generate_from_frequencies({"alpha": 3, "beta": 2})
    )

    terms = [point[MaidrKey.X] for point in layers(fig)[0][MaidrKey.DATA]]

    assert terms == ["alpha", "beta"]


def test_a_cloud_carries_no_selectors():
    # `imshow` rasterises the whole cloud into one element, so there is no
    # per-term element to point at. Left on, the base class emits its generic
    # `g[maidr='true'] > path`, which the core would resolve and pair
    # positionally with the terms -- lighting up whatever else drew that many
    # paths while this layer is read.
    fig, ax = plt.subplots()
    ax.imshow(cloud())

    assert MaidrKey.SELECTOR not in layers(fig)[0]


def test_a_chart_drawn_beside_a_cloud_keeps_its_reading():
    fig, (bars, cloudy) = plt.subplots(1, 2)
    bars.bar(["p", "q", "r"], [3, 1, 2])
    cloudy.imshow(cloud())

    types = [schema[MaidrKey.TYPE] for schema in layers(fig)]

    assert types == [PlotType.BAR, PlotType.WORD_CLOUD]


def test_a_real_heatmap_is_still_a_heatmap():
    # The wrapper sits on `Axes.imshow` alongside the heatmap's own. A grid
    # of numbers has no `words_`, so it falls straight through.
    fig, ax = plt.subplots()
    ax.imshow(np.array([[1.0, 2.0], [3.0, 4.0]]))

    assert layers(fig)[0][MaidrKey.TYPE] == PlotType.HEAT


def test_a_photograph_is_still_declined():
    # An `(M, N, 3)` array is a picture with no value per cell (#564), and
    # recognising clouds must not have made it readable.
    from maidr.exception import UnsupportedPlotError

    fig, ax = plt.subplots()
    ax.imshow(np.random.default_rng(0).random((4, 4, 3)))

    with pytest.raises(UnsupportedPlotError):
        FigureManager.get_maidr(fig)


def test_an_array_from_the_cloud_is_not_recognised():
    # `wc.to_array()` hands `imshow` a plain RGB array and the terms are not
    # in it. There is nothing to read, and claiming otherwise would announce
    # a chart whose data was never passed.
    from maidr.exception import UnsupportedPlotError

    fig, ax = plt.subplots()
    ax.imshow(cloud().to_array())

    with pytest.raises(UnsupportedPlotError):
        FigureManager.get_maidr(fig)
