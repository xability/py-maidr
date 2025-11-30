from __future__ import annotations

import wrapt
from matplotlib.axes import Axes

from maidr.core.context_manager import ContextManager
from maidr.core.plot.violinplot import ViolinLayerExtractor


@wrapt.patch_function_wrapper("seaborn", "violinplot")
def patch_violinplot(wrapped, instance, args, kwargs):
    """
    Patch for seaborn.violinplot to extract and register KDE and box plot layers with MAIDR.
    
    Always registers a KDE layer containing all violin shapes.
    Registers a box layer when inner='box' or inner='boxplot' (default is 'box' in Seaborn).
    """
    if ContextManager.is_internal_context():
        return wrapped(*args, **kwargs)

    # Original rendering - always execute
    with ContextManager.set_internal_context():
        ax = wrapped(*args, **kwargs)

    plot_ax = kwargs.get("ax", ax) or ax

    # Determine orientation
    orient = kwargs.get("orient", "v")
    vert = not (orient in ("h", "horizontal", "y"))
    orientation = "vert" if vert else "horz"

    # Extract and register KDE layer (always done for violin plots)
    ViolinLayerExtractor.extract_and_register_kde_layer(plot_ax, ax, instance, args, kwargs)

    # Register box layer when inner='box' or inner='boxplot'
    # Seaborn's default is inner='box', so we treat None/missing as 'box'
    inner = kwargs.get("inner", "box")  # Default to 'box' if not specified
    if inner in ("box", "boxplot"):
        ViolinLayerExtractor.extract_and_register_box_layer(plot_ax, args, kwargs, orientation)

    return ax
