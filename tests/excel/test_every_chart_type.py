"""Every chart type Excel draws is read, and read as what it is.

The DrawingML types XlsxWriter writes -- stacked line, radar, stock -- are
written by it. Those it cannot write -- bubble, surface, pie-of-pie -- and the
Excel 2016 types, which live in a ``chartEx`` part of their own, are made by
editing a part it wrote, the way the uncached and multi-level cases of
``test_read_excel_charts`` are.
"""

from __future__ import annotations

import re
import statistics
import warnings
from pathlib import Path
from typing import Any

import pytest

xlsxwriter = pytest.importorskip("xlsxwriter")

from lxml import etree  # noqa: E402
from lxml.cssselect import CSSSelector  # noqa: E402

import maidr  # noqa: E402
from maidr.excel import read_excel_charts  # noqa: E402
from maidr.excel.chartxml import Binning  # noqa: E402
from maidr.excel.drawex import (  # noqa: E402
    bin_labels,
    box_stats,
    excel_bins,
    quartile,
    squarify,
)
from tests.excel.test_read_excel_charts import (  # noqa: E402
    SALES,
    _add_series,
    _book,
    _chart,
    _layers,
    _read,
    _rewrite,
    _values,
)

CX = "http://schemas.microsoft.com/office/drawing/2014/chartex"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _svg_matches(chart: Any, selector: str) -> list[Any]:
    """The elements of the chart's drawing a selector matches."""
    html = str(maidr.render(chart, use_cdn=False))
    svg = etree.fromstring(
        re.search(r"<svg.*?</svg>", html, re.S).group(0).encode(),
        etree.XMLParser(recover=True),
    )
    for element in svg.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]
    return CSSSelector(selector)(svg)


def _vertices(path: Any) -> int:
    """How many points a ``<path>``'s outline visits."""
    return len(re.findall(r"[ML]", path.get("d", "")))


# --------------------------------------------------------------------------
# Line, radar, bubble, stock, surface, pie-of-pie
# --------------------------------------------------------------------------


def test_stacked_lines_read_as_a_stacked_area_of_their_own_values(tmp_path):
    path = _book(tmp_path, _chart("line", subtype="stacked"))

    (chart,) = _read(path)
    (layer,) = _layers(chart)

    assert layer["type"] == "stacked_area"
    north, south = layer["data"]
    assert _values(north) == [120, 150, 90, 175]
    assert _values(south) == [95, 110, 130, 160]
    assert {p["z"] for p in north} == {"North"}
    # The legend names the lines drawn, not the unpainted bands read.
    legend = chart.figure.axes[0].get_legend()
    assert [t.get_text() for t in legend.get_texts()] == ["North", "South"]


def test_percent_stacked_lines_read_as_shares(tmp_path):
    path = _book(tmp_path, _chart("line", subtype="percent_stacked"))

    (layer,) = _layers(_read(path)[0])

    north, south = layer["data"]
    assert north[0]["y"] == pytest.approx(100 * 120 / 215)
    assert north[0]["y"] + south[0]["y"] == pytest.approx(100)


@pytest.mark.parametrize("subtype", [None, "with_markers", "filled"])
def test_radar_reads_a_spoke_per_category_and_a_row_per_series(tmp_path, subtype):
    options = {"subtype": subtype} if subtype else {}
    path = _book(tmp_path, _chart("radar", **options))

    (chart,) = _read(path)
    (layer,) = _layers(chart)

    assert layer["type"] == "radar"
    assert [_values(row, "x") for row in layer["data"]] == [
        ["Q1", "Q2", "Q3", "Q4"]
    ] * 2
    assert [_values(row) for row in layer["data"]] == [
        [120, 150, 90, 175],
        [95, 110, 130, 160],
    ]
    assert [row[0]["z"] for row in layer["data"]] == ["North", "South"]
    assert layer["axes"]["x"]["label"] == "Quarter"
    # One drawn outline per series, visiting each spoke once: the edge that
    # closes the outline is drawn apart from it.
    for selector in layer["selectors"]:
        (outline,) = _svg_matches(chart, selector)
        assert _vertices(outline) == 4


def _bubbles(text: str) -> str:
    """A scatter chart part rewritten as the bubble chart Excel writes."""
    text = text.replace("c:scatterChart>", "c:bubbleChart>")
    text = re.sub(r"<c:scatterStyle [^>]*/>", "", text)
    sizes = (
        "<c:bubbleSize><c:numRef><c:f>Sales!$D$2:$D$5</c:f><c:numCache>"
        '<c:formatCode>General</c:formatCode><c:ptCount val="4"/>'
        + "".join(
            f'<c:pt idx="{i}"><c:v>{v}</c:v></c:pt>'
            for i, v in enumerate((4, 9, 1, 16))
        )
        + "</c:numCache></c:numRef></c:bubbleSize>"
    )
    return text.replace("</c:yVal>", "</c:yVal>" + sizes)


