"""
The KDE layer settles the figure layout once per extraction, not once per point.

``svg_x``/``svg_y`` are read off the axes position, and that position is only
final after ``tight_layout`` has run -- so the transform used to settle the
layout before converting each point, and one violin render ran a full layout
pass (text extents for every artist on the figure) once per KDE curve and
twice more per retained level: 124 passes for four seaborn violins, ~95% of
the render time, and every one of them rewriting the caller's subplot
parameters (#704).

The layout only has to be settled before the *first* conversion. What a reader
depends on is not the pass count but that the coordinates were computed under
the same layout the SVG was then saved from, so that is what these assert --
never SVG bytes or the ``svg_*`` floats themselves, which a single layout
pass is free to move by a fraction of a point.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

import maidr  # noqa: E402
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402

#: Four categories, so the RDP pass has something to thin on every violin.
CATEGORIES = ["ash", "birch", "cedar", "dogwood"]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _violins(orientation: str):
    """Draw four seaborn violins and return ``(fig, ax)``."""
    rng = np.random.default_rng(704)
    cats = [cat for cat in CATEGORIES for _ in range(25)]
    vals = np.concatenate(
        [rng.normal(loc, 1.0, 25) for loc, _ in enumerate(CATEGORIES)]
    ).tolist()
    fig, ax = plt.subplots()
    if orientation == "horz":
        sns.violinplot(x=vals, y=cats, ax=ax)
    else:
        sns.violinplot(x=cats, y=vals, ax=ax)
    return fig, ax


def _kde_layer(fig):
    """The figure's single ``violin_kde`` layer."""
    layers = [
        plot
        for plot in FigureManager.get_maidr(fig).plots
        if plot.type is PlotType.VIOLIN_KDE
    ]
    assert len(layers) == 1, f"expected one KDE layer, got {len(layers)}"
    return layers[0]


def _svg_coords_now(fig, ax, x: float, y: float) -> tuple[float, float]:
    """Where the figure's *current* transform puts a data point, in SVG points."""
    disp = ax.transData.transform([[x, y]])
    figpix = fig.transFigure.inverted().transform(disp)
    width_pts = fig.get_size_inches()[0] * 72
    height_pts = fig.get_size_inches()[1] * 72
    return float(figpix[0, 0] * width_pts), float((1 - figpix[0, 1]) * height_pts)


@pytest.mark.parametrize("orientation", ["vert", "horz"])
def test_one_layout_pass_per_extraction(mocker, orientation: str) -> None:
    """Extracting the KDE layer settles the layout once, however many points."""
    fig, _ = _violins(orientation)
    layer = _kde_layer(fig)
    spy = mocker.spy(Figure, "tight_layout")

    points = sum(len(violin) for violin in layer.render()["data"])

    assert points > 4, "the fixture must retain several levels per violin"
    assert spy.call_count == 1


def test_one_layout_pass_per_render(mocker) -> None:
    """A whole ``maidr.render`` of a violin figure settles the layout once."""
    fig, _ = _violins("vert")
    spy = mocker.spy(Figure, "tight_layout")

    maidr.render(fig)

    assert spy.call_count == 1


@pytest.mark.parametrize("orientation", ["vert", "horz"])
def test_svg_coords_match_the_layout_the_svg_was_saved_from(orientation) -> None:
    """
    After a render, every ``svg_*`` agrees exactly with the figure's transform.

    The SVG is written after extraction, from whatever layout the figure is
    then in. A reader's cursor lands on the outline only if the coordinates
    were computed under that same layout -- the property the pass count was
    standing in for.
    """
    fig, ax = _violins(orientation)
    maidr.render(fig)
    layer = _kde_layer(fig)

    # A value on the category axis has no bearing on the value axis.
    axis = 1 if orientation == "vert" else 0
    key = "svg_y" if orientation == "vert" else "svg_x"
    checked = 0
    for violin in layer.schema["data"]:
        for point in violin:
            value = point["y"]
            probe = (0.0, value) if orientation == "vert" else (value, 0.0)
            assert point[key] == _svg_coords_now(fig, ax, *probe)[axis]
            checked += 1
    assert checked > 0


@pytest.mark.parametrize("orientation", ["vert", "horz"])
def test_data_coordinates_do_not_follow_the_layout(orientation: str) -> None:
    """Only ``svg_*`` moves with the layout; ``x``, ``y`` and ``width`` stay."""
    fig, _ = _violins(orientation)
    layer = _kde_layer(fig)
    before = layer.render()["data"]

    # A different canvas gives tight_layout a different answer, so the axes
    # position -- and with it every svg_* -- genuinely moves between renders.
    width, height = fig.get_size_inches()
    fig.set_size_inches(width * 1.5, height * 0.75)
    after = layer.render()["data"]

    def _data_only(violins):
        return [
            [{k: v for k, v in pt.items() if not k.startswith("svg_")} for pt in v]
            for v in violins
        ]

    assert _data_only(after) == _data_only(before)
    assert after != before, "the layout change did not reach the svg_* keys"
