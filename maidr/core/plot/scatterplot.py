from __future__ import annotations

import uuid

import numpy as np
import numpy.ma as ma
from matplotlib.axes import Axes
from matplotlib.collections import Collection, PathCollection
from matplotlib.colors import to_rgba

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.core.plot.maidr_plot import group_name_of
from maidr.exception import ExtractionError
from maidr.util.grid_axes import tick_step
from maidr.util.hue_groups import grouped_by_name
from maidr.util.mixin import CollectionExtractorMixin, LineExtractorMixin


#: The keyword a patch hands this layer the collections its own call drew
#: under -- one ``PathCollection``, or a list of them where a layer spans
#: several. Named once and imported at both ends rather than spelled twice:
#: ``kwargs.get`` falls back to sweeping the axes on a mismatch, so a typo
#: would not raise -- it would quietly restore the behaviour #426 removed.
#:
#: Lives here rather than beside ``common.drawn_as`` because ``maidr.patch``
#: imports ``maidr.core`` and not the other way about.
DRAWN_POINTS = "_maidr_points"

#: The keyword a patch hands one hue group to this layer under: a
#: ``(name, members)`` pair naming the group and listing, **per collection of**
#: ``DRAWN_POINTS`` **and in the same order**, the offsets that belong to it.
#: One collection is one entry; the list is not flattened, because an offset
#: means nothing without the collection it indexes. Absent for an ungrouped
#: scatter, which is the chart this layer has always read and still reads
#: unchanged.
HUE_GROUP = "_maidr_hue_group"

#: The keyword a patch hands the grouping *variable's* name under, for the
#: charts whose legend cannot be asked for it. Only ever a fallback: the
#: legend's title is read first and wins, because it is what the chart shows.
#:
#: Three charts need it, and all three are ones the legend cannot answer for.
#: ``sns.catplot`` builds its legend at the *figure* after the panels are
#: drawn; ``legend=False`` suppresses it outright; and a ``hue=`` that repeats
#: the ``x`` variable makes seaborn draw one with no title at all. Each still
#: has a grouping, and a group named "x" with nothing saying what "x" is a
#: kind of is half a reading.
GROUP_LABEL = "_maidr_group_label"

#: How closely two colours must agree to be the same colour. Both sides come
#: from the same palette object -- the legend handle is built from the swatch
#: the points were coloured with -- so they agree exactly today; the rounding
#: is there so a future round trip through a hex string or a float32 buffer
#: does not silently turn one group into none.
_COLOUR_TOLERANCE = 6


def _rgba(colour) -> tuple[float, ...] | None:
    """
    One colour as a rounded RGBA tuple, or ``None`` when it is not one.

    Parameters
    ----------
    colour : Any
        Anything matplotlib accepts as a colour, or anything at all: a
        legend handle's colour is whatever the artist was given, and for a
        legend *section header* seaborn gives ``'w'`` on a markerless line.

    Returns
    -------
    tuple of float or None
        The rounded RGBA, or ``None`` when the value names no colour.
    """
    try:
        return tuple(np.round(to_rgba(colour), _COLOUR_TOLERANCE))
    except (ValueError, TypeError):
        return None


def _handle_colour(handle) -> tuple[float, ...] | None:
    """
    The colour a legend handle draws its swatch in.

    ``seaborn`` builds scatter legend handles as ``Line2D`` markers rather
    than as collections, so the colour is on ``get_color``; the marker face
    is asked first for the handle types that carry it there instead.

    Parameters
    ----------
    handle : matplotlib.artist.Artist
        One entry from ``legend.legend_handles``.

    Returns
    -------
    tuple of float or None
        The rounded RGBA, or ``None`` when the handle names no single colour.
    """
    for getter in ("get_markerfacecolor", "get_facecolor", "get_color"):
        read = getattr(handle, getter, None)
        if read is None:
            continue
        colour = _rgba(read())
        if colour is not None:
            return colour
    return None


