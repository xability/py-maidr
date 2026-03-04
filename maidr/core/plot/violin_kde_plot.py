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
from maidr.util.svg_utils import data_to_svg_coords


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

        # Register PolyCollections so highlight.py tags them in SVG.
        for poly in self._poly_collections:
            self._elements.append(poly)

    # ------------------------------------------------------------------
    # Selector
    # ------------------------------------------------------------------
    def _get_selector(self) -> list[str]:
        """Return one CSS selector per violin using PolyCollection GIDs."""
        if self._poly_gids:
            return [f"g[id='{gid}'] path, g[id='{gid}'] use" for gid in self._poly_gids]
        return ["g[id^='maidr-'] path"]

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

        for idx, kde_line in enumerate(self._kde_lines):
            self._elements.append(kde_line)
            xydata = np.asarray(kde_line.get_xydata())
            x_data, y_data = xydata[:, 0], xydata[:, 1]
            x_svg, y_svg = data_to_svg_coords(self.ax, x_data, y_data)

            x_label = x_levels[idx] if x_levels and idx < len(x_levels) else None

            violin_points = self._interpolate_violin(
                x_data, y_data, x_svg, y_svg, x_label
            )
            all_violins.append(violin_points)

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
        Resolve categorical X labels with a 3-strategy fallback chain.

        This must happen at *render* time (not patch time) because users
        often call ``ax.set_xticklabels()`` after ``ax.violinplot()``.
        """
        # Strategy 1 — current tick labels on the axes.
        try:
            raw = [lbl.get_text() for lbl in self.ax.get_xticklabels()]
            labels = [label for label in raw if label.strip()]
            if labels:
                return labels
        except Exception:
            pass

        # Strategy 2 — LevelExtractorMixin.
        levels = LevelExtractorMixin.extract_level(self.ax, MaidrKey.X)
        if levels:
            filtered = [level for level in levels if str(level).strip()]
            if filtered:
                return filtered

        # Strategy 3 — patch-time fallback.
        return self._x_levels

    def _interpolate_violin(
        self,
        x_data: np.ndarray,
        y_data: np.ndarray,
        x_svg: np.ndarray,
        y_svg: np.ndarray,
        x_label: str | None,
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
            return self._interpolated_points(left, right, y_common, x_label)
        except (ValueError, np.linalg.LinAlgError):
            return self._grouped_fallback(x_data, y_data, x_svg, y_svg, x_label)

    def _interpolated_points(
        self,
        left: list[tuple[float, float]],
        right: list[tuple[float, float]],
        y_common: np.ndarray,
        x_label: str | None,
    ) -> list[dict]:
        left_x, left_y = np.array([p[0] for p in left]), np.array([p[1] for p in left])
        right_x, right_y = (
            np.array([p[0] for p in right]),
            np.array([p[1] for p in right]),
        )

        li = np.argsort(left_y)
        ri = np.argsort(right_y)

        f_left = interpolate.interp1d(
            left_y[li],
            left_x[li],
            kind="linear",
            bounds_error=False,
            fill_value="extrapolate",
            assume_sorted=True,
        )
        f_right = interpolate.interp1d(
            right_y[ri],
            right_x[ri],
            kind="linear",
            bounds_error=False,
            fill_value="extrapolate",
            assume_sorted=True,
        )

        points: list[dict] = []
        for y_val in y_common:
            xl = float(f_left(y_val))
            xr = float(f_right(y_val))
            if np.isnan(xl) or np.isnan(xr) or np.isnan(y_val):
                continue
            width = abs(xr - xl)
            if np.isnan(width) or width <= 0:
                continue

            sx_l, sy_l = data_to_svg_coords(self.ax, np.array([xl]), np.array([y_val]))
            sx_r, sy_r = data_to_svg_coords(self.ax, np.array([xr]), np.array([y_val]))

            base: dict = {
                MaidrKey.X: x_label if x_label else xl,
                MaidrKey.Y: float(y_val),
            }
            points.append(
                {
                    **base,
                    "width": float(width),
                    "svg_x": float(sx_l[0]),
                    "svg_y": float(sy_l[0]),
                }
            )
            points.append(
                {
                    **base,
                    "width": float(width),
                    "svg_x": float(sx_r[0]),
                    "svg_y": float(sy_r[0]),
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
