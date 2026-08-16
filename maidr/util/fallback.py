"""The static-image fallback, shared by every entry point that can need it.

A figure maidr never registered used to behave two completely different ways
depending on which door the user went through. ``plt.show()`` warned and
rendered a static image; ``maidr.render()``, ``maidr.show()`` and
``maidr.save_html()`` raised ``KeyError: 'No MAIDR found for figure'`` (#443).

The graceful path existed and worked -- it was just wired into the matplotlib
backend and nothing else, so the three functions a user is actually told to
call were the ones that crashed. For an accessibility library that is the
wrong way round: the user who explicitly asked for accessible output was the
one who got nothing.

This module holds the pieces both paths need, so they cannot drift: the
warning, and the image. It is what ``r-maidr`` does through every one of its
entry points, and what ``plt.show()`` here already did through one.
"""

from __future__ import annotations

import base64
import io
import warnings

from htmltools import HTML, Tag, TagList, div, img, p
from matplotlib.figure import Figure

from maidr.exception.unsupported_plot_error import UnsupportedPlotError


def warn_unsupported(
    source: Figure | UnsupportedPlotError, *, stacklevel: int
) -> UnsupportedPlotError:
    """
    Warn that a figure cannot be described, and say why.

    Parameters
    ----------
    source : Figure or UnsupportedPlotError
        The figure with no MAIDR instance, or an error already describing it.
        Both are accepted because the two callers arrive differently: the
        backend has only a figure, while the API entry points are inside an
        ``except`` block and already hold the error. Passing the error avoids
        re-walking the figure's artist lists to re-decide something already
        decided.
    stacklevel : int
        Passed to :func:`warnings.warn`. Keyword-only because it counts frames
        through a call chain that differs per caller, so a positional value
        silently attributed the warning to the wrong line when a caller moved.

    Returns
    -------
    UnsupportedPlotError
        The error describing the figure, in case the caller wants to raise it
        rather than continue. The warning and the exception therefore always
        carry the same sentence.
    """
    error = (
        source
        if isinstance(source, UnsupportedPlotError)
        else UnsupportedPlotError(source)
    )
    warnings.warn(
        f"{error.message} Falling back to static image.",
        stacklevel=stacklevel,
    )
    return error


def fallback_png(fig: Figure) -> bytes:
    """
    Render ``fig`` to PNG bytes.

    Parameters
    ----------
    fig : Figure
        The figure to rasterise.

    Returns
    -------
    bytes
        The encoded image, at the same dpi and cropping the backend's own
        fallback uses, so the two produce the same picture.
    """
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=150, bbox_inches="tight")
    return buffer.getvalue()


def fallback_tag(fig: Figure, message: str) -> Tag:
    """
    Build the HTML a caller returns in place of an accessible chart.

    The message is rendered *into the page* rather than only warned to the
    console. A warning is seen by whoever ran the code; the HTML is what
    reaches everyone afterwards, and a reader who meets a bare image has no
    way to know an accessible version was expected and did not happen.

    Parameters
    ----------
    fig : Figure
        The figure to embed.
    message : str
        The sentence explaining why this is an image, taken from
        :attr:`UnsupportedPlotError.message` so it matches the warning.

    Returns
    -------
    Tag
        A ``<div>`` holding the note and the image. ``alt`` repeats the note,
        because the image is exactly the thing a screen reader cannot read and
        an empty ``alt`` would present it as decoration.
    """
    encoded = base64.b64encode(fallback_png(fig)).decode("ascii")
    return div(
        TagList(
            p(HTML(message), class_="maidr-fallback-message"),
            img(
                src=f"data:image/png;base64,{encoded}",
                alt=message,
                style="max-width: 100%;",
            ),
        ),
        class_="maidr-fallback",
    )
