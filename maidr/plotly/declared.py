"""The ``meta.maidr`` declarations a Plotly trace can carry.

maidr.js's own Plotly adapter reads a co-located declaration off a trace's
``meta``, plotly's slot for arbitrary metadata: ``meta={"maidr": {...}}``. A
precision-recall curve and a fan chart are drawn as plain lines and filled
lines, and nothing else in the figure says what they are, so a declaration is
the one unambiguous statement of either. This module honours the same two
blocks maidr.js's Plotly adapter does for them, with the same keys and the
same rules, so a figure declared once reads the same whether py-maidr builds
its schema or maidr.js does:

``{"type": "pr_curve", "threshold"?, "prevalence"?, "ap"?, "merge"?,
"title"?, "name"?}``
    On a line or step trace. Every line and step trace of the subplot joins
    the layer as a curve, unless the first declaring trace sets
    ``merge: False``; then only the traces declaring one do. ``threshold``
    names a key of the trace's ``customdata`` rows (dicts); ``prevalence``
    and ``ap`` are fractions of one, written on the curve's first point.

``{"type": "percentile_band", "bands": [{"series", "lower", "upper"}, ...],
"title"?, "name"?}``
    On the median, an unfilled line trace. Each band names, by ``uid`` or
    ``name``, the trace filled ``"tonexty"`` to the trace before it, which is
    the band's other edge. The levels are fractions, each band strictly
    inside the next wider one.

A block that breaks a rule is reported with a ``UserWarning`` and read as
the undeclared chart, or, for one band of several, left out of the layer.
"""

from __future__ import annotations

import math
import numbers
from typing import Any

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, paired_axes
from maidr.plotly.step_shape import is_step_trace, renders_through_webgl
from maidr.util.caller_warning import warn_at_caller

PR_CURVE = PlotType.PR_CURVE.value
PERCENTILE_BAND = PlotType.PERCENTILE_BAND.value

#: The keys each block takes, as maidr.js's validator lists them.
_KEYS = {
    PR_CURVE: {"type", "title", "name", "threshold", "prevalence", "ap", "merge"},
    PERCENTILE_BAND: {"type", "title", "name", "bands"},
}

#: Where a threshold is looked for when the block names no key, in order.
_THRESHOLD_KEYS = ("threshold", "thresholds", "cutoff")


def _warn(trace: dict, message: str) -> None:
    """Report a declaration that cannot be read as written."""
    name = trace.get("name")
    where = f'trace "{name}"' if isinstance(name, str) and name else "a trace"
    warn_at_caller(f"maidr declaration on {where} {message}")


def _fraction(value: Any) -> bool:
    """Whether a value is a number from 0 to 1."""
    return (
        isinstance(value, numbers.Real)
        and not isinstance(value, bool)
        and 0 <= value <= 1
    )


def _number(value: Any) -> float | None:
    """A finite number, or None; a numeric string counts, as in maidr.js."""
    if isinstance(value, bool):
        return None
    if isinstance(value, numbers.Real):
        value = float(value)
    elif isinstance(value, str) and value.strip():
        try:
            value = float(value)
        except ValueError:
            return None
    else:
        return None
    return value if math.isfinite(value) else None


def declaration_of(trace: dict) -> dict | None:
    """
    The ``pr_curve`` or ``percentile_band`` block a trace declares, validated.

    Parameters
    ----------
    trace : dict
        A plotly trace dictionary.

    Returns
    -------
    dict or None
        The block with every unusable key dropped, or None when the trace
        declares neither type or the block cannot be read at all.
    """
    meta = trace.get("meta")
    block = meta.get("maidr") if isinstance(meta, dict) else None
    if not isinstance(block, dict) or block.get("type") not in _KEYS:
        return None
    kind = block["type"]
    kept: dict = {"type": kind}
    for key, value in block.items():
        if key == "type" or value is None:
            continue
        if key not in _KEYS[kind]:
            _warn(trace, f'has unknown key "{key}"; ignored.')
            continue
        if key in ("title", "name"):
            ok = isinstance(value, str)
        elif key == "threshold":
            ok = isinstance(value, str) and bool(value.strip())
        elif key in ("prevalence", "ap"):
            ok = _fraction(value)
        elif key == "merge":
            ok = isinstance(value, bool)
        else:
            ok = _bands_ok(trace, value)
        if ok:
            kept[key] = value
        elif key != "bands":
            _warn(trace, f"has {key} {value!r}, which it cannot take; ignored.")
    if kind == PERCENTILE_BAND and "bands" not in kept:
        _warn(trace, "has no usable bands; reading it as the undeclared chart.")
        return None
    return kept


