from __future__ import annotations

import uuid
import warnings

from matplotlib.axes import Axes

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError
from maidr.util.mixin import (
    ContainerExtractorMixin,
    DictMergerMixin,
    LevelExtractorMixin,
)


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
        """
        Extract Q1 and Q3 from whiskers.
        
        Both matplotlib and synthetic box plots structure whiskers as:
        - Lower whisker: [MIN, Q1] (from minimum to first quartile)
        - Upper whisker: [Q3, MAX] (from third quartile to maximum)
        
        Therefore, we extract Q1 from the END point of the lower whisker
        and Q3 from the START point of the upper whisker.
        """
        data = []

        for wmin, wmax in zip(whiskers[::2], whiskers[1::2]):
            # Lower whisker: wmin goes from MIN to Q1
            # Upper whisker: wmax goes from Q3 to MAX
            wmin_fn = wmin.get_ydata if self.orientation == "vert" else wmin.get_xdata
            wmax_fn = wmax.get_ydata if self.orientation == "vert" else wmax.get_xdata

            # Get the END point of lower whisker (Q1) - last point
            wmin_data = wmin_fn()
            q1_value = float(wmin_data[-1])  # Last point is Q1

            # Get the START point of upper whisker (Q3) - first point
            wmax_data = wmax_fn()
            q3_value = float(wmax_data[0])  # First point is Q3

            data.append(
                {
                    MaidrKey.Q1.value: q1_value,
                    MaidrKey.Q3.value: q3_value,
                }
            )

        return data

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

        # Handle empty fliers - return empty outlier dicts for each cap
        if not fliers:
            # Return one empty outlier dict per cap (one per box)
            for _ in caps:
                data.append(
                    {
                        MaidrKey.LOWER_OUTLIER.value: [],
                        MaidrKey.UPPER_OUTLIER.value: [],
                    }
                )
            return data

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
        self._violin_layer = kwargs.pop("violin_layer", None)
        super().__init__(ax, PlotType.BOX, **kwargs)

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
            "mean": [],
            "boxes": [],
            "outliers": [],
        }
        self.lower_outliers_count = []

    def _get_selector(self) -> list[dict]:
        mins = self.elements_map["min"]
        maxs = self.elements_map["max"]
        medians = self.elements_map["median"]
        means = self.elements_map.get("mean", [])
        boxes = self.elements_map["boxes"]
        outliers = self.elements_map["outliers"]
        selector = []

        # zip stops at shortest list - ensure all lists have matching length
        num_boxes = len(boxes)
        
        # Safety check: if critical elements are missing, can't create selectors
        # This is primarily for synthetic box plots (like violin plots) where caps might not be extracted
        if num_boxes == 0:
            return []
        
        # Ensure outliers list matches (should have one entry per box, even if empty dict)
        if len(outliers) != num_boxes:
            # Pad outliers if needed
            while len(outliers) < num_boxes:
                outliers.append(None)
        
        # Ensure lower_outliers_count matches
        while len(self.lower_outliers_count) < num_boxes:
            self.lower_outliers_count.append(0)
        
        # Check if min/max caps were extracted - if not, we can't create selectors
        # Regular box plots should always have these, but synthetic ones might not
        if len(mins) != num_boxes or len(maxs) != num_boxes:
            # If min/max caps weren't extracted, can't create selectors
            warnings.warn(
                f"Unable to extract min/max caps for box plot selectors. "
                f"Expected {num_boxes} caps but found {len(mins)} min caps and {len(maxs)} max caps. "
                f"This may occur with synthetic box plots (e.g., violin plots). "
                f"Returning empty selectors.",
                UserWarning,
                stacklevel=2
            )
            return []

        # Ensure means list matches (optional – pad with None)
        if len(means) != num_boxes:
            while len(means) < num_boxes:
                means.append(None)

        for (
            min_gid,
            max_gid,
            median_gid,
            mean_gid,
            box_gid,
            outlier_gid,
            lower_outliers_count,
        ) in zip(
            mins,
            maxs,
            medians,
            means,
            boxes,
            outliers,
            self.lower_outliers_count,
        ):
            selector_entry: dict[str, object] = {
                MaidrKey.LOWER_OUTLIER.value: [
                    f"g[id='{outlier_gid}'] > g > :nth-child(-n+{lower_outliers_count} of use:not([visibility='hidden']))"
                ],
                MaidrKey.MIN.value: f"g[id='{min_gid}'] > path",
                MaidrKey.MAX.value: f"g[id='{max_gid}'] > path",
                MaidrKey.Q2.value: f"g[id='{median_gid}'] > path",
                MaidrKey.IQ.value: f"g[id='{box_gid}'] > path",
                MaidrKey.UPPER_OUTLIER.value: [
                    f"g[id='{outlier_gid}'] > g > :nth-child(n+{lower_outliers_count + 1} of use:not([visibility='hidden']))"
                ],
            }
            # Mean selector is optional; only present when a mean line was created
            if mean_gid is not None:
                selector_entry[MaidrKey.MEAN.value] = f"g[id='{mean_gid}'] > path"

            selector.append(selector_entry)
        return selector if self._orientation == "vert" else list(reversed(selector))

    def render(self) -> dict:
        base_schema = super().render()
        box_orientation = {MaidrKey.ORIENTATION: self._orientation}
        schema = DictMergerMixin.merge_dict(base_schema, box_orientation)
        # Include violinLayer metadata if present (for violin plots)
        if self._violin_layer is not None:
            schema["violinLayer"] = self._violin_layer
        return schema

    def _extract_plot_data(self) -> list:
        data = self._extract_bxp_maidr(self._bxp_stats)

        if data is None:
            raise ExtractionError(self.type, self.ax)

        return data

    def _extract_bxp_maidr(self, bxp_stats: dict) -> list[dict] | None:
        if bxp_stats is None:
            return None

        whiskers = self._bxp_extractor.extract_whiskers(bxp_stats["whiskers"])
        caps = self._bxp_extractor.extract_caps(bxp_stats["caps"])
        medians = self._bxp_extractor.extract_medians(bxp_stats["medians"])
        outliers = self._bxp_extractor.extract_outliers(bxp_stats["fliers"], caps)
        stats_list = bxp_stats.get("stats_list")

        for outlier in outliers:
            self.lower_outliers_count.append(len(outlier[MaidrKey.LOWER_OUTLIER.value]))

        # Extract cap elements (Line2D objects) for GID assignment
        # caps_elements should be a list of dicts: [{"min": Line2D, "max": Line2D}, ...]
        # Each dict contains the actual matplotlib Line2D objects (not values)
        caps_elements = self._bxp_elements_extractor.extract_caps(bxp_stats["caps"])
        bxp_maidr = []

        levels = (
            self.extract_level(self.ax, MaidrKey.X)
            if self._orientation == "vert"
            else self.extract_level(self.ax, MaidrKey.Y)
        )
        if levels is None:
            levels = []
        else:
            # Filter out empty/whitespace tick labels to keep levels aligned with boxes.
            # This helps when Matplotlib leaves an unlabeled tick (e.g., at 0) in addition
            # to the category ticks at 1..N.
            levels = [lvl for lvl in levels if str(lvl).strip() != ""]

        # Ensure levels has enough elements for all boxes (pad with fallback if needed)
        num_boxes = len(bxp_stats["boxes"])
        if len(levels) < num_boxes:
            # Pad with fallback labels
            levels = list(levels) + [f"Group {i+1}" for i in range(len(levels), num_boxes)]

        # Extract min and max cap Line2D objects from caps_elements
        # caps_elements format: [{"min": Line2D_obj, "max": Line2D_obj}, ...]
        _pairs = [(e["min"], e["max"]) for e in caps_elements if e and "min" in e and "max" in e]

        if _pairs and len(_pairs) == num_boxes:
            mins, maxs = map(list, zip(*_pairs))
        else:
            # If caps weren't extracted correctly, we can't create selectors
            # This should not happen if caps were created properly
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

        # Optional mean elements
        for element in bxp_stats.get("means", []):
            gid = "maidr-" + str(uuid.uuid4())
            element.set_gid(gid)
            self.elements_map["mean"].append(gid)
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

        for i, (whisker, cap, median, outlier) in enumerate(
            zip(whiskers, caps, medians, outliers)
        ):
            # Get level for this box (already padded to match num_boxes, but safe fallback)
            level = levels[i] if i < len(levels) else f"Group {i+1}"
            fill_value = str(level) if level else f"Group {i+1}"
            
            # Optional mean value – only present for plots that provide it (e.g., Matplotlib violins)
            mean_value = None
            if stats_list and i < len(stats_list):
                mean_value = stats_list[i].get(MaidrKey.MEAN.value)

            record = {
                MaidrKey.LOWER_OUTLIER.value: outlier[MaidrKey.LOWER_OUTLIER.value],
                MaidrKey.MIN.value: cap["min"],
                MaidrKey.Q1.value: whisker["q1"],
                MaidrKey.Q2.value: median,
                MaidrKey.Q3.value: whisker["q3"],
                MaidrKey.MAX.value: cap["max"],
                MaidrKey.UPPER_OUTLIER.value: outlier[MaidrKey.UPPER_OUTLIER.value],
                MaidrKey.FILL.value: fill_value,
            }
            if mean_value is not None:
                record[MaidrKey.MEAN.value] = mean_value

            bxp_maidr.append(record)

        return bxp_maidr if self._orientation == "vert" else list(reversed(bxp_maidr))
