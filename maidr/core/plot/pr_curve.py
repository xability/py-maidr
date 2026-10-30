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
        #: How the curves' lines run against the order their points are read
        #: in -- ``"data"`` or ``"reverse"``, maidr.js's
        #: ``domMapping.pointOrder`` -- or None when no one order fits them
        #: all, or a point was left out; set as the points are read.
        self._drawn_order: str | None = "data"
        super().__init__(ax, PlotType.PR_CURVE)

    def render(self) -> dict:
        """
        The layer schema, saying how the curves are drawn against their reading.

        maidr.js outlines a curve's i-th point at the i-th vertex of its path,
        a staircase's corners skipped, in the order the points are listed. A
        curve drawn from high recall down is read from low recall up, so the
        layer says its points are drawn the other way round
        (``domMapping.pointOrder``). Curves drawn in no one order, or with a
        point left out for a missing rate, are read without an outline, since
        no vertex order pairs with their reading.

        Returns
        -------
        dict
            The layer schema.
        """
        # `super().render()` reads the points, which sets `_drawn_order`.
        schema = super().render()
        if self._drawn_order is None:
            schema.pop(MaidrKey.SELECTOR, None)
        elif self._drawn_order == "reverse" and MaidrKey.SELECTOR in schema:
            schema[MaidrKey.DOM_MAPPING] = {"pointOrder": "reverse"}
        return schema

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
        Read each curve as its points, from low recall up, along its line.

        scikit-learn's ``precision_recall_curve`` answers its points from high
        recall down, and the display draws them in that order. Which way the
        lines run is read off the signs of each one's recall steps, in the
        order it is drawn: lines whose recall never falls are read as drawn,
        and lines whose recall never rises are read back to front, so either
        way the points come in the order a reader moving right along the axis
        meets them. A recall that repeats is read in the order the line
        passes through it -- the higher precision first, the order the
        TensorBoard reader gives the same trace -- and each point keeps the
        vertex that drew it, which is where maidr.js outlines it. A line
        whose recall is the same throughout passes as drawn. When the lines'
        recall both rises and falls, or the lines run both ways, each curve is
        sorted instead and the layer is read without an outline
        (:meth:`render`). The line is drawn with every vertex it was given
        (:func:`~maidr.survival.keep_every_vertex`): matplotlib merges the
        vertices of a path of 128 or more as it draws it, which wrote the
        gallery's 151-point staircase with 62.

        A point whose recall or precision is missing is left out. matplotlib
        breaks the line there, so its vertices no longer stand one for each
        point read, and the layer is read without an outline (:meth:`render`).

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
        # Imported here: maidr.survival imports the figure manager, which
        # loads this module.
        from maidr.survival import keep_every_vertex

        curves = self._drawn()
        if not curves:
            raise ExtractionError(self.type, self.ax)

        data: list[list[dict]] = []
        every_point_read = True
        for curve in curves:
            self._elements.append(curve.line)
            if curve.line.get_gid() is None:
                curve.line.set_gid(f"maidr-{uuid.uuid4()}")
            keep_every_vertex(curve.line)

            finite = np.isfinite(curve.recall) & np.isfinite(curve.precision)
            every_point_read = every_point_read and bool(finite.all())
            points: list[dict] = []
            for x, y in zip(
                curve.recall[finite].tolist(), curve.precision[finite].tolist()
            ):
                point = {MaidrKey.X: x, MaidrKey.Y: y}
                if curve.name is not None:
                    point[MaidrKey.Z] = curve.name
                points.append(point)
            data.append(points)

        data, self._drawn_order = _from_low_recall_up(data)
        if not every_point_read:
            self._drawn_order = None
        for curve, points in zip(curves, data):
            if curve.prevalence is not None:
                points[0][PREVALENCE] = curve.prevalence
            if curve.average_precision is not None:
                points[0][AVERAGE_PRECISION] = curve.average_precision
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


def _from_low_recall_up(
    curves: list[list[dict]],
) -> tuple[list[list[dict]], str | None]:
    """
    Each curve read from low recall up, along its line.

    The plotnine reader walks a ``geom_path`` the same way
    (``maidr/plotnine/layers.py``).

    Parameters
    ----------
    curves : list of list of dict
        Each curve's points, in the order its line is drawn through them.

    Returns
    -------
    tuple
        The curves, and how their lines run against that reading: ``"data"``
        when every one is drawn from low recall up, ``"reverse"`` when every
        one is drawn from high recall down, or None when no one order fits
        them all -- a line whose recall turns back, or lines drawn both ways.
        Each curve is then sorted, the higher precision first where a recall
        repeats, since its vertices are in no order its points can be paired
        with.
    """
    steps = [np.diff([point[MaidrKey.X] for point in points]) for points in curves]
    if all((step >= 0).all() for step in steps):
        return curves, "data"
    if all((step <= 0).all() for step in steps):
        return [points[::-1] for points in curves], "reverse"
    return [
        sorted(points, key=lambda p: (p[MaidrKey.X], -p[MaidrKey.Y]))
        for points in curves
    ], None
