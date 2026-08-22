from typing import List, Optional, Union

from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.enum.maidr_key import MaidrKey
from maidr.util.artist_label import series_name
from maidr.util.confidence_band import band_edges_at
from maidr.core.enum.plot_type import PlotType
from maidr.core.plot.maidr_plot import MaidrPlot
from maidr.exception.extraction_error import ExtractionError
from maidr.util.mixin.extractor_mixin import LineExtractorMixin
import math
import uuid

import numpy as np


def _has_position(x: object) -> bool:
    """
    Whether a sample sits anywhere a reader could be sent.

    A point whose ``x`` is not finite has no position on the axis, so there is
    nothing to announce and nothing to navigate to. Two ordinary idioms
    produce them, and neither is an observation:

    * ``sns.ecdfplot`` starts its staircase at ``-inf`` so the first step has
      somewhere to come from;
    * ``NaN`` is matplotlib's own way of *breaking* a line into segments --
      it sets **both** coordinates -- and a masked array becomes one on the
      way through.

    Dropping them is also what keeps the payload loadable at all.
    ``json.dumps`` writes ``NaN``, ``Infinity`` and ``-Infinity`` as bare
    tokens, which are legal JavaScript but not JSON, and the core parses the
    SVG's ``maidr`` attribute with ``JSON.parse``. One of them does not
    degrade the chart -- ``initMaidrOnElement`` is never reached, so audio,
    text, braille and highlight are all absent and the only trace is a
    ``console.error`` a screen reader user has no reason to be watching
    (#427).

    Deliberately asked of ``x`` alone. A sample with a real x and a
    non-finite ``y`` is a different thing: it has a position and no value,
    which is how ``seaborn.pointplot`` pads a hue level missing from one
    category so its two estimate lines stay the same length. Dropping it
    would break that pairing, so it is kept and its value emitted as ``null``
    by :func:`_reading` instead.

    Parameters
    ----------
    x : object
        A sample's x coordinate as extracted, numeric or categorical.

    Returns
    -------
    bool
        False only for a number that is NaN or infinite. A categorical x
        arrives as its label, which is both positioned and never a JSON
        hazard, so anything ``math.isfinite`` cannot judge is kept.
    """
    try:
        return math.isfinite(x)  # type: ignore[arg-type]
    except TypeError:
        return True



def _reading(y: object) -> object:
    """
    A sample's value, or ``None`` where it was positioned but never measured.

    ``seaborn.pointplot`` pads a hue level missing from one category so its
    estimate lines stay the same length, which is what keeps the pairing
    working and the interval polylines out of the data. That padding has a
    real x and no y: something to navigate to, nothing to report.

    ``None`` serialises to ``null``, which the core has read as a gap since
    maidr 4.3.0 (xability/maidr#926) -- it becomes ``NaN`` inside
    ``LineTrace``, stays out of the range, sounds as the empty tone rather
    than a floor tone, and announces as "missing". Before that release there
    was no honest way to say it: the bare ``NaN`` stopped the chart
    initialising at all, and a zero would have claimed a reading of zero
    (#429).

    Distinct from {@link _has_position}, which drops a sample outright. A
    sample with no *position* is not on the chart; this one is.

    Parameters
    ----------
    y : object
        A sample's value as extracted, numeric or categorical.

    Returns
    -------
    object
        The value, or ``None`` when it is a non-finite number. A categorical
        value is returned untouched.
    """
    try:
        return y if math.isfinite(y) else None  # type: ignore[arg-type]
    except TypeError:
        return y



def _drew_something(line: Line2D) -> bool:
    """
    Whether a line has any coordinates at all.

    Parameters
    ----------
    line : Line2D
        One of the axes' lines.

    Returns
    -------
    bool
        True when the line carries at least one point.
    """
    xydata = line.get_xydata()
    return xydata is not None and bool(getattr(xydata, "size", 0))

