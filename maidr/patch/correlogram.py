from __future__ import annotations

import wrapt
from matplotlib.axes import Axes

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.lollipop import DRAWN_MARKS, MARK_ARTIST, finite
from maidr.patch.common import _draw_quietly


def _register(instance: Axes, drawn: tuple) -> None:
    """
    Register the correlogram a patched call drew, where it drew one.

    ``Axes.acorr`` and ``Axes.xcorr`` return ``(lags, correlations, artist,
    extra)`` whichever way they were drawn, so the numbers come from the
    return value rather than back out of the artists. That matters for the
    default spelling: with ``usevlines=True`` the values live in the
    *lengths* of a ``LineCollection``'s segments, and nothing sits at the
    correlation for a reader to find.

    Parameters
    ----------
    instance : Axes
        The axes drawn on.
    drawn : tuple
        Whatever the wrapped call returned.
    """
    lags, correlations, artist = drawn[0], drawn[1], drawn[2]

    # Nothing drawable is not registered, rather than registered empty: a
    # layer a reader can walk into and find no points is #421's shape.
    if not finite((lags, correlations)):
        return

    ax = FigureManager.get_axes(artist)
    if ax is None:
        ax = instance

    FigureManager.create_maidr(
        ax,
        PlotType.LOLLIPOP,
        **{DRAWN_MARKS: (lags, correlations), MARK_ARTIST: artist},
    )


@wrapt.patch_function_wrapper(Axes, "acorr")
def acorr(wrapped, instance, args, kwargs) -> tuple:
    """
    Draw a patched ``Axes.acorr`` and register the correlogram it produced.

    A correlogram is one correlation per lag, marked at its value -- the
    lollipop shape #574 gave ``Axes.stem``, reached through two different
    sets of artists depending on one keyword, and read wrongly both ways
    before this (#577).

    With the default ``usevlines=True`` the chart is a ``LineCollection`` of
    stems from zero plus a horizontal reference line, and **neither** was
    read: the stems share an end, so the span reading refuses them by the
    rule xability/maidr#1100 settled, and the reference line is declined for
    the reason #176 gives. Both declines are right on their own, and together
    they left twenty-one real measurements announced nowhere. The stems were
    declined on the grounds that "the markers at their tips already carry
    that" -- and in this spelling there are no markers.

    With ``usevlines=False`` the values arrive as a marker-only ``Line2D``
    and were announced as a line, asserting a continuity between lags that
    the chart does not draw.

    Both are now the same one layer. The internal context is what makes that
    a replacement rather than an addition: `vlines`, `axhline` and `plot` are
    all patched, and this call reaches the reader through whichever of them
    it used.

    Parameters
    ----------
    wrapped : Callable
        ``Axes.acorr``.
    instance : Any
        The axes it was called on.
    args, kwargs : Any
        As passed by the caller.

    Returns
    -------
    tuple
        Whatever ``acorr`` returned, unchanged.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    with ContextManager.set_internal_context():
        drawn = _draw_quietly(wrapped, args, kwargs)

    _register(instance, drawn)
    return drawn


@wrapt.patch_function_wrapper(Axes, "xcorr")
def xcorr(wrapped, instance, args, kwargs) -> tuple:
    """
    Draw a patched ``Axes.xcorr`` and register the correlogram it produced.

    The same chart as :func:`acorr` against two series rather than one --
    ``Axes.acorr`` is literally ``xcorr(x, x)`` -- so it is read the same
    way. Patched separately rather than relying on one delegating to the
    other, because `acorr` calls `xcorr` internally and the internal context
    would then swallow the registration.

    Parameters
    ----------
    wrapped : Callable
        ``Axes.xcorr``.
    instance : Any
        The axes it was called on.
    args, kwargs : Any
        As passed by the caller.

    Returns
    -------
    tuple
        Whatever ``xcorr`` returned, unchanged.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    with ContextManager.set_internal_context():
        drawn = _draw_quietly(wrapped, args, kwargs)

    _register(instance, drawn)
    return drawn
