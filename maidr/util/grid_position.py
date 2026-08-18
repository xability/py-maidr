"""Where a panel sits in the grid a reader navigates.

A panel is keyed by where its gridspec span starts, so anything that
changes which gridspec an axes belongs to changes its coordinates. Adding
a colorbar does exactly that, which is why this is worth one function
rather than a call inlined in two places that could drift apart.
"""

from __future__ import annotations

from typing import Any

from matplotlib.axes import Axes


def topmost_subplotspec(ax: Axes) -> Any:
    """Return the outermost subplotspec of an axes, or None if it has none.

    Attaching a colorbar re-parents its panel into a fresh sub-gridspec
    where the panel sits at the origin. Two ``sns.heatmap`` calls into a
    ``subplots(1, 2)`` therefore both report ``(0, 0)`` for their own spec,
    and were emitted as a single position holding two ``heat`` layers
    rather than as two panels (#518).

    ``get_topmost_subplotspec`` walks up through the nesting to the
    gridspec the figure was laid out with, where the two are still the
    ``(0, 0)`` and ``(0, 1)`` their author wrote.

    Parameters
    ----------
    ax : Axes
        The axes whose position is being resolved.

    Returns
    -------
    SubplotSpec or None
        The outermost spec, or None for an axes with no subplotspec at all
        (one added by ``fig.add_axes``, say).
    """
    ss = ax.get_subplotspec()
    return None if ss is None else ss.get_topmost_subplotspec()
