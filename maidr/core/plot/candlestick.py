from __future__ import annotations

from typing import Union, Dict
from matplotlib.axes import Axes
import pandas as pd

from maidr.core.enum import PlotType
from maidr.core.plot import MaidrPlot
from maidr.core.enum.maidr_key import MaidrKey
from maidr.exception import ExtractionError


class CandlestickPlot(MaidrPlot):
    """
    Specialized candlestick plot class for mplfinance OHLC data.

    This class extracts candlestick data directly from the original DataFrame
    without any formatting or transformation.
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
        if not axes:
            raise ValueError("Axes list cannot be empty.")
        super().__init__(axes[0], PlotType.CANDLESTICK)

        # Store collections passed from mplfinance patch
        self._maidr_wick_collection = kwargs.get("_maidr_wick_collection", None)
        self._maidr_body_collection = kwargs.get("_maidr_body_collection", None)
        self._maidr_original_data = kwargs.get("_maidr_original_data", None)

        # Store the GID for selector generation
        self._maidr_gid = None
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
        Extract candlestick data directly from the original DataFrame.

        Returns
        -------
        list[dict]
            List of dictionaries containing candlestick data with keys:
            - 'value': Date string (raw from DataFrame index)
            - 'open': Opening price (float)
            - 'high': High price (float)
            - 'low': Low price (float)
            - 'close': Closing price (float)
            - 'volume': Volume (float)
        """
        body_collection = self._maidr_body_collection
        wick_collection = self._maidr_wick_collection

        if body_collection and wick_collection:
            # Store the GIDs from the collections
            self._maidr_body_gid = body_collection.get_gid()
            self._maidr_wick_gid = wick_collection.get_gid()
            self._maidr_gid = self._maidr_body_gid or self._maidr_wick_gid

            # Use the original collections for highlighting
            self._elements = [body_collection, wick_collection]

            # Extract data directly from DataFrame
            if self._maidr_original_data is not None and isinstance(
                self._maidr_original_data, pd.DataFrame
            ):
                return self._extract_from_dataframe(self._maidr_original_data)

        return []

    def _extract_from_dataframe(self, df: pd.DataFrame) -> list[dict]:
        """
        Extract candlestick data directly from DataFrame without any formatting.

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame with OHLC data and DatetimeIndex.

        Returns
        -------
        list[dict]
            List of candlestick data dictionaries with raw values.
        """
        candles = []

        for i in range(len(df)):
            try:
                # Get date directly from index - raw representation
                date_value = str(df.index[i])

                # Get OHLC values directly from DataFrame columns
                open_price = float(df.iloc[i]["Open"])
                high_price = float(df.iloc[i]["High"])
                low_price = float(df.iloc[i]["Low"])
                close_price = float(df.iloc[i]["Close"])

                # Get volume if available, otherwise 0
                volume = float(df.iloc[i].get("Volume", 0.0))

                candle_data = {
                    "value": date_value,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": volume,
                }
                candles.append(candle_data)
            except (KeyError, IndexError, ValueError, TypeError):
                continue

        return candles

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
        if (
            self._maidr_body_collection
            and self._maidr_wick_collection
            and self._maidr_body_gid
            and self._maidr_wick_gid
        ):
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
