"""A heatmap cell with no value was announced with one anyway (#696).

``HeatPlot`` read every cell through ``float(format(x, fmt))`` with no test
of whether there was a number there. Two ordinary inputs put a cell without
one in front of it:

* a ``NaN`` in the grid, which ``sns.heatmap``, ``imshow`` and ``pcolormesh``
  all draw as a blank cell;
* a **mask** -- ``sns.heatmap(corr, mask=np.triu(...))`` is the idiom for
  half a correlation matrix, and ``imshow`` of a ``np.ma.masked_where``
  behaves the same.

The first went wrong the way #427 did: ``json.dumps`` writes ``NaN`` as a bare
token, legal JavaScript and invalid JSON, and the core parses the SVG's
``maidr`` attribute with ``JSON.parse``, so one cell stopped the chart
initialising at all. The second was worse for being quiet -- the extractor
read ``.data``, the buffer *under* the mask, so the six blank cells of a
3 x 3 correlation were announced with the numbers the caller had hidden and
nothing raised.

``None`` serialises to ``null``, which ``HeatmapData.points`` is typed to
carry and the core reads as a gap, the way it already does for a bar
(``barplot._magnitude``) and a hexbin (``hexbinplot._count``).

The same method's per-cell loop is also the dominant Python-side cost of a
large render -- extracting a 1000 x 1000 float64 ``imshow`` took 2.0 s
against 0.09 s vectorised, min of 3 on a shared box under load -- so a
float64 or integer grid at the default format takes a vectorised path. That
path has to produce the values the loop did, cell for cell.
"""

from __future__ import annotations

import json
import logging

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.exception import ExtractionError  # noqa: E402

#: A 2 x 2 grid with one missing cell, small enough to spell out in full.
HOLED = np.array([[1.0, np.nan], [3.0, 4.0]])

#: A symmetric matrix with distinct off-diagonal values, so a reading that
#: took the cell under the mask cannot coincide with the right answer.
CORR = np.array([[1.0, 0.5, 0.2], [0.5, 1.0, 0.3], [0.2, 0.3, 1.0]])


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _reject_constant(token: str):
    raise ValueError(token)


def _points(fig) -> list[list]:
    """
    The cell values of a figure's one heatmap layer.

    Parameters
    ----------
    fig : matplotlib.figure.Figure
        The figure to read.

    Returns
    -------
    list of list
        The emitted grid, row by row.
    """
    maidr = FigureManager.get_maidr(fig)
    return maidr._plots[0].schema[MaidrKey.DATA][MaidrKey.POINTS]


def _parses_as_strict_json(fig) -> None:
    """Assert the payload survives what the core actually runs on it.

    ``json.loads`` accepts the bare tokens by default, exactly as
    ``json.dumps`` emits them, so a plain round trip passes while the browser
    fails. ``parse_constant`` is what lets this fail.
    """
    schema = FigureManager.get_maidr(fig)._flatten_maidr()

    json.loads(json.dumps(schema), parse_constant=_reject_constant)


@pytest.mark.parametrize(
    "name, draw",
    [
        ("heatmap", lambda ax: sns.heatmap(HOLED, ax=ax)),
        ("imshow", lambda ax: ax.imshow(HOLED)),
        ("pcolormesh", lambda ax: ax.pcolormesh(np.ma.masked_invalid(HOLED))),
        ("pcolormesh_nan", lambda ax: ax.pcolormesh(HOLED)),
        # Deliberately not gated on the matplotlib version. On 3.8 and 3.9
        # `pcolor`'s mesh hands back the masked cells *dropped* -- three
        # values for this 2 x 2 grid -- and the extractor reads around that
        # to the full grid the base class still holds, so the same answer is
        # expected everywhere. CI's Python 3.9 job, pinned to matplotlib
        # 3.9.4, is what exercises the older path.
        ("pcolor", lambda ax: ax.pcolor(np.ma.masked_invalid(HOLED))),
    ],
)
class TestACellWithNoValue:
    def test_it_is_emitted_as_null_rather_than_nan(self, name, draw):
        fig, ax = plt.subplots()
        draw(ax)

        assert _points(fig)[0][1] is None

    def test_the_measured_cells_are_untouched(self, name, draw):
        fig, ax = plt.subplots()
        draw(ax)

        points = _points(fig)

        assert points[0][0] == 1.0
        assert points[1] == [3.0, 4.0]

    def test_the_payload_is_loadable(self, name, draw):
        fig, ax = plt.subplots()
        draw(ax)

        _parses_as_strict_json(fig)


