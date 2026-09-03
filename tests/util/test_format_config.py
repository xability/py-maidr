"""Percent and date formats are announced at the scale matplotlib draws them (#703).

py-maidr hands the bundle a format config it applies to the announced data
value. ``PercentFormatter()`` defaults to ``xmax=100`` -- the data are already
percentages -- while the bundle's ``percent`` preset multiplies by 100 again,
so a 45 % bar was read as "4500.0%". A ``DateFormatter`` axis emits
matplotlib day numbers, which ``new Date(value)`` read as milliseconds, so
every date was read as 1970.
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
import subprocess

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
from matplotlib.ticker import FuncFormatter, PercentFormatter, StrMethodFormatter  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.util.format_config import (  # noqa: E402
    FormatConfigBuilder,
    JSBodyConverter,
    extract_axis_format,
)

NODE = shutil.which("node")

# A JS getter that is not the UTC one: ``getMonth`` but not ``getUTCMonth``.
LOCAL_GETTER = re.compile(r"\.get(?!UTC)[A-Z]\w*\(")


def _run_js(body: str, value: object) -> str:
    """Evaluate a format body the way the bundle does: ``new Function('value', body)``."""
    if NODE is None:
        pytest.skip("node is not installed")
    script = (
        f"var f=new Function('value',{json.dumps(body)});"
        f"process.stdout.write(String(f({json.dumps(value)})))"
    )
    return subprocess.run(
        [NODE, "-e", script], check=True, capture_output=True, text=True
    ).stdout


def _percent_body_in_python(body: str, value: float) -> str:
    """Apply the arithmetic of a percent body -- ``(n*scale).toFixed(d)+symbol``
    -- without a JS engine, so the scale is checked even where node is absent."""
    match = re.search(
        r"(?:\(n\*(?P<scale>[^)]+)\)|parseFloat\(value\))"
        r"\.toFixed\((?P<decimals>\d+)\)\+(?P<symbol>\"[^\"]*\"|'[^']*')$",
        body,
    )
    assert match is not None, body
    scale = float(match.group("scale") or 1)
    return f"{value * scale:.{match.group('decimals')}f}{match.group('symbol')[1:-1]}"


def _formatter_with_axis(formatter):
    """``PercentFormatter.__call__`` reads its axis to pick the decimals."""
    fig, ax = plt.subplots()
    ax.plot([0, 100], [0, 100])
    ax.yaxis.set_major_formatter(formatter)
    plt.close(fig)
    return formatter


@pytest.mark.parametrize(
    ("formatter", "expected"),
    [
        # matplotlib picks the decimals from the axis range when none are
        # given ("45%" here); the body keeps the preset's one decimal.
        (PercentFormatter(), "45.0%"),
        (PercentFormatter(xmax=100, decimals=0, symbol=" %"), "45 %"),
        (PercentFormatter(xmax=200, decimals=1), "22.5%"),
        (PercentFormatter(decimals=0, symbol=None), "45"),
        (StrMethodFormatter("{x:.0f}%"), "45%"),
    ],
)
def test_a_percent_axis_is_announced_at_matplotlibs_scale(formatter, expected):
    formatter = _formatter_with_axis(formatter)
    config = FormatConfigBuilder.from_formatter(formatter).to_dict()

    assert set(config) == {"function"}
    assert _percent_body_in_python(config["function"], 45) == expected
    # Same number matplotlib draws, whatever decimals it settled on.
    drawn = formatter(45)
    assert float(re.match(r"-?[\d.]+", expected).group()) == float(
        re.match(r"-?[\d.]+", drawn).group()
    )
    assert expected.lstrip("0123456789.") == drawn.lstrip("0123456789.")


@pytest.mark.parametrize(
    ("formatter", "value"),
    [
        (PercentFormatter(), 45),
        (PercentFormatter(xmax=100, decimals=0, symbol=" %"), 45),
        (StrMethodFormatter("{x:.0f}%"), 45),
    ],
)
def test_the_bundle_evaluates_the_percent_body_the_same_way(formatter, value):
    formatter = _formatter_with_axis(formatter)
    body = FormatConfigBuilder.from_formatter(formatter).function
    assert _run_js(body, value) == _percent_body_in_python(body, value)


@pytest.mark.parametrize(
    ("formatter", "expected"),
    [
        (PercentFormatter(xmax=1.0), {"type": "percent"}),
        (PercentFormatter(xmax=1.0, decimals=1), {"type": "percent", "decimals": 1}),
        (StrMethodFormatter("{x:.1%}"), {"type": "percent", "decimals": 1}),
    ],
)
def test_a_fraction_axis_keeps_the_percent_preset(formatter, expected):
    """These are the cases the preset's multiply-by-100 is right for."""
    assert FormatConfigBuilder.from_formatter(formatter).to_dict() == expected


