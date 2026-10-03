"""Draw an Excel chart with matplotlib, so py-maidr reads it like any other.

The figure is drawn through the ``Axes`` calls a matplotlib user would make --
``bar``, ``barh``, ``plot``, ``scatter``, ``pie`` and ``stackplot`` -- so the
layers, the selectors that highlight each mark and the announcements all come
from py-maidr's own readers of those calls, and nothing here builds a schema.

What is copied from the workbook is what a reader hears or a sighted colleague
would check against Excel: the values, the series names and colors, the
category labels as the axis writes them, the titles, the number format of the
value axis, its range, and the legend's place. Excel's fonts, effects and
exact proportions are not.
"""

from __future__ import annotations

import re
from typing import Any, Callable

import numpy as np
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import Formatter, PercentFormatter, StrMethodFormatter

from maidr.excel.chartxml import ChartSpec, Group, is_date_format
from maidr.util.caller_warning import warn_at_caller

#: How a category with no label is read.
BLANK = "(blank)"

#: Figure width in inches. The height follows the chart's own proportions.
_WIDTH = 7.0
_GRID = "#D9D9D9"

_CURRENCY = re.compile(r"\[\$([^\]-]*)[^\]]*\]|\"([^\"]*)\"|([$€£¥])")
_SYMBOLS = ("$", "€", "£", "¥")

#: Legend position codes, as matplotlib ``legend`` arguments outside the axes.
_LEGEND = {
    "r": {"loc": "center left", "bbox_to_anchor": (1.02, 0.5)},
    "l": {"loc": "center right", "bbox_to_anchor": (-0.12, 0.5)},
    "t": {"loc": "lower center", "bbox_to_anchor": (0.5, 1.08)},
    "b": {"loc": "upper center", "bbox_to_anchor": (0.5, -0.14)},
    "tr": {"loc": "upper left", "bbox_to_anchor": (1.02, 1.0)},
}


def draw(spec: ChartSpec, *, aspect: float | None, where: str) -> Figure:
    """
    Draw a chart.

    Parameters
    ----------
    spec : ChartSpec
        The chart, as :func:`maidr.excel.chartxml.read_chart` read it.
    aspect : float or None
        The chart's height over its width on the sheet, if known.
    where : str
        How warnings name the chart, such as ``"'Chart 1' on sheet 'Sales'"``.

    Returns
    -------
    matplotlib.figure.Figure
        A figure not managed by pyplot, with its layers registered with maidr.
    """
    height = min(_WIDTH, max(3.5, _WIDTH * aspect)) if aspect else 4.5
    fig = Figure(figsize=(_WIDTH, height))
    ax = fig.add_subplot()
    groups = list(spec.groups)
    pies = [g for g in groups if g.kind in ("pie", "doughnut")]
    if pies:
        if len(groups) > 1:
            warn_at_caller(
                f"maidr reads only the {pies[0].kind} of the chart {where}; "
                "the chart types drawn with it are left out."
            )
        _pie(ax, pies[0], where)
        _label(ax.xaxis, pies[0].category_name, "Category", False)
        _label(ax.yaxis, _value_name(spec, pies[0]), "Value", False)
    else:
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        twin = None
        for group in groups:
            target = ax
            if group.secondary:
                if twin is None:
                    twin = ax.twiny() if group.horizontal else ax.twinx()
                    for side in ("bottom", "left") if group.horizontal else ("top",):
                        twin.spines[side].set_visible(False)
                target = twin
            _DRAW[group.kind](target, group)
            _axes(target, group, spec)
        if spec.legend is not None:
            _legend(ax, twin, spec.legend)
    if spec.title:
        ax.set_title(spec.title)
    fig.tight_layout()
    return fig