def test_bubbles_read_as_points_whose_z_is_their_size(tmp_path):
    rows = [["Ads", "Spend", "Sales", "Stores"]] + [
        [f"A{i}", x, y, z]
        for i, (x, y, z) in enumerate(
            [(10, 120, 4), (20, 150, 9), (30, 90, 1), (40, 175, 16)]
        )
    ]

    def build(workbook, worksheet):
        chart = workbook.add_chart({"type": "scatter"})
        chart.add_series(
            {
                "name": ["Sales", 0, 2],
                "categories": ["Sales", 1, 1, 4, 1],
                "values": ["Sales", 1, 2, 4, 2],
            }
        )
        worksheet.insert_chart("F2", chart)

    path = _rewrite(_book(tmp_path, build, rows=rows), "xl/charts/chart1.xml", _bubbles)

    (chart,) = _read(path)
    (layer,) = _layers(chart)

    assert layer["type"] == "point"
    assert [(p["x"], p["y"], p["z"]) for p in layer["data"]] == [
        (10, 120, 4),
        (20, 150, 9),
        (30, 90, 1),
        (40, 175, 16),
    ]
    assert layer["axes"]["z"]["label"] == "Stores"
    assert len(_svg_matches(chart, layer["selectors"])) == 4


PRICES = [
    ["Day", "Open", "High", "Low", "Close", "Volume"],
    ["Mon", 10, 14, 8, 12, 300],
    ["Tue", 12, 15, 11, 11, 450],
    ["Wed", 11, 13, 9, 13, 200],
]


def _stock(columns: tuple[int, ...], *, bars: bool) -> Any:
    def build(workbook, worksheet):
        chart = workbook.add_chart({"type": "stock"})
        for column in columns:
            _add_series(chart, column, sheet="Prices", last=3)
        if bars:
            chart.set_up_down_bars({})
        chart.set_high_low_lines({})
        worksheet.insert_chart("H2", chart)

    return build


def test_an_open_high_low_close_chart_reads_as_candles(tmp_path):
    path = _book(tmp_path, _stock((1, 2, 3, 4), bars=True), rows=PRICES, sheet="Prices")

    (chart,) = _read(path)
    (layer,) = _layers(chart)

    assert layer["type"] == "candlestick"
    assert layer["data"][0] == {
        "value": "Mon",
        "open": 10,
        "high": 14,
        "low": 8,
        "close": 12,
    }
    selectors = layer["selectors"]
    for part in ("body", "wickLow", "wickHigh"):
        assert len(_svg_matches(chart, selectors[part])) == 3


def test_a_high_low_close_chart_reads_as_candles_without_an_open(tmp_path):
    path = _book(tmp_path, _stock((2, 3, 4), bars=False), rows=PRICES, sheet="Prices")

    (chart,) = _read(path)
    (layer,) = _layers(chart)

    assert layer["type"] == "candlestick"
    assert layer["data"][1] == {"value": "Tue", "high": 15, "low": 11, "close": 11}
    assert len(_svg_matches(chart, layer["selectors"]["close"])) == 3


def test_a_stock_chart_reads_its_volume_as_a_layer_and_with_each_candle(tmp_path):
    path = _book(tmp_path, _stock((1, 2, 3, 4), bars=True), rows=PRICES, sheet="Prices")

    def volume(text: str) -> str:
        # Excel draws a volume-open-high-low-close chart as a column group
        # with the stock group on the second axis.
        columns = (
            '<c:barChart><c:barDir val="col"/><c:grouping val="clustered"/>'
            '<c:ser><c:idx val="4"/><c:order val="0"/><c:tx><c:v>Volume</c:v>'
            "</c:tx><c:cat><c:strRef><c:f>Prices!$A$2:$A$4</c:f></c:strRef></c:cat>"
            "<c:val><c:numRef><c:f>Prices!$F$2:$F$4</c:f><c:numCache><c:ptCount "
            'val="3"/><c:pt idx="0"><c:v>300</c:v></c:pt><c:pt idx="1"><c:v>450'
            '</c:v></c:pt><c:pt idx="2"><c:v>200</c:v></c:pt></c:numCache>'
            '</c:numRef></c:val></c:ser><c:axId val="50010001"/>'
            '<c:axId val="50010002"/></c:barChart>'
        )
        return text.replace("<c:stockChart>", columns + "<c:stockChart>")

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        (chart,) = read_excel_charts(_rewrite(path, "xl/charts/chart1.xml", volume))
    candles, bars = _layers(chart)

    assert candles["type"] == "candlestick"
    assert [c["volume"] for c in candles["data"]] == [300, 450, 200]
    # A layer of its own too: the candles list the volume only in their
    # description, where it can be neither walked nor heard.
    assert bars["type"] == "bar"
    assert [(b["x"], b["y"]) for b in bars["data"]] == [
        ("Mon", 300),
        ("Tue", 450),
        ("Wed", 200),
    ]
    assert bars["axes"]["x"]["label"] == "Day"
    assert bars["axes"]["y"]["label"] == "Volume"


