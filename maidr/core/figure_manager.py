from __future__ import annotations

import threading
import weakref
from typing import Any

from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.container import BarContainer
from matplotlib.figure import Figure

from maidr.core import Maidr
from maidr.core.enum import PlotType
from maidr.core.plot import MaidrPlotFactory
from maidr.exception.unsupported_plot_error import UnsupportedPlotError


class _FigureRecords:
    """A mapping from ``Figure`` to ``Maidr`` that stores each entry on its key.

    Behaves as the plain ``dict`` this replaced -- ``figs[fig]``, ``fig in
    figs``, ``.get``, ``.pop``, ``.clear`` -- but the value is kept in the
    figure's own ``__dict__`` rather than in a module-level table.

    That is the whole point. A module-level dict is a strong reference from a
    class attribute, so a figure stayed reachable for the life of the process
    even after the application dropped it and matplotlib closed it (#456).
    Registration happens when a chart is *plotted*, not when it is rendered,
    so this applied to every supported figure -- and the ``plt.show()`` path
    only escaped it because the backend calls :meth:`FigureManager.destroy`
    explicitly. A Shiny or Streamlit render never goes through ``plt.show``.

    Storing the record on the figure makes the whole graph -- figure, its
    ``Maidr``, its layers, and the artists those layers hold -- one isolated
    reference cycle once the application lets go, which the cyclic collector
    reclaims. Measured on a figure built, rendered and closed:

    ======================================  =========
    registry                                collected
    ======================================  =========
    module-level dict                       no
    record stored on the figure             yes
    ======================================  =========

    This is deliberately *not* a ``WeakKeyDictionary``, which was tried first
    and freed nothing: every value reaches its own key -- ``Maidr._fig``,
    ``MaidrPlot.ax``, and each subclass's own artist handles such as
    ``BarPlot._own_bars`` -- so the entry keeps the figure alive and the weak
    key never dies. #498 records that chain. Keeping the value *on* the key
    sidesteps it entirely: a value that reaches its key is exactly what a
    cycle is, and cycles are collectable as long as nothing outside points in.

    Membership is by identity either way -- ``Figure`` inherits ``__hash__``
    and ``__eq__`` from ``object``, so dict lookup was already identity.

    ``_seen`` exists only so the mapping can be enumerated and cleared. It
    holds weak references and no values, so it retains nothing.
    """

    #: Attribute the record is stored under on the figure.
    _ATTR = "_maidr_record"

    #: Distinguishes "no default given" from a default of ``None``.
    _MISSING = object()

    def __init__(self) -> None:
        self._seen: weakref.WeakSet = weakref.WeakSet()

    def __contains__(self, fig: Figure) -> bool:
        return hasattr(fig, self._ATTR)

    def __getitem__(self, fig: Figure) -> Maidr:
        try:
            return getattr(fig, self._ATTR)
        except AttributeError:
            raise KeyError(fig) from None

    def __setitem__(self, fig: Figure, maidr: Maidr) -> None:
        setattr(fig, self._ATTR, maidr)
        self._seen.add(fig)

    def __delitem__(self, fig: Figure) -> None:
        try:
            delattr(fig, self._ATTR)
        except AttributeError:
            raise KeyError(fig) from None
        self._seen.discard(fig)

    def __len__(self) -> int:
        # Not just for completeness: without it `if figs:` is always true,
        # which is the one way a partial mapping fails *quietly* rather than
        # with a `TypeError`.
        return sum(1 for _ in self)

    def __iter__(self):
        # Over a snapshot: `_seen` is weak, so iterating it directly can drop
        # members mid-loop when a figure is collected by another thread.
        return iter([fig for fig in list(self._seen) if fig in self])

    def get(self, fig: Figure, default: Any = None) -> Any:
        return getattr(fig, self._ATTR, default)

    def pop(self, fig: Figure, default: Any = _MISSING) -> Any:
        maidr = getattr(fig, self._ATTR, self._MISSING)
        if maidr is self._MISSING:
            if default is self._MISSING:
                raise KeyError(fig)
            return default
        delattr(fig, self._ATTR)
        self._seen.discard(fig)
        return maidr

    def clear(self) -> None:
        for fig in self:
            self.pop(fig, None)


