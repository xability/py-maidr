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


def _reference_volume(frame: pd.DataFrame) -> list[tuple[str, float]]:
    out = []
    for i in range(len(frame)):
        volume = frame.iloc[i]["Volume"]
        if pd.isna(volume) or volume <= 0:
            continue
        out.append((str(frame.index[i]), float(volume)))
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
        volume = float(row["Volume"]) if "Volume" in frame.columns else 0.0
        if not math.isfinite(volume):
            volume = 0.0
        out.append(
            {
                "value": str(frame.index[i]),
                "open": prices[0],
                "high": prices[1],
                "low": prices[2],
                "close": prices[3],
                "volume": volume,
            }
        )
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
        str(stamp) for i, stamp in enumerate(frame.index) if i not in (17, 42)
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


@pytest.mark.parametrize(
    "bad", [np.inf, -np.inf, "n/a"], ids=["inf", "-inf", "non-numeric"]
)
def test_a_volume_that_is_not_a_finite_number_is_left_out(bad):
    """``inf`` would serialise as ``Infinity`` and a string would raise on ``>``."""
    frame = _frame(INDEXES["daily"])
    frame["Volume"] = frame["Volume"].astype(object)
    frame.loc[frame.index[3], "Volume"] = bad
    converter = create_datetime_converter(frame)

    labels = [label for label, _ in converter.extract_volume_data(None)]

    assert str(frame.index[3]) not in labels
    assert len(labels) == ROWS - 3
    assert all(np.isfinite(v) for _, v in converter.extract_volume_data(None))
