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
    POINTS = "points"
    LEVEL = "level"
    X = "x"
    Y = "y"

    # Plot legend keys.
    CAPTION = "caption"
    LABEL = "label"
    SUBTITLE = "subtitle"
    TITLE = "title"

    # Box plot keys.
    LOWER_OUTLIER = "lowerOutliers"
    MIN = "min"
    MAX = "max"
    Q1 = "q1"
    Q2 = "q2"
    Q3 = "q3"
    UPPER_OUTLIER = "upperOutliers"
    IQ = "iq"
    MEDIAN = "median"

    # Grouped bar and heatmap plot keys.
    FILL = "fill"
    LABELS = "labels"

    # Histogram plot keys.
    X_MIN = "xMin"
    X_MAX = "xMax"
    Y_MIN = "yMin"
    Y_MAX = "yMax"
