"""A plotly splom rendered a chart with no layers in it at all (#666).

A ``splom`` is one trace carrying ``n`` dimensions, and it draws an ``n`` by
``n`` grid of scatters. MAIDR's schema is a grid of subplots, which is that
shape exactly -- but nothing in the plotly path read a splom, so it produced
a one-by-one grid whose only cell held an empty layer list. `render()`
*succeeded* on that, so a reader was handed a chart that announced itself as
navigable and contained nothing. Worse than the unsupported-chart path,
which falls back to a picture and says what it is.

Measured before the reading:

    make_subplots 2x2   grid=2x[2, 2]  layers=[[[point], [bar]], [[point], [bar]]]
    splom (3 dims)      grid=1x[1]     layers=[[[]]]
    px.scatter_matrix   grid=1x[1]     layers=[[[]]]

So the machinery was there -- the plotly path already builds real subplot
grids -- and only the splom converter was missing.

Three keywords blank panels, and each is read rather than assumed: emitting
a panel the chart does not draw is the same defect as failing to emit one it
does. A blanked panel is left out entirely, and `_flatten_maidr` fills the
missing cell with an empty one, so the grid keeps its shape and the blanks
are holes in it -- which is what they are on the page.

**No panel claims a selector.** A splom's per-panel DOM has not been
measured, and the scatter selector addresses `.trace.scatter .point` inside
one subplot, which a splom does not lay out that way. Returning nothing is
what the WebGL branch already does for the same reason: a selector that
resolves to nothing is a highlight that silently never appears. Audio, text
and braille do not depend on it.
"""

from __future__ import annotations

import pytest

plotly = pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

A = [1.0, 2.0, 3.0]
B = [9.0, 8.0, 7.0]
C = [4.0, 5.0, 6.0]


def dims(*pairs):
    """Dimensions from ``(label, values)`` pairs."""
    return [dict(label=label, values=values) for label, values in pairs]


def grid(trace) -> list[list[list[dict]]]:
    """The layers of every cell, as a grid."""
    schema = PlotlyMaidr(go.Figure(trace))._flatten_maidr()
    return [[cell.get("layers", []) for cell in row] for row in schema["subplots"]]


def shape(cells) -> tuple[int, list[int]]:
    """Rows, and the width of each."""
    return len(cells), [len(row) for row in cells]


def drawn(cells) -> set[tuple[int, int]]:
    """The positions holding a layer."""
    return {
        (r, c)
        for r, row in enumerate(cells)
        for c, layers in enumerate(row)
        if layers
    }


def panel(cells, row, col) -> dict:
    """The single layer at one position."""
    layers = cells[row][col]
    assert len(layers) == 1
    return layers[0]


def test_a_splom_is_read_rather_than_emitting_nothing():
    cells = grid(go.Splom(dimensions=dims(("A", A), ("B", B))))

    assert shape(cells) == (2, [2, 2])
    assert len(drawn(cells)) == 4


def test_every_panel_is_a_scatter():
    cells = grid(go.Splom(dimensions=dims(("A", A), ("B", B))))

    for row in cells:
        for layers in row:
            for layer in layers:
                assert layer["type"].value == "point"


def test_a_panel_puts_its_column_on_x_and_its_row_on_y():
    # The whole layout. Panel (i, j) is dimension j against dimension i, so
    # a reading that transposed it would announce every off-diagonal panel
    # with its two variables the wrong way round.
    cells = grid(go.Splom(dimensions=dims(("A", A), ("B", B))))
    upper = panel(cells, 0, 1)

    assert upper["axes"]["x"]["label"] == "B"
    assert upper["axes"]["y"]["label"] == "A"
    assert [point["x"] for point in upper["data"]] == B
    assert [point["y"] for point in upper["data"]] == A


def test_the_diagonal_is_a_dimension_against_itself():
    cells = grid(go.Splom(dimensions=dims(("A", A), ("B", B))))
    corner = panel(cells, 0, 0)

    assert corner["axes"]["x"]["label"] == "A"
    assert corner["axes"]["y"]["label"] == "A"
    assert [point["x"] for point in corner["data"]] == A


def test_a_hidden_diagonal_leaves_holes_rather_than_panels():
    cells = grid(go.Splom(
        dimensions=dims(("A", A), ("B", B)),
        diagonal=dict(visible=False),
    ))

    assert shape(cells) == (2, [2, 2])
    assert drawn(cells) == {(0, 1), (1, 0)}


