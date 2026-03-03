"""
Format configuration utilities for extracting and representing axis formatting.

This module provides classes and utilities for detecting matplotlib axis formatters
and converting them to MAIDR-compatible format configurations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from matplotlib.axes import Axes
from matplotlib.dates import DateFormatter
from matplotlib.ticker import (
    Formatter,
    FuncFormatter,
    PercentFormatter,
    ScalarFormatter,
    StrMethodFormatter,
    FormatStrFormatter,
)


class FormatType(str, Enum):
    """
    Enumeration of supported format types for MAIDR.

    These types correspond to the formatting options supported by
    the MAIDR JavaScript library's FormatterService.
    """

    CURRENCY = "currency"
    PERCENT = "percent"
    DATE = "date"
    NUMBER = "number"
    SCIENTIFIC = "scientific"
    FIXED = "fixed"


@dataclass
class FormatConfig:
    """
    Configuration for axis value formatting.

    This class represents a format configuration that can be serialized
    to the MAIDR schema format. It supports both type-based formatting
    and custom JavaScript function bodies.

    Parameters
    ----------
    type : FormatType, optional
        The type of formatting to apply.
    function : str, optional
        JavaScript function body for custom formatting.
        This is evaluated by MAIDR JS using: new Function('value', functionBody)
        Example: "return parseFloat(value).toFixed(2)"
    decimals : int, optional
        Number of decimal places to display.
    currency : str, optional
        Currency code (e.g., "USD", "EUR") for currency formatting.
    locale : str, optional
        BCP 47 locale string (e.g., "en-US") for locale-specific formatting.
    dateFormat : str, optional
        Date format string (e.g., "%b %d" for "Jan 15") for date formatting.

    Examples
    --------
    >>> config = FormatConfig(type=FormatType.CURRENCY, decimals=2, currency="USD")
    >>> config.to_dict()
    {'type': 'currency', 'decimals': 2, 'currency': 'USD'}

    >>> config = FormatConfig(function="return '$' + parseFloat(value).toFixed(2)")
    >>> config.to_dict()
    {'function': "return '$' + parseFloat(value).toFixed(2)"}
    """

    type: Optional[FormatType] = None
    function: Optional[str] = None
    decimals: Optional[int] = None
    currency: Optional[str] = None
    locale: Optional[str] = None
    dateFormat: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the format configuration to a dictionary.

        Returns
        -------
        Dict[str, Any]
            Dictionary representation suitable for MAIDR schema.
            Only includes non-None values. If function is provided,
            it takes precedence over type-based formatting.
        """
        result: Dict[str, Any] = {}

        # Function takes precedence - if provided, use it directly
        if self.function is not None:
            result["function"] = self.function
            return result

        # Otherwise use type-based formatting
        if self.type is not None:
            result["type"] = self.type.value

        if self.decimals is not None:
            result["decimals"] = self.decimals
        if self.currency is not None:
            result["currency"] = self.currency
        if self.locale is not None:
            result["locale"] = self.locale
        if self.dateFormat is not None:
            result["dateFormat"] = self.dateFormat

        return result


