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

import atexit
import logging
import os
import shutil
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
# plots.  FigureManagerAgg is not a public export; the correct way to obtain
# the manager class is via ``FigureCanvasAgg.manager_class``.
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
        Additional keyword arguments.  The only one currently inspected
        is ``use_cdn``, which is forwarded to each figure's
        :meth:`Maidr.show` call so that ``plt.show(use_cdn=False)``
        and ``plt.show(use_cdn="auto")`` work end-to-end.  Any
        other kwargs are accepted (per the backend protocol) and
        silently ignored.
    """
    from maidr.api import get_use_cdn
    from maidr.core.figure_manager import FigureManager as MaidrFigureManager

    managers = Gcf.get_all_fig_managers()
    if not managers:
        return

    # Prefer an explicit ``plt.show(use_cdn=...)`` over the module-level
    # default; fall back to ``maidr.api.get_use_cdn()`` otherwise.  This
    # lets users opt in via any of: per-call kwarg, ``maidr.set_use_cdn``,
    # or the ``MAIDR_USE_CDN`` environment variable.
    use_cdn = kwargs.pop("use_cdn", None)
    if use_cdn is None:
        use_cdn = get_use_cdn()

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
            maidr_obj.show(clear_fig=False, use_cdn=use_cdn)
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
    # stacklevel=4 traces through: user code → plt.show() → backend.show()
    # → _show_fallback() → warnings.warn().  If the internal call chain
    # changes, this value must be updated.
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

        if Environment.is_wsl():
            # webbrowser.open() is unreliable on WSL; use cmd.exe instead.
            import subprocess

            subprocess.Popen(  # noqa: S603
                ["cmd.exe", "/c", "start", "", tmp_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            webbrowser.open(f"file://{tmp_path}")


def _cleanup_temp_dir() -> None:
    """Remove the maidr temporary directory on interpreter exit."""
    tmp_dir = os.path.join(tempfile.gettempdir(), "maidr")
    shutil.rmtree(tmp_dir, ignore_errors=True)


atexit.register(_cleanup_temp_dir)
