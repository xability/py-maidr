"""``data`` and ``selector`` come out of one pass, so it must run only once.

``PlotlyStepPlot`` and ``PlotlyMultiLinePlot`` filter their series and their
positions by the same predicate, in ``_line_series_with_positions``, so that
series *i* always addresses the element series *i* is drawn as (#316).
``render()`` then asks for the two halves separately -- ``_extract_plot_data()``
and ``_get_selector()`` -- and each was calling that pass for itself.

Repeating it assumes it can be repeated. ``as_list`` materialises a trace array
with ``list(value)``, so a one-shot iterable is spent by the first walk and
reads as empty on the second: the layer reports its series and then no selector
at all. That is the silent no-highlight the pairing exists to prevent, arrived
at from the other direction.
"""

from __future__ import annotations

import pytest

from maidr.core.enum.maidr_key import MaidrKey
from maidr.plotly.multiline import PlotlyMultiLinePlot
from maidr.plotly.plotly_plot import PlotlyPlot
from maidr.plotly.step import PlotlyStepPlot

pytest.importorskip("plotly")


def _step(x, y, name: str) -> dict:
    """
    Build a staircase trace.

    Parameters
    ----------
    x, y : Any
        Sample coordinates, in any shape ``as_list`` accepts.
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


def _line(x, y, name: str) -> dict:
    """
    Build a plain line trace.

    Parameters
    ----------
    x, y : Any
        Sample coordinates, in any shape ``as_list`` accepts.
    name : str
        Trace name.

    Returns
    -------
    dict
        A scatter/lines trace dict.
    """
    return {"type": "scatter", "mode": "lines", "x": x, "y": y, "name": name}


#: Both classes share the pass, so every case runs against both.
CLASSES = [
    pytest.param(PlotlyStepPlot, _step, id="step"),
    pytest.param(PlotlyMultiLinePlot, _line, id="multiline"),
]


@pytest.mark.parametrize(("plot_class", "make"), CLASSES)
def test_a_one_shot_trace_array_keeps_its_selectors(plot_class, make) -> None:
    """An iterator is spent by the first walk, so the second must not happen.

    ``Figure.to_dict()`` hands back lists, numpy arrays and typed-array specs,
    never an iterator, so the export path does not reach this. A caller
    constructing a layer directly does, and ``as_list`` accepts it -- the
    array simply comes out empty the second time, and with it every selector.
    """
    traces = [
        make(iter([0, 1]), iter([1, 2]), "a"),
        make(iter([0, 1]), iter([2, 1]), "b"),
    ]

    schema = plot_class(traces, {}, scatter_positions=[0, 1]).schema

    assert len(schema[MaidrKey.DATA]) == 2
    assert len(schema[MaidrKey.SELECTOR]) == 2


@pytest.mark.parametrize(("plot_class", "make"), CLASSES)
def test_the_pass_runs_once_per_render(plot_class, make, mocker) -> None:
    """One render, one walk of the points.

    Asserted on the call count rather than on timing: the pass allocates a
    dict per point of every trace, so running it twice doubles the cost of
    exporting a figure, and a count says so without a benchmark's noise.
    """
    spy = mocker.spy(PlotlyPlot, "_line_series_with_positions")
    traces = [make([0, 1], [1, 2], "a"), make([0, 1], [2, 1], "b")]

    plot_class(traces, {}, scatter_positions=[0, 1]).schema

    assert spy.call_count == 1


@pytest.mark.parametrize(("plot_class", "make"), CLASSES)
def test_a_second_layer_is_not_served_the_first_one_s_answer(
    plot_class, make
) -> None:
    """The cache is per layer, and keyed on the lists it was built from.

    Each layer is its own instance, so this could not go wrong today -- which
    is the point: it pins that the cache stays scoped to what it was computed
    for rather than becoming a class-level one later.
    """
    first = plot_class([make([0, 1], [1, 2], "a")], {}, scatter_positions=[0])
    second = plot_class([make([0, 1, 2], [5, 6, 7], "b")], {}, scatter_positions=[4])

    assert len(first.schema[MaidrKey.DATA][0]) == 2
    assert len(second.schema[MaidrKey.DATA][0]) == 3
    assert "nth-child(1)" in first.schema[MaidrKey.SELECTOR][0]
    assert "nth-child(5)" in second.schema[MaidrKey.SELECTOR][0]


@pytest.mark.parametrize(("plot_class", "make"), CLASSES)
def test_different_traces_are_not_answered_from_the_cache(plot_class, make) -> None:
    """Passing other lists recomputes rather than returning the stored pair.

    The cache holds one entry and matches it by the identity of both lists, so
    this is what keeps a helper that looks reusable actually reusable.
    """
    layer = plot_class([make([0, 1], [1, 2], "a")], {}, scatter_positions=[0])
    layer.schema

    other_traces = [make([0, 1, 2], [9, 9, 9], "b")]
    series, positions = layer._drawn_line_series(other_traces, [7])

    assert len(series[0]) == 3
    assert positions == [7]


@pytest.mark.parametrize(("plot_class", "make"), CLASSES)
def test_rendering_twice_gives_the_same_answer(plot_class, make) -> None:
    """A cached pass must not make the second render differ from the first.

    ``Maidr`` re-renders a figure whenever it is shown again, and a cache that
    served a stale or half-consumed answer would surface exactly there.
    """
    traces = [make([0, 1], [1, 2], "a"), make([], [], "empty"), make([2], [3], "c")]
    layer = plot_class(traces, {}, scatter_positions=[0, 1, 2])

    first = layer.render()
    second = layer.render()

    assert first[MaidrKey.DATA] == second[MaidrKey.DATA]
    assert first[MaidrKey.SELECTOR] == second[MaidrKey.SELECTOR]
