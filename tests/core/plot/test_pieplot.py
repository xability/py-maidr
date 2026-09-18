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

Slice order is walking order, not draw order. MAIDR steps Right through a
pie clockwise, and ``Axes.pie`` draws counterclockwise unless ``counterclock``
is False, so a pie drawn with the defaults is emitted in reverse: the
``CLOCKWISE_*`` constants below are ``FRUIT`` and ``UNITS`` as such a pie
reads them.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import json  # noqa: E402
import logging  # noqa: E402
import re  # noqa: E402
import warnings  # noqa: E402

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from lxml import etree  # noqa: E402

import maidr  # noqa: E402  # activates patches
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.core.plot.pieplot import PiePlot  # noqa: E402
from maidr.exception import ExtractionError  # noqa: E402
from maidr.patch.pieplot import _resolve  # noqa: E402


#: A pie whose sizes sum far above 1, so matplotlib normalizes them away.
FRUIT = ["Apples", "Bananas", "Cherries"]
UNITS = [30, 50, 20]

#: The same slices as a pie drawn with matplotlib's defaults reads them:
#: drawn counterclockwise, walked clockwise, so the last drawn is the first read.
CLOCKWISE_FRUIT = list(reversed(FRUIT))
CLOCKWISE_UNITS = list(reversed(UNITS))


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


class TestValuesSurviveNormalization:
    """The caller's magnitudes, not the fractions matplotlib kept."""

    def test_counts_are_reported_as_counts(self):
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS, labels=FRUIT)
            schema = _only_layer(fig)

            assert [point["y"] for point in schema["data"]] == CLOCKWISE_UNITS
        finally:
            plt.close(fig)

    def test_ndarray_sizes_are_reported_as_given(self):
        fig, ax = plt.subplots()
        try:
            ax.pie(np.array(UNITS), labels=FRUIT)
            schema = _only_layer(fig)

            assert [point["y"] for point in schema["data"]] == CLOCKWISE_UNITS
        finally:
            plt.close(fig)

    def test_series_sizes_are_reported_as_given(self):
        fig, ax = plt.subplots()
        try:
            ax.pie(pd.Series(UNITS), labels=FRUIT)
            schema = _only_layer(fig)

            assert [point["y"] for point in schema["data"]] == CLOCKWISE_UNITS
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
                {"x": "Cherries", "y": 20},
                {"x": "Bananas", "y": 50},
                {"x": "Apples", "y": 30},
            ]
        finally:
            plt.close(fig)

    def test_sizes_below_one_are_left_alone(self):
        # Shares of a whole are already the numbers the caller meant.
        fig, ax = plt.subplots()
        try:
            ax.pie([0.25, 0.75], labels=["Half", "Rest"])
            schema = _only_layer(fig)

            assert [point["y"] for point in schema["data"]] == [0.75, 0.25]
        finally:
            plt.close(fig)

    def test_an_unnormalized_partial_pie_keeps_its_gap(self):
        # `normalize=False` draws a pie that does not close, and only accepts
        # sizes summing to at most 1. The sizes are still the caller's.
        fig, ax = plt.subplots()
        try:
            ax.pie([0.2, 0.3], labels=["Done", "Started"], normalize=False)
            schema = _only_layer(fig)

            assert [point["y"] for point in schema["data"]] == [0.3, 0.2]
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
            assert [point["y"] for point in schema["data"]] == CLOCKWISE_UNITS
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
            assert [point["y"] for point in schema["data"]] == CLOCKWISE_UNITS
            assert [point["x"] for point in schema["data"]] == CLOCKWISE_FRUIT
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

            assert [point["x"] for point in schema["data"]] == CLOCKWISE_FRUIT
        finally:
            plt.close(fig)

    def test_an_unlabeled_pie_falls_back_to_positions(self):
        # Still navigable: every slice can be named, even if only by index.
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS)
            schema = _only_layer(fig)

            assert [point["x"] for point in schema["data"]] == ["2", "1", "0"]
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

            assert [point["x"] for point in schema["data"]] == [2023, 2022, 2021]
            json.dumps(schema)
        finally:
            plt.close(fig)


