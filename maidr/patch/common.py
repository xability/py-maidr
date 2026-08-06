from __future__ import annotations

import inspect
import warnings
from typing import Any, Callable

from maidr.core.context_manager import ContextManager
from maidr.core.figure_manager import FigureManager


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


def common(plot_type, wrapped, _, args, kwargs) -> Any:
    # Suppress warnings not to confuse screen-reader users
    warnings.filterwarnings("ignore")

    # Don't proceed if the call is made internally by the patched function.
    if ContextManager.is_internal_context():
        return wrapped(*args, **kwargs)

    # Set the internal context to avoid cyclic processing.
    with ContextManager.set_internal_context():
        # Patch the plotting function.
        plot = wrapped(*args, **kwargs)

    # Extract the data points for MAIDR from the plot.
    ax = FigureManager.get_axes(plot)
    kwargs.pop("ax", None)
    FigureManager.create_maidr(ax, plot_type, **kwargs)

    return plot
