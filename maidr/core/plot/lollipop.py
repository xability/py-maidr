from __future__ import annotations

import math
import uuid

from matplotlib.axes import Axes
from matplotlib.container import StemContainer

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot

#: The keyword the stem patch hands its container to this layer under.
#: Handed over rather than swept for, because the chart leaves two `Line2D`
#: artists on the axes and only the container says which is which (#527).
DRAWN_STEM = "_maidr_stem"


def marks(container: StemContainer) -> list[tuple[int, float, float]]:
    """
    The marks a stem plot drew, each with the element that carries it.

    ``StemContainer`` holds three artists and only one of them is data. The
    ``markerline`` carries a mark per value; the ``stemlines`` join each mark
    to the baseline, and the ``baseline`` is a single segment from the first
    position to the last. The stems and the baseline are how the chart is
    *drawn* -- neither carries a number the markers do not already carry, and
    the baseline's own value is the bottom of the frame rather than an
    observation. So the marks are the whole reading.

    The coordinates come back as matplotlib drew them, not reinterpreted into
    position and magnitude. That is the bar family's contract, measured
    rather than assumed: ``ax.barh(["a"], [4])`` emits ``{x: 4.0, y: "a"}``
    under ``orientation: "horz"``, so a horizontal chart puts the *magnitude*
    in ``x``. A horizontal stem's ``markerline`` already holds exactly that,
    and swapping the pair here would undo it.

    Non-finite values are dropped, and that is why the element index is
    returned rather than assumed. Measured: ``ax.stem([1,2,3,4], [4, nan, 2,
    7])`` leaves four points in ``get_xydata()`` and writes **three**
    ``<use>`` elements -- matplotlib skips a mark it cannot place. Numbering
    the announced marks from their place in the data would then put every
    highlight after the gap on its neighbour's mark, which is #429.

    Parameters
    ----------
    container : StemContainer
        What ``Axes.stem`` returned.

    Returns
    -------
    list of (int, float, float)
        For every drawable mark: its index among the drawn elements, and its
        two coordinates as drawn.
    """
    xydata = container.markerline.get_xydata()
    if xydata is None or not len(xydata):  # type: ignore[arg-type]
        return []

    drawn = []
    for point in xydata:
        x, y = float(point[0]), float(point[1])
        if not math.isfinite(x) or not math.isfinite(y):
            continue
        drawn.append((len(drawn), x, y))

    return drawn


def is_horizontal(container: StemContainer) -> bool:
    """
    Whether the stems stand along x rather than up from the axis.

    ``Axes.stem(..., orientation="horizontal")`` is not recorded anywhere on
    the container, so it is read back off the baseline: a vertical chart's
    baseline runs across the positions at one value, and a horizontal one's
    runs down them. Its two ends are compared rather than its slope, because
    a one-mark chart draws a baseline of zero length and the comparison then
    has to fall somewhere -- vertical, matching the default the caller did
    not override.

    Parameters
    ----------
    container : StemContainer
        What ``Axes.stem`` returned.

    Returns
    -------
    bool
        True when the values run along x.
    """
    ends = container.baseline.get_xydata()
    if ends is None or len(ends) < 2:  # type: ignore[arg-type]
        return False

    first, last = ends[0], ends[-1]
    return float(first[0]) == float(last[0]) and float(first[1]) != float(last[1])


class LollipopPlot(MaidrPlot):
    """
    A stem plot, read as the lollipop chart it draws.

    ``Axes.stem`` marks one value per position and joins each mark to a
    baseline. The core has a trace for that shape: ``lollipop``, which
    ``factory.ts`` constructs as a ``BarTrace`` outright -- a category and a
    magnitude -- on the grounds that a dot plot, a bar chart and a lollipop
    differ in what is drawn at the position rather than in how the chart is
    read.

    Not a line, which is what it used to be read as (#574). ``markerline``'s
    line style is ``"None"``: matplotlib draws no segment between the marks,
    because a stem plot is not claiming its positions are joined. Announcing
    it as a line asserts a continuity the chart declines to draw, and it
    brought the baseline in as a second series -- a flat two-point "line" at
    zero, which is a decoration of the drawing rather than an observation.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        super().__init__(ax, PlotType.LOLLIPOP)

        container = kwargs.get(DRAWN_STEM, None)
        self._container = container if isinstance(container, StemContainer) else None

        # Resolved here rather than at extraction because `render()` builds
        # the axes payload *before* the data payload, so `_extract_axes_data`
        # would otherwise be asked which way the chart runs before anything
        # had looked -- the defect #571's rug plot shipped with.
        self._horizontal = (
            is_horizontal(self._container) if self._container is not None else False
        )

        # The element indices `_get_selector` addresses, filled by extraction.
        self._drawn: list[int] = []

        # Stamped here rather than read later: matplotlib assigns a gid at
        # *draw* time and the schema is built first, so a layer that waited
        # would announce correctly and highlight nothing.
        if self._container is not None and self._container.markerline.get_gid() is None:
            self._container.markerline.set_gid(f"maidr-{uuid.uuid4()}")

    def _extract_plot_data(self) -> list[dict]:
        """
        One entry per mark, at the coordinates the chart drew it at.

        Which of the two is the magnitude is said by ``orientation`` rather
        than by the field a number sits in -- see :func:`marks` for the
        measurement the bar family's convention rests on.

        Returns
        -------
        list of dict
            The marks, in the order the chart holds them.
        """
        if self._container is None:
            return []

        drawn = marks(self._container)
        self._drawn = [index for index, _, _ in drawn]

        return [{MaidrKey.X: x, MaidrKey.Y: y} for _, x, y in drawn]

    def render(self) -> dict:
        """
        The base schema, plus which way the stems stand.

        ``orientation`` is a sibling of ``type`` rather than an entry in
        ``axes``, which holds only ``x``/``y``/``z``. Declaring the
        orientation without swapping the payload is the whole contract for
        the bar family; declaring one without the other in either direction
        is the defect #480 and r-maidr#189 both had.
        """
        schema = super().render()
        schema[MaidrKey.ORIENTATION] = "horz" if self._horizontal else "vert"
        return schema

    def _get_selector(self) -> str | list[str]:
        """
        Address each mark by the element matplotlib drew for it.

        Measured: a marker-only ``Line2D`` is written as one ``<g>`` carrying
        the marker's shape in a ``<defs>`` and one ``<use>`` per drawn mark.
        A descendant combinator rather than a child one, because matplotlib
        nests the marks inside a clip-path ``<g>`` of its own.

        ``nth-of-type`` rather than ``nth-child`` for the reason
        :class:`~maidr.core.plot.hexbinplot.HexbinPlot` gives: the ``<defs>``
        ahead of the marks would shift every count by one.
        """
        gid = (
            self._container.markerline.get_gid() if self._container is not None else None
        )
        if gid is None:
            return []

        return [
            f"g[id='{gid}'] use:nth-of-type({index + 1})" for index in self._drawn
        ]
