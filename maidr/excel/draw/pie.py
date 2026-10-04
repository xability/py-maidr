"""Pie, doughnut, pie-of-pie and bar-of-pie charts."""

from __future__ import annotations

from matplotlib.axes import Axes
from matplotlib.figure import Figure

from maidr.excel.draw.common import (
    category_labels,
    chart_name,
    name_axis,
    value_name,
)
from maidr.excel.spec import ChartSpec, Group
from maidr.util.caller_warning import warn_at_caller

#: What a pie-of-pie calls the slice that gathers its second plot.
_OTHER = "Other"
_OTHER_COLOR = "#A5A5A5"


def _pie(ax: Axes, group: Group, where: str) -> None:
    s = group.series[0]
    if len(group.series) > 1:
        what = "ring" if group.kind == "doughnut" else "series"
        warn_at_caller(
            f"maidr reads the first {what} of the {group.kind} chart {where}; "
            f"the other {len(group.series) - 1} are left out."
        )
    colors = dict(s.point_colors)
    labels, values, fills = [], [], []
    negative = 0
    for index, (label, value) in enumerate(
        zip(category_labels(s.categories, unique=False), s.values)
    ):
        if value is None or value == 0:
            continue
        if value < 0:
            negative += 1
            continue
        labels.append(label)
        values.append(value)
        fills.append(colors.get(index) or s.color)
    if negative:
        warn_at_caller(
            f"maidr leaves {negative} negative value(s) out of the {group.kind} "
            f"chart {where}: a slice has no negative size."
        )
    if not values:
        return
    ax.pie(
        values,
        labels=labels,
        colors=fills if all(fills) else None,
        startangle=90 - group.first_slice_angle,
        counterclock=False,
        wedgeprops={"width": 1 - (group.hole_size or 50) / 100}
        if group.kind == "doughnut"
        else None,
    )


def draw_pie(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """A pie, or a doughnut's first ring, alone on the figure."""
    ax = fig.add_subplot()
    _pie(ax, group, where)
    name_axis(ax.xaxis, group.category_name, "Category", False)
    name_axis(ax.yaxis, value_name(spec, group), "Value", False)
    return ax


def draw_of_pie(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """
    A pie-of-pie or bar-of-pie: the first pie, with the points of the second
    plot gathered into one slice, ``Other``, and the second plot beside it,
    which spells that slice out.

    Each is a subplot of its own, so the reader reaches the second from the
    first as they would the next panel of any figure.
    """
    s = group.series[0]
    if len(group.series) > 1:
        warn_at_caller(
            f"maidr reads the first series of the {chart_name(group)} chart {where}; "
            f"the other {len(group.series) - 1} are left out."
        )
    labels = category_labels(s.categories, unique=False)
    colors = dict(s.point_colors)
    second = set(group.second_plot)
    first_points, second_points = [], []
    negative = 0
    for index, (label, value) in enumerate(zip(labels, s.values)):
        if value is None or value == 0:
            continue
        if value < 0:
            negative += 1
            continue
        point = (label, value, colors.get(index) or s.color)
        (second_points if index in second else first_points).append(point)
    if negative:
        warn_at_caller(
            f"maidr leaves {negative} negative value(s) out of the {chart_name(group)} "
            f"chart {where}: a slice has no negative size."
        )
    main, detail = fig.subplots(1, 2, gridspec_kw={"width_ratios": [3, 2]})
    other = sum(value for _, value, _ in second_points)
    total = other + sum(value for _, value, _ in first_points)
    slices = first_points + ([(_OTHER, other, _OTHER_COLOR)] if second_points else [])
    if slices:
        fills = [color for _, _, color in slices]
        main.pie(
            [value for _, value, _ in slices],
            labels=[label for label, _, _ in slices],
            colors=fills if all(fills) else None,
            # The gathered slice faces the second plot, as Excel turns it.
            startangle=-180 * other / total if total else 90,
            counterclock=False,
        )
    name_axis(main.xaxis, group.category_name, "Category", False)
    name_axis(main.yaxis, value_name(spec, group), "Value", False)
    if second_points:
        if group.style == "bar":
            bottom = 0.0
            for label, value, color in second_points:
                detail.bar(
                    [_OTHER], [value], 0.5, bottom=bottom, label=label, color=color
                )
                bottom += value
            for side in ("top", "right"):
                detail.spines[side].set_visible(False)
            detail.legend(frameon=False, loc="center left", bbox_to_anchor=(1.0, 0.5))
        else:
            fills = [color for _, _, color in second_points]
            detail.pie(
                [value for _, value, _ in second_points],
                labels=[label for label, _, _ in second_points],
                colors=fills if all(fills) else None,
                startangle=90,
                counterclock=False,
                radius=0.75,
            )
        detail.set_title(_OTHER)
        name_axis(detail.xaxis, group.category_name, "Category", False)
        name_axis(detail.yaxis, value_name(spec, group), "Value", False)
    else:
        detail.set_visible(False)
    return main
