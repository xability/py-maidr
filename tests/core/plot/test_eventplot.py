"""`Axes.eventplot` draws a raster of event times, and it read as nothing (#548).

An event plot puts a tick at every event time, one row per series -- a spike
train, an arrival timeline, a log of occurrences. It is the standard way to
draw all three, and it registered no layer at all.

Everything a reading needs is on the artist. `eventplot` returns one
`EventCollection` per row, and each carries its positions, the offset it sits
at on the other axis, and which axis the events run along.

Two decisions are pinned here rather than left implicit.

**A scatter, not a spike.** A spike stands a *magnitude* at a place and its
length is the data. An event plot's ticks are all the same length --
`get_linelength()` is one number for the whole row -- so the height is
decoration and only the position is data, which is a scatter.

**One layer per row.** The rows are separate series, and merging them
announces one cloud where the chart shows several, which is what #426 was
about for scatters drawn as several collections.

No `orientation` key is emitted, and that is deliberate: a scatter is
symmetric, its trace does not read the key, and the coordinates below carry
the orientation already by being swapped. Declaring one without the other is
the defect #480 and xability/r-maidr#189 both had; declaring it *as well* as
swapping would be the same mistake from the other side.
"""

from __future__ import annotations

import re

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402

import maidr  # noqa: E402
from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402

#: Two rows of different lengths, so a reading that merged them or mixed up
#: which row is which cannot pass by symmetry.
ROWS = [np.array([1.0, 4.0, 7.0]), np.array([2.0, 5.0])]


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


def _points(layer: dict) -> list[tuple[float, float]]:
    """
    One layer's coordinates.

    Parameters
    ----------
    layer : dict
        The emitted layer.

    Returns
    -------
    list of tuple
        Its points as ``(x, y)``.
    """
    return [
        (float(point[MaidrKey.X]), float(point[MaidrKey.Y]))
        for point in layer[MaidrKey.DATA]
    ]


def _paths_in(html: str, gid: str) -> int:
    """
    How many ``<path>`` elements a group holds in the rendered SVG.

    Parameters
    ----------
    html : str
        The rendered chart.
    gid : str
        The id matplotlib wrote the row's group under.

    Returns
    -------
    int
        The count, or -1 when the group is not in the document at all.
    """
    svg = html[html.index("<svg") : html.index("</svg>") + 6]
    marker = svg.find(f'id="{gid}"')
    if marker == -1:
        return -1
    opening = svg.rfind("<g", 0, marker)
    return len(re.findall(r"<path\b", svg[opening : svg.index("</g>", opening)]))


def test_each_row_is_its_own_layer():
    """Two rows, two layers, each a scatter."""
    fig, ax = plt.subplots()
    ax.eventplot(ROWS)

    layers = _layers(fig)

    assert [layer[MaidrKey.TYPE] for layer in layers] == [
        PlotType.SCATTER,
        PlotType.SCATTER,
    ]


def test_a_row_announces_its_events_at_its_own_offset():
    """
    The events are the positions; the offset says which row they are in.

    Asserted per row rather than as a set, because the failure worth catching
    is two rows reading the same collection -- the shape of #426 -- and that
    passes any assertion about the points being present somewhere.
    """
    fig, ax = plt.subplots()
    ax.eventplot(ROWS)

    first, second = _layers(fig)

    assert _points(first) == [(1.0, 0.0), (4.0, 0.0), (7.0, 0.0)]
    assert _points(second) == [(2.0, 1.0), (5.0, 1.0)]


def test_a_vertical_raster_swaps_the_axes_rather_than_declaring_a_swap():
    """
    ``orientation="vertical"`` puts the events on y and the rows on x.

    The coordinates carry it. A scatter's trace does not read
    ``MaidrLayer.orientation`` -- points are symmetric -- so the swap has to
    be in the data or it does not happen at all.
    """
    fig, ax = plt.subplots()
    ax.eventplot(ROWS, orientation="vertical")

    first, second = _layers(fig)

    assert _points(first) == [(0.0, 1.0), (0.0, 4.0), (0.0, 7.0)]
    assert _points(second) == [(1.0, 2.0), (1.0, 5.0)]
    assert MaidrKey.ORIENTATION not in first


