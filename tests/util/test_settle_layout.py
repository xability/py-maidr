"""``settle_layout`` places the axes as the SVG will, imposing a layout only where it must.

The violin and regression layers convert their points to SVG coordinates,
which read the axes position, so they settle the figure's layout first.

A figure with a layout engine of its own is laid out by it alone: it used
to be re-laid-out tight, which replaced a constrained layout, with a
warning. A figure without one is laid out tight, as it always was, except
for a chart written into a Quarto page (``settling(keep_layout=True)``),
which is cut to what is drawn, as the plain figure beside it is, and so
keeps the plain figure's layout: there, re-laying it out showed the two
side by side at different shapes. Elsewhere the SVG is the figure's canvas,
and a small figure's axis labels lie past it unless it is laid out to fit
them. Within a render (:func:`settling`), a figure is settled once however
many layers ask. The violin layer's pass count and coordinates are pinned
in ``tests/core/plot/test_violin_kde_layout.py``.
"""

from __future__ import annotations

import io
import itertools

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.transforms import Bbox  # noqa: E402

import maidr  # noqa: E402
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.util.svg_utils import (  # noqa: E402
    data_to_svg_coords,
    settle_layout,
    settling,
)

sns = pytest.importorskip("seaborn")


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _labelled(layout: str | None = None):
    fig, ax = plt.subplots(figsize=(4, 3), layout=layout)
    ax.plot([1, 2, 3], [3, 1, 2])
    ax.set_xlabel("A long label for the x axis")
    ax.set_ylabel("Units")
    ax.set_title("A title")
    return fig, ax


def _regression(layout: str | None = None):
    rng = np.random.default_rng(0)
    x = np.arange(1, 21)
    y = 2 * x + rng.normal(0, 4, x.size)
    fig, ax = plt.subplots(figsize=(5, 3.5), layout=layout)
    sns.regplot(x=x, y=y, ax=ax)
    ax.set_xlabel("Dose")
    return fig, ax


def _inside_the_canvas(fig, ax) -> bool:
    """Whether the axis labels lie on the canvas, which the SVG is."""
    # A label is placed beside its tick labels only when it is drawn.
    fig.draw_without_rendering()
    renderer = fig.canvas.get_renderer()
    width, height = fig.canvas.get_width_height()
    boxes = [
        ax.xaxis.label.get_window_extent(renderer),
        ax.yaxis.label.get_window_extent(renderer),
    ]
    return all(
        box.x0 >= 0 and box.y0 >= 0 and box.x1 <= width and box.y1 <= height
        for box in boxes
    )


def test_in_a_page_a_figure_without_a_layout_engine_is_left_where_it_is():
    fig, ax = _labelled()
    params = vars(fig.subplotpars).copy()
    position = ax.get_position().bounds

    with settling(keep_layout=True):
        settle_layout(fig)

    assert vars(fig.subplotpars) == params
    assert ax.get_position().bounds == position
    assert fig.get_layout_engine() is None


@pytest.mark.parametrize("scope", ["none", "elsewhere"])
def test_elsewhere_a_figure_without_a_layout_engine_is_laid_out_to_fit_its_labels(
    scope,
):
    """As it always was: a 3x3 inch figure's labels lie past its canvas otherwise."""
    fig, ax = _labelled()
    fig.set_size_inches(3, 3)
    reference, reference_ax = _labelled()
    reference.set_size_inches(3, 3)
    assert not _inside_the_canvas(reference, reference_ax)
    reference.tight_layout()

    if scope == "none":
        settle_layout(fig)
    else:
        with settling(keep_layout=False):
            settle_layout(fig)

    assert ax.get_position().bounds == reference_ax.get_position().bounds
    assert _inside_the_canvas(fig, ax)


