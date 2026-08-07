from __future__ import annotations

import re
import uuid
from abc import ABC, abstractmethod
from typing import Any

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.step_shape import renders_through_webgl


class PlotlyPlot(ABC):
    """
    Abstract base class for Plotly plots managed by the MAIDR system.

    Parameters
    ----------
    trace : dict
        The Plotly trace dictionary containing plot data.
    layout : dict
        The Plotly layout dictionary containing axes and title info.
    plot_type : PlotType
        The type of the plot to be created, as defined in the PlotType enum.
    """

    def __init__(
        self,
        trace: dict,
        layout: dict,
        plot_type: PlotType,
        *,
        xaxis_name: str = "xaxis",
        yaxis_name: str = "yaxis",
    ) -> None:
        self._trace = trace
        self._layout = layout
        self.type = plot_type
        self._xaxis_name = xaxis_name
        self._yaxis_name = yaxis_name
        self.row_index: int = 0
        self.col_index: int = 0
        self._schema: dict = {}

    @staticmethod
    def _to_native(val: Any) -> Any:
        """Convert numpy scalars to native Python types.

        Parameters
        ----------
        val : Any
            The value to convert.

        Returns
        -------
        Any
            A native Python type if the input was a numpy scalar,
            otherwise the original value.
        """
        if hasattr(val, "item"):
            return val.item()
        return val

    def render(self) -> dict:
        """Generate the MAIDR schema for this plot layer."""
        data = self._extract_plot_data()
        schema = {
            MaidrKey.ID: str(uuid.uuid4()),
            MaidrKey.TYPE: self.type,
            MaidrKey.TITLE: self._get_title(),
            MaidrKey.AXES: self._extract_axes_data(),
            MaidrKey.DATA: data,
        }
        selector = self._get_selector()
        if selector:
            schema[MaidrKey.SELECTOR] = selector
        return schema

    def _subplot_css_prefix(self) -> str:
        """Return a CSS prefix that scopes selectors to this subplot.

        Plotly renders each subplot inside a ``<g class="subplot xy">``
        (or ``x2y2``, ``x3y3``, …) element.  This method converts the
        stored axis names into the corresponding CSS selector prefix so
        that selectors only match elements within a single subplot.
        """
        # "xaxis" -> "x", "xaxis2" -> "x2", "xaxis3" -> "x3"
        x_ref = self._xaxis_name.replace("xaxis", "x")
        y_ref = self._yaxis_name.replace("yaxis", "y")
        subplot_id = f"{x_ref}{y_ref}"
        return f".subplot.{subplot_id} "

    def _scatter_line_selector(self, position: int) -> str:
        """
        Return the selector for one scatter trace's rendered line path.

        ``nth-child`` counts within the subplot's ``scatterlayer``, which
        holds *every* scatter-family trace on the subplot. So the index has
        to be a trace's position there, never its position within whichever
        MAIDR layer it was grouped into. Those two agree only while one layer
        owns every scatter trace on the subplot — which stopped being true
        once step traces were split out into their own layers.

        Parameters
        ----------
        position : int
            The trace's zero-based position among the subplot's
            scatter-family traces.

        Returns
        -------
        str
            A CSS selector scoped to this subplot and that one trace.
        """
        return (
            f"{self._subplot_css_prefix()}.scatterlayer > "
            f".trace.scatter:nth-child({position + 1}) path.js-line"
        )

    def _scatter_line_selectors(
        self, traces: list[dict], positions: list[int]
    ) -> list[str]:
        """
        Return one line selector per trace, or none when they are not SVG.

        A WebGL trace has no element to address, so a selector built for it
        would resolve to zero elements and the highlight would simply not
        appear — with nothing in the output to say why. Emitting no selector
        at all says the same thing honestly: this layer has no highlightable
        geometry, while its audio, braille and text are unaffected.

        The choice is all-or-nothing per layer rather than per trace, because
        the emitted list is positional — the frontend pairs selector *i* with
        series *i*. Dropping one entry from the middle would slide every later
        series onto the wrong element, which is worse than no highlight.

        Parameters
        ----------
        traces : list of dict
            The traces this layer covers, in series order.
        positions : list of int
            Each trace's zero-based position among the subplot's
            scatter-family traces, in the same order.

        Returns
        -------
        list of str
            One selector per series, or an empty list for a WebGL layer.
        """
        # `any`, not `all`: the renderer split upstream already guarantees a
        # homogeneous layer, so the two agree today. If that invariant ever
        # breaks, `any` fails closed -- no highlight -- while `all` would emit
        # a full set of selectors for a layer that is partly canvas, putting
        # every series after the gl trace on the wrong element.
        if any(renders_through_webgl(trace) for trace in traces):
            return []
        return [self._scatter_line_selector(position) for position in positions]

    @staticmethod
    def _validate_scatter_positions(positions: list[int], trace_count: int) -> None:
        """
        Reject a position list that cannot describe these traces.

        Requiring positions closes the hole where a caller supplied none. It
        leaves a second one with the same failure mode: a list that is simply
        wrong. The emitted selector list is positional — the frontend pairs
        selector *i* with series *i* — so a length mismatch slides every later
        series onto another element, a negative index builds ``nth-child(0)``
        or lower and matches nothing, and a repeat points two series at one
        element. None of those raise on their own; they highlight the wrong
        geometry, which is the outcome this whole parameter exists to prevent.

        The guard is not exhaustive, and cannot be: a position beyond the
        subplot's actual scatter-trace count is well-formed by every rule
        here, so ``scatter_position=99`` on a two-trace subplot constructs
        happily and simply matches nothing at render time. Only
        ``PlotlyMaidr._extract_plots`` knows that total, so an upper bound
        would have to live there rather than in this class.

        Parameters
        ----------
        positions : list of int
            Zero-based positions among the subplot's scatter-family traces.
        trace_count : int
            How many traces this layer covers.

        Raises
        ------
        TypeError
            If ``positions`` is not a list/tuple, or any entry is not an int.
        ValueError
            If the length disagrees with ``trace_count``, or any position is
            negative or repeated.
        """
        # Type-checked before anything else, because the value most likely to
        # arrive here wrongly is ``None`` -- it was this parameter's default
        # until it became required, so a caller migrating off that default is
        # exactly who passes it explicitly. Left unchecked it surfaced as
        # "object of type 'NoneType' has no len()" or "'<' not supported
        # between instances of 'NoneType' and 'int'", neither of which names
        # the argument at fault.
        if not isinstance(positions, (list, tuple)):
            raise TypeError(
                f"scatter positions must be a list of int, got {positions!r}"
            )

        if len(positions) != trace_count:
            plural = "" if trace_count == 1 else "s"
            raise ValueError(
                f"expected {trace_count} scatter position{plural} to match "
                f"{trace_count} trace{plural}, got {len(positions)}: {positions}"
            )
        if any(not isinstance(position, int) for position in positions):
            raise TypeError(
                f"scatter positions must all be int, got {positions!r}"
            )

        if any(position < 0 for position in positions):
            raise ValueError(f"scatter positions must be >= 0, got {positions}")
        if len(set(positions)) != len(positions):
            raise ValueError(f"scatter positions must be unique, got {positions}")

    def _get_selector(self) -> str:
        """Return a CSS selector for Plotly SVG elements."""
        return ""

    def _get_title(self) -> str:
        """Extract the plot title from the layout.

        For subplots created with ``make_subplots(subplot_titles=...)``,
        Plotly stores the per-subplot titles as annotations.  This method
        matches annotations to the current subplot's y-axis domain so
        each subplot gets its own title instead of the figure-level one.
        """
        subplot_title = self._get_subplot_annotation_title()
        if subplot_title:
            return subplot_title

        title = self._layout.get("title", "")
        if isinstance(title, dict):
            return title.get("text", "")
        return str(title) if title else ""

    def _get_subplot_annotation_title(self) -> str | None:
        """Find the annotation that serves as this subplot's title.

        Plotly ``make_subplots`` places title annotations at the top of
        each subplot's y-axis domain.  This matches annotations by
        checking if their ``y`` position is near the top of this
        subplot's y-axis domain.
        """
        annotations = self._layout.get("annotations", [])
        if not annotations:
            return None

        yaxis = self._layout.get(self._yaxis_name, {})
        xaxis = self._layout.get(self._xaxis_name, {})
        y_domain = yaxis.get("domain", [0, 1])
        x_domain = xaxis.get("domain", [0, 1])
        y_top = y_domain[1]
        x_mid = (x_domain[0] + x_domain[1]) / 2

        for ann in annotations:
            if ann.get("xref") != "paper" or ann.get("yref") != "paper":
                continue
            ann_y = ann.get("y", 0)
            ann_x = ann.get("x", 0)
            # Subplot title annotations sit just above the y-domain top
            if abs(ann_y - y_top) < 0.05 and abs(ann_x - x_mid) < 0.1:
                text = ann.get("text", "")
                if text:
                    return text
        return None

    @staticmethod
    def _axis_config(
        label: str | None = None,
        *,
        min: float | None = None,
        max: float | None = None,
        tick_step: float | None = None,
        format: dict | None = None,
    ) -> dict:
        """Build a canonical per-axis ``AxisConfig`` dict (only non-None keys)."""
        cfg: dict = {}
        if label is not None:
            cfg[MaidrKey.LABEL] = label
        if min is not None:
            cfg[MaidrKey.MIN] = min
        if max is not None:
            cfg[MaidrKey.MAX] = max
        if tick_step is not None:
            cfg[MaidrKey.TICK_STEP] = tick_step
        if format is not None:
            cfg[MaidrKey.FORMAT] = format
        return cfg

    def _extract_axes_data(self) -> dict:
        """Extract axes labels and format configuration as per-axis
        ``AxisConfig`` objects.

        ``format`` is nested inside each ``AxisConfig`` — never emitted as a
        sibling of ``x``/``y``/``z``.
        """
        xaxis = self._layout.get(self._xaxis_name, {})
        yaxis = self._layout.get(self._yaxis_name, {})

        x_label = xaxis.get("title", "")
        if isinstance(x_label, dict):
            x_label = x_label.get("text", "")

        y_label = yaxis.get("title", "")
        if isinstance(y_label, dict):
            y_label = y_label.get("text", "")

        format_config = self._extract_format(xaxis, yaxis) or {}

        return {
            MaidrKey.X: self._axis_config(
                label=str(x_label) if x_label else "X",
                format=format_config.get("x"),
            ),
            MaidrKey.Y: self._axis_config(
                label=str(y_label) if y_label else "Y",
                format=format_config.get("y"),
            ),
        }

    @staticmethod
    def _extract_format(
        xaxis: dict, yaxis: dict
    ) -> dict[str, dict[str, Any]] | None:
        """Extract format configuration from Plotly axis settings.

        Parses ``tickformat``, ``tickprefix``, and ``ticksuffix`` from
        each axis and converts to MAIDR-compatible format dicts.
        """
        result: dict[str, dict[str, Any]] = {}

        x_fmt = PlotlyPlot._parse_axis_format(xaxis)
        if x_fmt:
            result["x"] = x_fmt

        y_fmt = PlotlyPlot._parse_axis_format(yaxis)
        if y_fmt:
            result["y"] = y_fmt

        return result if result else None

    @staticmethod
    def _parse_axis_format(axis: dict) -> dict[str, Any] | None:
        """Parse a single Plotly axis dict into a MAIDR format config.

        Handles Plotly's d3-format ``tickformat`` strings as well as
        ``tickprefix`` / ``ticksuffix`` for currency and percent.
        """
        tickformat = axis.get("tickformat", "")
        prefix = axis.get("tickprefix", "")
        suffix = axis.get("ticksuffix", "")

        # Check for date axis type even without tickformat/prefix/suffix
        if not tickformat and not prefix and not suffix:
            if axis.get("type") == "date":
                return {"type": "date", "dateFormat": None}
            return None

        # Currency via prefix ($, €, £, ¥)
        currency_map = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
        for symbol, code in currency_map.items():
            if symbol in prefix or symbol in tickformat:
                decimals = _extract_decimals(tickformat)
                return {"type": "currency", "decimals": decimals, "currency": code}

        # Percent via suffix or tickformat
        if suffix == "%" or (tickformat and "%" in tickformat):
            decimals = _extract_decimals(tickformat)
            return {"type": "percent", "decimals": decimals}

        # Scientific notation
        if tickformat and re.search(r"\.?\d*[eE]", tickformat):
            decimals = _extract_decimals(tickformat)
            return {"type": "scientific", "decimals": decimals}

        # Number with comma separator
        if tickformat and "," in tickformat:
            decimals = _extract_decimals(tickformat)
            return {"type": "number", "decimals": decimals}

        # Fixed decimal (e.g., ".2f")
        match = re.search(r"\.(\d+)f", tickformat) if tickformat else None
        if match:
            return {"type": "fixed", "decimals": int(match.group(1))}

        # Date format
        if axis.get("type") == "date":
            return {"type": "date", "dateFormat": tickformat or None}

        return None

    @abstractmethod
    def _extract_plot_data(self) -> list | dict:
        """Extract specific data from the Plotly trace."""
        raise NotImplementedError()

    @property
    def schema(self) -> dict:
        """Return the MAIDR schema of the plot as a dictionary.

        The emitted ``axes`` payload follows the canonical per-axis form —
        keys ⊆ ``{x, y, z}``; each value is an ``AxisConfig`` dict with
        optional ``label``, ``min``, ``max``, ``tickStep``, and ``format``
        fields. ``format``/``min``/``max``/``tickStep``/``fill``/``level``
        never appear as siblings of ``x``/``y``/``z``.
        """
        if not self._schema:
            self._schema = self.render()
        return self._schema


def _extract_decimals(fmt: str) -> int | None:
    """Extract decimal places from a d3-format / Plotly tickformat string."""
    if not fmt:
        return None
    match = re.search(r"\.(\d+)", fmt)
    return int(match.group(1)) if match else None
