import pandas as pd
import numpy as np
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

class DatetimeConverter:
    """
    Enhanced datetime converter that automatically detects time periods
    and provides intelligent date/time formatting for mplfinance plots.

    This utility automatically detects the time period of financial data and formats
    datetime values consistently for screen reader accessibility and visual clarity.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame with DatetimeIndex containing financial data.
    datetime_format : str, optional
        Custom datetime format string. If None, automatic format detection is used.

    Attributes
    ----------
    data : pd.DataFrame
        The input DataFrame with DatetimeIndex.
    datetime_format : str or None
        Custom datetime format string if provided.
    date_mapping : Dict[int, datetime]
        Mapping from integer index to datetime objects.
    time_period : str
        Detected time period ('minute', 'intraday', 'hour', 'day', 'week', 'month').

    Raises
    ------
    ValueError
        If the input data does not have a DatetimeIndex.

    Examples
    --------
    >>> import pandas as pd
    >>> from maidr.util.datetime_conversion import create_datetime_converter
    >>>
    >>> # Create sample data with DatetimeIndex
    >>> dates = pd.date_range('2024-01-15', periods=5, freq='D')
    >>> df = pd.DataFrame({'Open': [3050, 3078, 3080, 3075, 3087]}, index=dates)
    >>>
    >>> # Create converter
    >>> converter = create_datetime_converter(df)
    >>>
    >>> # Get formatted datetime
    >>> formatted = converter.get_formatted_datetime(0)
    >>> print(formatted)  # Output: "Jan 15 2024"
    >>>
    >>> # For time-based data
    >>> hourly_dates = pd.date_range('2024-01-15 09:00:00', periods=3, freq='H')
    >>> df_hourly = pd.DataFrame({'Open': [3050, 3078, 3080]}, index=hourly_dates)
    >>> converter_hourly = create_datetime_converter(df_hourly)
    >>> formatted_hourly = converter_hourly.get_formatted_datetime(0)
    >>> print(formatted_hourly)  # Output: "Jan 15 2024 09:00"
    """

    def __init__(self, data: pd.DataFrame, datetime_format: Optional[str] = None) -> None:
        """
        Initialize the DatetimeConverter.

        Parameters
        ----------
        data : pd.DataFrame
            DataFrame with DatetimeIndex containing financial data.
        datetime_format : str, optional
            Custom datetime format string. If None, automatic format detection is used.

        Raises
        ------
        ValueError
            If the input data does not have a DatetimeIndex.

        Notes
        -----
        The converter automatically detects the time period of the data based on
        average time differences between consecutive data points.
        """
        self.data = data
        self.datetime_format = datetime_format

        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("Data must have a DatetimeIndex")

        self.date_mapping = self._create_date_mapping()
        self.time_period = self._detect_time_period()

    def _create_date_mapping(self) -> Dict[int, datetime]:
        """
        Create mapping from integer index to datetime objects.

        Returns
        -------
        Dict[int, datetime]
            Dictionary mapping integer indices to corresponding datetime objects
            from the DataFrame index.
        """
        return {i: date for i, date in enumerate(self.data.index)}

    def _detect_time_period(self) -> str:
        """
        Detect the time period of the data based on average time differences.

        Returns
        -------
        str
            Detected time period: 'minute', 'intraday', 'hour', 'day', 'week', 'month', or 'unknown'.

        Notes
        -----
        Time period detection is based on average time differences between consecutive
        data points in the DatetimeIndex.
        """
        if len(self.data) < 2:
            return "unknown"

        # Calculate average time difference between consecutive data points
        time_diffs = []
        for i in range(1, len(self.data)):
            diff = self.data.index[i] - self.data.index[i-1]
            time_diffs.append(diff.total_seconds())

        avg_diff_seconds = np.mean(time_diffs)

        # Determine time period based on average difference
        if avg_diff_seconds < 60:  # Less than 1 minute
            return "minute"
        elif avg_diff_seconds < 3600:  # Less than 1 hour
            return "intraday"
        elif avg_diff_seconds < 86400:  # Less than 1 day
            return "hour"
        elif avg_diff_seconds < 604800:  # Less than 1 week
            return "day"
        elif avg_diff_seconds < 2592000:  # Less than 1 month
            return "week"
        else:
            return "month"

    def get_time_period_description(self) -> str:
        """
        Get human-readable description of detected time period.

        Returns
        -------
        str
            Human-readable description of the detected time period.
        """
        period_descriptions = {
            "minute": "Sub-minute data",
            "intraday": "Intraday (minute-level) data",
            "hour": "Hourly data",
            "day": "Daily data",
            "week": "Weekly data",
            "month": "Monthly data",
            "unknown": "Unknown time period"
        }
        return period_descriptions.get(self.time_period, "Unknown time period")

    def get_formatted_datetime(self, index: int) -> Optional[str]:
        """
        Get formatted datetime string for given index using consistent formatting.

        Always includes year for screen reader accessibility.

        Parameters
        ----------
        index : int
            Integer index into the DataFrame.

        Returns
        -------
        str or None
            Formatted datetime string or None if index is invalid.

        Examples
        --------
        >>> converter = create_datetime_converter(df)
        >>> formatted = converter.get_formatted_datetime(0)
        >>> print(formatted)  # "Jan 15 2024" for daily data
        """
        if index not in self.date_mapping:
            return None

        dt = self.date_mapping[index]
        return self._format_datetime_custom(dt)

    def _format_datetime_custom(self, dt: datetime) -> str:
        """
        Consistent datetime formatting with year always included.

        Parameters
        ----------
        dt : datetime
            Datetime object to format.

        Returns
        -------
        str
            Formatted datetime string with consistent pattern.

        Notes
        -----
        Formatting rules:
        - Daily data: "Jan 15 2024"
        - Time-based data: "Jan 15 2024 09:00" or "Jan 15 2024 09:00:30"
        - Seconds are only shown when they are non-zero for cleaner display.
        """
        if self.time_period in ["minute", "intraday", "hour"]:
            # Time-based data: include time with optional seconds
            if dt.second == 0:
                return dt.strftime("%b %d %Y %H:%M")
            else:
                return dt.strftime("%b %d %Y %H:%M:%S")
        else:
            # Daily/weekly/monthly data: just date
            return dt.strftime("%b %d %Y")

    @property
    def date_nums(self) -> List[float]:
        """
        Convert DatetimeIndex to matplotlib date numbers for backward compatibility.

        Returns
        -------
        List[float]
            List of matplotlib date numbers converted from the DatetimeIndex.
            Empty list if conversion fails.

        Notes
        -----
        This property provides backward compatibility with existing matplotlib
        plotting code that expects date numbers instead of datetime objects.
        """
        try:
            import matplotlib.dates as mdates
            date_nums = []
            for d in self.data.index:
                try:
                    date_num = mdates.date2num(d)
                    date_nums.append(float(date_num))
                except (ValueError, TypeError):
                    continue
            return date_nums
        except Exception:
            return []

    def extract_candlestick_data(self, ax, wick_collection=None, body_collection=None) -> List[Dict[str, Any]]:
        """
        Extract candlestick data with proper datetime formatting using original DataFrame.

        Parameters
        ----------
        ax : matplotlib.axes.Axes
            Matplotlib axes object (not used in current implementation).
        wick_collection : matplotlib.collections.LineCollection, optional
            Collection containing wick lines for candlestick plots.
        body_collection : matplotlib.collections.PolyCollection, optional
            Collection containing body rectangles for candlestick plots.

        Returns
        -------
        List[Dict[str, Any]]
            List of dictionaries containing candlestick data with keys:
            'value', 'open', 'high', 'low', 'close', 'volume'.
            Each 'value' contains formatted datetime string.

        Notes
        -----
        This method extracts OHLC data from the original DataFrame and formats
        datetime values using the enhanced datetime conversion logic.
        """
        candles = []
        if not hasattr(self.data, 'Open') or not hasattr(self.data, 'High') or not hasattr(self.data, 'Low') or not hasattr(self.data, 'Close'):
            return candles

        for i in range(len(self.data)):
            try:
                open_price = self.data.iloc[i]['Open']
                high_price = self.data.iloc[i]['High']
                low_price = self.data.iloc[i]['Low']
                close_price = self.data.iloc[i]['Close']
                volume = self.data.iloc[i].get('Volume', 0.0)

                formatted_datetime = self.get_formatted_datetime(i)

                candle_data = {
                    'value': formatted_datetime or f"datetime_{i:03d}",
                    'open': float(open_price),
                    'high': float(high_price),
                    'low': float(low_price),
                    'close': float(close_price),
                    'volume': float(volume)
                }
                candles.append(candle_data)
            except (KeyError, IndexError, ValueError):
                continue
        return candles

    def extract_moving_average_data(self, ax, line_index: int = 0) -> List[Tuple[str, float]]:
        """
        Extract moving average data with proper datetime formatting and NaN filtering.

        Parameters
        ----------
        ax : matplotlib.axes.Axes
            Matplotlib axes object containing the moving average lines.
        line_index : int, default=0
            Index of the line to extract data from.

        Returns
        -------
        List[Tuple[str, float]]
            List of tuples containing (formatted_datetime, y_value) pairs.
            NaN and infinite values are filtered out.

        Notes
        -----
        This method filters out invalid data points and formats datetime values
        using the enhanced datetime conversion logic.
        """
        ma_data = []
        lines = ax.get_lines() if ax else []
        if line_index >= len(lines):
            return ma_data
        line = lines[line_index]
        xydata = line.get_xydata()
        if xydata is None or len(xydata) == 0:
            return ma_data

        for i, (x, y) in enumerate(xydata):
            if np.isnan(y) or np.isinf(y):
                continue
            try:
                df_index = int(round(x))
                if 0 <= df_index < len(self.data):
                    formatted_datetime = self.get_formatted_datetime(df_index)
                    if formatted_datetime:
                        ma_data.append((formatted_datetime, float(y)))
            except (ValueError, TypeError):
                continue
        return ma_data

    def extract_volume_data(self, ax) -> List[Tuple[str, float]]:
        """
        Extract volume data with proper datetime formatting using original DataFrame.

        Parameters
        ----------
        ax : matplotlib.axes.Axes
            Matplotlib axes object (not used in current implementation).

        Returns
        -------
        List[Tuple[str, float]]
            List of tuples containing (formatted_datetime, volume) pairs.
            Zero and NaN volume values are filtered out.

        Notes
        -----
        This method extracts volume data from the original DataFrame and formats
        datetime values using the enhanced datetime conversion logic.
        """
        volume_data = []
        if hasattr(self.data, 'Volume'):
            for i in range(len(self.data)):
                try:
                    volume = self.data.iloc[i]['Volume']
                    if pd.isna(volume) or volume <= 0:
                        continue
                    formatted_datetime = self.get_formatted_datetime(i)
                    volume_data.append((formatted_datetime, float(volume)))
                except (KeyError, IndexError, ValueError):
                    continue
        return volume_data


def create_datetime_converter(data: pd.DataFrame, datetime_format: Optional[str] = None) -> DatetimeConverter:
    """
    Factory function to create a DatetimeConverter instance.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame with DatetimeIndex containing financial data.
    datetime_format : str, optional
        Custom datetime format string. If None, automatic format detection is used.

    Returns
    -------
    DatetimeConverter
        Configured DatetimeConverter instance for the given data.

    Examples
    --------
    >>> import pandas as pd
    >>> from maidr.util.datetime_conversion import create_datetime_converter
    >>>
    >>> dates = pd.date_range('2024-01-15', periods=5, freq='D')
    >>> df = pd.DataFrame({'Open': [3050, 3078, 3080, 3075, 3087]}, index=dates)
    >>> converter = create_datetime_converter(df)
    >>> print(type(converter))  # <class 'maidr.util.datetime_conversion.DatetimeConverter'>
    """
    return DatetimeConverter(data, datetime_format)
