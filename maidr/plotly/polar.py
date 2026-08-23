from __future__ import annotations

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list


class PlotlyPolarPlot(PlotlyPlot):
    """Extract data from a Plotly ``scatterpolar`` or ``barpolar`` trace.

    Both draw spokes around a circle -- one radius per angle -- and the core
    builds both on `RadarTrace`: a radar joins the spokes into an outline and
    a polar area fills the wedge between them, and a reader navigates the
    same spokes either way. So the payload is a line's: a list of series,
    each a list of ``{x: angle, y: radius}``.

    A polar chart has no orientation. `IS_ORIENTED` marks both false --
    "spokes sit around a circle rather than along an axis, so there is no
    main and cross axis to swap" -- so nothing is declared.
    """

    def __init__(
        self,
        trace: dict,
        layout: dict,
        plot_type: PlotType,
        *,
        trace_position: int = 0,
        **kwargs: str,
    ) -> None:
        super().__init__(trace, layout, plot_type, **kwargs)
        self._trace_position = trace_position

    def _get_selector(self) -> list[str]:
        """Address this trace's drawn outline, when it draws one.

        A radar-family layer resolves **one selector per series**, not one
        per point: `LineTrace.mapToSvgElements` compares
        ``selectors.length`` against the series count. A ``scatterpolar``
        draws exactly one ``path.js-line`` per trace, which is that element.

        Measured in Chromium: one scatterpolar gives one ``js-line``, two
        give two, each inside its own ``.polarlayer .scatterlayer .trace``.

        A ``barpolar`` gets none, and that is a limit worth stating. It
        draws no per-series path at all -- only one bar per spoke, four of
        them for four spokes. Four selectors would be read as four *series*,
        and the one selector its single series is allowed would have to
        point at the whole ``.trace.bars`` group, which outlines every bar
        at once and so highlights the same thing at every step of the walk.
        Neither says what a reader means by "where am I", so the layer ships
        without a highlight and keeps its audio, braille and text -- the
        outcome #145 established for a layer with nothing to point at.
        """
        if self.type is not PlotType.RADAR:
            return []
        return [
            f".polarlayer .scatterlayer "
            f".trace:nth-child({self._trace_position + 1}) path.js-line"
        ]

    def _extract_axes_data(self) -> dict:
        """Name the angle and the radius.

        A polar chart draws no cartesian axes, so ``layout.xaxis`` is not
        where its names live -- borrowing from there would take another
        trace's titles or the generic fallback where the author had in fact
        named these.

        Only the radius can be named. ``layout.polar.radialaxis`` takes a
        ``title``; ``angularaxis`` does not have the property at all --
        plotly rejects it outright ("Invalid property specified for object
        of type plotly.graph_objs.layout.polar.AngularAxis: 'title'"). So
        the angle always takes the generic word, and reading a title off it
        would be reading a key plotly never writes.
        """
        polar = self._layout.get("polar") or {}
        return {
            MaidrKey.X: self._axis_config(label="Angle"),
            MaidrKey.Y: self._axis_config(
                label=_axis_title(polar.get("radialaxis"), "Radius")
            ),
        }

    def _extract_plot_data(self) -> list[list[dict]]:
        """One series of spokes, wrapped for the list-of-series shape.

        ``theta`` is the angle and ``r`` the radius, which is the pair a
        polar trace states -- not ``x`` and ``y``, which it does not carry
        at all. A spoke with no radius is dropped: plotly draws nothing for
        it, and `RadarTrace` places its spokes at an equal share of the
        circle by *count*, so keeping a gap would rotate every later spoke.
        """
        angles = as_list(self._trace.get("theta"))
        radii = as_list(self._trace.get("r"))

        spokes = [
            {MaidrKey.X: self._to_native(angle), MaidrKey.Y: self._to_native(radius)}
            for angle, radius in zip(angles, radii)
            if radius is not None
        ]
        return [spokes] if spokes else []


def _axis_title(axis: object, default: str) -> str:
    """Return a plotly polar axis's title text, or ``default`` when unset."""
    if not isinstance(axis, dict):
        return default
    title = axis.get("title", "")
    if isinstance(title, dict):
        title = title.get("text", "")
    return str(title) if title else default
