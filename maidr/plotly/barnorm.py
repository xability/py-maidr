"""Rescaling a stack to a common total, the way ``layout.barnorm`` draws it.

``barnorm`` tells plotly to rescale every stack position to a common total, so
the bars a reader sees are *shares of their position* rather than the numbers
in the data frame. The layer is typed ``stacked_normalized_bar`` for it, and
the values underneath were the untouched inputs -- the type and the values
contradicting each other (#409).

Every rule here was measured against ``gd.calcdata[i][j].s`` after
``Plotly.newPlot`` in Chromium rather than read from the documentation, and
two of them are not what the documentation would suggest. See
``stack_shares`` for the denominators.

The MAIDR core does not do this arithmetic for us, and that is the settled
convention rather than an oversight: ``SegmentedTrace`` handles ``stacked``,
``dodged`` and ``stacked_normalized_bar`` with one class and normalises
nothing, so a normalised layer is expected to arrive already carrying shares.
Both r-maidr paths do exactly that -- base R because the author normalised the
matrix before calling ``barplot()``, ggplot2 because ``position = "fill"``
builds its data in 0..1 -- which is what makes py-maidr's plotly path the
outlier rather than the standard-setter. Contrast ``AreaTrace``, which *does*
compute its own stack totals, and so is deliberately fed raw values.
"""

from __future__ import annotations

import math
from typing import Any, Hashable, Sequence

#: The values ``layout.barnorm`` takes when plotly rescales a stack. ``percent``
#: scales each position to 100 and ``fraction`` to 1; anything else -- ``None``,
#: ``""``, an unrecognised string -- leaves the bars alone.
_NORMALISING_BARNORMS: dict[str, float] = {"percent": 100.0, "fraction": 1.0}

#: The one barmode that pools positive and negative into a single stack. Every
#: other combining mode -- ``relative``, which is plotly's default and what
#: ``px.bar`` leaves behind -- stacks the two sides separately.
#:
#: Tested for equality rather than resolved against a default, and that is
#: deliberate: an unset ``barmode`` must take the ``relative`` branch, which
#: ``!= "stack"`` already gives. It agrees with
#: ``PlotlyMaidr._PLOTLY_DEFAULT_BARMODE``, which spells the same default the
#: other way round, only because these are the two states that reach here --
#: ``group`` never does, since a dodged layer is not ``NORMALIZED``. A third
#: combining mode would have to be added in both places, not just one.
_POOLED_BARMODE = "stack"


def barnorm_scale(barnorm: Any) -> float | None:
    """The multiplier a ``barnorm`` setting scales each position to.

    Parameters
    ----------
    barnorm : Any
        ``layout.barnorm``, which may be absent, empty or unrecognised.

    Returns
    -------
    float or None
        ``100.0`` for ``percent``, ``1.0`` for ``fraction``, and ``None``
        when plotly normalises nothing -- in which case the caller should
        emit the values unchanged rather than scaling by 1.
    """
    if not isinstance(barnorm, str):
        return None
    return _NORMALISING_BARNORMS.get(barnorm)


def _measured(value: Any) -> bool:
    """Whether a value takes part in a total.

    A ``None`` or non-finite entry is a gap: plotly leaves it out of the
    denominator and leaves it undefined in the output. Measured -- a stack of
    ``[None, 4]`` came back ``[None, 100]``, so the null neither contributed
    to the total nor became a zero share.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    return math.isfinite(value)


def stack_totals(
    series: Sequence[Sequence[tuple[Hashable, Any]]], barmode: Any
) -> dict[Hashable, dict[bool, float]]:
    """Sum each stack position, the way the active barmode stacks it.

    Two denominators, and which applies is the barmode's doing:

    ``relative`` -- plotly's default, and what ``px.bar`` leaves behind --
    draws the positive and negative bars as two stacks growing away from the
    baseline, and normalises each against its own total. So the denominator
    is the sum of the *absolute* values sharing a sign. Measured: ``[3, -1]``
    comes back ``100, -100``, not ``75, -25``.

    ``stack`` pools both signs into one stack, so the denominator is the
    absolute value of the signed sum, applied to every value at the position.
    Measured: ``[3, -1, 6]`` comes back ``37.5, -12.5, 75`` -- a denominator
    of 8. The absolute value is load-bearing rather than cosmetic: ``[0, -4]``
    comes back ``0, -100``, and a plain signed sum of ``-4`` would have made
    the second bar ``+100``.

    Zero counts as positive. It contributes nothing either way, but the group
    it lands in decides whether it gets a share or a gap: measured under
    ``relative``, ``[0, -4]`` gives ``None, -100`` -- the zero's own group
    totals zero, so its share is undefined, while under ``stack`` the same
    input gives ``0, -100`` because the pooled total is non-zero.

    Parameters
    ----------
    series : sequence of sequence of (hashable, Any)
        One sequence per series, each holding ``(position, value)`` pairs.
        Positions are matched by value, not by index, so a series that skips
        a position contributes nothing there rather than shifting the rest.
    barmode : Any
        ``layout.barmode``. Only ``stack`` pools the signs.

    Returns
    -------
    dict
        ``{position: {sign_is_negative: total}}``. Under ``stack`` every
        value is filed under ``False``, since one total serves both signs.
    """
    pooled = barmode == _POOLED_BARMODE
    totals: dict[Hashable, dict[bool, float]] = {}

    for one_series in series:
        for position, value in one_series:
            if not _measured(value):
                continue
            bucket = totals.setdefault(position, {})
            key = False if pooled else value < 0
            bucket[key] = bucket.get(key, 0.0) + (value if pooled else abs(value))

    if pooled:
        # Taken after summing, not per term: the pooled denominator is the
        # magnitude of the net stack height.
        for bucket in totals.values():
            for key, total in bucket.items():
                bucket[key] = abs(total)

    return totals


def stack_shares(
    series: Sequence[Sequence[tuple[Hashable, Any]]],
    barmode: Any,
    scale: float,
) -> list[list[float | None]]:
    """Rescale every value to its share of its stack position.

    Parameters
    ----------
    series : sequence of sequence of (hashable, Any)
        One sequence per series, each holding ``(position, value)`` pairs.
    barmode : Any
        ``layout.barmode``; see :func:`stack_totals` for what it changes.
    scale : float
        ``100.0`` or ``1.0``, from :func:`barnorm_scale`.

    Returns
    -------
    list of list of (float or None)
        The shares, aligned elementwise with *series*. ``None`` marks a
        position plotly leaves undefined -- either the value was already a
        gap, or its stack totals zero and the share would be ``0/0``.
        Measured: a category whose every segment is zero comes back with its
        ``x`` intact and ``s`` null, so the position survives and only the
        value is missing. The count of points never changes.
    """
    pooled = barmode == _POOLED_BARMODE
    totals = stack_totals(series, barmode)
    shares: list[list[float | None]] = []

    for one_series in series:
        row: list[float | None] = []
        for position, value in one_series:
            if not _measured(value):
                row.append(None)
                continue
            bucket = totals.get(position, {})
            total = bucket.get(False if pooled else value < 0)
            row.append(None if not total else value / total * scale)
        shares.append(row)

    return shares
