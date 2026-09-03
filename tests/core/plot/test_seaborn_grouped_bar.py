"""Tests that a hued seaborn bar plot is bound as a grouped layer.

Whether a hue splits a bar layer into groups is seaborn's decision, taken
from `dodge="auto"` and the data, and it never reaches matplotlib: seaborn
draws through `Axes.bar` without forwarding `hue` or `dodge`. Classifying
from the seaborn arguments therefore only caught the calls that passed
`dodge=True` by hand; every other hued bar plot was bound as a plain bar
layer, where the grouped bars outnumber the tick labels and extraction
fails. These pin the classification to what seaborn actually drew, and the
grouped layer to both orientations.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402


DATA = pd.DataFrame(
    {
        "cat": ["a", "a", "b", "b", "c", "c"],
        "grp": ["x", "y", "x", "y", "x", "y"],
        "val": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
    }
)

GROUPED = [
    [
        {"x": "a", "z": "x", "y": 1.0},
        {"x": "b", "z": "x", "y": 3.0},
        {"x": "c", "z": "x", "y": 5.0},
    ],
    [
        {"x": "a", "z": "y", "y": 2.0},
        {"x": "b", "z": "y", "y": 4.0},
        {"x": "c", "z": "y", "y": 6.0},
    ],
]


def _schema(fig) -> dict:
    """Return the first layer's schema with plain string keys."""
    plot = FigureManager.get_maidr(fig).plots[0]
    return {(k.value if hasattr(k, "value") else k): v for k, v in plot.schema.items()}


def _layer_type(fig) -> PlotType:
    return FigureManager.get_maidr(fig).plots[0].type


@pytest.mark.parametrize("dodge", [None, True, False])
def test_a_hued_barplot_is_grouped_however_dodge_was_left(dodge: bool | None) -> None:
    """The bug: only `dodge=True` was recognised, and it is not the default.

    `dodge` defaults to `"auto"`, so the common call — hue and nothing else —
    was bound as a plain bar layer and raised while extracting. `dodge=False`
    stacks the groups on one another visually, but the data is still one
    series per hue level, so it is read the same way.
    """
    fig, ax = plt.subplots()
    try:
        kwargs = {} if dodge is None else {"dodge": dodge}
        sns.barplot(data=DATA, x="cat", y="val", hue="grp", ax=ax, **kwargs)
        schema = _schema(fig)

        assert _layer_type(fig) is PlotType.DODGED
        assert schema["orientation"] == "vert"
        assert schema["data"] == GROUPED
    finally:
        plt.close(fig)


def test_a_hued_countplot_is_grouped() -> None:
    fig, ax = plt.subplots()
    try:
        sns.countplot(data=DATA, x="cat", hue="grp", ax=ax)
        schema = _schema(fig)
    finally:
        plt.close(fig)

    assert schema["data"] == [
        [
            {"x": "a", "z": "x", "y": 1.0},
            {"x": "b", "z": "x", "y": 1.0},
            {"x": "c", "z": "x", "y": 1.0},
        ],
        [
            {"x": "a", "z": "y", "y": 1.0},
            {"x": "b", "z": "y", "y": 1.0},
            {"x": "c", "z": "y", "y": 1.0},
        ],
    ]


def test_a_horizontal_grouped_bar_puts_the_value_on_x_and_the_label_on_y() -> None:
    """The mirror of the vertical layout, which is what the renderer reads."""
    fig, ax = plt.subplots()
    try:
        sns.barplot(data=DATA, y="cat", x="val", hue="grp", ax=ax)
        schema = _schema(fig)
    finally:
        plt.close(fig)

    assert schema["orientation"] == "horz"
    assert schema["data"] == [
        [
            {"x": 1.0, "z": "x", "y": "a"},
            {"x": 3.0, "z": "x", "y": "b"},
            {"x": 5.0, "z": "x", "y": "c"},
        ],
        [
            {"x": 2.0, "z": "y", "y": "a"},
            {"x": 4.0, "z": "y", "y": "b"},
            {"x": 6.0, "z": "y", "y": "c"},
        ],
    ]


def test_a_single_category_split_by_hue_is_still_grouped() -> None:
    """One bar per group is the edge the tick-label count has to survive.

    Here each container holds a single bar, the same shape a redundant hue
    draws — the categorical axis is what tells them apart.
    """
    fig, ax = plt.subplots()
    try:
        sns.barplot(data=DATA[DATA["cat"] == "a"], x="cat", y="val", hue="grp", ax=ax)
        schema = _schema(fig)
    finally:
        plt.close(fig)

    assert _layer_type(fig) is PlotType.DODGED
    assert schema["data"] == [
        [{"x": "a", "z": "x", "y": 1.0}],
        [{"x": "a", "z": "y", "y": 2.0}],
    ]


