"""
Custom matplotlib backend that renders plots accessibly via maidr.

This backend delegates rendering to the Agg backend but overrides the
``show()`` function so that ``plt.show()`` displays accessible maidr HTML
output (with sonification, braille, and tactile support) instead of a
static image window.

The backend is automatically activated when ``import maidr`` is executed.
Users can also set it manually via ``matplotlib.use("module://maidr.backend")``.

In a notebook it also stands in for matplotlib_inline, the backend it
replaces there: a figure pyplot opens is queued to be shown at the end of the
cell (:func:`new_figure_manager_given_figure`), as matplotlib_inline queues
it; see :mod:`maidr.util.notebook_display`.
"""

from __future__ import annotations

import atexit
import logging
import os
import shutil
import tempfile
import webbrowser
from typing import Any

from matplotlib._pylab_helpers import Gcf
from matplotlib.backend_bases import FigureManagerBase
from matplotlib.backends import backend_agg
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from maidr.util.fallback import warn_unsupported

_logger = logging.getLogger(__name__)

# Required matplotlib backend exports.
# FigureCanvas: Agg canvas for non-interactive (file-based) rendering.
# FigureManager: matplotlib's internal figure-window manager — distinct from
# ``maidr.core.figure_manager.FigureManager`` which tracks maidr-accessible
# plots.  FigureManagerAgg is not a public export; the correct way to obtain
# the manager class is via ``FigureCanvasAgg.manager_class``.
FigureCanvas = FigureCanvasAgg
FigureManager = FigureCanvasAgg.manager_class

__all__ = [
    "FigureCanvas",
    "FigureManager",
    "new_figure_manager",
    "new_figure_manager_given_figure",
    "show",
]


def new_figure_manager(
    num: Any, *args: Any, FigureClass: Any = Figure, **kwargs: Any
) -> FigureManagerBase:
    """Return a manager for a new figure, as pyplot asks a backend for one.

    Defined, as matplotlib_inline defines it, so that the backend learns of
    every figure pyplot opens; see :func:`new_figure_manager_given_figure`.

    Parameters
    ----------
    num : int or str
        The figure's number or label.
    *args : Any
        Positional arguments for the figure class.
    FigureClass : type, default Figure
        The figure class.
    **kwargs : Any
        Keyword arguments for the figure class.

    Returns
    -------
    matplotlib.backend_bases.FigureManagerBase
        The manager.
    """
    return new_figure_manager_given_figure(num, FigureClass(*args, **kwargs))


def new_figure_manager_given_figure(num: Any, figure: Figure) -> FigureManagerBase:
    """Return a manager for a figure, and queue the figure for a notebook.

    The manager is Agg's. In a notebook, the figure is queued to be shown at
    the end of the cell, as matplotlib_inline queues the figures it is given
    a manager for: see :func:`maidr.util.notebook_display.note_new_figure`.

    Parameters
    ----------
    num : int or str
        The figure's number or label.
    figure : Figure
        The figure.

    Returns
    -------
    matplotlib.backend_bases.FigureManagerBase
        The manager.
    """
    from maidr.util.notebook_display import note_new_figure

    manager = backend_agg.new_figure_manager_given_figure(num, figure)
    note_new_figure(figure)
    return manager


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
    from maidr.api import _resolve_use_cdn
    from maidr.util.environment import Environment
    from maidr.util.pyodide_display import warn_no_page

    managers = Gcf.get_all_fig_managers()
    if not managers:
        return

    # A Pyodide web worker, or Node.js, has no page to put a chart in, and
    # `webbrowser.open` raises there. Say so instead, and leave the figures
    # open: the `maidr.render` the warning points to still has them, and so
    # does a host that shows whatever is left open.
    if Environment.is_pyodide_without_page():
        warn_no_page()
        return

    # Prefer an explicit ``plt.show(use_cdn=...)`` over the module-level
    # default; fall back to ``maidr.api.get_use_cdn()`` otherwise.  This
    # lets users opt in via any of: per-call kwarg, ``maidr.set_use_cdn``,
    # or the ``MAIDR_USE_CDN`` environment variable.  Routed through the
    # same resolver as ``maidr.render`` so that a value it would reject
    # (``"false"``, ``0``) is rejected here too, rather than reaching
    # ``Maidr.show`` and rendering CDN-only for someone who asked for
    # offline.
    use_cdn = _resolve_use_cdn(kwargs.pop("use_cdn", None))

    for manager in list(managers):
        # The warning for a figure maidr has no chart of names the caller of
        # ``plt.show()``: past this function and ``pyplot.show``.
        show_figure(manager.canvas.figure, use_cdn=use_cdn, stacklevel=3)
        Gcf.destroy(manager.num)


