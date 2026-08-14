from __future__ import annotations

import inspect
import threading
import warnings
from typing import Any, Callable

import wrapt

from matplotlib.axes import Axes

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager

# Serialises the warning-filter save/restore in `_draw_quietly`; see its
# docstring for why interleaving those corrupts the global filter list.
# Reentrant because patches nest: `regplot.patched_plot` wraps `Axes.plot`,
# which `lineplot.line` wraps as well, so one draw can enter twice.
_FILTER_LOCK = threading.RLock()


def _argument(name: str, wrapped: Callable, args: tuple, kwargs: dict) -> Any:
    """
    Read one argument of a patched call, whether it was passed by name or by
    position.

    Parameters
    ----------
    name : str
        Name of the parameter to read.
    wrapped : Callable
        The wrapped matplotlib function, used for its parameter order. It is
        the bound method, so ``self`` is not among its parameters.
    args : tuple
        Positional arguments the caller passed.
    kwargs : dict
        Keyword arguments the caller passed.

    Returns
    -------
    Any
        The argument's value, or None when the caller did not pass it or the
        installed matplotlib has no such parameter.
    """
    if name in kwargs:
        return kwargs[name]

    try:
        parameters = inspect.signature(wrapped).parameters
    except (TypeError, ValueError):
        return None

    # Declared order is the binding order: matplotlib's `vert` and
    # `orientation` are declared keyword-only, yet the deprecation shim they
    # sit behind still accepts them positionally and assigns them in that
    # order, so the kind cannot be filtered on. A variadic parameter is the one
    # thing that breaks the correspondence — past it an index means nothing —
    # so stop there and let the keyword lookup above be the only answer.
    positional: list[str] = []
    for parameter_name, parameter in parameters.items():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            break
        positional.append(parameter_name)

    if name not in positional:
        return None

    index = positional.index(name)
    return args[index] if index < len(args) else None


def resolve_orientation(wrapped: Callable, args: tuple, kwargs: dict) -> str:
    """
    Resolve the MAIDR orientation of a matplotlib call that takes ``vert``.

    Matplotlib 3.10 introduced ``orientation`` and pending-deprecated ``vert``
    on ``Axes.boxplot``, ``Axes.bxp`` and ``Axes.violinplot``. Reading ``vert``
    alone misses ``orientation="horizontal"``, and — because ``Axes.boxplot``
    forwards ``vert=None`` to ``Axes.bxp`` whenever the caller omits it —
    defaulting an absent ``vert`` to False reads every vertical plot as
    horizontal.

    Mirror what matplotlib itself does: an explicitly set ``vert`` wins while
    it is still supported, and ``orientation`` decides otherwise.

    Parameters
    ----------
    wrapped : Callable
        The wrapped matplotlib function, used to read arguments the caller
        passed positionally.
    args : tuple
        Positional arguments the caller passed.
    kwargs : dict
        Keyword arguments the caller passed.

    Returns
    -------
    str
        ``"horz"`` for a horizontal plot, ``"vert"`` otherwise.
    """
    vert = _argument("vert", wrapped, args, kwargs)
    if vert is not None:
        return "vert" if vert else "horz"

    orientation = _argument("orientation", wrapped, args, kwargs)
    return "horz" if orientation == "horizontal" else "vert"


def _draw_quietly(wrapped: Callable, args: tuple, kwargs: dict) -> Any:
    """
    Call a patched plotting function with its warnings suppressed.

    The suppression is not to confuse screen-reader users with warnings they
    did not ask for and cannot act on. It is scoped to the call rather than
    installed process-wide, because a filter that outlives the call goes on
    swallowing warnings raised much later and far from any plot -- including
    MAIDR's own diagnostics, which are raised while the schema is built and
    not while the figure is drawn.

    ``catch_warnings`` saves and restores the *global* filter list, which two
    threads drawing at once will corrupt outright rather than merely race on.
    Interleave one pair of calls and the restores nest wrongly::

        A enters, saving S0          filters = ignore + S0
        B enters, saving S1          S1 already contains A's ignore
        A exits,  restoring S0       filters = S0        (correct, for now)
        B exits,  restoring S1       filters = ignore + S0

    B puts back a snapshot it took while A was suppressing, so a process-wide
    ``ignore`` survives every draw -- exactly the leak this helper was written
    to remove, reintroduced under concurrency and permanently. Measured: eight
    threads drawing sixty times each leave one ``('ignore', None, Warning,
    None, 0)`` behind.

    Serialising the draw is what prevents it, since the save and restore have
    to pair up. The cost is real but narrow: drawing is already effectively
    single-threaded for the caller that motivated this (Shiny renders on one
    asyncio loop), and matplotlib's own guidance is that a figure belongs to
    one thread anyway. Python 3.14's context-aware filters would remove the
    need for the lock.

    What the lock does *not* fix is that a draw's ``ignore`` is global while
    it is held, so another thread warning at that moment is still silenced.
    That one is transient -- it ends with the draw -- rather than surviving
    it, and closing it would mean not touching the global filters at all.

    Parameters
    ----------
    wrapped : Callable
        The original plotting function.
    args : tuple
        Positional arguments the caller passed.
    kwargs : dict
        Keyword arguments the caller passed.

    Returns
    -------
    Any
        Whatever the wrapped function returned.
    """
    with _FILTER_LOCK, warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return wrapped(*args, **kwargs)


