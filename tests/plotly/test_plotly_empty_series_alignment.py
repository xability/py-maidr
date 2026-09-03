"""``data`` and ``selector`` are paired positionally, so they must stay aligned.

The frontend pairs selector *i* with series *i*. ``PlotlyStepPlot`` and
``PlotlyMultiLinePlot`` built the two lists from the same traces by two
different rules: a trace whose ``x``/``y`` came out empty was dropped from the
data and still consumed a selector. Every series after the empty one then
addressed its predecessor's element (#316).

The failure is silent in the way ``nth-child`` failures always are. Audio,
braille and text are all correct, and only the visual highlight is wrong -- so
a sighted collaborator sees the wrong line highlighted while the person using
the announcements has no way to notice. That is why these assert on the
selector *strings* rather than only on the two lengths matching: equal lengths
would also be satisfied by pointing every series at the wrong element.
"""

from __future__ import annotations

import pytest

from maidr.core.enum.maidr_key import MaidrKey
from maidr.plotly.multiline import PlotlyMultiLinePlot
from maidr.plotly.step import PlotlyStepPlot

pytest.importorskip("plotly")


def _step(x: list, y: list, name: str) -> dict:
    """
    Build a staircase trace.

    Parameters
    ----------
    x, y : list
        Sample coordinates; either may be empty.
    name : str
        Trace name.

    Returns
    -------
    dict
        A scatter trace whose ``line.shape`` makes plotly draw risers.
    """
    return {
        "type": "scatter",
        "mode": "lines",
        "x": x,
        "y": y,
        "line": {"shape": "hv"},
        "name": name,
    }


def _line(x: list, y: list, name: str) -> dict:
    """
    Build a plain line trace.

    Parameters
    ----------
    x, y : list
        Sample coordinates; either may be empty.
    name : str
        Trace name.

    Returns
    -------
    dict
        A scatter/lines trace dict.
    """
    return {"type": "scatter", "mode": "lines", "x": x, "y": y, "name": name}


def nth_child(selector: str) -> int:
    """
    Read the ``nth-child`` index out of a selector.

    Parameters
    ----------
    selector : str
        A selector built by ``_scatter_line_selector``.

    Returns
    -------
    int
        The one-based index the selector addresses.
    """
    marker = "nth-child("
    start = selector.index(marker) + len(marker)
    return int(selector[start : selector.index(")", start)])


#: The two classes share the defect and the fix, and the issue asked that they
#: stay consistent with each other, so every case runs against both.
CLASSES = [
    pytest.param(PlotlyStepPlot, _step, id="step"),
    pytest.param(PlotlyMultiLinePlot, _line, id="multiline"),
]


@pytest.mark.parametrize(("plot_class", "make"), CLASSES)
def test_an_empty_series_does_not_shift_the_ones_after_it(plot_class, make) -> None:
    """The series after an empty trace addresses its own element.

    This is the reported bug. ``'c'`` is the figure's third trace and renders
    at ``nth-child(3)``; paired with the empty trace's selector it highlighted
    ``nth-child(2)`` instead.
    """
    traces = [
        make([0, 1], [1, 2], "a"),
        make([], [], "empty"),
        make([0, 1], [2, 1], "c"),
    ]

    schema = plot_class(traces, {}, scatter_positions=[0, 1, 2]).schema
    data = schema[MaidrKey.DATA]
    selectors = schema[MaidrKey.SELECTOR]

    assert len(data) == len(selectors)
    assert [nth_child(s) for s in selectors] == [1, 3]


@pytest.mark.parametrize(("plot_class", "make"), CLASSES)
def test_a_leading_empty_series_shifts_nothing_either(plot_class, make) -> None:
    """The empty trace need not be in the middle for the lists to diverge."""
    traces = [
        make([], [], "empty"),
        make([0, 1], [1, 2], "b"),
        make([0, 1], [2, 1], "c"),
    ]

    schema = plot_class(traces, {}, scatter_positions=[0, 1, 2]).schema

    assert [nth_child(s) for s in schema[MaidrKey.SELECTOR]] == [2, 3]


@pytest.mark.parametrize(("plot_class", "make"), CLASSES)
def test_the_data_contract_is_unchanged(plot_class, make) -> None:
    """An empty trace still produces no series, as it did before.

    The alternative fix -- keeping the empty series so the lists stay
    parallel -- would have emitted a zero-point series for the frontend to
    tolerate. Dropping the position instead leaves ``data`` exactly as it was.
    """
    traces = [
        make([0, 1], [1, 2], "a"),
        make([], [], "empty"),
        make([0, 1], [2, 1], "c"),
    ]

    data = plot_class(traces, {}, scatter_positions=[0, 1, 2]).schema[MaidrKey.DATA]

    assert len(data) == 2
    assert [point[MaidrKey.Z] for series in data for point in series[:1]] == ["a", "c"]


@pytest.mark.parametrize(("plot_class", "make"), CLASSES)
def test_a_layer_with_no_empty_trace_is_untouched(plot_class, make) -> None:
    """The common case keeps every position it was given."""
    traces = [make([0, 1], [1, 2], "a"), make([0, 1], [2, 1], "b")]

    schema = plot_class(traces, {}, scatter_positions=[3, 4]).schema

    assert len(schema[MaidrKey.DATA]) == 2
    assert [nth_child(s) for s in schema[MaidrKey.SELECTOR]] == [4, 5]


@pytest.mark.parametrize(("plot_class", "make"), CLASSES)
def test_every_trace_empty_emits_no_selectors_at_all(plot_class, make) -> None:
    """Nothing drawn, nothing to address.

    ``render()`` omits the key entirely when the selector list is empty, which
    is the path a WebGL layer already takes and which the base class documents
    as the honest answer for a layer with no highlightable geometry. This case
    now joins it. Before, it was the defect at its purest: no data, and a
    selector for every trace anyway.
    """
    traces = [make([], [], "a"), make([], [], "b")]

    schema = plot_class(traces, {}, scatter_positions=[0, 1]).schema

    assert schema[MaidrKey.DATA] == []
    assert MaidrKey.SELECTOR not in schema


@pytest.mark.parametrize(("plot_class", "make"), CLASSES)
def test_a_trace_with_no_y_counts_as_empty_too(plot_class, make) -> None:
    """``zip`` stops at the shorter side, so an absent y draws nothing.

    A trace carrying x but no y produces no points and therefore no element,
    which is the same case as an empty x reaching the same guard by a
    different route.
    """
    traces = [
        make([0, 1], [1, 2], "a"),
        make([0, 1], [], "no y"),
        make([0, 1], [2, 1], "c"),
    ]

    schema = plot_class(traces, {}, scatter_positions=[0, 1, 2]).schema

    assert len(schema[MaidrKey.DATA]) == 2
    assert [nth_child(s) for s in schema[MaidrKey.SELECTOR]] == [1, 3]
