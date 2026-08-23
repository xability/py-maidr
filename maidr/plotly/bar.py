from __future__ import annotations

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, paired_axes


class PlotlyBarPlot(PlotlyPlot):
    """Extract data from a Plotly bar trace."""

    def __init__(self, trace: dict, layout: dict, **kwargs: str) -> None:
        super().__init__(trace, layout, PlotType.BAR, **kwargs)

        # Where each drawn bar sits in the trace's own arrays, when
        # ``categoryorder`` puts the two in different orders. Filled by
        # ``_extract_plot_data``, which ``render()`` runs before
        # ``_get_selector`` -- so the two cannot disagree about the order
        # (#495).
        self._drawn: list[int] | None = None

    def _get_selector(self) -> str | list[str]:
        """Address the bars, per drawn position when the two orders differ.

        One string is what an unsorted chart has always had, and it stays
        that: plotly writes its bars in the trace's own order, so a single
        selector resolves in the order the points are emitted in.

        A sorted chart cannot use it. Measured in Chromium on
        ``go.Bar(x=['charlie', 'alpha', 'bravo'])`` with
        ``categoryorder: 'category ascending'``, the three ``.point`` groups
        come back at x = 773, 37 and 405 -- the *trace's* order, while the
        chart draws alpha, bravo, charlie left to right. So reordering the
        points alone would leave every highlight one place out.

        ``nth-of-type`` addresses them one at a time. Measured on the same
        page, ``.point:nth-of-type(k)`` matches exactly one element and it is
        the kth in document order, for every k.

        A list reaches a bar layer's highlight as of xability/maidr#991. An
        older bundle answers ``[]`` -- ``Svg.selectAllElements`` guards on
        ``typeof query === 'string'`` -- so the highlight is *lost* rather
        than wrong, and the announced order stays corrected. That is the
        better of the two failures, and it only arises on a chart that
        declares an order.
        """
        prefix = f"{self._subplot_css_prefix()}.trace.bars"
        if self._drawn is None:
            return f"{prefix} .point > path"
        return [
            f"{prefix} .point:nth-of-type({index + 1}) > path" for index in self._drawn
        ]

    def render(self) -> dict:
        """Add ``orientation`` to the base schema.

        `paired_axes` is symmetric, so a horizontal bar's measure already
        arrives in ``x`` -- which is the arrangement the core wants, but only
        once it has been told the layer is horizontal. Without the key it
        defaults to vertical and reads ``point.y``, which here is the category
        name: no magnitude to pitch, so every bar was silent, and the
        announcement gave the measure as the point's identity and the category
        as its value (#480).

        The same override `PlotlyHistogramPlot` carries, for the same reason --
        its trace extends this one in the core.
        """
        schema = super().render()
        schema[MaidrKey.ORIENTATION] = (
            "horz" if self._trace.get("orientation") == "h" else "vert"
        )
        return schema

    def _extract_plot_data(self) -> list[dict]:
        """The bars, in the order plotly draws them.

        ``categoryorder`` sorts the category axis and leaves the trace's own
        ``x`` and ``y`` exactly as the author wrote them, so the arrays alone
        do not say what the chart shows. Every label still carried its own
        value before this and the highlight still landed on the right bar, so
        nothing read as broken -- what was wrong is everything that treats the
        index as a *position*: which way arrowing travels, the stereo pan, the
        braille line, and the autoplay sweep (#495).

        The category axis is the one the bars are named along, which is ``y``
        for a horizontal bar. ``paired_axes`` is symmetric and does not swap
        them, so the axis is chosen here rather than assumed to be ``x``.
        """
        x, y = paired_axes(self._trace)
        points = [
            {MaidrKey.X: self._to_native(xv), MaidrKey.Y: self._to_native(yv)}
            for xv, yv in zip(x, y)
        ]

        horizontal = self._trace.get("orientation") == "h"
        axis_name = self._yaxis_name if horizontal else self._xaxis_name
        labels = [self._to_native(v) for v in (y if horizontal else x)]

        drawn = self._drawn_category_order(axis_name, labels)
        if drawn is None or drawn == list(range(len(points))):
            # Either the sort cannot be resolved offline, or it is the order
            # the trace is already in. Both leave the layer exactly as it
            # read before, selector included.
            self._drawn = None
            return points

        self._drawn = drawn
        return [points[index] for index in drawn]
