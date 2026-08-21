from __future__ import annotations

import uuid

import numpy as np
import wrapt
from matplotlib.axes import Axes
from matplotlib.contour import ContourSet
from matplotlib.lines import Line2D
from matplotlib.collections import PolyCollection
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.contour import tag
from maidr.core.plot.maidr_plot import GROUP_NAME
from maidr.core.plot.scatterplot import _handle_colour, _rgba
from maidr.patch.common import _draw_quietly, common, plotter_axes, prospective_axes, wrap_seaborn
from maidr.core.context_manager import ContextManager
from maidr.util.svg_utils import unique_lines_by_xy


def _contour_sets_of(ax: Axes | None) -> list:
    """
    The contour sets already on an axes.

    Held as the artists themselves rather than as their ids, for the reason
    ``maidr/patch/histogram.py``'s ``_containers_of`` gives: an id compared
    after the object it named was freed can be matched by an unrelated artist
    allocated at the same address.

    Parameters
    ----------
    ax : Axes or None
        The axes to look at, or None when it does not exist yet.

    Returns
    -------
    list
        The contour sets on it, in draw order.
    """
    return [
        artist
        for artist in (getattr(ax, "collections", ()) or ())
        if isinstance(artist, ContourSet)
    ]


def _register_field(ax: Axes | None, before: list) -> None:
    """
    Register a field this call drew as a CONTOUR layer.

    A **bivariate** ``kdeplot`` is not a curve: seaborn draws the joint
    density as a contour set of iso-value curves, which has no line for
    ``_register_smooth`` to find. The call therefore declined and the chart
    went out silent -- the same shape as #522, where the recursion guard
    suppressed a registration the outer patch then declined. ``Axes.contour``
    is patched and would have claimed it, but ``kde`` sets the internal
    context around its own call so that it can make the registration itself.

    Asked of the sets *this call added* rather than of everything on the axes:
    an ``ax.contour(...)`` drawn beforehand has already registered a layer of
    its own, and claiming it again would put the same field in the schema
    twice.

    A **filled** density is declined, for the reason ``maidr/patch/contour.py``
    gives for ``contourf``: its outlines run along two different level curves
    stitched together, so announcing one as a level's curve would be right for
    half of its points.

    Parameters
    ----------
    ax : Axes or None
        The axes the call drew on.
    before : list
        The contour sets that were on it beforehand.
    """
    if ax is None:
        return

    seen = {id(drawn) for drawn in before}
    for drawn in _contour_sets_of(ax):
        if id(drawn) in seen or drawn.filled:
            continue
        if not any(len(path.vertices) for path in drawn.get_paths()):
            continue
        tag(drawn)
        FigureManager.create_maidr(ax, PlotType.CONTOUR, contour_set=drawn)


def _curve_names(ax: Axes, curves: list) -> list:
    """
    Name each KDE curve from the legend swatch drawn in its colour.

    A ``kdeplot(hue=...)`` draws one curve per group and both distributions
    are announced -- but with nothing to tell them apart, so a reader hears
    the identical announcement twice (#558). The colours are what separate
    them on screen and the legend is what names those colours, which is the
    match ``scatterplot.hue_groups`` already makes point by point and
    ``patch/histogram`` container by container.

    Not by position. Measured on seaborn 0.13.2 the legend runs the reverse of
    the draw order -- curves drawn orange then blue against entries listed
    ``['y', 'x']`` -- so pairing them off gives each curve the other group's
    name.

    Every reason to decline leaves the curves unnamed rather than naming them
    wrongly: no legend, a curve no swatch claims, or a swatch that names two
    things. A lone curve is left unnamed whatever the legend says, because a
    name on the only layer of a chart reads as though there were another to
    tell it from.

    Parameters
    ----------
    ax : Axes
        The axes drawn on, for its legend.
    curves : list
        The KDE lines, in draw order.

    Returns
    -------
    list
        One entry per curve, naming it or ``None``.
    """
    return _names_for(ax, [_rgba(curve.get_color()) for curve in curves])


