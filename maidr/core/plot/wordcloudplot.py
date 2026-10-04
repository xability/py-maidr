from __future__ import annotations

import uuid
from typing import Any

from matplotlib.axes import Axes
from matplotlib.image import AxesImage
from matplotlib.patches import Rectangle

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

    Recognized **structurally** rather than with ``isinstance``. ``wordcloud``
    is not a dependency of py-maidr and need not be installed, so importing it
    here to test against would either make it one or make this patch's
    behavior depend on an unrelated import having happened. ``words_`` is
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


#: How each term's box is styled in the SVG maidr.js reads.
#:
#: maidr.js highlights an element by painting a copy of it and leaves the
#: element itself as it was drawn, so the box on the page is hidden
#: (``visibility="hidden"``, which the copy turns back to visible) and only
#: the copy is ever seen. The rest is for that copy:
#:
#: - the fill is all but transparent, so the word reads through it. Not
#:   zero, because maidr.js raises a fill opacity at or below 0.01 to fully
#:   opaque -- a highlight is never invisible -- and a fill of zero would
#:   come back as a solid block over the word it points at;
#: - the stroke is opaque, so the highlight is an outline round the word;
#: - both are black, because maidr.js derives the highlight from the fill:
#:   a light fill is darkened a step, which on a white cloud gave a pale grey
#:   outline barely set off from the page, while a dark one gets the
#:   reader's own highlight color from the settings.
BOX_STYLE = "fill: #000000; fill-opacity: 0.02; stroke: #000000; stroke-width: 2"


