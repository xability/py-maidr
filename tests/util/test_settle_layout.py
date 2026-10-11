"""``settle_layout`` places the axes as the SVG will, imposing no layout of its own.

The violin and regression layers convert their points to SVG coordinates,
which read the axes position, so they settle the figure's layout first. That
used to run ``tight_layout``: a figure with no layout engine was re-laid-out,
so the chart was no longer the figure a reader saw drawn without maidr (a
Quarto page showed the two side by side at different shapes), and a
constrained layout was replaced by a tight one, with a warning. Settling now
draws the figure without rendering it, which runs only the figure's own
engine. The violin layer's pass count and coordinates are pinned in
``tests/core/plot/test_violin_kde_layout.py``.
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
from maidr.util.svg_utils import data_to_svg_coords, settle_layout  # noqa: E402

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


def test_a_figure_without_a_layout_engine_is_left_where_it_is():
    fig, ax = _labelled()
    params = vars(fig.subplotpars).copy()
    position = ax.get_position().bounds

    settle_layout(fig)

    assert vars(fig.subplotpars) == params
    assert ax.get_position().bounds == position
    assert fig.get_layout_engine() is None


@pytest.mark.parametrize("layout", ["constrained", "compressed", "tight"])
def test_a_figures_own_engine_is_kept_and_its_layout_applied(recwarn, layout):
    fig, ax = _labelled(layout)
    engine = type(fig.get_layout_engine())
    reference, reference_ax = _labelled(layout)
    reference.savefig(io.StringIO(), format="svg")

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

    settle_layout(fig)
    x, y = data_to_svg_coords(ax, np.array([0.0, 1.0]), np.array([0.0, 1.0]))
    fig.savefig(io.StringIO(), format="svg")
    after = data_to_svg_coords(ax, np.array([0.0, 1.0]), np.array([0.0, 1.0]))

    np.testing.assert_array_equal(x, after[0])
    np.testing.assert_array_equal(y, after[1])


def test_one_draw_without_an_engine(mocker):
    drawn = mocker.spy(Figure, "draw_without_rendering")
    saved = mocker.spy(Figure, "savefig")
    fig, _ = _labelled()

    settle_layout(fig)

    assert (drawn.call_count, saved.call_count) == (1, 0)


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


@pytest.mark.parametrize("layout", [None, "tight"])
def test_a_figure_that_cannot_be_drawn_is_still_read(mocker, layout):
    fig, _ = _labelled(layout)
    mocker.patch.object(Figure, "draw_without_rendering", side_effect=ValueError)
    mocker.patch.object(Figure, "savefig", side_effect=ValueError)

    settle_layout(fig)


def test_a_regression_keeps_the_users_layout_and_its_points_land_on_the_line():
    fig, ax = _regression()
    params = vars(fig.subplotpars).copy()

    maidr.render(fig)

    assert vars(fig.subplotpars) == params
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
