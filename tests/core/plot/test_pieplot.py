"""Tests for pie chart support.

A pie is the one plot type whose magnitudes matplotlib throws away.
``Axes.pie`` plots ``x / sum(x)`` and each ``Wedge`` keeps only its start and
end angle, so ``ax.pie([30, 50, 20])`` read back off the artists reports the
fractions 0.3/0.5/0.2 for a plot of counts. The patch reads the call before
matplotlib rewrites it, and most of what follows pins that down: the emitted
``y`` values are the caller's own numbers, whatever shape they arrived in.

The rest covers what the wire format asks of a pie layer — a flat row of
``{x, y}`` points, a per-slice selector in slice order, and an ``axes``
payload naming the two dimensions of a slice rather than positions on a
scale it does not have.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import json  # noqa: E402
import re  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from lxml import etree  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.core.plot.pieplot import PiePlot  # noqa: E402


#: A pie whose sizes sum far above 1, so matplotlib normalises them away.
FRUIT = ["Apples", "Bananas", "Cherries"]
UNITS = [30, 50, 20]


def _stringify(value):
    """Normalize MaidrKey/PlotType enum keys and values to plain strings."""
    if isinstance(value, dict):
        return {
            (k.value if hasattr(k, "value") else k): _stringify(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_stringify(item) for item in value]
    return value.value if hasattr(value, "value") else value


def _only_layer(fig) -> dict:
    """Assert the figure registered exactly one layer and return its schema."""
    maidr_obj = FigureManager.get_maidr(fig)
    assert len(maidr_obj._plots) == 1, (
        f"expected exactly one layer, got {[p.type for p in maidr_obj._plots]}"
    )
    return _stringify(maidr_obj._plots[0].schema)


def _layers(fig) -> list[dict]:
    """Return every registered layer's schema, in registration order."""
    return [_stringify(plot.schema) for plot in FigureManager.get_maidr(fig)._plots]


def _highlight_groups(fig) -> list[list]:
    """Render the figure and return the tagged group of each pie slice.

    The emitted selector is ``g[maidr='<id>'] > path``, so the elements it
    resolves to are the ``<g>`` elements carrying this layer's id, each
    holding one ``<path>``. Returning them in document order is what lets a
    test check that data index k and element k describe the same slice.
    """
    maidr_obj = FigureManager.get_maidr(fig)
    html = str(maidr_obj._create_html_tag().get_html_string())
    svg = re.search(r"<svg.*</svg>", html, re.S)
    assert svg is not None, "no SVG in the rendered output"

    root = etree.fromstring(svg.group(0).encode())
    return [
        [child for child in group if child.tag.endswith("path")]
        for group in root.xpath('//*[local-name()="g"][@maidr]')
    ]


class TestValuesSurviveNormalisation:
    """The caller's magnitudes, not the fractions matplotlib kept."""

    def test_counts_are_reported_as_counts(self):
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS, labels=FRUIT)
            schema = _only_layer(fig)

            assert [point["y"] for point in schema["data"]] == [30, 50, 20]
        finally:
            plt.close(fig)

    def test_ndarray_sizes_are_reported_as_given(self):
        fig, ax = plt.subplots()
        try:
            ax.pie(np.array(UNITS), labels=FRUIT)
            schema = _only_layer(fig)

            assert [point["y"] for point in schema["data"]] == [30, 50, 20]
        finally:
            plt.close(fig)

    def test_series_sizes_are_reported_as_given(self):
        fig, ax = plt.subplots()
        try:
            ax.pie(pd.Series(UNITS), labels=FRUIT)
            schema = _only_layer(fig)

            assert [point["y"] for point in schema["data"]] == [30, 50, 20]
        finally:
            plt.close(fig)

    def test_column_names_are_resolved_against_data(self):
        # `Axes.pie` sits behind matplotlib's `_preprocess_data`, so both
        # arguments may name a column instead of holding one.
        frame = pd.DataFrame({"units": UNITS, "fruit": FRUIT})
        fig, ax = plt.subplots()
        try:
            ax.pie("units", labels="fruit", data=frame)
            schema = _only_layer(fig)

            assert schema["data"] == [
                {"x": "Apples", "y": 30},
                {"x": "Bananas", "y": 50},
                {"x": "Cherries", "y": 20},
            ]
        finally:
            plt.close(fig)

    def test_sizes_below_one_are_left_alone(self):
        # Shares of a whole are already the numbers the caller meant.
        fig, ax = plt.subplots()
        try:
            ax.pie([0.25, 0.75], labels=["Half", "Rest"])
            schema = _only_layer(fig)

            assert [point["y"] for point in schema["data"]] == [0.25, 0.75]
        finally:
            plt.close(fig)

    def test_an_unnormalized_partial_pie_keeps_its_gap(self):
        # `normalize=False` draws a pie that does not close, and only accepts
        # sizes summing to at most 1. The sizes are still the caller's.
        fig, ax = plt.subplots()
        try:
            ax.pie([0.2, 0.3], labels=["Done", "Started"], normalize=False)
            schema = _only_layer(fig)

            assert [point["y"] for point in schema["data"]] == [0.2, 0.3]
        finally:
            plt.close(fig)

    def test_a_negative_size_is_rejected(self):
        # matplotlib refuses to draw one, and so does the layer built from it.
        fig, ax = plt.subplots()
        try:
            with pytest.raises(ValueError, match="non negative"):
                ax.pie([30, -50, 20])
        finally:
            plt.close(fig)


