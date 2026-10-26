"""A boxen layer names each distribution's ladder, so the one read is outlined.

maidr.js reads a boxen's selectors as one element per distribution, in the
order the distributions are declared, and outlines that element for every
rung of the distribution (docs/SCHEMA.md, "Selectors" by layer type). seaborn
draws each ladder as one ``PatchCollection``, whose group in the SVG holds
every box of it. The layer used to emit no selectors at all, so no step of a
boxen plot was outlined.
"""

from __future__ import annotations

import re

import numpy as np
import pytest

sns = pytest.importorskip("seaborn")
pytest.importorskip("lxml")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from lxml import etree  # noqa: E402
from lxml.cssselect import CSSSelector  # noqa: E402
from matplotlib.collections import PatchCollection  # noqa: E402

import maidr  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    """Three groups far enough apart that each ladder's span is its own."""
    rng = np.random.default_rng(6)
    return pd.DataFrame(
        {
            "g": np.repeat(["a", "b", "c"], 400),
            "v": np.concatenate([rng.normal(loc, 1.0, 400) for loc in (0, 10, 20)]),
            "h": np.tile(["u", "w"], 600),
        }
    )


CHARTS = {
    "vertical": lambda ax: sns.boxenplot(data=_frame(), x="g", y="v", ax=ax),
    "horizontal": lambda ax: sns.boxenplot(data=_frame(), x="v", y="g", ax=ax),
    "hue": lambda ax: sns.boxenplot(data=_frame(), x="g", y="v", hue="h", ax=ax),
}


def _render(draw):
    """Draw a boxen chart, render it, and return its axes, layer and SVG."""
    figure, ax = plt.subplots()
    draw(ax)
    html = maidr.render(figure)._repr_html_()
    svg = re.search(r"<svg.*?</svg>", html, re.S)
    assert svg is not None
    root = etree.fromstring(svg.group(0).encode(), etree.XMLParser(recover=True))
    for element in root.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]
    (layer,) = [
        plot.schema
        for plot in FigureManager.get_maidr(figure)._plots
        if plot.schema.get("type") == "boxen"
    ]
    return ax, layer, root


@pytest.mark.parametrize("chart", list(CHARTS))
def test_each_distribution_names_one_drawn_ladder(chart: str) -> None:
    """One selector per distribution, each matching one group of boxes."""
    _, layer, root = _render(CHARTS[chart])

    selectors = layer["selectors"]
    assert len(selectors) == len(layer["data"])
    matched = [CSSSelector(selector)(root) for selector in selectors]
    assert [len(found) for found in matched] == [1] * len(selectors)
    for (group,) in matched:
        assert group.tag == "g"
        assert len(group.findall("path")) >= 3, "not a ladder of boxes"
    assert len({id(group) for (group,) in matched}) == len(matched)


@pytest.mark.parametrize("chart", list(CHARTS))
def test_each_selector_names_its_own_distributions_ladder(chart: str) -> None:
    """Selector *i* names the ladder whose outermost box is row *i*'s."""
    ax, layer, _ = _render(CHARTS[chart])
    vertical = layer["orientation"] == "vert"
    ladders = {
        collection.get_gid(): collection
        for collection in ax.collections
        if isinstance(collection, PatchCollection)
    }

    for row, selector in zip(layer["data"], layer["selectors"]):
        gid = selector.split("id='", 1)[1].split("'", 1)[0]
        vertices = np.concatenate(
            [path.vertices for path in ladders[gid].get_paths()]
        )
        along = vertices[:, 1] if vertical else vertices[:, 0]
        deepest = min(row["levels"], key=lambda level: level["p"])
        assert (along.min(), along.max()) == pytest.approx(
            (deepest["lo"], deepest["hi"])
        )


def test_a_second_render_keeps_one_selector_per_distribution() -> None:
    """The gid list is rebuilt per extraction rather than appended to."""
    figure, ax = plt.subplots()
    CHARTS["vertical"](ax)
    maidr.render(figure)._repr_html_()
    maidr.render(figure)._repr_html_()

    (plot,) = FigureManager.get_maidr(figure)._plots
    schema = plot.render()
    assert len(schema["selectors"]) == len(schema["data"]) == 3