def test_the_axis_the_rows_are_stacked_along_is_named():
    """
    "Row", where the caller named nothing, on whichever axis carries them.

    The base fills "X" and "Y" as placeholders, so a reader of an unlabelled
    raster would otherwise be told the series are stacked along "Y" -- a
    letter, where the chart has rows.
    """
    fig, ax = plt.subplots()
    ax.eventplot(ROWS)
    horizontal = _layers(fig)[0][MaidrKey.AXES]

    plt.close(fig)
    fig, ax = plt.subplots()
    ax.eventplot(ROWS, orientation="vertical")
    vertical = _layers(fig)[0][MaidrKey.AXES]

    assert horizontal[MaidrKey.Y][MaidrKey.LABEL] == "Row"
    assert vertical[MaidrKey.X][MaidrKey.LABEL] == "Row"


def test_a_caller_who_labels_the_axis_keeps_their_label():
    """The default is a fallback, not an override."""
    fig, ax = plt.subplots()
    ax.set_ylabel("neuron")
    ax.eventplot(ROWS)

    assert _layers(fig)[0][MaidrKey.AXES][MaidrKey.Y][MaidrKey.LABEL] == "neuron"


def test_named_rows_are_announced_by_their_names():
    """
    A raster is routinely drawn against named rows, and the names are on the
    ticks rather than in the collections.

    ``MaidrLayer.name`` is what xability/maidr#828 added so two layers of a
    kind can be told apart, which is exactly the position a reader is in with
    a stack of identical-looking rows.
    """
    fig, ax = plt.subplots()
    ax.set_yticks([0, 1], ["neuron A", "neuron B"])
    ax.eventplot(ROWS)

    assert [layer.get(MaidrKey.NAME) for layer in _layers(fig)] == [
        "neuron A",
        "neuron B",
    ]


def test_an_unlabelled_row_is_not_named_after_its_own_number():
    """
    An unlabelled axis still has ticks, and their text is the offset.

    Taking it would "name" every row `0.0`, `1.0`, `2.0` -- the coordinate the
    payload already carries, so a reader switching layers would hear a number
    they were about to be told anyway. Worse than no name.
    """
    fig, ax = plt.subplots()
    ax.eventplot(ROWS)

    assert [layer.get(MaidrKey.NAME) for layer in _layers(fig)] == [None, None]


def test_a_row_with_no_events_is_not_a_layer():
    """
    An empty row would be a layer to walk into and find nothing (#421).

    The rows that did draw keep their own names, so this also pins that
    skipping one does not shift the names of the rest.
    """
    fig, ax = plt.subplots()
    ax.set_yticks([0, 1], ["quiet", "busy"])
    ax.eventplot([[], ROWS[0]])

    layers = _layers(fig)

    assert len(layers) == 1
    assert layers[0].get(MaidrKey.NAME) == "busy"
    assert len(layers[0][MaidrKey.DATA]) == 3


def test_every_selector_names_an_element_of_its_own_row():
    """
    The highlight follows the split, checked against the document.

    Measured: a row's collection is written as one ``<g>`` carrying one
    ``<path>`` per event, so an event has an element of its own. A layer whose
    selectors resolved into another row's group -- or to nothing -- would read
    correctly through audio, braille and text while outlining the wrong ticks,
    which is the blind spot xability/maidr#814 names.
    """
    fig, ax = plt.subplots()
    ax.eventplot(ROWS)
    html = str(maidr.render(fig).get_html_string())

    groups = set()
    for layer in _layers(fig):
        selectors = layer[MaidrKey.SELECTOR]
        assert len(selectors) == len(layer[MaidrKey.DATA])

        for selector in selectors:
            gid = selector.split("'")[1]
            groups.add(gid)
            wanted = int(re.search(r"nth-of-type\((\d+)\)", selector).group(1))
            available = _paths_in(html, gid)
            assert available >= wanted, (
                f"selector asks for path {wanted} of a group holding {available}"
            )

    # Two rows, two groups: a single shared group would mean both layers were
    # addressing the same elements while announcing different events.
    assert len(groups) == 2


def test_named_rows_survive_a_non_default_spacing():
    """
    A row is looked up by its own offset, not by its place in the list.

    The two are the same only at the default spacing.
    ``ax.eventplot(rows, lineoffsets=2)`` puts the second row at 2.0 --
    measured, ``get_lineoffset()`` returns 0 and 2 -- so a lookup by index
    asks the axis about 1.0, finds nothing, and silently drops a name the
    caller set explicitly. Every coordinate stays right while the layer goes
    unnamed, which is the kind of gap no assertion about the data would see.
    """
    fig, ax = plt.subplots()
    ax.set_yticks([0, 2], ["neuron A", "neuron B"])
    ax.eventplot(ROWS, lineoffsets=2)

    layers = _layers(fig)

    assert [layer.get(MaidrKey.NAME) for layer in layers] == [
        "neuron A",
        "neuron B",
    ]
    assert _points(layers[1]) == [(2.0, 2.0), (5.0, 2.0)]


