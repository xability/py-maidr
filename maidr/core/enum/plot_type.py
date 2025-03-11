from enum import Enum


class PlotType(str, Enum):
    """An enumeration of plot types supported by MAIDR."""

    BAR = "bar"
    BOX = "box"
    COUNT = "count"
    DODGED = "dodged_bar"
    HEAT = "heat"
    HIST = "hist"
    LINE = "line"
    SCATTER = "point"
    STACKED = "stacked_bar"
