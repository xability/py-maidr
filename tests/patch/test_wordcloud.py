"""A ``wordcloud.WordCloud`` shown with ``imshow`` reads as a word cloud.

Before this, a figure holding only a cloud registered no layer at all and
``FigureManager.get_maidr`` raised ``UnsupportedPlotError``. The cloud
reaches MAIDR through ``Axes.imshow``, the same entry point a heatmap does,
but it is not one -- it rasterises to an ``(M, N, 3)`` color array, and
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

#: Counts whose ratios are distinctive enough to recognize after normalizing.
#:
#: Deliberately **not** written heaviest-first. ``words_`` re-sorts by weight,
#: and a fixture that arrived already sorted could not tell that apart from a
#: dict that merely kept the insertion order it was handed -- measured, this
#: order goes in and :data:`BY_WEIGHT` comes out.
COUNTS = {"data": 250, "machine": 412, "model": 120, "learning": 300}

#: The same four terms in the order ``words_`` yields them: heaviest first.
BY_WEIGHT = ["machine", "learning", "data", "model"]


def cloud(**kwargs):
    """A small deterministic cloud over :data:`COUNTS`."""
    frequencies = kwargs.pop("frequencies", COUNTS)
    settings = {"width": 300, "height": 150, "max_words": 4, "random_state": 1}
    settings.update(kwargs)
    return wordcloud.WordCloud(**settings).generate_from_frequencies(frequencies)


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

    assert [point[MaidrKey.X] for point in data] == BY_WEIGHT
    # And the fixture is not already in that order, so the assertion above is
    # about `words_` re-sorting rather than about a dict keeping its keys.
    assert list(COUNTS) != BY_WEIGHT
    # Normalized by the largest count, so the heaviest term is exactly 1.0.
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


def selectors(fig):
    """The word cloud layer's selectors, or None when it carries none."""
    return layers(fig)[0].get(MaidrKey.SELECTOR)


def box_of(ax, selector):
    """The rectangle a selector names, by the gid inside its quotes."""
    gid = selector.split("'")[1]
    (box,) = [patch for patch in ax.patches if patch.get_gid() == gid]
    return box


def ink_in(image, box):
    """How many of the cloud's non-white pixels fall inside a box."""
    pixels = np.asarray(image.get_array())[..., :3]
    ink = (pixels != 255).any(axis=-1)
    rows, cols = np.indices(ink.shape)
    left, right, bottom, top = image.get_extent()
    first, last = (top, bottom) if image.origin == "upper" else (bottom, top)
    x = left + (cols + 0.5) * (right - left) / ink.shape[1]
    y = first + (rows + 0.5) * (last - first) / ink.shape[0]
    inside = (
        (x >= box.get_x())
        & (x <= box.get_x() + box.get_width())
        & (y >= box.get_y())
        & (y <= box.get_y() + box.get_height())
    )
    return int(ink[inside].sum()), ink, inside


def test_each_term_names_its_own_box():
    # One selector per term, in the order the terms are emitted -- the core
    # pairs the two by position. A shared or generic selector would resolve
    # to some other count of elements, and the core would drop the highlight.
    fig, ax = plt.subplots()
    ax.imshow(cloud())

    named = selectors(fig)

    assert len(named) == len(BY_WEIGHT)
    assert len({box_of(ax, one).get_gid() for one in named}) == len(BY_WEIGHT)


@pytest.mark.parametrize(
    "settings, shown",
    [
        ({}, {}),
        ({"scale": 2}, {}),
        ({"prefer_horizontal": 0.0}, {"origin": "lower"}),
        ({}, {"extent": (0, 10, 0, 5)}),
    ],
    ids=["default", "scaled", "rotated-origin-lower", "extent"],
)
def test_each_box_is_over_the_word_it_names(settings, shown):
    # The boxes are measured with PIL's own font, size, rotation and
    # position, then carried through the image's extent and origin into data
    # coordinates. Between them they must hold the drawing: every term's box
    # has ink in it, and only antialiasing fringe falls outside all of them.
    fig, ax = plt.subplots()
    image = ax.imshow(
        cloud(background_color="white", width=300, height=150, **settings),
        **shown,
    )

    covered = None
    for one in selectors(fig):
        count, ink, inside = ink_in(image, box_of(ax, one))
        assert count > 0
        covered = inside if covered is None else covered | inside

    assert (ink & ~covered).sum() / ink.sum() < 0.01


def test_each_box_holds_its_own_term():
    # The pairing, not only the coverage: every term is drawn in a color of
    # its own, and all of that color lies in the box named for the term at
    # that position. Boxes handed out in any other order would fail here.
    palette = {
        "machine": "rgb(255, 0, 0)",
        "learning": "rgb(0, 160, 0)",
        "data": "rgb(0, 0, 255)",
        "model": "rgb(160, 0, 160)",
    }
    rgb = {term: [int(c) for c in v[4:-1].split(",")] for term, v in palette.items()}
    fig, ax = plt.subplots()
    image = ax.imshow(
        cloud(
            background_color="white",
            color_func=lambda word, **_: palette[word],
            prefer_horizontal=0.5,
        )
    )
    pixels = np.asarray(image.get_array())[..., :3]

    for term, one in zip(BY_WEIGHT, selectors(fig)):
        _, _, inside = ink_in(image, box_of(ax, one))
        own = (pixels == rgb[term]).all(axis=-1)
        assert own.sum() > 0
        assert own[inside].sum() == own.sum(), term