def _surface(text: str) -> str:
    """A line chart part rewritten as a surface chart with a depth axis."""
    text = text.replace("c:lineChart>", "c:surfaceChart>")
    text = re.sub(r"<c:grouping [^>]*/>", "", text)
    text = re.sub(r"<c:marker val=\"1\"/>", "", text)
    text = text.replace(
        '<c:axId val="50010002"/></c:surfaceChart>',
        '<c:axId val="50010002"/><c:axId val="50010003"/></c:surfaceChart>',
    )
    return text.replace(
        "</c:valAx>",
        '</c:valAx><c:serAx><c:axId val="50010003"/><c:scaling><c:orientation '
        'val="minMax"/></c:scaling><c:axPos val="b"/><c:title><c:tx><c:rich>'
        "<a:p><a:r><a:t>Region</a:t></a:r></a:p></c:rich></c:tx></c:title>"
        '<c:crossAx val="50010002"/></c:serAx>',
        1,
    )


def test_a_surface_reads_as_a_heatmap_of_series_by_category(tmp_path):
    path = _rewrite(_book(tmp_path, _chart("line")), "xl/charts/chart1.xml", _surface)

    (chart,) = _read(path)
    (layer,) = _layers(chart)

    assert layer["type"] == "heat"
    assert layer["data"]["x"] == ["Q1", "Q2", "Q3", "Q4"]
    # Read from the top row down, and Excel draws the first series at the
    # bottom.
    assert layer["data"]["y"] == ["South", "North"]
    assert layer["data"]["points"] == [[95, 110, 130, 160], [120, 150, 90, 175]]
    assert layer["axes"]["y"]["label"] == "Region"
    assert layer["axes"]["z"]["label"] == "Value"


SHARES = [
    ["Fruit", "Sold"],
    ["Apple", 40],
    ["Banana", 25],
    ["Cherry", 15],
    ["Date", 8],
    ["Elder", 7],
    ["Fig", 5],
]


def _of_pie(kind: str, split: str = "") -> Any:
    def edit(text: str) -> str:
        text = text.replace(
            "<c:pieChart>", f'<c:ofPieChart><c:ofPieType val="{kind}"/>'
        )
        text = re.sub(r"<c:firstSliceAng [^>]*/>", "", text)
        return text.replace("</c:pieChart>", f"{split}</c:ofPieChart>")

    return edit


def _of_pie_book(tmp_path: Path, kind: str, split: str = "") -> Path:
    def build(workbook, worksheet):
        chart = workbook.add_chart({"type": "pie"})
        _add_series(chart, 1, last=6)
        worksheet.insert_chart("D2", chart)

    path = _book(tmp_path, build, rows=SHARES)
    return _rewrite(path, "xl/charts/chart1.xml", _of_pie(kind, split))


def test_pie_of_pie_reads_its_first_pie_and_the_slices_it_spells_out(tmp_path):
    (chart,) = _read(_of_pie_book(tmp_path, "pie"))

    first, second = _layers(chart)

    assert first["type"] == second["type"] == "pie"
    assert _values(first["data"], "x") == ["Apple", "Banana", "Cherry", "Other"]
    assert _values(first["data"]) == [40, 25, 15, 20]
    assert _values(second["data"], "x") == ["Date", "Elder", "Fig"]
    assert second["title"] == "Other"


def test_bar_of_pie_spells_out_its_slices_as_one_stacked_column(tmp_path):
    (chart,) = _read(_of_pie_book(tmp_path, "bar"))

    first, second = _layers(chart)

    assert first["type"] == "pie"
    assert second["type"] == "stacked_bar"
    assert [series[0]["y"] for series in second["data"]] == [8, 7, 5]
    assert [series[0]["z"] for series in second["data"]] == ["Date", "Elder", "Fig"]


