from enum import Enum


class PlotType(str, Enum):
    """An enumeration of plot types supported by MAIDR."""

    BAR = "bar"
    BOX = "box"
    #: A letter-value plot: the box plot's five-number summary generalised to a
    #: variable-depth ladder of quantiles, so a large sample's tails stay
    #: legible instead of collapsing into a whisker and a cloud of dots. A
    #: distinct type because :attr:`BOX` is fixed at one rung, and depth is the
    #: whole point of the chart.
    BOXEN = "boxen"
    COUNT = "count"
    DODGED = "dodged_bar"
    ERRORBAR = "error_bar"
    HEAT = "heat"
    #: A hexagonal bin lattice: the standard answer to an overplotted scatter.
    #: Read as a grid of cells each carrying a count, which is a heatmap --
    #: except that alternate rows are offset by half a cell, so a bin's column
    #: index is not its position and the trace announces centres instead.
    HEXBIN = "hexbin"
    HIST = "hist"
    LINE = "line"
    #: A filled band between a series and a baseline. Emitted for a single
    #: `stackplot` band, which has nothing stacked on it.
    AREA = "area"
    #: Bands stacked on one another, so a band's height is its own series'
    #: value while its top edge is the running total. A distinct type because
    #: a line layer announces one number per point with nothing to say which
    #: of those two it is.
    STACKED_AREA = "stacked_area"
    #: A stacked area rescaled so every position totals the same, the area
    #: counterpart of :attr:`NORMALIZED`. Distinct for the same reason: a band
    #: is a *share* of its position's total rather than a magnitude, and read
    #: as a plain stack the equal totals look like a property of the data
    #: rather than of the chart.
    NORMALIZED_AREA = "stacked_normalized_area"
    PIE = "pie"
    SCATTER = "point"
    STACKED = "stacked_bar"
    NORMALIZED = "stacked_normalized_bar"
    STEP = "step"
    SMOOTH = "smooth"
    CANDLESTICK = "candlestick"
    VIOLIN_KDE = "violin_kde"
    VIOLIN_BOX = "violin_box"

    @property
    def display_name(self) -> str:
        """
        Name for this plot type as a *user* would recognise it.

        A member's value is the MAIDR wire identifier, which does not always
        match what the user called: someone who ran ``ax.scatter`` should be
        told about "scatter", not about ``point``. Use this whenever a plot
        type is named in a message a user reads; use ``.value`` for the schema.

        Returns
        -------
        str
            The user-facing name, falling back to the wire value when the two
            are already the same.
        """
        return _DISPLAY_NAMES.get(self, self.value)


#: Overrides for the members whose wire value is not what a user would call the
#: plot. Members absent here already read naturally (``bar``, ``line``, ...).
#: Both violin layers display as "violin" because they are two layers of one
#: plot, and callers de-duplicate.
_DISPLAY_NAMES = {
    PlotType.DODGED: "dodged bar",
    PlotType.ERRORBAR: "error bar",
    PlotType.HEAT: "heatmap",
    PlotType.HIST: "histogram",
    PlotType.SCATTER: "scatter",
    PlotType.NORMALIZED: "100% stacked bar",
    PlotType.STACKED: "stacked bar",
    PlotType.STACKED_AREA: "stacked area",
    PlotType.NORMALIZED_AREA: "100% stacked area",
    PlotType.VIOLIN_BOX: "violin",
    PlotType.VIOLIN_KDE: "violin",
}
