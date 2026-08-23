from __future__ import annotations

import math

from matplotlib.axes import Axes
from matplotlib.container import BarContainer
from matplotlib.patches import Rectangle

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.core.plot.maidr_plot import group_name_of
from maidr.exception import ExtractionError
from maidr.util.mixin import (
    BarPositionMixin,
    ContainerExtractorMixin,
    DictMergerMixin,
    LevelExtractorMixin,
)


#: The keyword ``Axes.bar`` hands its own ``BarContainer`` to this layer
#: under. Named once and imported at both ends rather than spelled twice:
#: ``kwargs.get`` falls back to sweeping the axes on a mismatch, so a typo
#: would not raise -- it would quietly restore the behaviour #380 removed.
#:
#: Lives here rather than beside ``common.drawn_as`` because ``maidr.patch``
#: imports ``maidr.core`` and not the other way about.
DRAWN_BARS = "_maidr_bars"


def _magnitude(raw: float) -> float | None:
    """
    A bar's height, or ``None`` where it has none.

    matplotlib draws a rectangle for a ``NaN`` height, so a gap in the data
    survives as a bar with no magnitude rather than being dropped. Two things
    then go wrong at once if it is emitted as it stands.

    ``json.dumps`` writes ``NaN`` as a bare token, which is legal JavaScript
    and invalid JSON, and the core parses the SVG's ``maidr`` attribute with
    ``JSON.parse`` -- so one of them stops the chart initialising at all
    (#427). And ``Number(NaN)`` is not the reading a listener wants either.

    ``None`` serialises to ``null``, which is exactly what the core's
    ``toBarValue`` has read as a gap since the bar family gained the concept:
    it becomes ``NaN`` inside the model, is kept out of the range, sounds as
    the empty tone rather than a floor tone, and announces as "missing". A
    zero would be the wrong answer here for the reason that helper exists --
    an absent bar is not one measured at zero.

    Parameters
    ----------
    raw : float
        The dimension the bar grows along, as matplotlib recorded it.

    Returns
    -------
    float or None
        The magnitude as a plain ``float``, or ``None`` when the bar has no
        measurable one.

    Notes
    -----
    The ``float()`` is not decoration. matplotlib hands back whatever numpy
    type the caller's data carried, and ``json.dumps`` cannot serialise a
    ``numpy.int64`` -- dropping the cast raised ``TypeError: Object of type
    int64 is not JSON serializable`` on 28 tests, which is the whole render
    rather than one bar.
    """
    return float(raw) if math.isfinite(raw) else None


def bar_groups(ax: Axes, container: BarContainer) -> list[tuple[str, list[int]]] | None:
    """
    The groups a colour-split bar layer was drawn with, or ``None``.

    The ``BarContainer`` counterpart of
    :func:`maidr.core.plot.scatterplot.hue_groups`, and the same question:
    one artist carries every level, so the grouping survives only in the
    bars' colours and in the legend that names them.

    ``seaborn.objects`` needs it where ``seaborn.barplot(hue=...)`` does not.
    The classic function draws one container **per level**, so each layer
    already holds one bar per category; ``so.Bar()`` draws every level into
    one container, and what that costs is not only the group names. Measured
    on two categories and two levels::

        so.Plot(frame, x=, y=, color="g").add(so.Bar(), so.Dodge())
          bars 4, ticks ['a', 'b'] -> announced x ['-0.2', '0.2', '0.8', '1.2']

    Those are the dodge offsets. ``BarPlot._labels_for`` announces bar
    *positions* whenever the tick labels do not number the bars, which is
    right where #382 put it -- a numeric axis picks its own breaks -- and
    which a colour split walks straight into. Splitting the layer per level
    puts one bar against one tick again, so the category names come back
    with the group names (xability/py-maidr#617).

    Parameters
    ----------
    ax : Axes
        The axes drawn on, for its legend.
    container : BarContainer
        The bars.

    Returns
    -------
    list of (str, list of int) or None
        One entry per group in legend order, naming it and listing the
        container positions that belong to it, or ``None`` when the layer is
        not grouped.
    """
    from maidr.core.plot.scatterplot import _rgba, groups_from_colours

    return groups_from_colours(
        ax, [_rgba(patch.get_facecolor()) for patch in container]
    )