class TestReturnShapes:
    """``Axes.pie`` returns two lists, or three when ``autopct`` is set."""

    def test_wedges_and_texts(self):
        fig, ax = plt.subplots()
        try:
            returned = ax.pie(UNITS, labels=FRUIT)
            schema = _only_layer(fig)

            assert len(returned) == 2
            assert [point["y"] for point in schema["data"]] == [30, 50, 20]
        finally:
            plt.close(fig)

    def test_wedges_texts_and_autotexts(self):
        fig, ax = plt.subplots()
        try:
            returned = ax.pie(UNITS, labels=FRUIT, autopct="%1.1f%%")
            schema = _only_layer(fig)

            assert len(returned) == 3
            # The percentage labels matplotlib drew are not slices, so the
            # layer must still describe three of them.
            assert [point["y"] for point in schema["data"]] == [30, 50, 20]
            assert [point["x"] for point in schema["data"]] == FRUIT
        finally:
            plt.close(fig)

    def test_pyplot_entry_point_registers_the_layer(self):
        fig = plt.figure()
        try:
            plt.pie(UNITS, labels=FRUIT)
            schema = _only_layer(fig)

            assert schema["type"] == "pie"
        finally:
            plt.close(fig)


class TestLabels:
    """Labels argument, then the wedge's own label, then its position."""

    def test_labels_argument_names_the_slices(self):
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS, labels=FRUIT)
            schema = _only_layer(fig)

            assert [point["x"] for point in schema["data"]] == FRUIT
        finally:
            plt.close(fig)

    def test_an_unlabelled_pie_falls_back_to_positions(self):
        # Still navigable: every slice can be named, even if only by index.
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS)
            schema = _only_layer(fig)

            assert [point["x"] for point in schema["data"]] == ["0", "1", "2"]
        finally:
            plt.close(fig)

    def test_numeric_labels_stay_json_serializable(self):
        # A pandas column hands over numpy scalars, which `json.dumps`
        # refuses -- one of them would otherwise fail the whole figure.
        frame = pd.DataFrame({"units": UNITS, "year": [2021, 2022, 2023]})
        fig, ax = plt.subplots()
        try:
            ax.pie(frame["units"], labels=frame["year"])
            schema = _only_layer(fig)

            assert [point["x"] for point in schema["data"]] == [2021, 2022, 2023]
            json.dumps(schema)
        finally:
            plt.close(fig)


class TestSliceOrder:
    """Data index k and drawn wedge k describe the same slice."""

    @pytest.mark.parametrize(
        "kwargs",
        [
            {},
            {"startangle": 90},
            {"counterclock": False},
            {"explode": (0.1, 0, 0)},
        ],
        ids=["plain", "startangle", "clockwise", "exploded"],
    )
    def test_drawing_options_do_not_reorder_the_data(self, kwargs):
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS, labels=FRUIT, **kwargs)
            schema = _only_layer(fig)

            assert [point["x"] for point in schema["data"]] == FRUIT
            assert [point["y"] for point in schema["data"]] == [30, 50, 20]
        finally:
            plt.close(fig)

    def test_the_selector_resolves_to_one_element_per_slice(self):
        fig, ax = plt.subplots()
        try:
            wedges, _ = ax.pie(UNITS, labels=FRUIT)
            groups = _highlight_groups(fig)

            assert len(groups) == len(wedges)
            assert all(len(paths) == 1 for paths in groups)
        finally:
            plt.close(fig)

    def test_the_elements_are_in_slice_order(self):
        # The wedge colours come from the property cycle, so matching them
        # against the drawn wedges pins the order without depending on
        # geometry.
        from matplotlib.colors import to_hex

        fig, ax = plt.subplots()
        try:
            wedges, _ = ax.pie(UNITS, labels=FRUIT)
            expected = [to_hex(wedge.get_facecolor()) for wedge in wedges]
            groups = _highlight_groups(fig)

            drawn = [
                re.search(r"#[0-9a-f]{6}", paths[0].get("style", "")).group(0)
                for paths in groups
            ]
            assert drawn == expected
        finally:
            plt.close(fig)

    def test_a_shadow_is_not_a_slice(self):
        # `shadow=True` interleaves a `Shadow` patch behind every wedge; a
        # layer that counted those would report twice as many slices as the
        # selector resolves to.
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS, labels=FRUIT, shadow=True)
            schema = _only_layer(fig)

            assert len(schema["data"]) == 3
            assert len(_highlight_groups(fig)) == 3
        finally:
            plt.close(fig)


