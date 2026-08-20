"""Every entry point describes the same figure the same way.

`maidr.render`, Shiny's `render_maidr` and Streamlit's `maidr_html` are
three doors onto one figure, and a reader is not told which one their host
application used. So a grid that reads correctly through one and not
another is a defect they cannot diagnose, only experience.

The doors funnel into `Maidr._flatten_maidr` today, so this holds by
construction rather than by anyone maintaining it -- which is the reason to
pin it. #443 is the precedent: `plt.show()` degraded gracefully for an
unregistered figure while `render`/`show`/`save_html` raised, because the
graceful path had been wired into one door and not the others. Nothing
failed until a user went through the wrong one.

The three figures are the shapes whose grid coordinates were recently
corrected (#512, #517, #519). They are the ones where a divergence would
be most likely and least visible.
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
from maidr.widget.shiny import render_maidr  # noqa: E402
from maidr.widget.streamlit import maidr_html  # noqa: E402

_SCHEMA_IN_SVG = re.compile(r'maidr="([^"]*)"')


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _grid_of(rendered: object) -> list[list[int]]:
    """The layer count of every cell, read back out of emitted markup.

    Read from the markup rather than from the `Maidr` instance on purpose:
    the instance is what all three doors share, so asking it could not tell
    them apart.
    """
    match = _SCHEMA_IN_SVG.search(str(rendered))
    assert match, "no MAIDR schema in the emitted markup"
    schema = json.loads(html_module.unescape(match.group(1)))
    return [[len(cell.get("layers", [])) for cell in row] for row in schema["subplots"]]


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


@pytest.mark.parametrize(
    "build", [_gapped, _jointplot, _two_heatmaps], ids=lambda f: f.__name__
)
def test_every_door_reports_the_same_grid(build):
    """Notebook, Shiny and Streamlit agree on the shape of the figure."""
    figure = build()

    doors = {
        "maidr.render": _grid_of(maidr.render(figure)),
        "shiny.render_maidr": _grid_of(render_maidr(lambda: None)._render_off_loop(figure)),
        "streamlit.maidr_html": _grid_of(maidr_html(figure)),
    }

    distinct = {repr(grid) for grid in doors.values()}
    assert len(distinct) == 1, (
        f"the doors disagree about this figure: {doors}. A reader is not told "
        f"which one their host used, so a grid that is right through one and "
        f"wrong through another is a defect they cannot diagnose."
    )


@pytest.mark.parametrize(
    "build,expected",
    [
        (_gapped, [[1, 0, 1]]),
        (_jointplot, [[1, 0], [1, 1]]),
        (_two_heatmaps, [[1, 1]]),
    ],
    ids=["gapped", "jointplot", "two_heatmaps"],
)
def test_the_agreed_grid_is_the_correct_one(build, expected):
    """Agreement is necessary but not sufficient -- they could agree and be wrong.

    Pinned through Shiny specifically, since that is the door #454 and #452
    reworked and therefore the one most likely to grow its own path.
    """
    rendered = render_maidr(lambda: None)._render_off_loop(build())

    assert _grid_of(rendered) == expected
