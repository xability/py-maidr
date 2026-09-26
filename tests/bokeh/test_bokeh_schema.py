"""The MAIDR schema built from a Bokeh document model, glyph by glyph.

Each supported glyph is checked for the exact data it emits, its axes, its
type and orientation, against the shape the matplotlib and Plotly paths
emit for the same layer type.
"""

from __future__ import annotations

import json
import warnings

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("bokeh")

from bokeh.layouts import column, gridplot, row  # noqa: E402
from bokeh.models import (  # noqa: E402
    BooleanFilter,
    CDSView,
    ColumnDataSource,
    Div,
    FactorRange,
    GroupFilter,
    IndexFilter,
    TabPanel,
    Tabs,
)
from bokeh.plotting import figure  # noqa: E402
from bokeh.transform import dodge, linear_cmap  # noqa: E402

from maidr.bokeh.bokeh_maidr import BokehMaidr  # noqa: E402


def _plain(value):
    """Enum keys and values as the JSON the page receives."""
    return json.loads(json.dumps(value))


def _schema(model) -> dict:
    return _plain(BokehMaidr(model)._flatten_maidr())


def _layers(model) -> list[dict]:
    schema = _schema(model)
    return [
        layer
        for row_ in schema["subplots"]
        for cell in row_
        for layer in cell["layers"]
    ]


def _only(model) -> dict:
    layers = _layers(model)
    assert len(layers) == 1, layers
    return layers[0]


def _assert_canonical_axes(axes: dict) -> None:
    assert set(axes) <= {"x", "y", "z"}
    for config in axes.values():
        assert isinstance(config, dict)
        assert set(config) <= {"label", "min", "max", "tickStep", "format"}


class TestBars:
    def test_vbar_is_a_bar_in_drawn_order(self):
        p = figure(x_range=["a", "b", "c"], title="Sales", x_axis_label="Store")
        p.yaxis.axis_label = "Units"
        # Rows out of the range's order: arrowing must follow the axis.
        p.vbar(x=["c", "a", "b"], top=[3, 1, 2], width=0.9)

        layer = _only(p)

        assert layer["type"] == "bar"
        assert layer["orientation"] == "vert"
        assert layer["title"] == "Sales"
        assert layer["axes"] == {"x": {"label": "Store"}, "y": {"label": "Units"}}
        assert layer["data"] == [
            {"x": "a", "y": 1},
            {"x": "b", "y": 2},
            {"x": "c", "y": 3},
        ]
        _assert_canonical_axes(layer["axes"])

    def test_hbar_puts_the_magnitude_in_x(self):
        p = figure(y_range=["low", "high"])
        p.hbar(y=["low", "high"], right=[4, 9], height=0.5)

        layer = _only(p)

        assert layer["type"] == "bar"
        assert layer["orientation"] == "horz"
        assert layer["data"] == [{"x": 4, "y": "low"}, {"x": 9, "y": "high"}]

    def test_unlabelled_axes_fall_back_like_plotly(self):
        p = figure(x_range=["a"])
        p.vbar(x=["a"], top=[1], width=0.5)

        assert _only(p)["axes"] == {"x": {"label": "X"}, "y": {"label": "Y"}}

    def test_a_bar_off_the_baseline_reads_its_extent(self):
        p = figure(x_range=["a", "b"])
        p.vbar(x=["a", "b"], bottom=[1, 2], top=[4, 3], width=0.5)

        assert [point["y"] for point in _only(p)["data"]] == [3, 1]

    def test_a_legend_label_names_the_layer(self):
        p = figure(x_range=["a"])
        p.vbar(x=["a"], top=[1], width=0.5, legend_label="2024")

        assert _only(p)["name"] == "2024"

    def test_numeric_positions_read_left_to_right(self):
        p = figure()
        p.vbar(x=[3, 1, 2], top=[30, 10, 20], width=0.5)

        assert [point["x"] for point in _only(p)["data"]] == [1, 2, 3]

    def test_a_view_filter_drops_the_rows_it_hides(self):
        source = ColumnDataSource({"x": ["a", "b", "c"], "top": [1, 2, 3]})
        p = figure(x_range=["a", "b", "c"])
        p.vbar(
            x="x", top="top", width=0.5, source=source,
            view=CDSView(filter=IndexFilter([0, 2])),
        )

        assert _only(p)["data"] == [{"x": "a", "y": 1}, {"x": "c", "y": 3}]


    @pytest.mark.parametrize("view_filter", [IndexFilter(), BooleanFilter()])
    def test_a_filter_left_at_its_default_keeps_every_row(self, view_filter):
        # BokehJS reads ``indices=None`` / ``booleans=None`` as "all rows".
        source = ColumnDataSource({"x": ["a", "b"], "top": [1, 2]})
        p = figure(x_range=["a", "b"])
        p.vbar(
            x="x", top="top", width=0.5, source=source,
            view=CDSView(filter=view_filter),
        )

        assert _only(p)["data"] == [{"x": "a", "y": 1}, {"x": "b", "y": 2}]


