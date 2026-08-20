"""A figure's grid survives the iframe a hosted render wraps it in.

Under Shiny -- and anywhere else `Environment` reports a live host -- the
chart is nested inside an iframe's `srcdoc`, which escapes the schema a
second time on top of the escaping lxml already applied to the `<svg>`.
That is the form a Shiny or Flask reader actually receives, and until this
file nothing asserted the grid still reads correctly in it: every existing
grid test builds the schema through `_flatten_maidr` directly, where no
wrapping happens.

The three entry points are checked together, but not because they branch:
the wrapping decision is environmental rather than per-door, so
`maidr.render`, `render_maidr` and `maidr_html` all wrap or all do not.
Measured -- with a session active the three emit byte-identical markup.
What holds them together is therefore weaker than "these paths differ" and
still worth pinning: **no door may grow post-processing of its own.** #443
is why. `plt.show()` degraded gracefully for an unregistered figure while
`render`/`show`/`save_html` raised, because a behaviour had been wired into
one door and not the others, and nothing failed until a user went through
the wrong one.

The figures are the shapes whose grid coordinates #512, #517 and #519
corrected -- an authored gap, a proportions gridspec, and panels
re-parented by their colorbars.
"""

from __future__ import annotations

import html as html_module
import json
import re

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: E402
from maidr.util.environment import Environment  # noqa: E402

# Guarded here as well as in `conftest.py`, matching `test_shiny.py`. The
# directory-level skip already covers a missing shiny, but only because
# pytest skips a whole subtree when a `conftest` raises during collection.
# Relying on that leaves this file uncollectable on its own.
pytest.importorskip("shiny")

from maidr.widget.shiny import render_maidr  # noqa: E402
from maidr.widget.streamlit import maidr_html  # noqa: E402

#: The chart document a hosted render nests inside an iframe.
_SRCDOC = re.compile(r'srcdoc="([^"]*)"')

#: The schema as it sits on the ``<svg>`` element of that document.
_SCHEMA_IN_SVG = re.compile(r'maidr="([^"]*)"')


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _grid_of(rendered: object) -> list[list[int]]:
    """The layer count of every cell, read back out of emitted markup.

    Read from the markup rather than from the `Maidr` instance on purpose:
    the instance is what every door shares, so asking it would skip the
    wrapping and escaping this file exists to cover.
    """
    markup = str(rendered)

    frame = _SRCDOC.search(markup)
    if frame is not None:
        markup = html_module.unescape(frame.group(1))

    match = _SCHEMA_IN_SVG.search(markup)
    assert match, "no MAIDR schema in the emitted markup"

    return [
        [len(cell.get("layers", [])) for cell in row]
        for row in json.loads(html_module.unescape(match.group(1)))["subplots"]
    ]


def _gapped():
    """A grid position the author left empty between two panels."""
    fig, axs = plt.subplots(1, 3)
    axs[0].bar(["p", "q"], [1, 2])
    axs[2].bar(["p", "q"], [3, 4])
    return fig


def _jointplot():
    """A gridspec used for proportions rather than positions."""
    df = pd.DataFrame({"x": np.arange(30) % 7, "y": (np.arange(30) * 3) % 11})
    return sns.jointplot(data=df, x="x", y="y").figure


def _two_heatmaps():
    """Two panels each re-parented into a sub-gridspec by its colorbar."""
    fig, axs = plt.subplots(1, 2)
    for ax in axs:
        sns.heatmap(np.arange(16).reshape(4, 4), ax=ax)
    return fig


FIGURES = [
    (_gapped, [[1, 0, 1]]),
    (_jointplot, [[1, 0], [1, 1]]),
    (_two_heatmaps, [[1, 1]]),
]
IDS = ["gapped", "jointplot", "two_heatmaps"]


@pytest.mark.parametrize("build,expected", FIGURES, ids=IDS)
def test_the_grid_survives_being_wrapped_in_an_iframe(build, expected, fake_session):
    """The form a Shiny reader receives, schema escaped twice."""
    rendered = str(render_maidr(lambda: None)._render_off_loop(build()))

    assert "srcdoc=" in rendered, (
        "this figure was not wrapped, so the escaping under test never "
        "happened and the assertion below would pass for the wrong reason"
    )
    assert Environment.is_shiny()
    assert _grid_of(rendered) == expected


