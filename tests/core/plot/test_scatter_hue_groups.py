"""A hue-grouped scatter reads as one layer per group (#544).

``seaborn`` draws a hue-grouped scatter as **one** ``PathCollection`` with a
colour per point, not one collection per group, so the grouping survives in
the drawn artist only as those colours and in the legend that names them.
Read as a single layer -- which is what happened before this -- every point
is announced and nothing says which group it belongs to. A sighted reader
sees three colours and a legend; a blind reader gets one undifferentiated
cloud, and the grouping *is* the chart.

The split is a layer per group rather than a field per point because the
grammar has no series dimension for a scatter: ``MaidrLayer.data`` admits
``LinePoint[][]`` and ``SmoothPoint[][]`` and ``ScatterPoint[]``, flat. It is
also what the project already does elsewhere -- in plotly each hue group
arrives as its own trace, and ``jointplot(hue=)``'s own marginals already
emit one ``smooth`` per level.

Two things are asserted throughout and neither is optional:

- **Every point survives.** A split that loses one is worse than no split.
- **Every selector resolves to its own group's marker.** This is the
  highlight-only blind spot xability/maidr#814 names: the audio, braille and
  text would all read correctly while the wrong dot lit up, and nothing that
  listens to announcements can see it. So the tests below read the rendered
  SVG rather than trusting the selector strings.
"""

from __future__ import annotations

import re

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.collections import PathCollection  # noqa: E402
from matplotlib.colors import to_hex  # noqa: E402

import maidr  # noqa: E402
from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402

#: Three groups of four, so a layer holding a third of the points is
#: distinguishable from one holding all of them and from one holding none.
_RNG = np.random.default_rng(544)
FRAME = pd.DataFrame(
    {
        "x": _RNG.normal(0.0, 1.0, 12),
        "y": _RNG.normal(3.0, 2.0, 12),
        "g": ["a", "b", "c"] * 4,
        #: A second grouping, on a different cut of the rows, for the
        #: `style=` cases -- seaborn merges the legend when `hue` and
        #: `style` name the same column.
        "s": ["p", "q"] * 6,
    }
)


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _layers(fig) -> list[dict]:
    """
    The layers a figure registered, in registration order.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure to read.

    Returns
    -------
    list of dict
        Every layer of every subplot, or an empty list when none registered.
    """
    try:
        grid = FigureManager.get_maidr(fig)._flatten_maidr()["subplots"]
    except KeyError:
        return []
    return [layer for row in grid for cell in row for layer in cell["layers"]]


def _points(fig) -> list[dict]:
    """
    The scatter layers a figure registered.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure to read.

    Returns
    -------
    list of dict
        The layers typed ``point``, in registration order.
    """
    return [layer for layer in _layers(fig) if layer[MaidrKey.TYPE] == PlotType.SCATTER]


def _marker_fills(html: str, gid: str) -> list[str]:
    """
    The fill of each drawn marker, in document order.

    Read out of the rendered SVG rather than off the artist, because the
    question these tests ask is what a selector would *land on*.

    Parameters
    ----------
    html : str
        The rendered chart.
    gid : str
        The id matplotlib wrote the collection's group under.

    Returns
    -------
    list of str
        One hex colour per ``<g>`` holding a marker, in document order.
    """
    svg = html[html.index("<svg") : html.index("</svg>") + 6]
    opening = svg.rfind("<g", 0, svg.index(f'id="{gid}"'))

    depth, cursor = 0, opening
    while True:
        found = re.compile(r"<g\b|</g>").search(svg, cursor)
        if found.group() == "<g":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                closing = found.end()
                break
        cursor = found.end()

    block = svg[opening:closing]
    markers = re.findall(r"<g\b[^>]*>\s*(<use[^>]*/>)\s*</g>", block)
    return [re.search(r"fill: (#[0-9a-f]{6})", marker).group(1) for marker in markers]


def _legend_fills(ax) -> dict[str, str]:
    """
    The colour the legend gives each group.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        The axes drawn on.

    Returns
    -------
    dict of str to str
        Group name to hex colour.
    """
    legend = ax.get_legend()
    return {
        text.get_text(): to_hex(handle.get_markerfacecolor())
        for handle, text in zip(legend.legend_handles, legend.get_texts())
    }


def _collection(ax) -> PathCollection:
    """
    The one collection a scatter drew.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        The axes drawn on.

    Returns
    -------
    PathCollection
        The points.
    """
    drawn = [artist for artist in ax.collections if isinstance(artist, PathCollection)]
    assert len(drawn) == 1, "seaborn draws a hue-grouped scatter as one collection"
    return drawn[0]


def test_a_hue_grouped_scatter_is_one_layer_per_group():
    """Three groups, three layers, each named after the group it reads."""
    ax = sns.scatterplot(data=FRAME, x="x", y="y", hue="g")

    layers = _points(ax.figure)

    assert [layer[MaidrKey.NAME] for layer in layers] == ["a", "b", "c"]