def show_figure(fig: Figure, use_cdn: Any = None, *, stacklevel: int = 1) -> None:
    """Show one figure as ``plt.show()`` does, leaving it open.

    Its maidr chart, or, for a figure maidr has no chart of, a static image
    and a warning; see :func:`_show_fallback`.

    maidr's record of the figure is kept: it lives on the figure (#456) and
    goes with it, and a figure shown again later -- the value of a later
    notebook cell -- is then still its chart, with every layer drawn on it.

    Parameters
    ----------
    fig : Figure
        The figure.
    use_cdn : bool, {"auto"}, or None, default None
        See :func:`maidr.render`; ``None`` defers to :func:`maidr.get_use_cdn`.
    stacklevel : int, default 1
        Whose line the warning for a figure maidr has no chart of names, as
        :func:`warnings.warn` counts it from this function's caller: 1 is
        the caller.
    """
    from maidr.api import _resolve_use_cdn
    from maidr.core.figure_manager import FigureManager as MaidrFigureManager

    try:
        maidr_obj = MaidrFigureManager.get_maidr(fig)
    except KeyError:
        # Figure not tracked by maidr (e.g. unsupported plot type).
        # Fall back to displaying a static image so the user still
        # sees their plot.
        _show_fallback(fig, stacklevel=stacklevel + 3)
    else:
        # clear_fig=False because the caller closes the figure.
        maidr_obj.show(clear_fig=False, use_cdn=_resolve_use_cdn(use_cdn))


def _show_fallback(fig: Figure, *, stacklevel: int = 5) -> None:
    """Display a figure as a static image when maidr does not support it.

    Emits a warning and renders the figure using IPython's display system
    (in notebooks) or by saving a temporary PNG and opening it in the
    default browser (in scripts).

    Parameters
    ----------
    fig : Figure
        The matplotlib figure to display.
    stacklevel : int, default 5
        Passed to :func:`warn_unsupported`, which hands it to
        :func:`warnings.warn`: 1 names the line in ``warn_unsupported``, 2
        the line here, and each level after that one frame further out.
        :func:`show_figure` counts it for its own callers.
    """
    # The level counts the frames between the warning and the line it
    # names: user code → plt.show() → backend.show() → show_figure()
    # → _show_fallback() → warn_unsupported() → warnings.warn(). If the
    # internal call chain changes, ``show_figure``'s count must be updated.
    #
    # The sentence itself lives in `maidr.util.fallback` because the API
    # entry points need the same one: `maidr.render()`, `maidr.show()` and
    # `maidr.save_html()` used to raise a bare KeyError where this path
    # warned and drew a picture (#443). Two copies of a message that must
    # agree is how the previous hand-listed one drifted.
    warn_unsupported(fig, stacklevel=stacklevel)

    from maidr.util.environment import Environment

    if Environment.is_notebook():
        try:
            from maidr.util.notebook_display import display_plain

            # The image the notebook shows of the figure without maidr, at
            # the size it shows it; a PNG of our own where no formatter for
            # a figure is registered to make that image.
            if display_plain(fig):
                return

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
