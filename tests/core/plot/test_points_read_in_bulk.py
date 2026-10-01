"""Scatter, strip and rug points are read in bulk, and read exactly as they did.

Four costs, each of them paid per point or per category where the answer was
the same every time:

* a ``hue=`` scatter converted every point's colour with ``to_rgba`` -- most
  of a 100k-point ``sns.scatterplot`` plotting call -- although a chart has a
  handful of distinct colours;
* a scatter on numeric axes built every point through ``_sample_on``, which
  with no slots and no names reduces to ``{x, y}`` as drawn;
* a strip plot read its category ticks once per collection, and it draws one
  collection per category, while snapping each point measured it against
  every category slot -- quadratic in the categories either way;
* a rug was read once by the patch, to decide whether to register it, and
  again by every layer it made.

Each is pinned here two ways: the new reading against the old one, kept as
the reference where it no longer runs, and a count of the work, so the
change is held without timing anything on a shared machine.
"""

from __future__ import annotations

import itertools
import json
import uuid
import warnings
from typing import Any, Callable, Iterator

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.core.plot import rugplot, scatterplot  # noqa: E402
from maidr.core.plot.scatterplot import ScatterPlot, rgba_rows  # noqa: E402
from maidr.util.mixin.extractor_mixin import LineExtractorMixin  # noqa: E402

#: A chart builder: draws one chart on the axes it is handed.
Draw = Callable[[Axes], None]


@pytest.fixture(autouse=True)
def _close_figures() -> Iterator[None]:
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


@pytest.fixture(autouse=True)
def _quiet_seaborn() -> Iterator[None]:
    """Keep seaborn's deprecation notes out of the output."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield


def _layers(fig: Figure, kind: PlotType) -> list:
    """
    The layers of one kind a figure registered.

    Parameters
    ----------
    fig : Figure
        The figure to read.
    kind : PlotType
        The layer type to keep.

    Returns
    -------
    list
        Those layers, in registration order.
    """
    return [plot for plot in FigureManager.get_maidr(fig).plots if plot.type is kind]


# --- colours --------------------------------------------------------------


@pytest.mark.parametrize(
    "rows",
    [
        pytest.param(
            np.array([[0.1, 0.2, 0.3, 1.0], [0.4, 0.5, 0.6, 1.0]] * 50), id="repeated"
        ),
        pytest.param(
            np.array(
                [[0.0, 0.5, 0.5, 1.0], [-0.0, 0.5, 0.5, 1.0], [0.0, 0.5, 0.5, 1.0]]
            ),
            id="signed-zero",
        ),
        pytest.param(
            np.array([[np.nan, 0.5, 0.5, 1.0], [0.2, 0.2, 0.2, 1.0]] * 3), id="nan"
        ),
        pytest.param(np.array([[0.3, 0.3, 0.3]] * 4), id="rgb"),
        pytest.param(np.array([[0.3, 0.3, 0.3, 0.5]]), id="one-row"),
        pytest.param(np.empty((0, 4)), id="empty"),
        pytest.param(np.array([0.3, 0.3, 0.3, 1.0]), id="one-dimensional"),
    ],
)
def test_colours_read_per_distinct_row_are_the_colours_read_per_row(
    rows: np.ndarray,
) -> None:
    got = rgba_rows(rows)
    want = [scatterplot._rgba(row) for row in rows]

    # Compared by repr, since a NaN is unequal even to itself.
    assert repr(got) == repr(want)
    # And as the grouping sees them, as set members: a colour holding a NaN
    # never matched another, so sharing one answer between two such rows
    # would have merged two colours into one.
    assert len(set(got)) == len(set(want))


def test_a_hue_scatter_converts_each_distinct_colour_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``to_rgba`` is tens of microseconds a call; a chart has few colours."""
    calls = []
    convert = scatterplot._rgba

    def counting(color: Any) -> Any:
        calls.append(1)
        return convert(color)

    monkeypatch.setattr(scatterplot, "_rgba", counting)
    rng = np.random.default_rng(0)

    sns.scatterplot(
        x=rng.normal(size=600),
        y=rng.normal(size=600),
        hue=rng.integers(0, 3, 600).astype(str),
    )

    # Three colours on the points, plus the legend's handles.
    assert 0 < len(calls) < 60, f"{len(calls)} conversions for 600 points"


# --- numeric scatter --------------------------------------------------------


def _plain(ax: Axes) -> None:
    """Plain floats."""
    rng = np.random.default_rng(1)
    ax.scatter(rng.normal(size=400), rng.normal(size=400))


def _gaps(ax: Axes) -> None:
    """NaN and inf offsets, which are not drawn."""
    rng = np.random.default_rng(2)
    x, y = rng.normal(size=120), rng.normal(size=120)
    x[[3, 4]] = np.nan
    y[10] = np.inf
    ax.scatter(x, y)


