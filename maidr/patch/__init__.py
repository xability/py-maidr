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
    contour,
    correlogram,
    errorbar,
    eventplot,
    fillbetween,
    gantt,
    heatmap,
    hexbin,
    highlight,
    histogram,
    lineplot,
    stem,
    stripplot,
    pieplot,
    pointplot,
    scatterplot,
    triplot,
    spanplot,
    stairs,
    regplot,
    rugplot,
    kdeplot,
    candlestick,
    mplfinance,
    violinplot,
    seaborn_objects,
    seaborn_probe,
)
