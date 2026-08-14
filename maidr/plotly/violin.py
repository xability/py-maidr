"""Read a plotly violin trace as the `violin_box` + `violin_kde` layer pair.

A violin is announced as two layers, matching the matplotlib path: the box
summarises the distribution, and the KDE is the shape the chart actually
draws. Every violin on a subplot shares one pair, however many traces they
came from -- the same grouping the browser-side plotly adapter uses.

Plotly computes the density in the browser, so the curve is not in the Python
figure and has to be recomputed. :mod:`maidr.plotly.violin_stats` ports
plotly's own rules for that and is checked against plotly's `calcdata`; see
its docstring for the measured agreement.
"""

from __future__ import annotations

from typing import Any, NamedTuple

import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list
from maidr.plotly.violin_stats import ViolinStats, violin_stats

#: The trace type this module reads.
VIOLIN_TRACE_TYPE = "violin"

#: What plotly calls a horizontal violin: values along x, categories up y.
_HORIZONTAL = "h"

def is_violin_trace(trace: dict) -> bool:
    """
    Return whether *trace* is a plotly violin.

    Parameters
    ----------
    trace : dict
        A plotly trace dictionary.

    Returns
    -------
    bool
        ``True`` for a ``violin`` trace.
    """
    return trace.get("type") == VIOLIN_TRACE_TYPE


class Violin(NamedTuple):
    """One violin: a labelled sample, with selectors for what plotly drew.

    Attributes
    ----------
    label : str
        What the violin is called -- its category, or the trace name when the
        trace draws only one.
    stats : ViolinStats
        The statistics and density curve for this violin's sample.
    kde_selector : str
        Addresses the violin's outline.
    box_selector : str
        Addresses the inner box. Written whether or not this trace draws one:
        the position holds no ``path.box`` otherwise, so the selector finds
        nothing and leaves the violins that do have one alone.
    mean_selector : str or None
        Addresses the mean line, when the trace draws one. ``None`` otherwise,
        which is what keeps the box layer from offering a section for a mark
        that is not on the chart.
    has_box : bool
        Whether this trace draws the inner box. Decides whether the layer
        emits selectors at all -- a layer of violins that drew no boxes has
        nothing to highlight.
    """

    label: str
    stats: ViolinStats
    kde_selector: str
    box_selector: str
    mean_selector: str | None
    has_box: bool


def _grouped(labels: list, values: list) -> list[tuple[str, np.ndarray]]:
    """Split *values* by *labels*, keeping first-appearance order.

    Plotly's default ``categoryorder`` is ``"trace"`` -- categories are drawn
    in the order they first appear rather than sorted -- so grouping any other
    way would pair a violin's numbers with a neighbour's name.
    """
    order: list[str] = []
    buckets: dict[str, list[float]] = {}
    for label, value in zip(labels, values):
        key = str(label)
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(value)
    return [(key, np.asarray(buckets[key], dtype=float)) for key in order]


def _samples(trace: dict) -> list[tuple[str, np.ndarray]]:
    """Return this trace's violins as ``(label, values)`` pairs.

    A violin trace holds several violins when its categories come from an
    array on the position axis, and one otherwise.
    """
    horizontal = trace.get("orientation") == _HORIZONTAL
    values = as_list(trace.get("x" if horizontal else "y"))
    positions = as_list(trace.get("y" if horizontal else "x"))

    if positions and len(positions) == len(values):
        return _grouped(positions, values)

    # One violin for the whole trace. Named after the trace, which is what
    # plotly writes on the category axis in that case.
    name = trace.get("name")
    label = str(name) if name is not None else ""
    return [(label, np.asarray(values, dtype=float))]


