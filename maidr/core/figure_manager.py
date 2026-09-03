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

    Reads as the plain ``dict`` this replaced -- ``figs[fig]``, ``fig in
    figs``, ``.get``, ``.pop``, ``.clear``, iteration, ``len`` -- but the
    value lives in the figure's own ``__dict__`` rather than in a
    module-level table. A class-level dict kept every registered figure
    reachable for the life of the process; storing the record on the figure
    makes the whole graph one isolated cycle once the caller lets go, which
    the collector reclaims (#456).

    Not a ``WeakKeyDictionary``: every value reaches its own key --
    ``Maidr._fig``, ``MaidrPlot.ax``, and each subclass's artist handles --
    so the entry would keep the figure alive and the weak key would never
    die. #498 records that chain.

    Invariants
    ----------
    A record belongs to a figure only if ``record.fig is fig``.
        Every read goes through :meth:`_record`, which enforces it, and the
        one write refuses a record that fails it. Without this a
        ``copy.copy`` of a figure -- which copies ``__dict__`` entries by
        reference -- would answer as registered and hand back the
        *original's* chart.

    ``_seen`` holds every figure this mapping can enumerate.
        It backs iteration, ``len`` and ``clear`` only, weakly, so it
        retains nothing. :meth:`_record` adds to it, because ``deepcopy``
        and ``pickle`` install a valid record without going through
        :meth:`__setitem__`. **A read therefore mutates shared state**,
        which is why every operation takes ``_guard``.

    Notes
    -----
    Reclamation is the cyclic collector's rather than refcounting's, so a
    host running ``gc.disable()`` gets the growth back between collections.
    In proportion: a bare matplotlib ``Figure`` is not refcount-reclaimable
    either, since its artists refer back to it, so turning the collector off
    leaks figures with or without this package.

    The approach leans on ``Figure`` accepting instance attributes and on
    ``copy``/``deepcopy``/``pickle`` treating ``__dict__`` as they do today.
    Neither is a contract matplotlib publishes. If either changes the
    failure is quiet -- the attribute is simply absent and a figure reads as
    unregistered -- so ``tests/core/test_figure_manager.py`` pins all three
    behaviours rather than leaving them to be assumed.
    """

    #: Attribute the record is stored under on the figure.
    _ATTR = "_maidr_record"

    #: Distinguishes "no default given" from a default of ``None``.
    _MISSING = object()

    def __init__(self) -> None:
        self._seen: weakref.WeakSet = weakref.WeakSet()
        # Its own lock, not `FigureManager._lock`: `figs` is reachable
        # directly and a caller cannot be relied on to hold that one.
        # Reentrant because `clear` walks `__iter__`, which asks
        # `__contains__`.
        #
        # `FigureManager._lock` is still required for what this cannot do --
        # spanning the check-then-act in `_get_maidr` and the paired append
        # in `create_maidr`.
        #
        # Without this, concurrent add/remove during iteration raises
        # `RuntimeError: Set changed size during iteration`. Untested here:
        # provoking it needs sustained contention and detects about half the
        # time. `test_one_thread_cannot_enter_the_registry_while_another_is_inside`
        # asserts the exclusion this provides instead, deterministically.
        self._guard = threading.RLock()

    def _record(self, fig: Figure) -> Any:
        """This figure's own record, or ``_MISSING``.

        Returns
        -------
        Maidr or object
            The record when ``record.fig is fig``, else the ``_MISSING``
            sentinel. A missing attribute, a record naming another figure,
            and a record whose ``Maidr`` has been destroyed (``Maidr.fig``
            raising after ``Maidr.destroy``) are all "not registered" --
            the last because a shallow copy can outlive the pop that
            detached the original, and a membership test must answer a bool
            rather than raise.

        Also brings ``_seen`` up to date, per the class's second invariant.
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
        # Upholds the ownership invariant at the one write, so the mapping
        # cannot hold a record no read would return. The dict this replaced
        # would have stored a mismatched record and handed it back.
        if maidr.fig is not fig:
            raise ValueError(
                "a figure's record must be the Maidr for that figure; "
                f"{maidr!r} names a different one"
            )
        with self._guard:
            setattr(fig, self._ATTR, maidr)
            self._seen.add(fig)

    def __delitem__(self, fig: Figure) -> None:
        # Through `_record`, so `del figs[fig]` and `figs.pop(fig)` agree
        # about what is registered.
        with self._guard:
            if self._record(fig) is self._MISSING:
                raise KeyError(fig)
            self._delete(fig)

    def _delete(self, fig: Figure) -> None:
        # Tolerant of a lost race: the entry the caller wanted gone is gone
        # either way, and raising `AttributeError` where the class promises
        # `KeyError` would be the wrong answer.
        with self._guard:
            try:
                delattr(fig, self._ATTR)
            except AttributeError:
                pass
            self._seen.discard(fig)

    def __len__(self) -> int:
        # Without it `if figs:` is always true -- the one way a partial
        # mapping fails quietly rather than with a `TypeError`.
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
        """Drop every record in ``_seen`` -- which is not quite every record.

        A ``deepcopy``/``pickle`` clone enters ``_seen`` only when its record
        is first read, so one that has never been looked up survives this.
        Closing the gap would need a hook on the copy, meaning registry
        knowledge inside ``Maidr.__deepcopy__``/``__setstate__``; not worth
        it, since the clone's record is reachable only through the clone, so
        this is an enumeration gap rather than a leak. ``clear`` exists for
        test isolation.
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
        """
        Recursively extract Axes objects from the input artist or container.

        The list branch **recurses** rather than reading ``.axes`` off each
        element, because a list does not promise to hold artists.
        ``Axes.hist`` returns one for every multi-dataset call and fills it
        with whatever the ``histtype`` drew -- a ``BarContainer`` per dataset
        for ``bar`` and ``barstacked``, a list of ``Polygon``\ s for ``step``
        and ``stepfilled``. Neither has ``.axes``, so all four raised from the
        caller's own ``ax.hist(...)`` line, naming matplotlib rather than the
        accessibility layer that actually failed (#553)::

            ax.hist([a, b], bins=2)
            AttributeError: 'BarContainer' object has no attribute 'axes'

        Nothing found is ``None`` rather than a bare ``StopIteration``, which
        is the answer every caller here is written for and the shape of
        failure #388, #520 and #529 removed from the extractors for the same
        reason.

        Accepted inputs, and what each resolves to: an ``Axes`` (itself); a
        ``BarContainer`` (the axes of its first child); any other ``Artist``
        (its ``.axes`` -- for a ``Figure`` that is the list of its axes); a
        dict of artist lists and a list (the first ``Axes`` found); and a
        seaborn ``FacetGrid``, ``JointGrid`` or ``PairGrid`` (every axes of
        its figure, as a list). ``None`` resolves to ``None``.
        """
        if artist is None:
            return None
        elif isinstance(artist, Axes):
            return artist
        elif isinstance(artist, BarContainer):
            # Get axes from the first occurrence of any child artist
            return next(
                (
                    child_artist.axes
                    for child_artist in artist.get_children()
                    if isinstance(child_artist.axes, Axes)
                ),
                None,
            )
        elif isinstance(artist, Artist):
            return artist.axes
        elif isinstance(artist, dict):
            return next(
                (
                    _artist.axes
                    for _artists in artist.values()
                    for _artist in _artists
                    if isinstance(_artist.axes, Axes)
                ),
                None,
            )
        elif isinstance(artist, list):
            return next(
                (
                    resolved
                    for resolved in (
                        FigureManager.get_axes(_artist) for _artist in artist
                    )
                    if isinstance(resolved, Axes)
                ),
                None,
            )
        elif isinstance(getattr(artist, "figure", None), Figure):
            # seaborn's figure-level functions -- lmplot, catplot, displot,
            # jointplot, pairplot -- return a FacetGrid, JointGrid or
            # PairGrid. A Grid is not an Artist, so the branches above fell
            # through and this returned None, and every entry point raised on
            # the value the user was handed -- even though each layer was
            # registered on the grid's figure and its axes carry them
            # (#694). Duck-typed on `.figure`
            # so this module does not import seaborn; on the >=0.13 floor
            # every Grid exposes it (`.fig` is the deprecated spelling).
            return artist.figure.axes
