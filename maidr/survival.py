"""Kaplan-Meier survival curves, read as maidr.js ``survival`` layers.

A survival curve drawn with ``ax.step`` is read as a ``step`` layer, which
announces the probability at each time and nothing else: not which times are
censored, nor the confidence band, nor the median survival the figure is quoted
by. :func:`plot_survival` draws the curve from its numbers and registers it as
a ``survival`` layer, which carries all of them. ``survival`` is an
experimental type; see ``docs/stability.qmd``.

lifelines' ``KaplanMeierFitter.plot_survival_function`` is read the same way
by ``maidr/patch/survival.py``, through :func:`register_arm`.
"""

from __future__ import annotations

import threading
from typing import Any, Iterable, Optional

import matplotlib as mpl
import numpy as np
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.context_manager import ContextManager
from maidr.core.enum import MaidrKey
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.survival import SurvivalArm, SurvivalPlot
from maidr.exception import UnsupportedPlotError

__all__ = ["keep_every_vertex", "plot_survival", "register_arm", "survival_points"]

#: Held across "is there a survival layer on this axes, and if not make one",
#: for the reason ``maidr/patch/roc.py`` gives: two threads drawing onto one
#: fresh axes could otherwise both find none and split the arms in two.
_arms_lock = threading.Lock()


class _EveryVertexLine(Line2D):
    """
    A line drawn with every vertex it was given.

    matplotlib simplifies a path of 128 vertices or more as it draws it,
    merging collinear segments -- on a staircase, a time where the curve does
    not step, which is every censored time. maidr.js pairs a step path's
    vertices with the points (``2N - 1`` of them), so a merged vertex moves
    every highlight after it. The path is rebuilt with simplification off
    whenever the line is drawn, so a later ``set_data`` cannot bring it back.
    """

    def draw(self, renderer: Any) -> None:
        """Draw the line with path simplification off."""
        with mpl.rc_context({"path.simplify": False}):
            self.recache_always()
            super().draw(renderer)


def keep_every_vertex(line: Line2D) -> None:
    """
    Have a drawn line keep every vertex of its path in the SVG.

    Parameters
    ----------
    line : Line2D
        A plain ``Line2D``, as ``ax.plot`` returns it. Its class is swapped
        for a subclass that adds no state, so everything already set on it
        stands.
    """
    if type(line) is Line2D:
        line.__class__ = _EveryVertexLine


def _finite_1d(name: str, values: Any) -> np.ndarray:
    """
    One argument as a flat array of finite floats.

    Parameters
    ----------
    name : str
        The argument's name, for the error.
    values : array_like
        What was passed.

    Returns
    -------
    numpy.ndarray
        The values as a 1-D float array.

    Raises
    ------
    ValueError
        If a value is not a finite number.
    """
    array = np.asarray(values, dtype=float).reshape(-1)
    if not np.isfinite(array).all():
        raise ValueError(f"`{name}` holds values that are NaN or infinite.")
    return array


def survival_points(
    time: Any,
    survival: Any,
    *,
    censored: Optional[Iterable[float]] = None,
    lower: Any = None,
    upper: Any = None,
    name: Optional[str] = None,
) -> list[dict]:
    """
    A curve's points as a ``survival`` layer carries them.

    A censoring time that is already one of ``time`` flags that point. One
    that is not is added as a point of its own, at the survival in force then,
    because the curve does not step at a censoring and maidr.js announces the
    censored time where the reader reaches it.

    Parameters
    ----------
    time : array_like
        The times at which the estimate is stated, strictly increasing. The
        estimate holds from each time until the next.
    survival : array_like
        The survival probability from each time on.
    censored : iterable of float, optional
        The times at which a subject left without the event happening. None
        may come before the first of ``time``.
    lower, upper : array_like, optional
        The confidence band at each time. Both or neither.
    name : str, optional
        The arm, carried as ``z`` on every point.

    Returns
    -------
    list of dict
        One ``{x, y}`` per time, with ``censored``, ``yMin``/``yMax`` and
        ``z`` where they apply.

    Raises
    ------
    ValueError
        If the arrays are empty or differ in length, ``time`` is not strictly
        increasing, a value is not finite, only one of ``lower`` and ``upper``
        is given, or a censoring time comes before the first time.
    """
    t = _finite_1d("time", time)
    s = _finite_1d("survival", survival)
    if t.size == 0:
        raise ValueError("A survival curve needs at least one time.")
    if s.shape != t.shape:
        raise ValueError(
            f"`survival` has {s.size} values and `time` has {t.size}; "
            "they pair one to one."
        )
    if np.any(np.diff(t) <= 0):
        raise ValueError("`time` must be strictly increasing.")
    if (lower is None) != (upper is None):
        raise ValueError("Pass both `lower` and `upper` for a band, or neither.")
    band = None
    if lower is not None:
        lo = _finite_1d("lower", lower)
        hi = _finite_1d("upper", upper)
        if lo.shape != t.shape or hi.shape != t.shape:
            raise ValueError("`lower` and `upper` need one value per time.")
        band = (lo, hi)

    times = t.tolist()
    flags = [False] * len(times)
    index_of = list(range(len(times)))
    if censored is not None:
        for c in sorted(set(_finite_1d("censored", list(censored)).tolist())):
            at = int(np.searchsorted(t, c, side="right")) - 1
            if at < 0:
                raise ValueError(
                    f"Censoring time {c:g} comes before the curve's first time "
                    f"{t[0]:g}."
                )
            if t[at] == c:
                flags[times.index(c)] = True
                continue
            # Inserted after every point at or before it, which the sorted
            # walk keeps in time order.
            position = int(np.searchsorted(times, c, side="right"))
            times.insert(position, c)
            flags.insert(position, True)
            index_of.insert(position, at)

    points = []
    for x, flag, source in zip(times, flags, index_of):
        point: dict = {MaidrKey.X.value: x, MaidrKey.Y.value: float(s[source])}
        if name is not None:
            point[MaidrKey.Z.value] = name
        if band is not None:
            point[MaidrKey.Y_MIN.value] = float(band[0][source])
            point[MaidrKey.Y_MAX.value] = float(band[1][source])
        if flag:
            point[MaidrKey.CENSORED.value] = True
        points.append(point)
    return points


