"""SurvivalPlot -- Kaplan-Meier curves, one arm per curve, as a ``survival`` layer."""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field

from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot.maidr_plot import MaidrPlot
from maidr.exception import ExtractionError
from maidr.util.step_utils import resolve_step_direction


@dataclass(eq=False)
class SurvivalArm:
    """
    One curve of a survival chart: the line that draws it and its points.

    Attributes
    ----------
    line : Line2D
        The step line drawn for the curve, one vertex pair per point, so the
        path's vertices are the points in order.
    points : list of dict
        One ``{x, y}`` per time, with ``z`` naming the arm when it has a name,
        ``censored: True`` at a censored time, and ``yMin``/``yMax`` when the
        chart draws a confidence band.
    """

    line: Line2D
    points: list[dict] = field(default_factory=list)


class SurvivalPlot(MaidrPlot):
    """
    A Kaplan-Meier chart read as a ``survival`` layer.

    Read as a ``step`` layer, a survival curve loses the two things the figure
    is drawn for: which times are censored rather than events, and the median
    survival. The ``survival`` trace in maidr.js announces both, and offers a
    rotor over the censored times. The points are what the caller stated or
    what the fitter estimated, not what is read back off the line, because the
    line holds neither the censoring nor the band.

    Several curves on one axes -- the ordinary way to compare arms -- are
    arms of one layer through :meth:`add_arm`, so a reader moves between arms
    at the same time rather than between one-curve layers.

    Parameters
    ----------
    ax : Axes
        The axes the curves are drawn on.
    arms : list of SurvivalArm
        The curves registered so far.
    """

    def __init__(self, ax: Axes, arms: list[SurvivalArm]) -> None:
        super().__init__(ax, PlotType.SURVIVAL)
        self._arms: list[SurvivalArm] = list(arms)

    def add_arm(self, arm: SurvivalArm) -> None:
        """
        Take another curve on the same axes as a further arm.

        The cached schema is dropped, as ``RocPlot.add_curves`` drops it, so
        an arm added after the schema was first built still appears.

        Parameters
        ----------
        arm : SurvivalArm
            The new curve.
        """
        self._arms.append(arm)
        self._schema = {}

    def _drawn(self) -> list[SurvivalArm]:
        """The arms with at least one point, for the data and the selectors alike."""
        return [arm for arm in self._arms if arm.points]

    def render(self) -> dict:
        """
        Build the layer, with ``stepDirection`` when every curve states one.

        Returns
        -------
        dict
            The MAIDR layer schema.
        """
        schema = super().render()
        direction = resolve_step_direction(arm.line for arm in self._drawn())
        if direction is not None:
            schema[MaidrKey.STEP_DIRECTION] = direction
        return schema

    def _extract_axes_data(self) -> dict:
        """
        The axis labels as the chart shows them, in the canonical form.

        Returns
        -------
        dict
            ``x`` and ``y`` labelled from the axes, and ``z`` from the legend
            title when the arms are named and the legend has one.
        """
        axes = {
            MaidrKey.X: self._axis_config(label=self.ax.get_xlabel() or None),
            MaidrKey.Y: self._axis_config(label=self.ax.get_ylabel() or None),
        }
        title = self._legend_title()
        if title:
            axes[MaidrKey.Z] = self._axis_config(label=title)
        return axes

    def _extract_plot_data(self) -> list[list[dict]]:
        """
        Each arm's points, in time order.

        Returns
        -------
        list of list of dict
            One list of ``SurvivalPoint`` per arm.

        Raises
        ------
        ExtractionError
            When no arm carries a point.
        """
        arms = self._drawn()
        if not arms:
            raise ExtractionError(self.type, self.ax)
        for arm in arms:
            self._elements.append(arm.line)
        return [copy.deepcopy(arm.points) for arm in arms]

    def _get_selector(self) -> list[str]:  # type: ignore[override]
        """
        One selector per arm, naming the path its line renders as.

        Returns
        -------
        list of str
            Sized to the arms emitted, which the line family in maidr.js reads
            index-aligned with the data.
        """
        selectors = []
        for arm in self._drawn():
            if arm.line.get_gid() is None:
                arm.line.set_gid(f"maidr-{uuid.uuid4()}")
            selectors.append(f"g[id='{arm.line.get_gid()}'] > path")
        return selectors