def _bands_ok(trace: dict, bands: Any) -> bool:
    """Whether a ``bands`` list is usable: well-formed entries that nest."""
    if not isinstance(bands, list) or not bands:
        return False
    for band in bands:
        if not isinstance(band, dict):
            return False
        series, lower, upper = band.get("series"), band.get("lower"), band.get("upper")
        if not (isinstance(series, str) and series.strip()):
            return False
        if not (_fraction(lower) and _fraction(upper) and lower < 0.5 < upper):
            _warn(
                trace,
                f'has band "{series}" with levels {lower!r} and {upper!r}; '
                "expected a lower level from 0 to below 0.5 and an upper one "
                "above 0.5 to 1.",
            )
            return False
    ordered = sorted(bands, key=lambda band: band["lower"])
    for outer, inner in zip(ordered, ordered[1:]):
        if not (inner["lower"] > outer["lower"] and inner["upper"] < outer["upper"]):
            _warn(
                trace,
                f'has bands "{outer["series"]}" and "{inner["series"]}" that do '
                "not nest; each band must lie strictly inside the next wider one.",
            )
            return False
    return True


def _values_by_x(trace: dict) -> dict[str, float]:
    """A trace's finite y values, keyed by the x each is drawn at."""
    xs, ys = paired_axes(trace)
    at: dict[str, float] = {}
    for x, y in zip(xs, ys):
        value = _number(y)
        if x is not None and value is not None:
            at[str(PlotlyPlot._to_native(x))] = value
    return at


def _fills(trace: dict) -> bool:
    """Whether plotly fills anything for this trace."""
    return trace.get("fill") not in (None, "none")


class PlotlyDeclaredPrCurvePlot(PlotlyPlot):
    """
    The precision-recall curves one subplot declares, as one ``pr_curve`` layer.

    Parameters
    ----------
    traces : list of dict
        The curves, in trace order.
    blocks : list of dict or None
        Each curve's own ``pr_curve`` block, or None where it carries none.
    layout : dict
        The figure layout.
    scatter_positions : list of int
        Each trace's position among the subplot's scatter-family traces.
    title : str or None
        The first block's ``title``.
    name : str or None
        The first block's ``name``.
    **kwargs : str
        Axis names forwarded to the parent class.
    """

    def __init__(
        self,
        traces: list[dict],
        blocks: list[dict | None],
        layout: dict,
        scatter_positions: list[int],
        title: str | None = None,
        name: str | None = None,
        **kwargs: str,
    ) -> None:
        PlotlyPlot._validate_scatter_positions(scatter_positions, len(traces))
        super().__init__(traces[0], layout, PlotType.PR_CURVE, **kwargs)
        self._traces = list(traces)
        self._blocks = list(blocks)
        self._positions = list(scatter_positions)
        self._declared_title = title
        self._declared_name = name

    def _curves(self) -> list[tuple[list[dict], int]]:
        """Each curve that has a point, with its scatter position."""
        curves = []
        for row, (trace, block, position) in enumerate(
            zip(self._traces, self._blocks, self._positions)
        ):
            xs, ys = paired_axes(trace)
            customdata = trace.get("customdata")
            rows = list(customdata) if isinstance(customdata, (list, tuple)) else []
            label = trace.get("name") or f"Curve {row + 1}"
            ref = (block or {}).get("threshold")
            keys = (ref,) if ref else _THRESHOLD_KEYS
            points: list[dict] = []
            for i, (x, y) in enumerate(zip(xs, ys)):
                recall, precision = _number(x), _number(y)
                if recall is None or precision is None:
                    continue
                point: dict = {"x": recall, "y": precision, "z": label}
                custom = rows[i] if i < len(rows) else None
                if isinstance(custom, dict):
                    found = next((custom[k] for k in keys if k in custom), None)
                    threshold = _number(found)
                    if threshold is not None:
                        point["threshold"] = threshold
                points.append(point)
            if not points:
                continue
            if ref and not any("threshold" in point for point in points):
                _warn(trace, f'names threshold "{ref}", which no customdata row has.')
            for key in ("prevalence", "ap"):
                if block is not None and key in block:
                    points[0][key] = float(block[key])
            curves.append((points, position))
        return curves

    def _get_title(self) -> str:
        """The declared title, or else the figure's, or a lone curve's name."""
        if self._declared_title is not None:
            return self._declared_title
        title = super()._get_title()
        names = [trace.get("name") for trace in self._traces if trace.get("name")]
        return title or (names[0] if len(names) == 1 else "")

    def _extract_plot_data(self) -> list[list[dict]]:
        return [points for points, _ in self._curves()]

    def _get_selector(self) -> list[str]:
        if any(renders_through_webgl(trace) for trace in self._traces):
            return []
        return [self._scatter_line_selector(pos) for _, pos in self._curves()]

    def render(self) -> dict:
        schema = super().render()
        schema[MaidrKey.TYPE] = PlotType.PR_CURVE
        if self._declared_name is not None:
            schema[MaidrKey.NAME] = self._declared_name
        return schema


