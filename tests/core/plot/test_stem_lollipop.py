"""A stem plot is read as the lollipop it draws, baseline excluded."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pytest

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.figure_manager import FigureManager
from maidr.exception import UnsupportedPlotError


def _layers(fig) -> list:
    return FigureManager.get_maidr(fig).plots


def test_a_stem_plot_is_one_lollipop_layer() -> None:
    fig, ax = plt.subplots()
    ax.stem([1, 2, 3], [4, 9, 2])

    layers = _layers(fig)
    assert [layer.type for layer in layers] == [PlotType.LOLLIPOP]

    plt.close(fig)


def test_the_marks_are_the_data() -> None:
    fig, ax = plt.subplots()
    ax.stem([1, 2, 3], [4, 9, 2])

    schema = _layers(fig)[0].schema
    assert schema[MaidrKey.DATA] == [
        {MaidrKey.X: 1.0, MaidrKey.Y: 4.0},
        {MaidrKey.X: 2.0, MaidrKey.Y: 9.0},
        {MaidrKey.X: 3.0, MaidrKey.Y: 2.0},
    ]

    plt.close(fig)


def test_the_baseline_is_not_announced_as_a_series() -> None:
    """The defect #574 was filed for: a flat two-point line at the bottom.

    Asserted on the *shape* of the payload rather than by looking for the
    baseline's coordinates, because a lollipop's data is a flat list -- a
    second series could only arrive by the layer becoming a line again.
    """
    fig, ax = plt.subplots()
    ax.stem([1, 2, 3], [4, 9, 2])

    data = _layers(fig)[0].schema[MaidrKey.DATA]
    assert all(isinstance(entry, dict) for entry in data)
    assert len(data) == 3

    # The baseline sits at y=0 across the whole chart; no announced mark does.
    assert {entry[MaidrKey.Y] for entry in data} == {4.0, 9.0, 2.0}

    plt.close(fig)


def test_the_baseline_a_caller_moved_is_not_announced_either() -> None:
    """`bottom=` moves the baseline onto the values' own scale."""
    fig, ax = plt.subplots()
    ax.stem([1, 2, 3], [4, 9, 2], bottom=3)

    data = _layers(fig)[0].schema[MaidrKey.DATA]
    assert len(data) == 3
    assert 3.0 not in {entry[MaidrKey.Y] for entry in data}

    plt.close(fig)


@pytest.mark.parametrize(
    ("kwargs", "orientation", "expected"),
    [
        (
            {},
            "vert",
            [(1.0, 4.0), (2.0, 9.0), (3.0, 2.0)],
        ),
        (
            {"orientation": "horizontal"},
            "horz",
            # The bar family puts the magnitude in `x` when horizontal --
            # measured off `ax.barh`, which emits {x: 4.0, y: "a"}.
            [(4.0, 1.0), (9.0, 2.0), (2.0, 3.0)],
        ),
    ],
)
def test_the_orientation_is_declared_and_the_payload_matches_it(
    kwargs: dict, orientation: str, expected: list
) -> None:
    fig, ax = plt.subplots()
    ax.stem([1, 2, 3], [4, 9, 2], **kwargs)

    schema = _layers(fig)[0].schema
    assert schema[MaidrKey.ORIENTATION] == orientation
    assert [
        (entry[MaidrKey.X], entry[MaidrKey.Y]) for entry in schema[MaidrKey.DATA]
    ] == expected

    plt.close(fig)


def test_a_mark_matplotlib_could_not_place_is_skipped_with_its_selector() -> None:
    """Four values, one of them non-finite, leave three marks and three
    elements -- and the third selector must address the third element, not
    the fourth."""
    fig, ax = plt.subplots()
    ax.stem([1, 2, 3, 4], [4.0, float("nan"), 2.0, 7.0])

    schema = _layers(fig)[0].schema
    data = schema[MaidrKey.DATA]
    selectors = schema[MaidrKey.SELECTOR]

    assert [entry[MaidrKey.X] for entry in data] == [1.0, 3.0, 4.0]
    assert len(selectors) == 3
    assert selectors[-1].endswith("use:nth-of-type(3)")

    plt.close(fig)


def test_every_mark_has_a_selector_of_its_own() -> None:
    fig, ax = plt.subplots()
    ax.stem([1, 2, 3], [4, 9, 2])

    schema = _layers(fig)[0].schema
    selectors = schema[MaidrKey.SELECTOR]

    assert len(selectors) == len(schema[MaidrKey.DATA])
    assert len(set(selectors)) == len(selectors)
    assert all(selector.startswith("g[id='maidr-") for selector in selectors)

    plt.close(fig)


