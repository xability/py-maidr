"""The gallery pages run, and each section emits the chart it says it does.

Nothing else executes the ``{python}`` chunks in the gallery against the
library under test. The docs workflow renders the site, but only for a pull
request that touches ``docs/``; a change to an extractor runs the unit suite
and never the gallery. So an example that stops running, or a paragraph that
describes a reading the extractor no longer produces, failed nothing (#692).

The pages have taken on prose that states specific extraction behavior --
which ticks name a gantt lane, that ``levels=6`` on a contour is six heights
rather than six curves, that a pie is walked clockwise whichever way it was
drawn -- because that behavior is not obvious, and each such claim is one a
refactor can invalidate silently. The docs would still build; they would just
be wrong, in the direction of telling a reader their chart is accessible in a
way it no longer is.

Three checks, in increasing strength:

1. Every chunk runs. This alone catches a renamed argument, a moved import
   or an example that stops producing a figure.
2. Every section emits the layer types listed in ``EXPECTED_LAYERS``, so a
   chart that silently starts reading as something else fails, and a new
   section is not covered until it is listed.
3. The measured claims the prose makes -- lane names, curve counts, band
   names, slice order, level names -- hold against the emitted data.

A page is executed the way Quarto executes it: its chunks in order, in one
namespace, from its own directory. A chunk that reads a name an earlier
chunk on the same page bound is therefore fine here, as it is on the site.
Fences without the ``{python}`` executable marker are skipped for the same
reason: Quarto does not run them either.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pytest
from matplotlib._pylab_helpers import Gcf
from matplotlib.figure import Figure as MplFigure

import maidr
from maidr import api
from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.excel import ExcelChart
from maidr.office import PowerPointChart, WordChart, read_powerpoint_charts
from maidr.tensorboard import TensorBoardChart
from maidr.util.metric_chart import MetricChart

DOCS = Path(__file__).parents[2] / "docs"

#: The gallery: the matplotlib/seaborn family pages plus the one-page Plotly,
#: Bokeh, plotnine, Altair, Excel, PowerPoint and Word, and TensorBoard
#: galleries. Discovered rather than listed, so a new
#: page is run as soon as it exists -- and fails below until its sections are
#: listed.
PAGES = sorted(DOCS.glob("examples*.qmd")) + sorted((DOCS / "examples").glob("*.qmd"))

#: Pages whose library is an optional extra that nothing else in the suite
#: requires, so an environment without it -- ``uv sync --dev`` with no extras --
#: skips the page rather than failing it.
REQUIRES = {"examples-plotnine.qmd": "plotnine", "examples-mlflow.qmd": "mlflow"}

#: A figure as a reader receives it: one entry per subplot cell, each the
#: emitted layer types joined with `` + ``. A section lists one such figure
#: per ``plt.show()`` / ``maidr.show()`` it makes.
#:
#: The Altair page is the exception. Its schema is built upstream by the
#: Vega-Lite adapter in the browser, so there is no layer type to read here;
#: its entries are the Vega-Lite ``mark`` types the chunk hands over, one per
#: layer, which is what that adapter reads.
Figure = list[str]

EXPECTED_LAYERS: dict[str, dict[str, list[Figure]]] = {
    "examples/area-errorbar-point-lollipop.qmd": {
        "Area Plot [experimental]": [["stacked_area"], ["area"]],
        "Error Bar Plot [experimental]": [["error_bar"]],
        "Point Plot [experimental]": [["error_bar"]],
        "Lollipop Plot [experimental]": [["lollipop"]],
    },
    "examples/bar.qmd": {
        "Bar Plot": [["bar"]],
        "Count Plot": [["bar"]],
        "Stacked Bar Plot": [["stacked_bar"]],
        "Dodged Bar Plot": [["dodged_bar"]],
    },
    "examples/box-boxen-violin.qmd": {
        "Box Plot": [["box"]],
        "Seaborn Violin Plot (Horizontal)": [["violin_box + violin_kde"]],
        "Matplotlib Violin Plot": [["violin_box + violin_kde"]],
        "Boxen Plot (Letter-Value Plot) [experimental]": [["boxen"]],
    },
    "examples/candlestick-gantt.qmd": {
        # The candles, the three moving averages as one line layer, and the
        # volume bars. All in one cell: mplfinance places its panels with
        # `add_axes` rather than a gridspec, so none carries a subplotspec
        # and every layer reports position (0, 0). The page's "volume panel
        # available as its own subplot" is not what the reader gets today.
        "Candlestick Chart": [["candlestick + bar + line"]],
        "Gantt Chart [experimental]": [["gantt"]],
    },
    "examples/heatmap-hexbin-contour.qmd": {
        "Heat Map": [["heat"]],
        "Hexbin Plot [experimental]": [["hexbin"]],
        "Contour Plot [experimental]": [["contour"]],
    },
    "examples/histogram-kde.qmd": {
        "Histogram": [["hist + smooth"]],
        "KDE (Kernel Density Estimation) Plot": [["smooth"]],
    },
    "examples/line-step.qmd": {
        "Single Line Plot": [["line"]],
        "Multiline Plot": [["line"]],
        "Step Plot": [["step"]],
    },
    "examples/multi-layer-panel-facet.qmd": {
        "Multi-Layered Plot": [["bar + line"]],
        "Multi-Panel Plot (Multiple Subplots)": [["line", "bar", "bar"]],
        "Facet Plot": [["bar", "bar", "bar", "bar"]],
    },
    "examples/pie-wordcloud.qmd": {
        "Pie Chart": [["pie"]],
        "Word Cloud [experimental]": [["word_cloud"]],
    },
    "examples/network-graph.qmd": {
        # The nodes are one point collection, read as the graph rather than
        # as their layout positions.
        "A pipeline": [["directed_graph"]],
        "Labels and node data": [["directed_graph"]],
    },
    "examples/pr-curve.qmd": {
        # Two classifiers on one axes are two curves of one layer, and the
        # chance level `plot_chance_level=True` draws is not a curve.
        "One classifier": [["pr_curve"]],
        "Comparing classifiers": [["pr_curve"]],
    },
    "examples/roc.qmd": {
        # Two classifiers on one axes are two curves of one layer, and the
        # chance diagonal `plot_chance_level=True` draws is not a curve.
        "One classifier": [["roc"]],
        "Comparing classifiers": [["roc"]],
    },
    "examples/scatter-regression.qmd": {
        # `hue="species"`: one point layer per species.
        "Scatter Plot": [["point + point + point"]],
        "Regression Plot": [["point + smooth"]],
    },
    "examples-plotly.qmd": {
        "Bar Plot": [["bar"]],
        "Dodged (Grouped) Bar Plot": [["dodged_bar"]],
        "Stacked Bar Plot": [["stacked_bar"]],
        "Count Plot (Categorical Histogram)": [["bar"]],
        "Pie Chart": [["pie"]],
        "Histogram": [["hist"]],
        "Box Plot (Vertical)": [["box"]],
        "Box Plot (Horizontal)": [["box"]],
        "Heatmap": [["heat"]],
        "Line Plot": [["line"]],
        "Multi-Line Plot": [["line"]],
        "Step Plot": [["step"]],
        "Scatter Plot": [["point"]],
        "KDE (Histogram + KDE Overlay)": [["line + hist"]],
        "Regression (Scatter + Trend Line)": [["line + point"]],
        "Multipanel Plot (Line + Bar + Scatter)": [["line", "bar", "point"]],
        "Facet Bar Plot (2x2 Grid)": [["bar", "bar", "bar", "bar"]],
        "Facet Combined Plot (Line + Bar)": [
            ["point", "bar", "point", "bar", "point", "bar"]
        ],
    },
    "examples-bokeh.qmd": {
        "Bar Plot": [["bar"]],
        "Horizontal Bar Plot": [["bar"]],
        "Stacked Bar Plot": [["stacked_bar"]],
        "Dodged (Grouped) Bar Plot": [["dodged_bar"]],
        "Histogram": [["hist"]],
        "Line Plot": [["line"]],
        "Multi-Line Plot": [["line"]],
        "Step Plot": [["step"]],
        "Scatter Plot": [["point"]],
        "Heatmap": [["heat"]],
        "Image Heatmap": [["heat"]],
        "Pie Chart": [["pie"]],
        "Candlestick Chart": [["candlestick"]],
        "Multi-Panel Layout (gridplot)": [["bar", "line"]],
        "Stacked Area Plot [experimental]": [["stacked_area"]],
        "Horizontal Area Plot [experimental]": [["area"]],
        "Gantt Chart [experimental]": [["gantt"]],
        "Hexbin Plot [experimental]": [["hexbin"]],
        "Directed Graph [experimental]": [["directed_graph"]],
    },
    "examples-plotnine.qmd": {
        "Bar Plot": [["bar"]],
        "Stacked Bar Plot": [["stacked_bar"]],
        "Dodged (Grouped) Bar Plot": [["dodged_bar"]],
        "Histogram": [["hist"]],
        "Scatter Plot": [["point"]],
        "Line Plot": [["line"]],
        "Multi-Line Plot": [["line"]],
        "Box Plot": [["box"]],
        "Heatmap": [["heat"]],
        "Scatter Plot with a Smooth": [["point + smooth"]],
        "Faceted Plot": [["point", "point", "point"]],
        "Normalized Stacked Bar Plot [experimental]": [["stacked_normalized_bar"]],
    },
    "examples-excel.qmd": {
        "Clustered Column Chart": [["dodged_bar"]],
        "Line Chart": [["line"]],
        "Pie Chart": [["pie"]],
        "Combo Chart on Two Axes": [["bar + line"]],
        "Stock Chart": [["candlestick"]],
        "Histogram": [["hist"]],
        "Box and Whisker Chart": [["box"]],
        "Stacked Area Chart [experimental]": [["stacked_area"]],
        "Radar Chart [experimental]": [["radar"]],
        "Waterfall Chart [experimental]": [["waterfall"]],
        "Treemap [experimental]": [["treemap"]],
    },
    "examples-office.qmd": {
        "Column Chart on a Slide": [["dodged_bar"]],
        "Line Chart on a Slide": [["line"]],
        "Pie Chart on a Hidden Slide": [["pie"]],
        "Line Chart in a Document": [["line"]],
        "Bar Chart in a Document": [["bar"]],
    },
    "examples-keras.qmd": {
        "Training Curves from model.fit": [["line", "line"]],
        "Confusion Matrix": [["heat"]],
        "PR Curve [experimental]": [["pr_curve"]],
        "Model Graph [experimental]": [["directed_graph"]],
    },
    "examples-wandb.qmd": {
        "Training Loss": [["line"]],
        "Evaluation Loss": [["line"]],
    },
    "examples-mlflow.qmd": {
        "Training Loss": [["line"]],
        "Evaluation Loss": [["line"]],
    },
    "examples-tensorboard.qmd": {
        "Training and Validation Loss": [["line"]],
        "Accuracy Without Smoothing": [["line"]],
        "Profile": [["stacked_bar"], ["bar"]],
        "Hyperparameter Sweep as a Scatter Matrix": [["point"] * 8],
        "Embedding Projector": [["point + point + point"]],
        "Distributions as Percentile Bands [experimental]": [["percentile_band"]],
        "PR Curves [experimental]": [["pr_curve"]],
        "Histograms as Ridgelines [experimental]": [["ridgeline"]],
        "Hyperparameter Sweep as Parallel Coordinates [experimental]": [
            ["parallel_coordinates"]
        ],
        "Model Graph [experimental]": [["directed_graph"]],
    },
    "examples-altair.qmd": {
        "Bar Plot": [["bar"]],
        "Dodged (Grouped) Bar Plot": [["bar"]],
        "Stacked Bar Plot": [["bar"]],
        "Count Plot": [["bar"]],
        "Histogram": [["bar"]],
        "Single KDE Plot": [["line"]],
        "Multiple KDE Overlays": [["line"]],
        "Box Plot (Vertical and Horizontal)": [["boxplot"], ["boxplot"]],
        "Heatmap": [["rect + text"]],
        "Line Plot": [["line"]],
        "Multi-Line Plot": [["line"]],
        "Step Plot": [["line"]],
        "Scatter Plot": [["point"]],
        "Multi-Layered Plot": [["bar + line"]],
        "Regression (Scatter + LOESS Smooth)": [["point + line"]],
    },
}


# --------------------------------------------------------------------------
# Reading a page
# --------------------------------------------------------------------------


@dataclass
class Chunk:
    """One executable chunk and the section heading it sits under."""

    section: str
    code: str
    line: int


_FENCE_OPEN = re.compile(r"^```\{python\}")
_FENCE_CLOSE = re.compile(r"^```\s*$")
_HEADING = re.compile(r"^#{2,} +(.+?)\s*(\{#[^}]*\})?\s*$")


def _chunks(page: Path) -> list[Chunk]:
    """The ``{python}`` chunks of a page, in order, each with its section.

    Line-based rather than one regular expression over the page, because a
    ``#`` line inside a chunk is a comment and must not be mistaken for the
    heading of the chunk after it.
    """
    chunks: list[Chunk] = []
    section = ""
    code: list[str] = []
    opened_at = 0
    inside = False

    for number, line in enumerate(page.read_text(encoding="utf-8").splitlines(), 1):
        if inside:
            if _FENCE_CLOSE.match(line):
                chunks.append(Chunk(section, "\n".join(code) + "\n", opened_at))
                inside = False
            else:
                code.append(line)
        elif _FENCE_OPEN.match(line):
            inside, code, opened_at = True, [], number
        else:
            heading = _HEADING.match(line)
            if heading:
                section = heading.group(1)

    assert not inside, f"{page.name}: chunk opened at line {opened_at} never closes"
    return chunks


# --------------------------------------------------------------------------
# Running a page
# --------------------------------------------------------------------------


@dataclass
class Shown:
    """What one ``show()`` call handed the reader."""

    #: Per subplot cell, the emitted layer type names.
    types: list[list[str]]
    #: Per subplot cell, the emitted layer schemas. Empty for an Altair
    #: chart, whose schema is built in the browser.
    layers: list[list[dict]] = field(default_factory=list)

    @property
    def figure(self) -> Figure:
        """The figure in the form ``EXPECTED_LAYERS`` lists it."""
        return [" + ".join(cell) for cell in self.types]

    def layer(self, plot_type: PlotType) -> dict:
        """The one emitted layer of the given type."""
        matches = [
            layer
            for cell in self.layers
            for layer in cell
            if PlotType(layer[MaidrKey.TYPE]) is plot_type
        ]
        assert len(matches) == 1, f"expected one {plot_type.value} layer"
        return matches[0]


def _cells(schema: dict) -> list[list[dict]]:
    """The layers of each subplot cell, row-major, as the reader gets them."""
    return [cell["layers"] for row in schema["subplots"] for cell in row]


def _from_schema(schema: dict) -> Shown:
    cells = _cells(schema)
    return Shown(
        types=[
            [PlotType(layer[MaidrKey.TYPE]).value for layer in cell] for cell in cells
        ],
        layers=cells,
    )


def _from_altair(chart: Any) -> Shown:
    """Run the chart through the adapter, and record the marks it embeds."""
    from maidr.altair import AltairMaidr

    AltairMaidr(chart).render()

    spec = chart.to_dict()
    layers = [spec] if "mark" in spec else spec.get("layer", [])
    marks = [layer["mark"] for layer in layers]
    return Shown(
        types=[[mark["type"] if isinstance(mark, dict) else mark for mark in marks]]
    )


class _Capture:
    """Stand-in for the two ``show`` paths a gallery chunk can take.

    Records what each call would have emitted, keyed by the section the
    running chunk sits under, instead of opening a browser.
    """

    def __init__(self) -> None:
        self.section = ""
        self.shown: dict[str, list[Shown]] = {}

    def _record(self, shown: Shown) -> None:
        self.shown.setdefault(self.section, []).append(shown)

    def pyplot_show(self, *args: Any, **kwargs: Any) -> None:
        """``plt.show()``: every open figure, as the maidr backend does it."""
        for manager in list(Gcf.get_all_fig_managers()):
            fig = manager.canvas.figure
            try:
                schema = FigureManager.get_maidr(fig)._flatten_maidr()
            except KeyError:
                # What the backend would show instead: a static image with a
                # warning. Named so it shows up in the comparison as itself.
                self._record(Shown(types=[["static image"]]))
            else:
                self._record(_from_schema(schema))
            FigureManager.destroy(fig)
            Gcf.destroy(manager.num)

    def maidr_show(self, plot: Any = None, *args: Any, **kwargs: Any) -> None:
        """``maidr.show(plot)``: Altair, Plotly, Bokeh, plotnine, an Excel,
        PowerPoint, Word, TensorBoard, W&B or MLflow chart, a figure drawn
        outside pyplot, or pyplot."""
        charts = (ExcelChart, MetricChart, PowerPointChart, WordChart, TensorBoardChart)
        if isinstance(plot, charts):
            plot = plot.figure
        if isinstance(plot, MplFigure) and plot.canvas.manager is None:
            # Drawn outside pyplot, so not among the figures `plt.show()` sees.
            self._record(_from_schema(FigureManager.get_maidr(plot)._flatten_maidr()))
            FigureManager.destroy(plot)
        elif api._is_altair_chart(plot):
            self._record(_from_altair(plot))
        elif plot is not None and api._is_plotly_figure(plot):
            self._record(_from_schema(api._get_plotly_maidr(plot)._flatten_maidr()))
        elif plot is not None and api._is_bokeh_model(plot):
            self._record(_from_schema(api._get_bokeh_maidr(plot)._flatten_maidr()))
        elif plot is not None and api._is_plotnine_plot(plot):
            reader = api._get_plotnine_maidr(plot)
            self._record(_from_schema(reader._flatten_maidr()))
        else:
            self.pyplot_show()


def _run(page: Path) -> dict[str, list[Shown]]:
    """Execute a page's chunks in order, in one namespace, from its directory."""
    capture = _Capture()
    namespace: dict[str, Any] = {"__name__": "__main__"}

    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(page.parent)
        patch.setattr(plt, "show", capture.pyplot_show)
        patch.setattr(maidr, "show", capture.maidr_show)

        for chunk in _chunks(page):
            capture.section = chunk.section
            source = compile(chunk.code, f"{page.name}:{chunk.line}", "exec")
            try:
                # The pages set `warning: false` on their chunks; what they
                # would print is not what this measures.
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    exec(source, namespace)
            except Exception as error:
                raise AssertionError(
                    f"{page.relative_to(DOCS)}: the chunk at line {chunk.line}, "
                    f"under '{chunk.section}', raised {type(error).__name__}: "
                    f"{error}"
                ) from error
            finally:
                plt.close("all")

    return capture.shown


