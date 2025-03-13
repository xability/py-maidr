__version__ = "0.16.1"

from .api import close, render, save_html, set_engine, show, stacked
from .core import Maidr
from .core.enum import PlotType
from .patch import (
    barplot,
    boxplot,
    clear,
    heatmap,
    highlight,
    histogram,
    lineplot,
    scatterplot,
)

__all__ = [
    "close",
    "render",
    "save_html",
    "show",
    "stacked",
]