class MultiLinePlot(MaidrPlot, LineExtractorMixin):
    """
    A class for extracting and processing data from line plots.

    This class can handle both single-line and multi-line plots, extracting
    coordinate data and line identifiers. It processes matplotlib Line2D objects
    and converts them into structured data for further processing or visualization.

    Parameters
    ----------
    ax : Axes
        The matplotlib axes object containing the line plot(s).
    plot_type : PlotType, optional
        The layer type to emit, by default ``PlotType.LINE``. Subclasses that
        share this extraction logic but describe a different chart — notably
        :class:`maidr.core.plot.stepplot.StepPlot` — override it.
    lines : list of Line2D, optional
        The lines to describe, by default every line on the axes. A patch
        passes this when some of what was drawn is not a series: seaborn's
        point plot renders each confidence interval as a line of its own, and
        describing those alongside the estimates announces cap geometry as
        data.
    **kwargs : dict
        Additional keyword arguments to pass to the parent class.

    Attributes
    ----------
    type : PlotType
        The plot type this layer identifies as, ``PlotType.LINE`` by default.

    Notes
    -----
    - When using the JavaScript engine, only single-line plots are supported.
    - For multi-line plots, use the TypeScript engine.
    - The extracted data structure includes x, y coordinates and line identifiers
      (fill values) for each point.
    """

    def __init__(
        self,
        ax: Axes,
        plot_type: PlotType = PlotType.LINE,
        lines: Optional[List[Line2D]] = None,
        **kwargs,
    ):
        super().__init__(ax, plot_type)
        self._lines = lines

    def _series(self) -> List[Line2D]:
        """
        Return the lines this layer describes.

        Returns
        -------
        list[Line2D]
            The lines a patch narrowed the layer to, or every line on the axes
            when it did not.
        """
        if self._lines is not None:
            return self._lines

        return [line for line in self.ax.get_lines() if self._is_in_data_space(line)]

    def _is_in_data_space(self, line: Line2D) -> bool:
        """
        Whether a line's coordinates mean what the axes say they mean.

        ``axhline`` and ``axvline`` blend the *axes* transform on one axis with
        the data transform on the other, so their stored coordinates run 0 to 1
        and describe the extent of the axes rather than any value. Measured on
        ``ax.plot([10, 20, 30], [1, 2, 3])`` followed by ``ax.axhline(2)``::

            [{"x": 10.0, ...}, {"x": 20.0, ...}, {"x": 30.0, ...}]
            [{"x":  0.0, "y": 2.0}, {"x": 1.0, "y": 2.0}]   <- the axhline

        The chart's x runs 10 to 30, and the reference line was announced at
        0 and 1. That is not a degraded reading of a real series; it is a
        confident reading of one that is not there, and nothing in the output
        says its numbers are in a different space from every other number in
        the chart (#434).

        A reference line is decoration rather than data, and the grammar has no
        annotation to put it in, so it is left out. Describing the threshold
        somewhere is worth doing separately -- it is genuinely useful to know
        one is drawn -- but that is a grammar question and should not keep a
        wrong reading in the meantime.

        Only the transform is asked about, never the values. A genuinely flat
        data line -- ``ax.plot([1, 2], [5, 5])`` -- is drawn in data space and
        stays, which a shape test would have thrown away.

        Parameters
        ----------
        line : Line2D
            A line found on the axes.

        Returns
        -------
        bool
            True when the line is positioned by the data transform.
        """
        return line.get_transform() is self.ax.transData

    def _extract_axes_data(self) -> dict:
        """
        Extend the base per-axis ``AxisConfig`` mapping with a ``z`` axis
        whose label is sourced from the legend title (multi-series column).

        Omitted when there is no legend title.
        """
        axes_data = super()._extract_axes_data()

        z_label = self._legend_title()
        if z_label:
            axes_data[MaidrKey.Z] = self._axis_config(label=z_label)

        return axes_data

    def _get_selector(self) -> Union[str, List[str]]:
        # Return selectors for all lines that have data
        all_lines = self._series()
        if not all_lines:
            return ["g[maidr='true'] > path"]

        selectors = []
        for line in all_lines:
            # Only create selectors for lines that have data (same logic as _extract_line_data)
            xydata = line.get_xydata()
            if xydata is None or not xydata.size:  # type: ignore
                continue
            gid = line.get_gid()
            if gid:
                selectors.append(f"g[id='{gid}'] path")
            else:
                selectors.append("g[maidr='true'] > path")

        if not selectors:
            return ["g[maidr='true'] > path"]

        return selectors

    def _extract_plot_data(self) -> Union[List[List[dict]], None]:
        data = self._extract_line_data()

        if data is None:
            raise ExtractionError(self.type, None)

        return data

    def _extract_line_data(self) -> Union[List[List[dict]], None]:
        """
        Extract data from all line objects and return as separate arrays.

        Returns
        -------
        list[list[dict]] | None
            List of lists, where each inner list contains dictionaries with x,y coordinates
            and line identifiers for one line, or None if the plot data is invalid.
        """
        all_lines = self._series()

        # Only the lines that drew something take part, in both the pairing
        # below and the loop. A seaborn `hue` split leaves probe lines with
        # no data among the real ones, and counting those against the legend
        # would pair its names with series that are never announced.
        all_lines = [line for line in all_lines if _drew_something(line)]
        if not all_lines:
            return None

        # Try to get series names from legend
        legend_labels = []
        if self.ax.legend_ is not None:
            legend_labels = [text.get_text() for text in self.ax.legend_.get_texts()]

        # Which line each legend entry belongs to. A legend is not always as
        # long as the series list, and pairing the two by position when it is
        # not hands a line its neighbour's name: matplotlib's own legend
        # builder skips an artist whose label starts with an underscore, so
        #
        #     ax.plot(x, y, label="_nolegend_")
        #     ax.plot(x, z, label="revenue")
        #     ax.legend()
        #
        # leaves one entry against two lines, and both were announced
        # "revenue" -- the hidden one taking the name of the series after it.
        #
        # Equal lengths do not settle it either, because the legend may be in
        # a different order from the axes: `ax.legend(handles=[q, p])` is how
        # a caller reorders one without redrawing, and pairing by position
        # then announced each series under the other's name (#578). The
        # handles cannot be used to recover the pairing -- measured, they are
        # proxy artists and `handle is line` is False for every drawn line --
        # but the *text* still identifies the series, so a legend that is a
        # permutation of the lines' own names is matched by name.
        #
        # The test is only that the two sets agree, which is narrower than it
        # looks and was arrived at by deleting the parts that turned out not
        # to be. Requiring every line to be *named* adds nothing: an unnamed
        # line contributes "" to the set, and matplotlib renders no legend
        # entry for one, so the sets cannot agree anyway. Requiring the names
        # to be *unique* adds nothing either: two lines called the same thing
        # are announced by that name whichever of them an entry is paired
        # with. Both guards survived every mutation, so neither is here.
        #
        # Anything short of agreement falls back to position, which is what
        # the two cases that rely on it need: `ax.legend(["A", "B"])` renames
        # every series positionally and means to -- its texts are *not* the
        # lines' names, which is exactly what tells the two apart -- and a
        # seaborn `hue` split names its groups in the legend while the lines
        # themselves carry `_child` sentinels (#502).
        #
        # Only when the legend is *shorter* is it matched against the lines
        # matplotlib would have put in it.
        named = [index for index, line in enumerate(all_lines) if series_name(line)]
        own = [series_name(line) for line in all_lines]
        from_legend: dict = {}
        if len(legend_labels) == len(all_lines):
            renaming = set(legend_labels) == set(own)
            # Nothing to record when the legend only restates the names the
            # lines already carry: each line then answers for itself below,
            # in its own order, which is the whole point.
            if not renaming:
                from_legend = dict(enumerate(legend_labels))
        elif len(legend_labels) == len(named):
            from_legend = dict(zip(named, legend_labels))

        all_lines_data = []
        # Regions handed to an earlier series, so a band answers for one line.
        claimed: list = []

        for i, line in enumerate(all_lines):
            self._elements.append(line)

            # Assign unique GID to each line if not already set
            if line.get_gid() is None:
                unique_gid = f"maidr-{uuid.uuid4()}"
                line.set_gid(unique_gid)

            # Try to get the series name from legend labels
            line_type = from_legend.get(i) or series_name(line)

            # Use the new method to extract data with categorical labels
            line_coords = LineExtractorMixin.extract_line_data_with_categorical_labels(
                self.ax, line
            )
            if line_coords is None:
                continue

            line_data = [
                {
                    MaidrKey.X: x,
                    MaidrKey.Y: _reading(y),
                    **({MaidrKey.Z: line_type} if line_type else {}),
                }
                for x, y in line_coords
                if _has_position(x)
            ]

            self._attach_band(line_data, claimed)

            if line_data:
                all_lines_data.append(line_data)

        return all_lines_data if all_lines_data else None

    def _attach_band(self, line_data: list, claimed: list) -> None:
        """
        Give each point the interval the chart shades around it, if there is
        one.

        ``sns.lineplot`` aggregates repeated x values and draws a 95%%
        confidence band **by default**, and matplotlib's own documentation
        writes the same chart as ``plot`` plus ``fill_between``. Either way
        the line was announced alone, so a reader was told the trend and not
        how well determined it is -- the gap xability/r-maidr#135 closed for
        `geom_smooth(se = TRUE)` and #451 for a `regplot` (#562).

        ``SmoothPoint``'s `yMin`/`yMax` is the shape for it, and the region is
        identified by bracketing rather than by type; see
        :mod:`maidr.util.confidence_band`.

        Parameters
        ----------
        line_data : list
            One series' points, modified in place.
        claimed : list
            Regions already given to an earlier series, appended to here. A
            chart with several lines has several bands, and a wide one can
            bracket a neighbour's samples as well as its own.
        """
        positions = [point[MaidrKey.X] for point in line_data]
        values = [point[MaidrKey.Y] for point in line_data]
        if len(positions) < 2 or not all(
            isinstance(value, (int, float)) and not isinstance(value, bool)
            for value in positions + values
        ):
            return

        lower, upper, region = band_edges_at(
            self.ax, np.asarray(positions, dtype=float),
            np.asarray(values, dtype=float), tuple(claimed),
        )
        if region is None:
            return

        claimed.append(region)
        for point, low, high in zip(line_data, lower, upper):
            point[MaidrKey.Y_MIN] = float(low)
            point[MaidrKey.Y_MAX] = float(high)
