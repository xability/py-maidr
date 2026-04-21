"""ViolinBoxPlot — computes box-plot statistics from raw violin data."""

from __future__ import annotations

import uuid
from typing import Any

from matplotlib.axes import Axes

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.core.plot.maidr_plot import MaidrPlot
from maidr.core.plot.violinplot import ViolinBoxStatsCalculator


class ViolinBoxPlot(MaidrPlot):
    """
    Represents the box-statistics layer of a violin plot.

    Unlike the regular ``BoxPlot`` class, this does **not** rely on
    synthetic matplotlib artists.  Instead it computes Q1/Q2/Q3/min/max
    directly from the raw data arrays and produces the ``BoxPoint[]``
    schema required by the MAIDR violin-plot specification.

    Selectors are built from the *existing* inner-box artists that
    matplotlib or seaborn already drew (LineCollections or Line2D objects).

    Parameters
    ----------
    ax : Axes
        The matplotlib Axes containing the rendered violin plot.
    **kwargs
        groups : list[str]
            Category label for each violin (e.g. ``["Ideal", "Good"]``).
        values : list[np.ndarray]
            Raw data arrays — one per violin.
        orientation : str
            ``"vert"`` (default) or ``"horz"``.
        violin_options : dict | None
            ``{showMedian, showMean, showExtrema, showOutliers}`` flags.
        use_full_range : bool
            If ``True`` use actual data min/max (matplotlib style);
            otherwise use Tukey fences (seaborn style).
        mpl_artists : dict | None
            LineCollection artists from ``Axes.violinplot()`` return dict.
            Keys: ``cmins``, ``cmaxes``, ``cbars``, ``cmedians``, ``cmeans``.
        sns_box_lines : list[dict] | None
            Per-violin classified Line2D objects from seaborn inner box.
            Each dict has keys ``whisker``, ``iq``, ``median``.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        super().__init__(ax, PlotType.VIOLIN_BOX, **kwargs)

        self._groups: list[str] = kwargs.get("groups", [])
        self._values: list = kwargs.get("values", [])
        self._orientation: str = kwargs.get("orientation", "vert")
        self._violin_options: dict[str, Any] | None = kwargs.get("violin_options", None)
        self._use_full_range: bool = kwargs.get("use_full_range", False)

        # Artist references for selector extraction.
        self._mpl_artists: dict | None = kwargs.get("mpl_artists", None)
        self._sns_box_lines: list[dict] | None = kwargs.get("sns_box_lines", None)

        # GID maps populated during _extract_plot_data().
        self._mpl_gids: dict[str, str] = {}  # key → GID for LineCollections
        self._sns_gids: list[dict[str, str]] = []  # per-violin {role → GID}

        # Enable highlighting when we have artists to tag.
        has_artists = bool(self._mpl_artists) or bool(self._sns_box_lines)
        self._support_highlighting = has_artists

    # ------------------------------------------------------------------
    # Selector
    # ------------------------------------------------------------------
    def _get_selector(self) -> list[dict]:
        """
        Return structured ``BoxSelector[]`` per violin-plot spec §7.2.

        Builds CSS selectors from the GIDs assigned to inner-box artists.

        * **Matplotlib** path: each statistical element is a single
          ``LineCollection`` containing N segments (one per violin).
          Selectors use ``nth-child`` to target individual segments.

        * **Seaborn** path: each element is an individual ``Line2D``
          with its own GID.
        """
        num_violins = len(self._groups)

        if self._mpl_gids:
            return self._build_mpl_selectors(num_violins)
        if self._sns_gids:
            return self._build_sns_selectors()

        # Fallback — no artists, return empty selectors.
        return [self._empty_selector() for _ in range(num_violins)]

    # ------------------------------------------------------------------
    # Data extraction
    # ------------------------------------------------------------------
    def _extract_plot_data(self) -> list[dict]:
        """
        Compute ``BoxPoint[]`` from raw data and tag inner-box artists.

        Returns
        -------
        list[dict]
            One dict per violin with keys: ``z, lowerOutliers, min,
            q1, q2, q3, max, upperOutliers, mean?``.
        """
        # Tag artists and register elements for SVG highlighting.
        self._tag_artists()

        groups = self._resolve_groups()
        box_data: list[dict] = []

        for group, vals in zip(groups, self._values):
            if self._use_full_range:
                stats = ViolinBoxStatsCalculator.compute_full_range(vals)
            else:
                stats = ViolinBoxStatsCalculator.compute(vals)

            record: dict = {
                MaidrKey.Z.value: str(group),
                MaidrKey.LOWER_OUTLIER.value: stats[MaidrKey.LOWER_OUTLIER.value],
                MaidrKey.MIN.value: round(stats[MaidrKey.MIN.value], 4),
                MaidrKey.Q1.value: round(stats[MaidrKey.Q1.value], 4),
                MaidrKey.Q2.value: round(stats[MaidrKey.Q2.value], 4),
                MaidrKey.Q3.value: round(stats[MaidrKey.Q3.value], 4),
                MaidrKey.MAX.value: round(stats[MaidrKey.MAX.value], 4),
                MaidrKey.UPPER_OUTLIER.value: stats[MaidrKey.UPPER_OUTLIER.value],
            }

            # Include mean only when requested.
            show_mean = (
                self._violin_options.get("showMean", False)
                if self._violin_options
                else False
            )
            if show_mean and MaidrKey.MEAN.value in stats:
                record[MaidrKey.MEAN.value] = round(stats[MaidrKey.MEAN.value], 4)

            box_data.append(record)

        return box_data if self._orientation == "vert" else list(reversed(box_data))

    # ------------------------------------------------------------------
    # Artist tagging
    # ------------------------------------------------------------------
    def _tag_artists(self) -> None:
        """Assign ``maidr-`` GIDs to inner-box artists and register elements."""
        if self._mpl_artists:
            self._tag_mpl_artists()
        elif self._sns_box_lines:
            self._tag_sns_artists()

    def _tag_mpl_artists(self) -> None:
        """Tag matplotlib LineCollection artists with GIDs."""
        for key, artist in self._mpl_artists.items():
            gid = f"maidr-{uuid.uuid4()}"
            artist.set_gid(gid)
            self._mpl_gids[key] = gid
            self._elements.append(artist)

    def _tag_sns_artists(self) -> None:
        """Tag seaborn inner-box Line2D artists with GIDs."""
        for violin_lines in self._sns_box_lines:
            gid_map: dict[str, str] = {}
            for role, line in violin_lines.items():
                if line is not None:
                    gid = f"maidr-{uuid.uuid4()}"
                    line.set_gid(gid)
                    gid_map[role] = gid
                    self._elements.append(line)
            self._sns_gids.append(gid_map)

    # ------------------------------------------------------------------
    # Selector builders
    # ------------------------------------------------------------------
    def _build_mpl_selectors(self, num_violins: int) -> list[dict]:
        """
        Build selectors for matplotlib violinplot.

        Each ``LineCollection`` renders as ``<g id="gid"> <path/>... </g>``
        with one ``<path>`` per violin segment.  Use ``:nth-child(i)`` to
        select the *i*-th violin's element.
        """
        cmins_gid = self._mpl_gids.get("cmins", "")
        cmaxes_gid = self._mpl_gids.get("cmaxes", "")
        cbars_gid = self._mpl_gids.get("cbars", "")
        cmedians_gid = self._mpl_gids.get("cmedians", "")
        cmeans_gid = self._mpl_gids.get("cmeans", "")

        selectors: list[dict] = []
        for i in range(num_violins):
            nth = i + 1  # CSS nth-child is 1-indexed
            sel: dict[str, Any] = {
                MaidrKey.LOWER_OUTLIER.value: [],
                MaidrKey.MIN.value: (
                    f"g[id='{cmins_gid}'] > path:nth-child({nth})" if cmins_gid else ""
                ),
                # cbars is the vertical whisker bar (min→max), not the IQ range.
                # Matplotlib violinplot has no IQ-range visual element.
                MaidrKey.IQ.value: (
                    f"g[id='{cbars_gid}'] > path:nth-child({nth})" if cbars_gid else ""
                ),
                MaidrKey.Q2.value: (
                    f"g[id='{cmedians_gid}'] > path:nth-child({nth})"
                    if cmedians_gid
                    else ""
                ),
                MaidrKey.MAX.value: (
                    f"g[id='{cmaxes_gid}'] > path:nth-child({nth})"
                    if cmaxes_gid
                    else ""
                ),
                MaidrKey.UPPER_OUTLIER.value: [],
            }
            if cmeans_gid:
                sel[MaidrKey.MEAN.value] = (
                    f"g[id='{cmeans_gid}'] > path:nth-child({nth})"
                )
            selectors.append(sel)

        return selectors

    def _build_sns_selectors(self) -> list[dict]:
        """
        Build selectors for seaborn violinplot.

        Each inner-box element is an individual ``Line2D`` with its own GID.
        """
        selectors: list[dict] = []
        for gid_map in self._sns_gids:
            whisker_gid = gid_map.get("whisker", "")
            iq_gid = gid_map.get("iq", "")
            median_gid = gid_map.get("median", "")

            sel: dict[str, Any] = {
                MaidrKey.LOWER_OUTLIER.value: [],
                MaidrKey.MIN.value: (
                    f"g[id='{whisker_gid}'] > path" if whisker_gid else ""
                ),
                MaidrKey.IQ.value: (f"g[id='{iq_gid}'] > path" if iq_gid else ""),
                MaidrKey.Q2.value: (
                    f"g[id='{median_gid}'] > path" if median_gid else ""
                ),
                MaidrKey.MAX.value: (
                    f"g[id='{whisker_gid}'] > path" if whisker_gid else ""
                ),
                MaidrKey.UPPER_OUTLIER.value: [],
            }
            selectors.append(sel)

        return selectors

    @staticmethod
    def _empty_selector() -> dict:
        return {
            MaidrKey.LOWER_OUTLIER.value: [],
            MaidrKey.MIN.value: "",
            MaidrKey.IQ.value: "",
            MaidrKey.Q2.value: "",
            MaidrKey.MAX.value: "",
            MaidrKey.UPPER_OUTLIER.value: [],
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _resolve_groups(self) -> list[str]:
        """
        Resolve group labels at render time.

        When the patch captured generic names (``"Group 1"``, ``"Group 2"``,
        ...) — typically from the matplotlib ``Axes.violinplot`` path — we
        try to replace them with actual tick labels that the user may have
        set after the plot call.
        """
        has_generic = any(g.startswith("Group ") for g in self._groups)
        if not has_generic:
            return self._groups

        # Try tick labels from the appropriate axis.
        if self._orientation == "vert":
            raw = [lbl.get_text() for lbl in self.ax.get_xticklabels()]
        else:
            raw = [lbl.get_text() for lbl in self.ax.get_yticklabels()]

        labels = [label for label in raw if label.strip()]

        if len(labels) == len(self._groups):
            return labels

        return self._groups

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def render(self) -> dict:
        """Add ``orientation`` and ``violinOptions`` to the base schema."""
        schema = super().render()
        schema[MaidrKey.ORIENTATION] = self._orientation
        if self._violin_options is not None:
            schema["violinOptions"] = self._violin_options
        return schema
