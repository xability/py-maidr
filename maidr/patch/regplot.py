from __future__ import annotations

import uuid
import numpy as np
import wrapt
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection
from matplotlib.lines import Line2D

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.enum.smooth_keywords import SMOOTH_KEYWORDS
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.scatterplot import DRAWN_POINTS
from maidr.patch.common import (
    MAX_INTERVAL_VERTICES,
    _draw_quietly,
    common,
    prospective_axes,
    wrap_seaborn,
)


def _is_interval_bar(line: Line2D) -> bool:
    """
    Whether a line is the confidence bar around one binned estimate.

    ``sns.regplot(x_estimator=...)`` collapses each x to an estimate and draws
    an interval around it, as an ordinary line. So the bar is a *vertical*
    segment: every vertex at one x, spanning the bound. The fitted curve is the
    opposite -- a hundred distinct x values across the axis -- which makes the
    two separable without asking seaborn anything.

    Asked of the geometry rather than of the label. The label is what the old
    sweep used, and `_child0`/`_child1` is what matplotlib names *any*
    unlabelled artist rather than something a regression line is distinguished
    by, so the bars answered to it and so did a line the caller drew
    beforehand (#451).

    The single-x test is the part that depends on `regplot` having no
    `capsize`, which it does not -- `pointplot` takes one and `regplot`'s
    signature has no equivalent. A capped bar draws its caps at two further x
    values, so were one ever added here the width test would fail first and
    the bar would be described as a curve; the vertex ceiling is only an upper
    bound and would not be what gave way.

    Parameters
    ----------
    line : Line2D
        A line this call drew.

    Returns
    -------
    bool
        True when the line is a single-x segment short enough to be one bar.
    """
    xs = np.asarray(line.get_xdata(), dtype=float)
    finite = xs[np.isfinite(xs)]
    if finite.size < 2 or finite.size > MAX_INTERVAL_VERTICES:
        return False
    return bool(np.ptp(finite) == 0)


def _interval_position(line: Line2D) -> float:
    """The single x an interval bar stands at."""
    xs = np.asarray(line.get_xdata(), dtype=float)
    return float(xs[np.isfinite(xs)][0])


def _paired_estimates(
    collection: PathCollection, intervals: list[Line2D]
) -> tuple[Line2D, list[Line2D]] | None:
    """
    Match each interval bar to the estimate it was drawn around.

    Returns the estimates as a ``Line2D`` because that is what
    :class:`~maidr.core.plot.pointplot.PointPlot` reads, and it zips its
    estimates against its intervals positionally -- so both come back in one x
    order rather than in whichever order the artists happen to sit in.

    Verified rather than assumed, the way ``pointplot``'s own split is: the
    counts must agree and every bar must stand at an estimate. When they do
    not, the caller falls back to describing the scatter and the curves
    separately, which is the reading that was there before and is merely
    incomplete rather than wrong.

    Parameters
    ----------
    collection : PathCollection
        The estimates this call drew.
    intervals : list of Line2D
        The bars this call drew.

    Returns
    -------
    tuple or None
        ``(estimates, intervals)`` in one x order, or None when they do not
        pair up.
    """
    offsets = np.asarray(collection.get_offsets(), dtype=float)
    if offsets.ndim != 2 or offsets.shape[0] != len(intervals):
        return None

    ordered_offsets = offsets[np.argsort(offsets[:, 0])]
    ordered_intervals = sorted(intervals, key=_interval_position)

    for (x, _), interval in zip(ordered_offsets, ordered_intervals):
        # A bar is drawn *at* its estimate, so any disagreement past floating
        # point means these are not the artists they look like.
        if not np.isclose(x, _interval_position(interval)):
            return None

    estimates = Line2D(ordered_offsets[:, 0], ordered_offsets[:, 1])
    estimates.axes = collection.axes
    return estimates, ordered_intervals


def _register_curves(axes: Axes, curves: list[Line2D], instance, args, kwargs) -> None:
    """Register each fitted curve this call drew as a SMOOTH layer."""
    for line in curves:
        if line.get_gid() is None:
            line.set_gid(f"maidr-{uuid.uuid4()}")
        common(
            PlotType.SMOOTH,
            lambda *a, **k: axes,
            instance,
            args,
            dict(kwargs, regression_line=line),
        )


