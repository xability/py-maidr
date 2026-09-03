"""``CandlestickPlot`` reads the frame by column, not by cell (#706).

The old loop built ``df.iloc[i]`` -- a fresh Series, with dtype upcasting --
five times for every row, which came to about 0.5 ms a candle and 39% of a
render of a decade of daily bars. Reading each column once gives the same
dictionaries, so these tests pin what the loop promised: one dict per row
with the raw ``str(index[i])`` as its value, ``0.0`` for a volume the frame
does not carry, and a row that cannot be read as numbers skipped on its own.
"""

from __future__ import annotations

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")

from maidr.core.plot.candlestick import CandlestickPlot  # noqa: E402


@pytest.fixture
def extract(axes):
    return CandlestickPlot([axes])._extract_from_dataframe


def _frame(**overrides) -> pd.DataFrame:
    columns = {
        "Open": [1, 2, 3, 4, 5],
        "High": [2.5, 3.5, 4.5, 5.5, 6.5],
        "Low": [0, 1, 2, 3, 4],
        "Close": [1.5, 2.5, 3.5, 4.5, 5.5],
        "Volume": [10, 20, 30, 40, 50],
    }
    columns.update(overrides)
    return pd.DataFrame(columns, index=pd.date_range("2026-01-05", periods=5))


def _candle(date, open_, high, low, close, volume) -> dict:
    return {
        "value": str(date),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


EXPECTED = [
    _candle(pd.Timestamp("2026-01-05"), 1.0, 2.5, 0.0, 1.5, 10.0),
    _candle(pd.Timestamp("2026-01-06"), 2.0, 3.5, 1.0, 2.5, 20.0),
    _candle(pd.Timestamp("2026-01-07"), 3.0, 4.5, 2.0, 3.5, 30.0),
    _candle(pd.Timestamp("2026-01-08"), 4.0, 5.5, 3.0, 4.5, 40.0),
    _candle(pd.Timestamp("2026-01-09"), 5.0, 6.5, 4.0, 5.5, 50.0),
]


def test_a_frame_with_volume_gives_one_dict_per_row(extract):
    assert extract(_frame()) == EXPECTED


def test_every_value_is_a_python_float(extract):
    # Integer columns must not leak numpy scalars into the JSON payload.
    # ``isinstance`` cannot say so: ``np.float64`` is a subclass of ``float``.
    for candle in extract(_frame()):
        for key in ("open", "high", "low", "close", "volume"):
            assert type(candle[key]) is float  # noqa: E721


def test_volume_is_zero_when_the_frame_has_none(extract):
    frame = _frame().drop(columns="Volume")

    assert extract(frame) == [dict(candle, volume=0.0) for candle in EXPECTED]


def test_the_date_is_the_raw_index_string(extract):
    # Whatever the index holds is reported as ``str(index[i])`` -- a tz-aware
    # stamp keeps its offset, an integer index its integers.
    frame = _frame().tz_localize("US/Eastern")

    values = [candle["value"] for candle in extract(frame)]
    assert values == [str(frame.index[i]) for i in range(len(frame))]
    assert values[0] == "2026-01-05 00:00:00-05:00"


def test_a_non_numeric_close_skips_that_row_only(extract):
    frame = _frame(Close=[1.5, "n/a", 3.5, 4.5, 5.5])

    assert extract(frame) == [EXPECTED[0]] + EXPECTED[2:]


def test_a_missing_price_column_gives_nothing(extract):
    assert extract(_frame().drop(columns="Close")) == []


def test_a_non_finite_price_skips_the_row(extract):
    # The rule `test_non_finite_coordinates.py` states: a bare NaN or Infinity
    # in the payload stops the whole figure initialising, and no price a
    # reader could be told is lost by leaving the row out.
    frame = _frame(Low=[0, np.nan, 2, 3, 4], High=[2.5, 3.5, 4.5, np.inf, 6.5])

    assert extract(frame) == [EXPECTED[0], EXPECTED[2], EXPECTED[4]]


def test_a_non_numeric_volume_is_zero_and_the_prices_survive(extract):
    # A stray string in Volume is no reason to lose the candle: the prices
    # are read, and the volume is reported as it would be for a NaN.
    frame = _frame(Volume=[10, "n/a", 30, 40, 50])

    candles = extract(frame)
    assert len(candles) == 5
    assert candles[1] == dict(EXPECTED[1], volume=0.0)
    assert [candles[i] for i in (0, 2, 3, 4)] == [EXPECTED[i] for i in (0, 2, 3, 4)]


def test_a_non_finite_volume_is_reported_as_zero(extract):
    # The same value the frame gets when it carries no Volume at all.
    frame = _frame(Volume=[10, 20, np.nan, 40, 50])

    candles = extract(frame)
    assert len(candles) == 5
    assert candles[2] == dict(EXPECTED[2], volume=0.0)
