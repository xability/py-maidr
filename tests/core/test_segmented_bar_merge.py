"""A stacked bar in one panel was deleting layers from every other panel.

``BarPlot`` and ``GroupedBarPlot`` both read *every* ``BarContainer`` on their
axes rather than the bars their own call drew, so a stacked chart built from
three ``ax.bar()`` calls registers three layers that each describe the whole
chart. One has to survive; the rest are duplicates. That much was known and
handled.

What was wrong is how the survivor was chosen. ``Maidr.plot_type`` is a
*figure-wide* "highest priority type seen", and ``PLOT_TYPE_PRIORITY`` gives
``STACKED``/``DODGED`` a 2 against everything else's 1 -- so one stacked bar
anywhere set it for the whole figure. ``_flatten_maidr`` then collapsed
**every** subplot position down to ``position_plots[0]``, the first layer
registered there, whatever its type.

Three things followed, and none of them errored:

    a stacked bar in panel 0     panel 1 emitted ['line'] instead of
                                 ['line', 'point']
    a line drawn before the bars the bar chart was the layer dropped
    bottom omitted on call 1     ExtractionError -- no HTML at all

The third is matplotlib's own documented stacked bar::

    ax.bar(labels, men_means, width, label='Men')
    ax.bar(labels, women_means, width, bottom=men_means, label='Women')

which registers ``BAR`` then ``STACKED``, kept the ``BAR``, and that layer's
extractor then found six patches against three tick labels and raised.
Writing ``bottom=np.zeros(n)`` on the first call avoided it, which is why
every test wrote it that way and why this survived (#376).
"""

from __future__ import annotations

import matplotlib
import numpy as np

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.core.plot.mplfinance_barplot import MplfinanceBarPlot  # noqa: E402

CATEGORIES = ["a", "b", "c"]
SERIES_0 = np.array([10.0, 20.0, 30.0])
SERIES_1 = np.array([30.0, 20.0, 10.0])


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _emitted(fig) -> list[list[list[str]]]:
    """The layer types of every subplot cell, as a row-major grid.

    A cell with nothing registered in it is ``{}`` rather than a cell with an
    empty ``layers``, so the key is read defensively -- an empty panel is one
    of the states under test here.
    """
    grid = FigureManager.get_maidr(fig)._flatten_maidr()["subplots"]
    return [
        [[layer["type"].value for layer in cell.get("layers", [])] for cell in row]
        for row in grid
    ]


def test_the_documented_stacked_bar_renders() -> None:
    """matplotlib's own example, which produced no HTML at all.

    ``bottom`` is omitted on the first call, the way the matplotlib gallery
    writes it and the way anyone writes it. That first call registers a
    ``BarPlot``; the second lifts the figure to ``STACKED``, the collapse
    fired, and it kept the ``BarPlot`` -- whose extractor reads the whole
    axes, finds six patches against three tick labels, and raises.

    ``ExtractionError`` is fatal to the figure rather than to its own layer,
    so this is asserted through a real ``render()`` and not only through the
    layer list: the old failure happened while collecting artists, one step
    before the schema was built.
    """
    fig, ax = plt.subplots()
    ax.bar(CATEGORIES, SERIES_0, label="s0")
    ax.bar(CATEGORIES, SERIES_1, bottom=SERIES_0, label="s1")

    assert _emitted(fig) == [[["stacked_bar"]]]
    assert maidr.render(fig) is not None


def test_the_same_chart_with_an_explicit_zero_bottom_is_unchanged() -> None:
    """The control: the spelling that always worked still gives one layer.

    Writing ``bottom=np.zeros(n)`` on the first call registers ``STACKED``
    twice rather than ``BAR`` then ``STACKED``, so the old code kept a
    segmented layer by luck. Nothing here should move.
    """
    fig, ax = plt.subplots()
    ax.bar(CATEGORIES, SERIES_0, bottom=np.zeros(len(CATEGORIES)), label="s0")
    ax.bar(CATEGORIES, SERIES_1, bottom=SERIES_0, label="s1")

    assert _emitted(fig) == [[["stacked_bar"]]]


def test_a_panel_with_no_bars_keeps_its_layers() -> None:
    """The quietest of the three, and the one with the widest blast radius.

    Panel 1 is written identically in both halves of this test. The only
    difference is what panel 0 contains -- and a stacked bar there used to
    delete panel 1's scatter, because the collapse was gated on a
    figure-wide type and then applied to every position.
    """
    fig, axes = plt.subplots(1, 2)
    axes[1].plot(CATEGORIES, SERIES_0)
    axes[1].scatter(CATEGORIES, SERIES_1)

    assert _emitted(fig) == [[[], ["line", "point"]]]
    plt.close(fig)

    fig, axes = plt.subplots(1, 2)
    axes[0].bar(CATEGORIES, SERIES_0, bottom=np.zeros(len(CATEGORIES)))
    axes[0].bar(CATEGORIES, SERIES_1, bottom=SERIES_0)
    axes[1].plot(CATEGORIES, SERIES_0)
    axes[1].scatter(CATEGORIES, SERIES_1)

    assert _emitted(fig) == [[["stacked_bar"], ["line", "point"]]]


