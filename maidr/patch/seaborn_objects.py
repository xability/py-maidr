"""Read the marks of ``seaborn.objects``, seaborn's declarative interface."""

from __future__ import annotations

import warnings
from typing import Any, NamedTuple

import wrapt
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection
from matplotlib.container import BarContainer
from matplotlib.lines import Line2D

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.barplot import DRAWN_BARS, bar_groups
from maidr.core.plot.grouped_barplot import DRAWN_GROUPS
from maidr.core.plot.maidr_plot import GROUP_NAME
from maidr.core.plot.scatterplot import DRAWN_POINTS, HUE_GROUP, hue_groups
from maidr.patch.common import _draw_quietly


class _Reading(NamedTuple):
    """
    How one mark is read: what it is, where it lands, and how it is handed on.

    Attributes
    ----------
    plot_type : PlotType
        What the layer is registered as.
    holder : str
        The ``Axes`` attribute the mark's artists arrive in -- ``collections``,
        ``lines`` or ``containers``. Read by name because that is what makes
        the before-and-after diff possible without knowing how many artists a
        mark makes.
    artist : type
        The artist class to keep. The holder is filtered by it rather than
        taken whole, so a layer that lands beside an unrelated artist of
        another class in the same list describes only its own.
    binding : str
        The keyword the artists are handed over under, which is the existing
        plot class' own: nothing new is extracted for any of these marks.
    singular : bool
        Whether that keyword names **one** artist rather than the list.
        ``DRAWN_BARS`` does, because ``Axes.bar`` draws exactly one container
        and ``BarPlot`` wraps what it is given in a list of one. So a reading
        that finds several becomes several layers rather than one truncated
        to the first -- which is also how a hue-grouped bar is already read
        elsewhere (#593, #595), one layer per group. Measured, no ``so.Bar``
        spelling reaches that branch: plain, horizontal, ``color=``,
        ``Dodge()``, ``Stack()``, ``Hist()`` and faceted are each a single
        container of n bars.
    """

    plot_type: PlotType
    holder: str
    artist: type
    binding: str
    singular: bool = False


#: The marks read today, keyed by class name.
#:
#: By **name** rather than by ``isinstance``, and that is load-bearing here
#: rather than a style choice. seaborn's mark hierarchy does not track what a
#: mark draws::
#:
#:     Line  < Path  < Mark      Line2D
#:     Dash  < Paths < Mark      LineCollection
#:     Range < Paths < Mark      LineCollection
#:
#: ``Dash`` and ``Range`` are ``Paths`` subclasses that draw a
#: ``LineCollection``, so dispatching on ancestry would claim two marks whose
#: artists this cannot read -- the shape xability/r-maidr#225 hit from the
#: other side, where ``class(geom)[1]`` declined a subclass that *was*
#: readable. A name misses a mark seaborn renames; ancestry would claim one it
#: cannot read, and a wrong reading is worse than a missing one.
#:
#: A caller's own ``Mark`` subclass is declined for the same reason: it is not
#: in this table, and what it draws is not knowable from the class it came
#: from.
#: Where a plotter keeps the layers it has drawn but not yet registered.
#:
#: On the ``Plotter`` instance, which is built fresh by every ``Plot.plot()``
#: call, so two plots in flight cannot see each other's.
_PENDING = "_maidr_pending"

_READINGS: dict[str, _Reading] = {
    "Dot": _Reading(PlotType.SCATTER, "collections", PathCollection, DRAWN_POINTS),
    "Dots": _Reading(PlotType.SCATTER, "collections", PathCollection, DRAWN_POINTS),
    "Line": _Reading(PlotType.LINE, "lines", Line2D, "lines"),
    "Path": _Reading(PlotType.LINE, "lines", Line2D, "lines"),
    "Bar": _Reading(PlotType.BAR, "containers", BarContainer, DRAWN_BARS, True),
}


def _reading_for(layer: Any) -> _Reading | None:
    """
    How to read one layer, or ``None`` when its mark is not one of these.

    Parameters
    ----------
    layer : Any
        The layer ``Plotter._plot_layer`` was handed. A ``TypedDict`` at type
        level and a plain dict at runtime; anything else declines.

    Returns
    -------
    _Reading or None
        ``None`` leaves the layer exactly as it was, which is unregistered.
    """
    if not isinstance(layer, dict):
        return None
    return _READINGS.get(type(layer.get("mark")).__name__)


