from __future__ import annotations

import math
from typing import Any

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list, domain_interval


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
    borrows_axis_titles : bool, default=True
        Whether this pie may name its two dimensions from the layout's axis
        titles. A pie draws no axes, so those titles are only its own when no
        cartesian trace shares them — see :meth:`_extract_axes_data` for why
        borrowing another trace's is worse than the generic fallback. The
        default describes the pie-only figure;
        :class:`~maidr.plotly.plotly_maidr.PlotlyMaidr` passes False when a
        cartesian trace shares the pie's default axis pair.
    **kwargs : str
        Axis names forwarded to the parent class.
    """

    def __init__(
        self,
        trace: dict,
        layout: dict,
        *,
        pie_position: int = 0,
        borrows_axis_titles: bool = True,
        **kwargs: str,
    ) -> None:
        # A negative position builds ``nth-child(0)`` or lower, which matches
        # nothing and reports nothing -- the highlight simply never appears.
        if pie_position < 0:
            raise ValueError(f"pie position must be >= 0, got {pie_position}")

        super().__init__(trace, layout, PlotType.PIE, **kwargs)
        self._pie_position = pie_position
        self._borrows_axis_titles = borrows_axis_titles

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

    def _title_anchor(self) -> tuple[float, float]:
        """
        Return the point a ``subplot_titles`` annotation for this pie sits at.

        The base class reads the rectangle off ``layout.xaxis``/``yaxis``,
        which a pie does not have: every pie in a figure shares the *default*
        axis names, so every one of them would read the default domain
        ``[0, 1]``, put its anchor at the middle of the figure, and match none
        of the titles ``make_subplots`` centred over the actual columns. A pie
        is placed by its own ``domain`` rectangle instead — the same one
        :meth:`~maidr.plotly.plotly_maidr.PlotlyMaidr._trace_domain_start`
        reads to give it a grid cell — so that is what it is anchored by.

        Only the anchor is overridden; matching a title to it stays in the
        base class, so a pie and a bar agree on what counts as a match.

        Returns
        -------
        tuple of (float, float)
            The ``(x_mid, y_top)`` of this pie's rectangle, as fractions of
            the figure.
        """
        domain = self._trace.get("domain")
        x_start, x_end = domain_interval(domain, "x")
        _, y_top = domain_interval(domain, "y")
        return (x_start + x_end) / 2, y_top

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

        These rules are mirrored rather than called, so they can drift if
        plotly changes them. Verified against plotly.py 6.7.0; the tests pin
        one rule each, so a drift surfaces as a named failure rather than as
        silently shifted slices.

        Returns
        -------
        list of (str, float)
            One ``(label, value)`` pair per drawn wedge, in slice order.
        """
        # Whether anything is drawn at all is decided by `draws_wedges`, which
        # the subplot grid asks as well: a pie that yields no slices forms no
        # layer, and a layer-less pie must not claim a grid cell either.
        if not draws_wedges(self._trace):
            return []

        raw_labels = self._trace.get("labels")
        raw_values = self._trace.get("values")
        labels = as_list(raw_labels)
        values = as_list(raw_values)
        has_labels = raw_labels is not None
        has_values = raw_values is not None
        length = _entry_count(self._trace)
        numbers = [_as_number(value) for value in values[:length]]

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
            label = _wedge_label(label, index)

            position = position_of.get(label)
            if position is None:
                position_of[label] = len(wedges)
                wedges.append([label, value])
            else:
                wedges[position][1] += value

        wedges = [wedge for wedge in wedges if wedge[1] >= 0]
        if self._sorts_wedges():
            wedges.sort(key=lambda wedge: wedge[1], reverse=True)

        # Plotly matches `hiddenlabels` with `indexOf` against the *stringified*
        # label -- `i.indexOf(p) !== -1`, where `p` has already become "null",
        # an index, or `String(label)`. `indexOf` is strict equality, so only a
        # string entry can ever match: `[null].indexOf("null")` is -1, and so is
        # `[5].indexOf("5")`. A non-string entry therefore hides nothing there,
        # and must hide nothing here -- dropping a wedge plotly still draws
        # would shift every later slice onto the wrong element.
        hidden = {
            label
            for label in as_list(self._layout.get("hiddenlabels"))
            if isinstance(label, str)
        }
        return [(label, value) for label, value in wedges if label not in hidden]

    def _sorts_wedges(self) -> bool:
        """Report whether plotly orders this trace's wedges by value.

        A hook rather than a `self._trace.get("sort", True)` in place,
        because :class:`~maidr.plotly.funnelarea.PlotlyFunnelareaPlot` shares
        every other rule in :meth:`_slices` and breaks this one: plotly gives
        a funnelarea no ``sort`` attribute at all, and measured against
        ``gd.calcdata``, ``values=[40, 100, 60]`` stayed in that order rather
        than being reordered largest-first.

        Returns
        -------
        bool
            True when the wedges are drawn largest-first, which is plotly's
            default for a pie.
        """
        return bool(self._trace.get("sort", True))

    #: What this trace's two dimensions are called when the layout names
    #: neither. A pie's slices are categories carrying values; a subclass
    #: whose slices mean something else says so by overriding this.
    _AXIS_FALLBACKS = ("Category", "Value")

    def _extract_axes_data(self) -> dict:
        """Extract the two axis labels a pie carries.

        A pie draws no axes, but the wire format still names what its slice
        labels *are* on ``x`` and what their values *measure* on ``y`` — MAIDR
        announces a slice as those two names paired with the point. Plotly
        names neither, so an author who wants them says so through the
        layout's axis titles; otherwise the generic pair stands in, which at
        least reads as English where ``X`` and ``Y`` would not. It is the same
        pair :class:`~maidr.core.plot.pieplot.PiePlot` falls back to, because
        an unlabelled pie is announced by its plot type, not by its library.

        Those titles are only borrowed when the pie has them to itself. A
        cartesian trace with no explicit axis pair shares the same default
        ``xaxis``/``yaxis``, and their titles describe *its* axes — a bar's
        "Month" read against a pie's slice labels is worse than the generic
        pair, because it is confidently wrong rather than merely vague.
        """
        if self._borrows_axis_titles:
            x_axis = self._layout.get(self._xaxis_name, {})
            y_axis = self._layout.get(self._yaxis_name, {})
        else:
            x_axis, y_axis = {}, {}

        x_default, y_default = self._AXIS_FALLBACKS
        return {
            MaidrKey.X: self._axis_config(label=_axis_title(x_axis, x_default)),
            MaidrKey.Y: self._axis_config(label=_axis_title(y_axis, y_default)),
        }


