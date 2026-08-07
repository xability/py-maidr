"""Recognising Plotly staircase traces and the convention they draw.

Plotly has no step trace type. A step chart is an ordinary ``scatter`` trace
whose ``line.shape`` tells plotly.js to draw risers between the samples
instead of interpolating across them, so the shape is the only thing that
distinguishes one from a line.

The values and the direction mapping here mirror the upstream JS adapter
(``src/adapters/plotly/extractor.ts`` in xability/maidr, added in #746) so a
plotly figure describes itself the same way whether it is bound in the
browser or exported through this package.
"""

from __future__ import annotations

#: ``line.shape`` values plotly draws as a staircase.
#:
#: ``linear``, ``spline`` and an absent shape are deliberately not here: they
#: interpolate between samples, which is what a step chart does not do.
STEP_SHAPES = frozenset({"hv", "vh", "hvh", "vhv"})

#: Where each staircase shape jumps, in MAIDR ``stepDirection`` terms.
#:
#: ``vhv`` is deliberately absent rather than mapped to ``mid``. It is the one
#: shape whose horizontal segments do not sit at a sample's own value: ``hvh``
#: holds each sample's value and jumps midway between x values, where ``vhv``
#: jumps at the x values themselves and holds a value between two samples. A
#: ``vhv`` trace still binds as a step — the data is piecewise constant — but
#: the direction is withheld, which is what an optional ``stepDirection``
#: exists for.
STEP_SHAPE_DIRECTION: dict[str, str] = {
    "hv": "hv",
    "vh": "vh",
    "hvh": "mid",
}


#: Plotly trace types that render as a connected path in the scatter layer.
#:
#: ``scattergl`` is included because it is a scatter trace in every respect
#: that matters to classification — same ``mode``, same ``line.shape``, same
#: data. It differs only in how it is painted, which
#: :func:`renders_through_webgl` handles separately.
_CONNECTED_TRACE_TYPES = ("scatter", "scattergl")


#: Plotly trace types painted onto a ``<canvas>`` through WebGL, not as SVG.
#:
#: These have no per-trace DOM element, so no CSS selector can address their
#: geometry — see :func:`renders_through_webgl` for what follows from that.
_WEBGL_TRACE_TYPES = ("scattergl",)


def renders_through_webgl(trace: dict) -> bool:
    """
    Report whether a trace is painted to a canvas rather than to SVG.

    A WebGL trace has no element to select: plotly draws every ``scattergl``
    trace on the subplot into one shared ``<canvas>``, so there is no
    ``path.js-line`` and no ``.point`` to match. Emitting the SVG selectors
    anyway produced layers whose highlight silently resolved to zero elements
    — correct audio, braille and text, no visible highlight, no warning.

    Upstream leaves no room for a canvas selector either. ``maidr``'s
    highlight service rejects a non-``SVGElement`` outright, and canvas-backed
    libraries are served instead by the ``onNavigate`` callback, which
    ``src/type/grammar.ts`` documents as "not serializable as JSON" — so it is
    unreachable from an exported figure by construction, not merely unused.

    Parameters
    ----------
    trace : dict
        The plotly trace dictionary.

    Returns
    -------
    bool
        True when the trace renders through WebGL.
    """
    return trace.get("type", "scatter") in _WEBGL_TRACE_TYPES


def is_scatter_family_trace(trace: dict) -> bool:
    """
    Report whether a trace belongs to the subplot's scatter layer.

    This is the membership test for ``scatterlayer``, so it decides both which
    traces can be lines or steps and which ones the ``nth-child`` selector
    indices count over. Those two must agree: a trace classified as a line but
    absent from the index would have no position to look up.

    ``type`` defaults to ``"scatter"`` because that is plotly's own default
    for a trace that omits it.

    Parameters
    ----------
    trace : dict
        The plotly trace dictionary.

    Returns
    -------
    bool
        True for a ``scatter`` or ``scattergl`` trace.
    """
    return trace.get("type", "scatter") in _CONNECTED_TRACE_TYPES


