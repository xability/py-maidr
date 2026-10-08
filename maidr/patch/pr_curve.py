from __future__ import annotations

import threading
from typing import Any

import wrapt
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.pr_curve import DRAWN_CURVES, PrCurve, PrCurvePlot
from maidr.exception import UnsupportedPlotError
from maidr.patch.common import _draw_quietly
from maidr.patch.roc import _as_list, _rates

#: Held across "is there a PR layer already, and if not make one", for the
#: reason ``maidr/patch/roc.py`` gives its own lock.
_curves_lock = threading.Lock()


def pr_curve(wrapped, instance, args, kwargs) -> Any:
    """
    Draw a patched ``PrecisionRecallDisplay.plot`` and register its curves.

    Every way scikit-learn draws a precision-recall curve ends here:
    ``from_estimator``, ``from_predictions`` and ``from_cv_results`` each
    build a display and call its ``plot()``, and so does a hand-built
    ``PrecisionRecallDisplay(precision=, recall=)``. Inside, ``plot()`` calls
    ``ax.plot(recall, precision, drawstyle="steps-post")`` once per curve and,
    when asked, once more for the chance level.

    Drawn inside the internal context, as ``maidr.patch.roc`` draws a ROC
    display, so the line patch does not register those calls as a step layer
    with the chance level for a second series; the display is read instead.

    Parameters
    ----------
    wrapped : Callable
        ``PrecisionRecallDisplay.plot``, bound to the display.
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
            FigureManager.create_maidr(ax, PlotType.PR_CURVE, **{DRAWN_CURVES: curves})

    return display


def _curves_of(display: Any, name: Any) -> list[PrCurve]:
    """
    The curves a display drew, as the layer reads them.

    Parameters
    ----------
    display : Any
        The plotted ``PrecisionRecallDisplay``.
    name : Any
        The ``name`` the caller passed to ``plot()``, which names the curve
        ahead of the one the display was built with.

    Returns
    -------
    list of PrCurve
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
    precisions = _rates(getattr(display, "precision", None), count)
    recalls = _rates(getattr(display, "recall", None), count)
    averages = _as_list(getattr(display, "average_precision", None), count)
    prevalences = _as_list(getattr(display, "prevalence_pos_label", None), count)
    # `name` since scikit-learn 1.7, `estimator_name` before it; the caller's
    # `name=` wins over both, as it does in the legend.
    given = name if name is not None else getattr(display, "name", None)
    if given is None:
        given = getattr(display, "estimator_name", None)
    names = _as_list(given, count)

    curves = []
    for line, precision, recall, average, prevalence, label in zip(
        lines, precisions, recalls, averages, prevalences, names
    ):
        # As for a ROC display: rates handed over as one array for several
        # lines cannot be paired with them, so each is read off its line.
        if precision is None or recall is None:
            recall, precision = line.get_xdata(), line.get_ydata()
        curves.append(PrCurve(line, precision, recall, average, prevalence, label))
    return curves


def _layer_of(ax: Axes) -> PrCurvePlot | None:
    """
    The PR layer already registered for an axes, when there is one.

    Parameters
    ----------
    ax : Axes
        The axes the display drew on.

    Returns
    -------
    PrCurvePlot or None
        The layer to extend, or None when this is the axes' first curve.
    """
    figure = ax.get_figure()
    if figure is None:
        return None
    try:
        registered = FigureManager.get_maidr(figure)
    except UnsupportedPlotError:
        return None
    return next(
        (
            plot
            for plot in registered.plots
            if isinstance(plot, PrCurvePlot) and plot.ax is ax
        ),
        None,
    )


@wrapt.when_imported("sklearn.metrics")
def _patch_precision_recall_display(module: Any) -> None:
    """
    Wrap ``PrecisionRecallDisplay.plot`` once ``sklearn.metrics`` is imported.

    A post-import hook, as for ``RocCurveDisplay``, so scikit-learn stays
    optional.
    """
    display = getattr(module, "PrecisionRecallDisplay", None)
    if display is None or not hasattr(display, "plot"):
        return
    wrapt.wrap_function_wrapper(display, "plot", pr_curve)
