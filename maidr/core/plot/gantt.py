from __future__ import annotations

import uuid

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import Collection
from matplotlib.ticker import FixedLocator

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError


class GanttPlot(MaidrPlot):
    """
    A schedule of intervals in lanes, as ``Axes.broken_barh`` draws it.

    ``broken_barh(xranges, yrange)`` is matplotlib's gantt chart, and it is
    shaped like one already: **one call is one lane**. The `yrange` says where
    that lane sits and each `(start, width)` in `xranges` is an interval in it,
    so the trace's `{lane, start, end}` is what the caller wrote rather than
    something inferred from a drawing.

    The numbers come off the artist exactly. A `PolyCollection` holds one path
    per interval and each path's vertices are the corners, so a bar written
    `(1, 3)` reads back as 1 to 4 with nothing to invert and nothing to round.

    Naming the lane
    ---------------
    The `yrange` is a position, not a name, and the chart the matplotlib
    documentation shows names its lanes afterwards::

        ax.broken_barh([(110, 30), (150, 10)], (10, 9))
        ax.broken_barh([(10, 50), (100, 20)], (20, 9))
        ax.set_yticks([15, 25], labels=["Bill", "Jim"])

    Two things make that readable. Extraction runs when the schema is first
    asked for rather than when the call was patched, so ticks set *after* the
    bars are in place by then. And the tick that names a lane is the one
    **inside** it: measured, the example above puts its ticks at 15 and 25
    while the bars span 10-19 and 20-29, so their centres are 14.5 and 24.5
    and an exact match finds nothing.

    Only a ``FixedLocator`` counts, which is what tells a name from an axis.
    ``set_yticks`` installs one; left alone, matplotlib uses an ``AutoLocator``
    and puts several ticks inside every bar -- measured, an unlabelled chart
    offers "8", "10", "12", "14" and "16" for a lane spanning 10 to 19, none of
    which is that lane's name. A lane with no single tick of its own is named
    by its position, which is always true and never a guess.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        self._collections: list[Collection] = list(kwargs.pop("collections", ()) or ())
        super().__init__(ax, PlotType.GANTT)

    def add_lane(self, collection: Collection) -> None:
        """
        Take another ``broken_barh`` call on the same axes as another lane.

        A gantt chart is drawn one call per lane, so a two-lane schedule is
        two calls. Registering each as its own layer would give a reader two
        one-lane charts to switch between rather than one chart to move up and
        down inside, which is the whole of what the trace is for -- `points`
        is nested by lane precisely so one layer holds them all.

        The schema is dropped rather than amended, because it is built lazily
        on first access and a lane arriving after it was built would otherwise
        never appear.

        Parameters
        ----------
        collection : Collection
            The `PolyCollection` the new call drew.
        """
        self._collections.append(collection)
        self._schema = {}

    def _extract_plot_data(self) -> dict:
        """
        Read each collection as one lane of intervals.

        Returns
        -------
        dict
            ``{"points": [[{"x", "start", "end"}, ...], ...], "lanes": [...]}``
            -- the intervals nested by lane, and what each lane is called.

        Raises
        ------
        ExtractionError
            When the call left no readable interval.
        """
        if not self._collections:
            raise ExtractionError(self.type, self.ax)

        points: list[list[dict]] = []
        lanes: list[str | float] = []
        for collection in self._collections:
            spans = [self._corners(path) for path in collection.get_paths()]
            spans = [span for span in spans if span is not None]
            if not spans:
                continue

            # Every interval in one call shares that call's `yrange`, so the
            # lane is asked once, of the first.
            lane = self._lane_name(spans[0][2], spans[0][3])
            lanes.append(lane)
            points.append(
                [
                    {
                        MaidrKey.X: lane,
                        MaidrKey.START: start,
                        MaidrKey.END: end,
                    }
                    for start, end, _, _ in spans
                ]
            )

            # Assigned here rather than relied upon: a gid is otherwise only
            # stamped at draw time and the schema is built first, which is
            # what `HexbinPlot` and `AreaPlot` do for the same reason.
            if collection.get_gid() is None:
                collection.set_gid(f"maidr-{uuid.uuid4()}")

        if not points:
            raise ExtractionError(self.type, self.ax)

        self._elements.clear()
        self._elements.extend(self._collections)

        return {MaidrKey.POINTS: points, MaidrKey.LANES: lanes}

    @staticmethod
    def _corners(path) -> tuple[float, float, float, float] | None:
        """
        The x span and y span of one drawn interval.

        Parameters
        ----------
        path : Path
            One interval's polygon.

        Returns
        -------
        tuple or None
            ``(start, end, y_low, y_high)``, or None when the path holds no
            finite vertex.
        """
        vertices = np.asarray(path.vertices, dtype=float)
        finite = vertices[np.isfinite(vertices).all(axis=1)]
        if finite.shape[0] == 0:
            return None
        return (
            float(finite[:, 0].min()),
            float(finite[:, 0].max()),
            float(finite[:, 1].min()),
            float(finite[:, 1].max()),
        )

    def _lane_name(self, low: float, high: float, axis=None) -> str | float:
        """
        What to call the lane a bar spanning ``low`` to ``high`` sits in.

        Parameters
        ----------
        low, high : float
            The bar's extent along the lane axis.
        axis : Axis, optional
            The axis the lanes are laid out on. The y axis by default, which
            is where ``broken_barh`` puts them; ``SpanPlot`` passes the x axis
            for a set of vertical spans, whose lanes run the other way.

        Returns
        -------
        str or float
            The tick label naming it, or its centre when no single tick does.
        """
        axis = self.ax.get_yaxis() if axis is None else axis
        centre = (low + high) / 2
        if not isinstance(axis.get_major_locator(), FixedLocator):
            # An axis matplotlib chose the ticks for. Several land inside a
            # bar and none of them is its name.
            return centre

        inside = [
            text.get_text()
            for position, text in zip(axis.get_ticklocs(), axis.get_ticklabels())
            if low <= position <= high and text.get_text()
        ]
        # Exactly one, or the label is a guess between candidates rather than
        # a name the author gave this lane.
        return inside[0] if len(inside) == 1 else centre

    def _get_selector(self) -> list[str]:
        """
        Return one selector per lane, addressing that lane's whole collection.

        Returns
        -------
        list of str
            One selector per lane, in the order the lanes are announced.
        """
        return [
            f"g[id='{collection.get_gid()}'] > path"
            for collection in self._collections
            if collection.get_gid() is not None
        ]
