"""A contour's holes were read as holes; plotly fills them before tracing.

`maidr/plotly/contour.py` masked a missing point, on the reading that the
curves should stop at it the way plotly's do. Plotly does not stop there. It
runs `findEmpties` and `interp2d` over the grid first -- each hole becomes the
average of its orthogonal neighbours, relaxed until the field settles -- and
traces the curves *through* what was missing. Straight off `calcdata` in
Chromium, on a 5x5 field with its centre set to None:

```
contour                    -> z[2][2] = 0.6    _emptypoints = 1
heatmap                    -> z[2][2] = None   _emptypoints = null
heatmap, connectgaps=True  -> z[2][2] = 0.6    _emptypoints = 1
```

So it is a step contours take and heatmaps do not, and it was not visible in
the curve *counts*: on a 9x9 gaussian with one cell punched, both readings
find nine levels of one curve each. What moved was the curves. Sampling every
drawn path at 80 points and measuring each to the nearest segment of the
series announced with it:

```
                       worst gap (grid cells are 0.5 across)
whole field (control)  0.16   <- polyline against bezier, the floor
one cell punched       0.91   <- before
one cell punched       0.16   <- after
```

The rule is transcribed from the bundle this wheel ships rather than
approximated, because a near-miss puts the curves where neither library draws
them. Thirteen filled fields match plotly's own `calcdata` to 1e-9 -- single
holes, adjacent pairs, an L, a 2x2 block, a 4x4 block, a cross, a row with
only its ends left, holes at a corner and on an edge, and scatters of them
through ripples and through noise. See #651.
"""

from __future__ import annotations

import pytest

# `plotly` is an optional extra; guard it the way the rest of this directory
# does, so a minimal install skips rather than failing at collection.
pytest.importorskip("plotly")

import numpy as np  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from maidr.plotly.holes import _find_empties, filled  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402


def _punched(rows: int, columns: int, holes: list) -> np.ndarray:
    """A field of its own coordinates, with cells knocked out of it.

    Its own coordinates rather than a constant, so a hole filled from the
    wrong neighbours lands somewhere the assertions can see.
    """
    field = np.array(
        [[float(row * 10 + column) for column in range(columns)] for row in range(rows)]
    )
    for row, column in holes:
        field[row][column] = np.nan
    return field


class TestAHoleTakesItsNeighboursAverage:
    def test_one_hole_is_the_mean_of_its_four(self) -> None:
        """The plain case, and the one measured straight off `calcdata`.

        A 5x5 field whose centre is punched comes back from plotly holding
        0.6, which is what its four neighbours -- all 0.6 -- average to.
        """
        field = np.array(
            [
                [0.0, 0.1, 0.2, 0.1, 0.0],
                [0.1, 0.4, 0.6, 0.4, 0.1],
                [0.2, 0.6, np.nan, 0.6, 0.2],
                [0.1, 0.4, 0.6, 0.4, 0.1],
                [0.0, 0.1, 0.2, 0.1, 0.0],
            ]
        )

        assert filled(field)[2][2] == pytest.approx(0.6)

    def test_a_hole_reads_no_diagonals(self) -> None:
        """Four neighbours, not eight -- which the corners here would show.

        The field runs ``row * 10 + column``, so the hole at (1, 1) has
        orthogonal neighbours 1, 10, 12 and 21 (average 11) and diagonals 0,
        2, 20 and 22, which would pull it nowhere different on their own but
        would change the answer if they were counted alongside.
        """
        assert filled(_punched(3, 3, [(1, 1)]))[1][1] == pytest.approx(11.0)

    def test_a_hole_against_an_edge_averages_what_is_there(self) -> None:
        """Three neighbours, and the missing side is simply not counted.

        (0, 1) on the same ramp has 0, 2 and 11 beside it. Reading past the
        edge would wrap round to the far side of the field in Python, where
        plotly reads `undefined` and skips.
        """
        assert filled(_punched(3, 3, [(0, 1)]))[0][1] == pytest.approx(13 / 3)

    def test_a_field_with_no_holes_comes_back_unchanged(self) -> None:
        field = _punched(4, 4, [])

        assert np.array_equal(filled(field), field)

    def test_a_field_of_nothing_but_holes_has_nothing_to_fill_from(self) -> None:
        """Plotly's own pass raises rather than answers, so this declines."""
        assert filled(np.full((3, 3), np.nan)) is None

    def test_the_field_handed_in_is_not_written_over(self) -> None:
        """It is read again for the levels, and by whoever passed it."""
        field = _punched(3, 3, [(1, 1)])

        filled(field)

        assert np.isnan(field[1][1])