class _Gallery:
    """Runs each page at most once, whichever test asks first.

    A page that raises is remembered as raising, so every test that depends
    on it reports the same failure rather than the first one erroring the
    rest out.
    """

    def __init__(self) -> None:
        self._runs: dict[Path, Any] = {}

    def __getitem__(self, page: Path) -> dict[str, list[Shown]]:
        required = REQUIRES.get(_page_id(page))
        if required is not None:
            pytest.importorskip(required)
        if page not in self._runs:
            try:
                self._runs[page] = _run(page)
            except AssertionError as error:
                self._runs[page] = error
        result = self._runs[page]
        if isinstance(result, AssertionError):
            raise result
        return result

    def shown(self, page: str, section: str) -> Shown:
        """The one figure a section shows."""
        figures = self[DOCS / page][section]
        assert len(figures) == 1, f"{page}: '{section}' shows {len(figures)} figures"
        return figures[0]


@pytest.fixture(scope="module")
def gallery() -> _Gallery:
    return _Gallery()


def _page_id(page: Path) -> str:
    return str(page.relative_to(DOCS))


# --------------------------------------------------------------------------
# 1 and 2: every chunk runs, and every section emits what it is listed as
# --------------------------------------------------------------------------


@pytest.mark.parametrize("page", PAGES, ids=_page_id)
def test_every_section_emits_the_layers_it_is_listed_as(
    gallery: _Gallery, page: Path
) -> None:
    """Both directions at once.

    A section that emits something and is not listed fails, so a new example
    is covered from the day it is added. A listed section that no longer
    shows anything fails too, so the table cannot go stale.
    """
    emitted = {
        section: [shown.figure for shown in figures]
        for section, figures in gallery[page].items()
    }

    assert emitted == EXPECTED_LAYERS.get(_page_id(page), {})


