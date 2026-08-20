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

The registry lives here, and :meth:`maidr.core.maidr.Maidr._create_html_tag`
is the only thing that takes a lock from it. That is deliberate: every
render of a matplotlib figure funnels through that one method, so a lock
held there covers every caller -- the Shiny and Streamlit integrations,
a threaded Flask app, a notebook doing its own threading, anything.

The integrations each held their own lock until #532, which covered the
two doors this package ships and nothing else. It also meant each door
had to work out *which* figure a value named before it could lock it, and
a resolver that disagreed with the renderer locked a figure the render
never touched (#531). Locking where the figure is already known removes
that class of bug rather than fixing instances of it.
"""

from __future__ import annotations

import threading
import weakref
from typing import Any

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


__all__ = ["figure_lock"]
