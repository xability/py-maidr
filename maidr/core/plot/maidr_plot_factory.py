from __future__ import annotations

from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.collections import LineCollection, PatchCollection, PolyCollection
from matplotlib.patches import StepPatch
from maidr.core.enum import PlotType
from maidr.core.plot.areaplot import AreaPlot
from maidr.core.plot.barplot import BarPlot
from maidr.core.plot.boxenplot import BoxenPlot
from maidr.core.plot.boxplot import BoxPlot
from maidr.core.plot.contour import ContourPlot
from maidr.core.plot.dashplot import DRAWN_DASHES, DashPlot
from maidr.core.plot.textplot import DRAWN_LABELS, TextPlot
from maidr.core.plot.bars_histogram import BarsHistPlot, DRAWN_BINS
from maidr.core.plot.errorbar import ErrorBarPlot
from maidr.core.plot.intervalplot import DRAWN_INTERVALS, IntervalPlot
from maidr.core.plot.eventplot import DRAWN_EVENTS, EventPlot
from maidr.core.plot.gantt import GanttPlot
from maidr.core.plot.grouped_barplot import GroupedBarPlot
from maidr.core.plot.heatmap import HeatPlot
from maidr.core.plot.hexbinplot import HexbinPlot
from maidr.core.plot.histogram import HistPlot
from maidr.core.plot.lineplot import MultiLinePlot
from maidr.core.plot.segment_lineplot import DRAWN_SEGMENTS, SegmentLinePlot
from maidr.core.plot.lollipop import LollipopPlot
from maidr.core.plot.maidr_plot import MaidrPlot
from maidr.core.plot.outlined_histogram import OUTLINE_LINE, OutlinedHistPlot
from maidr.core.plot.pieplot import PiePlot
from maidr.core.plot.pointplot import PointPlot
from maidr.core.plot.scatterplot import ScatterPlot
from maidr.core.plot.regplot import SmoothPlot
from maidr.core.plot.rugplot import DRAWN_RUG, RugPlot
from maidr.core.plot.spanplot import DRAWN_SPANS, SpanPlot
from maidr.core.plot.stairs import StairsPlot
from maidr.core.plot.stepped_histogram import SteppedHistPlot
from maidr.core.plot.step_histogram import STEP_COUNTS, STEP_EDGES, StepHistPlot
from maidr.core.plot.stepplot import StepPlot
from maidr.core.plot.violin_kde_plot import ViolinKdePlot
from maidr.core.plot.violin_box_plot import ViolinBoxPlot
from maidr.core.plot.mplfinance_barplot import MplfinanceBarPlot
from maidr.core.plot.mplfinance_lineplot import MplfinanceLinePlot
from maidr.core.plot.candlestick import CandlestickPlot
from maidr.util.plot_detection import PlotDetectionUtils


