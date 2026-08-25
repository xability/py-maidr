"""
A box or boxen chart lost its grouping when the legend sat on the figure
(#674).

Three readers still asked ``ax.get_legend()`` directly after #672 and #617
had moved everything else onto
:func:`maidr.util.legend_names.legend_of`, which finds the legend wherever
it was put. Measured on ``seaborn 0.13.2``, the same chart drawn twice --
once with the legend seaborn leaves on the axes, once with the *drawn*
handles moved onto the figure, which is what a grid's ``add_legend()``
does:

===========  ==============  =====================  ==========================
chart        legend          ``axes.z``             per-box ``z``
===========  ==============  =====================  ==========================
boxplot      on the axes     ``{"label": "g"}``     ``"a, p"``  ``"b, p"`` ...
boxplot      on the figure   **absent**             ``"a, p"``  ``"b, p"`` ...
boxenplot    on the axes     ``{"label": "g"}``     ``"a, p"``  ``"a, q"`` ...
boxenplot    on the figure   **absent**             ``"a"``  ``"a"``  ...
===========  ==============  =====================  ==========================

So the two halves fail differently, and the boxen half is the worse one.

``BoxPlot`` names each box by matching its drawn colour against a swatch,
through :func:`~maidr.util.legend_names.names_for`, which already reads the
chosen legend -- so only the *variable*'s name was dropped. A reader was
told which side of a grouping each box was on and never told what the
grouping was.

``BoxenPlot`` cannot match on colour: a ladder is many boxes shading from
dark to light, so its level comes from its rank in the dodge lattice looked
up in the legend's own list of names. With no axes legend that list was
empty, and **every ladder in a category was announced identically** -- two
ladders both called ``"a"``, which is the shape ``xability/maidr#828``
exists to prevent.

Both are one lookup. What is asserted here is that the label and the levels
now come from the *same* legend: reading them off two different ones is
what the defect was.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import pytest
import seaborn as sns

import maidr
from maidr.core.figure_manager import FigureManager


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    """Two categories split two ways, with enough spread to draw a box."""
    return pd.DataFrame(
        {
            "cat": ["a", "a", "a", "a", "b", "b", "b", "b"] * 3,
            "g": ["p", "q"] * 12,
            "val": [
                1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0,
                2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0,
                3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0,
            ],
        }
    )


def _moved_to_the_figure(draw, title: str = "g") -> plt.Figure:
    """One chart whose legend was moved off the panel and onto the figure.

    The swatches are the *drawn* ones. That is what makes this the real case
    rather than a stand-in: a grid's ``add_legend()`` gathers the panels' own
    handles, so the colour match that names a box still holds and only the
    legend's owner has changed. Handing it fresh patches instead would break
    the match for a reason that has nothing to do with where the legend is --
    seaborn desaturates a box's face, so a stand-in swatch in the palette
    colour names nothing.
    """
    figure, ax = plt.subplots()
    draw(ax)
    own = ax.get_legend()
    handles = own.legend_handles
    labels = [text.get_text() for text in own.get_texts()]
    own.remove()
    figure.legend(handles, labels, title=title)
    return figure


def _schema(figure: plt.Figure) -> dict:
    """The one layer's schema, rendered the way a caller gets it."""
    maidr.render(figure)._repr_html_()
    return FigureManager.get_maidr(figure).plots[0].schema


def _boxes(figure: plt.Figure) -> list[str]:
    """Each drawn box's own name, in drawing order."""
    return [str(entry["z"]) for entry in _schema(figure)["data"]]


def _box(ax, **kwargs) -> None:
    sns.boxplot(data=_frame(), x="cat", y="val", hue="g", ax=ax, **kwargs)


def _boxen(ax, **kwargs) -> None:
    sns.boxenplot(data=_frame(), x="cat", y="val", hue="g", ax=ax, **kwargs)


def test_a_box_chart_names_its_variable_from_a_legend_moved_to_the_figure():
    # The boxes were already named -- `names_for` reads the chosen legend --
    # so this is the half that was only ever a missing label.
    schema = _schema(_moved_to_the_figure(_box))

    assert schema["axes"]["z"] == {"label": "g"}


