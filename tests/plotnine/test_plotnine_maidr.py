"""A ``ggplot`` read from plotnine's own layer data (#814).

Each geom's reading is pinned against the values plotnine computed, and each
selector is resolved against the SVG the same render wrote, which is the only
way to check that it names the element its point describes.
"""

from __future__ import annotations

import json
import re
import warnings

import numpy as np
import pandas as pd
import pytest

plotnine = pytest.importorskip("plotnine")

from lxml import etree  # noqa: E402
from lxml.cssselect import CSSSelector  # noqa: E402
from plotnine import (  # noqa: E402
    aes,
    coord_flip,
    facet_grid,
    facet_wrap,
    geom_bar,
    geom_boxplot,
    geom_col,
    geom_histogram,
    geom_jitter,
    geom_line,
    geom_point,
    geom_smooth,
    geom_tile,
    geom_violin,
    ggplot,
    labs,
    scale_x_log10,
    scale_y_log10,
)

import maidr  # noqa: E402
from maidr import api  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.plotnine import PlotnineMaidr, is_plotnine_plot  # noqa: E402

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _read(plot) -> tuple[dict, etree._Element]:
    """Render ``plot`` once; return the schema it embeds and its SVG."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        html = str(PlotnineMaidr(plot).render(use_cdn=False))
    svg = re.search(r"<svg.*?</svg>", html, re.S)
    assert svg is not None, "no chart was rendered"
    root = etree.fromstring(svg.group(0).encode(), etree.XMLParser(recover=True))
    for element in root.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]
    return json.loads(root.get("maidr")), root


def _layers(schema: dict) -> list[dict]:
    return [layer for row in schema["subplots"] for cell in row for layer in cell["layers"]]


def _only(schema: dict) -> dict:
    (layer,) = _layers(schema)
    return layer


def _one(root, selector: str):
    (found,) = CSSSelector(selector)(root)
    return found


def _points_of(path) -> np.ndarray:
    """The vertices of an SVG ``path``, in the SVG's own coordinates."""
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", path.get("d"))]
    return np.array(numbers).reshape(-1, 2)


def _centre(path) -> tuple[float, float]:
    xy = _points_of(path)
    return float(xy[:, 0].mean()), float(xy[:, 1].mean())


def _warnings_of(plot) -> list[str]:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        PlotnineMaidr(plot)
    return [str(w.message) for w in caught if "maidr" in str(w.message)]


# --------------------------------------------------------------------------
# Data
# --------------------------------------------------------------------------

#: Rows deliberately not in category order, so reading order and drawing
#: order differ.
SALES = pd.DataFrame({"c": ["b", "a", "c"], "v": [5.0, 3.0, 2.0]})

SPLIT = pd.DataFrame(
    {
        "cat": ["a", "a", "b", "b", "c"],
        "g": ["p", "q", "p", "q", "q"],
        "v": [1.0, 2.0, 3.0, 4.0, 5.0],
    }
)

XY = pd.DataFrame(
    {
        "x": [1.0, 2.0, 3.0, 4.0, 5.0],
        "y": [2.0, 4.0, 3.0, 5.0, 1.0],
        "g": ["p", "p", "q", "q", "q"],
    }
)

BOXES = pd.DataFrame(
    {"g": ["p"] * 7 + ["q"] * 5, "y": [1, 2, 3, 4, 5, 20, -10, 2, 3, 4, 5, 6]}
)

TILES = pd.DataFrame(
    {"a": ["x", "x", "y", "y"], "b": ["u", "v", "u", "v"], "z": [1, 2, 3, 4]}
)


# --------------------------------------------------------------------------
# Dispatch and isolation
# --------------------------------------------------------------------------


def test_the_probe_names_a_ggplot_and_nothing_else():
    plot = ggplot(SALES, aes("c", "v")) + geom_col()

    assert is_plotnine_plot(plot)
    assert api._is_plotnine_plot(plot)
    assert not is_plotnine_plot(plot.draw())
    assert not is_plotnine_plot(object())


def test_render_save_html_and_close_take_a_ggplot(tmp_path):
    plot = ggplot(SALES, aes("c", "v")) + geom_col()

    assert "maidr=" in str(maidr.render(plot, use_cdn=False))
    written = maidr.save_html(plot, str(tmp_path / "chart.html"), use_cdn=False)
    assert "maidr=" in (tmp_path / "chart.html").read_text(encoding="utf-8")
    assert written == str(tmp_path / "chart.html")
    assert maidr.close(plot) is None


