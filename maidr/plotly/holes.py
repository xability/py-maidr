from __future__ import annotations

import math
from typing import Any

import numpy as np

#: How small the largest fractional change has to get before the relaxation
#: below stops, and how many passes it gets to reach it. Plotly's own
#: ``INTERPTHRESHOLD`` and loop bound; it logs and gives up at the hundredth
#: pass rather than iterating further.
_THRESHOLD = 0.01
_PASSES = 100

#: The four cells a missing one takes its value from. Orthogonal only --
#: plotly does not read the diagonals.
_NEIGHBOURS = ((-1, 0), (1, 0), (0, -1), (0, 1))

#: What the "no neighbours of my own yet" pass divides its score by, to keep a
#: hole reached only through other holes below the ones reached directly.
_SECOND_HAND = 20


def filled(z: np.ndarray) -> np.ndarray | None:
    """Return the field with its holes filled, the way plotly fills them.

    A missing point in a ``contour``'s ``z`` is not a hole in the chart:
    plotly runs ``findEmpties`` and ``interp2d`` over the grid before tracing
    it, so the curves run *through* what was missing. Measured off
    ``calcdata`` in Chromium -- a 5x5 field with its centre cell set to None
    comes back with 0.6 in it, and ``_emptypoints`` counting the one it
    filled. A ``go.Heatmap`` given the same field keeps its None, and keeps
    it until asked for ``connectgaps``, so this is a step contours take and
    heatmaps do not.

    Reading the hole as a hole instead is not a small difference. On a 9x9
    gaussian with one cell punched on the flank of the peak, the curve counts
    still agree with plotly level for level -- and the curves themselves move
    by up to 0.91 data units on a grid whose cells are 0.5 across, against a
    0.16 sampling floor measured on the same field unpunched. A reader
    tracing near the hole is told about ground the chart draws no curve
    through (#651).

    The rule is plotly's, transcribed rather than approximated, because a
    near-miss puts the curves somewhere neither library draws them.

    Parameters
    ----------
    z : numpy.ndarray
        The field, with NaN where a point is missing. Not modified.

    Returns
    -------
    numpy.ndarray or None
        A copy with the missing points filled, or None when there is nothing
        to fill them from -- a field of nothing but holes, which plotly's own
        pass raises on rather than answers.
    """
    field = np.asarray(z, dtype=float)
    if not np.isnan(field).any():
        return np.array(field)
    if np.isnan(field).all():
        return None

    # The working copy, and the reason the field handed in survives: nothing
    # below writes through to it. It is read again for the levels, which take
    # their range from the values that were actually there.
    grid = [list(row) for row in field]
    empties = _find_empties(grid)

    # One pass to give every hole a starting value, then the relaxation --
    # which the holes with all four neighbours already sit still for, so
    # plotly drops them from it. They are first in the list, since it is
    # sorted by neighbour count.
    _iterate(grid, empties)
    settled = next(
        (index for index, empty in enumerate(empties) if empty[2] < 4), len(empties)
    )
    unsettled = empties[settled:]

    change = 1.0
    for _ in range(_PASSES):
        if change <= _THRESHOLD:
            break
        change = _iterate(grid, unsettled, _overshoot(change))

    return np.array(grid, dtype=float)


def _overshoot(change: float) -> float:
    """How far past the neighbours' average to push, given the last pass.

    Plotly's ``correctionOvershoot``: a relaxation factor that starts near a
    half and eases off as the field settles.
    """
    return 0.5 - 0.25 * min(1.0, change * 0.5)


