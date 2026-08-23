from enum import Enum


class MaidrKey(str, Enum):
    # Maidr info keys.
    ID = "id"
    ORIENTATION = "orientation"
    SELECTOR = "selectors"
    TYPE = "type"

    # Plot data keys.
    AXES = "axes"
    DATA = "data"
    FORMAT = "format"
    POINTS = "points"
    LEVEL = "level"
    X = "x"
    Y = "y"

    # Plot legend keys.
    CAPTION = "caption"
    LABEL = "label"
    #: What this layer *is*, when a figure holds several of a kind: the hue
    #: group a split scatter reads, say. Distinct from `TITLE`, which names
    #: the chart and is carried by every layer of a figure alike
    #: (xability/maidr#828).
    NAME = "name"
    SUBTITLE = "subtitle"
    TITLE = "title"

    # Box plot keys.
    LOWER_OUTLIER = "lowerOutliers"
    MIN = "min"
    MAX = "max"
    MEAN = "mean"
    Q1 = "q1"
    Q2 = "q2"
    Q3 = "q3"
    UPPER_OUTLIER = "upperOutliers"
    IQ = "iq"
    MEDIAN = "median"

    # Boxen (letter-value) plot keys. A rung is a pair of quantiles symmetric
    # about the median, named by its *tail* probability -- `p = 0.25` spans the
    # middle half, `p = 0.125` the middle three quarters -- which is how the
    # letter-value literature defines it and how seaborn reports it.
    LEVELS = "levels"
    P = "p"
    LO = "lo"
    HI = "hi"

    # Grouped bar, heatmap, and z-axis keys.
    Z = "z"
    LABELS = "labels"
    DOM_MAPPING = "domMapping"

    # Scatter plot grid navigation keys.
    TICK_STEP = "tickStep"

    # Hexbin keys. A bin carries its centre and how many points fell in it.
    COUNT = "count"

    # Step plot keys. The per-point ordinal level name reuses LABEL above.
    STEP_DIRECTION = "stepDirection"

    # Gantt keys. An interval carries the two ends of its span; its lane is
    # `X`, and the lane names live in `LANES` so that a lane holding nothing
    # still has somewhere to carry one.
    START = "start"
    END = "end"
    LANES = "lanes"

    # Waterfall keys. A step carries the two running totals it sits between
    # -- reusing `START` and `END` above, which mean the same two things a
    # gantt interval's ends do -- plus its own signed contribution and which
    # way it moved. `DELTA` is carried rather than derived because a producer
    # may round the two totals for display, and a delta recomputed from
    # rounded ends is not the number the chart's own label shows.
    DELTA = "delta"
    KIND = "kind"

    # Histogram plot keys.
    X_MIN = "xMin"
    X_MAX = "xMax"
    Y_MIN = "yMin"
    Y_MAX = "yMax"

    # Scatter plot keys. The category a coordinate is a *position* for, when
    # the axis carries names -- a strip plot, a swarm plot, any scatter on a
    # discrete scale. Suffixed per axis because either one can be the
    # categorical one, unlike LABEL above, which a step layer only ever needs
    # for its y.
    X_LABEL = "xLabel"
    Y_LABEL = "yLabel"
