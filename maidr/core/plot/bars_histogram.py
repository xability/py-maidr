"""BarsHistPlot — the histogram ``seaborn.objects`` draws as one collection."""

from __future__ import annotations

import uuid
from typing import List, Sequence

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import PatchCollection

from maidr.core.plot.histogram import HistPlot
from maidr.exception import ExtractionError

#: The keyword the drawn collection is handed over under.
DRAWN_BINS = "bins"

#: The keyword the paths of one group are handed over under.
BIN_MEMBERS = "bin_members"


class BarsHistPlot(HistPlot):
    """
    A histogram drawn as one ``PatchCollection`` rather than as a container.

    ``so.Bars()`` is the continuous-x bar `seaborn.objects` draws for a
    histogram, where ``so.Bar()`` is the categorical one. Measured on
    ``seaborn 0.13.2``, the two leave different artists and that is the whole
    of why one was read and the other was not::

        so.Bar(), so.Count()   Rectangle patches + a BarContainer   read
        so.Bars(), so.Hist()   one PatchCollection of rectangles    --

    ``HistPlot`` looks a ``BarContainer`` up and finds none, which is the same
    decline ``element="step"`` hit before :class:`SteppedHistPlot` (#522).

    Every bin is read off its own rectangle, and nothing is reconstructed. A
    path runs ``[left, 0] [right, 0] [right, count] [left, count]``, so the
    edges and the count are all three in the drawing::

        vertical    [[-2.83, 0], [-2.39, 0], [-2.39, 3], [-2.83, 3], ...]
        horizontal  [[0, -2.83], [3, -2.83], [3, -2.39], [0, -2.39], ...]

    Orientation is read from the drawing rather than from the caller's
    ``orient=``, and not from one rectangle's vertices: measured, the first
    two differ on ``x`` in **both** orientations -- they span the bin when it
    is vertical and the count when it is not -- so the winding says nothing.
    What does is the baseline. A histogram's bars grow from zero, so the axis
    whose lowest point over the whole chart is zero is the count one.

    ``so.Stack()`` does not disturb that: it lifts the later segments and
    leaves the first sitting on the baseline. It does change what a bar's
    *length* means, which is why the count is read as a span rather than as a
    top -- see :func:`_span`.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        self._collection: PatchCollection = kwargs.pop(DRAWN_BINS, None)

        # Which of the collection's paths are this layer's. A colour split
        # overlays every group in one collection, so a layer is a slice of it
        # rather than the whole; absent means all of them.
        self._members: Sequence[int] | None = kwargs.pop(BIN_MEMBERS, None)

        super().__init__(ax, **kwargs)

    def _extract_plot_data(self) -> list[dict]:
        paths = self._paths()
        if not paths:
            raise ExtractionError(self.type, self.ax)

        corners = [np.asarray(path.vertices, dtype=float) for path in paths]
        self._orientation = "vert" if self._vertical(corners) else "horz"
        bins = 0 if self._orientation == "vert" else 1
        counts = 1 - bins

        data = []
        for corner in corners:
            # The rectangle's extent per axis rather than named vertices: the
            # path's winding is not the same in both orientations -- measured,
            # the first two vertices span the bin when it is vertical and the
            # count when it is not -- and a bounding box does not care.
            low, high = corner[:, bins].min(), corner[:, bins].max()
            if low == high:
                # A rectangle of no width spans no bin. Announcing it would
                # put both edges of a bin at the same place and claim a
                # boundary the chart never drew. No `so.Bars` spelling
                # reaches this -- measured across `Hist`, `Count`, `Agg` and
                # a raw `y`, a bin the binner produced has a width whether
                # or not anything landed in it -- so the guard is against a
                # collection from anywhere else, and it is tested against
                # one built to have the case rather than left as an
                # unreachable claim.
                continue
            # Plain floats, not the numpy scalars the vertices come back as:
            # `json.dumps` cannot write one, and the payload is serialised
            # into the SVG's `maidr` attribute (#429).
            data.append(
                self._bin_point(
                    self._orientation,
                    float(low),
                    float(high - low),
                    float(_span(corner[:, counts])),
                )
            )

        if not data:
            raise ExtractionError(self.type, self._collection)

        return data

    def _get_selector(self) -> List[str]:
        """
        One selector per bin, addressing its own path inside the group.

        The collection draws one path per bin as direct children of one
        group, and a colour split puts every group's bins in that same
        collection -- so a layer addresses its own paths by position and
        leaves its neighbours' alone. Numbered against the **collection**
        rather than against this layer's bins, which is what keeps the
        second group's selectors pointing at the second group's paths.

        Setting the gid here is the whole of the tagging. ``SegmentLinePlot``
        also puts its artist in ``_elements``, but it has stand-ins to
        displace; there is nothing here to displace, and measured, the gid
        written here reaches the rendered document on its own.

        Returns
        -------
        list of str
            One selector per bin, in the order the payload announces them.
        """
        gid = self._collection.get_gid()
        if not gid or not str(gid).startswith("maidr-"):
            gid = f"maidr-{uuid.uuid4()}"
            self._collection.set_gid(gid)

        return [
            f"g[id='{gid}'] > path:nth-of-type({position + 1})"
            for position in self._positions()
        ]

    def _positions(self) -> list[int]:
        """Which of the collection's paths this layer draws, in order."""
        count = len(self._collection.get_paths()) if self._collection else 0
        if self._members is None:
            return list(range(count))
        return [index for index in self._members if 0 <= index < count]

    def _paths(self) -> list:
        """This layer's rectangles, in drawing order."""
        if self._collection is None:
            return []
        paths = self._collection.get_paths()
        return [paths[index] for index in self._positions()]

    @staticmethod
    def _vertical(corners: Sequence[np.ndarray]) -> bool:
        """
        Whether the bins run along the x axis.

        Two rectangles say it outright: they sit at different places along
        the bin axis and start from the same value on the count axis, so the
        axis their lower corners differ on is the bin axis.

        Parameters
        ----------
        corners : sequence of numpy.ndarray
            Each rectangle's path vertices, in drawing order.

        Returns
        -------
        bool
            True when the bins run along x.
        """
        drawn = np.vstack([np.asarray(corner, dtype=float) for corner in corners])

        # A histogram's bars grow from zero, so the count axis is the one
        # whose lowest point over the whole chart is zero. True of a stack
        # too: it lifts the later segments and leaves the first sitting on
        # the baseline. Answered from the drawing as a whole rather than by
        # comparing two bars, so it holds for a chart of one bin.
        if drawn[:, 1].min() == 0:
            return True
        return drawn[:, 0].min() != 0