def test_every_listed_page_exists() -> None:
    """A renamed or removed page must leave the table with it."""
    assert set(EXPECTED_LAYERS) <= {_page_id(page) for page in PAGES}


# --------------------------------------------------------------------------
# 3: the measured claims the prose makes
# --------------------------------------------------------------------------
#
# Each of these pins one sentence a page says about what the reader hears,
# against the data the section's chunk actually emits. The sentence is quoted
# so that changing the behavior means changing the page, and the other way
# round.


def test_gantt_lanes_are_named_by_the_fixed_ticks(gallery: _Gallery) -> None:
    """candlestick-gantt.qmd: "Naming the lanes takes both ``set_yticks()``
    and ``set_yticklabels()``, as the example does" -- and "a phase that
    stops and restarts is two spans on one lane, not two separate rows".
    """
    data = gallery.shown(
        "examples/candlestick-gantt.qmd", "Gantt Chart [experimental]"
    ).layer(PlotType.GANTT)[MaidrKey.DATA]

    assert data[MaidrKey.LANES] == ["Design", "Build", "Launch"]
    assert [len(lane) for lane in data[MaidrKey.POINTS]] == [1, 2, 1]


def test_candlestick_dates_read_as_the_axis_draws_them(gallery: _Gallery) -> None:
    """candlestick-gantt.qmd: "Pass ``datetime_format=`` to ``mpf.plot()``,
    as above, and the dates are announced the way the x axis draws them:
    every candle, volume bar and moving average reads as its tick label does,
    ``Nov 01, 2019`` here".
    """
    shown = gallery.shown("examples/candlestick-gantt.qmd", "Candlestick Chart")

    candles = [
        candle["value"] for candle in shown.layer(PlotType.CANDLESTICK)[MaidrKey.DATA]
    ]
    volume = [bar[MaidrKey.X] for bar in shown.layer(PlotType.BAR)[MaidrKey.DATA]]
    averages = shown.layer(PlotType.LINE)[MaidrKey.DATA]

    assert candles[0] == "Nov 01, 2019"
    assert volume == candles
    # Each moving average starts once its window is full, on a later candle.
    assert [line[0][MaidrKey.X] for line in averages] == [
        candles[2],
        candles[5],
        candles[8],
    ]
    assert {point[MaidrKey.X] for line in averages for point in line} <= set(candles)