class TestSliceOrder:
    """Data index k and element k describe the same slice, walked clockwise.

    MAIDR walks a pie clockwise: Right steps to the next slice round the
    dial, the audio pans to where the slice sits, and ``p`` names its clock
    position, all on the assumption that data order runs clockwise from the
    start. ``Axes.pie`` draws counterclockwise by default, so the order it drew
    is the order a reader would walk backwards -- the slices are turned
    round, and the document is put in the same order so the selector still
    lands on the slice being read.
    """

    def test_a_default_pie_is_walked_against_its_draw_order(self):
        # Drawn counterclockwise from 3 o'clock: Apples, then Bananas above it,
        # then Cherries. Clockwise from the same point that is Cherries,
        # Bananas, Apples.
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS, labels=FRUIT)
            schema = _only_layer(fig)

            assert [point["x"] for point in schema["data"]] == CLOCKWISE_FRUIT
            assert [point["y"] for point in schema["data"]] == CLOCKWISE_UNITS
        finally:
            plt.close(fig)

    def test_a_clockwise_pie_is_walked_as_drawn(self):
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS, labels=FRUIT, counterclock=False)
            schema = _only_layer(fig)

            assert [point["x"] for point in schema["data"]] == FRUIT
            assert [point["y"] for point in schema["data"]] == UNITS
        finally:
            plt.close(fig)

    def test_counterclock_is_read_off_the_call_by_position(self):
        # `counterclock` is the eleventh positional parameter of `Axes.pie`;
        # a caller who passes it that way must be read the same as one who
        # names it. Matplotlib 3.10 deprecates passing the parameters before
        # it positionally and means to refuse them in 3.12; once it does, no
        # caller can reach this path and there is nothing left to pin.
        fig, ax = plt.subplots()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                try:
                    ax.pie(UNITS, None, FRUIT, None, None, 0.6, False, 1.1, 0, 1, False)
                except TypeError:
                    pytest.skip(
                        "this matplotlib no longer takes counterclock by position"
                    )
            schema = _only_layer(fig)

            assert [point["x"] for point in schema["data"]] == FRUIT
        finally:
            plt.close(fig)

    def test_an_explicit_none_is_drawn_clockwise_and_read_that_way(self):
        # `Axes.pie` tests `counterclock` for truth, so `None` draws clockwise
        # exactly as `False` does. Reading it as "not passed" would turn a
        # clockwise pie round and walk it backwards -- the very fault the
        # reversal exists to fix.
        fig, ax = plt.subplots()
        try:
            wedges, _ = ax.pie(UNITS, labels=FRUIT, counterclock=None)
            schema = _only_layer(fig)

            # Drawn clockwise: each wedge ends where the next begins, going
            # down through the angles.
            assert wedges[1].theta2 == pytest.approx(wedges[0].theta1)
            assert [point["x"] for point in schema["data"]] == FRUIT
        finally:
            plt.close(fig)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {},
            {"startangle": 90},
            {"explode": (0.1, 0, 0)},
            {"shadow": True},
            {"counterclock": False},
        ],
        ids=["plain", "startangle", "exploded", "shadowed", "clockwise"],
    )
    def test_drawing_options_leave_the_walk_alone(self, kwargs):
        # Where the pie starts and how the wedges are dressed up does not
        # change which way round they were laid out, so the walk is decided
        # by the drawing direction alone.
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS, labels=FRUIT, **kwargs)
            schema = _only_layer(fig)

            expected = FRUIT if kwargs.get("counterclock") is False else CLOCKWISE_FRUIT
            assert [point["x"] for point in schema["data"]] == expected
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

    @pytest.mark.parametrize(
        "kwargs",
        [{}, {"shadow": True}, {"counterclock": False}],
        ids=["reversed", "reversed-with-shadows", "as-drawn"],
    )
    def test_the_elements_are_in_walking_order(self, kwargs):
        # The wedge colors come from the property cycle, so matching them
        # against the drawn wedges pins the order without depending on
        # geometry. The document order has to be the data order: element k
        # is what the frontend highlights for slice k.
        from matplotlib.colors import to_hex

        fig, ax = plt.subplots()
        try:
            wedges, _ = ax.pie(UNITS, labels=FRUIT, **kwargs)
            schema = _only_layer(fig)
            color_of = dict(zip(FRUIT, (to_hex(w.get_facecolor()) for w in wedges)))
            expected = [color_of[point["x"]] for point in schema["data"]]
            groups = _highlight_groups(fig)

            drawn = [
                re.search(r"#[0-9a-f]{6}", paths[0].get("style", "")).group(0)
                for paths in groups
            ]
            assert drawn == expected
        finally:
            plt.close(fig)

    def test_reordering_leaves_the_rest_of_the_document_alone(self):
        # The wedge groups swap places among themselves; nothing else in the
        # SVG moves, and no placeholder is left behind.
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS, labels=FRUIT)
            maidr_obj = FigureManager.get_maidr(fig)
            html = str(maidr_obj._create_html_tag().get_html_string())
            svg = re.search(r"<svg.*</svg>", html, re.S).group(0)
            root = etree.fromstring(svg.encode())

            groups = root.xpath('//*[local-name()="g"][@maidr]')
            parents = {group.getparent() for group in groups}
            assert len(parents) == 1
            assert "maidr slot" not in svg
            # Three wedges and three labels, drawn on the one axes.
            axes_group = parents.pop()
            texts = axes_group.xpath('./*[local-name()="g"][starts-with(@id, "text")]')
            assert len(texts) == 3
            # Wedges are drawn before the text; the reorder keeps them there.
            children = list(axes_group)
            assert max(children.index(g) for g in groups) < min(
                children.index(t) for t in texts
            )
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

            assert [point["y"] for point in outer["data"]] == CLOCKWISE_UNITS
            assert [point["y"] for point in inner["data"]] == [40, 30, 20, 10]
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
            assert [point["y"] for point in pie["data"]] == CLOCKWISE_UNITS
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

    def test_unlabeled_axes_read_as_english(self):
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
            assert [point["y"] for point in data] == pytest.approx([0.2, 0.5, 0.3])
            assert [point["x"] for point in data] == CLOCKWISE_FRUIT
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

    def test_an_axes_with_no_wedges_is_an_extraction_failure(self):
        # The empty-pie rule below is about a call that legitimately drew
        # nothing, which the patch reports by handing over an empty wedge
        # list. A layer built with no list at all falls back to scanning the
        # axes, and finding nothing there means the pie it was built for
        # cannot be found -- still an error, and it must stay one.
        fig, ax = plt.subplots()
        try:
            ax.bar(["a", "b"], [1, 2])

            with pytest.raises(ExtractionError):
                _ = PiePlot(ax).schema
        finally:
            plt.close(fig)


