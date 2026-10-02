"""``DatetimeConverter`` works on the index and the Volume column as arrays
(#706).

Detecting the time period subtracted one Timestamp pair at a time,
``extract_volume_data`` built ``iloc[i]`` for every bar, and ``date_nums``
called ``date2num`` once per element. Each has a vectorised spelling with the
same result, and the reference loops below are the plain per-row versions of
what the class promises, so any drift between the two would show here.
"""

from __future__ import annotations

import math
from datetime import time

import matplotlib
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")

from maidr.core.plot.candlestick import CandlestickPlot  # noqa: E402
from maidr.util.datetime_conversion import (  # noqa: E402
    DatetimeConverter,
    create_datetime_converter,
)

ROWS = 200


def _frame(index: pd.DatetimeIndex) -> pd.DataFrame:
    rng = np.random.default_rng(706)
    opens = 100 + rng.normal(size=len(index)).cumsum()
    closes = opens + rng.normal(size=len(index))
    volume = rng.integers(1, 1000, len(index)).astype(float)
    volume[17] = np.nan
    volume[42] = 0.0
    return pd.DataFrame(
        {
            "Open": opens,
            "High": np.maximum(opens, closes) + 1,
            "Low": np.minimum(opens, closes) - 1,
            "Close": closes,
            "Volume": volume,
        },
        index=index,
    )


INDEXES = {
    "daily": pd.date_range("2024-01-01", periods=ROWS, freq="D"),
    "minute bars": pd.date_range("2024-01-01 09:30", periods=ROWS, freq="min"),
    "tz-aware hourly": pd.date_range(
        "2024-01-01", periods=ROWS, freq="h", tz="US/Eastern"
    ),
    "second resolution": pd.DatetimeIndex(
        pd.date_range("2024-01-01", periods=ROWS, freq="D").values.astype(
            "datetime64[s]"
        )
    ),
}


@pytest.fixture(params=list(INDEXES), ids=list(INDEXES))
def frame(request) -> pd.DataFrame:
    return _frame(INDEXES[request.param])


def _reference_labels(index: pd.DatetimeIndex) -> list[str]:
    """The labels without a ``datetime_format``: the date alone when no stamp
    has a time of day, and the full stamp when any does."""
    if all(stamp.time() == time(0) for stamp in index):
        return [stamp.date().isoformat() for stamp in index]
    return [str(stamp) for stamp in index]


def _reference_volume(frame: pd.DataFrame) -> list[tuple[str, float]]:
    labels = _reference_labels(frame.index)
    out = []
    for i in range(len(frame)):
        volume = frame.iloc[i]["Volume"]
        if pd.isna(volume) or volume <= 0:
            continue
        out.append((labels[i], float(volume)))
    return out


def _reference_date_nums(frame: pd.DataFrame) -> list[float]:
    return [float(mdates.date2num(stamp)) for stamp in frame.index]


def _reference_candles(frame: pd.DataFrame) -> list[dict]:
    out = []
    for i in range(len(frame)):
        row = frame.iloc[i]
        prices = [float(row[name]) for name in ("Open", "High", "Low", "Close")]
        if not all(math.isfinite(price) for price in prices):
            continue
        candle = {
            "value": str(frame.index[i]),
            "open": prices[0],
            "high": prices[1],
            "low": prices[2],
            "close": prices[3],
        }
        # A volume the frame does not record is left out, not reported as 0.
        if "Volume" in frame.columns and math.isfinite(float(row["Volume"])):
            candle["volume"] = float(row["Volume"])
        out.append(candle)
    return out


def test_volume_matches_a_row_by_row_loop(frame):
    converter = create_datetime_converter(frame)

    volume = converter.extract_volume_data(None)
    assert volume == _reference_volume(frame)
    # The NaN and the zero are the two bars the loop leaves out.
    assert len(volume) == ROWS - 2


def test_the_volume_label_is_still_the_formatted_datetime(frame):
    converter = create_datetime_converter(frame)

    labels = [label for label, _ in converter.extract_volume_data(None)]
    assert labels[0] == converter.get_formatted_datetime(0)
    assert labels == [
        label
        for i, label in enumerate(_reference_labels(frame.index))
        if i not in (17, 42)
    ]


def test_a_frame_without_volume_gives_nothing():
    frame = _frame(INDEXES["daily"]).drop(columns="Volume")

    assert create_datetime_converter(frame).extract_volume_data(None) == []


