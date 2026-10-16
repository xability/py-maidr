"""Read lifelines' Kaplan-Meier plots as ``survival`` layers.

``KaplanMeierFitter.plot_survival_function`` (and ``plot``, which calls it)
draws the estimate through pandas' ``DataFrame.plot`` with
``drawstyle="steps-post"``, the band through ``ax.fill_between`` and the
censoring marks, when asked, through ``ax.plot``. Left alone, those patched
calls register a ``step`` layer and a band, and the censoring the fitter knows
is lost. This wraps the method so the fitter is read instead.

A post-import hook rather than an import, as ``maidr/patch/roc.py`` reaches
scikit-learn: nothing in maidr imports lifelines, and a user without it is
unaffected.
"""

from __future__ import annotations

from typing import Any, Optional

import wrapt
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.context_manager import ContextManager
from maidr.core.enum import MaidrKey
from maidr.core.plot.survival import SurvivalArm
from maidr.patch.common import _draw_quietly
from maidr.survival import keep_every_vertex, register_arm
from maidr.util.step_utils import is_step_drawstyle


def kaplan_meier(wrapped: Any, instance: Any, args: tuple, kwargs: dict) -> Any:
    """
    Draw a patched ``plot_survival_function`` and register the curve it drew.

    Parameters
    ----------
    wrapped : Callable
        ``KaplanMeierFitter.plot_survival_function``, bound to the fitter.
    instance : Any
        The fitted ``KaplanMeierFitter``.
    args, kwargs : Any
        As passed by the caller.

    Returns
    -------
    Any
        Whatever the method returned -- the axes.
    """
    # An interval-censored fit is drawn as a plain `steps-pre` line with no
    # censoring to state, so it keeps its ordinary reading.
    censoring = getattr(getattr(instance, "_censoring_type", None), "value", None)
    if ContextManager.is_internal_context() or censoring == "interval":
        return wrapped(*args, **kwargs)

    ax = kwargs.get("ax")
    if not isinstance(ax, Axes):
        # Where lifelines draws when it is given no axes.
        import matplotlib.pyplot as plt

        ax = plt.gca()
    before = set(ax.get_lines())
    with ContextManager.set_internal_context():
        result = _draw_quietly(wrapped, args, kwargs)

    if not isinstance(result, Axes):
        return result
    drawn = [line for line in result.get_lines() if line not in before]
    line = _curve_line(drawn)
    if line is not None:
        points = _points(instance, line, ci_show=kwargs.get("ci_show", True))
        if points:
            keep_every_vertex(line)
            register_arm(result, SurvivalArm(line, points))
    return result


def _curve_line(lines: list[Line2D]) -> Optional[Line2D]:
    """
    The line that draws the estimate, among those the call drew.

    lifelines draws the censoring marks first, with no line between them, then
    the estimate, then -- with ``ci_only_lines`` -- the band's two edges. So
    the estimate is the first new step line that has a line style.

    Parameters
    ----------
    lines : list of Line2D
        The lines the call drew, in drawing order.

    Returns
    -------
    Line2D or None
        The estimate's line, or None when none was drawn.
    """
    return next(
        (
            line
            for line in lines
            if is_step_drawstyle(line.get_drawstyle())
            and line.get_linestyle() not in ("None", "none", "", " ")
        ),
        None,
    )


def _column(frame: Any, index: int) -> dict[float, float]:
    """One column of a fitter's frame as ``{time: value}``, or empty."""
    try:
        values = frame.iloc[:, index]
        return {float(t): float(v) for t, v in zip(frame.index.values, values.values)}
    except (AttributeError, IndexError, TypeError, ValueError):
        return {}


def _points(fitter: Any, line: Line2D, *, ci_show: bool) -> list[dict]:
    """
    The curve as drawn, with the fitter's censoring and band at each time.

    Read off the line's own vertices, so a ``loc`` or ``iloc`` slice is the
    slice the reader hears, and annotated from the fitter by time.

    Parameters
    ----------
    fitter : Any
        The fitted ``KaplanMeierFitter``.
    line : Line2D
        The estimate's line.
    ci_show : bool
        Whether the band was drawn, and so is announced.

    Returns
    -------
    list of dict
        The ``survival`` points, empty when the line holds none.
    """
    try:
        xs = [float(x) for x in line.get_xdata()]
        ys = [float(y) for y in line.get_ydata()]
    except (TypeError, ValueError):
        return []

    censored: set[float] = set()
    table = getattr(fitter, "event_table", None)
    try:
        censored = {float(t) for t in table.index[table["censored"] > 0]}
    except (AttributeError, KeyError, TypeError, ValueError):
        pass

    lower: dict[float, float] = {}
    upper: dict[float, float] = {}
    if ci_show:
        band = getattr(fitter, "confidence_interval_survival_function_", None)
        if band is None:
            band = getattr(fitter, "confidence_interval_", None)
        lower, upper = _column(band, 0), _column(band, 1)

    name = getattr(fitter, "label", None) or getattr(fitter, "_label", None)
    name = str(name) if name is not None else None
    points = []
    for x, y in zip(xs, ys):
        point: dict = {MaidrKey.X.value: x, MaidrKey.Y.value: y}
        if name:
            point[MaidrKey.Z.value] = name
        if x in lower and x in upper:
            point[MaidrKey.Y_MIN.value] = lower[x]
            point[MaidrKey.Y_MAX.value] = upper[x]
        if x in censored:
            point[MaidrKey.CENSORED.value] = True
        points.append(point)
    return points


@wrapt.when_imported("lifelines")
def _patch_kaplan_meier(module: Any) -> None:
    """
    Wrap ``KaplanMeierFitter.plot_survival_function`` once lifelines is imported.

    ``plot`` is the deprecated alias that calls it, so wrapping this one
    covers both.
    """
    fitter = getattr(module, "KaplanMeierFitter", None)
    if fitter is None or not hasattr(fitter, "plot_survival_function"):
        return
    wrapt.wrap_function_wrapper(fitter, "plot_survival_function", kaplan_meier)
