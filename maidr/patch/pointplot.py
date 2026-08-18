from __future__ import annotations

import numpy as np
import wrapt
from matplotlib.axes import Axes
from matplotlib.colors import to_rgba
from matplotlib.legend import Legend
from matplotlib.lines import Line2D

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import (
    MAX_INTERVAL_VERTICES,
    _draw_quietly,
    plotter_axes,
    plotter_panels,
    wrap_seaborn,
)

# The marker seaborn leaves on the lines it draws the intervals with. The
# estimate line carries a real one -- `"o"` by default, and the empty string
# when the caller turns it off, which is why this tests for the literal rather
# than for falsiness.
_INTERVAL_MARKER = "None"


def point(wrapped, instance, args, kwargs) -> Axes:
    """
    Draw ``seaborn.pointplot`` quietly and leave the reading to the plotter.

    Registration used to happen here and no longer does. ``sns.catplot(
    kind="point")`` reaches this function not at all -- it drives
    ``_CategoricalPlotter`` directly and imports nothing -- so its panels were
    left to the ``Axes.plot`` wrapper and arrived as ``line`` where this gives
    ``error_bar``. The estimates survived and the intervals did not (#448).
    :func:`sns_categorical_points` wraps the method both interfaces drive and
    registers there, through the same :func:`_register_point_layer`.

    What remains here is ``_draw_quietly`` over the whole seaborn call and the
    ``wrap_seaborn`` that keeps both bindings of the name wrapped. Nothing sets
    the internal context, which is what would silence the plotter patch; the
    ``Axes.plot`` calls it used to suppress are made inside ``plot_points``,
    and so inside the context that patch sets.

    Parameters
    ----------
    wrapped : Callable
        The original ``seaborn.pointplot``.
    instance : Any
        Unused; ``pointplot`` is a module-level function.
    args : tuple
        Positional arguments the caller passed.
    kwargs : dict
        Keyword arguments the caller passed.

    Returns
    -------
    Axes
        Whatever the wrapped function returned, unchanged.
    """
    return _draw_quietly(wrapped, args, kwargs)


def _register_point_layer(ax: Axes, existing: list[Line2D]) -> None:
    """
    Describe one panel of a point plot as the layer it actually drew.

    Split out of :func:`point` so ``sns.catplot(kind="point")`` can reuse it.
    ``catplot`` drives ``_CategoricalPlotter`` directly rather than importing
    ``pointplot``, so its panels reached neither name ``wrap_seaborn`` patches
    and were left to the ``Axes.plot`` wrapper -- which gave ``line`` where the
    axes-level function gives ``error_bar``. The estimates survived and the
    confidence intervals #246 added did not, so a reader was handed the means
    with no indication that the chart draws intervals around them, which is
    the thing a point plot exists to show (#448).

    Parameters
    ----------
    ax : Axes
        The panel to read.
    existing : list of Line2D
        The lines the panel held before the call, so this describes only the
        ones it drew.
    """
    drawn = [line for line in ax.lines if line not in existing]
    estimates, intervals = _split(drawn)

    if not estimates:
        # Nothing looked like an estimate line, so the split says nothing and
        # every drawn line is described -- the same fallback the verification
        # below takes, and for the same reason. Registering no layer at all
        # would leave the chart unreadable, which is a worse answer than the
        # one the generic wrapper already gave.
        if drawn:
            FigureManager.create_maidr(ax, PlotType.LINE, lines=drawn)
        return

    paired = _pairs_up(estimates, intervals)
    measured = any(_has_drawn_segment(line.get_xydata()) for line in intervals)

    if paired and measured and len(estimates) == 1:
        FigureManager.create_maidr(
            ax, PlotType.ERRORBAR, estimate=estimates[0], intervals=intervals
        )
        return

    if paired and measured:
        # A `hue` split the chart into groups. This used to fall through to
        # `line`, dropping the intervals rather than mis-assigning them,
        # because the MAIDR error bar layer carried a single flat series with
        # no field naming the group. maidr 4.4.0 gave it one --
        # `ErrorBarPoint[][]` with a `z`, xability/maidr#942 -- so the
        # intervals now have somewhere to go (#462).
        #
        # The estimates arrive one per group and the intervals estimate-major,
        # which `PointPlot` slices; `_pairs_up` has already checked the counts
        # divide evenly, so the slicing cannot straddle two groups.
        FigureManager.create_maidr(
            ax,
            PlotType.ERRORBAR,
            estimates=estimates,
            intervals=intervals,
            groups=_group_labels(ax, estimates),
        )
        return

    # Everything else is a line chart. `errorbar=None` draws no intervals to
    # carry, and a chart whose every group holds one observation has none to
    # draw. Both are still a repair over describing every drawn line, since
    # the interval polylines no longer travel as series of their own.
    #
    # A chart where only *some* groups have an interval takes the branch above,
    # not this one: the undrawable lines stay in the list to hold their
    # positions, and the layer omits the bound for those groups alone.
    FigureManager.create_maidr(
        ax, PlotType.LINE, lines=estimates if paired else drawn
    )