@pytest.mark.parametrize(
    ("split", "second"),
    [
        ('<c:splitType val="pos"/><c:splitPos val="2"/>', ["Elder", "Fig"]),
        ('<c:splitType val="val"/><c:splitPos val="10"/>', ["Date", "Elder", "Fig"]),
        (
            '<c:splitType val="percent"/><c:splitPos val="10"/>',
            ["Date", "Elder", "Fig"],
        ),
        (
            '<c:splitType val="cust"/><c:custSplit><c:secondPiePt val="0"/>'
            '<c:secondPiePt val="3"/></c:custSplit>',
            ["Apple", "Date"],
        ),
    ],
)
def test_the_second_plot_holds_the_points_the_split_names(tmp_path, split, second):
    (chart,) = _read(_of_pie_book(tmp_path, "pie", split))

    _, detail = _layers(chart)

    assert _values(detail["data"], "x") == second


# --------------------------------------------------------------------------
# The Excel 2016 chart types
# --------------------------------------------------------------------------


def _dimension(tag: str, kind: str, formula: str, levels: list[list[Any]]) -> str:
    """A ``cx:strDim`` or ``cx:numDim`` with its cached levels, innermost first."""
    body = f"<cx:f>{formula}</cx:f>"
    for level in levels:
        fmt = ' formatCode="General"' if tag == "numDim" else ""
        body += f'<cx:lvl ptCount="{len(level)}"{fmt}>'
        body += "".join(
            f'<cx:pt idx="{i}">{v}</cx:pt>'
            for i, v in enumerate(level)
            if v is not None
        )
        body += "</cx:lvl>"
    return f'<cx:{tag} type="{kind}">{body}</cx:{tag}>'


def _part(
    layout: str,
    categories: str,
    values: str,
    *,
    layout_pr: str = "",
    title: str | None = "Chart",
    more: str = "",
) -> str:
    """An Excel 2016 chart part with one data block and one series."""
    heading = (
        f"<cx:title><cx:tx><cx:txData><cx:v>{title}</cx:v></cx:txData></cx:tx>"
        "</cx:title>"
        if title
        else ""
    )
    return (
        f'<cx:chartSpace xmlns:a="{A}" xmlns:cx="{CX}"><cx:chartData>'
        f'<cx:data id="0">{categories}{values}</cx:data></cx:chartData>'
        f"<cx:chart>{heading}<cx:plotArea><cx:plotAreaRegion>"
        f'<cx:series layoutId="{layout}"><cx:tx><cx:txData><cx:f>Sales!$B$1</cx:f>'
        '<cx:v>North</cx:v></cx:txData></cx:tx><cx:dataId val="0"/>'
        f"<cx:layoutPr>{layout_pr}</cx:layoutPr></cx:series>{more}"
        "</cx:plotAreaRegion>"
        '<cx:axis id="0"><cx:catScaling gapWidth="0.5"/></cx:axis>'
        '<cx:axis id="1"><cx:valScaling/></cx:axis>'
        '</cx:plotArea><cx:legend pos="t"/></cx:chart></cx:chartSpace>'
    )


def _excel_2016(tmp_path: Path, part: str, rows: list[list[Any]] = SALES) -> Path:
    """A workbook whose one chart is the Excel 2016 chart ``part`` holds."""
    path = _book(tmp_path, _chart("column", (1,)), rows=rows)
    path = _rewrite(
        path,
        "xl/drawings/_rels/drawing1.xml.rels",
        lambda text: text.replace(
            "http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart",
            "http://schemas.microsoft.com/office/2014/relationships/chartEx",
        ),
    )
    return _rewrite(path, "xl/charts/chart1.xml", lambda _: part)


def _sales_part(layout: str, values: list[Any], **options: Any) -> str:
    labels = [row[0] for row in SALES[1:]]
    return _part(
        layout,
        _dimension("strDim", "cat", "Sales!$A$2:$A$5", [labels]),
        _dimension("numDim", "val", "Sales!$B$2:$B$5", [values]),
        **options,
    )


