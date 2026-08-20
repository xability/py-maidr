from __future__ import annotations

import math
import uuid

import numpy as np
import numpy.ma as ma
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection
from matplotlib.colors import to_rgba

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError
from maidr.util.mixin import CollectionExtractorMixin, LineExtractorMixin


#: The keyword ``Axes.scatter`` hands its own ``PathCollection`` to this layer
#: under. Named once and imported at both ends rather than spelled twice:
#: ``kwargs.get`` falls back to sweeping the axes on a mismatch, so a typo
#: would not raise -- it would quietly restore the behaviour #426 removed.
#:
#: Lives here rather than beside ``common.drawn_as`` because ``maidr.patch``
#: imports ``maidr.core`` and not the other way about.
DRAWN_POINTS = "_maidr_points"

#: The keyword the scatter patch hands one hue group to this layer under: a
#: ``(name, members)`` pair naming the group and listing the collection
#: offsets that belong to it. Absent for an ungrouped scatter, which is the
#: chart this layer has always read and still reads unchanged.
HUE_GROUP = "_maidr_hue_group"

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


def hue_groups(ax: Axes, collection: PathCollection) -> list[tuple[str, list[int]]] | None:
    """
    The hue groups a scatter was drawn with, or ``None`` when it has none.

    ``seaborn`` draws a hue-grouped scatter as **one** ``PathCollection``
    carrying a colour per point, not one collection per group, so the grouping
    survives only in those colours and in the legend that names them. Read
    together they give it back exactly: every point's colour is one of the
    legend's swatches, and each swatch carries its group's name.

    Everything here is a reason to decline, and each has a chart behind it:

    - **One colour for the whole collection.** ``get_facecolors()`` returns a
      single row when every point shares a colour, which is what an ungrouped
      scatter and a ``style=``-only scatter both produce.
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
    - **A point no swatch claims.** A *continuous* hue is the case: measured,
      ``hue='v'`` on a numeric column gives ten distinct colours for ten
      points against five legend levels sampled at round numbers, so most
      points match nothing. That is a colour *scale*, not a grouping, and
      splitting it into one layer per point would be nonsense.
    - **Fewer than two groups.** Nothing to tell apart.

    Parameters
    ----------
    ax : Axes
        The axes drawn on, for its legend.
    collection : PathCollection
        The points.

    Returns
    -------
    list of (str, list of int) or None
        One entry per group in legend order, naming it and listing the
        collection offsets that belong to it, or ``None`` for a scatter that
        is not grouped.
    """
    colours = [_rgba(row) for row in collection.get_facecolors()]
    if len(colours) < 2 or any(colour is None for colour in colours):
        return None

    legend = ax.get_legend()
    if legend is None:
        return None

    named = _named_colours(legend, set(colours))
    if named is None or len(named) < 2:
        return None

    members: dict[str, list[int]] = {name: [] for name in named.values()}
    for index, colour in enumerate(colours):
        name = named.get(colour)
        if name is None:
            return None
        members[name].append(index)

    groups = [(name, found) for name, found in members.items() if found]
    return groups if len(groups) > 1 else None


