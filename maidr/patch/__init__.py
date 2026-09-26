import wrapt

from ._seaborn_version import check_seaborn_version

# Every seaborn patch below is applied from a `wrapt.when_imported("seaborn")`
# hook rather than at import time, so a process that never imports seaborn
# never pays for loading it (~0.8 s of `import maidr`). The hooks fire in the
# order they are registered, immediately when seaborn is already loaded and
# at the end of `import seaborn` otherwise -- so `import seaborn; import maidr`
# and `import maidr; import seaborn` patch the same names in the same order.
#
# This one is registered first so it still runs before anything else: the
# modules below wrap seaborn internals by name, and on a seaborn too old to
# have them `wrapt` raises an AttributeError that names neither seaborn nor a
# version (#441). Raised from here, the readable ImportError comes out of
# `import maidr` when seaborn is already loaded and out of `import seaborn`
# when it is not.
wrapt.when_imported("seaborn")(lambda _seaborn: check_seaborn_version())

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
    grid_panel,
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
    roc,
    wordcloud,
)
