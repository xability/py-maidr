from __future__ import annotations

import uuid
from typing import Union, Dict
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle
import numpy as np

from maidr.core.enum import PlotType
from maidr.core.plot import MaidrPlot
from maidr.core.enum.maidr_key import MaidrKey
from maidr.exception import ExtractionError
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
        self._maidr_original_data = kwargs.get("_maidr_original_data", None)  # Store original data

        # Store the GID for proper selector generation (legacy/shared)
        self._maidr_gid = None
        # Modern-path separate gids for body and wick
        self._maidr_body_gid = None
        self._maidr_wick_gid = None
        if self._maidr_body_collection:
            self._maidr_gid = self._maidr_body_collection.get_gid()
            self._maidr_body_gid = self._maidr_gid
        elif self._maidr_wick_collection:
            self._maidr_gid = self._maidr_wick_collection.get_gid()
            self._maidr_wick_gid = self._maidr_gid

    def _extract_plot_data(self) -> list[dict]:
        """
        Extract candlestick data from the plot.

        This method processes candlestick plots from both modern (mplfinance.plot) and
        legacy (original_flavor) pipelines, extracting OHLC data and setting up
        highlighting elements and GIDs.

        Returns
        -------
        list[dict]
            List of dictionaries containing candlestick data with keys:
            - 'value': Date string
            - 'open': Opening price (float)
            - 'high': High price (float)
            - 'low': Low price (float)
            - 'close': Closing price (float)
            - 'volume': Volume (float, typically 0 for candlestick-only plots)
        """

        # Get the custom collections from kwargs
        body_collection = self._maidr_body_collection
        wick_collection = self._maidr_wick_collection

        if body_collection and wick_collection:
            # Store the GIDs from the collections (modern path)
            self._maidr_body_gid = body_collection.get_gid()
            self._maidr_wick_gid = wick_collection.get_gid()
            # Keep legacy gid filled for backward compatibility
            self._maidr_gid = self._maidr_body_gid or self._maidr_wick_gid

            # Use the original collections for highlighting
            self._elements = [body_collection, wick_collection]

            # Use the utility class to extract data
            data = MplfinanceDataExtractor.extract_candlestick_data(
                body_collection, wick_collection, self._maidr_date_nums, self._maidr_original_data
            )
            return data

        # Fallback to original detection method
        if not self.axes:
            return []

        ax_ohlc = self.axes[0]

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
                self._maidr_gid = f"maidr-{uuid.uuid4()}"
                # Set GID on all rectangles
                for rect in body_rectangles:
                    rect.set_gid(self._maidr_gid)
            # Keep a dedicated body gid for legacy dict selectors
            self._maidr_body_gid = getattr(self, "_maidr_body_gid", None) or self._maidr_gid

            # Assign a shared gid to wick Line2D (vertical 2-point lines) on the same axis
            wick_lines = []
            for line in ax_ohlc.get_lines():
                try:
                    xydata = line.get_xydata()
                    if xydata is None:
                        continue
                    xy_arr = np.asarray(xydata)
                    if xy_arr.ndim == 2 and xy_arr.shape[0] == 2 and xy_arr.shape[1] >= 2:
                        x0 = float(xy_arr[0, 0])
                        x1 = float(xy_arr[1, 0])
                        if abs(x0 - x1) < 1e-10:
                            wick_lines.append(line)
                except Exception:
                    continue
            if wick_lines:
                if not getattr(self, "_maidr_wick_gid", None):
                    self._maidr_wick_gid = f"maidr-{uuid.uuid4()}"
                for line in wick_lines:
                    line.set_gid(self._maidr_wick_gid)

            # Use the utility class to extract data
            data = MplfinanceDataExtractor.extract_rectangle_candlestick_data(
                body_rectangles, self._maidr_date_nums, self._maidr_original_data
            )
            return data

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

    def _get_selector(self) -> Union[str, Dict[str, str]]:
        """Return selectors for highlighting candlestick elements.

        - Modern path (collections present): return a dict with separate selectors for body, wickLow, wickHigh
        - Legacy path: return a dict with body and shared wick selectors (no open/close keys)
        """
        # Modern path: build structured selectors using separate gids
        if self._maidr_body_collection and self._maidr_wick_collection and self._maidr_body_gid and self._maidr_wick_gid:
            # Determine candle count N
            N = None
            if self._maidr_original_data is not None:
                try:
                    N = len(self._maidr_original_data)
                except Exception:
                    N = None
            if N is None and hasattr(self._maidr_wick_collection, "get_paths"):
                try:
                    wick_paths = len(list(self._maidr_wick_collection.get_paths()))
                    if wick_paths % 2 == 0 and wick_paths > 0:
                        N = wick_paths // 2
                except Exception:
                    pass
            if N is None and hasattr(self._maidr_body_collection, "get_paths"):
                try:
                    body_paths = len(list(self._maidr_body_collection.get_paths()))
                    if body_paths > 0:
                        N = body_paths
                except Exception:
                    pass
            if N is None:
                raise ExtractionError(PlotType.CANDLESTICK, self._maidr_wick_collection)

            selectors = {
                "body": f"g[id='{self._maidr_body_gid}'] > path",
                "wickLow": f"g[id='{self._maidr_wick_gid}'] > path:nth-child(-n+{N})",
                "wickHigh": f"g[id='{self._maidr_wick_gid}'] > path:nth-child(n+{N + 1})",
            }
            return selectors

        # Legacy path: build shared-id selectors; omit open/close
        legacy_selectors = {}
        if getattr(self, "_maidr_body_gid", None) or self._maidr_gid:
            body_gid = getattr(self, "_maidr_body_gid", None) or self._maidr_gid
            legacy_selectors["body"] = f"g[id='{body_gid}'] > path"
        if getattr(self, "_maidr_wick_gid", None):
            legacy_selectors["wick"] = f"g[id='{self._maidr_wick_gid}'] > path"
        if legacy_selectors:
            return legacy_selectors

        # Fallback
        return "g[maidr='true'] > path, g[maidr='true'] > rect"

    def render(self) -> dict:
        """Initialize the MAIDR schema dictionary with basic plot information."""
        base_schema = super().render()
        base_schema[MaidrKey.TITLE] = "Candlestick Chart"
        base_schema[MaidrKey.AXES] = self._extract_axes_data()
        base_schema[MaidrKey.DATA] = self._extract_plot_data()
        # Include selector only if the plot supports highlighting.
        if self._support_highlighting:
            base_schema[MaidrKey.SELECTOR] = self._get_selector()
        return base_schema
