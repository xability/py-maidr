"""`acorr` and `xcorr` are one chart drawn two ways, read the same way (#577)."""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ElementTree

import matplotlib.pyplot as plt
import numpy as np
import pytest

import maidr
from maidr.core.enum import MaidrKey, PlotType
from maidr.core.figure_manager import FigureManager
from maidr.exception import UnsupportedPlotError

SERIES = np.sin(np.arange(40, dtype=float))
SVG_NS = "{http://www.w3.org/2000/svg}"


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _layers(fig) -> list:
    try:
        return [plot.type for plot in FigureManager.get_maidr(fig).plots]
    except UnsupportedPlotError:
        return []


def _schema(fig) -> dict:
    plots = FigureManager.get_maidr(fig).plots
    assert len(plots) == 1
    return plots[0].schema


@pytest.mark.parametrize("draw", ["acorr", "xcorr"])
@pytest.mark.parametrize("usevlines", [True, False])
def test_a_correlogram_is_one_lollipop_layer(draw: str, usevlines: bool) -> None:
    fig, ax = plt.subplots()
    if draw == "acorr":
        ax.acorr(SERIES, usevlines=usevlines)
    else:
        ax.xcorr(SERIES, SERIES[::-1], usevlines=usevlines)

    assert _layers(fig) == [PlotType.LOLLIPOP]


@pytest.mark.parametrize("usevlines", [True, False])
def test_both_spellings_announce_the_same_numbers(usevlines: bool) -> None:
    """The keyword changes which artists are drawn, not what the chart says."""
    fig, ax = plt.subplots()
    lags, correlations, _, _ = ax.acorr(SERIES, usevlines=usevlines)

    data = _schema(fig)[MaidrKey.DATA]
    assert [entry[MaidrKey.X] for entry in data] == [float(lag) for lag in lags]
    assert [entry[MaidrKey.Y] for entry in data] == [
        float(value) for value in correlations
    ]


def test_the_two_spellings_agree_with_each_other() -> None:
    fig, ax = plt.subplots()
    ax.acorr(SERIES)
    stems = _schema(fig)[MaidrKey.DATA]

    other, axis = plt.subplots()
    axis.acorr(SERIES, usevlines=False)
    markers = _schema(other)[MaidrKey.DATA]

    assert stems == markers


def test_the_reference_line_is_not_announced() -> None:
    """`usevlines=True` draws a horizontal line at zero; it is not data."""
    fig, ax = plt.subplots()
    ax.acorr(SERIES)

    assert PlotType.LINE not in _layers(fig)
    values = [entry[MaidrKey.Y] for entry in _schema(fig)[MaidrKey.DATA]]
    assert len(values) == 21


def test_the_chart_is_announced_vertically() -> None:
    fig, ax = plt.subplots()
    ax.acorr(SERIES)

    assert _schema(fig)[MaidrKey.ORIENTATION] == "vert"


def test_the_lag_at_zero_correlates_perfectly_with_itself() -> None:
    """A sanity check on the numbers themselves, not just their shape."""
    fig, ax = plt.subplots()
    ax.acorr(SERIES)

    data = _schema(fig)[MaidrKey.DATA]
    at_zero = next(entry for entry in data if entry[MaidrKey.X] == 0.0)
    assert at_zero[MaidrKey.Y] == pytest.approx(1.0)


def test_every_mark_has_a_selector_of_its_own() -> None:
    fig, ax = plt.subplots()
    ax.acorr(SERIES)

    schema = _schema(fig)
    selectors = schema[MaidrKey.SELECTOR]
    assert len(selectors) == len(schema[MaidrKey.DATA])
    assert len(set(selectors)) == len(selectors)


def test_the_stems_are_addressed_as_the_paths_they_are_drawn_as() -> None:
    """Measured by parsing the SVG: one bare `<path>` child per segment."""
    fig, ax = plt.subplots()
    ax.acorr(SERIES)

    schema = _schema(fig)
    gid = re.search(r"g\[id='([^']+)'\]", schema[MaidrKey.SELECTOR][0]).group(1)
    assert "> path:nth-of-type(1)" in schema[MaidrKey.SELECTOR][0]

    buffer = io.BytesIO()
    fig.savefig(buffer, format="svg")
    buffer.seek(0)
    root = ElementTree.fromstring(buffer.read())

    group = next(g for g in root.iter(f"{SVG_NS}g") if g.get("id") == gid)
    children = [child for child in group if child.tag == f"{SVG_NS}path"]
    assert len(children) == 21
    assert {child.tag for child in group} == {f"{SVG_NS}path"}


def test_the_markers_are_addressed_as_the_uses_they_are_drawn_as() -> None:
    """The other spelling nests its marks and shares one shape from a defs."""
    fig, ax = plt.subplots()
    ax.acorr(SERIES, usevlines=False)

    schema = _schema(fig)
    assert "use:nth-of-type(1)" in schema[MaidrKey.SELECTOR][0]
    assert "> path" not in schema[MaidrKey.SELECTOR][0]


def test_a_chart_beside_a_correlogram_is_untouched() -> None:
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    ax.acorr(SERIES)

    assert sorted(layer.value for layer in _layers(fig)) == ["bar", "lollipop"]


def test_a_line_drawn_after_a_correlogram_is_still_read() -> None:
    """Drawing quietly must not silence the caller's own plot."""
    fig, ax = plt.subplots()
    ax.acorr(SERIES)
    ax.plot([1, 2, 3], [1, 2, 3])

    assert sorted(layer.value for layer in _layers(fig)) == ["line", "lollipop"]


def test_a_correlogram_with_nothing_drawable_registers_no_layer() -> None:
    fig, ax = plt.subplots()
    ax.acorr(np.full(40, np.nan))

    with pytest.raises(UnsupportedPlotError):
        FigureManager.get_maidr(fig)


def test_the_chart_renders() -> None:
    fig, ax = plt.subplots()
    ax.acorr(SERIES)

    assert len(maidr.render(fig)._repr_html_()) > 0


def test_maxlags_decides_how_many_marks_there_are() -> None:
    fig, ax = plt.subplots()
    ax.acorr(SERIES, maxlags=4)

    assert len(_schema(fig)[MaidrKey.DATA]) == 9
