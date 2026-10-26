"""A chart drawn by ``mplfinance.original_flavor`` is read candle by candle.

``candlestick_ohlc`` and ``candlestick_ochl`` draw through ``_candlestick``,
one ``Line2D`` wick and one ``Rectangle`` body per quote. The patch handed
``CandlestickPlot`` the prices as a dict of lists, which it reads only as a
frame, and none of the artists: the layer held no candles at all. Every key on
it was silent but for the edge tones, the description reported 0 periods, and
the highlight's selector named nothing (py-example-a#5).

The quotes are now read into the frame the ``mpf.plot`` path reads, in the
order the call says they are in, and each candle names its own body and wick.
"""

from __future__ import annotations

import re

import numpy as np
import pytest

pytest.importorskip("lxml")
pytest.importorskip("mplfinance")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from lxml import etree  # noqa: E402
from lxml.cssselect import CSSSelector  # noqa: E402
from mplfinance.original_flavor import (  # noqa: E402
    candlestick_ochl,
    candlestick_ohlc,
)

import maidr  # noqa: E402
from maidr.core.enum import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402

DAYS = np.array(["2021-01-04", "2021-01-05", "2021-01-06", "2021-01-07"], "M8[D]")
OPEN = [10.0, 11.0, 12.0, 13.0]
HIGH = [12.0, 13.0, 14.0, 15.0]
LOW = [9.0, 10.0, 11.0, 12.0]
CLOSE = [11.0, 10.0, 13.0, 12.5]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _ohlc(days=DAYS) -> np.ndarray:
    return np.column_stack([mdates.date2num(days), OPEN, HIGH, LOW, CLOSE])


def _candles(draw) -> tuple:
    """Draw, render, and return the figure, axes, candlestick layer and SVG."""
    figure, ax = plt.subplots()
    draw(ax)
    html = maidr.render(figure)._repr_html_()
    svg = re.search(r"<svg.*?</svg>", html, re.S).group(0)
    root = etree.fromstring(svg.encode(), etree.XMLParser(recover=True))
    for element in root.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]
    layers = [
        plot.schema
        for plot in FigureManager.get_maidr(figure)._plots
        if plot.type == PlotType.CANDLESTICK
    ]
    assert len(layers) == 1
    return figure, ax, layers[0], root


def _prices(layer: dict) -> list[tuple]:
    keys = ("value", "open", "high", "low", "close")
    return [tuple(candle[key] for key in keys) for candle in layer["data"]]


EXPECTED = [
    (str(day), o, h, low, c)
    for day, o, h, low, c in zip(DAYS, OPEN, HIGH, LOW, CLOSE)
]


def test_candlestick_ohlc_reads_every_candle():
    _, _, layer, _ = _candles(lambda ax: candlestick_ohlc(ax, _ohlc(), width=0.6))

    assert _prices(layer) == EXPECTED


def test_a_quote_may_go_on_past_its_prices():
    # matplotlib.finance's quotes carried a volume sixth; `_candlestick`
    # reads the first five fields and so does the layer.
    quotes = np.column_stack([_ohlc(), [100, 200, 300, 400]])
    _, _, layer, _ = _candles(lambda ax: candlestick_ohlc(ax, quotes, width=0.6))

    assert _prices(layer) == EXPECTED


def test_quotes_given_as_a_generator_are_read():
    # `_candlestick` iterates the quotes as it draws; a generator read after
    # that would be spent, and the chart would get no candles.
    quotes = (tuple(quote) for quote in _ohlc())
    _, _, layer, _ = _candles(lambda ax: candlestick_ohlc(ax, quotes, width=0.6))

    assert _prices(layer) == EXPECTED


def test_candlestick_ochl_reads_its_own_column_order():
    # Each quote is (time, open, close, high, low) here; read as ohlc it
    # would announce every close as a high.
    ochl = _ohlc()[:, [0, 1, 4, 2, 3]]
    _, _, layer, _ = _candles(lambda ax: candlestick_ochl(ax, ochl, width=0.6))

    assert _prices(layer) == EXPECTED


def test_a_time_of_day_is_kept():
    stamps = DAYS.astype("M8[m]") + np.timedelta64(9 * 60 + 30, "m")
    _, _, layer, _ = _candles(
        lambda ax: candlestick_ohlc(ax, _ohlc(stamps), width=0.02)
    )

    assert layer["data"][0]["value"] == "2021-01-04 09:30:00"


def test_each_candle_names_its_own_body_and_wick():
    figure, ax, layer, root = _candles(
        lambda ax: candlestick_ohlc(ax, _ohlc(), width=0.6)
    )
    selectors = layer["selectors"]
    assert len(selectors["body"]) == len(selectors["wick"]) == len(DAYS)

    # In the SVG's points, x running right from the left edge.
    xs = ax.transData.transform(
        np.column_stack([mdates.date2num(DAYS), np.zeros(len(DAYS))])
    )[:, 0] * 72 / figure.dpi
    for kind in ("body", "wick"):
        for selector, x in zip(selectors[kind], xs):
            (path,) = CSSSelector(selector)(root)
            numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", path.get("d"))]
            drawn = numbers[0::2]
            assert min(drawn) - 0.01 <= x <= max(drawn) + 0.01, (
                f"the {kind} named for the candle at {x:.2f} is drawn at "
                f"{min(drawn):.2f}..{max(drawn):.2f}"
            )


def test_a_quote_with_no_prices_is_left_out_with_its_artists():
    # mplfinance still draws a wick and a body for the gap, so the candles
    # after it name their own artists rather than the next ones along.
    quotes = _ohlc()
    quotes[1, 1:] = np.nan
    figure, ax, layer, root = _candles(
        lambda ax: candlestick_ohlc(ax, quotes, width=0.6)
    )

    assert [candle["value"] for candle in layer["data"]] == [
        str(DAYS[0]),
        str(DAYS[2]),
        str(DAYS[3]),
    ]
    xs = ax.transData.transform(
        np.column_stack([mdates.date2num(DAYS[[0, 2, 3]]), np.zeros(3)])
    )[:, 0] * 72 / figure.dpi
    for selector, x in zip(layer["selectors"]["body"], xs):
        (path,) = CSSSelector(selector)(root)
        drawn = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", path.get("d"))][0::2]
        assert min(drawn) <= x <= max(drawn)