def _with_a_nat(index: pd.DatetimeIndex, at: int) -> pd.DatetimeIndex:
    values = index.tz_localize(None).to_numpy().copy()
    values[at] = np.datetime64("NaT")
    return pd.DatetimeIndex(values).tz_localize(index.tz)


@pytest.mark.parametrize("name", ["daily", "tz-aware hourly"])
def test_a_nat_in_the_index_is_left_out_of_date_nums(name):
    # ``date2num`` maps a NaT to NaN on a naive index and raises on a tz-aware
    # one; either way the number list must not carry it. A NaN would reach
    # ``_convert_date_num_to_string``, whose fallback is ``int(date_num)``.
    index = _with_a_nat(INDEXES[name], at=50)
    converter = create_datetime_converter(_frame(index))

    date_nums = converter.date_nums
    assert len(date_nums) == ROWS - 1
    assert all(math.isfinite(num) for num in date_nums)
    assert date_nums == [
        float(mdates.date2num(stamp)) for stamp in index if stamp is not pd.NaT
    ]


def test_date_nums_match_a_call_per_element(frame):
    converter = create_datetime_converter(frame)

    assert converter.date_nums == _reference_date_nums(frame)
    # Plain floats, as before -- ``np.float64`` would pass ``isinstance``.
    assert all(type(num) is float for num in converter.date_nums)  # noqa: E721


@pytest.mark.parametrize(
    ("freq", "expected"),
    [
        ("s", "minute"),
        ("min", "intraday"),
        ("h", "hour"),
        ("D", "day"),
        ("W", "week"),
        ("MS", "month"),
    ],
)
def test_the_time_period_is_read_off_the_whole_index(freq, expected):
    frame = _frame(pd.date_range("2024-01-01", periods=ROWS, freq=freq))

    assert create_datetime_converter(frame).time_period == expected


def test_the_time_period_of_the_reference_indexes(frame):
    # A second-resolution index must not be read as a thousand times shorter.
    diffs = [
        (frame.index[i] - frame.index[i - 1]).total_seconds()
        for i in range(1, len(frame))
    ]
    average = sum(diffs) / len(diffs)
    expected = "hour" if average < 86400 else "day"
    if average < 3600:
        expected = "intraday"

    assert create_datetime_converter(frame).time_period == expected


def test_a_single_row_has_no_time_period():
    frame = _frame(INDEXES["daily"]).iloc[:1]

    assert DatetimeConverter(frame).time_period == "unknown"


def test_the_candlestick_layer_matches_a_row_by_row_loop(frame, axes):
    frame.iloc[100, :4] = np.nan  # a gap mplfinance draws as empty geometry

    candles = CandlestickPlot([axes])._extract_from_dataframe(frame)
    assert candles == _reference_candles(frame)
    assert len(candles) == ROWS - 1
    # Row 17's NaN volume leaves that candle without one; row 42's 0 is kept.
    assert "volume" not in candles[17]
    assert candles[42]["volume"] == 0.0


@pytest.mark.parametrize(
    "bad", [np.inf, -np.inf, "n/a"], ids=["inf", "-inf", "non-numeric"]
)
def test_a_volume_that_is_not_a_finite_number_is_left_out(bad):
    """``inf`` would serialize as ``Infinity`` and a string would raise on ``>``."""
    frame = _frame(INDEXES["daily"])
    frame["Volume"] = frame["Volume"].astype(object)
    frame.loc[frame.index[3], "Volume"] = bad
    converter = create_datetime_converter(frame)

    labels = [label for label, _ in converter.extract_volume_data(None)]

    assert converter.get_formatted_datetime(3) not in labels
    assert len(labels) == ROWS - 3
    assert all(np.isfinite(v) for _, v in converter.extract_volume_data(None))


# Without a ``datetime_format``, a daily chart was announced as
# ``2024-01-02 00:00:00`` on every candle, volume bar and moving average: a
# time of day the data never recorded. An index with no time of day is now
# labeled by the date alone; one with any time keeps the full stamp.


