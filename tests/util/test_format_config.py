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


def percent(x, pos=None):
    """A FuncFormatter whose name is what the heuristic keys on."""
    return f"{x * 100:.1f}%"


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
        [NODE, "-e", script],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout


def _percent_body_in_python(body: str, value: float) -> str:
    """Apply the arithmetic of a percent body -- ``(n*scale).toFixed(d)+symbol``
    -- without a JS engine, so the scale is checked even where node is absent."""
    match = re.search(
        r"(?:\(n\*(?P<scale>[^)]+)\)|\bn)"
        r"\.toFixed\((?P<decimals>\d+)\)\+(?P<symbol>\"[^\"]*\"|'[^']*')$",
        body,
    )
    assert match is not None, body
    scale = float(match.group("scale") or 1)
    return f"{value * scale:.{match.group('decimals')}f}{match.group('symbol')[1:-1]}"


def _drawn(formatter, value):
    """The tick text, with the Unicode minus ``fix_minus`` draws written as
    the hyphen-minus a JS body produces; a reader speaks both as "minus"."""
    return formatter(value).replace("\u2212", "-")


def _formatter_with_axis(formatter, ylim=(0, 100)):
    """``PercentFormatter.__call__`` reads its axis to pick the decimals."""
    fig, ax = plt.subplots()
    ax.set_ylim(*ylim)
    ax.yaxis.set_major_formatter(formatter)
    plt.close(fig)
    return formatter


@pytest.mark.parametrize(
    ("formatter", "expected"),
    [
        # No decimals given: matplotlib derives them from the 0-100 range.
        (PercentFormatter(), "45%"),
        (PercentFormatter(xmax=100, decimals=0, symbol=" %"), "45 %"),
        (PercentFormatter(xmax=200, decimals=1), "22.5%"),
        (PercentFormatter(decimals=0, symbol=None), "45"),
        # A negative xmax flips the sign; the range-derived decimals are 0.
        (PercentFormatter(xmax=-100), "-45%"),
        (StrMethodFormatter("{x:.0f}%"), "45%"),
    ],
)
def test_a_percent_axis_is_announced_at_matplotlibs_scale(formatter, expected):
    formatter = _formatter_with_axis(formatter)
    config = FormatConfigBuilder.from_formatter(formatter).to_dict()

    assert set(config) == {"function"}
    assert _percent_body_in_python(config["function"], 45) == expected
    # The very text matplotlib draws on the tick, decimals included.
    assert _drawn(formatter, 45) == expected


@pytest.mark.parametrize(
    ("formatter", "ylim", "value"),
    [
        # format_pct's table: >50 -> 0 decimals, >5 -> 1, >0.5 -> 2, ...
        (PercentFormatter(), (0, 100), 45.678),
        (PercentFormatter(), (0, 10), 4.5678),
        (PercentFormatter(), (0, 1), 0.45678),
        (PercentFormatter(), (0, 0.1), 0.045678),
        # ... clamped to 5 for a tiny range, and the scale is xmax's.
        (PercentFormatter(), (0, 1e-9), 4.5678e-10),
        (PercentFormatter(xmax=200, symbol=" pct"), (0, 50), 22.839),
        (PercentFormatter(xmax=1.0), (0, 1), 0.45678),
        (PercentFormatter(xmax=1.0), (0, 0.05), 0.045678),
    ],
)
def test_the_decimals_follow_the_axis_range_as_matplotlib_picks_them(
    formatter, ylim, value
):
    formatter = _formatter_with_axis(formatter, ylim)
    config = FormatConfigBuilder.from_formatter(formatter).to_dict()

    if "function" in config:
        announced = _percent_body_in_python(config["function"], value)
    else:
        # The fraction preset: the bundle does (n*100).toFixed(decimals)+'%'.
        assert config["type"] == "percent"
        announced = f"{value * 100:.{config['decimals']}f}%"
    assert announced == formatter(value)


def test_an_unattached_percent_formatter_keeps_the_presets_one_decimal():
    """Nothing to derive the decimals from until there is an axis range."""
    body = FormatConfigBuilder.from_formatter(PercentFormatter()).function
    assert _percent_body_in_python(body, 45) == "45.0%"
    assert FormatConfigBuilder.from_formatter(PercentFormatter(xmax=1.0)).to_dict() == {
        "type": "percent"
    }


