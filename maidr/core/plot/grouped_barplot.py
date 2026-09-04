from __future__ import annotations

from matplotlib.axes import Axes
from matplotlib.axis import Axis
from matplotlib.category import StrCategoryLocator
from matplotlib.container import BarContainer
from matplotlib.patches import Rectangle
from matplotlib.ticker import FixedLocator

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.core.plot.barplot import _magnitude
from maidr.exception import ExtractionError
from maidr.util.legend_names import legend_of
from maidr.util.mixin import (
    BarPositionMixin,
    ContainerExtractorMixin,
    DictMergerMixin,
    LevelExtractorMixin,
)

#: Key a patch uses to hand this layer the containers it drew, one per group,
#: instead of letting it sweep the axes. A `seaborn.objects` bar needs it for
#: a reason the classic path never has: `so.Bar(color=)` draws every level
#: into *one* container, so the groups are synthesised from the bars' colours
#: and are not on the axes to be found (#617).
DRAWN_GROUPS = "_maidr_bar_groups"


# How the helpers below fit together. `grouped_layout` is the one decision:
# it asks `bars_are_ragged` whether every container is full, `ticks_are_categories`
# and `ticks_are_the_axis_categories` what kind of ticks the axis has, then
# `bars_by_category` to place each container's bars against those ticks, and
# `shares_a_category` / `every_category_has_a_bar` to judge that placement.
# The seaborn classifier and the extractor both call `grouped_layout` and
# nothing else, so they cannot disagree.


def bars_are_ragged(plot: list[BarContainer]) -> bool:
    """
    Whether the containers of one layer hold different numbers of bars.

    ``seaborn.barplot(hue=)`` drops a row whose value is ``NaN`` before it
    draws, so a hue level that lacks one category comes out a bar short of
    its siblings (#752). Containers that are all the same length are not
    ragged, however short of the axis they run -- and that shape is two
    things: a category missing from every hue level, or the hue that
    repeats the category, which draws one bar per container. Raggedness
    alone can only be the first, so it is evidence of a hue split on its
    own; equal lengths need :func:`shares_a_category` to tell the two apart.

    Parameters
    ----------
    plot : list of BarContainer
        The containers holding this layer's series, one per group.

    Returns
    -------
    bool
        True when at least two containers differ in length.
    """
    return len({len(container.patches) for container in plot}) > 1


def _axis_for(ax: Axes, key: MaidrKey) -> Axis:
    """
    The axis the bar labels sit on.

    Parameters
    ----------
    ax : Axes
        The axes to read.
    key : MaidrKey
        Which axis, ``X`` or ``Y``.

    Returns
    -------
    Axis
        ``ax.xaxis`` for ``X``, ``ax.yaxis`` otherwise.
    """
    return ax.xaxis if key == MaidrKey.X else ax.yaxis


def ticks_are_categories(ax: Axes, key: MaidrKey) -> bool:
    """
    Whether the ticks on one axis are its categories, one per tick.

    Placing bars against the ticks only means something when the ticks
    were put there for the categories -- by ``seaborn``'s categorical axis
    or matplotlib's, which lay them with a ``StrCategoryLocator``, or by a
    caller's ``set_xticks``, which fixes them. A locator that chose its own
    breaks lays ticks that are breaks, not categories: a stacked chart over
    ``np.arange(len(species))`` has five of them in view for three bars
    (#384), and placing the bars against those would announce ``"0.5"`` as
    a category no bar was drawn for.

    Parameters
    ----------
    ax : Axes
        The axes to read.
    key : MaidrKey
        Which axis, ``X`` or ``Y``.

    Returns
    -------
    bool
        True when the ticks were fixed rather than chosen.
    """
    locator = _axis_for(ax, key).get_major_locator()
    return isinstance(locator, (FixedLocator, StrCategoryLocator))


def ticks_are_the_axis_categories(ax: Axes, key: MaidrKey) -> bool:
    """
    Whether the ticks are the categories matplotlib registered on the axis.

    A ``StrCategoryLocator`` lays one tick per category the axis was given,
    and nothing else -- seaborn's categorical axis and ``ax.bar(["a", "b"])``
    both go through it. A ``FixedLocator`` is a caller's ``set_xticks``, and
    its ticks sit wherever the caller put them; :func:`ticks_are_categories`
    admits both, and this is the narrower question.

    Parameters
    ----------
    ax : Axes
        The axes to read.
    key : MaidrKey
        Which axis, ``X`` or ``Y``.

    Returns
    -------
    bool
        True when the axis itself holds the categories.
    """
    return isinstance(_axis_for(ax, key).get_major_locator(), StrCategoryLocator)