class PlotlyPercentileBandPlot(PlotlyPlot):
    """
    A declared fan chart: a median line and the bands named around it.

    Parameters
    ----------
    median : dict
        The trace drawing the median.
    bands : list of tuple
        ``(lower, upper, low_trace, high_trace, filled_to_position)`` for each
        band, outermost first.
    layout : dict
        The figure layout.
    median_position : int
        The median's position among the subplot's scatter-family traces.
    title : str or None
        The block's ``title``.
    name : str or None
        The block's ``name``.
    **kwargs : str
        Axis names forwarded to the parent class.
    """

    def __init__(
        self,
        median: dict,
        bands: list[tuple[float, float, dict, dict, int]],
        layout: dict,
        median_position: int,
        title: str | None = None,
        name: str | None = None,
        **kwargs: str,
    ) -> None:
        PlotlyPlot._validate_scatter_positions([median_position], 1)
        super().__init__(median, layout, PlotType.PERCENTILE_BAND, **kwargs)
        self._bands = bands
        self._median_position = median_position
        self._declared_title = title
        self._declared_name = name

    def _get_title(self) -> str:
        if self._declared_title is not None:
            return self._declared_title
        return super()._get_title() or self._trace.get("name") or ""

    def _extract_plot_data(self) -> list[dict]:
        edges = [
            (lower, upper, _values_by_x(low), _values_by_x(high))
            for lower, upper, low, high, _ in self._bands
        ]
        xs, ys = paired_axes(self._trace)
        data = []
        for x, y in zip(xs, ys):
            value = _number(y)
            if x is None or value is None:
                continue
            x = self._to_native(x)
            quantiles: list[dict] = [{"level": 0.5, "value": value}]
            for lower, upper, low, high in edges:
                quantiles.append({"level": lower, "value": low.get(str(x))})
                quantiles.append({"level": upper, "value": high.get(str(x))})
            quantiles.sort(key=lambda quantile: quantile["level"])
            data.append({"x": x, "quantiles": quantiles})
        return data

    def _get_selector(self) -> list[str]:
        """
        One selector per band, outermost first, then the median's line.

        A ``tonexty`` fill is drawn as the one ``path.js-fill`` in the group
        of the trace it fills to, as maidr.js's Plotly adapter measured it.
        """
        if renders_through_webgl(self._trace):
            return []
        prefix = self._subplot_css_prefix()
        fills = [
            f"{prefix}.scatterlayer > .trace.scatter:nth-child({position + 1}) "
            "path.js-fill"
            for *_, position in self._bands
        ]
        return [*fills, self._scatter_line_selector(self._median_position)]

    def render(self) -> dict:
        schema = super().render()
        if self._declared_name is not None:
            schema[MaidrKey.NAME] = self._declared_name
        return schema