class MaidrPlotFactory:
    """
    A factory for creating instances of ``maidr.core.maidr.MaidrPlot`` based on the
    plot type.

    Warnings
    --------
    End users will typically not have to use this class directly.

    See Also
    --------
    MaidrPlot : The base class for MAIDR plot data objects.
    PlotType : An enumeration of types of plots supported within MAIDR.
    """

    @staticmethod
    def create(ax: Axes | list[Axes], plot_type: PlotType, **kwargs) -> MaidrPlot:
        if plot_type == PlotType.CANDLESTICK:
            axes = PlotDetectionUtils.get_candlestick_axes(ax)
            return CandlestickPlot(axes, **kwargs)

        if isinstance(ax, list):
            single_ax = ax[0]
        else:
            single_ax = ax

        if PlotType.AREA == plot_type or PlotType.STACKED_AREA == plot_type:
            # One class, both types. They differ in how the bands relate, not
            # in where the numbers are read from.
            return AreaPlot(single_ax, plot_type, **kwargs)

        if PlotType.BAR == plot_type or PlotType.COUNT == plot_type:
            if PlotDetectionUtils.is_mplfinance_bar_plot(**kwargs):
                return MplfinanceBarPlot(single_ax, **kwargs)
            else:
                return BarPlot(single_ax, **kwargs)
        elif PlotType.BOX == plot_type:
            return BoxPlot(single_ax, **kwargs)
        elif PlotType.BOXEN == plot_type:
            return BoxenPlot(single_ax, **kwargs)
        elif PlotType.GANTT == plot_type:
            # Two calls draw this chart and they are shaped oppositely.
            # `broken_barh` draws one lane per call and hands back a
            # `PolyCollection` of corners; `hlines`/`vlines` draw every lane
            # in one call and hand back a `LineCollection` of segments. The
            # layer is the same either way, so the type cannot say which, and
            # the artist the patch passes does (#568).
            if DRAWN_SPANS in kwargs:
                return SpanPlot(single_ax, **kwargs)
            return GanttPlot(single_ax, **kwargs)
        elif PlotType.CONTOUR == plot_type:
            return ContourPlot(single_ax, **kwargs)
        elif PlotType.ERRORBAR == plot_type:
            # Both read an estimate and the interval around it, and both emit
            # the same layer; they differ only in what the library drew.
            # `Axes.errorbar` leaves a container, while seaborn's point plot
            # leaves the lines the patch resolved and hands them over here.
            # `estimates` (plural) is the `hue`-split form, one line per
            # group; `estimate` is the single-series one. Either says the
            # lines came from seaborn.
            if isinstance(kwargs.get("estimate"), Line2D) or kwargs.get("estimates"):
                return PointPlot(single_ax, **kwargs)
            # `so.Band` and `so.Range` draw the interval and no estimate at
            # all, so there is no container and no estimate line to resolve --
            # only the band or the bars themselves, which is what this names.
            if DRAWN_INTERVALS in kwargs:
                return IntervalPlot(single_ax, **kwargs)
            return ErrorBarPlot(single_ax, **kwargs)
        elif PlotType.HEAT == plot_type:
            return HeatPlot(single_ax, **kwargs)
        elif PlotType.HEXBIN == plot_type:
            return HexbinPlot(single_ax, **kwargs)
        elif PlotType.HIST == plot_type:
            # Two spellings of one chart. `Axes.hist` leaves a `BarContainer`
            # for `HistPlot` to find; `Axes.stairs` leaves a single
            # `StepPatch` and hands it over, because there is no container to
            # find and no per-bin artist to look for.
            if isinstance(kwargs.get("step_patch"), StepPatch):
                return StairsPlot(single_ax, **kwargs)
            # `so.Bars()` draws the same distribution as one `PatchCollection`
            # of rectangles -- neither a container nor an outline, so neither
            # of the two below can read it.
            if isinstance(kwargs.get(DRAWN_BINS), PatchCollection):
                return BarsHistPlot(single_ax, **kwargs)
            # `sns.histplot(element="step"/"poly")` draws the same
            # distribution as one closed outline, so there is no container to
            # find and the call hands its `PolyCollection` over instead.
            if isinstance(kwargs.get("collection"), PolyCollection):
                return SteppedHistPlot(single_ax, **kwargs)
            # The same two elements drawn `fill=False`, which swaps the
            # collection for a bare `Line2D` and left the chart silent (#583).
            outline = kwargs.get(OUTLINE_LINE)
            if outline is not None:
                return OutlinedHistPlot(single_ax, outline, **kwargs)
            # `ax.hist(histtype="step"/"stepfilled")` draws a `Polygon` per
            # dataset and leaves no container either, so the call hands over
            # the counts and edges it already returned (#555).
            counts = kwargs.get(STEP_COUNTS)
            edges = kwargs.get(STEP_EDGES)
            if counts is not None and edges is not None:
                return StepHistPlot(single_ax, counts, edges, **kwargs)
            return HistPlot(single_ax, **kwargs)
        elif PlotType.LINE == plot_type:
            # `so.Lines` and `so.Paths` draw every series into one
            # `LineCollection` rather than a `Line2D` each, so the layer is
            # handed the collection and reads its segments (#670). The same
            # shape `SteppedHistPlot` is selected by above.
            if isinstance(kwargs.get(DRAWN_SEGMENTS), LineCollection):
                return SegmentLinePlot(single_ax, **kwargs)
            if PlotDetectionUtils.is_mplfinance_line_plot(single_ax, **kwargs):
                return MplfinanceLinePlot(single_ax, **kwargs)
            else:
                return MultiLinePlot(single_ax, **kwargs)
        elif PlotType.LOLLIPOP == plot_type:
            return LollipopPlot(single_ax, **kwargs)
        elif PlotType.STEP == plot_type:
            return StepPlot(single_ax, **kwargs)
        elif PlotType.PIE == plot_type:
            return PiePlot(single_ax, **kwargs)
        elif PlotType.SCATTER == plot_type:
            # An event plot's row is a scatter of positions, but it arrives as
            # an `EventCollection` rather than a `PathCollection` and keeps its
            # values in `get_positions()` rather than in offsets, so it reads
            # through a class of its own under the same type (#548).
            if kwargs.get(DRAWN_EVENTS) is not None:
                return EventPlot(single_ax, **kwargs)
            # A rug's ticks are a scatter of positions for the same reason,
            # and arrive as a plain `LineCollection` -- not an
            # `EventCollection`, so `EventPlot` cannot read one (#250).
            if kwargs.get(DRAWN_RUG) is not None:
                return RugPlot(single_ax, **kwargs)
            # `so.Dash()` draws a horizontal tick per observation instead of a
            # marker, so it too arrives as a plain `LineCollection` and keeps
            # its values in the segments rather than in offsets (#670).
            if kwargs.get(DRAWN_DASHES) is not None:
                return DashPlot(single_ax, **kwargs)
            # `so.Text()` writes a string at each observation instead of
            # drawing a marker, so it leaves `Text` artists and nothing in
            # `collections` at all -- the only mark #670 read that draws into
            # a holder no other reading names.
            if kwargs.get(DRAWN_LABELS) is not None:
                return TextPlot(single_ax, **kwargs)
            return ScatterPlot(single_ax, **kwargs)
        elif plot_type in (PlotType.DODGED, PlotType.STACKED, PlotType.NORMALIZED):
            # One class, three types. They differ in how the groups relate --
            # side by side, piled up, piled up to a whole -- not in where the
            # numbers come from, which is one magnitude per bar either way.
            # A `NORMALIZED` layer's bars are already shares, because the
            # library drew them that way; the plotly path computes its own
            # (`maidr/plotly/barnorm.py`) only because plotly draws the raw
            # values and normalises them in the view (#338, #620).
            return GroupedBarPlot(single_ax, plot_type, **kwargs)
        elif PlotType.SMOOTH == plot_type:
            return SmoothPlot(single_ax, **kwargs)
        elif PlotType.VIOLIN_KDE == plot_type:
            return ViolinKdePlot(single_ax, **kwargs)
        elif PlotType.VIOLIN_BOX == plot_type:
            return ViolinBoxPlot(single_ax, **kwargs)
        else:
            raise TypeError(f"Unsupported plot type: {plot_type}.")