class JSBodyConverter:
    """
    Converter for generating JavaScript function bodies from matplotlib formatters.

    These function bodies are evaluated by MAIDR JS using:
    new Function('value', functionBody)
    """

    # Mapping of Python strftime codes to JavaScript date formatting
    # Common patterns with optimized JS bodies
    STRFTIME_PATTERNS: Dict[str, str] = {
        "%b %d": (
            "var m=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];"
            "var d=new Date(value);return m[d.getMonth()]+' '+d.getDate()"
        ),
        "%b %d, %Y": (
            "var m=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];"
            "var d=new Date(value);return m[d.getMonth()]+' '+d.getDate()+', '+d.getFullYear()"
        ),
        "%Y-%m-%d": (
            "var d=new Date(value);"
            "return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'"
            "+String(d.getDate()).padStart(2,'0')"
        ),
        "%m/%d/%Y": (
            "var d=new Date(value);"
            "return String(d.getMonth()+1).padStart(2,'0')+'/'"
            "+String(d.getDate()).padStart(2,'0')+'/'+d.getFullYear()"
        ),
        "%d/%m/%Y": (
            "var d=new Date(value);"
            "return String(d.getDate()).padStart(2,'0')+'/'"
            "+String(d.getMonth()+1).padStart(2,'0')+'/'+d.getFullYear()"
        ),
        "%Y": "return new Date(value).getFullYear().toString()",
        "%B %Y": (
            "var m=['January','February','March','April','May','June',"
            "'July','August','September','October','November','December'];"
            "var d=new Date(value);return m[d.getMonth()]+' '+d.getFullYear()"
        ),
        "%H:%M": (
            "var d=new Date(value);"
            "return String(d.getHours()).padStart(2,'0')+':'"
            "+String(d.getMinutes()).padStart(2,'0')"
        ),
        "%H:%M:%S": (
            "var d=new Date(value);"
            "return String(d.getHours()).padStart(2,'0')+':'"
            "+String(d.getMinutes()).padStart(2,'0')+':'"
            "+String(d.getSeconds()).padStart(2,'0')"
        ),
        "%I:%M %p": (
            "var d=new Date(value);"
            "var h=d.getHours();var ampm=h>=12?'PM':'AM';h=h%12;h=h?h:12;"
            "return String(h).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')+' '+ampm"
        ),
    }

    @staticmethod
    def date_format_to_js(fmt: str) -> str:
        """
        Convert Python strftime format to JavaScript function body.

        Parameters
        ----------
        fmt : str
            Python strftime format string (e.g., '%b %d', '%Y-%m-%d')

        Returns
        -------
        str
            JavaScript function body that formats dates similarly.
        """
        if fmt in JSBodyConverter.STRFTIME_PATTERNS:
            return JSBodyConverter.STRFTIME_PATTERNS[fmt]

        # Fallback: use toLocaleString for unrecognized formats
        return "return new Date(value).toLocaleDateString()"

    @staticmethod
    def currency_format_to_js(symbol: str, decimals: int = 2) -> str:
        """
        Convert currency format to JavaScript function body.

        Parameters
        ----------
        symbol : str
            Currency symbol ($, €, £, ¥)
        decimals : int
            Number of decimal places

        Returns
        -------
        str
            JavaScript function body for currency formatting.
        """
        # Map symbols to locales
        locale_map = {
            "$": "en-US",
            "€": "de-DE",
            "£": "en-GB",
            "¥": "ja-JP",
        }
        locale = locale_map.get(symbol, "en-US")

        # Yen typically has no decimals
        if symbol == "¥":
            decimals = 0

        return (
            f"return '{symbol}'+parseFloat(value).toLocaleString('{locale}',"
            f"{{minimumFractionDigits:{decimals},maximumFractionDigits:{decimals}}})"
        )

    @staticmethod
    def number_format_to_js(decimals: Optional[int] = None) -> str:
        """
        Convert number format (with thousands separator) to JavaScript function body.

        Parameters
        ----------
        decimals : int, optional
            Number of decimal places

        Returns
        -------
        str
            JavaScript function body for number formatting.
        """
        if decimals is not None:
            return (
                f"return parseFloat(value).toLocaleString('en-US',"
                f"{{minimumFractionDigits:{decimals},maximumFractionDigits:{decimals}}})"
            )
        return "return parseFloat(value).toLocaleString('en-US')"

    @staticmethod
    def fixed_format_to_js(decimals: int) -> str:
        """
        Convert fixed decimal format to JavaScript function body.

        Parameters
        ----------
        decimals : int
            Number of decimal places

        Returns
        -------
        str
            JavaScript function body for fixed decimal formatting.
        """
        return f"return parseFloat(value).toFixed({decimals})"

    @staticmethod
    def percent_format_to_js(decimals: int = 1, multiply: bool = True) -> str:
        """
        Convert percent format to JavaScript function body.

        Parameters
        ----------
        decimals : int
            Number of decimal places
        multiply : bool
            Whether to multiply by 100 (for values stored as decimals)

        Returns
        -------
        str
            JavaScript function body for percent formatting.
        """
        if multiply:
            return f"return (parseFloat(value)*100).toFixed({decimals})+'%'"
        return f"return parseFloat(value).toFixed({decimals})+'%'"

    @staticmethod
    def scientific_format_to_js(decimals: int = 2) -> str:
        """
        Convert scientific notation format to JavaScript function body.

        Parameters
        ----------
        decimals : int
            Number of decimal places in mantissa

        Returns
        -------
        str
            JavaScript function body for scientific notation formatting.
        """
        return f"return parseFloat(value).toExponential({decimals})"

    @staticmethod
    def default_format_to_js() -> str:
        """
        Return default JavaScript function body for unsupported formatters.

        Returns
        -------
        str
            JavaScript function body that returns value as string.
        """
        return "return String(value)"