@pytest.mark.parametrize("keep_layout", [True, False])
@pytest.mark.parametrize("layout", ["constrained", "compressed", "tight"])
def test_a_figures_own_engine_is_kept_and_its_layout_applied(
    recwarn, layout, keep_layout
):
    fig, ax = _labelled(layout)
    engine = type(fig.get_layout_engine())
    reference, reference_ax = _labelled(layout)
    reference.savefig(io.StringIO(), format="svg")

    with settling(keep_layout=keep_layout):
        settle_layout(fig)

    assert type(fig.get_layout_engine()) is engine
    assert ax.get_position().bounds == pytest.approx(
        reference_ax.get_position().bounds, abs=0.005
    )
    assert not [w for w in recwarn if "layout has changed" in str(w.message)]


def test_an_axes_with_a_fixed_aspect_is_placed_as_the_svg_draws_it():
    """``set_aspect`` moves the axes only when it is drawn; settling draws it."""
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.plot([0, 1], [0, 1])
    ax.set_aspect("equal")

    with settling(keep_layout=True):
        settle_layout(fig)
    x, y = data_to_svg_coords(ax, np.array([0.0, 1.0]), np.array([0.0, 1.0]))
    fig.savefig(io.StringIO(), format="svg")
    after = data_to_svg_coords(ax, np.array([0.0, 1.0]), np.array([0.0, 1.0]))

    np.testing.assert_array_equal(x, after[0])
    np.testing.assert_array_equal(y, after[1])


@pytest.mark.parametrize("keep_layout", [True, False])
def test_one_pass_without_an_engine(mocker, keep_layout):
    """A draw in a page, a tight layout elsewhere; never an SVG."""
    drawn = mocker.spy(Figure, "draw_without_rendering")
    tightened = mocker.spy(Figure, "tight_layout")
    saved = mocker.spy(Figure, "savefig")
    fig, _ = _labelled()

    with settling(keep_layout=keep_layout):
        settle_layout(fig)

    passes = (drawn.call_count, tightened.call_count, saved.call_count)
    assert passes == ((1, 0, 0) if keep_layout else (0, 1, 0))


@pytest.mark.parametrize("keep_layout", [True, False])
@pytest.mark.parametrize("layout", [None, "constrained"])
def test_a_render_settles_a_figure_once_however_many_layers_ask(
    mocker, layout, keep_layout
):
    """The figure does not change between one layer's extraction and the next."""
    drawn = mocker.spy(Figure, "draw_without_rendering")
    tightened = mocker.spy(Figure, "tight_layout")
    saved = mocker.spy(Figure, "savefig")
    fig, _ = _labelled(layout)
    other, _ = _labelled(layout)

    with settling(keep_layout=keep_layout):
        settle_layout(fig)
        passes = drawn.call_count + tightened.call_count + saved.call_count
        for _ in range(5):
            settle_layout(fig)
        assert drawn.call_count + tightened.call_count + saved.call_count == passes
        # Another figure is settled on its own.
        settle_layout(other)
        assert drawn.call_count + tightened.call_count + saved.call_count > passes

    # And a later render settles the figure again.
    passes = drawn.call_count + tightened.call_count + saved.call_count
    with settling(keep_layout=keep_layout):
        settle_layout(fig)
    assert drawn.call_count + tightened.call_count + saved.call_count > passes


def test_an_engine_is_run_through_the_svg_until_it_stops_moving_the_axes(mocker):
    """The SVG's renderer measures the text; one pass more says it has settled."""
    drawn = mocker.spy(Figure, "draw_without_rendering")
    saved = mocker.spy(Figure, "savefig")
    fig, _ = _labelled("constrained")

    settle_layout(fig)
    assert (drawn.call_count, saved.call_count) == (0, 2)
    assert {call.kwargs["format"] for call in saved.call_args_list} == {"svg"}

    saved.reset_mock()
    settle_layout(fig)
    assert saved.call_count == 1, "a settled figure took more than one pass"


def test_a_tight_layout_that_keeps_moving_is_saved_at_most_four_times(mocker):
    saved = mocker.spy(Figure, "savefig")
    fig, _ = _labelled("tight")
    # The axes a little further right each time they are asked for.
    steps = itertools.count()
    mocker.patch.object(
        type(fig.axes[0]),
        "get_position",
        side_effect=lambda *a, **k: Bbox.from_bounds(
            0.1 + next(steps) * 0.01, 0.1, 0.5, 0.5
        ),
    )

    settle_layout(fig)

    assert saved.call_count == 4


