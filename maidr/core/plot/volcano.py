"""A scatter declared a volcano or a Manhattan plot.

Both are scatters read almost entirely through a threshold: a volcano puts
effect size against significance, a Manhattan puts genomic position against
it. maidr.js gives them a trace of their own (``volcano.ts``) that opens with
how many points clear the threshold, offers a rotor over just those points,
and announces each point's name and region.

Nothing in a drawing says a scatter is one of these, and nothing in it says
where the threshold is: a dashed line at 1.3 and one at 7.3 are both just
lines. So the layer is never inferred. :func:`maidr.volcano` and
:func:`maidr.manhattan` declare it, and this class is what they register in
place of the plain scatter layer the patched ``Axes.scatter`` registered.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from numbers import Real
from typing import Any, Literal

import numpy as np
import numpy.ma as ma
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot.scatterplot import DRAWN_POINTS, ScatterPlot

#: The two layer types this class emits.
THRESHOLD_TYPES = frozenset({PlotType.VOLCANO, PlotType.MANHATTAN})

#: The sides of the cutoff ``ThresholdOptions.significanceDirection`` names.
DIRECTIONS = ("above", "below")


def threshold_options(
    significance: float,
    *,
    direction: Literal["above", "below"] = "above",
    effect: float | None = None,
) -> dict[str, Any]:
    """
    The layer's ``thresholdOptions``, checked.

    The cutoff has no default on purpose, here as in maidr.js: these charts
    sit on transformed axes whose conventions differ by field -- -log10(p) at
    1.3 for p < 0.05, at 7.3 for genome-wide significance, and a raw p axis
    whose findings sit *below* the line -- so a guessed one would put every
    point on the wrong side of it without saying so.

    Parameters
    ----------
    significance : float
        The cutoff on the y axis.
    direction : {"above", "below"}, default "above"
        Which side of ``significance`` is the significant one. ``"below"`` is
        for a raw p-value axis.
    effect : float or None, optional
        The cutoff on the magnitude of x, for a volcano. ``None`` declares
        none.

    Returns
    -------
    dict
        ``significance``, ``significanceDirection`` and, when given,
        ``effect``, as maidr.js reads them.

    Raises
    ------
    TypeError
        If a cutoff is not a real number.
    ValueError
        If a cutoff is not finite, ``effect`` is negative, or ``direction``
        is neither ``"above"`` nor ``"below"``.
    """
    options: dict[str, Any] = {
        MaidrKey.SIGNIFICANCE.value: _finite("significance", significance)
    }
    if direction not in DIRECTIONS:
        raise ValueError(
            f"significance_direction must be 'above' or 'below', not {direction!r}"
        )
    options[MaidrKey.SIGNIFICANCE_DIRECTION.value] = direction
    if effect is not None:
        cutoff = _finite("effect", effect)
        if cutoff < 0:
            # Applied to |x|, so a negative cutoff is cleared by every point
            # and says nothing; the caller meant its magnitude or a mistake.
            raise ValueError(f"effect is applied to the magnitude of x: {effect!r}")
        options[MaidrKey.EFFECT.value] = cutoff
    return options


def _finite(name: str, value: Any) -> float:
    """
    A cutoff as a finite float.

    Parameters
    ----------
    name : str
        The argument's name, for the message.
    value : Any
        What the caller passed.

    Returns
    -------
    float
        The value.

    Raises
    ------
    TypeError
        If it is not a real number (a ``bool`` is not one here).
    ValueError
        If it is not finite.
    """
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a number, not {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite, not {value!r}")
    return number


def _names(values: Sequence[Any] | None, count: int, what: str) -> list[str | None]:
    """
    One name per point, or none at all.

    Parameters
    ----------
    values : sequence or None
        What the caller passed: a list, an array, a pandas ``Series``.
    count : int
        How many points the collections hold, drawn or not.
    what : str
        The argument's name, for the message.

    Returns
    -------
    list of str or None
        A name per point; ``None`` where the caller gave none, an empty
        string, ``None`` or NaN. Empty when ``values`` is ``None``.

    Raises
    ------
    ValueError
        If there is not exactly one per point.
    """
    if values is None:
        return []
    given = list(values)
    if len(given) != count:
        raise ValueError(
            f"{what} needs one entry per point the scatter was given: "
            f"got {len(given)} for {count} points"
        )
    names: list[str | None] = []
    for value in given:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            names.append(None)
            continue
        text = str(value)
        names.append(text or None)
    return names


class VolcanoPlot(ScatterPlot):
    """
    A volcano or Manhattan layer over the points of one or more scatters.

    Read exactly as :class:`ScatterPlot` reads an ungrouped scatter -- the
    same points, the same order, the same selector, which the volcano trace
    resolves as the point trace does -- with each point's name and region
    added and the threshold carried on the layer.

    Parameters
    ----------
    ax : Axes
        The axes the points are drawn on.
    plot_type : PlotType
        :attr:`PlotType.VOLCANO` or :attr:`PlotType.MANHATTAN`.
    points : list of PathCollection
        The collections holding the points, in the order ``labels`` and
        ``groups`` follow.
    thresholds : dict
        The layer's ``thresholdOptions``, from :func:`threshold_options`.
    labels : sequence or None, optional
        A name per point -- a gene, a SNP -- announced as the point's name.
    groups : sequence or None, optional
        A region per point -- a chromosome -- announced alongside it.

    Raises
    ------
    ValueError
        If ``plot_type`` is neither type, or ``labels`` or ``groups`` does not
        hold one entry per point.
    """

    def __init__(
        self,
        ax: Axes,
        plot_type: PlotType,
        *,
        points: list[PathCollection],
        thresholds: dict[str, Any],
        labels: Sequence[Any] | None = None,
        groups: Sequence[Any] | None = None,
    ) -> None:
        if plot_type not in THRESHOLD_TYPES:
            raise ValueError(f"not a threshold layer type: {plot_type!r}")
        super().__init__(ax, **{DRAWN_POINTS: list(points)})
        self.type = plot_type
        self._thresholds = dict(thresholds)

        # One entry per offset, drawn or not: the caller counts the rows they
        # handed `scatter`, and matplotlib keeps a row it could not draw as a
        # masked offset rather than dropping it. Checked here, at the call
        # that declared the layer, rather than when the page is built.
        count = sum(len(collection.get_offsets()) for collection in self._own_points)
        self._labels = _names(labels, count, "labels")
        self._groups = _names(groups, count, "groups")

    def render(self) -> dict:
        """
        The scatter's schema, carrying the threshold.

        ``thresholdOptions`` sits on the layer, beside ``data``, which is
        where ``MaidrLayer`` declares it.

        Returns
        -------
        dict
            The layer's schema.
        """
        schema = super().render()
        schema[MaidrKey.THRESHOLD_OPTIONS] = dict(self._thresholds)
        return schema

    def _extract_plot_data(self) -> list[dict]:
        """
        The scatter's points, each with its name and region.

        :class:`ScatterPlot` emits the points it can draw, in offset order,
        collection after collection. The same walk here finds which offset
        each emitted point came from, so a name lands on the point it was
        given for even when an undrawn row before it was skipped.

        Returns
        -------
        list of dict
            ``VolcanoPoint`` entries: ``x``, ``y`` and, where given,
            ``label`` and ``group``.
        """
        samples = super()._extract_plot_data()
        if not self._labels and not self._groups:
            return samples

        parts = self._own_points or self._swept()
        drawn: list[int] = []
        base = 0
        for collection in parts:
            offsets = np.asarray(
                ma.getdata(collection.get_offsets()), dtype=float
            ).reshape(-1, 2)
            finite = np.isfinite(offsets).all(axis=1)
            drawn.extend((np.flatnonzero(finite) + base).tolist())
            base += len(offsets)

        for sample, index in zip(samples, drawn):
            if self._labels and self._labels[index] is not None:
                sample[MaidrKey.LABEL.value] = self._labels[index]
            if self._groups and self._groups[index] is not None:
                sample[MaidrKey.GROUP.value] = self._groups[index]
        return samples
