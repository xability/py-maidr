"""Group a layer's drawn things by the name each one was given."""

from __future__ import annotations


def grouped_by_name(
    names: list, order: list | None = None
) -> list[tuple[str, list[int]]] | None:
    """
    Turn one name per drawn thing into one group per distinct name.

    The tail every hue split ends in. What a chart is read *from* differs by
    artist -- a scatter has a face colour per point, a rug a colour per
    segment, a strip plot a plotter to consult outright -- but what happens
    after is the same three decisions every time, and they were made three
    times in three ways before this existed:

    - **A thing no name claims declines the whole split.** A partly-named
      chart announces a group called "None" holding the rest -- maidr's own
      word for "unmatched", read aloud as a level -- and is worse than an
      unnamed one. The case behind it is a continuous ``hue=``: measured on a
      scatter, ten points took ten distinct colours against five legend
      levels sampled at round numbers, so most points matched nothing. That
      is a colour *scale*, and one layer per point is not a reading of it.
    - **Fewer than two groups is not a grouping.** Nothing to tell apart.
    - **The groups come out in the order given**, which for every caller so
      far is the legend's rather than the draw order -- the convention #502
      settled. Stated as a parameter rather than assumed, because it is the
      half most likely to drift: the two callers reached it by different
      mechanisms before, one relying on a dict built in legend order and the
      other sorting against the legend's texts.

    A name the order does not mention sorts last, keeping its position
    among its fellows. That case is not reachable through either caller --
    both draw their names from the same legend they order by -- and is
    defined rather than left to chance so that a caller reading names from
    somewhere else gets a stated answer instead of an exception.

    Parameters
    ----------
    names : list
        One name per drawn thing, in drawing order. ``None`` anywhere
        declines.
    order : list, optional
        The names in the order the groups should come out in. Omitted, the
        groups keep the order their names first appear in.

    Returns
    -------
    list of (str, list of int) or None
        One entry per group, naming it and listing the positions that belong
        to it, or ``None`` when the names are not a grouping.

    Examples
    --------
    >>> grouped_by_name(["b", "a", "b"], ["a", "b"])
    [('a', [1]), ('b', [0, 2])]
    >>> grouped_by_name(["a", None, "b"]) is None
    True
    >>> grouped_by_name(["a", "a"]) is None
    True
    """
    if not names or any(name is None for name in names):
        return None

    members: dict[str, list[int]] = {}
    for index, name in enumerate(names):
        members.setdefault(name, []).append(index)
    if len(members) < 2:
        return None

    if not order:
        return list(members.items())

    return sorted(
        members.items(),
        key=lambda group: order.index(group[0]) if group[0] in order else len(order),
    )
