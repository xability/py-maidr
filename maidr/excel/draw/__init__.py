"""Draw an Excel chart with matplotlib, so py-maidr reads it like any other.

Where matplotlib has a call for the chart -- ``bar``, ``barh``, ``plot``,
``scatter``, ``pie``, ``stackplot``, ``pcolormesh``, ``hist`` and ``bxp`` --
the figure is drawn through it, so the layers, the selectors that highlight
each mark and the announcements all come from py-maidr's own readers of those
calls. Where it has none -- a radar, a bubble chart's sizes, a stock chart's
candles, a waterfall, a funnel, a treemap, a sunburst, a map -- the marks are
drawn from plain artists and described by the layers of
:mod:`maidr.excel.layers`.

What is copied from the workbook is what a reader hears or a sighted colleague
would check against Excel: the values, the series names and colors, the
category labels as the axis writes them, the titles, the number format of the
value axis, its range, and the legend's place. Excel's fonts, effects and
exact proportions are not.

Each family of charts is drawn by a module of its own; :func:`draw_chart`
picks it, and draws what every chart has: its figure and its title.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Callable

from matplotlib.axes import Axes
from matplotlib.figure import Figure

from maidr.excel.draw.box import draw_box
from maidr.excel.draw.cartesian import (
    draw_area,
    draw_bar,
    draw_bubble,
    draw_line,
    draw_scatter,
)
from maidr.excel.draw.common import (
    NAMES,
    chart_name,
    new_figure,
    show_legend,
    style_axes,
)
from maidr.excel.draw.funnel import draw_funnel
from maidr.excel.draw.hierarchy import draw_sunburst, draw_treemap
from maidr.excel.draw.histogram import draw_histogram, draw_pareto
from maidr.excel.draw.pie import draw_of_pie, draw_pie
from maidr.excel.draw.radar import draw_radar
from maidr.excel.draw.region import draw_region
from maidr.excel.draw.stock import draw_stock
from maidr.excel.draw.surface import draw_surface
from maidr.excel.draw.waterfall import draw_waterfall
from maidr.excel.spec import ChartSpec, Group
from maidr.util.caller_warning import warn_at_caller


def draw_chart(spec: ChartSpec, *, aspect: float | None, where: str) -> Figure:
    """
    Draw a chart.

    Parameters
    ----------
    spec : ChartSpec
        The chart, as :func:`maidr.excel.chartxml.read_chart` or
        :func:`maidr.excel.chartex.read_chartex` read it, with at least one
        group.
    aspect : float or None
        The chart's height over its width on the sheet, if known.
    where : str
        How warnings name the chart, such as ``"'Chart 1' on sheet 'Sales'"``.

    Returns
    -------
    matplotlib.figure.Figure
        A figure not managed by pyplot, with its layers registered with maidr.
    """
    fig = new_figure(aspect)
    if spec.groups[0].kind in _EXCEL_2016:
        ax = _draw_excel_2016(fig, spec, where)
    else:
        ax = _draw_drawingml(fig, spec, where)
    if spec.title:
        ax.set_title(spec.title)
    fig.tight_layout()
    return fig


def _draw_drawingml(fig: Figure, spec: ChartSpec, where: str) -> Axes:
    """
    A chart of a DrawingML part: its groups on shared axes, or the one that
    takes the whole figure.
    """
    groups = list(spec.groups)
    whole = next((g for g in groups if g.kind in _WHOLE), None)
    stock = next((g for g in groups if g.kind == "stock"), None)
    if stock is not None and len(stock.series) < 3:
        # A stock chart needs a high, a low and a close; with fewer it is
        # read as the lines its series are.
        groups = [replace(g, kind="line") if g is stock else g for g in groups]
        stock = None
    volume = None
    if stock is not None:
        # A stock chart's volume is a column group drawn with it.
        volume = next((g for g in groups if g.kind == "bar"), None)
    drawn = whole or stock
    if drawn is not None:
        left_out = [g for g in groups if g is not drawn and g is not volume]
        if left_out:
            warn_at_caller(
                f"maidr reads only the {chart_name(drawn)} of the chart {where}; "
                "the chart types drawn with it are left out."
            )
    if whole is not None:
        return _WHOLE[whole.kind](fig, whole, spec, where)
    ax = fig.add_subplot()
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    twin = None
    if stock is not None:
        draw_stock(ax, stock, volume)
        style_axes(ax, stock, spec)
        groups = []
    for group in groups:
        target = ax
        if group.secondary:
            if twin is None:
                twin = ax.twiny() if group.horizontal else ax.twinx()
                for side in ("bottom", "left") if group.horizontal else ("top",):
                    twin.spines[side].set_visible(False)
            target = twin
        _SHARED[group.kind](target, group)
        style_axes(target, group, spec)
    if spec.legend is not None:
        show_legend(ax, twin, spec.legend)
    return ax


def _draw_excel_2016(fig: Figure, spec: ChartSpec, where: str) -> Axes:
    """A chart of an Excel 2016 part, which holds one group."""
    group = spec.groups[0]
    if group.kind not in ("box", "pareto") and len(group.series) > 1:
        warn_at_caller(
            f"maidr reads the first series of the {NAMES[group.kind]} chart "
            f"{where}; the other {len(group.series) - 1} are left out."
        )
    return _EXCEL_2016[group.kind](fig, group, spec, where)


#: Kinds drawn on shared axes, any of them with the others.
_SHARED: dict[str, Callable[[Axes, Group], None]] = {
    "bar": draw_bar,
    "line": draw_line,
    "area": draw_area,
    "scatter": draw_scatter,
    "bubble": draw_bubble,
}

#: Kinds that take the whole figure, drawn without any other.
_WHOLE: dict[str, Callable[[Figure, Group, ChartSpec, str], Axes]] = {
    "pie": draw_pie,
    "doughnut": draw_pie,
    "ofpie": draw_of_pie,
    "radar": draw_radar,
    "surface": draw_surface,
}

#: The kinds of an Excel 2016 part, each drawn alone.
_EXCEL_2016: dict[str, Callable[[Figure, Group, ChartSpec, str], Axes]] = {
    "histogram": draw_histogram,
    "pareto": draw_pareto,
    "box": draw_box,
    "waterfall": draw_waterfall,
    "funnel": draw_funnel,
    "treemap": draw_treemap,
    "sunburst": draw_sunburst,
    "region": draw_region,
}
