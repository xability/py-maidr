"""Steps sharing a figure with other trace types, and across a subplot grid.

``test_plotly_step.py`` exercises step classification, direction mapping,
grouping and selector indexing thoroughly, but always on a single subplot
holding only scatter-family traces. Two combinations were left uncovered, and
both are ones where the failure mode is silent: a wrong ``nth-child`` index
does not raise, it highlights somebody else's element.

* A step beside ``bar`` or ``box`` traces. ``_extract_plots`` merges bars,
  lines, steps and boxes in one pass over the same trace group, each branch
  appending to ``self._plots`` and updating ``merged`` independently.
* Steps across a ``make_subplots`` grid, where ``position_of`` and the whole
  merge are computed per subplot group, so each cell should number from its
  own first scatter child.
"""

from __future__ import annotations

import pytest

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_maidr import PlotlyMaidr

pytest.importorskip("plotly")
import plotly.graph_objects as go  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402


def _step_kwargs(shape: str, name: str = "", **overrides) -> dict:
    """
    Build ``add_scatter`` keyword arguments for a staircase trace.

    Parameters
    ----------
    shape : str
        The ``line.shape`` to author.
    name : str, optional
        Trace name, emitted as the series' ``z``.
    **overrides
        Extra keyword arguments merged in, e.g. ``row`` and ``col``.

    Returns
    -------
    dict
        Keyword arguments for ``Figure.add_scatter``.
    """
    return {
        "mode": "lines",
        "x": [0, 1, 2],
        "y": [1, 2, 3],
        "line": {"shape": shape},
        **({"name": name} if name else {}),
        **overrides,
    }


def _layers(fig) -> list[dict]:
    """
    Render a figure through PlotlyMaidr and return its layer schemas.

    Parameters
    ----------
    fig : plotly.graph_objects.Figure
        The figure to export.

    Returns
    -------
    list of dict
        One schema per emitted layer, in emission order.
    """
    return [plot.schema for plot in PlotlyMaidr(fig)._plots]


def _only(layers: list[dict], predicate, description: str) -> dict:
    """
    Return the one layer matching ``predicate``.

    Fails with a readable assertion rather than ``StopIteration`` when nothing
    matches, so a broken grouping reports what was being looked for instead of
    an opaque iterator error several frames from the cause.

    Parameters
    ----------
    layers : list of dict
        The emitted layer schemas.
    predicate : callable
        Called with each layer; must match exactly one.
    description : str
        How to describe the sought layer in the failure message.

    Returns
    -------
    dict
        The single matching layer schema.
    """
    matches = [layer for layer in layers if predicate(layer)]
    assert len(matches) == 1, (
        f"expected exactly one layer {description}, found {len(matches)} "
        f"among types {[layer[MaidrKey.TYPE] for layer in layers]}"
    )
    return matches[0]


class TestAStepBesideBarTraces:
    """Bars occupy their own render layer and must not shift a step's index."""

    def test_a_bar_does_not_shift_the_step_selector(self):
        # `nth-child` counts within the subplot's `scatterlayer`. A bar is
        # drawn in the `barlayer`, so declaring it first must leave the step
        # as the first — and only — scatter child.
        fig = go.Figure()
        fig.add_bar(x=[0, 1, 2], y=[3, 2, 1], name="bars")
        fig.add_scatter(**_step_kwargs("hv", "stage"))

        layers = _layers(fig)
        step = _only(
            layers, lambda x: x[MaidrKey.TYPE] == PlotType.STEP, "of type step"
        )

        assert "nth-child(1)" in step[MaidrKey.SELECTOR][0]
        assert ".scatterlayer" in step[MaidrKey.SELECTOR][0]

    def test_both_layers_are_emitted(self):
        fig = go.Figure()
        fig.add_bar(x=[0, 1, 2], y=[3, 2, 1], name="bars")
        fig.add_scatter(**_step_kwargs("hv", "stage"))

        types = [layer[MaidrKey.TYPE] for layer in _layers(fig)]

        assert sorted(types) == sorted([PlotType.STEP, PlotType.BAR])

    def test_grouped_bars_coexist_with_two_step_conventions(self):
        # The bar branch and the step branch both run over the same trace
        # group and both update `merged`; neither may swallow the other's
        # traces. The two step conventions still split into a layer each.
        fig = go.Figure()
        fig.add_bar(x=[0, 1, 2], y=[3, 2, 1], name="bars a")
        fig.add_bar(x=[0, 1, 2], y=[1, 2, 3], name="bars b")
        fig.add_scatter(**_step_kwargs("hv", "hv step"))
        fig.add_scatter(**_step_kwargs("vh", "vh step"))

        layers = _layers(fig)
        steps = [x for x in layers if x[MaidrKey.TYPE] == PlotType.STEP]

        assert len(layers) == 3
        assert [x.get(MaidrKey.STEP_DIRECTION) for x in steps] == ["hv", "vh"]
        assert "nth-child(1)" in steps[0][MaidrKey.SELECTOR][0]
        assert "nth-child(2)" in steps[1][MaidrKey.SELECTOR][0]