def _group_labels(ax: Axes, estimates: list[Line2D]) -> list[str]:
    """
    Name each ``hue`` group from the legend seaborn drew.

    The estimate lines carry `_child`-prefixed labels rather than the group
    names, so the legend is the only place the names appear.

    All the groups are named or none is. A legend that does not carry
    exactly one entry per drawn group is not one this can read, and naming
    the groups it does cover would leave the layer declaring an ``axes.z``
    while some of its series carried no ``z`` at all -- a shape the consumer
    has no reading for. Returning nothing instead gives the clean fallback:
    an unlabelled grouped chart, which is what the old ``line`` fallback
    produced anyway.

    **Which name goes on which group is settled by colour, not by
    position.** Reading the legend in order assumes seaborn lists its
    handles in the order it drew the lines -- true today, and not part of
    its public API, so a release that kept the count and reordered the
    legend would attach every name to the wrong series with the estimates
    and bounds all correct and nothing to indicate the swap (#502). The hue
    mapping that names a group is the same one that colours it, so matching
    each legend handle's colour to an estimate line's is independent
    evidence rather than the same assumption restated.

    Legend order remains the fallback, for the case where colour cannot
    tell the groups apart -- a monochrome palette, or one whose entries
    repeat. That is no worse than reading positionally always, which is
    what this did before.

    Parameters
    ----------
    ax : Axes
        The panel the point plot was drawn on.
    estimates : list of Line2D
        The estimate line of each drawn group, in drawing order.

    Returns
    -------
    list of str
        One name per group in drawing order, or empty when the legend
        cannot be read as naming exactly those groups.
    """
    legend = ax.get_legend()
    if legend is None:
        return []

    names = [text.get_text() for text in legend.get_texts()]
    if len(names) != len(estimates):
        return []

    return _names_by_colour(legend, names, estimates) or names


def _names_by_colour(
    legend: Legend, names: list[str], estimates: list[Line2D]
) -> list[str]:
    """
    Pair each estimate line with the legend entry drawn in its colour.

    Answers empty whenever the pairing cannot be made to stand on its own:
    a legend whose handles do not correspond one-to-one with its texts, a
    handle carrying no readable colour, two groups sharing one, or an
    estimate whose colour matches no handle. In every one of those the
    caller falls back to legend order, which is what the whole function
    used to do.

    ``legend_handles`` is the matplotlib 3.7 spelling; ``legendHandles`` is
    what came before it, and ``pyproject.toml`` declares ``matplotlib>=3.8``
    -- so the second name is not reached today and is probed anyway, since
    an attribute that is absent must degrade to the fallback rather than
    raise inside a draw.

    Parameters
    ----------
    legend : Legend
        The legend seaborn drew for the hue groups.
    names : list of str
        The legend's texts, in legend order.
    estimates : list of Line2D
        The estimate line of each drawn group, in drawing order.

    Returns
    -------
    list of str
        One name per estimate line, or empty when colour cannot settle it.
    """
    handles = getattr(legend, "legend_handles", None)
    if handles is None:
        handles = getattr(legend, "legendHandles", None)
    if handles is None or len(handles) != len(names):
        return []

    keys = [_colour_key(handle) for handle in handles]
    if any(key is None for key in keys) or len(set(keys)) != len(keys):
        return []

    by_colour = dict(zip(keys, names))
    named: list[str] = []
    for line in estimates:
        name = by_colour.get(_colour_key(line))
        if name is None:
            return []
        named.append(name)

    return named


def _colour_key(artist: object) -> tuple[float, ...] | None:
    """
    Normalise an artist's colour into something two artists can be compared by.

    A colour reaches matplotlib as a name, a hex string, an RGB tuple or an
    RGBA one, and seaborn does not use one spelling throughout -- so the
    comparison is made on the resolved RGBA rather than on whatever was
    handed in. Rounded, because a value that survived a float conversion on
    one artist and not on the other is the same colour.

    Parameters
    ----------
    artist : object
        Any artist exposing ``get_color``.

    Returns
    -------
    tuple of float or None
        The rounded RGBA, or None when the artist has no readable colour.
    """
    getter = getattr(artist, "get_color", None)
    if getter is None:
        return None
    try:
        return tuple(round(channel, 6) for channel in to_rgba(getter()))
    except (ValueError, TypeError):
        return None


