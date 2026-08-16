"""StepPlot — a piecewise-constant line whose levels may carry ordinal names."""

from __future__ import annotations

from typing import Dict, List, Optional

from matplotlib import cbook
from matplotlib.axes import Axes

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.core.plot.lineplot import MultiLinePlot
from maidr.util.step_utils import resolve_step_direction


class StepPlot(MultiLinePlot):
    """
    A step (stairs) plot layer, where the value is held across an interval and
    then jumps rather than being interpolated between samples.

    Numerically a step plot is a line plot, so all coordinate extraction,
    per-series nesting, GID assignment, selector generation and legend/``z``
    handling are inherited unchanged from :class:`MultiLinePlot`. ``y`` stays
    numeric because it is what drives sonification, braille and the min/max
    bounds on the MAIDR side.

    On top of that this class emits the two things a step chart has that a
    line chart does not:

    ``stepDirection``
        Which side of each sample the value is held on, mapped from the
        matplotlib ``drawstyle``. Omitted when the axes does not author one
        unambiguously.
    per-point ``label``
        The ordinal level *name* for a point's numeric ``y`` — ``"REM"``
        rather than ``3`` — resolved from the y tick labels. This is what
        makes a hypnogram (sleep stage against time) announce a stage name
        instead of an opaque stage code.

    Parameters
    ----------
    ax : Axes
        The matplotlib axes object containing the step line(s).
    **kwargs : dict
        Additional keyword arguments forwarded to the parent class.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        super().__init__(ax, PlotType.STEP, **kwargs)

    def render(self) -> dict:
        """
        Build the base line schema, then add the step-specific payload.

        Returns
        -------
        dict
            The MAIDR layer schema, with ``stepDirection`` added when the axes
            authors one and a ``label`` added to every point that sits on a
            named y tick.

        Notes
        -----
        ``super().render()`` must run first: it is what merges the per-axis
        format configuration into ``axes`` and attaches ``selectors``, and it
        is what produces the ``data`` payload this method annotates.
        """
        schema = super().render()

        # Resolved from the lines this layer describes, not from the axes.
        # `render()` runs at `save_html()` time, so anything drawn onto the
        # axes in between reached the sweep -- a box plot added after the step
        # line was enough to make the drawstyles "disagree" and drop the field.
        direction = resolve_step_direction(self._series())
        if direction is not None:
            schema[MaidrKey.STEP_DIRECTION] = direction

        self._attach_level_labels(schema.get(MaidrKey.DATA))

        return schema

    def _attach_level_labels(self, data: Optional[List[List[dict]]]) -> None:
        """
        Add ``label`` to every point whose ``y`` sits on a named y tick.

        Points whose ``y`` does not land on a named tick are left untouched,
        so a numeric step plot emits no labels at all rather than emitting
        misleading ones.

        Parameters
        ----------
        data : list of list of dict or None
            The nested per-series point payload produced by the parent class.
            Mutated in place.
        """
        levels = self._resolve_y_levels()
        if not levels or not data:
            return

        for series in data:
            for point in series:
                y = point.get(MaidrKey.Y)
                try:
                    name = levels.get(float(y))  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    continue
                if name:
                    point[MaidrKey.LABEL] = name

    def _resolve_y_levels(self) -> Dict[float, str]:
        """
        Map each named y tick position to its ordinal level name.

        Resolution happens at *render* time, not at patch time, because the
        idiomatic way to build a hypnogram is to plot the numeric stage codes
        first and name them afterwards with ``ax.set_yticks(codes,
        labels=names)`` or ``ax.set_yticklabels(names)``.

        Notes
        -----
        The map is keyed by tick *coordinate* rather than by index, and is
        read straight off the axes rather than through
        :meth:`maidr.util.mixin.extractor_mixin.LevelExtractorMixin.extract_level`.
        That helper filters tick labels against ``ax.dataLim``, which silently
        drops the boundary levels — precisely the ``Awake`` and ``N3`` ends of
        a hypnogram — and returns labels without their positions, so it cannot
        answer "which level is at y = 4?" at all.

        Returns
        -------
        dict
            ``{tick position: level name}``. Empty when the axes carries no
            named levels.
        """
        levels = self._levels_from_ticks(self.ax)
        if levels:
            return levels

        # Fallback: a faceted hypnogram commonly names the levels on only one
        # panel of a ``sharey`` group, mirroring how ``extract_shared_ylabel``
        # recovers a shared axis label.
        try:
            siblings = self.ax.get_shared_y_axes().get_siblings(self.ax)
        except (AttributeError, TypeError):
            return {}

        for sibling in siblings:
            if sibling is self.ax:
                continue
            levels = self._levels_from_ticks(sibling)
            if levels:
                return levels

        return {}

    @staticmethod
    def _levels_from_ticks(ax: Axes) -> Dict[float, str]:
        """
        Read ``{tick position: level name}`` off a single axes.

        Blank labels are skipped, as are labels that are themselves numerals
        (``"3"``, ``"1,000"``, ``"−0.5"``) and labels rendered as mathtext
        (``"$\\mathdefault{10^{1}}$"`` on a log axis). Neither carries ordinal
        information: they are the y *number* written out by a tick formatter,
        which MAIDR already announces, and a formatter is free to write a
        number that is not the tick's own coordinate — the default
        ``ScalarFormatter`` labels y = 1000000 as ``"0.0"`` once it factors an
        offset out, and ``ticklabel_format(style="sci")`` labels it ``"1.00"``.
        Emitting those as level names would announce a flatly wrong value, so
        every numeral is dropped rather than only the ones that echo their own
        position.

        Parameters
        ----------
        ax : Axes
            The axes whose y ticks should be read.

        Returns
        -------
        dict
            ``{tick position: level name}``, possibly empty.
        """
        try:
            positions = list(ax.get_yticks())
            labels = [text.get_text() for text in ax.get_yticklabels()]
        except (AttributeError, TypeError):
            return {}

        levels: Dict[float, str] = {}
        for position, text in zip(positions, labels):
            name = text.strip()
            if not name:
                continue
            if StepPlot._is_number_rendering(name):
                continue
            levels[float(position)] = name
        return levels

    @staticmethod
    def _is_number_rendering(text: str) -> bool:
        """
        Report whether a tick label is a formatter's rendering of a number.

        Parameters
        ----------
        text : str
            The tick label text.

        Returns
        -------
        bool
            ``True`` when ``text`` parses as a bare number, or is mathtext
            (which is how numeric formatters typeset exponents). A label a
            formatter cannot have produced from the number alone — ``"$1,000"``,
            ``"50%"``, ``"Awake"`` — returns ``False`` and is kept.

        Notes
        -----
        A numeral is rejected whatever its value, not only when it matches its
        own tick position: an offset or scaled axis renders y = 1000000 as
        ``"0.0"``, and labelling that point ``"0.0"`` is worse than leaving it
        unlabelled. The cost is that an axis deliberately relabelled with
        numerals (``set_yticks([0, 1], labels=["1", "2"])``) yields no level
        names; those points still sonify and braille from their numeric ``y``.
        """
        # matplotlib typesets exponents (log axes) as mathtext; announcing the
        # raw LaTeX would be worse than announcing nothing.
        if cbook.is_math_text(text):
            return True
        # matplotlib renders negative ticks with U+2212 MINUS SIGN.
        normalized = text.replace(",", "").replace("−", "-")
        try:
            float(normalized)
        except ValueError:
            return False
        return True
