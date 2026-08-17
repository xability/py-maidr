"""
An mplfinance chart keeps the title its caller gave it (#464).

``CandlestickPlot``, ``MplfinanceBarPlot`` and ``MplfinanceLinePlot`` each
overwrote whatever title the layer had with a fixed description of the chart
type, so a caller naming their chart on the axes lost that name.

It matters more than it did. #453 names the iframe every chart renders into
after the chart's own title, so the fixed string became the chart's
*accessible name* as well as its announced title -- and three candlesticks on
one page were announced identically, which is the failure #453 was filed
about, reappearing for these plot types by another route.

``mpf.plot(title=...)`` was never affected: it sets the figure suptitle, which
lands in the figure-level title and was never the thing being overwritten.
Both spellings are covered here, since the point is that they now agree.
"""

from __future__ import annotations

import matplotlib
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

import maidr  # noqa: E402,F401
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.util.iframe_utils import chart_title_of, iframe_title  # noqa: E402

mpf = pytest.importorskip("mplfinance")


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _prices() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=5)
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


def _layer_titles(fig) -> list[str]:
    schema = FigureManager.figs[fig]._flatten_maidr()
    return [
        layer.get("title", "")
        for row in schema.get("subplots", [])
        for panel in row
        for layer in panel.get("layers", [])
    ]


def _schema(fig) -> dict:
    return FigureManager.figs[fig]._flatten_maidr()


class TestTheCallersTitleSurvives:
    def test_an_axes_title_is_kept(self) -> None:
        fig, axlist = mpf.plot(_prices(), type="candle", returnfig=True)
        axlist[0].set_title("AAPL 2026 Q1")

        # Before the fix every one of these read "Candlestick Chart".
        assert "AAPL 2026 Q1" in _layer_titles(fig)

    def test_the_frame_is_named_after_the_chart(self) -> None:
        fig, axlist = mpf.plot(_prices(), type="candle", returnfig=True)
        axlist[0].set_title("AAPL 2026 Q1")

        assert (
            iframe_title(chart_title_of(_schema(fig)))
            == "AAPL 2026 Q1, accessible chart"
        )

    def test_two_charts_are_told_apart(self) -> None:
        # The property the fix exists for: distinct names, not one shared one.
        names = []
        for symbol in ("AAPL", "MSFT"):
            plt.close("all")
            fig, axlist = mpf.plot(_prices(), type="candle", returnfig=True)
            axlist[0].set_title(f"{symbol} 2026 Q1")
            names.append(iframe_title(chart_title_of(_schema(fig))))

        assert names[0] != names[1]

    def test_a_volume_panel_keeps_its_axes_title(self) -> None:
        fig, axlist = mpf.plot(
            _prices(), type="candle", volume=True, returnfig=True
        )
        # `axlist` is [price, price twin, volume, volume twin], so the volume
        # panel is index 2 -- the second *panel*, not the second element.
        # Measured rather than assumed: the twins carry an empty ylabel and
        # the panels carry 'Price' and 'Volume'.
        axlist[2].set_title("Traded volume")

        assert "Traded volume" in _layer_titles(fig)

    def test_a_moving_average_keeps_its_axes_title(self) -> None:
        fig, axlist = mpf.plot(_prices(), type="candle", mav=2, returnfig=True)
        axlist[0].set_title("AAPL with 2-day MA")

        titles = _layer_titles(fig)
        assert "AAPL with 2-day MA" in titles
        # Both layers on that axes take the axes' title, so neither is left
        # announcing the fixed string beside a named sibling.
        assert "Moving Average Line Plot" not in titles


class TestTheDescriptiveLabelIsStillTheFallback:
    def test_an_untitled_candlestick_says_what_it_is(self) -> None:
        fig, _ = mpf.plot(_prices(), type="candle", returnfig=True)

        # Better than the empty string the base render leaves: a reader given
        # no name still learns what kind of chart they are on.
        assert "Candlestick Chart" in _layer_titles(fig)

    def test_an_untitled_volume_panel_says_what_it_is(self) -> None:
        fig, _ = mpf.plot(_prices(), type="candle", volume=True, returnfig=True)

        assert "Volume Bar Plot" in _layer_titles(fig)

    def test_an_untitled_moving_average_says_what_it_is(self) -> None:
        fig, _ = mpf.plot(_prices(), type="candle", mav=2, returnfig=True)

        assert "Moving Average Line Plot" in _layer_titles(fig)

    def test_a_whitespace_title_counts_as_absent(self) -> None:
        fig, axlist = mpf.plot(_prices(), type="candle", returnfig=True)
        axlist[0].set_title("   ")

        # Otherwise the chart would be announced as a run of spaces, and the
        # frame named "   , accessible chart".
        assert "Candlestick Chart" in _layer_titles(fig)


class TestTheFigureLevelSpellingIsUnchanged:
    def test_the_mplfinance_title_argument_still_works(self) -> None:
        fig, _ = mpf.plot(
            _prices(), type="candle", returnfig=True, title="AAPL 2026 Q1"
        )

        # This sets the suptitle, which was never overwritten -- covered so
        # the two spellings are pinned as agreeing rather than assumed to.
        assert chart_title_of(_schema(fig)) == "AAPL 2026 Q1"