class ScatterPlot(MaidrPlot, CollectionExtractorMixin, LineExtractorMixin):
    def __init__(self, ax: Axes, **kwargs) -> None:
        super().__init__(ax, PlotType.SCATTER)
        # The collection this layer's own call drew, when the patch could say.
        # `None` falls back to the first collection on the axes, which is the
        # right answer only while a layer *is* one collection.
        #
        # Guarded on the type rather than on presence: `seaborn.scatterplot`
        # is patched through the same wrapper and returns an `Axes`, not the
        # collection. Falling back is correct there -- measured, it draws a
        # single `PathCollection` of every point even under `hue`, so the
        # sweep finds exactly the right one.
        own_points = kwargs.get(DRAWN_POINTS, None)
        self._own_points = (
            own_points if isinstance(own_points, PathCollection) else None
        )

        # The hue group this layer reads, when the patch found one. `None`
        # means the layer reads every point the collection holds, which is
        # what an ungrouped scatter has always done.
        group = kwargs.get(HUE_GROUP, None)
        self._group_name = group[0] if group else None
        self._group_members = set(group[1]) if group else None

        # A grouped layer addresses its points through the collection's id, so
        # the collection needs one before the SVG is written. Assigned here
        # rather than relied upon, for the reason `HexbinPlot` and
        # `contour.tag` give: matplotlib stamps a gid at *draw* time, and the
        # schema is built first -- so reading it here would find `None` and
        # the layer would ship with an empty selector list, announcing
        # correctly and highlighting nothing.
        #
        # Every group shares the one collection, so the first layer built
        # names it and the rest find the name already there.
        if self._group_members is not None and self._own_points is not None:
            if self._own_points.get_gid() is None:
                self._own_points.set_gid(f"maidr-{uuid.uuid4()}")

        # Where each emitted point sits among the drawn ones, filled in by
        # extraction and read by `_get_selector`. `render()` builds `data`
        # before `selectors`, so the order is guaranteed rather than lucky --
        # and a selector list built from a stale one would highlight the
        # previous group's points, which is the failure nothing announced can
        # see (xability/maidr#814).
        self._drawn_positions: list[int] = []

    def render(self) -> dict:
        """
        The base schema, plus the name of the group this layer reads.

        ``MaidrLayer.name`` is the field xability/maidr#828 added so that two
        layers of a kind can be told apart -- which is exactly the position a
        split scatter puts a reader in. Without it the chart offers three
        ``point`` layers and no way to know which is which.

        Distinct from ``title``, which every layer of a figure carries and
        which names the *chart*.
        """
        schema = super().render()
        if self._group_name:
            schema[MaidrKey.NAME] = self._group_name
        return schema

    def _get_selector(self) -> str | list[str]:
        """
        Address this layer's points, whether or not it is one group of several.

        An ungrouped scatter keeps the selector it has always had. matplotlib
        writes a uniformly styled collection as one ``<g>`` holding every
        ``<use>``, so one selector matching them all is both correct and in
        document order.

        A hue-grouped one cannot use it: the collection holds every group's
        points, so that selector would light up the whole chart for a layer
        that announces a third of it. Under per-point colours matplotlib
        writes **one ``<g>`` per point** instead -- measured, six points give
        six groups of one ``<use>`` each -- so each point has an element of
        its own to name, and the layer names only its own.

        ``nth-of-type`` rather than ``nth-child``, for the reason
        :class:`~maidr.core.plot.hexbinplot.HexbinPlot` gives: the shared
        marker is written into a ``<defs>`` sibling ahead of the point groups,
        and counting that would shift every point by one.
        """
        if self._group_members is None:
            return ["g[maidr='true'] > g > use"]

        collection = self._own_points
        if collection is None:
            collection = self.extract_collection(self.ax, PathCollection)
        gid = collection.get_gid() if collection is not None else None
        if gid is None:
            return []

        return [
            f"g[id='{gid}'] > g:nth-of-type({position + 1}) > use"
            for position in self._drawn_positions
        ]

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
        if self._group_members is not None:
            z_label = self._legend_title()
            if z_label:
                axes_data[MaidrKey.Z] = self._axis_config(label=z_label)

        return axes_data

    @staticmethod
    def _compute_tick_step(ticks: np.ndarray) -> float | None:
        """Compute tick step from an array of tick positions.

        Returns the tick interval if ticks are uniformly spaced,
        otherwise returns ``None``.
        """
        if ticks is None or len(ticks) < 2:
            return None
        diffs = np.diff(ticks)
        if np.allclose(diffs, diffs[0]):
            return float(diffs[0])
        return None

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

    def _extract_plot_data(self) -> list[dict]:
        plot = self._own_points
        if plot is None:
            plot = self.extract_collection(self.ax, PathCollection)
        data = self._extract_point_data(plot)

        if data is None:
            raise ExtractionError(self.type, plot)

        return data

    def _extract_point_data(self, plot: PathCollection | None) -> list[dict] | None:
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
        members = self._group_members
        samples: list[dict] = []
        positions: list[int] = []
        position = 0

        for index, (x, y) in enumerate(ma.getdata(plot.get_offsets())):
            if not (math.isfinite(x) and math.isfinite(y)):
                continue
            drawn_at = position
            position += 1
            if members is not None and index not in members:
                continue
            samples.append(self._sample(float(x), float(y), x_ticks, y_ticks))
            positions.append(drawn_at)

        self._drawn_positions = positions
        return samples

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
        x_slots = sorted(x_ticks)
        y_slots = sorted(y_ticks)
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