def _fill_names(ax: Axes, fills: list) -> list:
    """
    Name each filled KDE band from the legend swatch drawn in its colour.

    ``kdeplot(hue=..., fill=True)`` draws no lines at all -- measured, two
    groups give two ``PolyCollection`` bands and no ``Line2D`` at all -- so the
    curve match above never sees them. A band's ``get_facecolor`` carries the
    same translucent colour its swatch does, which is the whole difference.

    Parameters
    ----------
    ax : Axes
        The axes drawn on, for its legend.
    fills : list
        The bands, in draw order.

    Returns
    -------
    list
        One entry per band, naming it or ``None``.
    """
    return _names_for(ax, [_collection_colour(fill) for fill in fills])


def _collection_colour(collection) -> tuple | None:
    """
    The one colour a collection is filled with, if it has one.

    Parameters
    ----------
    collection : PolyCollection
        The band.

    Returns
    -------
    tuple or None
        The rounded RGBA, or ``None`` when it is filled with several colours
        or none.
    """
    colours = {_rgba(row) for row in collection.get_facecolor()}
    if len(colours) != 1:
        return None
    return colours.pop()


def _names_for(ax: Axes, colours: list) -> list:
    """
    Match a list of drawn colours against the legend that names them.

    Two passes, and the second is not a convenience. Measured on seaborn
    0.13.2, ``histplot(kde=True, hue=...)`` draws its overlay curves **opaque**
    while the legend swatches carry the bars' translucency::

        line   (1.0, 0.498, 0.055, 1.0)
        swatch (1.0, 0.498, 0.055, 0.5)

    Identical hue, different alpha, so an RGBA comparison names nothing at all
    -- the chart would announce two named histograms and two anonymous curves
    over one axis. What identifies a group is the hue, so a second pass
    compares the three colour channels alone.

    That pass is guarded: it runs only where the drawn colours are already
    distinct without their alpha. Two artists separated *by* their opacity
    would otherwise both take whichever name matched, and a confident wrong
    name is worse than none.

    Every other reason to decline stands: no legend, an artist no swatch
    claims, a swatch that names two things, and a lone artist -- which needs
    nothing to be told apart from.

    Parameters
    ----------
    ax : Axes
        The axes drawn on, for its legend.
    colours : list
        One rounded RGBA per artist, or ``None`` where it has no single one.

    Returns
    -------
    list
        One name per entry, or ``None``.
    """
    if len(colours) < 2:
        return [None] * len(colours)

    legend = ax.get_legend()
    if legend is None:
        return [None] * len(colours)

    swatches = [
        (_handle_colour(handle), text.get_text())
        for handle, text in zip(legend.legend_handles, legend.get_texts())
    ]

    keys = [lambda colour: colour]
    hues = [colour[:3] for colour in colours if colour is not None]
    if len(set(hues)) == len(hues):
        keys.append(lambda colour: colour[:3])

    for key in keys:
        named = _match_swatches(colours, swatches, key)
        if named:
            return [
                None if colour is None else named.get(key(colour))
                for colour in colours
            ]
    return [None] * len(colours)


def _match_swatches(colours: list, swatches: list, key) -> dict | None:
    """
    Map each swatch that a drawn artist shares a colour with to its name.

    Parameters
    ----------
    colours : list
        The drawn colours.
    swatches : list
        ``(colour, name)`` per legend entry, colour ``None`` where the handle
        names no single one.
    key : callable
        What counts as "the same colour" for this pass.

    Returns
    -------
    dict or None
        Key to name, or ``None`` when one colour is claimed by two names --
        a ``style=`` legend does that, and a swatch meaning two things cannot
        name the group an artist belongs to.
    """
    drawn = {key(colour) for colour in colours if colour is not None}
    named: dict = {}
    for colour, name in swatches:
        if colour is None:
            continue
        matched = key(colour)
        if matched not in drawn:
            continue
        if named.get(matched, name) != name:
            return None
        named[matched] = name
    return named