def test_a_row_holding_a_missing_value_still_reads():
    """
    One non-finite value must not take the chart down.

    ``EventCollection.get_positions()`` **raises** on such a row: matplotlib
    gives a non-finite event a degenerate segment of shape ``(0,)`` and
    ``get_positions`` indexes it as ``segment[0, pos]``.

        ax.eventplot([[2.0, float("nan"), 5.0]])
        coll.get_segments()   # [(2, 2), (2, 2), (0,)]
        coll.get_positions()  # IndexError

    So reading the artist the convenient way would turn a chart that draws
    today into one that raises inside the caller's own plotting call --
    which is why the reader works off ``get_segments()`` instead.
    """
    fig, ax = plt.subplots()
    drawn = ax.eventplot([[2.0, float("nan"), 5.0]])

    layers = _layers(fig)

    # The offset is read off the artist rather than written down: matplotlib
    # places a lone row at 1.0 and a pair at 0.0 and 1.0, and this test is
    # about the missing value, not about that.
    offset = float(drawn[0].get_lineoffset())

    assert len(layers) == 1
    assert _points(layers[0]) == [(2.0, offset), (5.0, offset)]


def test_a_missing_value_leaves_an_element_the_reader_is_never_sent_to():
    """
    The document holds a mark for the value that was dropped, and no
    announced event is addressed to it.

    Measured, matplotlib writes one ``<path>`` per *segment* including the
    degenerate one -- three paths for two drawable events -- and it **sorts**
    the row, putting the non-finite value last:

        ax.eventplot([[5.0, float("nan"), 2.0]])
        segments      [(2, 2), (2, 2), (0,)]
        first coords  2.0, 5.0, None

    So the surplus element is at the end here rather than in the middle, and
    the two announced events happen to be elements one and two. That is the
    ordering this asserts, together with the count -- because what must hold
    is that every selector names the element of the event it announces, and
    a reading that numbered its own points from one would be right in this
    layout and wrong the moment matplotlib stopped sorting.

    The announced order is the sorted order, which is also worth knowing: the
    reader walks the row left to right, not in the order the caller wrote.
    """
    fig, ax = plt.subplots()
    ax.eventplot([[5.0, float("nan"), 2.0]])
    html = str(maidr.render(fig).get_html_string())

    layer = _layers(fig)[0]
    selectors = layer[MaidrKey.SELECTOR]

    assert [point[MaidrKey.X] for point in layer[MaidrKey.DATA]] == [2.0, 5.0]
    assert len(selectors) == 2

    positions = [
        int(re.search(r"nth-of-type\((\d+)\)", selector).group(1))
        for selector in selectors
    ]
    assert positions == [1, 2]

    # One element more than there are events: the dropped value kept its slot.
    gid = selectors[0].split("'")[1]
    assert _paths_in(html, gid) == 3


def test_a_row_of_only_missing_values_is_not_a_layer():
    """
    Nothing drawable is nothing to announce, however it came to be empty.

    A row given no events and a row whose every event is non-finite differ in
    the artist -- no segments against degenerate ones -- and neither has
    anything for a reader to walk into (#421).
    """
    fig, ax = plt.subplots()
    ax.eventplot([[float("nan"), float("nan")], ROWS[0]])

    layers = _layers(fig)

    assert len(layers) == 1
    assert len(layers[0][MaidrKey.DATA]) == 3


def test_a_raster_beside_another_chart_stays_in_its_own_panel():
    """
    Both rows land in the subplot they were drawn on, and only there.

    A figure of several panels is the ordinary case for a raster -- the spike
    train above, the stimulus trace below -- and the rows are registered in a
    loop that names an axes once, outside it. An axes resolved from the
    figure rather than from the artist would put every row in whichever
    panel is current, which reads as one panel holding a chart it does not
    draw and another holding nothing.
    """
    fig, (left, right) = plt.subplots(1, 2)
    left.eventplot(ROWS)
    right.scatter([1.0, 2.0], [3.0, 4.0])

    grid = FigureManager.get_maidr(fig)._flatten_maidr()["subplots"]

    assert [len(cell["layers"]) for row in grid for cell in row] == [2, 1]

    raster, other = grid[0][0]["layers"], grid[0][1]["layers"][0]
    assert [_points(layer) for layer in raster] == [
        [(1.0, 0.0), (4.0, 0.0), (7.0, 0.0)],
        [(2.0, 1.0), (5.0, 1.0)],
    ]
    assert _points(other) == [(1.0, 3.0), (2.0, 4.0)]