def _named_colours(legend, drawn: set[tuple[float, ...]]) -> dict | None:
    """
    Map each colour the legend names to the name it gives it.

    Only colours that are *also* on the points count. That one condition does
    all the discriminating, and it is measured rather than guessed at::

        sns.scatterplot(..., hue='g', style='s')

    gives seven legend entries -- two section headers drawn ``'w'`` with no
    marker, two hue swatches in the palette colours, and three style markers
    all drawn in the neutral ``'.2'``. Only the two hue swatches appear among
    the point colours, so keeping those is exactly the hue split, without this
    having to know anything about how seaborn lays a legend out.

    Parameters
    ----------
    legend : matplotlib.legend.Legend
        The axes' legend.
    drawn : set of tuple
        The distinct colours the points were drawn in.

    Returns
    -------
    dict or None
        Colour to name, in legend order, or ``None`` when two names claim one
        colour -- a ``style=`` legend does that, and a swatch that means two
        things cannot name the group a point belongs to.
    """
    named: dict[tuple[float, ...], str] = {}
    for handle, text in zip(legend.legend_handles, legend.get_texts()):
        colour = _handle_colour(handle)
        if colour is None or colour not in drawn:
            continue
        name = text.get_text()
        if named.get(colour, name) != name:
            return None
        named[colour] = name
    return named


def _collections(given) -> list[PathCollection]:
    """
    The collections a patch handed this layer, in the order it drew them.

    Either spelling is read: ``Axes.scatter`` has one collection to give and
    gives it, while a patch whose layer spans several -- a hue group over
    ``seaborn``'s one-collection-per-category strip plot (#586) -- gives the
    list. Everything below works in the list, so a single collection becomes
    a list of one here rather than a second path through the layer.

    Filtered by type rather than trusted, for the reason the one-collection
    form was: ``seaborn.scatterplot`` is patched through the same wrapper and
    returns an ``Axes``, not a collection. An empty answer falls back to
    sweeping the axes, which is right for that call and for that call alone.

    Parameters
    ----------
    given : Any
        Whatever arrived under :data:`DRAWN_POINTS`.

    Returns
    -------
    list of PathCollection
        Possibly empty, which is the caller's signal to sweep instead.
    """
    if isinstance(given, PathCollection):
        return [given]
    if isinstance(given, (list, tuple)):
        return [part for part in given if isinstance(part, PathCollection)]
    return []


def hue_groups(
    ax: Axes, collection: Collection
) -> list[tuple[str, list[int]]] | None:
    """
    The hue groups a scatter was drawn with, or ``None`` when it has none.

    ``seaborn`` draws a hue-grouped scatter as **one** ``PathCollection``
    carrying a colour per point, not one collection per group, so the grouping
    survives only in those colours and in the legend that names them. Read
    together they give it back exactly: every point's colour is one of the
    legend's swatches, and each swatch carries its group's name.

    Reading those colours off the collection is the whole of what is specific
    to the artist, and :func:`drawn_colours` is the whole of that -- a
    ``so.Dash()`` draws the same grouping as an unfilled ``LineCollection``
    and is read here too (#680). Every reason to decline is
    :func:`groups_from_colours`', which a bar layer reaches from a
    ``BarContainer`` and must be told the same (#599, #617).

    Parameters
    ----------
    ax : Axes
        The axes drawn on, for its legend.
    collection : Collection
        The marks. A ``PathCollection`` of points, or the
        ``LineCollection`` of ticks a dash mark draws.

    Returns
    -------
    list of (str, list of int) or None
        One entry per group in legend order, naming it and listing the
        collection offsets that belong to it, or ``None`` for a scatter that
        is not grouped.
    """
    return groups_from_colours(ax, [_rgba(row) for row in drawn_colours(collection)])


def drawn_colours(collection: Collection) -> np.ndarray:
    """
    The colours a collection drew its marks in.

    Face colours where the artist has them and edge colours otherwise, which
    is a fact about the artist rather than about the chart -- and so belongs
    beside :func:`hue_groups`, whose whole job is the part that is specific
    to the artist.

    A ``PathCollection``'s markers are filled; a ``LineCollection``'s ticks
    are not. Measured on a colour-split ``so.Dash()`` over two levels::

        get_facecolors()   (0, 4)     <- empty
        get_edgecolors()   (40, 4)

    So asking for faces alone read nothing off a chart whose colours were all
    there, one attribute over: the split was declined and the reader was
    handed one anonymous layer of forty ticks (#680).

    Parameters
    ----------
    collection : Collection
        The artist to read.

    Returns
    -------
    ndarray
        One RGBA row per mark, or however many the artist was given.
    """
    faces = np.asarray(collection.get_facecolors())
    if len(faces):
        return faces
    return np.asarray(collection.get_edgecolors())


