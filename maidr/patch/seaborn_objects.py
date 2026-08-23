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
from maidr.core.plot.barplot import DRAWN_BARS
from maidr.core.plot.scatterplot import DRAWN_POINTS
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
        handovers = (
            [{reading.binding: one} for one in own]
            if reading.singular
            else [{reading.binding: own}]
        )
        for handover in handovers:
            FigureManager.create_maidr(ax, reading.plot_type, **handover)

    return drawn


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
        from seaborn._core.plot import Plotter
    except ImportError:  # pragma: no cover - seaborn without the objects API
        Plotter = None  # type: ignore[assignment]

    if Plotter is None or not hasattr(Plotter, "_plot_layer"):
        warnings.warn(
            "maidr: seaborn._core.plot.Plotter._plot_layer is not there to "
            "wrap, so seaborn.objects charts are not read. Every mark -- "
            "so.Dot, so.Line, so.Bar -- draws through the artist API rather "
            "than through Axes.scatter/plot/bar, so nothing else picks them "
            "up and the chart registers no layers at all. Charts written "
            "with the classic seaborn functions are unaffected.",
            stacklevel=2,
        )
        return

    wrapt.wrap_function_wrapper(Plotter, "_plot_layer", _layer)


_wrap()
