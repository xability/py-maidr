"""A numeric-axis heatmap was labelled with its axis ticks, not its cells (#526).

``HeatPlot`` filled ``x`` and ``y`` from the axes' **tick labels**. On a
categorical axis those are the cells: ``sns.heatmap`` puts one fixed tick at
the centre of every cell and labels it, so the axis already names the grid. On
a numeric axis they are not, and there are usually more of them than there are
cells. Measured on matplotlib 3.9.4, every case below drawing a 2 x 3 grid:

    ax.hist2d(a, b, bins=(3, 2))    2 x 3    9 x labels    7 y labels
    ax.pcolormesh(z)                2 x 3    7 x labels    9 y labels
    ax.imshow(z)                    2 x 3    7 x labels    9 y labels
    sns.heatmap(z)                  2 x 3    3 x labels    2 y labels

Nothing raised, the layer rendered, and the counts and values were right, so a
reader moving to the second of three columns was read a number off matplotlib's
tick locator -- chosen to look tidy on an axis -- with no way to tell it was
somebody else's coordinate.

Every one of these artists knows its own boundaries: a mesh carries them as its
coordinates, an image as its extent. A cell is named by its **centre** rather
than by the range it covers, following ``HexbinPoint``, which carries a bin's
centre for the same reasons -- one label per column in the grammar, announced
on every move of the cursor, and the spacing between consecutive centres is the
cell width already.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402

#: A 2 x 3 grid of distinct values, so a transposed reading cannot pass.
GRID = np.arange(6, dtype=float).reshape(2, 3)

_RNG = np.random.default_rng(20260821)
#: Samples that fall into a 3 x 2 binning without an empty bin.
A = _RNG.normal(size=200)
B = _RNG.normal(size=200)


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _layer(fig) -> dict:
    """
    The single layer a figure registered.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure to read.

    Returns
    -------
    dict
        Its one layer.
    """
    grid = FigureManager.get_maidr(fig)._flatten_maidr()["subplots"]
    layers = [layer for row in grid for cell in row for layer in cell["layers"]]
    assert len(layers) == 1
    return layers[0]


def _shape(layer: dict) -> tuple[int, int]:
    """
    How many rows and columns the emitted grid has.

    Parameters
    ----------
    layer : dict
        The emitted layer.

    Returns
    -------
    tuple of int
        ``(rows, columns)``.
    """
    points = layer[MaidrKey.DATA][MaidrKey.POINTS]
    return len(points), len(points[0])


@pytest.mark.parametrize(
    "name, draw",
    [
        ("hist2d", lambda ax: ax.hist2d(A, B, bins=(3, 2))),
        ("pcolormesh", lambda ax: ax.pcolormesh(GRID)),
        ("pcolor", lambda ax: ax.pcolor(GRID)),
        ("imshow", lambda ax: ax.imshow(GRID)),
        ("heatmap", lambda ax: sns.heatmap(GRID, ax=ax)),
    ],
)
def test_every_heatmap_names_one_cell_per_cell(name, draw):
    """
    However the grid is drawn, there is a name for each of its cells.

    The count is the whole defect: a label list longer than the grid cannot be
    a list of the grid's names, whatever the numbers in it are.
    """
    fig, ax = plt.subplots()
    draw(ax)

    layer = _layer(fig)
    rows, columns = _shape(layer)

    assert (rows, columns) == (2, 3), name
    assert len(layer[MaidrKey.DATA][MaidrKey.X]) == columns, name
    assert len(layer[MaidrKey.DATA][MaidrKey.Y]) == rows, name


def test_a_binned_grid_is_named_by_the_centres_of_its_bins():
    """
    ``hist2d``'s cells are named from the edges it binned to.

    Asked of the artist rather than recomputed here: the bins are chosen from
    the data's range, so a test that wrote the numbers down would be pinning
    this sample rather than the reading.
    """
    fig, ax = plt.subplots()
    _, x_edges, y_edges, _ = ax.hist2d(A, B, bins=(3, 2))

    layer = _layer(fig)
    expected_x = [(x_edges[i] + x_edges[i + 1]) / 2 for i in range(3)]
    expected_y = [(y_edges[i] + y_edges[i + 1]) / 2 for i in range(2)]

    # Six significant figures, which is what a name is rounded to.
    assert [float(name) for name in layer[MaidrKey.DATA][MaidrKey.X]] == pytest.approx(
        expected_x, rel=1e-5
    )
    assert [float(name) for name in layer[MaidrKey.DATA][MaidrKey.Y]] == pytest.approx(
        expected_y, rel=1e-5
    )


def test_an_image_names_its_cells_by_index_as_a_categorical_heatmap_does():
    """
    ``imshow``'s default extent puts cell *i* at *i*, and that is its name.

    The same grid through ``sns.heatmap`` is named ``0``, ``1``, ``2`` off a
    categorical axis, and an image drawn from the same array should not
    disagree with it about what its columns are called.
    """
    fig, ax = plt.subplots()
    ax.imshow(GRID)
    image = _layer(fig)

    figure, axes = plt.subplots()
    sns.heatmap(GRID, ax=axes)
    categorical = _layer(figure)

    assert [float(name) for name in image[MaidrKey.DATA][MaidrKey.X]] == [0.0, 1.0, 2.0]
    assert [float(name) for name in image[MaidrKey.DATA][MaidrKey.Y]] == [0.0, 1.0]
    assert [float(name) for name in categorical[MaidrKey.DATA][MaidrKey.X]] == [
        0.0,
        1.0,
        2.0,
    ]


def test_an_image_drawn_from_the_bottom_names_its_rows_in_the_order_it_emits_them():
    """
    ``origin="lower"`` puts array row 0 at the bottom, and it is still row 0.

    ``get_extent()`` reports its ends bottom-then-top whichever way up the
    image is drawn -- ``(-0.5, 2.5, 1.5, -0.5)`` for ``upper`` and
    ``(-0.5, 2.5, -0.5, 1.5)`` for ``lower`` -- so reading them in the order
    given names the rows backwards for one of the two. The values are emitted
    in array order either way, so the names have to be.
    """
    fig, ax = plt.subplots()
    ax.imshow(GRID, origin="lower")
    layer = _layer(fig)

    assert layer[MaidrKey.DATA][MaidrKey.POINTS][0] == [0.0, 1.0, 2.0]
    assert [float(name) for name in layer[MaidrKey.DATA][MaidrKey.Y]] == [0.0, 1.0]


def test_a_caller_who_names_the_cells_themselves_keeps_their_names():
    """
    Ticks that *are* the cells are still the answer.

    This is what ``sns.heatmap`` relies on, and what a caller labelling a
    numeric grid by hand relies on too. The check is on where the ticks sit,
    not on how many there are: a locator that happened to draw three ticks on
    a three-column grid would otherwise have its numbers taken as the names.
    """
    fig, ax = plt.subplots()
    ax.pcolormesh(GRID)
    ax.set_xticks([0.5, 1.5, 2.5], ["left", "middle", "right"])
    ax.set_yticks([0.5, 1.5], ["bottom", "top"])

    layer = _layer(fig)

    assert layer[MaidrKey.DATA][MaidrKey.X] == ["left", "middle", "right"]
    assert layer[MaidrKey.DATA][MaidrKey.Y] == ["bottom", "top"]


def test_ticks_that_merely_count_right_do_not_become_the_names():
    """
    Three ticks in the wrong places are not three cell names.

    The tick positions are compared against the cells rather than counted,
    because a count alone is a coincidence a chart can hit: here the axis
    carries exactly one tick per column and not one of them is on a column.
    """
    fig, ax = plt.subplots()
    ax.pcolormesh(GRID)
    ax.set_xticks([0.0, 1.0, 2.0], ["zero", "one", "two"])

    layer = _layer(fig)

    assert layer[MaidrKey.DATA][MaidrKey.X] == ["0.5", "1.5", "2.5"]


def test_a_mesh_is_named_by_the_centres_between_its_own_coordinates():
    """
    ``pcolormesh`` cells sit between the coordinates the mesh carries.

    Pinned exactly rather than only counted, because this is the branch that
    reads a mesh's own coordinates and the one the axis-alignment assumption
    below lives in.
    """
    fig, ax = plt.subplots()
    ax.pcolormesh(GRID)
    layer = _layer(fig)

    assert layer[MaidrKey.DATA][MaidrKey.X] == ["0.5", "1.5", "2.5"]
    assert layer[MaidrKey.DATA][MaidrKey.Y] == ["0.5", "1.5"]


def test_a_mesh_whose_columns_do_not_share_an_x_is_not_given_column_names():
    """
    A curvilinear mesh has no one name per column, and is not handed one.

    ``pcolormesh(X, Y, Z)`` accepts a fully two-dimensional ``X``. Sheared,
    a 2 x 3 has x edges of ``[0, 1, 2, 3]`` on its first row and
    ``[0.3, 1.3, 2.3, 3.3]`` on its second, so naming every column after the
    row that happens to come first would give a reader a coordinate that is
    true of one row of the grid and of no other.

    What it falls back to -- the axis ticks -- is the reading #526 is about,
    and for this one shape it is unchanged: a grid whose cells cannot be
    located is left exactly as it was rather than given names invented for
    it.
    """
    columns, rows = np.meshgrid(np.arange(4.0), np.arange(3.0))
    sheared = columns + 0.3 * rows

    fig, ax = plt.subplots()
    ax.pcolormesh(sheared, rows, GRID)
    layer = _layer(fig)

    assert len(layer[MaidrKey.DATA][MaidrKey.X]) != 3


def test_cells_too_close_to_separate_at_six_figures_get_longer_names():
    """
    Two cells with one name would tell a reader they had not moved.

    Six significant figures is short enough to say on every move and enough
    for any ordinary grid, but centres around 1e9 spaced by 1 all round to
    the same six, so the precision is raised until the names differ.
    """
    edges = np.array([1e9, 1e9 + 1, 1e9 + 2, 1e9 + 3])
    fig, ax = plt.subplots()
    ax.pcolormesh(edges, np.array([0.0, 1.0, 2.0]), GRID)

    names = _layer(fig)[MaidrKey.DATA][MaidrKey.X]

    assert len(set(names)) == 3
    assert [float(name) for name in names] == [1e9 + 0.5, 1e9 + 1.5, 1e9 + 2.5]


def test_a_pcolor_grid_is_named_like_the_mesh_it_shares_a_contract_with():
    """
    ``pcolor``'s `PolyQuadMesh` keeps its coordinates the same way.

    Pinned to values rather than left to the shape check the parametrised
    test makes: the two classes disagree about how they store their *values*
    -- one flattens, one does not -- so agreeing about their coordinates is
    worth asserting rather than assuming.
    """
    fig, ax = plt.subplots()
    ax.pcolor(GRID)
    layer = _layer(fig)

    assert layer[MaidrKey.DATA][MaidrKey.X] == ["0.5", "1.5", "2.5"]
    assert layer[MaidrKey.DATA][MaidrKey.Y] == ["0.5", "1.5"]


def test_a_gouraud_shaded_mesh_is_named_at_its_coordinates_not_between_them():
    """
    ``shading="gouraud"`` puts the values *at* the coordinates.

    So there is one coordinate per cell rather than one per boundary, and
    each is already the cell's position -- measured as shape ``(2, 3, 2)``
    against the flat-shaded ``(3, 4, 2)``. Taking midpoints of a list that
    short would name two cells from three, which is why the count decides
    which reading applies.

    The names come out as the same indices ``imshow`` and ``sns.heatmap``
    give the same grid, which is the answer a reader should get however the
    chart was drawn.
    """
    fig, ax = plt.subplots()
    ax.pcolormesh(GRID, shading="gouraud")
    layer = _layer(fig)

    assert layer[MaidrKey.DATA][MaidrKey.X] == ["0", "1", "2"]
    assert layer[MaidrKey.DATA][MaidrKey.Y] == ["0", "1"]
