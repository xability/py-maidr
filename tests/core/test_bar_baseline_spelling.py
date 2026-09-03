"""A stacked bar's baseline is read however matplotlib lets it be written.

``Axes.bar(x, height, width=0.8, bottom=None)`` takes its baseline as the
fourth positional argument and ``Axes.barh`` takes ``left`` the same way, but
the patch read the two names off ``kwargs`` alone. Measured on the two
spellings of one chart (#754)::

    ax.bar(x, a); ax.bar(x, b, bottom=a)    ['bar', 'stacked_bar'] -> stacked_bar
    ax.bar(x, a); ax.bar(x, b, 0.8, a)      ['bar', 'bar']         -> bar, bar

The numbers were right both ways. What the positional spelling withheld from
a reader is that the second series sits on the first, which is the whole
content of a stacked chart -- the #385 failure again, one argument over.

Two neighbours of the same read. ``bottom=0`` is matplotlib's own default
written out, and it registered a one-group stack whose only group wore
matplotlib's container label ``_container0``. And the thickness that decides
whether two calls are dodged was read as ``width`` for both orientations, so
``ax.barh(..., height=0.4)`` twice compared the bar *lengths* and read as two
plain layers where ``ax.bar(..., width=0.4)`` twice reads as dodged.

And the same misreading one step over (#760): a constant non-zero baseline
on bare axes -- ``bottom=5``, ``bottom=[5, 5, 5]``, ``left=5`` -- is an axis
offset, not a second series, yet it registered the same one-group stack. A
baseline only says "stacked" when a bar layer already sits under it.
"""

from __future__ import annotations

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.patch.barplot import _is_constant_baseline  # noqa: E402

CATEGORIES = ["a", "b", "c"]
SERIES_0 = np.array([10.0, 20.0, 30.0])
SERIES_1 = np.array([30.0, 20.0, 10.0])


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def _registered(fig) -> list[str]:
    """The types of every layer registered on the figure, in call order."""
    return [plot.type.value for plot in FigureManager.get_maidr(fig).plots]


def _emitted(fig) -> list[tuple[str, object]]:
    """``(type, data)`` of every layer the first subplot cell emits.

    The data and not only the type, because a stack with the wrong number of
    groups and a stack with the right number are the same word.
    """
    grid = FigureManager.get_maidr(fig)._flatten_maidr()["subplots"]
    return [
        (layer["type"].value, layer["data"]) for layer in grid[0][0].get("layers", [])
    ]


def test_a_positional_baseline_reads_as_a_stack() -> None:
    """The reproduction: ``bottom`` as the fourth positional argument.

    Asserted against the keyword spelling of the same chart rather than
    against a literal, since the two are one chart and a reader must be
    told the same thing about both.
    """
    fig, ax = plt.subplots()
    ax.bar(CATEGORIES, SERIES_0, label="s0")
    ax.bar(CATEGORIES, SERIES_1, 0.8, SERIES_0, label="s1")

    reference, reference_ax = plt.subplots()
    reference_ax.bar(CATEGORIES, SERIES_0, label="s0")
    reference_ax.bar(CATEGORIES, SERIES_1, 0.8, bottom=SERIES_0, label="s1")

    assert _registered(fig) == ["bar", "stacked_bar"]
    assert _emitted(fig) == _emitted(reference)
    assert [kind for kind, _ in _emitted(fig)] == ["stacked_bar"]
    assert len(_emitted(fig)[0][1]) == 2, "both series are groups of the stack"


def test_a_positional_left_reads_barh_as_a_stack() -> None:
    """``left`` is ``barh``'s spelling of the baseline, positional as well."""
    fig, ax = plt.subplots()
    ax.barh(CATEGORIES, SERIES_0, label="s0")
    ax.barh(CATEGORIES, SERIES_1, 0.8, SERIES_0, label="s1")

    assert _registered(fig) == ["bar", "stacked_bar"]
    assert [kind for kind, _ in _emitted(fig)] == ["stacked_bar"]
    assert len(_emitted(fig)[0][1]) == 2