class BarPlot(
    MaidrPlot,
    BarPositionMixin,
    ContainerExtractorMixin,
    LevelExtractorMixin,
    DictMergerMixin,
):
    def __init__(self, ax: Axes, **kwargs) -> None:
        super().__init__(ax, PlotType.BAR)
        self._orientation = "vert"
        # The container this layer's own call drew, when the patch could say.
        # `None` falls back to sweeping the axes, which is what seaborn needs:
        # it draws one layer as several containers, one per hue group.
        self._own_bars = kwargs.get(DRAWN_BARS, None)
        # The group this layer reads, when the patch found one. Opted into
        # here rather than read by `MaidrPlot`; see `GROUP_NAME` for why that
        # is per class, and `render` for the callable form.
        self._group_name = group_name_of(kwargs)

    @property
    def _is_horizontal(self) -> bool:
        return self._orientation == "horz"

    @property
    def _level_key(self) -> MaidrKey:
        """
        The axis the bar labels sit on: ``y`` for a horizontal bar plot
        (``Axes.barh``, ``seaborn.barplot(orient="h")``), ``x`` otherwise.
        """
        return MaidrKey.Y if self._is_horizontal else MaidrKey.X

    @staticmethod
    def _extract_orientation(plot: list[BarContainer] | None) -> str:
        """
        Read the orientation matplotlib recorded on the bar container.

        Only the first container is asked: every container on one Axes is
        drawn by the same call, so a layer runs one way or the other, never
        both. A mixed-orientation layer would need this to say so per bar.

        Parameters
        ----------
        plot : list of BarContainer, optional
            The containers holding the bars of this layer.

        Returns
        -------
        str
            ``"horz"`` for a horizontal bar plot, ``"vert"`` otherwise.
        """
        if not plot:
            return "vert"

        return "horz" if plot[0].orientation == "horizontal" else "vert"

    def render(self) -> dict:
        """Add ``orientation``, and the name of the group this layer reads."""
        # Read after the super call, not before: `self._orientation` is
        # populated by `_extract_plot_data`, which that call runs.
        base_schema = super().render()
        bar_orientation = {MaidrKey.ORIENTATION: self._orientation}
        schema = DictMergerMixin.merge_dict(base_schema, bar_orientation)

        # `MaidrLayer.name` is what xability/maidr#828 added so that two
        # layers of a kind can be told apart, which is exactly the position a
        # colour-split bar puts a reader in. A callable is resolved here
        # rather than at registration, for the timing #612 describes.
        name = self._group_name() if callable(self._group_name) else self._group_name
        if name:
            schema[MaidrKey.NAME] = name
        return schema

    def _extract_plot_data(self) -> list:
        plot = self._own_containers()
        self._orientation = self._extract_orientation(plot)
        patches = self._patches(plot)
        data = self._extract_bar_container_data(plot)
        if data is None:
            raise ExtractionError(self.type, plot)

        levels = self._labels_for(patches, data)

        # A horizontal bar's magnitude runs along x and its label sits on y,
        # which is the layout the renderer reads for a horizontal layer. The
        # vertical layer is the mirror of that.
        if self._is_horizontal:
            combined_data = list(zip(data, levels))  # type: ignore
        else:
            combined_data = list(zip(levels, data))  # type: ignore

        if not combined_data:
            raise ExtractionError(self.type, plot)

        return [{"x": x, "y": y} for x, y in combined_data]

    def _labels_for(self, patches: list[Rectangle], data: list) -> list[str]:
        """
        What to announce alongside each magnitude.

        The tick labels when there is one per bar, and the positions the bars
        were drawn at otherwise.

        The labels are one *presentation* of x, not x itself. matplotlib puts
        exactly one tick per category on a categorical axis, so the counts
        agree there by construction -- and on a numeric axis the tick locator
        picks its own breaks, so they have no reason to. Three bars against
        five ticks used to return ``None`` and raise, which is fatal to the
        whole figure, so a bar chart with a numeric x produced no HTML at all
        (#382). That is matplotlib's own grouped-bar shape::

            x = np.arange(len(species))
            ax.bar(x + offset, measurement, width, label=attribute)

        which survives in the gallery only because the example goes on to
        call ``set_xticks(x + width, species)`` and make the counts line up.

        Raising was the wrong response to a real hazard. Pairing three bars
        against five labels would announce the wrong name for every bar, so
        the mismatch does have to be caught -- but a bar at x=0 with no tick
        beside it still has a position, and announcing ``0`` is honest where
        announcing nothing is not.

        Parameters
        ----------
        patches : list of Rectangle
            This layer's bars, already flattened out of their containers.
        data : list
            One magnitude per bar, used for its length.

        Returns
        -------
        list of str
            One label per bar, either read off the axis or derived from the
            bars' own centres.
        """
        levels = self.extract_level(self.ax, self._level_key)
        if levels and len(levels) == len(data):
            return levels

        return [self._bar_position(patch) for patch in patches]

    @staticmethod
    def _patches(plot: list[BarContainer] | None) -> list[Rectangle]:
        """Every bar of every container, in the order they are held."""
        if not plot:
            return []
        return [patch for container in plot for patch in container.patches]

    def _own_containers(self) -> list[BarContainer] | None:
        """
        The containers this layer describes.

        The containers its own call drew when the patch could name them, and
        every ``BarContainer`` on the axes otherwise.

        The sweep is not a fallback in the apologetic sense -- seaborn draws
        one bar layer as several containers, one per hue group, and registers
        it from a seaborn-level patch where no single container is the answer.
        What the sweep cannot do is tell one ``ax.bar()`` call's bars from
        another's, so two overlaid calls each found both containers' patches,
        failed the count check against one axis' worth of tick labels, and
        raised ``ExtractionError`` -- fatal to the whole figure (#380).

        Returns
        -------
        list of BarContainer, optional
            One or more containers, in the order the axes holds them. ``None``
            when the axes holds no container list at all, which the caller
            already treats as nothing to extract.
        """
        if self._own_bars is not None:
            return [self._own_bars]
        return self.extract_container(self.ax, BarContainer, include_all=True)

    def _extract_bar_container_data(
        self, plot: list[BarContainer] | None
    ) -> list | None:
        """
        Read one magnitude per bar, in the containers' own order.

        It used to take the labels as well, and return ``None`` when their
        count disagreed with the bars' -- which the caller turned into an
        ``ExtractionError`` and so into an empty render. That decision now
        lives in ``_labels_for``, which answers it with the bars' positions
        instead of with nothing, so the parameter is gone rather than left
        vestigial (#382).

        Parameters
        ----------
        plot : list of BarContainer, optional
            The containers holding the bars of this layer.

        Returns
        -------
        list, optional
            One magnitude per bar, or None when there are no containers.
        """
        if plot is None:
            return None

        # Since v0.13, Seaborn has transitioned from using `list[Patch]` to
        # `list[BarContainers] for plotting bar plots.
        # So, extract data correspondingly based on the level.
        # Flatten all the `list[BarContainer]` to `list[Patch]`.
        plot = self._patches(plot)

        self._elements.extend(plot)

        # A bar's magnitude is the dimension it grows along: the width of a
        # horizontal bar, the height of a vertical one.
        if self._is_horizontal:
            return [_magnitude(patch.get_width()) for patch in plot]

        return [_magnitude(patch.get_height()) for patch in plot]