def _bar(ax: Axes, group: Group) -> None:
    series = group.series
    labels = _labels(series[0].categories, unique=False)
    positions = np.arange(len(labels), dtype=float)
    draw_bar = ax.barh if group.horizontal else ax.bar
    stacked = group.grouping in ("stacked", "percentStacked") and len(series) > 1
    if stacked:
        values = [_floats(s.values) for s in series]
        if group.grouping == "percentStacked":
            totals = np.nansum(np.abs(values), axis=0)
            totals[totals == 0] = np.nan
            values = [100 * v / totals for v in values]
        above = np.zeros(len(labels))
        below = np.zeros(len(labels))
        for s, vals in zip(series, values):
            base = np.where(np.nan_to_num(vals) < 0, below, above)
            kwargs = (
                {"left" if group.horizontal else "bottom": base} if base.any() else {}
            )
            draw_bar(positions, vals, label=s.name, color=s.color, **kwargs)
            above = above + np.where(vals > 0, vals, 0)
            below = below + np.where(vals < 0, vals, 0)
    elif len(series) == 1:
        s = series[0]
        draw_bar(positions, _floats(s.values), label=s.name, color=s.color)
    else:
        width = 0.8 / len(series)
        for i, s in enumerate(series):
            offset = (i - (len(series) - 1) / 2) * width
            draw_bar(
                positions + offset,
                _floats(s.values),
                width,
                label=s.name,
                color=s.color,
            )
    if group.horizontal:
        ax.set_yticks(positions, labels)
    else:
        ax.set_xticks(positions, labels)


def _line(ax: Axes, group: Group) -> None:
    labels = _labels(group.series[0].categories, unique=True)
    for s in group.series:
        ax.plot(
            labels,
            _floats(s.values),
            label=s.name,
            color=s.color,
            marker="o" if s.marker else None,
            zorder=3,
        )


def _area(ax: Axes, group: Group) -> None:
    labels = _labels(group.series[0].categories, unique=True)
    series = group.series
    values = [_floats(s.values) for s in series]
    if group.grouping == "percentStacked":
        totals = np.nansum(np.abs(values), axis=0)
        totals[totals == 0] = np.nan
        values = [100 * v / totals for v in values]
    if group.grouping in ("stacked", "percentStacked") and len(series) > 1:
        ax.stackplot(
            labels,
            *values,
            labels=[s.name or "" for s in series],
            colors=[s.color for s in series] if all(s.color for s in series) else None,
        )
        return
    # Excel draws each band of a plain area chart from zero, the later ones in
    # front; one stack per band is the same picture.
    for s, vals in zip(series, values):
        ax.stackplot(
            labels,
            vals,
            labels=[s.name or ""],
            colors=[s.color] if s.color else None,
            alpha=0.85 if len(series) > 1 else 1.0,
        )


def _scatter(ax: Axes, group: Group) -> None:
    for s in group.series:
        xs, ys = _floats(s.categories), _floats(s.values)
        if s.line:
            ax.plot(
                xs, ys, label=s.name, color=s.color, marker="o" if s.marker else None
            )
        else:
            ax.scatter(xs, ys, label=s.name, color=s.color)


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
        zip(_labels(s.categories, unique=False), s.values)
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


