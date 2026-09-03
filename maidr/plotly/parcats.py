from __future__ import annotations

import numbers

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list

#: What separates one dimension's level from another's in a node name.
#: A parallel-sets diagram routinely repeats a level name across dimensions --
#: "yes" under `Survived` and "yes" under `Boarded` -- and the grammar derives
#: its nodes from the flows, so two nodes named alike *are* one node. Naming a
#: node by its dimension is what keeps them apart, and it is also what a
#: reader needs to hear: "Survived: yes" says which question was answered.
_NODE_SEPARATOR = ": "


class PlotlyParcatsPlot(PlotlyPlot):
    """Extract data from a Plotly ``parcats`` trace.

    A parallel *sets* diagram: categorical dimensions side by side, with a
    ribbon between adjacent ones for every combination that occurs, drawn at
    a width proportional to how often it does. The core reads it as
    `ALLUVIAL`, which shares `FlowTrace` with `SANKEY` and `CHORD` -- one
    weighted flow between two named nodes, the nodes derived from the flows.

    So a ribbon spanning several dimensions becomes one flow **per adjacent
    pair**. That is what the grammar's unit is, and it is also the reading:
    what a parallel-sets diagram shows is how a population is re-divided at
    each step, and each step is a pair.
    """

    def __init__(self, trace: dict, layout: dict, **kwargs: str) -> None:
        super().__init__(trace, layout, PlotType.ALLUVIAL, **kwargs)

    def _get_selector(self) -> list[str]:
        """No selector: the drawn order is plotly's, and it is not derivable.

        Measured in Chromium on a five-row trace whose first and fifth rows
        share a combination. Plotly merges them -- four ``path`` elements for
        five rows -- and, decisively, writes them in **its own layout order**
        rather than the declaration order: the bound ``key`` values in
        document order were ``0, 2, 1, 3``, carrying counts ``8, 2, 1, 4``.

        So ``:nth-of-type(k)`` addresses whichever ribbon plotly happened to
        place kth, which cannot be computed from the trace offline. A list
        built in the data's order would resolve to real elements and to the
        *wrong* ones -- a highlight that is confidently incorrect, which is
        worse than none at all.

        The layer therefore ships without a highlight and keeps its audio,
        braille and text: the outcome #145 established for a layer with
        nothing it can point at.
        """
        return []

    def _extract_axes_data(self) -> dict:
        """A flow layer names no axes.

        `FlowTrace` announces a flow as its two nodes and its weight, and the
        nodes carry their own dimension names. There is no x or y for a
        reader to be told about, and inventing a pair would put words in a
        chart that has neither.
        """
        return {}

    def _extract_plot_data(self) -> list[dict]:
        """One flow per adjacent pair of dimensions, per combination.

        Two things are aggregated here, and both were measured rather than
        assumed:

        * **Plotly merges duplicate combinations.** Five rows whose first and
          fifth share a combination drew four ribbons, the shared one at the
          summed count of 8. Emitting the rows unaggregated would announce
          two flows where the chart draws one.
        * **A hidden dimension is not a column.** ``visible: False`` takes a
          dimension out of the drawing, so a flow through it would join two
          nodes the chart never places side by side.

        ``counts`` weights each row and defaults to one per row, which is
        what plotly does with it. It is ``arrayOk``, so a scalar is the
        one-value-for-every-row spelling and weights each row at that value.
        A row longer than the shortest dimension is dropped, because it has
        no value on every axis and so no ribbon.
        """
        columns = [
            dimension
            for dimension in as_list(self._trace.get("dimensions"))
            if isinstance(dimension, dict) and dimension.get("visible") is not False
        ]
        if not columns:
            # Only the *no* columns case needs saying: `min()` over an empty
            # sequence raises. One column needs no guard -- there is no
            # adjacent pair, so the loop below yields nothing and #636's
            # payload guard drops the layer, which is the same answer arrived
            # at once rather than twice.
            return []

        values = [as_list(column.get("values")) for column in columns]
        rows = min(len(column) for column in values)
        if rows == 0:
            return []

        labels = [_column_name(column, index) for index, column in enumerate(columns)]
        raw_counts = self._trace.get("counts")
        # `numbers.Real` takes a numpy scalar too, which is what `to_dict()`
        # hands back for one; a bool is a Real that no author means as a
        # weight, and `as_list` turns a scalar into nothing, not into a row.
        if isinstance(raw_counts, numbers.Real) and not isinstance(raw_counts, bool):
            weights = [float(raw_counts)] * rows
        else:
            weights = as_list(raw_counts) or [1] * rows

        flows: dict[tuple[str, str], float] = {}
        order: list[tuple[str, str]] = []
        for step in range(len(columns) - 1):
            for row in range(rows):
                edge = (
                    _node_name(labels[step], values[step][row]),
                    _node_name(labels[step + 1], values[step + 1][row]),
                )
                weight = weights[row] if row < len(weights) else 1
                if edge not in flows:
                    flows[edge] = 0.0
                    order.append(edge)
                flows[edge] += float(self._to_native(weight) or 0)

        return [
            {
                MaidrKey.SOURCE: source,
                MaidrKey.TARGET: target,
                MaidrKey.VALUE: flows[(source, target)],
            }
            for source, target in order
        ]


def is_parcats_trace(trace: dict) -> bool:
    """Report whether a trace is a parallel sets diagram."""
    return trace.get("type") == "parcats"


def _node_name(dimension: str, level: object) -> str:
    """Name one node by the dimension it belongs to and the level it is."""
    return f"{dimension}{_NODE_SEPARATOR}{level}"


def _column_name(dimension: dict, index: int) -> str:
    """Name one dimension, falling back to its position when unnamed.

    ``label`` is optional and may be written empty, and plotly draws an
    unnamed dimension with a blank title. A blank half of a node name reaches
    the reader as ``": yes"``, which says less than the position does.
    """
    label = dimension.get("label")
    if label is None:
        return str(index + 1)
    label = str(label)
    return label if label else str(index + 1)
