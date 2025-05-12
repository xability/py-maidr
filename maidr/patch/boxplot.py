from __future__ import annotations

import wrapt
from matplotlib.axes import Axes

from maidr.core.context_manager import BoxplotContextManager, ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager


@wrapt.patch_function_wrapper(Axes, "bxp")
def mpl_box(wrapped, _, args, kwargs) -> dict:
    # Don't proceed if the call is made internally by the patched function.
    if BoxplotContextManager.is_internal_context():
        plot = wrapped(*args, **kwargs)
        BoxplotContextManager.add_bxp_context(plot)
        return plot

    # Set the internal context to avoid cyclic processing.
    with ContextManager.set_internal_context():
        # Patch `ax.boxplot()` and `ax.bxp()`.
        plot = wrapped(*args, **kwargs)

    # Set the orientation of the boxplot
    if not kwargs.get("vert", True):
        orientation = "horz"
    else:
        orientation = "vert"

    # Extract the boxplot data points for MAIDR from the plot.
    ax = FigureManager.get_axes(plot)
    FigureManager.create_maidr(
        ax, PlotType.BOX, bxp_stats=plot, orientation=orientation
    )

    # Return to the caller.
    return plot


@wrapt.patch_function_wrapper("seaborn", "boxplot")
def sns_box(wrapped, _, args, kwargs) -> Axes:
    # Set the internal context to avoid cyclic processing.
    with BoxplotContextManager.set_internal_context() as bxp_context:
        # Patch `ax.boxplot()` and `ax.bxp()`.
        plot = wrapped(*args, **kwargs)
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


def sns_infer_new_orient(wrapped, instance, args, kwargs) -> str:
    if BoxplotContextManager.is_internal_context():
        orientation = instance.orient
        BoxplotContextManager.set_bxp_orientation(orientation)

    return wrapped(*args, **kwargs)


def patch_seaborn():
    import packaging.version as version
    import seaborn

    sns_version = seaborn.__version__
    min_version = "0.12"

    if version.parse(sns_version) < version.parse(min_version):
        wrapt.wrap_function_wrapper(
            "seaborn.categorical", "_BoxPlotter.plot", sns_version
        )
    else:
        wrapt.wrap_function_wrapper(
            "seaborn.categorical",
            "_CategoricalPlotter.plot_boxes",
            sns_infer_new_orient,
        )


# Apply the appropriate patches based on the Seaborn version
patch_seaborn()