class TestAMaskedCell:
    def test_a_masked_heatmap_hides_what_the_caller_hid(self):
        # The idiom for half a correlation matrix. The artist's mask is the
        # authority on which cells were drawn; before this the extractor read
        # the buffer beneath it and announced the full symmetric matrix.
        fig, ax = plt.subplots()
        sns.heatmap(CORR, mask=np.triu(np.ones_like(CORR, dtype=bool)), ax=ax)

        assert _points(fig) == [
            [None, None, None],
            [0.5, None, None],
            [0.2, 0.3, None],
        ]
        _parses_as_strict_json(fig)

    def test_a_gap_lands_exactly_where_the_artist_is_masked(self):
        fig, ax = plt.subplots()
        sns.heatmap(CORR, mask=np.triu(np.ones_like(CORR, dtype=bool)), ax=ax)

        mask = np.ma.getmaskarray(ax.collections[0].get_array())
        gaps = np.array([[cell is None for cell in row] for row in _points(fig)])

        assert gaps.shape == mask.shape
        assert (gaps == mask).all()

    def test_a_masked_image_is_covered_too(self):
        fig, ax = plt.subplots()
        ax.imshow(np.ma.masked_where(CORR > 0.9, CORR))

        points = _points(fig)

        assert [row[i] for i, row in enumerate(points)] == [None, None, None]
        assert points[0][1] == 0.5
        _parses_as_strict_json(fig)

    def test_a_masked_integer_grid_still_serialises(self):
        # Pinned because it can break: a NaN needs a float to sit in, and
        # `ma.filled` refuses to write one into an integer grid.
        fig, ax = plt.subplots()
        ax.imshow(np.ma.masked_equal(np.array([[1, 2], [3, 0]]), 0))

        assert _points(fig) == [[1.0, 2.0], [3.0, None]]
        _parses_as_strict_json(fig)


class TestAnArrayThatDoesNotFitItsGrid:
    def test_it_is_left_unread_rather_than_raising_out_of_the_render(
        self, mocker, caplog
    ):
        # What the older `pcolor` did by accident, done on purpose to a mesh
        # of either kind: the values cannot be laid onto the grid, and the
        # answer is the `ExtractionError` a mesh with no array gets, not a
        # `ValueError` from `reshape` in the middle of a render.
        fig, ax = plt.subplots()
        mesh = ax.pcolormesh(HOLED)
        mocker.patch.object(mesh, "get_array", return_value=np.array([1.0, 3.0, 4.0]))
        plot = FigureManager.get_maidr(fig)._plots[0]

        with caplog.at_level(logging.DEBUG, logger="maidr.core.plot.heatmap"):
            with pytest.raises(ExtractionError):
                plot.render()

        assert "holds 3 values for a 2 x 2 grid" in caplog.text


class TestWhatMustNotChange:
    def test_a_grid_without_gaps_is_unchanged(self):
        fig, ax = plt.subplots()
        sns.heatmap(CORR, ax=ax)

        assert _points(fig) == CORR.tolist()

    @pytest.mark.parametrize(
        "grid",
        [
            np.random.default_rng(20260903).random((7, 5)),
            np.arange(12, dtype=np.int64).reshape(3, 4) - 5,
            np.arange(12, dtype=np.uint8).reshape(4, 3),
        ],
        ids=["float64", "int64", "uint8"],
    )
    def test_the_fast_path_emits_what_the_format_loop_did(self, grid):
        # The vectorised path exists to skip `float(format(x, ""))` per
        # cell, on the grounds that the two are the same number for these
        # dtypes. This is that claim, checked cell for cell.
        fig, ax = plt.subplots()
        ax.imshow(grid)

        expected = [[float(format(x, "")) for x in row] for row in grid]

        assert _points(fig) == expected

    def test_a_caller_format_is_still_applied(self):
        # `sns.heatmap(fmt=)` is what the per-cell loop is *for*: the values
        # are announced at the precision the caller annotated them with.
        fig, ax = plt.subplots()
        sns.heatmap(np.array([[1.234, 5.678]]), annot=True, fmt=".1f", ax=ax)

        assert _points(fig) == [[1.2, 5.7]]

    def test_a_zero_cell_is_still_a_reading(self):
        # The distinction the whole change exists to preserve. A zero cell
        # was measured; a gap was not.
        fig, ax = plt.subplots()
        ax.imshow(np.array([[0.0, 1.0]]))

        assert _points(fig)[0][0] == 0.0
        assert _points(fig)[0][0] is not None

    def test_a_boolean_grid_is_still_ones_and_zeros(self):
        # The `ax.spy()` case (#564), which the mask handling sits next to.
        fig, ax = plt.subplots()
        ax.spy(np.array([[1, 0], [0, 1]]))

        assert _points(fig) == [[1.0, 0.0], [0.0, 1.0]]
