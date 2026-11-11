"""The text a figure draws, as distinct from the text it holds."""

from __future__ import annotations

from typing import Optional

from matplotlib.text import Text


def drawn_text(text: Optional[Text]) -> str:
    """
    The string a text artist draws, or the empty string when it draws none.

    A title hidden with ``set_visible(False)`` keeps its string, and
    ``Axes.get_title()`` and ``Figure.get_suptitle()`` return it as readily
    as a drawn one, so a reader was told a title the chart does not show:
    the legacy candlestick example titles its volume axes "Volume Chart" and
    hides it, and the volume layer was read as "Volume Chart".

    Parameters
    ----------
    text : matplotlib.text.Text or None
        The artist, or ``None`` where the figure has not made one, as
        ``Figure._suptitle`` is until ``suptitle`` is called.

    Returns
    -------
    str
        The artist's text when it is visible, otherwise ``""``.
    """
    if text is None or not text.get_visible():
        return ""
    return text.get_text()
