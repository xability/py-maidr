from __future__ import annotations

import uuid

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot

#: Key the patch hands this layer the ``LineCollection`` its own call drew
#: under. Named like ``eventplot.DRAWN_EVENTS`` and read the same way: the
#: layer is told which artist it reads rather than sweeping the axes for one,
#: which is the distinction #426 was about.
DRAWN_RUG = "_maidr_rug"

#: Key carrying the name to announce the layer under, when there is one.
RUG_LABEL = "_maidr_rug_label"

#: What the layer's constant axis is called when the chart does not say.
#: A rug's ticks sit in a strip against the frame rather than at a measured
#: height, so the coordinate across the tick names the strip, not a value.
RUG_AXIS_LABEL = "Rug"


def read_rug(collection) -> tuple[list, bool] | None:
    """
    The positions a rug marks, and which axis they lie along.

    A rug tick is a segment held constant on the axis carrying the data and
    stretched across the other, so the *constant* coordinate is the
    observation and the stretch is the tick's height. Measured on seaborn
    0.13.2::

        sns.rugplot(x=[10.251, ...])
        [[10.251, 0.0], [10.251, 0.025]]

    Parameters
    ----------
    collection : LineCollection or None
        The artist the call drew.

    Returns
    -------
    tuple of (list of float, bool) or None
        The positions in draw order, and True when they lie along x. ``None``
        when this is not a rug: a collection whose segments are not all held
        constant on exactly one axis marks no single set of positions, and
        the whole layer is declined rather than part of it read, so a chart
        is never announced as a subset of itself.
    """
    if not isinstance(collection, LineCollection):
        return None

    segments = collection.get_segments()
    if not segments:
        return None

    ends = []
    for segment in segments:
        pair = np.asarray(segment, dtype=float)
        if pair.shape != (2, 2) or not np.all(np.isfinite(pair)):
            return None
        ends.append(pair)

    level_x = all(pair[0][0] == pair[1][0] for pair in ends)
    level_y = all(pair[0][1] == pair[1][1] for pair in ends)

    # Exactly one, not "x first": a tick of zero height is constant on both
    # and marks nothing, and a sloped segment is constant on neither.
    if level_x == level_y:
        return None

    axis = 0 if level_x else 1
    return [float(pair[0][axis]) for pair in ends], level_x


class RugPlot(MaidrPlot):
    """
    A seaborn rug plot, read as the observations it marks.

    A rug draws one short tick per observation against the frame, showing
    where the raw data actually fell. Read as a **scatter**, for the reason
    :class:`~maidr.core.plot.eventplot.EventPlot` gives about an event plot's
    ticks: every tick is the same length -- ``height`` is one number for the
    whole call -- so the height is decoration and only the position is data.
    What the reader navigates is a series of positions, which is a scatter.

    Where it differs from an event plot is the coordinate across the tick.
    An event plot's rows sit at ``lineoffsets``, which is a real place on a
    real axis and worth announcing; a rug's ticks sit in a strip against the
    frame at a fraction of the axes height, which is not a measurement of
    anything. So that axis is named :data:`RUG_AXIS_LABEL` rather than left
    carrying the chart's own label -- a rug drawn over a ``kdeplot`` would
    otherwise announce every observation as "Density 0", which is a number
    the chart does not show.

    A rug is routinely drawn *beside* another layer, and it registers its own
    layer there rather than being declined as a duplicate. That is the
    opposite call to the one xability/maidr#1124 made for Vega-Lite text
    overlays, and for a reason: those labels sit **on** the marks they
    duplicate, whereas a rug occupies its own strip and, next to a density
    curve or a histogram, is the only thing in the figure stating where the
    observations actually are. It is named so a reader can tell the two
    apart, which is what xability/maidr#828 added ``name`` for.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        super().__init__(ax, PlotType.SCATTER)

        collection = kwargs.get(DRAWN_RUG, None)
        self._collection = (
            collection if isinstance(collection, LineCollection) else None
        )
        self._label = kwargs.get(RUG_LABEL, None)

        # Read once, here, rather than again per render. Two reasons, and
        # the first is correctness: `MaidrPlot.render()` builds the *axes*
        # payload before the data, so an orientation settled in
        # `_extract_plot_data` is still the default when
        # `_extract_axes_data` reads it -- measured, a `rugplot(y=...)` then
        # named the y axis "Rug" and left the observations it carries
        # labelled "X". The second is that `render()` can run more than once
        # for a layer, and the collection cannot change underneath it, so
        # revalidating every segment each time buys nothing.
        read = read_rug(self._collection)
        self._positions, self._along_x = read if read is not None else ([], True)

        # Assigned here rather than relied upon, for the reason `EventPlot`
        # and `HexbinPlot` give: matplotlib stamps a gid at *draw* time and
        # the schema is built first, so reading it later finds `None` and the
        # layer ships announcing correctly and highlighting nothing.
        if self._collection is not None and self._collection.get_gid() is None:
            self._collection.set_gid(f"maidr-{uuid.uuid4()}")

    def render(self) -> dict:
        """
        The base schema, plus the name the rug is announced under.

        ``MaidrLayer.name`` is what xability/maidr#828 added so two layers of
        a kind can be told apart, which is exactly where a reader stands with
        a rug drawn beside a scatter of the same variable.
        """
        schema = super().render()
        if self._label:
            schema[MaidrKey.NAME] = self._label
        return schema

    def _extract_plot_data(self) -> list[dict]:
        """
        The marked observations, as points on the axis they lie along.

        Returns
        -------
        list of dict
            One point per tick, in the order the collection holds them.
        """
        # The coordinate across the tick is the strip the rug occupies, not a
        # height the chart measured, so it is emitted as a constant rather
        # than as the tick's own base -- which is a fraction of the axes and
        # would read as data at whatever scale the other axis happens to use.
        if self._along_x:
            return [
                {MaidrKey.X: position, MaidrKey.Y: 0} for position in self._positions
            ]
        return [{MaidrKey.X: 0, MaidrKey.Y: position} for position in self._positions]

    def _extract_axes_data(self) -> dict:
        """
        Name the axes, calling the strip the ticks sit in what it is.

        The axis carrying the observations keeps the chart's own label. The
        one across the ticks is renamed even when the caller labelled it,
        unlike ``EventPlot``'s "Row" which only fills a blank: a rug over a
        ``kdeplot`` has a real "Density" label on that axis, and every point
        this layer emits sits at 0 rather than at any density.
        """
        axes_data = super()._extract_axes_data()
        across = MaidrKey.Y if self._along_x else MaidrKey.X
        axes_data[across] = self._axis_config(label=RUG_AXIS_LABEL)
        return axes_data

    def _get_selector(self) -> str | list[str]:
        """
        Address each tick by the element matplotlib drew for it.

        One ``<g>`` carrying one ``<path>`` per segment, in draw order, which
        is the order the points were emitted in -- so a tick has an element
        of its own and the two lists line up without numbering either.

        The empty case hands back ``[]`` rather than ``""`` to match
        :meth:`~maidr.core.plot.eventplot.EventPlot._get_selector`, the
        sibling this class is shaped after. Not reachable through the patch,
        which only registers a layer for a collection it has read.
        """
        if self._collection is None or self._collection.get_gid() is None:
            return []
        return f"g[id='{self._collection.get_gid()}'] > path"
