"""Two ``ax.bar()`` calls on one axes produced no HTML at all.

``BarPlot`` swept every ``BarContainer`` on its axes rather than reading the
bars its own call drew, so two overlaid calls each found six patches against
three tick labels, failed the count check, and raised ``ExtractionError`` --
which is fatal to the whole figure rather than to its own layer (#380).

#377 fixed the neighbouring case, where one of the calls passes ``bottom`` and
so registers a segmented layer for the collapse to keep. Here neither does,
both register as plain ``BAR``, and nothing supersedes anything.

The reading two overlapping bar layers *should* get is a real question rather
than an oversight, which is why it was filed separately. Two series drawn over
one another with alpha are two series, so two layers -- each describing its
own bars -- is the answer that loses no data and matches what is drawn.

The sweep stays for seaborn, and that is not a grudging fallback: seaborn
draws one bar layer as several containers, one per hue group, and registers it
from a seaborn-level patch where no single container is the answer. What the
sweep cannot do is tell one ``ax.bar()`` call's bars from another's, and only
the matplotlib entry point knows that.
"""

from __future__ import annotations

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402

CATEGORIES = ["a", "b", "c"]
SERIES_0 = np.array([10.0, 20.0, 30.0])
SERIES_1 = np.array([30.0, 20.0, 10.0])


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _layers(fig) -> list[dict]:
    """Every emitted layer of the first subplot cell."""
    grid = FigureManager.get_maidr(fig)._flatten_maidr()["subplots"]
    return grid[0][0].get("layers", [])


def test_two_overlaid_bar_calls_each_read_their_own_bars() -> None:
    """The reproduction, asserted by data rather than by layer count.

    Two layers of the right type would also be the answer if both described
    the same six patches, so the magnitudes are what is checked: the first
    layer is the first call's bars and the second is the second's.

    Rendered as well as counted, because the old failure happened during
    extraction -- there was no schema to inspect.
    """
    fig, ax = plt.subplots()
    ax.bar(CATEGORIES, SERIES_0, alpha=0.6)
    ax.bar(CATEGORIES, SERIES_1, alpha=0.6)

    layers = _layers(fig)

    assert [layer["type"].value for layer in layers] == ["bar", "bar"]
    assert [point["y"] for point in layers[0]["data"]] == list(SERIES_0)
    assert [point["y"] for point in layers[1]["data"]] == list(SERIES_1)
    assert maidr.render(fig) is not None


def test_one_bar_call_is_unchanged() -> None:
    """The control, and the overwhelmingly common case.

    A single call has exactly one container either way, so narrowing must
    cost it nothing.
    """
    fig, ax = plt.subplots()
    ax.bar(CATEGORIES, SERIES_0)

    layers = _layers(fig)

    assert [layer["type"].value for layer in layers] == ["bar"]
    assert [point["y"] for point in layers[0]["data"]] == list(SERIES_0)


def test_a_hued_seaborn_bar_still_reads_every_group() -> None:
    """seaborn is why the sweep exists, and it has to keep working.

    A hue splits one seaborn layer across several containers, one per group,
    and it is registered from the seaborn-level patch -- where no single
    container is the answer and there is no ``_maidr_bars`` to narrow to. If
    narrowing ever leaked into that path, this layer would describe one hue
    group and quietly drop the rest.
    """
    frame = pd.DataFrame(
        {
            "group": ["a", "a", "b", "b", "c", "c"],
            "half": ["x", "y"] * 3,
            "value": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        }
    )
    fig, ax = plt.subplots()
    sns.barplot(data=frame, x="group", y="value", hue="half", ax=ax)

    layers = _layers(fig)

    assert len(layers) == 1
    # Six bars: three groups times two hue levels, not the three of one group.
    assert sum(len(series) for series in layers[0]["data"]) == 6


def test_a_stacked_chart_is_unchanged() -> None:
    """The #377 regression guard.

    A stacked chart is still one layer describing every bar on the axes:
    ``GroupedBarPlot`` sweeps deliberately, and only ``BarPlot`` narrows.
    Narrowing the wrong one would announce a stacked chart as its first
    series alone.
    """
    fig, ax = plt.subplots()
    ax.bar(CATEGORIES, SERIES_0, label="s0")
    ax.bar(CATEGORIES, SERIES_1, bottom=SERIES_0, label="s1")

    layers = _layers(fig)

    assert [layer["type"].value for layer in layers] == ["stacked_bar"]
    assert len(layers[0]["data"]) == 2, "both series, not just the first"
