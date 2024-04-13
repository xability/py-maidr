# __version__ will be automatically updated by python-semantic-release
__version__ = "0.0.1"

from .core import Maidr
from .core.enum import PlotType
from .maidr import bar, box, count, heat, hist, line, scatter, stacked

__all__ = [
    "bar",
    "box",
    "count",
    "heat",
    "hist",
    "line",
    "scatter",
    "stacked",
]
