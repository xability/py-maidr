from __future__ import annotations

import math

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot, as_list, subplot_block
from maidr.plotly.step_shape import renders_through_webgl


class PlotlyPolarPlot(PlotlyPlot):
    """Extract data from a Plotly ``scatterpolar``, ``scatterpolargl`` or
    ``barpolar`` trace.

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
        trace_position: int,
        **kwargs: str,
    ) -> None:
        super().__init__(trace, layout, plot_type, **kwargs)
        self._trace_position = trace_position
        self._subplot = subplot_name(trace)

    def _get_selector(self) -> list[str]:
        """Address this trace's drawn outline, when it draws one.

        A radar-family layer resolves **one selector per series**, not one
        per point: `LineTrace.mapToSvgElements` compares
        ``selectors.length`` against the series count. A ``scatterpolar``
        draws exactly one ``path.js-line`` per trace, which is that element.

        Measured in Chromium: one scatterpolar gives one ``js-line``, two
        give two, each inside its own ``.scatterlayer .trace``.

        The selector is scoped to **this trace's own polar subplot**, and
        the position counted among that subplot's scatterpolar traces only.
        A figure may hold several: plotly draws each as its own
        ``<g class="polar">`` / ``<g class="polar2">`` under one shared
        ``.polarlayer``, each with its own ``.scatterlayer`` numbered from
        one. Unscoped, ``.trace:nth-child(1)`` matched the first trace of
        *every* polar subplot -- one keypress outlining two charts -- and
        ``nth-child(2)`` matched nothing at all, because no subplot held a
        second. Measured on a 1x2 polar grid before this: 2 elements and 0.
        Scoped, every (subplot, position) pair resolves to exactly one.

        A ``barpolar`` gets none, and that is a limit worth stating. It
        draws no per-series path at all -- only one bar per spoke, four of
        them for four spokes. Four selectors would be read as four *series*,
        and the one selector its single series is allowed would have to
        point at the whole ``.trace.bars`` group, which outlines every bar
        at once and so highlights the same thing at every step of the walk.
        Neither says what a reader means by "where am I", so the layer ships
        without a highlight and keeps its audio, braille and text -- the
        outcome #145 established for a layer with nothing to point at.

        ## When there is no outline

        "Exactly one ``path.js-line`` per trace" holds for every mode that
        draws a line and for none that does not, which is a distinction the
        original measurement did not have to make. Measured again in
        Chromium on ``r=[1, 2, 3]``, counting inside the trace's own ``<g>``:

        .. code-block:: text

            mode                 path.js-line   g.points path.point
            unset (default)            1               3
            "lines"                    1               3
            "lines+markers"            1               3
            "markers"                  0               3
            "text"                     0               0

        So a markers-only radar named an element plotly never drew and the
        layer lost its highlight entirely (#656). Its markers are named
        instead: one ``path.point`` per sample, which is the shape
        `LineTrace.mapViaDomElements` already takes -- a selector whose match
        count equals the series' point count is used element for element,
        with no path to parse.

        A ``mode="text"`` trace draws neither, and keeps no selector for the
        reason ``barpolar`` has none.

        ## When there is no element at all

        A ``scatterpolargl`` draws the same spokes through regl, onto a
        ``<canvas>``, and so puts nothing in the ``.scatterlayer`` for any
        mode. Measured in Chromium on ``r=[1, 2, 3]``: a ``scatterpolar``
        gives one ``.trace`` there and no canvas, a ``scatterpolargl`` gives
        no ``.trace`` and three canvases (#668). It keeps its audio, braille
        and text and names nothing, which is what its cartesian twin already
        does.
        """
        if self.type is not PlotType.RADAR:
            return []
        if renders_through_webgl(self._trace):
            return []
        drawn = self._drawn_mark()
        if drawn is None:
            return []
        return [
            f".polarlayer > g.{self._subplot} .scatterlayer "
            f".trace:nth-child({self._trace_position + 1}) {drawn}"
        ]

    def _drawn_mark(self) -> str | None:
        """The element this trace draws for a reader to be pointed at.

        Read from ``mode`` rather than from the drawing, which is not
        available here. An absent ``mode`` is plotly's default and always
        includes lines -- ``"lines+markers"`` up to twenty points and
        ``"lines"`` beyond -- so it takes the outline.

        Returns
        -------
        str or None
            The element to name, or None when the trace draws no mark.
        """
        mode = self._trace.get("mode")
        if mode is None or "lines" in str(mode):
            return "path.js-line"
        if "markers" in str(mode):
            return "g.points path.point"
        return None

    def _extract_axes_data(self) -> dict:
        """Name the angle and the radius.

        A polar chart draws no cartesian axes, so ``layout.xaxis`` is not
        where its names live -- borrowing from there would take another
        trace's titles or the generic fallback where the author had in fact
        named these. The titles are read from *this* trace's own polar
        block: a figure's second polar subplot is ``layout.polar2``, and
        reading ``layout.polar`` for it would hand a reader the first
        chart's radial title.

        Only the radius can be named. ``layout.polar.radialaxis`` takes a
        ``title``; ``angularaxis`` does not have the property at all --
        plotly rejects it outright ("Invalid property specified for object
        of type plotly.graph_objs.layout.polar.AngularAxis: 'title'"). So
        the angle always takes the generic word, and reading a title off it
        would be reading a key plotly never writes.
        """
        polar = self._layout.get(self._subplot) or {}
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

        "No radius" is ``None`` or a non-finite number, because a gap
        reaches this in either spelling and the difference is not the
        author's. A list written with ``None`` arrives as ``None``; the
        same list as a numpy array arrives base64-encoded and comes back
        through `as_list` as ``nan``. Dropping only ``None`` would have made
        the same chart read correctly or rotate depending on how its author
        happened to hold the data.
        """
        angles = as_list(self._trace.get("theta"))
        radii = as_list(self._trace.get("r"))

        spokes = [
            {MaidrKey.X: self._to_native(angle), MaidrKey.Y: self._to_native(radius)}
            for angle, radius in zip(angles, radii)
            if _is_a_radius(radius)
        ]
        return [spokes] if spokes else []


def subplot_name(trace: dict) -> str:
    """Return the ``layout`` key naming this polar trace's own subplot.

    A polar trace is addressed by ``subplot`` -- ``"polar"``, ``"polar2"``,
    ... -- rather than by an axis pair, and the same string is both the
    ``layout`` key holding that subplot's axes and domain and the class
    plotly gives its ``<g>`` under ``.polarlayer``. A trace that names none
    belongs to the first.

    Parameters
    ----------
    trace : dict
        One ``scatterpolar`` or ``barpolar`` trace.

    Returns
    -------
    str
        The subplot name, defaulting to ``"polar"``.
    """
    return subplot_block(trace, "subplot", "polar")


def _is_a_radius(value: object) -> bool:
    """Report whether a ``r`` entry is a radius rather than a gap."""
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    return True


def _axis_title(axis: object, default: str) -> str:
    """Return a plotly polar axis's title text, or ``default`` when unset."""
    if not isinstance(axis, dict):
        return default
    title = axis.get("title", "")
    if isinstance(title, dict):
        title = title.get("text", "")
    return str(title) if title else default