def draws_wedges(trace: dict) -> bool:
    """
    Report whether plotly draws any wedge for a pie or funnelarea trace.

    This is the emptiness rule of :meth:`PlotlyPiePlot._slices`, kept apart
    so it has a second caller: :func:`~maidr.plotly.plotly_maidr.PlotlyMaidr`
    decides whether the trace's ``domain`` rectangle earns a grid cell, and a
    trace that draws nothing forms no layer (#638), so it must not reserve a
    cell either (#702). The two go together: a cell without a layer is an
    empty stop for the reader to tab into.

    Two things leave a pie with nothing to draw. An array the author supplied
    bounds the other, so an empty ``labels`` or ``values`` bounds the pie down
    to no entries at all -- ``labels=["a", "b"]`` with ``values=[]`` draws
    nothing, whatever the labels say. And plotly marks a pie whose values hold
    nothing positive invisible, rendering no wedges; that is a short circuit
    rather than a rule of its own, since the merge and filter steps of
    :meth:`~PlotlyPiePlot._slices` reach the same empty answer, but it is
    what lets the question be asked without building the slices.

    Parameters
    ----------
    trace : dict
        The pie or funnelarea trace dict.

    Returns
    -------
    bool
        True when at least one wedge is drawn.
    """
    length = _entry_count(trace)
    if not length:
        return False
    raw_values = trace.get("values")
    if raw_values is None:
        # Without a `values` array every entry weighs one, so every entry is
        # a wedge.
        return True
    numbers = [_as_number(value) for value in as_list(raw_values)[:length]]
    return any(n is not None and n > 0 for n in numbers)


def _entry_count(trace: dict) -> int:
    """
    Return how many entries plotly reads off a pie's arrays.

    Each of ``labels`` and ``values`` bounds the other, and an array the
    author never supplied bounds nothing -- an empty one still bounds the pie
    down to nothing, and a pie with neither array has no entries at all.

    Parameters
    ----------
    trace : dict
        The pie or funnelarea trace dict.

    Returns
    -------
    int
        The length of the shortest supplied array, or 0 when none is.
    """
    lengths = [
        len(as_list(trace.get(key)))
        for key in ("labels", "values")
        if trace.get(key) is not None
    ]
    return min(lengths) if lengths else 0


def _wedge_label(label: Any, index: int) -> str:
    """
    Name a wedge the way plotly names it.

    Plotly replaces exactly one label: an empty one becomes the entry's own
    index. A null one it simply stringifies to ``null``, which is why a pair
    of nulls merges into a single wedge there -- and so has to merge here too,
    or every slice after the second lands on the wrong element.

    Parameters
    ----------
    label : Any
        The label as the author wrote it, already converted to a Python scalar.
    index : int
        The entry's position, substituted for an empty label.

    Returns
    -------
    str
        The wedge's name.
    """
    if label is None:
        return "null"
    if label == "":
        return str(index)
    return str(label)


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
