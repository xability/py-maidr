"""
Custom matplotlib backend that renders plots accessibly via maidr.

This backend delegates rendering to the Agg backend but overrides the
``show()`` function so that ``plt.show()`` displays accessible maidr HTML
output (with sonification, braille, and tactile support) instead of a
static image window.

The backend is automatically activated when ``import maidr`` is executed.
Users can also set it manually via ``matplotlib.use("module://maidr.backend")``.
"""

from __future__ import annotations

import logging
import os
import tempfile
import warnings
import webbrowser
from typing import Any

from matplotlib._pylab_helpers import Gcf
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

_logger = logging.getLogger(__name__)

# Required matplotlib backend exports.
# FigureCanvas: Agg canvas for non-interactive (file-based) rendering.
# FigureManager: matplotlib's internal figure-window manager — distinct from
# ``maidr.core.figure_manager.FigureManager`` which tracks maidr-accessible
# plots.
FigureCanvas = FigureCanvasAgg
FigureManager = FigureCanvasAgg.manager_class

__all__ = ["FigureCanvas", "FigureManager", "show"]


def show(*args: Any, **kwargs: Any) -> None:
    """Display all open figures using maidr's accessible renderer.

    This function is called by ``plt.show()``.  For every figure tracked by
    maidr's `FigureManager`, the accessible HTML representation is rendered.
    Figures that are not tracked (e.g. those created without any supported
    plot type) fall back to static image display with a warning.

    Parameters
    ----------
    *args : Any
        Accepted to satisfy the matplotlib backend protocol but not used.
    **kwargs : Any
        Accepted to satisfy the matplotlib backend protocol but not used.
    """
    from maidr.core.figure_manager import FigureManager as MaidrFigureManager

    managers = Gcf.get_all_fig_managers()
    if not managers:
        return

    for manager in list(managers):
        fig = manager.canvas.figure
        try:
            maidr_obj = MaidrFigureManager.get_maidr(fig)
        except KeyError:
            # Figure not tracked by maidr (e.g. unsupported plot type).
            # Fall back to displaying a static image so the user still
            # sees their plot.
            _show_fallback(fig)
        else:
            # clear_fig=False because the backend handles figure cleanup.
            maidr_obj.show(clear_fig=False)
            # Clean up maidr's own tracking to prevent memory leaks.
            # Without this, FigureManager.figs grows unboundedly because
            # clear_fig=False skips the plt.close() -> clear.py path.
            MaidrFigureManager.destroy(fig)
        Gcf.destroy(manager.num)


def _show_fallback(fig: Figure) -> None:
    """Display a figure as a static image when maidr does not support it.

    Emits a warning and renders the figure using IPython's display system
    (in notebooks) or by saving a temporary PNG and opening it in the
    default browser (in scripts).

    Parameters
    ----------
    fig : Figure
        The matplotlib figure to display.
    """
    warnings.warn(
        "This figure contains plot type(s) not yet supported by maidr. "
        "Falling back to static image. Supported types: bar, box, count, "
        "dodged, heat, hist, line, scatter, stacked, kde, violin, candlestick.",
        stacklevel=4,
    )

    from maidr.util.environment import Environment

    if Environment.is_notebook():
        try:
            import io

            from IPython.display import Image, display

            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
            buf.seek(0)
            display(Image(data=buf.getvalue()))
        except ImportError:
            _logger.debug("IPython not available for fallback display.")
    else:
        # Save to a temporary PNG and open in the default browser.
        tmp_dir = os.path.join(tempfile.gettempdir(), "maidr")
        os.makedirs(tmp_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(suffix=".png", dir=tmp_dir)
        os.close(fd)
        fig.savefig(tmp_path, dpi=150, bbox_inches="tight")
        webbrowser.open(f"file://{tmp_path}")
