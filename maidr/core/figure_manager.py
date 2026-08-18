from __future__ import annotations

import threading
from typing import Any

from matplotlib.artist import Artist
from matplotlib.axes import Axes
from matplotlib.container import BarContainer
from matplotlib.figure import Figure

from maidr.core import Maidr
from maidr.core.enum import PlotType
from maidr.core.plot import MaidrPlotFactory
from maidr.exception.unsupported_plot_error import UnsupportedPlotError


class FigureManager:
    """
    Manages creation and retrieval of Maidr instances associated with figures.

    This class provides methods to manage Maidr objects which facilitate the
    organization and manipulation of plots within matplotlib figures.

    Attributes
    ----------
    figs : dict
        A dictionary that maps matplotlib Figure objects to their corresponding
        Maidr instances.

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

    figs = {}

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
        # between them. The lock costs one uncontended acquire per layer.
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
        if fig not in cls.figs.keys():
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