@pytest.mark.parametrize("line_first", [True, False])
def test_an_overlay_survives_whichever_order_it_was_drawn_in(line_first) -> None:
    """A line over a stacked bar is a second layer, not a duplicate of it.

    The old collapse kept ``position_plots[0]``, so the survivor was decided
    by registration order rather than by type. Drawing the reference line
    first meant the *bar chart* -- the thing the figure is of -- was the layer
    dropped, and only the annotation was announced. Both orders are
    parametrized because each dropped a different layer.
    """
    fig, ax = plt.subplots()

    def draw_line():
        ax.plot(CATEGORIES, SERIES_0 + SERIES_1, label="total")

    def draw_bars():
        ax.bar(CATEGORIES, SERIES_0, bottom=np.zeros(len(CATEGORIES)), label="s0")
        ax.bar(CATEGORIES, SERIES_1, bottom=SERIES_0, label="s1")

    if line_first:
        draw_line()
        draw_bars()
        expected = ["line", "stacked_bar"]
    else:
        draw_bars()
        draw_line()
        expected = ["stacked_bar", "line"]

    assert _emitted(fig) == [[expected]]


def test_a_twinned_axes_keeps_its_own_stacked_bar() -> None:
    """Two axes in one grid cell are two charts, not one chart twice.

    The duplication this collapse resolves comes from the extractor reading
    every container on ``self.ax``, so the axes is what makes two layers
    descriptions of the same bars. ``ax.twinx()`` gives a *second* axes at the
    *same* ``(row, col)`` -- so keyed by grid cell, a stacked bar on each side
    of a twinned pair collapsed to one and the right-hand chart was announced
    nowhere.

    Both layers are asserted by their data rather than only by count, since
    two layers of the right type could still both be the left-hand chart.
    """
    fig, ax = plt.subplots()
    ax.bar(CATEGORIES, SERIES_0, bottom=np.zeros(len(CATEGORIES)), label="l0")
    ax.bar(CATEGORIES, SERIES_1, bottom=SERIES_0, label="l1")

    right = ax.twinx()
    right.bar(CATEGORIES, SERIES_1 * 2, bottom=np.zeros(len(CATEGORIES)), label="r0")
    right.bar(CATEGORIES, SERIES_0 * 2, bottom=SERIES_1 * 2, label="r1")

    grid = FigureManager.get_maidr(fig)._flatten_maidr()["subplots"]
    layers = grid[0][0]["layers"]

    assert [layer["type"].value for layer in layers] == ["stacked_bar"] * 2
    assert [layer["data"][0][0]["y"] for layer in layers] == [10.0, 60.0]


def test_every_layer_keeps_its_own_selector_id() -> None:
    """The pairing that a naive filter would break silently.

    ``_plots`` and ``selector_ids`` are matched by index in both directions --
    the artists are tagged with ``selector_ids[i]`` and the schema stamps the
    same index into the layer's selector string. Dropping a layer without
    dropping its id shifts every id after it by one, so each surviving layer
    would carry its neighbour's and the highlight would land on the wrong
    mark. Nothing errors; the outline just moves.

    Here the dropped layer is at index 0, so the shift is visible: the
    stacked layer's id must be the *second* one issued, not the first.
    """
    fig, ax = plt.subplots()
    ax.bar(CATEGORIES, SERIES_0, label="s0")
    ax.bar(CATEGORIES, SERIES_1, bottom=SERIES_0, label="s1")

    figure_maidr = FigureManager.get_maidr(fig)
    issued = list(figure_maidr.selector_ids)
    assert len(issued) == 2

    figure_maidr._flatten_maidr()

    assert len(figure_maidr.plots) == 1
    assert figure_maidr.selector_ids == [issued[1]]


def test_a_bar_typed_layer_outside_the_family_is_not_dropped() -> None:
    """The family is a class, not a ``PlotType``, and that has to stay true.

    ``MplfinanceBarPlot`` carries ``PlotType.BAR`` but reads the volume
    patches handed to it rather than sweeping the axes -- so the premise that
    justifies dropping a layer, *its extractor already describes every bar
    here*, is not true of it. A ``plot.type`` check said it was, and a stacked
    bar sharing its axes would have taken the volume chart with it.

    The obvious later "simplification" is to collapse ``_AXES_WIDE_BAR_PLOTS``
    back to a set of types, which reads cleaner and is wrong. This is the test
    that catches that, so it drives the classification directly rather than
    building an mplfinance figure to reach it.
    """
    fig, ax = plt.subplots()
    ax.bar(CATEGORIES, SERIES_0, bottom=np.zeros(len(CATEGORIES)), label="s0")
    ax.bar(CATEGORIES, SERIES_1, bottom=SERIES_0, label="s1")

    figure_maidr = FigureManager.get_maidr(fig)
    volume = MplfinanceBarPlot(ax)
    figure_maidr.plots.append(volume)
    figure_maidr.selector_ids.append("volume-id")

    figure_maidr._drop_superseded_layers()

    assert volume in figure_maidr.plots
    assert "volume-id" in figure_maidr.selector_ids
    # The duplicate stacked registration is still dropped, so this is not
    # passing because the collapse stopped working.
    assert len(figure_maidr.plots) == 2


def test_collapsing_twice_changes_nothing() -> None:
    """It runs from two places, so it has to be safe to run again.

    ``_create_html_tag`` drops superseded layers before collecting artists -- it has to,
    since reading a superseded ``BarPlot``'s elements is what raised -- and
    ``_flatten_maidr`` collapses too, because it is reachable on its own.
    A single render therefore calls it twice.
    """
    fig, ax = plt.subplots()
    ax.bar(CATEGORIES, SERIES_0, label="s0")
    ax.bar(CATEGORIES, SERIES_1, bottom=SERIES_0, label="s1")

    figure_maidr = FigureManager.get_maidr(fig)
    figure_maidr._drop_superseded_layers()
    after_once = (list(figure_maidr.plots), list(figure_maidr.selector_ids))
    figure_maidr._drop_superseded_layers()

    assert (figure_maidr.plots, figure_maidr.selector_ids) == after_once