class TestEmptyPie:
    """``ax.pie([])`` is a legal call, and an empty layer on the wire.

    The figure is registered by the time the schema is built, so raising on
    an empty pie takes the whole figure down with it -- including any working
    plot drawn beside it, which no static-image fallback rescues. An empty
    layer reaches the wire instead, which is the rule
    ``PlotlyPiePlot._slices`` already follows on the plotly side.
    """

    def test_an_empty_pie_is_an_empty_layer(self):
        fig, ax = plt.subplots()
        try:
            ax.pie([])
            schema = _only_layer(fig)

            assert schema["type"] == "pie"
            assert schema["data"] == []
        finally:
            plt.close(fig)

    def test_a_bar_beside_an_empty_pie_survives(self):
        fig, axs = plt.subplots(1, 2)
        try:
            axs[0].bar(["a", "b"], [1, 2])
            axs[1].pie([])
            bar, pie = _layers(fig)

            assert [point["y"] for point in bar["data"]] == [1, 2]
            assert pie["data"] == []
        finally:
            plt.close(fig)

    def test_the_whole_figure_still_renders(self):
        # The error used to fire inside `_flatten_maidr`, well past the point
        # where the figure could be dropped, so nothing below `render()`
        # proves the fix.
        fig, axs = plt.subplots(1, 2)
        try:
            axs[0].bar(["a", "b"], [1, 2])
            axs[1].pie([])

            schema = _stringify(FigureManager.get_maidr(fig)._flatten_maidr())
            cells = schema["subplots"][0]
            html = maidr.render(fig)

            assert [cell["layers"][0]["type"] for cell in cells] == ["bar", "pie"]
            assert "<svg" in str(html)
            json.dumps(schema)
        finally:
            plt.close(fig)


class TestDonut:
    """``wedgeprops={"width": ...}`` cuts the middle out and nothing else.

    A donut is a pie whose wedges are annuli. The data behind them is
    untouched, so the layer must be identical to the same call without it.
    """

    def test_a_donut_reports_the_callers_magnitudes(self):
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS, labels=FRUIT, wedgeprops={"width": 0.4})
            schema = _only_layer(fig)

            assert [point["x"] for point in schema["data"]] == CLOCKWISE_FRUIT
            assert [point["y"] for point in schema["data"]] == CLOCKWISE_UNITS
        finally:
            plt.close(fig)

    def test_a_donut_still_has_one_element_per_slice(self):
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS, labels=FRUIT, wedgeprops={"width": 0.4})
            groups = _highlight_groups(fig)

            assert len(groups) == 3
            assert all(len(paths) == 1 for paths in groups)
        finally:
            plt.close(fig)


class TestZeroValuedSlice:
    """A zero-sized slice is still a slice.

    ``ax.pie([0, 5, 5])`` draws a `Wedge` spanning no angle at all for the
    zero. Matplotlib keeps it -- it is in the returned wedge list and in
    ``ax.patches`` -- so dropping it here would leave the data one entry short
    of the elements the selector resolves to, landing every later slice on the
    wrong wedge.
    """

    def test_the_zero_slice_is_kept_in_place(self):
        fig, ax = plt.subplots()
        try:
            wedges, _ = ax.pie([0, 5, 5], labels=FRUIT)
            schema = _only_layer(fig)

            assert len(wedges) == 3
            assert [point["y"] for point in schema["data"]] == [5, 5, 0]
            assert [point["x"] for point in schema["data"]] == CLOCKWISE_FRUIT
        finally:
            plt.close(fig)

    def test_the_data_and_the_elements_stay_aligned(self):
        fig, ax = plt.subplots()
        try:
            ax.pie([0, 5, 5], labels=FRUIT)
            schema = _only_layer(fig)

            assert len(_highlight_groups(fig)) == len(schema["data"])
        finally:
            plt.close(fig)


