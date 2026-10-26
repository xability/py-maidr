"""A plotly step chart names its levels by the y axis's ``ticktext``.

A hypnogram codes its sleep stages as numbers -- they drive the pitch, the
braille and the range -- and names them with ``tickvals`` and ``ticktext``.
Only the codes were read, so the reader heard "Sleep stage is 4" where the
chart says Awake, as an audit that drove every example with the keyboard
found. Each point on a named tick now carries the name as ``label``, which
the core announces instead of the number; the matplotlib reader does the same
from named y ticks.
"""

from __future__ import annotations

import pytest

pytest.importorskip("plotly")
np = pytest.importorskip("numpy")

import plotly.graph_objects as go  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

STAGES = ["N3", "N2", "N1", "REM", "Awake"]
CODES = [4, 3, 2, 1, 0, 0, 1, 3, 2, 1, 0, 1, 3, 2, 1, 3, 4]


def _hypnogram(**yaxis) -> go.Figure:
    """The gallery's hypnogram, with the y axis given."""
    fig = go.Figure(
        go.Scatter(
            x=[i * 0.5 for i in range(len(CODES))],
            y=CODES,
            mode="lines",
            line_shape="hv",
            name="Night 1",
        )
    )
    fig.update_layout(yaxis=yaxis)
    return fig


def _named(**yaxis) -> go.Figure:
    return _hypnogram(
        title="Sleep stage",
        tickvals=list(range(len(STAGES))),
        ticktext=STAGES,
        **yaxis,
    )


def _points(fig: go.Figure) -> list[dict]:
    """The one step layer's points, across its series."""
    (layer,) = [plot.schema for plot in PlotlyMaidr(fig)._plots]
    assert layer[MaidrKey.TYPE] == PlotType.STEP
    return [point for series in layer[MaidrKey.DATA] for point in series]


def test_every_point_carries_the_stage_its_code_names():
    points = _points(_named(tickmode="array"))

    assert [point.get(MaidrKey.LABEL.value) for point in points] == [
        STAGES[code] for code in CODES
    ]
    # The code stays the value: it is what drives the pitch and the range.
    assert [point[MaidrKey.Y.value] for point in points] == CODES


def test_tickvals_alone_put_the_axis_in_array_mode():
    # Plotly's default once `tickvals` is given, as the gallery writes it.
    points = _points(_named())

    assert {p["label"] for p in points if p["y"] == 3} == {"REM"}


@pytest.mark.parametrize("tickmode", ["auto", "linear"])
def test_a_tick_mode_that_ignores_tickvals_names_nothing(tickmode):
    # Plotly draws neither the ticks nor the text in these modes.
    assert not any("label" in p for p in _points(_named(tickmode=tickmode)))


def test_an_axis_without_names_is_read_as_numbers():
    assert not any("label" in p for p in _points(_hypnogram(title="Stage")))


def test_a_point_between_named_ticks_keeps_its_number():
    points = _points(_hypnogram(tickvals=[0, 4], ticktext=["N3", "Awake"]))

    assert {p["y"]: p.get("label") for p in points} == {
        0: "N3",
        1: None,
        2: None,
        3: None,
        4: "Awake",
    }


def test_numbers_written_out_and_blanks_name_no_level():
    points = _points(
        _hypnogram(tickvals=[0, 1, 2, 3, 4], ticktext=["0", "1,000", "", "REM", "4"])
    )

    assert {p["y"]: p.get("label") for p in points} == {
        0: None,
        1: None,
        2: None,
        3: "REM",
        4: None,
    }


def test_a_word_float_would_read_is_still_a_name():
    # `float` takes "NaN" and "Infinity"; a tick named so is named so.
    points = _points(
        _hypnogram(
            tickvals=[0, 1, 2, 3, 4],
            ticktext=["NaN", "Infinity", "1e3", "\u22122", ".5"],
        )
    )

    assert {p["y"]: p.get("label") for p in points} == {
        0: "NaN",
        1: "Infinity",
        2: None,
        3: None,
        4: None,
    }


def test_a_computed_value_on_a_named_tick_takes_its_name():
    # 0.1 + 0.2 is 0.30000000000000004, drawn on the tick at 0.3.
    fig = go.Figure(
        go.Scatter(x=[0, 1], y=[0.1 + 0.2, 0.6], mode="lines", line_shape="hv")
    )
    fig.update_layout(yaxis={"tickvals": [0.3, 0.6], "ticktext": ["Low", "High"]})

    assert [p.get("label") for p in _points(fig)] == ["Low", "High"]


def test_a_name_is_read_without_its_markup():
    points = _points(
        _hypnogram(tickvals=[3], ticktext=["<b>REM</b><br>sleep"])
    )

    assert {p.get("label") for p in points if p["y"] == 3} == {"REM sleep"}


def test_numpy_tick_arrays_are_read():
    # Exported as typed-array specs, which have to be decoded to be read.
    points = _points(
        _hypnogram(tickvals=np.arange(len(STAGES)), ticktext=np.array(STAGES))
    )

    assert {p["label"] for p in points if p["y"] == 4} == {"Awake"}


def test_a_shared_panel_takes_the_names_of_the_axis_it_matches():
    # `shared_yaxes` hides the right panel's tick labels in favor of the left
    # one's, which carries the names.
    fig = make_subplots(rows=1, cols=2, shared_yaxes=True)
    for col in (1, 2):
        fig.add_trace(
            go.Scatter(x=[0, 1, 2], y=[0, 3, 4], mode="lines", line_shape="hv"),
            row=1,
            col=col,
        )
    fig.update_yaxes(tickvals=list(range(5)), ticktext=STAGES, row=1, col=1)

    layers = [plot.schema for plot in PlotlyMaidr(fig)._plots]

    assert [
        [point.get("label") for point in layer[MaidrKey.DATA][0]] for layer in layers
    ] == [["N3", "REM", "Awake"], ["N3", "REM", "Awake"]]
