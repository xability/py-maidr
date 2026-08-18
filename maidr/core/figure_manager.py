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
        # Reentrant because this class calls itself: `clear` walks `__iter__`,
        # which asks `__contains__`, and pops as it goes.
        #
        # Its own lock rather than `FigureManager._lock`, because a caller
        # cannot be relied on to hold that one. `figs` is a public class
        # attribute that reads like a dict, and `if fig in FigureManager.figs`
        # is the natural thing to write -- but since the record moved onto the
        # figure a lookup also updates `_seen`, so that apparently-read-only
        # line races. Making each operation self-contained means the contract
        # is enforced instead of documented.
        #
        # `FigureManager._lock` is still needed and still does something this
        # cannot: it spans the *compound* operations -- the check-then-act in
        # `_get_maidr`, and the paired append in `create_maidr` -- which no
        # per-operation lock can make atomic.
        #
        # What goes wrong without this: threads adding and removing entries
        # while others iterate raise `RuntimeError: Set changed size during
        # iteration` out of `__iter__`. Reproduced 3 of 3 against a build
        # with this lock removed, and 0 of 3 with it.
        #
        # Deliberately not covered by a test. Detection needs sustained
        # contention -- a bounded version of that harness detected on only
        # about half its runs, and raising the budget did not improve it,
        # so the rate is thread-scheduling luck rather than duration. A
        # coin-flip guard costing a busy-waiting second per suite run is
        # worth less than this comment.
        self._guard = threading.RLock()

    def _record(self, fig: Figure) -> Any:
        """This figure's own record, or ``_MISSING``.

        The ownership check is not a formality. ``copy.copy`` on a ``Figure``
        copies the ``__dict__`` entries themselves, so a shallow copy would
        inherit the original's record and answer as registered -- handing
        back a ``Maidr`` bound to a *different* figure, and rendering the
        original's chart under the copy's name. The module-level dict could
        not do that, because only the object actually inserted was ever a
        key.

        ``deepcopy`` and ``pickle`` are the opposite case and are left
        working: both rebuild the record alongside the figure, so the copy's
        record points at the copy and it is genuinely registered. Neither
        goes through :meth:`__setitem__`, though -- they write ``__dict__``
        directly -- so a legitimately owned record is added to ``_seen``
        here. Without that a copied figure answered ``in`` but was missing
        from ``list(figs)``, uncounted by ``len``, and survived ``clear()``.

        The ``AttributeError`` guard covers a record whose ``Maidr`` has been
        destroyed. ``FigureManager.destroy`` pops the record before calling
        ``Maidr.destroy()``, which deletes ``_fig`` -- but it pops it off the
        figure it was given, and a shallow copy taken beforehand still holds
        the same object. Reading ``record.fig`` there raised out of a
        membership test, which has to answer a bool.
        """
        record = getattr(fig, self._ATTR, self._MISSING)
        if record is self._MISSING:
            return self._MISSING
        try:
            owner = record.fig
        except AttributeError:
            return self._MISSING
        if owner is not fig:
            return self._MISSING
        with self._guard:
            self._seen.add(fig)
        return record

    def __contains__(self, fig: Figure) -> bool:
        return self._record(fig) is not self._MISSING

    def __getitem__(self, fig: Figure) -> Maidr:
        record = self._record(fig)
        if record is self._MISSING:
            raise KeyError(fig)
        return record

    def __setitem__(self, fig: Figure, maidr: Maidr) -> None:
        # Refused rather than stored, because every read enforces ownership
        # and a record naming another figure could not be read back: the
        # write appeared to succeed, left the attribute set, and `figs[fig]`
        # then raised `KeyError`. The dict this replaced would have stored
        # and returned it. Raising puts the error at the mistake instead of
        # at a lookup somewhere else.
        if maidr.fig is not fig:
            raise ValueError(
                "a figure's record must be the Maidr for that figure; "
                f"{maidr!r} names a different one"
            )
        with self._guard:
            setattr(fig, self._ATTR, maidr)
            self._seen.add(fig)

    def __delitem__(self, fig: Figure) -> None:
        # Through `_record` like every other read, so that `del figs[fig]`
        # and `figs.pop(fig)` agree about what is registered. Deleting
        # straight off the attribute would succeed for a shallow copy that
        # `pop` refuses -- two spellings of one operation disagreeing.
        with self._guard:
            if self._record(fig) is self._MISSING:
                raise KeyError(fig)
            self._delete(fig)

    def _delete(self, fig: Figure) -> None:
        # `delattr` after a `_record` check is a check-then-act, where the
        # dict operation it replaced was atomic. `FigureManager` holds
        # `_lock` across both, but `figs` is reachable directly, so a caller
        # that does not would otherwise get an `AttributeError` out of `pop`
        # where the class promises a `KeyError` -- or nothing, since the
        # entry it wanted gone is gone either way.
        with self._guard:
            try:
                delattr(fig, self._ATTR)
            except AttributeError:
                pass
            self._seen.discard(fig)

    def __len__(self) -> int:
        # Not just for completeness: without it `if figs:` is always true,
        # which is the one way a partial mapping fails *quietly* rather than
        # with a `TypeError`.
        return sum(1 for _ in self)

    def __iter__(self):
        # Over a snapshot: `_seen` is weak, so iterating it directly can drop
        # members mid-loop when a figure is collected by another thread.
        with self._guard:
            return iter([fig for fig in list(self._seen) if fig in self])

    def get(self, fig: Figure, default: Any = None) -> Any:
        record = self._record(fig)
        return default if record is self._MISSING else record

    def pop(self, fig: Figure, default: Any = _MISSING) -> Any:
        with self._guard:
            maidr = self._record(fig)
            if maidr is self._MISSING:
                if default is self._MISSING:
                    raise KeyError(fig)
                return default
            self._delete(fig)
            return maidr

    def clear(self) -> None:
        """Drop every record this mapping knows about.

        "Knows about" is the caveat, and it is not fixable from here.
        ``_seen`` learns of a figure when its record is written or read, and
        ``deepcopy``/``pickle`` do neither -- they rebuild ``__dict__``
        directly. A clone whose record has never been looked up is therefore
        still registered afterwards:

        ======================================  ==================
        clone                                   dropped by clear
        ======================================  ==================
        read once before the clear              yes
        never read                              no
        ======================================  ==================

        Closing it would need a hook on the copy itself, which means putting
        registry knowledge into ``Maidr.__deepcopy__``/``__setstate__``.
        Not worth it for what this costs: nothing outlives the clone, since
        its record is reachable only through it, so this is an enumeration
        gap rather than a leak. ``clear`` exists for test isolation.
        """
        with self._guard:
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

        Every method above holds ``_lock``, and a direct caller of ``figs``
        must too -- including for what look like reads. Since #456 a lookup
        also updates the bookkeeping behind iteration, so ``in`` and
        ``get`` mutate shared state rather than only observing it.

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
            maidr = cls.figs.get(fig)
            if maidr is None:
                maidr = Maidr(fig, plot_type)
                cls.figs[fig] = maidr
            return maidr

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
            maidr = cls.figs.get(fig)
            if maidr is None:
                raise UnsupportedPlotError(fig)
            return maidr

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
