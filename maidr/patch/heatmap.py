from __future__ import annotations

import inspect
from typing import Callable

import wrapt

from matplotlib.axes import Axes
from matplotlib.collections import Collection
from matplotlib.image import AxesImage

from matplotlib.collections import PolyQuadMesh, QuadMesh

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.heatmap import DRAWN_GRID
from maidr.patch.common import _draw_quietly, wrap_seaborn


def _grid_of(plot, ax: Axes | None):
    """
    The mesh or image a call drew, if it can be had.

    Preferring the return value is the whole point: a layer that looks its
    artist up from the axes later resolves *per axes*, so two heatmaps drawn
    on one axes both read the first one's values (#527).

    The fallback takes the **last** grid rather than the first, which is where
    it parts company with ``extract_scalar_mappable``. That helper answers
    "which artist is this axes' heatmap", and reasonably says the first; this
    one answers "which artist did the call that is registering right now
    draw", and matplotlib appends artists in draw order -- measured, a second
    ``pcolormesh`` on the same axes arrives after the first in
    ``get_children()``, and ``seaborn.heatmap`` beside an existing mesh leaves
    its own last, carrying its own values.

    Parameters
    ----------
    plot : Any
        Whatever the patched function returned. ``Axes.imshow`` returns an
        ``AxesImage``, ``Axes.pcolormesh`` a ``QuadMesh``, ``Axes.pcolor`` a
        ``PolyQuadMesh``, and ``seaborn.heatmap`` the axes.
    ax : Axes or None
        The axes drawn on.

    Returns
    -------
    QuadMesh or PolyQuadMesh or AxesImage or None
        The grid, or ``None`` when neither the return value nor the axes
        offers one.
    """
    grids = (QuadMesh, PolyQuadMesh, AxesImage)
    if isinstance(plot, grids):
        return plot
    drawn = [
        artist
        for artist in (getattr(ax, "get_children", list)() or ())
        if isinstance(artist, grids)
    ]
    return drawn[-1] if drawn else None


def _is_colour_image(grid) -> bool:
    """
    Whether the artist holds a picture rather than a grid of values.

    ``ax.imshow`` accepts three shapes: an ``(M, N)`` array of scalars, which
    is a heatmap, and ``(M, N, 3)`` / ``(M, N, 4)`` arrays whose last axis is
    **colour**. The last two are photographs and rendered images, and there is
    no number per cell to announce -- no value, and nothing for the colourbar
    the ``z`` axis describes to mean.

    Registered as a heatmap they did not merely read badly, they killed the
    figure: ``HeatPlot`` formats each cell with ``float(format(x, fmt))``, and
    for a row of an RGB image ``x`` is a length-3 array, so ``render`` raised
    ``ValueError: could not convert string to float: '[0.5 0.5 0.5]'`` and
    took every other chart on the figure with it (#564).

    Declining leaves the image drawn and unregistered, which is what
    ``ax.quiver`` and ``ax.streamplot`` already do -- the figure renders, and
    a bar chart beside the picture keeps working.

    Parameters
    ----------
    grid : Any
        The artist :func:`_grid_of` found, or None.

    Returns
    -------
    bool
        True when the artist's array carries colour rather than values.
    """
    array = getattr(grid, "get_array", lambda: None)()
    return array is not None and getattr(array, "ndim", 0) >= 3


