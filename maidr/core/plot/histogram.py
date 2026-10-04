from __future__ import annotations

from matplotlib.axes import Axes
from matplotlib.container import BarContainer

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.core.plot.maidr_plot import group_name_of
from maidr.exception import ExtractionError
from maidr.util.mixin import ContainerExtractorMixin, DictMergerMixin

#: Key the patch passes the container its own call drew under. Named like
#: ``heatmap.DRAWN_GRID`` and ``scatterplot.DRAWN_POINTS``, and read the same
#: way.
DRAWN_BARS = "_maidr_bars"



class HistPlot(MaidrPlot, ContainerExtractorMixin, DictMergerMixin):
    def __init__(self, ax: Axes, **kwargs) -> None:
        # The bars this layer's own call drew, when the patch could say.
        # `None` falls back to searching the axes, which resolves *per axes*
        # and so hands every histogram on one axes the same container: two
        # `ax.hist()` calls were both announced with the first one's bins, the
        # second distribution appearing nowhere and nothing raising. Found by
        # the audit #527 asked for, and the same defect it records for
        # heatmaps.
        #
        # Guarded on the type, like `HeatPlot._own_grid` and
        # `ScatterPlot._own_points`. `ax.hist([a, b])` returns a *list* of
        # containers rather than one, which this would decline -- though that
        # case cannot arrive today: the patch resolves its axes from the same
        # return value and raises on a list before any layer exists (#553).
        # So the guard is structural rather than a live path, and stays for
        # when that call is made to work.
        own_bars = kwargs.pop(DRAWN_BARS, None)
        self._own_bars = own_bars if isinstance(own_bars, BarContainer) else None
        # The hue group this layer's container belongs to, when the patch
        # could name it. `None` is the ungrouped case and every chart that
        # drew no legend. Opted into here rather than read by `MaidrPlot`;
        # see `GROUP_NAME` for why that is per class.
        # A string names the group now; a callable names it at render, which
        # is what a `pairplot` needs -- its legend does not exist until every
        # panel has been drawn (#561).
        self._group_name = group_name_of(kwargs)
        super().__init__(ax, PlotType.HIST)
        self._orientation = "vert"

    @staticmethod
    def _extract_orientation(plot: BarContainer | None) -> str:
        """
        Read the orientation matplotlib recorded on the bar container.

        Parameters
        ----------
        plot : BarContainer, optional
            The container holding the histogram bars.

        Returns
        -------
        str
            ``"horz"`` for ``hist(orientation="horizontal")``, ``"vert"``
            otherwise.
        """
        if plot is None:
            return "vert"

        return "horz" if plot.orientation == "horizontal" else "vert"

    def render(self) -> dict:
        """
        Add ``orientation`` to the base schema, and the group's name when the
        layer reads one distribution of several.

        ``MaidrLayer.name`` is the field xability/maidr#828 added so two
        layers of a kind can be told apart, which is exactly where a
        hue-grouped histogram leaves a reader. Distinct from ``title``, which
        every layer of a figure carries and which names the *chart*.
        """
        # Read after the super call, not before: `self._orientation` is
        # populated by `_extract_plot_data`, which that call runs.
        base_schema = super().render()
        hist_orientation = {MaidrKey.ORIENTATION: self._orientation}
        name = self._group_name() if callable(self._group_name) else self._group_name
        if name:
            hist_orientation[MaidrKey.NAME] = name
        return DictMergerMixin.merge_dict(base_schema, hist_orientation)

    def _extract_plot_data(self) -> list[dict]:
        # The container this layer was registered for, not whichever one a
        # search of the axes turns up first. `extract_container` resolves per
        # axes and cannot tell two histograms apart; it is still the fallback,
        # for a producer that registers a histogram without saying which
        # container drew it.
        plot = self._own_bars
        if plot is None:
            plot = self.extract_container(self.ax, BarContainer)
        self._orientation = self._extract_orientation(plot)
        data = self._extract_bar_container_data(plot)

        if data is None:
            raise ExtractionError(self.type, plot)

        return data

    @staticmethod
    def _bin_point(
        orientation: str, bin_start: float, bin_size: float, count: float | None
    ) -> dict:
        """
        Build one bin's point, whichever way the histogram was drawn.

        Shared with :class:`~maidr.core.plot.stairs.StairsPlot`, so the two
        spellings of a histogram -- a row of bars from ``Axes.hist``, a
        staircase from ``Axes.stairs`` -- emit the same payload for the same
        chart rather than two that merely resemble one another.

        Parameters
        ----------
        orientation : str
            ``"horz"`` when the bins run up the y axis, ``"vert"`` otherwise.
        bin_start : float
            The bin's lower edge, along the axis the bins run on.
        bin_size : float
            The width of the bin, on that same axis.
        count : float or None
            What the bin holds, or ``None`` when it holds nothing measurable.

        Returns
        -------
        dict
            The point, with the bin edges on the axis the bins run on.

        Notes
        -----
        The bounds across the bins -- ``yMin``/``yMax`` on a vertical
        histogram, ``xMin``/``xMax`` on a horizontal one -- are emitted for
        the shape's sake and are not read: the core's ``Histogram`` trace
        takes its bin range from the pair on the *binned* axis and never
        looks at the other.
        """
        if orientation == "horz":
            return {
                MaidrKey.X.value: count,
                MaidrKey.Y.value: bin_start + bin_size / 2,
                MaidrKey.Y_MIN.value: bin_start,
                MaidrKey.Y_MAX.value: bin_start + bin_size,
                MaidrKey.X_MIN.value: 0,
                MaidrKey.X_MAX.value: count,
            }

        return {
            MaidrKey.Y.value: count,
            MaidrKey.X.value: bin_start + bin_size / 2,
            MaidrKey.X_MIN.value: bin_start,
            MaidrKey.X_MAX.value: bin_start + bin_size,
            MaidrKey.Y_MIN.value: 0,
            MaidrKey.Y_MAX.value: count,
        }

    def _extract_bar_container_data(
        self, plot: BarContainer | None
    ) -> list[dict] | None:
        if plot is None or plot.patches is None:
            return None

        data = []
        for patch in plot.patches:
            # A horizontal histogram runs its bins up the y axis and its
            # counts along x, so the bin edges come off the patch's y and
            # height and the count off its width. The vertical case is the
            # mirror of that.
            if self._orientation == "horz":
                data.append(
                    self._bin_point(
                        "horz",
                        float(patch.get_y()),
                        float(patch.get_height()),
                        float(patch.get_width()),
                    )
                )
                continue

            data.append(
                self._bin_point(
                    "vert",
                    float(patch.get_x()),
                    float(patch.get_width()),
                    float(patch.get_height()),
                )
            )

        # Tag the elements for highlighting
        self._elements.extend(plot.patches)

        return data