def test_candlestick_dates_without_a_format_read_as_the_frame_holds_them() -> None:
    """candlestick-gantt.qmd: "Without it, each date is announced as the
    frame holds it [...]: ``2019-11-01`` for daily data like this, whose index
    has no time of day".

    The section draws with ``datetime_format``, so the page's own data is
    drawn again here without it.
    """
    import pandas as pd

    mpf = pytest.importorskip("mplfinance")
    daily = pd.read_csv(
        DOCS.parent / "example" / "candle_stick" / "volcandat.csv",
        index_col=0,
        parse_dates=True,
    )
    fig, _ = mpf.plot(daily, type="candle", volume=True, mav=3, returnfig=True)
    try:
        shown = _from_schema(FigureManager.get_maidr(fig)._flatten_maidr())
    finally:
        FigureManager.destroy(fig)
        plt.close(fig)

    candles = [
        candle["value"] for candle in shown.layer(PlotType.CANDLESTICK)[MaidrKey.DATA]
    ]
    volume = [bar[MaidrKey.X] for bar in shown.layer(PlotType.BAR)[MaidrKey.DATA]]
    assert candles[0] == "2019-11-01"
    assert volume == candles


def test_contour_reads_six_curves_for_six_levels(gallery: _Gallery) -> None:
    """heatmap-hexbin-contour.qmd: "On a single-peaked surface like this
    one the two coincide -- six levels, six curves."
    """
    curves = gallery.shown(
        "examples/heatmap-hexbin-contour.qmd", "Contour Plot [experimental]"
    ).layer(PlotType.CONTOUR)[MaidrKey.DATA]

    assert len(curves) == 6
    assert len({point[MaidrKey.LEVEL] for curve in curves for point in curve}) == 6


