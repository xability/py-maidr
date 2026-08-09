from __future__ import annotations

from typing import Any

from matplotlib.axes import Axes
from matplotlib.patches import Wedge

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError


class PiePlot(MaidrPlot):
    """
    A MAIDR layer for a matplotlib pie chart.

    A pie is one flat row of slices: N labels paired with N magnitudes, in the
    order ``Axes.pie`` drew them. The percentage a slice covers is derived from
    those magnitudes by the renderer, so it is deliberately absent here — a
    percentage emitted alongside the values it is supposedly derived from is a
    second source of truth that can disagree with the first.

    Parameters
    ----------
    ax : Axes
        The ``matplotlib.axes.Axes`` the pie was drawn on.
    **kwargs
        ``values`` and ``labels``, as the patch on ``Axes.pie`` read them off
        the original call, and ``wedges``, the slices that call drew. All
        three are optional; see the ``_extract_*`` methods for what happens
        without them.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        self._values = kwargs.pop("values", None)
        self._labels = kwargs.pop("labels", None)
        self._wedges = kwargs.pop("wedges", None)
        super().__init__(ax, PlotType.PIE)

    def _extract_axes_data(self) -> dict:
        """
        Extract the plot's axes data as canonical per-axis ``AxisConfig``
        objects.

        A pie has no x or y scale, so the two axes name the *dimensions* of a
        slice rather than a position: ``x`` says what the slice labels mean and
        ``y`` says what the slice magnitudes measure. An author who set
        ``xlabel``/``ylabel`` on the axes has already named them; otherwise the
        generic "X"/"Y" of the base class would be read out against every slice
        ("X: Apples"), so a pie names them after what they hold instead.

        Returns
        -------
        dict
            ``{"x": {"label": ...}, "y": {"label": ...}}``.
        """
        x_label = self.ax.get_xlabel()
        if not x_label:
            x_label = self.extract_shared_xlabel(self.ax)
        if not x_label:
            x_label = "Category"

        y_label = self.ax.get_ylabel()
        if not y_label:
            y_label = self.extract_shared_ylabel(self.ax)
        if not y_label:
            y_label = "Value"

        return {
            MaidrKey.X: self._axis_config(label=x_label),
            MaidrKey.Y: self._axis_config(label=y_label),
        }

    def _extract_plot_data(self) -> list:
        wedges = self._extract_wedges()
        if not wedges:
            raise ExtractionError(self.type, self.ax)

        values = self._extract_values(wedges)
        labels = self._extract_labels(wedges)

        self._elements.extend(wedges)

        return [
            {MaidrKey.X: label, MaidrKey.Y: value}
            for label, value in zip(labels, values)
        ]

    def _extract_wedges(self) -> list[Wedge]:
        """
        Read the slices of this layer, in the order they were drawn.

        The wedges ``Axes.pie`` returned are used when the patch handed them
        over, because they are this call's own: a nested pie draws two rings
        on one axes, and a layer that read the axes instead would see both
        rings' wedges and pair the wrong ones with its values.

        Falling back to the axes, ``Axes.pie`` adds one ``Wedge`` per slice
        in slice order, so the patch order is the data order the renderer
        indexes by. ``shadow=True`` interleaves a ``Shadow`` patch behind
        each slice; those are not wedges and are dropped either way, which
        keeps the wedges contiguous and index-aligned with the data.

        Returns
        -------
        list of Wedge
            One wedge per slice, in slice order.
        """
        patches = self.ax.patches if self._wedges is None else self._wedges
        return [patch for patch in patches if isinstance(patch, Wedge)]

    def _extract_values(self, wedges: list[Wedge]) -> list[float]:
        """
        Read one magnitude per slice, in slice order.

        A ``Wedge`` carries only its start and end angle, and ``Axes.pie``
        normalises its input — it plots ``x / sum(x)`` whenever the sum
        exceeds 1 — so the angles no longer hold the magnitudes the caller
        passed. ``ax.pie([30, 50, 20])`` draws wedges spanning 108/180/72
        degrees, and reading those back reports the fractions 0.3/0.5/0.2 for
        a plot of counts. The patch sees the call before matplotlib rewrites
        it, so the caller's own numbers are used whenever it supplied them.

        The angular fallback covers the case where they were not: the plot
        is then only recoverable as fractions of the whole, which is what
        matplotlib itself kept.

        Parameters
        ----------
        wedges : list of Wedge
            The slices of this layer, in slice order.

        Returns
        -------
        list of float
            One magnitude per slice.

        Raises
        ------
        ValueError
            If any magnitude the caller passed is negative. A negative slice
            has no area to draw, and matplotlib rejects one for the same
            reason.
        """
        values = self._as_floats(self._values)

        if values is not None and len(values) == len(wedges):
            if any(value < 0 for value in values):
                raise ValueError("Wedge sizes 'x' must be non negative values")
            return values

        # `theta2 - theta1` is the slice's share of the 360 degree whole. A
        # wedge matplotlib drew has already passed its own non-negative check,
        # so this branch has nothing left to reject.
        return [(float(wedge.theta2) - float(wedge.theta1)) / 360.0 for wedge in wedges]

    def _extract_labels(self, wedges: list[Wedge]) -> list[Any]:
        """
        Read one label per slice, in slice order.

        Parameters
        ----------
        wedges : list of Wedge
            The slices of this layer, in slice order.

        Returns
        -------
        list
            The ``labels`` argument of the original call where it was given,
            the labels matplotlib set on the wedges themselves where it was
            not, and the slice's position as a last resort — an unlabelled
            pie is still navigable when each slice can be named.
        """
        if self._labels is not None and len(self._labels) == len(wedges):
            return [self._as_label(label) for label in self._labels]

        labels = [str(wedge.get_label()) for wedge in wedges]
        return [label or str(index) for index, label in enumerate(labels)]

    @staticmethod
    def _as_label(label: Any) -> Any:
        """
        Coerce one slice label to something the schema can carry.

        A label is a string or a number on the wire, and the schema is JSON,
        so the numpy scalar a pandas column hands over has to be unwrapped to
        the Python value inside it — ``json.dumps`` refuses it otherwise, and
        the whole figure fails to render over one label. Anything else is
        named by its text, which is what a slice label is for.

        Parameters
        ----------
        label : Any
            One entry of the ``labels`` argument of the original call.

        Returns
        -------
        Any
            The label as a string or a number.
        """
        if isinstance(label, str):
            return label

        value = label.item() if hasattr(label, "item") else label
        if isinstance(value, (str, int, float)) and not isinstance(value, bool):
            return value

        return str(label)

    @staticmethod
    def _as_floats(values: Any) -> list[float] | None:
        """
        Coerce the caller's wedge sizes to plain floats.

        ``Axes.pie`` takes any 1-D array-like — a list, a numpy array, a
        pandas Series — and the schema is JSON, so whatever came in is read
        as a sequence of floats or not read at all.

        Parameters
        ----------
        values : Any
            The ``x`` argument of the original call, or None.

        Returns
        -------
        list of float, optional
            The magnitudes, or None when they are not a sequence of numbers.
        """
        # A string is iterable and its characters are not magnitudes; an
        # unresolved `data=` column name arrives as exactly that.
        if values is None or isinstance(values, (str, bytes)):
            return None

        try:
            return [float(value) for value in values]
        except (TypeError, ValueError):
            return None