# --- The bounds that make the layer reachable in grid mode (#606) ------------
#
# A point layer renders braille only in grid mode, and grid mode is built from
# `axes.{x,y}.{min,max,tickStep}`. With the labels alone, maidr's `ScatterTrace`
# returns `{empty: true}`, so a raster was the second chart -- after a rug,
# fixed in #605 -- with no braille surface reachable by any keystroke.
# Measured there, the first row of `ROWS` over a 0.7-7.3 axis now gives
# `values [[1, 0, 0, 1, 0, 0, 1]]`: the events at 1, 4 and 7, spaced as the
# axis spaces them, which is the pattern a raster is drawn to show and the one
# thing its audio cannot carry -- every event in a row is the same pitch.
#
# One grid per row, not one for the chart. `ScatterTrace` holds `gridCells` as
# instance state and builds them from its own layer's points, so it never sees
# a sibling row's events: a whole-chart surface, one row felt against another,
# is not something a producer can ask for. That settles the question #606 left
# open by architecture rather than by preference.


def _axis(layer, key) -> dict:
    """
    One axis' config, as plain data.

    ``MaidrKey`` is a str enum, so the emitted keys compare equal to their
    plain-string spellings -- but the dict itself is keyed by the enum members,
    and ``dict()`` is what lets it be compared against a literal.

    Parameters
    ----------
    layer : dict
        The emitted layer.
    key : str
        Which axis.

    Returns
    -------
    dict
        The axis config.
    """
    return dict(layer[MaidrKey.AXES][key])


def test_the_event_axis_carries_the_chart_s_own_bounds():
    """The plotting area, not the spread of one row's events.

    A reader feeling the grid is feeling the axis they would see, and the two
    rows here hold different events -- so bounds taken from the data would put
    each row on a surface of its own width and make the same cell mean two
    different spans.
    """
    fig, ax = plt.subplots()
    ax.eventplot(ROWS)

    low, high = ax.get_xlim()
    for layer in _layers(fig):
        x = _axis(layer, MaidrKey.X)
        assert x[MaidrKey.MIN] == pytest.approx(low)
        assert x[MaidrKey.MAX] == pytest.approx(high)
        assert x[MaidrKey.TICK_STEP] > 0


def test_each_row_is_one_cell_deep_at_the_offset_it_was_drawn_at():
    """
    Across the rows, the grid is exactly the one cell this layer occupies.

    Its *own* cell, which is the whole difference between a raster and a rug:
    a rug always sits at zero, while ``eventplot`` stacks its rows at 0, 1,
    2 ... and each layer holds exactly one of them.

    Measured against maidr's `ScatterTrace`, the two readings are the
    difference between a surface and a blank one. With its own cell the
    second row gives `values [[0, 1, 0, 0, 1, 0, 0]]` -- its two events,
    where they fall. Handed the zero-centred cell instead, every one of its
    points is outside the surface and it gives `[[0, 0, 0, 0, 0, 0, 0]]`: a
    grid that renders, reports nothing wrong, and says the row is empty.

    One cell deep rather than finer: there is nothing to resolve across a row
    whose entries all sit at the same offset, and a smaller step buys rows of
    zeroes.
    """
    fig, ax = plt.subplots()
    ax.eventplot(ROWS)

    first, second = _layers(fig)

    assert _axis(first, MaidrKey.Y) == {
        MaidrKey.LABEL: "Row",
        MaidrKey.MIN: -0.5,
        MaidrKey.MAX: 0.5,
        MaidrKey.TICK_STEP: 1.0,
    }
    assert _axis(second, MaidrKey.Y) == {
        MaidrKey.LABEL: "Row",
        MaidrKey.MIN: 0.5,
        MaidrKey.MAX: 1.5,
        MaidrKey.TICK_STEP: 1.0,
    }


