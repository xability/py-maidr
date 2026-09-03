"""The mplfinance patch converts the whole index to date numbers at once
(#706).

``mdates.date2num`` accepts an index and returns the same float64 values as
a call per element, at about 60 us a row less. The values are what the
volume bars and moving averages are labelled from, so the two spellings are
asserted equal here for a naive and a tz-aware index.
"""

from __future__ import annotations

import matplotlib
import pytest

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

import maidr  # noqa: E402,F401
from maidr.core.enum import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402

mpf = pytest.importorskip("mplfinance")


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


INDEXES = {
    "naive": pd.date_range("2026-01-01", periods=5),
    "tz-aware": pd.date_range("2026-01-01", periods=5, tz="US/Eastern"),
}


def _prices(index: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [1, 2, 3, 4, 5],
            "High": [2, 3, 4, 5, 6],
            "Low": [0, 1, 2, 3, 4],
            "Close": [1.5, 2.5, 3.5, 4.5, 5.5],
            "Volume": [10, 20, 30, 40, 50],
        },
        index=index,
    )


def _layer(fig, plot_type: PlotType):
    return next(p for p in FigureManager.get_maidr(fig)._plots if p.type == plot_type)


@pytest.mark.parametrize("index", list(INDEXES.values()), ids=list(INDEXES))
def test_the_date_numbers_match_a_call_per_element(index):
    frame = _prices(index)
    fig, _ = mpf.plot(frame, type="candle", volume=True, mav=3, returnfig=True)

    # The one list the patch builds is handed to the volume layer and set on
    # every moving-average line; the candlestick layer does not keep it.
    date_nums = _layer(fig, PlotType.BAR)._maidr_date_nums
    assert date_nums == [mdates.date2num(stamp) for stamp in frame.index]
    assert date_nums == list(mdates.date2num(frame.index))
    for line in _layer(fig, PlotType.LINE).ax.get_lines():
        assert line._maidr_date_nums == date_nums


def test_the_candlestick_still_registers():
    fig, _ = mpf.plot(_prices(INDEXES["naive"]), type="candle", returnfig=True)

    assert _layer(fig, PlotType.CANDLESTICK).schema["data"]
