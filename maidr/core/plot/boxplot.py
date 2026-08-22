from __future__ import annotations

import uuid

import numpy as np
from matplotlib.axes import Axes

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.core.plot.scatterplot import _rgba
from maidr.exception import ExtractionError
from maidr.util.legend_names import names_for
from maidr.util.mixin import (
    ContainerExtractorMixin,
    DictMergerMixin,
    LevelExtractorMixin,
)


def _box_centre(box, horizontal: bool) -> float | None:
    """
    Where on the category axis a box sits.

    Read off the artist rather than counted, because a hue splits a category's
    slot into one box per level and only the position says which slot a box
    landed in.

    ``get_path`` answers for both spellings of a box, which is why there is no
    second branch: ``patch_artist=True`` -- what seaborn draws -- gives a
    ``PathPatch``, and the plain ``ax.boxplot`` gives a ``Line2D``, whose
    path carries the same data-space vertices its ``get_xdata`` does.
    Measured on a box at position 5.0, both answer
    ``[4.925, 5.075, 5.075, 4.925, 4.925]``. Neither is a placeholder unit
    square: ``Axes.bxp`` builds the outline from explicit vertices because a
    notched box is not a rectangle.

    Parameters
    ----------
    box : Any
        One box artist.
    horizontal : bool
        Whether the categories run up the y axis.

    Returns
    -------
    float or None
        The midpoint of the box's extent along the category axis, or ``None``
        for an artist neither spelling reads.
    """
    path = getattr(box, "get_path", None)
    if path is None:
        return None

    vertices = np.asarray(path().vertices, dtype=float)
    if vertices.ndim != 2 or not len(vertices):
        return None
    along = vertices[:, 1 if horizontal else 0]
    if not np.all(np.isfinite(along)):
        return None
    return float((along.min() + along.max()) / 2)


def _box_colour(box):
    """
    The one colour a box was drawn in, if it has one.

    Its face where it is filled and its edge otherwise, which is the same
    order :func:`maidr.core.plot.scatterplot._handle_colour` asks a legend
    handle in -- a filled box carries the hue on its face, and an unfilled
    one has only its outline to carry it.

    Parameters
    ----------
    box : Any
        One box artist.

    Returns
    -------
    tuple of float or None
        The rounded RGBA, or ``None`` when the artist names no single colour.
    """
    for getter in ("get_facecolor", "get_edgecolor", "get_color"):
        read = getattr(box, getter, None)
        if read is None:
            continue
        colour = _rgba(read())
        if colour is not None:
            return colour
    return None


class BoxPlotContainer(DictMergerMixin):
    def __init__(self):
        self._orientation = None
        self.boxes = []
        self.medians = []
        self.whiskers = []
        self.caps = []
        self.fliers = []

    def __repr__(self):
        return f"<BoxPlotContainer object with {len(self.boxes)} boxes>"

    def orientation(self):
        return self._orientation

    def set_orientation(self, orientation: str):
        self._orientation = orientation

    def add_artists(self, artist: dict):
        for box in artist["boxes"]:
            self.boxes.append(box)
        for median in artist["medians"]:
            self.medians.append(median)
        for whisker in artist["whiskers"]:
            self.whiskers.append(whisker)
        for cap in artist["caps"]:
            self.caps.append(cap)
        for flier in artist["fliers"]:
            self.fliers.append(flier)

    def bxp_stats(self) -> dict:
        return {
            "boxes": self.boxes,
            "medians": self.medians,
            "whiskers": self.whiskers,
            "caps": self.caps,
            "fliers": self.fliers,
        }


class BoxPlotExtractor:
    def __init__(self, orientation: str = "vert"):
        self.orientation = orientation

    def extract_whiskers(self, whiskers: list) -> list[dict]:
        return self._extract_extremes(whiskers, MaidrKey.Q1, MaidrKey.Q3)

    def extract_caps(self, caps: list) -> list[dict]:
        return self._extract_extremes(caps, MaidrKey.MIN, MaidrKey.MAX)

    def _extract_extremes(
        self, extremes: list, start_key: MaidrKey, end_key: MaidrKey
    ) -> list[dict]:
        data = []

        for start, end in zip(extremes[::2], extremes[1::2]):
            start_data_fn = (
                start.get_ydata if self.orientation == "vert" else start.get_xdata
            )
            end_data_fn = end.get_ydata if self.orientation == "vert" else end.get_xdata

            start_data = float(start_data_fn()[0])
            end_data = float(end_data_fn()[0])

            data.append(
                {
                    start_key.value: start_data,
                    end_key.value: end_data,
                }
            )

        return data

    def extract_medians(self, medians: list) -> list:
        return [
            float(
                (
                    median.get_ydata if self.orientation == "vert" else median.get_xdata
                )()[0]
            )
            for median in medians
        ]

    def extract_outliers(self, fliers: list, caps: list) -> list[dict]:
        data = []

        for outlier, cap in zip(fliers, caps):
            outlier_fn = (
                outlier.get_ydata if self.orientation == "vert" else outlier.get_xdata
            )
            outliers = [float(value) for value in outlier_fn()]
            _min, _max = cap.values()

            data.append(
                {
                    MaidrKey.LOWER_OUTLIER.value: sorted(
                        [out for out in outliers if out < _min]
                    ),
                    MaidrKey.UPPER_OUTLIER.value: sorted(
                        [out for out in outliers if out > _max]
                    ),
                }
            )

        return data