def test_a_repeated_term_names_one_box():
    # `repeat=True` places a term more than once; the term is read once, so
    # it is given one box, or the core would find more elements than terms.
    fig, ax = plt.subplots()
    ax.imshow(
        wordcloud.WordCloud(
            max_words=6, repeat=True, random_state=1, width=200, height=200
        ).generate_from_frequencies({"alpha": 3, "beta": 2})
    )

    assert len(selectors(fig)) == 2


def test_a_term_that_did_not_fit_leaves_the_cloud_without_selectors():
    # A term the packer could not place has nothing to point at, and the core
    # pairs selectors with terms by position: a gap would put every later
    # highlight on the wrong word, so there is no highlight at all instead.
    fig, ax = plt.subplots()
    shown = cloud(width=40, height=20, min_font_size=8)
    assert set(shown.words_) - {entry[0][0] for entry in shown.layout_}
    ax.imshow(shown)

    assert selectors(fig) is None


def test_the_boxes_draw_nothing_outside_the_svg():
    # Undrawn in every backend: a cloud saved as a picture is the cloud alone.
    import io

    def saved(fig):
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png")
        return buffer.getvalue()

    shown = cloud()
    fig, ax = plt.subplots()
    ax.imshow(shown)
    layers(fig)
    bare, plain = plt.subplots()
    plain.imshow(shown.to_array())

    assert saved(fig) == saved(bare)


def test_the_boxes_are_hidden_in_the_svg_until_highlighted():
    # maidr.js highlights a copy of each box and leaves the box itself as it
    # was drawn, so the box is hidden and the copy is turned visible. The
    # style is the copy's: an opaque outline, and a fill faint enough that
    # the word reads through it but above the 0.01 maidr.js would raise to
    # opaque.
    from lxml import etree

    fig, ax = plt.subplots()
    ax.imshow(cloud())
    svg = etree.fromstring(
        str(FigureManager.get_maidr(fig)._get_svg(embed_data=False)).encode()
    )

    for one in selectors(fig):
        (path,) = svg.xpath(
            "//*[local-name()='g'][@id=$gid]/*[local-name()='path']",
            gid=box_of(ax, one).get_gid(),
        )
        assert path.get("visibility") == "hidden"
        assert "fill-opacity: 0.02" in path.get("style")
        assert "stroke-width: 2" in path.get("style")


def test_rendering_again_adds_no_boxes():
    # The boxes are made with the layer, not with each render; a figure that
    # is shown twice must not stack a second set on the axes.
    fig, ax = plt.subplots()
    ax.imshow(cloud())
    first = selectors(fig)
    FigureManager.get_maidr(fig).render()

    assert len(ax.patches) == len(BY_WEIGHT)
    assert selectors(fig) == first


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
    # recognizing clouds must not have made it readable.
    from maidr.exception import UnsupportedPlotError

    fig, ax = plt.subplots()
    ax.imshow(np.random.default_rng(0).random((4, 4, 3)))

    with pytest.raises(UnsupportedPlotError):
        FigureManager.get_maidr(fig)


def test_an_array_from_the_cloud_is_not_recognized():
    # `wc.to_array()` hands `imshow` a plain RGB array and the terms are not
    # in it. There is nothing to read, and claiming otherwise would announce
    # a chart whose data was never passed.
    from maidr.exception import UnsupportedPlotError

    fig, ax = plt.subplots()
    ax.imshow(cloud().to_array())

    with pytest.raises(UnsupportedPlotError):
        FigureManager.get_maidr(fig)


def test_a_layer_built_without_a_cloud_raises_rather_than_emits():
    # Defensive: the patch never builds one this way, since it only registers
    # after `cloud_shown` has handed it an object. Pinned because the
    # alternative to raising is emitting an empty layer, and a word cloud
    # announcing no terms is indistinguishable from one whose terms were read.
    from maidr.core.plot.wordcloudplot import WordCloudPlot
    from maidr.exception import ExtractionError

    _, ax = plt.subplots()

    with pytest.raises(ExtractionError):
        WordCloudPlot(ax).schema


def test_a_facet_grid_label_names_the_terms():
    # One cloud per group carries its label on the shared outer axes rather
    # than on its own, so asking only `self.ax` would fall through to the
    # generic name for a figure that was labeled -- the same fallback
    # `PiePlot` uses.
    fig, axs = plt.subplots(2, 1, sharex=True)
    for ax in axs:
        ax.imshow(cloud())
    axs[-1].set_xlabel("Keyword")

    labeled = layers(fig)[0][MaidrKey.AXES][MaidrKey.X][MaidrKey.LABEL]

    assert labeled == "Keyword"
