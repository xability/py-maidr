from __future__ import annotations

import uuid
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.core.plot.roc import _is_number
from maidr.exception import ExtractionError

#: The kwarg the patch hands the factory: the curves one ``plot()`` call drew.
DRAWN_CURVES = "curves"

#: Where maidr.js's ``pr_curve`` trace reads a curve's share of positives and
#: its average precision: on the curve's first point, the way ``auc`` rides a
#: ROC curve's.
PREVALENCE = "prevalence"
AVERAGE_PRECISION = "ap"


class PrCurve:
    """
    One curve of a precision-recall chart: its line and the numbers behind it.

    Held as the numbers ``PrecisionRecallDisplay`` was given rather than read
    back off the line, because the display carries three things the line
    does not: the average precision it computed, the share of positives it
    was scored on (the precision a classifier guessing at random keeps, which
    every point is read against), and the name it was given before the legend
    wrapped ``(AP = 0.83)`` around it.

    Parameters
    ----------
    line : Line2D
        The artist ``ax.plot`` returned for this curve.
    precision, recall : array-like
        The precision and recall at each threshold.
    average_precision : float or None
        The average precision as the display computed it, if it did.
    prevalence : float or None
        The share of positives in the scored sample, if the display knows it.
    name : str or None
        What the curve is called, if the caller named it.
    """

    def __init__(
        self,
        line: Line2D,
        precision: Any,
        recall: Any,
        average_precision: float | None,
        prevalence: float | None,
        name: str | None,
    ) -> None:
        self.line = line
        self.precision = np.asarray(precision, dtype=float).ravel()
        self.recall = np.asarray(recall, dtype=float).ravel()
        self.average_precision = (
            float(average_precision) if _is_number(average_precision) else None
        )
        self.prevalence = (
            float(prevalence)
            if _is_number(prevalence) and 0 <= float(prevalence) <= 1
            else None
        )
        self.name = name if isinstance(name, str) and name else None


class PrCurvePlot(MaidrPlot):
    """
    A precision-recall chart, as ``PrecisionRecallDisplay`` draws it.

    ``PrecisionRecallDisplay.plot`` draws each curve with ``ax.plot(recall,
    precision, drawstyle="steps-post")``, which the line patch would register
    as a *step* layer, with the dashed chance level ``plot_chance_level=True``
    adds announced as a second series. A step reads the precision correctly
    and answers the wrong questions about it: whether the classifier beats
    guessing is the gap between each point and the share of positives, and
    the number the chart is quoted by -- the average precision -- sits in the
    legend text and reaches no reader.

    So the display is read instead, as ``RocPlot`` reads ``RocCurveDisplay``,
    and the layer is maidr.js's ``pr_curve``: each point its recall and
    precision, each curve its name, with the share of positives and the
    average precision on the curve's first point, from which maidr.js
    announces each point against the baseline, the average precision against
    it, and the point with the best F1. The chance level is a reference, not
    a curve, and is left out; maidr.js draws its own reading of it.

    Several ``plot(ax=ax)`` calls on one axes become further curves of one
    layer through :meth:`add_curves`, so a reader moves up and down between
    classifiers.

    Parameters
    ----------
    ax : Axes
        The axes the display drew on.
    **kwargs : dict
        ``curves``, the :class:`PrCurve` objects the patch built.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        self._curves: list[PrCurve] = list(kwargs.pop(DRAWN_CURVES, ()) or ())
        super().__init__(ax, PlotType.PR_CURVE)

    def add_curves(self, curves: list[PrCurve]) -> None:
        """
        Take another ``plot()`` call on the same axes as further curves.

        The schema is dropped rather than amended, for the reason
        ``RocPlot.add_curves`` gives: it is built lazily, and a curve arriving
        after it was built would otherwise never appear.

        Parameters
        ----------
        curves : list of PrCurve
            The curves the new call drew.
        """
        self._curves.extend(curves)
        self._schema = {}

    def _drawn(self) -> list[PrCurve]:
        """
        The curves that have at least one point to announce.

        One filter for the points and the selectors both, because the two
        lists are read index-aligned and the core drops the layer's highlight
        when their lengths disagree.
        """
        return [
            curve
            for curve in self._curves
            if curve.recall.size == curve.precision.size
            and bool((np.isfinite(curve.recall) & np.isfinite(curve.precision)).any())
        ]

    def _extract_plot_data(self) -> list[list[dict]]:
        """
        Read each curve as its points, from low recall up.

        scikit-learn's ``precision_recall_curve`` answers its points from high
        recall down; they are read from low recall up, the order a reader
        moving right along the axis meets them, with the higher precision
        first where a recall repeats -- the order the TensorBoard reader
        gives the same trace.

        Returns
        -------
        list of list of dict
            One array per curve of ``{x, y}`` points -- recall and precision
            -- with ``z`` naming the curve when it has a name, and
            ``prevalence`` and ``ap`` on the first point when the display
            knows them.

        Raises
        ------
        ExtractionError
            When no curve carries a point.
        """
        curves = self._drawn()
        if not curves:
            raise ExtractionError(self.type, self.ax)

        data: list[list[dict]] = []
        for curve in curves:
            self._elements.append(curve.line)
            if curve.line.get_gid() is None:
                curve.line.set_gid(f"maidr-{uuid.uuid4()}")

            finite = np.isfinite(curve.recall) & np.isfinite(curve.precision)
            recall, precision = curve.recall[finite], curve.precision[finite]
            order = np.lexsort((-precision, recall))
            points: list[dict] = []
            for x, y in zip(recall[order].tolist(), precision[order].tolist()):
                point = {MaidrKey.X: x, MaidrKey.Y: y}
                if curve.name is not None:
                    point[MaidrKey.Z] = curve.name
                points.append(point)

            if curve.prevalence is not None:
                points[0][PREVALENCE] = curve.prevalence
            if curve.average_precision is not None:
                points[0][AVERAGE_PRECISION] = curve.average_precision
            data.append(points)
        return data

    def _get_selector(self) -> list[str]:
        """
        One selector per curve, naming the path its line renders as.

        Sized to the curves emitted, because the core drops the whole layer's
        highlight unless the two lengths agree.
        """
        selectors = []
        for curve in self._drawn():
            if curve.line.get_gid() is None:
                curve.line.set_gid(f"maidr-{uuid.uuid4()}")
            selectors.append(f"g[id='{curve.line.get_gid()}'] path")
        return selectors
