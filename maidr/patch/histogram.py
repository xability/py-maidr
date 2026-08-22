from __future__ import annotations

from typing import Any

import wrapt

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import PolyCollection, PolyQuadMesh, QuadMesh
from matplotlib.container import BarContainer
from matplotlib.patches import Polygon
from matplotlib.lines import Line2D
import uuid

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.histogram import DRAWN_BARS
from maidr.core.plot.maidr_plot import GROUP_NAME
from maidr.core.plot.outlined_histogram import OUTLINE_LINE
from maidr.core.plot.outlined_histogram import reads as outline_reads
from maidr.core.plot.scatterplot import _rgba
from maidr.patch.kdeplot import _curve_names, _names_for, deferred_names
from maidr.core.plot.step_histogram import STEP_COUNTS, STEP_EDGES, STEP_ORIENTATION
from maidr.core.plot.stepped_histogram import reads as _reads_outline
from maidr.patch.common import _draw_quietly, common, plotter_axes, prospective_axes, wrap_seaborn


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
    # One layer per dataset, each handed the container it was drawn as.
    #
    # `Axes.hist` returns a *list* of containers whenever it was given a list
    # of datasets, and reading one of them would announce one distribution and
    # drop the rest -- so a two-dataset call is two layers, which is what
    # `sns.histplot(hue=...)` gets from the scatter split of #544 and what a
    # reader moving between them expects.
    #
    # A `barstacked` call is read the same way, and measured rather than
    # assumed: each container's bar *heights* are still its own dataset's
    # counts, and the stacking lives in the bars' `bottom`. So the counts
    # announced are right either way; only the fact that they are stacked is
    # not said, which is the reading `stacked_bar` would add.
    #
    containers = _drawn_containers(plot)
    if containers:
        for container in containers:
            FigureManager.create_maidr(ax, PlotType.HIST, **{DRAWN_BARS: container})
        return plot

    # No container to read means `histtype="step"` or `"stepfilled"`, which
    # draw a `Polygon` per dataset. Nothing has to be recovered from the
    # outline: `n` and `bins` above *are* the counts and the edges, so they
    # are handed over and `StepHistPlot` reads them (#555).
    #
    # One layer per dataset here too, for the same reason the container branch
    # emits one: a multi-dataset call returns a list of count arrays, and
    # reading one would announce a single distribution and drop the rest.
    for counts in _step_counts(n):
        FigureManager.create_maidr(
            ax,
            PlotType.HIST,
            **{
                STEP_COUNTS: counts,
                STEP_EDGES: bins,
                # Read from the caller's kwargs because the `Polygon` a step
                # histtype draws records nothing about it, unlike the
                # `BarContainer` the bar histtypes leave.
                STEP_ORIENTATION: kwargs.get("orientation"),
            },
        )

    # Return to the caller.
    return n, bins, plot


def _step_counts(n: Any) -> list:
    """
    The per-dataset count arrays one ``Axes.hist`` call produced.

    ``n`` is a flat array of counts for a single dataset and a list of them
    for several, which is the same shape split the third return value has --
    so the two branches of the patch stay symmetrical rather than one of them
    quietly reading only the first distribution.

    Told apart by the *elements* rather than by the container's type: both
    forms are array-like, and both have a length. A first element that is
    itself a sequence is what says the call was given several datasets.

    Parameters
    ----------
    n : Any
        The first element of what ``Axes.hist`` returned.

    Returns
    -------
    list
        One count array per dataset, possibly empty.
    """
    counts = list(n) if n is not None and len(n) else []
    if counts and hasattr(counts[0], "__len__"):
        return counts
    return [counts] if counts else []


def _drawn_containers(plot: Any) -> list:
    """
    The bar containers one ``Axes.hist`` call drew, in dataset order.

    ``Axes.hist`` returns its third value in three shapes and the caller's
    arguments do not say which: a single ``BarContainer`` for one dataset, a
    list of them for several, and a list of ``Polygon`` lists for the two step
    histtypes, which create no container at all. Asked of the return value
    rather than of the axes, so a call registers exactly what it drew and
    never a neighbour's bars.

    Parameters
    ----------
    plot : Any
        The third element of what ``Axes.hist`` returned.

    Returns
    -------
    list
        Every ``BarContainer`` this call drew, possibly empty.
    """
    if isinstance(plot, BarContainer):
        return [plot]
    if isinstance(plot, (list, tuple)):
        return [entry for entry in plot if isinstance(entry, BarContainer)]
    return []


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