def test_a_row_at_a_non_default_offset_gets_the_cell_it_was_drawn_in():
    """
    The offset is read off the artist, not counted from the layer's place.

    The two agree only at the default spacing.
    ``ax.eventplot(rows, lineoffsets=2)`` draws the second row at 2.0, so a
    cell numbered from the layer index would hand it -0.5 to 0.5 and 0.5 to
    1.5 -- a surface its events sit outside of, while every coordinate in the
    payload stays right. Same trap the row *names* fell into before
    ``test_named_rows_survive_a_non_default_spacing``.
    """
    fig, ax = plt.subplots()
    ax.eventplot(ROWS, lineoffsets=2)

    first, second = _layers(fig)

    assert (_axis(first, MaidrKey.Y)[MaidrKey.MIN], _points(first)[0][1]) == (-0.5, 0.0)
    assert (_axis(second, MaidrKey.Y)[MaidrKey.MIN], _points(second)[0][1]) == (
        1.5,
        2.0,
    )


def test_a_vertical_raster_bounds_the_axis_its_events_run_along():
    """The bounds follow the orientation, as the coordinates already do.

    Reading the wrong axis would be silent: both are numeric and both have
    ticks, so a grid built across the rows and one cell wide along the events
    is a surface that resolves nothing and reports no error.
    """
    fig, ax = plt.subplots()
    ax.eventplot(ROWS, orientation="vertical")

    first, second = _layers(fig)

    assert _axis(first, MaidrKey.Y)[MaidrKey.MIN] == pytest.approx(ax.get_ylim()[0])
    assert _axis(first, MaidrKey.X) == {
        MaidrKey.LABEL: "Row",
        MaidrKey.MIN: -0.5,
        MaidrKey.MAX: 0.5,
        MaidrKey.TICK_STEP: 1.0,
    }
    assert _axis(second, MaidrKey.X)[MaidrKey.MIN] == 0.5


def test_a_caller_s_own_name_for_the_rows_survives_the_bounds():
    """A grid says where the cells are, never what the axis is called."""
    fig, ax = plt.subplots()
    ax.set_ylabel("neuron")
    ax.eventplot(ROWS)

    y = _axis(_layers(fig)[0], MaidrKey.Y)
    assert y[MaidrKey.LABEL] == "neuron"
    assert y[MaidrKey.MAX] == 0.5


def test_unevenly_spaced_ticks_take_the_row_cells_with_them():
    """
    Half a grid is not a grid, so the decline has to reach both axes.

    An axis whose ticks are not evenly spaced names no step, and a surface
    built on an invented one has cells that do not correspond to the axis the
    reader is told about. Emitting the row cell anyway would leave bounds on
    one axis alone -- which builds nothing, and reads as a chart that meant to
    offer a grid.
    """
    fig, ax = plt.subplots()
    ax.set_xticks([0.0, 1.0, 5.0, 10.0])
    ax.eventplot(ROWS)

    layer = _layers(fig)[0]
    assert _axis(layer, MaidrKey.X) == {MaidrKey.LABEL: "X"}
    assert _axis(layer, MaidrKey.Y) == {MaidrKey.LABEL: "Row"}


def test_a_log_event_axis_is_declined():
    """Spikes on a log time axis are an ordinary chart, and the cells a linear
    grid describes are not the cells that axis draws."""
    fig, ax = plt.subplots()
    ax.set_xscale("log")
    ax.eventplot(ROWS)

    layer = _layers(fig)[0]
    assert _axis(layer, MaidrKey.X) == {MaidrKey.LABEL: "X"}
    assert _axis(layer, MaidrKey.Y) == {MaidrKey.LABEL: "Row"}


def test_the_bounds_change_nothing_the_layer_already_said():
    """Additive only: grid mode is entered deliberately, so the reading a
    reader gets without asking for it has to be untouched. Pinned against what
    the layer emitted before the bounds existed."""
    fig, ax = plt.subplots()
    ax.set_yticks([0, 1], ["neuron A", "neuron B"])
    ax.eventplot(ROWS)

    first, second = _layers(fig)

    assert [layer.get(MaidrKey.NAME) for layer in (first, second)] == [
        "neuron A",
        "neuron B",
    ]
    assert _points(first) == [(1.0, 0.0), (4.0, 0.0), (7.0, 0.0)]
    assert _points(second) == [(2.0, 1.0), (5.0, 1.0)]
    assert len(first[MaidrKey.SELECTOR]) == 3