def test_stackplot_labels_name_each_band(gallery: _Gallery) -> None:
    """area-errorbar-point-lollipop.qmd: "Pass ``labels=`` and each band is
    announced by name."
    """
    stacked, _plain = gallery[DOCS / "examples/area-errorbar-point-lollipop.qmd"][
        "Area Plot [experimental]"
    ]
    bands = stacked.layer(PlotType.STACKED_AREA)[MaidrKey.DATA]

    assert [{point[MaidrKey.Z] for point in band} for band in bands] == [
        {"Subscriptions"},
        {"Services"},
    ]


def test_pie_is_walked_clockwise_from_the_top(gallery: _Gallery) -> None:
    """pie-wordcloud.qmd: "maidr therefore reads a counterclockwise pie in
    reverse: Fri, then Thur, Sun and Sat, which is the clockwise order from
    12 o'clock."
    """
    slices = gallery.shown("examples/pie-wordcloud.qmd", "Pie Chart").layer(
        PlotType.PIE
    )[MaidrKey.DATA]

    assert [piece[MaidrKey.X] for piece in slices] == ["Fri", "Thur", "Sun", "Sat"]


def test_step_points_carry_the_stage_names(gallery: _Gallery) -> None:
    """line-step.qmd: "maidr attaches the names to each point and announces
    'REM' instead of '3'."
    """
    (points,) = gallery.shown("examples/line-step.qmd", "Step Plot").layer(
        PlotType.STEP
    )[MaidrKey.DATA]

    assert {point[MaidrKey.LABEL] for point in points if point[MaidrKey.Y] == 3} == {
        "REM"
    }