def glyph_boxes(cloud: Any, image: AxesImage) -> list[tuple] | None:
    """
    Where each term of a cloud was drawn, in the data coordinates of its image.

    ``layout_`` records each placement as ``((term, weight), font_size,
    (row, col), orientation, color)``, and ``WordCloud.to_image`` draws each
    with ``ImageDraw.text`` at that position, scaled by ``cloud.scale``. The
    box is measured with the same font, size, rotation and position, so it is
    the box PIL itself would draw into.

    ``repeat=True`` places a term more than once; the first placement is the
    heaviest one, and the one a reader would look for. A term in ``words_``
    the packer could not fit at ``min_font_size`` has no placement at all:
    then there is nothing to point at for it, and maidr.js would pair every
    later term with the wrong box, so no box is returned for any of them.

    Parameters
    ----------
    cloud : Any
        The ``wordcloud.WordCloud`` being shown.
    image : AxesImage
        What ``imshow`` returned for it.

    Returns
    -------
    list of tuple or None
        ``(x, y, width, height)`` per term, in ``words_`` order, or None when
        a term was not drawn or the cloud cannot be measured.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont

        placed: dict = {}
        for (term, _), font_size, position, orientation, _ in cloud.layout_:
            placed.setdefault(term, (font_size, position, orientation))

        shape = image.get_array().shape
        height, width = shape[0], shape[1]
        left, right, bottom, top = image.get_extent()
        first_row, last_row = (
            (top, bottom) if image.origin == "upper" else (bottom, top)
        )

        draw = ImageDraw.Draw(Image.new("1", (1, 1)))
        scale = cloud.scale
        boxes = []
        for term in cloud.words_:
            if term not in placed:
                return None
            font_size, position, orientation = placed[term]
            font = ImageFont.TransposedFont(
                ImageFont.truetype(cloud.font_path, int(font_size * scale)),
                orientation=orientation,
            )
            origin = (int(position[1] * scale), int(position[0] * scale))
            x0, y0, x1, y1 = draw.textbbox(origin, term, font=font)

            data_x0 = left + x0 * (right - left) / width
            data_x1 = left + x1 * (right - left) / width
            data_y0 = first_row + y0 * (last_row - first_row) / height
            data_y1 = first_row + y1 * (last_row - first_row) / height
            boxes.append(
                (
                    min(data_x0, data_x1),
                    min(data_y0, data_y1),
                    abs(data_x1 - data_x0),
                    abs(data_y1 - data_y0),
                )
            )
        return boxes
    except Exception:
        # A cloud built by a version of `wordcloud` that lays out differently,
        # or a font that is gone: the reading stands without a highlight.
        return None


class WordCloudPlot(MaidrPlot):
    """
    A MAIDR layer for a ``wordcloud.WordCloud`` shown with ``Axes.imshow``.

    A word cloud is the chart that carries real data while being readable
    only by eye: each term's weight is drawn as glyph size and written down
    nowhere. Structurally it is a categorical label and a magnitude, so the
    reading is a term and its number.

    **The weights are relative, and the axis label says so.** ``WordCloud``
    normalizes by the largest frequency in
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
    honors ``max_words``.

    **Highlighted through a box per term, not through the glyphs.**
    ``imshow`` rasterises the whole cloud into one ``<image>`` element, so
    there is no per-term element in what the cloud itself draws. Each term
    is given one instead: a rectangle over the box PIL drew the term into
    (:func:`glyph_boxes`), carrying its own gid. It draws nothing, and in the
    SVG it is hidden (:meth:`finish_svg`); maidr.js outlines it as the reader
    moves, and the word stays legible inside the outline. When a term was
    never placed, there is no box to give it, and the layer carries no
    selectors at all -- the core pairs selectors with terms by position, so
    one gap would put every later highlight on the wrong word.

    Parameters
    ----------
    ax : Axes
        The axes the cloud was shown on.
    **kwargs
        ``cloud``, the object the patch saw being shown.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        self._cloud = kwargs.pop("cloud", None)
        image = kwargs.pop("image", None)
        super().__init__(ax, PlotType.WORD_CLOUD)

        # Made once, here, rather than on each render: a render can happen
        # several times, and each would add another set of boxes to the axes.
        self._boxes = self._draw_boxes(image) if image is not None else []

        # Without a box per term, no selector can name a term. Left on, the
        # base class emits its generic `g[maidr='true'] > path`, which is
        # worse than nothing: the core resolves whatever that matches and
        # pairs it with the terms positionally, so a figure whose *other*
        # layer happens to draw as many paths as this cloud has terms would
        # light up that layer's marks while this one is read.
        self._support_highlighting = bool(self._boxes)

    def _draw_boxes(self, image: AxesImage) -> list[Rectangle]:
        """
        Put an undrawn rectangle over each term, for maidr.js to outline.

        Parameters
        ----------
        image : AxesImage
            What ``imshow`` returned for the cloud.

        Returns
        -------
        list of Rectangle
            One per term in ``words_`` order, or empty when the terms could
            not all be measured.
        """
        boxes = glyph_boxes(self._cloud, image) if self._cloud is not None else None
        if not boxes:
            return []

        rectangles = []
        for x, y, width, height in boxes:
            # Nothing drawn, in any backend: a `savefig` to PNG shows the
            # cloud and nothing else. `finish_svg` styles the box, and only
            # in the SVG maidr.js reads.
            rectangle = Rectangle(
                (x, y), width, height, facecolor="none", edgecolor="none"
            )
            rectangle.set_gid(f"maidr-{uuid.uuid4()}")
            self.ax.add_patch(rectangle)
            rectangles.append(rectangle)
        return rectangles

    def finish_svg(self, tree) -> None:
        """
        Style each term's box for maidr.js to outline, hidden until it does.

        See :data:`BOX_STYLE`. Matplotlib has no way to write either the
        ``visibility`` attribute or a style for an element nothing draws, so
        both are set on what it wrote.

        Parameters
        ----------
        tree : lxml.etree._Element
            The rendered SVG, modified in place.
        """
        for box in self._boxes:
            for path in tree.xpath(
                "//*[local-name()='g'][@id=$gid]/*[local-name()='path']",
                gid=box.get_gid(),
            ):
                path.set("visibility", "hidden")
                path.set("style", BOX_STYLE)

    def _get_selector(self) -> list[str]:
        """
        One selector per term, in the order the terms are emitted.

        Returns
        -------
        list of str
            The selector of each term's box.
        """
        return [f"g[id='{box.get_gid()}'] > path" for box in self._boxes]

    def _extract_axes_data(self) -> dict:
        """
        Name the two dimensions of a term.

        A cloud has no x or y scale -- the glyph positions are packing, not
        data -- so the axes name what a point *holds* rather than where it
        sits, the way :class:`~maidr.core.plot.pieplot.PiePlot` does. An
        author who labeled the axes has already named them; otherwise the
        base class's generic "X"/"Y" would be read out against every term.

        The shared-label fallback is the rest of that pattern: one cloud per
        group on a facet grid carries its label on the shared outer axes
        rather than on its own, so asking only ``self.ax`` would fall through
        to the generic name for a figure that was labeled.

        Returns
        -------
        dict
            ``{"x": {"label": ...}, "y": {"label": ...}}``.
        """
        x_label = self.ax.get_xlabel()
        if not x_label:
            x_label = self.extract_shared_xlabel(self.ax)
        if not x_label:
            x_label = TERM_LABEL

        y_label = self.ax.get_ylabel()
        if not y_label:
            y_label = self.extract_shared_ylabel(self.ax)
        if not y_label:
            y_label = WEIGHT_LABEL

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
        right -- but it is the order :meth:`_get_selector` names the boxes
        in, and the core pairs the two by position.

        Returns
        -------
        list of dict
            One ``{"x": term, "y": weight}`` point per term.

        Raises
        ------
        ExtractionError
            If the layer was built without a cloud to read. Unlike an empty
            pie, an empty cloud is not a legal chart someone drew: ``words_``
            is non-empty by the time :func:`cloud_shown` recognizes one, so
            reaching here with nothing means the layer and its artist came
            apart.
        """
        words = getattr(self._cloud, "words_", None)
        if not isinstance(words, dict) or not words:
            raise ExtractionError(self.type, self.ax)

        self._elements.extend(self._boxes)
        return [
            {MaidrKey.X: str(term), MaidrKey.Y: float(weight)}
            for term, weight in words.items()
        ]