@pytest.mark.parametrize(
    "baseline",
    [
        pytest.param(0, id="int"),
        pytest.param(0.0, id="float"),
        pytest.param(np.zeros(len(CATEGORIES)), id="zeros"),
    ],
)
def test_a_zero_baseline_is_a_plain_bar(baseline) -> None:
    """A baseline of zeros is where a bar starts anyway.

    ``bottom=0`` used to register a stack of one group, named after the
    container matplotlib minted for it, so a plain chart was announced as
    a stacked one. Each spelling of zero has to read exactly as the bare
    call does.
    """
    fig, ax = plt.subplots()
    ax.bar(CATEGORIES, SERIES_0, bottom=baseline)

    bare, bare_ax = plt.subplots()
    bare_ax.bar(CATEGORIES, SERIES_0)

    assert _registered(fig) == ["bar"]
    assert _emitted(fig) == _emitted(bare)


def test_a_zero_first_baseline_still_collapses_into_the_stack() -> None:
    """The idiom every older test wrote, kept working.

    ``bottom=0`` on the first call now registers ``BAR`` rather than
    ``STACKED``, which is the shape matplotlib's own gallery example already
    has -- and the segmented layer that follows supersedes it, so the chart
    still emits as one stack of two groups.
    """
    fig, ax = plt.subplots()
    ax.bar(CATEGORIES, SERIES_0, bottom=0, label="s0")
    ax.bar(CATEGORIES, SERIES_1, bottom=SERIES_0, label="s1")

    assert _registered(fig) == ["bar", "stacked_bar"]
    assert [kind for kind, _ in _emitted(fig)] == ["stacked_bar"]
    assert len(_emitted(fig)[0][1]) == 2


def test_an_unbound_call_reads_its_arguments_at_the_same_indices() -> None:
    """``Axes.bar(ax, x, h, w, b)`` binds ``b`` to ``bottom`` too.

    The unbound spelling reaches the patch through wrapt's partial proxy,
    whose signature still opens with ``self`` while the instance is already
    out of ``args``. Read naively, every index lands one argument early:
    the width was found at the baseline's slot, so two side-by-side calls
    stopped reading as dodged, and a positional baseline was not found at
    all. Both have to read exactly as the bound call does.
    """
    positions = np.arange(len(CATEGORIES))

    dodged, dodged_ax = plt.subplots()
    Axes.bar(dodged_ax, positions + 0.2, SERIES_0, 0.4, label="s0")
    Axes.bar(dodged_ax, positions - 0.2, SERIES_1, 0.4, label="s1")

    stacked, stacked_ax = plt.subplots()
    Axes.bar(stacked_ax, CATEGORIES, SERIES_0, label="s0")
    Axes.bar(stacked_ax, CATEGORIES, SERIES_1, 0.8, SERIES_0, label="s1")

    assert _registered(dodged) == ["dodged_bar", "dodged_bar"]
    assert _registered(stacked) == ["bar", "stacked_bar"]


def test_a_zero_baseline_named_in_data_is_a_plain_bar() -> None:
    """``bottom="b", data=df`` with a column of zeros reads as the bare call.

    The name is looked up before the zero test, so the two spellings of one
    chart -- the column by name and the column by value -- agree.
    """
    frame = pd.DataFrame({"x": CATEGORIES, "h": SERIES_0, "b": np.zeros(3)})
    fig, ax = plt.subplots()
    ax.bar("x", "h", bottom="b", data=frame)

    bare, bare_ax = plt.subplots()
    bare_ax.bar(CATEGORIES, SERIES_0)

    assert _registered(fig) == ["bar"]
    assert _emitted(fig) == _emitted(bare)


def test_a_baseline_named_in_data_still_stacks() -> None:
    """``bottom="col", data=df`` names a column, which is not a zero.

    The zero test must not swallow a string: a name that cannot be read as
    numbers is a baseline like any other, and the call stacks.
    """
    frame = pd.DataFrame({"x": CATEGORIES, "h": SERIES_1, "b": SERIES_0})
    fig, ax = plt.subplots()
    ax.bar("x", "h", bottom="b", data=frame)

    assert _registered(fig) == ["stacked_bar"]


