from __future__ import annotations

import math
import uuid

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import EventCollection

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot

#: The keyword the event patch hands one row's collection to this layer under.
#: A chart is one collection per row and one layer per collection, so the
#: layer is told which row it reads rather than sweeping for it -- the
#: distinction #426 was about, one axes along.
DRAWN_EVENTS = "_maidr_events"

#: The keyword carrying the row's name, when the axis it sits on has one.
EVENT_ROW_LABEL = "_maidr_event_row"


def events(collection: EventCollection) -> list[tuple[int, float]]:
    """
    The events a row actually drew, each with its place among the row's marks.

    Read from ``get_segments()`` rather than from ``get_positions()``, which
    **raises** on any row holding a non-finite value. matplotlib gives a
    non-finite event a degenerate segment of shape ``(0,)`` and
    ``get_positions`` indexes it as ``segment[0, pos]``:

        ax.eventplot([[2.0, float("nan"), 5.0]])
        coll.get_segments()   # [(2, 2), (2, 2), (0,)]
        coll.get_positions()  # IndexError: too many indices for array

    So a single missing value in an otherwise ordinary row is enough, and
    asking the artist the convenient way would turn a chart that draws today
    into one that raises.

    Two indices come back because they are not the same one. The float is the
    event's position; the integer is its place among the row's *segments*,
    which is what the SVG is numbered by -- measured, matplotlib writes one
    ``<path>`` per segment including the degenerate ones, so a row with three
    segments has three elements whether or not all three were drawable.

    They cannot currently disagree, and that is worth stating rather than
    implying. ``EventCollection.set_positions`` sorts with ``np.sort``, which
    puts every non-finite value last, so a degenerate segment never precedes
    a drawable one and numbering the announced points from one would give the
    same answer. The segment index is kept anyway: it is what the document is
    actually numbered by, and it is the version that stays right on the day
    that sort changes. No test separates the two, because no chart can.

    The sort also decides the reading order. A row is announced left to
    right, not in the order the caller wrote it.

    Parameters
    ----------
    collection : EventCollection
        One row of the chart.

    Returns
    -------
    list of (int, float)
        The segment index and position of every drawable event, in order.
    """
    along = 0 if collection.get_orientation() == "horizontal" else 1

    drawn = []
    for index, segment in enumerate(collection.get_segments()):
        marks = np.asarray(segment)
        if marks.ndim != 2 or marks.shape[0] == 0:
            # A non-finite event. matplotlib drew no line for it, so there is
            # nothing to announce and nothing a reader could be shown -- and
            # emitting it would put `NaN` in the payload, which `JSON.parse`
            # rejects outright and which stops the chart initialising (#427).
            continue
        position = float(marks[0, along])
        if math.isfinite(position):
            drawn.append((index, position))
    return drawn


def reads(collection: EventCollection) -> bool:
    """
    Whether a row has anything to announce.

    An event plot drawn from an empty row -- ``ax.eventplot([[], times])`` --
    produces a collection with no segments, and one whose every value is
    non-finite produces only degenerate ones. Either way there is nothing to
    announce, and registering it would put a layer with no points in the
    schema for a reader to walk into and find nothing, which is the
    phantom-layer shape of #421.

    Parameters
    ----------
    collection : EventCollection
        One row of the chart.

    Returns
    -------
    bool
        True when the row drew at least one event.
    """
    return len(events(collection)) > 0