def collect_violins(traces: list[dict], prefix: str) -> list[Violin]:
    """
    Flatten a subplot's violin traces into one entry per drawn violin.

    Parameters
    ----------
    traces : list of dict
        The subplot's *drawn* violin traces, in declaration order. A hidden
        trace gets no group in the layer, so passing one would both describe a
        shape the reader cannot see and move everyone else's group index.
    prefix : str
        The CSS prefix scoping selectors to this subplot.

    Returns
    -------
    list of Violin
        One entry per violin that has a curve. A sample plotly draws nothing
        for is skipped.
    """
    violins: list[Violin] = []

    # Plotly drops the group of a trace it drew nothing for, so only traces
    # that render advance the `nth-child` index. Counting every trace instead
    # would slide each later trace's selectors onto its neighbour's group.
    rendered = 0

    for trace in traces:
        samples = _samples(trace)
        computed = [(label, violin_stats(values)) for label, values in samples]
        if not any(stats is not None for _, stats in computed):
            continue

        rendered += 1
        group = f"{prefix}.violinlayer > g:nth-child({rendered})"
        has_box = bool((trace.get("box") or {}).get("visible"))
        has_mean = bool((trace.get("meanline") or {}).get("visible"))

        # Plotly draws the mean inside the box as `path.mean`, and as
        # `path.meanline` when there is no box to draw it in -- measured, not
        # assumed. Using one name for both would address nothing in half the
        # figures that ask for a mean line.
        mean_mark = "path.mean" if has_box else "path.meanline"

        # Plotly draws one `path.violin` per category it has numbers for, and
        # omits a category entirely when it has none -- measured: a trace with
        # an all-missing category and a real one puts a single `path.violin`
        # in its group, not two. So the index counts the drawn violins rather
        # than the samples; counting samples pushed every category after a
        # missing one onto a shape that does not exist, and a selector
        # matching nothing loses the highlight silently.
        #
        # `stats is None` is exactly that set: it is returned only for a
        # sample with no finite values, which is the case plotly drops. A
        # sample whose values are all equal keeps its stats, because plotly
        # keeps drawing it.
        drawn = 0

        for label, stats in computed:
            if stats is None:
                continue
            drawn += 1
            nth = drawn
            violins.append(
                Violin(
                    label=label,
                    stats=stats,
                    kde_selector=f"{group} > :nth-child({nth} of path.violin)",
                    box_selector=f"{group} > :nth-child({nth} of path.box)",
                    mean_selector=(
                        f"{group} > :nth-child({nth} of {mean_mark})"
                        if has_mean
                        else None
                    ),
                    has_box=has_box,
                )
            )

    return violins


class _PlotlyViolinLayer(PlotlyPlot):
    """Shared construction for the two halves of a violin.

    Both are built from the same list of violins so the layers cannot fall out
    of step with one another, and both carry the orientation, which decides
    which axis a reader is navigating.
    """

    def __init__(
        self,
        traces: list[dict],
        layout: dict,
        plot_type: PlotType,
        violins: list[Violin],
        **kwargs: str,
    ) -> None:
        # The first trace stands for the group when the base class needs a
        # title or an axis pair, the way the grouped bar and multi-box layers
        # do it.
        super().__init__(traces[0], layout, plot_type, **kwargs)
        self._violins = violins
        self._horizontal = traces[0].get("orientation") == _HORIZONTAL

    def render(self) -> dict:
        """Add ``orientation`` to the base schema."""
        schema = super().render()
        schema[MaidrKey.ORIENTATION] = "horz" if self._horizontal else "vert"
        return schema

    def _ordered(self) -> list[Violin]:
        """The violins in the order a reader moves through them.

        The core reads a horizontal violin plot bottom-to-top, so emitting
        plotly's own order there would pair each row with the wrong name.
        Reversal happens on a fresh list every call rather than in place: a
        list reversed in place would go back to drawn order on every second
        render, and after an even number of renders the selectors and the data
        would disagree -- the failure #354 describes, one list further along.
        """
        if self._horizontal:
            return list(reversed(self._violins))
        return list(self._violins)