def test_a_hue_that_repeats_the_category_stays_a_plain_bar_layer() -> None:
    """Seaborn draws this one container per bar, and does not group it.

    It is only colouring the bars it would have drawn anyway, so reading it
    as groups would report one group per bar. The bars are counted against
    the tick labels to tell the two apart.
    """
    fig, ax = plt.subplots()
    try:
        sns.barplot(data=DATA, x="cat", y="val", hue="cat", ax=ax)
        schema = _schema(fig)
    finally:
        plt.close(fig)

    assert _layer_type(fig) is PlotType.BAR
    assert schema["data"] == [
        {"x": "a", "y": 1.5},
        {"x": "b", "y": 3.5},
        {"x": "c", "y": 5.5},
    ]


def test_hue_groups_that_do_not_cover_every_category_are_still_grouped() -> None:
    """Ragged containers are a grouped layer with a gap, not a plain one.

    Seaborn draws no bar at all for a category and hue level that never
    occur together, so the containers come out ragged. `GroupedBarPlot`
    used to pair bars with labels by position alone and could not read
    those, so the classification turned the layer back to a plain bar --
    whose labels were then the bars' fractional positions, "-0.2" for "a",
    in place of the category and hue names a reader hears on the chart
    (#752). The bars that were drawn still sit against their category's
    tick, so the layer is placed against the ticks instead and the missing
    bar is the same `null` gap a `NaN` height emits.
    """
    ragged = DATA[~((DATA["cat"] == "b") & (DATA["grp"] == "y"))]
    fig, ax = plt.subplots()
    try:
        sns.barplot(data=ragged, x="cat", y="val", hue="grp", ax=ax)
        # The premise: seaborn dropped the bar rather than drawing a gap.
        assert [len(c.patches) for c in ax.containers] == [3, 2]
        schema = _schema(fig)

        assert _layer_type(fig) is PlotType.DODGED
        assert schema["data"] == [
            GROUPED[0],
            [
                {"x": "a", "z": "y", "y": 2.0},
                {"x": "b", "z": "y", "y": None},
                {"x": "c", "z": "y", "y": 6.0},
            ],
        ]
    finally:
        plt.close(fig)


def test_a_hue_with_one_level_stays_a_plain_bar_layer() -> None:
    """Nothing to group by: seaborn draws the one container it would anyway."""
    single = DATA.assign(grp="only")
    fig, ax = plt.subplots()
    try:
        sns.barplot(data=single, x="cat", y="val", hue="grp", ax=ax)
        schema = _schema(fig)
    finally:
        plt.close(fig)

    assert _layer_type(fig) is PlotType.BAR
    assert schema["data"] == [
        {"x": "a", "y": 1.5},
        {"x": "b", "y": 3.5},
        {"x": "c", "y": 5.5},
    ]


def test_a_barplot_without_a_hue_stays_a_plain_bar_layer() -> None:
    fig, ax = plt.subplots()
    try:
        sns.barplot(data=DATA, x="cat", y="val", ax=ax)
        schema = _schema(fig)
    finally:
        plt.close(fig)

    assert _layer_type(fig) is PlotType.BAR
    assert schema["data"] == [
        {"x": "a", "y": 1.5},
        {"x": "b", "y": 3.5},
        {"x": "c", "y": 5.5},
    ]


def test_a_stacked_bar_layer_reports_its_orientation() -> None:
    """Stacked layers share the grouped extractor, so they gained the key."""
    labels = ["a", "b", "c"]
    fig, ax = plt.subplots()
    try:
        ax.bar(labels, [1.0, 2.0, 3.0], label="lo")
        ax.bar(labels, [4.0, 5.0, 6.0], bottom=[1.0, 2.0, 3.0], label="hi")
        stacked = FigureManager.get_maidr(fig).plots[-1]
        schema = {
            (k.value if hasattr(k, "value") else k): v
            for k, v in stacked.schema.items()
        }
    finally:
        plt.close(fig)

    assert stacked.type is PlotType.STACKED
    assert schema["orientation"] == "vert"
    assert schema["data"] == [
        [
            {"x": "a", "z": "lo", "y": 1.0},
            {"x": "b", "z": "lo", "y": 2.0},
            {"x": "c", "z": "lo", "y": 3.0},
        ],
        [
            {"x": "a", "z": "hi", "y": 4.0},
            {"x": "b", "z": "hi", "y": 5.0},
            {"x": "c", "z": "hi", "y": 6.0},
        ],
    ]