def test_a_shiny_render_function_may_return_a_ggplot():
    """``@render_maidr`` checks its value before ``maidr.render`` sees it."""
    pytest.importorskip("shiny")
    from maidr.widget.shiny import _check_supported

    _check_supported(ggplot(SALES, aes("c", "v")) + geom_col(), "chart")


def test_the_callers_ggplot_is_left_as_it_was():
    plot = ggplot(SALES, aes("c", "v")) + geom_col()
    PlotnineMaidr(plot)

    assert "draw_group" not in vars(plot.layers[0].geom)
    assert "map" not in vars(plot.layers)
    # And it reads the same the second time.
    assert _only(_read(plot)[0])["data"] == _only(_read(plot)[0])["data"]


def test_the_scatter_patch_does_not_register_a_second_reading():
    """``geom_point`` draws through ``Axes.scatter``, which maidr patches."""
    reader = PlotnineMaidr(ggplot(XY, aes("x", "y")) + geom_point())

    assert reader.figure not in FigureManager.figs
    assert [layer["type"] for layer in _layers(reader._flatten_maidr())] == ["point"]


# --------------------------------------------------------------------------
# Bars
# --------------------------------------------------------------------------


def test_a_column_chart_reads_left_to_right_and_outlines_each_bar():
    schema, root = _read(
        ggplot(SALES, aes("c", "v")) + geom_col() + labs(title="Sales", y="Units")
    )
    layer = _only(schema)

    assert layer["type"] == "bar"
    assert layer["title"] == "Sales"
    assert layer["axes"] == {"x": {"label": "c"}, "y": {"label": "Units"}}
    assert layer["data"] == [
        {"x": "a", "y": 3.0},
        {"x": "b", "y": 5.0},
        {"x": "c", "y": 2.0},
    ]
    # One selector per bar, each naming the bar drawn at that category.
    centres = [_centre(_one(root, s))[0] for s in layer["selectors"]]
    assert centres == sorted(centres) and len(set(centres)) == 3


def test_a_count_is_the_count_plotnine_computed():
    layer = _only(_read(ggplot(SPLIT, aes("cat")) + geom_bar())[0])

    assert layer["data"] == [
        {"x": "a", "y": 2.0},
        {"x": "b", "y": 2.0},
        {"x": "c", "y": 1.0},
    ]
    assert layer["axes"]["y"]["label"] == "count"


def test_a_fill_on_the_x_variable_colours_the_bars_without_splitting_them():
    layer = _only(_read(ggplot(SALES, aes("c", "v", fill="c")) + geom_col())[0])

    assert layer["type"] == "bar"
    assert [point["y"] for point in layer["data"]] == [3.0, 5.0, 2.0]


def test_a_stack_is_read_bottom_first_with_each_segments_own_value():
    schema, root = _read(ggplot(SPLIT, aes("cat", "v", fill="g")) + geom_col())
    layer = _only(schema)

    assert layer["type"] == "stacked_bar"
    assert layer["axes"]["z"] == {"label": "g"}
    # plotnine stacks the first level on top, so `q` is the bottom series.
    # `c` has no `p` bar: a gap, not a zero.
    assert layer["data"] == [
        [
            {"x": "a", "y": 2.0, "z": "q"},
            {"x": "b", "y": 4.0, "z": "q"},
            {"x": "c", "y": 5.0, "z": "q"},
        ],
        [
            {"x": "a", "y": 1.0, "z": "p"},
            {"x": "b", "y": 3.0, "z": "p"},
            {"x": "c", "y": None, "z": "p"},
        ],
    ]
    bottom, top = layer["selectors"]
    assert top[2] is None
    for low, high in zip(bottom[:2], top[:2]):
        # SVG y grows downwards: the bottom segment is drawn lower.
        assert _centre(_one(root, low))[1] > _centre(_one(root, high))[1]


def test_a_negative_segment_keeps_its_sign():
    frame = pd.DataFrame({"c": ["a", "a"], "g": ["p", "q"], "v": [3.0, -2.0]})
    layer = _only(_read(ggplot(frame, aes("c", "v", fill="g")) + geom_col())[0])

    values = sorted(row[0]["y"] for row in layer["data"])
    assert values == [-2.0, 3.0]


def test_a_bar_below_zero_is_read_with_its_sign():
    """plotnine moves a stacked bar's ``y`` to its top -- 0 for a bar below it."""
    frame = pd.DataFrame({"c": ["a", "b"], "v": [3.0, -2.0]})
    layer = _only(_read(ggplot(frame, aes("c", "v")) + geom_col())[0])

    assert [point["y"] for point in layer["data"]] == [3.0, -2.0]


