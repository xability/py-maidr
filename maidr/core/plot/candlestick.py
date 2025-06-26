from __future__ import annotations

import matplotlib.dates as mdates
import numpy as np
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle

from maidr.core.enum import PlotType
from maidr.core.plot import MaidrPlot
from maidr.core.enum.maidr_key import MaidrKey
from maidr.util.mplfinance_utils import MplfinanceDataExtractor


class CandlestickPlot(MaidrPlot):
    """
    Specialized candlestick plot class for mplfinance OHLC data.

    This class handles the extraction and processing of candlestick data from mplfinance
    plots, including proper date conversion and data validation.
    """

    def __init__(self, axes: list[Axes], **kwargs) -> None:
        """
        Initialize the CandlestickPlot.

        Parameters
        ----------
        axes : list[Axes]
            A list of Matplotlib Axes objects. Expected to contain at least
            one Axes for OHLC data, and optionally a second for volume data.
        **kwargs : dict
            Additional keyword arguments.
        """
        self.axes = axes
        # Ensure there's at least one axis for the superclass init
        if not axes:
            raise ValueError("Axes list cannot be empty.")
        super().__init__(axes[0], PlotType.CANDLESTICK)

        # Store custom collections passed from mplfinance patch
        self._maidr_wick_collection = kwargs.get("_maidr_wick_collection", None)
        self._maidr_body_collection = kwargs.get("_maidr_body_collection", None)
        self._maidr_date_nums = kwargs.get("_maidr_date_nums", None)

        # Store the GID for proper selector generation
        self._maidr_gid = None
        if self._maidr_body_collection:
            self._maidr_gid = self._maidr_body_collection.get_gid()
        elif self._maidr_wick_collection:
            self._maidr_gid = self._maidr_wick_collection.get_gid()

    def _extract_plot_data(self) -> list[dict]:
        """Extract candlestick data from the plot."""

        # Get the custom collections from kwargs
        body_collection = self._maidr_body_collection
        wick_collection = self._maidr_wick_collection

        if body_collection and wick_collection:
            # Store the GID from the body collection for highlighting
            self._maidr_gid = body_collection.get_gid()

            # Use the original collections for highlighting
            self._elements = [body_collection, wick_collection]

            # Use the utility class to extract data
            return MplfinanceDataExtractor.extract_candlestick_data(
                body_collection, wick_collection, self._maidr_date_nums
            )

        # Fallback to original detection method
        if not self.axes:
            return []

        ax_ohlc = self.axes[0]
        candles = []

        # Look for Rectangle patches (original_flavor candlestick)
        body_rectangles = []
        for patch in ax_ohlc.patches:
            if isinstance(patch, Rectangle):
                body_rectangles.append(patch)

        if body_rectangles:
            # Set elements for highlighting
            self._elements = body_rectangles

            # Generate a GID for highlighting if none exists
            if not self._maidr_gid:
                import uuid

                self._maidr_gid = f"maidr-{uuid.uuid4()}"
                # Set GID on all rectangles
                for rect in body_rectangles:
                    rect.set_gid(self._maidr_gid)

            # Use the utility class to extract data
            return MplfinanceDataExtractor.extract_rectangle_candlestick_data(
                body_rectangles, self._maidr_date_nums
            )

        return []

    def _extract_axes_data(self) -> dict:
        """
        Extract the plot's axes data including labels.

        Returns
        -------
        dict
            Dictionary containing x and y axis labels.
        """
        x_labels = self.ax.get_xlabel()
        if not x_labels:
            x_labels = self.extract_shared_xlabel(self.ax)
        if not x_labels:
            x_labels = "X"
        return {MaidrKey.X: x_labels, MaidrKey.Y: self.ax.get_ylabel()}

    def _get_selector(self) -> str:
        """Return the CSS selector for highlighting candlestick elements in the SVG output."""
        # Use the stored GID if available, otherwise fall back to generic selector
        if self._maidr_gid:
            # Use the full GID as the id attribute (since that's what's in the SVG)
            selector = (
                f"g[id='{self._maidr_gid}'] > path, g[id='{self._maidr_gid}'] > rect"
            )
        else:
            selector = "g[maidr='true'] > path, g[maidr='true'] > rect"
        return selector

    def render(self) -> dict:
        """Initialize the MAIDR schema dictionary with basic plot information."""
        title = "Candlestick Chart"

        maidr_schema = {
            MaidrKey.TYPE: self.type,
            MaidrKey.TITLE: title,
            MaidrKey.AXES: self._extract_axes_data(),
            MaidrKey.DATA: self._extract_plot_data(),
        }

        # Include selector only if the plot supports highlighting.
        if self._support_highlighting:
            maidr_schema[MaidrKey.SELECTOR] = self._get_selector()

        return maidr_schema