def _held(ax: Axes, reading: _Reading) -> list:
    """
    The artists of this reading's kind currently on one axes.

    Parameters
    ----------
    ax : Axes
        The panel to look at.
    reading : _Reading
        Which holder to read and which class to keep.

    Returns
    -------
    list
        In the order the axes holds them, which is the order they were drawn.
    """
    return [
        artist
        for artist in getattr(ax, reading.holder, [])
        if isinstance(artist, reading.artist)
    ]


def _panels(plotter: Any) -> list[Axes]:
    """
    Every axes the figure being drawn holds.

    Read off the figure rather than off ``Plotter._subplots``, because the
    diff below already decides which of them this layer drew on: a panel that
    gained nothing registers nothing, whether it is one seaborn allocated and
    left empty or one the caller drew on themselves before handing the figure
    over. Asking the figure is one internal instead of two.

    Parameters
    ----------
    plotter : Any
        The ``Plotter`` the wrapped method is bound to.

    Returns
    -------
    list of Axes
        Possibly empty, which makes the caller a no-op rather than a guess.
    """
    figure = getattr(plotter, "_figure", None)
    return [ax for ax in getattr(figure, "axes", [])]


#: What a position transform makes a colour-split bar chart. Keyed on the
#: ``Move``'s class name for the reason the mark table is: ancestry does not
#: track what a move *does*, and matching the name states exactly what was
#: asked for.
#:
#: ``Stack`` before ``Dodge`` because a layer may carry both, and stacking is
#: the one a reader meets -- `so.Dodge(), so.Stack()` dodges the levels apart
#: and then stacks within each dodged slot, so the segments a reader steps
#: through are the stack's.
#:
#: ``Norm`` is deliberately absent. It looks like the 100% stack's transform
#: and is not one: `so.Norm()` divides by a *per-group* maximum, so measured
#: on two categories over two levels, `Norm()` after `Stack()` draws negative
#: heights and `Norm()` before it leaves the categories summing to 0.833 and
#: 2.0 rather than to 1. The spelling that is a 100% stack is
#: `so.Norm(func="sum", by=["x"])` before `so.Stack()`, and reading it needs
#: a `stacked_normalized_bar` emitter this side does not have -- `NORMALIZED`
#: is plotly-only in this package. Reported separately (#617).
_MOVES: tuple[tuple[str, PlotType], ...] = (
    ("Stack", PlotType.STACKED),
    ("Dodge", PlotType.DODGED),
)


def _grouped_type(move: list[Any] | None) -> PlotType | None:
    """
    What a layer's position transform makes it, or ``None`` for no transform.

    ``layer["move"]`` is ``None`` or a *list* of ``Move`` objects, applied in
    the order written. It states the transform outright, which is more than
    the classic path gets -- `seaborn.barplot(hue=)` is read as dodged by
    counting containers, and a stacked bar has to be declared through
    `maidr.stacked()`.

    Parameters
    ----------
    move : list of Move, optional
        ``layer["move"]``: ``None``, or a list of ``Move`` instances. Typed
        loosely because naming ``seaborn._core.moves.Move`` would import a
        private class this module deliberately does not depend on -- it
        matches on the class *name* for exactly that reason.

    Returns
    -------
    PlotType or None
        ``STACKED`` or ``DODGED`` when the layer carries that transform,
        ``None`` when it carries neither.
    """
    names = {type(one).__name__ for one in move or ()}
    for name, plot_type in _MOVES:
        if name in names:
            return plot_type
    return None