def _split(lines: list[Line2D]) -> tuple[list[Line2D], list[Line2D]]:
    """
    Sort the drawn lines into estimates and intervals.

    Parameters
    ----------
    lines : list of Line2D
        The lines this call drew, in the order it drew them.

    Returns
    -------
    tuple of list
        The estimate lines and the interval lines, each in drawing order.
    """
    estimates, intervals = [], []
    for line in lines:
        vertices = line.get_xydata()
        if vertices is None or not len(vertices):
            # The proxy artists a `hue` legend is built from carry no data.
            continue
        if line.get_marker() != _INTERVAL_MARKER:
            estimates.append(line)
        else:
            # Kept whether or not it carries a bound. The list is read against
            # the estimates *by position*, so dropping the line a group with a
            # single observation leaves behind would shift every later group's
            # interval onto the wrong estimate. `_has_drawn_segment` decides
            # what to do with it; it does not decide whether it is there.
            intervals.append(line)

    return estimates, intervals


def _has_drawn_segment(vertices: np.ndarray) -> bool:
    """
    Check that a candidate interval is a shape the chart actually drew.

    A group with a single observation has nothing to estimate an interval
    from, and seaborn renders that as a polyline whose value coordinates are
    all NaN -- the cap positions survive, the interval does not. Such a line
    carries no bound, and treating it as one hands the reader the cap's own
    width as the interval, which is neither a measurement nor even in the
    right units.

    Answering False does not remove the line: it stays in the list to hold its
    group's position, and the layer omits that one group's bound. What this
    decides is whether the chart draws *any* interval, and so whether it is an
    error bar chart at all.

    Tested as "two vertices finite in both coordinates", which is what it
    takes to draw a segment at all, so the check needs no view on which axis
    is which.

    Parameters
    ----------
    vertices : numpy.ndarray
        The line's vertices, as an ``(n, 2)`` array.

    Returns
    -------
    bool
        True when at least one segment of the polyline was drawable.
    """
    finite = np.isfinite(np.asarray(vertices, dtype=float)).all(axis=1)
    return bool(finite.sum() >= 2)


def _pairs_up(estimates: list[Line2D], intervals: list[Line2D]) -> bool:
    """
    Check that every estimate has one interval per group, or none has any.

    This is the guard on reading another library's rendering. Seaborn emits an
    estimate line and then one short polyline per group; if some future
    version emits a shape this does not describe, the counts stop matching and
    the caller can fall back rather than pair the wrong artists up.

    Parameters
    ----------
    estimates : list of Line2D
        The lines carrying the group estimates.
    intervals : list of Line2D
        The candidate interval lines.

    Returns
    -------
    bool
        True when the intervals can be handed over as they stand.
    """
    if not intervals:
        # `errorbar=None` draws the estimates alone, which is a point plot
        # with nothing to pair.
        return True

    groups = {len(estimate.get_xydata()) for estimate in estimates}
    if len(groups) != 1:
        return False

    if len(intervals) != len(estimates) * groups.pop():
        return False

    return all(
        len(interval.get_xydata()) <= MAX_INTERVAL_VERTICES
        for interval in intervals
    )


# Patch seaborn function.
wrap_seaborn("pointplot", point)


def sns_categorical_points(wrapped, instance, args, kwargs):
    """
    Register every point-plot panel seaborn draws, whichever interface drew it.

    One registrar for both. ``seaborn.pointplot`` and
    ``sns.catplot(kind="point")`` share no code above this method, so a patch
    on the function reached one of them and a patch here reaches both -- the
    idiom ``maidr/patch/boxplot.py`` uses for ``plot_boxes`` and #446 used for
    ``_DistributionPlotter``.

    The loss this closes is the quietest of the ``catplot`` kinds. A point
    plot's estimates read correctly as a line either way; what went missing is
    the confidence intervals #246 added, so the reader was given three means
    with nothing saying the chart draws intervals around them -- which is the
    thing a point plot exists to show::

        sns.catplot(df, x="g", y="v", kind="point")   line(3)
        sns.pointplot(df, x="g", y="v", ax=ax)        error_bar(3)

    Snapshotting per panel is what makes it work on a grid, and matters on a
    single axes too: the panel may already hold lines that are not this call's,
    and an estimate taken from another chart is worse than no layer at all.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    before = {id(ax): list(ax.lines) for ax in plotter_axes(instance)}

    with ContextManager.set_internal_context():
        drawn = _draw_quietly(wrapped, args, kwargs)

    for ax, _ in plotter_panels(instance):
        _register_point_layer(ax, before.get(id(ax), []))

    return drawn


# And the plotter method beneath `seaborn.pointplot`, which is the only thing
# `catplot` drives. Wrapped by module path rather than by importing the private
# class, matching how `maidr/patch/boxplot.py` reaches `_CategoricalPlotter`.
wrapt.wrap_function_wrapper(
    "seaborn.categorical",
    "_CategoricalPlotter.plot_points",
    sns_categorical_points,
)
