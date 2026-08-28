from __future__ import annotations

from typing import Any

from matplotlib.axes import Axes

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.plot import MaidrPlot
from maidr.exception import ExtractionError

#: What the terms are called when the axes does not name them.
TERM_LABEL = "Term"

#: What the weights are called when the axes does not name them.
#:
#: Not "Occurrences", which is what the core's own example uses and what a
#: reader would take a count to mean. ``WordCloud`` divides every frequency
#: by the largest one and keeps only the ratio, so the heaviest term is
#: always exactly ``1.0`` and the rest are fractions of it. Announcing those
#: under a count's name would hand a reader "machine, 1.0" for a term that
#: occurred 412 times.
WEIGHT_LABEL = "Relative frequency"


def cloud_shown(args: tuple, kwargs: dict) -> Any | None:
    """
    The word cloud an ``Axes.imshow`` call is displaying, if it is showing one.

    Recognised **structurally** rather than with ``isinstance``. ``wordcloud``
    is not a dependency of py-maidr and need not be installed, so importing it
    here to test against would either make it one or make this patch's
    behaviour depend on an unrelated import having happened. ``words_`` is
    specific enough on its own: it is a non-empty mapping of term to weight,
    on an object being handed to ``imshow``.

    Parameters
    ----------
    args : tuple
        The positional arguments of the ``Axes.imshow`` call.
    kwargs : dict
        Its keyword arguments.

    Returns
    -------
    Any or None
        The object being shown when it carries a word cloud's terms, else
        None.
    """
    image = kwargs["X"] if "X" in kwargs else (args[0] if args else None)
    words = getattr(image, "words_", None)

    if not isinstance(words, dict) or not words:
        return None
    return image


class WordCloudPlot(MaidrPlot):
    """
    A MAIDR layer for a ``wordcloud.WordCloud`` shown with ``Axes.imshow``.

    A word cloud is the chart that carries real data while being readable
    only by eye: each term's weight is drawn as glyph size and written down
    nowhere. Structurally it is a categorical label and a magnitude, so the
    reading is a term and its number.

    **The weights are relative, and the axis label says so.** ``WordCloud``
    normalises by the largest frequency in
    ``generate_from_frequencies`` and keeps only the ratio -- measured, the
    counts ``{machine: 412, learning: 300, data: 250}`` come back as
    ``{machine: 1.0, learning: 0.728, data: 0.607}``, and the raw counts are
    on no attribute of the object. That is not a loss this layer can repair,
    and it is also what the chart draws: glyph size is proportional to the
    ratio, so a reader hearing 1.0 and 0.728 hears what a sighted reader
    sees. Naming the axis "Relative frequency" is what keeps that honest.

    **Read from ``words_``, not ``layout_``.** ``layout_`` is the placement
    list, and with ``repeat=True`` it lists a term once per placement --
    measured, a two-term cloud came back as
    ``[(alpha, 1.0), (beta, 0.667), (alpha, 0.667), (beta, 0.444)]``. Reading
    that would announce alpha twice, at two different weights, when the
    repetition is the packer filling space rather than anything in the data.
    ``words_`` is keyed by term, so it cannot repeat one, and it already
    honours ``max_words``.

    **No selectors.** ``imshow`` rasterises the whole cloud into one
    ``<image>`` element; there is no per-term element to point at, so this
    layer carries no highlight. The core handles a layer without selectors --
    ``WordCloudTrace`` returns no highlight rather than a wrong one.

    Parameters
    ----------
    ax : Axes
        The axes the cloud was shown on.
    **kwargs
        ``cloud``, the object the patch saw being shown.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        self._cloud = kwargs.pop("cloud", None)
        super().__init__(ax, PlotType.WORD_CLOUD)

        # No per-term element exists, so no selector can name one. Left on,
        # the base class emits its generic `g[maidr='true'] > path`, which is
        # worse than nothing: the core resolves whatever that matches and
        # pairs it with the terms positionally, so a figure whose *other*
        # layer happens to draw as many paths as this cloud has terms would
        # light up that layer's marks while this one is read.
        self._support_highlighting = False

    def _extract_axes_data(self) -> dict:
        """
        Name the two dimensions of a term.

        A cloud has no x or y scale -- the glyph positions are packing, not
        data -- so the axes name what a point *holds* rather than where it
        sits, the way :class:`~maidr.core.plot.pieplot.PiePlot` does. An
        author who labelled the axes has already named them; otherwise the
        base class's generic "X"/"Y" would be read out against every term.

        Returns
        -------
        dict
            ``{"x": {"label": ...}, "y": {"label": ...}}``.
        """
        x_label = self.ax.get_xlabel() or TERM_LABEL
        y_label = self.ax.get_ylabel() or WEIGHT_LABEL

        return {
            MaidrKey.X: self._axis_config(label=x_label),
            MaidrKey.Y: self._axis_config(label=y_label),
        }

    def _extract_plot_data(self) -> list:
        """
        Read the cloud's terms as a flat row of ``{x, y}`` points.

        Emitted in ``words_``'s own order, which is descending weight. The
        core sorts again for navigation and carries each term's authored
        index alongside, so the order here is not what makes the reading
        right -- but emitting the drawn order keeps the two in step for any
        producer that later gains selectors.

        Returns
        -------
        list of dict
            One ``{"x": term, "y": weight}`` point per term.

        Raises
        ------
        ExtractionError
            If the layer was built without a cloud to read. Unlike an empty
            pie, an empty cloud is not a legal chart someone drew: ``words_``
            is non-empty by the time :func:`cloud_shown` recognises one, so
            reaching here with nothing means the layer and its artist came
            apart.
        """
        words = getattr(self._cloud, "words_", None)
        if not isinstance(words, dict) or not words:
            raise ExtractionError(self.type, self.ax)

        return [
            {MaidrKey.X: str(term), MaidrKey.Y: float(weight)}
            for term, weight in words.items()
        ]
