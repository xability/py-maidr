from __future__ import annotations

import base64
import math
from typing import Any

import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot


class PlotlyPiePlot(PlotlyPlot):
    """
    Extract data from a Plotly pie trace.

    A donut needs nothing of its own here: ``hole`` cuts the middle out of the
    wedges and leaves the data behind them untouched, so it is still a pie.

    Parameters
    ----------
    trace : dict
        The pie trace dict.
    layout : dict
        The Plotly figure layout.
    pie_position : int, default=0
        The trace's zero-based position among the figure's pie traces. Plotly
        draws every pie into one figure-level ``pielayer`` rather than into a
        subplot, so this — not an axis pair, which a pie does not have — is
        what makes the selector address *this* pie. The default describes the
        single-pie figure; :class:`~maidr.plotly.plotly_maidr.PlotlyMaidr`
        passes real positions.
    **kwargs : str
        Axis names forwarded to the parent class.
    """

    def __init__(
        self,
        trace: dict,
        layout: dict,
        *,
        pie_position: int = 0,
        **kwargs: str,
    ) -> None:
        # A negative position builds ``nth-child(0)`` or lower, which matches
        # nothing and reports nothing -- the highlight simply never appears.
        if pie_position < 0:
            raise ValueError(f"pie position must be >= 0, got {pie_position}")

        super().__init__(trace, layout, PlotType.PIE, **kwargs)
        self._pie_position = pie_position

    def _get_selector(self) -> str:
        """
        Return the selector matching this pie's wedges, in slice order.

        This is the one plot type here that cannot scope itself with
        :meth:`_subplot_css_prefix`: pies are drawn into a figure-level
        ``g.pielayer``, so their wedges are never inside a ``.subplot.xy``
        group and a prefixed selector would match nothing. The pie's position
        among that layer's trace groups takes its place.

        Returns
        -------
        str
            A CSS selector resolving to one ``path.surface`` per slice, in the
            same order as the emitted data.
        """
        return (
            f".pielayer > .trace:nth-child({self._pie_position + 1}) "
            f"> .slice > path.surface"
        )

    def _extract_plot_data(self) -> list[dict]:
        """Return one flat ``{x: label, y: value}`` point per drawn wedge."""
        return [
            {MaidrKey.X: label, MaidrKey.Y: value}
            for label, value in self._slices()
        ]

    def _slices(self) -> list[tuple[str, float]]:
        """
        Reproduce the wedges plotly draws, in the order it draws them.

        Plotly does not draw one wedge per ``values`` entry in the order
        given; ``pie/calc.js`` builds its own slice list first. The emitted
        data has to follow that list exactly, because the selector is
        positional — one element per slice — so the first divergence lands
        every later slice on another wedge. The rules it applies, in order:

        * a value plotly does not read as a number is skipped, drawing no
          wedge at all;
        * repeated labels merge into one wedge holding their sum, kept at the
          label's first position;
        * an empty label becomes the entry's own index, while a null one
          stringifies to ``null`` as plotly's does, so a pair of them merges
          into one wedge in both;
        * a wedge whose merged total is negative is dropped;
        * with ``sort`` — plotly's *default* — the wedges are then ordered by
          value, largest first, which is why data order is not slice order;
        * a label named in ``layout.hiddenlabels`` keeps its place in that
          ordering but has its wedge removed, so it must not be emitted
          either.

        A pie with no positive value left to draw is marked invisible by
        plotly and renders nothing, so it yields no slices here.

        Returns
        -------
        list of (str, float)
            One ``(label, value)`` pair per drawn wedge, in slice order.
        """
        raw_labels = self._trace.get("labels")
        raw_values = self._trace.get("values")
        labels = _as_list(raw_labels)
        values = _as_list(raw_values)

        # Each array bounds the other, and an array the author never supplied
        # bounds nothing -- an empty one still bounds the pie down to nothing.
        has_labels = raw_labels is not None
        has_values = raw_values is not None
        lengths = [len(labels)] if has_labels else []
        if has_values:
            lengths.append(len(values))
        length = min(lengths) if lengths else 0
        if not length:
            return []

        numbers = [_as_number(value) for value in values[:length]]
        if has_values and not any(n is not None and n > 0 for n in numbers):
            return []

        # Without a ``values`` array plotly weighs every entry equally and the
        # pie reports label counts; without a ``labels`` array it names the
        # wedges off ``label0``/``dlabel``, whose defaults number them 0, 1, 2.
        label0 = self._trace.get("label0", 0)
        dlabel = self._trace.get("dlabel", 1)

        wedges: list[list[Any]] = []
        position_of: dict[str, int] = {}
        for index in range(length):
            value = numbers[index] if has_values else 1
            if value is None:
                continue

            label = (
                self._to_native(labels[index])
                if has_labels
                else label0 + index * dlabel
            )
            # An empty label is the only one plotly replaces. A null one it
            # simply stringifies, which is why two of them merge into a single
            # "null" wedge there -- and so have to merge here too, or every
            # slice after the second lands on the wrong element.
            if label is None:
                label = "null"
            elif label == "":
                label = index
            label = str(label)

            position = position_of.get(label)
            if position is None:
                position_of[label] = len(wedges)
                wedges.append([label, value])
            else:
                wedges[position][1] += value

        wedges = [wedge for wedge in wedges if wedge[1] >= 0]
        if self._trace.get("sort", True):
            wedges.sort(key=lambda wedge: wedge[1], reverse=True)

        hidden = {str(label) for label in _as_list(self._layout.get("hiddenlabels"))}
        return [(label, value) for label, value in wedges if label not in hidden]

    def _extract_axes_data(self) -> dict:
        """Extract the two axis labels a pie carries.

        A pie draws no axes, but the wire format still names what its slice
        labels *are* on ``x`` and what their values *measure* on ``y`` — MAIDR
        announces a slice as those two names paired with the point. Plotly
        names neither, so an author who wants them says so through the
        layout's axis titles; otherwise the generic pair stands in, which at
        least reads as English where ``X`` and ``Y`` would not.
        """
        return {
            MaidrKey.X: self._axis_config(
                label=_axis_title(self._layout.get(self._xaxis_name, {}), "Label")
            ),
            MaidrKey.Y: self._axis_config(
                label=_axis_title(self._layout.get(self._yaxis_name, {}), "Value")
            ),
        }


