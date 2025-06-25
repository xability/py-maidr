"""
Utility functions for handling mplfinance-specific data extraction and processing.
"""

import matplotlib.dates as mdates
import numpy as np
from matplotlib.patches import Rectangle
from typing import List, Optional, Tuple, Any


class MplfinanceDataExtractor:
    """
    Utility class for extracting and processing mplfinance-specific data.

    This class handles the conversion of mplfinance plot elements (patches, collections)
    into standardized data formats that can be used by the core plot classes.
    """

    @staticmethod
    def extract_volume_data(
        volume_patches: List[Rectangle], date_nums: Optional[List[float]] = None
    ) -> List[dict]:
        """
        Extract volume data from mplfinance Rectangle patches.

        Parameters
        ----------
        volume_patches : List[Rectangle]
            List of Rectangle patches representing volume bars
        date_nums : Optional[List[float]], default=None
            List of matplotlib date numbers corresponding to the patches

        Returns
        -------
        List[dict]
            List of dictionaries with 'x' and 'y' keys for volume data
        """
        if not volume_patches:
            return []

        formatted_data = []

        # Sort patches by x-coordinate to maintain order
        sorted_patches = sorted(volume_patches, key=lambda p: p.get_x())

        for i, patch in enumerate(sorted_patches):
            height = patch.get_height()

            # Use date mapping if available, otherwise use index
            if date_nums is not None and i < len(date_nums):
                date_num = date_nums[i]
                x_label = MplfinanceDataExtractor._convert_date_num_to_string(date_num)
            else:
                x_label = f"date_{i:03d}"

            formatted_data.append({"x": str(x_label), "y": float(height)})

        return formatted_data

    @staticmethod
    def extract_candlestick_data(
        body_collection: Any,
        wick_collection: Any,
        date_nums: Optional[List[float]] = None,
    ) -> List[dict]:
        """
        Extract candlestick data from mplfinance collections.

        Parameters
        ----------
        body_collection : Any
            PolyCollection containing candlestick bodies
        wick_collection : Any
            LineCollection containing candlestick wicks
        date_nums : Optional[List[float]], default=None
            List of matplotlib date numbers corresponding to the candles

        Returns
        -------
        List[dict]
            List of dictionaries with OHLC data
        """
        if not body_collection or not hasattr(body_collection, "get_paths"):
            return []

        candles = []
        paths = body_collection.get_paths()
        face_colors = body_collection.get_facecolor()

        for i, path in enumerate(paths):
            if len(path.vertices) >= 4:
                # Extract rectangle coordinates from the path
                vertices = path.vertices
                x_coords = vertices[:, 0]
                y_coords = vertices[:, 1]

                x_min, x_max = x_coords.min(), x_coords.max()
                y_min, y_max = y_coords.min(), y_coords.max()

                # Use date mapping if available
                if date_nums is not None and i < len(date_nums):
                    date_num = date_nums[i]
                    date_str = MplfinanceDataExtractor._convert_date_num_to_string(
                        date_num
                    )
                else:
                    x_center = (x_min + x_max) / 2
                    date_str = MplfinanceDataExtractor._convert_date_num_to_string(
                        x_center
                    )

                # Determine if this is an up or down candle based on color
                is_up = MplfinanceDataExtractor._is_up_candle(face_colors, i)

                # Extract OHLC values
                (
                    open_val,
                    close_val,
                ) = MplfinanceDataExtractor._extract_ohlc_from_rectangle(
                    y_min, y_max, is_up
                )

                # Estimate high and low (these would normally come from wick data)
                high_val = y_max + (y_max - y_min) * 0.1
                low_val = y_min - (y_max - y_min) * 0.1

                candle_data = {
                    "value": date_str,
                    "open": round(open_val, 2),
                    "high": round(high_val, 2),
                    "low": round(low_val, 2),
                    "close": round(close_val, 2),
                    "volume": 0,  # Volume is handled separately
                }
                candles.append(candle_data)

        return candles

    @staticmethod
    def extract_rectangle_candlestick_data(
        body_rectangles: List[Rectangle], date_nums: Optional[List[float]] = None
    ) -> List[dict]:
        """
        Extract candlestick data from Rectangle patches (original_flavor).

        Parameters
        ----------
        body_rectangles : List[Rectangle]
            List of Rectangle patches representing candlestick bodies
        date_nums : Optional[List[float]], default=None
            List of matplotlib date numbers corresponding to the candles

        Returns
        -------
        List[dict]
            List of dictionaries with OHLC data
        """
        if not body_rectangles:
            return []

        candles = []

        # Sort rectangles by x-coordinate
        body_rectangles.sort(key=lambda r: r.get_x())

        for i, rect in enumerate(body_rectangles):
            x_left = rect.get_x()
            width = rect.get_width()
            x_center_num = x_left + width / 2.0

            # Convert x coordinate to date
            if date_nums is not None and i < len(date_nums):
                date_str = MplfinanceDataExtractor._convert_date_num_to_string(
                    date_nums[i]
                )
            else:
                date_str = MplfinanceDataExtractor._convert_date_num_to_string(
                    x_center_num
                )

            y_bottom = rect.get_y()
            height = rect.get_height()
            face_color = rect.get_facecolor()

            # Determine if this is an up or down candle based on color
            is_up_candle = MplfinanceDataExtractor._is_up_candle_from_color(face_color)

            # Extract OHLC values from rectangle
            (
                open_price,
                close_price,
            ) = MplfinanceDataExtractor._extract_ohlc_from_rectangle(
                y_bottom, y_bottom + height, is_up_candle
            )

            # Estimate high and low
            high_price = max(open_price, close_price) + height * 0.1
            low_price = min(open_price, close_price) - height * 0.1

            # Ensure all values are valid numbers
            open_price = float(open_price) if not np.isnan(open_price) else 0.0
            high_price = float(high_price) if not np.isnan(high_price) else 0.0
            low_price = float(low_price) if not np.isnan(low_price) else 0.0
            close_price = float(close_price) if not np.isnan(close_price) else 0.0

            candle_data = {
                "value": date_str,
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "close": round(close_price, 2),
                "volume": 0,
            }
            candles.append(candle_data)

        return candles

    @staticmethod
    def clean_axis_label(label: str) -> str:
        """
        Clean up axis labels by removing LaTeX formatting.

        Parameters
        ----------
        label : str
            The original axis label

        Returns
        -------
        str
            Cleaned axis label
        """
        if not label or not isinstance(label, str):
            return label

        import re

        # Removes LaTeX-like scientific notation, e.g., "$10^{6}$"
        cleaned_label = re.sub(r"\s*\$.*?\$", "", label).strip()
        return cleaned_label if cleaned_label else label

    @staticmethod
    def _convert_date_num_to_string(date_num: float) -> str:
        """
        Convert matplotlib date number to date string.

        Parameters
        ----------
        date_num : float
            Matplotlib date number

        Returns
        -------
        str
            Date string in YYYY-MM-DD format or fallback index
        """
        try:
            # Check if this looks like a matplotlib date number (typically > 700000)
            if date_num > 700000:
                date_dt = mdates.num2date(date_num)
                if hasattr(date_dt, "replace"):
                    date_dt = date_dt.replace(tzinfo=None)
                return date_dt.strftime("%Y-%m-%d")
            elif date_num > 1000:
                # Try converting as if it's a pandas timestamp
                try:
                    import pandas as pd

                    date_dt = pd.to_datetime(date_num, unit="D")
                    return date_dt.strftime("%Y-%m-%d")
                except:
                    pass
        except (ValueError, TypeError, OverflowError):
            pass

        # Fallback to index-based date string
        return f"date_{int(date_num):03d}"

    @staticmethod
    def convert_x_to_date(x_center_num: float, axes: Optional[List] = None) -> str:
        """
        Convert matplotlib x-coordinate to date string.

        Parameters
        ----------
        x_center_num : float
            X-coordinate value to convert
        axes : Optional[List], optional
            List of matplotlib axes to help with date conversion

        Returns
        -------
        str
            Date string in YYYY-MM-DD format or fallback
        """
        # First, try to get the actual dates from the axes x-axis data
        if axes and len(axes) > 0:
            ax = axes[0]
            try:
                # Get x-axis ticks which might contain the actual dates
                x_ticks = ax.get_xticks()

                # If we have x-axis ticks and they look like dates (large numbers), use them
                if len(x_ticks) > 0 and x_ticks[0] > 1000:
                    # Find the closest tick to our x_center_num
                    tick_index = int(round(x_center_num))
                    if 0 <= tick_index < len(x_ticks):
                        actual_date_num = x_ticks[tick_index]

                        # Convert the actual date number
                        if actual_date_num > 700000:
                            date_dt = mdates.num2date(actual_date_num)
                            if hasattr(date_dt, "replace"):
                                date_dt = date_dt.replace(tzinfo=None)
                            date_str = date_dt.strftime("%Y-%m-%d")
                            return date_str
            except Exception:
                pass

        # Use the utility class for date conversion
        return MplfinanceDataExtractor._convert_date_num_to_string(x_center_num)

    @staticmethod
    def _is_up_candle(face_colors: Any, index: int) -> bool:
        """
        Determine if a candle is up based on face color.

        Parameters
        ----------
        face_colors : Any
            Face colors from the collection
        index : int
            Index of the candle

        Returns
        -------
        bool
            True if up candle, False if down candle
        """
        is_up = True  # Default to up candle
        if hasattr(face_colors, "__len__") and len(face_colors) > index:
            color = (
                face_colors[index]
                if hasattr(face_colors[index], "__len__")
                else face_colors
            )
            if isinstance(color, (list, tuple, np.ndarray)):
                if len(color) >= 3:
                    # Dark colors typically indicate down candles
                    if color[0] < 0.5 and color[1] < 0.5 and color[2] < 0.5:
                        is_up = False
        return is_up

    @staticmethod
    def _is_up_candle_from_color(face_color: Any) -> bool:
        """
        Determine if a candle is up based on face color (for Rectangle patches).

        Parameters
        ----------
        face_color : Any
            Face color of the rectangle

        Returns
        -------
        bool
            True if up candle, False if down candle
        """
        try:
            if (
                isinstance(face_color, (list, tuple, np.ndarray))
                and len(face_color) >= 3
            ):
                # Green colors typically indicate up candles
                if face_color[1] > face_color[0]:
                    return True
                else:
                    return False
        except (TypeError, IndexError):
            pass
        return True  # Default to up candle

    @staticmethod
    def _extract_ohlc_from_rectangle(
        y_min: float, y_max: float, is_up: bool
    ) -> Tuple[float, float]:
        """
        Extract open and close values from rectangle bounds.

        Parameters
        ----------
        y_min : float
            Minimum y value of rectangle
        y_max : float
            Maximum y value of rectangle
        is_up : bool
            Whether this is an up candle

        Returns
        -------
        Tuple[float, float]
            (open_price, close_price)
        """
        if is_up:
            # Up candle: open at bottom, close at top
            return y_min, y_max
        else:
            # Down candle: open at top, close at bottom
            return y_max, y_min
