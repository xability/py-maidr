from __future__ import annotations

import wrapt

from matplotlib.axes import Axes
from matplotlib.patches import StepPatch

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import _draw_quietly


@wrapt.patch_function_wrapper(Axes, "stairs")
def stairs(wrapped, instance, args, kwargs) -> StepPatch:
    """
    Draw a patched ``Axes.stairs`` and register the histogram it produced.

    ``ax.step`` already reads as ``step`` and ``ax.hist`` as ``hist``, so a
    staircase drawn by the third spelling was the only one of the three that
    left the chart silent -- and it is the spelling matplotlib's own
    documentation reaches for once the binning has already happened.

    The patch's own artist is handed to the layer rather than looked up on the
    axes, for the reason ``maidr/patch/gantt.py`` gives: a second ``stairs``
    call leaves a second ``StepPatch`` beside the first, and "the patch on
    this axes" would describe the opening call twice.

    Parameters
    ----------
    wrapped : Callable
        ``Axes.stairs``.
    instance : Any
        The axes it was called on.
    args, kwargs : Any
        As passed by the caller.

    Returns
    -------
    StepPatch
        Whatever ``stairs`` returned, unchanged.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    with ContextManager.set_internal_context():
        plot = _draw_quietly(wrapped, args, kwargs)

    # `ax.stairs([], [0])` is legal and draws nothing. Registering it would
    # put an empty layer in the schema, which the core has to navigate into
    # and cannot read -- the phantom-layer shape of #421.
    if len(plot.get_data().values) == 0:
        return plot

    ax = FigureManager.get_axes(plot)
    FigureManager.create_maidr(ax, PlotType.HIST, step_patch=plot)

    return plot