def _iterate(
    grid: list[list[float]], empties: list[tuple[int, int, float]], overshoot: float = 0.0
) -> float:
    """Move every hole to its neighbours' average, and report the largest move.

    The move is reported as a fraction of the spread among those neighbours,
    so a field of large numbers and a field of small ones settle at the same
    point. A hole being filled for the first time has no previous value to
    overshoot from, and answers "not settled" when it had fewer than four
    neighbours to average.

    ``overshoot`` is unused on the seeding pass and defaults accordingly:
    every hole is still empty when that pass reaches it, so the branch that
    reads it cannot be taken.
    """
    change = 0.0
    rows = len(grid)
    for row_index, column_index, _ in empties:
        previous = grid[row_index][column_index]
        total = 0.0
        count = 0
        low = high = 0.0
        for row_shift, column_shift in _NEIGHBOURS:
            row = row_index + row_shift
            column = column_index + column_shift
            if not 0 <= row < rows or not 0 <= column < len(grid[row]):
                continue
            value = grid[row][column]
            if math.isnan(value):
                continue
            # Seeded off the running total rather than the count, which is
            # what plotly does -- and it is not the same test: a first
            # neighbour of zero leaves the pair to be seeded again by the
            # second. Transcribed rather than corrected, because the spread
            # it feeds only decides how quickly the relaxation stops.
            if total == 0:
                low = high = value
            else:
                low = min(low, value)
                high = max(high, value)
            count += 1
            total += value

        if count == 0:  # pragma: no cover - `_find_empties` orders them away
            return change

        grid[row_index][column_index] = total / count
        if math.isnan(previous):
            if count < 4:
                change = 1.0
        else:
            grid[row_index][column_index] = (1 + overshoot) * grid[row_index][
                column_index
            ] - overshoot * previous
            if high > low:
                moved = abs(grid[row_index][column_index] - previous) / (high - low)
                change = max(change, moved)
    return change


def _find_empties(grid: list[list[float]]) -> list[tuple[int, int, float]]:
    """Every hole, with a score for how well surrounded it is, best first.

    The score counts a hole's filled orthogonal neighbours and adds one for
    each side of the grid it lies against -- an edge being as good as a
    neighbour, since there is nothing beyond it to disagree with. Holes with
    fewer than four then take a second pass for the sake of holes that touch
    only *them*: those get a fraction of their neighbours' scores, which
    keeps them behind in the ordering without ever reaching four.

    Order is the whole point of the function. :func:`filled` seeds in this
    order so that a hole is always reached after something it can average,
    and cuts the relaxation at the first score below four.
    """
    rows = len(grid)
    width = max((len(row) for row in grid), default=0)
    empties: list[tuple[int, int, float]] = []
    scored: dict[tuple[int, int], float] = {}
    unreached: list[tuple[int, int]] = []

    for row_index in range(rows):
        row = grid[row_index]
        above = grid[row_index - 1] if row_index else []
        below = grid[row_index + 1] if row_index + 1 < rows else []
        for column_index in range(width):
            if not math.isnan(_at(row, column_index)):
                continue
            score = float(
                (not math.isnan(_at(row, column_index - 1)))
                + (not math.isnan(_at(row, column_index + 1)))
                + (not math.isnan(_at(above, column_index)))
                + (not math.isnan(_at(below, column_index)))
            )
            if not score:
                unreached.append((row_index, column_index))
                continue
            score += float(
                (row_index == 0)
                + (column_index == 0)
                + (row_index == rows - 1)
                + (column_index == len(row) - 1)
            )
            if score < 4:
                scored[(row_index, column_index)] = score
            empties.append((row_index, column_index, score))

    while unreached:
        found: dict[tuple[int, int], float] = {}
        # Walked backwards, because plotly walks it backwards -- it removes
        # each match as it goes, which a forward walk cannot do safely, and
        # the holes it finds are appended in the order the walk met them. On
        # a square block of holes that is the difference between filling the
        # far corner first and the near one, and the two settle a thousandth
        # apart.
        for row_index, column_index in reversed(unreached):
            score = (
                scored.get((row_index - 1, column_index), 0.0)
                + scored.get((row_index + 1, column_index), 0.0)
                + scored.get((row_index, column_index - 1), 0.0)
                + scored.get((row_index, column_index + 1), 0.0)
            ) / _SECOND_HAND
            if score:
                found[(row_index, column_index)] = score
        if not found:  # pragma: no cover - `filled` declines an all-hole field
            break
        unreached = [cell for cell in unreached if cell not in found]
        for (row_index, column_index), score in found.items():
            scored[(row_index, column_index)] = score
            empties.append((row_index, column_index, score))

    # Stable, so holes of equal standing keep the order they were found in --
    # which is the order plotly's own sort leaves them in.
    return sorted(empties, key=lambda empty: empty[2], reverse=True)


def _at(row: Any, index: int) -> float:
    """One cell of a row, or NaN where there is no cell there.

    Plotly reads past the ends of its rows and gets ``undefined``, which its
    tests for a filled neighbour answer no to. Python would wrap a negative
    index around to the far end instead, and read a neighbour from the other
    side of the field.
    """
    if index < 0 or index >= len(row):
        return math.nan
    return float(row[index])
