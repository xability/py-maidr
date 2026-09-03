"""ViolinKdePlot — extracts KDE density curve data for violin plots."""

from __future__ import annotations

from collections import defaultdict

import numpy as np
from matplotlib.axes import Axes
from scipy import interpolate

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.core.plot.maidr_plot import MaidrPlot
from maidr.util.mixin.extractor_mixin import LevelExtractorMixin
from maidr.util.rdp_utils import simplify_curve
from maidr.util.svg_utils import data_to_svg_coords, settle_layout

#: Default maximum number of output points per violin KDE curve.
_DEFAULT_MAX_KDE_POINTS = 30


class ViolinKdePlot(MaidrPlot):
    """
    Represents the KDE (kernel density estimation) layer of a violin plot.

    Each violin's density curve is extracted as paired left/right points
    at each Y level, producing a ``ViolinKdePoint[][]`` data structure
    per the MAIDR violin-plot specification.

    Parameters
    ----------
    ax : Axes
        The matplotlib Axes containing the rendered violin plot.
    **kwargs
        poly_collections : list[PolyCollection]
            The PolyCollection objects representing each violin shape.
        kde_lines : list[Line2D]
            Line2D boundaries created from each PolyCollection's vertices.
        poly_gids : list[str]
            Unique GID assigned to each PolyCollection/Line2D pair.
        x_levels : list[str] | None
            Categorical X-axis labels captured at patch time (fallback).
        orientation : str
            ``"vert"`` (default) or ``"horz"``.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        super().__init__(ax, PlotType.VIOLIN_KDE, **kwargs)

        self._poly_collections = kwargs.get("poly_collections", [])
        self._kde_lines = kwargs.get("kde_lines", [])
        self._poly_gids = kwargs.get("poly_gids", [])
        self._x_levels = kwargs.get("x_levels", None)
        self._orientation = kwargs.get("orientation", "vert")

    # ------------------------------------------------------------------
    # Selector
    # ------------------------------------------------------------------
    def _get_selector(self) -> list[str]:
        """
        Return one CSS selector per violin using PolyCollection GIDs.

        In the order the data was emitted, which for a horizontal violin is
        the reverse of the order the collections were drawn in -- the box
        layer's convention, which the KDE layer matches.

        The reversal is done here rather than to ``self._poly_gids``, because
        that list is the constructor's and persists across renders. Reversing
        it in place put it back in drawn order on every second render while
        the data, rebuilt each time, stayed reversed -- so an even number of
        renders left selector *i* pointing at a different violin from point
        *i*, and the highlight landed on a neighbour. The same failure #354
        describes, one list further along.
        """
        if not self._poly_gids:
            return ["g[id^='maidr-'] path"]

        gids = (
            list(reversed(self._poly_gids))
            if self._orientation == "horz"
            else self._poly_gids
        )
        return [f"g[id='{gid}'] path, g[id='{gid}'] use" for gid in gids]

    # ------------------------------------------------------------------
    # Data extraction
    # ------------------------------------------------------------------
    def _extract_plot_data(self) -> list[list[dict]]:
        """
        Extract ``ViolinKdePoint[][]`` — outer list per violin, inner list
        per curve position.

        Each point contains ``{x, y, density?, width?, svg_x?, svg_y?}``.
        Both left and right sides of the violin are included (no
        deduplication) so the frontend can navigate the full outline.
        """
        x_levels = self._resolve_x_levels()
        all_violins: list[list[dict]] = []

        # Registered here rather than in `__init__` so that extraction owns the
        # whole element list and `render()` can clear it without dropping the
        # violin bodies. Both lists arrive from the constructor, so rebuilding
        # them per render costs nothing and keeps one place responsible (#354).
        for poly in self._poly_collections:
            self._elements.append(poly)

        is_horz = self._orientation == "horz"

        # The SVG coordinates read the axes position, which is only final once
        # the layout has been settled. Once for the whole layer, not once per
        # point: a layout pass measures every artist on the figure, and this
        # layer used to pay for one twice per retained level (#704).
        settle_layout(self.ax.figure)

        for idx, kde_line in enumerate(self._kde_lines):
            self._elements.append(kde_line)
            xydata = np.asarray(kde_line.get_xydata())

            if is_horz:
                # Horizontal violin: col 0 = value axis, col 1 = density axis.
                # Swap so that internal variables match vertical convention:
                #   x_data = density axis (around category position)
                #   y_data = value axis
                x_data, y_data = xydata[:, 1], xydata[:, 0]
            else:
                x_data, y_data = xydata[:, 0], xydata[:, 1]

            x_svg, y_svg = data_to_svg_coords(self.ax, xydata[:, 0], xydata[:, 1])

            x_label = x_levels[idx] if x_levels and idx < len(x_levels) else None

            violin_points = self._interpolate_violin(
                x_data, y_data, x_svg, y_svg, x_label, is_horz
            )
            all_violins.append(violin_points)

        # Reverse for horizontal to match the box layer's ordering convention.
        # `all_violins` is rebuilt every call, so reversing it is idempotent;
        # the matching order for the selectors is derived in `_get_selector`
        # rather than written back onto the constructor's gid list.
        if is_horz:
            all_violins.reverse()

        return all_violins

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def render(self) -> dict:
        """Add ``orientation`` to the base schema."""
        schema = super().render()
        schema[MaidrKey.ORIENTATION] = self._orientation
        return schema

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _resolve_x_levels(self) -> list[str] | None:
        """
        Resolve categorical labels with a 3-strategy fallback chain.

        For vertical violins categories are on the X-axis; for horizontal
        violins they are on the Y-axis.

        This must happen at *render* time (not patch time) because users
        often call ``ax.set_xticklabels()`` after ``ax.violinplot()``.

        Each strategy has to produce exactly one label per violin to be
        believed. A bare ``ax.violinplot()`` leaves the category axis numeric,
        so its ticks are values at whatever steps matplotlib chose -- seven of
        them at half-units for three violins -- and the caller pairs them with
        violins by index. That named the violin drawn at x = 2 ``"1.5"``, and
        left the KDE layer disagreeing with the box layer of the same chart,
        which calls the same three ``Group 1/2/3`` (#469).

        The count test is the one ``ViolinBoxPlot._resolve_groups()`` already
        applies to the same tick labels, which is why only this layer was
        wrong. A categorical axis -- what ``sns.violinplot()`` produces, and
        what ``ax.set_xticklabels()`` makes -- has one tick per violin and
        passes it.

        When nothing passes, the violins are named the way the box layer names
        them. Falling back to a number that came off the axis would be the bug
        again in a quieter form: it reads like a category and is not one, and
        it would still disagree with the other half of the same chart.
        """
        is_horz = self._orientation == "horz"
        tick_getter = self.ax.get_yticklabels if is_horz else self.ax.get_xticklabels
        maidr_key = MaidrKey.Y if is_horz else MaidrKey.X
        violin_count = len(self._kde_lines)

        # Strategy 1 — current tick labels on the axes.
        try:
            raw = [lbl.get_text() for lbl in tick_getter()]
            labels = [label for label in raw if label.strip()]
            if len(labels) == violin_count:
                return labels
        except Exception:
            pass

        # Strategy 2 — LevelExtractorMixin.
        levels = LevelExtractorMixin.extract_level(self.ax, maidr_key)
        if levels:
            filtered = [level for level in levels if str(level).strip()]
            if len(filtered) == violin_count:
                return filtered

        # Strategy 3 — patch-time fallback, held to the same count.
        if self._x_levels and len(self._x_levels) == violin_count:
            return self._x_levels

        # Nothing named these violins, so name them as the box layer does.
        return [f"Group {i + 1}" for i in range(violin_count)]

    def _interpolate_violin(
        self,
        x_data: np.ndarray,
        y_data: np.ndarray,
        x_svg: np.ndarray,
        y_svg: np.ndarray,
        x_label: str | None,
        is_horz: bool = False,
    ) -> list[dict]:
        """
        Interpolate left/right sides of a single violin to a common Y
        grid and return paired ``ViolinKdePoint`` dicts.
        """
        y_unique = sorted(set(y_data))
        if len(y_unique) < 2:
            return self._fallback_points(x_data, y_data, x_svg, y_svg, x_label)

        y_min, y_max = min(y_unique), max(y_unique)
        y_common = np.linspace(y_min, y_max, len(y_unique))

        x_center = np.mean(x_data)
        left = [(x, y) for x, y in zip(x_data, y_data) if x <= x_center]
        right = [(x, y) for x, y in zip(x_data, y_data) if x >= x_center]

        if not left or not right:
            return self._fallback_points(x_data, y_data, x_svg, y_svg, x_label)

        try:
            return self._interpolated_points(left, right, y_common, x_label, is_horz)
        except (ValueError, np.linalg.LinAlgError):
            return self._grouped_fallback(x_data, y_data, x_svg, y_svg, x_label)

    def _interpolated_points(
        self,
        left: list[tuple[float, float]],
        right: list[tuple[float, float]],
        y_common: np.ndarray,
        x_label: str | None,
        is_horz: bool = False,
    ) -> list[dict]:
        left_x, left_y = np.array([p[0] for p in left]), np.array([p[1] for p in left])
        right_x, right_y = (
            np.array([p[0] for p in right]),
            np.array([p[1] for p in right]),
        )

        # One knot per y, sorted. The polygon repeats its start vertex as its
        # closing vertex and its turn-around at the top, at identical x, so a
        # side holds 103 knots for 100 distinct y. Built on those, interp1d
        # asked for exactly y_min divided by the zero gap between the two
        # bottom knots: scipy warned on the user's console on every render,
        # the level came back NaN, and the guard below dropped it, so the
        # emitted range began one level above the drawn one (#705).
        # `np.unique` sorts, which is what `assume_sorted` relies on.
        left_y, li = np.unique(left_y, return_index=True)
        right_y, ri = np.unique(right_y, return_index=True)

        f_left = interpolate.interp1d(
            left_y,
            left_x[li],
            kind="linear",
            bounds_error=False,
            fill_value="extrapolate",
            assume_sorted=True,
        )
        f_right = interpolate.interp1d(
            right_y,
            right_x[ri],
            kind="linear",
            bounds_error=False,
            fill_value="extrapolate",
            assume_sorted=True,
        )

        # --- Evaluate on full grid, then simplify with RDP ---------------
        y_vals: list[float] = []
        xl_vals: list[float] = []
        xr_vals: list[float] = []
        widths: list[float] = []

        for y_val in y_common:
            xl = float(f_left(y_val))
            xr = float(f_right(y_val))
            if np.isnan(xl) or np.isnan(xr) or np.isnan(y_val):
                continue
            width = abs(xr - xl)
            if np.isnan(width) or width <= 0:
                continue
            y_vals.append(float(y_val))
            xl_vals.append(xl)
            xr_vals.append(xr)
            widths.append(width)

        if not y_vals:
            return []

        # Each Y-level produces 2 output points (left + right), so the
        # target number of Y-levels is half the desired point count.
        target_levels = max(_DEFAULT_MAX_KDE_POINTS // 2, 3)

        y_arr = np.array(y_vals)
        w_arr = np.array(widths)

        if len(y_arr) > target_levels:
            # Build a (y, width) curve and apply RDP to find the Y-levels
            # that best preserve the violin shape.
            shape_curve = np.column_stack([y_arr, w_arr])
            mask = simplify_curve(shape_curve, target=target_levels)
            indices = np.where(mask)[0]
        else:
            indices = np.arange(len(y_arr))

        # --- Convert the retained Y-levels to SVG coordinates ------------
        # One call per side rather than one per level: the transform is
        # affine and applied row by row, so the batch gives the same floats
        # the per-level calls did, without a transform per point (#704).
        sel_y = y_arr[indices]
        sel_l = np.array(xl_vals)[indices]
        sel_r = np.array(xr_vals)[indices]
        if is_horz:
            # Horizontal: xl/xr are density-axis (y in mpl), y_val is
            # value-axis (x in mpl).
            sx_l, sy_l = data_to_svg_coords(self.ax, sel_y, sel_l)
            sx_r, sy_r = data_to_svg_coords(self.ax, sel_y, sel_r)
        else:
            sx_l, sy_l = data_to_svg_coords(self.ax, sel_l, sel_y)
            sx_r, sy_r = data_to_svg_coords(self.ax, sel_r, sel_y)

        # --- Build output points for retained Y-levels -------------------
        points: list[dict] = []
        for k, i in enumerate(indices):
            y_val = y_vals[i]
            xl = xl_vals[i]
            width = widths[i]

            base: dict = {
                MaidrKey.X: x_label if x_label else xl,
                MaidrKey.Y: float(y_val),
            }
            points.append(
                {
                    **base,
                    "width": float(width),
                    "svg_x": float(sx_l[k]),
                    "svg_y": float(sy_l[k]),
                }
            )
            points.append(
                {
                    **base,
                    "width": float(width),
                    "svg_x": float(sx_r[k]),
                    "svg_y": float(sy_r[k]),
                }
            )

        return points

    def _grouped_fallback(
        self,
        x_data: np.ndarray,
        y_data: np.ndarray,
        x_svg: np.ndarray,
        y_svg: np.ndarray,
        x_label: str | None,
    ) -> list[dict]:
        y_to_x: dict[float, list[float]] = defaultdict(list)
        for x, y in zip(x_data, y_data):
            if not (np.isnan(x) or np.isnan(y)):
                y_to_x[float(y)].append(float(x))

        y_to_width: dict[float, float] = {}
        for yv, xs in y_to_x.items():
            if len(xs) >= 2:
                w = abs(max(xs) - min(xs))
                if not np.isnan(w) and w > 0:
                    y_to_width[yv] = w

        points: list[dict] = []
        for x, y, sx, sy in zip(x_data, y_data, x_svg, y_svg):
            if np.isnan(x) or np.isnan(y):
                continue
            pt: dict = {
                MaidrKey.X: x_label if x_label else float(x),
                MaidrKey.Y: float(y),
                "svg_x": float(sx),
                "svg_y": float(sy),
            }
            w = y_to_width.get(float(y))
            if w is not None:
                pt["width"] = w
            points.append(pt)
        return points

    def _fallback_points(
        self,
        x_data: np.ndarray,
        y_data: np.ndarray,
        x_svg: np.ndarray,
        y_svg: np.ndarray,
        x_label: str | None,
    ) -> list[dict]:
        return [
            {
                MaidrKey.X: x_label if x_label else float(x),
                MaidrKey.Y: float(y),
                "svg_x": float(sx),
                "svg_y": float(sy),
            }
            for x, y, sx, sy in zip(x_data, y_data, x_svg, y_svg)
            if not (np.isnan(x) or np.isnan(y))
        ]