def test_a_waterfall_reads_each_step_and_each_total(tmp_path):
    rows = [["Step", "Amount"], ["Start", 100], ["Sales", 50], ["Costs", -30],
            ["Tax", -10], ["End", 110]]  # fmt: skip
    part = _part(
        "waterfall",
        _dimension("strDim", "cat", "Sales!$A$2:$A$6", [[r[0] for r in rows[1:]]]),
        _dimension("numDim", "val", "Sales!$B$2:$B$6", [[r[1] for r in rows[1:]]]),
        layout_pr='<cx:subtotals><cx:idx val="0"/><cx:idx val="4"/></cx:subtotals>',
    )

    (chart,) = _read(_excel_2016(tmp_path, part, rows))
    (layer,) = _layers(chart)

    assert layer["type"] == "waterfall"
    assert [(p["x"], p["start"], p["end"], p["kind"]) for p in layer["data"]] == [
        ("Start", 0, 100, "total"),
        ("Sales", 100, 150, "increase"),
        ("Costs", 150, 120, "decrease"),
        ("Tax", 120, 110, "decrease"),
        ("End", 0, 110, "total"),
    ]
    assert layer["axes"]["x"]["label"] == "Step"
    assert len(_svg_matches(chart, layer["selectors"])) == 5


def test_a_funnel_reads_its_stages_top_down(tmp_path):
    rows = [["Stage", "People"], ["Visits", 1000], ["Signups", 400],
            ["Trials", 150], ["Paid", 60]]  # fmt: skip
    part = _part(
        "funnel",
        _dimension("strDim", "cat", "Sales!$A$2:$A$5", [[r[0] for r in rows[1:]]]),
        _dimension("numDim", "val", "Sales!$B$2:$B$5", [[r[1] for r in rows[1:]]]),
    )

    (chart,) = _read(_excel_2016(tmp_path, part, rows))
    (layer,) = _layers(chart)

    assert layer["type"] == "funnel"
    assert layer["orientation"] == "horz"
    assert [(p["y"], p["x"]) for p in layer["data"]] == [
        ("Visits", 1000),
        ("Signups", 400),
        ("Trials", 150),
        ("Paid", 60),
    ]
    assert layer["axes"]["y"]["label"] == "Stage"
    assert len(_svg_matches(chart, layer["selectors"])) == 4


TREE = [
    ["Group", "Item", "Sold"],
    ["Fruit", "Apple", 10],
    ["Fruit", "Pear", 6],
    ["Veg", "Kale", 4],
    ["Veg", "Leek", 3],
    ["Bread", None, 5],
]


def _tree_part(layout: str) -> str:
    inner = [r[1] for r in TREE[1:]]
    outer = [r[0] for r in TREE[1:]]
    return _part(
        layout,
        _dimension("strDim", "cat", "Sales!$A$2:$B$6", [inner, outer]),
        _dimension("numDim", "size", "Sales!$C$2:$C$6", [[r[2] for r in TREE[1:]]]),
    )


@pytest.mark.parametrize(
    ("layout", "kind"), [("treemap", "treemap"), ("sunburst", "sunburst")]
)
def test_a_hierarchy_reads_every_node_with_its_path(tmp_path, layout, kind):
    (chart,) = _read(_excel_2016(tmp_path, _tree_part(layout), TREE))
    (layer,) = _layers(chart)

    assert layer["type"] == kind
    assert layer["data"] == [
        {"x": "Fruit"},
        {"x": "Apple", "y": 10, "path": ["Fruit"]},
        {"x": "Pear", "y": 6, "path": ["Fruit"]},
        {"x": "Veg"},
        {"x": "Kale", "y": 4, "path": ["Veg"]},
        {"x": "Leek", "y": 3, "path": ["Veg"]},
        {"x": "Bread", "y": 5},
    ]
    # One drawn mark per node, in the order the nodes are declared.
    assert len(_svg_matches(chart, layer["selectors"])) == 7


def test_a_map_reads_as_its_regions_and_says_it_draws_no_shapes(tmp_path):
    rows = [["State", "People"], ["Washington", 7.7], ["Oregon", 4.2],
            ["California", 39.5]]  # fmt: skip
    part = _part(
        "regionMap",
        _dimension("strDim", "cat", "Sales!$A$2:$A$4", [[r[0] for r in rows[1:]]]),
        _dimension("numDim", "colorVal", "Sales!$B$2:$B$4", [[r[1] for r in rows[1:]]]),
    )

    with pytest.warns(UserWarning, match="as a list of its regions"):
        (chart,) = read_excel_charts(_excel_2016(tmp_path, part, rows))
    (layer,) = _layers(chart)

    assert layer["type"] == "choropleth"
    assert layer["data"] == [
        {"x": "Washington", "y": 7.7},
        {"x": "Oregon", "y": 4.2},
        {"x": "California", "y": 39.5},
    ]
    assert len(_svg_matches(chart, layer["selectors"])) == 3