def test_a_bar_on_a_log_scale_announces_its_value():
    frame = pd.DataFrame({"c": ["a", "b"], "v": [3.0, 100.0]})
    with warnings.catch_warnings():
        # log10(0), the foot of every bar, is plotnine's to warn about.
        warnings.simplefilter("ignore")
        plot = ggplot(frame, aes("c", "v")) + geom_col() + scale_y_log10()
        layer = _only(_read(plot)[0])

    assert [point["y"] for point in layer["data"]] == pytest.approx([3.0, 100.0])


def test_a_stack_on_a_log_scale_is_declined():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        messages = _warnings_of(
            ggplot(SPLIT, aes("cat", "v", fill="g")) + geom_col() + scale_y_log10()
        )

    assert any("transformed y scale" in m for m in messages)


def test_a_dodge_is_read_left_first():
    schema, root = _read(
        ggplot(SPLIT, aes("cat", "v", fill="g")) + geom_col(position="dodge")
    )
    layer = _only(schema)

    assert layer["type"] == "dodged_bar"
    assert [[point["y"] for point in row] for row in layer["data"]] == [
        [1.0, 3.0, None],
        [2.0, 4.0, 5.0],
    ]
    left, right = layer["selectors"]
    for a, b in zip(left[:2], right[:2]):
        assert _centre(_one(root, a))[0] < _centre(_one(root, b))[0]


def test_a_series_mapped_twice_to_one_variable_is_named_once():
    plot = ggplot(SPLIT, aes("cat", "v", fill="g", color="g")) + geom_col(
        position="dodge"
    )
    layer = _only(_read(plot)[0])

    assert [row[0]["z"] for row in layer["data"]] == ["p", "q"]
    assert layer["axes"]["z"] == {"label": "g"}


def test_a_filled_stack_is_normalized_and_each_category_sums_to_one():
    layer = _only(
        _read(ggplot(SPLIT, aes("cat", "v", fill="g")) + geom_col(position="fill"))[0]
    )

    assert layer["type"] == "stacked_normalized_bar"
    columns = zip(*[[point["y"] or 0.0 for point in row] for row in layer["data"]])
    assert [pytest.approx(sum(column)) for column in columns] == [1.0, 1.0, 1.0]


def test_two_bars_of_one_series_at_one_category_are_declined():
    frame = pd.DataFrame({"c": ["a", "a", "b"], "v": [1.0, 2.0, 3.0]})
    plot = ggplot(frame, aes("c", "v")) + geom_col()

    messages = _warnings_of(plot)
    assert any("geom_col" in m and "more than one bar" in m for m in messages)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        html = str(maidr.render(plot, use_cdn=False))
    assert "maidr-fallback-message" in html


# --------------------------------------------------------------------------
# Histogram
# --------------------------------------------------------------------------


def test_a_histogram_reads_each_bin_with_its_edges():
    frame = pd.DataFrame({"v": [0.5, 1.5, 1.6, 2.5, 2.6, 2.7]})
    schema, root = _read(ggplot(frame, aes("v")) + geom_histogram(breaks=[0, 1, 2, 3]))
    layer = _only(schema)

    assert layer["type"] == "hist"
    assert layer["data"] == [
        {"x": 0.5, "y": 1.0, "xMin": 0.0, "xMax": 1.0, "yMin": 0, "yMax": 1.0},
        {"x": 1.5, "y": 2.0, "xMin": 1.0, "xMax": 2.0, "yMin": 0, "yMax": 2.0},
        {"x": 2.5, "y": 3.0, "xMin": 2.0, "xMax": 3.0, "yMin": 0, "yMax": 3.0},
    ]
    centres = [_centre(_one(root, s))[0] for s in layer["selectors"]]
    assert centres == sorted(centres)


def test_a_histogram_of_several_groups_is_declined():
    frame = pd.DataFrame({"v": [0.5, 1.5, 2.5, 0.7], "g": ["p", "p", "q", "q"]})
    messages = _warnings_of(ggplot(frame, aes("v", fill="g")) + geom_histogram(bins=3))

    assert any("geom_histogram" in m and "several groups" in m for m in messages)


# --------------------------------------------------------------------------
# Points, lines, smooths
# --------------------------------------------------------------------------


def test_points_are_read_exactly_and_the_selector_names_every_marker():
    schema, root = _read(ggplot(XY, aes("x", "y")) + geom_point())
    layer = _only(schema)

    assert layer["type"] == "point"
    assert layer["data"] == [
        {"x": x, "y": y} for x, y in zip(XY["x"], XY["y"])
    ]
    assert len(CSSSelector(layer["selectors"])(root)) == len(XY)


