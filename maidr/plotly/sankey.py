from __future__ import annotations

from typing import Any

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list


class PlotlySankeyPlot(PlotlyPlot):
    """Extract data from a Plotly sankey trace.

    A sankey is weighted flow between nodes, and `FlowPoint` states one link
    as the two nodes it joins and how much moves: ``{source, target,
    value}``. Plotly states the same thing by *index* -- ``link.source`` and
    ``link.target`` point into ``node.label`` -- so the whole of the mapping
    is resolving those indices back to the names a reader is told.

    The links are emitted in the trace's own order. Measured against the
    ``__data__`` d3 binds onto each drawn ribbon, with values written out of
    order so a re-sort by magnitude would show: ``value=[3, 9, 5, 1]`` came
    back as indices 0, 1, 2, 3 in that order.
    """

    def __init__(
        self, trace: dict, layout: dict, *, addressable: bool = True, **kwargs: str
    ) -> None:
        super().__init__(trace, layout, PlotType.SANKEY, **kwargs)
        self._addressable = addressable

    def _get_selector(self) -> str:
        """Address the ribbons, when this figure's sankey can be picked out.

        ``.sankey .sankey-link`` matches one ``<path>`` per link, in the
        trace's own order.

        A figure holding **two** sankeys gets no selector, and that is a
        limit rather than an oversight. Measured: both ``.sankey`` groups
        are bare ``<g class="sankey">`` siblings under ``main-svg`` with no
        id and no data attribute -- they differ only by a ``transform``,
        which moves with the layout. ``:nth-of-type`` cannot separate them
        either, because it counts *every* ``<g>`` sibling and the two
        sankeys were the 15th and 16th: ``.sankey:nth-of-type(1)`` resolved
        to **0** elements.

        So a second sankey has no addressable geometry, and emitting a
        selector that matched both traces' ribbons would be worse than
        emitting none -- the resolved count would not equal either layer's
        link count, and both highlights would be dropped anyway. The layer
        still reads: its audio, braille and text are unaffected, which is
        the same honest outcome #145 established for a layer with nothing to
        point at.
        """
        return ".sankey .sankey-link" if self._addressable else ""

    def _extract_axes_data(self) -> dict:
        """Name the two dimensions a flow carries.

        A sankey draws no axes. The core announces a link as the pair of
        nodes it joins and the amount that moves, so the generic pair says
        what those are -- the stand-in a pie takes, in this chart's words.
        """
        return {
            MaidrKey.X: self._axis_config(label="Flow"),
            MaidrKey.Y: self._axis_config(label="Value"),
        }

    def _extract_plot_data(self) -> list[dict]:
        """One point per link, in the trace's own order.

        A link whose endpoint is not a node plotly could name is skipped.
        `FlowPoint` has no shape for a nameless end, and plotly draws
        nothing for an out-of-range index either -- so passing one on would
        announce a ribbon that is not on the screen.
        """
        node = self._trace.get("node") or {}
        link = self._trace.get("link") or {}

        labels = [self._to_native(label) for label in as_list(node.get("label"))]
        sources = as_list(link.get("source"))
        targets = as_list(link.get("target"))
        values = as_list(link.get("value"))

        count = min(len(sources), len(targets), len(values))
        points: list[dict] = []
        for index in range(count):
            source = _node_name(sources[index], labels)
            target = _node_name(targets[index], labels)
            value = _number(values[index])
            if source is None or target is None or value is None:
                continue
            points.append(
                {
                    MaidrKey.SOURCE: source,
                    MaidrKey.TARGET: target,
                    MaidrKey.VALUE: value,
                }
            )
        return points


def _node_name(index: Any, labels: list[Any]) -> Any:
    """Return the label an endpoint index points at, or None when it has none."""
    position = _number(index)
    if position is None or position != int(position):
        return None
    position = int(position)
    if 0 <= position < len(labels):
        return labels[position]
    return None


def _number(value: Any) -> float | None:
    """Coerce one of plotly's numbers, or None when it is not one."""
    value = PlotlyPlot._to_native(value)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
