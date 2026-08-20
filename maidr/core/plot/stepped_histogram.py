"""SteppedHistPlot — the histogram seaborn draws as an outline instead of bars."""

from __future__ import annotations

import math

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import PolyCollection

from maidr.core.plot.histogram import HistPlot

#: How far two bin widths may differ and still count as the same width.
#:
#: Relative, because the widths are data coordinates and a histogram of
#: nanoseconds and one of light-years both have to pass. The tolerance exists
#: at all because the widths come back through a float division of the axis
#: range, so evenly spaced bins are equal to within rounding rather than
#: exactly.
_WIDTH_TOLERANCE = 1e-9


class SteppedHistPlot(HistPlot):
    """
    A histogram drawn as one closed outline rather than as a row of bars.

    ``sns.histplot(element="step")`` and ``element="poly"`` draw the same
    distribution ``element="bars"`` does, as a single ``PolyCollection``
    instead of a ``BarContainer``. That is the whole of why they were silent:
    ``HistPlot`` looks a container up, seaborn's own patch asks whether the
    call drew bars, and neither finds anything -- the third branch of the
    decline #522 fixed for the bivariate mesh.

    The two spellings differ in what the outline traces, and so in how much of
    the reading is exact.

    ``step`` traces the **bin edges**. Its ring walks the baseline left to
    right, up the right-hand edge, and back along the tops, so every edge is
    visited on the way out and every count is held on the way back. Both
    halves are read off the drawing and nothing is reconstructed -- an empty
    bin included: its edges are on both legs, and its count is sampled inside
    it rather than taken from the flat run the return leg makes across it.

    ``poly`` traces the **bin centres**, joining them with straight lines, and
    the edges are not in the drawing at all. They are recovered from the
    spacing, which is exact when the bins are even and impossible when they
    are not: ``bins=[0, 1, 5, 10]`` gives centres 0.5, 3.0 and 7.5, and three
    numbers whose gaps are 2.5 and 4.5 do not say where the boundaries were.
    Such a chart is declined rather than announced with invented edges.

    Parameters
    ----------
    ax : Axes
        The axes the distribution was drawn on.
    collection : PolyCollection
        The outline this call produced, handed over rather than searched for:
        a ``hue`` draws one per series, and "the collection on this Axes"
        would read the first series once per layer.
    **kwargs : dict
        Ignored; accepted so the factory can forward what it was given.
    """

    def __init__(self, ax: Axes, collection: PolyCollection, **kwargs) -> None:
        self._collection = collection
        super().__init__(ax)
        # One `<path>` for the whole outline, as `Axes.stairs` has: there is no
        # per-bin element for a selector to name, and one naming the outline
        # would light the whole distribution up at every bin.
        self._support_highlighting = False

    def _extract_plot_data(self) -> list[dict]:
        """
        Read one point per bin off the outline.

        Returns
        -------
        list of dict
            One point per bin, in ascending bin order. Empty when the outline
            is not one this can read -- an uneven ``poly``, or a ring whose
            vertex count does not match either shape.
        """
        horizontal = _runs_up_the_y_axis(self._collection)
        if horizontal is None:
            return []
        self._orientation = "horz" if horizontal else "vert"

        bins = _read_outline(self._collection, horizontal)
        if bins is None:
            return []

        return [
            self._bin_point(self._orientation, low, high - low, count)
            for low, high, count in bins
        ]


def _runs_up_the_y_axis(collection: PolyCollection) -> bool | None:
    """
    Which way round the outline is, read off the drawing.

    Asked of the geometry rather than of the caller's keywords, because
    ``sns.histplot(y=...)``, ``sns.histplot(data=df, y="v")`` and a
    ``displot`` panel are three spellings of one chart and only the drawing is
    the same in all three.

    The ring opens on the first bin's edge and steps straight to the baseline,
    then walks along it -- so the second and third vertices share the baseline
    coordinate and differ in the other. That is the coordinate the bins run
    along.

    Parameters
    ----------
    collection : PolyCollection
        The outline seaborn drew.

    Returns
    -------
    bool or None
        True when the bins run up y, False when they run along x, and None
        when the ring is too short or too degenerate to say.
    """
    paths = collection.get_paths()
    if len(paths) != 1:
        return None
    vertices = np.asarray(paths[0].vertices, dtype=float)
    if len(vertices) < 3 or not np.all(np.isfinite(vertices[:3])):
        return None

    first, second = vertices[1], vertices[2]
    if first[1] == second[1] and first[0] != second[0]:
        return False
    if first[0] == second[0] and first[1] != second[1]:
        return True
    return None


