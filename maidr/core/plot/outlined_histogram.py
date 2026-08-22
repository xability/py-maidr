"""OutlinedHistPlot — the histogram seaborn draws as a bare line, unfilled."""

from __future__ import annotations

import numpy as np
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.plot.histogram import HistPlot

#: The keyword the histogram patch hands one unfilled outline over under.
#: Handed over rather than searched for, because a ``hue`` draws one line per
#: group and "the line on this Axes" would read the first group once per
#: layer -- the defect #527 fixed for containers.
OUTLINE_LINE = "_maidr_outline_line"

#: How far two bin widths may differ and still count as the same width.
#: Relative, for the reason :mod:`maidr.core.plot.stepped_histogram` gives:
#: the widths are data coordinates, and a histogram of nanoseconds and one of
#: light-years both have to pass.
_WIDTH_TOLERANCE = 1e-9


class OutlinedHistPlot(HistPlot):
    """
    A histogram drawn as a bare outline, with ``fill=False``.

    ``sns.histplot(element="step"|"poly", fill=False)`` draws the same
    distribution its filled twin does -- ``fill`` is a purely visual choice
    and changes no count -- but swaps the ``PolyCollection`` for a single
    ``Line2D``. :class:`~maidr.core.plot.stepped_histogram.SteppedHistPlot`
    looks for the collection, so the unfilled spelling registered nothing at
    all and the chart fell back to a picture (#583). That is the shape of
    #556, where four ``histtype`` s of ``ax.hist`` were read for two.

    The line is easier to read than the ring its filled twin draws, because
    it is the pre-binned histogram rather than a closed outline that has to be
    walked out and back. Measured on seaborn 0.13.2 across both elements and
    both orientations:

    ``step`` carries the **bin edges** and one value per edge, the last count
    repeated to close the staircase::

        histplot(x=..., bins=4)   drawstyle steps-post
            [(1, 3), (3, 3), (5, 0), (7, 2), (9, 2)]
        histplot(y=..., bins=4)   drawstyle steps-pre
            [(3, 1), (3, 3), (0, 5), (2, 7), (2, 9)]

    Both are edges ``1, 3, 5, 7, 9`` against counts ``3, 3, 0, 2`` with the
    last repeated -- seaborn transposes the pair and flips the drawstyle to
    draw the same staircase the other way up, and the *array* layout is the
    same either way. So the last value is dropped in both, and the drawstyle
    is read only to tell a step from a poly.

    ``poly`` carries the **bin centres** and one value each, with nothing
    repeated. The edges are recovered from the spacing, which is exact when
    the bins are even and impossible when they are not -- measured,
    ``bins=[0, 1, 5, 10]`` gives centres ``0.5, 3.0, 7.5``, and three numbers
    whose gaps are ``2.5`` and ``4.5`` do not say where the boundaries were.
    Such a chart is declined rather than announced with invented edges, which
    is the rule ``SteppedHistPlot`` already settled for the filled poly.

    A stepped outline needs no such recovery and is read exactly even when the
    bins are uneven, because it carries the edges themselves.

    Parameters
    ----------
    ax : Axes
        The axes the distribution was drawn on.
    line : Line2D
        The outline this call produced.
    **kwargs : dict
        Ignored; accepted so the factory can forward what it was given.
    """

    def __init__(self, ax: Axes, line: Line2D, **kwargs) -> None:
        self._line = line
        super().__init__(ax)
        # One `<path>` for the whole outline, as `SteppedHistPlot` and
        # `Axes.stairs` have: there is no per-bin element for a selector to
        # name, and one naming the line would light the whole distribution up
        # at every bin.
        self._support_highlighting = False

    def _extract_plot_data(self) -> list[dict]:
        """
        Read one point per bin off the outline.

        Returns
        -------
        list of dict
            One point per bin, in ascending bin order, or empty when the
            outline is not one this can read.
        """
        read = _read_line(self._line)
        if read is None:
            return []

        horizontal, bins = read
        self._orientation = "horz" if horizontal else "vert"
        return [
            self._bin_point(self._orientation, low, high - low, count)
            for low, high, count in bins
        ]


def reads(line: Line2D) -> bool:
    """
    Whether this outline is one that can be read as a histogram.

    Asked in the patch so a chart that cannot be read registers nothing at
    all, rather than a layer that refuses at extraction and takes the whole
    figure with it -- the defect #564 was about.

    Parameters
    ----------
    line : Line2D
        The outline seaborn drew.

    Returns
    -------
    bool
        True when the bins and counts can be recovered.
    """
    return _read_line(line) is not None


def _read_line(line: Line2D) -> tuple[bool, list[tuple[float, float, float]]] | None:
    """
    Recover the orientation and ``(low, high, count)`` of every bin.

    Parameters
    ----------
    line : Line2D
        The outline seaborn drew.

    Returns
    -------
    tuple or None
        ``(runs up the y axis, bins)``, or None when the outline cannot be
        read.
    """
    xydata = np.asarray(line.get_xydata(), dtype=float)
    if xydata.ndim != 2 or len(xydata) < 2 or not np.all(np.isfinite(xydata)):
        return None

    stepped = str(line.get_drawstyle()).startswith("steps")

    # Which column the bins run along, read off the drawing rather than the
    # caller's keywords: `histplot(y=...)`, `histplot(data=df, y="v")` and a
    # `displot` panel are three spellings of one chart and only the drawing is
    # the same in all three. The bins are the column that ascends.
    for horizontal, positions, values in (
        (False, xydata[:, 0], xydata[:, 1]),
        (True, xydata[:, 1], xydata[:, 0]),
    ):
        if not np.all(np.diff(positions) > 0):
            continue
        bins = _bins_from(positions, values, stepped)
        if bins is not None:
            return horizontal, bins

    return None


def _bins_from(
    positions: np.ndarray, values: np.ndarray, stepped: bool
) -> list[tuple[float, float, float]] | None:
    """
    Turn one outline's positions and values into bins.

    Parameters
    ----------
    positions : numpy.ndarray
        The ascending coordinates the bins run along -- edges for a stepped
        outline, centres for a poly one.
    values : numpy.ndarray
        The counts, with the last repeated for a stepped outline.
    stepped : bool
        Whether the outline was drawn with a step drawstyle.

    Returns
    -------
    list of tuple, or None
        The bins in ascending order, or None when they cannot be recovered.
    """
    if stepped:
        if len(positions) < 2:
            return None
        return [
            (float(positions[i]), float(positions[i + 1]), float(values[i]))
            for i in range(len(positions) - 1)
        ]

    if len(positions) < 2:
        return None
    widths = np.diff(positions)
    if not np.all(np.abs(widths - widths[0]) <= abs(widths[0]) * _WIDTH_TOLERANCE):
        return None

    half = widths[0] / 2.0
    return [
        (float(centre - half), float(centre + half), float(value))
        for centre, value in zip(positions, values)
    ]