def shares_a_category(rows: list[list[Rectangle | None]]) -> bool:
    """
    Whether some category holds bars of more than one container.

    Side by side is what a dodged chart is, so a layer in which every
    category holds one bar is not one: that is the hue that repeats the
    category, which colours the bars a plain chart would have drawn anyway
    and splits them one per container, with every container the same
    length and short of the axis. A category missing from every hue level
    leaves the containers that same shape (#752), and this is what tells
    the two apart -- the hue levels still meet at the categories they
    share.

    Parameters
    ----------
    rows : list of list of Rectangle or None
        The placement :func:`bars_by_category` returned.

    Returns
    -------
    bool
        True when a category holds bars from at least two containers.
    """
    return any(
        sum(patch is not None for patch in column) > 1 for column in zip(*rows)
    )


def every_category_has_a_bar(rows: list[list[Rectangle | None]]) -> bool:
    """
    Whether every category holds a bar of at least one container.

    A tick no container's bar is nearest to is not a category the chart
    drew: place bars against ticks at ``0, 0.5, 1, 1.5, 2`` and the half
    steps come out as categories with a gap in every series, which the
    chart never showed. Placement is declined for such an axis, and the
    layer announces the positions its bars were drawn at instead.

    Parameters
    ----------
    rows : list of list of Rectangle or None
        The placement :func:`bars_by_category` returned.

    Returns
    -------
    bool
        True when no column of ``rows`` is empty.
    """
    return all(any(patch is not None for patch in column) for column in zip(*rows))


def bars_by_category(
    plot: list[BarContainer], positions: list[float], horizontal: bool
) -> list[list[Rectangle | None]] | None:
    """
    Place every container's bars against the shared category positions.

    A bar seaborn did draw still sits against its category's tick, offset
    by the dodge -- which is less than half the spacing between ticks -- so
    the tick nearest each bar says which category it belongs to, and the
    category no bar of a container is nearest to is that container's gap.
    Read off the rectangles rather than the caller's arguments for the
    reason :meth:`~maidr.util.mixin.BarPositionMixin._bar_position` gives:
    the arguments are not available here, and the drawn centre is what the
    value became.

    Parameters
    ----------
    plot : list of BarContainer
        The containers holding this layer's series, one per group.
    positions : list of float
        Where each category's tick sits on the label axis, in the order
        the labels are announced.
    horizontal : bool
        Whether the bars grow along x, so their centres are read on y.

    Returns
    -------
    list of list of Rectangle or None, or None
        One row per container holding a bar, or ``None`` for a gap, per
        category. ``None`` altogether when the bars cannot be placed -- two
        bars of one container nearest the same tick is not one bar per
        category, and there is nothing honest to pair such a container
        with.
    """
    if not positions:
        return None

    rows: list[list[Rectangle | None]] = []
    for container in plot:
        row: list[Rectangle | None] = [None] * len(positions)
        for patch in container.patches:
            if horizontal:
                centre = patch.get_y() + patch.get_height() / 2
            else:
                centre = patch.get_x() + patch.get_width() / 2
            distances = [abs(position - centre) for position in positions]
            # The nearest tick; on a tie the lower index wins, `index` being
            # the first match.
            slot = distances.index(min(distances))
            if row[slot] is not None:
                return None
            row[slot] = patch
        rows.append(row)

    return rows


