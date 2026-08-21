from __future__ import annotations

import wrapt
from matplotlib.axes import Axes
from matplotlib.collections import EventCollection

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.eventplot import DRAWN_EVENTS, EVENT_ROW_LABEL, reads
from maidr.patch.common import _draw_quietly


def _row_labels(
    ax: Axes, horizontal: bool, rows: list[EventCollection]
) -> list[str | None]:
    """
    The name each row has on the axis it is stacked along, where it has one.

    An event plot is routinely drawn against named rows -- one per neuron,
    per sensor, per subject -- and the names live on the ticks rather than in
    the collections. Read at registration, so a caller who labels the axis
    afterwards gets the numbers; that is how a *group name* is read too --
    ``scatterplot.hue_groups()`` captures one at patch time. The legend
    *title* is the opposite case and not the precedent here: ``_legend_title``
    is called from ``_extract_axes_data``, so it is asked live at render and
    a later retitle does show up.

    Each row is looked up by **its own offset** rather than by its place in
    the list, because the two are the same only at the default spacing.
    ``ax.eventplot(rows, lineoffsets=2)`` puts the second row at 2.0, so a
    lookup by index asks the axis about 1.0, finds nothing, and silently
    drops a name the caller set explicitly. Asked of the collection rather
    than recomputed from ``lineoffsets``, which is the artist's own answer
    and needs no assumption about how a scalar is broadcast.

    Parameters
    ----------
    ax : Axes
        The axes drawn on.
    horizontal : bool
        Whether the events run along x, which puts the rows on y.
    rows : list of EventCollection
        The rows the call drew.

    Returns
    -------
    list of (str or None)
        One name per row, or ``None`` where the axis has no name for it.
    """
    axis = ax.get_yaxis() if horizontal else ax.get_xaxis()
    names = {
        float(position): text.get_text()
        for position, text in zip(axis.get_ticklocs(), axis.get_ticklabels())
        if text.get_text()
    }
    return [
        _a_name(names.get(float(row.get_lineoffset())), row.get_lineoffset())
        for row in rows
    ]


def _a_name(text: str | None, offset: float) -> str | None:
    """
    The tick's text, unless it is only the row's own number.

    An unlabelled axis still has ticks, and their text is the offset -- so
    without this every row would be "named" `0.0`, `1.0`, `2.0`, which is the
    coordinate the payload already carries and worse than no name at all: a
    reader switching layers would hear a number they were about to be told
    anyway.

    Compared numerically rather than as a string, because matplotlib writes
    the same offset as `0`, `0.0` or `\u22120.5` depending on the formatter and
    the locale, and a string comparison would let two of those three through.

    Parameters
    ----------
    text : str or None
        Whatever the tick says, or None where there is no tick.
    offset : float
        Where the row sits on the axis it is stacked along.

    Returns
    -------
    str or None
        The name, or None when the tick only restates the number.
    """
    if not text:
        return None
    try:
        # `\u2212` is the minus sign matplotlib's default formatter writes,
        # which `float` does not accept.
        if float(text.replace("\u2212", "-")) == float(offset):
            return None
    except ValueError:
        return text
    return text


@wrapt.patch_function_wrapper(Axes, "eventplot")
def eventplot(wrapped, instance, args, kwargs) -> list[EventCollection]:
    """
    Draw a patched ``Axes.eventplot`` and register each row it produced.

    A raster plot puts a tick at every event time, one row per series -- a
    spike train, an arrival timeline, a log of occurrences. Each row is read
    as a scatter of its positions; see
    :class:`~maidr.core.plot.eventplot.EventPlot` for why a scatter rather
    than a spike, and why one layer per row.

    Parameters
    ----------
    wrapped : Callable
        ``Axes.eventplot``.
    instance : Any
        The axes it was called on.
    args, kwargs : Any
        As passed by the caller.

    Returns
    -------
    list of EventCollection
        Whatever ``eventplot`` returned, unchanged.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    with ContextManager.set_internal_context():
        drawn = _draw_quietly(wrapped, args, kwargs)

    rows = [row for row in drawn if isinstance(row, EventCollection)]
    if not rows:
        return drawn

    ax = FigureManager.get_axes(rows[0])
    kwargs.pop("ax", None)
    horizontal = rows[0].get_orientation() == "horizontal"
    labels = _row_labels(ax, horizontal, rows)

    # A row with no events is skipped rather than registered empty, so the
    # reader is not offered a layer to walk into and find nothing (#421). The
    # rows that did draw keep their own names, so skipping one does not
    # rename the rest -- which is why the label is looked up by the row's
    # own index rather than by its place among the registered layers.
    for index, row in enumerate(rows):
        if not reads(row):
            continue
        FigureManager.create_maidr(
            ax,
            PlotType.SCATTER,
            **dict(
                kwargs,
                **{DRAWN_EVENTS: row, EVENT_ROW_LABEL: labels[index]},
            ),
        )

    return drawn