def common(
    plot_type: PlotType | Callable[[Axes], PlotType], wrapped, _, args, kwargs
) -> Any:
    """
    Draw a patched plot and register the layer it produced with MAIDR.

    Parameters
    ----------
    plot_type : PlotType or callable
        The type to register the layer as. A callable is handed the drawn
        Axes and returns the type, for plots whose layout is only decided
        inside the library being patched: seaborn works out on its own
        whether a hue splits a bar layer into groups, and does not forward
        that decision to matplotlib.
    wrapped : Callable
        The original plotting function.
    _ : Any
        The instance wrapt bound the patched function to, or None for a
        module-level function. Unused here, and named for that.
    args : tuple
        Positional arguments the caller passed.
    kwargs : dict
        Keyword arguments the caller passed.

    Returns
    -------
    Any
        Whatever the wrapped function returned.
    """
    # Don't proceed if the call is made internally by the patched function.
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    # Set the internal context to avoid cyclic processing.
    with ContextManager.set_internal_context():
        # Patch the plotting function.
        plot = _draw_quietly(wrapped, args, kwargs)

    # Extract the data points for MAIDR from the plot.
    ax = FigureManager.get_axes(plot)
    kwargs.pop("ax", None)
    if callable(plot_type):
        plot_type = plot_type(ax)
    FigureManager.create_maidr(ax, plot_type, **kwargs)

    return plot


def wrap_seaborn(name: str, wrapper: Callable) -> None:
    """
    Wrap a seaborn function at both of the names it answers to.

    seaborn re-exports its plotting functions from the package root, and its
    own figure-level functions import them from the *defining* module inside
    the function body::

        from .relational import scatterplot   # Avoid circular import
        from .distributions import histplot, kdeplot

    Those are two separate bindings to one function object, so wrapping
    ``seaborn.scatterplot`` leaves ``seaborn.relational.scatterplot``
    untouched -- and every grid in ``seaborn/axisgrid.py`` takes the second
    one. `pairplot`, `jointplot`, `catplot`, `relplot`, `displot` and
    `lmplot` therefore ran the *unpatched* function, and the panel was seen
    only by the matplotlib-level patches.

    That cost two things at once. A `histplot` panel arrived as bars, because
    `Axes.bar` cannot know it is drawing a histogram and the seaborn-level
    patch that would have known never ran. And every panel registered twice:
    `seaborn.utils._default_color` draws a throwaway artist to resolve a
    default colour and removes it again, and with no seaborn-level patch
    there was no recursion context to suppress it, so the probe registered as
    a chart of its own (#344).

    The defining module is located through ``__module__`` rather than a table
    of names, so a function seaborn moves does not quietly stop being
    patched -- and the identity check means a name that no longer resolves to
    the same object is left alone rather than wrapped by guess.

    Parameters
    ----------
    name : str
        The function's name, the same at both bindings.
    wrapper : Callable
        The wrapt-style wrapper to install.
    """
    import importlib

    import seaborn

    original = getattr(seaborn, name, None)
    if original is None:  # pragma: no cover - seaborn dropped the function
        return

    defining = getattr(original, "__module__", None)
    wrapt.wrap_function_wrapper(seaborn, name, wrapper)

    if not defining or defining == "seaborn":  # pragma: no cover
        return
    try:
        module = importlib.import_module(defining)
    except ImportError:  # pragma: no cover - a module seaborn does not ship
        return
    if getattr(module, name, None) is original:
        wrapt.wrap_function_wrapper(module, name, wrapper)