def test_a_point_on_a_discrete_axis_keeps_its_position_and_names_its_category():
    layer = _only(_read(ggplot(BOXES, aes("g", "y")) + geom_point())[0])

    assert {(p["x"], p["xLabel"]) for p in layer["data"]} == {(1.0, "p"), (2.0, "q")}


def test_jittered_points_are_declined():
    messages = _warnings_of(ggplot(BOXES, aes("g", "y")) + geom_jitter())

    assert any("geom_jitter" in m for m in messages)


def test_a_line_per_colour_is_a_named_series_outlined_through_its_own_path():
    schema, root = _read(ggplot(XY, aes("x", "y", color="g")) + geom_line())
    layer = _only(schema)

    assert layer["type"] == "line"
    assert layer["axes"]["z"] == {"label": "g"}
    assert layer["data"] == [
        [{"x": 1.0, "y": 2.0, "z": "p"}, {"x": 2.0, "y": 4.0, "z": "p"}],
        [
            {"x": 3.0, "y": 3.0, "z": "q"},
            {"x": 4.0, "y": 5.0, "z": "q"},
            {"x": 5.0, "y": 1.0, "z": "q"},
        ],
    ]
    paths = [_one(root, selector) for selector in layer["selectors"]]
    assert [len(_points_of(path)) for path in paths] == [2, 3]


def test_a_line_whose_colour_varies_along_it_is_read_without_a_highlight():
    layer = _only(_read(ggplot(XY, aes("x", "y", color="y")) + geom_line())[0])

    assert [point["y"] for point in layer["data"][0]] == list(XY["y"])
    assert "selectors" not in layer


def test_a_smooth_carries_its_band_and_leaves_a_line_beside_it_alone():
    plot = (
        ggplot(XY, aes("x", "y"))
        + geom_line()
        + geom_smooth(method="lm", se=True)
    )
    schema, root = _read(plot)
    line, smooth = _layers(schema)

    assert (line["type"], smooth["type"]) == ("line", "smooth")
    first = smooth["data"][0][0]
    # The least-squares fit of the five points: y = 3.3 - 0.1 x.
    assert first["x"] == 1.0
    assert first["y"] == pytest.approx(3.2)
    assert first["yMin"] < first["y"] < first["yMax"]
    (selector,) = smooth["selectors"]
    assert len(_points_of(_one(root, selector))) == len(smooth["data"][0])


# --------------------------------------------------------------------------
# Boxes and tiles
# --------------------------------------------------------------------------


def test_a_box_is_plotnines_five_numbers_and_its_outliers():
    schema, root = _read(ggplot(BOXES, aes("g", "y")) + geom_boxplot())
    layer = _only(schema)

    assert layer["type"] == "box"
    assert layer["data"] == [
        {
            "z": "p",
            "lowerOutliers": [-10.0],
            "min": 1.0,
            "q1": 1.5,
            "q2": 3.0,
            "q3": 4.5,
            "max": 5.0,
            "upperOutliers": [20.0],
        },
        {
            "z": "q",
            "lowerOutliers": [],
            "min": 2.0,
            "q1": 3.0,
            "q2": 4.0,
            "q3": 5.0,
            "max": 6.0,
            "upperOutliers": [],
        },
    ]
    first = layer["selectors"][0]
    low_whisker, high_whisker = _one(root, first["min"]), _one(root, first["max"])
    assert _centre(low_whisker)[1] > _centre(high_whisker)[1]
    (low,) = [_one(root, s) for s in first["lowerOutliers"]]
    (high,) = [_one(root, s) for s in first["upperOutliers"]]
    assert _centre(low)[1] > _centre(high)[1]
    for part in ("iq", "q2"):
        assert CSSSelector(first[part])(root)


def test_a_tile_chart_is_a_heatmap_of_the_values_fill_maps():
    schema, root = _read(ggplot(TILES, aes("a", "b", fill="z")) + geom_tile())
    layer = _only(schema)

    assert layer["type"] == "heat"
    assert layer["axes"]["z"] == {"label": "z"}
    # Rows top first: `v` sits above `u`.
    assert layer["data"] == {
        "x": ["x", "y"],
        "y": ["v", "u"],
        "points": [[2.0, 4.0], [1.0, 3.0]],
    }
    # The core keys its selector grid bottom row first.
    bottom, top = layer["selectors"]
    for low, high in zip(bottom, top):
        assert _centre(_one(root, low))[1] > _centre(_one(root, high))[1]


