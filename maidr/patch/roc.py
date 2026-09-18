from __future__ import annotations

import threading
from typing import Any

import wrapt
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.roc import DRAWN_CURVES, RocCurve, RocPlot
from maidr.exception import UnsupportedPlotError
from maidr.patch.common import _draw_quietly

#: Held across the whole "is there a ROC layer already, and if not make one"
#: decision, for the reason ``maidr/patch/gantt.py`` gives: two threads
#: drawing onto one fresh axes could otherwise both find no layer and each
#: register one, which is the split-into-two-charts outcome this exists to
#: prevent. ``FigureManager._lock`` cannot serve, since ``create_maidr``
#: takes it again.
_curves_lock = threading.Lock()


def roc(wrapped, instance, args, kwargs) -> Any:
    """
    Draw a patched ``RocCurveDisplay.plot`` and register the curves it drew.

    Every way scikit-learn draws a ROC curve ends here: ``from_estimator``,
    ``from_predictions`` and ``from_cv_results`` each build a display and
    call its ``plot()``, and so does a hand-built ``RocCurveDisplay(fpr=,
    tpr=)``. Inside, ``plot()`` calls ``ax.plot(fpr, tpr)`` once per curve
    and, when asked, once more for the chance diagonal.

    The internal context is what makes this a *replacement* reading rather
    than an extra one. Both of those ``ax.plot`` calls are patched by
    ``maidr.patch.lineplot``, and left alone they register a line layer --
    with the chance diagonal announced as a second series. Drawing inside the
    context keeps that patch out, and the display is read instead: its rates,
    its computed area and the name the caller gave, none of which the line
    carries.

    Several ``plot(ax=ax)`` calls on one axes are one chart with several
    curves, so a later call extends the layer the first one registered
    rather than registering its own.

    Parameters
    ----------
    wrapped : Callable
        ``RocCurveDisplay.plot``, bound to the display.
    instance : Any
        The display being plotted.
    args, kwargs : Any
        As passed by the caller.

    Returns
    -------
    Any
        Whatever ``plot`` returned -- the display itself.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    with ContextManager.set_internal_context():
        display = _draw_quietly(wrapped, args, kwargs)

    curves = _curves_of(display, kwargs.get("name"))
    if not curves:
        return display

    ax = getattr(display, "ax_", None)
    if not isinstance(ax, Axes):
        ax = FigureManager.get_axes(curves[0].line)
    if ax is None:
        return display

    with _curves_lock:
        layer = _layer_of(ax)
        if layer is not None:
            layer.add_curves(curves)
        else:
            FigureManager.create_maidr(ax, PlotType.ROC, **{DRAWN_CURVES: curves})

    return display


def _as_list(value: Any, count: int) -> list:
    """
    Spread one display attribute over its curves.

    A display holding one curve keeps ``fpr``, ``tpr``, ``roc_auc`` and
    ``name`` as scalars; one holding several -- ``from_cv_results``, or a
    list handed to the constructor -- keeps each as a list, one entry per
    curve. Either way this answers one entry per curve.
    """
    if isinstance(value, (list, tuple)):
        return list(value) if len(value) == count else [None] * count
    return [value] * count


def _curves_of(display: Any, name: Any) -> list[RocCurve]:
    """
    The curves a display drew, as the layer reads them.

    Parameters
    ----------
    display : Any
        The plotted ``RocCurveDisplay``.
    name : Any
        The ``name`` the caller passed to ``plot()``, which names the curve
        ahead of the one the display was built with.

    Returns
    -------
    list of RocCurve
        One per line the display drew, in drawing order; empty when the
        display carries no line at all.
    """
    drawn = getattr(display, "line_", None)
    lines = [
        line
        for line in (drawn if isinstance(drawn, (list, tuple)) else [drawn])
        if isinstance(line, Line2D)
    ]
    if not lines:
        return []

    count = len(lines)
    fprs = _as_list(getattr(display, "fpr", None), count)
    tprs = _as_list(getattr(display, "tpr", None), count)
    areas = _as_list(getattr(display, "roc_auc", None), count)
    # `name` is the display's field since scikit-learn 1.7 and
    # `estimator_name` before it; the caller's `name=` wins over both, the
    # way it wins in the legend.
    given = name if name is not None else getattr(display, "name", None)
    if given is None:
        given = getattr(display, "estimator_name", None)
    names = _as_list(given, count)

    # With several curves the display may have been handed the rates as one
    # array each; then there is nothing to pair them with per line, and the
    # curve is read off the line's own data rather than guessed at.
    curves = []
    for line, fpr, tpr, area, label in zip(lines, fprs, tprs, areas, names):
        if fpr is None or tpr is None:
            fpr, tpr = line.get_xdata(), line.get_ydata()
        curves.append(RocCurve(line, fpr, tpr, area, label))
    return curves


def _layer_of(ax: Axes) -> RocPlot | None:
    """
    The ROC layer already registered for an axes, when there is one.

    Parameters
    ----------
    ax : Axes
        The axes the display drew on.

    Returns
    -------
    RocPlot or None
        The layer to extend, or None when this is the axes' first curve.
    """
    figure = ax.get_figure()
    if figure is None:
        return None
    try:
        registered = FigureManager.get_maidr(figure)
    except UnsupportedPlotError:
        # Nothing registered for this figure yet: the ordinary first call.
        return None
    return next(
        (
            plot
            for plot in registered.plots
            if isinstance(plot, RocPlot) and plot.ax is ax
        ),
        None,
    )


@wrapt.when_imported("sklearn.metrics")
def _patch_roc_curve_display(module: Any) -> None:
    """
    Wrap ``RocCurveDisplay.plot`` once ``sklearn.metrics`` is imported.

    A post-import hook rather than an import, so that scikit-learn stays
    optional: nothing in maidr imports it, a user without it is unaffected,
    and a user who imported it before maidr is covered too -- ``wrapt`` runs
    the hook at once for a module already in ``sys.modules``.
    """
    display = getattr(module, "RocCurveDisplay", None)
    if display is None or not hasattr(display, "plot"):
        return
    wrapt.wrap_function_wrapper(display, "plot", roc)
