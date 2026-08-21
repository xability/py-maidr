"""StepHistPlot -- the histogram ``Axes.hist(histtype="step")`` draws as an outline."""

from __future__ import annotations

from typing import Any

from matplotlib.axes import Axes

from maidr.core.plot.histogram import HistPlot
from maidr.core.plot.stairs import bins_to_points

#: Keys the patch passes a step histogram's own numbers under.
STEP_COUNTS = "_maidr_step_counts"
STEP_EDGES = "_maidr_step_edges"
#: And the orientation the caller asked for, which nothing else records.
STEP_ORIENTATION = "_maidr_step_orientation"


class StepHistPlot(HistPlot):
    """
    A histogram whose bars were drawn as one outline rather than as bars.

    ``histtype="step"`` and ``"stepfilled"`` draw a ``Polygon`` per dataset and
    leave ``ax.containers`` empty, so :class:`HistPlot` -- which reads a
    ``BarContainer`` -- had nothing to find. The layer was registered anyway
    and raised ``ExtractionError`` when it was rendered, taking the whole
    figure with it (#555)::

        ax.hist(np.array([1.0] * 10), bins=2, histtype="step")
        maidr.render(fig)
        ExtractionError: Error extracting data for hist plot type from <class 'NoneType'>.

    Nothing has to be recovered from the outline. ``Axes.hist`` returns
    ``(n, bins, patches)`` whatever the histtype, and the first two *are* the
    counts and the edges -- so the patch hands them over and this reads them,
    the same way :class:`~maidr.core.plot.stairs.StairsPlot` reads the pair a
    ``StepPatch`` carries. Both go through ``bins_to_points`` so the two
    spellings of one chart announce it identically.

    Highlighting is declined for the reason ``StairsPlot`` declines it: the
    outline is a single element covering every bin, so a selector naming it
    would outline the whole histogram at every bin and tell a low-vision
    reader nothing about which bin they are on. The reading still ships,
    because the chart was an error before -- there is no highlight being taken
    away, and ``histtype="bar"`` draws the same histogram with a patch per bin
    for anyone who needs both.

    Parameters
    ----------
    ax : Axes
        The axes the outline was drawn on.
    counts : Any
        One count per bin, as ``Axes.hist`` returned them.
    edges : Any
        One more edge than there are counts, in bin order.
    **kwargs : dict
        Ignored; accepted so the factory can forward what it was given.
    """

    def __init__(self, ax: Axes, counts: Any, edges: Any, **kwargs) -> None:
        self._counts = counts
        self._edges = edges
        # Which way the bins run, from the caller's own `orientation=`.
        #
        # There is nowhere else to get it. `HistPlot` reads it off the
        # `BarContainer` matplotlib annotates, and a step histtype makes no
        # container -- the `Polygon` it draws instead records nothing about
        # which axis the bins were laid along. Without this a horizontal step
        # histogram announced as vertical, with its counts read as positions.
        self._declared_orientation = (
            "horz" if kwargs.get(STEP_ORIENTATION) == "horizontal" else "vert"
        )
        super().__init__(ax)
        self._support_highlighting = False

    def _extract_plot_data(self) -> list[dict]:
        """
        Read one point per bin off the numbers the call returned.

        Returns
        -------
        list of dict
            One point per bin, in the order the bins were given.
        """
        self._orientation = self._declared_orientation
        return bins_to_points(self._orientation, self._counts, self._edges)