def test_barh_height_keyword_reads_dodged_like_the_positional_spelling() -> None:
    """The thickness of a horizontal bar is its ``height``.

    Read as ``width`` -- the bar's length on ``barh`` -- two side-by-side
    horizontal bars compared the wrong number and came out as two plain
    layers, while the same chart drawn vertically, or with the thickness
    passed positionally, reads as dodged.
    """
    positions = np.arange(len(CATEGORIES))

    horizontal, ax = plt.subplots()
    ax.barh(positions + 0.2, SERIES_0, height=0.4, label="s0")
    ax.barh(positions - 0.2, SERIES_1, height=0.4, label="s1")

    vertical, ax = plt.subplots()
    ax.bar(positions + 0.2, SERIES_0, width=0.4, label="s0")
    ax.bar(positions - 0.2, SERIES_1, width=0.4, label="s1")

    assert _registered(vertical) == ["dodged_bar", "dodged_bar"]
    assert _registered(horizontal) == _registered(vertical)
    assert [kind for kind, _ in _emitted(horizontal)] == ["dodged_bar"]


def test_a_baseline_with_a_gap_is_read_from_its_measured_values() -> None:
    """NaN is not equal to itself, which must not make a baseline vary.

    A baseline of one value with a gap in it is still an offset, and one
    that is NaN throughout draws no bar at all, so neither says anything
    about stacking.
    """
    assert _is_constant_baseline([5.0, np.nan, 5.0])
    assert _is_constant_baseline([np.nan, np.nan])
    assert not _is_constant_baseline([5.0, np.nan, 6.0])


@pytest.mark.parametrize(
    "baseline",
    [
        pytest.param(5, id="int"),
        pytest.param(5.0, id="float"),
        pytest.param([5, 5, 5], id="list"),
        pytest.param(np.full(len(CATEGORIES), 5.0), id="array"),
    ],
)
def test_a_constant_baseline_on_bare_axes_is_a_plain_bar(baseline) -> None:
    """The reproduction of #760: ``bottom=5`` with nothing beneath it.

    Every bar is drawn from 5 upward, which is an axis offset and not a
    second series, yet it registered a one-group stack whose only group
    wore matplotlib's container label. Each constant spelling has to read
    exactly as the bare call does: the same type, and the category names
    as labels rather than ``_container0``.
    """
    fig, ax = plt.subplots()
    ax.bar(CATEGORIES, SERIES_0, bottom=baseline)

    bare, bare_ax = plt.subplots()
    bare_ax.bar(CATEGORIES, SERIES_0)

    assert _registered(fig) == ["bar"]
    assert _emitted(fig) == _emitted(bare)
    (kind, data), = _emitted(fig)
    assert kind == "bar"
    assert [point["x"] for point in data] == CATEGORIES


def test_a_constant_left_on_bare_axes_reads_barh_as_a_plain_bar() -> None:
    """``left=5`` is ``barh``'s spelling of the same offset."""
    fig, ax = plt.subplots()
    ax.barh(CATEGORIES, SERIES_0, left=5)

    bare, bare_ax = plt.subplots()
    bare_ax.barh(CATEGORIES, SERIES_0)

    assert _registered(fig) == ["bar"]
    assert _emitted(fig) == _emitted(bare)
    (kind, data), = _emitted(fig)
    assert kind == "bar"
    assert [point["y"] for point in data] == CATEGORIES


@pytest.mark.parametrize(
    ("method", "baseline_name"),
    [
        pytest.param("bar", "bottom", id="bar"),
        pytest.param("barh", "left", id="barh"),
    ],
)
def test_a_constant_baseline_over_an_existing_layer_still_stacks(
    method: str, baseline_name: str
) -> None:
    """A constant offset on a second series is a stack, because one is beneath.

    ``ax.bar(x, a); ax.bar(x, b, bottom=5)`` is how a matplotlib user writes
    a second series sitting on a first of constant height. The baseline is
    constant, but a bar container already stands on the axes, so the rule
    that reads a lone ``bottom=5`` as an offset must not reach this call.
    """
    fig, ax = plt.subplots()
    getattr(ax, method)(CATEGORIES, np.full(len(CATEGORIES), 5.0), label="s0")
    getattr(ax, method)(CATEGORIES, SERIES_1, label="s1", **{baseline_name: 5})

    assert _registered(fig) == ["bar", "stacked_bar"]
    assert [kind for kind, _ in _emitted(fig)] == ["stacked_bar"]
    assert len(_emitted(fig)[0][1]) == 2, "both series are groups of the stack"