def test_bokeh_lines_are_series_named_by_their_legend(gallery: _Gallery) -> None:
    """examples-bokeh.qmd: "Every ``line`` on a figure becomes one series of
    one line layer, named by its legend label."
    """
    series = gallery.shown("examples-bokeh.qmd", "Multi-Line Plot").layer(
        PlotType.LINE
    )[MaidrKey.DATA]

    assert [{point[MaidrKey.Z] for point in line} for line in series] == [
        {"1949"},
        {"1954"},
        {"1960"},
    ]


def test_bokeh_grid_is_one_subplot_per_figure(gallery: _Gallery) -> None:
    """examples-bokeh.qmd: "Each figure of a ``gridplot``, ``row`` or
    ``column`` is a subplot."
    """
    shown = gallery.shown("examples-bokeh.qmd", "Multi-Panel Layout (gridplot)")

    assert [[layer[MaidrKey.TITLE] for layer in cell] for cell in shown.layers] == [
        ["Penguins per Species"],
        ["Passengers per Year"],
    ]


def test_bokeh_pie_reads_the_values_clockwise(gallery: _Gallery) -> None:
    """examples-bokeh.qmd: "Each slice is announced with the value it was
    computed from -- here the ``penguins`` column ... on a pie Bokeh drew
    counterclockwise from 3 o'clock it starts on the slice drawn last."
    """
    layer = gallery.shown("examples-bokeh.qmd", "Pie Chart").layer(PlotType.PIE)

    assert layer[MaidrKey.AXES][MaidrKey.Y][MaidrKey.LABEL] == "penguins"
    assert [point[MaidrKey.X] for point in layer[MaidrKey.DATA]] == [
        "Gentoo",
        "Chinstrap",
        "Adelie",
    ]
    assert [point[MaidrKey.Y] for point in layer[MaidrKey.DATA]] == [124, 68, 152]


def test_bokeh_harea_steps_through_the_months(gallery: _Gallery) -> None:
    """examples-bokeh.qmd: "the arrow keys step through the months, and the
    passengers are what you hear."
    """
    layer = gallery.shown(
        "examples-bokeh.qmd", "Horizontal Area Plot [experimental]"
    ).layer(PlotType.AREA)

    (band,) = layer[MaidrKey.DATA]
    assert [point[MaidrKey.X] for point in band] == list(range(1, 13))
    assert band[0][MaidrKey.Y] == 417
    assert layer[MaidrKey.AXES][MaidrKey.X][MaidrKey.LABEL] == "Month"
    assert layer[MaidrKey.AXES][MaidrKey.Y][MaidrKey.LABEL] == "Passengers"


def test_bokeh_candlestick_is_a_candle_per_date(gallery: _Gallery) -> None:
    """examples-bokeh.qmd: "**maidr** reads them together as one candlestick,
    a candle per date."
    """
    layer = gallery.shown("examples-bokeh.qmd", "Candlestick Chart").layer(
        PlotType.CANDLESTICK
    )

    candles = layer[MaidrKey.DATA]
    assert len(candles) == 15
    assert candles[0]["value"] == "2024-03-01"
    assert candles[0]["open"] == 100.0
    assert all(
        candle["low"] <= min(candle["open"], candle["close"])
        and candle["high"] >= max(candle["open"], candle["close"])
        for candle in candles
    )


def test_bokeh_gantt_is_a_lane_per_task_in_days(gallery: _Gallery) -> None:
    """examples-bokeh.qmd: "each task is a lane, the up and down arrows move
    between lanes as they are drawn, and every bar is announced with ... its
    length in days."
    """
    layer = gallery.shown("examples-bokeh.qmd", "Gantt Chart [experimental]").layer(
        PlotType.GANTT
    )

    data = layer[MaidrKey.DATA]
    # Bottom to top, as the reversed range draws them.
    assert data[MaidrKey.LANES] == ["Launch", "Test", "Build", "Design", "Research"]
    assert data["unit"] == "days"
    research = data[MaidrKey.POINTS][-1][0]
    assert research[MaidrKey.END] - research[MaidrKey.START] == 9


def test_bokeh_hexbin_counts_every_penguin(gallery: _Gallery) -> None:
    """examples-bokeh.qmd: "Each hexagon is a bin announced by its centre and
    how many penguins fell in it."
    """
    layer = gallery.shown("examples-bokeh.qmd", "Hexbin Plot [experimental]").layer(
        PlotType.HEXBIN
    )

    bins = [cell for row in layer[MaidrKey.DATA] for cell in row]
    assert sum(cell[MaidrKey.COUNT] for cell in bins) == 333
    assert layer[MaidrKey.AXES][MaidrKey.Z][MaidrKey.LABEL] == "Penguins"


