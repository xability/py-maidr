"""
Custom matplotlib backend that renders plots accessibly via maidr.

This backend delegates rendering to the Agg backend but overrides the
``show()`` function so that ``plt.show()`` displays accessible maidr HTML
output (with sonification, braille, and tactile support) instead of a
static image window.

The backend is automatically activated when ``import maidr`` is executed.
Users can also set it manually::

    import matplotlib
    matplotlib.use("module://maidr.backend")
"""

from __future__ import annotations

from matplotlib._pylab_helpers import Gcf
from matplotlib.backends.backend_agg import FigureCanvasAgg

FigureCanvas = FigureCanvasAgg
FigureManager = FigureCanvasAgg.manager_class


def show(*args, **kwargs) -> None:
    """
    Display all open figures using maidr's accessible renderer.

    This function is called by ``plt.show()``.  For every figure tracked by
    maidr's :class:`~maidr.core.figure_manager.FigureManager`, the accessible
    HTML representation is rendered.  Figures that are not tracked (e.g. those
    created without any supported plot type) are silently skipped.
    """
    from maidr.core.figure_manager import FigureManager as MaidrFigureManager

    managers = Gcf.get_all_fig_managers()
    if not managers:
        return

    for manager in list(managers):
        fig = manager.canvas.figure
        try:
            maidr_obj = MaidrFigureManager.get_maidr(fig)
            # clear_fig=False because the backend handles figure cleanup
            maidr_obj.show(clear_fig=False)
        except KeyError:
            # Figure not registered with maidr — skip it
            pass
        Gcf.destroy(manager.num)