def test_a_stem_plot_registers_no_line_layer() -> None:
    """The marks are not joined; announcing a line would say they are."""
    fig, ax = plt.subplots()
    ax.stem([1, 2, 3], [4, 9, 2])

    assert PlotType.LINE not in {layer.type for layer in _layers(fig)}

    plt.close(fig)


def test_a_line_drawn_beside_a_stem_is_still_read() -> None:
    """Drawing the stem quietly must not silence the caller's own plot."""
    fig, ax = plt.subplots()
    ax.stem([1, 2, 3], [4, 9, 2])
    ax.plot([1, 2, 3], [1, 2, 3])

    assert {layer.type for layer in _layers(fig)} == {
        PlotType.LOLLIPOP,
        PlotType.LINE,
    }

    plt.close(fig)


def test_a_line_drawn_before_a_stem_is_still_read() -> None:
    """The other draw order, because only one direction can be broken."""
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 2, 3])
    ax.stem([1, 2, 3], [4, 9, 2])

    assert {layer.type for layer in _layers(fig)} == {
        PlotType.LOLLIPOP,
        PlotType.LINE,
    }

    plt.close(fig)


def test_a_line_read_beside_a_stem_holds_only_its_own_points() -> None:
    """The line must not pick up the stem's marker or baseline artists."""
    fig, ax = plt.subplots()
    ax.stem([1, 2, 3], [4, 9, 2])
    ax.plot([1, 2, 3], [1, 2, 3])

    line = next(
        layer for layer in _layers(fig) if layer.type == PlotType.LINE
    )
    series = line.schema[MaidrKey.DATA]
    assert len(series) == 1
    assert [entry[MaidrKey.Y] for entry in series[0]] == [1.0, 2.0, 3.0]

    plt.close(fig)


def test_a_chart_with_nothing_drawable_registers_no_layer() -> None:
    """An empty layer is one a reader can walk into and find nothing (#421).

    Nothing registered means the figure has no `Maidr` at all, which is the
    same answer any unread chart gives -- so the chart falls back to a
    picture rather than shipping a layer with no points.
    """
    fig, ax = plt.subplots()
    ax.stem([1, 2], [float("nan"), float("nan")])

    with pytest.raises(UnsupportedPlotError):
        FigureManager.get_maidr(fig)

    plt.close(fig)


def test_the_chart_renders() -> None:
    import maidr

    fig, ax = plt.subplots()
    ax.stem([1, 2, 3], [4, 9, 2])

    assert len(maidr.render(fig)._repr_html_()) > 0

    plt.close(fig)


def test_the_selectors_address_elements_the_svg_actually_has() -> None:
    """The selector shape is measured against the drawing, not assumed."""
    import io
    import re

    fig, ax = plt.subplots()
    ax.stem([1, 2, 3], [4, 9, 2])

    schema = _layers(fig)[0].schema
    gid = re.search(r"g\[id='([^']+)'\]", schema[MaidrKey.SELECTOR][0]).group(1)

    buffer = io.StringIO()
    fig.savefig(buffer, format="svg")
    svg = buffer.getvalue()

    group = re.search(rf'<g id="{re.escape(gid)}".*?</g>\s*</g>', svg, re.S)
    assert group is not None
    assert group.group(0).count("<use") == 3

    plt.close(fig)


def test_a_single_mark_is_read_as_vertical() -> None:
    """A one-mark chart draws a baseline of zero length, so the orientation
    cannot be read off its slope; the default is what the caller did not
    override."""
    fig, ax = plt.subplots()
    ax.stem([1], [4])

    schema = _layers(fig)[0].schema
    assert schema[MaidrKey.ORIENTATION] == "vert"
    assert schema[MaidrKey.DATA] == [{MaidrKey.X: 1.0, MaidrKey.Y: 4.0}]

    plt.close(fig)


def test_the_marks_are_read_in_the_order_they_were_given() -> None:
    """Unlike an event plot's row, a stem is not sorted by matplotlib."""
    fig, ax = plt.subplots()
    ax.stem([3, 1, 2], [4, 9, 2])

    data = _layers(fig)[0].schema[MaidrKey.DATA]
    assert [entry[MaidrKey.X] for entry in data] == [3.0, 1.0, 2.0]

    plt.close(fig)


def test_the_layer_reads_a_numpy_series() -> None:
    fig, ax = plt.subplots()
    ax.stem(np.array([1, 2, 3]), np.array([4.0, 9.0, 2.0]))

    data = _layers(fig)[0].schema[MaidrKey.DATA]
    assert [entry[MaidrKey.Y] for entry in data] == [4.0, 9.0, 2.0]

    plt.close(fig)