class EventPlot(MaidrPlot):
    """
    One row of an event plot, read as the positions it marks.

    An event plot -- a raster plot, a spike train, an arrival timeline -- puts
    a tick at every event time, one row per series. Each row is a
    ``EventCollection`` carrying its positions, the offset it sits at on the
    other axis, and which axis the events run along.

    Read as a **scatter**, not a spike. A spike stands a *magnitude* at a
    place, and its length is data; an event plot's ticks are all the same
    length -- ``get_linelength()`` is one number for the whole row -- so the
    height is decoration and only the position is data. What the reader
    navigates is a series of positions, which is a scatter.

    One layer per row rather than one for the chart, for the reason #426
    gives about scatters: the rows are separate series, and merging them
    announces one cloud where the chart shows several.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        super().__init__(ax, PlotType.SCATTER)

        collection = kwargs.get(DRAWN_EVENTS, None)
        self._collection = (
            collection if isinstance(collection, EventCollection) else None
        )
        self._row_label = kwargs.get(EVENT_ROW_LABEL, None)

        # Assigned here rather than relied upon, for the reason `HexbinPlot`
        # and `contour.tag` give: matplotlib stamps a gid at *draw* time and
        # the schema is built first, so reading it later finds `None` and the
        # layer ships announcing correctly and highlighting nothing.
        if self._collection is not None and self._collection.get_gid() is None:
            self._collection.set_gid(f"maidr-{uuid.uuid4()}")

    def render(self) -> dict:
        """
        The base schema, plus the row's name when the chart gives it one.

        ``MaidrLayer.name`` is what xability/maidr#828 added so two layers of
        a kind can be told apart, which is exactly the position a reader is in
        with three rows of ticks.
        """
        schema = super().render()
        if self._row_label:
            schema[MaidrKey.NAME] = self._row_label
        return schema

    def _extract_plot_data(self) -> list[dict]:
        """
        The row's events, as points on the axis they run along.

        ``get_orientation()`` decides which axis that is: ``"horizontal"``
        puts the events on x at a fixed y, and ``"vertical"`` the other way
        about. Both the coordinates and the layer's ``orientation`` follow it,
        because declaring one without the other is the defect
        xability/py-maidr#480 and xability/r-maidr#189 both had -- the payload
        is then read back the way it came in.

        Returns
        -------
        list of dict
            One point per event, in the order the row holds them.
        """
        if self._collection is None:
            return []

        drawn = events(self._collection)
        offset = float(self._collection.get_lineoffset())
        horizontal = self._collection.get_orientation() == "horizontal"

        # Kept so `_get_selector` can name each announced event's own element
        # rather than counting from one: a row holding a non-finite value has
        # more segments than points, and numbering the points would put every
        # highlight after the gap on its neighbour's tick (#429).
        self._marks = [index for index, _ in drawn]

        if horizontal:
            return [
                {MaidrKey.X: position, MaidrKey.Y: offset} for _, position in drawn
            ]
        return [{MaidrKey.X: offset, MaidrKey.Y: position} for _, position in drawn]

    def _extract_axes_data(self) -> dict:
        """
        Name the axes, and say which way the row runs.

        The chart's own labels are used where the caller set them; the axis
        the rows are stacked along is named "Row" rather than left blank,
        because a bare number there says nothing about what it counts.
        """
        axes_data = super()._extract_axes_data()

        if self._collection is None:
            return axes_data

        horizontal = self._collection.get_orientation() == "horizontal"
        stacked = MaidrKey.Y if horizontal else MaidrKey.X

        # Asked of the axes rather than of the payload the base built, which
        # fills "X" and "Y" as placeholders where the caller set nothing --
        # so a check on what came back would see them as labels and leave a
        # reader being told the rows are stacked along "Y".
        named = self.ax.get_ylabel() if horizontal else self.ax.get_xlabel()
        if not named:
            axes_data[stacked] = self._axis_config(label="Row")

        return axes_data

    def _get_selector(self) -> str | list[str]:
        """
        Address each event by the element matplotlib drew for it.

        Measured: a row's collection is written as one ``<g>`` carrying one
        ``<path>`` per event, in position order, so an event has an element of
        its own and a row names only its own events.

        ``nth-of-type`` rather than ``nth-child`` for the reason
        :class:`~maidr.core.plot.hexbinplot.HexbinPlot` gives, and because a
        ``<defs>`` or a clip path written into the group would shift every
        count by one.
        """
        gid = self._collection.get_gid() if self._collection is not None else None
        if gid is None:
            return []

        return [
            f"g[id='{gid}'] > path:nth-of-type({index + 1})"
            for index in getattr(self, "_marks", [])
        ]