def test_a_visible_diagonal_is_the_default():
    # Plotly's default is visible, so an absent `diagonal` must not be read
    # as a hidden one.
    cells = grid(go.Splom(dimensions=dims(("A", A), ("B", B))))

    assert (0, 0) in drawn(cells)
    assert (1, 1) in drawn(cells)


def test_showupperhalf_false_keeps_the_lower_triangle():
    cells = grid(go.Splom(
        dimensions=dims(("A", A), ("B", B), ("C", C)),
        showupperhalf=False,
    ))

    assert drawn(cells) == {(0, 0), (1, 0), (1, 1), (2, 0), (2, 1), (2, 2)}


def test_showlowerhalf_false_keeps_the_upper_triangle():
    cells = grid(go.Splom(
        dimensions=dims(("A", A), ("B", B), ("C", C)),
        showlowerhalf=False,
    ))

    assert drawn(cells) == {(0, 0), (0, 1), (0, 2), (1, 1), (1, 2), (2, 2)}


def test_a_triangle_without_its_diagonal_keeps_the_drawn_panels_in_place():
    # Both blanking rules at once. Nothing is drawn in row 0 or in column 2,
    # so the grid is narrower -- but every panel the chart *does* draw keeps
    # the position it has on the page, which is what a reader navigates by.
    cells = grid(go.Splom(
        dimensions=dims(("A", A), ("B", B), ("C", C)),
        showupperhalf=False,
        diagonal=dict(visible=False),
    ))

    assert drawn(cells) == {(1, 0), (2, 0), (2, 1)}
    assert panel(cells, 2, 1)["axes"]["x"]["label"] == "B"
    assert panel(cells, 2, 1)["axes"]["y"]["label"] == "C"


def test_a_dimension_the_chart_hides_is_not_a_row_or_a_column():
    # `visible: False` on a dimension removes its panels entirely. Kept, it
    # would put an empty row and column in the grid -- the phantom-layer
    # shape of #421 spread across a whole axis of the matrix.
    cells = grid(go.Splom(dimensions=[
        dict(label="A", values=A),
        dict(label="B", values=B, visible=False),
    ]))

    assert shape(cells) == (1, [1])
    assert panel(cells, 0, 0)["axes"]["x"]["label"] == "A"


@pytest.mark.parametrize(
    "empty",
    [
        pytest.param({"label": "empty", "values": []}, id="empty list"),
        pytest.param({"label": "none"}, id="no values at all"),
    ],
)
def test_a_dimension_with_no_values_is_not_a_variable(empty):
    # Asked of `splom_panels` as well as of the whole pipeline. Measured,
    # both shapes survive `to_dict()` -- `values` comes back as `[]` and as
    # `None` respectively -- so the guard is what drops them here. The
    # pipeline happens to strip them a second time further up, which is why
    # the grid alone cannot tell whether this rule is being applied.
    from maidr.plotly.splom import splom_panels

    trace = {"type": "splom", "dimensions": [{"label": "A", "values": A}, empty]}
    panels = splom_panels(trace)

    assert len(panels) == 1
    assert (panels[0][0], panels[0][1]) == (0, 0)

    cells = grid(go.Splom(dimensions=[dict(label="A", values=A), dict(**empty)]))
    assert shape(cells) == (1, [1])


def test_a_single_dimension_reads_as_one_panel():
    cells = grid(go.Splom(dimensions=dims(("A", A))))

    assert shape(cells) == (1, [1])
    assert drawn(cells) == {(0, 0)}


def test_no_panel_claims_an_element_to_highlight():
    cells = grid(go.Splom(dimensions=dims(("A", A), ("B", B))))

    for row in cells:
        for layers in row:
            for layer in layers:
                assert "selector" not in layer
                assert "selectors" not in layer


def test_a_scatter_matrix_written_through_express_reads_the_same():
    px = pytest.importorskip("plotly.express")
    pd = pytest.importorskip("pandas")

    frame = pd.DataFrame({"A": A, "B": B})
    figure = px.scatter_matrix(frame, dimensions=["A", "B"])
    schema = PlotlyMaidr(figure)._flatten_maidr()
    cells = [[cell.get("layers", []) for cell in row] for row in schema["subplots"]]

    assert shape(cells) == (2, [2, 2])
    assert len(drawn(cells)) == 4