class BoxPlotElementsExtractor:
    def __init__(self, orientation: str = "vert"):
        self.orientation = orientation

    def extract_whiskers(self, whiskers: list) -> list[dict]:
        return self._extract_extremes(whiskers, MaidrKey.Q1, MaidrKey.Q3)

    def extract_caps(self, caps: list) -> list[dict]:
        return self._extract_extremes(caps, MaidrKey.MIN, MaidrKey.MAX)

    def _extract_extremes(
        self, extremes: list, start_key: MaidrKey, end_key: MaidrKey
    ) -> list[dict]:
        elements = []

        for start, end in zip(extremes[::2], extremes[1::2]):
            elements.append(
                {
                    start_key.value: start,
                    end_key.value: end,
                }
            )

        return elements

    def extract_outliers(self, fliers: list, caps: list):
        elements = []

        for outlier, _ in zip(fliers, caps):
            elements.append(outlier)

        return elements


class BoxPlot(
    MaidrPlot,
    ContainerExtractorMixin,
    LevelExtractorMixin,
    DictMergerMixin,
):
    def __init__(self, ax: Axes, **kwargs) -> None:
        super().__init__(ax, PlotType.BOX)

        self._bxp_stats = kwargs.pop("bxp_stats", None)
        self._orientation = kwargs.pop("orientation", "vert")
        self._bxp_extractor = BoxPlotExtractor(orientation=self._orientation)
        self._bxp_elements_extractor = BoxPlotElementsExtractor(
            orientation=self._orientation
        )
        self._support_highlighting = True
        self.elements_map = {
            "min": [],
            "max": [],
            "median": [],
            "boxes": [],
            "outliers": [],
        }
        self.lower_outliers_count = []

    def _extract_axes_data(self) -> dict:
        """
        Extend the base per-axis ``AxisConfig`` mapping with a ``z`` axis whose
        label is sourced from the legend title when a hue dimension is
        present. Omitted otherwise (per-box ``z`` values remain in data).
        """
        axes_data = super()._extract_axes_data()

        legend = self.ax.get_legend()
        if legend is not None:
            title = legend.get_title()
            if title is not None:
                z_label = title.get_text().strip()
                if z_label:
                    axes_data[MaidrKey.Z] = self._axis_config(label=z_label)

        return axes_data

    def _get_selector(self) -> list[dict]:
        mins, maxs, medians, boxes, outliers = self.elements_map.values()
        selector = []

        for (
            min,
            max,
            median,
            box,
            outlier,
            lower_outliers_count,
        ) in zip(
            mins,
            maxs,
            medians,
            boxes,
            outliers,
            self.lower_outliers_count,
        ):
            selector.append(
                {
                    MaidrKey.LOWER_OUTLIER.value: [
                        f"g[id='{outlier}'] > g > :nth-child(-n+{lower_outliers_count} of use:not([visibility='hidden']))"
                    ],
                    MaidrKey.MIN.value: f"g[id='{min}'] > path",
                    MaidrKey.MAX.value: f"g[id='{max}'] > path",
                    MaidrKey.Q2.value: f"g[id='{median}'] > path",
                    MaidrKey.IQ.value: f"g[id='{box}'] > path",
                    MaidrKey.UPPER_OUTLIER.value: [
                        f"g[id='{outlier}'] > g > :nth-child(n+{lower_outliers_count + 1} of use:not([visibility='hidden']))"
                    ],
                }
            )
        return selector if self._orientation == "vert" else list(reversed(selector))

    def render(self) -> dict:
        base_schema = super().render()
        box_orientation = {MaidrKey.ORIENTATION: self._orientation}
        return DictMergerMixin.merge_dict(base_schema, box_orientation)

    def _named_boxes(self, boxes: list, labels: list[str], key: MaidrKey) -> list[str]:
        """
        One name per box, for a chart that drew more than one per category.

        Two questions per box, each answered by the drawing:

        - **Which category.** The tick its slot belongs to, by position. Safe
          by construction rather than by luck: seaborn dodges a category's
          levels inside a slot narrower than the unit its ticks are spaced by,
          so a box never lands nearer another category's tick. Measured on
          three categories and two levels, against a half-spacing of 0.5, the
          outermost box sits 0.267 from its own tick.
        - **Which level.** The colour it was drawn in, matched against the
          legend swatch that names it -- the same match the histogram and the
          strip plot make, and the reason it is not the dodge lattice
          :meth:`BoxenPlot._category_of` reads: a box carries its level on its
          face, and a ladder of boxen boxes does not.

        Answering only the first is still an improvement on answering neither:
        a chart drawn ``legend=False``, or one whose hue repeats the category
        variable, gets its boxes back with the category alone rather than
        losing half of them.

        Parameters
        ----------
        boxes : list
            The box artists, in drawing order.
        labels : list of str
            The category tick labels.
        key : MaidrKey
            Which axis the categories run along.

        Returns
        -------
        list of str
            Exactly ``len(boxes)`` names, so the caller's ``zip`` cannot
            truncate. ``"category, level"`` where both are known, the category
            alone where the level is not, and ``""`` for a box that has
            neither.
        """
        positions = self.extract_level_positions(self.ax, key) or []
        ticks = list(zip(positions, labels)) if len(positions) == len(labels) else []
        levels = names_for(self.ax, [_box_colour(box) for box in boxes])
        horizontal = self._orientation != "vert"

        named = []
        for box, level in zip(boxes, levels):
            centre = _box_centre(box, horizontal)
            label = ""
            if ticks and centre is not None:
                label = min(ticks, key=lambda tick: abs(tick[0] - centre))[1]
            if label and level:
                named.append(f"{label}, {level}")
            else:
                named.append(label or level or "")
        return named

    def _extract_plot_data(self) -> list:
        data = self._extract_bxp_maidr(self._bxp_stats)

        if data is None:
            raise ExtractionError(self.type, self.ax)

        return data

    def _extract_bxp_maidr(self, bxp_stats: dict) -> list[dict] | None:
        if bxp_stats is None:
            return None

        # Three lists beside `_elements` are filled here and read by
        # `_get_selector()`, and they carried the same defect: appended to on
        # every render, so a second one produced twice as many selectors as
        # there are boxes. Worse than the extra entries, this loop stamps a
        # fresh gid on each artist every time, so after a second render the
        # *first* half of the map names gids no artist carries any more and
        # those selectors resolve to nothing (#354).
        for gids in self.elements_map.values():
            gids.clear()
        self.lower_outliers_count.clear()

        whiskers = self._bxp_extractor.extract_whiskers(bxp_stats["whiskers"])
        caps = self._bxp_extractor.extract_caps(bxp_stats["caps"])
        medians = self._bxp_extractor.extract_medians(bxp_stats["medians"])
        outliers = self._bxp_extractor.extract_outliers(bxp_stats["fliers"], caps)

        for outlier in outliers:
            self.lower_outliers_count.append(len(outlier[MaidrKey.LOWER_OUTLIER.value]))

        caps_elements = self._bxp_elements_extractor.extract_caps(bxp_stats["caps"])
        bxp_maidr = []

        key = MaidrKey.X if self._orientation == "vert" else MaidrKey.Y
        levels = self.extract_level(self.ax, key) or []

        # A `hue` draws one box per category *per level*, and the axis still
        # carries one tick per category -- so the `zip` below, which ends at
        # the shortest of what it is given, stopped at the ticks and dropped
        # every box past them. Measured on three categories and two levels:
        # six boxes drawn, three announced, and the three that survived were
        # the first level's paired with the tick labels in order (#593). The
        # selector list is built from the artists rather than from this, so
        # the same chart also emitted six selectors against three rows.
        if len(medians) > len(levels):
            levels = self._named_boxes(bxp_stats["boxes"], levels, key)

        _pairs = [(e["min"], e["max"]) for e in caps_elements if e]

        if _pairs:
            mins, maxs = map(list, zip(*_pairs))
        else:
            mins, maxs = [], []

        elements = []

        for element in mins:
            gid = "maidr-" + str(uuid.uuid4())
            element.set_gid(gid)
            self.elements_map["min"].append(gid)
            elements.append(element)

        for element in maxs:
            gid = "maidr-" + str(uuid.uuid4())
            element.set_gid(gid)
            self.elements_map["max"].append(gid)
            elements.append(element)

        for element in bxp_stats["medians"]:
            gid = "maidr-" + str(uuid.uuid4())
            element.set_gid(gid)
            self.elements_map["median"].append(gid)
            elements.append(element)

        for element in bxp_stats["boxes"]:
            gid = "maidr-" + str(uuid.uuid4())
            element.set_gid(gid)
            self.elements_map["boxes"].append(gid)
            elements.append(element)

        for element in bxp_stats["fliers"]:
            gid = "maidr-" + str(uuid.uuid4())
            element.set_gid(gid)
            self.elements_map["outliers"].append(gid)
            elements.append(element)

        self._elements.extend(elements)

        for whisker, cap, median, outlier, level in zip(
            whiskers, caps, medians, outliers, levels
        ):
            bxp_maidr.append(
                {
                    MaidrKey.LOWER_OUTLIER.value: outlier[MaidrKey.LOWER_OUTLIER.value],
                    MaidrKey.MIN.value: cap["min"],
                    MaidrKey.Q1.value: whisker["q1"],
                    MaidrKey.Q2.value: median,
                    MaidrKey.Q3.value: whisker["q3"],
                    MaidrKey.MAX.value: cap["max"],
                    MaidrKey.UPPER_OUTLIER.value: outlier[MaidrKey.UPPER_OUTLIER.value],
                    MaidrKey.Z.value: level,
                }
            )

        return bxp_maidr if self._orientation == "vert" else list(reversed(bxp_maidr))
