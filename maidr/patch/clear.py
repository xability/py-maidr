from __future__ import annotations

import wrapt

from matplotlib.axes import Axes
from matplotlib.figure import Figure

from maidr.core.figure_manager import FigureManager
from maidr.patch.lineplot import forget_axes_state


@wrapt.patch_function_wrapper(Figure, "clear")
def clear(wrapped, instance, args, kwargs) -> None:
    wrapped(*args, **kwargs)
    try:
        maidr = FigureManager.get_maidr(instance.get_figure())
    except KeyError:
        return
    maidr.clear()


def _clear_axes(wrapped, instance, args, kwargs) -> None:
    """Drop the layers drawn on an axes when matplotlib clears it.

    Only ``Figure.clear`` was patched, so re-plotting into a cleared axes
    *appended* a layer rather than replacing one, and the reader was offered
    a layer describing artists no longer drawn -- announced with confident
    values, and with a highlight resolving to nothing because those artists
    never reach ``HighlightContextManager``. It accumulated: five clear
    cycles left six layers (#499).

    ``ax.clear()`` is the ordinary way to redraw into a reused axes, so the
    two spellings of the same intent behaved differently and the correct one
    was the less common.

    Narrower than ``Figure.clear``'s ``maidr.clear()`` on purpose: on a
    figure with several axes, clearing one must leave the others registered.

    Dropping the layers is not enough on its own. ``lineplot`` keeps its
    own "already registered" latch on the axes, which matplotlib does not
    reset because it does not own it -- so clearing the layers while
    leaving the latch set makes the next ``ax.plot()`` register *nothing*,
    and the chart goes from mis-described to undescribed. See
    ``forget_axes_state``.

    Runs after ``wrapped``, matching the ``Figure.clear`` patch above -- the
    layers are dropped once matplotlib has actually removed the artists, not
    before.
    """
    wrapped(*args, **kwargs)

    # Before the registration lookup, not after: this state lives on the
    # axes and outlives any maidr entry. A figure closed with `maidr.close()`
    # and then cleared would otherwise keep the latch set, and nothing drawn
    # on it afterwards would register.
    forget_axes_state(instance)

    figure = instance.get_figure()
    if figure is None:
        return
    try:
        maidr = FigureManager.get_maidr(figure)
    except KeyError:
        return
    maidr.clear_axes(instance)


# Both spellings, because they delegate to each other depending on
# ``Axes._subclass_uses_cla``: ``clear()`` may call ``cla()`` or vice versa.
# Patching only one leaves the other reachable on a subclass that inverts
# the delegation. When both fire for a single call the second finds nothing
# left to drop, which is why ``clear_axes`` is idempotent.
wrapt.wrap_function_wrapper(Axes, "clear", _clear_axes)
wrapt.wrap_function_wrapper(Axes, "cla", _clear_axes)
