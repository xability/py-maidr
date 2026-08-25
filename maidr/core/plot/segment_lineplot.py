"""SegmentLinePlot — the series a ``LineCollection`` draws, one per segment."""

from __future__ import annotations

import uuid
from typing import List

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D

from maidr.core.enum.plot_type import PlotType
from maidr.core.plot.lineplot import MultiLinePlot

#: The keyword the collection is handed over under.
#:
#: The same one ``SteppedHistPlot`` takes, and for the same reason: the layer
#: is told which artist it describes rather than searching the axes, so a
#: second call on the same panel reads its own.
DRAWN_SEGMENTS = "collection"


class SegmentLinePlot(MultiLinePlot):
    """
    Several line series drawn as one ``LineCollection`` rather than as a
    ``Line2D`` each.

    ``so.Lines`` and ``so.Paths`` are the mark ``seaborn.objects`` draws when
    the series are many: measured, a colour-split layer leaves **one**
    collection carrying one segment per group, where ``so.Line`` leaves one
    ``Line2D`` per group. The reading is the same multi-series line either
    way, so everything about *what is announced* is inherited -- coordinates,
    the gap rule, per-series naming from whichever legend named the colours,
    the ``z`` label. Only two things differ, and both are about the artist.

    **Where the series come from.** ``MultiLinePlot`` walks ``Line2D``
    objects, so each segment is wrapped in one. They are stand-ins rather
    than drawings: never added to the axes, carrying the segment's points and
    the colour it was drawn in, which is all the inherited walk reads. The
    colour matters -- it is what pairs a series with its legend entry, and
    pairing by position gets two groups the wrong way round whenever the
    legend is not in the drawn order (#582).

    **What is outlined.** One collection is one SVG group holding one
    ``<path>`` per segment, in segment order -- measured, three groups give
    three paths as direct children. So a series is addressed by its position
    within the group rather than by a group of its own, which is the one
    thing the inherited selector cannot say.

    An empty segment is not a case to handle: ``LineCollection`` refuses to
    hold one, so every segment has at least one point and the paths and the
    series stay one to one. A single-point group *is* drawn -- measured, it
    leaves a segment and a degenerate path of its own -- so it keeps its
    position in both lists.

    Parameters
    ----------
    ax : Axes
        The axes the series were drawn on.
    collection : LineCollection
        The collection this call produced, handed over rather than searched
        for.
    **kwargs : dict
        Forwarded to :class:`MultiLinePlot`.
    """

    def __init__(self, ax: Axes, collection: LineCollection, **kwargs) -> None:
        super().__init__(ax, PlotType.LINE, **kwargs)
        self._collection = collection

    def _series(self) -> List[Line2D]:
        """
        One stand-in ``Line2D`` per drawn segment.

        Rebuilt on each walk rather than kept. Nothing downstream holds one
        by identity -- the payload reads their coordinates and colours, the
        selectors read only how many there are, and the artist that gets
        tagged is the collection -- so a cache would be a rule no caller
        relies on.

        The colour **is** relied on: it is what pairs a series with its
        legend entry, which is the pairing #582 exists for. Matplotlib does
        not expand a short colour list to match the segments -- measured, a
        collection drawn in one colour reports exactly one however many
        segments it holds, and that is the default -- so the reading cycles
        it the way the drawing does rather than running off the end.

        Returns
        -------
        list of Line2D
            In the order the collection holds its segments, which is the
            order it draws them.
        """
        colours = np.asarray(self._collection.get_colors())
        stand_ins: List[Line2D] = []
        for index, segment in enumerate(self._collection.get_segments()):
            points = np.asarray(segment, dtype=float)
            line = Line2D(points[:, 0], points[:, 1])
            if len(colours):
                line.set_color(colours[index % len(colours)])
            stand_ins.append(line)
        return stand_ins

    def _extract_line_data(self):
        """
        The inherited reading, with the drawn artist put back.

        ``MultiLinePlot`` records each series' ``Line2D`` as the element to
        tag, which is right where the series *are* the drawing. Here they are
        stand-ins that were never added to the axes, so tagging them would
        write a ``maidr`` attribute onto nothing and the collection's own
        group would carry none. The one collection is the one drawn artist.

        No guard on an empty reading: the inherited ``_extract_plot_data``
        raises rather than returning one, so a layer that read nothing never
        reaches the tagging at all.

        Returns
        -------
        list[list[dict]] or None
            Whatever the inherited walk read.
        """
        data = super()._extract_line_data()
        self._elements.clear()
        self._elements.append(self._collection)
        return data

    def _get_selector(self) -> List[str]:
        """
        One selector per series, addressing its own path inside the group.

        The inherited selector answers ``g[id=…] path`` per line, which is
        right when each series has a group of its own and wrong here: every
        series would outline every other one's segment too.

        The gid is assigned here when the collection has none, exactly as the
        inherited walk does for a line. ``maidr.patch.highlight`` keeps an id
        that already begins with ``maidr-`` when the artist is drawn, so the
        one written here is the one that reaches the SVG.

        Returns
        -------
        list of str
            One selector per segment, in the order the payload announces them.
        """
        gid = self._collection.get_gid()
        if not gid or not str(gid).startswith("maidr-"):
            gid = f"maidr-{uuid.uuid4()}"
            self._collection.set_gid(gid)

        return [
            f"g[id='{gid}'] > path:nth-of-type({position + 1})"
            for position in range(len(self._series()))
        ]