class TestNestedPie:
    """Two calls on one axes are two layers, each holding its own ring."""

    def test_each_ring_describes_only_its_own_slices(self):
        fig, ax = plt.subplots()
        try:
            ax.pie([30, 50, 20], labels=FRUIT, radius=1)
            ax.pie([10, 20, 30, 40], radius=0.7)
            outer, inner = _layers(fig)

            assert [point["y"] for point in outer["data"]] == [30, 50, 20]
            assert [point["y"] for point in inner["data"]] == [10, 20, 30, 40]
        finally:
            plt.close(fig)

    def test_the_two_rings_get_distinct_selectors(self):
        fig, ax = plt.subplots()
        try:
            ax.pie([30, 50, 20], labels=FRUIT, radius=1)
            ax.pie([10, 20, 30, 40], radius=0.7)

            # Rendering resolves each layer's `maidr='true'` placeholder to
            # its own id, so the two selectors must differ once resolved.
            maidr_obj = FigureManager.get_maidr(fig)
            schema = _stringify(maidr_obj._flatten_maidr())
            layers = schema["subplots"][0][0]["layers"]
            selectors = [layer["selectors"] for layer in layers]

            assert len(set(selectors)) == 2
            assert len(_highlight_groups(fig)) == 7
        finally:
            plt.close(fig)


class TestMixedFigure:
    """A pie alongside another plot type is still one layer of its own."""

    def test_a_pie_shares_a_figure_with_a_bar(self):
        fig, axs = plt.subplots(1, 2)
        try:
            axs[0].bar(["a", "b"], [1, 2])
            axs[1].pie(UNITS, labels=FRUIT)
            bar, pie = _layers(fig)

            assert bar["type"] == "bar"
            assert pie["type"] == "pie"
            assert [point["y"] for point in pie["data"]] == [30, 50, 20]
        finally:
            plt.close(fig)

    def test_each_panel_keeps_its_own_cell(self):
        fig, axs = plt.subplots(1, 2)
        try:
            axs[0].bar(["a", "b"], [1, 2])
            axs[1].pie(UNITS, labels=FRUIT)

            maidr_obj = FigureManager.get_maidr(fig)
            schema = _stringify(maidr_obj._flatten_maidr())
            cells = schema["subplots"][0]

            assert len(cells) == 2
            assert cells[1]["layers"][0]["type"] == "pie"
        finally:
            plt.close(fig)


class TestAxesPayload:
    """A pie names what a slice *is* and what it *measures*."""

    def test_authored_labels_are_used(self):
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS, labels=FRUIT)
            ax.set_xlabel("Fruit")
            ax.set_ylabel("Units")
            schema = _only_layer(fig)

            assert schema["axes"] == {
                "x": {"label": "Fruit"},
                "y": {"label": "Units"},
            }
        finally:
            plt.close(fig)

    def test_unlabelled_axes_read_as_english(self):
        # "X: Apples" is not a sentence; the generic pair of the base class
        # would be announced against every slice.
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS, labels=FRUIT)
            schema = _only_layer(fig)

            assert schema["axes"]["x"]["label"] == "Category"
            assert schema["axes"]["y"]["label"] == "Value"
        finally:
            plt.close(fig)

    def test_no_orientation_and_no_percentage(self):
        # Percentage is derived from the values by the renderer, and a pie
        # has no orientation to report.
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS, labels=FRUIT)
            schema = _only_layer(fig)

            assert "orientation" not in schema
            assert "percentage" not in schema
            assert all(set(point) == {"x", "y"} for point in schema["data"])
        finally:
            plt.close(fig)


class TestPiePlotDirectly:
    """The class built without the patch's help, which is all a direct
    caller can do."""

    def test_it_falls_back_to_the_fractions_matplotlib_kept(self):
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS, labels=FRUIT)
            plot = PiePlot(ax)
            data = _stringify(plot.schema)["data"]

            assert plot.type == PlotType.PIE
            # Without the call's own numbers, a slice's share of the whole is
            # all that is left to report.
            assert [point["y"] for point in data] == pytest.approx([0.3, 0.5, 0.2])
            assert [point["x"] for point in data] == FRUIT
        finally:
            plt.close(fig)

    def test_a_negative_size_is_rejected(self):
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS, labels=FRUIT)
            plot = PiePlot(ax, values=[30, -50, 20], labels=FRUIT)

            with pytest.raises(ValueError, match="non negative"):
                _ = plot.schema
        finally:
            plt.close(fig)