def test_bokeh_image_is_the_arrays_cells(gallery: _Gallery) -> None:
    """examples-bokeh.qmd: "An ``image`` is read as a heatmap whose cells are
    the array's, bottom row first as Bokeh draws it, each row and column named
    by the centre of its cells."
    """
    heat = gallery.shown("examples-bokeh.qmd", "Image Heatmap").layer(PlotType.HEAT)[
        MaidrKey.DATA
    ]

    assert len(heat[MaidrKey.POINTS]) == 12
    assert all(len(row) == 12 for row in heat[MaidrKey.POINTS])
    assert heat[MaidrKey.X][0] == "0.125"
    # Emitted top row first: the last row is array row 0, cos(0) = 1.
    assert heat[MaidrKey.Y][-1] == "0.125"
    assert heat[MaidrKey.POINTS][-1][0] == 0.0


def test_plotnine_stack_reads_each_segments_own_count(gallery: _Gallery) -> None:
    """examples-plotnine.qmd: "Each segment is announced with its own count,
    not the height of the stack it sits on, and a species with no penguins on
    an island is announced as missing rather than as zero."
    """
    from plotnine.data import penguins

    layer = gallery.shown("examples-plotnine.qmd", "Stacked Bar Plot").layer(
        PlotType.STACKED
    )
    counts = penguins.groupby(["species", "island"], observed=True).size()
    cells = [cell for row in layer[MaidrKey.DATA] for cell in row]

    for cell in cells:
        key = (cell[MaidrKey.X], cell[MaidrKey.Z])
        expected = float(counts[key]) if key in counts.index else None
        assert cell[MaidrKey.Y] == expected, key
    assert any(cell[MaidrKey.Y] is None for cell in cells)


def test_plotnine_heatmap_leaves_an_unrecorded_cell_empty(gallery: _Gallery) -> None:
    """examples-plotnine.qmd: "A species never recorded on an island has no
    tile, and is announced as missing."
    """
    heat = gallery.shown("examples-plotnine.qmd", "Heatmap").layer(PlotType.HEAT)[
        MaidrKey.DATA
    ]
    row = heat[MaidrKey.Y].index("Chinstrap")
    column = heat[MaidrKey.X].index("Biscoe")

    assert heat[MaidrKey.POINTS][row][column] is None
    assert heat[MaidrKey.POINTS][row][heat[MaidrKey.X].index("Dream")] is not None


def test_plotnine_facets_are_subplots_titled_by_their_facet(gallery: _Gallery) -> None:
    """examples-plotnine.qmd: "Each panel is a subplot, titled by its facet as
    ``cyl = 4``."
    """
    shown = gallery.shown("examples-plotnine.qmd", "Faceted Plot")

    assert [cell[0][MaidrKey.TITLE] for cell in shown.layers] == [
        "cyl = 4",
        "cyl = 6",
        "cyl = 8",
    ]


def test_plotnine_heatmap_colour_bar_stays_light(gallery: _Gallery) -> None:
    """examples-plotnine.qmd: "the rectangles look the same and weigh a few
    tens of kilobytes" -- against the close to 2 MB of plotnine's default
    gradient, which put the page over the 1.9 MB budget of
    ``docs/_scripts/check-page-sizes.sh`` (#825).
    """
    # Through the gallery first, which skips where plotnine is not installed.
    assert gallery.shown("examples-plotnine.qmd", "Heatmap").layer(PlotType.HEAT)

    import io

    import pandas as pd
    from plotnine import aes, geom_tile, ggplot, guide_colorbar, guides

    frame = pd.DataFrame({"a": ["x", "y"], "b": ["u", "u"], "z": [1.0, 2.0]})

    def svg_bytes(plot) -> int:
        buffer = io.StringIO()
        figure = plot.draw()
        figure.savefig(buffer, format="svg")
        plt.close(figure)
        return len(buffer.getvalue())

    base = ggplot(frame, aes("a", "b", fill="z")) + geom_tile()
    light = base + guides(fill=guide_colorbar(display="rectangles"))

    assert svg_bytes(light) < 100_000 < 1_000_000 < svg_bytes(base)


def test_plotnine_normalized_segments_add_up_to_one(gallery: _Gallery) -> None:
    """examples-plotnine.qmd: "the segments of one bar add up to 1."."""
    layer = gallery.shown(
        "examples-plotnine.qmd", "Normalized Stacked Bar Plot [experimental]"
    ).layer(PlotType.NORMALIZED)
    columns = zip(
        *[[c[MaidrKey.Y] or 0.0 for c in row] for row in layer[MaidrKey.DATA]]
    )

    assert [pytest.approx(sum(column)) for column in columns] == [1.0, 1.0, 1.0]


def test_excel_untitled_axis_is_named_after_its_header(gallery: _Gallery) -> None:
    """examples-excel.qmd: "An axis Excel draws no title on is named after the
    header cell above its categories, such as *Quarter*"."""
    layer = gallery.shown("examples-excel.qmd", "Line Chart").layer(PlotType.LINE)

    assert layer[MaidrKey.AXES][MaidrKey.X][MaidrKey.LABEL] == "Quarter"


def test_excel_margin_reads_as_a_percentage(gallery: _Gallery) -> None:
    """examples-excel.qmd: "The margin is read as a percentage, because its
    cells are formatted as one"."""
    shown = gallery.shown("examples-excel.qmd", "Combo Chart on Two Axes")
    axis = shown.layer(PlotType.LINE)[MaidrKey.AXES][MaidrKey.Y]

    assert axis[MaidrKey.LABEL] == "Margin"
    assert axis["format"] == {"type": "percent", "decimals": 0}


