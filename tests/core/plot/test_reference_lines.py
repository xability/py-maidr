"""A reference line was announced as data at coordinates that do not exist (#434).

``ax.axhline`` and ``ax.axvline`` blend the *axes* transform on one axis with
the data transform on the other, so their stored coordinates run 0 to 1 and
describe the extent of the axes rather than any value. Measured on
``ax.plot([10, 20, 30], [1, 2, 3])`` followed by ``ax.axhline(2)``::

    [{"x": 10.0, ...}, {"x": 20.0, ...}, {"x": 30.0, ...}]
    [{"x":  0.0, "y": 2.0}, {"x": 1.0, "y": 2.0}]          <- the axhline

The chart's x runs 10 to 30 and the reference line was announced at 0 and 1 —
a confident reading of a series that is not there, with nothing to say its
numbers are in a different space from every other number in the chart.

Two independent defects produced it, which is why the fix is in two places and
why filtering alone was not enough:

* a **real** layer's ``_series()`` sweeps every line on the axes, so it picked
  the reference line up as an extra series;
* ``sns.residplot`` registered a line layer with **no artist of its own**.
  Traced: ``seaborn.utils._default_color`` plots a throwaway artist to resolve
  a default colour, and the returned line is in data space with an empty
  ``get_xydata()`` — the #373 mechanism. That layer then fell back to sweeping
  the axes, where the only line is the ``axhline``.

Fixing only the first turns a residual plot's wrong series into a fatal
``ExtractionError``, because the layer is left with nothing to extract. Both
halves are needed, and both are pinned below.
"""

from __future__ import annotations

import numpy as np
import pytest

sns = pytest.importorskip("seaborn")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def layers(ax) -> list:
    return FigureManager.get_maidr(ax.get_figure())._plots


def series_of(ax) -> list[list[dict]]:
    line_layers = [
        plot
        for plot in layers(ax)
        if str(plot.type).endswith("LINE") or str(plot.type).endswith("STEP")
    ]
    assert len(line_layers) == 1, f"expected one line layer, got {len(line_layers)}"
    return line_layers[0].schema["data"]


class TestAReferenceLineBesideRealData:
    def test_axhline_is_not_a_second_series(self):
        _, ax = plt.subplots()
        ax.plot([10, 20, 30], [1, 2, 3])
        ax.axhline(2)

        assert len(series_of(ax)) == 1

    def test_the_real_series_is_untouched(self):
        _, ax = plt.subplots()
        ax.plot([10, 20, 30], [1, 2, 3])
        ax.axhline(2)

        assert [(point["x"], point["y"]) for point in series_of(ax)[0]] == [
            (10.0, 1.0),
            (20.0, 2.0),
            (30.0, 3.0),
        ]

    def test_no_announced_x_falls_outside_the_data(self):
        # The defect's signature, stated as what a reader would notice: the
        # reference line was announced at x = 0 and x = 1 on a chart whose x
        # begins at 10.
        _, ax = plt.subplots()
        ax.plot([10, 20, 30], [1, 2, 3])
        ax.axhline(2)
        xs = [point["x"] for series in series_of(ax) for point in series]

        assert min(xs) >= 10.0

    def test_axvline_is_covered_too(self):
        # The mirror image: `axvline` blends the other way round, so its y
        # values are the ones in axes space.
        _, ax = plt.subplots()
        ax.plot([10, 20, 30], [1, 2, 3])
        ax.axvline(20)
        ys = [point["y"] for series in series_of(ax) for point in series]

        assert len(series_of(ax)) == 1
        assert min(ys) >= 1.0

    def test_a_step_chart_is_covered_by_the_same_rule(self):
        _, ax = plt.subplots()
        ax.step([1, 2, 3], [1, 2, 3])
        ax.axhline(2)

        assert len(series_of(ax)) == 1


class TestALayerWithNoArtistOfItsOwn:
    def test_residplot_does_not_register_a_line_layer(self):
        # `residplot` draws a scatter and a zero reference line. The line layer
        # it used to register came from the colour probe, not from anything the
        # reader can see.
        rng = np.random.default_rng(0)
        ax = sns.residplot(x=rng.normal(size=40), y=rng.normal(size=40))

        assert [str(plot.type) for plot in layers(ax)] == ["PlotType.SCATTER"]

    def test_it_renders_rather_than_raising(self):
        # Filtering the sweep without this half leaves the layer with nothing
        # to extract, and `_extract_plot_data` raises — which is fatal to the
        # whole figure. Trading a wrong series for a dead chart is not a fix,
        # so this is the case that says the two halves belong together.
        rng = np.random.default_rng(0)
        ax = sns.residplot(x=rng.normal(size=40), y=rng.normal(size=40))

        FigureManager.get_maidr(ax.get_figure())._flatten_maidr()


class TestWhatMustNotChange:
    def test_a_flat_data_line_is_still_data(self):
        # Asked about the transform, never the values. A genuinely flat series
        # looks exactly like a reference line by shape, and a shape test would
        # have thrown it away.
        _, ax = plt.subplots()
        ax.plot([1, 2], [5, 5])

        assert [(point["x"], point["y"]) for point in series_of(ax)[0]] == [
            (1.0, 5.0),
            (2.0, 5.0),
        ]

    def test_a_plain_line_chart_is_unchanged(self):
        _, ax = plt.subplots()
        ax.plot([10, 20, 30], [1, 2, 3])

        assert len(series_of(ax)) == 1
        assert len(series_of(ax)[0]) == 3

    def test_seaborn_lineplot_still_registers(self):
        ax = sns.lineplot(x=[1, 2, 3], y=[4, 5, 6])

        assert [str(plot.type) for plot in layers(ax)] == ["PlotType.LINE"]

    def test_regplot_keeps_both_of_its_layers(self):
        ax = sns.regplot(x=[1, 2, 3, 4], y=[1, 3, 2, 4])

        assert [str(plot.type) for plot in layers(ax)] == [
            "PlotType.SCATTER",
            "PlotType.SMOOTH",
        ]
