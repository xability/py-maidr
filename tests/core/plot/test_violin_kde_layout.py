"""
The KDE layer settles the figure layout once per extraction, not once per point.

``svg_x``/``svg_y`` are read off the axes position, and that position is only
final once the figure has been drawn -- so the transform used to settle the
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

A figure with a layout engine of its own is laid out by it and no other: it
used to be laid out tight, which replaced a constrained layout with a tight
one. One without is laid out tight, as it always was, except for a chart
written into a Quarto page, which keeps the layout of the plain figure
beside it and is only drawn. A render settles the figure once, however many
violins it holds.
"""

from __future__ import annotations

import io

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
from maidr.util import svg_utils  # noqa: E402
from maidr.util.svg_utils import settling  # noqa: E402

#: Four categories, so the RDP pass has something to thin on every violin.
CATEGORIES = ["ash", "birch", "cedar", "dogwood"]


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


@pytest.fixture(params=[False, True], ids=["elsewhere", "in-a-page"])
def in_page(request, mocker):
    """A render outside a Quarto page, and one writing the chart into it."""
    mocker.patch("maidr.core.maidr.inline_applies", return_value=request.param)
    return request.param


def _pass(keep_layout: bool) -> str:
    """What settles a figure without a layout engine."""
    return "draw_without_rendering" if keep_layout else "tight_layout"


def _violins(orientation: str, layout: str | None = None):
    """Draw four seaborn violins and return ``(fig, ax)``."""
    rng = np.random.default_rng(704)
    cats = [cat for cat in CATEGORIES for _ in range(25)]
    vals = np.concatenate(
        [rng.normal(loc, 1.0, 25) for loc, _ in enumerate(CATEGORIES)]
    ).tolist()
    fig, ax = plt.subplots(layout=layout)
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


@pytest.mark.parametrize("keep_layout", [False, True])
@pytest.mark.parametrize("orientation", ["vert", "horz"])
def test_one_layout_pass_per_extraction(
    mocker, orientation: str, keep_layout: bool
) -> None:
    """Extracting the KDE layer settles the layout once, however many points."""
    fig, _ = _violins(orientation)
    layer = _kde_layer(fig)
    spy = mocker.spy(Figure, _pass(keep_layout))

    with settling(keep_layout=keep_layout):
        points = sum(len(violin) for violin in layer.render()["data"])

    assert points > 4, "the fixture must retain several levels per violin"
    assert spy.call_count == 1


def test_one_layout_pass_per_render(mocker, in_page) -> None:
    """A whole ``maidr.render`` of a violin figure settles the layout once."""
    fig, _ = _violins("vert")
    spy = mocker.spy(Figure, _pass(in_page))

    maidr.render(fig)

    assert spy.call_count == 1


@pytest.mark.parametrize("layout", [None, "constrained", "tight"])
def test_a_render_settles_a_grid_of_violins_once(mocker, in_page, layout) -> None:
    """Six violin layers, one settle: the figure is the same for each of them.

    A figure with a layout engine is settled through SVG saves, a few of
    them; six layers made six times as many, and a render four or five
    times as long.
    """
    rng = np.random.default_rng(731)
    fig, axes = plt.subplots(2, 3, layout=layout)
    for ax in axes.flat:
        cats = [cat for cat in CATEGORIES[:3] for _ in range(20)]
        sns.violinplot(x=cats, y=rng.normal(size=60).tolist(), ax=ax)
    engine = mocker.spy(svg_utils, "_settle_engine")
    other = mocker.spy(Figure, _pass(in_page))
    saved = mocker.spy(Figure, "savefig")

    maidr.render(fig)

    layers = [
        plot
        for plot in FigureManager.get_maidr(fig).plots
        if plot.type is PlotType.VIOLIN_KDE
    ]
    assert len(layers) == 6
    assert engine.call_count + other.call_count == 1
    # The settle's saves, at most, and the chart's own.
    assert saved.call_count <= svg_utils._ENGINE_PASSES + 1


@pytest.mark.parametrize("hinting", ["no_hinting", "force_autohint"])
@pytest.mark.parametrize("layout", [None, "constrained", "tight"])
@pytest.mark.parametrize("orientation", ["vert", "horz"])
def test_svg_coords_match_the_layout_the_svg_was_saved_from(
    orientation, layout, hinting, in_page
) -> None:
    """
    After a render, every ``svg_*`` agrees with the figure's transform.

    The SVG is written after extraction, from whatever layout the figure is
    then in. A reader's cursor lands on the outline only if the coordinates
    were computed under that same layout -- the property the pass count was
    standing in for. Exactly, for a figure without a layout engine; within a
    hundredth of a point for one with its own, which the SVG's save runs
    once more. With text hinted, as matplotlib's default has it, or not:
    the raster renderer measures hinted text otherwise than the SVG's.
    """
    with plt.rc_context({"text.hinting": hinting}):
        fig, ax = _violins(orientation, layout)
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
            now = _svg_coords_now(fig, ax, *probe)[axis]
            if layout is None:
                assert point[key] == now
            else:
                assert point[key] == pytest.approx(now, abs=0.01)
            checked += 1
    assert checked > 0


@pytest.mark.parametrize("orientation", ["vert", "horz"])
def test_data_coordinates_do_not_follow_the_layout(orientation: str) -> None:
    """Only ``svg_*`` moves with the layout; ``x``, ``y`` and ``width`` stay."""
    fig, _ = _violins(orientation)
    layer = _kde_layer(fig)
    before = layer.render()["data"]

    # A different canvas puts the axes elsewhere in points, so every svg_*
    # genuinely moves between renders.
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


def test_in_a_page_a_figure_without_a_layout_engine_keeps_its_layout(
    mocker,
) -> None:
    """The violins sit where they sit in the plain figure beside the chart."""
    mocker.patch("maidr.core.maidr.inline_applies", return_value=True)
    fig, ax = _violins("vert")
    params = vars(fig.subplotpars).copy()
    position = ax.get_position().bounds

    maidr.render(fig)

    assert vars(fig.subplotpars) == params
    assert ax.get_position().bounds == pytest.approx(position)
    assert fig.get_layout_engine() is None


@pytest.mark.parametrize("layout", ["constrained", "compressed", "tight"])
def test_a_figures_own_layout_engine_is_kept_and_run(recwarn, layout, in_page) -> None:
    """A constrained layout stays constrained, with no warning that it changed.

    The axes end where the same figure's own engine puts them without maidr,
    to within 0.005 of the figure: the engine runs more often here, which
    settles them a fraction of a point from where its first pass put them.
    Another engine's layout would move them by ten times that.
    """
    fig, ax = _violins("vert", layout)
    engine = type(fig.get_layout_engine())
    reference, reference_ax = _violins("vert", layout)
    reference.savefig(io.StringIO(), format="svg")

    maidr.render(fig)

    assert type(fig.get_layout_engine()) is engine
    assert ax.get_position().bounds == pytest.approx(
        reference_ax.get_position().bounds, abs=0.005
    )
    assert not [w for w in recwarn if "layout has changed" in str(w.message)]
