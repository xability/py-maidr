from __future__ import annotations

import wrapt
from matplotlib.axes import Axes

from maidr.core.context_manager import BoxplotContextManager, ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import _draw_quietly, resolve_orientation, wrap_seaborn


@wrapt.patch_function_wrapper(Axes, "bxp")
def mpl_box(wrapped, _, args, kwargs) -> dict:
    # Don't proceed if the call is made internally by the patched function.
    if BoxplotContextManager.is_internal_context():
        plot = _draw_quietly(wrapped, args, kwargs)
        BoxplotContextManager.add_bxp_context(plot)
        return plot

    # Set the internal context to avoid cyclic processing.
    with ContextManager.set_internal_context():
        # Patch `ax.boxplot()` and `ax.bxp()`.
        plot = _draw_quietly(wrapped, args, kwargs)

    # Set the orientation of the boxplot
    orientation = resolve_orientation(wrapped, args, kwargs)

    # Extract the boxplot data points for MAIDR from the plot.
    ax = FigureManager.get_axes(plot)
    FigureManager.create_maidr(
        ax, PlotType.BOX, bxp_stats=plot, orientation=orientation
    )

    # Return to the caller.
    return plot


def sns_box(wrapped, _, args, kwargs) -> Axes:
    # Set the internal context to avoid cyclic processing.
    with BoxplotContextManager.set_internal_context() as bxp_context:
        # Patch `ax.boxplot()` and `ax.bxp()`.
        plot = _draw_quietly(wrapped, args, kwargs)
        bxp_container = bxp_context

    # Set the orientation of the boxplot
    if bxp_container.orientation() == "y" or bxp_container.orientation() == "h":
        orientation = "horz"
    else:
        orientation = "vert"

    # Extract the boxplot data points for MAIDR from the plot.
    ax = FigureManager.get_axes(bxp_container.bxp_stats())
    FigureManager.create_maidr(
        ax, PlotType.BOX, bxp_stats=bxp_container.bxp_stats(), orientation=orientation
    )

    # Return to the caller.
    return plot


# Patch seaborn function.
wrap_seaborn("boxplot", sns_box)


def sns_infer_new_orient(wrapped, instance, args, kwargs) -> str:
    if BoxplotContextManager.is_internal_context():
        orientation = instance.orient
        BoxplotContextManager.set_bxp_orientation(orientation)

    return _draw_quietly(wrapped, args, kwargs)


def patch_seaborn():
    """
    Wrap the seaborn internal that reports a categorical plot's orientation.

    ``_CategoricalPlotter.plot_boxes`` arrived with the categorical rewrite in
    seaborn **0.13**, and this used to branch on ``"0.12"`` -- so 0.12 took the
    0.13 path and ``wrapt`` raised while resolving the attribute. At import
    time, which meant ``import maidr`` did not survive a seaborn the package
    declared support for::

        AttributeError: type object '_CategoricalPlotter' has no attribute 'plot_boxes'

    The other branch could not have helped: it passed ``sns_version``, a
    *string*, where the wrapper function goes. Nothing was ever ``< 0.12`` and
    installable, so the mistake never surfaced.

    Rather than repair a path nothing runs, ``pyproject.toml`` now declares
    ``seaborn>=0.13`` -- which is what CI installs and the only version any
    test has run against, and which breaks no working installation because
    0.12 could not import in the first place. Making 0.12 genuinely work is
    still open as the other half of #441; it would need the boxen extraction
    to read that release's nested ladder as well.
    """
    wrapt.wrap_function_wrapper(
        "seaborn.categorical",
        "_CategoricalPlotter.plot_boxes",
        sns_infer_new_orient,
    )


patch_seaborn()