def test_each_layer_holds_its_own_group_and_the_layers_hold_every_point():
    """
    A layer reads its group's observations, and between them nothing is lost.

    Both halves matter and they fail differently: a layer reading the wrong
    rows describes a chart the reader does not have, while layers that
    between them drop a row lose an observation with nothing to say so.
    """
    ax = sns.scatterplot(data=FRAME, x="x", y="y", hue="g")

    layers = _points(ax.figure)
    announced = {
        layer[MaidrKey.NAME]: sorted(
            round(float(point[MaidrKey.X]), 9) for point in layer[MaidrKey.DATA]
        )
        for layer in layers
    }
    expected = {
        name: sorted(round(float(value), 9) for value in rows["x"])
        for name, rows in FRAME.groupby("g")
    }

    assert announced == expected
    assert sum(len(layer[MaidrKey.DATA]) for layer in layers) == len(FRAME)


def test_the_grouping_variable_is_named_on_the_z_axis():
    """
    ``z`` says what the split is *by*; ``name`` says which side of it.

    The variable's name appears nowhere else in the payload -- seaborn puts
    it on the legend title and nothing else -- so without this a reader is
    told they are in group "a" of something unnamed.
    """
    ax = sns.scatterplot(data=FRAME, x="x", y="y", hue="g")

    for layer in _points(ax.figure):
        assert layer[MaidrKey.AXES][MaidrKey.Z][MaidrKey.LABEL] == "g"


def test_every_selector_lands_on_a_marker_of_its_own_group():
    """
    The highlight follows the split, asserted against the rendered SVG.

    This is the half no announcement can check. A layer whose selectors
    resolved to another group's markers -- or to nothing -- would read
    correctly through audio, braille and text while outlining the wrong dots,
    which is the failure xability/maidr#814 describes. So the assertion is
    made against the document: resolve each selector's position and check the
    marker there is painted this group's colour.
    """
    ax = sns.scatterplot(data=FRAME, x="x", y="y", hue="g")
    html = str(maidr.render(ax.figure).get_html_string())

    fills = _marker_fills(html, _collection(ax).get_gid())
    wanted = _legend_fills(ax)

    assert len(fills) == len(FRAME), "one marker per point is drawn"

    for layer in _points(ax.figure):
        name = layer[MaidrKey.NAME]
        selectors = layer[MaidrKey.SELECTOR]

        assert len(selectors) == len(layer[MaidrKey.DATA]), (
            "the frontend withdraws highlighting unless the resolved element "
            "count matches the point count, so a short list is worse than none"
        )

        for selector in selectors:
            position = int(re.search(r"nth-of-type\((\d+)\)", selector).group(1))
            assert fills[position - 1] == wanted[name]


def test_an_ungrouped_scatter_is_untouched():
    """
    One colour, one layer, and the selector it has always had.

    matplotlib writes a uniformly styled collection as one ``<g>`` holding
    every ``<use>``, so the group-wide selector is both correct and in
    document order there. Nothing about the split may reach this chart.
    """
    ax = sns.scatterplot(data=FRAME, x="x", y="y")

    layers = _points(ax.figure)

    assert len(layers) == 1
    assert MaidrKey.NAME not in layers[0]
    assert len(layers[0][MaidrKey.DATA]) == len(FRAME)

    # One selector for the whole collection, not a list of positions. The
    # `maidr` attribute is rewritten to this render's own id on the way out,
    # so the shape is what is asserted rather than the literal string.
    selectors = layers[0][MaidrKey.SELECTOR]
    assert len(selectors) == 1
    assert selectors[0].endswith("> g > use")
    assert "nth-of-type" not in selectors[0]


def test_a_scatter_with_no_legend_is_read_as_one_layer():
    """
    Colours with no names are not a grouping worth splitting on.

    ``legend=False`` leaves the per-point colours in place and takes away the
    only thing that says what they mean. Layers called "1" and "2" are not an
    improvement on one cloud, so the chart is read as it always was.
    """
    ax = sns.scatterplot(data=FRAME, x="x", y="y", hue="g", legend=False)

    layers = _points(ax.figure)

    assert len(layers) == 1
    assert len(layers[0][MaidrKey.DATA]) == len(FRAME)


def test_a_continuous_hue_is_not_split():
    """
    A colour *scale* is not a grouping.

    Measured: ``hue=`` on a numeric column gives one distinct colour per
    point against a legend of round-numbered levels that mostly match no
    point at all. Split on colour it would give one layer per observation,
    which is nonsense -- so a point that no swatch claims declines the whole
    reading.
    """
    frame = FRAME.assign(v=_RNG.normal(0.0, 1.0, len(FRAME)))
    ax = sns.scatterplot(data=frame, x="x", y="y", hue="v")

    layers = _points(ax.figure)

    assert len(layers) == 1
    assert len(layers[0][MaidrKey.DATA]) == len(FRAME)