def _new_bar_containers(ax: Axes | None, before: list) -> list[BarContainer]:
    """
    The bar containers a call just added to an axes, in draw order.

    Compared by identity against the snapshot. Not because value comparison
    would be wrong -- measured, two containers over identical data compare
    **unequal**, because ``BarContainer`` extends ``tuple`` over ``Rectangle``
    artists and those compare by identity -- but because "is this the same
    object" is the question actually being asked, and it cannot become wrong
    if matplotlib ever gives the container value semantics.

    **All** of them, which is the correction #558 records. A call that adds
    several is a hue-grouped ``histplot``, and this used to answer with the
    first on the reasoning that the groups share one binning so the choice was
    unobservable. The *edges* are shared. The counts are not -- measured, two
    groups over one binning gave ``[0, 4, 10, 9, 5]`` and ``[1, 11, 8, 8, 4]``
    -- so answering with one announced one distribution and left the other
    drawn but unspoken, which is the defect #553 fixed for ``ax.hist([a, b])``
    and #527 for two ``ax.bar`` calls.

    Parameters
    ----------
    ax : Axes or None
        The axes drawn on.
    before : list
        The containers the axes held before the call, by reference.

    Returns
    -------
    list of BarContainer
        The containers this call added, possibly none.
    """
    return [
        container
        for container in (getattr(ax, "containers", ()) or ())
        if isinstance(container, BarContainer)
        and not any(container is seen for seen in before)
    ]


def _group_names(ax: Axes | None, containers: list) -> list[str | None]:
    """
    Name each container from the legend swatch drawn in its colour.

    A ``histplot(hue=...)`` draws one container per group, every bar of it in
    that group's colour, and the legend names those colours -- so the same
    match ``scatterplot.hue_groups`` makes point by point works container by
    container, one level up. The helpers are imported rather than reimplemented
    for that reason.

    Not by position. Measured on seaborn 0.13.2, the legend runs the *exact
    reverse* of the draw order -- ``['y', 'x']`` against containers drawn
    ``x, y``, and ``['z', 'x', 'y']`` against ``y, x, z`` -- so pairing them
    off in order gives every layer somebody else's name. Reading the legend
    backwards would agree on those charts, and is not what this does: the
    reversal is nothing seaborn documents, and a legend carrying entries that
    are not group swatches would still have to be declined rather than
    counted.

    Every reason to decline is a reason to leave the layers unnamed rather
    than to name them wrongly:

    - **No legend.** ``legend=False`` suppresses it, and a chart with a single
      distribution never had one. Nothing names the colours.
    - **A container no swatch claims.** Nothing to call it.
    - **Two names for one colour.** A swatch that means two things cannot name
      the group a container belongs to.

    A single container is left unnamed whatever the legend says: one
    distribution needs nothing to tell it apart from, and a name there would
    read as though the chart held more.

    The match itself is ``kdeplot._names_for``, which is the same one this
    used to make inline against ``_named_colours`` plus a second pass this
    lacked. That pass is not a nicety here: a ``pairplot(hue=...)`` draws its
    bars translucent and builds its figure legend from **opaque** swatches --
    measured, bars at alpha 0.5 against swatches at 1.0, identical hues -- so
    an RGBA comparison named nothing and every diagonal panel stayed
    anonymous (#561). Comparing the three colour channels alone, guarded on
    the drawn colours already being distinct without their alpha, names them.

    Parameters
    ----------
    ax : Axes or None
        The axes drawn on, for its legend.
    containers : list
        The containers this call drew, in draw order.

    Returns
    -------
    list of str or None
        One entry per container, naming it or ``None``.
    """
    if ax is None:
        return [None] * len(containers)

    return _names_for(ax, [_container_colour(c) for c in containers])


def _container_colour(container) -> tuple[float, ...] | None:
    """
    The one colour a container's bars are drawn in, if they share one.

    Parameters
    ----------
    container : BarContainer
        The bars.

    Returns
    -------
    tuple of float or None
        The rounded RGBA every bar shares, or ``None`` when they differ or
        there are no bars.
    """
    colours = {_rgba(patch.get_facecolor()) for patch in container}
    if len(colours) != 1:
        return None
    return colours.pop()


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
    return bool(_new_bar_containers(ax, before))


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


#: The exact types a stepped or filled histogram outline arrives as.
#:
#: seaborn draws ``element="step"`` and ``element="poly"`` through
#: ``Axes.fill_between``, and matplotlib 3.10 gave that method a
#: ``PolyCollection`` subclass of its own. So the same chart is a plain
#: ``PolyCollection`` on 3.9 and a ``FillBetweenPolyCollection`` on 3.10 and
#: later -- measured, identically shaped either way: five bins give 25
#: vertices as a step and 13 as a polygon on both.
#:
#: Named as exact types rather than matched with ``isinstance(artist,
#: PolyCollection)``, because the *other* subclasses are other charts:
#: ``PolyQuadMesh`` is a heatmap and has its own reading, and ``Quiver`` and
#: ``Barbs`` are vector fields that a histogram reader would announce as a
#: distribution over nothing.
_OUTLINE_TYPES: tuple[type, ...] = (PolyCollection,)

