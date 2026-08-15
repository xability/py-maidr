from __future__ import annotations

from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list

#: The two plotly trace types that carry an OHLC series. They differ only in
#: how plotly draws a bar -- a filled body for ``candlestick``, a tick on
#: either side of a vertical range for ``ohlc`` -- and not at all in what the
#: numbers mean, so both are read as the same MAIDR layer.
OHLC_TRACE_TYPES = frozenset({"candlestick", "ohlc"})

#: The DOM layer each trace type draws into, measured in a browser rather than
#: assumed: a ``candlestick`` shares plotly's box machinery (``g.boxlayer`` >
#: ``g.trace.boxes`` > ``path.box``) while an ``ohlc`` has a layer of its own
#: (``g.ohlclayer`` > ``g.trace.ohlc`` > ``path``).
_LAYER_OF = {"candlestick": "boxlayer", "ohlc": "ohlclayer"}
_GROUP_OF = {"candlestick": ".trace.boxes", "ohlc": ".trace.ohlc"}
_MARK_OF = {"candlestick": "path.box", "ohlc": "> path"}

#: Trace types that share ``g.boxlayer`` and so count towards a candlestick's
#: position within it. A ``go.Violin`` draws into ``g.violinlayer`` and a
#: scatter into ``g.scatterlayer``, so neither shifts the count.
_BOXLAYER_TRACE_TYPES = frozenset({"box", "candlestick"})


def is_ohlc_trace(trace: dict) -> bool:
    """
    Return whether *trace* carries an open/high/low/close series.

    Parameters
    ----------
    trace : dict
        A plotly trace dictionary.

    Returns
    -------
    bool
        ``True`` for a ``candlestick`` or ``ohlc`` trace.
    """
    return trace.get("type") in OHLC_TRACE_TYPES


def layer_position(traces: list[dict], trace: dict) -> int:
    """
    Return *trace*'s zero-based position among its DOM layer-mates.

    Plotly appends one ``<g class="trace ...">`` per trace to the layer its
    type draws into, in the order the traces were declared, so a trace's
    position among the traces sharing that layer is its ``nth-child`` index.
    Counting all traces instead would skip a child for every scatter or violin
    beside it and scope the selector to nothing.

    Parameters
    ----------
    traces : list of dict
        The subplot's *drawn* traces, in declaration order. A hidden trace
        gets no group in the layer, so passing one would push this trace's
        index onto a group that does not exist.
    trace : dict
        The trace to locate.

    Returns
    -------
    int
        The zero-based position among traces drawing into the same layer.
    """
    kind = trace.get("type")
    if kind in _BOXLAYER_TRACE_TYPES:
        # Both directions, not just the candlestick's. `go.Box` and
        # `go.Candlestick` draw into the same `g.boxlayer`, so each shifts
        # the other's group index. Counting only same-typed traces was
        # symmetric-looking and wrong in one direction: a candlestick
        # counted the boxes beside it, while a box ignored the candlestick
        # and claimed the group the candlestick had already taken (#395).
        mates = _BOXLAYER_TRACE_TYPES
    else:
        mates = frozenset({kind}) if kind else frozenset()

    position = 0
    for candidate in traces:
        if candidate is trace:
            return position
        if candidate.get("type") in mates:
            position += 1
    return position


class PlotlyCandlestickPlot(PlotlyPlot):
    """Extract data from a Plotly ``candlestick`` or ``ohlc`` trace.

    Both types state every number they draw: ``open``, ``high``, ``low`` and
    ``close`` arrive as arrays on the trace itself, so nothing here is
    inferred from the drawing.

    ``trend`` and ``volatility`` are deliberately not emitted. The MAIDR core
    derives both from the OHLC values and overwrites whatever a producer
    sends, so a second copy here could only ever disagree with the one that
    is used. The matplotlib :class:`~maidr.core.plot.candlestick.CandlestickPlot`
    omits them for the same reason.

    ``volume`` is likewise absent: neither plotly type carries it, and the
    core announces no volume section, so there is nothing to invent.
    """

    def __init__(
        self,
        trace: dict,
        layout: dict,
        *,
        layer_position: int = 0,
        **kwargs: str,
    ) -> None:
        """
        Parameters
        ----------
        trace : dict
            A plotly ``candlestick`` or ``ohlc`` trace dictionary.
        layout : dict
            The plotly layout dictionary.
        layer_position : int, default=0
            The trace's zero-based position among the traces drawing into its
            DOM layer. Scopes the selector to this trace's marks.
        **kwargs : str
            ``xaxis_name`` / ``yaxis_name``, forwarded to :class:`PlotlyPlot`.
        """
        super().__init__(trace, layout, PlotType.CANDLESTICK, **kwargs)
        self._layer_position = layer_position

    def _get_selector(self) -> str:
        """Return a CSS selector for this trace's marks.

        Scoped three ways, each for a measured reason.

        ``.subplot.<id>`` excludes the **rangeslider**. Plotly gives a
        candlestick chart one by default, and it holds a complete second copy
        of the plot -- ``g.rangeslider-rangeplot`` -- so an unscoped selector
        matches every mark twice and the highlight for the second half of the
        candles lands in the thumbnail.

        ``nth-child`` picks this trace out of its layer. Two candlestick
        traces put two ``g.trace.boxes`` groups in the same ``g.boxlayer``,
        and a ``go.Box`` beside a candlestick lands there too and draws its
        own ``path.box`` -- so without a position the selector matches both
        traces' marks and every index after the first names the wrong bar.
        """
        kind = self._trace.get("type", "candlestick")
        layer = _LAYER_OF.get(kind, "boxlayer")
        group = _GROUP_OF.get(kind, ".trace.boxes")
        mark = _MARK_OF.get(kind, "path.box")
        return (
            f"{self._subplot_css_prefix()}.{layer} > "
            f"{group}:nth-child({self._layer_position + 1}) {mark}"
        )

    def _extract_plot_data(self) -> list[dict]:
        """
        Return one entry per candle, in the order plotly declares them.

        Returns
        -------
        list of dict
            ``{"value", "open", "high", "low", "close"}`` per candle. The keys
            are plain strings rather than :class:`MaidrKey` members because
            the OHLC vocabulary has none, and the matplotlib emitter spells
            them the same way.
        """
        opens = as_list(self._trace.get("open"))
        highs = as_list(self._trace.get("high"))
        lows = as_list(self._trace.get("low"))
        closes = as_list(self._trace.get("close"))
        values = as_list(self._trace.get("x"))

        # The shortest array decides the count. Plotly draws only as many bars
        # as it has all four numbers for, so reading past that would announce
        # candles it never drew.
        count = min(len(opens), len(highs), len(lows), len(closes))

        candles = []
        for index in range(count):
            try:
                candle = {
                    "open": float(opens[index]),
                    "high": float(highs[index]),
                    "low": float(lows[index]),
                    "close": float(closes[index]),
                }
            except (TypeError, ValueError):
                # A gap plotly leaves blank. Skipping keeps the announced
                # candles aligned with the drawn ones, which a placeholder
                # would not.
                continue

            # Positions default to the index when the author gave no `x`,
            # which is what plotly labels the axis with in that case.
            label = values[index] if index < len(values) else index
            candle["value"] = str(self._to_native(label))
            candles.append(candle)

        return candles
