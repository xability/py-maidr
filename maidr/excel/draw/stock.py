"""Stock charts, and the volume drawn with them.

The prices are drawn as candles where Excel draws up and down bars, and as
high-low lines with the close marked where it draws none.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.patches import Rectangle

from maidr.core.enum import PlotType
from maidr.excel.draw.common import as_floats, category_labels, name_axis
from maidr.excel.layers import each_mark, each_path, register
from maidr.excel.spec import Group


def draw_stock(ax: Axes, group: Group, volume: Group | None) -> None:
    """
    A stock chart's prices, read as candles: open-to-close bodies where Excel
    draws its up and down bars, and a high-low line with the close marked
    where it draws none. A volume drawn with it is read with each candle and
    drawn behind them.
    """
    series = group.series
    labels = category_labels(series[0].categories, unique=False)
    prices = [as_floats(s.values) for s in series]
    if len(prices) >= 4:
        opens, highs, lows, closes = prices[:4]
    else:
        opens, (highs, lows, closes) = None, prices[:3]
    volumes = as_floats(volume.series[0].values) if volume is not None else None
    rows = [
        i
        for i in range(len(labels))
        if all(np.isfinite(p[i]) for p in (highs, lows, closes))
        and (opens is None or np.isfinite(opens[i]))
    ]
    positions = np.arange(len(labels), dtype=float)

    candles = []
    for i in rows:
        candle: dict[str, Any] = {"value": labels[i]}
        if opens is not None:
            candle["open"] = float(opens[i])
        candle.update(high=float(highs[i]), low=float(lows[i]), close=float(closes[i]))
        if volumes is not None and np.isfinite(volumes[i]):
            candle["volume"] = float(volumes[i])
        candles.append(candle)

    n = len(rows)
    if group.style == "updown" and opens is not None:
        bodies = PatchCollection(
            [
                Rectangle(
                    (positions[i] - 0.3, min(opens[i], closes[i])),
                    0.6,
                    abs(closes[i] - opens[i]),
                )
                for i in rows
            ],
            facecolor=["white" if closes[i] >= opens[i] else "black" for i in rows],
            edgecolor="black",
            linewidth=0.8,
            zorder=3,
        )
        wicks = LineCollection(
            [
                [(positions[i], lows[i]), (positions[i], min(opens[i], closes[i]))]
                for i in rows
            ]
            + [
                [(positions[i], max(opens[i], closes[i])), (positions[i], highs[i])]
                for i in rows
            ],
            colors="black",
            linewidths=0.8,
            zorder=2,
        )
        ax.add_collection(wicks)
        ax.add_collection(bodies)
        wick = each_path(wicks)
        selectors: Any = {
            "body": each_mark(bodies),
            "wickLow": f"{wick}:nth-child(-n+{n})",
            "wickHigh": f"{wick}:nth-child(n+{n + 1})",
        }
    else:
        spans = LineCollection(
            [[(positions[i], lows[i]), (positions[i], highs[i])] for i in rows],
            colors="black",
            linewidths=1,
            zorder=2,
        )
        ticks = LineCollection(
            [
                [(positions[i], closes[i]), (positions[i] + 0.25, closes[i])]
                for i in rows
            ],
            colors="black",
            linewidths=1.5,
            zorder=3,
        )
        ax.add_collection(spans)
        ax.add_collection(ticks)
        span = each_path(spans)
        selectors = {
            "body": span,
            "wickLow": span,
            "wickHigh": span,
            "close": each_path(ticks),
        }
        if opens is not None:
            starts = LineCollection(
                [
                    [(positions[i] - 0.25, opens[i]), (positions[i], opens[i])]
                    for i in rows
                ],
                colors="black",
                linewidths=1.5,
                zorder=3,
            )
            ax.add_collection(starts)
            selectors["open"] = each_path(starts)
    ax.set_xticks(positions, labels)
    ax.set_xlim(-0.6, len(labels) - 0.4)
    ax.autoscale_view(scalex=False)
    register(
        ax,
        PlotType.CANDLESTICK,
        labels={"x": None, "y": None},
        data=candles,
        selectors=selectors,
        formats={"y": "y"},
    )
    if volumes is not None:
        # The volume is a layer of its own, after the candles, drawn as the
        # bars py-maidr reads: the candles list it only in their description,
        # where a reader can neither walk nor hear it.
        twin = ax.twinx()
        twin.bar(
            positions,
            volumes,
            0.6,
            color=volume.series[0].color or "#A5A5A5",
            alpha=0.5,
        )
        twin.set_ylim(0, 4 * max(np.nanmax(volumes, initial=0.0), 1.0))
        name_axis(twin.yaxis, volume.series[0].name, "Volume", True)
        name_axis(twin.xaxis, group.category_name, "Category", False)
        twin.spines["top"].set_visible(False)
        ax.set_zorder(twin.get_zorder() + 1)
        ax.patch.set_visible(False)
