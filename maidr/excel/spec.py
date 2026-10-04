"""What maidr needs to draw a chart, whichever kind of part it was read from.

The DrawingML reader (:mod:`maidr.excel.chartxml`) and the Excel 2016 one
(:mod:`maidr.excel.chartex`) both read a chart into a :class:`ChartSpec`,
which the drawing (:mod:`maidr.excel.draw`) takes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Axis:
    """One axis of a chart group, as drawn and as announced."""

    #: The title Excel draws on the axis, or ``None`` when it draws none.
    title: str | None
    #: What the reader hears the axis called: the title, or a name found for
    #: an untitled axis.
    label: str | None
    hidden: bool
    position: str
    minimum: float | None
    maximum: float | None
    reversed: bool
    #: The number format of the axis labels, as an Excel format code.
    number_format: str | None


@dataclass(frozen=True)
class Series:
    """One series: its name, its points and how it is drawn."""

    name: str | None
    #: Category labels, or the x values of a scatter or bubble series.
    categories: tuple[Any, ...]
    values: tuple[float | None, ...]
    color: str | None
    #: Per-point colors -- a pie's slices -- as ``(index, "#RRGGBB")`` pairs.
    point_colors: tuple[tuple[int, str], ...]
    line: bool
    marker: bool
    #: The size of each bubble of a bubble series.
    sizes: tuple[float | None, ...] = ()
    #: Each point's category as the levels of a hierarchy, outermost first:
    #: a treemap's or a sunburst's branches.
    paths: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class Binning:
    """How a histogram groups its values into bins, as Excel was told to."""

    #: The width of a bin, or ``None`` to work it out.
    size: float | None = None
    #: How many bins, or ``None`` to work it out.
    count: int | None = None
    #: Values at or below this go to one bin of their own.
    underflow: float | None = None
    #: Values above this go to one bin of their own.
    overflow: float | None = None
    #: Which end of a bin it includes: ``"r"``, as ``(a, b]``, or ``"l"``.
    closed: str = "r"
    #: Whether each category is a bin of its own, its values summed.
    by_category: bool = False


def sums_categories(binning: Binning | None, series: Series) -> bool:
    """
    Whether a histogram or a Pareto chart makes each category a bin of its
    own, its values summed.

    Parameters
    ----------
    binning : Binning or None
        What the chart says of its bins, or ``None`` when it says nothing.
    series : Series
        The series binned.

    Returns
    -------
    bool
        What the chart says, or, when it says nothing, whether it has
        categories, as Excel decides for text ones.
    """
    if binning is not None:
        return binning.by_category
    return any(c is not None for c in series.categories)


@dataclass(frozen=True)
class Group:
    """One chart group: series of one chart type that share axes."""

    #: ``"bar"``, ``"line"``, ``"pie"``, ``"doughnut"``, ``"ofpie"``,
    #: ``"scatter"``, ``"bubble"``, ``"area"``, ``"radar"``, ``"stock"`` or
    #: ``"surface"``; or one of the Excel 2016 types, ``"histogram"``,
    #: ``"pareto"``, ``"box"``, ``"waterfall"``, ``"funnel"``, ``"treemap"``,
    #: ``"sunburst"`` or ``"region"``.
    kind: str
    horizontal: bool
    #: ``"standard"``, ``"clustered"``, ``"stacked"`` or ``"percentStacked"``.
    grouping: str
    series: tuple[Series, ...]
    #: The category axis, or the x axis of a scatter group.
    x_axis: Axis | None
    #: The value axis, or the y axis of a scatter group.
    y_axis: Axis | None
    #: What the categories are called: the category axis' title, or the
    #: header above their range, which also names a pie's slices.
    category_name: str | None
    secondary: bool
    first_slice_angle: float
    hole_size: float | None
    #: How a radar is drawn (``"standard"``, ``"marker"`` or ``"filled"``),
    #: what a pie-of-pie's second plot is (``"pie"`` or ``"bar"``), and
    #: whether a stock chart draws its open-to-close bodies (``"updown"``).
    style: str | None = None
    #: The points a pie-of-pie draws in its second plot, by index.
    second_plot: tuple[int, ...] = ()
    #: How large a bubble chart draws its bubbles, in percent of the default.
    bubble_scale: float = 100.0
    #: What the series of a surface are called: the title of its depth axis.
    series_name: str | None = None
    #: What a bubble chart's sizes are: the header above their range.
    size_name: str | None = None
    #: How a histogram or a Pareto chart bins its values.
    binning: Binning | None = None
    #: How a box and whisker chart finds its quartiles: ``"exclusive"`` or
    #: ``"inclusive"`` of the median.
    quartiles: str = "exclusive"
    #: Whether a box and whisker chart marks each box's mean.
    mean_marker: bool = True
    #: The points of a waterfall that are totals rather than steps, by index.
    totals: tuple[int, ...] = ()


@dataclass(frozen=True)
class ChartSpec:
    """Everything maidr needs from one chart part to draw it."""

    title: str | None
    groups: tuple[Group, ...]
    #: Where the legend sits (``"r"``, ``"b"``, ``"t"``, ``"l"``, ``"tr"``),
    #: or ``None`` when the chart has no legend.
    legend: str | None
    #: The chart types in the part that maidr does not read, by name.
    unread: tuple[str, ...]
