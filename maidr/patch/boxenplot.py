from __future__ import annotations

from matplotlib.axes import Axes

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import _draw_quietly, wrap_seaborn


def boxen(wrapped, instance, args, kwargs) -> Axes:
    """
    Register ``seaborn.boxenplot`` as one letter-value layer per axes.

    The internal context is what makes this a fix rather than an addition.
    A boxen plot is not drawn by a renderer of its own: seaborn builds each
    ladder from patches, draws the median with ``Axes.plot`` and the fliers
    with ``Axes.scatter``, both of which MAIDR already patches. Left alone,
    those two produce the reading :class:`~maidr.core.plot.boxenplot.BoxenPlot`
    exists to replace -- a line layer of medians, each announced as a
    two-sample series, and a scatter layer per category holding only the
    outliers, positioned at numeric slots rather than at the category labels.
    Suppressing them here is therefore not tidying: it removes a chart that
    claimed to be complete and was describing the scaffolding (#253).

    Parameters
    ----------
    wrapped : Callable
        ``seaborn.boxenplot``.
    instance : Any
        Unused; seaborn's plotting functions are module level.
    args, kwargs
        The caller's arguments, passed through untouched.

    Returns
    -------
    Axes
        Whatever seaborn returned.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    with ContextManager.set_internal_context():
        plot = _draw_quietly(wrapped, args, kwargs)

    ax = FigureManager.get_axes(plot)
    if ax is not None:
        FigureManager.create_maidr(ax, PlotType.BOXEN)

    return plot


wrap_seaborn("boxenplot", boxen)