def test_a_style_only_scatter_is_not_split():
    """
    ``style=`` groups by marker shape, which is not a colour and not read.

    Every point is drawn in one colour, and the three legend swatches are
    that same colour -- so a colour there means three things at once and
    cannot say which group a point is in. Declined rather than guessed at.
    """
    ax = sns.scatterplot(data=FRAME, x="x", y="y", style="g")

    layers = _points(ax.figure)

    assert len(layers) == 1
    assert len(layers[0][MaidrKey.DATA]) == len(FRAME)


def test_a_hue_and_style_scatter_still_splits_on_the_hue():
    """
    The extra legend entries do not confuse the split.

    Measured, that legend carries seven entries: two section headers drawn
    ``'w'`` with no marker, three hue swatches in the palette colours, and
    two style markers drawn in the neutral ``'.2'``. Only the hue swatches
    are colours the points were actually painted in.

    The two headers are why that condition is load-bearing rather than
    tidiness: both are white, so a reading that let them in would see one
    colour claimed by two names, refuse the ambiguity, and read a perfectly
    ordinary grouped scatter as one cloud.

    Styled by a *different* column than the hue on purpose. Given the same
    column seaborn merges the two into a single legend section with no
    headers at all, and the case this test exists for never arises.
    """
    ax = sns.scatterplot(data=FRAME, x="x", y="y", hue="g", style="s")

    layers = _points(ax.figure)

    assert [layer[MaidrKey.NAME] for layer in layers] == ["a", "b", "c"]


def test_a_joint_panel_and_its_marginals_agree_about_the_groups():
    """
    The inconsistency that made this worth fixing, pinned.

    ``jointplot(hue=)``'s marginals already emitted one ``smooth`` per hue
    level while the joint panel emitted one ``point`` layer for all of them,
    so within a single chart the summaries were navigable by group and the
    observations they summarise were not.
    """
    grid = sns.jointplot(data=FRAME, x="x", y="y", hue="g")

    layers = _layers(grid.figure)
    scatters = [
        layer for layer in layers if layer[MaidrKey.TYPE] == PlotType.SCATTER
    ]
    smooths = [layer for layer in layers if layer[MaidrKey.TYPE] == PlotType.SMOOTH]

    assert [layer[MaidrKey.NAME] for layer in scatters] == ["a", "b", "c"]
    # Two marginals, three levels each.
    assert len(smooths) == 6


def test_a_pair_grid_splits_every_off_diagonal_panel():
    """
    The split reaches a grid, where the scatter is drawn once per cell.

    ``pairplot`` draws each off-diagonal panel with its own ``scatterplot``
    call, so this is the same reading repeated -- which is exactly why it is
    asserted: a fix that reached only the axes-level call would leave the
    chart most likely to be read this way behind.
    """
    grid = sns.pairplot(FRAME[["x", "y", "g"]], hue="g")

    scatters = [
        layer
        for layer in _layers(grid.figure)
        if layer[MaidrKey.TYPE] == PlotType.SCATTER
    ]

    # Two off-diagonal panels, three groups each.
    assert len(scatters) == 6
    assert {layer[MaidrKey.NAME] for layer in scatters} == {"a", "b", "c"}


def test_a_hue_order_that_names_only_some_levels_is_not_split():
    """
    A point no swatch claims declines the split, rather than vanishing.

    ``hue_order=["a", "b"]`` on a three-level column is a real chart and an
    awkward one: measured, seaborn draws all twelve points in three colours
    and puts two of them in the legend. The four points of the unnamed level
    are on the chart with nothing saying what they are.

    Split on the two named colours, those four would belong to no layer --
    announced nowhere, with nothing to say they had been dropped, which is
    the worst of the three possible outcomes. Declining reads all twelve as
    one cloud, which is what the chart did before any of this and loses
    nothing.
    """
    ax = sns.scatterplot(data=FRAME, x="x", y="y", hue="g", hue_order=["a", "b"])

    layers = _points(ax.figure)

    assert len(layers) == 1
    assert len(layers[0][MaidrKey.DATA]) == len(FRAME)


def test_seaborn_drops_a_non_finite_row_before_drawing():
    """
    The fact that keeps two indices in step, pinned rather than assumed.

    A group's membership is written in *collection* offsets while the SVG is
    numbered by *drawn* markers, and the reader tracks both because a marker
    matplotlib declines to draw would put every later highlight on its
    neighbour. Today the two never diverge on a chart that splits: only
    seaborn produces the per-point colours and the legend a split needs, and
    seaborn drops the non-finite row upstream of the artist.

    So this is the assumption made checkable. If a seaborn release stops
    dropping, this fails -- and that is the release where the reader's
    two-index arithmetic starts earning its keep rather than merely being
    correct.
    """
    frame = FRAME.copy()
    frame.loc[frame.index[4], "x"] = np.nan

    ax = sns.scatterplot(data=frame, x="x", y="y", hue="g")

    offsets = _collection(ax).get_offsets()
    assert len(offsets) == len(frame) - 1
    assert np.isfinite(np.asarray(offsets)).all()