def groups_from_colours(ax: Axes, colours: list) -> list[tuple[str, list[int]]] | None:
    """
    The groups a legend names among one layer's drawn colours.

    Everything :func:`hue_groups` does after reading a collection's drawn
    colours, which is everything that is not about the artist. A bar layer
    asks the same question of a ``BarContainer``'s patches
    (:func:`maidr.core.plot.barplot.bar_groups`) and must get the same answer,
    including the declines -- three implementations of one rule had begun to
    drift once already (#599), and this is where the second caller arrived.

    Everything here is a reason to decline, and each has a chart behind it:

    - **One colour for the whole layer.** A collection reports a single
      colour row when every mark shares one, which is what an ungrouped
      scatter and a ``style=``-only scatter both produce; a bar drawn without
      ``color=`` arrives one-long the same way.
    - **No legend.** ``legend=False`` suppresses it, and a manual
      ``ax.scatter(c=[...])`` never had one. The colours are still there but
      nothing names them, and groups called "1" and "2" are not an improvement
      on one cloud.

      Read at registration, which is to say the instant the drawing call
      returns. A legend built afterwards -- ``ax.scatter(c=[...])`` followed
      by ``ax.legend(handles=[...])`` -- does not exist yet and the chart is
      read as one layer, even though the same axes would split if asked a
      line later. seaborn builds its legend inside the call, so its charts
      are unaffected.

    Two more declines are :func:`~maidr.util.hue_groups.grouped_by_name`'s
    rather than this function's, and its docstring carries the charts behind
    them: a point no swatch claims, and fewer than two groups. They live
    there because the rug split reaches the same two from a different artist.

    Parameters
    ----------
    ax : Axes
        The axes drawn on, for its legend.
    colours : list
        One rounded RGBA per drawn thing, in draw order, as :func:`_rgba`
        gives them. A ``None`` among them declines the split.

    Returns
    -------
    list of (str, list of int) or None
        One entry per group in legend order, naming it and listing the
        positions that belong to it, or ``None`` when the layer is not
        grouped.
    """
    if len(colours) < 2 or any(colour is None for colour in colours):
        return None

    # `legend_of` rather than `ax.get_legend()`, which is what this asked
    # before. The two answer the same question -- which legend names this
    # axes' colours -- and answering it twice, differently, in one module is
    # the drift #599 extracted `legend_names` to end. The wider answer also
    # reads a lone *figure* legend (#561) and a lone shared-axis sibling's
    # (#610), which is where `seaborn.objects` puts the only legend a
    # `so.Plot(color=...)` has.
    #
    # Imported here rather than at module scope because `legend_names` reads
    # `_handle_colour` from this module, so the two would import each other.
    from maidr.util.legend_names import legend_of

    legend = legend_of(ax)
    if legend is None:
        return None

    named = _named_colours(legend, set(colours))
    if named is None or len(named) < 2:
        return None

    # `named` was built in legend order, so its values are the order #502
    # settled a grouped layer's layers on. The grouping itself, and the two
    # declines that go with it, are `grouped_by_name`'s -- shared with the rug
    # split, which reaches the same three decisions from a different artist.
    return grouped_by_name(
        [named.get(colour) for colour in colours], list(named.values())
    )


