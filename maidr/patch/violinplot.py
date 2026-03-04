"""Monkey-patches for ``seaborn.violinplot`` and ``Axes.violinplot``.

Registers two MAIDR layers per violin plot:

* **VIOLIN_BOX** — box-plot summary statistics computed from the raw data,
  with CSS selectors pointing at the existing inner-box artists.
* **VIOLIN_KDE** — the KDE density curves (PolyCollection outlines).
"""

from __future__ import annotations

import uuid
from typing import Any, Callable

import numpy as np
import wrapt
from matplotlib.axes import Axes
from matplotlib.collections import PolyCollection
from matplotlib.lines import Line2D

from maidr.core.context_manager import ContextManager
from maidr.core.enum import PlotType
from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.figure_manager import FigureManager
from maidr.core.plot.violinplot import ViolinDataExtractor
from maidr.util.mixin.extractor_mixin import LevelExtractorMixin


# ======================================================================
# Seaborn
# ======================================================================
@wrapt.patch_function_wrapper("seaborn", "violinplot")
def patch_violinplot(
    wrapped: Callable, instance: Any, args: tuple, kwargs: dict
) -> Any:
    """Intercept ``seaborn.violinplot`` and register box + KDE layers."""
    if ContextManager.is_internal_context():
        return wrapped(*args, **kwargs)

    # Snapshot existing Line2D objects so we can detect new ones later.
    pre_ax = kwargs.get("ax", None)
    lines_before: set[int] = (
        {id(line) for line in pre_ax.lines} if pre_ax is not None else set()
    )

    with ContextManager.set_internal_context():
        ax = wrapped(*args, **kwargs)

    plot_ax = kwargs.get("ax", ax) or ax

    orient = kwargs.get("orient", "v")
    orientation = "horz" if orient in ("h", "horizontal", "y") else "vert"

    inner = kwargs.get("inner", "box")
    if inner in ("box", "boxplot"):
        # Identify the Line2D objects seaborn added for the inner box.
        new_lines = [line for line in plot_ax.lines if id(line) not in lines_before]
        sns_box_lines = _classify_sns_box_lines(new_lines, orientation)

        _register_box_layer(
            plot_ax,
            args,
            kwargs,
            orientation,
            use_full_range=False,
            violin_options=None,
            sns_box_lines=sns_box_lines,
        )

    _register_kde_layer(plot_ax, args, kwargs, orientation)

    return ax


# ======================================================================
# Matplotlib
# ======================================================================
@wrapt.patch_function_wrapper(Axes, "violinplot")
def mpl_violinplot(wrapped: Callable, instance: Axes, args: tuple, kwargs: dict) -> Any:
    """Intercept ``Axes.violinplot`` and register box + KDE layers."""
    if ContextManager.is_internal_context():
        return wrapped(*args, **kwargs)

    with ContextManager.set_internal_context():
        plot = wrapped(*args, **kwargs)

    plot_ax: Axes = instance
    orientation = "vert" if kwargs.get("vert", True) else "horz"

    violin_options = {
        "showMean": bool(kwargs.get("showmeans", False)),
        "showMedian": bool(kwargs.get("showmedians", False)),
        "showExtrema": bool(kwargs.get("showextrema", True)),
    }

    # Collect LineCollection artists from the return dict.
    mpl_artists: dict = {}
    for key in ("cmins", "cmaxes", "cbars", "cmedians", "cmeans"):
        if key in plot:
            mpl_artists[key] = plot[key]

    _register_box_layer(
        plot_ax,
        args,
        kwargs,
        orientation,
        use_full_range=True,
        violin_options=violin_options,
        mpl_artists=mpl_artists,
    )

    _register_kde_layer(plot_ax, args, kwargs, orientation)

    return plot