def grouped_layout(
    ax: Axes, containers: list[BarContainer], key: MaidrKey
) -> tuple[list[str], list[list[Rectangle | None]]] | None:
    """
    The one reading of a grouped layer: its labels, and every container's
    bar at each.

    Decided here and nowhere else, for two callers that used to decide it
    apart. :func:`maidr.patch.barplot._seaborn_bar_type` classifies a
    layer when seaborn draws it and :class:`GroupedBarPlot` reads it when
    the figure renders, and each re-derived the answer from the same
    primitives with a check the other lacked -- so a layer classification
    called grouped could be one extraction declined, and the decline was an
    ``ExtractionError``, fatal to the whole figure. A layer is grouped if
    and only if this returns a layout.

    Three readings, tried in order:

    1. The tick labels, paired by position, when every container holds one
       bar per label. matplotlib puts exactly one tick per category on a
       categorical axis, so the counts agree there by construction.
    2. The tick labels, with each container's bars placed against the
       ticks and ``None`` where it has none, when the ticks are categories
       and no two bars of one container sit nearest one tick. This is the
       layer seaborn leaves when it drops a ``NaN`` cell before drawing
       (#752) -- one container short, or every one of them. A tick no
       container claims is a gap in every series when the containers are
       ragged, which is honest and the only reading ragged containers have;
       and when the ticks are the axis's own categories, where it is a
       category every level is empty at. Equal-length containers on ticks a
       caller fixed by hand decline it: the half steps of
       ``set_xticks([0, 0.5, 1, 1.5, 2])`` are breaks, not categories, and
       announcing them would invent one the chart never drew -- and those
       containers can be read by position instead.
    3. None. On a numeric axis the tick locator picks its own breaks and
       they have no reason to agree with the bars (#384); a caller of this
       reads such a layer from the bars alone, or does not call it grouped.

    Parameters
    ----------
    ax : Axes
        The axes the layer was drawn on.
    containers : list of BarContainer
        The containers holding its series, one per group.
    key : MaidrKey
        The axis the bar labels sit on: ``Y`` for a horizontal layer,
        ``X`` otherwise.

    Returns
    -------
    tuple of (list of str, list of list of Rectangle or None), or None
        One label per category and one row per container holding a bar or
        ``None`` per category, or ``None`` when the containers cannot be
        read as one bar per category.
    """
    level = LevelExtractorMixin.extract_level(ax, key)
    if not level:
        return None

    if all(len(container.patches) == len(level) for container in containers):
        return level, [list(container.patches) for container in containers]

    if not ticks_are_categories(ax, key):
        return None

    # The positions are paired with the labels index for index by
    # `_ticks_in_view`; a count that disagrees means `extract_level` fell
    # back to a sibling axes' labels, whose positions these are not.
    positions = LevelExtractorMixin.extract_level_positions(ax, key)
    if positions is None or len(positions) != len(level):
        return None

    rows = bars_by_category(containers, positions, key == MaidrKey.Y)
    if rows is None:
        return None

    # Deliberately asymmetric -- see reading 2 in the docstring. Equal-length
    # containers on hand-fixed ticks can be read by position, so an unclaimed
    # tick sends them there; ragged containers have no positional reading, so
    # the unclaimed tick is announced as a gap in every series.
    if (
        not bars_are_ragged(containers)
        and not ticks_are_the_axis_categories(ax, key)
        and not every_category_has_a_bar(rows)
    ):
        return None

    return level, rows