def _handovers(
    reading: _Reading, ax: Axes, own: list, move: list[Any] | None = None
) -> list[tuple[PlotType, dict]]:
    """
    What to register for one layer's artists: one entry per layer to make.

    Four shapes, and each is a fact about the plot class being handed to.

    A **colour-split scatter** becomes one layer per group. `so.Dot(color=)`
    draws a *single* ``PathCollection`` carrying a colour per point -- the
    same shape ``seaborn.scatterplot(hue=)`` produces -- so the grouping
    survives only in those colours and in the legend naming them, which is
    exactly what ``hue_groups`` inverts. Without it a reader is handed one
    layer of every point where the classic spelling of the same chart gives
    one per level, named (#617).

    A **colour-split bar carrying a position transform** becomes one
    ``dodged_bar`` or ``stacked_bar`` layer holding every group, which is the
    shape ``seaborn.barplot(hue=)`` already reads as: `data` a list per group,
    each point carrying its group in `z`, and cross-group navigation between
    levels at one category. That is strictly more than the split gives, and
    it is available here because `so` states the transform outright.

    A **colour-split bar with no transform** falls back to one layer per
    group. `so.Bar(color=)` alone overplots the levels at the same position
    -- measured, four bars at two x values -- which is neither a dodge nor a
    stack, so a grouped reading would claim a structure the chart does not
    have. Named layers are the honest reading of overplotted bars.

    A **singular binding** becomes one layer per artist; see
    :class:`_Reading`.

    Everything else is one layer holding every artist it drew, which is what
    a multi-series line is: `so.Line(color=)` draws one ``Line2D`` per level
    and reads as one layer of several series -- measured, exactly what
    ``seaborn.lineplot(hue=)`` already does, so there is nothing to bring
    into line there.

    Parameters
    ----------
    reading : _Reading
        How this mark is read.
    ax : Axes
        The panel drawn on, asked for the legend that names the colours.
    own : list
        The artists this layer drew on that panel, in draw order.
    move : list of Move, optional
        ``layer["move"]``: the position transforms the layer was written
        with, which is what types a colour-split bar.

    Returns
    -------
    list of (PlotType, dict)
        One (type, keyword mapping) pair per layer to register. The type is
        the mark's own except where a position transform names a richer one.
    """
    if reading.plot_type is PlotType.SCATTER and len(own) == 1:
        groups = hue_groups(ax, own[0])
        if groups:
            # `hue_groups` answers in the offsets of the collection it was
            # asked about, and the layer takes a list of those -- one per
            # collection -- because a classic strip plot's groups span
            # several (#586). A mark draws one, so it is a list of one.
            return [
                (
                    reading.plot_type,
                    {reading.binding: own, HUE_GROUP: (name, [members])},
                )
                for name, members in groups
            ]

    if reading.plot_type is PlotType.BAR and len(own) == 1:
        groups = bar_groups(ax, own[0])
        if groups:
            # A synthetic container per group rather than a filter inside the
            # plot class: the patches are the ones on the axes, so the
            # selectors resolve unchanged, and every layer then holds one bar
            # per tick -- which is what brings the category names back.
            containers = [
                BarContainer(
                    tuple(own[0][index] for index in members),
                    orientation=own[0].orientation,
                )
                for _, members in groups
            ]
            grouped = _grouped_type(move)
            if grouped is not None:
                # One layer of every group, which is what `GroupedBarPlot`
                # takes -- the same list-of-containers a classic
                # `seaborn.barplot(hue=)` leaves on the axes. It names the
                # groups from the legend itself, so no `GROUP_NAME` here.
                return [(grouped, {DRAWN_GROUPS: containers})]
            return [
                (reading.plot_type, {reading.binding: container, GROUP_NAME: name})
                for container, (name, _) in zip(containers, groups)
            ]

    if reading.singular:
        return [(reading.plot_type, {reading.binding: one}) for one in own]
    return [(reading.plot_type, {reading.binding: own})]


def _layer(wrapped, instance, args, kwargs) -> Any:
    """
    Draw one ``seaborn.objects`` layer and register what it drew.

    ``Plotter._plot_layer`` runs once per ``.add()`` and draws that layer
    across every panel, so this is the one place where "which artists belong
    to which layer" is still answerable. Taking the axes' artists before and
    after the call answers it exactly, and without predicting how many a mark
    makes -- ``so.Line(color=...)`` draws one ``Line2D`` per level, and a
    faceted layer draws on some panels and not others.

    A mark that is not in :data:`_READINGS` is drawn and left alone entirely,
    rather than drawn inside the internal context. That keeps the change
    additive by construction: every unread mark registers exactly what it
    registered before, which is nothing.

    Parameters
    ----------
    wrapped : Callable
        ``Plotter._plot_layer``.
    instance : Any
        The plotter it was called on.
    args, kwargs : Any
        As seaborn passed them: ``(p, layer)``.

    Returns
    -------
    Any
        Whatever ``_plot_layer`` returned, unchanged.
    """
    if ContextManager.is_internal_context():
        return _draw_quietly(wrapped, args, kwargs)

    layer = kwargs.get("layer", args[1] if len(args) > 1 else None)
    reading = _reading_for(layer)
    if reading is None:
        return _draw_quietly(wrapped, args, kwargs)

    panels = _panels(instance)
    try:
        pending = instance.__dict__.setdefault(_PENDING, [])
    except AttributeError:
        # A plotter that grew `__slots__` has nowhere to keep this. Declining
        # leaves the chart reading as it did before #615 -- as nothing --
        # which is this module's posture for a mark it cannot read, and far
        # better than an `AttributeError` raised out of the user's draw.
        return _draw_quietly(wrapped, args, kwargs)
    before = {id(ax): {id(artist) for artist in _held(ax, reading)} for ax in panels}

    with ContextManager.set_internal_context():
        drawn = _draw_quietly(wrapped, args, kwargs)

    for ax in panels:
        own = [
            artist for artist in _held(ax, reading) if id(artist) not in before[id(ax)]
        ]
        # A panel this layer did not draw on registers nothing rather than an
        # empty layer, which the reader would be offered and find nothing in
        # (#421). A `col`/`row` grid allocates a panel per combination whether
        # the data holds one or not, so this is the ordinary case and not an
        # edge of it.
        if not own:
            continue
        # Recorded rather than registered, because the legend that names a
        # colour split does not exist yet: `Plotter._make_legend` runs after
        # every layer has been drawn. That is the timing #612 met with
        # `FacetGrid.add_legend()`, and a name can be deferred to render as a
        # callable -- but a *split* cannot, because it decides how many
        # layers there are. So the reading waits for `_register`.
        pending.append((ax, reading, own, layer.get("move")))

    return drawn