def test_a_missing_tile_is_a_gap_with_no_element():
    layer = _only(
        _read(ggplot(TILES.iloc[:3], aes("a", "b", fill="z")) + geom_tile())[0]
    )

    assert layer["data"]["points"] == [[2.0, None], [1.0, 3.0]]
    assert layer["selectors"][1][1] is None


def test_tiles_filled_by_a_category_are_declined():
    frame = TILES.assign(z=["lo", "lo", "hi", "hi"])
    messages = _warnings_of(ggplot(frame, aes("a", "b", fill="z")) + geom_tile())

    assert any("geom_tile" in m and "discrete" in m for m in messages)


# --------------------------------------------------------------------------
# Facets, scales, labels
# --------------------------------------------------------------------------


def test_facet_wrap_places_each_panel_where_it_is_drawn():
    frame = XY.assign(k=["a", "b", "c", "a", "b"])
    schema, _ = _read(
        ggplot(frame, aes("x", "y"))
        + geom_point()
        + facet_wrap("k", ncol=2)
        + labs(title="Wrapped", subtitle="three panels")
    )

    assert schema["title"] == "Wrapped"
    assert schema["subtitle"] == "three panels"
    cells = [[cell["layers"] for cell in row] for row in schema["subplots"]]
    assert [[len(layers) for layers in row] for row in cells] == [[1, 1], [1, 0]]
    assert [layers[0]["title"] for row in cells for layers in row if layers] == [
        "k = a",
        "k = b",
        "k = c",
    ]
    assert [p["x"] for p in cells[1][0][0]["data"]] == [3.0]


def test_facet_grid_keeps_an_empty_panel_as_an_empty_cell():
    frame = pd.DataFrame(
        {"x": [1.0, 2.0, 3.0], "y": [1.0, 2.0, 3.0], "r": ["u", "u", "w"],
         "c": ["a", "b", "a"]}
    )
    schema, _ = _read(ggplot(frame, aes("x", "y")) + geom_point() + facet_grid("r ~ c"))

    titles = [
        [cell["layers"][0]["title"] if cell["layers"] else None for cell in row]
        for row in schema["subplots"]
    ]
    assert titles == [["r = u | c = a", "r = u | c = b"], ["r = w | c = a", None]]


def test_a_log_scale_announces_the_values_not_their_logarithms():
    frame = pd.DataFrame({"x": [1.0, 10.0, 100.0], "y": [1.0, 2.0, 3.0]})
    layer = _only(_read(ggplot(frame, aes("x", "y")) + geom_line() + scale_x_log10())[0])

    assert [point["x"] for point in layer["data"][0]] == pytest.approx([1, 10, 100])


def test_a_date_axis_announces_iso_dates():
    frame = pd.DataFrame(
        {"d": pd.date_range("2024-01-01", periods=3, freq="D"), "v": [1.0, 3.0, 2.0]}
    )
    layer = _only(_read(ggplot(frame, aes("d", "v")) + geom_line())[0])

    assert [point["x"] for point in layer["data"][0]] == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
    ]


# --------------------------------------------------------------------------
# What is declined
# --------------------------------------------------------------------------


def test_an_unread_geom_is_left_out_by_name_and_the_rest_is_read():
    plot = ggplot(BOXES, aes("g", "y")) + geom_violin() + geom_point()

    messages = _warnings_of(plot)
    assert any("geom_violin" in m for m in messages)
    assert [layer["type"] for layer in _layers(_read(plot)[0])] == ["point"]


def test_a_flipped_chart_is_a_static_image_and_says_why():
    plot = ggplot(SALES, aes("c", "v")) + geom_col() + coord_flip()

    messages = _warnings_of(plot)
    assert any("coord_flip" in m for m in messages)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert "maidr-fallback-message" in str(maidr.render(plot, use_cdn=False))


def test_a_plotnine_older_than_the_floor_is_drawn_as_a_static_image(monkeypatch):
    monkeypatch.setattr(plotnine, "__version__", "0.12.4")
    plot = ggplot(SALES, aes("c", "v")) + geom_col()

    messages = _warnings_of(plot)
    assert any("plotnine 0.13 or newer" in m for m in messages)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        assert "maidr-fallback-message" in str(maidr.render(plot, use_cdn=False))


def test_warnings_name_the_callers_line():
    plot = ggplot(BOXES, aes("g", "y")) + geom_violin()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        maidr.render(plot, use_cdn=False)

    assert caught and {w.filename for w in caught if "maidr" in str(w.message)} == {
        __file__
    }