def _span(values: np.ndarray) -> float:
    """
    What one bar holds: the length of the rectangle, not where its top is.

    The two are the same only while every bar starts at zero. Measured, a
    stacked histogram lifts the later ones -- ``so.Bars(), so.Hist(),
    so.Stack()`` draws a second level's bar from 1 to 41 -- so reading the
    top would announce 41 where that level counted 40, and every level but
    the first would be announced with its neighbours' counts added on.

    That is also what ``HistPlot`` reads on its own path: a ``BarContainer``
    patch's ``get_height()`` is the segment, matplotlib having stacked it by
    moving the bottom rather than by growing the bar.

    Parameters
    ----------
    values : numpy.ndarray
        One rectangle's coordinates on the count axis.

    Returns
    -------
    float
        What that bar holds.
    """
    return float(values.max()) - float(values.min())


def hist_groups(ax: Axes, collection: PatchCollection) -> list[tuple[str, list[int]]] | None:
    """
    The groups a colour-split ``so.Bars`` layer was drawn with, or ``None``.

    The ``PatchCollection`` counterpart of
    :func:`maidr.core.plot.barplot.bar_groups`, and the same question: one
    artist carries every level, so the grouping survives only in the
    rectangles' colours and in the legend that names them.

    Needed here for the reason the bar one is needed and one more. A classic
    ``seaborn.histplot(hue=...)`` draws a container **per level**, so each
    layer already holds one distribution; ``so.Bars()`` overlays every level
    in one collection, and read whole it would announce two distributions'
    bins as one -- the same bin edge appearing twice with two different
    counts, in no stated order.

    Measured, the paths run group by group rather than interleaved, so a
    level's bins stay in bin order inside its own layer.

    Parameters
    ----------
    ax : Axes
        The axes drawn on, for its legend.
    collection : matplotlib.collections.PatchCollection
        The drawn rectangles.

    Returns
    -------
    list of (str, list of int) or None
        One entry per group in legend order, naming it and listing the
        collection positions that belong to it, or ``None`` when the layer is
        not grouped.
    """
    from maidr.core.plot.scatterplot import _rgba, groups_from_colours

    colours = np.asarray(collection.get_facecolors(), dtype=float)
    if colours.ndim == 1:
        colours = colours.reshape(1, -1)
    count = len(collection.get_paths())
    if len(colours) == 0:
        return None

    # Cycled rather than indexed, for the reason `SegmentLinePlot` cycles its
    # own: `get_facecolors()` returns exactly what was set, and matplotlib
    # cycles those over the paths at draw time -- measured, four rectangles
    # given two colours come back as a (2, 4) array with all four drawn.
    # Indexed straight, the third rectangle falls off the end.
    #
    # Measured, `so.Bars` always sets one per rectangle -- 8 for 8 bins, 16
    # for a two-level split -- so no chart drawn by this mark reaches the
    # cycle. It is the collection's contract rather than the mark's, and it
    # is tested against a collection built to have it.
    return groups_from_colours(
        ax, [_rgba(colours[index % len(colours)][:4]) for index in range(count)]
    )
