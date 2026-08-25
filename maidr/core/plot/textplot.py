"""Read a ``so.Text`` mark as the labelled scatter it draws."""

from __future__ import annotations

import math
import uuid
from typing import List, Sequence

from matplotlib.axes import Axes
from matplotlib.text import Text

from maidr.core.enum import MaidrKey
from maidr.core.plot.scatterplot import ScatterPlot
from maidr.exception import ExtractionError

#: The keyword the drawn labels are handed over under.
DRAWN_LABELS = "labels"


class TextPlot(ScatterPlot):
    """
    One observation per label, read off where the label was written.

    ``so.Text()`` writes a string at each observation instead of drawing a
    marker there, which is the mark Observable's ``Plot.text`` is and the
    shape xability/maidr#1106 added ``ScatterPoint.label`` for: a chart where
    the point's **identity** is the payload rather than a decoration. A
    reader told "x is 3, y is 14.1" has been given the two numbers and
    withheld the one thing the chart was drawn to show.

    It is the last mark #670 left, and the only one that draws no artist any
    other reading's holder names. Measured on ``seaborn 0.13.2``, twelve
    observations::

        ax.lines        []
        ax.collections  []
        ax.patches      []
        ax.texts        12 Text artists, 'a' at (8.0, 5.12), ...

    So the layer is read from ``Axes.texts``, which ``_held`` reaches by name
    like any other holder -- no new mechanism, one more entry in the table.

    **A label with nothing in it is not a point.** ``so.Text()`` written
    without a ``text=`` variable still draws one artist per observation, each
    with an empty string -- measured, twelve of them. Nothing is on the page,
    and announcing twelve positions for marks a sighted reader cannot see
    would describe a chart that is not there. Such a layer is declined.

    Parameters
    ----------
    ax : Axes
        The panel drawn on.
    **kwargs : dict
        Carries the artists under :data:`DRAWN_LABELS`, and whatever the
        factory forwards.
    """

    def __init__(self, ax: Axes, **kwargs) -> None:
        self._labels: Sequence[Text] = kwargs.pop(DRAWN_LABELS)
        # Which of the handed-over artists the payload announces, in payload
        # order. Filled by `_extract_plot_data`; empty here so a layer asked
        # for its selectors before its data returns none rather than raising.
        self._drawn: List[int] = []
        super().__init__(ax, **kwargs)

    def _extract_plot_data(self) -> list[dict]:
        """
        One sample per written label, in the order the axes holds them.

        Returns
        -------
        list of dict
            One point per label, carrying its text.

        Raises
        ------
        ExtractionError
            When no label carries a string, which is what a ``so.Text()``
            written with no ``text=`` variable leaves behind.
        """
        x_ticks = self._category_tick_labels(self.ax, "x")
        y_ticks = self._category_tick_labels(self.ax, "y")

        samples: list[dict] = []
        self._drawn = []
        for position, artist in enumerate(self._labels):
            written = artist.get_text()
            if not written:
                continue
            x, y = artist.get_position()
            # A label at no coordinate has nowhere to be announced, and
            # `json.dumps` writes `NaN` as a bare token, which is legal
            # JavaScript and invalid JSON -- one of them stops the chart
            # initialising at all (#427).
            if not (math.isfinite(float(x)) and math.isfinite(float(y))):
                continue
            sample = self._sample(float(x), float(y), x_ticks, y_ticks)
            sample[MaidrKey.LABEL] = written
            samples.append(sample)
            self._drawn.append(position)

        if not samples:
            raise ExtractionError(self.type, self.ax)
        return samples

    def _get_selector(self) -> List[str]:
        """
        One selector per announced label, addressing its own group.

        matplotlib writes each ``Text`` as a group of its own, so a label has
        an element to name -- unlike the outline shapes
        :class:`~maidr.core.plot.stepped_histogram.SteppedHistPlot` declines
        highlighting for. The gid is assigned here for the reason
        :class:`~maidr.core.plot.intervalplot.IntervalPlot` gives: matplotlib
        stamps one at *draw* time and the schema is built first, so reading it
        would find ``None`` and the layer would ship with an empty list.

        Numbered against the **written** labels rather than the announced
        ones, so a layer holding a blank this declines keeps every later
        label pointing at its own element.

        Returns
        -------
        list of str
            One selector per announced label, in payload order.
        """
        selectors: list[str] = []
        for position in self._drawn:
            artist = self._labels[position]
            gid = artist.get_gid()
            if not gid or not str(gid).startswith("maidr-"):
                gid = f"maidr-{uuid.uuid4()}"
                artist.set_gid(gid)
            selectors.append(f"g[id='{gid}']")
        return selectors


def reads(labels: Sequence[Text]) -> bool:
    """
    Whether a set of labels is one this can read, asked before a layer exists.

    ``so.Text()`` written without a ``text=`` variable still draws one artist
    per observation, each holding an empty string -- measured, twelve of them
    for twelve rows. Nothing is on the page, and a layer of twelve positions
    would describe marks a sighted reader cannot see.

    Asked here rather than left to the reading's own refusal, for the reason
    :func:`maidr.core.plot.stepped_histogram.reads` gives: a layer registered
    and then unable to extract raises, and an ``ExtractionError`` takes the
    **whole figure** to a static image. Declining before registration leaves
    every other layer on the chart readable.

    Parameters
    ----------
    labels : sequence of Text
        The artists the mark drew.

    Returns
    -------
    bool
        True when at least one label carries a string.
    """
    return any(artist.get_text() for artist in labels)
