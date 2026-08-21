"""StairsPlot — the pre-binned histogram ``Axes.stairs`` draws as a staircase."""

from __future__ import annotations

import math
from typing import Any

from matplotlib.axes import Axes
from matplotlib.patches import StepPatch

from maidr.core.plot.histogram import HistPlot


class StairsPlot(HistPlot):
    """
    A histogram whose bars were drawn as one continuous outline.

    ``Axes.stairs`` is how modern matplotlib draws a histogram that was binned
    somewhere else -- ``np.histogram`` first, ``ax.stairs(counts, edges)``
    after -- and the artist keeps both halves of it exactly::

        ax.stairs([1, 3, 2], [0, 1, 2, 3]).get_data()
        # StairData(values=array([1, 3, 2]), edges=array([0, 1, 2, 3]), ...)

    Counts and bin edges, unrounded, straight off the artist. So this reads
    the same layer :class:`HistPlot` does, from a different place: there is no
    ``BarContainer`` on the axes to find, because a staircase is a single
    :class:`~matplotlib.patches.StepPatch` rather than one patch per bin.

    That single patch is also what it costs. It renders as **one** ``<path>``
    covering every bin, where ``ax.hist`` renders one per bar, so there is no
    per-bin element for a selector to name and the chart announces every bin
    while highlighting none of them. A selector matching the one path would be
    worse than none: it would outline the whole staircase identically at every
    bin, telling a low-vision reader nothing about which bin they are on. The
    reading ships anyway because it is a strict gain -- the chart was silent
    before, so no highlight is being taken away -- and ``ax.hist`` draws the
    same histogram with a patch per bin for anyone who needs both.

    Parameters
    ----------
    ax : Axes
        The axes the staircase was drawn on.
    step_patch : StepPatch
        The artist this call produced. Handed over rather than searched for:
        two ``stairs`` calls on one axes leave two patches, and "the patch on
        this axes" would read the first one twice.
    **kwargs : dict
        Ignored; accepted so the factory can forward what it was given.
    """

    def __init__(self, ax: Axes, step_patch: StepPatch, **kwargs) -> None:
        self._step_patch = step_patch
        super().__init__(ax)
        self._support_highlighting = False

    def _extract_plot_data(self) -> list[dict]:
        """
        Read one point per bin off the artist.

        Returns
        -------
        list of dict
            One point per bin, in the order the bins were given.
        """
        values, edges, _ = self._step_patch.get_data()
        self._orientation = (
            "horz" if self._step_patch.orientation == "horizontal" else "vert"
        )

        return bins_to_points(self._orientation, values, edges)


def bins_to_points(orientation: str, values: Any, edges: Any) -> list[dict]:
    """
    One point per bin, from a pair of counts and edges.

    Shared by every spelling of a pre-binned histogram that hands its numbers
    over rather than leaving a ``BarContainer`` to find: ``Axes.stairs``, which
    keeps them on its ``StepPatch``, and ``Axes.hist(histtype="step")``, whose
    counts and edges are the first two things it returns (#555). Both draw the
    same chart as one outline, and reading them through one function is what
    keeps them announcing it identically.

    Parameters
    ----------
    orientation : str
        ``"horz"`` when the bins run up the y axis, ``"vert"`` otherwise.
    values : Any
        One count per bin.
    edges : Any
        One more edge than there are counts, in bin order.

    Returns
    -------
    list of dict
        One point per bin, in the order the bins were given.
    """
    data = []
    for index, value in enumerate(values):
        low = float(edges[index])
        high = float(edges[index + 1])
        # A bin with no position is nowhere to navigate to, and a bare
        # `NaN` or `Infinity` in the payload is not JSON -- `JSON.parse`
        # rejects the whole schema and the chart never initialises (#427).
        if not (math.isfinite(low) and math.isfinite(high)):
            continue
        data.append(
            HistPlot._bin_point(orientation, low, high - low, _reading(value))
        )

    return data


def _reading(value: Any) -> float | None:
    """
    One bin's count, or ``None`` when it has none.

    ``NaN`` is how a ``stairs`` chart leaves a bin blank -- matplotlib draws a
    gap there -- and unlike the edges that is a bin with a position and no
    value, which the payload can say. ``None`` serialises to ``null``, which
    the core's bar family reads as a gap: kept out of the range, sounded as
    the empty tone, announced as missing. A zero would claim the bin was
    measured and found empty, which is a different statement.

    Parameters
    ----------
    value : Any
        The count matplotlib recorded, in whatever numpy type it arrived as.

    Returns
    -------
    float or None
        The count as a plain ``float``, or ``None`` when it is not finite.

    Notes
    -----
    The ``float()`` is not decoration: ``json.dumps`` cannot serialise a
    ``numpy.int64``, and ``ax.stairs([1, 3, 2], ...)`` hands back exactly
    that.
    """
    raw = float(value)
    return raw if math.isfinite(raw) else None
