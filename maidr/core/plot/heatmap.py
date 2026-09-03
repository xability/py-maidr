from __future__ import annotations

import math

import numpy as np
import numpy.ma as ma
from matplotlib.axes import Axes
from matplotlib.cm import ScalarMappable
from matplotlib.collections import PolyQuadMesh, QuadMesh
from matplotlib.image import AxesImage

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError
from maidr.util.mixin import (
    DictMergerMixin,
    LevelExtractorMixin,
    ScalarMappableExtractorMixin,
)

#: Key the patch passes the artist its own call drew under. Named like
#: ``scatterplot.DRAWN_POINTS`` and read the same way.
DRAWN_GRID = "_maidr_grid"


class HeatPlot(
    MaidrPlot, LevelExtractorMixin, ScalarMappableExtractorMixin, DictMergerMixin
):
    def __init__(self, ax: Axes, **kwargs) -> None:
        self._z_label = kwargs.pop("z_label", "Z")
        self._fmt = kwargs.pop("fmt", "")
        # The grid this layer's own call drew, when the patch could say.
        # `None` falls back to searching the axes, which resolves *per axes*
        # and so hands every heatmap on one axes the same artist: two
        # `ax.pcolormesh()` calls were both announced with the first mesh's
        # values, the second chart's numbers appearing nowhere and nothing
        # raising (#527).
        #
        # Guarded on the type rather than on presence, the way
        # `ScatterPlot._own_points` is: `seaborn.heatmap` is patched through
        # the same wrapper and returns an `Axes`, not the mesh.
        own_grid = kwargs.pop(DRAWN_GRID, None)
        self._own_grid = (
            own_grid
            if isinstance(own_grid, (QuadMesh, PolyQuadMesh, AxesImage))
            else None
        )
        super().__init__(ax, PlotType.HEAT)

    def render(self) -> dict:
        base_maidr = super().render()
        heat_maidr = {
            MaidrKey.LABELS: {
                MaidrKey.Z: self._z_label,
            },
        }
        return self.merge_dict(base_maidr, heat_maidr)

    def _extract_axes_data(self) -> dict:
        """
        Extend the base per-axis ``AxisConfig`` mapping with a ``z`` axis
        describing the colormap / fill dimension.

        The base class already supplies ``x`` and ``y`` as ``AxisConfig`` dicts
        (``{"label": ...}``). Here we simply add ``z`` with its label.
        """
        axes_data = super()._extract_axes_data()
        axes_data[MaidrKey.Z] = self._axis_config(label=self._z_label)
        return axes_data

    def _extract_plot_data(self) -> dict:
        # The artist this layer was registered for, not whichever one a search
        # of the axes turns up first. `extract_scalar_mappable` resolves per
        # axes and therefore cannot tell two meshes apart -- it is still the
        # fallback, for a producer that registers a heatmap without saying
        # which artist drew it.
        plot = self._own_grid
        if plot is None:
            plot = self.extract_scalar_mappable(self.ax)
        data = self._extract_scalar_mappable_data(plot)

        if data is None:
            raise ExtractionError(self.type, plot)

        rows = len(data)
        cols = len(data[0]) if rows else 0

        return {
            MaidrKey.POINTS: data,
            MaidrKey.X: self._cell_names(plot, MaidrKey.X, cols),
            MaidrKey.Y: self._cell_names(plot, MaidrKey.Y, rows),
        }

    def _cell_names(
        self, sm: ScalarMappable | None, key: MaidrKey, count: int
    ) -> list[str] | None:
        """
        What each column or row of the grid is called.

        The axis ticks are the answer when they *are* the cells, which is the
        case a categorical heatmap draws: ``sns.heatmap`` puts one fixed tick
        at the centre of every cell and labels it, so the axis already names
        the grid.

        On a numeric axis they are not. A tick locator chooses positions that
        look tidy on an axis, with no relation to where the cells fall, and
        there are usually more of them: measured on matplotlib 3.9.4, a 2 x 3
        ``ax.hist2d(a, b, bins=(3, 2))`` produced nine x labels and seven y
        labels. Nothing raises and the values are right, so a reader moving
        to the second of three columns hears a number off the locator and has
        no way to tell it is somebody else's coordinate (#526).

        So the ticks are checked against the cells rather than assumed to be
        them, and the artist is asked when they disagree. Every one of these
        artists knows its own boundaries -- a mesh carries them as its
        coordinates, an image as its extent.

        A cell is named by its **centre**, not by the range it covers. That
        follows ``HexbinPoint``, which carries a bin's centre for the same
        reason: the grammar has one label per column, the label is announced
        on every move of the cursor, and a range doubles the length of an
        announcement to say something consecutive centres already give -- the
        spacing between them *is* the cell width.

        Parameters
        ----------
        sm : ScalarMappable or None
            The artist that drew the grid.
        key : MaidrKey
            Which axis, ``X`` or ``Y``.
        count : int
            How many cells the grid has along that axis.

        Returns
        -------
        list of str or None
            One name per cell, or whatever the axis gave when the cells
            cannot be located.
        """
        ticks = self.extract_level(self.ax, key)
        centres = self._cell_centres(sm, key, count)
        if centres is None:
            return ticks

        at = self.extract_level_positions(self.ax, key)
        # Both lengths, not just the labels': `zip` stops at the shorter of
        # its arguments, so a positions list shorter than the cells would
        # leave the tail of the comparison unmade and pass on a prefix.
        if (
            ticks is not None
            and at is not None
            and len(ticks) == len(centres)
            and len(at) == len(centres)
            and all(
                np.isclose(position, centre) for position, centre in zip(at, centres)
            )
        ):
            return ticks

        return self._as_names(centres)

    @staticmethod
    def _as_names(centres: list[float]) -> list[str]:
        """
        Write the centres out at the shortest precision that keeps them apart.

        Six significant figures to begin with, and deliberately not
        ``self._fmt``: that is the caller's format for the cell *values* --
        what ``sns.heatmap`` annotates a cell with -- and a coordinate is not
        one of those. Six is short enough to be said on every move of the
        cursor and separates the cells of any ordinary grid.

        Not of every grid, though. Cells a millionth of their own magnitude
        apart -- centres around 1e9 spaced by 1 -- all round to the same six
        figures, and two cells with one name are worse than a long one: a
        reader moving between them is told they have not moved. So the
        precision is raised until the names differ, rather than assumed to be
        enough.

        Parameters
        ----------
        centres : list of float
            One centre per cell.

        Returns
        -------
        list of str
            One name per cell, distinct wherever the centres are.
        """
        for precision in (6, 12, 17):
            names = [f"{centre:.{precision}g}" for centre in centres]
            if len(set(names)) == len(set(centres)):
                return names
        return names

    @staticmethod
    def _cell_centres(
        sm: ScalarMappable | None, key: MaidrKey, count: int
    ) -> list[float] | None:
        """
        Where the grid's cells sit along one axis, in the order they are read.

        Read from the artist rather than the axis, and in the order the
        emitted rows are already in, so the names pair with the values
        without reordering either. Which end row 0 is at is the artist's
        answer too: an image's ``origin`` decides it, and ``get_extent()``
        reports the two ends in a fixed order rather than in that one.

        Parameters
        ----------
        sm : ScalarMappable or None
            The artist that drew the grid.
        key : MaidrKey
            Which axis, ``X`` or ``Y``.
        count : int
            How many cells the grid has along that axis.

        Returns
        -------
        list of float or None
            One centre per cell, or ``None`` when the artist does not say.
        """
        if count <= 0:
            return None

        if isinstance(sm, (QuadMesh, PolyQuadMesh)):
            coordinates = np.asarray(ma.getdata(sm.get_coordinates()))
            if coordinates.ndim != 3:
                return None
            # Row 0's x and column 0's y stand for the whole grid only when
            # the mesh is axis-aligned. `pcolormesh(X, Y, Z)` accepts a
            # curvilinear one, and a sheared 2 x 3 measured as x edges of
            # [0, 1, 2, 3] on row 0 and [0.3, 1.3, 2.3, 3.3] on row 1 -- a
            # grid whose columns do not share an x, and so has no one name
            # per column. Say so by declining rather than by naming every
            # column after the row that happens to be first.
            xs, ys = coordinates[:, :, 0], coordinates[:, :, 1]
            if not (
                np.allclose(xs, xs[0, :], equal_nan=True)
                and np.allclose(ys, ys[:, :1], equal_nan=True)
            ):
                return None
            edges = xs[0, :] if key == MaidrKey.X else ys[:, 0]
        elif isinstance(sm, AxesImage):
            left, right, bottom, top = (float(edge) for edge in sm.get_extent())
            if key == MaidrKey.X:
                edges = np.linspace(left, right, count + 1)
            else:
                # `get_extent()` names its ends bottom-then-top whichever way
                # up the image is drawn, so which of them row 0 sits against
                # comes from `origin` and not from their order. Measured on a
                # 2 x 3: `origin="upper"` gives (-0.5, 2.5, 1.5, -0.5) and
                # `origin="lower"` gives (-0.5, 2.5, -0.5, 1.5), and row 0 is
                # at -0.5 in both.
                first, last = (bottom, top) if sm.origin == "lower" else (top, bottom)
                edges = np.linspace(first, last, count + 1)
        else:
            return None

        # One coordinate per cell rather than one per boundary is what
        # `shading="gouraud"` gives: the values sit *at* the coordinates
        # instead of filling the quads between them, so each coordinate is
        # already a cell's position and there is no midpoint to take.
        # Measured on a 2 x 3:
        # `pcolormesh(z, shading="gouraud")` returns coordinates of shape
        # (2, 3, 2) against the flat-shaded (3, 4, 2).
        if len(edges) == count:
            return [float(edge) for edge in edges]
        if len(edges) != count + 1:
            return None
        return [float((edges[i] + edges[i + 1]) / 2) for i in range(count)]

    def _extract_scalar_mappable_data(
        self, sm: ScalarMappable | None
    ) -> list[list] | None:
        if sm is None or sm.get_array() is None:
            return None

        # The masked array, not the buffer beneath it. `.data` is what is
        # left when the mask is stripped, and for a cell the caller hid --
        # `sns.heatmap(corr, mask=np.triu(...))`, `imshow` of a
        # `np.ma.masked_where` -- that is a number nobody drew: the mask
        # blanks six cells of a 3 x 3 correlation and the full symmetric
        # matrix was announced (#696).
        array = ma.asarray(sm.get_array())
        if isinstance(sm, (QuadMesh, PolyQuadMesh)):
            # The two mesh classes disagree about the shape they keep their
            # values in: `pcolormesh`'s QuadMesh flattens them, while
            # `pcolor`'s PolyQuadMesh keeps the grid. Reshaping unconditionally
            # would fail on the one that is already two-dimensional, so the
            # recovery is driven by the array rather than by the class.
            if array.ndim == 1:
                m, n, _ = ma.shape(sm.get_coordinates())
                # Coordinates shape is (M + 1, N + 1)
                array = array.reshape(m - 1, n - 1)

            # Tag the elements for highlighting
            self._elements.append(sm)
        else:
            self._support_highlighting = False

        # A mask is a grid of numbers as much as a grid of counts is, and
        # `ax.spy()` draws nothing else: its whole purpose is to show where a
        # matrix is non-zero. It only failed at the default format --
        # `self._fmt` is `""` unless seaborn's caller set one, and
        # `format(np.True_, "")` is `"True"`, which `float` refuses. With any
        # numeric format it already worked: `format(np.True_, ".2f")` is
        # `"1.00"`. Converting first gives the same 1 and 0 under every
        # format instead of only some of them (#564).
        if array.dtype == bool:
            array = array.astype(float)

        # A masked cell becomes a NaN here, so from this point the two ways a
        # cell can have no value -- a NaN in the input and a mask over it --
        # are one case, and `_cell` turns both into a gap. Only a float can
        # hold the NaN, and `ma.filled` refuses to write one into an integer
        # grid even where nothing is masked, so the cast is made for the
        # grids that need it and the others keep their dtype -- which the
        # fast path below and the format step both read.
        if ma.is_masked(array):
            if array.dtype.kind != "f":
                array = array.astype(float)
            array = ma.filled(array, np.nan)
        else:
            array = ma.getdata(array)

        # `format(x, "")` is `repr` for a float64 or an integer, and `float`
        # of that round-trips exactly, so at the default format the per-cell
        # loop is an identity costing a Python call per cell. Measured on
        # this method for a 1000 x 1000 float64 `imshow`, min of 3 on a
        # shared box under load: 2.0 s for the loop against 0.09 s for the
        # path below. The gate is on the dtype rather than on the format alone
        # because numpy 1.x, which the 3.9 floor still installs, formats a
        # float32 at its *own* shortest repr, so only float64 and the integer
        # kinds are known to round-trip.
        if self._fmt == "" and (array.dtype.kind in "iu" or array.dtype == np.float64):
            # An integer grid is still widened, so its cells come out as the
            # `1.0` the format loop wrote rather than as `1`; a float64 one
            # is already what `tolist` needs.
            if array.dtype != np.float64:
                array = array.astype(float)
            # A grid with nothing missing -- the common one -- is handed over
            # as `tolist` made it, without a second pass in Python to look
            # for gaps that a vectorised check has already said are not
            # there.
            if np.isfinite(array).all():
                return array.tolist()
            rows = array.tolist()
        else:
            rows = [[float(format(x, self._fmt)) for x in row] for row in array]

        return [[self._cell(value) for value in row] for row in rows]

    @staticmethod
    def _cell(value: float) -> float | None:
        """
        One cell's value, or ``None`` where it has none.

        A NaN in the input and a masked cell both arrive here as NaN, and
        neither is a reading. Emitted as it stands, ``json.dumps`` writes it
        as a bare ``NaN`` token -- legal JavaScript, invalid JSON -- and the
        core parses the SVG's ``maidr`` attribute with ``JSON.parse``, so one
        such cell stops the chart initialising at all (#427, #696).

        ``None`` serialises to ``null``, which ``HeatmapData.points`` is typed
        to carry and the core's ``toBarValue`` reads as a gap: it stays out of
        the range, sounds as the empty tone and announces as "missing". The
        same rule ``barplot._magnitude`` and ``hexbinplot._count`` apply.

        Parameters
        ----------
        value : float
            The cell's value after formatting.

        Returns
        -------
        float or None
            The value, or ``None`` for a cell without one.
        """
        return value if math.isfinite(value) else None
