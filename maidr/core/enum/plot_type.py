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
    #: A scalar field drawn as curves of constant value. The level is a
    #: number here rather than a colour -- `QuadContourSet.levels` is the
    #: data, and `get_paths()` gives one path per level -- which is what
    #: separates `Axes.contour` from the same chart in a renderer that keeps
    #: its magnitude only in a fill.
    CONTOUR = "contour"
    COUNT = "count"
    DODGED = "dodged_bar"
    ERRORBAR = "error_bar"
    #: A schedule of intervals in lanes. `Axes.broken_barh` is matplotlib's
    #: gantt chart: one call per lane, drawing that lane's intervals as a
    #: `PolyCollection`, so the shape the trace wants -- a lane and the two
    #: ends of each interval in it -- is what the call was given.
    GANTT = "gantt"
    HEAT = "heat"
    #: A hexagonal bin lattice: the standard answer to an overplotted scatter.
    #: Read as a grid of cells each carrying a count, which is a heatmap --
    #: except that alternate rows are offset by half a cell, so a bin's column
    #: index is not its position and the trace announces centres instead.
    HEXBIN = "hexbin"
    HIST = "hist"
    LINE = "line"
    #: One value per position, each marked and joined to a baseline.
    #: `Axes.stem` is matplotlib's spelling. A distinct type from `BAR`
    #: only in what is drawn at the position -- the core builds both on
    #: `BarTrace` -- and a distinct type from `LINE` in a way that matters:
    #: the marks are not joined to each other, and the baseline is a frame
    #: rather than a series (#574).
    LOLLIPOP = "lollipop"
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
    #: Spokes around a circle, one radius per angle. `RADAR` joins them into
    #: an outline and `POLAR_AREA` fills the wedge between them; a reader
    #: navigates the same spokes either way, which is why the core builds
    #: both on one trace.
    RADAR = "radar"
    POLAR_AREA = "polar_area"
    #: Regions of a map shaded by a value. Stated as a region and its number
    #: rather than as a grid, because a map has no rows and columns -- and
    #: without centroids, which a plotly trace does not carry, it is read as
    #: a list of regions in the order they were declared.
    CHOROPLETH = "choropleth"
    #: Categorical dimensions side by side, with a ribbon between adjacent
    #: ones for every combination that occurs -- a parallel sets diagram.
    #: The same weighted flow :attr:`SANKEY` carries, drawn without a
    #: left-to-right budget, which is why the core builds both on one trace.
    ALLUVIAL = "alluvial"
    #: Weighted flow between nodes, drawn as ribbons whose width is the
    #: magnitude. Stated as one point per link -- the two nodes it joins and
    #: how much moves -- rather than as a series, because the chart is a
    #: graph and there is no grid reading of it.
    SANKEY = "sankey"
    #: A hierarchy drawn as nested rectangles, and the two paintings of the
    #: same tree that differ from it only in shape: concentric rings for a
    #: sunburst, stacked bands for an icicle. Kept apart because the chart
    #: type is announced, and a reader told "treemap" about a sunburst has
    #: been told something false about the picture beside them.
    TREEMAP = "treemap"
    SUNBURST = "sunburst"
    ICICLE = "icicle"
    #: One measure against a dial, with the range it sits in and -- when the
    #: chart draws one -- the target it is measured against. The one type
    #: here whose payload is a single point rather than a list of them.
    GAUGE = "gauge"
    #: A population shrinking across ordered stages. Read as a bar layer is,
    #: with the one difference that decides whether the chart is legible: the
    #: number a reader wants is the *retention* between adjacent stages
    #: rather than the count, so that is what the core pitches. The counts
    #: are announced alongside it.
    FUNNEL = "funnel"
    #: One polyline per observation crossing a row of vertical axes, each a
    #: different variable. Structurally a multi-line layer, which is what the
    #: core builds it on -- and a distinct type for the one thing that makes
    #: the chart legible: the columns are not one scale, so a value is
    #: pitched against *its own* axis rather than against the layer.
    PARALLEL = "parallel_coordinates"
    #: A starting value carried to an ending value through a sequence of
    #: signed contributions, each bar floating between the running total
    #: before it and the running total after it. A distinct type from `BAR`
    #: because a step carries two numbers a bar conflates -- the contribution
    #: it made and the total it produced -- and announcing either alone
    #: answers half the question the chart is drawn for.
    WATERFALL = "waterfall"

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
    PlotType.PARALLEL: "parallel coordinates",
    PlotType.POLAR_AREA: "polar area",
    PlotType.VIOLIN_BOX: "violin",
    PlotType.VIOLIN_KDE: "violin",
}
