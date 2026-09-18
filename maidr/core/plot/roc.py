from __future__ import annotations

import math
import uuid
from typing import Any

import numpy as np
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError

#: The kwarg the patch hands the factory: the curves one ``plot()`` call drew.
DRAWN_CURVES = "curves"


class RocCurve:
    """
    One curve of a ROC chart: the line that draws it and the numbers behind it.

    Held as the numbers rather than read back off the line, because the line
    is only what ``RocCurveDisplay.plot`` drew from them and the display
    carries two things the line does not: the area it computed, and the name
    it was given before the legend label wrapped the area around it.

    Parameters
    ----------
    line : Line2D
        The artist ``ax.plot`` returned for this curve.
    fpr, tpr : array-like
        The false and true positive rates, one per operating point.
    roc_auc : float or None
        The area under the curve as the display computed it, if it did.
    name : str or None
        What the curve is called, if the caller named it.
    """

    def __init__(
        self,
        line: Line2D,
        fpr: Any,
        tpr: Any,
        roc_auc: float | None,
        name: str | None,
    ) -> None:
        self.line = line
        self.fpr = np.asarray(fpr, dtype=float).ravel()
        self.tpr = np.asarray(tpr, dtype=float).ravel()
        self.roc_auc = roc_auc if _is_number(roc_auc) else None
        self.name = name if isinstance(name, str) and name else None


def _is_number(value: Any) -> bool:
    """Whether ``value`` is a finite real number and not a bool."""
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


class RocPlot(MaidrPlot):
    """
    A receiver operating characteristic chart, as ``RocCurveDisplay`` draws it.

    scikit-learn's ``RocCurveDisplay`` is the way a ROC curve is drawn in
    Python: ``from_estimator``, ``from_predictions``, ``from_cv_results`` and a
    hand-built display all end in its ``plot()``, which calls ``ax.plot(fpr,
    tpr)`` once per curve. Left alone, that ``ax.plot`` registers a *line*
    layer, and a line answers the wrong questions about a ROC curve: the
    minimum and maximum are 0 and 1 on every one, the pitch is scaled to each
    curve's own range so two classifiers sound alike, and the area -- the
    number the chart is quoted by -- is in the legend text and nowhere a
    reader is told (xability/maidr#814's pattern: the parent trace reads the
    data correctly and answers the wrong question).

    So the display is read rather than the line. Each curve is its rates as
    the display holds them, its name as the caller gave it before the legend
    wrapped ``(AUC = 0.90)`` around it, and the area the display computed,
    carried on the curve's first point the way a series name is. The chance
    diagonal ``plot_chance_level=True`` draws is a reference, not a curve, and
    is left out.

    Several ``plot(ax=ax)`` calls on one axes -- the ordinary way to compare
    classifiers -- become further curves of one layer through
    :meth:`add_curves`, so a reader moves up and down between classifiers
    rather than switching between one-curve layers.

    Parameters
    ----------
    ax : Axes
        The axes the display drew on.
    **kwargs : dict
        ``curves``, the :class:`RocCurve` objects the patch built.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        self._curves: list[RocCurve] = list(kwargs.pop(DRAWN_CURVES, ()) or ())
        super().__init__(ax, PlotType.ROC)

    def add_curves(self, curves: list[RocCurve]) -> None:
        """
        Take another ``plot()`` call on the same axes as further curves.

        The schema is dropped rather than amended, because it is built lazily
        on first access and a curve arriving after it was built would
        otherwise never appear -- the reasoning ``GanttPlot.add_lane`` gives.

        Parameters
        ----------
        curves : list of RocCurve
            The curves the new call drew.
        """
        self._curves.extend(curves)
        self._schema = {}

    def _drawn(self) -> list[RocCurve]:
        """
        The curves that have at least one operating point to announce.

        One filter for the points and the selectors both, because the two
        lists are read index-aligned and the core drops the whole layer's
        highlight when their lengths disagree. A rate that is not a number
        is not an operating point, and ``roc_curve`` returns a curve of
        nothing but ``NaN`` when the sample it scored holds one class --
        an ordinary small or imbalanced fold -- so that curve is left out
        here, before either list is built, rather than from one of them.
        """
        return [
            curve
            for curve in self._curves
            if curve.fpr.size and curve.tpr.size and bool(np.isfinite(curve.fpr).any())
        ]

    def _extract_plot_data(self) -> list[list[dict]]:
        """
        Read each curve as its operating points.

        Returns
        -------
        list of list of dict
            One array per curve of ``{x, y}`` points -- the false and true
            positive rates -- with ``z`` naming the curve when it has a name
            and ``auc`` on the first point when the display computed one.

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
            # Assigned here rather than relied upon, for the selector below:
            # a gid is otherwise only what the caller happened to set.
            if curve.line.get_gid() is None:
                curve.line.set_gid(f"maidr-{uuid.uuid4()}")

            points: list[dict] = []
            for x, y in zip(curve.fpr.tolist(), curve.tpr.tolist()):
                # A rate that is not a number is not an operating point, and
                # a bare NaN is not JSON (#427).
                if not math.isfinite(x):
                    continue
                point = {
                    MaidrKey.X: x,
                    MaidrKey.Y: y if math.isfinite(y) else None,
                }
                if curve.name is not None:
                    point[MaidrKey.Z] = curve.name
                points.append(point)

            if curve.roc_auc is not None:
                points[0][MaidrKey.AUC] = float(curve.roc_auc)
            data.append(points)

        if not data:
            raise ExtractionError(self.type, self.ax)
        return data

    def _get_selector(self) -> list[str]:
        """
        One selector per curve, naming the path its line renders as.

        Sized to the curves emitted, because the core's multi-line trace
        drops the whole layer's highlight unless the two lengths agree.
        """
        selectors = []
        for curve in self._drawn():
            if curve.line.get_gid() is None:
                curve.line.set_gid(f"maidr-{uuid.uuid4()}")
            selectors.append(f"g[id='{curve.line.get_gid()}'] path")
        return selectors
