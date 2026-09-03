from __future__ import annotations

import math
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
        if self._maidr_wick_collection:
            self._maidr_wick_gid = self._maidr_wick_collection.get_gid()
            if not self._maidr_gid:
                self._maidr_gid = self._maidr_wick_gid

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

            # Use the original collections for highlighting. Extended rather
            # than rebound, so `self._elements` stays the list `render()`
            # cleared rather than becoming a different one.
            self._elements.extend([body_collection, wick_collection])

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
            List of candlestick data dictionaries with raw values. A row whose
            open, high, low or close is not finite is left out; a missing or
            non-finite volume is reported as ``0.0``.

        Notes
        -----
        The frame is read one column at a time. Building ``df.iloc[i]`` for
        every row constructs a fresh Series (with dtype upcasting) five times
        per candle, which came to about 0.5 ms a row -- 39% of a render of a
        decade of daily bars (#706). Column access gives the same values.

        A row mplfinance draws as a gap (all four prices NaN) is skipped rather
        than emitted, for the reason `test_non_finite_coordinates.py` gives:
        ``json.dumps`` writes a bare ``NaN`` token, ``JSON.parse`` rejects it,
        and the whole figure -- volume bars and moving averages included --
        loses its accessibility. The SVG still holds a body path and two wick
        paths for the gap row, which is why `_get_selector` keeps counting
        ``len(df)``.
        """
        try:
            columns = [df[name].to_numpy() for name in ("Open", "High", "Low", "Close")]
        except KeyError:
            return []
        volumes = df["Volume"].to_numpy() if "Volume" in df.columns else None
        # Raw representation of the index, exactly as ``str(df.index[i])``.
        dates = [str(date) for date in df.index]

        candles = []
        for i, date_value in enumerate(dates):
            try:
                open_price, high_price, low_price, close_price = (
                    float(column[i]) for column in columns
                )
                # Volume when available, otherwise 0
                volume = float(volumes[i]) if volumes is not None else 0.0
            except (ValueError, TypeError):
                continue

            if not all(
                math.isfinite(price)
                for price in (open_price, high_price, low_price, close_price)
            ):
                continue
            if not math.isfinite(volume):
                volume = 0.0

            candles.append(
                {
                    "value": date_value,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": volume,
                }
            )

        return candles

    def _extract_axes_data(self) -> dict:
        """
        Extract the plot's axes data as canonical per-axis ``AxisConfig``
        objects.

        Returns
        -------
        dict
            ``{"x": {"label": ...}, "y": {"label": ...}}``.
        """
        x_label = self.ax.get_xlabel()
        if not x_label:
            x_label = self.extract_shared_xlabel(self.ax)
        if not x_label:
            x_label = "X"
        y_label = self.ax.get_ylabel()
        if not y_label:
            y_label = self.extract_shared_ylabel(self.ax)
        if not y_label:
            y_label = "Y"

        return {
            MaidrKey.X: self._axis_config(label=x_label),
            MaidrKey.Y: self._axis_config(label=y_label),
        }

    def _get_selector(self) -> Union[str, Dict[str, str]]:
        """Return selectors for highlighting candlestick elements."""
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

        # Legacy path
        legacy_selectors = {}
        if self._maidr_body_gid or self._maidr_gid:
            body_gid = self._maidr_body_gid or self._maidr_gid
            legacy_selectors["body"] = f"g[id='{body_gid}'] > path"
        if self._maidr_wick_gid:
            legacy_selectors["wick"] = f"g[id='{self._maidr_wick_gid}'] > path"
        if legacy_selectors:
            return legacy_selectors

        # Fallback
        return "g[maidr='true'] > path, g[maidr='true'] > rect"

    def render(self) -> dict:
        """
        Initialize the MAIDR schema dictionary with basic plot information.

        Preserves the per-axis ``format`` fields already populated by the base
        ``render()`` — format is nested inside each ``AxisConfig``, not a
        sibling of ``x``/``y``.
        """
        base_schema = super().render()
        # The caller's own title wins. This used to overwrite it, so a chart
        # named with ``ax.set_title()`` announced "Candlestick Chart" instead --
        # and since #453 that fixed string became its accessible name too, so
        # every candlestick chart on a page was announced identically and a reader
        # tabbing between them could not tell which they had reached (#464).
        #
        # The label stays as the fallback, because it says what the chart *is*
        # to a reader who was given no name for it, which is better than the
        # empty string the base render leaves for an untitled layer.
        base_schema[MaidrKey.TITLE] = (
            str(base_schema.get(MaidrKey.TITLE, "") or "").strip()
            or "Candlestick Chart"
        )

        # Preserve per-axis format (nested inside each AxisConfig) while
        # refreshing labels through _extract_axes_data().
        previous_axes = base_schema.get(MaidrKey.AXES, {}) or {}
        axes_data = self._extract_axes_data()
        for axis_key, axis_cfg in list(axes_data.items()):
            prev = previous_axes.get(axis_key)
            if isinstance(prev, dict) and MaidrKey.FORMAT in prev:
                axis_cfg[MaidrKey.FORMAT] = prev[MaidrKey.FORMAT]
        base_schema[MaidrKey.AXES] = axes_data

        # Data and selector are left as `super().render()` built them. Running
        # the extraction a second time here appended a second set of artists
        # to `self._elements` within one render, which the frontend then
        # indexes into by point index (#354). Only the axes needed refreshing.
        return base_schema