def _prices(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({"Close": np.arange(len(index), dtype=float)}, index=index)


@pytest.mark.parametrize(
    "index",
    [
        pd.date_range("2024-01-01", periods=5, freq="D"),
        pd.date_range("2024-01-01", periods=5, freq="B"),
        pd.date_range("2024-01-07", periods=5, freq="W"),
        pd.date_range("2024-01-01", periods=5, freq="MS"),
        INDEXES["second resolution"][:5],
    ],
    ids=["daily", "business days", "weekly", "monthly", "second resolution"],
)
def test_an_index_of_dates_is_labeled_by_the_date_alone(index):
    converter = create_datetime_converter(_prices(index))

    assert converter.dates_only
    assert [converter.get_formatted_datetime(row) for row in range(5)] == [
        stamp.strftime("%Y-%m-%d") for stamp in index
    ]


def test_a_tz_aware_index_of_dates_drops_the_offset_with_the_time():
    # mplfinance draws the index's own wall clock, so the date is the one in
    # its zone -- not the UTC date, and with no ``-05:00`` left dangling.
    index = pd.date_range("2024-01-01", periods=5, freq="D", tz="US/Eastern")
    converter = create_datetime_converter(_prices(index))

    assert converter.get_formatted_datetime(0) == "2024-01-01"
    assert str(index[0]) == "2024-01-01 00:00:00-05:00"


def test_an_index_with_a_time_of_day_keeps_every_full_stamp():
    # Hourly bars across midnight: the midnight bar keeps its time too, so it
    # reads like its neighbours rather than as a bare date among times.
    index = pd.date_range("2024-01-01 22:00", periods=5, freq="h")
    converter = create_datetime_converter(_prices(index))

    assert not converter.dates_only
    labels = [converter.get_formatted_datetime(row) for row in range(5)]
    assert labels == [str(stamp) for stamp in index]
    assert labels[2] == "2024-01-02 00:00:00"


def test_one_stamp_with_a_time_keeps_the_full_stamps():
    index = pd.DatetimeIndex(["2024-01-01", "2024-01-02", "2024-01-03 12:00"])
    converter = create_datetime_converter(_prices(index))

    assert converter.get_formatted_datetime(0) == "2024-01-01 00:00:00"


def test_a_nat_does_not_stop_the_date_alone():
    index = _with_a_nat(pd.date_range("2024-01-01", periods=5, freq="D"), at=2)
    converter = create_datetime_converter(_prices(index))

    assert [converter.get_formatted_datetime(row) for row in range(5)] == [
        "2024-01-01",
        "2024-01-02",
        "NaT",
        "2024-01-04",
        "2024-01-05",
    ]


def test_a_format_still_wins_over_the_date_alone():
    converter = create_datetime_converter(
        _prices(pd.date_range("2024-01-01", periods=5)), datetime_format="%d %b %Y"
    )

    assert converter.get_formatted_datetime(0) == "01 Jan 2024"


# Hourly bars across a midnight the zone skips (clocks forward at 00:00) or
# repeats (clocks back into 00:00). Localizing that midnight raises, so the
# check for a time of day must not: the caller's own ``mpf.plot`` runs it.
ACROSS_A_CHANGE_AT_MIDNIGHT = {
    "nonexistent midnight": pd.date_range(
        "2018-11-03 20:00", periods=12, freq="h", tz="America/Sao_Paulo"
    ),
    "ambiguous midnight": pd.date_range(
        "2023-10-28 20:00", periods=12, freq="h", tz="Atlantic/Azores"
    ),
}


@pytest.mark.parametrize(
    "index",
    list(ACROSS_A_CHANGE_AT_MIDNIGHT.values()),
    ids=list(ACROSS_A_CHANGE_AT_MIDNIGHT),
)
def test_a_clock_change_at_midnight_keeps_the_full_stamps(index):
    converter = create_datetime_converter(_prices(index))

    assert not converter.dates_only
    assert [converter.get_formatted_datetime(row) for row in range(12)] == [
        str(stamp) for stamp in index
    ]


def test_extract_candlestick_data_leaves_out_a_volume_the_frame_lacks():
    # The same rule as the candlestick layer: no ``volume`` for a NaN, a 0
    # recorded as 0 kept, and none at all without a Volume column.
    frame = _frame(INDEXES["daily"])
    candles = create_datetime_converter(frame).extract_candlestick_data(None)

    assert "volume" not in candles[17]
    assert candles[42]["volume"] == 0.0
    assert candles[0]["volume"] == frame["Volume"].iloc[0]

    no_volume = frame.drop(columns="Volume")
    candles = create_datetime_converter(no_volume).extract_candlestick_data(None)
    assert len(candles) == ROWS
    assert not any("volume" in candle for candle in candles)
