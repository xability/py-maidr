"""
A plain ``mpf.plot(df)`` still displays, and still returns nothing (#717).

``mplfinance.plot`` only hands back its figure under ``returnfig=True``, so
the patch forces that mode to register the layers. But mplfinance runs its
own ``plt.show()`` and ``closefig`` handling only when ``returnfig`` is
*false*, so forcing it skipped both: a caller writing the plain call from
the mplfinance docs -- and from #199, the issue this patch was written for
-- got no window, no inline render, no accessible HTML, and ``None`` where
they were not expecting a handle anyway. With the maidr backend active,
``plt.show()`` *is* the accessible renderer, so the plain call lost exactly
the output the patch exists to produce.

The patch now replays mplfinance's tail after registering: show unless
``savefig`` was given, close on the same ``closefig``/``block`` conditions,
and return ``None``. The close is deferred until after the show, because the
maidr backend renders only figures that are still open.

Measured before the fix, with ``plt.show`` stubbed: the patched call made 0
show calls, returned ``None`` and left the figure open; the unpatched
``mpf.plot.__wrapped__`` made 1 call with ``block=None``.
"""

from __future__ import annotations

import json

import matplotlib
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib._pylab_helpers import Gcf  # noqa: E402

import maidr  # noqa: E402,F401
from maidr.core.figure_manager import FigureManager  # noqa: E402

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


def _open_figures() -> list:
    return [manager.canvas.figure for manager in Gcf.get_all_fig_managers()]


@pytest.fixture
def show_calls(monkeypatch) -> list[dict]:
    """
    Stub ``plt.show`` and record each call.

    Every record carries the kwargs the call was made with plus, under
    ``"open"``, the figures that were still open at that moment -- the ones
    the maidr backend would actually render.
    """
    calls: list[dict] = []

    def record(*args, **kwargs) -> None:
        calls.append(dict(kwargs, open=_open_figures()))

    monkeypatch.setattr(plt, "show", record)
    return calls


class TestThePlainCallIsShown:
    def test_it_shows_once_and_returns_nothing(self, show_calls) -> None:
        result = mpf.plot(_prices(), type="candle")

        assert result is None
        assert len(show_calls) == 1
        # ``block`` is forwarded as mplfinance forwards it, default included.
        assert show_calls[0]["block"] is None

    def test_the_figure_it_shows_is_registered(self, show_calls) -> None:
        # The property the fix exists for: what reaches the renderer is a
        # figure maidr knows about, so the plain call yields accessible HTML.
        mpf.plot(_prices(), type="candle", volume=True, mav=2)

        (shown,) = show_calls[0]["open"]
        assert shown in FigureManager.figs

    def test_block_is_forwarded(self, show_calls) -> None:
        mpf.plot(_prices(), type="candle", block=False)

        assert [call["block"] for call in show_calls] == [False]

    def test_the_figure_is_left_open_by_default(self, show_calls) -> None:
        # mplfinance's default ``closefig='auto'`` closes after a show only
        # when ``block`` is set, so the plain call leaves the figure up.
        mpf.plot(_prices(), type="candle")

        assert _open_figures() == show_calls[0]["open"]


class TestItIsNotShownTwice:
    def test_returnfig_shows_nothing_and_returns_the_tuple(self, show_calls) -> None:
        result = mpf.plot(_prices(), type="candle", returnfig=True)

        assert show_calls == []
        fig, axlist = result
        assert fig in FigureManager.figs
        assert isinstance(axlist, list)

    def test_savefig_shows_nothing(self, show_calls, tmp_path) -> None:
        target = tmp_path / "candle.png"

        result = mpf.plot(_prices(), type="candle", savefig=str(target))

        assert show_calls == []
        assert result is None
        assert target.exists()


class TestCloseFigIsHonoured:
    def test_closefig_closes_after_the_show_not_before(self, show_calls) -> None:
        mpf.plot(_prices(), type="candle", closefig=True)

        # Under the forced ``returnfig`` mplfinance closed the figure itself,
        # before anything could show it; the backend then had nothing to
        # render. The figure must be open when shown and closed afterwards.
        assert len(show_calls[0]["open"]) == 1
        assert _open_figures() == []

    def test_block_with_the_default_closefig_closes_after_the_show(
        self, show_calls
    ) -> None:
        mpf.plot(_prices(), type="candle", block=True)

        assert len(show_calls[0]["open"]) == 1
        assert _open_figures() == []

    def test_closefig_false_keeps_the_figure_after_a_blocking_show(
        self, show_calls
    ) -> None:
        mpf.plot(_prices(), type="candle", block=True, closefig=False)

        assert len(_open_figures()) == 1

    def test_savefig_closes_by_default(self, show_calls, tmp_path) -> None:
        mpf.plot(_prices(), type="candle", savefig=str(tmp_path / "c.png"))

        assert _open_figures() == []

    def test_savefig_with_closefig_false_keeps_the_figure(
        self, show_calls, tmp_path
    ) -> None:
        mpf.plot(
            _prices(), type="candle", savefig=str(tmp_path / "c.png"), closefig=False
        )

        assert len(_open_figures()) == 1


def _price_line_labels(axlist) -> list[str]:
    return [str(line.get_label()) for line in axlist[0].get_lines()]


def _schema_text(fig) -> str:
    return json.dumps(FigureManager.figs[fig]._flatten_maidr())


class TestACallersLineLabelIsKept:
    """
    An addplot line named by the caller keeps that name (#717).

    Every ``Line2D`` on the price axes went through the moving-average
    relabelling, so ``label='Upper band'`` came out as ``'Upper band_MA1'``:
    that was the series name in the schema and the entry in any later
    ``ax.legend()``, while mplfinance's own legend still read ``'Upper
    band'``. The period was already stored on the line for
    ``MplfinanceLinePlot`` to read, so the suffix carried nothing.
    """

    def _plot(self):
        prices = _prices()
        band = mpf.make_addplot(prices["Close"] * 1.01, label="Upper band")
        return mpf.plot(prices, type="candle", mav=2, addplot=band, returnfig=True)

    def test_the_label_on_the_line_is_unchanged(self) -> None:
        _, axlist = self._plot()

        labels = _price_line_labels(axlist)
        assert "Upper band" in labels
        assert not any("_MA" in label for label in labels)

    def test_the_schema_names_the_series_after_it(self) -> None:
        fig, _ = self._plot()

        text = _schema_text(fig)
        assert "Upper band" in text
        assert "Upper band_MA" not in text

    def test_an_unlabelled_moving_average_is_still_named(self) -> None:
        # The other half of the relabelling is what the schema already calls
        # these series, and stays.
        fig, axlist = self._plot()

        assert "Moving Average 2 days" in _price_line_labels(axlist)
        assert "Moving Average 2 days" in _schema_text(fig)
