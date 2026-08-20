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
