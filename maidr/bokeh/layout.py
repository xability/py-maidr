"""Place the plots of a Bokeh layout on MAIDR's subplot grid.

MAIDR navigates a figure as a grid of subplots. Bokeh arranges plots with
``row``/``column`` (nested freely), ``gridplot``/``GridBox`` (explicit
cells) and ``Tabs``. Every one of those is flattened here into
``(plot, row, col)`` triples, in the reading order a sighted user would
scan them.
"""

from __future__ import annotations

from typing import Any, NamedTuple

from maidr.bokeh.utils import warn


class PlacedPlot(NamedTuple):
    """One Bokeh ``Plot`` and the grid cell it occupies."""

    plot: Any
    row: int
    col: int


def place_plots(model: Any) -> list[PlacedPlot]:
    """
    Every plot in a Bokeh layout, with its cell on the subplot grid.

    ``Row`` puts its children side by side and ``Column`` stacks them, each
    child taking as many cells as it spans itself, so ``column(row(a, b),
    c)`` puts ``a`` and ``b`` in the first row and ``c`` under ``a``.
    ``GridPlot`` and ``GridBox`` name their cells, and those are used as
    given. Widgets, ``Div`` s and spacers carry no data and take no cell.

    A ``Tabs`` shows one panel at a time, and MAIDR has no notion of a panel
    it cannot see, so only the active panel is placed; a warning names the
    ones left out rather than letting a reader believe the first tab is all
    there is.

    Parameters
    ----------
    model : bokeh.models.LayoutDOM
        A plot or a layout holding plots.

    Returns
    -------
    list of PlacedPlot
        The plots, in row-major reading order.
    """
    placed: list[PlacedPlot] = []
    _place(model, 0, 0, placed)
    # Row-major, so a grid built column by column is still read across first.
    placed.sort(key=lambda p: (p.row, p.col))
    return placed


def _place(model: Any, row: int, col: int, out: list[PlacedPlot]) -> tuple[int, int]:
    """
    Place ``model`` with its top-left cell at ``(row, col)``.

    Returns
    -------
    tuple of (int, int)
        How many rows and columns the model spans; ``(0, 0)`` for one that
        holds no plot, so it takes no room.
    """
    from bokeh.models import Column, GridBox, Plot, Row, Tabs

    try:
        from bokeh.models import GridPlot
    except ImportError:  # pragma: no cover - GridPlot is new in Bokeh 3.0
        GridPlot = GridBox

    if isinstance(model, Plot):
        out.append(PlacedPlot(model, row, col))
        return 1, 1

    if isinstance(model, Row):
        width, height = 0, 0
        for child in model.children:
            rows, cols = _place(child, row, col + width, out)
            width += cols
            height = max(height, rows)
        return height, width

    if isinstance(model, Column):
        width, height = 0, 0
        for child in model.children:
            rows, cols = _place(child, row + height, col, out)
            height += rows
            width = max(width, cols)
        return height, width

    if isinstance(model, (GridPlot, GridBox)):
        height, width = 0, 0
        for entry in model.children:
            child, child_row, child_col = entry[0], entry[1], entry[2]
            if child is None:
                continue
            rows, cols = _place(child, row + child_row, col + child_col, out)
            if rows and cols:
                height = max(height, child_row + rows)
                width = max(width, child_col + cols)
        return height, width

    if isinstance(model, Tabs):
        if not model.tabs:
            return 0, 0
        active = model.active if 0 <= (model.active or 0) < len(model.tabs) else 0
        left_out = [
            str(panel.title or index + 1)
            for index, panel in enumerate(model.tabs)
            if index != active
        ]
        if left_out:
            warn(
                "maidr reads only the active panel of a Bokeh Tabs layout; "
                f"the other panels ({', '.join(left_out)}) are not included."
            )
        return _place(model.tabs[active].child, row, col, out)

    return 0, 0
