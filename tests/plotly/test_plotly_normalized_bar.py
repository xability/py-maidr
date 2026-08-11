"""A 100% stacked bar is its own chart, not a stacked bar with other numbers.

Plotly declares normalisation on the layout as ``barnorm`` and applies it at
render time, leaving the trace arrays absolute. So nothing in the data says
the bars were drawn to a common total: read as ``stacked_bar``, the chart is
announced under the wrong name, and the equal bar heights a sighted reader
sees have no counterpart in what is said (#338).

``barnorm`` being declared rather than computed is what makes this detectable
here at all. matplotlib and seaborn have no equivalent -- a caller who wants
100% bars normalises the data first, so by the time py-maidr sees it there is
nothing left to distinguish it from a stacked bar of shares.
"""

from __future__ import annotations

import pytest

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_maidr import PlotlyMaidr

plotly = pytest.importorskip("plotly")
go = pytest.importorskip("plotly.graph_objects")


def _two_bar_figure(**layout):
    """
    Build a two-trace bar figure with the given layout.

    Parameters
    ----------
    **layout
        Passed straight to ``update_layout`` -- ``barmode``, ``barnorm``.

    Returns
    -------
    plotly.graph_objects.Figure
        A figure with two bar traces over the same two categories.
    """
    figure = go.Figure(
        data=[
            go.Bar(name="x", x=["a", "b"], y=[1, 2]),
            go.Bar(name="y", x=["a", "b"], y=[3, 2]),
        ]
    )
    figure.update_layout(**layout)
    return figure


@pytest.mark.parametrize("barnorm", ["percent", "fraction"])
def test_a_normalised_stack_is_its_own_type(barnorm: str) -> None:
    """Both of plotly's normalisations produce the 100% type.

    ``fraction`` and ``percent`` differ only in the units drawn on the axis;
    both draw every bar to the same length, which is the thing being named.
    """
    figure = _two_bar_figure(barmode="stack", barnorm=barnorm)

    assert PlotlyMaidr(figure)._plots[0].type is PlotType.NORMALIZED


def test_a_plain_stack_is_unchanged() -> None:
    """Without ``barnorm`` the bars carry their own totals, as before."""
    figure = _two_bar_figure(barmode="stack")

    assert PlotlyMaidr(figure)._plots[0].type is PlotType.STACKED


def test_a_grouped_bar_is_unchanged() -> None:
    """``barmode='group'`` wins regardless: nothing is stacked to normalise.

    Plotly ignores ``barnorm`` for grouped bars, so reading it here would
    rename a chart whose bars were never drawn to a common total.
    """
    figure = _two_bar_figure(barmode="group", barnorm="percent")

    assert PlotlyMaidr(figure)._plots[0].type is PlotType.DODGED


def test_an_unknown_barnorm_is_not_treated_as_normalised() -> None:
    """Only the two values plotly defines count.

    A typo or a future value must fall back to the honest ``stacked_bar``
    rather than claiming a normalisation that plotly will not have drawn.
    """
    figure = _two_bar_figure(barmode="stack", barnorm="")

    assert PlotlyMaidr(figure)._plots[0].type is PlotType.STACKED


def test_the_emitted_values_stay_absolute() -> None:
    """The type changes; the numbers do not.

    Plotly leaves the trace arrays absolute and normalises when drawing, and
    the Vega-Lite adapter -- the only other producer of this type -- emits its
    rows unchanged for ``NORMALIZED`` too. Following that keeps one wire
    meaning for the field rather than two that depend on the producer.
    """
    figure = _two_bar_figure(barmode="stack", barnorm="percent")

    layer = PlotlyMaidr(figure)._plots[0].render()

    assert layer[MaidrKey.TYPE] is PlotType.NORMALIZED
    assert [point[MaidrKey.Y.value] for point in layer[MaidrKey.DATA][0]] == [1, 2]
    assert [point[MaidrKey.Y.value] for point in layer[MaidrKey.DATA][1]] == [3, 2]


def test_the_type_reads_as_a_user_would_name_it() -> None:
    """The display name is what someone would call the chart."""
    assert PlotType.NORMALIZED.display_name == "100% stacked bar"
    assert PlotType.NORMALIZED.value == "stacked_normalized_bar"
