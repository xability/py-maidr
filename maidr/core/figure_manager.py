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


class FigureManager:
    """
    Manages creation and retrieval of Maidr instances associated with matplotlib figures.

    This class provides methods to manage Maidr objects which facilitate the organization and
    manipulation of plots within matplotlib figures.

    Attributes
    ----------
    figs : dict
        A dictionary that maps matplotlib Figure objects to their corresponding Maidr instances.

    Methods
    -------
    create_maidr(ax, plot_type, **kwargs)
        Creates a Maidr instance for the given Axes and plot type, and adds a plot to it.
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
                    cls._instance = super(FigureManager, cls).__new__()
        return cls._instance

    @classmethod
    def create_maidr(cls, ax: Axes, plot_type: PlotType, **kwargs) -> Maidr:
        """Create a Maidr instance for the given Axes and plot type, and adds a plot to it."""
        if ax is None:
            raise ValueError("No plot found.")
        if plot_type is None:
            raise ValueError("No plot type found.")
        if ax.get_figure() is None:
            raise ValueError(f"No figure found for axis: {ax}.")

        # Add plot to the Maidr object associated with the plot's figure.
        maidr = cls._get_maidr(ax.get_figure(), plot_type)
        plot = MaidrPlotFactory.create(ax, plot_type, **kwargs)
        maidr.plots.append(plot)
        return maidr

    @classmethod
    def _get_maidr(cls, fig: Figure, plot_type: PlotType) -> Maidr:
        """Retrieve or create a Maidr instance for the given Figure."""
        if fig not in cls.figs.keys():
            cls.figs[fig] = Maidr(fig, plot_type)
        return cls.figs[fig]

    @classmethod
    def get_maidr(cls, fig: Figure) -> Maidr:
        """Retrieve the Maidr instance for the given Figure."""
        if fig not in cls.figs.keys():
            raise KeyError(f"No MAIDR found for figure: {fig}.")
        return cls.figs[fig]

    @classmethod
    def destroy(cls, fig: Figure) -> None:
        try:
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
