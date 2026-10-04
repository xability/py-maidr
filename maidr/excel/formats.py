"""How Excel writes a value: its numbers, its dates and its number formats.

A chart part keeps numbers as text and dates as serial numbers, and says how
each is written with an Excel format code such as ``mmm-yy`` or ``$#,##0``.
This reads them, writes a date or a category the way its format code writes
it, and turns a number format into the matplotlib formatter that py-maidr
announces it through.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any, Iterator

from matplotlib.ticker import Formatter, PercentFormatter, StrMethodFormatter

_MONTHS = (
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
)  # fmt: skip
_DAYS = (
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
)  # fmt: skip
_DATE_TOKEN = re.compile(
    r'"[^"]*"|\\.|\[[^\]]*\]|yyyy|yy|e|mmmmm|mmmm|mmm|mm|m|dddd|ddd|dd|d'
    r"|hh|h|ss|s|am/pm|a/p|.",
    re.IGNORECASE,
)
_NOT_A_TOKEN = re.compile(r'"[^"]*"|\\.|\[[^\]]*\]')

_CURRENCY = re.compile(r"\[\$([^\]-]*)[^\]]*\]|\"([^\"]*)\"|([$€£¥])")
_SYMBOLS = ("$", "€", "£", "¥")


def as_number(value: Any) -> float | None:
    """A cell or cached value as a finite number, or ``None``."""
    if value is None or value == "":
        return None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def as_text(value: Any) -> str | None:
    """A cell or cached value as text, or ``None`` when it is empty."""
    if value is None or value == "":
        return None
    if isinstance(value, float):
        return _number_label(value)
    return str(value)


def _number_label(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:.10g}"


def category_label(
    value: Any, code: str | None, dates: bool, date1904: bool
) -> str | None:
    """A category as Excel labels it: text as it is, a date as the axis shows it."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        return value
    number = as_number(value)
    if number is None:
        return None
    if is_date_format(code):
        return format_date(serial_to_datetime(number, date1904), code)
    if dates:
        return format_date(serial_to_datetime(number, date1904), None)
    return _number_label(number)


def is_date_format(code: str | None) -> bool:
    """
    Whether an Excel number format shows a date or a time.

    Parameters
    ----------
    code : str or None
        The format code, such as ``"mmm-yy"`` or ``"0.0%"``.

    Returns
    -------
    bool
        ``True`` for a code with date or time parts and no digit placeholders.
    """
    if not code or code.lower() == "general":
        return False
    bare = _NOT_A_TOKEN.sub("", code.split(";")[0]).lower()
    return any(c in bare for c in "ymdhs") and not re.search(r"[0#?]", bare)


def serial_to_datetime(serial: float, date1904: bool = False) -> datetime:
    """
    The date an Excel serial number stands for.

    Parameters
    ----------
    serial : float
        Days since the workbook's epoch, with the time of day as a fraction.
    date1904 : bool, default False
        Whether the workbook counts from 1904-01-01 rather than 1900.

    Returns
    -------
    datetime
        The date and time, to the nearest second. In the 1900 system serial
        60 is Excel's 1900-02-29, which never was; it reads as 1900-02-28.
    """
    if date1904:
        base = datetime(1904, 1, 1)
    elif serial >= 61:
        base = datetime(1899, 12, 30)
    else:
        base = datetime(1899, 12, 31)
        if serial >= 60:
            serial -= 1
    return base + timedelta(seconds=round(serial * 86400))


def format_date(moment: datetime, code: str | None) -> str:
    """
    A date written the way an Excel format code writes it.

    Parameters
    ----------
    moment : datetime
        The date.
    code : str or None
        An Excel date format code such as ``"mmm-yy"``. Without one, the date
        is written ISO 8601 style, with the time only when there is one.

    Returns
    -------
    str
        ``"Jan-24"`` for ``mmm-yy``. Names are in English.
    """
    if not code or not is_date_format(code):
        if moment.hour or moment.minute or moment.second:
            return moment.strftime("%Y-%m-%d %H:%M:%S").removesuffix(":00")
        return moment.strftime("%Y-%m-%d")
    tokens = _DATE_TOKEN.findall(code.split(";")[0])
    twelve_hour = any(t.lower() in ("am/pm", "a/p") for t in tokens)
    out = []
    for i, token in enumerate(tokens):
        lower = token.lower()
        if lower in ("m", "mm") and _is_minute(tokens, i):
            out.append(f"{moment.minute:02d}" if lower == "mm" else str(moment.minute))
        else:
            out.append(_date_part(token, lower, moment, twelve_hour))
    return "".join(out).strip()


def _is_minute(tokens: list[str], index: int) -> bool:
    """Whether an ``m`` token means minutes: after hours, or before seconds."""

    def letters(seq: Iterator[str]) -> str | None:
        for token in seq:
            lower = token.lower()
            if lower[:1] in "ymdhs" and not lower.startswith(("[", '"', "\\")):
                return lower
        return None

    before = letters(reversed(tokens[:index]))
    after = letters(iter(tokens[index + 1 :]))
    return (before or "").startswith("h") or (after or "").startswith("s")


def _date_part(token: str, lower: str, moment: datetime, twelve_hour: bool) -> str:
    hour = moment.hour % 12 or 12 if twelve_hour else moment.hour
    parts = {
        "yyyy": f"{moment.year:04d}",
        "e": f"{moment.year:04d}",
        "yy": f"{moment.year % 100:02d}",
        "mmmmm": _MONTHS[moment.month - 1][0],
        "mmmm": _MONTHS[moment.month - 1],
        "mmm": _MONTHS[moment.month - 1][:3],
        "mm": f"{moment.month:02d}",
        "m": str(moment.month),
        "dddd": _DAYS[moment.weekday()],
        "ddd": _DAYS[moment.weekday()][:3],
        "dd": f"{moment.day:02d}",
        "d": str(moment.day),
        "hh": f"{hour:02d}",
        "h": str(hour),
        "ss": f"{moment.second:02d}",
        "s": str(moment.second),
        "am/pm": "AM" if moment.hour < 12 else "PM",
        "a/p": "A" if moment.hour < 12 else "P",
    }
    if lower in parts:
        return parts[lower]
    if token.startswith('"') and token.endswith('"'):
        return token[1:-1]
    if token.startswith("\\"):
        return token[1:]
    if token.startswith("["):
        return ""
    return token


def number_formatter(code: str | None) -> Formatter | None:
    """
    The matplotlib formatter for an Excel number format, where py-maidr can
    announce it.

    Parameters
    ----------
    code : str or None
        An Excel format code such as ``"0.0%"`` or ``"$#,##0"``.

    Returns
    -------
    matplotlib.ticker.Formatter or None
        A percent, currency or grouped-number formatter, or ``None`` for
        ``General``, dates and anything else, which read as plain numbers.
    """
    if not code or code.lower() == "general" or is_date_format(code):
        return None
    section = code.split(";")[0]
    match = re.search(r"\.([0#?]+)", section)
    decimals = len(match.group(1)) if match else 0
    bare = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]', "", section)
    if "%" in bare:
        return PercentFormatter(xmax=1, decimals=decimals)
    if not re.search(r"[0#]", bare):
        return None
    grouping = "," if re.search(r"[0#],[0#]", bare) else ""
    symbol = next(
        (
            s
            for found in _CURRENCY.finditer(section)
            for s in found.groups()
            if s and s.strip() in _SYMBOLS
        ),
        "",
    ).strip()
    return StrMethodFormatter(f"{symbol}{{x:{grouping}.{decimals}f}}")