def test_excel_histogram_bins_are_ten_points_wide(gallery: _Gallery) -> None:
    """examples-excel.qmd: "here ten points wide, as the chart says, each bin
    including its right end"."""
    layer = gallery.shown("examples-excel.qmd", "Histogram").layer(PlotType.HIST)
    bins = [(b["xMin"], b["xMax"]) for b in layer[MaidrKey.DATA]]

    assert all(high - low == 10 for low, high in bins)
    # The lowest score, 45, starts the first bin; 55 itself falls in it.
    assert bins[0] == (45, 55)
    assert layer[MaidrKey.DATA][0]["y"] == 3


def test_excel_waterfall_totals_are_read_from_zero(gallery: _Gallery) -> None:
    """examples-excel.qmd: "The opening and closing balances are set as totals
    in Excel, so each is read from zero"."""
    shown = gallery.shown("examples-excel.qmd", "Waterfall Chart [experimental]")
    steps = shown.layer(PlotType.WATERFALL)[MaidrKey.DATA]

    for step in (steps[0], steps[-1]):
        assert (step["kind"], step["start"]) == ("total", 0)
    assert [s["end"] for s in (steps[0], steps[-1])] == [500, 430]


def test_office_untitled_axis_is_named_after_its_data_sheet(
    gallery: _Gallery,
) -> None:
    """examples-office.qmd: "The category axis has no title on the slide, so it
    is named after the header above the quarters in the chart's data sheet,
    *Quarter*"."""
    shown = gallery.shown("examples-office.qmd", "Column Chart on a Slide")
    layer = shown.layer(PlotType.DODGED)

    assert layer[MaidrKey.AXES][MaidrKey.X][MaidrKey.LABEL] == "Quarter"


def test_office_margin_reads_as_a_percentage(gallery: _Gallery) -> None:
    """examples-office.qmd: "The margin is read as a percentage, because its
    data sheet formats it as one"."""
    shown = gallery.shown("examples-office.qmd", "Line Chart on a Slide")
    axis = shown.layer(PlotType.LINE)[MaidrKey.AXES][MaidrKey.Y]

    assert axis["format"] == {"type": "percent", "decimals": 0}


def test_office_teams_are_named_after_their_data_sheet(gallery: _Gallery) -> None:
    """examples-office.qmd: "The teams are named after the header above them in
    the chart's data sheet, *Team*"."""
    shown = gallery.shown("examples-office.qmd", "Bar Chart in a Document")
    layer = shown.layer(PlotType.BAR)

    assert layer[MaidrKey.AXES][MaidrKey.Y][MaidrKey.LABEL] == "Team"


def test_office_charts_of_a_hidden_slide_are_read_and_say_so() -> None:
    """examples-office.qmd: "a chart on each of three slides, the last of them
    hidden" and "The charts of hidden slides are read too"."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        charts = read_powerpoint_charts(DOCS / "slides.pptx")

    slides = [(chart.slide, chart.hidden) for chart in charts]
    assert slides == [(2, False), (3, False), (4, True)]
    for chart in charts:
        maidr.close(chart)


def _final_losses(shown: Shown) -> dict[str, float]:
    """Each line's last value, by the name it is announced under."""
    (lines,) = [cell[0][MaidrKey.DATA] for cell in shown.layers]
    return {line[0][MaidrKey.Z]: line[-1][MaidrKey.Y] for line in lines}


def _halfway(shown: Shown) -> dict[str, float]:
    """Each line's value at its middle point."""
    (lines,) = [cell[0][MaidrKey.DATA] for cell in shown.layers]
    return {line[0][MaidrKey.Z]: line[len(line) // 2][MaidrKey.Y] for line in lines}


def test_wandb_lora_loss_falls_faster_and_further(gallery: _Gallery) -> None:
    """examples-wandb.qmd: "The *lora-r16* run's loss falls faster and further
    than the baseline's."
    """
    shown = gallery.shown("examples-wandb.qmd", "Training Loss")
    assert _halfway(shown)["lora-r16"] < _halfway(shown)["baseline"]
    assert _final_losses(shown)["lora-r16"] < _final_losses(shown)["baseline"]


def test_wandb_eval_loss_is_every_twenty_steps(gallery: _Gallery) -> None:
    """examples-wandb.qmd: "here the evaluation loss, every 20 steps." """
    (lines,) = [
        cell[0][MaidrKey.DATA]
        for cell in gallery.shown("examples-wandb.qmd", "Evaluation Loss").layers
    ]
    for line in lines:
        assert [point[MaidrKey.X] for point in line] == [19, 39, 59, 79, 99, 119]


def test_mlflow_lists_the_newest_run_first(gallery: _Gallery) -> None:
    """examples-mlflow.qmd: "*lora-r16* is the first line. Its loss falls
    faster and further than the baseline's."
    """
    shown = gallery.shown("examples-mlflow.qmd", "Training Loss")
    assert list(_final_losses(shown)) == ["lora-r16", "baseline"]
    assert _halfway(shown)["lora-r16"] < _halfway(shown)["baseline"]
    assert _final_losses(shown)["lora-r16"] < _final_losses(shown)["baseline"]
