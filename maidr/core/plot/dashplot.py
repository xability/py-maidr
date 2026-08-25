"""Read a ``so.Dash`` mark as the scatter of ticks it draws."""

from __future__ import annotations

import math
import uuid
from typing import List

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection

from maidr.core.plot.scatterplot import ScatterPlot
from maidr.exception import ExtractionError

#: The keyword the drawn collection is handed over under.
DRAWN_DASHES = "dashes"


class DashPlot(ScatterPlot):
    """
    One observation per tick, read off the tick's middle.

    ``so.Dash()`` is ``so.Dot()``'s flat sibling: instead of a marker it
    draws a short horizontal segment at each observation, so several
    observations at one category stack up as a row of rules rather than as a
    pile of overlapping circles. What it leaves behind is a
    ``LineCollection`` and nothing else, which is the whole of why it was
    silent -- ``ScatterPlot`` asks a ``PathCollection`` for its offsets, and
    a line collection has none.

    Measured on ``seaborn 0.13.2``, forty observations over five categories::

        so.Dash()               LineCollection, 40 segments
        first segment           [[-0.4, 3.696], [0.4, 3.696]]
        so.Dash(), so.Dodge()   [[-0.4, 3.696], [ 0.0, 3.696]]

    **The width is drawing and the middle is the datum.** A segment spans
    ``width`` either side of the position, ``0.8`` by default and halved
    again by a ``Dodge()``, and neither number is anything the chart
    measured. What both spellings agree on is the segment's *centre*, which
    is where the observation is -- so the reading takes the midpoint and
    discards the span, rather than announcing a bar of no meaning.

    That is also what makes the dodge case come out right. A dodged tick's
    midpoint is offset from its tick, which is the shape #617 describes for
    ``so.Bar``: read literally it announces ``-0.2`` where the axis says
    ``a``. Here it needs no special case, because
    :meth:`~maidr.core.plot.scatterplot.ScatterPlot._on_axis` already snaps a
    drawn coordinate to the slot it belongs to and
    :meth:`~maidr.core.plot.scatterplot.ScatterPlot._sample` names it -- the
    machinery a jittered strip plot needed (#439), reused unchanged.

    Read as a scatter rather than as a spike: a spike runs from a baseline to
    its value, and measured, these do not reach one. They are marks at a
    position, which is what a point is.

    Parameters
    ----------
    ax : Axes
        The panel drawn on.
    **kwargs : dict
        Carries the collection under :data:`DRAWN_DASHES`, and whatever the
        factory forwards.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        self._collection: LineCollection = kwargs.pop(DRAWN_DASHES)
        # Which of the collection's segments the payload announces, in payload
        # order. Filled by `_extract_plot_data` and read by `_get_selector`;
        # empty here so a layer asked for its selectors before its data
        # returns none rather than raising.
        self._drawn: List[int] = []
        super().__init__(ax, **kwargs)

    def _extract_plot_data(self) -> list[dict]:
        """
        One sample per tick, in the order the collection holds them.

        Returns
        -------
        list of dict
            One point per drawn tick.

        Raises
        ------
        ExtractionError
            When the collection holds no tick this can read.
        """
        segments = self._collection.get_segments()
        if not segments:
            raise ExtractionError(self.type, self.ax)

        # No `_elements.append` here. `ScatterPlot` keeps its collections so
        # that `maidr.core.maidr` can stamp a gid on them before the SVG is
        # written; this layer assigns its own in `_get_selector` and reads it
        # back off `self._collection`, so appending would put an artist in a
        # list nothing here consults. Verified against the real render rather
        # than reasoned about: with the line gone, the collection's `<g>` is
        # still in the emitted SVG carrying all forty paths.
        x_ticks = self._category_tick_labels(self.ax, "x")
        y_ticks = self._category_tick_labels(self.ax, "y")

        samples: list[dict] = []
        self._drawn = []
        for position, segment in enumerate(segments):
            middle = _middle(segment)
            if middle is None:
                continue
            samples.append(self._sample(middle[0], middle[1], x_ticks, y_ticks))
            self._drawn.append(position)

        if not samples:
            raise ExtractionError(self.type, self._collection)
        return samples

    def _get_selector(self) -> List[str]:
        """
        One selector per tick, addressing its own path inside the group.

        The inherited scatter selector cannot serve: it names ``<use>``
        elements, which is what a marker collection writes and what a line
        collection does not -- matplotlib draws these as one ``<path>`` per
        segment, the shape
        :class:`~maidr.core.plot.intervalplot.IntervalPlot` already addresses
        for ``so.Range``.

        Numbered against the **drawn** ticks rather than the announced ones,
        so a collection holding a segment this declines keeps every later
        tick pointing at its own path.

        Returns
        -------
        list of str
            One selector per announced tick, in payload order.
        """
        gid = self._collection.get_gid()
        if not gid or not str(gid).startswith("maidr-"):
            gid = f"maidr-{uuid.uuid4()}"
            self._collection.set_gid(gid)

        return [
            f"g[id='{gid}'] > path:nth-of-type({position + 1})"
            for position in self._drawn
        ]


def _middle(segment) -> tuple[float, float] | None:
    """
    Where a tick's observation is, or ``None`` where it has none.

    Parameters
    ----------
    segment : array_like
        One segment's vertices, as the collection holds them.

    Returns
    -------
    tuple of float, or None
        The observation, or None when the segment is not a readable tick.

    Notes
    -----
    A tick runs across the axis its category is on and sits at one value on
    the other, and **which axis that is depends on the chart**. Measured on
    ``seaborn 0.13.2``, the same forty observations drawn both ways::

        so.Plot(x="cat", y="v")   [[-0.4, 3.696], [ 0.4, 3.696]]
        so.Plot(y="cat", x="v")   [[3.696, -0.4], [3.696,  0.4]]

    So the constant coordinate is the datum and the spanned one is the mark's
    width. Reading only the first spelling is not a narrower reading, it is a
    broken one: every segment of the transposed chart fails the horizontal
    test, the layer finds nothing to announce, and the ``ExtractionError``
    that follows takes the **whole figure** to a static image.

    A segment constant on neither axis is not one of these marks and is
    declined rather than averaged into a position the chart never drew.

    The **shape** check is what keeps a non-finite tick out, and it is doing
    more work than it looks like. matplotlib strips a non-finite vertex
    before ``get_segments`` returns -- measured, ``[(2, nan), (2, 5)]`` comes
    back as ``[[2.0, 5.0]]``, a single point -- so such a tick arrives with
    the wrong shape rather than with a ``NaN`` in it. That matters because
    ``json.dumps`` writes ``NaN`` as a bare token, which is legal JavaScript
    and invalid JSON, and the core parses the payload with ``JSON.parse``:
    one of them stops the chart initialising at all (#427). An explicit
    ``isfinite`` test beside this one would be unreachable.
    """
    ends = np.asarray(segment, dtype=float)
    if ends.shape != (2, 2):
        return None
    if _same(ends[0, 1], ends[1, 1]):
        return float(ends[:, 0].mean()), float(ends[0, 1])
    if _same(ends[0, 0], ends[1, 0]):
        return float(ends[0, 0]), float(ends[:, 1].mean())
    return None


def _same(one: float, other: float) -> bool:
    """
    Whether two coordinates are the one value a tick sits at.

    Exact equality would do for every chart measured -- seaborn writes the
    same number into both ends -- but the tolerance costs nothing and keeps a
    tick that has been through a transform from being declined over the last
    bit of a float.

    Parameters
    ----------
    one, other : float
        The two ends' coordinates on one axis.

    Returns
    -------
    bool
        True when they are the same position.
    """
    return math.isclose(one, other, rel_tol=1e-12, abs_tol=1e-12)
