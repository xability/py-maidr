"""``CandlestickPlot`` reads the frame by column, not by cell (#706).

The old loop built ``df.iloc[i]`` -- a fresh Series, with dtype upcasting --
five times for every row, which came to about 0.5 ms a candle and 39% of a
render of a decade of daily bars. Reading each column once gives the same
dictionaries, so these tests pin what the loop promised: one dict per row
with the raw ``str(index[i])`` as its value, and a row that cannot be read as
numbers skipped on its own.

A volume the frame does not record is left out of the candle rather than
reported as ``0.0``: the core reads ``volume`` as optional, showing a Volume
column only when some candle has one and an empty cell for a candle without,
so a zero there was a measurement the chart never took.
"""

from __future__ import annotations

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")

from maidr.core.enum import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
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


def _without_volume(candle: dict) -> dict:
    return {key: value for key, value in candle.items() if key != "volume"}


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


def test_no_candle_has_a_volume_when_the_frame_has_none(extract):
    # The core then adds no Volume column to the data table at all, rather
    # than a column of zeros the chart never measured.
    frame = _frame().drop(columns="Volume")

    assert extract(frame) == [_without_volume(candle) for candle in EXPECTED]


def test_a_chart_drawn_without_volume_emits_none():
    # The whole path: mplfinance draws the frame, the patch registers it, and
    # the schema maidr.js and an agent read has no volume to report.
    mpf = pytest.importorskip("mplfinance")
    fig, _ = mpf.plot(_frame().drop(columns="Volume"), type="candle", returnfig=True)
    layer = next(
        plot
        for plot in FigureManager.get_maidr(fig)._plots
        if plot.type == PlotType.CANDLESTICK
    )

    candles = layer.schema["data"]
    assert len(candles) == 5
    assert not any("volume" in candle for candle in candles)


def test_a_volume_column_of_nothing_but_nan_gives_no_volume_either(extract):
    frame = _frame(Volume=[np.nan] * 5)

    assert extract(frame) == [_without_volume(candle) for candle in EXPECTED]


def test_a_recorded_zero_volume_is_kept(extract):
    # Zero is a measurement -- nothing traded -- unlike a volume not recorded.
    frame = _frame(Volume=[10, 0, 30, 40, 50])

    assert extract(frame)[1] == dict(EXPECTED[1], volume=0.0)


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
    # in the payload stops the whole figure initializing, and no price a
    # reader could be told is lost by leaving the row out.
    frame = _frame(Low=[0, np.nan, 2, 3, 4], High=[2.5, 3.5, 4.5, np.inf, 6.5])

    assert extract(frame) == [EXPECTED[0], EXPECTED[2], EXPECTED[4]]


def test_a_non_numeric_volume_is_left_out_and_the_prices_survive(extract):
    # A stray string in Volume is no reason to lose the candle: the prices
    # are read, and the volume is left out as it would be for a NaN.
    frame = _frame(Volume=[10, "n/a", 30, 40, 50])

    candles = extract(frame)
    assert len(candles) == 5
    assert candles[1] == _without_volume(EXPECTED[1])
    assert [candles[i] for i in (0, 2, 3, 4)] == [EXPECTED[i] for i in (0, 2, 3, 4)]


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf], ids=str)
def test_a_non_finite_volume_is_left_out_of_that_candle_only(extract, bad):
    # Not 0.0, which would say nothing traded that day. The core shows the
    # Volume column for the other candles and an empty cell for this one, and
    # a bare ``Infinity`` would not survive ``JSON.parse`` anyway.
    frame = _frame(Volume=[10, 20, bad, 40, 50])

    candles = extract(frame)
    assert len(candles) == 5
    assert candles[2] == _without_volume(EXPECTED[2])
    assert [candles[i] for i in (0, 1, 3, 4)] == [EXPECTED[i] for i in (0, 1, 3, 4)]


def test_a_skipped_row_is_left_out_of_the_drawn_rows(axes):
    # The SVG keeps a body path and two wick paths for a row the loop skipped,
    # so `_get_selector` names each candle's paths by the position of its row
    # in the frame rather than by its index in the data (#749).
    plot = CandlestickPlot([axes])
    frame = _frame(Low=[0, np.nan, 2, 3, 4], High=[2.5, 3.5, 4.5, np.inf, 6.5])

    plot._extract_from_dataframe(frame)

    assert plot._drawn_rows == [0, 2, 4]
