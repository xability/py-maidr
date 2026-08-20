"""A figure drawn into *while* it is rendered says so, instead of lying.

The schema is read from the artists and the SVG is written from them
afterwards, so anything that draws into the figure between those two
points lands in one and not the other: a chart that shows something it
never announces, or announces something it does not show. The per-figure
lock stops another *render* from doing that; it cannot stop the
application itself, on a figure it still holds (#530).

The failure is the kind this project treats as worst -- a sighted user
sees the change, a screen-reader user is never told it exists, and every
check that reads the payload passes.
"""

from __future__ import annotations

import warnings

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

import maidr  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402

_MESSAGE = "drawn into while it was being rendered"


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _render_catching_warnings(axes):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        maidr.render(axes, use_cdn=True)
    return [w for w in caught if _MESSAGE in str(w.message)]


def test_a_figure_drawn_into_mid_render_warns(monkeypatch):
    """Driven deterministically, not by racing two threads.

    A thread race would make this a test of the scheduler: it would pass
    on a machine where the mutation happened to land inside the window and
    silently stop testing anything on one where it did not. Mutating from
    inside ``_get_svg`` puts the change exactly where a concurrent
    application would have to put it to go unnoticed -- after the schema
    is read, before the SVG is written -- every time.
    """
    from maidr.core.maidr import Maidr

    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    original = Maidr._get_svg

    def draw_into_the_figure_first(self, *args, **kwargs):
        self._fig.axes[0].bar(["c"], [3])
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Maidr, "_get_svg", draw_into_the_figure_first)

    assert _render_catching_warnings(ax), "a mid-render mutation went unreported"


def test_the_warning_says_what_to_do_about_it():
    """A warning a reader cannot act on is noise.

    Pinned because the two remedies are not obvious from the symptom: the
    chart looks fine, and nothing raised.
    """
    from maidr.core.maidr import Maidr

    fig, ax = plt.subplots()
    ax.bar(["a"], [1])
    original = Maidr._get_svg

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Maidr._get_svg = lambda self, *a, **k: (  # noqa: E731
            self._fig.axes[0].set_title("moved"),
            original(self, *a, **k),
        )[1]
        try:
            maidr.render(ax, use_cdn=True)
        finally:
            Maidr._get_svg = original

    message = str(next(w.message for w in caught if _MESSAGE in str(w.message)))
    assert "Finish plotting before rendering" in message
    assert "no other thread is using" in message


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(lambda ax: ax.bar(["a", "b"], [1, 2]), id="bar"),
        pytest.param(lambda ax: ax.plot([1, 2, 3], [3, 2, 1]), id="line"),
        pytest.param(lambda ax: ax.scatter([1, 2], [2, 1]), id="scatter"),
        pytest.param(lambda ax: ax.hist([1, 2, 2, 3]), id="hist"),
        pytest.param(lambda ax: ax.boxplot([[1, 2, 3], [2, 3, 4]]), id="boxplot"),
        pytest.param(
            lambda ax: ax.pcolormesh(np.arange(6).reshape(2, 3)), id="heatmap"
        ),
    ],
)
def test_an_undisturbed_render_is_silent(build):
    """The direction that decides whether this can ship at all.

    A detector that reports the render's own work would fire on every
    chart, and a warning that always fires is one nobody reads. The census
    counts artists and labels, and the render adds neither -- tagging for
    highlight sets attributes on artists that already exist.

    Parametrised across the shapes whose renders do the most to the
    figure. Verified over the whole suite as well: 2,456 tests, zero
    occurrences of this warning.
    """
    fig, ax = plt.subplots()
    build(ax)

    assert not _render_catching_warnings(ax), "an ordinary render warned"


def test_a_colorbar_does_not_look_like_interference():
    """The one shape that re-parents axes during its own construction.

    ``fig.colorbar`` adds an axes, which is exactly what the census
    counts. It happens before the render rather than during it, and this
    pins that distinction -- the census is taken inside the render, so a
    figure that was *built* with a colorbar is not interference (#519).
    """
    fig, ax = plt.subplots()
    mesh = ax.pcolormesh(np.arange(6).reshape(2, 3))
    fig.colorbar(mesh, ax=ax)

    assert not _render_catching_warnings(ax), "a colorbar was read as interference"


def test_the_census_is_not_confused_by_a_second_render_of_the_same_figure():
    """Rendering twice must not report the first render as interference.

    The census is taken fresh inside each render rather than stored on the
    instance, so nothing carries over. Worth pinning because storing it
    would be the obvious optimisation and would break exactly this.
    """
    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    FigureManager.get_maidr(fig)

    assert not _render_catching_warnings(ax)
    assert not _render_catching_warnings(ax), "the second render warned"
