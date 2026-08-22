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

# `_handle_colour` and `legend_of` are re-exported rather than used here:
# both moved out when the colour matching became shared, and both are
# imported from this module by name elsewhere.
from maidr.core.plot.scatterplot import _handle_colour, _rgba  # noqa: F401
from maidr.patch.common import (
    _draw_quietly,
    common,
    plotter_axes,
    prospective_axes,
    wrap_seaborn,
)
from maidr.core.context_manager import ContextManager

# `legend_of` and `_names_for` are re-exported rather than used here:
# `tests/core/plot/test_hue_kde_naming.py` and
# `tests/core/plot/test_pairplot_group_names.py` reach the colour match
# through this module, which is where it lived before it moved to
# `maidr/util/legend_names.py`. The blanket noqa is what lets them.
from maidr.util.legend_names import (  # noqa: F401
    legend_of,
    names_for as _names_for,
    names_for_panel as _names_for_panel,
)
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


def _curve_names(ax: Axes, curves: list, faceted: bool = False) -> list:
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
    tell it from -- unless the chart is a grid and this is one panel of it,
    where the other layers exist and are drawn next door (#608).

    Parameters
    ----------
    ax : Axes
        The axes drawn on, for its legend.
    curves : list
        The KDE lines, in draw order.
    faceted : bool
        Whether this panel is one of several.

    Returns
    -------
    list
        One entry per curve, naming it or ``None``.
    """
    return _names_for_panel(ax, [_rgba(curve.get_color()) for curve in curves], faceted)


def _fill_names(ax: Axes, fills: list, faceted: bool = False) -> list:
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
    faceted : bool
        Whether this panel is one of several.

    Returns
    -------
    list
        One entry per band, naming it or ``None``.
    """
    return _names_for_panel(ax, [_collection_colour(fill) for fill in fills], faceted)


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


def deferred_names(resolve, count: int) -> list:
    """
    One lazy name per artist, resolved together the first time any is asked.

    The match itself is unchanged; **when** it runs is the whole point. A
    ``pairplot(hue=...)`` draws every panel before ``PairGrid.add_legend()``
    builds the legend, so at registration there is no legend anywhere --
    measured, neither on the axes nor on the figure -- and every diagonal
    panel came out anonymous while the scatters beside it were named (#561).

    Resolved once and shared: the layers of one call must agree, and a legend
    read per layer would be read once per layer for no gain. A caller who
    relabels the legend between drawing and rendering therefore changes what
    the chart says, which is the divergence ``MaidrPlot._legend_title``
    already accepts for ``axes.z``.

    Parameters
    ----------
    resolve : callable
        Returns the whole list of names, in artist order.
    count : int
        How many artists there are.

    Returns
    -------
    list
        One zero-argument callable per artist.
    """
    resolved: list = []

    def at(index: int):
        def name():
            if not resolved:
                resolved.append(resolve())
            names = resolved[0]
            return names[index] if index < len(names) else None

        return name

    return [at(index) for index in range(count)]


def _register_smooth(
    ax: Axes | None, instance, args, kwargs, faceted: bool = False
) -> None:
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
    faceted : bool
        Whether this panel is one of several, which is what lets a panel
        holding a single curve still be named (#608).
    """
    if ax is not None:
        # Register all unique Line2D objects
        lines = [line for line in ax.get_lines() if isinstance(line, Line2D)]
        curves = list(unique_lines_by_xy(lines))
        for kde_line, name in zip(
            curves,
            deferred_names(lambda: _curve_names(ax, curves, faceted), len(curves)),
        ):
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
        for poly, fill_name in zip(
            fills, deferred_names(lambda: _fill_names(ax, fills, faceted), len(fills))
        ):
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

    # One legend for the whole grid, so a panel holding one curve holds one
    # of several and the name that says which is worth having (#608).
    panels = plotter_axes(instance)
    faceted = len(panels) > 1
    for ax in panels:
        _register_smooth(ax, instance, args, kwargs, faceted)

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