def test_an_infinite_xmax_scales_to_zero_as_matplotlib_draws_it():
    """``100 / inf`` is ``0.0``, a numeral the body can carry.

    matplotlib draws every tick of such an axis as ``0%``; the preset would
    have announced ``4500%`` instead.
    """
    formatter = _formatter_with_axis(PercentFormatter(xmax=float("inf")))

    config = FormatConfigBuilder.from_formatter(formatter).to_dict()

    assert "n*0.0" in config["function"]


@pytest.mark.parametrize("xmax", [0, float("nan")], ids=["zero", "nan"])
def test_a_percent_formatter_with_no_finite_scale_keeps_the_preset(xmax):
    """matplotlib divides by xmax at draw time; extraction must not raise.

    Nor may it emit a body it cannot run: ``100 / nan`` is ``nan``, and
    ``repr`` spells that ``nan``, which is not a JavaScript numeral -- the
    body would throw a ``ReferenceError`` at the first tick.
    """
    for formatter in (PercentFormatter(xmax=xmax), PercentFormatter(xmax, 2)):
        formatter = _formatter_with_axis(formatter)
        config = FormatConfigBuilder.from_formatter(formatter).to_dict()
        assert config["type"] == "percent"
        assert config.get("decimals") == formatter.decimals
        assert "function" not in config


def test_a_non_default_percent_axis_is_announced_as_its_tick_is_drawn():
    """End to end: the axis, its formatter, and the body the bundle runs."""
    formatter = PercentFormatter(xmax=200, symbol=" pct")
    fig, ax = plt.subplots()
    ax.set_ylim(0, 50)
    ax.yaxis.set_major_formatter(formatter)
    try:
        formats = extract_axis_format(ax)
        drawn = formatter(45)
    finally:
        plt.close(fig)

    assert set(formats) == {"y"}
    body = formats["y"]["function"]
    assert drawn == "22.5 pct"
    assert _percent_body_in_python(body, 45) == drawn
    assert _run_js(body, 45) == drawn