@pytest.mark.parametrize("size", [(4, 3), (3, 3)])
@pytest.mark.parametrize("hinting", ["no_hinting", "force_autohint"])
@pytest.mark.parametrize("layout", ["constrained", "tight"])
def test_an_engine_leaves_the_axes_where_the_svg_draws_them(layout, hinting, size):
    """Within a hundredth of a point, hinted text or not, a small figure or not.

    A 3x3 inch figure's tight layout moves its axes 0.8 of a point on its
    second pass; a single pass would have left them there.
    """
    with plt.rc_context({"text.hinting": hinting}):
        fig, ax = _labelled(layout)
        fig.set_size_inches(*size)
        settle_layout(fig)
        settled = np.array(ax.get_position().bounds)
        fig.savefig(io.StringIO(), format="svg")
        saved = np.array(ax.get_position().bounds)

    points = np.array(size * 2) * 72
    assert np.all(np.abs(saved - settled) * points < 0.01)


@pytest.mark.parametrize("keep_layout", [True, False])
@pytest.mark.parametrize("layout", [None, "tight"])
def test_a_figure_that_cannot_be_drawn_is_still_read(mocker, layout, keep_layout):
    fig, _ = _labelled(layout)
    mocker.patch.object(Figure, "draw_without_rendering", side_effect=ValueError)
    mocker.patch.object(Figure, "tight_layout", side_effect=ValueError)
    mocker.patch.object(Figure, "savefig", side_effect=ValueError)

    with settling(keep_layout=keep_layout):
        settle_layout(fig)


@pytest.fixture(params=[False, True], ids=["elsewhere", "in-a-page"])
def in_page(request, mocker):
    """A render outside a Quarto page, and one writing the chart into it."""
    mocker.patch("maidr.core.maidr.inline_applies", return_value=request.param)
    return request.param


def test_a_regressions_layout_and_its_points_land_on_the_line(in_page):
    """Kept in a page; laid out to fit its labels elsewhere, as it always was."""
    fig, ax = _regression()
    fig.set_size_inches(3, 3)
    params = vars(fig.subplotpars).copy()

    maidr.render(fig)

    assert (vars(fig.subplotpars) == params) is in_page
    if not in_page:
        assert _inside_the_canvas(fig, ax)
    layer = next(
        plot
        for plot in FigureManager.get_maidr(fig).plots
        if plot.type is PlotType.SMOOTH
    )
    points = layer.schema["data"][0]
    xs = np.array([p["x"] for p in points])
    ys = np.array([p["y"] for p in points])
    now_x, now_y = data_to_svg_coords(ax, xs, ys)
    np.testing.assert_array_equal([p["svg_x"] for p in points], now_x)
    np.testing.assert_array_equal([p["svg_y"] for p in points], now_y)


@pytest.mark.parametrize("make", ["violin", "regression"])
def test_save_html_shows_the_labels_of_a_small_figure(tmp_path, make):
    """The document's SVG is the canvas: the labels are laid out onto it."""
    if make == "violin":
        fig, ax = plt.subplots(figsize=(3, 3))
        rng = np.random.default_rng(1)
        sns.violinplot(x=[c for c in "ABC" for _ in range(30)], y=rng.normal(size=90))
        ax.set_xlabel("Treatment group")
        ax.set_ylabel("Response")
    else:
        fig, ax = _regression()
        fig.set_size_inches(3, 3)
        ax.set_ylabel("Response")
    path = tmp_path / "chart.html"

    maidr.save_html(fig, str(path), use_cdn=False)

    html = path.read_text(encoding="utf-8")
    svg = html[html.index("<svg") : html.index(">", html.index("<svg"))]
    assert 'viewBox="0 0 216 216"' in svg
    assert _inside_the_canvas(fig, ax)
