from __future__ import annotations

import uuid

import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import Collection

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError


class HexbinPlot(MaidrPlot):
    """
    A hexagonal bin lattice read as a grid of counted cells.

    ``Axes.hexbin`` answers an overplotted scatter by binning the points into
    hexagons and encoding each bin's count as fill. Read that way it is a
    heatmap, and the navigation, braille and pitch all transfer.

    The one real difference is that a hex lattice **staggers alternate rows by
    half a cell**, which is what lets the hexagons tessellate. Two consequences
    shape everything below.

    First, a bin's column index is not its position: bin 3 of one row and bin 3
    of the next sit at different x. So each bin carries its own centre, and the
    frontend announces centres rather than indices.

    Second, matplotlib does not emit the bins in the order the grid reads them.
    ``get_offsets()`` is built lattice by lattice and, within each, x index by x
    index -- so consecutive offsets walk *up a column*, and the second lattice
    (the offset rows) comes after the whole of the first. Regrouping the points
    into rows without regrouping the selectors alongside them would leave every
    bin past the first row boundary highlighting a hexagon belonging to someone
    else, which on a staggered lattice is not even a neighbour in the direction
    a reader would guess.

    Rows are ragged by design and are left that way. The lattices hold
    different numbers of bins, and ``mincnt`` or a ``C`` argument drops the
    empty ones, so a row can be shorter than the one below it. Padding would
    invent bins that were never drawn; the frontend's ``MovableGrid`` clamps a
    row change to the new row's length precisely because grids arrive ragged.

    Notes
    -----
    The collection comes from the patch rather than being searched for on the
    axes. ``hexbin(marginals=True)`` draws two further ``PolyCollection``s for
    the marginal distributions, and a violin or a ``fill_between`` band on the
    same axes is one too -- so "the PolyCollection on this Axes" does not
    identify the lattice, while the call's own return value does.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        self._collection: Collection | None = kwargs.pop("collection", None)
        self._z_label = kwargs.pop("z_label", "count")
        #: Emission indices of the bins, in the row-major order the points are
        #: emitted in. This is what keeps the selectors aligned with them.
        self._bin_order: list[int] = []
        super().__init__(ax, PlotType.HEXBIN)

    def _extract_axes_data(self) -> dict:
        """
        Extend the base per-axis mapping with the ``z`` axis the fill encodes.

        Returns
        -------
        dict
            ``{"x": ..., "y": ..., "z": {"label": ...}}``.
        """
        axes_data = super()._extract_axes_data()
        axes_data[MaidrKey.Z] = self._axis_config(label=self._z_label)
        return axes_data

    def _extract_plot_data(self) -> list[list[dict]]:
        """
        Read the lattice as rows of bins, bottom row first.

        Returns
        -------
        list of list of dict
            One list per lattice row, each holding ``{"x", "y", "count"}`` for
            every bin in it, left to right.

        Raises
        ------
        ExtractionError
            When the call left no readable lattice.
        """
        collection = self._collection
        if collection is None:
            raise ExtractionError(self.type, self.ax)

        offsets = np.asarray(collection.get_offsets(), dtype=float)
        values = collection.get_array()
        if values is None or offsets.ndim != 2 or offsets.shape[0] == 0:
            raise ExtractionError(self.type, self.ax)

        values = np.asarray(values, dtype=float)
        if len(values) != len(offsets):
            # The two are filtered together by `mincnt`, so they cannot
            # disagree on any matplotlib this reads -- but the whole scheme
            # below indexes one by the other, and a silent mismatch would
            # pair a bin with a stranger's count.
            raise ExtractionError(self.type, self.ax)

        # Grouped on the y centre by exact equality, which is exact rather
        # than approximate here: matplotlib builds every centre in a row from
        # the same `index * spacing + origin`, so a row's values are identical
        # bit for bit, and the two lattices are half a spacing apart.
        rows: dict[float, list[int]] = {}
        for index, (_, y) in enumerate(offsets):
            rows.setdefault(float(y), []).append(index)

        # Ascending y, because the frontend's UPWARD steps to the *next* row
        # index -- so row 0 is the bottom of the chart, as it is for a heatmap.
        self._bin_order = []
        data: list[list[dict]] = []
        for y in sorted(rows):
            in_row = sorted(rows[y], key=lambda index: offsets[index][0])
            data.append(
                [
                    {
                        MaidrKey.X: float(offsets[index][0]),
                        MaidrKey.Y: float(offsets[index][1]),
                        MaidrKey.COUNT: float(values[index]),
                    }
                    for index in in_row
                ]
            )
            self._bin_order.extend(in_row)

        # Assigned here rather than relied upon: a gid is otherwise only
        # stamped at draw time, and the schema is built first. `AreaPlot` and
        # `MultiLinePlot` do the same for the same reason.
        if collection.get_gid() is None:
            collection.set_gid(f"maidr-{uuid.uuid4()}")
        self._elements.clear()
        self._elements.append(collection)

        return data

    def _get_selector(self) -> list[str]:
        """
        Return one selector per bin, in the order the points are emitted.

        Every bin is drawn, including the empty ones, so the SVG holds one
        ``<use>`` per offset and the correspondence is exact. What it is *not*
        is in reading order, so each bin is addressed by its own emission index
        rather than by relying on document order -- see the class docstring.

        ``nth-of-type`` rather than ``nth-child`` because matplotlib writes the
        shared hexagon into a ``<defs>`` sibling ahead of the groups, and
        counting that would shift every bin by one.

        Returns
        -------
        list of str
            One selector per bin, row-major, bottom row first.
        """
        gid = self._collection.get_gid() if self._collection is not None else None
        if gid is None:
            return []
        return [
            f"g[id='{gid}'] > g:nth-of-type({index + 1}) > use"
            for index in self._bin_order
        ]
