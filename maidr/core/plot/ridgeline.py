"""A ridgeline layer, built from the curves a reader drew rather than read off.

matplotlib has no ridgeline call: the chart is one filled polygon per group,
offset down the page. A reader that draws one -- such as the TensorBoard
histograms reader -- knows each group's curve before it draws it, so it builds
this layer from those curves and registers it with
:meth:`~maidr.core.figure_manager.FigureManager.add_plot`. The offset each
polygon was drawn at is presentation and is never part of the layer.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import numpy as np
from matplotlib.axes import Axes
from matplotlib.artist import Artist

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot.maidr_plot import MaidrPlot


class RidgelinePlot(MaidrPlot):
    """
    One curve per group, each a value and the height of the curve there.

    Parameters
    ----------
    ax : Axes
        The axes the ridges are drawn on.
    groups : sequence
        Each group's name, in the order the ridges are drawn and navigated.
    values : sequence of array_like
        Each group's sample positions along the value axis.
    heights : sequence of array_like
        The height of each group's curve at each of its positions, before the
        group's offset was added.
    ridges : sequence of Artist
        The artist drawing each group's ridge, in the same order as the
        groups; each is named in the SVG by its gid and highlights its group.
        The order the ridges were *drawn* in may differ, so that a lower ridge
        can sit in front of the one above it.
    group_label : str
        What the groups are, such as ``"Step"``.
    height_label : str
        What a curve's height is, such as ``"Count"``.

    Raises
    ------
    ValueError
        If ``groups``, ``values``, ``heights`` and ``ridges`` differ in
        length, or a group's values and heights do.
    """

    def __init__(
        self,
        ax: Axes,
        *,
        groups: Sequence[object],
        values: Sequence[Sequence[float]],
        heights: Sequence[Sequence[float]],
        ridges: Sequence[Artist],
        group_label: str,
        height_label: str,
    ) -> None:
        super().__init__(ax, PlotType.RIDGELINE)
        if not len(groups) == len(values) == len(heights) == len(ridges):
            raise ValueError("a ridgeline needs one curve per group")
        self._groups = list(groups)
        self._values = [np.asarray(v, dtype=float) for v in values]
        self._heights = [np.asarray(h, dtype=float) for h in heights]
        if any(len(v) != len(h) for v, h in zip(self._values, self._heights)):
            raise ValueError("a curve needs one height per value")
        self._gids = []
        for ridge in ridges:
            if ridge.get_gid() is None:
                ridge.set_gid(f"maidr-{uuid.uuid4()}")
            self._gids.append(str(ridge.get_gid()))
        self._group_label = group_label
        self._height_label = height_label

    def _extract_axes_data(self) -> dict:
        """
        The value axis, the groups and the curves' heights.

        Returns
        -------
        dict
            ``x`` the value axis as the axes label it, ``y`` the groups and
            ``z`` the height, as the ridgeline trace reads them.
        """
        return {
            MaidrKey.X: self._axis_config(label=self.ax.get_xlabel() or "Value"),
            MaidrKey.Y: self._axis_config(label=self._group_label),
            MaidrKey.Z: self._axis_config(label=self._height_label),
        }

    def _extract_plot_data(self) -> list[list[dict]]:
        """
        Each group's curve, a point per sample.

        Returns
        -------
        list of list of dict
            ``{"x": group, "y": value, "density": height}`` per sample. A
            height that is not finite is left out of its curve.
        """
        return [
            [
                {"x": _plain(group), "y": float(value), "density": float(height)}
                for value, height in zip(values, heights)
                if np.isfinite(value) and np.isfinite(height)
            ]
            for group, values, heights in zip(self._groups, self._values, self._heights)
        ]

    def _get_selector(self) -> list[str]:  # type: ignore[override]
        """One selector per group, in group order, each naming its ridge."""
        return [f"g[id='{gid}'] > path" for gid in self._gids]


def _plain(group: object) -> object:
    """A group name as JSON carries it: a NumPy number as a Python one."""
    return group.item() if isinstance(group, np.generic) else group
