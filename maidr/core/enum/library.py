from enum import Enum


class Library(str, Enum):
    MATPLOTLIB = "matplotlib"
    SEABORN = "seaborn"
    ALTAIR = "altair"
