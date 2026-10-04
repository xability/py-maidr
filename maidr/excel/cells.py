"""Cell ranges, as a chart's series formulas name them.

A series names its data with a formula such as ``Sales!$B$2:$B$5``; both
kinds of chart part, DrawingML and Excel 2016's, read it the same way, and
read no more points or cells than the limits here allow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterator

from maidr.excel.package import Cell, column_index

_REFERENCE = re.compile(
    r"^(?:'(?P<quoted>(?:[^']|'')+)'|(?P<plain>[^'!\[\]]+))!"
    r"\$?(?P<c1>[A-Za-z]{1,3})\$?(?P<r1>\d+)"
    r"(?::\$?(?P<c2>[A-Za-z]{1,3})\$?(?P<r2>\d+))?$"
)

#: The most points a series is read with: a sheet's row count. A part that
#: claims more is damaged, and is not allowed to ask for that much memory.
MAX_POINTS = 1_048_576
#: The most cells read for a series range the part has no copy of. Excel always
#: writes the copy; a larger uncached range reads as empty rather than scanning
#: the sheet for it.
MAX_UNCACHED = 100_000

#: ``(sheet, row, column)`` to the cell there, or ``None`` for an empty one.
Cells = Callable[[str, int, int], "Cell | None"]


@dataclass(frozen=True)
class Range:
    """A rectangular cell range on one sheet, zero-based and inclusive."""

    sheet: str
    first_row: int
    first_column: int
    last_row: int
    last_column: int

    def size(self) -> int:
        """How many cells the range holds."""
        rows = self.last_row - self.first_row + 1
        return rows * (self.last_column - self.first_column + 1)

    def positions(self) -> Iterator[tuple[int, int]]:
        """Each cell, row by row."""
        for row in range(self.first_row, self.last_row + 1):
            for column in range(self.first_column, self.last_column + 1):
                yield row, column

    def header(self) -> tuple[int, int] | None:
        """
        The cell that names this range: above a column of values, left of a
        row of them.
        """
        if self.first_row == self.last_row and self.last_column > self.first_column:
            if self.first_column == 0:
                return None
            return self.first_row, self.first_column - 1
        if self.first_row == 0:
            return None
        return self.first_row - 1, self.last_column


def parse_range(formula: str | None) -> Range | None:
    """
    The range a series formula names.

    Parameters
    ----------
    formula : str or None
        A formula such as ``Sales!$B$2:$B$5`` or ``'Q1 data'!$A$1``.

    Returns
    -------
    Range or None
        ``None`` for anything else: a defined name, a reference to another
        workbook, or several areas joined in parentheses.
    """
    if not formula:
        return None
    match = _REFERENCE.match(formula.strip())
    if match is None:
        return None
    sheet = match.group("plain") or match.group("quoted").replace("''", "'")
    r1, c1 = int(match.group("r1")) - 1, column_index(match.group("c1"))
    r2 = int(match.group("r2")) - 1 if match.group("r2") else r1
    c2 = column_index(match.group("c2")) if match.group("c2") else c1
    return Range(sheet, min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2))
