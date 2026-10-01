"""A series on two numeric axes is read as arrays, and reads exactly as it did.

A line, a step, an ECDF or an area on numeric axes used to be read one sample
at a time: every coordinate went through ``_named_coordinate``, ``_scalar``,
``_has_position`` and ``_reading``, each point was built as a dict keyed by
``MaidrKey`` members, and a band check rebuilt both columns from those dicts.
On a 200k-point ``ax.plot`` that was 0.56 s of a 0.88 s render.

Two numeric axes name nothing, so those calls reduce to ``float()`` and two
finiteness tests, which NumPy answers for a whole column at once. The points
are now built from the columns directly, keyed by the plain strings the
members stand for. That second part matters as much as the first: an enum
member is an object the garbage collector tracks, so every dict keyed by one
was tracked too, and each full collection later in the render walked every
point of every series -- about a quarter of that render on its own.

What is pinned here is that nothing a reader receives changes. Each chart is
read twice, once in bulk and once with the bulk path switched off so the
per-sample reading -- still the one a category axis takes -- runs instead,
and the two payloads must serialize identically. The cases are the ones a
rewrite could get wrong: gaps, infinities, masks, ``-0.0``, integers, dates,
log axes, a confidence band, an ECDF's ``-inf`` start, several named series
and the smallest series there are.
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.core.plot import lineplot  # noqa: E402
from maidr.core.plot.areaplot import AreaPlot  # noqa: E402
from maidr.util.mixin.extractor_mixin import LineExtractorMixin  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _walk(n: int, seed: int = 0) -> np.ndarray:
    return np.random.default_rng(seed).normal(size=n).cumsum()


def _line(ax):
    ax.plot(np.arange(500.0), _walk(500))


def _gaps(ax):
    y = _walk(300)
    y[[10, 11, 50]] = np.nan
    y[100] = np.inf
    y[101] = -np.inf
    x = np.arange(300.0)
    x[[200, 201]] = np.nan
    x[250] = np.inf
    ax.plot(x, y)


def _masked(ax):
    y = np.ma.masked_array(_walk(100), mask=np.arange(100) % 7 == 0)
    ax.plot(np.arange(100), y)


def _signed_zeros(ax):
    ax.plot([-0.0, 0.0, 1.0, 2.0], [0.0, -0.0, -0.0, 3.0])


def _integers(ax):
    ax.plot(np.arange(50), np.arange(50) ** 2)


def _dates(ax):
    ax.plot(pd.date_range("2024-01-01", periods=120, freq="h"), _walk(120))


def _aware_dates(ax):
    when = pd.date_range("2024-01-01", periods=48, freq="h", tz="US/Central")
    ax.plot(when, _walk(48))


def _log(ax):
    ax.plot(np.arange(1.0, 200.0), np.exp(np.linspace(0, 8, 199)))
    ax.set_yscale("log")


def _one_point(ax):
    ax.plot([1.5], [2.5], "o")


def _two_points(ax):
    ax.plot([0.0, 1.0], [1.0, 0.5])


def _named_series(ax):
    for index in range(4):
        ax.plot(np.arange(80.0), _walk(80, index), label=f"series {index}")
    ax.legend()


def _band(ax):
    x = np.linspace(0, 10, 200)
    y = np.sin(x)
    ax.plot(x, y)
    ax.fill_between(x, y - 0.3, y + 0.4, alpha=0.3)


def _seaborn_band(ax):
    rng = np.random.default_rng(3)
    frame = pd.DataFrame({"x": np.repeat(np.arange(40), 6), "y": rng.normal(size=240)})
    sns.lineplot(frame, x="x", y="y", ax=ax, seed=0)


def _seaborn_hue(ax):
    rng = np.random.default_rng(4)
    frame = pd.DataFrame(
        {
            "x": np.tile(np.arange(30), 3),
            "y": rng.normal(size=90),
            "g": np.repeat(["a", "b", "c"], 30),
        }
    )
    sns.lineplot(frame, x="x", y="y", hue="g", ax=ax, errorbar=None)


def _step(ax):
    ax.step(np.arange(60.0), _walk(60), where="mid")


def _ecdf(ax):
    sns.ecdfplot(np.random.default_rng(5).normal(size=300), ax=ax)


def _categorical(ax):
    ax.plot(["a", "b", "c", "d"], [1.0, 3.0, 2.0, 4.0])


LINES = {
    "line": _line,
    "gaps": _gaps,
    "masked": _masked,
    "signed-zeros": _signed_zeros,
    "integers": _integers,
    "dates": _dates,
    "aware-dates": _aware_dates,
    "log": _log,
    "one-point": _one_point,
    "two-points": _two_points,
    "named-series": _named_series,
    "band": _band,
    "seaborn-band": _seaborn_band,
    "seaborn-hue": _seaborn_hue,
    "step": _step,
    "ecdf": _ecdf,
}


def _payloads(draw, types) -> list[str]:
    """Every layer of the given types, serialized as the page receives it."""
    fig, ax = plt.subplots()
    draw(ax)
    plots = [plot for plot in FigureManager.get_maidr(fig).plots if plot.type in types]
    assert plots, "the chart registered none of the layers under test"
    return [json.dumps(plot.schema[MaidrKey.DATA]) for plot in plots]


_LINE_TYPES = {PlotType.LINE, PlotType.STEP}


@pytest.mark.parametrize("name", list(LINES))
def test_a_line_reads_in_bulk_as_it_does_sample_by_sample(name, monkeypatch):
    bulk_reads = []
    read = lineplot._numeric_points

    def counting(*args):
        bulk_reads.append(1)
        return read(*args)

    monkeypatch.setattr(lineplot, "_numeric_points", counting)
    bulk = _payloads(LINES[name], _LINE_TYPES)
    assert bulk_reads, "the bulk reading never ran, so nothing was compared"

    monkeypatch.setattr(lineplot, "_numeric_samples", lambda line: None)
    per_sample = _payloads(LINES[name], _LINE_TYPES)

    assert bulk == per_sample


def test_a_category_axis_still_reads_sample_by_sample(monkeypatch):
    # Names come from the ticks, which only the per-sample reading consults.
    def refused(*args):
        raise AssertionError("a category axis was read in bulk")

    monkeypatch.setattr(lineplot, "_numeric_points", refused)

    (payload,) = _payloads(_categorical, _LINE_TYPES)

    assert [point["x"] for point in json.loads(payload)[0]] == ["a", "b", "c", "d"]


def _stack(ax):
    x = np.arange(40.0)
    ax.stackplot(x, _walk(40, 1) + 10, _walk(40, 2) + 10, labels=["p", "q"])


def _stack_unlabeled(ax):
    ax.stackplot(np.arange(30), np.arange(30) % 7, np.arange(30) % 5)


def _stack_gaps(ax):
    x = np.arange(25.0)
    x[[3, 4]] = np.nan
    y = _walk(25, 3) + 10
    y[[7, 8]] = np.nan
    y[9] = np.inf
    ax.stackplot(x, y, np.abs(_walk(25, 4)), labels=["r", "s"])


def _stack_float32(ax):
    ax.stackplot(
        np.arange(20, dtype=np.float32),
        np.linspace(0.1, 2.0, 20, dtype=np.float32),
        np.linspace(1.0, 0.5, 20, dtype=np.float32),
    )


def _fill(ax):
    x = np.linspace(0.0, 5.0, 60)
    ax.fill_between(x, np.sin(x) + 2, label="area")


def _fill_sideways(ax):
    y = np.linspace(0.0, 5.0, 60)
    ax.fill_betweenx(y, np.cos(y) + 2)


def _fill_dates(ax):
    when = pd.date_range("2024-01-01", periods=30, freq="D")
    ax.fill_between(when, np.abs(_walk(30, 6)))


def _fill_words(ax):
    ax.fill_between(["a", "b", "c", "d"], [1.0, 3.0, 2.0, 4.0])


AREAS = {
    "stack": _stack,
    "stack-unlabeled": _stack_unlabeled,
    "stack-gaps": _stack_gaps,
    "stack-float32": _stack_float32,
    "fill": _fill,
    "fill-sideways": _fill_sideways,
    "fill-dates": _fill_dates,
    "fill-words": _fill_words,
}

_AREA_TYPES = {PlotType.AREA, PlotType.STACKED_AREA}


@pytest.mark.parametrize("name", list(AREAS))
def test_an_area_reads_in_bulk_as_it_does_point_by_point(name, monkeypatch):
    bulk = _payloads(AREAS[name], _AREA_TYPES)

    monkeypatch.setattr(
        AreaPlot, "_numeric_positions", staticmethod(lambda positions: (None, None))
    )
    per_point = _payloads(AREAS[name], _AREA_TYPES)

    assert bulk == per_point


@pytest.mark.parametrize(
    "draw, types",
    [
        pytest.param(_named_series, _LINE_TYPES, id="line"),
        pytest.param(_band, _LINE_TYPES, id="line-band"),
        pytest.param(_step, _LINE_TYPES, id="step"),
        pytest.param(_stack, _AREA_TYPES, id="stack"),
    ],
)
def test_a_numeric_point_is_keyed_by_plain_strings(draw, types):
    """The keys are the strings the members stand for, not the members.

    The JSON is the same either way. The garbage collector is not: an enum
    member is an object it tracks, so a dict keyed by one is tracked too,
    and a long series kept every one of its points in the heap that each
    full collection walks for the rest of the render.
    """
    fig, ax = plt.subplots()
    draw(ax)

    for plot in FigureManager.get_maidr(fig).plots:
        if plot.type not in types:
            continue
        for series in plot.schema[MaidrKey.DATA]:
            for point in series:
                assert {type(key) for key in point} == {str}, point


def test_the_ticks_are_read_once_per_layer_not_once_per_line(monkeypatch):
    """On a category axis every read lays every tick out again."""
    reads = []
    read = LineExtractorMixin._category_tick_labels

    def counting(ax, axis):
        reads.append(axis)
        return read(ax, axis)

    monkeypatch.setattr(
        LineExtractorMixin, "_category_tick_labels", staticmethod(counting)
    )
    fig, ax = plt.subplots()
    for offset in range(5):
        ax.plot(["a", "b", "c", "d"], np.arange(4.0) + offset)
    (plot,) = [
        plot for plot in FigureManager.get_maidr(fig).plots if plot.type in _LINE_TYPES
    ]
    reads.clear()

    plot.schema

    assert sorted(reads) == ["x", "y"]