def _axes(ax: Axes, group: Group, spec: ChartSpec) -> None:
    """Name, format and scale a group's axes as Excel does."""
    category_axis, value_axis = (
        (ax.yaxis, ax.xaxis) if group.horizontal else (ax.xaxis, ax.yaxis)
    )
    x, y = group.x_axis, group.y_axis
    if x is not None:
        _label(
            category_axis,
            x.label,
            "X" if group.kind == "scatter" else "Category",
            x.title is not None,
        )
        if x.hidden:
            category_axis.set_visible(False)
        if group.kind == "scatter":
            _scale(ax, "x", x.minimum, x.maximum, x.reversed)
            formatter = number_formatter(x.number_format)
            if formatter is not None:
                ax.xaxis.set_major_formatter(formatter)
        elif x.reversed:
            if group.horizontal:
                ax.invert_yaxis()
            else:
                ax.invert_xaxis()
    if y is not None:
        _label(
            value_axis,
            y.label or _value_name(spec, group),
            "Y" if group.kind == "scatter" else "Value",
            y.title is not None,
        )
        if y.hidden:
            value_axis.set_visible(False)
        if group.grouping == "percentStacked":
            value_axis.set_major_formatter(PercentFormatter(xmax=100, decimals=0))
        else:
            formatter = number_formatter(y.number_format)
            if formatter is not None:
                value_axis.set_major_formatter(formatter)
        _scale(ax, "x" if group.horizontal else "y", y.minimum, y.maximum, y.reversed)
    ax.grid(axis="x" if group.horizontal else "y", color=_GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _value_name(spec: ChartSpec, group: Group) -> str | None:
    """An untitled value axis is named after the only series drawn against it."""
    shared = [
        s for g in spec.groups if g.secondary == group.secondary for s in g.series
    ]
    if len(shared) == 1 and shared[0].name:
        return shared[0].name
    return None


def _label(axis: Any, label: str | None, fallback: str, drawn: bool) -> None:
    """
    Name an axis for the reader, and draw the name only where Excel does.

    A name found for an untitled axis -- the header above its range -- is read
    out but not drawn, so the picture keeps Excel's layout.
    """
    axis.set_label_text(label or fallback)
    axis.label.set_visible(drawn)


def _scale(
    ax: Axes, which: str, low: float | None, high: float | None, flip: bool
) -> None:
    if low is not None or high is not None:
        (ax.set_xlim if which == "x" else ax.set_ylim)(low, high)
    if flip:
        (ax.invert_xaxis if which == "x" else ax.invert_yaxis)()


def _legend(ax: Axes, twin: Axes | None, position: str) -> None:
    handles, labels = ax.get_legend_handles_labels()
    if twin is not None:
        more = twin.get_legend_handles_labels()
        handles, labels = handles + more[0], labels + more[1]
    kept = [
        (h, text)
        for h, text in zip(handles, labels)
        if text and not text.startswith("_")
    ]
    if not kept:
        return
    place = _LEGEND.get(position, _LEGEND["r"])
    extra = {"ncol": len(kept)} if position in ("t", "b") else {}
    ax.legend(*zip(*kept), frameon=False, **place, **extra)


def number_formatter(code: str | None) -> Formatter | None:
    """
    The matplotlib formatter for an Excel number format, where py-maidr can
    announce it.

    Parameters
    ----------
    code : str or None
        An Excel format code such as ``"0.0%"`` or ``"$#,##0"``.

    Returns
    -------
    matplotlib.ticker.Formatter or None
        A percent, currency or grouped-number formatter, or ``None`` for
        ``General``, dates and anything else, which read as plain numbers.
    """
    if not code or code.lower() == "general" or is_date_format(code):
        return None
    section = code.split(";")[0]
    match = re.search(r"\.([0#?]+)", section)
    decimals = len(match.group(1)) if match else 0
    bare = re.sub(r'"[^"]*"|\\.|\[[^\]]*\]', "", section)
    if "%" in bare:
        return PercentFormatter(xmax=1, decimals=decimals)
    if not re.search(r"[0#]", bare):
        return None
    grouping = "," if re.search(r"[0#],[0#]", bare) else ""
    symbol = next(
        (
            s
            for found in _CURRENCY.finditer(section)
            for s in found.groups()
            if s and s.strip() in _SYMBOLS
        ),
        "",
    ).strip()
    return StrMethodFormatter(f"{symbol}{{x:{grouping}.{decimals}f}}")


def _labels(categories: tuple[Any, ...], *, unique: bool) -> list[str]:
    """
    Category labels to draw and read: a missing one reads ``(blank)``, and
    where the axis needs them distinct, a repeated one gets its occurrence
    number, ``Q1 (2)``.
    """
    out, seen = [], {}
    for category in categories:
        label = str(category) if category not in (None, "") else BLANK
        if unique:
            count = seen.get(label, 0) + 1
            seen[label] = count
            if count > 1:
                label = f"{label} ({count})"
        out.append(label)
    return out


def _floats(values: tuple[Any, ...]) -> np.ndarray:
    return np.array([np.nan if v is None else float(v) for v in values], dtype=float)


_DRAW: dict[str, Callable[[Axes, Group], None]] = {
    "bar": _bar,
    "line": _line,
    "area": _area,
    "scatter": _scatter,
}
