from __future__ import annotations

from typing import Any

import matplotlib.pyplot as plt
import wrapt

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import PolyQuadMesh, QuadMesh
from matplotlib.container import BarContainer
from matplotlib.patches import Polygon
from matplotlib.lines import Line2D
import uuid

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import _draw_quietly, common, plotter_axes, wrap_seaborn


@wrapt.patch_function_wrapper(Axes, "hist")
def mpl_hist(
    wrapped, _, args, kwargs
) -> tuple[
    np.ndarray | list[np.ndarray],
    np.ndarray,
    BarContainer | Polygon | list[BarContainer | Polygon],
]:
    """
    Patch matplotlib Axes.hist to register HIST layer for MAIDR.
    """
    # Don't proceed if the call is made internally by the patched function.
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    # Set the internal context to avoid cyclic processing.
    with ContextManager.set_internal_context():
        # Patch `ax.hist()`.
        n, bins, plot = _draw_quietly(wrapped, args, kwargs)

    # Extract the histogram data points for MAIDR from the plots.
    ax = FigureManager.get_axes(plot)
    FigureManager.create_maidr(ax, PlotType.HIST)

    # Return to the caller.
    return n, bins, plot


def _prospective_axes(kwargs: dict) -> Axes | None:
    """
    The axes ``histplot`` is about to draw on, resolved before it draws.

    Named without drawing anything: an explicit ``ax=`` is the answer when
    given, and otherwise seaborn will take ``plt.gca()``, which is only asked
    for when a figure already exists so that a call on a clean slate does not
    conjure one early.

    Parameters
    ----------
    kwargs : dict
        Keyword arguments the caller passed.

    Returns
    -------
    Axes or None
        The axes to snapshot, or None when there is nothing drawn yet.
    """
    # `ax` is read from kwargs alone because seaborn declares it keyword-only:
    # everything after `data` in `histplot`'s signature is, so there is no
    # positional spelling to miss. `test_seaborn_still_takes_ax_by_keyword`
    # asserts that rather than trusting it, so a signature change fails loudly
    # instead of quietly emptying the snapshot below.
    ax = kwargs.get("ax")
    if ax is not None:
        return ax
    return plt.gcf().gca() if plt.get_fignums() else None


def _containers_of(ax: Axes | None) -> list:
    """
    The containers an axes holds right now, kept by reference.

    The objects themselves rather than their ``id()``s, and that is not
    incidental. An id is only unique while its object is alive, so a snapshot
    of ids could be matched by an unrelated container that happened to be
    allocated at a freed address -- which would make a genuinely new histogram
    look pre-existing and be declined. Holding the list keeps every one of
    them alive for the comparison.

    A ``set`` would be wrong for a second reason: ``BarContainer`` extends
    ``tuple``, so it hashes by value, and two equal containers would collapse
    into one.
    """
    return list(getattr(ax, "containers", ()) or ())


def _drew_bars(plot: Any, before: list) -> bool:
    """
    Whether *this call* drew a histogram made of bars.

    `sns.histplot(x=..., y=...)` is a **2D** histogram: seaborn draws it as a
    ``QuadMesh`` of joint counts, not as bars. `hist` promises one bin per bar
    with a count, which such a layer has neither of -- so registering it
    promises a reading nothing can produce, and extraction then took the whole
    figure down with it. `sns.jointplot(kind="hist")` produced no HTML at all,
    and so did any supported chart that happened to share the axes (#388).

    Asked of the artists rather than of the arguments, because "did this draw
    bars" is the question the extractor actually needs answered, and a `y=`
    keyword is seaborn's spelling of it rather than the thing itself.

    Asked of the containers *this call added* rather than of everything on the
    axes, which is the difference between declining and lying. An axes that
    already holds bars -- `sns.barplot(ax=ax)` first, then a bivariate
    `histplot(ax=ax)` -- would otherwise answer True for someone else's
    artists, and `extract_container` returns the first container on the axes,
    so the `hist` layer would describe the *barplot's* bars with bin edges
    invented for them:

        registered: ['bar', 'hist']
          bar   [{'x': 'a', 'y': 8.67}, ...]
          hist  [{'y': 8.67, 'xMin': -0.4, 'xMax': 0.4}, ...]

    Right numbers, wrong chart, and nothing raised -- which is worse than the
    crash this function was added to prevent.

    Parameters
    ----------
    plot : Any
        Whatever the patched call returned.
    before : list
        The containers the axes held before the call, by reference.

    Returns
    -------
    bool
        True when this call added at least one ``BarContainer``.
    """
    try:
        ax = FigureManager.get_axes(plot)
    except StopIteration:  # pragma: no cover - an artist with no axes on it
        # `get_axes` walks a container's children with a bare `next()`, so an
        # artist it cannot resolve raises rather than returning. Declining is
        # the gentler answer and loses nothing: `common` would call the same
        # function a line below and raise the same way.
        return False
    if ax is None or not ax.containers:
        return False
    return any(
        isinstance(container, BarContainer)
        and not any(container is seen for seen in before)
        for container in ax.containers
    )