try:  # pragma: no cover - depends on the installed matplotlib
    from matplotlib.collections import FillBetweenPolyCollection

    _OUTLINE_TYPES += (FillBetweenPolyCollection,)
except ImportError:
    pass


def _outlines_of(ax: Axes | None) -> list:
    """
    The closed outlines already on an axes.

    ``PolyCollection`` is what ``element="step"`` and ``element="poly"`` draw
    a histogram as, and what a violin, a `fill_between` band and a hexbin
    lattice are drawn as too -- which is exactly why the comparison below is
    against what *this call* added rather than against everything present.

    Held as the artists themselves rather than as their ids, for the reason
    ``_containers_of`` gives.

    Parameters
    ----------
    ax : Axes or None
        The axes to look at, or None when it does not exist yet.

    Returns
    -------
    list
        The outlines on it, in draw order.
    """
    return [
        artist
        for artist in (getattr(ax, "collections", ()) or ())
        if type(artist) in _OUTLINE_TYPES
    ]


def _drew_outlines(ax: Axes | None, before: list) -> list:
    """
    The outlines *this call* added, if any.

    ``sns.histplot(element="step")`` and ``element="poly"`` draw the same
    distribution ``element="bars"`` does, as one closed outline per series
    rather than as a row of bars. Neither ``_drew_bars`` nor ``_drew_mesh``
    sees one, so the call declined and the chart went out silent -- the third
    branch of the decline #522 fixed for the bivariate mesh, and measured::

        element=bars   containers=[BarContainer]     -> ['hist']
        element=step   collections=[PolyCollection]  -> nothing
        element=poly   collections=[PolyCollection]  -> nothing

    One outline per series, so a ``hue`` gives one layer per level: each is an
    independent histogram over the same bins, which is what `hist` describes.

    Parameters
    ----------
    ax : Axes or None
        The axes the call drew on.
    before : list
        The outlines that were on it beforehand.

    Returns
    -------
    list
        The outlines this call added *and* can read, in draw order. An uneven
        ``poly`` is left out here rather than registered and then refused: a
        layer whose data comes back empty is a row the core has to navigate
        into and cannot announce (#421).
    """
    seen = {id(outline) for outline in before}
    return [
        outline
        for outline in _outlines_of(ax)
        if id(outline) not in seen and _reads_outline(outline)
    ]



def _lines_of(ax: Axes | None) -> list:
    """
    The lines already on an axes, for a before-and-after comparison.

    Parameters
    ----------
    ax : Axes or None
        The axes about to be drawn on, where the caller named one.

    Returns
    -------
    list
        The `Line2D` artists present, or empty.
    """
    if ax is None:
        return []
    return list(getattr(ax, "lines", ()) or ())


