"""Layers for the Excel charts no patched matplotlib call is read as.

py-maidr reads a figure from the ``Axes`` calls that drew it, and matplotlib
has none for a radar, a bubble chart's sizes, a stock chart's candles, a
waterfall, a funnel, a treemap, a sunburst or a map. Those are drawn from
plain artists, which nothing registers, and each is described by an
:class:`ExcelLayer` built from the chart's own values. Its selectors find the
marks by the ``id`` matplotlib writes for an artist's gid, as the plotnine
reader's do.
"""

from __future__ import annotations

import copy
import uuid
from typing import Any

from matplotlib.artist import Artist
from matplotlib.axes import Axes

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.maidr_plot import MaidrPlot


class ExcelLayer(MaidrPlot):
    """
    A layer whose schema was built from an Excel chart's values.

    Parameters
    ----------
    ax : Axes
        The axes the layer's marks are drawn on.
    plot_type : PlotType
        What the layer is read as.
    labels : dict
        ``{"x": ..., "y": ..., "z": ...}``: what each axis is called. ``None``
        for ``x`` or ``y`` reads the axes' own label when the schema is built,
        after the chart has been labelled.
    data : Any
        The layer's ``data``, in the shape its type reads.
    selectors : Any
        The layer's ``selectors``, in the shape its type reads.
    formats : dict
        ``{layer axis: matplotlib axis}``: which matplotlib axis' tick
        formatter, ``"x"`` or ``"y"``, says how each of the layer's axes
        writes its numbers. A horizontal funnel's values, its ``x``, are
        along matplotlib's x axis; a map's values, its ``y``, are too.
    extra : dict, optional
        More top-level keys, such as ``orientation``.
    """

    def __init__(
        self,
        ax: Axes,
        plot_type: PlotType,
        *,
        labels: dict[str, str | None],
        data: Any,
        selectors: Any,
        formats: dict[str, str] | None = None,
        extra: dict | None = None,
    ) -> None:
        super().__init__(ax, plot_type)
        self._labels = labels
        self._data = data
        self._selectors = selectors
        self._formats = formats or {}
        self._extra = extra or {}

    def render(self) -> dict:
        """The layer's schema, with a fresh id as every layer's render has."""
        axes = {}
        for key, label in self._labels.items():
            if label is None and key in ("x", "y"):
                label = (self.ax.get_xlabel if key == "x" else self.ax.get_ylabel)()
            axes[MaidrKey(key)] = self._axis_config(label=label or key.upper())
        found = self.extract_format(self.ax) or {}
        wanted = {
            key: found[source]
            for key, source in self._formats.items()
            if source in found
        }
        if wanted:
            self._merge_format_into_axes(axes, wanted)
        schema = {
            MaidrKey.ID: str(uuid.uuid4()),
            MaidrKey.TYPE: self.type,
            MaidrKey.TITLE: self.ax.get_title(),
            MaidrKey.AXES: axes,
            MaidrKey.DATA: copy.deepcopy(self._data),
            MaidrKey.SELECTOR: copy.deepcopy(self._selectors),
        }
        schema.update(copy.deepcopy(self._extra))
        return schema

    def _extract_plot_data(self) -> Any:
        return copy.deepcopy(self._data)


def register(
    ax: Axes,
    plot_type: PlotType,
    *,
    labels: dict[str, str | None],
    data: Any,
    selectors: Any,
    formats: dict[str, str] | None = None,
    extra: dict | None = None,
) -> None:
    """
    Register an :class:`ExcelLayer` with the figure ``ax`` is on, unless it
    has nothing to read: a chart whose every value is blank registers none,
    and is left out as having no data.
    """
    rows = data if isinstance(data, list) else [data]
    if not data or all(isinstance(row, list) and not row for row in rows):
        return
    FigureManager.add_plot(
        ExcelLayer(
            ax,
            plot_type,
            labels=labels,
            data=data,
            selectors=selectors,
            formats=formats,
            extra=extra,
        )
    )


def gid(artist: Artist) -> str:
    """The artist's gid, minting one; matplotlib writes it as its ``<g id>``."""
    found = artist.get_gid()
    if found is None:
        found = f"maidr-{uuid.uuid4()}"
        artist.set_gid(found)
    return str(found)


def each_path(artist: Artist) -> str:
    """A selector for each path a line, or a collection of lines, draws."""
    return f"g[id='{gid(artist)}'] > path"


def each_mark(artist: Artist) -> str:
    """
    A selector for each mark a collection of shapes draws, in order.

    matplotlib writes a collection's shapes as paths, one each, except a
    collection of one outlined shape, which it writes as a definition and one
    ``<use>`` of it; the selector names whichever was written.
    """
    group = f"g[id='{gid(artist)}']"
    return f"{group} > path, {group} > g > use"