class TestAStepBesideBoxTraces:
    """Boxes are not scatter-family, so they too leave the index alone."""

    def test_a_box_does_not_shift_the_step_selector(self):
        fig = go.Figure()
        fig.add_box(y=[1, 2, 3, 4, 5], name="box")
        fig.add_scatter(**_step_kwargs("hv", "stage"))

        layers = _layers(fig)
        step = _only(
            layers, lambda x: x[MaidrKey.TYPE] == PlotType.STEP, "of type step"
        )

        assert "nth-child(1)" in step[MaidrKey.SELECTOR][0]

    def test_merged_boxes_coexist_with_a_step(self):
        # Two boxes merge into one `PlotlyMultiBoxPlot`; the step branch runs
        # over the same group and must be unaffected by that merge.
        fig = go.Figure()
        fig.add_box(y=[1, 2, 3, 4, 5], name="box a")
        fig.add_box(y=[2, 3, 4, 5, 6], name="box b")
        fig.add_scatter(**_step_kwargs("vh", "stage"))

        layers = _layers(fig)
        types = [layer[MaidrKey.TYPE] for layer in layers]
        step = _only(
            layers, lambda x: x[MaidrKey.TYPE] == PlotType.STEP, "of type step"
        )

        assert PlotType.BOX in types
        assert step[MaidrKey.STEP_DIRECTION] == "vh"
        assert "nth-child(1)" in step[MaidrKey.SELECTOR][0]


class TestStepsAcrossASubplotGrid:
    """Each grid cell numbers from its own first scatter child."""

    def test_each_row_carries_its_own_subplot_prefix(self):
        fig = make_subplots(rows=2, cols=1)
        fig.add_scatter(**_step_kwargs("hv", "top", row=1, col=1))
        fig.add_scatter(**_step_kwargs("vh", "bottom", row=2, col=1))

        top, bottom = _layers(fig)

        assert top[MaidrKey.SELECTOR][0].startswith(".subplot.xy ")
        assert bottom[MaidrKey.SELECTOR][0].startswith(".subplot.x2y2 ")

    def test_each_cell_numbers_from_its_own_first_child(self):
        # The second row's trace is the figure's second trace overall, but the
        # first in its own subplot — so it must be `nth-child(1)`, not (2).
        fig = make_subplots(rows=2, cols=1)
        fig.add_scatter(**_step_kwargs("hv", "top", row=1, col=1))
        fig.add_scatter(**_step_kwargs("vh", "bottom", row=2, col=1))

        top, bottom = _layers(fig)

        assert "nth-child(1)" in top[MaidrKey.SELECTOR][0]
        assert "nth-child(1)" in bottom[MaidrKey.SELECTOR][0]

    def test_a_step_after_a_line_is_indexed_within_its_own_cell(self):
        # Row 1 holds a line then a step; row 2 holds a step alone. The row-1
        # step is the second scatter child of its cell, while the row-2 step
        # is still the first of its own.
        fig = make_subplots(rows=2, cols=1)
        fig.add_scatter(
            mode="lines", x=[0, 1, 2], y=[3, 2, 1], name="line", row=1, col=1
        )
        fig.add_scatter(**_step_kwargs("hv", "top step", row=1, col=1))
        fig.add_scatter(**_step_kwargs("hv", "bottom step", row=2, col=1))

        layers = _layers(fig)
        steps = [x for x in layers if x[MaidrKey.TYPE] == PlotType.STEP]
        line = _only(
            layers, lambda x: x[MaidrKey.TYPE] == PlotType.LINE, "of type line"
        )

        assert line[MaidrKey.SELECTOR][0].startswith(".subplot.xy ")
        assert "nth-child(1)" in line[MaidrKey.SELECTOR][0]

        top_step = _only(
            steps,
            lambda x: x[MaidrKey.SELECTOR][0].startswith(".subplot.xy "),
            "stepping in the first subplot",
        )
        bottom_step = _only(
            steps,
            lambda x: x[MaidrKey.SELECTOR][0].startswith(".subplot.x2y2 "),
            "stepping in the second subplot",
        )

        assert "nth-child(2)" in top_step[MaidrKey.SELECTOR][0]
        assert "nth-child(1)" in bottom_step[MaidrKey.SELECTOR][0]

    def test_grid_position_is_recorded_per_cell(self):
        fig = make_subplots(rows=2, cols=2)
        fig.add_scatter(**_step_kwargs("hv", "r1c1", row=1, col=1))
        fig.add_scatter(**_step_kwargs("hv", "r1c2", row=1, col=2))
        fig.add_scatter(**_step_kwargs("hv", "r2c1", row=2, col=1))
        fig.add_scatter(**_step_kwargs("hv", "r2c2", row=2, col=2))

        plots = PlotlyMaidr(fig)._plots

        assert {(p.row_index, p.col_index) for p in plots} == {
            (0, 0),
            (0, 1),
            (1, 0),
            (1, 1),
        }

    def test_every_cell_selector_is_distinct(self):
        # Four independent cells must produce four distinct selectors. Sharing
        # one would mean two layers highlighting the same element.
        fig = make_subplots(rows=2, cols=2)
        fig.add_scatter(**_step_kwargs("hv", "r1c1", row=1, col=1))
        fig.add_scatter(**_step_kwargs("hv", "r1c2", row=1, col=2))
        fig.add_scatter(**_step_kwargs("hv", "r2c1", row=2, col=1))
        fig.add_scatter(**_step_kwargs("hv", "r2c2", row=2, col=2))

        selectors = [layer[MaidrKey.SELECTOR][0] for layer in _layers(fig)]

        assert len(set(selectors)) == 4