@pytest.mark.parametrize(
    ("formatter", "value"),
    [
        (PercentFormatter(), 45),
        (PercentFormatter(xmax=100, decimals=0, symbol=" %"), 45),
        (PercentFormatter(xmax=-100), 45),
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


@pytest.mark.parametrize(
    "formatter",
    [PercentFormatter(), StrMethodFormatter("{x:.0f}%"), FuncFormatter(percent)],
    ids=["PercentFormatter", "literal-suffix", "FuncFormatter-percent"],
)
def test_a_category_name_on_a_percent_axis_is_announced_as_itself(formatter):
    body = FormatConfigBuilder.from_formatter(formatter).function
    assert _run_js(body, "Cherries") == "Cherries"


# 0.25 at one decimal and 1234.5 at none sit exactly on a rounding tie:
# Python rounds half-even, to 0.2 and 1,234; JavaScript's ``toFixed`` and
# ``Intl.NumberFormat`` round half up, to 0.3 and 1,235. Every such body,
# upstream's ``fixed`` and ``number`` presets included, differs from Python
# there; it is not what the literal suffix changes, so it is recorded rather
# than papered over.
HALF_UP_TIE = pytest.mark.xfail(
    strict=True, reason="JavaScript rounds a half up where Python rounds it even"
)
TIES = {("{x:.1f} %", 0.25), ("{x:,.0f}%", 1234.5)}


def _suffix_case(fmt, value):
    return pytest.param(fmt, value, marks=[HALF_UP_TIE] if (fmt, value) in TIES else [])


@pytest.mark.parametrize(
    ("fmt", "value"),
    [
        _suffix_case(fmt, value)
        for fmt in ("{x}%", "{x} %", "{x:.1f} %")
        for value in (45, 45.5, 0.25)
    ],
)
def test_a_literal_percent_suffix_is_announced_as_python_formats_it(fmt, value):
    """The suffix verbatim -- space included -- and, with no precision given,
    the float's default form: matplotlib hands the formatter a float, so the
    tick at 45 reads "45.0%", and the body keeps that ``.0``."""
    formatter = StrMethodFormatter(fmt)
    body = FormatConfigBuilder.from_formatter(formatter).function
    assert body.endswith("+" + json.dumps(fmt[fmt.index("}") + 1 :]))
    assert _run_js(body, float(value)) == formatter(float(value))


@pytest.mark.parametrize(
    ("fmt", "value"),
    [
        _suffix_case(fmt, value)
        for fmt, values in (
            ("{x:,.0f}%", (1234.5, 1234.56, 45)),
            ("{x:,.2f}%", (1234.5, 45)),
            ("{x:,}%", (1234.5, 45)),
            ("{x:.2e}%", (1234.5, 0.25)),
        )
        for value in values
    ],
)
def test_a_grouped_or_scientific_field_keeps_its_literal_suffix(fmt, value):
    """These specs fell through to the number and scientific presets, which
    know nothing of the suffix (#703). The exponent keeps Python's two
    digits, ``e+03``, and the grouped form its ``.0`` on an integral value."""
    formatter = StrMethodFormatter(fmt)
    body = FormatConfigBuilder.from_formatter(formatter).function
    assert body.endswith("+" + json.dumps("%"))
    assert ("toExponential" if "e}" in fmt else "toLocaleString") in body
    assert _run_js(body, float(value)) == _drawn(formatter, float(value))


@pytest.mark.parametrize(
    ("fmt", "value"),
    [
        (fmt, value)
        for fmt in ("{x:e}%", "{x:f}%", "{x:f} %")
        for value in (45, 1234.5, 0.25)
    ],
)
def test_a_bare_kind_with_no_precision_keeps_pythons_six_decimals(fmt, value):
    """``{x:e}`` and ``{x:f}`` are valid with no precision: Python draws six
    decimals for either, ``4.500000e+01`` and ``45.000000``. The suffix
    parser wanted a ``.`` before the kind, so both fell through to the
    scientific and fixed presets and lost the ``%``."""
    formatter = StrMethodFormatter(fmt)
    body = FormatConfigBuilder.from_formatter(formatter).function
    assert body.endswith("+" + json.dumps(fmt[fmt.index("}") + 1 :]))
    assert "(6)" in body
    assert _run_js(body, float(value)) == _drawn(formatter, float(value))


def test_a_percent_sign_that_is_not_a_suffix_is_read_as_the_field_says():
    """``{x:.0f}% of total`` is a fixed-point field with some text after it."""
    config = FormatConfigBuilder.from_formatter(StrMethodFormatter("{x:.0f}% of total"))
    assert config.to_dict() == {"type": "fixed", "decimals": 0}


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


def test_a_date_line_says_its_values_count_days():
    """maidr.js reads a length along a time axis as a span of time once the
    axis's format says what one of its values counts (xability/maidr#1695)."""
    dates = [datetime.date(2024, 1, 15) + datetime.timedelta(days=i) for i in range(3)]
    fig, ax = plt.subplots()
    ax.plot(dates, [1, 2, 3])
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    try:
        x_format = FigureManager.get_maidr(fig)._plots[0].schema["axes"]["x"]["format"]
    finally:
        plt.close(fig)

    assert x_format["unit"] == "day"


def test_a_date_histogram_says_its_bins_count_days():
    """Weekly bins of matplotlib dates are 7 wide: with the unit maidr.js
    reads that bin width as "1 week", without it as "7"."""
    start = datetime.date(2024, 1, 1)
    days = [start + datetime.timedelta(days=i) for i in range(28)]
    edges = mdates.date2num([start + datetime.timedelta(weeks=k) for k in range(5)])
    fig, ax = plt.subplots()
    ax.hist(days, bins=edges)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    try:
        schema = FigureManager.get_maidr(fig)._plots[0].schema
    finally:
        plt.close(fig)

    assert {b["xMax"] - b["xMin"] for b in schema["data"]} == {7.0}
    assert schema["axes"]["x"]["format"]["unit"] == "day"


def test_a_func_formatter_named_for_dates_says_its_values_count_days():
    def format_date(x, pos=None):
        return str(x)

    config = FormatConfigBuilder.from_formatter(FuncFormatter(format_date)).to_dict()

    assert config["unit"] == "day"


def test_a_format_that_draws_no_dates_names_no_unit():
    formats = [
        FormatConfigBuilder.from_formatter(StrMethodFormatter("${x:,.2f}")),
        FormatConfigBuilder.from_formatter(FuncFormatter(lambda x, pos=None: str(x))),
        FormatConfigBuilder.from_formatter(PercentFormatter()),
    ]

    assert [config.to_dict().get("unit") for config in formats] == [None, None, None]


def _x_format(fig) -> dict:
    """The first layer's x axis format, read as the schema emits it."""
    try:
        return FigureManager.get_maidr(fig)._plots[0].schema["axes"]["x"]["format"]
    finally:
        plt.close(fig)


def test_a_line_on_matplotlibs_default_date_axis_announces_dates():
    """A date axis gets ``AutoDateFormatter`` unless the caller sets one,
    which py-maidr read as no format: "Date is 19,737"."""
    start = datetime.date(2024, 1, 15)
    dates = [start + datetime.timedelta(days=i) for i in range(28)]
    fig, ax = plt.subplots()
    ax.plot(dates, range(28))

    x_format = _x_format(fig)

    # The format a DateFormatter at the axis's resolution gets, whole.
    daily = FormatConfigBuilder.from_formatter(mdates.DateFormatter("%Y-%m-%d"))
    assert x_format == daily.to_dict()
    assert x_format["unit"] == "day"
    assert _run_js(x_format["function"], mdates.date2num(dates[0])) == "2024-01-15"


def test_a_concise_date_axis_announces_full_dates():
    """``ConciseDateFormatter`` labels ticks "Jan", "08"; a value is read
    as its whole date."""
    start = datetime.date(2024, 1, 15)
    dates = [start + datetime.timedelta(days=i) for i in range(28)]
    fig, ax = plt.subplots()
    ax.plot(dates, range(28))
    locator = mdates.AutoDateLocator()
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))

    body = _x_format(fig)["function"]

    assert _run_js(body, mdates.date2num(dates[3])) == "2024-01-18"


