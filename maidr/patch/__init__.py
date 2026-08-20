# Before anything else: the modules below wrap seaborn internals by name,
# and on a seaborn too old to have them `wrapt` raises an AttributeError
# that names neither seaborn nor a version (#441).
from ._seaborn_version import check_seaborn_version

check_seaborn_version()

# Import all patches to ensure they are applied
from . import (  # noqa: E402, F401
    areaplot,
    barplot,
    boxenplot,
    boxplot,
    clear,
    colorbar,
    errorbar,
    fillbetween,
    gantt,
    heatmap,
    hexbin,
    highlight,
    histogram,
    lineplot,
    pieplot,
    pointplot,
    scatterplot,
    regplot,
    kdeplot,
    candlestick,
    mplfinance,
    violinplot,
    seaborn_probe,
)
