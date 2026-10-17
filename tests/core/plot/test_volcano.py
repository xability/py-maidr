"""``maidr.volcano`` and ``maidr.manhattan`` declare a scatter a threshold layer.

maidr.js reads a ``volcano`` or ``manhattan`` layer as ``VolcanoPoint[]`` with
``thresholdOptions`` on the layer (``src/type/grammar.ts``), and its selector
as one string, the way it reads a ``point`` layer's (``docs/SCHEMA.md``). These
pin that shape, that the declared layer takes the place of the scatter layers
it reads rather than sitting beside them, and that a name stays on the point it
was given for.
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: E402
from maidr.core.enum import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _layers(figure) -> list[dict]:
    """The figure's layers as the page carries them."""
    schema = json.loads(json.dumps(FigureManager.get_maidr(figure)._flatten_maidr()))
    return [
        layer for row in schema["subplots"] for cell in row for layer in cell["layers"]
    ]


def test_a_scatter_becomes_one_volcano_layer():
    figure, ax = plt.subplots()
    points = ax.scatter([-2.5, 0.1, 3.2], [6.0, 0.4, 8.1])
    ax.set_xlabel("log2 fold change")
    ax.set_ylabel("-log10 p")

    maidr.volcano(points, significance=1.3, effect=1.0, labels=["TP53", "GAPDH", "MYC"])

    (layer,) = _layers(figure)
    assert layer["type"] == "volcano"
    assert layer["data"] == [
        {"x": -2.5, "y": 6.0, "label": "TP53"},
        {"x": 0.1, "y": 0.4, "label": "GAPDH"},
        {"x": 3.2, "y": 8.1, "label": "MYC"},
    ]
    assert layer["thresholdOptions"] == {
        "significance": 1.3,
        "significanceDirection": "above",
        "effect": 1.0,
    }
    # One string, as for a point layer: maidr.js hands it to
    # `querySelectorAll` and pairs the matches by position.
    assert isinstance(layer["selectors"], str)
    assert "maidr='true'" not in layer["selectors"]
    assert layer["axes"]["x"]["label"] == "log2 fold change"
    assert set(layer["axes"]) <= {"x", "y", "z"}


def test_a_manhattan_layer_carries_each_points_chromosome():
    figure, ax = plt.subplots()
    first = ax.scatter([10, 120], [2.1, 8.4])
    second = ax.scatter([260], [1.0])

    maidr.manhattan(
        [first, second],
        significance=7.3,
        labels=["rs1", "rs2", "rs3"],
        groups=["chr1", "chr1", "chr2"],
    )

    (layer,) = _layers(figure)
    assert layer["type"] == "manhattan"
    assert layer["data"] == [
        {"x": 10.0, "y": 2.1, "label": "rs1", "group": "chr1"},
        {"x": 120.0, "y": 8.4, "label": "rs2", "group": "chr1"},
        {"x": 260.0, "y": 1.0, "label": "rs3", "group": "chr2"},
    ]
    # No effect cutoff: x is a position on the genome, not a size.
    assert layer["thresholdOptions"] == {
        "significance": 7.3,
        "significanceDirection": "above",
    }


def test_the_axes_form_reads_every_scatter_on_it_including_a_hue_split():
    data = pd.DataFrame(
        {
            "fc": [-2.0, 1.0, 3.0, 0.2],
            "p": [5.0, 0.5, 9.0, 0.1],
            "call": ["down", "ns", "up", "ns"],
            "gene": ["A", "B", "C", "D"],
        }
    )
    figure, ax = plt.subplots()
    drawn = sns.scatterplot(data, x="fc", y="p", hue="call", ax=ax)
    assert len(FigureManager.get_maidr(figure).plots) == 3

    maidr.volcano(drawn, significance=2.0, labels=data["gene"])

    (layer,) = _layers(figure)
    assert layer["type"] == "volcano"
    assert [point["label"] for point in layer["data"]] == ["A", "B", "C", "D"]


def test_a_name_stays_on_its_point_past_an_undrawn_row():
    figure, ax = plt.subplots()
    points = ax.scatter([1.0, np.nan, 3.0], [4.0, 5.0, 6.0])

    maidr.volcano(points, significance=1.0, labels=["a", "b", "c"])

    (layer,) = _layers(figure)
    assert layer["data"] == [
        {"x": 1.0, "y": 4.0, "label": "a"},
        {"x": 3.0, "y": 6.0, "label": "c"},
    ]


def test_a_missing_name_is_left_off_rather_than_announced():
    figure, ax = plt.subplots()
    points = ax.scatter([1.0, 2.0, 3.0], [4.0, 5.0, 6.0])

    maidr.volcano(points, significance=1.0, labels=["a", None, ""])

    assert [sorted(p) for p in _layers(figure)[0]["data"]] == [
        ["label", "x", "y"],
        ["x", "y"],
        ["x", "y"],
    ]