def regplot(wrapped, instance, args, kwargs) -> Axes:
    """
    Register ``seaborn.regplot`` as the layers it actually drew.

    Two readings were wrong, and both came of asking the *axes* which of its
    lines were fits rather than knowing which lines this call drew (#451).

    **Each confidence bar was a fitted curve of its own.**
    ``regplot(x_estimator=...)`` collapses each x to an estimate and draws an
    interval around it; those intervals are ordinary lines, so every one
    registered as a ``smooth`` layer::

        sns.regplot(df, x="dose", y="resp", x_estimator=np.mean)
          point(4), smooth(2), smooth(2), smooth(2), smooth(2), smooth(30)

    Six layers for four estimates and one line, and the count scales with the
    data -- ``x_estimator`` bins by unique x when ``x_bins`` is absent, so
    sixty distinct values give sixty-one layers. `smooth` means a computed
    fit, and a vertical bar is not one; the reader who navigates into it hears
    a curve with two points at the same x. And the estimates sat in their own
    layer, so the uncertainty was unreachable from the value it belonged to.

    **A line drawn before the regplot was announced twice.** The sweep matched
    any label starting with ``_child``, which is what matplotlib names *any*
    unlabelled artist::

        ax.plot(...); sns.regplot(...)   line, point, smooth, smooth

    The caller's own series, once correctly as `line` and again as a model of
    itself. Order decided it: a line added *after* the regplot was safe, and
    "plot the series, overlay a fit" is the ordinary way round.

    Both are answered by the before/after snapshot -- the idiom
    ``maidr/patch/lineplot.py`` and ``boxenplot.py`` already use -- plus a
    geometric split of what it returns. An interval bar stands at one x; the
    fitted curve spans the axis.

    The estimates and their intervals then travel as one ERRORBAR layer,
    through the same :class:`~maidr.core.plot.pointplot.PointPlot` that
    ``sns.pointplot`` uses, so ``yMin``/``yMax`` sit on the sample they bound.

    Parameters
    ----------
    wrapped : Callable
        The original ``seaborn.regplot``.
    instance : Any
        Unused; seaborn's plotting functions are module level.
    args, kwargs
        The caller's arguments, passed through untouched.

    Returns
    -------
    Axes
        Whatever seaborn returned.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    # Sets, not lists: membership is asked once per artist below, and the
    # list form is the quadratic scan `lineplot.py` and `boxenplot.py` already
    # moved off for this reason. The artists themselves rather than their
    # `id()`s, which keeps every one alive for the comparison -- an id is only
    # unique while its object is -- and costs nothing, since an Artist hashes
    # by identity.
    target = prospective_axes(kwargs)
    before_lines = set(target.lines) if target is not None else set()
    before_collections = set(target.collections) if target is not None else set()

    with ContextManager.set_internal_context():
        drawn = _draw_quietly(wrapped, args, kwargs)

    axes = drawn if isinstance(drawn, Axes) else getattr(drawn, "axes", None)
    if not isinstance(axes, Axes):
        return drawn

    added_lines = [line for line in axes.lines if line not in before_lines]
    intervals = [line for line in added_lines if _is_interval_bar(line)]
    curves = [line for line in added_lines if line not in intervals]
    points = next(
        (
            collection
            for collection in axes.collections
            if isinstance(collection, PathCollection)
            and collection not in before_collections
        ),
        None,
    )

    paired = (
        _paired_estimates(points, intervals)
        if points is not None and intervals
        else None
    )
    if paired is not None:
        estimates, ordered = paired
        FigureManager.create_maidr(
            axes, PlotType.ERRORBAR, estimate=estimates, intervals=ordered
        )
        described = curves
    else:
        if points is not None:
            # The scatter's own collection rather than a sweep of the axes, so
            # a regplot overlaid on another scatter reads its own points
            # (#426).
            FigureManager.create_maidr(
                axes, PlotType.SCATTER, **{DRAWN_POINTS: points}
            )
        # Whatever could not be paired is still described. Mistyping a bar as
        # a curve is the reading this change replaces and is bad; dropping it
        # is worse, because a layer that is not there cannot be navigated to
        # and nothing says it is missing. Written so no branch can drop one --
        # the arm that skipped them needed `scatter=False` *and* binning, which
        # seaborn cannot produce today, and a guard nothing reaches is exactly
        # the kind that stops holding when an upstream release moves.
        described = intervals + curves

    _register_curves(axes, described, instance, args, kwargs)

    return drawn


def patched_plot(wrapped, instance, args, kwargs):
    """
    Patch matplotlib Axes.plot to register SMOOTH layers for MAIDR if the label matches SMOOTH_KEYWORDS.
    """
    # Call the original plot function
    lines = _draw_quietly(wrapped, args, kwargs)

    # Check each line for smooth keywords and register if found
    for line in lines:
        if isinstance(line, Line2D):
            label = line.get_label() or ""
            label_str = str(label)
            # Detect if this is a smooth/regression line by label
            if any(key in label_str.lower() for key in SMOOTH_KEYWORDS):
                # Assign a unique gid if not already set
                if line.get_gid() is None:
                    new_gid = f"maidr-{uuid.uuid4()}"
                    line.set_gid(new_gid)
                # Register as a smooth layer
                common(
                    PlotType.SMOOTH,
                    lambda *a, **k: instance,
                    instance,
                    args,
                    dict(kwargs, regression_line=line),
                )

    return lines


# Patch seaborn function.
wrap_seaborn("regplot", regplot)
# Patch matplotlib Axes.plot for smooth line detection/registration
wrapt.wrap_function_wrapper(Axes, "plot", patched_plot)
