"""
Format configuration utilities for extracting and representing axis formatting.

This module provides classes and utilities for detecting matplotlib axis formatters
and converting them to MAIDR-compatible format configurations.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

import matplotlib.dates as mdates
import numpy as np
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

    # Mapping of Python strftime codes to JavaScript date formatting.
    # Each body continues the prologue from ``_date_prologue`` -- ``d`` is
    # already the ``Date`` -- and reads it through the UTC getters, because a
    # matplotlib date axis is UTC unless the user asked for a timezone: the
    # local getters read a UTC-midnight date as the previous evening anywhere
    # west of UTC.
    STRFTIME_PATTERNS: Dict[str, str] = {
        "%b %d": (
            "var m=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];"
            "return m[d.getUTCMonth()]+' '+d.getUTCDate()"
        ),
        "%b %d, %Y": (
            "var m=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];"
            "return m[d.getUTCMonth()]+' '+d.getUTCDate()+', '+d.getUTCFullYear()"
        ),
        "%Y-%m-%d": (
            "return d.getUTCFullYear()+'-'+String(d.getUTCMonth()+1).padStart(2,'0')+'-'"
            "+String(d.getUTCDate()).padStart(2,'0')"
        ),
        "%m/%d/%Y": (
            "return String(d.getUTCMonth()+1).padStart(2,'0')+'/'"
            "+String(d.getUTCDate()).padStart(2,'0')+'/'+d.getUTCFullYear()"
        ),
        "%d/%m/%Y": (
            "return String(d.getUTCDate()).padStart(2,'0')+'/'"
            "+String(d.getUTCMonth()+1).padStart(2,'0')+'/'+d.getUTCFullYear()"
        ),
        "%Y": "return d.getUTCFullYear().toString()",
        "%B %Y": (
            "var m=['January','February','March','April','May','June',"
            "'July','August','September','October','November','December'];"
            "return m[d.getUTCMonth()]+' '+d.getUTCFullYear()"
        ),
        "%H:%M": (
            "return String(d.getUTCHours()).padStart(2,'0')+':'"
            "+String(d.getUTCMinutes()).padStart(2,'0')"
        ),
        "%H:%M:%S": (
            "return String(d.getUTCHours()).padStart(2,'0')+':'"
            "+String(d.getUTCMinutes()).padStart(2,'0')+':'"
            "+String(d.getUTCSeconds()).padStart(2,'0')"
        ),
        "%I:%M %p": (
            "var h=d.getUTCHours();var ampm=h>=12?'PM':'AM';h=h%12;h=h?h:12;"
            "return String(h).padStart(2,'0')+':'+String(d.getUTCMinutes()).padStart(2,'0')+' '+ampm"
        ),
    }

    # Fallback for a strftime pattern the table does not know; the UTC zone
    # keeps it on the same calendar day as the getters above.
    DATE_FALLBACK: str = "return d.toLocaleDateString(undefined,{timeZone:'UTC'})"

    @staticmethod
    def _date_prologue() -> str:
        """
        JavaScript that turns the announced value into a ``Date`` named ``d``.

        py-maidr emits a date axis's values as matplotlib date numbers -- days
        since ``matplotlib.dates.get_epoch()`` -- as floats, or as strings on a
        bar axis; ``new Date(value)`` would read either as milliseconds and
        announce every one of them as 1970. The epoch is read here rather than
        at import so a user's ``rcParams['date.epoch']`` is honoured, and the
        product is rounded to the millisecond so a day number carrying a
        time of day does not land a fraction of a millisecond before it.

        A value that is not a number -- a category name on an axis that also
        carries a date format -- is announced as itself, as upstream's
        ``asFiniteNumber`` does for its own formatters.
        """
        epoch = np.datetime64(mdates.get_epoch()) - np.datetime64("1970-01-01T00:00:00")
        offset_ms = int(epoch / np.timedelta64(1, "ms"))
        return (
            "var n=Number(value);if(!isFinite(n))return String(value);"
            f"var d=new Date(Math.round({offset_ms}+n*86400000));"
        )

    @staticmethod
    def date_format_to_js(fmt: Optional[str] = None) -> str:
        """
        Convert Python strftime format to JavaScript function body.

        Parameters
        ----------
        fmt : str, optional
            Python strftime format string (e.g., '%b %d', '%Y-%m-%d'). None,
            or a pattern the converter does not know, falls back to the
            locale's date rendering.

        Returns
        -------
        str
            JavaScript function body that formats matplotlib date numbers
            similarly.
        """
        body = JSBodyConverter.STRFTIME_PATTERNS.get(
            fmt or "", JSBodyConverter.DATE_FALLBACK
        )
        return JSBodyConverter._date_prologue() + body

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
            JavaScript function body for percent formatting. A value that is
            not a finite number is announced as itself, as upstream's
            ``asFiniteNumber`` does for the percent preset.
        """
        guard = "var n=parseFloat(value);if(!isFinite(n))return String(value);"
        if multiply:
            return guard + f"return (n*100).toFixed({decimals})+'%'"
        return guard + f"return n.toFixed({decimals})+'%'"

    @staticmethod
    def literal_percent_format_to_js(
        decimals: Optional[int],
        suffix: str,
        grouping: bool = False,
        exponent: bool = False,
    ) -> str:
        """
        Convert a format string ending in a literal percent sign, like
        ``{x:.1f} %``, to a JavaScript function body.

        Parameters
        ----------
        decimals : int, optional
            Precision of the field. None is a field with no precision,
            ``{x}`` or ``{x:,}``, which Python renders with the float's
            default form -- ``45.0``, ``45.5`` -- so the body keeps the
            ``.0`` on an integral value where ``String(n)`` would drop it.
        suffix : str
            The literal text after the field, emitted verbatim -- ``%``,
            or `` %`` with the space the format string carries.
        grouping : bool
            Whether the spec asks for thousands separators, ``{x:,.0f}``.
            Written the way the comma preset's body is, through
            ``toLocaleString('en-US')``.
        exponent : bool
            Whether the spec is scientific, ``{x:.2e}``. Python pads the
            exponent to two digits, ``1.23e+03``, where ``toExponential``
            gives ``1.23e+3``; the body pads it back.

        Returns
        -------
        str
            JavaScript function body for a literal-suffix percent format.
            A value that is not a finite number is announced as itself, as
            upstream's ``asFiniteNumber`` does for the percent preset.
        """
        if exponent:
            number = (
                f"n.toExponential({decimals})"
                ".replace(/e([+-])(\\d)$/,function(s,a,b){return 'e'+a+'0'+b})"
            )
        elif decimals is None and grouping:
            number = (
                "(Number.isInteger(n)?n.toLocaleString('en-US')+'.0'"
                ":n.toLocaleString('en-US',{maximumFractionDigits:20}))"
            )
        elif decimals is None:
            # Python's default float str, for the magnitudes a tick takes;
            # an extreme Python writes in exponent form, 1e-05 or 1e+16,
            # String(n) spells out.
            number = "(Number.isInteger(n)?n.toFixed(1):String(n))"
        elif grouping:
            number = (
                "n.toLocaleString('en-US',{minimumFractionDigits:"
                f"{decimals},maximumFractionDigits:{decimals}}})"
            )
        else:
            number = f"n.toFixed({decimals})"
        return (
            "var n=parseFloat(value);if(!isFinite(n))return String(value);"
            f"return {number}+{json.dumps(suffix)}"
        )

    @staticmethod
    def scaled_percent_format_to_js(scale: float, decimals: int, symbol: str) -> str:
        """
        Convert a ``PercentFormatter`` that is not the fraction preset to a
        JavaScript function body.

        Parameters
        ----------
        scale : float
            Factor the data value is multiplied by before the symbol is
            appended -- matplotlib's ``100 / xmax``.
        decimals : int
            Number of decimal places
        symbol : str
            Text appended to the number; ``''`` for a bare number.

        Returns
        -------
        str
            JavaScript function body for percent formatting at that scale.
            A value that is not a finite number is announced as itself, as
            upstream's ``asFiniteNumber`` does for the percent preset.
        """
        return (
            "var n=parseFloat(value);if(!isFinite(n))return String(value);"
            f"return (n*{scale!r}).toFixed({decimals})+{json.dumps(symbol)}"
        )

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
        """Parse a PercentFormatter to FormatConfig at the scale matplotlib draws it.

        The ``percent`` preset in MAIDR JS multiplies by 100, which is only what
        matplotlib does for ``xmax=1.0``. Its default is ``xmax=100`` -- the data
        are already percentages -- so that and every other ``xmax`` get a
        function body scaled by ``100 / xmax``, as ``format_pct`` is. The
        decimals are the ones matplotlib draws: its own when it was given
        them, otherwise the count ``format_pct`` derives from the axis range.
        """
        explicit = None
        if hasattr(formatter, "decimals") and formatter.decimals is not None:
            explicit = int(formatter.decimals)
        xmax = float(getattr(formatter, "xmax", 100.0))

        # matplotlib divides by xmax at draw time and raises on zero; a schema
        # extraction has nothing sensible to scale by, so it keeps the preset.
        # A negative xmax draws a sign-flipped percentage and scales as usual.
        if xmax == 0:
            return FormatConfig(type=FormatType.PERCENT, decimals=explicit)

        decimals = FormatConfigBuilder._percent_decimals(formatter, xmax, explicit)
        symbol = getattr(formatter, "symbol", "%") or ""

        if xmax == 1.0 and symbol == "%":
            return FormatConfig(type=FormatType.PERCENT, decimals=decimals)

        # Unattached, the formatter has no range to derive decimals from; one
        # is what the preset defaults to and reads the same way.
        js_body = JSBodyConverter.scaled_percent_format_to_js(
            100.0 / xmax, decimals if decimals is not None else 1, symbol
        )
        return FormatConfig(function=js_body)

    @staticmethod
    def _percent_decimals(
        formatter: PercentFormatter, xmax: float, explicit: Optional[int]
    ) -> Optional[int]:
        """The decimals matplotlib's ``format_pct`` draws for this formatter.

        With none given, matplotlib derives them at draw time from the axis
        view interval: ``ceil(2 - log10(2 * range))`` with the range scaled
        to percent, clamped to 0..5 and 0 for an empty range. The same rule
        is applied here so the announced text carries the digits the tick
        label shows -- "45%" on a 0-100 axis, not "45.0%". Returns None when
        the formatter is not attached to an axis yet, or the range is not a
        finite number, because there is nothing to derive from.
        """
        if explicit is not None:
            return explicit
        axis = getattr(formatter, "axis", None)
        if axis is None:
            return None
        vmin, vmax = axis.get_view_interval()
        scaled_range = 100.0 * (abs(float(vmax) - float(vmin)) / xmax)
        if not math.isfinite(scaled_range):
            return None
        if scaled_range <= 0:
            return 0
        return min(5, max(0, math.ceil(2.0 - math.log10(2.0 * scaled_range))))

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
            js_body = JSBodyConverter.date_format_to_js()
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

        # A literal % closing the string, like {x:.0f}% or {x} %, is a
        # percentage the data already hold: keep the suffix as written,
        # without the preset's multiply-by-100. A % followed by more text is
        # not a suffix and is read as whatever the field itself says; so is
        # a field whose spec is not one of empty, grouping, fixed-point or
        # scientific -- the presets below would drop the suffix (#703).
        suffix_match = re.search(r"\{[^}:]*(?::([^}]*))?\}(\s*%\s*)$", fmt)
        if suffix_match:
            spec, suffix = suffix_match.group(1) or "", suffix_match.group(2)
            parsed = re.fullmatch(r"(,)?(?:\.(\d+)([fe]))?", spec)
            if parsed:
                grouping, precision, kind = parsed.groups()
                return FormatConfig(
                    function=JSBodyConverter.literal_percent_format_to_js(
                        int(precision) if precision else None,
                        suffix,
                        grouping=bool(grouping),
                        exponent=kind == "e",
                    )
                )

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
        Dictionary with 'x' and/or 'y' keys containing ``AxisFormat``
        configurations. Only includes axes where a format could be detected.

    Notes
    -----
    The returned mapping is consumed by ``MaidrPlot.render()`` and nested into
    the per-axis ``AxisConfig`` objects of the MAIDR schema — i.e.
    ``axes[x|y|z].format``. It is never emitted as a sibling of
    ``x``/``y``/``z`` inside ``axes`` (the legacy shape has been removed).

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
