"""Every point layer's selector names drawn markers, one per point.

A point layer's ``selectors`` address the chart's markers in the exported SVG,
through either the group's ``id`` (the collection's gid) or its ``maidr``
attribute (written by ``maidr/patch/highlight.py`` while the collection is
drawn). The second only exists if the collection's draw went through the
highlight wrapper, which nothing in the payload can show.

``sns.swarmplot`` is where it did not. Seaborn packs a swarm at draw time, so
``plot_swarms`` binds a ``draw`` of its own onto each collection and ends it
with ``super(PathCollection, points).draw(renderer)``. The wrapper sat on
``PathCollection.draw`` -- exactly the attribute both of those skip -- so a
swarm's groups carried no ``maidr`` attribute, every layer's
``g[maidr='<id>'] > g > use`` matched nothing in the page, and each point was
announced with nothing outlined. Measured before the fix on a three-category
swarm: three selectors, each id present 0 times in the SVG; the strip plot
of the same data, 1 each.

These resolve every emitted selector against the exported SVG, across the
charts that emit point layers, and for the swarm also check that the markers
matched are the packed ones seaborn drew, on the value the payload carries.
The highlight itself is measured in a browser by
``tests/browser/test_scatter_highlight.py``.
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

import maidr  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def frame() -> pd.DataFrame:
    """Three categories of twelve values, with ties for the swarm to pack."""
    rng = np.random.default_rng(3)
    return pd.DataFrame(
        {
            "g": np.repeat(["a", "b", "c"], 12),
            "y": np.round(rng.normal(10, 3, 36), 1),
            "h": np.tile(["u", "v"], 18),
        }
    )


#: Charts that emit ``point`` layers, keyed by a readable name.
CHARTS = {
    "ax.scatter": lambda ax: ax.scatter([1, 2, 3, 4], [3, 5, 2, 4]),
    "two ax.scatter calls": lambda ax: (
        ax.scatter([1, 2], [3, 4]),
        ax.scatter([3, 4], [1, 2]),
    ),
    "sns.scatterplot": lambda ax: sns.scatterplot(data=frame(), x="y", y="y", ax=ax),
    "sns.scatterplot hue": lambda ax: sns.scatterplot(
        data=frame(), x="y", y="y", hue="h", ax=ax
    ),
    "sns.stripplot": lambda ax: sns.stripplot(data=frame(), x="g", y="y", ax=ax),
    "sns.stripplot hue": lambda ax: sns.stripplot(
        data=frame(), x="g", y="y", hue="h", ax=ax
    ),
    "sns.swarmplot": lambda ax: sns.swarmplot(data=frame(), x="g", y="y", ax=ax),
    "sns.swarmplot horizontal": lambda ax: sns.swarmplot(
        data=frame(), x="y", y="g", ax=ax
    ),
    "sns.swarmplot hue": lambda ax: sns.swarmplot(
        data=frame(), x="g", y="y", hue="h", ax=ax
    ),
    "sns.swarmplot dodge": lambda ax: sns.swarmplot(
        data=frame(), x="g", y="y", hue="h", dodge=True, ax=ax
    ),
}


def _render(draw):
    """Draw a chart, render it, and return its point layers and its SVG."""
    figure, ax = plt.subplots()
    draw(ax)
    html = maidr.render(figure)._repr_html_()
    svg = re.search(r"<svg.*?</svg>", html, re.S)
    assert svg is not None
    root = etree.fromstring(svg.group(0).encode(), etree.XMLParser(recover=True))
    for element in root.iter():
        if isinstance(element.tag, str) and "}" in element.tag:
            element.tag = element.tag.split("}", 1)[1]
    layers = [
        plot.schema
        for plot in FigureManager.get_maidr(figure)._plots
        if plot.schema.get("type") == "point"
    ]
    return figure, ax, layers, root


@pytest.mark.parametrize("chart", list(CHARTS))
def test_every_point_layer_selector_resolves_one_marker_per_point(chart):
    _, _, layers, root = _render(CHARTS[chart])
    assert layers, "the chart emitted no point layer"

    matched: list = []
    for layer in layers:
        selector = layer["selectors"]
        assert isinstance(selector, str)
        found = CSSSelector(selector)(root)
        assert len(found) == len(layer["data"]), (
            f"{selector[:80]!r} matched {len(found)} elements for "
            f"{len(layer['data'])} points"
        )
        matched.extend(found)

    # No marker is claimed by two layers.
    assert len({id(element) for element in matched}) == len(matched)


@pytest.mark.parametrize("chart", list(CHARTS))
def test_every_maidr_id_a_selector_names_is_in_the_svg(chart):
    # The narrower form of the above, and the defect's own signature: the
    # id appeared in the payload and nowhere in the drawing.
    _, _, layers, root = _render(CHARTS[chart])
    tagged = {element.get("maidr") for element in root.iter() if element.get("maidr")}
    for layer in layers:
        for named in re.findall(r"g\[maidr='([^']+)'\]", layer["selectors"]):
            assert named in tagged


@pytest.mark.parametrize(
    ("chart", "value_axis"),
    [("sns.swarmplot", "y"), ("sns.swarmplot horizontal", "x")],
)
def test_a_swarm_resolves_to_the_markers_seaborn_packed(chart, value_axis):
    # Seaborn moves a swarm's markers across the category axis while it
    # draws; the value axis is untouched. So each layer's markers must sit
    # where the value axis puts that layer's values -- the markers of its
    # own category, as drawn, rather than some other group's.
    figure, ax, layers, root = _render(CHARTS[chart])
    assert len(layers) == 3

    # The SVG is written in points, with y running down from the top.
    scale = 72 / figure.dpi
    height = figure.get_figheight() * 72
    for layer in layers:
        found = CSSSelector(layer["selectors"])(root)
        if value_axis == "y":
            drawn = sorted(height - float(use.get("y")) for use in found)
            values = [point["y"] for point in layer["data"]]
            want = sorted(
                ax.transData.transform([(0, v) for v in values])[:, 1] * scale
            )
        else:
            drawn = sorted(float(use.get("x")) for use in found)
            values = [point["x"] for point in layer["data"]]
            want = sorted(
                ax.transData.transform([(v, 0) for v in values])[:, 0] * scale
            )
        assert np.allclose(drawn, want, atol=0.01)

    # And across the category axis, the packing spread each group out.
    across = "x" if value_axis == "y" else "y"
    for layer in layers:
        found = CSSSelector(layer["selectors"])(root)
        assert len({use.get(across) for use in found}) > 1
