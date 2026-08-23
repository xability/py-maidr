from __future__ import annotations

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.pie import PlotlyPiePlot


class PlotlyFunnelareaPlot(PlotlyPiePlot):
    """Extract data from a Plotly funnelarea trace.

    A funnelarea is a funnel drawn as nested trapezoids rather than as bars,
    and it is stated the way a pie is -- ``labels`` and ``values``, placed by
    a ``domain`` rectangle rather than by an axis pair. So it inherits the
    pie's slice builder rather than growing a second copy of it: measured
    against ``gd.calcdata`` in Chromium, every rule matched, one by one --

    ==========================  ==============================================
    written                     drawn
    ==========================  ==============================================
    ``labels=[a, b, a]``        two slices, ``a`` = the sum, at ``a``'s first
                                position
    ``values=[10, 0, 5]``       three slices; the zero is kept
    ``values=[10, -5, 5]``      two slices; the negative is dropped
    no ``values``               every entry weighs 1
    no ``labels``               slices named ``0``, ``1``, ``2``
    an empty label              the entry's own index
    ``layout.hiddenlabels``     the named slice is not drawn
    ==========================  ==============================================

    -- with exactly one exception, which is why the sort is a hook on the
    parent: a funnelarea has no ``sort`` attribute and never reorders.
    ``values=[40, 100, 60]`` stayed in that order, where a pie would have
    drawn 100, 60, 40.

    That exception is the whole reason the two cannot simply be one class.
    A funnel's axis *is* its sequence, so a funnelarea keeps the stages the
    author wrote; reusing the pie's sorting default would reorder the stages
    of a funnel by size and announce a conversion path nobody drew.
    """

    #: A funnelarea's slices are the stages of a funnel and their counts,
    #: which is what the reader should be told they are when the layout names
    #: nothing. "Category" and "Value" would be true of a pie and vague here.
    _AXIS_FALLBACKS = ("Stage", "Count")

    def __init__(
        self,
        trace: dict,
        layout: dict,
        *,
        pie_position: int = 0,
        borrows_axis_titles: bool = True,
        **kwargs: str,
    ) -> None:
        super().__init__(
            trace,
            layout,
            pie_position=pie_position,
            borrows_axis_titles=borrows_axis_titles,
            **kwargs,
        )
        # Set after the parent has stamped `PlotType.PIE` on it. A funnelarea
        # is read as the funnel it draws: `FunnelTrace` extends the bar trace
        # and pitches the retention between adjacent stages, which is the
        # number this chart exists to show and the one a pie layer has no
        # notion of.
        self.type = PlotType.FUNNEL

    def _sorts_wedges(self) -> bool:
        """A funnelarea never reorders its stages.

        Measured: plotly gives the trace no ``sort`` attribute --
        ``gd._fullData[0].sort`` is undefined -- and ``values=[40, 100, 60]``
        drew in that order.
        """
        return False

    def _get_selector(self) -> str:
        """Address this trace's slices inside the figure's funnelarea layer.

        ``funnelarealayer`` rather than ``pielayer``: measured in Chromium on
        a figure holding one of each, ``.pielayer .trace .slice path.surface``
        matched the pie's 2 slices and ``.funnelarealayer ...`` the
        funnelarea's 3, with neither reaching the other.

        Both layers sit directly under ``main-svg`` rather than inside a
        ``.subplot.xy`` group, which is why the position among the layer's
        trace groups stands in for the subplot prefix. Measured on two
        funnelareas: ``> .trace:nth-child(1)`` resolved to 3 slices and
        ``nth-child(2)`` to 2, against 5 for the unpositioned form.
        """
        return (
            f".funnelarealayer > .trace:nth-child({self._pie_position + 1}) "
            f"> .slice > path.surface"
        )

    def render(self) -> dict:
        """Add ``orientation`` to the base schema.

        `FunnelTrace` reads the stage name off ``point.x`` when the layer is
        vertical and off ``point.y`` when it is horizontal, and a funnelarea
        carries its stage names in ``x`` -- it has no axes to be drawn along,
        so there is no second arrangement for it to be in. Declared rather
        than left to the default so the payload says what it holds, which is
        what xability/maidr#947 asks of a producer.
        """
        schema = super().render()
        schema[MaidrKey.ORIENTATION] = "vert"
        return schema
