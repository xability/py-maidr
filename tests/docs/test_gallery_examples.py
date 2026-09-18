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

import maidr
from maidr import api
from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.core.figure_manager import FigureManager

DOCS = Path(__file__).parents[2] / "docs"

#: The gallery: the matplotlib/seaborn family pages plus the one-page Plotly
#: and Altair galleries. Discovered rather than listed, so a new page is run
#: as soon as it exists -- and fails below until its sections are listed.
PAGES = sorted(DOCS.glob("examples*.qmd")) + sorted((DOCS / "examples").glob("*.qmd"))

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
        "Area Plot": [["stacked_area"], ["area"]],
        "Error Bar Plot": [["error_bar"]],
        "Point Plot": [["error_bar"]],
        "Lollipop Plot": [["lollipop"]],
    },
    "examples/bar.qmd": {
        "Bar Plot": [["bar"]],
        "Count Plot": [["bar"]],
        "Stacked Bar Plot": [["stacked_bar"]],
        "Dodged Bar Plot": [["dodged_bar"]],
    },
    "examples/box-boxen-violin.qmd": {
        "Box Plot": [["box"]],
        "Boxen Plot (Letter-Value Plot)": [["boxen"]],
        "Seaborn Violin Plot (Horizontal)": [["violin_box + violin_kde"]],
        "Matplotlib Violin Plot": [["violin_box + violin_kde"]],
    },
    "examples/candlestick-gantt.qmd": {
        # The candles, the three moving averages as one line layer, and the
        # volume bars. All in one cell: mplfinance places its panels with
        # `add_axes` rather than a gridspec, so none carries a subplotspec
        # and every layer reports position (0, 0). The page's "volume panel
        # available as its own subplot" is not what the reader gets today.
        "Candlestick Chart": [["candlestick + bar + line"]],
        "Gantt Chart": [["gantt"]],
    },
    "examples/heatmap-hexbin-contour.qmd": {
        "Heat Map": [["heat"]],
        "Hexbin Plot": [["hexbin"]],
        "Contour Plot": [["contour"]],
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
        "Word Cloud": [["word_cloud"]],
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
        """``maidr.show(plot)``: an Altair chart, a Plotly figure, or pyplot."""
        if api._is_altair_chart(plot):
            self._record(_from_altair(plot))
        elif plot is not None and api._is_plotly_figure(plot):
            self._record(_from_schema(api._get_plotly_maidr(plot)._flatten_maidr()))
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
    data = gallery.shown("examples/candlestick-gantt.qmd", "Gantt Chart").layer(
        PlotType.GANTT
    )[MaidrKey.DATA]

    assert data[MaidrKey.LANES] == ["Design", "Build", "Launch"]
    assert [len(lane) for lane in data[MaidrKey.POINTS]] == [1, 2, 1]


def test_contour_reads_six_curves_for_six_levels(gallery: _Gallery) -> None:
    """heatmap-hexbin-contour.qmd: "On a single-peaked surface like this
    one the two coincide -- six levels, six curves."
    """
    curves = gallery.shown("examples/heatmap-hexbin-contour.qmd", "Contour Plot").layer(
        PlotType.CONTOUR
    )[MaidrKey.DATA]

    assert len(curves) == 6
    assert len({point[MaidrKey.LEVEL] for curve in curves for point in curve}) == 6


def test_stackplot_labels_name_each_band(gallery: _Gallery) -> None:
    """area-errorbar-point-lollipop.qmd: "Pass ``labels=`` and each band is
    announced by name."
    """
    stacked, _plain = gallery[DOCS / "examples/area-errorbar-point-lollipop.qmd"][
        "Area Plot"
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
