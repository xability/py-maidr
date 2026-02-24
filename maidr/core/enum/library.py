from enum import Enum


class Library(str, Enum):
    MATPLOTLIB = "matplotlib"
    SEABORN = "seaborn"
    PLOTLY = "plotly"