class TestTheOrderHolesAreFilledIn:
    """Not an implementation detail: a block of holes settles differently.

    Each hole is scored by how well surrounded it is -- filled orthogonal
    neighbours, plus one for each side of the grid it lies against -- and they
    are seeded best-first so that a hole is always reached after something it
    can average. Holes that touch only other holes take a second pass and get
    a twentieth of their neighbours' scores, which keeps them last without
    ever reaching four.

    Measured against plotly's own `_emptypoints` on a 4x4 block punched out
    of an 8x8 field: sixteen holes, the four corners of the block scoring 2,
    the twelve edges 1, and the four interior ones 0.1 -- in that order, and
    with the interior four in the order below rather than its reverse. That
    last part is not cosmetic: filling the far corner before the near one
    settles the block a thousandth away from where plotly settles it.
    """

    def test_the_scores_and_their_order_are_plotly_s(self) -> None:
        field = _punched(8, 8, [(row, column) for row in range(2, 6) for column in range(2, 6)])

        found = _find_empties([list(row) for row in field])

        assert [(row, column) for row, column, _ in found[:4]] == [
            (2, 2),
            (2, 5),
            (5, 2),
            (5, 5),
        ]
        assert {score for _, _, score in found[:4]} == {2.0}
        assert {score for _, _, score in found[4:12]} == {1.0}
        assert [(row, column) for row, column, _ in found[12:]] == [
            (4, 4),
            (4, 3),
            (3, 4),
            (3, 3),
        ]

    def test_a_hole_against_two_sides_scores_for_both(self) -> None:
        """A corner has two neighbours and two edges, so it scores four.

        Which puts it among the holes the relaxation leaves alone -- there is
        nothing on the other side of an edge to disagree with it.
        """
        found = _find_empties([list(row) for row in _punched(4, 4, [(0, 0)])])

        assert found == [(0, 0, 4.0)]


class TestTheCurvesRunThroughIt:
    """The reading, rather than the field -- which is what #651 was about."""

    #: A gaussian on a 9x9 grid, its peak at the middle. Rounded, so the
    #: numbers here are the numbers plotly is given.
    SMOOTH = np.round(
        np.exp(
            -(
                np.linspace(-2, 2, 9)[None, :] ** 2
                + np.linspace(-2, 2, 9)[:, None] ** 2
            )
        ),
        4,
    )

    def _curves(self, z: list) -> list[list[tuple[float, float]]]:
        figure = go.Figure(go.Contour(z=z, contours=dict(coloring="lines")))
        grid = PlotlyMaidr(figure)._flatten_maidr()["subplots"]
        layers = [layer for row in grid for cell in row for layer in cell["layers"]]
        return [
            [(point["x"], point["y"]) for point in series]
            for layer in layers
            for series in layer["data"]
        ]

    def test_a_punched_field_reads_as_the_field_with_the_hole_filled(self) -> None:
        """The point of the change, said in the emitted curves.

        One cell punched on the flank of the peak, where the neighbours
        disagree most. The hole has all four of them, so it is seeded at
        their mean and the relaxation leaves it there -- 0.645225 where the
        field held 0.7788. Reading the punched field is then exactly reading
        that one, curve for curve and point for point.

        Measured in the browser as well, since equality here would also hold
        for a fill nobody draws: sampling every drawn path at 80 points and
        measuring each to the nearest segment of the series announced with
        it, the punched field's worst gap is 0.16 data units -- the same
        floor the unpunched field gives, where masking gave 0.91 on a grid
        whose cells are 0.5 across.
        """
        punched = self.SMOOTH.tolist()
        punched[4][3] = None
        by_hand = self.SMOOTH.tolist()
        by_hand[4][3] = (
            self.SMOOTH[3][3]
            + self.SMOOTH[5][3]
            + self.SMOOTH[4][2]
            + self.SMOOTH[4][4]
        ) / 4

        assert self._curves(punched) == self._curves(by_hand)

    def test_and_not_as_the_field_it_was_punched_from(self) -> None:
        """Guards the assertion above against passing for the wrong reason.

        The hole is filled with an average, not with the value that was
        there, so the punched field is a different chart from the whole one
        -- and if it were not, the test above would hold however the hole
        were filled.
        """
        punched = self.SMOOTH.tolist()
        punched[4][3] = None

        assert self._curves(punched) != self._curves(self.SMOOTH.tolist())