class ScatterPlot(MaidrPlot, CollectionExtractorMixin, LineExtractorMixin):
    def __init__(self, ax: Axes, **kwargs) -> None:
        super().__init__(ax, PlotType.SCATTER)
        # The collections this layer's own call drew, when the patch could
        # say. Empty falls back to the first collection on the axes, which is
        # the right answer only while a layer *is* one collection.
        #
        # A list rather than one, because a hue group is not always confined
        # to a single collection: seaborn draws a categorical scatter as one
        # collection per *category*, so a group that spans the categories --
        # which is what a hue level is -- spans the collections with them
        # (#586). `Axes.scatter` hands over the one collection it drew and
        # takes the one-entry path through everything below.
        self._own_points = _collections(kwargs.get(DRAWN_POINTS, None))

        # The hue group this layer reads, when the patch found one: one set of
        # offsets per collection, positionally paired with `_own_points`.
        # `None` means the layer reads every point there is, which is what an
        # ungrouped scatter has always done.
        group = kwargs.get(HUE_GROUP, None)
        # `HUE_GROUP` where the patch split one collection between levels and
        # so had to say *which points*; `GROUP_NAME` where the whole layer is
        # one group and only the name is in question. A `regplot` is the
        # second: `lmplot(hue=...)` calls it once per level, so its scatter is
        # that level entire and there is nothing to filter (#612). Opted into
        # here rather than read by `MaidrPlot`; see `GROUP_NAME` for why that
        # is per class, and `render` for the callable form a `FacetGrid`
        # needs.
        self._group_name = group[0] if group else group_name_of(kwargs)
        self._group_label = str(kwargs.get(GROUP_LABEL, "") or "")
        self._group_members = [set(members) for members in group[1]] if group else None

        # A grouped layer addresses its points through each collection's id,
        # so they need one before the SVG is written. Assigned here rather
        # than relied upon, for the reason `HexbinPlot` and `contour.tag`
        # give: matplotlib stamps a gid at *draw* time, and the schema is
        # built first -- so reading it here would find `None` and the layer
        # would ship with an empty selector list, announcing correctly and
        # highlighting nothing.
        #
        # Every group shares the same collections, so the first layer built
        # names them and the rest find the names already there.
        if self._group_members is not None:
            for collection in self._own_points:
                if collection.get_gid() is None:
                    collection.set_gid(f"maidr-{uuid.uuid4()}")

        # Where each emitted point sits among the drawn ones -- which
        # collection, and which position within it -- filled in by extraction
        # and read by `_get_selector`. `render()` builds `data` before
        # `selectors`, so the order is guaranteed rather than lucky -- and a
        # selector list built from a stale one would highlight the previous
        # group's points, which is the failure nothing announced can see
        # (xability/maidr#814).
        self._drawn_positions: list[tuple[int, int]] = []

    def render(self) -> dict:
        """
        The base schema, plus the name of the group this layer reads.

        ``MaidrLayer.name`` is the field xability/maidr#828 added so that two
        layers of a kind can be told apart -- which is exactly the position a
        split scatter puts a reader in. Without it the chart offers three
        ``point`` layers and no way to know which is which.

        Distinct from ``title``, which every layer of a figure carries and
        which names the *chart*.

        A callable is resolved here rather than at registration, which is what
        an ``lmplot`` needs: ``FacetGrid.add_legend()`` runs after every panel
        is drawn, so the legend that names the colours does not exist when the
        layer registers (#561, #612).
        """
        schema = super().render()
        name = self._group_name() if callable(self._group_name) else self._group_name
        if name:
            schema[MaidrKey.NAME] = name
        return schema

    def _get_selector(self) -> str | list[str]:
        """
        Address this layer's points, whether or not it is one group of several.

        An ungrouped scatter keeps the selector it has always had. matplotlib
        writes a uniformly styled collection as one ``<g>`` holding every
        ``<use>``, so one selector matching them all is both correct and in
        document order.

        A hue-grouped one cannot use it: the collections hold every group's
        points, so that selector would light up the whole chart for a layer
        that announces a third of it. Under per-point colours matplotlib
        writes **one ``<g>`` per point** instead -- measured, six points give
        six groups of one ``<use>`` each, and a strip plot's uniformly
        coloured dodged collection writes them too, because seaborn colours
        it point by point either way -- so each point has an element of its
        own to name, and the layer names only its own.

        Each position carries the collection it belongs to, so a group that
        spans several addresses each through that collection's own id.

        ``nth-of-type`` rather than ``nth-child``, for the reason
        :class:`~maidr.core.plot.hexbinplot.HexbinPlot` gives: the shared
        marker is written into a ``<defs>`` sibling ahead of the point groups,
        and counting that would shift every point by one.
        """
        if self._group_members is None:
            return ["g[maidr='true'] > g > use"]

        parts = self._own_points or self._swept()
        selectors: list[str] = []
        for part, position in self._drawn_positions:
            gid = parts[part].get_gid() if part < len(parts) else None
            if gid is None:
                return []
            selectors.append(f"g[id='{gid}'] > g:nth-of-type({position + 1}) > use")
        return selectors

    def _extract_axes_data(self) -> dict:
        """Extract axes data as canonical per-axis ``AxisConfig`` objects.

        Always returns per-axis objects with ``label``. When the grid
        navigation preconditions hold (linear scales, uniform ticks, valid
        bounds), ``min``, ``max``, and ``tickStep`` are additionally included
        on both axes. If any precondition fails, those numeric fields are
        omitted on both axes, silently disabling grid navigation while still
        complying with the canonical axes shape.
        """
        # Labels (with fallback matching base class behavior).
        x_label = self.ax.get_xlabel()
        if not x_label:
            x_label = self.extract_shared_xlabel(self.ax)
        if not x_label:
            x_label = "X"
        y_label = self.ax.get_ylabel()
        if not y_label:
            y_label = self.extract_shared_ylabel(self.ax)
        if not y_label:
            y_label = "Y"

        # Axis limits.
        x_min, x_max = self.ax.get_xlim()
        y_min, y_max = self.ax.get_ylim()

        # Tick step from major tick intervals.
        x_tick_step = self._compute_tick_step(self.ax.get_xticks())
        y_tick_step = self._compute_tick_step(self.ax.get_yticks())

        # If grid config is invalid, emit bare AxisConfig objects with labels
        # only (no min/max/tickStep). This keeps the canonical per-axis shape.
        if not self._is_valid_grid_config(
            x_min, x_max, x_tick_step, y_min, y_max, y_tick_step
        ):
            axes_data = {
                MaidrKey.X: self._axis_config(label=x_label),
                MaidrKey.Y: self._axis_config(label=y_label),
            }
        else:
            axes_data = {
                MaidrKey.X: self._axis_config(
                    label=x_label,
                    min=float(x_min),
                    max=float(x_max),
                    tick_step=float(x_tick_step),
                ),
                MaidrKey.Y: self._axis_config(
                    label=y_label,
                    min=float(y_min),
                    max=float(y_max),
                    tick_step=float(y_tick_step),
                ),
            }

        # A grouped layer names the grouping *variable* on z, the way the line
        # and point layers do. The group's own name goes on the layer rather
        # than here: `z` says what the split is by, `name` says which side of
        # it this layer is.
        #
        # The legend's title first, then whatever the patch could name the
        # variable from -- see `GROUP_LABEL` for the three charts that have a
        # grouping and no legend title to read it off.
        if self._group_members is not None:
            z_label = self._legend_title() or self._group_label
            if z_label:
                axes_data[MaidrKey.Z] = self._axis_config(label=z_label)

        return axes_data

    @staticmethod
    def _compute_tick_step(ticks: np.ndarray) -> float | None:
        """Compute tick step from an array of tick positions.

        Delegates to :func:`maidr.util.grid_axes.tick_step`, which is where
        the reading now lives: ``RugPlot`` needs the same answer for the axis
        its ticks stand on, and borrowing this private static across classes
        would couple the two on something that is not a contract. Kept as a
        method so this class's own callers are unchanged.
        """
        return tick_step(ticks)

    def _is_valid_grid_config(
        self,
        x_min: float,
        x_max: float,
        x_tick_step: float | None,
        y_min: float,
        y_max: float,
        y_tick_step: float | None,
    ) -> bool:
        """Validate that all grid navigation parameters are present and sane.

        Checks per the spec:
        - All 6 numeric values present (not None).
        - min < max for both axes.
        - tickStep > 0 for both axes.
        - tickStep <= (max - min) for both axes (at least 1 bin).
        - Both axes use linear scale.
        """
        # Both axes must be linear scale.
        if self.ax.get_xscale() != "linear" or self.ax.get_yscale() != "linear":
            return False

        # All tick steps must be present.
        if x_tick_step is None or y_tick_step is None:
            return False

        # min < max.
        if x_min >= x_max or y_min >= y_max:
            return False

        # tickStep > 0.
        if x_tick_step <= 0 or y_tick_step <= 0:
            return False

        # tickStep <= range (at least 1 bin).
        if x_tick_step > (x_max - x_min) or y_tick_step > (y_max - y_min):
            return False

        return True

    def _swept(self) -> list[PathCollection]:
        """
        The axes' first collection, for a layer whose patch named none.

        A list of one, or an empty list where the axes holds no collection at
        all -- so the callers below read it exactly as they read the ones the
        patch did name.
        """
        found = self.extract_collection(self.ax, PathCollection)
        return [found] if found is not None else []

    def _extract_plot_data(self) -> list[dict]:
        # One pass per collection, in the order the patch drew them, so a
        # group that spans several reads as one series in drawing order. A
        # layer the patch named one collection for -- every scatter before
        # #586 -- makes a single pass and comes out unchanged.
        parts = self._own_points or self._swept()
        if not parts:
            raise ExtractionError(self.type, None)

        members = self._group_members
        if members is None:
            members = [None] * len(parts)

        samples: list[dict] = []
        positions: list[tuple[int, int]] = []
        for part, (plot, mine) in enumerate(zip(parts, members)):
            read = self._extract_point_data(plot, mine)
            if read is None:
                raise ExtractionError(self.type, plot)
            found, drawn = read
            samples.extend(found)
            positions.extend((part, at) for at in drawn)

        self._drawn_positions = positions
        return samples

    def _extract_point_data(
        self, plot: PathCollection | None, members: set[int] | None
    ) -> tuple[list[dict], list[int]] | None:
        if plot is None or plot.get_offsets() is None:
            return None

        # Tag the elements for highlighting.
        self._elements.append(plot)

        # Only the points matplotlib actually drew. A marker with a non-finite
        # coordinate is not rendered -- there is nowhere to put it -- so
        # emitting one leaves the layer with more entries than the selector
        # resolves to `<use>` elements, and every point after it is highlighted
        # at its neighbour's marker while the last has none left. That is worse
        # than an absent point: the reader is shown a mark that does not
        # correspond to the value being announced, and nothing says so (#429).
        #
        # It is also what keeps the payload loadable. `json.dumps` writes `NaN`
        # as a bare token, which is legal JavaScript and invalid JSON, and the
        # core parses the SVG's `maidr` attribute with `JSON.parse` -- so one
        # of them stops the chart initialising at all (#427).
        #
        # Unlike a bar, a scatter point has nothing left to announce once its
        # position is gone: a bar keeps its category and reports a missing
        # height, while a marker at no coordinates has neither. Dropping is the
        # whole answer here rather than half of one. Masked entries arrive as
        # `NaN` through `getdata`, so they take the same path.
        x_ticks = self._category_tick_labels(self.ax, "x")
        y_ticks = self._category_tick_labels(self.ax, "y")

        # Two indices run here and they are not the same one. `index` is the
        # offset's place in the collection, which is what a hue group's
        # membership list is written in; `position` is its place among the
        # points matplotlib actually *drew*, which is what the SVG is
        # numbered by. Using either for the other's job puts the highlight on
        # a neighbour.
        #
        # No chart that splits makes them differ today, and that is measured
        # rather than assumed: only seaborn produces the per-point colours
        # and the legend a split needs, and seaborn drops non-finite rows
        # before it draws, so its collection holds no gaps for the two to
        # diverge over. `test_seaborn_drops_a_non_finite_row_before_drawing`
        # pins that, and turns red on the release where this arithmetic
        # starts mattering.
        #
        # The tick maps and their sorted slots are the same for every point,
        # so they are read once here rather than once per point: measured on
        # a 100k-point numeric scatter, sorting the two (empty) maps inside
        # the loop was most of the extraction (#715). The finiteness test is
        # one array pass for the same reason, and `drawn_at` is the running
        # count of drawn points up to each offset -- the position the old
        # per-point counter reached -- so an offset's place in the SVG is
        # read off rather than counted up to.
        x_slots = sorted(x_ticks)
        y_slots = sorted(y_ticks)

        offsets = np.asarray(ma.getdata(plot.get_offsets()), dtype=float)
        offsets = offsets.reshape(-1, 2)
        finite = np.isfinite(offsets).all(axis=1)
        drawn_at = (np.cumsum(finite) - 1).tolist()
        xs = offsets[:, 0].tolist()
        ys = offsets[:, 1].tolist()

        samples: list[dict] = []
        positions: list[int] = []
        for index in np.flatnonzero(finite).tolist():
            if members is not None and index not in members:
                continue
            samples.append(
                self._sample_on(
                    xs[index], ys[index], x_ticks, y_ticks, x_slots, y_slots
                )
            )
            positions.append(drawn_at[index])

        return samples, positions

    @classmethod
    def _sample(
        cls,
        x: float,
        y: float,
        x_ticks: dict[float, str],
        y_ticks: dict[float, str],
    ) -> dict:
        """
        One point, positioned on its axis and named after it where it has a name.

        The position and the name are the two halves of the same fix.
        :meth:`_on_axis` stops a rendering artefact being announced as a
        measurement; the name stops the reader being handed a slot index where
        the chart shows a word. Without it a strip plot announced "g is 0"
        against ticks reading ``a``, ``b``, ``c`` (#439).

        The name travels *alongside* the coordinate rather than replacing it,
        because the core sorts on the number, measures distance with it and
        groups columns by it -- ``'a' - 'b'`` is ``NaN``, so a string in ``x``
        would give an unstable sort and a highlight that lands nowhere. That is
        the shape ``ScatterPoint.xLabel`` was added for
        (xability/maidr#927).

        Both axes are asked. A strip plot drawn ``sns.stripplot(df, x='g',
        y='v')`` puts the names on x and ``sns.stripplot(df, y='g', x='v')``
        puts them on y, and asking about x alone was itself the #353 defect.

        Parameters
        ----------
        x, y : float
            The drawn coordinates.
        x_ticks, y_ticks : dict of float to str
            Each axis's tick names, from :meth:`_category_tick_labels`. Empty
            on a numeric axis, which is what keeps a measurement from being
            renamed after whichever tick it falls nearest.

        Returns
        -------
        dict
            The sample, carrying a label only for an axis that has one.
        """
        return cls._sample_on(x, y, x_ticks, y_ticks, sorted(x_ticks), sorted(y_ticks))

    @classmethod
    def _sample_on(
        cls,
        x: float,
        y: float,
        x_ticks: dict[float, str],
        y_ticks: dict[float, str],
        x_slots: list[float],
        y_slots: list[float],
    ) -> dict:
        """
        :meth:`_sample`, given the slots it would otherwise sort itself.

        The one difference is who sorts. A scatter reads thousands of points
        against the same two tick maps, and sorting them afresh for each was
        most of what a large extraction cost (#715); a caller that has the
        slots already hands them in here. :meth:`_sample` stays the
        one-point spelling for the layers that read a handful -- a dash, a
        text label -- so nothing about *what* is announced lives in two
        places.

        Parameters
        ----------
        x, y : float
            The drawn coordinates.
        x_ticks, y_ticks : dict of float to str
            As for :meth:`_sample`.
        x_slots, y_slots : list of float
            ``sorted(x_ticks)`` and ``sorted(y_ticks)``, what
            :meth:`_on_axis` snaps to.

        Returns
        -------
        dict
            The sample, carrying a label only for an axis that has one.
        """
        sample = {
            MaidrKey.X: cls._on_axis(x, x_slots),
            MaidrKey.Y: cls._on_axis(y, y_slots),
        }

        for key, ticks, position in (
            (MaidrKey.X_LABEL, x_ticks, sample[MaidrKey.X]),
            (MaidrKey.Y_LABEL, y_ticks, sample[MaidrKey.Y]),
        ):
            name = ticks.get(position)
            if name:
                sample[key] = name

        return sample

    @staticmethod
    def _on_axis(coordinate: float, slots: list[float]) -> float:
        """
        Where a point sits on its axis, rather than where it was drawn.

        On a category axis the two are not the same. ``sns.stripplot`` scatters
        each point sideways by a random offset so overlapping observations stay
        separable, and ``sns.swarmplot`` runs a packing algorithm to the same
        end. Neither offset is an observation -- both are chosen by the
        renderer, and the jitter is literally random -- but the offset is what
        ``get_offsets`` returns, so it is what was announced. Measured on a
        three-category strip plot::

            {"x": -0.0399..., "y": 0.1257...}
            {"x":  0.0629..., "y": -0.1321...}
            {"x": -0.0739..., "y": 0.6404...}

        against an axis labelled ``g`` whose ticks read ``a``, ``b``, ``c``. A
        reader was given a precise number for a quantity that does not exist,
        where the chart says a name.

        Snapping also restores the chart's shape. ``ScatterTrace`` groups
        points into columns by exact ``x`` equality, so 90 jittered points
        became 90 columns of one point each instead of 3 columns of 30 --
        column navigation stepped through individual observations and never
        through categories.

        This does not put the *name* in the payload: ``ScatterPoint.x`` is
        typed ``number`` in the grammar and the trace subtracts x values to
        sort and to group, so a string there would not survive
        (xability/maidr#927). What it does is stop a rendering artefact being
        reported as a measurement, and put the point on the tick a sighted
        reader sees it against.

        Parameters
        ----------
        coordinate : float
            The drawn coordinate.
        slots : list of float
            Tick coordinates of the category axis, ascending, or empty when
            the axis is numeric.

        Returns
        -------
        float
            The nearest category slot, or the coordinate unchanged on a
            numeric axis -- where the drawn position *is* the value, and
            snapping it would destroy the data.
        """
        if not slots:
            return coordinate

        return min(slots, key=lambda slot: abs(slot - coordinate))