VALUES = [2, 4, 4, 5, 7, 9, 10, 12, 30]


def _values_part(layout: str, layout_pr: str = "", values: list[float] = VALUES) -> str:
    return _part(
        layout,
        "",
        _dimension("numDim", "val", f"Sales!$B$2:$B${len(values) + 1}", [values]),
        layout_pr=layout_pr,
    )


def test_a_histogram_bins_by_scotts_rule_from_the_smallest_value(tmp_path):
    (chart,) = _read(_excel_2016(tmp_path, _values_part("clusteredColumn")))
    (layer,) = _layers(chart)

    width = 3.5 * statistics.stdev(VALUES) / len(VALUES) ** (1 / 3)
    assert layer["type"] == "hist"
    assert layer["data"][0]["xMin"] == 2
    # Read to three figures of the width, 14.2: what Excel's label shows.
    assert layer["data"][0]["xMax"] == round(2 + width, 1) == 16.2
    assert sum(p["y"] for p in layer["data"]) == len(VALUES)


def test_a_histogram_keeps_its_bin_width_and_its_overflow(tmp_path):
    binning = (
        '<cx:binning intervalClosed="r" overflow="20"><cx:binSize val="5"/>'
        "</cx:binning>"
    )
    (chart,) = _read(_excel_2016(tmp_path, _values_part("clusteredColumn", binning)))
    (layer,) = _layers(chart)

    assert [(p["xMin"], p["xMax"], p["y"]) for p in layer["data"]] == [
        (2, 7, 5),  # [2, 7]
        (7, 12, 3),  # (7, 12]
        (12, 17, 0),
        (17, 20, 0),
        (20, 30, 1),  # > 20
    ]


def test_bins_close_on_the_side_the_chart_says():
    data = [1, 4, 5, 6, 9, 10, 11, 14, 15, 16, 22]

    edges, counts = excel_bins(data, Binning(size=5, underflow=5, overflow=15))
    assert list(edges) == [1, 5, 10, 15, 22]
    assert counts == [3, 3, 3, 2]

    edges, counts = excel_bins(data, Binning(size=5, closed="l"))
    assert list(edges) == [1, 6, 11, 16, 21, 26]
    assert counts == [3, 3, 3, 1, 1]


def test_a_histogram_by_category_sums_each_category(tmp_path):
    part = _sales_part(
        "clusteredColumn", [120, 150, 90, 175], layout_pr="<cx:aggregation/>"
    )

    (layer,) = _layers(_read(_excel_2016(tmp_path, part))[0])

    assert layer["type"] == "bar"
    assert _values(layer["data"], "x") == ["Q1", "Q2", "Q3", "Q4"]


def test_a_pareto_sorts_its_categories_and_runs_their_share(tmp_path):
    rows = [["Cause", "Count"], ["Late", 5], ["Damaged", 2], ["Wrong item", 3],
            ["Late", 4], ["Other", 1]]  # fmt: skip
    part = _part(
        "clusteredColumn",
        _dimension("strDim", "cat", "Sales!$A$2:$A$6", [[r[0] for r in rows[1:]]]),
        _dimension("numDim", "val", "Sales!$B$2:$B$6", [[r[1] for r in rows[1:]]]),
        layout_pr="<cx:aggregation/>",
        more='<cx:series layoutId="paretoLine" ownerIdx="0"><cx:axisId val="2"/>'
        "</cx:series>",
    )

    (chart,) = _read(_excel_2016(tmp_path, part, rows))
    bars, line = _layers(chart)

    assert bars["type"] == "bar"
    assert [(p["x"], p["y"]) for p in bars["data"]] == [
        ("Late", 9),
        ("Wrong item", 3),
        ("Damaged", 2),
        ("Other", 1),
    ]
    assert line["type"] == "line"
    assert _values(line["data"][0]) == pytest.approx([0.6, 0.8, 14 / 15, 1.0])
    assert line["axes"]["y"]["format"]["type"] == "percent"


@pytest.mark.parametrize(
    ("method", "q1", "q3"), [("exclusive", 4, 11), ("inclusive", 4, 10)]
)
def test_quartiles_are_found_as_excel_finds_them(method, q1, q3):
    data = sorted(VALUES)

    assert quartile(data, 0.25, method) == q1
    assert quartile(data, 0.5, method) == 7
    assert quartile(data, 0.75, method) == q3


def test_whiskers_reach_the_last_value_within_one_and_a_half_ranges():
    stats = box_stats(VALUES, "exclusive", "A")

    assert (stats["whislo"], stats["whishi"]) == (2, 12)
    assert stats["fliers"] == [30]