def _declares_fmt(wrapped: Callable) -> bool:
    """
    Whether a patched function takes ``fmt`` as a parameter of its own.

    ``fmt`` is seaborn's: ``seaborn.heatmap`` declares it and uses it to format
    the cell annotations. The matplotlib entry points patched here do not, and
    forwarding it to one of them does not fail cleanly -- ``Axes.pcolormesh``
    swallows the kwarg into ``**kwargs`` and passes it to the artist, which
    raises ``AttributeError: QuadMesh.set() got an unexpected keyword argument
    'fmt'`` from somewhere the caller has no way to connect back to MAIDR.

    So the test has to be for an *explicitly declared* parameter. A
    ``**kwargs``-accepting signature is exactly the case that misleads here:
    every one of these functions has one, and none of them can actually use
    the value.

    Parameters
    ----------
    wrapped : Callable
        The wrapped plotting function.

    Returns
    -------
    bool
        True when the function declares ``fmt`` and can be handed it.
    """
    try:
        return "fmt" in inspect.signature(wrapped).parameters
    except (TypeError, ValueError):
        # A callable with no introspectable signature. Assume it cannot take
        # `fmt`: dropping it costs MAIDR nothing, since the value is read out
        # for the schema either way, while forwarding one the function cannot
        # take aborts the draw.
        return False


def heat(wrapped, _, args, kwargs) -> Axes | AxesImage | Collection:
    """
    Draw a patched heatmap call and register the layer it produced with MAIDR.

    Wraps every way a heatmap reaches the canvas: ``Axes.imshow``,
    ``Axes.pcolormesh``, ``Axes.pcolor`` and ``seaborn.heatmap``. Two MAIDR-only
    parameters are lifted out of ``kwargs`` before the draw — ``z_label``, which
    names the colour dimension and which matplotlib has never heard of, and
    ``fmt``, which only ``seaborn.heatmap`` declares.

    This does not route through :func:`maidr.patch.common.common` precisely
    because of that lifting: ``common`` forwards ``kwargs`` untouched, and these
    two have to be removed first.

    Parameters
    ----------
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
    Axes or AxesImage or Collection
        Whatever the wrapped function returned: an ``Axes`` from seaborn, an
        ``AxesImage`` from ``imshow``, or the mesh the two ``pcolor`` variants
        render.
    """
    # `seaborn.heatmap` draws through `Axes.pcolormesh`, and both are patched
    # here. Without this guard the inner call registers a second HEAT layer for
    # the same axes, so one `sns.heatmap()` would be announced as two identical
    # heatmaps the user has to navigate between. Every other patch reaches the
    # same guard through `common()`; this one does not call it, because it has
    # to pop `z_label` before the draw rather than pass it through.
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    # Check for additional params used by MAIDR heatmap.
    optional_params = {}
    if "z_label" in kwargs:
        # Remove `z_label` because it is introduced by us.
        optional_params["z_label"] = kwargs.pop("z_label")
    if "fmt" in kwargs:
        # Read for the schema either way, but only forwarded to a function that
        # can actually take it -- see `_declares_fmt`.
        optional_params["fmt"] = kwargs["fmt"]
        if not _declares_fmt(wrapped):
            kwargs.pop("fmt")

    # Patch `ax.imshow()`, `ax.pcolormesh()`, `ax.pcolor()` and `seaborn.heatmap`.
    with ContextManager.set_internal_context():
        plot = _draw_quietly(wrapped, args, kwargs)

    # Extract the heatmap data points for MAIDR from the plots.
    ax = FigureManager.get_axes(plot)
    grid = _grid_of(plot, ax)

    # An RGB or RGBA image is not a heatmap -- see `_is_colour_image`.
    if _is_colour_image(grid):
        return plot

    optional_params[DRAWN_GRID] = grid
    FigureManager.create_maidr(ax, PlotType.HEAT, **optional_params)

    # Return to the caller.
    return plot


# Patch matplotlib functions.
#
# `imshow` is not the only way a matplotlib heatmap gets drawn, and it is not
# the most common one: `pcolormesh` is what you reach for whenever the grid is
# irregular or the axes carry real coordinates rather than array indices, which
# covers most scientific use. Until these two were patched such a figure
# registered nothing at all, and the user got silence with no indication that
# anything had been missed.
wrapt.wrap_function_wrapper(Axes, "imshow", heat)
wrapt.wrap_function_wrapper(Axes, "pcolormesh", heat)
wrapt.wrap_function_wrapper(Axes, "pcolor", heat)

# Patch seaborn function.
wrap_seaborn("heatmap", heat)