def test_a_box_chart_still_names_each_box_from_that_same_legend():
    # Asserted beside the label rather than assumed: the point of the fix is
    # that both now come from one legend, and a change that moved only the
    # title would pass the test above while leaving them on two.
    assert _boxes(_moved_to_the_figure(_box)) == ["a, p", "b, p", "a, q", "b, q"]


def test_a_boxen_chart_names_its_variable_from_a_legend_moved_to_the_figure():
    schema = _schema(_moved_to_the_figure(_boxen))

    assert schema["axes"]["z"] == {"label": "g"}


def test_a_boxen_ladder_keeps_its_level_when_the_legend_is_the_figures():
    # The worse half. A ladder's level is its rank in the dodge lattice
    # looked up in the legend's list of names; with no axes legend that list
    # was empty, so both ladders in a category came out as the category
    # alone -- two identical announcements for two different distributions.
    assert _boxes(_moved_to_the_figure(_boxen)) == ["a, p", "a, q", "b, p", "b, q"]


@pytest.mark.parametrize("order", [["p", "q"], ["q", "p"]])
def test_a_reordered_hue_keeps_each_boxen_ladder_with_its_level(order):
    # The coupling `_hue_levels` documents -- seaborn lays the dodge out in
    # legend order -- has to survive the legend moving. `hue_order` moves
    # both together, and nothing would raise if they ever came apart: every
    # level would simply be announced as its neighbour.
    figure = _moved_to_the_figure(lambda ax: _boxen(ax, hue_order=order))

    assert _boxes(figure) == [
        f"{category}, {level}" for category in ("a", "b") for level in order
    ]


@pytest.mark.parametrize("draw", [_box, _boxen], ids=["box", "boxen"])
def test_the_axes_own_legend_still_wins_over_the_figures(draw):
    # `legend_of`'s rule, asserted as reached rather than reimplemented. A
    # panel that kept its own legend is named by it and never consults the
    # figure's, which is the mitigation for one figure legend being read as
    # naming every axes.
    figure, ax = plt.subplots()
    draw(ax)
    ax.get_legend().set_title("on the axes")
    figure.legend(
        ax.get_legend().legend_handles, ["p", "q"], title="on the figure"
    )

    assert _schema(figure)["axes"]["z"] == {"label": "on the axes"}


@pytest.mark.parametrize(
    ("draw", "categories"),
    # The two classes walk their boxes in different orders -- `BoxPlot` reads
    # matplotlib's `bxp` output, level by level, and `BoxenPlot` reads the
    # dodge lattice, category by category -- so the expected order is named
    # per class rather than accepted either way.
    [(_box, ["a", "b", "a", "b"]), (_boxen, ["a", "a", "b", "b"])],
    ids=["box", "boxen"],
)
def test_a_chart_with_no_legend_names_nothing_rather_than_something(draw, categories):
    # Drawn `legend=False` and left that way. There is nothing to read, and
    # the categories still come back -- answering one of the two questions is
    # an improvement on answering neither.
    figure, ax = plt.subplots()
    draw(ax, legend=False)
    schema = _schema(figure)

    assert "z" not in schema["axes"]
    assert [str(entry["z"]) for entry in schema["data"]] == categories


@pytest.mark.parametrize("draw", [_box, _boxen], ids=["box", "boxen"])
def test_two_figure_legends_name_nothing_rather_than_one_of_them(draw):
    # Also `legend_of`'s: two figure legends cannot say which names this
    # axes' colours, and a confident wrong name is worse than none. Asserted
    # for both classes because both now route through it.
    figure, ax = plt.subplots()
    draw(ax)
    own = ax.get_legend()
    handles = own.legend_handles
    own.remove()
    figure.legend(handles, ["p", "q"], title="g", loc="upper left")
    figure.legend(handles, ["p", "q"], title="h", loc="upper right")

    assert "z" not in _schema(figure)["axes"]