def test_a_box_and_whisker_reads_a_box_per_category(tmp_path):
    groups = ["A"] * 5 + ["B"] * 4
    rows = [["Group", "Score"]] + [[g, v] for g, v in zip(groups, VALUES)]
    part = _part(
        "boxWhisker",
        _dimension("strDim", "cat", "Sales!$A$2:$A$10", [groups]),
        _dimension("numDim", "val", "Sales!$B$2:$B$10", [VALUES]),
        layout_pr='<cx:statistics quartileMethod="inclusive"/>',
    )

    (chart,) = _read(_excel_2016(tmp_path, part, rows))
    (layer,) = _layers(chart)

    assert layer["type"] == "box"
    first, second = layer["data"]
    # A is 2, 4, 4, 5, 7: quartiles 4 and 5, so 2 and 7 lie outside.
    assert (first["z"], first["q2"], first["min"], first["max"]) == ("A", 4, 4, 5)
    assert (first["lowerOutliers"], first["upperOutliers"]) == ([2], [7])
    assert (second["z"], second["q2"], second["upperOutliers"]) == ("B", 11, [30])


def test_an_excel_2016_chart_reads_its_cells_through_the_names_it_uses(tmp_path):
    part = _sales_part("funnel", [120, 150, 90, 175])
    part = re.sub(r"<cx:lvl .*?</cx:lvl>", "", part)
    part = part.replace("Sales!$A$2:$A$5", "_xlchart.v1.0").replace(
        "Sales!$B$2:$B$5", "_xlchart.v1.1"
    )
    path = _excel_2016(tmp_path, part)

    def names(text: str) -> str:
        return text.replace(
            "</sheets>",
            '</sheets><definedNames><definedName name="_xlchart.v1.0" hidden="1">'
            'Sales!$A$2:$A$5</definedName><definedName name="_xlchart.v1.1" '
            'hidden="1">Sales!$B$2:$B$5</definedName></definedNames>',
        )

    (layer,) = _layers(_read(_rewrite(path, "xl/workbook.xml", names))[0])

    assert [(p["y"], p["x"]) for p in layer["data"]] == [
        ("Q1", 120),
        ("Q2", 150),
        ("Q3", 90),
        ("Q4", 175),
    ]
    assert layer["axes"]["y"]["label"] == "Quarter"


def test_an_excel_2016_layout_maidr_does_not_know_is_left_out_naming_it(tmp_path):
    part = _sales_part("newShape", [1, 2, 3, 4])

    with pytest.warns(UserWarning, match="does not read newShape charts"):
        assert read_excel_charts(_excel_2016(tmp_path, part)) == []


def test_squarified_tiles_fill_their_rectangle_in_proportion():
    tiles = squarify([6, 6, 4, 3, 2, 2, 1], 0, 0, 6, 4)

    areas = [w * h for _, _, w, h in tiles]
    assert areas == pytest.approx([6, 6, 4, 3, 2, 2, 1])
    for x, y, w, h in tiles:
        assert -1e-9 <= x and x + w <= 6 + 1e-9
        assert -1e-9 <= y and y + h <= 4 + 1e-9


def test_a_radar_whose_every_value_is_blank_reads_as_nothing(tmp_path):
    def build(workbook, worksheet):
        chart = workbook.add_chart({"type": "radar"})
        chart.add_series(
            {"categories": ["Sales", 1, 0, 4, 0], "values": ["Sales", 1, 5, 4, 5]}
        )
        worksheet.insert_chart("E2", chart)

    with pytest.warns(UserWarning, match="has no data maidr can read"):
        assert read_excel_charts(_book(tmp_path, build)) == []


def test_a_chart_maidr_cannot_draw_costs_that_chart_alone(tmp_path, monkeypatch):
    import maidr.excel.drawex as drawex

    def broken(*args: Any) -> None:
        raise ValueError("no room for it")

    monkeypatch.setitem(drawex._DRAW, "funnel", broken)
    path = _excel_2016(tmp_path, _sales_part("funnel", [120, 150, 90, 175]))

    with pytest.warns(UserWarning, match="cannot draw 'Chart 1'.*no room for it"):
        assert read_excel_charts(path) == []


@pytest.mark.parametrize("columns", [(1,), (1, 2)])
def test_a_stock_chart_without_three_prices_reads_as_lines(tmp_path, columns):
    path = _book(tmp_path, _stock(columns, bars=False), rows=PRICES, sheet="Prices")

    (layer,) = _layers(_read(path)[0])

    assert layer["type"] == "line"