def _as_list(value: Any) -> list:
    """
    Return a plotly data array as a plain list.

    ``Figure.to_dict()`` hands back the arrays the author supplied, plus one
    shape they never wrote: a numeric numpy array is exported as the
    ``{"dtype": ..., "bdata": ...}`` base64 spec plotly.js consumes, which is
    what ``plotly.express`` produces for every numeric column. Decoding it
    here keeps ``px.pie`` on the same path as a hand-built ``go.Pie``, where
    iterating the dict would otherwise walk its two keys. Anything that will
    not decode comes back empty rather than as something worse.

    Parameters
    ----------
    value : Any
        A plotly data array, a typed-array spec, or None.

    Returns
    -------
    list
        The array's entries, or an empty list.
    """
    if value is None:
        return []

    if isinstance(value, dict):
        dtype = value.get("dtype")
        bdata = value.get("bdata")
        if dtype is None or bdata is None:
            return []
        try:
            return np.frombuffer(base64.b64decode(bdata), dtype=dtype).tolist()
        except (TypeError, ValueError):
            return []

    # A string is iterable, so without this it would decompose into one
    # single-character entry per letter instead of being rejected.
    if isinstance(value, str):
        return []

    try:
        return list(value)
    except TypeError:
        return []


def _as_number(value: Any) -> float | None:
    """
    Return ``value`` as a number when plotly would read it as one.

    Plotly's numeric gate accepts finite numbers and the strings that parse as
    them, and skips everything else — a skipped entry draws no wedge, which is
    why this returns None rather than a stand-in. Booleans are numbers to
    Python but not to that gate, so they are rejected here too.

    Parameters
    ----------
    value : Any
        A single entry of the trace's ``values`` array.

    Returns
    -------
    float or None
        The number plotly would use, or None when it would skip the entry.
    """
    number = PlotlyPlot._to_native(value)

    if isinstance(number, bool):
        return None
    if isinstance(number, (int, float)):
        return number if math.isfinite(number) else None
    if isinstance(number, str):
        try:
            parsed = float(number)
        except ValueError:
            return None
        return parsed if math.isfinite(parsed) else None
    return None


def _axis_title(axis: dict, default: str) -> str:
    """Return a plotly axis dict's title text, or ``default`` when unset."""
    title = axis.get("title", "")
    if isinstance(title, dict):
        title = title.get("text", "")
    return str(title) if title else default