def _meshes_of(ax: Axes | None) -> list:
    """
    The mesh artists already on an axes.

    Both mesh classes, not only the one seaborn currently draws through.
    Measured on seaborn 0.13.2, a bivariate ``histplot`` reaches
    ``Axes.pcolormesh`` and so produces a ``QuadMesh`` -- but naming only that
    would tie this to a seaborn internal, and the failure if it ever moved to
    ``Axes.pcolor`` would be the silent one this whole change exists to
    remove: the mesh would go unrecognised, the call would decline as before,
    and the chart would be quiet again. ``PolyQuadMesh`` costs nothing to
    accept and is a heatmap by the same argument.

    Held as a list of the artists themselves rather than of their ids, for the
    reason ``_containers_of`` gives: an id compared after the object it named
    was freed can be matched by an unrelated artist allocated at the same
    address.

    Parameters
    ----------
    ax : Axes or None
        The axes to look at, or None when it does not exist yet.

    Returns
    -------
    list
        The meshes on it, in draw order.
    """
    return [
        artist
        for artist in (getattr(ax, "collections", ()) or ())
        if isinstance(artist, (QuadMesh, PolyQuadMesh))
    ]


def _drew_mesh(ax: Axes | None, before: list) -> bool:
    """
    Whether *this call* drew a mesh of joint counts.

    Asked the same way ``_drew_bars`` asks its question, and for the same
    reason: an axes that already held a heatmap -- ``sns.heatmap(ax=ax)``
    first, then a bivariate ``histplot(ax=ax)`` -- would otherwise have
    someone else's mesh claimed as this call's.

    Parameters
    ----------
    ax : Axes or None
        The axes the call drew on.
    before : list
        The meshes that were on it beforehand.

    Returns
    -------
    bool
        True when a mesh appeared that was not there before.
    """
    seen = {id(mesh) for mesh in before}
    return any(id(mesh) not in seen for mesh in _meshes_of(ax))


