from __future__ import annotations

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
        self._support_highlighting = False

    def render(self) -> dict:
        base_schema = super().render()
        box_orientation = {MaidrKey.ORIENTATION: self._orientation}
        return DictMergerMixin.merge_dict(base_schema, box_orientation)

    def _extract_plot_data(self) -> list:
        data = self._extract_bxp_maidr(self._bxp_stats)

        if data is None:
            raise ExtractionError(self.type, self.ax)

        return data

    def _extract_bxp_maidr(self, bxp_stats: dict) -> list[dict] | None:
        if bxp_stats is None:
            return None

        bxp_maidr = []
        whiskers = self._bxp_extractor.extract_whiskers(bxp_stats["whiskers"])
        caps = self._bxp_extractor.extract_caps(bxp_stats["caps"])
        medians = self._bxp_extractor.extract_medians(bxp_stats["medians"])
        outliers = self._bxp_extractor.extract_outliers(bxp_stats["fliers"], caps)
        levels = (
            self.extract_level(self.ax, MaidrKey.X)
            if self._orientation == "vert"
            else self.extract_level(self.ax, MaidrKey.Y)
        )
        if levels is None:
            levels = []

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
                    MaidrKey.FILL.value: level,
                }
            )

        return bxp_maidr if self._orientation == "vert" else list(reversed(bxp_maidr))