def _register(wrapped, instance, args, kwargs) -> Any:
    """
    Draw a whole ``so.Plot`` and register the layers it recorded.

    The second half of a hook deliberately split in two. ``_plot_layer`` is
    the only place that can say which artists a layer drew, and it runs too
    early to say what *names* them: ``Plotter._make_legend`` builds the one
    legend a ``so.Plot`` has after every layer is on the page, so a colour
    split asked about there finds nothing and every chart reads as one
    unnamed layer of every point.

    Deferring the whole registration rather than only the name, because the
    split decides how many layers there are -- and unlike a name, that cannot
    be resolved at render from a callable.

    ``Plot.plot`` is where every route ends up: ``show()``, ``save()`` and
    ``_repr_png_()`` all call it, so wrapping it once covers them.

    Parameters
    ----------
    wrapped : Callable
        ``Plot.plot``.
    instance : Any
        The plot it was called on.
    args, kwargs : Any
        As passed by the caller.

    Returns
    -------
    Plotter
        Whatever ``plot`` returned, unchanged.
    """
    if ContextManager.is_internal_context():
        return wrapped(*args, **kwargs)

    plotter = wrapped(*args, **kwargs)

    for ax, reading, own, move in getattr(plotter, _PENDING, ()):
        for plot_type, handover in _handovers(reading, ax, own, move):
            FigureManager.create_maidr(ax, plot_type, **handover)

    return plotter


def _wrap() -> None:
    """
    Wrap the per-layer draw, or say why it could not be.

    ``seaborn._core.plot.Plotter._plot_layer`` is private twice over -- a
    private method of a private module -- which is why this is guarded where
    ``maidr/patch/histogram.py`` and its neighbours are not. Those wrap
    ``_CategoricalPlotter`` and ``_DistributionPlotter`` methods that
    ``maidr/patch/_seaborn_version.py`` states a floor for, and a seaborn
    below it is turned into a readable ``ImportError``. There is no such floor
    to state here: the name could move in a minor release, and letting that
    take ``import maidr`` down with it would break every *classic* seaborn
    chart over a mark nobody in that process drew.

    Warns
    -----
    UserWarning
        When the method cannot be found, naming what stops reading as a
        consequence.
    """
    try:
        from seaborn._core.plot import Plot, Plotter
    except ImportError:  # pragma: no cover - seaborn without the objects API
        Plot = Plotter = None  # type: ignore[assignment]

    # Both hooks are asked for, because the reading needs both: one says
    # which artists a layer drew and the other says when the legend naming
    # them exists. `Plot is None` is not tested separately -- the import
    # above binds the two together, and `hasattr(None, "plot")` is False, so
    # the short circuit already covers it.
    if (
        Plotter is None
        or not hasattr(Plotter, "_plot_layer")
        or not hasattr(Plot, "plot")
    ):
        warnings.warn(
            "maidr: seaborn._core.plot.Plotter._plot_layer or Plot.plot is "
            "not there to wrap, so seaborn.objects charts are not read. "
            "Every mark -- so.Dot, so.Line, so.Bar -- draws through the "
            "artist API rather than through Axes.scatter/plot/bar, so "
            "nothing else picks them up and the chart registers no layers "
            "at all. Charts written with the classic seaborn functions are "
            "unaffected.",
            stacklevel=2,
        )
        return

    wrapt.wrap_function_wrapper(Plotter, "_plot_layer", _layer)
    wrapt.wrap_function_wrapper(Plot, "plot", _register)


_wrap()
