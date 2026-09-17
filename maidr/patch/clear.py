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


def _discarded_child_axes(ax: Axes) -> list[Axes]:
    """Every axes ``ax`` is about to discard along with its own artists.

    ``Axes.inset_axes`` parents the inset to the axes it sits in rather than
    to the figure, and ``_AxesBase.__clear`` empties ``child_axes`` -- so a
    clear detaches every inset as surely as it removes the artists drawn
    directly on the axes. ``clear_axes`` keys layers by their own axes, which
    is right for a ``twinx`` twin (a sibling on the figure, and not a child)
    but leaves the inset's layer registered against an axes nothing will
    draw again.

    Depth first, because an inset may hold an inset. The parent's clear
    detaches the outer one and stops there -- the inner one is still
    attached to a detached axes -- so a single level would leave the deeper
    layer behind.

    Parameters
    ----------
    ax : Axes
        The axes being cleared, read **before** matplotlib clears it.

    Returns
    -------
    list of Axes
        The discarded children, deepest last.
    """
    discarded = []
    for child in getattr(ax, "child_axes", ()):
        discarded.append(child)
        discarded.extend(_discarded_child_axes(child))
    return discarded


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

    Narrow by *axes*, though, not by artist: a clear also discards the axes'
    own children, and a layer drawn into an inset is keyed by the inset, so
    the narrow rule that correctly spares a ``twinx`` twin missed the inset
    entirely. The inset's layer survived a clear it did not survive the
    drawing of -- announced first, with its old data, and with a highlight
    resolving to nothing -- and five clear-and-rebuild cycles left six
    layers, which is #499 again through a route this hook did not reach.

    Dropping the layers is not enough on its own. ``lineplot`` keeps its
    own "already registered" latch on the axes, which matplotlib does not
    reset because it does not own it -- so clearing the layers while
    leaving the latch set makes the next ``ax.plot()`` register *nothing*,
    and the chart goes from mis-described to undescribed. See
    ``forget_axes_state``.

    Runs after ``wrapped``, matching the ``Figure.clear`` patch above -- the
    layers are dropped once matplotlib has actually removed the artists, not
    before. The one thing that has to be read *first* is the list of child
    axes, which the clear empties; see ``_discarded_child_axes``.
    """
    # Read before `wrapped`, because `_AxesBase.__clear` empties
    # `child_axes`: after the call there is nothing left on `instance` to
    # say an inset was ever there.
    discarded = _discarded_child_axes(instance)

    wrapped(*args, **kwargs)

    # Before the registration lookup, not after: this state lives on the
    # axes and outlives any maidr entry. A figure closed with `maidr.close()`
    # and then cleared would otherwise keep the latch set, and nothing drawn
    # on it afterwards would register.
    #
    # The discarded children get the same treatment as the axes itself. They
    # are detached rather than destroyed -- a caller holding the inset can
    # draw on it again -- and dropping a layer while leaving the latch set is
    # the one failure `forget_axes_state` exists to prevent: the redraw
    # registers nothing and the chart goes from mis-described to undescribed.
    # It also drops the detached `Line2D` objects the series list holds.
    cleared = (instance, *discarded)
    for axes in cleared:
        forget_axes_state(axes)

    figure = instance.get_figure()
    if figure is None:
        return
    try:
        maidr = FigureManager.get_maidr(figure)
    except KeyError:
        return
    # The children are looked up against the *parent's* figure: a detached
    # inset still answers `get_figure()`, but the registration that owns its
    # layer is the one the clear was addressed to.
    for axes in cleared:
        maidr.clear_axes(axes)


# Both spellings, because they delegate to each other depending on
# ``Axes._subclass_uses_cla``: ``clear()`` may call ``cla()`` or vice versa.
# Patching only one leaves the other reachable on a subclass that inverts
# the delegation. When both fire for a single call the second finds nothing
# left to drop, which is why ``clear_axes`` is idempotent.
wrapt.wrap_function_wrapper(Axes, "clear", _clear_axes)
wrapt.wrap_function_wrapper(Axes, "cla", _clear_axes)
