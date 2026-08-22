"""Tell a name a caller chose from one matplotlib gave itself."""

from __future__ import annotations

from typing import Any


def series_name(artist: Any) -> str:
    """
    Return the name to announce for ``artist``, or ``""`` if it has none.

    matplotlib labels every artist, whether or not the caller asked for a
    name, and reserves a leading underscore for the ones it made up. Its own
    legend builder is the definition: ``Legend`` skips any label starting with
    ``_``, so a label matplotlib would not show in a legend is not a name the
    caller chose either.

    Two spellings of that reach maidr. ``_child0``, ``_line2`` and friends are
    what an unlabelled artist gets. ``_nolegend_`` is what a caller passes to
    keep an artist out of the legend -- documented, and used by matplotlib
    itself: ``Axes.stem`` labels both its marker line and its baseline that
    way. Announcing either as the series name tells a reader the series is
    called ``_child0``.

    Matching matplotlib's rule rather than listing the two spellings is
    deliberate: the list is not closed (``_nolegend_`` is spelled
    ``_nolegend_`` only by convention, and new internal prefixes have
    appeared before), and a caller who wants a series named ``_x`` announced
    has no way to put it in a matplotlib legend either.

    Parameters
    ----------
    artist : Any
        Any matplotlib artist, or anything else with a ``get_label``.

    Returns
    -------
    str
        The caller's name for the artist, or ``""`` when matplotlib named it.
    """
    getter = getattr(artist, "get_label", None)
    if getter is None:
        return ""

    label = getter()
    if not isinstance(label, str) or label.startswith("_"):
        return ""

    return label