class TestSegmentedBars:
    FRUITS = ["Apples", "Pears"]
    DATA = {"fruits": FRUITS, "2015": [2, 1], "2016": [5, 3]}

    def test_vbar_stack_is_a_stacked_bar_of_each_series_own_values(self):
        p = figure(x_range=self.FRUITS)
        p.vbar_stack(
            ["2015", "2016"], x="fruits", width=0.9, source=self.DATA,
            legend_label=["2015", "2016"],
        )

        layer = _only(p)

        assert layer["type"] == "stacked_bar"
        assert layer["orientation"] == "vert"
        # Each segment's own height, not the running total it is drawn at:
        # the core stacks them itself.
        assert layer["data"] == [
            [{"x": "Apples", "z": "2015", "y": 2}, {"x": "Pears", "z": "2015", "y": 1}],
            [{"x": "Apples", "z": "2016", "y": 5}, {"x": "Pears", "z": "2016", "y": 3}],
        ]

    def test_hbar_stack_is_horizontal(self):
        p = figure(y_range=self.FRUITS)
        p.hbar_stack(["2015", "2016"], y="fruits", height=0.9, source=self.DATA)

        layer = _only(p)

        assert layer["type"] == "stacked_bar"
        assert layer["orientation"] == "horz"
        assert layer["data"][1] == [
            {"x": 5, "z": "2016", "y": "Apples"},
            {"x": 3, "z": "2016", "y": "Pears"},
        ]

    def test_dodge_is_a_dodged_bar_ordered_left_to_right(self):
        source = ColumnDataSource(self.DATA)
        p = figure(x_range=self.FRUITS)
        # Added right group first; the drawn order is what is read.
        p.vbar(
            x=dodge("fruits", 0.2, range=p.x_range), top="2016", width=0.2,
            source=source, legend_label="2016",
        )
        p.vbar(
            x=dodge("fruits", -0.2, range=p.x_range), top="2015", width=0.2,
            source=source, legend_label="2015",
        )

        layer = _only(p)

        assert layer["type"] == "dodged_bar"
        assert [[point["z"] for point in row_] for row_ in layer["data"]] == [
            ["2015", "2015"],
            ["2016", "2016"],
        ]
        assert layer["data"][0] == [
            {"x": "Apples", "z": "2015", "y": 2},
            {"x": "Pears", "z": "2015", "y": 1},
        ]

    def test_nested_factors_are_a_dodged_bar(self):
        factors = [(f, y) for f in self.FRUITS for y in ["2015", "2016"]]
        p = figure(x_range=FactorRange(*factors))
        p.vbar(x=factors, top=[2, 5, 1, 3], width=0.9)

        layer = _only(p)

        assert layer["type"] == "dodged_bar"
        assert layer["data"] == [
            [{"x": "Apples", "z": "2015", "y": 2}, {"x": "Pears", "z": "2015", "y": 1}],
            [{"x": "Apples", "z": "2016", "y": 5}, {"x": "Pears", "z": "2016", "y": 3}],
        ]

    def test_a_ragged_nested_grid_falls_back_to_bars(self):
        factors = [("Apples", "2015"), ("Apples", "2016"), ("Pears", "2015")]
        p = figure(x_range=FactorRange(*factors))
        p.vbar(x=factors, top=[2, 5, 1], width=0.9)

        layer = _only(p)

        assert layer["type"] == "bar"
        assert [point["x"] for point in layer["data"]] == [
            "Apples, 2015",
            "Apples, 2016",
            "Pears, 2015",
        ]


class TestHistogram:
    def test_quad_is_a_hist_in_the_matplotlib_shape(self):
        p = figure()
        p.quad(top=[1, 3, 2], bottom=0, left=[0, 1, 2], right=[1, 2, 3])

        layer = _only(p)

        assert layer["type"] == "hist"
        assert layer["orientation"] == "vert"
        assert layer["data"][1] == {
            "y": 3, "x": 1.5, "xMin": 1.0, "xMax": 2.0, "yMin": 0, "yMax": 3,
        }

    def test_quads_sharing_a_left_edge_are_a_sideways_histogram(self):
        p = figure()
        p.quad(left=0, right=[4, 6], bottom=[0, 1], top=[1, 2])

        layer = _only(p)

        assert layer["orientation"] == "horz"
        assert layer["data"][0] == {
            "x": 4, "y": 0.5, "yMin": 0.0, "yMax": 1.0, "xMin": 0, "xMax": 4,
        }