class FormatConfigBuilder:
    """
    Builder for extracting format configurations from matplotlib formatters.

    This class provides static methods to detect and parse matplotlib axis
    formatters and convert them to FormatConfig objects with JavaScript
    function bodies for MAIDR JS evaluation.

    Examples
    --------
    >>> from matplotlib import pyplot as plt
    >>> fig, ax = plt.subplots()
    >>> ax.yaxis.set_major_formatter('${x:,.2f}')
    >>> config = FormatConfigBuilder.from_formatter(ax.yaxis.get_major_formatter())
    >>> config.function
    "return '$'+parseFloat(value).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})"
    """

    # Currency symbol patterns for detection
    CURRENCY_PATTERNS = {
        "$": "USD",
        "USD": "USD",
        "€": "EUR",
        "EUR": "EUR",
        "£": "GBP",
        "GBP": "GBP",
        "¥": "JPY",
        "JPY": "JPY",
    }

    @staticmethod
    def from_formatter(formatter: Optional[Formatter]) -> Optional[FormatConfig]:
        """
        Create a FormatConfig from a matplotlib Formatter.

        Parameters
        ----------
        formatter : Formatter or None
            A matplotlib ticker Formatter object, or None.

        Returns
        -------
        FormatConfig or None
            The detected format configuration, or None if the formatter
            type could not be determined.
        """
        if formatter is None:
            return None

        # Check for DateFormatter (for date/time axes)
        if isinstance(formatter, DateFormatter):
            return FormatConfigBuilder._parse_date_formatter(formatter)

        # Check for PercentFormatter
        if isinstance(formatter, PercentFormatter):
            return FormatConfigBuilder._parse_percent_formatter(formatter)

        # Check for StrMethodFormatter (most common for custom formats)
        if isinstance(formatter, StrMethodFormatter):
            return FormatConfigBuilder._parse_str_method_formatter(formatter)

        # Check for FormatStrFormatter (old-style % formatting)
        if isinstance(formatter, FormatStrFormatter):
            return FormatConfigBuilder._parse_format_str_formatter(formatter)

        # Check for ScalarFormatter with scientific notation
        if isinstance(formatter, ScalarFormatter):
            return FormatConfigBuilder._parse_scalar_formatter(formatter)

        # Check for FuncFormatter (custom function)
        if isinstance(formatter, FuncFormatter):
            return FormatConfigBuilder._parse_func_formatter(formatter)

        return None

    @staticmethod
    def _parse_date_formatter(formatter: DateFormatter) -> FormatConfig:
        """Parse a DateFormatter to FormatConfig with JS function body."""
        date_format = None
        if hasattr(formatter, "fmt") and formatter.fmt is not None:
            date_format = formatter.fmt

        # Generate JS function body for date formatting
        js_body = JSBodyConverter.date_format_to_js(date_format) if date_format else None

        if js_body:
            return FormatConfig(function=js_body)

        # Fallback to type-based config
        return FormatConfig(type=FormatType.DATE, dateFormat=date_format)

    @staticmethod
    def _parse_percent_formatter(formatter: PercentFormatter) -> FormatConfig:
        """Parse a PercentFormatter to FormatConfig using type-based preset."""
        decimals = None
        if hasattr(formatter, "decimals") and formatter.decimals is not None:
            decimals = int(formatter.decimals)

        # Use type-based preset for percent
        return FormatConfig(type=FormatType.PERCENT, decimals=decimals)

    @staticmethod
    def _parse_str_method_formatter(
        formatter: StrMethodFormatter,
    ) -> Optional[FormatConfig]:
        """Parse a StrMethodFormatter to FormatConfig using hybrid approach."""
        fmt = getattr(formatter, "fmt", None)
        if fmt is None:
            return None

        return FormatConfigBuilder._parse_format_string_hybrid(fmt)

    @staticmethod
    def _parse_format_str_formatter(
        formatter: FormatStrFormatter,
    ) -> Optional[FormatConfig]:
        """Parse a FormatStrFormatter (old-style %) to FormatConfig using type-based presets."""
        fmt = getattr(formatter, "fmt", None)
        if fmt is None:
            return None

        # Convert old-style format to type-based config
        # e.g., "%.2f" -> fixed with 2 decimals
        match = re.search(r"%\.?(\d*)([efg])", fmt, re.IGNORECASE)
        if match:
            decimals_str = match.group(1)
            format_char = match.group(2).lower()

            decimals = int(decimals_str) if decimals_str else None

            if format_char == "e":
                return FormatConfig(type=FormatType.SCIENTIFIC, decimals=decimals)
            elif format_char in ("f", "g"):
                return FormatConfig(type=FormatType.FIXED, decimals=decimals)

        return None

    @staticmethod
    def _parse_scalar_formatter(formatter: ScalarFormatter) -> Optional[FormatConfig]:
        """Parse a ScalarFormatter to FormatConfig using type-based preset.

        ScalarFormatter is the default matplotlib formatter and often has _scientific=True
        due to auto-detection. We only return a FormatConfig if useMathText is explicitly
        enabled, as this indicates the user wants formatted scientific notation display.
        """
        # useMathText is only True when explicitly set by user via set_useMathText(True)
        # This provides nice-looking scientific notation like 10^6 instead of 1e6
        use_math_text = getattr(formatter, "_useMathText", False)
        if use_math_text is True:
            return FormatConfig(type=FormatType.SCIENTIFIC)

        # Default ScalarFormatter - no explicit format configured by user
        # We ignore _scientific since matplotlib auto-sets it based on data magnitude
        return None

    @staticmethod
    def _parse_func_formatter(formatter: FuncFormatter) -> Optional[FormatConfig]:
        """
        Attempt to parse a FuncFormatter by examining the function.

        This is a best-effort approach since FuncFormatter can contain
        arbitrary functions. For unsupported functions, returns a default
        formatter that shows the value as-is.
        """
        func = getattr(formatter, "func", None)
        if func is None:
            return None

        # Try to get function source or docstring for hints
        func_name = getattr(func, "__name__", "")

        # Common naming conventions - generate JS function bodies
        if "percent" in func_name.lower():
            js_body = JSBodyConverter.percent_format_to_js(1, multiply=True)
            return FormatConfig(function=js_body)
        elif "currency" in func_name.lower() or "dollar" in func_name.lower():
            js_body = JSBodyConverter.currency_format_to_js("$", 2)
            return FormatConfig(function=js_body)
        elif "date" in func_name.lower() or "time" in func_name.lower():
            js_body = "return new Date(value).toLocaleDateString()"
            return FormatConfig(function=js_body)

        # For unknown FuncFormatters, return default (value as-is)
        # This ensures the value is still displayed
        return FormatConfig(function=JSBodyConverter.default_format_to_js())

    @staticmethod
    def _parse_format_string_hybrid(fmt: str) -> Optional[FormatConfig]:
        """
        Parse a format string using hybrid approach: type-based presets for simple
        formats, JS functions for complex formats.

        Parameters
        ----------
        fmt : str
            A Python format string (e.g., "${x:,.2f}", "{x:.1%}").

        Returns
        -------
        FormatConfig or None
            The detected format configuration using appropriate approach.
        """
        if not fmt:
            return None

        decimals = FormatConfigBuilder._extract_decimals(fmt)

        # Detect currency by symbol prefix - use type-based preset
        for symbol, currency_code in FormatConfigBuilder.CURRENCY_PATTERNS.items():
            if symbol in fmt:
                return FormatConfig(
                    type=FormatType.CURRENCY, decimals=decimals, currency=currency_code
                )

        # Detect percent format (ends with %) like {x:.1%} - use type-based preset
        if "%" in fmt and "{" in fmt:
            if re.search(r"\{[^}]*%\}", fmt):
                return FormatConfig(type=FormatType.PERCENT, decimals=decimals)

        # Detect scientific notation like {x:.2e} - use type-based preset
        if re.search(r"\{[^}]*[eE]\}", fmt):
            return FormatConfig(type=FormatType.SCIENTIFIC, decimals=decimals)

        # Detect number format with comma separators like {x:,.2f} or {x:,}
        # - use type-based preset
        if re.search(r"\{[^}]*,", fmt):
            return FormatConfig(type=FormatType.NUMBER, decimals=decimals)

        # Detect fixed-point format (no comma separator) like {x:.2f}
        # - use type-based preset
        match = re.search(r"\{[^}]*\.(\d+)f\}", fmt)
        if match:
            decimals = int(match.group(1))
            return FormatConfig(type=FormatType.FIXED, decimals=decimals)

        # No recognized format - return None (don't add format config)
        return None

    @staticmethod
    def _parse_format_string(fmt: str) -> Optional[FormatConfig]:
        """
        Parse a format string to detect the format type and options.
        (Legacy method - kept for backwards compatibility)

        Parameters
        ----------
        fmt : str
            A Python format string (e.g., "${x:,.2f}", "{x:.1%}").

        Returns
        -------
        FormatConfig or None
            The detected format configuration.
        """
        if not fmt:
            return None

        # Detect currency by symbol prefix
        for symbol, currency_code in FormatConfigBuilder.CURRENCY_PATTERNS.items():
            if symbol in fmt:
                decimals = FormatConfigBuilder._extract_decimals(fmt)
                return FormatConfig(
                    type=FormatType.CURRENCY, decimals=decimals, currency=currency_code
                )

        # Detect percent format (ends with %)
        if "%" in fmt and "{" in fmt:
            # Check if it's a percent format like {x:.1%}
            if re.search(r"\{[^}]*%\}", fmt):
                decimals = FormatConfigBuilder._extract_decimals(fmt)
                return FormatConfig(type=FormatType.PERCENT, decimals=decimals)

        # Detect scientific notation
        if re.search(r"\{[^}]*[eE]\}", fmt):
            decimals = FormatConfigBuilder._extract_decimals(fmt)
            return FormatConfig(type=FormatType.SCIENTIFIC, decimals=decimals)

        # Detect number format with comma separators (must check before fixed-point)
        # This matches formats like {x:,.2f} or {x:,}
        if re.search(r"\{[^}]*,", fmt):
            decimals = FormatConfigBuilder._extract_decimals(fmt)
            return FormatConfig(type=FormatType.NUMBER, decimals=decimals)

        # Detect fixed-point format (no comma separator)
        match = re.search(r"\{[^}]*\.(\d+)f\}", fmt)
        if match:
            decimals = int(match.group(1))
            return FormatConfig(type=FormatType.FIXED, decimals=decimals)

        return None

    @staticmethod
    def _extract_decimals(fmt: str) -> Optional[int]:
        """
        Extract the number of decimal places from a format string.

        Parameters
        ----------
        fmt : str
            A Python format string.

        Returns
        -------
        int or None
            The number of decimal places, or None if not specified.
        """
        # Match patterns like .2f, .1%, .3e
        match = re.search(r"\.(\d+)[fFeE%]", fmt)
        if match:
            return int(match.group(1))
        return None