def register_arm(ax: Axes, arm: SurvivalArm) -> None:
    """
    Add a curve to the axes' survival layer, making the layer if it is the first.

    Parameters
    ----------
    ax : Axes
        The axes the curve is drawn on.
    arm : SurvivalArm
        The curve.
    """
    with _arms_lock:
        layer = _layer_of(ax)
        if layer is not None:
            layer.add_arm(arm)
        else:
            FigureManager.add_plot(SurvivalPlot(ax, [arm]))


def _layer_of(ax: Axes) -> Optional[SurvivalPlot]:
    """
    The survival layer already registered for an axes, when there is one.

    Parameters
    ----------
    ax : Axes
        The axes being drawn on.

    Returns
    -------
    SurvivalPlot or None
        The layer to extend, or None for the axes' first curve.
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
            if isinstance(plot, SurvivalPlot) and plot.ax is ax
        ),
        None,
    )


def plot_survival(
    time: Any,
    survival: Any,
    *,
    censored: Optional[Iterable[float]] = None,
    lower: Any = None,
    upper: Any = None,
    label: Optional[str] = None,
    ax: Optional[Axes] = None,
    show_censors: bool = True,
    ci_alpha: float = 0.25,
    **kwargs: Any,
) -> Axes:
    """
    Draw a Kaplan-Meier curve and read it as a ``survival`` layer.

    The curve is drawn as ``ax.step(time, survival, where="post")`` draws it,
    with the band as a shaded step and each censoring time as a tick on the
    curve. Several calls on one axes draw the arms of one chart, which a
    reader moves between with Up and Down.

    Parameters
    ----------
    time : array_like
        The times at which the estimate is stated, strictly increasing,
        usually starting at 0. The estimate holds from each time until the
        next.
    survival : array_like
        The survival probability from each time on.
    censored : iterable of float, optional
        The times at which a subject left the study without the event
        happening. The curve does not step there; each is announced as
        censored, and the reader can move between them with the rotor.
    lower, upper : array_like, optional
        The confidence band at each time, announced after the estimate.
    label : str, optional
        The arm's name, in the legend and in what is announced.
    ax : Axes, optional
        Where to draw; the current axes by default.
    show_censors : bool, default True
        Whether to draw the censoring ticks. They are announced either way.
    ci_alpha : float, default 0.25
        The band's opacity.
    **kwargs : Any
        Passed to ``ax.plot`` for the curve, such as ``color``.

    Returns
    -------
    Axes
        The axes drawn on.

    Raises
    ------
    ValueError
        As :func:`survival_points` raises.

    Notes
    -----
    ``survival`` is an experimental type; see ``docs/stability.qmd``.

    Examples
    --------
    >>> import matplotlib.pyplot as plt
    >>> import maidr
    >>> fig, ax = plt.subplots()
    >>> maidr.plot_survival(
    ...     [0, 3, 6, 9], [1.0, 0.88, 0.71, 0.5], censored=[7], label="Control", ax=ax
    ... )  # doctest: +SKIP
    >>> maidr.show(fig)  # doctest: +SKIP
    """
    points = survival_points(
        time, survival, censored=censored, lower=lower, upper=upper, name=label
    )
    if ax is None:
        import matplotlib.pyplot as plt

        ax = plt.gca()

    xs = [point[MaidrKey.X.value] for point in points]
    ys = [point[MaidrKey.Y.value] for point in points]
    # Drawn inside the internal context so the patched `plot` and
    # `fill_between` register nothing of their own: the curve is read from
    # these numbers, as one `survival` layer.
    with ContextManager.set_internal_context():
        (line,) = ax.plot(xs, ys, drawstyle="steps-post", label=label, **kwargs)
        keep_every_vertex(line)
        color = line.get_color()
        if lower is not None:
            ax.fill_between(
                xs,
                [point[MaidrKey.Y_MIN.value] for point in points],
                [point[MaidrKey.Y_MAX.value] for point in points],
                step="post",
                alpha=ci_alpha,
                color=color,
                linewidth=0,
            )
        ticks = [p for p in points if p.get(MaidrKey.CENSORED.value)]
        if show_censors and ticks:
            ax.add_line(
                Line2D(
                    [p[MaidrKey.X.value] for p in ticks],
                    [p[MaidrKey.Y.value] for p in ticks],
                    linestyle="none",
                    marker="|",
                    markersize=10,
                    markeredgewidth=1.5,
                    color=color,
                )
            )

    register_arm(ax, SurvivalArm(line, points))
    return ax