def is_connected_line_trace(trace: dict) -> bool:
    """
    Report whether a trace draws a connected path rather than loose markers.

    This is the gate in front of every line/step decision: a trace only
    reaches that classification if plotly is joining its samples up. It lives
    here so ``PlotlyMaidr._extract_plots`` and ``PlotlyPlotFactory`` share one
    definition — they classify the same traces in two places, and a rule
    duplicated by hand is one that eventually disagrees with itself.

    It is deliberately built on :func:`is_scatter_family_trace` rather than
    repeating the type test, so the scatter-family rule has exactly one home.
    Spelling it out twice is what previously let the two tests drift apart and
    produce a trace that was a line but had no selector position.

    Parameters
    ----------
    trace : dict
        The plotly trace dictionary.

    Returns
    -------
    bool
        True for a scatter-family trace in a lines-only mode, or a staircase
        that never authored a mode at all.
    """
    if not is_scatter_family_trace(trace):
        return False

    mode = trace.get("mode")
    if mode is None:
        # ``to_dict()`` omits ``mode`` when the author never set one, and
        # plotly's default draws lines either way — "lines+markers" under 20
        # points, "lines" at or above. Reading an absent mode as markers-only
        # would send a trace authored as
        # ``add_scatter(..., line_shape="hv")`` to a scatter layer, so the
        # chart plotly actually draws as a staircase gets announced as loose
        # points, losing the piecewise-constant reading entirely.
        #
        # Only a declared stepping shape is rescued here. A mode-less trace
        # with no ``line.shape`` keeps whatever classification it had before
        # steps existed, so plain scatters are untouched.
        return is_step_trace(trace)

    return "lines" in mode and "markers" not in mode


def is_step_shape(shape: str | None) -> bool:
    """
    Report whether a ``line.shape`` makes plotly draw a staircase.

    Parameters
    ----------
    shape : str or None
        The trace's ``line.shape``, or None when it authors none.

    Returns
    -------
    bool
        True for every shape plotly renders as piecewise constant.
    """
    return shape is not None and shape in STEP_SHAPES


def trace_line_shape(trace: dict) -> str | None:
    """
    Read ``line.shape`` off a trace, tolerating a missing or odd ``line``.

    Plotly accepts ``line`` as a dict; a trace may omit it entirely, and a
    hand-built dict may carry something else there. Anything that is not a
    dict with a string ``shape`` reads as "no shape authored".

    Parameters
    ----------
    trace : dict
        The plotly trace dictionary.

    Returns
    -------
    str or None
        The authored shape, or None.
    """
    line = trace.get("line")
    if not isinstance(line, dict):
        return None
    shape = line.get("shape")
    return shape if isinstance(shape, str) else None


def is_step_trace(trace: dict) -> bool:
    """
    Report whether a trace is a plotly staircase.

    Parameters
    ----------
    trace : dict
        The plotly trace dictionary.

    Returns
    -------
    bool
        True when the trace's ``line.shape`` is a stepping shape.
    """
    return is_step_shape(trace_line_shape(trace))


def step_direction_of(trace: dict) -> str | None:
    """
    Resolve the MAIDR ``stepDirection`` a trace authored.

    Parameters
    ----------
    trace : dict
        The plotly trace dictionary.

    Returns
    -------
    str or None
        One of ``"hv"``, ``"vh"``, ``"mid"``, or None when plotly's shape has
        no MAIDR equivalent (``vhv``) or none was authored.
    """
    shape = trace_line_shape(trace)
    return None if shape is None else STEP_SHAPE_DIRECTION.get(shape)


def group_by_direction(traces: list[dict]) -> list[list[dict]]:
    """
    Split step traces into groups that share one step convention.

    A MAIDR layer carries a single ``stepDirection`` for all of its series, so
    merging an ``hv`` trace with a ``vh`` one would describe one of them
    wrongly. Traces whose shape reports no direction (``vhv``) group together
    rather than being scattered across the directional groups.

    Insertion order is preserved both between and within groups, so the
    emitted layers follow the order plotly declared the traces in.

    Parameters
    ----------
    traces : list of dict
        The step traces on one subplot.

    Returns
    -------
    list of list of dict
        One inner list per distinct convention, each non-empty.
    """
    grouped: dict[str, list[dict]] = {}
    for trace in traces:
        # "" keys the shapes that report no direction, keeping them together
        # instead of merging them into whichever directional group came first.
        key = step_direction_of(trace) or ""
        grouped.setdefault(key, []).append(trace)
    return list(grouped.values())