class GroupedBarPlot(
    MaidrPlot,
    BarPositionMixin,
    ContainerExtractorMixin,
    LevelExtractorMixin,
    DictMergerMixin,
):
    def __init__(self, ax: Axes, plot_type: PlotType, **kwargs) -> None:
        super().__init__(ax, plot_type)
        self._orientation = "vert"
        self._own_groups = kwargs.get(DRAWN_GROUPS, None)

    @property
    def _is_horizontal(self) -> bool:
        return self._orientation == "horz"

    @property
    def _level_key(self) -> MaidrKey:
        """
        The axis the bar labels sit on: ``y`` for a horizontal layer
        (``seaborn.barplot(orient="h", hue=...)``), ``x`` otherwise.
        """
        return MaidrKey.Y if self._is_horizontal else MaidrKey.X

    @staticmethod
    def _extract_orientation(plot: list[BarContainer] | None) -> str:
        """
        Read the orientation matplotlib recorded on the bar containers.

        Only the first container is asked: the containers of one layer are
        drawn by the same call, so they all run the same way.

        Parameters
        ----------
        plot : list of BarContainer, optional
            The containers holding the bars of this layer, one per group.

        Returns
        -------
        str
            ``"horz"`` for a horizontal layer, ``"vert"`` otherwise.
        """
        if not plot:
            return "vert"

        return "horz" if plot[0].orientation == "horizontal" else "vert"

    def render(self) -> dict:
        """Add ``orientation`` to the base schema."""
        # Read after the super call, not before: `self._orientation` is
        # populated by `_extract_plot_data`, which that call runs.
        base_schema = super().render()
        orientation = {MaidrKey.ORIENTATION: self._orientation}
        return DictMergerMixin.merge_dict(base_schema, orientation)

    def _extract_axes_data(self) -> dict:
        """
        Extend the base per-axis ``AxisConfig`` mapping with a ``z`` axis whose
        label is sourced from the legend title (the hue/group column).

        If no legend or no legend title is available, ``z`` is omitted —
        per-point ``z`` values remain in the data payload.
        """
        axes_data = super()._extract_axes_data()

        z_label = self._extract_z_label_from_legend()
        if z_label:
            axes_data[MaidrKey.Z] = self._axis_config(label=z_label)

        return axes_data

    def _extract_z_label_from_legend(self) -> str:
        """
        Return the legend title text (trimmed) or an empty string.

        Through :func:`~maidr.util.legend_names.legend_of` rather than
        ``ax.get_legend()``, which is what this read before. The two answer
        the same question -- which legend names this axes' groups -- and the
        wider answer also reads a lone *figure* legend, which is where
        ``so.Plot`` puts the only legend a colour-split bar has (#617).
        """
        legend = legend_of(self.ax)
        if legend is None:
            return ""
        title = legend.get_title()
        if title is None:
            return ""
        return title.get_text().strip()

    def _own_containers(self) -> list[BarContainer] | None:
        """
        The containers this layer holds: the ones handed to it, or the axes'.

        Sweeping the axes is what every grouped bar read before, and it is
        right for the classic spelling -- ``seaborn.barplot(hue=)`` draws one
        container per level and nothing else onto that axes. It cannot serve
        a ``seaborn.objects`` bar, whose levels arrive in a single container
        and are split by colour after the fact (#617): the sweep would find
        the one undivided container and read every level as one group.

        The same shape :meth:`maidr.core.plot.barplot.BarPlot._own_containers`
        already has, for the reason #527 gave it -- a layer reads the artists
        its own call drew.

        Returns
        -------
        list of BarContainer, optional
            The handed-over containers when there are any, otherwise every
            container on the axes.
        """
        if self._own_groups is not None:
            return self._own_groups
        return self.extract_container(self.ax, BarContainer, include_all=True)

    def _extract_plot_data(self) -> list[list[dict]]:
        plot = self._own_containers()
        data = self._extract_grouped_bar_data(plot)

        if data is None:
            raise ExtractionError(self.type, plot)

        return data

    def _extract_grouped_bar_data(
        self, plot: list[BarContainer] | None
    ) -> list[list[dict]] | None:
        if plot is None:
            return None

        self._orientation = self._extract_orientation(plot)

        rows = self._labels_and_bars(plot)
        if rows is None:
            return None

        data = []

        self._elements.extend(
            [patch for container in plot for patch in container.patches]
        )

        # Get hue categories from legend
        hue_categories = self._extract_hue_categories_from_legend()

        for i, (container, row) in enumerate(zip(plot, rows)):
            container_data = []

            # Use hue category if available, otherwise fall back to container label
            fill_value = (
                hue_categories[i] if i < len(hue_categories) else container.get_label()
            )

            for label, patch in row:
                # A horizontal bar's magnitude runs along x and its label sits
                # on y, which is the layout the renderer reads for a
                # horizontal layer. The vertical layer is the mirror of that.
                #
                # Through `_magnitude` for the reason `BarPlot` reads its bars
                # that way: matplotlib draws a rectangle for a NaN height, and
                # `ax.bar(..., bottom=a)` over data with a gap emitted it as a
                # bare `NaN` token that `JSON.parse` refuses, so the whole
                # figure stopped initialising (#427, #696).
                #
                # A bar seaborn never drew -- the `NaN` cell it dropped before
                # drawing (#752) -- is the same gap: `None`, which the core
                # reads as "missing" and, having no element for it in the DOM,
                # steps over when it pairs the bars with their rectangles.
                #
                # Checked against the bundle shipped in `maidr/static/maidr.js`
                # rather than the core's source. Its segmented layer claims
                # one element per cell off a single cursor `s`, and when the
                # DOM holds fewer elements than there are cells (`r`) a cell
                # that is zero or unmeasured (`Qo`, the source's
                # `isDomOmittable`) takes an empty placeholder without
                # advancing it::
                #
                #     function Qo(e){return e===0||!ao(e)}
                #     ...s=0,c=(e,n)=>r&&Qo(this.barValues[e][n])||s>=t.length
                #         ?M.createEmptyElement():t[s++];
                #
                # So the `null` consumes no rectangle and the bars after it
                # still land on their own. One flat selector is therefore
                # enough; a per-bar list is not needed for alignment.
                if self._is_horizontal:
                    point = {
                        MaidrKey.X.value: self._magnitude_of(patch, horizontal=True),
                        MaidrKey.Z.value: fill_value,
                        MaidrKey.Y.value: label,
                    }
                else:
                    point = {
                        MaidrKey.X.value: label,
                        MaidrKey.Z.value: fill_value,
                        MaidrKey.Y.value: self._magnitude_of(patch, horizontal=False),
                    }
                container_data.append(point)
            data.append(container_data)

        return data

    @staticmethod
    def _magnitude_of(patch: Rectangle | None, horizontal: bool) -> float | None:
        """
        The magnitude of one bar, or ``None`` for a bar that was never drawn.

        Parameters
        ----------
        patch : Rectangle or None
            The bar, or ``None`` where the container has no bar for the
            category.
        horizontal : bool
            Whether the bar grows along x, so its magnitude is its width.

        Returns
        -------
        float or None
            The bar's magnitude through :func:`_magnitude`, or ``None``.
        """
        if patch is None:
            return None
        return _magnitude(patch.get_width() if horizontal else patch.get_height())

    def _labels_and_bars(
        self, plot: list[BarContainer]
    ) -> list[list[tuple[str, Rectangle | None]]] | None:
        """
        What to announce alongside each bar of every series, and which bar.

        The layout :func:`grouped_layout` decides, which is the same one the
        seaborn patch classified the layer by -- so a layer called grouped
        at draw time reads as one here. When there is none, the layer is
        read from its bars alone rather than raised on, since an
        ``ExtractionError`` here is fatal to the whole figure: the ticks are
        read afresh at render, and a caller's ``set_xticks`` between the two
        may have moved them onto breaks the bars do not sit against, or two
        of one container's bars onto one tick. ``maidr.stacked(ax)`` over a
        numeric axis arrives the same way, never having had a layout (#384).

        Read from the bars alone means the positions they were drawn at, the
        first container's naming every series when they all run the same
        length -- every series of a segmented chart shares one category
        axis, so the announcement has to agree across them, and this is
        what main emitted -- and, when they do not, each container's own.
        The series then no longer share one axis, which is a lesser wrong
        than no figure.

        Parameters
        ----------
        plot : list of BarContainer
            The containers holding this layer's series.

        Returns
        -------
        list of list of tuple, or None
            One row per container of ``(label, bar)`` pairs, the bar
            ``None`` for a gap; ``None`` only for no containers at all.
        """
        layout = grouped_layout(self.ax, plot, self._level_key)
        if layout is not None:
            level, rows = layout
            return [list(zip(level, row)) for row in rows]

        first = plot[0].patches if plot else []
        labels = [self._bar_position(patch) for patch in first]
        if labels and all(len(c.patches) == len(labels) for c in plot):
            return [list(zip(labels, container.patches)) for container in plot]

        rows = [
            [(self._bar_position(patch), patch) for patch in container.patches]
            for container in plot
        ]
        return rows if any(rows) else None

    def _extract_hue_categories_from_legend(self) -> list[str]:
        """
        Extract hue categories from the axes legend.

        This method reads the legend text elements from the axes legend,
        trims whitespace from each text, and returns a list of cleaned
        category names. This is used to get the actual category names
        instead of using the generic container labels like '_container0', '_container1'.

        Parameters
        ----------
        None
            This method uses the instance's axes object.

        Returns
        -------
        list[str]
            List of trimmed hue category names from the legend.
            Returns empty list if no legend is found or if legend has no text elements.

        Examples
        --------
        >>> # For a seaborn barplot with hue='category' and legend showing 'Below', 'Above'
        >>> plot = GroupedBarPlot(ax, PlotType.DODGED)
        >>> categories = plot._extract_hue_categories_from_legend()
        >>> print(categories)
        ['Below', 'Above']

        >>> # If no legend exists
        >>> categories = plot._extract_hue_categories_from_legend()
        >>> print(categories)
        []

        Notes
        -----
        Read through :func:`~maidr.util.legend_names.legend_of`, so a lone
        figure legend counts -- ``so.Plot`` puts the only legend a
        colour-split bar has there, and ``ax.get_legend()`` is ``None`` (#617).
        """
        legend = legend_of(self.ax)
        if legend is None:
            return []

        # Get legend text elements
        legend_texts = legend.get_texts()
        if not legend_texts:
            return []

        # Extract text content from legend elements and trim whitespace
        hue_categories = [text.get_text().strip() for text in legend_texts]

        # Filter out empty strings and return
        return [category for category in hue_categories if category]