@pytest.mark.parametrize("build,expected", FIGURES, ids=IDS)
def test_the_grid_is_the_same_unwrapped(build, expected):
    """No session, so nothing wraps -- the grid must not depend on that."""
    rendered = str(render_maidr(lambda: None)._render_off_loop(build()))

    assert "srcdoc=" not in rendered
    assert _grid_of(rendered) == expected


@pytest.mark.parametrize("build,expected", FIGURES, ids=IDS)
def test_no_door_post_processes_the_schema(build, expected, fake_session):
    """Every entry point emits the grid it was given, unaltered.

    Weaker than it looks, and deliberately so: these doors do not branch on
    which one was called, so this cannot catch a divergence that exists
    today. It catches one being *introduced* -- a door that starts caching,
    trimming or rebuilding the schema on its way out.
    """
    figure = build()

    doors = {
        "maidr.render": _grid_of(maidr.render(figure)),
        "shiny.render_maidr": _grid_of(
            render_maidr(lambda: None)._render_off_loop(figure)
        ),
        "streamlit.maidr_html": _grid_of(maidr_html(figure)),
    }

    assert list(doors.values()) == [expected] * 3, (
        f"a door altered the grid on its way out: {doors}. A reader is not "
        f"told which entry point their host used."
    )


def test_the_two_doors_exclude_each_other_on_one_figure(monkeypatch):
    """One lock registry, not one per integration -- asserted, not inferred.

    The Shiny renderer and ``maidr_html`` both take the per-figure lock in
    ``maidr.util.figure_lock``. That they take the *same* lock follows from
    both importing one module-level registry, which is a guarantee from
    Python's import semantics rather than from any test -- so a later
    change that gave either door a registry of its own would keep every
    per-door test green while reopening exactly the case the shared
    registry exists to prevent: a Shiny session and a Streamlit session
    rendering one shared figure at the same moment, racing on ``fig.dpi``
    (#454, #531).

    Asserts exclusion rather than output equality: the two doors wrap the
    chart differently, so their markup is not comparable, and what matters
    here is that the two renders do not overlap in time.

    ``maidr.render`` is stubbed to a sleeping recorder, so this measures
    the lock rather than a real render -- the consequence of *not*
    excluding is covered per door by the two
    ``test_concurrent_renders_of_one_figure_agree`` tests.
    """
    import threading
    import time

    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])

    in_flight = 0
    overlapped = False
    guard = threading.Lock()

    class _Rendered:
        """The little of a rendered chart that ``maidr_html`` goes on to use."""

        @staticmethod
        def get_html_string() -> str:
            return '<script src="https://cdn.jsdelivr.net/npm/maidr@4/dist/maidr.js"></script>'

        def __str__(self) -> str:
            return self.get_html_string()

    def sleeping_render(plot, **kwargs):
        nonlocal in_flight, overlapped
        with guard:
            in_flight += 1
            if in_flight > 1:
                overlapped = True
        time.sleep(0.2)
        with guard:
            in_flight -= 1
        return _Rendered()

    start = threading.Barrier(2)
    failures: list[Exception] = []

    def through_shiny():
        try:
            start.wait(timeout=30)
            render_maidr(lambda: ax, use_cdn=True)._render_off_loop(ax)
        except Exception as error:  # noqa: BLE001 - re-raised after the join
            failures.append(error)

    def through_streamlit():
        try:
            start.wait(timeout=30)
            maidr_html(ax, use_cdn=True)
        except Exception as error:  # noqa: BLE001 - re-raised after the join
            failures.append(error)

    monkeypatch.setattr(maidr, "render", sleeping_render)
    try:
        threads = [
            threading.Thread(target=through_shiny, daemon=True),
            threading.Thread(target=through_streamlit, daemon=True),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
            assert not thread.is_alive(), "a render deadlocked on the lock"
    finally:
        plt.close(fig)

    assert not failures, failures
    assert not overlapped, (
        "a Shiny render and a Streamlit render of one figure ran at once; "
        "the two doors are not sharing a lock registry"
    )