class TestLines:
    def test_lines_are_one_layer_with_a_row_per_series(self):
        p = figure(x_axis_label="t", y_axis_label="v")
        p.line([1, 2, 3], [1, 2, 3], legend_label="up")
        p.line([1, 2, 3], [8, 7, 6], legend_label="down")

        layer = _only(p)

        assert layer["type"] == "line"
        assert layer["axes"] == {"x": {"label": "t"}, "y": {"label": "v"}}
        assert layer["data"] == [
            [{"x": x, "y": y, "z": "up"} for x, y in [(1, 1), (2, 2), (3, 3)]],
            [{"x": x, "y": y, "z": "down"} for x, y in [(1, 8), (2, 7), (3, 6)]],
        ]

    def test_a_legend_title_is_the_z_axis(self):
        p = figure()
        p.line([1, 2], [1, 2], legend_label="up")
        p.legend.title = "Direction"

        assert _only(p)["axes"]["z"] == {"label": "Direction"}

    def test_multi_line_is_a_row_per_path(self):
        p = figure()
        p.multi_line([[1, 2], [1, 2]], [[1, 2], [2, 1]])

        layer = _only(p)

        assert layer["type"] == "line"
        assert layer["data"] == [
            [{"x": 1, "y": 1}, {"x": 2, "y": 2}],
            [{"x": 1, "y": 2}, {"x": 2, "y": 1}],
        ]

    def test_a_missing_value_is_a_gap_not_nan(self):
        p = figure()
        p.line([1, 2, 3], [1, np.nan, 3])

        data = _only(p)["data"][0]

        assert data[1] == {"x": 2, "y": None}

    def test_dates_are_iso_strings(self):
        p = figure(x_axis_type="datetime")
        p.line(pd.date_range("2024-01-01", periods=3), [1, 2, 3])

        assert [point["x"] for point in _only(p)["data"][0]] == [
            "2024-01-01",
            "2024-01-02",
            "2024-01-03",
        ]

    def test_a_date_column_shares_one_unit(self):
        p = figure(x_axis_type="datetime")
        p.line([pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-01T12:00")], [1, 2])

        assert [point["x"] for point in _only(p)["data"][0]] == [
            "2024-01-01T00:00",
            "2024-01-01T12:00",
        ]

    def test_epoch_milliseconds_on_a_datetime_axis_are_dates(self):
        p = figure(x_axis_type="datetime")
        p.line([1704067200000, 1704153600000], [1, 2])

        assert [point["x"] for point in _only(p)["data"][0]] == [
            "2024-01-01",
            "2024-01-02",
        ]

    def test_step_carries_its_direction(self):
        p = figure()
        p.step([1, 2, 3], [1, 3, 2], mode="after")

        layer = _only(p)

        assert layer["type"] == "step"
        assert layer["stepDirection"] == "hv"
        assert layer["data"] == [[{"x": 1, "y": 1}, {"x": 2, "y": 3}, {"x": 3, "y": 2}]]

    @pytest.mark.parametrize(
        ("mode", "direction"), [("before", "vh"), ("center", "mid")]
    )
    def test_each_step_mode_maps_to_a_direction(self, mode, direction):
        p = figure()
        p.step([1, 2], [1, 2], mode=mode)

        assert _only(p)["stepDirection"] == direction


class TestAreas:
    def test_varea_is_an_area(self):
        p = figure()
        p.varea(x=[1, 2, 3], y1=0, y2=[1, 2, 3])

        layer = _only(p)

        assert layer["type"] == "area"
        assert layer["data"] == [[{"x": 1, "y": 1}, {"x": 2, "y": 2}, {"x": 3, "y": 3}]]

    def test_varea_stack_is_a_stacked_area_of_each_band_own_values(self):
        p = figure()
        p.varea_stack(
            ["s1", "s2"], x="x", source={"x": [1, 2], "s1": [1, 2], "s2": [3, 4]},
            legend_label=["s1", "s2"],
        )

        layer = _only(p)

        assert layer["type"] == "stacked_area"
        assert layer["data"] == [
            [{"x": 1, "y": 1.0, "z": "s1"}, {"x": 2, "y": 2.0, "z": "s1"}],
            [{"x": 1, "y": 3.0, "z": "s2"}, {"x": 2, "y": 4.0, "z": "s2"}],
        ]


class TestScatter:
    def test_scatter_is_a_point_layer(self):
        p = figure()
        p.scatter([1, 2, 3], [4, 5, 6], legend_label="obs")

        layer = _only(p)

        assert layer["type"] == "point"
        assert layer["name"] == "obs"
        assert layer["data"] == [{"x": 1, "y": 4}, {"x": 2, "y": 5}, {"x": 3, "y": 6}]

    def test_circle_is_a_point_layer_too(self):
        p = figure()
        p.circle([1], [2], radius=0.1)

        assert _only(p)["type"] == "point"

    def test_a_group_filter_keeps_its_group(self):
        source = ColumnDataSource(
            {"x": [1, 2, 3], "y": [4, 5, 6], "g": ["a", "b", "a"]}
        )
        p = figure()
        p.scatter(
            "x", "y", source=source,
            view=CDSView(filter=GroupFilter(column_name="g", group="a")),
        )

        assert _only(p)["data"] == [{"x": 1, "y": 4}, {"x": 3, "y": 6}]


class TestHeatmap:
    def _heat(self, color_bar_title="Rate"):
        frame = pd.DataFrame(
            {
                "x": ["a", "b", "a", "b"],
                "y": ["u", "u", "v", "v"],
                "rate": [1.0, 2.0, 3.0, 4.0],
            }
        )
        p = figure(x_range=["a", "b"], y_range=["u", "v"])
        r = p.rect(
            x="x", y="y", width=1, height=1, source=frame,
            fill_color=linear_cmap("rate", "Viridis256", 1, 4),
        )
        if color_bar_title:
            p.add_layout(r.construct_color_bar(title=color_bar_title), "right")
        return p

    def test_rect_through_a_color_mapper_is_a_heatmap_top_row_first(self):
        layer = _only(self._heat())

        assert layer["type"] == "heat"
        assert layer["axes"]["z"] == {"label": "Rate"}
        # Emitted top row first, as the other paths emit it; ``v`` is the
        # upper factor of the y range.
        assert layer["data"] == {
            "x": ["a", "b"],
            "y": ["v", "u"],
            "points": [[3.0, 4.0], [1.0, 2.0]],
        }
        _assert_canonical_axes(layer["axes"])

    def test_without_a_color_bar_the_field_names_z(self):
        assert _only(self._heat(color_bar_title=None))["axes"]["z"] == {"label": "rate"}

    def test_a_plain_rect_is_not_a_heatmap(self):
        p = figure()
        p.rect(x=[1], y=[1], width=1, height=1)

        with pytest.warns(UserWarning, match="Rect"):
            schema = BokehMaidr(p)._flatten_maidr()

        assert schema is None


class TestLayouts:
    def _bar(self, title):
        p = figure(x_range=["a"], title=title)
        p.vbar(x=["a"], top=[1], width=0.5)
        return p

    def _grid_titles(self, model) -> list[list[list[str]]]:
        return [
            [[layer["title"] for layer in cell["layers"]] for cell in row_]
            for row_ in _schema(model)["subplots"]
        ]

    def test_gridplot_places_each_figure_in_its_cell(self):
        grid = gridplot([[self._bar("a"), self._bar("b")], [None, self._bar("c")]])

        assert self._grid_titles(grid) == [[["a"], ["b"]], [[], ["c"]]]

    def test_row_of_columns_is_a_grid(self):
        layout = row(column(self._bar("a"), self._bar("c")), self._bar("b"))

        assert self._grid_titles(layout) == [[["a"], ["b"]], [["c"], []]]

    def test_widgets_take_no_cell(self):
        layout = column(Div(text="Heading"), self._bar("a"))

        assert self._grid_titles(layout) == [[["a"]]]

    def test_tabs_read_the_active_panel_and_say_so(self):
        tabs = Tabs(
            tabs=[
                TabPanel(child=self._bar("first"), title="One"),
                TabPanel(child=self._bar("second"), title="Two"),
            ],
            active=1,
        )

        with pytest.warns(UserWarning, match=r"active panel.*\(One\)"):
            titles = self._grid_titles(tabs)

        assert titles == [[["second"]]]


class TestUnsupported:
    def test_an_unsupported_glyph_is_skipped_with_a_warning(self):
        p = figure()
        p.line([1, 2], [1, 2])
        p.wedge(x=[1], y=[1], radius=1, start_angle=0, end_angle=1)

        with pytest.warns(UserWarning, match="Wedge"):
            layers = _layers(p)

        assert [layer["type"] for layer in layers] == ["line"]

    def test_nothing_supported_still_renders_the_plot(self):
        p = figure()
        p.wedge(x=[1], y=[1], radius=1, start_angle=0, end_angle=1)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            maidr_ = BokehMaidr(p)
            html = str(maidr_._create_html_tag(use_iframe=False, use_cdn=True))

        assert "var schema = null;" in html
        assert "Bokeh.embed.embed_item" in html

    def test_the_warning_names_the_callers_line(self):
        p = figure()
        p.wedge(x=[1], y=[1], radius=1, start_angle=0, end_angle=1)

        with pytest.warns(UserWarning) as record:
            BokehMaidr(p)

        assert all(w.filename == __file__ for w in record)