class PlotlyViolinBoxPlot(_PlotlyViolinLayer):
    """The box summary drawn inside a plotly violin."""

    def __init__(
        self, traces: list[dict], layout: dict, violins: list[Violin], **kwargs: str
    ) -> None:
        super().__init__(traces, layout, PlotType.VIOLIN_BOX, violins, **kwargs)

    def _get_selector(self) -> list[dict]:
        """Return one ``BoxSelector`` per violin, or none when no box is drawn.

        A flat list of strings would be the wrong shape: the frontend reads
        ``selectors[i].min``, ``selectors[i].q2`` and so on off an object, so
        a string there addresses nothing at best. `PlotlyBoxPlot` and the
        matplotlib `ViolinBoxPlot` both build the dict for the same reason.

        Every section shares one selector because plotly draws the whole box
        -- whiskers, quartile box and median together -- as a single
        ``path.box``. There is nothing finer to point at, so pointing all of
        them at the box is honest rather than lossy.

        ``mean`` is separate, because plotly draws it as its own path. It
        appears only for the violins whose trace asked for a mean line;
        offering the section otherwise would highlight the box for a mark that
        is not on the chart.

        A layer whose violins drew neither a box nor a mean line has nothing
        to point at, and emits no selectors rather than a set that matches
        nothing. A mean line on its own is enough, though: it is a mark a
        reader can be taken to, and withholding the whole set for want of a
        box would leave it unreachable -- ``box_visible`` is off by default,
        so that is the common case rather than an unusual one.

        Where some violins drew a box and others did not, every violin still
        gets its entry: the ones without simply hold a position no
        ``path.box`` occupies, which leaves their neighbours' indices alone.
        """
        ordered = self._ordered()
        if not any(
            violin.has_box or violin.mean_selector is not None for violin in ordered
        ):
            return []

        selectors = []
        for violin in ordered:
            selector = {
                MaidrKey.LOWER_OUTLIER: [],
                MaidrKey.MIN: violin.box_selector,
                "iq": violin.box_selector,
                MaidrKey.Q2: violin.box_selector,
                MaidrKey.MAX: violin.box_selector,
                MaidrKey.UPPER_OUTLIER: [],
            }
            if violin.mean_selector is not None:
                selector[MaidrKey.MEAN] = violin.mean_selector
            selectors.append(selector)
        return selectors

    def _extract_plot_data(self) -> list[dict]:
        """
        Return one box summary per violin.

        The whiskers are the sample's own extremes rather than a Tukey fence,
        and no outliers are separated out, because that is what a plotly
        violin draws: the KDE curve beside it already covers the tails, so
        splitting points off would announce a distinction the chart does not
        make.
        """
        summaries = []
        for violin in self._ordered():
            stats = violin.stats
            summary: dict[str, Any] = {
                MaidrKey.Z: violin.label,
                MaidrKey.LOWER_OUTLIER: [],
                MaidrKey.MIN: stats.minimum,
                MaidrKey.Q1: stats.q1,
                MaidrKey.Q2: stats.median,
                MaidrKey.Q3: stats.q3,
                MaidrKey.MAX: stats.maximum,
                MaidrKey.UPPER_OUTLIER: [],
            }
            if violin.mean_selector is not None:
                summary[MaidrKey.MEAN] = stats.mean
            summaries.append(summary)
        return summaries


class PlotlyViolinKdePlot(_PlotlyViolinLayer):
    """The density curve a plotly violin is drawn from."""

    def __init__(
        self, traces: list[dict], layout: dict, violins: list[Violin], **kwargs: str
    ) -> None:
        super().__init__(traces, layout, PlotType.VIOLIN_KDE, violins, **kwargs)

    def _get_selector(self) -> list[str]:
        return [violin.kde_selector for violin in self._ordered()]

    def _extract_plot_data(self) -> list[list[dict]]:
        """
        Return one curve per violin, as ``ViolinKdePoint[][]``.

        One point per position plotly evaluated, and one side of the outline
        rather than both: the density is the half-width, so walking the mirror
        image would announce every value twice. This is the shape the
        browser-side plotly adapter emits.

        ``svg_x`` / ``svg_y`` are omitted. They are optional on the point, and
        they are pixel coordinates -- plotly lays the chart out in the browser,
        so Python has no honest value for them. Their absence costs the
        highlight's positioning, not the reading.
        """
        curves = []
        for violin in self._ordered():
            stats = violin.stats
            curves.append(
                [
                    {
                        MaidrKey.X: violin.label,
                        MaidrKey.Y: float(position),
                        "density": float(density),
                    }
                    for position, density in zip(stats.positions, stats.density)
                ]
            )
        return curves
