from __future__ import annotations

from typing import Any

import wrapt
from matplotlib.colorbar import Colorbar

from maidr.core.context_manager import ContextManager


def _suppress_registration(wrapped, _, args, kwargs) -> Any:
    """
    Draw a colorbar without registering it as a chart of its own.

    Named apart from ``common._draw_quietly``, which is a different helper
    doing a different job -- that one suppresses *warnings* around a
    plotting call, and nearly every other patch module uses it.

    A colorbar paints its gradient onto its own axes through the very entry
    points the heatmap patch wraps, so MAIDR was registering it as a second
    ``heat`` layer. It is not a chart: it is the legend for the one beside it,
    and the values it carries are already the ``z`` axis of that layer.

    Two things went wrong, and the second is the one a user notices.

    A phantom layer, first -- a reader handed a second "heatmap" to page
    through that the figure does not contain. And then the render **died**:
    extraction reaches the colorbar's outline, a ``LineCollection`` where a
    mappable is expected, and raises. An ``ExtractionError`` is not confined
    to its own layer; it takes the whole figure with it, so a chart that would
    have read perfectly well produced nothing at all (#369).

    Every route -- ``Figure.colorbar``, ``plt.colorbar``, an explicitly
    supplied ``cax`` -- goes through ``Colorbar._draw_all``, which is why the
    guard lives here rather than on a test for "is this axes a colorbar".
    Attribute-sniffing would also have been wrong on the timing:
    ``ax._colorbar`` is not assigned until after the draw that registers the
    layer.

    Parameters
    ----------
    wrapped : Callable
        The original ``Colorbar._draw_all``.
    _ : Any
        The ``Colorbar`` wrapt bound the method to. Unused, and named for that.
    args : tuple
        Positional arguments matplotlib passed.
    kwargs : dict
        Keyword arguments matplotlib passed.

    Returns
    -------
    Any
        Whatever the wrapped method returned, unchanged.
    """
    with ContextManager.set_internal_context():
        return wrapped(*args, **kwargs)


# `_draw_all` is private, so a rename upstream must degrade to the previous
# behaviour rather than stop the package importing. That is a phantom layer
# and a broken render, which is bad -- but a package that cannot be imported
# is worse, and the failure would be caught by the tests that pin this rather
# than by a user.
try:
    wrapt.wrap_function_wrapper(Colorbar, "_draw_all", _suppress_registration)
except AttributeError:  # pragma: no cover - matplotlib renamed the method
    pass
