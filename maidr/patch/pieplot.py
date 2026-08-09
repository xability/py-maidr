from __future__ import annotations

import warnings
from typing import Any, Callable, Dict, Tuple

import wrapt
from matplotlib.axes import Axes

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import _argument


def pie(
    wrapped: Callable, instance: Axes, args: Tuple[Any, ...], kwargs: Dict[str, Any]
) -> tuple:
    """
    Patch function for `Axes.pie`.

    The slice magnitudes are read off the call rather than off the wedges it
    drew: `Axes.pie` plots `x / sum(x)` whenever the sum exceeds 1, and a
    `Wedge` keeps only its angles, so by the time the plot exists the caller's
    own numbers are gone. Reading them here is what lets `ax.pie([30, 50, 20])`
    report 30/50/20 instead of 0.3/0.5/0.2. `labels` travels the same way, for
    the same reason in reverse: matplotlib copies it onto the wedges, but only
    when the caller passed it.

    `maidr.patch.common.common` is not used here. It hands the wrapped
    function's return value to `FigureManager.get_axes`, and `Axes.pie` returns
    a tuple of artist lists rather than an artist; and its `kwargs` are the
    call's own, so there is nowhere in it to put what is extracted here.

    Parameters
    ----------
    wrapped : Callable
        The original function to be wrapped.
    instance : Axes
        The axes `Axes.pie` was called on, and the one it drew the wedges on.
    args : tuple
        Positional arguments passed to the original function.
    kwargs : dict
        Keyword arguments passed to the original function.

    Returns
    -------
    tuple
        `(wedges, texts)`, or `(wedges, texts, autotexts)` when the caller
        passed `autopct` — whichever the original function returned.
    """
    # Suppress warnings not to confuse screen-reader users
    warnings.filterwarnings("ignore")

    # Don't proceed if the call is made internally by the patched function.
    if ContextManager.is_internal_context():
        return wrapped(*args, **kwargs)

    # Set the internal context to avoid cyclic processing.
    with ContextManager.set_internal_context():
        plot = wrapped(*args, **kwargs)

    data = _argument("data", wrapped, args, kwargs)
    values = _resolve(_argument("x", wrapped, args, kwargs), data)
    labels = _resolve(_argument("labels", wrapped, args, kwargs), data)

    # `plot[0]` is the wedge list in both return shapes. Handing it over keeps
    # a nested pie's two rings apart: each layer then describes the slices its
    # own call drew rather than every wedge sitting on the axes.
    FigureManager.create_maidr(
        instance, PlotType.PIE, values=values, labels=labels, wedges=plot[0]
    )

    return plot


def _resolve(value: Any, data: Any) -> Any:
    """
    Resolve an argument that names a column of the call's ``data``.

    `Axes.pie` sits behind matplotlib's `_preprocess_data`, so
    ``ax.pie("sales", labels="fruit", data=df)`` is a valid call in which both
    arguments are column names. The patch wraps the outside of that decorator
    and therefore sees the names, not the columns; this looks them up the way
    matplotlib does.

    Parameters
    ----------
    value : Any
        The argument as the caller passed it.
    data : Any
        The call's ``data`` argument, or None when it had none.

    Returns
    -------
    Any
        The indexed value, or the argument unchanged when it does not name
        anything in ``data``.
    """
    if data is None or not isinstance(value, str):
        return value

    try:
        return data[value]
    except Exception:
        # Matplotlib treats an unresolvable name as a plain value too, and a
        # pie that renders must not fail to be described.
        return value


# Patch matplotlib function.
wrapt.wrap_function_wrapper(Axes, "pie", pie)