def test_a_category_name_on_a_percent_axis_is_announced_as_itself():
    body = FormatConfigBuilder.from_formatter(PercentFormatter()).function
    assert _run_js(body, "Cherries") == "Cherries"


@pytest.mark.parametrize(
    "fmt", [*JSBodyConverter.STRFTIME_PATTERNS, "%d %B %Y (%A)", None]
)
def test_every_date_body_reads_matplotlib_day_numbers_in_utc(fmt):
    body = JSBodyConverter.date_format_to_js(fmt)
    assert "*86400000" in body
    assert "isFinite" in body
    assert not LOCAL_GETTER.search(body), body


def test_the_date_body_counts_days_from_matplotlibs_epoch(monkeypatch):
    monkeypatch.setattr(mdates, "get_epoch", lambda: "2000-01-01T00:00:00")
    assert "new Date(Math.round(946684800000+n*86400000))" in (
        JSBodyConverter.date_format_to_js("%Y")
    )


def test_a_func_formatter_named_for_dates_gets_the_same_body():
    def format_date(x, pos=None):
        return str(x)

    body = FormatConfigBuilder.from_formatter(FuncFormatter(format_date)).function
    assert body == JSBodyConverter.date_format_to_js()


def _day_from_body(body: str, value: float) -> datetime.datetime:
    """The prologue's arithmetic in Python: ``new Date(offset + n*86400000)``."""
    match = re.search(r"new Date\(Math\.round\((-?\d+)\+n\*86400000\)\)", body)
    assert match is not None, body
    ms = round(int(match.group(1)) + float(value) * 86400000)
    return datetime.datetime(1970, 1, 1) + datetime.timedelta(milliseconds=ms)


def test_a_line_over_dates_announces_the_date_matplotlib_draws():
    dates = [datetime.date(2024, 1, 15) + datetime.timedelta(days=i) for i in range(3)]
    fig, ax = plt.subplots()
    ax.plot(dates, [1, 2, 3])
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    try:
        schema = FigureManager.get_maidr(fig)._plots[0].schema
        data = schema["data"][0]  # one point list per line
        x_format = schema["axes"]["x"]["format"]
    finally:
        plt.close(fig)

    xs = [point["x"] for point in data]
    assert xs == [mdates.date2num(d) for d in dates]
    body = x_format["function"]
    assert _day_from_body(body, xs[0]).strftime("%Y-%m-%d") == "2024-01-15"
    assert _run_js(body, xs[0]) == "2024-01-15"
    # A bar axis emits the same day number as a string.
    assert _run_js(body, str(int(xs[0]))) == "2024-01-15"


def test_a_time_of_day_survives_the_float_day_number():
    """00:09 as a day fraction is 19737.00625, whose product with 86400000
    lands a fraction of a millisecond early in floating point; ``new Date``
    truncates, so without rounding to the millisecond it read as 00:08."""
    nine_past = mdates.date2num(datetime.datetime(2024, 1, 15, 0, 9))
    body = JSBodyConverter.date_format_to_js("%H:%M")
    assert _day_from_body(body, nine_past).strftime("%H:%M") == "00:09"
    assert _run_js(body, nine_past) == "00:09"
    # The same body with the rounding taken out is what this guards against.
    assert _run_js(body.replace("Math.round(", "("), nine_past) == "00:08"


def test_a_date_axis_format_is_nested_under_the_axis():
    fig, ax = plt.subplots()
    ax.plot([datetime.date(2024, 1, 15)], [1])
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    try:
        formats = extract_axis_format(ax)
    finally:
        plt.close(fig)
    assert set(formats) == {"x"}
    assert _run_js(formats["x"]["function"], 19737.0) == "Jan 15"
