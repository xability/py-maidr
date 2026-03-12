__version__ = "1.11.0"

from .api import close, render, save_html, show, stacked
from .core import Maidr  # noqa: F401
from .core.enum import PlotType  # noqa: F401
from .patch import (  # noqa: F401
    barplot,
    boxplot,
    clear,
    heatmap,
    highlight,
    histogram,
    lineplot,
    scatterplot,
    regplot,
    kdeplot,
    candlestick,
    mplfinance,
)

__all__ = [
    "close",
    "render",
    "save_html",
    "show",
    "stacked",
]