def test_a_date_histogram_on_the_default_axis_announces_its_edges_as_dates():
    start = datetime.date(2024, 1, 1)
    days = [start + datetime.timedelta(days=i) for i in range(28)]
    edges = mdates.date2num([start + datetime.timedelta(weeks=k) for k in range(5)])
    fig, ax = plt.subplots()
    ax.hist(days, bins=edges)

    body = _x_format(fig)["function"]

    assert [_run_js(body, edge) for edge in edges[:2]] == ["2024-01-01", "2024-01-08"]


def test_an_axis_ticked_by_the_hour_announces_the_time_of_day():
    start = datetime.datetime(2024, 1, 15, 6)
    times = [start + datetime.timedelta(hours=i) for i in range(12)]
    fig, ax = plt.subplots()
    ax.plot(times, range(12))

    body = _x_format(fig)["function"]

    assert _run_js(body, mdates.date2num(times[3])) == "2024-01-15 09:00"


def test_hourly_values_ticked_by_the_week_announce_the_time_of_day():
    """1440 hourly readings over 60 days are ticked weekly; read at the
    ticks' step, 24 points in a row read as the same date."""
    start = datetime.datetime(2024, 1, 1)
    times = [start + datetime.timedelta(hours=i) for i in range(1440)]
    fig, ax = plt.subplots()
    ax.plot(times, range(1440))
    ticks = ax.xaxis.get_majorticklocs()

    body = _x_format(fig)["function"]

    assert min(ticks[1:] - ticks[:-1]) >= 7
    assert _run_js(body, mdates.date2num(times[25])) == "2024-01-02 01:00"


def test_values_a_minute_apart_announce_minutes_without_seconds():
    """A minute between float day numbers is a hair under 1/1440 of a day;
    read as a step of seconds, every value ended in ":00"."""
    start = datetime.datetime(2024, 1, 15, 6)
    times = [start + datetime.timedelta(minutes=i) for i in range(30)]
    fig, ax = plt.subplots()
    ax.plot(times, range(30))

    body = _x_format(fig)["function"]

    assert _run_js(body, mdates.date2num(times[1])) == "2024-01-15 06:01"


def test_dates_on_the_y_axis_are_read_at_their_own_step():
    start = datetime.datetime(2024, 1, 15, 6)
    times = [start + datetime.timedelta(minutes=i) for i in range(30)]
    fig, ax = plt.subplots()
    ax.plot(range(30), times)
    try:
        schema = FigureManager.get_maidr(fig)._plots[0].schema
    finally:
        plt.close(fig)

    body = schema["axes"]["y"]["format"]["function"]
    assert _run_js(body, mdates.date2num(times[1])) == "2024-01-15 06:01"


def test_hourly_bars_ticked_by_the_week_announce_the_time_of_day():
    start = datetime.datetime(2024, 1, 1)
    times = [start + datetime.timedelta(hours=i) for i in range(1440)]
    fig, ax = plt.subplots()
    ax.bar(times, range(1440), width=1 / 48)

    body = _x_format(fig)["function"]

    assert _run_js(body, mdates.date2num(times[25])) == "2024-01-02 01:00"


def test_a_date_formatter_on_no_axis_reads_whole_dates():
    pattern = FormatConfigBuilder._tick_date_pattern(mdates.AutoDateFormatter(None))

    assert pattern == "%Y-%m-%d"


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
