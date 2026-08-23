from __future__ import annotations

from typing import Any

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list


def draws_a_dial(trace: dict) -> bool:
    """Report whether a plotly indicator draws a gauge this can read.

    Three things separate an indicator MAIDR can read from one it cannot,
    and all three were measured against ``gd._fullData[0]`` in Chromium:

    * ``mode="number"`` draws no dial at all -- no arc, no axis, and
      ``gauge.axis.range`` absent from the resolved trace. A `GaugePoint`
      needs a range to place its measure in, and a bare number is not a
      chart to navigate.
    * a gauge with no explicit ``axis.range`` still gets one, computed from
      the value: ``[0, 1.5 * value]``, with ``value = 0`` a special case at
      ``[-1, 1]``. Measured across 42 -> [0, 63], 100 -> [0, 150],
      7 -> [0, 10.5], 3.5 -> [0, 5.25], 0 -> [-1, 1].
    * that rule runs backwards for a negative value: -20 -> ``[0, -30]``,
      a dial whose upper end is below its lower one. `GaugePoint` names its
      two ends "lower" and "upper", so that pair is outside what the
      grammar describes, and such a chart is declined rather than emitted
      inverted.

    Parameters
    ----------
    trace : dict
        One trace of the figure.

    Returns
    -------
    bool
        True when the trace draws a dial with a range this can state.
    """
    if trace.get("type") != "indicator":
        return False

    # `mode`, not the presence of a `gauge` dict. `Figure.to_dict()` omits
    # `gauge` entirely when the author set nothing inside it, so
    # `go.Indicator(mode="gauge+number", value=42)` arrives with no `gauge`
    # key at all -- and it draws a full dial. Plotly's own default mode is
    # `"number"`, which is why an absent mode declines.
    if "gauge" not in str(trace.get("mode", "number")):
        return False

    gauge = trace.get("gauge")
    if isinstance(gauge, dict) and _explicit_range(gauge) is not None:
        return True

    value = _number(trace.get("value"))
    return value is not None and value >= 0


def _explicit_range(gauge: dict) -> tuple[float, float] | None:
    """Return the author's ``gauge.axis.range``, when they set one."""
    axis = gauge.get("axis")
    if not isinstance(axis, dict):
        return None
    bounds = [_number(bound) for bound in as_list(axis.get("range"))]
    if len(bounds) != 2 or any(bound is None for bound in bounds):
        return None
    return bounds[0], bounds[1]  # type: ignore[return-value]


def _number(value: Any) -> float | None:
    """Coerce one of plotly's numbers, or None when it is not one."""
    value = PlotlyPlot._to_native(value)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


class PlotlyGaugePlot(PlotlyPlot):
    """Extract data from a Plotly indicator trace that draws a gauge.

    A gauge is one measure against a dial, so its payload is a single
    `GaugePoint` rather than a list of them -- the one plot type here whose
    ``data`` is an object.

    ``gauge.threshold.value`` becomes the point's ``target``: that is what a
    bullet chart's marker is, and the core announces it alongside the
    measure precisely so "220 against a target of 200" is one sentence
    rather than two navigations.

    ``gauge.steps`` deliberately does **not** become ``bands``. A
    `GaugeBand` carries a required ``label`` -- it exists so a reader hears
    "in the 'ok' band" -- and a plotly step is a colour over a range with no
    name at all. Synthesising one would announce a name the chart does not
    carry, which is worse than announcing no band: the reader would have no
    way to know the word was ours.
    """

    def __init__(
        self, trace: dict, layout: dict, *, gauge_position: int = 0, **kwargs: str
    ) -> None:
        super().__init__(trace, layout, PlotType.GAUGE, **kwargs)
        self._gauge_position = gauge_position

    def _get_selector(self) -> str:
        """Address this indicator's drawn value arc.

        Measured in Chromium on two indicators sharing a figure:
        ``.indicatorlayer .value-arc`` matched both arcs, and
        ``> .trace:nth-child(k) .value-arc`` matched exactly the kth. The
        arc is the mark that moves with the measure -- the background arc,
        the outline and the tick marks are all frame.

        An indicator is drawn into a figure-level ``indicatorlayer`` under
        ``main-svg`` rather than into a subplot group, so the position among
        that layer's trace groups stands in for the subplot prefix, as it
        does for a pie.

        That position counts **every** indicator, not only the ones this
        reads. Plotly appends a ``.trace`` group for a `mode="number"`
        indicator too -- it has a number to draw, just no dial -- so
        numbering only the dial-drawing ones put the second gauge of
        `[gauge, number, gauge]` on ``nth-child(2)``, which is the bare
        number's group and holds no arc at all. Measured: that selector
        resolved to 0. The same lesson #395 records for boxes and
        candlesticks sharing a layer.
        """
        return (
            f".indicatorlayer > .trace:nth-child({self._gauge_position + 1}) "
            f".value-arc"
        )

    def _extract_axes_data(self) -> dict:
        """Name the measure's two dimensions.

        An indicator draws no cartesian axes, and the core reads
        ``this.xAxis`` for what the measure is called and ``this.yAxis`` for
        the measure itself. Plotly names neither, so the generic pair stands
        in -- the same fallback a pie takes, in this chart's own words.
        """
        return {
            MaidrKey.X: self._axis_config(label="Measure"),
            MaidrKey.Y: self._axis_config(label="Value"),
        }

    def _extract_plot_data(self) -> dict:
        """Return the single ``GaugePoint`` this dial states.

        The range is the author's when they set one and plotly's computed
        default otherwise -- see :func:`draws_a_dial` for the measurements
        behind that rule and for why a negative value with no explicit range
        never reaches here.
        """
        gauge = self._trace.get("gauge") or {}
        value = _number(self._trace.get("value")) or 0.0

        bounds = _explicit_range(gauge) if gauge else None
        if bounds is None:
            bounds = (-1.0, 1.0) if value == 0 else (0.0, 1.5 * value)

        point: dict = {
            MaidrKey.VALUE: value,
            MaidrKey.MIN: bounds[0],
            MaidrKey.MAX: bounds[1],
        }

        label = self._indicator_title()
        if label:
            point[MaidrKey.LABEL] = label

        threshold = gauge.get("threshold")
        if isinstance(threshold, dict):
            target = _number(threshold.get("value"))
            if target is not None:
                point[MaidrKey.TARGET] = target

        return point

    def _indicator_title(self) -> str:
        """Return what the indicator calls its measure, or an empty string.

        ``title`` on an indicator is the measure's own name -- "Speed",
        "Profit" -- rather than the figure's, which is why it becomes the
        point's ``label`` rather than the layer's title.
        """
        title = self._trace.get("title")
        if isinstance(title, dict):
            title = title.get("text", "")
        return str(title) if title else ""
