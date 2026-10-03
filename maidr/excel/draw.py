"""Draw an Excel chart with matplotlib, so py-maidr reads it like any other.

Where matplotlib has a call for the chart -- ``bar``, ``barh``, ``plot``,
``scatter``, ``pie``, ``stackplot`` and ``pcolormesh`` -- the figure is drawn
through it, so the layers, the selectors that highlight each mark and the
announcements all come from py-maidr's own readers of those calls. Where it
has none -- a radar, a bubble chart's sizes, a stock chart's candles -- the
marks are drawn from plain artists and described by the layers of
:mod:`maidr.excel.layers`.

What is copied from the workbook is what a reader hears or a sighted colleague
would check against Excel: the values, the series names and colors, the
category labels as the axis writes them, the titles, the number format of the
value axis, its range, and the legend's place. Excel's fonts, effects and
exact proportions are not.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Callable

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection, PatchCollection, PathCollection
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.markers import MarkerStyle
from matplotlib.patches import Polygon, Rectangle
from matplotlib.ticker import (
    Formatter,
    MaxNLocator,
    PercentFormatter,
    StrMethodFormatter,
)

from maidr.core.enum import PlotType
from maidr.excel.chartxml import ChartSpec, Group, is_date_format
from maidr.excel.layers import each_mark, each_path, gid, register
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


#: What a reader is told each kind of chart group is called.
NAMES = {
    "bar": "bar",
    "line": "line",
    "area": "area",
    "scatter": "scatter",
    "bubble": "bubble",
    "pie": "pie",
    "doughnut": "doughnut",
    "radar": "radar",
    "stock": "stock",
    "surface": "surface",
}


def new_figure(aspect: float | None) -> Figure:
    """
    A figure as wide as every chart is drawn, as tall as the chart's own
    proportions on the sheet say, within bounds.
    """
    height = min(_WIDTH, max(3.5, _WIDTH * aspect)) if aspect else 4.5
    return Figure(figsize=(_WIDTH, height))


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
    fig = new_figure(aspect)
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
                f"maidr reads only the {_name(drawn)} of the chart {where}; "
                "the chart types drawn with it are left out."
            )
    if whole is not None:
        ax = _WHOLE[whole.kind](fig, whole, spec, where)
    else:
        ax = fig.add_subplot()
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        twin = None
        if stock is not None:
            _stock(ax, stock, volume)
            _axes(ax, stock, spec)
            groups = []
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


def _name(group: Group) -> str:
    if group.kind == "ofpie":
        return f"{group.style or 'pie'}-of-pie"
    return NAMES.get(group.kind, group.kind)


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
    if group.grouping in ("stacked", "percentStacked") and len(group.series) > 1:
        _stacked_lines(ax, group, labels)
        return
    for s in group.series:
        ax.plot(
            labels,
            _floats(s.values),
            label=s.name,
            color=s.color,
            marker="o" if s.marker else None,
            zorder=3,
        )


def _stacked_lines(ax: Axes, group: Group, labels: list[str]) -> None:
    """
    Each line drawn at the running total, read as a stacked area.

    The bands are what py-maidr reads, each series' own values with the
    stacking it took; they are left unpainted, and the lines Excel draws are
    drawn over them.
    """
    series = group.series
    values = _stacked_values(group)
    bands = ax.stackplot(labels, *values, labels=[s.name or "" for s in series])
    positions = np.arange(len(labels), dtype=float)
    top = np.zeros(len(labels))
    for band, s, vals in zip(bands, series, values):
        band.set_facecolor("none")
        band.set_edgecolor("none")
        band.set_label("_nolegend_")
        top = top + np.nan_to_num(vals)
        ax.add_line(
            Line2D(
                positions,
                np.where(np.isnan(vals), np.nan, top),
                color=s.color,
                marker="o" if s.marker else None,
                linewidth=2,
                label=s.name,
                zorder=3,
            )
        )


def _stacked_values(group: Group) -> list[np.ndarray]:
    """Each series' values, as shares of their category's total for 100%."""
    values = [_floats(s.values) for s in group.series]
    if group.grouping == "percentStacked":
        totals = np.nansum(np.abs(values), axis=0)
        totals[totals == 0] = np.nan
        values = [100 * v / totals for v in values]
    return values


def _area(ax: Axes, group: Group) -> None:
    labels = _labels(group.series[0].categories, unique=True)
    series = group.series
    values = _stacked_values(group)
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


def _bubble(ax: Axes, group: Group) -> None:
    """
    Each series' bubbles, read as points whose ``z`` is the bubble's size.

    Excel sizes a bubble by its area unless told to by its width, and draws
    the largest at a quarter of the plot's height, scaled by the chart's
    bubble scale.
    """
    marker = MarkerStyle("o")
    path = marker.get_path().transformed(marker.get_transform())
    sizes = [abs(v) for s in group.series for v in s.sizes if v is not None]
    largest = max(sizes, default=0.0) or 1.0
    # matplotlib sizes a marker by its area in points squared.
    biggest = (0.25 * 72 * ax.figure.get_figheight() * group.bubble_scale / 100) ** 2
    for s in group.series:
        xs, ys = _floats(s.categories), _floats(s.values)
        size = _floats(s.sizes) if s.sizes else np.full(len(xs), largest)
        keep = np.isfinite(xs) & np.isfinite(ys) & np.isfinite(size) & (size > 0)
        share = size[keep] / largest
        if group.style == "w":
            share = share**2
        bubbles = PathCollection(
            [path],
            sizes=biggest * share,
            offsets=np.column_stack([xs[keep], ys[keep]]),
            offset_transform=ax.transData,
            facecolors=s.color or "C0",
            edgecolors="white",
            alpha=0.85,
            label=s.name,
            zorder=3,
        )
        ax.add_collection(bubbles)
        mark = f"g[id='{gid(bubbles)}']"
        register(
            ax,
            PlotType.SCATTER,
            labels={"x": None, "y": None, "z": group.size_name or "Size"},
            data=[
                {"x": float(x), "y": float(y), "z": float(z)}
                for x, y, z in zip(xs[keep], ys[keep], size[keep])
            ],
            selectors=f"{mark} > g > use, {mark} > path",
            formats={"x": "x", "y": "y"},
        )
    ax.autoscale_view()
    # A bubble's radius reaches past its center; leave room for the largest.
    ax.margins(0.12)


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


def _pie_chart(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    ax = fig.add_subplot()
    _pie(ax, group, where)
    _label(ax.xaxis, group.category_name, "Category", False)
    _label(ax.yaxis, _value_name(spec, group), "Value", False)
    return ax


def _of_pie(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
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
            f"maidr reads the first series of the {_name(group)} chart {where}; "
            f"the other {len(group.series) - 1} are left out."
        )
    labels = _labels(s.categories, unique=False)
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
            f"maidr leaves {negative} negative value(s) out of the {_name(group)} "
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
    _label(main.xaxis, group.category_name, "Category", False)
    _label(main.yaxis, _value_name(spec, group), "Value", False)
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
        _label(detail.xaxis, group.category_name, "Category", False)
        _label(detail.yaxis, _value_name(spec, group), "Value", False)
    else:
        detail.set_visible(False)
    return main


def _radar(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """
    A radar: one spoke per category, clockwise from the top, and one closed
    outline per series, on a web of the value axis' gridlines.

    Each series is read from its own line, drawn open; the edge that closes
    it is drawn apart, so the line holds one vertex per category.
    """
    ax = fig.add_subplot()
    ax.set_aspect("equal")
    ax.set_axis_off()
    series = group.series
    labels = _labels(series[0].categories, unique=False)
    count = len(labels)
    values = [_floats(s.values) for s in series]
    found = np.concatenate(values) if values else np.array([])
    found = found[np.isfinite(found)]
    axis = group.y_axis
    low = axis.minimum if axis is not None and axis.minimum is not None else None
    high = axis.maximum if axis is not None and axis.maximum is not None else None
    ticks = MaxNLocator(nbins=5).tick_values(
        low if low is not None else min(0.0, found.min(initial=0.0)),
        high if high is not None else found.max(initial=1.0),
    )
    low = low if low is not None else float(ticks[0])
    high = high if high is not None else float(ticks[-1])
    ticks = [t for t in ticks if low <= t <= high]
    span = (high - low) or 1.0
    angles = np.pi / 2 - 2 * np.pi * np.arange(count) / max(count, 1)
    cos, sin = np.cos(angles), np.sin(angles)

    for tick in ticks:
        ring = (tick - low) / span
        ax.add_line(
            Line2D(
                np.append(cos, cos[:1]) * ring,
                np.append(sin, sin[:1]) * ring,
                color=_GRID,
                linewidth=0.8,
            )
        )
    for x, y, label in zip(cos, sin, labels):
        ax.add_line(Line2D([0, x], [0, y], color=_GRID, linewidth=0.8))
        ax.text(
            1.1 * x,
            1.1 * y,
            label,
            ha="center" if abs(x) < 0.3 else ("left" if x > 0 else "right"),
            va="center" if abs(y) < 0.3 else ("bottom" if y > 0 else "top"),
        )
    formatter = number_formatter(axis.number_format) if axis is not None else None
    if formatter is not None:
        ax.yaxis.set_major_formatter(formatter)
    for tick in ticks:
        ring = (tick - low) / span
        ax.text(
            0.03,
            ring,
            formatter(tick) if formatter is not None else f"{tick:g}",
            fontsize=8,
            color="#595959",
            va="center",
        )

    data, selectors = [], []
    for s, vals in zip(series, values):
        radius = (vals - low) / span
        xs, ys = radius * cos, radius * sin
        drawn = np.isfinite(radius)
        if group.style == "filled" and drawn.any():
            ax.add_patch(
                Polygon(
                    np.column_stack([xs[drawn], ys[drawn]]),
                    closed=True,
                    facecolor=s.color or "C0",
                    edgecolor="none",
                    alpha=0.6,
                )
            )
        line = Line2D(
            xs,
            ys,
            color=s.color,
            linewidth=1.5 if group.style == "filled" else 2,
            marker="o" if s.marker else None,
            label=s.name,
            zorder=3,
        )
        ax.add_line(line)
        if count > 2 and drawn[0] and drawn[-1]:
            ax.add_line(
                Line2D(
                    [xs[-1], xs[0]],
                    [ys[-1], ys[0]],
                    color=s.color,
                    linewidth=line.get_linewidth(),
                    zorder=3,
                )
            )
        selectors.append(each_path(line))
        points = []
        for label, value in zip(labels, s.values):
            point: dict[str, Any] = {"x": label, "y": value}
            if s.name:
                point["z"] = s.name
            points.append(point)
        data.append(points)
    ax.set_xlim(-1.45, 1.45)
    ax.set_ylim(-1.3, 1.3)
    if not found.size:
        # Every value blank: nothing to read, and the chart is left out.
        return ax
    register(
        ax,
        PlotType.RADAR,
        labels={
            "x": group.category_name or "Category",
            "y": (axis.label if axis is not None else None)
            or _value_name(spec, group)
            or "Value",
        },
        data=data,
        selectors=selectors,
        formats={"y": "y"},
    )
    if spec.legend is not None and any(s.name for s in series):
        _legend(ax, None, spec.legend)
    return ax


def _stock(ax: Axes, group: Group, volume: Group | None) -> None:
    """
    A stock chart's prices, read as candles: open-to-close bodies where Excel
    draws its up and down bars, and a high-low line with the close marked
    where it draws none. A volume drawn with it is read with each candle and
    drawn behind them.
    """
    series = group.series
    labels = _labels(series[0].categories, unique=False)
    prices = [_floats(s.values) for s in series]
    if len(prices) >= 4:
        opens, highs, lows, closes = prices[:4]
    else:
        opens, (highs, lows, closes) = None, prices[:3]
    volumes = _floats(volume.series[0].values) if volume is not None else None
    rows = [
        i
        for i in range(len(labels))
        if all(np.isfinite(p[i]) for p in (highs, lows, closes))
        and (opens is None or np.isfinite(opens[i]))
    ]
    positions = np.arange(len(labels), dtype=float)

    candles = []
    for i in rows:
        candle: dict[str, Any] = {"value": labels[i]}
        if opens is not None:
            candle["open"] = float(opens[i])
        candle.update(high=float(highs[i]), low=float(lows[i]), close=float(closes[i]))
        if volumes is not None and np.isfinite(volumes[i]):
            candle["volume"] = float(volumes[i])
        candles.append(candle)

    if volumes is not None:
        shown = [i for i in range(len(labels)) if np.isfinite(volumes[i])]
        twin = ax.twinx()
        twin.add_collection(
            PatchCollection(
                [Rectangle((positions[i] - 0.3, 0), 0.6, volumes[i]) for i in shown],
                facecolor=volume.series[0].color or "#A5A5A5",
                edgecolor="none",
                alpha=0.5,
            )
        )
        twin.set_ylim(0, 4 * max((volumes[i] for i in shown), default=1.0))
        twin.set_ylabel(volume.series[0].name or "Volume")
        twin.spines["top"].set_visible(False)
        ax.set_zorder(twin.get_zorder() + 1)
        ax.patch.set_visible(False)

    n = len(rows)
    if group.style == "updown" and opens is not None:
        bodies = PatchCollection(
            [
                Rectangle(
                    (positions[i] - 0.3, min(opens[i], closes[i])),
                    0.6,
                    abs(closes[i] - opens[i]),
                )
                for i in rows
            ],
            facecolor=["white" if closes[i] >= opens[i] else "black" for i in rows],
            edgecolor="black",
            linewidth=0.8,
            zorder=3,
        )
        wicks = LineCollection(
            [
                [(positions[i], lows[i]), (positions[i], min(opens[i], closes[i]))]
                for i in rows
            ]
            + [
                [(positions[i], max(opens[i], closes[i])), (positions[i], highs[i])]
                for i in rows
            ],
            colors="black",
            linewidths=0.8,
            zorder=2,
        )
        ax.add_collection(wicks)
        ax.add_collection(bodies)
        wick = each_path(wicks)
        selectors: Any = {
            "body": each_mark(bodies),
            "wickLow": f"{wick}:nth-child(-n+{n})",
            "wickHigh": f"{wick}:nth-child(n+{n + 1})",
        }
    else:
        spans = LineCollection(
            [[(positions[i], lows[i]), (positions[i], highs[i])] for i in rows],
            colors="black",
            linewidths=1,
            zorder=2,
        )
        ticks = LineCollection(
            [
                [(positions[i], closes[i]), (positions[i] + 0.25, closes[i])]
                for i in rows
            ],
            colors="black",
            linewidths=1.5,
            zorder=3,
        )
        ax.add_collection(spans)
        ax.add_collection(ticks)
        span = each_path(spans)
        selectors = {
            "body": span,
            "wickLow": span,
            "wickHigh": span,
            "close": each_path(ticks),
        }
        if opens is not None:
            starts = LineCollection(
                [
                    [(positions[i] - 0.25, opens[i]), (positions[i], opens[i])]
                    for i in rows
                ],
                colors="black",
                linewidths=1.5,
                zorder=3,
            )
            ax.add_collection(starts)
            selectors["open"] = each_path(starts)
    ax.set_xticks(positions, labels)
    ax.set_xlim(-0.6, len(labels) - 0.4)
    ax.autoscale_view(scalex=False)
    register(
        ax,
        PlotType.CANDLESTICK,
        labels={"x": None, "y": None},
        data=candles,
        selectors=selectors,
        formats={"y": "y"},
    )


def _surface(fig: Figure, group: Group, spec: ChartSpec, where: str) -> Axes:
    """
    A surface, seen from above as Excel's contour chart shows it: a cell per
    category and series, shaded by its value, read as a heatmap whose rows are
    the series, the first at the bottom.
    """
    ax = fig.add_subplot()
    # A heatmap is read from its top row down, so the rows are drawn that
    # way, the last series first, which leaves the first at the bottom.
    series = group.series[::-1]
    columns = _labels(series[0].categories, unique=False)
    rows = [s.name or f"Series {len(series) - i}" for i, s in enumerate(series)]
    grid = np.array([_floats(s.values) for s in series])
    value = group.y_axis
    value_name = (value.label if value is not None else None) or "Value"
    accent = group.series[0].color or "#4472C4"
    shades = LinearSegmentedColormap.from_list("excel", ["#FFFFFF", accent])
    mesh = ax.pcolormesh(
        grid, cmap=shades, edgecolors="white", linewidth=0.5, z_label=value_name
    )
    ax.set_xticks(np.arange(len(columns)) + 0.5, columns)
    ax.set_yticks(np.arange(len(rows)) + 0.5, rows)
    ax.invert_yaxis()
    bar = fig.colorbar(mesh, ax=ax)
    bar.set_label(value_name)
    formatter = number_formatter(value.number_format) if value is not None else None
    if formatter is not None:
        bar.formatter = formatter
        bar.update_ticks()
    titled = group.x_axis is not None and group.x_axis.title is not None
    _label(ax.xaxis, group.category_name, "Category", titled)
    _label(ax.yaxis, group.series_name, "Series", group.series_name is not None)
    return ax


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
            "X" if group.kind in ("scatter", "bubble") else "Category",
            x.title is not None,
        )
        if x.hidden:
            category_axis.set_visible(False)
        if group.kind in ("scatter", "bubble"):
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
            "Y" if group.kind in ("scatter", "bubble") else "Value",
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


#: Kinds drawn on shared axes, any of them with the others.
_DRAW: dict[str, Callable[[Axes, Group], None]] = {
    "bar": _bar,
    "line": _line,
    "area": _area,
    "scatter": _scatter,
    "bubble": _bubble,
}

#: Kinds that take the whole figure, drawn without any other.
_WHOLE: dict[str, Callable[[Figure, Group, ChartSpec, str], Axes]] = {
    "pie": _pie_chart,
    "doughnut": _pie_chart,
    "ofpie": _of_pie,
    "radar": _radar,
    "surface": _surface,
}

#: What a pie-of-pie calls the slice that gathers its second plot.
_OTHER = "Other"
_OTHER_COLOR = "#A5A5A5"
