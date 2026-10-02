"""An mplfinance chart announces its dates as its x axis draws them (#233).

``mpf.plot(..., datetime_format=...)`` sets the strftime format of the tick
labels, and the patch never passed it on: every candle, volume bar and moving
average was announced as the full ``str()`` of its stamp, so a chart of
minute bars drawn as ``09:30`` was read out as ``2026-03-02 09:30:00``.

The labels are compared with the tick formatter mplfinance installed, called
at each row's position, rather than with a strftime written out here: that
formatter *is* the drawn label, so the tests say "the reader hears the tick"
and not merely "the reader hears some formatting".
"""

from __future__ import annotations

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

import maidr  # noqa: E402,F401
from maidr.core.enum import PlotType  # noqa: E402
from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.util.datetime_conversion import DatetimeConverter  # noqa: E402

mpf = pytest.importorskip("mplfinance")

ROWS = 8


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _prices(index: pd.DatetimeIndex) -> pd.DataFrame:
    base = np.arange(len(index), dtype=float)
    return pd.DataFrame(
        {
            "Open": base + 1,
            "High": base + 3,
            "Low": base,
            "Close": base + 2,
            "Volume": (base + 1) * 10,
        },
        index=index,
    )


def _layer(fig, plot_type: PlotType):
    return next(p for p in FigureManager.get_maidr(fig)._plots if p.type == plot_type)


def _read(frame: pd.DataFrame, **kwargs) -> tuple[list[str], dict[str, list]]:
    """Draw the chart; return its tick label per row and what each layer says."""
    fig, axes = mpf.plot(
        frame, type="candle", volume=True, mav=3, returnfig=True, **kwargs
    )
    tick = axes[0].xaxis.get_major_formatter()
    drawn = [tick(row) for row in range(len(frame))]

    (moving_average,) = _layer(fig, PlotType.LINE).schema[MaidrKey.DATA]
    announced = {
        "candles": [
            candle["value"]
            for candle in _layer(fig, PlotType.CANDLESTICK).schema[MaidrKey.DATA]
        ],
        "volume": [
            bar[MaidrKey.X] for bar in _layer(fig, PlotType.BAR).schema[MaidrKey.DATA]
        ],
        "moving average": [point[MaidrKey.X] for point in moving_average],
    }
    return drawn, announced


CASES = {
    "daily with the year": (pd.date_range("2025-12-29", periods=ROWS), "%b %d, %Y"),
    # The issue's other ask: a format without the year, for recent candles.
    "daily without the year": (pd.date_range("2026-03-02", periods=ROWS), "%a %d %b"),
    "minute bars": (
        pd.date_range("2026-03-02 09:30", periods=ROWS, freq="min"),
        "%H:%M",
    ),
    # mplfinance drops the zone before drawing (``tz_localize=True``), so the
    # tick shows the index's own wall-clock time -- not the UTC one.
    "tz-aware minute bars": (
        pd.date_range("2026-03-02 09:30", periods=ROWS, freq="min", tz="US/Eastern"),
        "%H:%M",
    ),
}


@pytest.mark.parametrize(("index", "fmt"), list(CASES.values()), ids=list(CASES))
def test_every_layer_announces_the_date_the_tick_draws(index, fmt):
    drawn, announced = _read(_prices(index), datetime_format=fmt)

    assert drawn[0] == index[0].strftime(fmt)
    assert announced["candles"] == drawn
    assert announced["volume"] == drawn
    # A three-row average starts on the third row.
    assert announced["moving average"] == drawn[2:]


def test_without_a_format_the_labels_are_the_raw_stamps():
    # Intraday bars drawn without ``datetime_format`` keep the full stamp:
    # mplfinance chooses its tick format by the span of the data, and that
    # choice is not passed on.
    index = pd.date_range("2026-03-02 09:30", periods=ROWS, freq="min")
    drawn, announced = _read(_prices(index))

    raw = [str(stamp) for stamp in index]
    assert drawn[0] == "09:30"
    assert announced["candles"] == raw
    assert announced["volume"] == raw
    assert announced["moving average"] == raw[2:]


DATES_ONLY = {
    "daily": pd.date_range("2026-03-02", periods=ROWS, freq="B"),
    "tz-aware daily": pd.date_range(
        "2026-03-02", periods=ROWS, freq="B", tz="US/Eastern"
    ),
}


@pytest.mark.parametrize("index", list(DATES_ONLY.values()), ids=list(DATES_ONLY))
def test_without_a_format_a_daily_chart_reads_the_date_alone(index):
    # ``str()`` of a daily stamp is ``2026-03-02 00:00:00`` -- a midnight the
    # data never recorded, which every candle, volume bar and moving average
    # announced. An index with no time of day reads as the date it holds.
    _, announced = _read(_prices(index))

    dates = [stamp.strftime("%Y-%m-%d") for stamp in index]
    assert dates[0] == "2026-03-02"
    assert announced["candles"] == dates
    assert announced["volume"] == dates
    assert announced["moving average"] == dates[2:]


def test_a_nat_keeps_its_label_under_a_format():
    # ``NaT.strftime`` raises; the stamp keeps the "NaT" it had without one.
    index = pd.DatetimeIndex(["2026-03-02", None, "2026-03-04"])
    converter = DatetimeConverter(_prices(index), datetime_format="%d %b")

    assert [converter.get_formatted_datetime(row) for row in range(3)] == [
        "02 Mar",
        "NaT",
        "04 Mar",
    ]