def declared_layers(
    connected: list[dict],
    all_scatter: list[dict],
    position_of: dict[int, int],
    layout: dict,
    **axis_kwargs: str,
) -> tuple[list[PlotlyPlot], set[int]]:
    """
    The layers one subplot's ``meta.maidr`` blocks declare, and what they take.

    Parameters
    ----------
    connected : list of dict
        The subplot's drawn, connected line traces that are not areas, in
        trace order: the traces a declaration may name.
    all_scatter : list of dict
        Every drawn scatter-family trace of the subplot, in trace order, which
        is what plotly links a ``tonexty`` fill through.
    position_of : dict
        Each scatter-family trace's position, keyed by ``id``.
    layout : dict
        The figure layout.
    **axis_kwargs : str
        The subplot's axis names.

    Returns
    -------
    tuple of (list of PlotlyPlot, set of int)
        The declared layers, and the ``id`` of every trace they consume.
    """
    blocks = {id(trace): declaration_of(trace) for trace in connected}
    taken: set[int] = set()
    layers: list[PlotlyPlot] = []
    svg_scatter = [t for t in all_scatter if not renders_through_webgl(t)]

    for median in connected:
        block = blocks[id(median)]
        if block is None or block["type"] != PERCENTILE_BAND:
            continue
        if _fills(median) or is_step_trace(median) or renders_through_webgl(median):
            _warn(
                median,
                'declares "percentile_band" but is not an unfilled line trace; '
                "reading it as the undeclared chart.",
            )
            continue
        taken.add(id(median))
        bands = []
        for band in sorted(block["bands"], key=lambda band: band["lower"]):
            read = _band_edges(median, band, connected, svg_scatter, taken)
            if read is not None:
                low, high, filled_to = read
                taken.update((id(low), id(high)))
                bands.append(
                    (
                        band["lower"],
                        band["upper"],
                        low,
                        high,
                        position_of[id(filled_to)],
                    )
                )
        plot = PlotlyPercentileBandPlot(
            median,
            bands,
            layout,
            position_of[id(median)],
            title=block.get("title"),
            name=block.get("name"),
            **axis_kwargs,
        )
        layers.append(plot)

    lines = [t for t in connected if id(t) not in taken]
    declaring = [t for t in lines if (blocks[id(t)] or {}).get("type") == PR_CURVE]
    if declaring:
        first = blocks[id(declaring[0])]
        curves = declaring if first.get("merge") is False else lines
        # One renderer per layer, as every line layer is split.
        gl = renders_through_webgl(declaring[0])
        curves = [t for t in curves if renders_through_webgl(t) == gl]
        layers.append(
            PlotlyDeclaredPrCurvePlot(
                curves,
                [
                    blocks[id(t)]
                    if (blocks[id(t)] or {}).get("type") == PR_CURVE
                    else None
                    for t in curves
                ],
                layout,
                [position_of[id(t)] for t in curves],
                title=first.get("title"),
                name=first.get("name"),
                **axis_kwargs,
            )
        )
        taken.update(id(t) for t in curves)
    return layers, taken


def _band_edges(
    median: dict,
    band: dict,
    connected: list[dict],
    svg_scatter: list[dict],
    taken: set[int],
) -> tuple[dict, dict, dict] | None:
    """
    A band's low edge, high edge and the trace its fill is drawn with, or None.

    The band's ``series`` names the trace filled ``"tonexty"``, by ``uid`` and
    then by ``name``; plotly fills it to the trace drawn before it on the
    subplot, which is the band's other edge. Which edge is the high one is
    read from the values, and a pair that crosses is no band.
    """
    series = band["series"]
    others = [t for t in connected if t is not median]
    filler = next((t for t in others if t.get("uid") == series), None) or next(
        (t for t in others if t.get("name") == series), None
    )
    if filler is None:
        _warn(
            median, f'names "{series}" as a band, which this subplot draws no line for.'
        )
        return None
    at = next((i for i, t in enumerate(svg_scatter) if t is filler), 0)
    filled_to = svg_scatter[at - 1] if at > 0 else None
    if (
        filler.get("fill") != "tonexty"
        or filled_to is None
        or not any(t is filled_to for t in others)
    ):
        _warn(
            median,
            f'names "{series}" as a band, which is not filled "tonexty" to '
            "another line trace; emitting the layer without it.",
        )
        return None
    if id(filler) in taken or id(filled_to) in taken:
        _warn(median, f'names "{series}" as a band whose edges are already read.')
        return None
    a, b = _values_by_x(filler), _values_by_x(filled_to)
    shared = [x for x in a if x in b]
    above = sum(a[x] > b[x] for x in shared)
    below = sum(a[x] < b[x] for x in shared)
    if (above > 0) == (below > 0):
        _warn(median, f'names "{series}" as a band whose two edges cross.')
        return None
    return (filled_to, filler, filled_to) if above else (filler, filled_to, filled_to)


__all__ = [
    "PlotlyDeclaredPrCurvePlot",
    "PlotlyPercentileBandPlot",
    "declaration_of",
    "declared_layers",
]