def test_a_raw_p_axis_declares_its_findings_below_the_line():
    figure, ax = plt.subplots()
    points = ax.scatter([1.0, 2.0], [0.01, 0.4])

    maidr.volcano(points, significance=0.05, significance_direction="below")

    (layer,) = _layers(figure)
    assert layer["thresholdOptions"]["significanceDirection"] == "below"


def test_other_layers_keep_their_place_and_their_ids():
    figure, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    points = ax.scatter([1.0, 2.0], [3.0, 4.0])
    ax.bar([0, 1], [1, 2])
    manager = FigureManager.get_maidr(figure)
    line_id, scatter_id, bar_id = manager.selector_ids

    maidr.volcano(points, significance=1.0)

    assert [plot.type for plot in manager.plots] == [
        PlotType.LINE,
        PlotType.VOLCANO,
        PlotType.BAR,
    ]
    assert manager.selector_ids == [line_id, scatter_id, bar_id]


def test_the_threshold_is_required():
    figure, ax = plt.subplots()
    points = ax.scatter([1.0], [2.0])

    with pytest.raises(TypeError):
        maidr.volcano(points)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"significance": float("nan")}, ValueError),
        ({"significance": "1.3"}, TypeError),
        ({"significance": True}, TypeError),
        ({"significance": 1.3, "effect": -1.0}, ValueError),
        ({"significance": 1.3, "significance_direction": "up"}, ValueError),
        ({"significance": 1.3, "labels": ["only one"]}, ValueError),
        ({"significance": 1.3, "groups": ["a", "b", "c"]}, ValueError),
    ],
)
def test_a_bad_declaration_is_refused_at_the_call(kwargs, error):
    figure, ax = plt.subplots()
    points = ax.scatter([1.0, 2.0], [2.0, 3.0])

    with pytest.raises(error):
        maidr.volcano(points, **kwargs)
    # Nothing was replaced.
    assert [p.type for p in FigureManager.get_maidr(figure).plots] == [PlotType.SCATTER]


def test_axes_with_no_scatter_are_refused():
    figure, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])

    with pytest.raises(ValueError, match="no scatter"):
        maidr.manhattan(ax, significance=7.3)


def test_something_other_than_a_scatter_is_refused():
    figure, ax = plt.subplots()
    (line,) = ax.plot([0, 1], [0, 1])

    with pytest.raises(TypeError):
        maidr.volcano(line, significance=1.3)  # type: ignore[arg-type]


def test_the_page_carries_the_layer():
    figure, ax = plt.subplots()
    points = ax.scatter([-2.0, 3.0], [6.0, 8.0])
    maidr.volcano(points, significance=1.3, labels=["TP53", "MYC"])

    html = str(maidr.render(figure))

    assert "&quot;volcano&quot;" in html or '"volcano"' in html
    assert "thresholdOptions" in html


def test_declaring_the_same_points_again_replaces_the_layer():
    # A notebook cell run again with a new cutoff, or a volcano redeclared a
    # Manhattan: one layer, carrying what the last call said.
    figure, ax = plt.subplots()
    points = ax.scatter([1.0, 2.0], [3.0, 4.0])
    manager = FigureManager.get_maidr(figure)
    (scatter_id,) = manager.selector_ids

    maidr.volcano(points, significance=1.3)
    maidr.volcano(points, significance=2.0, labels=["a", "b"])

    (layer,) = _layers(figure)
    assert layer["thresholdOptions"]["significance"] == 2.0
    assert [point["label"] for point in layer["data"]] == ["a", "b"]
    assert manager.selector_ids == [scatter_id]

    maidr.manhattan(ax, significance=7.3)
    assert [layer["type"] for layer in _layers(figure)] == ["manhattan"]


def test_one_scatter_of_several_converts_only_that_one():
    figure, ax = plt.subplots()
    ax.scatter([1.0], [2.0])
    hits = ax.scatter([3.0], [4.0])

    maidr.volcano(hits, significance=1.0)

    assert [layer["type"] for layer in _layers(figure)] == ["point", "volcano"]


@pytest.mark.parametrize(
    "missing",
    [None, float("nan"), np.float32("nan"), np.float64("nan"), pd.NA, pd.NaT, ""],
    ids=["None", "nan", "float32-nan", "float64-nan", "pd.NA", "NaT", "empty"],
)
def test_every_kind_of_missing_name_is_left_off(missing):
    figure, ax = plt.subplots()
    points = ax.scatter([1.0, 2.0], [3.0, 4.0])

    maidr.volcano(points, significance=1.0, labels=["a", missing])

    assert [point.get("label") for point in _layers(figure)[0]["data"]] == ["a", None]


def test_names_from_a_series_with_gaps_are_left_off():
    figure, ax = plt.subplots()
    points = ax.scatter([1.0, 2.0, 3.0], [3.0, 4.0, 5.0])
    chromosomes = pd.Series(["chr1", None, "chr2"], dtype="string")

    maidr.manhattan(points, significance=1.0, groups=chromosomes)

    assert [point.get("group") for point in _layers(figure)[0]["data"]] == [
        "chr1",
        None,
        "chr2",
    ]