def _read_outline(
    collection: PolyCollection, horizontal: bool
) -> list[tuple[float, float, float]] | None:
    """
    Recover ``(low edge, high edge, count)`` for every bin of one outline.

    Parameters
    ----------
    collection : PolyCollection
        The outline seaborn drew.
    horizontal : bool
        Whether the bins run up the y axis.

    Returns
    -------
    list of tuple, or None
        The bins in ascending order, or None when the outline cannot be read.

    Notes
    -----
    The vertex count narrows the shape but does not settle it: measured across
    one to eight bins a ``step`` ring holds ``4k + 5`` vertices and a ``poly``
    ring ``2k + 3``, and those collide at nine -- one bin stepped, three
    binned as a polygon. Read as the wrong one, an uneven three-bin ``poly``
    came back as a single bin spanning the first two, with the third gone.

    What separates them is how many distinct positions the ring visits along
    the binned axis: a step ring walks every **edge**, so ``k + 1`` of them,
    while a poly ring visits every **centre**, so ``k``. The two counts agree
    only at five vertices, which is below the step shape's own minimum -- so
    asking both and taking the one that matches is decisive rather than a
    tie-break.
    """
    paths = collection.get_paths()
    if len(paths) != 1:
        return None

    vertices = np.asarray(paths[0].vertices, dtype=float)
    if not np.all(np.isfinite(vertices)):
        return None

    # The bins run along one axis and the counts along the other; a horizontal
    # histogram is the same ring with the two swapped.
    along = vertices[:, 1] if horizontal else vertices[:, 0]
    across = vertices[:, 0] if horizontal else vertices[:, 1]

    total = len(vertices)
    positions = len({float(value) for value in along})

    if total >= 9 and (total - 5) % 4 == 0:
        bins = (total - 5) // 4
        if positions == bins + 1:
            return _read_step(along, across, bins)
    if total >= 5 and (total - 3) % 2 == 0:
        bins = (total - 3) // 2
        if positions == bins:
            return _read_poly(along, across, bins)
    return None


def _read_step(along: np.ndarray, across: np.ndarray, bins: int) -> list | None:
    """
    Read a ``step`` outline, whose ring walks every bin edge.

    Parameters
    ----------
    along : ndarray
        The coordinate the bins run along, per vertex.
    across : ndarray
        The coordinate the counts run along, per vertex.
    bins : int
        How many bins the vertex count says there are.

    Returns
    -------
    list of tuple, or None
        The bins, or None when the outward leg does not give ``bins + 1``
        distinct edges.
    """
    # The outward leg is the baseline walk, taken here because that is what it
    # is: the list of edges, in order, before any count is involved.
    #
    # Not because the return leg would lose one. It would not -- the ring is
    # closed, so both legs cross the full width and both visit every edge,
    # including the edges of a bin nothing landed in. Reading the edges off
    # the return leg instead gives the same answer on every chart here, which
    # is worth saying rather than leaving as an implied reason: what the
    # return leg cannot do is tell a run of empty bins apart by *height*,
    # since it runs flat across them, and that is why the counts below are
    # sampled per bin rather than read off its corners.
    edges = _distinct(along[1 : 2 * bins + 1])
    if len(edges) != bins + 1:
        return None

    # Read back left to right, the return leg is the staircase itself: a step
    # function whose value over a bin is that bin's count. Sampling it at the
    # midpoint asks the one question that has a single answer, whatever the
    # ring repeats at the corners.
    walk = list(zip(along[2 * bins + 2 :][::-1], across[2 * bins + 2 :][::-1]))
    if not walk:
        return None

    out = []
    for index in range(bins):
        low, high = edges[index], edges[index + 1]
        middle = (low + high) / 2
        held = [value for position, value in walk if position <= middle]
        if not held:
            return None
        out.append((low, high, float(held[-1])))
    return out


def _read_poly(along: np.ndarray, across: np.ndarray, bins: int) -> list | None:
    """
    Read a ``poly`` outline, whose ring joins the bin centres.

    Parameters
    ----------
    along : ndarray
        The coordinate the bins run along, per vertex.
    across : ndarray
        The coordinate the counts run along, per vertex.
    bins : int
        How many bins the vertex count says there are.

    Returns
    -------
    list of tuple, or None
        The bins, or None when the edges cannot be recovered -- a single bin,
        which has no spacing, or uneven bins, whose boundaries the centres do
        not determine.
    """
    if bins < 2:
        return None

    # The tops are the last leg of the ring, right to left, before the vertex
    # that closes it.
    centres = along[bins + 2 : 2 * bins + 2][::-1]
    counts = across[bins + 2 : 2 * bins + 2][::-1]
    if len(centres) != bins:
        return None

    widths = np.diff(centres)
    if len(widths) == 0 or not np.all(np.isfinite(widths)):
        return None
    width = float(widths[0])
    if width <= 0:
        return None
    if any(abs(other - width) > _WIDTH_TOLERANCE * max(abs(width), 1.0)
           for other in widths):
        return None

    half = width / 2
    return [
        (float(centre) - half, float(centre) + half, float(count))
        for centre, count in zip(centres, counts)
    ]


def _distinct(values: np.ndarray) -> list[float]:
    """
    Consecutive duplicates removed, order kept.

    Parameters
    ----------
    values : ndarray
        The coordinates of one leg of the ring.

    Returns
    -------
    list of float
        The distinct values, in the order walked.
    """
    out: list[float] = []
    for value in values:
        number = float(value)
        if not math.isfinite(number):
            continue
        if not out or out[-1] != number:
            out.append(number)
    return out


def reads(collection: PolyCollection) -> bool:
    """
    Whether an outline is one this can read, asked before a layer exists.

    An outline it cannot read -- an uneven ``poly``, whose centres do not say
    where the boundaries were -- must not become a layer at all. Registered
    anyway it is an empty row the core has to navigate into and cannot
    announce, which is the phantom-layer shape of #421, and the reading's own
    refusal would arrive too late to prevent it.

    Parameters
    ----------
    collection : PolyCollection
        The outline seaborn drew.

    Returns
    -------
    bool
        True when the bins and their counts come back off the drawing.
    """
    horizontal = _runs_up_the_y_axis(collection)
    if horizontal is None:
        return False
    return bool(_read_outline(collection, horizontal))
