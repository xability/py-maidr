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


def reads(collection: EventCollection) -> bool:
    """
    Whether a row has anything to announce.

    An event plot drawn from an empty row -- ``ax.eventplot([[], times])`` --
    produces a collection with no positions. Registering it would put a layer
    with no points in the schema for a reader to walk into and find nothing,
    which is the phantom-layer shape of #421.

    Parameters
    ----------
    collection : EventCollection
        One row of the chart.

    Returns
    -------
    bool
        True when the row drew at least one event.
    """
    return len(np.asarray(collection.get_positions())) > 0


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

        positions = [
            float(position)
            for position in np.asarray(self._collection.get_positions()).ravel()
        ]
        offset = float(self._collection.get_lineoffset())
        horizontal = self._collection.get_orientation() == "horizontal"

        # A non-finite position is not drawn -- there is nowhere to put it --
        # so emitting one would leave the layer with more entries than the
        # selector resolves to elements, and every event after it would be
        # highlighted at its neighbour's tick (#429). It also keeps the
        # payload loadable: `json.dumps` writes `NaN` as a bare token, which
        # `JSON.parse` rejects (#427).
        drawn = [position for position in positions if math.isfinite(position)]
        self._drawn = len(drawn)

        if horizontal:
            return [
                {MaidrKey.X: position, MaidrKey.Y: offset} for position in drawn
            ]
        return [{MaidrKey.X: offset, MaidrKey.Y: position} for position in drawn]

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
            for index in range(getattr(self, "_drawn", 0))
        ]