def _register_smooth(ax: Axes | None, instance, args, kwargs) -> None:
    """
    Register every KDE curve on one axes as a SMOOTH layer.

    Split out of :func:`kde` so ``seaborn.displot(kind="kde")`` can reuse it.
    ``displot`` does not import ``kdeplot`` -- it drives
    ``_DistributionPlotter`` directly -- so its panels reached neither name
    ``wrap_seaborn`` patches and were left to the line patch, which typed them
    ``line`` where the axes-level function gives ``smooth`` (#446). A fitted
    curve is not a series of observations, and `smooth` is the type that says
    so.

    Parameters
    ----------
    ax : Axes or None
        The axes to read. ``None`` is a no-op, so a caller that could not
        resolve one does nothing rather than guessing.
    instance, args, kwargs
        Forwarded to :func:`maidr.patch.common.common` unchanged.
    """
    if ax is not None:
        # Register all unique Line2D objects
        lines = [line for line in ax.get_lines() if isinstance(line, Line2D)]
        curves = list(unique_lines_by_xy(lines))
        for kde_line, name in zip(curves, _curve_names(ax, curves)):
            if kde_line.get_gid() is None:
                gid = f"maidr-{uuid.uuid4()}"
                kde_line.set_gid(gid)
            common(
                PlotType.SMOOTH,
                lambda *a, **k: ax,
                instance,
                args,
                dict(kwargs, regression_line=kde_line, **{GROUP_NAME: name}),
            )
        # Register all PolyCollection boundaries as SMOOTH
        fills = [c for c in ax.collections if isinstance(c, PolyCollection)]
        for poly, fill_name in zip(fills, _fill_names(ax, fills)):
            if poly.get_paths():
                path = poly.get_paths()[0]
                boundary = path.vertices
                # Defensive: ensure boundary is a numpy array
                boundary = np.asarray(boundary)
                kde_line = Line2D(boundary[:, 0], boundary[:, 1])
                gid = f"maidr-{uuid.uuid4()}"
                kde_line.set_gid(gid)
                poly.set_gid(gid)  # Assign gid to PolyCollection group
                common(
                    PlotType.SMOOTH,
                    lambda *a, **k: ax,
                    instance,
                    args,
                    dict(
                        kwargs,
                        regression_line=kde_line,
                        poly_gid=gid,
                        is_polycollection=True,
                        **{GROUP_NAME: fill_name},
                    ),
                )


def kde(wrapped, instance, args, kwargs) -> Axes | Line2D | PolyCollection:
    """
    Patch for seaborn.kdeplot: register the curves, or the field, that it drew.

    A univariate density is one or more curves and registers as ``smooth``. A
    bivariate one is a scalar field drawn as iso-value curves and registers as
    ``contour``; see :func:`_register_field` for why that has to happen here.
    """
    before = _contour_sets_of(prospective_axes(kwargs))

    with ContextManager.set_internal_context():
        plot = _draw_quietly(wrapped, args, kwargs)
    ax = plot if isinstance(plot, Axes) else getattr(plot, "axes", None)
    _register_field(ax, before)
    _register_smooth(ax, instance, args, kwargs)
    return plot


def sns_distribution_density(wrapped, instance, args, kwargs):
    """
    Register the KDE panels ``seaborn.displot(kind="kde")`` draws.

    The same gap the histogram half of #446 describes, one method along:
    ``displot`` drives ``_DistributionPlotter`` rather than importing
    ``kdeplot``, so its curves were seen only by the line patch and typed
    ``line``. Measured against the axes-level function on the same data::

        sns.kdeplot(df, x="v")              -> smooth
        sns.displot(df, x="v", kind="kde")  -> line

    ``kdeplot`` sets the internal context around its own call, so this
    declines when it is the one driving and no panel registers twice.

    One call covers the whole grid, so every panel is registered rather than
    only ``plotter.ax`` -- see :func:`maidr.patch.common.plotter_axes` for why
    that matters.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    with ContextManager.set_internal_context():
        drawn = _draw_quietly(wrapped, args, kwargs)

    for ax in plotter_axes(instance):
        _register_smooth(ax, instance, args, kwargs)

    return drawn


# Patch seaborn kdeplot
wrap_seaborn("kdeplot", kde)

# And the plotter method beneath it, which is the only thing `displot`
# drives; see `sns_distribution_density`.
wrapt.wrap_function_wrapper(
    "seaborn.distributions",
    "_DistributionPlotter.plot_univariate_density",
    sns_distribution_density,
)
