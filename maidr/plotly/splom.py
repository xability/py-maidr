from __future__ import annotations

from typing import Any

from maidr.plotly.scatter import PlotlyScatterPlot


def is_splom_trace(trace: dict) -> bool:
    """
    Whether a trace is a scatterplot matrix.

    Parameters
    ----------
    trace : dict
        The Plotly trace dictionary.

    Returns
    -------
    bool
        True for a ``splom`` trace.
    """
    return trace.get("type") == "splom"


def _dimensions(trace: dict) -> list[dict]:
    """
    The dimensions a splom was given, dropped to those it can draw.

    A dimension plotly is told to hide (``visible: False``) is not a panel,
    and one carrying no values is not a variable -- both would otherwise put
    an empty row and column in the grid, which is the phantom-layer shape of
    #421 spread across a whole axis of the matrix.

    Parameters
    ----------
    trace : dict
        The Plotly trace dictionary.

    Returns
    -------
    list of dict
        The drawable dimensions, in the order the chart lays them out.
    """
    drawable = []
    for dimension in trace.get("dimensions", []) or []:
        if not isinstance(dimension, dict):
            continue
        if dimension.get("visible") is False:
            continue
        values = dimension.get("values")
        if values is None or len(values) == 0:
            continue
        drawable.append(dimension)
    return drawable


def _draws_panel(trace: dict, row: int, col: int) -> bool:
    """
    Whether the chart draws the panel at ``(row, col)``.

    Three keywords blank panels, and each is read rather than assumed --
    emitting a panel the chart does not draw is the same defect as failing
    to emit one it does.

    - ``diagonal.visible = False`` blanks the leading diagonal. Plotly's
      default is visible, and a diagonal panel is a variable against itself.
    - ``showupperhalf = False`` blanks everything above it.
    - ``showlowerhalf = False`` blanks everything below it.

    Parameters
    ----------
    trace : dict
        The Plotly trace dictionary.
    row, col : int
        The panel's position, both zero-based.

    Returns
    -------
    bool
        True when the panel is drawn.
    """
    if row == col:
        diagonal = trace.get("diagonal") or {}
        return diagonal.get("visible") is not False
    if col > row:
        return trace.get("showupperhalf") is not False
    return trace.get("showlowerhalf") is not False


def _axis_title(label: Any) -> dict:
    """A layout axis carrying one title, or an empty one when unlabelled."""
    if isinstance(label, str) and label != "":
        return {"title": {"text": label}}
    return {}


class PlotlySplomPanelPlot(PlotlyScatterPlot):
    """
    One panel of a plotly scatterplot matrix, read as the scatter it is.

    A ``splom`` is a single trace carrying ``n`` dimensions, and it draws an
    ``n`` by ``n`` grid of scatters: panel ``(i, j)`` puts dimension ``j`` on
    x against dimension ``i`` on y. MAIDR's schema is a grid of subplots,
    which is that shape exactly, so each panel becomes an ordinary scatter
    layer at its own grid position rather than the whole matrix becoming one
    trace type of its own.

    Before this, a splom produced a one-by-one grid whose only cell held **no
    layers at all**, and `render()` succeeded on it -- so a reader was handed
    a chart that announced itself as navigable and contained nothing (#666).
    That is worse than the unsupported-chart path, which falls back to a
    picture and says what it is.

    The panel is handed a synthesised trace and a synthesised layout rather
    than the splom's own, so the parent's whole axes pipeline -- labels,
    formats, ranges and the grid-navigation preconditions -- applies to the
    two dimensions this panel actually draws.

    **No selector.** A splom's per-panel DOM has not been measured, and the
    parent's scatter selector addresses `.trace.scatter .point` inside one
    subplot, which a splom does not lay out that way. Returning nothing is
    the same answer the WebGL branch gives for the same reason: a selector
    that resolves to nothing is a highlight that silently never appears.
    Audio, text and braille do not depend on it.
    """

    def __init__(self, trace: dict, x: dict, y: dict) -> None:
        panel = {
            "type": "scatter",
            "mode": "markers",
            "x": list(x.get("values", [])),
            "y": list(y.get("values", [])),
        }
        layout = {
            "xaxis": _axis_title(x.get("label")),
            "yaxis": _axis_title(y.get("label")),
        }
        title = (trace.get("name") or "").strip()
        if title:
            layout["title"] = {"text": title}
        super().__init__(panel, layout)

    def _get_selector(self) -> str:
        """No element is claimed; see the class docstring."""
        return ""


def splom_panels(trace: dict) -> list[tuple[int, int, PlotlySplomPanelPlot]]:
    """
    One plot per panel the matrix draws, with its position in the grid.

    Positions are relative to the matrix's own top-left corner; the caller
    offsets them by the subplot the splom sits in.

    A panel the chart blanks is left out entirely rather than emitted empty:
    `_flatten_maidr` fills a missing cell in with an empty one, so the grid
    keeps its shape and the blanked panels are holes in it, which is what
    they are on the page.

    Parameters
    ----------
    trace : dict
        The Plotly trace dictionary.

    Returns
    -------
    list of (int, int, PlotlySplomPanelPlot)
        Each drawn panel, in row-major order.
    """
    dimensions = _dimensions(trace)
    panels = []
    for row, y in enumerate(dimensions):
        for col, x in enumerate(dimensions):
            if not _draws_panel(trace, row, col):
                continue
            panels.append((row, col, PlotlySplomPanelPlot(trace, x, y)))
    return panels
