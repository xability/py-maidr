"""Multiple plotly histogram traces that share a subplot, and a bin grid.

Plotly stacks or dodges histogram traces on one axis pair exactly as it does
bar traces, and bins them **jointly**: the grid is computed once from every
trace's values together, and each trace is then binned on it. Reading each
trace on a grid of its own announced bins the chart never draws (#394).
"""

from __future__ import annotations

import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.histogram import (
    _UNDEFINED_WHEN_EMPTY,
    _occupied_span,
    aggregate_bins,
    apply_histnorm,
    as_numeric,
    binned_axis,
    compute_bin_edges,
    paired_arrays,
)
from maidr.plotly.plotly_plot import PlotlyPlot


def is_histogram_trace(trace: dict) -> bool:
    """Whether *trace* is a histogram."""
    return trace.get("type") == "histogram"


def group_bin_spec(traces: list[dict], binned: str) -> tuple[dict | None, int | None]:
    """The bin spec governing a group, from whichever trace carries one.

    Not "the first trace's spec". Measured: with ``xbins=dict(size=3)`` on the
    *second* of two traces, plotly resolves the first trace's spec to
    ``{start: 0, end: 6}`` and the second's to ``{size: 3}``, and bins **both**
    at width 3 -- output identical to putting the same spec on the first
    trace, and different from the width 2 the pair autobins to.

    Parameters
    ----------
    traces : list[dict]
        The group's histogram traces, in declaration order.
    binned : str
        ``"x"`` or ``"y"``, the axis being binned.

    Returns
    -------
    tuple[dict | None, int | None]
        The ``bins`` dict and the ``nbins`` hint, each from the first trace
        that supplies one.
    """
    bins: dict | None = None
    nbins: int | None = None
    for trace in traces:
        if bins is None:
            bins = trace.get(f"{binned}bins") or None
        if nbins is None:
            nbins = trace.get(f"nbins{binned}")
    return bins, nbins


class PlotlyGroupedHistogramPlot(PlotlyPlot):
    """Histogram traces plotly draws as one stack or one dodged group.

    Emits the same ``list[list[dict]]`` shape as
    :class:`~maidr.plotly.grouped_bar.PlotlyGroupedBarPlot`: one inner list per
    trace, each item carrying ``x`` (the bin centre), ``z`` (the trace's name)
    and ``y`` (its value). The plot type decides how the core reads them, and
    is worked out from ``barmode``/``barnorm`` by
    :meth:`~maidr.plotly.plotly_maidr.PlotlyMaidr._extract_plots`, the same way
    it is for bars.

    Merging also settles the highlight. Left as separate layers, every
    histogram in a subplot emitted the identical selector -- ``.trace.bars
    .point > path`` matches every bar in the panel -- so each layer
    highlighted its neighbours' bars as well as its own. One layer holding
    every series is what that selector actually describes.
    """

    def __init__(
        self,
        traces: list[dict],
        layout: dict,
        plot_type: PlotType,
        **kwargs: str,
    ) -> None:
        # The first trace stands for the group when the base class needs a
        # title or an axis pair, as the grouped bar and multi-box layers do.
        super().__init__(traces[0], layout, plot_type, **kwargs)
        self._traces = traces
        self._binned = binned_axis(traces[0])

    @property
    def _horizontal(self) -> bool:
        return self._binned == "y"

    def render(self) -> dict:
        """Add ``orientation`` to the base schema."""
        schema = super().render()
        schema[MaidrKey.ORIENTATION] = "horz" if self._horizontal else "vert"
        return schema

    def _get_selector(self) -> str:
        return f"{self._subplot_css_prefix()}.trace.bars .point > path"

    def _shared_edges(self, samples: list[np.ndarray]) -> np.ndarray | None:
        """One grid, from every trace's values together.

        The union is what makes this joint rather than per-trace: fed the two
        samples of ``px.histogram(frame, x="v", color="h")`` separately the
        existing port returns widths of 0.2 and 1.0, and fed their union it
        returns plotly's own ``size=1, start=-2, end=12``.
        """
        pooled = np.concatenate([s for s in samples if s.size])
        if not pooled.size:
            return None
        bins, nbins = group_bin_spec(self._traces, self._binned)
        return compute_bin_edges(pooled, bins, nbins)

    def _extract_plot_data(self) -> list[list[dict]]:
        samples: list[np.ndarray] = []
        values: list[list | None] = []
        for trace in self._traces:
            sample, other = paired_arrays(trace, self._binned)
            if sample is None:
                samples.append(np.empty(0))
                values.append(None)
                continue
            try:
                samples.append(np.array(sample, dtype=float))
            except (ValueError, TypeError):
                # A categorical group is drawn as a count bar chart rather
                # than binned, and is a different layer shape entirely. The
                # factory handles those one trace at a time; declining here
                # leaves them to it rather than half-describing them.
                return []
            values.append(other)

        edges = self._shared_edges(samples)
        if edges is None:
            return []

        histfunc = self._traces[0].get("histfunc") or "count"
        histnorm = self._traces[0].get("histnorm")
        drop_empty = histfunc in _UNDEFINED_WHEN_EMPTY and not histnorm
        widths = np.diff(edges)

        data: list[list[dict]] = []
        for trace, sample, other in zip(self._traces, samples, values):
            counts, _ = np.histogram(sample, bins=edges)
            first, last = _occupied_span(counts)
            if first is None:
                # A trace with nothing in the grid still holds a place in the
                # group, so the series' names stay paired with their data.
                data.append([])
                continue

            if other is None or histfunc == "count":
                measured, present = counts.astype(float), counts > 0
            else:
                measured, present = aggregate_bins(
                    _bin_assignment(sample, edges),
                    as_numeric(other),
                    len(counts),
                    histfunc,
                )

            bar_values = apply_histnorm(measured, widths, histnorm)
            fill = str(trace.get("name", ""))

            series: list[dict] = []
            for index in range(first, last + 1):
                if drop_empty and not present[index]:
                    continue
                low = float(edges[index])
                high = float(edges[index + 1])
                value = float(bar_values[index])
                series.append(
                    {
                        MaidrKey.X.value: (low + high) / 2,
                        MaidrKey.Z.value: fill,
                        MaidrKey.Y.value: (
                            int(value) if value == int(value) else value
                        ),
                    }
                )
            data.append(series)

        return data


def _bin_assignment(arr: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Which bin each observation falls in, or ``-1`` for none.

    The same convention :meth:`PlotlyHistogramPlot._bin_assignment` uses, so a
    grouped layer and a single one cannot disagree about where a value sits.
    """
    from maidr.plotly.histogram import PlotlyHistogramPlot

    return PlotlyHistogramPlot._bin_assignment(arr, edges)