# ======================================================================
# Layer registration helpers
# ======================================================================
def _register_kde_layer(
    plot_ax: Axes, args: tuple, kwargs: dict, orientation: str
) -> None:
    """Detect PolyCollections on *plot_ax* and register a VIOLIN_KDE layer."""
    kde_polys = [c for c in plot_ax.collections if isinstance(c, PolyCollection)]
    if not kde_polys:
        return

    kde_lines: list[Line2D] = []
    poly_gids: list[str] = []

    for poly in kde_polys:
        paths = poly.get_paths()
        if not paths:
            continue
        boundary = np.asarray(paths[0].vertices)
        line = Line2D(boundary[:, 0], boundary[:, 1])
        line.axes = plot_ax

        gid = f"maidr-{uuid.uuid4()}"
        line.set_gid(gid)
        poly.set_gid(gid)

        kde_lines.append(line)
        poly_gids.append(gid)

    if not kde_lines:
        return

    x_levels = LevelExtractorMixin.extract_level(plot_ax, MaidrKey.X)

    FigureManager.create_maidr(
        plot_ax,
        PlotType.VIOLIN_KDE,
        poly_collections=kde_polys,
        kde_lines=kde_lines,
        poly_gids=poly_gids,
        x_levels=x_levels,
        orientation=orientation,
    )


def _register_box_layer(
    plot_ax: Axes,
    args: tuple,
    kwargs: dict,
    orientation: str,
    *,
    use_full_range: bool,
    violin_options: dict | None,
    mpl_artists: dict | None = None,
    sns_box_lines: list[dict] | None = None,
) -> None:
    """Extract raw data and register a VIOLIN_BOX layer."""
    groups, values = ViolinDataExtractor.extract(args, kwargs)
    if not groups or not values:
        return

    FigureManager.create_maidr(
        plot_ax,
        PlotType.VIOLIN_BOX,
        groups=groups,
        values=values,
        orientation=orientation,
        violin_options=violin_options,
        use_full_range=use_full_range,
        mpl_artists=mpl_artists,
        sns_box_lines=sns_box_lines,
    )


# ======================================================================
# Seaborn inner-box line classification
# ======================================================================
def _classify_sns_box_lines(new_lines: list[Line2D], orientation: str) -> list[dict]:
    """
    Group and classify seaborn's inner-box Line2D objects.

    Seaborn creates 3 Line2D per violin when ``inner="box"``:
      * whisker — thin line from min to max (longest data range)
      * iq      — thick line from Q1 to Q3 (medium data range)
      * median  — single-point marker (no range)

    Returns a list of dicts, one per violin, each with keys
    ``{"whisker": Line2D, "iq": Line2D, "median": Line2D}``.
    """
    if not new_lines:
        return []

    is_vert = orientation == "vert"

    # Group lines by their position (x for vertical, y for horizontal).
    groups: dict[float, list[Line2D]] = {}
    for line in new_lines:
        pos_data = line.get_xdata() if is_vert else line.get_ydata()
        pos = round(float(np.mean(pos_data)), 6)
        groups.setdefault(pos, []).append(line)

    result: list[dict] = []
    for pos in sorted(groups.keys()):
        lines = groups[pos]
        classified: dict[str, Line2D | None] = {
            "whisker": None,
            "iq": None,
            "median": None,
        }

        if len(lines) >= 3:
            # Sort by data range on the value axis (y for vert, x for horz).
            def _data_range(line: Line2D) -> float:
                vals = line.get_ydata() if is_vert else line.get_xdata()
                if len(vals) < 2:
                    return 0.0
                return float(np.ptp(vals))

            lines.sort(key=_data_range)
            classified["median"] = lines[0]  # smallest range (single point)
            classified["iq"] = lines[1]  # medium range
            classified["whisker"] = lines[2]  # largest range
        elif len(lines) == 2:

            def _data_range(line: Line2D) -> float:
                vals = line.get_ydata() if is_vert else line.get_xdata()
                if len(vals) < 2:
                    return 0.0
                return float(np.ptp(vals))

            lines.sort(key=_data_range)
            classified["median"] = lines[0]
            classified["whisker"] = lines[1]
        elif len(lines) == 1:
            classified["whisker"] = lines[0]

        result.append(classified)

    return result