def _masked(ax: Axes) -> None:
    """A masked array, whose masked offsets arrive as NaN."""
    rng = np.random.default_rng(3)
    y = np.ma.masked_array(rng.normal(size=60), mask=np.arange(60) % 5 == 0)
    ax.scatter(np.arange(60.0), y)


def _signed_zeros(ax: Axes) -> None:
    """``-0.0`` on both axes, which has to survive as written."""
    ax.scatter([-0.0, 0.0, 1.0], [0.0, -0.0, 2.0])


def _integers(ax: Axes) -> None:
    """Integer offsets."""
    ax.scatter(np.arange(30), np.arange(30) % 7)


def _hue(ax: Axes) -> None:
    """``sns.scatterplot`` split by ``hue`` into one layer per group."""
    rng = np.random.default_rng(4)
    sns.scatterplot(
        x=rng.normal(size=300),
        y=rng.normal(size=300),
        hue=rng.integers(0, 3, 300).astype(str),
        ax=ax,
    )


def _two_labeled(ax: Axes) -> None:
    """Two labelled ``ax.scatter`` calls on one axes."""
    rng = np.random.default_rng(5)
    ax.scatter(rng.normal(size=50), rng.normal(size=50), label="p")
    ax.scatter(rng.normal(size=50), rng.normal(size=50), label="q")
    ax.legend()


SCATTERS: dict[str, Draw] = {
    "plain": _plain,
    "gaps": _gaps,
    "masked": _masked,
    "signed-zeros": _signed_zeros,
    "integers": _integers,
    "hue": _hue,
    "two-labeled": _two_labeled,
}


