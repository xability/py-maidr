from __future__ import annotations

from typing import Any

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list

#: Plotly's own default when a step names no measure. Every step is a
#: contribution unless the author says otherwise, which is why a waterfall
#: written with `x` and `y` alone accumulates.
_DEFAULT_MEASURE = "relative"


class PlotlyWaterfallPlot(PlotlyPlot):
    """Extract data from a Plotly waterfall trace.

    Plotly states a waterfall in *offsets* -- a `measure` array saying what
    each `y` means -- while `WaterfallPoint` wants the two absolute running
    totals a step sits between. Converting between them is the whole of this
    class, and the conversion is not a rename: what `y` means depends on the
    step's measure, and one of the three measures ignores `y` entirely.

    The semantics were measured rather than read off the documentation, by
    rendering each case in Chromium and inverting the drawn rectangles back
    through plotly's own axis map:

    ======================  ==================================================
    ``measure=[…]``         drawn
    ======================  ==================================================
    absent                  every step relative: ``y=[10, -4, 7]`` draws
                            ``0->10``, ``10->6``, ``6->13``
    ``relative``            adds ``y`` to the running total
    ``total``               draws from ``base`` to the running total and
                            leaves it there; the step's own ``y`` is ignored
                            (``y=999`` on a total drew ``0->15``)
    ``absolute``            *sets* the running total to ``y``: after
                            ``[relative, absolute, relative]`` on
                            ``[10, 100, 5]`` the third step drew ``100->105``
    ======================  ==================================================

    ``base`` moves where the accumulation starts, totals included:
    ``base=100`` on ``y=[10, 5, 0(total)]`` drew ``100->110``, ``110->115``,
    ``100->115``.
    """

    def __init__(
        self, trace: dict, layout: dict, *, layer_position: int = 0, **kwargs: str
    ) -> None:
        super().__init__(trace, layout, PlotType.WATERFALL, **kwargs)
        self._layer_position = layer_position

    def _get_selector(self) -> str:
        """Address this trace's steps inside the subplot's waterfall layer.

        ``.waterfalllayer`` rather than ``.trace.bars`` alone. Plotly gives
        each trace family its own ``mlayer`` group and reuses the inner class
        names inside every one of them, so on a subplot holding a bar trace
        and a waterfall the bare ``.trace.bars`` matched seven elements --
        four bars and three steps (#628).

        ``nth-of-type`` picks this trace's group out of the layer, for the
        reason ``PlotlyGroupedBarPlot`` numbers its own: plotly appends one
        ``.trace.bars`` group per waterfall trace, in declaration order, so
        two waterfalls on one subplot would otherwise each claim both sets.
        """
        return (
            f"{self._subplot_css_prefix()}.waterfalllayer "
            f".trace.bars:nth-of-type({self._layer_position + 1}) .point > path"
        )

    def _extract_axes_data(self) -> dict:
        """Name the category axis ``x`` however the chart is drawn.

        ``WaterfallTrace`` fixes ``mainAxis: 'x'`` and announces the step's
        label against ``this.xAxis``, because the core holds that a waterfall
        has no orientation -- "the steps run along the category axis and the
        contributions along the value axis, but the trace reads the same
        either way round" (``IS_ORIENTED`` in ``src/util/orientation.ts``).

        So a horizontal waterfall is emitted with its category in ``x``, and
        the two axis titles have to travel with it. Leaving them in plotly's
        arrangement would announce the value axis's title beside the category
        name and the category axis's title beside the contribution -- both
        labels attached to the wrong number.
        """
        axes = super()._extract_axes_data()
        if self._is_horizontal():
            axes[MaidrKey.X], axes[MaidrKey.Y] = axes[MaidrKey.Y], axes[MaidrKey.X]
        return axes

    def _is_horizontal(self) -> bool:
        """Report whether plotly draws this waterfall across the page."""
        return self._trace.get("orientation") == "h"

    def _extract_plot_data(self) -> list[dict]:
        """The steps, as the absolute pair each one sits between.

        A step's ``kind`` is read from its measure rather than from the sign
        of its contribution: an ``absolute`` step and a ``total`` step both
        *restate* the running value rather than moving it, which is what
        ``'total'`` means to the core -- it excludes those steps from
        "largest contribution" and from the extrema targets, precisely so the
        opening and closing bars do not bury the answer the reader wanted.
        """
        horizontal = self._is_horizontal()
        labels = as_list(self._trace.get("y" if horizontal else "x"))
        values = as_list(self._trace.get("x" if horizontal else "y"))
        measures = as_list(self._trace.get("measure"))

        base = self._number(self._trace.get("base"), 0.0)
        running = base

        points: list[dict] = []
        for index, label in enumerate(labels):
            measure = (
                str(measures[index]) if index < len(measures) else _DEFAULT_MEASURE
            )
            value = self._number(values[index] if index < len(values) else None, 0.0)

            if measure == "total":
                start, end = base, running
            elif measure == "absolute":
                start, end = base, value
                running = value
            else:
                start, end = running, running + value
                running = end

            points.append(
                {
                    MaidrKey.X: self._to_native(label),
                    MaidrKey.START: start,
                    MaidrKey.END: end,
                    MaidrKey.DELTA: end - start,
                    MaidrKey.KIND: self._kind(measure, end - start),
                }
            )
        return points

    @staticmethod
    def _kind(measure: str, delta: float) -> str:
        """Return the ``WaterfallKind`` a measure and its contribution make.

        A zero-contribution relative step reads as an ``increase``: it is a
        step that happened to net to nothing, not a restatement of the total,
        and calling it a total would take it out of the extrema search and
        out of the increase/decrease counts the description reports.
        """
        if measure in ("total", "absolute"):
            return "total"
        return "decrease" if delta < 0 else "increase"

    @staticmethod
    def _number(value: Any, default: float) -> float:
        """Coerce one of plotly's numbers, falling back when it is absent."""
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