def test_squarify_leaves_tiles_with_no_size_empty():
    tiles = squarify([3, 1, 0, 0], 0, 0, 2, 2)

    assert [w * h for _, _, w, h in tiles] == pytest.approx([3, 1, 0, 0])


@pytest.mark.parametrize(
    ("binning", "edges", "labels"),
    [
        (Binning(size=5), [1, 6, 11], ["[1, 6]", "(6, 11]"]),
        # The underflow bin took 5 itself, so the first bin after it is open.
        (
            Binning(size=5, underflow=5),
            [1, 5, 10, 15],
            ["≤5", "(5, 10]", "(10, 15]"],
        ),
        (Binning(size=5, closed="l"), [1, 6, 11], ["[1, 6)", "[6, 11]"]),
        # The overflow bin took 11, so the last bin before it is open.
        (
            Binning(size=5, overflow=11, closed="l"),
            [1, 6, 11, 22],
            ["[1, 6)", "[6, 11)", "≥11"],
        ),
    ],
)
def test_a_bins_bracket_says_whether_it_holds_its_end(binning, edges, labels):
    assert bin_labels(edges, binning, 0) == labels


def test_bin_labels_keep_the_decimals_their_edges_were_rounded_to(tmp_path):
    years = list(range(2001, 2025))
    part = _part(
        "clusteredColumn",
        "",
        _dimension("numDim", "val", "Sales!$B$2:$B$25", [years]),
        layout_pr='<cx:binning intervalClosed="r"/>',
        more='<cx:series layoutId="paretoLine" ownerIdx="0"/>',
    )

    (chart,) = _read(_excel_2016(tmp_path, part))
    bars, _ = _layers(chart)

    # Scott's rule makes the bins 8.58 years wide: 2010 is in the second.
    assert [(p["x"], p["y"]) for p in bars["data"]] == [
        ("[2001, 2009.58]", 9),
        ("(2009.58, 2018.16]", 9),
        ("(2018.16, 2026.74]", 6),
    ]


def test_a_chart_of_one_mark_is_still_outlined(tmp_path):
    rows = [["State", "People"], ["Oregon", 4.2]]
    part = _part(
        "regionMap",
        _dimension("strDim", "cat", "Sales!$A$2:$A$2", [["Oregon"]]),
        _dimension("numDim", "colorVal", "Sales!$B$2:$B$2", [[4.2]]),
    )

    (chart,) = _read(_excel_2016(tmp_path, part, rows))
    (layer,) = _layers(chart)

    # matplotlib writes a collection of one outlined shape as a <use>.
    assert len(_svg_matches(chart, layer["selectors"])) == 1


def test_steps_a_chart_names_none_of_are_numbered(tmp_path):
    part = _part(
        "waterfall",
        "",
        _dimension("numDim", "val", "Sales!$B$2:$B$4", [[10, -4, 7]]),
    )

    (layer,) = _layers(_read(_excel_2016(tmp_path, part))[0])

    assert [p["x"] for p in layer["data"]] == ["1", "2", "3"]


def test_a_point_with_a_damaged_index_costs_that_point_alone(tmp_path):
    part = _sales_part("funnel", [120, 150, 90, 175]).replace(
        '<cx:pt idx="0">120</cx:pt>',
        '<cx:pt idx="x">7</cx:pt><cx:pt idx="0">120</cx:pt>',
    )

    (layer,) = _layers(_read(_excel_2016(tmp_path, part))[0])

    assert [p["x"] for p in layer["data"]] == [120, 150, 90, 175]


def test_a_bin_width_too_small_to_draw_draws_as_many_bins_as_are_drawn():
    data = [1.0, 2.0, 3.0, 1000.0]

    edges, counts = excel_bins(data, Binning(size=1e-310))

    assert len(counts) == 1000
    assert sum(counts) == len(data)
    assert edges[0] == 1 and edges[-1] == 1000


def test_a_hierarchy_deeper_than_maidr_reads_is_read_to_its_depth_limit(tmp_path):
    levels = [[f"L{depth}"] for depth in range(40)]
    part = _part(
        "sunburst",
        _dimension("strDim", "cat", "Sales!$A$2:$AN$2", levels),
        _dimension("numDim", "size", "Sales!$AO$2:$AO$2", [[5]]),
    )

    (layer,) = _layers(_read(_excel_2016(tmp_path, part))[0])

    assert max(len(p.get("path", [])) for p in layer["data"]) == 31