def _drew_outline_lines(ax: Axes | None, before: list, kde: bool) -> list:
    """
    The unfilled outlines this call added, if it added any it can tell apart.

    ``fill=False`` makes ``element="step"`` and ``element="poly"`` draw a
    ``Line2D`` where the filled spelling draws a ``PolyCollection``, and a
    ``hue`` draws one per group. Compared against a snapshot rather than swept
    for, so a line already on the axes is not claimed.

    The care here is telling an outline from a ``kde=True`` overlay, which is
    also a ``Line2D`` this call added. Measured on seaborn 0.13.2, the two
    interleave -- ``[outline, kde, outline, kde]`` for two groups -- so
    neither "the first half" nor "the last one" separates them.

    What does separate them is the drawstyle, for one of the two elements. A
    stepped outline is ``steps-post`` (or ``steps-pre`` drawn sideways) and a
    density is never stepped, so ``element="step"`` is decided outright. A
    ``poly`` outline and a density are both ``"default"`` and differ only in
    how many vertices they happen to have -- 4 against 200 here, but
    ``gridsize=`` moves the second and the bin count moves the first, so a
    threshold between them would be a guess.

    So a ``poly`` outline is read only when the call asked for no density.
    That leaves ``element="poly", fill=False, kde=True`` unread, which is
    narrower than the silence it replaces and is a decline rather than a
    density announced as a distribution.

    Parameters
    ----------
    ax : Axes or None
        The axes drawn on.
    before : list
        The lines present beforehand.
    kde : bool
        Whether the caller asked for a density overlay.

    Returns
    -------
    list
        The outlines this call drew, in draw order.
    """
    if ax is None:
        return []
    seen = {id(line) for line in before}
    added = [line for line in (getattr(ax, "lines", ()) or ()) if id(line) not in seen]
    return [
        line
        for line in added
        if outline_reads(line)
        and (not kde or str(line.get_drawstyle()).startswith("steps"))
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

    prospective = prospective_axes(kwargs)
    before = _containers_of(prospective)
    meshes = _meshes_of(prospective)
    outlines = _outlines_of(prospective)
    lines = _lines_of(prospective)

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
        axes = FigureManager.get_axes(drawn)
        drew = _drew_outlines(axes, outlines)
        if drew:
            # `element="step"` / `"poly"`: the same distribution drawn as one
            # closed outline per series instead of a row of bars.
            for outline in drew:
                FigureManager.create_maidr(axes, PlotType.HIST, collection=outline)
            return drawn
        outlined = _drew_outline_lines(axes, lines, bool(kwargs.get("kde", False)))
        if outlined:
            # The same two elements drawn `fill=False`: seaborn swaps the
            # collection for a bare `Line2D`, so the branch above finds
            # nothing and the chart was silent (#583). Named from the legend
            # by colour, as the filled spelling and the density already are.
            names = deferred_names(
                lambda: _names_for(axes, [_rgba(line.get_color()) for line in outlined]),
                len(outlined),
            )
            for line, name in zip(outlined, names):
                FigureManager.create_maidr(
                    axes,
                    PlotType.HIST,
                    **{OUTLINE_LINE: line, GROUP_NAME: name},
                )
            return drawn
        if _drew_mesh(axes, meshes):
            # Named from `stat` rather than hardcoded, because it is what the
            # cells actually hold: the default is a count, but
            # `stat="density"` or `"probability"` makes them something else,
            # and a reader hearing "count" for a density has been told the
            # wrong thing about every cell. `HexbinPlot` labels its own `z`
            # the same way and for the same reason.
            FigureManager.create_maidr(
                axes, PlotType.HEAT, z_label=str(kwargs.get("stat", "count"))
            )
        return drawn

    # Register the histogram as HIST as before, naming the container this
    # call drew. Passed through `kwargs` the way the SMOOTH registration below
    # passes `regression_line`. Without it the layer searches the axes and
    # every histogram on one axes resolves to the first -- a `histplot` drawn
    # beside an `ax.hist()` announced the matplotlib call's bins.
    #
    # Looked up on the *drawn* axes rather than the prospective one, which is
    # None whenever the caller did not pass `ax=`. `before` is then empty and
    # every container reads as new, but the answer is still the newest one,
    # which is still this call's.
    drawn_axes = FigureManager.get_axes(drawn)
    # One layer per container, because a `hue` draws one container per group
    # and reading a single one announced one distribution while leaving the
    # rest drawn and unspoken (#558). `common` registers one layer, so the
    # first group goes through it -- keeping the orientation and axis handling
    # every histogram has always had -- and the rest are registered beside it.
    containers = _new_bar_containers(drawn_axes, before)
    names = deferred_names(
        lambda: _group_names(drawn_axes, containers), len(containers)
    )
    ax = common(
        PlotType.HIST,
        lambda *a, **k: drawn,
        instance,
        args,
        dict(kwargs, **{DRAWN_BARS: containers[0], GROUP_NAME: names[0]}),
    )
    for container, name in zip(containers[1:], names[1:]):
        FigureManager.create_maidr(
            drawn_axes, PlotType.HIST, **{DRAWN_BARS: container, GROUP_NAME: name}
        )
    # Only register KDE overlay as SMOOTH if kde=True was set
    kde_enabled = kwargs.get("kde", False)
    if kde_enabled:
        # Find the KDE line(s) and register as SMOOTH
        axes = ax if isinstance(ax, Axes) else getattr(ax, "axes", None)
        if axes is not None:
            # The overlay is drawn one curve per hue group too, so it is named
            # the same way the bars beneath it are -- otherwise a chart with
            # both would announce two named histograms and two anonymous
            # curves over the same axis (#558).
            curves = [line for line in axes.get_lines() if isinstance(line, Line2D)]
            for line, name in zip(curves, _curve_names(axes, curves)):
                if line.get_gid() is None:
                    gid = f"maidr-{uuid.uuid4()}"
                    line.set_gid(gid)
                common(
                    PlotType.SMOOTH,
                    lambda *a, **k: axes,
                    instance,
                    args,
                    dict(kwargs, regression_line=line, **{GROUP_NAME: name}),
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
        seen = before.get(id(ax), [])
        if not _drew_bars(ax, seen):
            continue
        # One layer per group here too; `displot(hue=...)` reaches only this
        # site, so leaving it reading the first container would fix the defect
        # for `histplot` and not for the figure-level spelling of the same
        # chart -- the asymmetry #522 and #446 were both about.
        containers = _new_bar_containers(ax, seen)
        for container, name in zip(containers, deferred_names(
            lambda: _group_names(ax, containers), len(containers)
        )):
            FigureManager.create_maidr(
                ax, PlotType.HIST, **{DRAWN_BARS: container, GROUP_NAME: name}
            )

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