def sns_hist(wrapped, instance, args, kwargs) -> Axes:
    """
    Patch seaborn.histplot to register HIST and (if kde=True) SMOOTH layers for MAIDR.

    A bivariate histogram is left unregistered rather than read wrongly; see
    `_drew_bars`.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    prospective = _prospective_axes(kwargs)
    before = _containers_of(prospective)
    meshes = _meshes_of(prospective)

    with ContextManager.set_internal_context():
        drawn = _draw_quietly(wrapped, args, kwargs)

    if not _drew_bars(drawn, before):
        # A bivariate histogram, which draws a `QuadMesh` of joint counts.
        # Declining `hist` for it is right -- see `_drew_bars` -- but declining
        # it is not the same as leaving the chart silent. Seaborn reaches the
        # mesh through `Axes.pcolormesh`, which is patched and would register
        # `heat` on its own; the internal context set above suppressed that
        # registration so this function could make its own, and then this
        # function declined. So make the one the chart is owed here.
        #
        # `sns.displot(x=..., y=...)` reads as `heat` today for no better
        # reason than that it is unpatched, so the inner call runs outside the
        # context -- which is what made the same figure readable through one
        # spelling and silent through the other (#522).
        axes = drawn if isinstance(drawn, Axes) else FigureManager.get_axes(drawn)
        if _drew_mesh(axes, meshes):
            FigureManager.create_maidr(axes, PlotType.HEAT)
        return drawn

    # Register the histogram as HIST as before
    ax = common(PlotType.HIST, lambda *a, **k: drawn, instance, args, kwargs)
    # Only register KDE overlay as SMOOTH if kde=True was set
    kde_enabled = kwargs.get("kde", False)
    if kde_enabled:
        # Find the KDE line(s) and register as SMOOTH
        axes = ax if isinstance(ax, Axes) else getattr(ax, "axes", None)
        if axes is not None:
            for line in axes.get_lines():
                if isinstance(line, Line2D):
                    if line.get_gid() is None:
                        gid = f"maidr-{uuid.uuid4()}"
                        line.set_gid(gid)
                    common(
                        PlotType.SMOOTH,
                        lambda *a, **k: axes,
                        instance,
                        args,
                        dict(kwargs, regression_line=line),
                    )
    return ax


def sns_distribution_hist(wrapped, instance, args, kwargs) -> Any:
    """
    Register the panels ``seaborn.displot`` draws, which reach no other patch.

    ``displot`` does not import ``histplot`` -- it drives
    ``_DistributionPlotter`` directly -- so neither name ``wrap_seaborn``
    patches is ever bound, and the panel was seen only by ``Axes.bar``. That
    cannot know it is drawing a histogram, so a distribution arrived as a
    **dodged bar chart** with its bin edges gone (#446)::

        sns.displot(df, x="v", bins=3)
          dodged_bar   {'x': '-1.61082', 'z': '_container0', 'y': 9.0}
        sns.histplot(df, x="v", bins=3)
          hist         {'y': 9.0, 'x': -1.6108, 'xMin': -2.3250, 'xMax': -0.8966, ...}

    Three losses at once: the type names a chart that compares groups side by
    side; `xMin`/`xMax` are gone, so the bin *centre* is announced as though
    it were the bar's label, a precise number that is neither an observation
    nor a boundary; and `z` -- the name a reader hears to tell series apart --
    carried ``_container0``, maidr's own internal identifier for a
    ``BarContainer``.

    Patching the plotter method rather than ``displot`` covers ``histplot``
    too, since both drive it. ``histplot``'s own patch runs first and sets the
    internal context, so this one declines and no panel registers twice --
    the recursion guard the box and boxen patches already rely on.

    Each panel is asked separately whether *it* drew bars, so a bivariate
    histogram keeps declining for the reason ``_drew_bars`` gives: seaborn
    draws that as a ``QuadMesh`` of joint counts, and `hist` promises one bin
    per bar with a count, which such a layer has neither of.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    # Snapshot per axes before the call, so a panel that already held bars --
    # someone else's `barplot` on the same axes -- is not claimed as this
    # histogram's. Empty for a faceted call, whose panels do not exist yet.
    before = {id(ax): _containers_of(ax) for ax in plotter_axes(instance)}

    with ContextManager.set_internal_context():
        drawn = _draw_quietly(wrapped, args, kwargs)

    for ax in plotter_axes(instance):
        if _drew_bars(ax, before.get(id(ax), [])):
            FigureManager.create_maidr(ax, PlotType.HIST)

    return drawn


# Patch seaborn function at both names it answers to; see `wrap_seaborn`.
wrap_seaborn("histplot", sns_hist)

# And the plotter class beneath them, which is the only thing `displot`
# drives. Wrapped by module path rather than by importing the private class,
# matching how `maidr/patch/boxplot.py` reaches `_CategoricalPlotter`.
wrapt.wrap_function_wrapper(
    "seaborn.distributions",
    "_DistributionPlotter.plot_univariate_histogram",
    sns_distribution_hist,
)