def _schemas(draw: Draw, kind: PlotType, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """
    Every layer of one kind, serialized whole, with ids minted in order.

    The selectors name each drawn mark by its place among the drawn points
    and the gid minted for its collection, so they are compared too: a
    reading that kept the points and lost their places would fail here.

    Parameters
    ----------
    draw : Draw
        The chart builder.
    kind : PlotType
        The layer type to read.
    monkeypatch : pytest.MonkeyPatch
        Installs the counting ``uuid4``.

    Returns
    -------
    list of str
        Each such layer's schema, as JSON.
    """
    counter = itertools.count()
    monkeypatch.setattr(uuid, "uuid4", lambda: uuid.UUID(int=next(counter)))
    fig, ax = plt.subplots()
    draw(ax)
    plots = _layers(fig, kind)
    assert plots, f"the chart registered no {kind.value} layer"
    return [json.dumps(plot.schema) for plot in plots]


@pytest.mark.parametrize("name", list(SCATTERS))
def test_a_scatter_reads_in_bulk_as_it_does_point_by_point(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    bulk_reads = []
    read = ScatterPlot._numeric_reading

    def counting(*args: Any) -> Any:
        bulk_reads.append(1)
        return read(*args)

    monkeypatch.setattr(ScatterPlot, "_numeric_reading", staticmethod(counting))
    bulk = _schemas(SCATTERS[name], PlotType.SCATTER, monkeypatch)
    # Without this the comparison below could pass with the bulk path never
    # taken: both runs would then read point by point.
    assert bulk_reads, "the bulk reading never ran, so nothing was compared"

    monkeypatch.setattr(
        ScatterPlot, "_numeric_reading", staticmethod(lambda *args: None)
    )
    per_point = _schemas(SCATTERS[name], PlotType.SCATTER, monkeypatch)

    assert bulk == per_point


# --- snapping to a category slot -------------------------------------------


def _nearest_by_min(coordinate: float, slots: list) -> float:
    """``_on_axis`` as it was: every slot measured."""
    if not slots:
        return coordinate
    return min(slots, key=lambda slot: abs(slot - coordinate))


def test_snapping_finds_the_slot_min_found() -> None:
    rng = np.random.default_rng(6)
    for _ in range(2000):
        slots = sorted(set(rng.integers(-20, 20, rng.integers(1, 12)).tolist()))
        slots = [float(slot) for slot in slots]
        coordinates = [
            *slots,
            *(a + (b - a) / 2 for a, b in zip(slots, slots[1:])),
            *rng.uniform(-30, 30, 8).tolist(),
            float("nan"),
            float("inf"),
            float("-inf"),
        ]
        for coordinate in coordinates:
            assert ScatterPlot._on_axis(coordinate, slots) == _nearest_by_min(
                coordinate, slots
            ) or (
                np.isnan(coordinate)
                and ScatterPlot._on_axis(coordinate, slots) == slots[0]
            )


def test_snapping_far_from_zero_keeps_the_first_of_tied_slots() -> None:
    # Large magnitudes round two neighbouring distances to the same float;
    # `min` then keeps the earlier slot, and so must the bisection.
    slots = [1e16, 1e16 + 2.0, 1e16 + 4.0]
    for coordinate in (1e16 + 1.0, 1e16 + 3.0, 1e16 + 2.0):
        assert ScatterPlot._on_axis(coordinate, slots) == _nearest_by_min(
            coordinate, slots
        )


# --- strip plots ------------------------------------------------------------


def _strip_frame(categories: int) -> pd.DataFrame:
    """Twenty observations in each of ``categories`` named groups."""
    rng = np.random.default_rng(7)
    return pd.DataFrame(
        {
            "g": np.repeat([f"c{index:02d}" for index in range(categories)], 20),
            "v": rng.normal(size=categories * 20),
        }
    )


def test_a_strip_plot_reads_its_ticks_once_per_axis_while_it_draws(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One collection per category used to mean one tick layout per category."""
    reads = []
    read = LineExtractorMixin._category_tick_labels

    def counting(ax: Axes, axis: str) -> dict:
        reads.append(axis)
        return read(ax, axis)

    monkeypatch.setattr(
        LineExtractorMixin, "_category_tick_labels", staticmethod(counting)
    )
    np.random.seed(0)

    sns.stripplot(_strip_frame(30), x="g", y="v")

    assert len(reads) <= 2, f"{len(reads)} tick reads for 30 categories"


def test_a_strip_plot_reads_as_it_did(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ticks shared between a call's collections name every layer as before."""

    def strip(ax: Axes) -> None:
        np.random.seed(0)
        sns.stripplot(_strip_frame(12), x="g", y="v", ax=ax)

    shared = _schemas(strip, PlotType.SCATTER, monkeypatch)

    from maidr.patch import stripplot

    category = stripplot._collection_category
    monkeypatch.setattr(
        stripplot,
        "_collection_category",
        lambda ax, collection, ticks=None: category(ax, collection, None),
    )

    assert _schemas(strip, PlotType.SCATTER, monkeypatch) == shared


# --- rugs ---------------------------------------------------------------------


def _read_rug_as_it_was(collection: Any) -> tuple[list[float], bool] | None:
    """``read_rug`` before it was vectorised, segment by segment."""
    if not isinstance(collection, LineCollection):
        return None
    segments = collection.get_segments()
    if not segments:
        return None
    ends = []
    for segment in segments:
        pair = np.asarray(segment, dtype=float)
        if pair.shape != (2, 2) or not np.all(np.isfinite(pair)):
            return None
        ends.append(pair)
    level_x = all(pair[0][0] == pair[1][0] for pair in ends)
    level_y = all(pair[0][1] == pair[1][1] for pair in ends)
    if level_x == level_y:
        return None
    axis = 0 if level_x else 1
    return [float(pair[0][axis]) for pair in ends], level_x


@pytest.mark.parametrize(
    "segments",
    [
        pytest.param([[[1.5, 0.0], [1.5, 0.1]], [[-0.0, 0.0], [-0.0, 0.1]]], id="x"),
        pytest.param([[[0.0, 2.0], [0.1, 2.0]], [[0.0, 3.0], [0.1, 3.0]]], id="y"),
        pytest.param([[[1.0, 0.0], [1.0, 0.0]]], id="zero-height"),
        pytest.param([[[0.0, 0.0], [1.0, 1.0]]], id="sloped"),
        pytest.param([[[np.nan, 0.0], [np.nan, 0.1]]], id="nan"),
        pytest.param([[[1.0, 0.0], [1.0, 0.1], [1.0, 0.2]]], id="three-ends"),
        pytest.param([], id="empty"),
    ],
)
def test_a_rug_reads_as_it_did_tick_by_tick(segments: list) -> None:
    collection = LineCollection(segments)

    assert rugplot.read_rug(collection) == _read_rug_as_it_was(collection)


@pytest.mark.parametrize("hue", [None, "g"], ids=["plain", "hue"])
def test_a_rug_is_read_once_however_many_layers_it_makes(
    hue: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The patch's reading is handed to every layer rather than redone."""
    reads = []
    read = rugplot.read_rug

    def counting(collection: Any) -> Any:
        reads.append(1)
        return read(collection)

    monkeypatch.setattr(rugplot, "read_rug", counting)
    from maidr.patch import rugplot as rug_patch

    monkeypatch.setattr(rug_patch, "read_rug", counting)
    rng = np.random.default_rng(8)
    frame = pd.DataFrame(
        {"v": rng.normal(size=90), "g": np.repeat(["a", "b", "c"], 30)}
    )

    fig, ax = plt.subplots()
    sns.rugplot(frame, x="v", hue=hue, ax=ax)

    assert _layers(fig, PlotType.RUG), "the rug registered no layer"
    assert len(reads) == 1, f"the rug was read {len(reads)} times"
