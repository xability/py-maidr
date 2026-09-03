"""A box drawn without its caps or its fliers is still read (#697).

``showfliers=False``, ``sym=""`` and ``showcaps=False`` each leave a box on
screen with one kind of artist missing, and each used to empty the whole
layer: ``Axes.bxp`` hands back an empty ``caps`` or ``fliers`` list, and the
``zip`` that assembles one row per box ends at the shortest of its lists.
Measured on three samples::

    default                          rows=3
    showfliers=False                 rows=0
    sym=''                           rows=0
    showcaps=False                   rows=0
    showfliers=False, showcaps=False rows=0

Nothing raised: the layer registered as a box with ``data: []`` and
``selectors: []``, so a reader met a silent chart that was plainly drawn.

Both are recoverable from what is on screen. A whisker runs from the box edge
to the same value a cap would mark -- on the default chart every cap sits at
its whisker's far end -- so a chart with no caps reads its extremes off the
whiskers. Hidden fliers are simply not drawn, so two empty outlier lists are
the honest reading. The statistics do not change either way: ``showfliers``
and ``showcaps`` are drawing options, not inputs to ``boxplot_stats``.
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.cbook import boxplot_stats  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402

# One upper outlier, one lower outlier, none: every branch of the outlier
# split has a box exercising it.
SAMPLES = [
    [1.0, 2.0, 3.0, 4.0, 5.0, 30.0],
    [2.0, 3.0, 4.0, 5.0, 6.0, -20.0],
    [3.0, 4.0, 5.0, 6.0, 7.0],
]
STATISTICS = ("min", "q1", "q2", "q3", "max")


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _reject_constant(token: str):
    raise ValueError(token)


def draw_matplotlib(**kwargs) -> plt.Figure:
    fig, ax = plt.subplots()
    ax.boxplot(SAMPLES, **kwargs)
    return fig


def draw_seaborn(**kwargs) -> plt.Figure:
    fig, ax = plt.subplots()
    sns.boxplot(data=SAMPLES, ax=ax, **kwargs)
    return fig


def _layer(fig) -> dict:
    """The first layer's schema with plain string keys."""
    plot = FigureManager.get_maidr(fig).plots[0]
    return {(k.value if hasattr(k, "value") else k): v for k, v in plot.schema.items()}


def parses_as_strict_json(fig) -> None:
    """Assert the payload survives what the core actually runs on it.

    ``json.loads`` accepts the bare tokens ``json.dumps`` emits, so a plain
    round trip passes while ``JSON.parse`` in the browser fails.
    """
    schema = FigureManager.get_maidr(fig)._flatten_maidr()

    json.loads(json.dumps(schema), parse_constant=_reject_constant)


# (draw, orientation keywords, hiding keywords). The reference chart for each
# case is drawn with the orientation alone, so a horizontal case is compared
# row for row against a horizontal default rather than a vertical one.
CASES = {
    "matplotlib showfliers=False": (draw_matplotlib, {}, {"showfliers": False}),
    "matplotlib showcaps=False": (draw_matplotlib, {}, {"showcaps": False}),
    "matplotlib both hidden": (
        draw_matplotlib,
        {},
        {"showfliers": False, "showcaps": False},
    ),
    "matplotlib sym=''": (draw_matplotlib, {}, {"sym": ""}),
    "matplotlib horizontal showfliers=False": (
        draw_matplotlib,
        {"vert": False},
        {"showfliers": False},
    ),
    "matplotlib horizontal showcaps=False": (
        draw_matplotlib,
        {"vert": False},
        {"showcaps": False},
    ),
    "seaborn showfliers=False": (draw_seaborn, {}, {"showfliers": False}),
    "seaborn showcaps=False": (draw_seaborn, {}, {"showcaps": False}),
    "seaborn both hidden": (
        draw_seaborn,
        {},
        {"showfliers": False, "showcaps": False},
    ),
    "seaborn horizontal showfliers=False": (
        draw_seaborn,
        {"orient": "h"},
        {"showfliers": False},
    ),
}

parametrised = pytest.mark.parametrize(
    ("draw", "orientation", "hidden"), CASES.values(), ids=CASES.keys()
)


def _fliers_hidden(hidden: dict) -> bool:
    return hidden.get("showfliers") is False or hidden.get("sym") == ""


@parametrised
def test_every_box_is_still_read(draw, orientation, hidden):
    rows = _layer(draw(**orientation, **hidden))["data"]

    assert len(rows) == len(SAMPLES)


@parametrised
def test_the_statistics_match_the_default_chart(draw, orientation, hidden):
    reference = _layer(draw(**orientation))["data"]
    rows = _layer(draw(**orientation, **hidden))["data"]

    for row, expected in zip(rows, reference):
        assert {key: row[key] for key in STATISTICS} == {
            key: expected[key] for key in STATISTICS
        }
        assert row["z"] == expected["z"]


@parametrised
def test_hidden_fliers_read_as_no_outliers(draw, orientation, hidden):
    reference = _layer(draw(**orientation))["data"]
    rows = _layer(draw(**orientation, **hidden))["data"]

    for row, expected in zip(rows, reference):
        if _fliers_hidden(hidden):
            assert row["lowerOutliers"] == []
            assert row["upperOutliers"] == []
        else:
            assert row["lowerOutliers"] == expected["lowerOutliers"]
            assert row["upperOutliers"] == expected["upperOutliers"]


@parametrised
def test_one_selector_per_box(draw, orientation, hidden):
    layer = _layer(draw(**orientation, **hidden))

    assert len(layer["selectors"]) == len(layer["data"])


@parametrised
def test_the_payload_is_loadable(draw, orientation, hidden):
    parses_as_strict_json(draw(**orientation, **hidden))


def test_hidden_caps_point_the_extreme_selectors_at_the_whiskers():
    # The values were read off the whiskers' far ends, so that is what the
    # min and max selectors highlight.
    fig = draw_matplotlib(showcaps=False)
    plot = FigureManager.get_maidr(fig).plots[0]
    plot.schema  # noqa: B018  # extraction runs on first access
    whiskers = plot._bxp_stats["whiskers"]

    assert plot.elements_map["min"] == [w.get_gid() for w in whiskers[::2]]
    assert plot.elements_map["max"] == [w.get_gid() for w in whiskers[1::2]]


class TestWhatMustNotChange:
    def test_the_default_chart_reads_its_tukey_statistics(self):
        rows = _layer(draw_matplotlib())["data"]
        expected = boxplot_stats(SAMPLES)

        assert [row["z"] for row in rows] == ["1", "2", "3"]
        for row, stats in zip(rows, expected):
            assert row["min"] == stats["whislo"]
            assert row["q1"] == stats["q1"]
            assert row["q2"] == stats["med"]
            assert row["q3"] == stats["q3"]
            assert row["max"] == stats["whishi"]
        assert rows[0]["upperOutliers"] == [30.0]
        assert rows[1]["lowerOutliers"] == [-20.0]
        assert rows[2]["lowerOutliers"] == rows[2]["upperOutliers"] == []

    def test_the_default_chart_addresses_its_flier_artists(self):
        fig = draw_matplotlib()
        plot = FigureManager.get_maidr(fig).plots[0]
        plot.schema  # noqa: B018

        assert plot.elements_map["outliers"] == [
            flier.get_gid() for flier in plot._bxp_stats["fliers"]
        ]
        assert plot.elements_map["min"] == [
            cap.get_gid() for cap in plot._bxp_stats["caps"][::2]
        ]