def extract_axis_format(ax: Optional[Axes]) -> Dict[str, Dict[str, Any]]:
    """
    Extract format configurations from both axes of a plot.

    Parameters
    ----------
    ax : Axes or None
        The matplotlib Axes object to extract formats from, or None.

    Returns
    -------
    Dict[str, Dict[str, Any]]
        Dictionary with 'x' and/or 'y' keys containing format configurations.
        Only includes axes where a format could be detected.

    Examples
    --------
    >>> from matplotlib import pyplot as plt
    >>> fig, ax = plt.subplots()
    >>> ax.yaxis.set_major_formatter('${x:,.2f}')
    >>> formats = extract_axis_format(ax)
    >>> formats
    {'y': {'type': 'currency', 'decimals': 2, 'currency': 'USD'}}
    """
    if ax is None:
        return {}

    result: Dict[str, Dict[str, Any]] = {}

    # Extract X-axis format
    x_formatter = ax.xaxis.get_major_formatter()
    x_config = FormatConfigBuilder.from_formatter(x_formatter)
    if x_config is not None:
        result["x"] = x_config.to_dict()

    # Extract Y-axis format
    y_formatter = ax.yaxis.get_major_formatter()
    y_config = FormatConfigBuilder.from_formatter(y_formatter)
    if y_config is not None:
        result["y"] = y_config.to_dict()

    return result
