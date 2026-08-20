"""One lock per matplotlib ``Figure``, shared by every threaded entry point.

Not process-wide: ``savefig`` on distinct figures is safe in parallel, and
a single lock would serialise unrelated sessions and throw away most of
what threading buys.

Why a lock is needed at all: ``savefig`` mutates the figure it is writing,
for the duration of the write. Two things, both measured by watching the
attribute from another thread while renders ran:

* ``fig.dpi`` goes 100 -> 72 -> 100, so two concurrent writes race on that
  one attribute and the loser renders its whole chart at the other's dpi.
  A 640x480 chart came out 460.8x345.6 -- exactly the 100/72 ratio -- as a
  valid SVG, raising nothing, on 1 of 6 concurrent renders (#454).
* ``fig.canvas`` is swapped to a canvas that supports the output format and
  swapped back (``FigureCanvasAgg`` -> ``FigureCanvasSVG`` ->
  ``FigureCanvasAgg``), by
  ``FigureCanvasBase._switch_canvas_and_return_print_method``.

That second one also answers a question this raises: a render may run on a
worker thread, and GUI backends generally want canvas work on the main
thread. It does not reach the GUI canvas -- the write goes through the
format's own canvas, which for SVG is pure Python and has no thread
affinity. maidr's own backend delegates to ``FigureCanvasAgg`` besides,
and is what ``import maidr`` activates.

The registry lives here rather than in one integration because more than
one door renders on threads. Shiny renders off the event loop through
``asyncio.to_thread``; Streamlit runs every session's script in its own
ScriptRunner thread. Two doors with two registries would let a Shiny
render and a Streamlit render of the *same* figure overlap, which is the
case the lock exists to prevent -- so there is one registry, keyed by
figure, for the process.
"""

from __future__ import annotations

import logging
import threading
import weakref
from typing import Any

_logger = logging.getLogger(__name__)

#: The locks themselves, keyed weakly so a closed figure's lock goes with
#: it. The lock does not reference the figure, so this adds no retention
#: (#498).
#:
#: ``threading.Lock``, not ``RLock``: nothing re-enters a render of the
#: same figure on the same thread today, and if something ever does, a
#: deadlock is a better outcome than two interleaved writes to one figure,
#: because it is the one that shows up.
_FIGURE_LOCKS: weakref.WeakKeyDictionary[Any, threading.Lock] = (
    weakref.WeakKeyDictionary()
)

#: Guards creation of the per-figure locks above, which is itself a
#: check-then-act on a shared mapping.
_FIGURE_LOCKS_GUARD = threading.Lock()


def figure_lock(figure: Any) -> threading.Lock:
    """Return the lock for ``figure``, creating it on first use.

    Parameters
    ----------
    figure : Any
        The ``matplotlib`` figure about to be rendered, or ``None`` when it
        could not be resolved.

    Returns
    -------
    threading.Lock
        A lock unique to that figure. An unresolvable figure gets a fresh
        lock rather than a shared one -- serialising things we cannot tell
        apart would be a guess in the direction of a deadlock, and the
        render is safe on its own.

        Note what that means: an unresolvable value gets **no**
        synchronisation at all. Correct today because the values that land
        here -- plotly, altair -- are rendered without touching a
        ``matplotlib`` figure's ``dpi`` or ``canvas``, so there is no
        shared state to race on. A future plot type that resolves to
        ``None`` here *and* mutates shared figure state would be
        unprotected silently, which is the reason to say so rather than
        leave it to be inferred.
    """
    if figure is None:
        return threading.Lock()
    with _FIGURE_LOCKS_GUARD:
        lock = _FIGURE_LOCKS.get(figure)
        if lock is None:
            lock = threading.Lock()
            _FIGURE_LOCKS[figure] = lock
        return lock


def resolve_figure(value: Any) -> Any:
    """Return the ``matplotlib`` figure ``value`` belongs to, or ``None``.

    Resolves the way :func:`maidr.render` does, deliberately: ``None``
    means the current figure there, and a value naming several axes is
    rendered as the last one's figure. A resolver that disagreed with the
    renderer would take a lock on a figure the render never touches, which
    looks synchronised and is not.

    Parameters
    ----------
    value : Any
        Whatever the caller is about to render. ``None`` is the current
        matplotlib figure, as it is for :func:`maidr.render`.

    Returns
    -------
    Any
        The figure to lock, or ``None`` when there is none to lock --
        which :func:`figure_lock` answers with an unshared lock.
    """
    from maidr.api import _get_plot_or_current
    from maidr.core.figure_manager import FigureManager

    try:
        axes = FigureManager.get_axes(_get_plot_or_current(value))
    except (AttributeError, StopIteration):
        # Narrow, and not the case one might expect. A foreign figure --
        # plotly, altair -- does not raise: `get_axes` matches no branch
        # and returns `None`, which the `getattr` below turns into `None`
        # without ever reaching here. Measured: plotly-shaped, `None`,
        # `int` and `str` all return `None`; only an empty list or dict
        # raises, as `StopIteration`.
        #
        # So this catches malformed input that the caller's own validation
        # should already have rejected. Logged rather than swallowed: a
        # bare `except Exception` here would quietly downgrade a real bug
        # in `get_axes` to "lock scope lost", immediately before an
        # unsynchronised render.
        _logger.debug(
            "could not resolve a figure to lock for %r; rendering "
            "without a shared lock",
            type(value).__name__,
            exc_info=True,
        )
        return None

    if isinstance(axes, list):
        # Only a ``Figure`` lands here: ``get_axes`` returns its ``.axes``
        # property, while a list of artists takes a different branch and
        # comes back as a single ``Axes``. That is a coupling to
        # ``FigureManager.get_axes``'s branch order rather than to
        # matplotlib -- a ``Figure``-specific branch added ahead of the
        # ``Artist`` one would change which shape arrives here. A figure's axes all share that
        # figure, so which one is picked does not matter -- the last,
        # matching ``render``'s own loop over the list.
        axes = axes[-1] if axes else None

    # ``axes`` is an ``Axes`` or ``None`` by here: ``get_axes`` returns one
    # of those or a list, and the list is unwrapped above.
    return getattr(axes, "figure", None)


__all__ = ["figure_lock", "resolve_figure"]
