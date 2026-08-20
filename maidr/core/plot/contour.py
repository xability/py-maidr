"""ContourPlot — a scalar field read as the iso-value curves it is drawn as."""

from __future__ import annotations

import math
import uuid

import numpy as np
from matplotlib.axes import Axes
from matplotlib.contour import ContourSet
from matplotlib.path import Path

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot


class ContourPlot(MaidrPlot):
    """
    A contour plot: one curve per level of a scalar field.

    ``Axes.contour`` is the one chart in this family whose value is a **number
    rather than a colour**. ``QuadContourSet.levels`` holds the levels the
    caller asked for, and ``get_paths()`` returns one path per level, so both
    halves invert exactly and nothing has to be recovered from a fill. That is
    what separates it from the same chart elsewhere: xability/maidr#1084 left
    Observable Plot's ``contour`` unread because there the magnitude survives
    only in a continuous fill colour.

    Two things about the drawing shape the reading.

    **A level is not one curve.** A field with two peaks crosses a level twice,
    and matplotlib draws both islands in a *single* compound path with two
    ``MOVETO`` commands. Read as one series they would be joined by a straight
    line running between the peaks -- a curve announced across ground the field
    never took, which is the defect xability/maidr#1079 describes for a gappy
    line. So each drawn polyline becomes its own series, and several series may
    share a level. ``ContourPoint`` carries the level on every point precisely
    so that costs nothing.

    **A filled contour is not this chart.** ``contourf`` draws the *bands*
    between levels, so its outlines run along two different level curves
    stitched together and there is one fewer of them than there are levels --
    measured, three levels give two paths. Announcing such an outline as "the
    0.2 contour" would be right for half of its points. The patch declines it;
    see ``maidr/patch/contour.py``.

    Parameters
    ----------
    ax : Axes
        The axes the field was drawn on.
    contour_set : ContourSet
        The artist this call produced, handed over rather than searched for:
        two ``contour`` calls on one axes leave two sets, and "the contour set
        on this Axes" would read the first one twice.
    **kwargs : dict
        Ignored; accepted so the factory can forward what it was given.
    """

    def __init__(self, ax: Axes, contour_set: ContourSet, **kwargs) -> None:
        self._contour_set = contour_set
        #: The level index behind each emitted series, in emission order.
        #:
        #: This is what keeps the selectors aligned when one level draws
        #: several islands and so contributes more than one series. It is the
        #: index into ``get_paths()`` rather than a count of the series
        #: emitted, and that is load-bearing: a level nothing reaches emits no
        #: series but **does** reach the document, as a ``<path>`` with no
        #: ``d`` attribute, so the elements and the paths stay in step while
        #: the series do not.
        self._series_levels: list[int] = []
        super().__init__(ax, PlotType.CONTOUR)

    def _extract_plot_data(self) -> list[list[dict]]:
        """
        Read one series per drawn polyline off the contour set.

        Returns
        -------
        list of list of dict
            One series per polyline, each point carrying its level. Levels
            nothing reached contribute no series -- matplotlib still emits an
            empty path for them, and a series with no points is a row a reader
            can land on and be told nothing about.
        """
        levels = np.asarray(self._contour_set.levels, dtype=float)
        paths = self._contour_set.get_paths()

        self._series_levels = []
        data: list[list[dict]] = []
        for index, path in enumerate(paths):
            if index >= len(levels):
                break
            level = float(levels[index])
            if not math.isfinite(level):
                continue
            for polyline in _polylines(path):
                data.append(
                    [
                        {
                            MaidrKey.X.value: float(vertex[0]),
                            MaidrKey.Y.value: float(vertex[1]),
                            MaidrKey.LEVEL.value: level,
                        }
                        for vertex in polyline
                    ]
                )
                self._series_levels.append(index)

        return data

    def _get_selector(self) -> list[str]:
        """
        Return one selector per emitted series.

        matplotlib draws the whole set as one group holding a ``<path>`` per
        level, so a series is addressed by the level it belongs to. Two series
        of one level therefore name the same element: a reader on either island
        of the 0.5 contour sees the 0.5 contour outlined, which is the honest
        answer when the drawing gives the islands no elements of their own.

        Returns
        -------
        list of str
            One selector per series, in emission order.
        """
        gid = self._contour_set.get_gid()
        if gid is None:
            return []
        return [
            f"g[id='{gid}'] > path:nth-of-type({index + 1})"
            for index in self._series_levels
        ]


def _polylines(path: Path) -> list[np.ndarray]:
    """
    Split one compound path into the separate curves it draws.

    Parameters
    ----------
    path : Path
        One level's path, which may hold several disconnected curves.

    Returns
    -------
    list of ndarray
        One ``(n, 2)`` array per curve. Curves of fewer than two points are
        dropped: a single vertex is a place the field touched a level rather
        than a curve along it, and there is nothing to move along.

    Notes
    -----
    A closed curve is closed by repeating its own first point rather than by
    taking the vertex sitting in the ``CLOSEPOLY`` slot. matplotlib documents
    that vertex as *ignored*, so what it holds is not part of the contract --
    and measured on 3.9.4, a contour writes the subpath's start point there,
    which makes the two choices indistinguishable on this artist. That is
    exactly why the documented one is taken: an artist that ever put something
    else there would announce a corner at whatever happened to be in the slot,
    and nothing here would notice.
    """
    vertices = np.asarray(path.vertices, dtype=float)
    if len(vertices) == 0:
        return []

    codes = path.codes
    if codes is None:
        return [vertices] if len(vertices) > 1 else []

    curves: list[np.ndarray] = []
    current: list[np.ndarray] = []

    def flush() -> None:
        if len(current) > 1:
            curves.append(np.asarray(current, dtype=float))
        current.clear()

    for vertex, code in zip(vertices, codes):
        if code == Path.MOVETO:
            flush()
            current.append(vertex)
        elif code == Path.LINETO:
            current.append(vertex)
        elif code == Path.CLOSEPOLY:
            if current:
                current.append(current[0])
            flush()
    flush()

    return curves


def tag(contour_set: ContourSet) -> str:
    """
    Give a contour set a stable id, so its curves can be addressed.

    Assigned here rather than relied upon: matplotlib stamps a gid only at draw
    time, and the schema is built first. ``MultiLinePlot`` and ``AreaPlot`` do
    the same for the same reason.

    Parameters
    ----------
    contour_set : ContourSet
        The artist to tag.

    Returns
    -------
    str
        The gid it now carries.
    """
    gid = contour_set.get_gid()
    if gid is None:
        gid = f"maidr-{uuid.uuid4()}"
        contour_set.set_gid(gid)
    return gid