class TestDataColumnNames:
    """``ax.pie("sales", labels="fruit", data=df)`` names columns, not values.

    ``Axes.pie`` sits behind matplotlib's ``_preprocess_data``, and the patch
    wraps the outside of that decorator, so it sees the names. It looks them
    up the way matplotlib does.
    """

    def test_column_names_are_resolved_against_data(self):
        frame = pd.DataFrame({"units": UNITS, "fruit": FRUIT})
        fig, ax = plt.subplots()
        try:
            ax.pie("units", labels="fruit", data=frame)
            schema = _only_layer(fig)

            assert [point["x"] for point in schema["data"]] == CLOCKWISE_FRUIT
            assert [point["y"] for point in schema["data"]] == CLOCKWISE_UNITS
        finally:
            plt.close(fig)

    @pytest.mark.parametrize(
        "data",
        [
            pytest.param(pd.DataFrame({"units": UNITS}), id="KeyError"),
            pytest.param(np.array(UNITS), id="IndexError"),
            pytest.param([30, 50, 20], id="TypeError-list"),
            pytest.param(object(), id="TypeError-unindexable"),
        ],
    )
    def test_an_unresolvable_name_is_passed_through_unchanged(self, data):
        # Matplotlib treats a name it cannot look up as a plain value, and so
        # must this: raising instead would fail a pie matplotlib drew
        # perfectly well. One case per way an indexable object says "not this
        # key" -- the three, and only the three, `_resolve` catches. A numpy
        # array is what raises `IndexError`; a plain list raises `TypeError`,
        # so it cannot stand in for that arm.
        assert _resolve("missing_col", data) == "missing_col"

    def test_a_name_is_only_looked_up_when_there_is_data_to_look_it_up_in(self):
        assert _resolve("units", None) == "units"

    def test_an_unresolvable_name_still_describes_the_pie_it_drew(self):
        # The end-to-end reach of the fallback is narrow: matplotlib rejects
        # an unresolved `labels` whose length is not the slice count, so the
        # name has to be as long as the pie is wide. It then labels the wedges
        # by its own characters, and the layer has to report those -- the
        # slices really are named "a", "b", "c" on the page.
        frame = pd.DataFrame({"units": UNITS, "fruit": FRUIT})
        fig, ax = plt.subplots()
        try:
            ax.pie("units", labels="abc", data=frame)
            schema = _only_layer(fig)

            assert [point["x"] for point in schema["data"]] == ["c", "b", "a"]
            assert [point["y"] for point in schema["data"]] == CLOCKWISE_UNITS
        finally:
            plt.close(fig)


class TestMismatchDiagnostic:
    """The values/wedges mismatch is logged, and the log is reachable.

    ``maidr.patch.pieplot.pie`` suppresses warnings only for the duration of
    the ``Axes.pie`` call it wraps -- the same scope
    ``maidr.patch.common.common`` uses on every other plot type -- so nothing
    the patch installs is still in front of ``render()`` when the diagnostic
    is emitted.
    """

    def test_the_mismatch_is_reported_through_logging(self, caplog):
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS, labels=FRUIT)
            plot = PiePlot(ax, values=[30, 50], labels=FRUIT)

            with caplog.at_level(logging.WARNING, logger="maidr.core.plot.pieplot"):
                data = _stringify(plot.schema)["data"]

            assert "2 values for 3 wedges" in caplog.text
            # The fallback still happened: shares of the whole, not 30/50/20.
            assert [point["y"] for point in data] == pytest.approx([0.2, 0.5, 0.3])
        finally:
            plt.close(fig)

    def test_the_patch_leaves_no_filter_behind_to_swallow_it(self):
        # The diagnostic above is only reachable because `Axes.pie` no longer
        # leaves an "ignore" filter installed behind it. Pin that: a warning
        # raised after the pie is drawn still reaches the caller.
        fig, ax = plt.subplots()
        try:
            ax.pie(UNITS, labels=FRUIT)

            with warnings.catch_warnings(record=True) as caught:
                warnings.warn("heard after the pie", UserWarning)

            assert [str(w.message) for w in caught] == ["heard after the pie"]
        finally:
            plt.close(fig)
