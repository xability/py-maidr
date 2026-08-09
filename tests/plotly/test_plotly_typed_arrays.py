"""Figures built by ``plotly.express`` report their own numbers.

Since plotly 6.x, ``Figure.to_dict()`` exports a numeric array as the
``{"dtype": ..., "bdata": ...}`` base64 typed-array spec plotly.js consumes,
and a non-numeric one as a numpy array. ``plotly.express`` produces one or the
other for every column it plots, so an extractor that iterates a trace array
literally walks the spec's two keys and emits ``"dtype"`` and ``"bdata"`` as
the data.

Every figure here is therefore built through ``plotly.express`` from a
DataFrame. A hand-built ``go.Bar(y=[1, 2, 3])`` passes a plain list and does
not reproduce any of this, which is what the rest of ``tests/plotly`` uses and
why it stayed green.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pytest

plotly = pytest.importorskip("plotly")
pd = pytest.importorskip("pandas")

import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402
from maidr.plotly.plotly_plot import as_list  # noqa: E402
from maidr.plotly.step_shape import default_mode  # noqa: E402

FRAME = pd.DataFrame(
    {
        "category": ["a", "b", "c"],
        "value": [10, 20, 30],
    }
)


def _leaves(value: Any) -> list:
    """Return every scalar reachable in a nested schema payload."""
    if isinstance(value, dict):
        return [leaf for item in value.values() for leaf in _leaves(item)]
    if isinstance(value, (list, tuple)):
        return [leaf for item in value for leaf in _leaves(item)]
    return [value]


def _data_of(fig: go.Figure) -> list:
    """Return the emitted ``data`` payload of every layer the figure produces."""
    return [plot.schema["data"] for plot in PlotlyMaidr(fig)._plots]


def _values_for(key: str, payload: Any) -> list:
    """Collect one key's values out of a payload, whatever depth they sit at.

    The extractors disagree on how deep their points are nested and on whether
    they key them by :class:`~maidr.core.enum.maidr_key.MaidrKey` or by its
    string value, so both are looked through rather than assumed.
    """
    if isinstance(payload, dict):
        found = [
            value
            for name, value in payload.items()
            if getattr(name, "value", name) == key
        ]
        return found + [
            value for item in payload.values() for value in _values_for(key, item)
        ]
    if isinstance(payload, (list, tuple)):
        return [value for item in payload for value in _values_for(key, item)]
    return []


# One case per extractor under `maidr/plotly/`, each built through px so its
# numeric columns arrive as typed-array specs.
EXPRESS_FIGURES = {
    "bar": lambda: px.bar(FRAME, x="category", y="value"),
    "line": lambda: px.line(FRAME, x="category", y="value"),
    "scatter": lambda: px.scatter(_wide(), x="x", y="y"),
    "multiline": lambda: px.line(_wide(), x="x", y="y", color="group"),
    "grouped_bar": lambda: px.bar(
        _wide(), x="label", y="y", color="group", barmode="group"
    ),
    "step": lambda: px.line(_wide(), x="x", y="y", line_shape="hv"),
    "histogram": lambda: px.histogram(_wide(), x="y"),
    "box": lambda: px.box(_wide(), y="y"),
    "multibox": lambda: px.box(_wide(), x="label", y="y", color="group"),
    "heatmap": lambda: px.imshow(np.array([[1, 2, 3], [4, 5, 6]])),
    "pie": lambda: px.pie(FRAME, names="category", values="value"),
}


def _wide() -> Any:
    """Return a frame wide enough for the binning and grouping extractors."""
    return pd.DataFrame(
        {
            "x": list(range(12)),
            "y": [float(i) for i in range(12)],
            "label": list("abcd") * 3,
            "group": ["p", "q"] * 6,
        }
    )


@pytest.mark.parametrize("name", sorted(EXPRESS_FIGURES))
def test_no_extractor_emits_the_typed_array_keys_as_data(name: str):
    leaves = _leaves(_data_of(EXPRESS_FIGURES[name]()))

    assert leaves, f"{name} emitted nothing to check"
    assert "dtype" not in leaves
    assert "bdata" not in leaves
    assert "shape" not in leaves


def test_bar_reports_the_frames_own_magnitudes():
    assert _values_for("y", _data_of(px.bar(FRAME, x="category", y="value"))) == [
        10,
        20,
        30,
    ]


def test_line_reports_every_point_not_just_the_specs_two_keys():
    data = _data_of(px.line(FRAME, x="category", y="value"))

    assert _values_for("x", data) == ["a", "b", "c"]
    assert _values_for("y", data) == [10, 20, 30]


def test_scatter_reports_both_axes():
    data = _data_of(px.scatter(_wide(), x="x", y="y"))

    assert _values_for("x", data) == list(range(12))
    assert _values_for("y", data) == [float(i) for i in range(12)]


def test_heatmap_keeps_its_rows_rather_than_flattening_them():
    # `z` is the one two-dimensional trace array, so it is the one exported
    # with a `shape`; losing it would collapse the rows into a flat run.
    points = _data_of(px.imshow(np.array([[1, 2, 3], [4, 5, 6]])))[0]["points"]

    assert points == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]


def test_box_computes_its_quartiles_from_the_decoded_samples():
    stats = _data_of(px.box(_wide(), y="y"))[0][0]

    assert stats["q2"] == pytest.approx(5.5)
    assert stats["min"] == pytest.approx(0.0)
    assert stats["max"] == pytest.approx(11.0)


def test_histogram_bins_the_samples_rather_than_counting_the_spec_keys():
    data = _data_of(px.histogram(_wide(), x="y"))[0]

    assert sum(_values_for("y", data)) == 12


def test_pie_is_unchanged_by_moving_its_decoder():
    data = _data_of(px.pie(FRAME, names="category", values="value"))

    # Plotly sorts wedges by value, largest first.
    assert _values_for("x", data) == ["c", "b", "a"]
    assert _values_for("y", data) == [30, 20, 10]


def test_a_numpy_backed_trace_is_counted_by_its_points_not_its_spec_keys():
    # `default_mode` resolves the mode plotly applies when the author sets
    # none, and it decides that on the point count. A spec's own length is 2
    # whatever it holds, which capped every numpy-backed trace below the
    # marker threshold and read a 30-point line as "lines+markers".
    numpy_trace = go.Figure(
        go.Scatter(x=np.arange(30), y=np.arange(30, dtype=float))
    ).to_dict()["data"][0]
    list_trace = go.Figure(
        go.Scatter(x=list(range(30)), y=[float(i) for i in range(30)])
    ).to_dict()["data"][0]

    assert "mode" not in numpy_trace
    assert default_mode(numpy_trace) == default_mode(list_trace) == "lines"


class TestAsList:
    """The decoder leaves everything that already worked alone."""

    @pytest.mark.parametrize(
        "value, expected",
        [
            ([1, 2, 3], [1, 2, 3]),
            ((1, 2, 3), [1, 2, 3]),
            (["a", "b"], ["a", "b"]),
            ([], []),
            (None, []),
        ],
    )
    def test_plain_sequences_and_none_pass_through(self, value: Any, expected: list):
        assert as_list(value) == expected

    def test_a_string_is_rejected_rather_than_split_into_letters(self):
        assert as_list("abc") == []

    def test_a_one_dimensional_spec_decodes_to_its_numbers(self):
        spec = go.Figure(go.Bar(y=np.array([10, 20, 30]))).to_dict()["data"][0]["y"]

        assert isinstance(spec, dict)
        assert as_list(spec) == [10, 20, 30]

    def test_a_spec_carrying_a_shape_decodes_to_nested_rows(self):
        spec = go.Figure(go.Heatmap(z=np.array([[1, 2, 3], [4, 5, 6]]))).to_dict()[
            "data"
        ][0]["z"]

        assert spec["shape"] == "2, 3"
        assert as_list(spec) == [[1, 2, 3], [4, 5, 6]]

    @pytest.mark.parametrize(
        "spec",
        [
            {"dtype": "i1"},
            {"bdata": "ChQe"},
            {"dtype": "not-a-dtype", "bdata": "ChQe"},
            {"dtype": "i1", "bdata": "!!!not base64!!!"},
            {"dtype": "i1", "bdata": "ChQe", "shape": "5, 5"},
        ],
    )
    def test_an_undecodable_spec_comes_back_empty(self, spec: dict):
        assert as_list(spec) == []

    @pytest.mark.parametrize(
        "spec",
        [
            {"dtype": "i1"},
            {"bdata": "ChQe"},
            {"dtype": "not-a-dtype", "bdata": "ChQe"},
            {"dtype": "i1", "bdata": "!!!not base64!!!"},
            {"dtype": "i1", "bdata": "ChQe", "shape": "5, 5"},
        ],
    )
    def test_an_undecodable_spec_says_so(self, spec: dict, caplog):
        # An empty layer is the safe answer, but a silent one repeats the very
        # fault this decoder exists to fix: a chart that draws while its
        # accessible layer is wrong and nothing says so.
        with caplog.at_level(logging.WARNING, logger="maidr.plotly.plotly_plot"):
            as_list(spec)

        assert "maidr" in caplog.text
        assert "no data" in caplog.text

    def test_a_spec_that_decodes_says_nothing(self, caplog):
        with caplog.at_level(logging.WARNING, logger="maidr.plotly.plotly_plot"):
            assert as_list({"dtype": "i1", "bdata": "ChQe"}) == [10, 20, 30]

        assert caplog.text == ""


class TestPartialDecodeFailure:
    """One unreadable statistic shortens a boxplot; it does not crash it.

    The five precomputed arrays decode independently, so a corrupt spec in
    one of them leaves the others populated. Indexing the short one is what
    a crash would look like, and a crash here takes the whole figure with it
    — including every layer that decoded perfectly well.
    """

    @staticmethod
    def _trace(**overrides: Any) -> dict:
        good = {"dtype": "i1", "bdata": "ChQe"}  # 10, 20, 30
        trace = {
            "type": "box",
            "q1": good,
            "median": good,
            "q3": good,
        }
        trace.update(overrides)
        return trace

    @pytest.mark.parametrize("field", ["q1", "median", "q3"])
    def test_an_undecodable_statistic_shortens_the_layer(self, field: str):
        from maidr.plotly.box import PlotlyBoxPlot

        broken = {"dtype": "i1", "bdata": "!!!not base64!!!"}
        plot = PlotlyBoxPlot(self._trace(**{field: broken}), {})

        assert plot._extract_plot_data() == []

    def test_a_short_statistic_describes_only_the_complete_boxes(self):
        from maidr.plotly.box import PlotlyBoxPlot

        # One q1 for three medians: two boxes have no lower quartile.
        plot = PlotlyBoxPlot(self._trace(q1={"dtype": "i1", "bdata": "Cg=="}), {})
        boxes = plot._extract_plot_data()

        assert len(boxes) == 1
        assert boxes[0]["q1"] == 10

    def test_the_shortening_is_reported(self, caplog):
        from maidr.plotly.box import PlotlyBoxPlot

        plot = PlotlyBoxPlot(self._trace(q1={"dtype": "i1", "bdata": "Cg=="}), {})
        with caplog.at_level(logging.WARNING, logger="maidr.plotly.box"):
            plot._extract_plot_data()

        assert "3 medians but only 1" in caplog.text

    def test_a_complete_trace_is_unaffected_and_silent(self, caplog):
        from maidr.plotly.box import PlotlyBoxPlot

        plot = PlotlyBoxPlot(self._trace(), {})
        with caplog.at_level(logging.WARNING, logger="maidr.plotly.box"):
            boxes = plot._extract_plot_data()

        assert len(boxes) == 3
        assert caplog.text == ""

    def test_the_multi_box_extractor_behaves_the_same(self):
        from maidr.plotly.multibox import PlotlyMultiBoxPlot

        broken = {"dtype": "i1", "bdata": "!!!not base64!!!"}
        plot = PlotlyMultiBoxPlot([self._trace(q3=broken)], {})

        assert plot._extract_plot_data() == []