class FigureManager:
    """
    Manages creation and retrieval of Maidr instances associated with figures.

    This class provides methods to manage Maidr objects which facilitate the
    organization and manipulation of plots within matplotlib figures.

    Attributes
    ----------
    figs : _FigureRecords
        Maps matplotlib Figure objects to their corresponding Maidr instances.
        Reads as a dict; each entry is stored on its own figure so that
        registering a chart no longer keeps it alive for the life of the
        process (#456). See :class:`_FigureRecords`.

        Reads reach worker threads since #504, which renders off the Shiny
        event loop. Both write paths -- :meth:`_get_maidr`'s insert and
        :meth:`destroy`'s pop -- take ``_lock``, as does the paired append
        of ``plots`` and ``selector_ids`` in :meth:`create_maidr`, which
        must stay index-aligned. Individual dict and list operations are
        atomic under the GIL; the lock is for the check-then-act and the
        paired write around them.

    Methods
    -------
    create_maidr(ax, plot_type, **kwargs)
        Creates a Maidr instance for the given Axes and plot type, and adds a
        plot to it.
    _get_maidr(fig)
        Retrieves or creates a Maidr instance associated with the given Figure.
    get_axes(artist)
        Recursively extracts Axes objects from the input artist or container.
    """

    figs = _FigureRecords()

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super(FigureManager, cls).__new__(cls)
        return cls._instance

    @classmethod
    def create_maidr(
        cls, axes: Axes | list[Axes], plot_type: PlotType, **kwargs
    ) -> Maidr:
        """Create a Maidr instance for the given Axes and plot type, and
        adds a plot to it."""
        if axes is None:
            raise ValueError("No plot found.")
        if plot_type is None:
            raise ValueError("No plot type found.")
        if isinstance(axes, list):
            ax = axes[0]
        else:
            ax = axes
        if ax.get_figure() is None:
            raise ValueError(f"No figure found for axis: {ax}.")

        # Add plot to the Maidr object associated with the plot's figure.
        maidr = cls._get_maidr(ax.get_figure(), plot_type)

        # Extraction stays *outside* the lock: it is the expensive part and
        # touches only the artists it was handed.
        plot = MaidrPlotFactory.create(axes, plot_type, **kwargs)

        # The two appends do not. `plots` and `selector_ids` are separate
        # lists held index-aligned -- `Maidr._flatten_maidr` and
        # `_create_html_tag` both zip them, and `_drop_superseded_layers`
        # documents what misalignment costs: every surviving layer wears its
        # neighbour's id, so the highlight lands on the wrong mark with
        # nothing raised.
        #
        # Each `append` is atomic under the GIL; the *pair* is not. Two
        # concurrent registrations on one figure can interleave between
        # them, which reproduces deterministically:
        #
        #     plots        ['plot-A', 'plot-B']
        #     selector_ids ['id-B',   'id-A']
        with cls._lock:
            maidr.plots.append(plot)
            maidr.selector_ids.append(Maidr._unique_id())
        return maidr

    @classmethod
    def _get_maidr(cls, fig: Figure, plot_type: PlotType) -> Maidr:
        """
        Retrieve or create a Maidr instance for the given Figure.

        A figure that already has one is returned as it is. It used to have
        its ``plot_type`` raised here whenever a layer of higher priority was
        registered -- DODGED and STACKED outranking everything else -- so that
        ``_flatten_maidr`` could consult one figure-wide answer to decide
        whether bar layers should be collapsed. That is what made a stacked
        bar in one panel delete layers from every other panel, and the
        question is asked per position now, so the table and the update it
        served are both gone (#376).

        Parameters
        ----------
        fig : Figure
            The matplotlib figure to get or create a Maidr instance for.
        plot_type : PlotType
            The type of the layer being registered. Used only when the figure
            is new, to record what it started as.

        Returns
        -------
        Maidr
            The Maidr instance associated with the figure.
        """
        # Guarded because this is a check-then-act on shared state, and the
        # thread it runs on stopped being guaranteed when the Shiny renderer
        # moved off the event loop (#504, #505). Registration still happens
        # on the loop thread there -- plotting is the user's code, which runs
        # before the render is offloaded -- but that is a property of where
        # callers happen to live, not of this method, and losing it would
        # mint two `Maidr` objects for one figure and split a chart's layers
        # between them. Two uncontended acquires per registered layer, counting the
        # paired append in `create_maidr`.
        with cls._lock:
            if fig not in cls.figs:
                cls.figs[fig] = Maidr(fig, plot_type)
            return cls.figs[fig]

    @classmethod
    def get_maidr(cls, fig: Figure) -> Maidr:
        """
        Retrieve the Maidr instance for the given Figure.

        Raises
        ------
        UnsupportedPlotError
            When maidr never registered the figure -- because its chart type
            is not supported, or because nothing has been drawn on it yet.
            A subclass of ``KeyError``, so the matplotlib backend's existing
            ``except KeyError`` around this call still catches it; the message
            is the change, since "No MAIDR found for figure" described maidr's
            own bookkeeping rather than anything a user could act on (#443).
        """
        # Locked for the same reason the writes are: this is a check-then-act,
        # and `destroy` popping between the two lines would turn the careful
        # `UnsupportedPlotError` below into a bare `KeyError` -- losing the
        # message that is the whole point of raising it.
        with cls._lock:
            if fig not in cls.figs:
                raise UnsupportedPlotError(fig)
            return cls.figs[fig]

    @classmethod
    def destroy(cls, fig: Figure) -> None:
        # Under the same lock as the registering writes: this is the second
        # write path into `figs`, and a `pop` racing a `_get_maidr` insert
        # decides which of them wins by timing.
        try:
            with cls._lock:
                maidr = cls.figs.pop(fig)
        except KeyError:
            return
        # Teardown runs outside the lock, deliberately -- it is real work,
        # not a dict operation. That leaves one gap this does not close: a
        # `create_maidr` that took its reference just before the pop can
        # still append to an object no longer in `figs`. Its layers go
        # nowhere. Independent of this lock, and unchanged by #456: the
        # record moving onto the figure changes how long an entry lives,
        # not who may be holding a reference to it mid-registration.
        maidr.destroy()
        del maidr

    @staticmethod
    def get_axes(
        artist: Artist | Axes | BarContainer | dict | list | None,
    ) -> Any:
        """Recursively extract Axes objects from the input artist or container."""
        if artist is None:
            return None
        elif isinstance(artist, Axes):
            return artist
        elif isinstance(artist, BarContainer):
            # Get axes from the first occurrence of any child artist
            return next(
                child_artist.axes
                for child_artist in artist.get_children()
                if isinstance(child_artist.axes, Axes)
            )
        elif isinstance(artist, Artist):
            return artist.axes
        elif isinstance(artist, dict):
            return next(
                _artist.axes
                for _artists in artist.values()
                for _artist in _artists
                if isinstance(_artist.axes, Axes)
            )
        elif isinstance(artist, list):
            return next(
                _artist.axes for _artist in artist if isinstance(_artist.axes, Axes)
            )
