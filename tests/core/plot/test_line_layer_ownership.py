"""A line layer described lines its own calls never drew (#440).

``MultiLinePlot._series()`` swept every data-space line on the axes. That is
right while nothing else draws lines, and box plots, violins and boxen plots
all do -- matplotlib renders whiskers, caps and medians as ``Line2D`` objects
in data space. So one reference line over any of them made the line layer
describe the *box's own geometry* as a chart.

Measured, with a single ``ax.plot([0, 1], [0.5, 0.5])`` over each:

    ax.plot + sns.boxplot     line layer: 11 series   (should be 1)
    ax.plot + sns.violinplot  line layer:  7 series
    ax.plot + sns.boxenplot   line layer:  3 series

Every extra series is two points long, because a whisker is a segment. A
reader switching to the line layer of that chart was walked through ten
two-sample "series" whose values are whisker endpoints and cap positions,
announced exactly as data would be, with nothing saying otherwise. Drawing a
threshold on a box plot is ordinary: a target, a control limit, a prior year's
median.

The layer now keeps the lines its own calls drew, which is the mechanism #380
introduced for ``Axes.bar`` and #426 extended to scatter. What made it cheap
here is that the internal context already separates the two: a companion chart
draws its lines inside its own patch's context, so the line patch declines
them, while a user's ``ax.plot`` arrives with the context clear.

The sweep was doing one thing worth keeping -- letting several ``ax.plot()``
calls form one multi-series layer -- so the lines accumulate on the axes and
the list is handed over by reference. Both halves are tested below; the
accumulation cases are the ones a naive "pass this call's lines" fix breaks.
"""

from __future__ import annotations

import numpy as np
import pytest

sns = pytest.importorskip("seaborn")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "g": np.repeat(["a", "b"], 50),
            "v": np.random.default_rng(0).normal(size=100),
        }
    )


def line_series(ax) -> list[list[dict]]:
    """Every series of every line-family layer on the axes."""
    ax = getattr(ax, "axes", ax)
    maidr = FigureManager.get_maidr(ax.get_figure())
    return [
        series
        for plot in maidr._plots
        if plot.type.value in ("line", "step")
        for series in plot.schema["data"]
    ]


@pytest.mark.parametrize("companion", ["boxplot", "violinplot", "boxenplot"])
class TestAReferenceLineOverADistributionChart:
    @staticmethod
    def _axes(companion: str):
        _, ax = plt.subplots()
        ax.plot([0, 1], [0.5, 0.5], color="grey")
        getattr(sns, companion)(frame(), x="g", y="v", ax=ax)
        return ax

    def test_the_layer_holds_only_the_line_that_was_plotted(self, companion):
        assert len(line_series(self._axes(companion))) == 1

    def test_it_is_the_line_that_was_plotted(self, companion):
        # Stronger than the count: a layer of one series could still be the
        # wrong one. Whiskers and caps are two-point segments too, so the
        # count alone would not tell them apart from the reference line.
        #
        # Identified by its value. The threshold is flat at 0.5 across both
        # ends, where a whisker runs between two different quantiles and a cap
        # sits at one -- neither is 0.5 twice for this data.
        #
        # The x arrives as `a` and `b` rather than 0 and 1 because the
        # companion chart makes the axis categorical, and #353's label
        # recovery then names the positions the line was drawn at. That is the
        # right reading of a line spanning category a to category b, and it is
        # asserted rather than sidestepped so a regression there shows up too.
        series = line_series(self._axes(companion))[0]

        assert [(point["x"], point["y"]) for point in series] == [
            ("a", 0.5),
            ("b", 0.5),
        ]

    def test_the_companion_chart_still_reads(self, companion):
        # The guard. Suppressing the box's lines from the *line* layer must
        # not take them out of the chart they belong to -- "no phantom
        # series" would otherwise be satisfiable by reading nothing at all.
        ax = self._axes(companion)
        maidr = FigureManager.get_maidr(ax.get_figure())
        kinds = {plot.type.value for plot in maidr._plots}

        assert kinds & {"box", "violin_box", "violin_kde", "boxen"}


@pytest.mark.parametrize("companion", ["boxplot", "violinplot", "boxenplot"])
class TestNeitherCallNamesItsAxes:
    """The idiom that leaves ``ax=`` off both calls, which is the common one.

    ``wrap_seaborn`` wraps ``seaborn.lineplot`` as a module-level function, so
    the wrapper's ``instance`` is always None; with no ``ax=`` either, there
    was nothing to take a before-snapshot of and every line on the axes looked
    newly drawn. Measured on ``sns.boxplot`` then ``sns.lineplot``, neither
    passing ``ax=``: 11 series again, values being whisker endpoints -- the
    defect this file exists to close, left intact for the more common spelling
    of it.

    Parametrized over all three companions rather than just the box plot,
    since the snapshot is what fails and it does not know which chart drew
    what.
    """

    @staticmethod
    def _figure(companion: str):
        plt.figure()
        getattr(sns, companion)(data=frame(), x="g", y="v")
        sns.lineplot(
            data=pd.DataFrame({"g": ["a", "b"], "v": [0.5, 0.4]}), x="g", y="v"
        )
        return plt.gca()

    def test_the_layer_holds_only_the_line_that_was_plotted(self, companion):
        assert len(line_series(self._figure(companion))) == 1

    def test_it_is_the_summary_line(self, companion):
        series = line_series(self._figure(companion))[0]

        assert [(point["x"], point["y"]) for point in series] == [
            ("a", 0.5),
            ("b", 0.4),
        ]


class TestSeveralCallsAreStillOneLayer:
    """What the sweep was right about, and the half a naive fix breaks.

    Passing only the registering call's lines would leave every later
    ``ax.plot()`` out of the chart, which trades one wrong reading for a
    missing one. The lines accumulate on the axes instead, and the list is
    handed over by reference so extraction sees additions made after the
    layer was registered.
    """

    def test_two_calls_make_two_series(self):
        _, ax = plt.subplots()
        ax.plot([0, 1], [1, 2])
        ax.plot([0, 1], [3, 4])

        assert len(line_series(ax)) == 2

    def test_a_third_call_is_not_lost(self):
        _, ax = plt.subplots()
        ax.plot([0, 1], [1, 2])
        ax.plot([0, 1], [3, 4])
        ax.plot([0, 1], [5, 6])

        assert len(line_series(ax)) == 3

    def test_one_call_drawing_several_series_keeps_them_all(self):
        # `ax.plot` takes repeated x/y pairs and returns a line per pair, so
        # this is one call and three lines rather than three calls.
        _, ax = plt.subplots()
        ax.plot([0, 1], [1, 2], [0, 1], [3, 4], [0, 1], [5, 6])

        assert len(line_series(ax)) == 3

    def test_every_series_keeps_its_own_values(self):
        _, ax = plt.subplots()
        ax.plot([0, 1], [1, 2])
        ax.plot([0, 1], [3, 4])

        assert [[point["y"] for point in s] for s in line_series(ax)] == [
            [1.0, 2.0],
            [3.0, 4.0],
        ]


@pytest.mark.parametrize("companion", ["boxplot", "violinplot", "boxenplot"])
class TestAStepChartSharingItsAxes:
    """The same sweep, one level down, in ``maidr/util/step_utils.py``.

    Narrowing ``_series()`` fixed which lines a layer *describes*. It left two
    reads of the axes behind, and both decide things about a step chart:

    ``is_step_layer`` (classification, at registration)
        A step chart drawn *after* a companion saw the box's whiskers in the
        mix, concluded the axes was not piecewise-constant, and registered as
        ``line``. That is not a cosmetic mislabel -- ``line`` builds
        ``MultiLinePlot`` rather than ``StepPlot``, so the ordinal level names
        go with it, and a hypnogram announces ``3`` where it should say
        ``REM``.

    ``resolve_step_direction`` (the field, at render)
        Read at ``save_html()`` time, so a companion drawn *after* the step
        line was enough: the step line was unambiguous, box geometry disagreed
        with it, and ``stepDirection`` was silently dropped.

    Measured, per ordering::

        sns.boxplot(...); ax.step(...)   type "line"   stepDirection n/a
        ax.step(...); sns.boxplot(...)   type "step"   stepDirection absent

    Both orderings are covered because they fail through different functions.
    """

    @staticmethod
    def _levels(ax):
        # A hypnogram, which is what makes the classification loss legible:
        # the level names only exist on a StepPlot.
        ax.set_yticks([1, 2, 3], labels=["N3", "N2", "REM"])

    def _companion_first(self, companion: str):
        _, ax = plt.subplots()
        getattr(sns, companion)(frame(), x="g", y="v", ax=ax)
        ax.step([0, 1, 2], [1, 2, 3], where="post")
        self._levels(ax)
        return ax

    def _step_first(self, companion: str):
        _, ax = plt.subplots()
        ax.step([0, 1, 2], [1, 2, 3], where="post")
        getattr(sns, companion)(frame(), x="g", y="v", ax=ax)
        self._levels(ax)
        return ax

    @staticmethod
    def _step_layer(ax):
        maidr = FigureManager.get_maidr(ax.get_figure())
        steps = [plot for plot in maidr._plots if plot.type.value == "step"]

        assert len(steps) == 1, [plot.type.value for plot in maidr._plots]
        return steps[0].schema

    def test_a_step_drawn_after_a_companion_is_still_a_step(self, companion):
        assert self._step_layer(self._companion_first(companion))

    def test_it_keeps_its_direction_when_drawn_after(self, companion):
        assert self._step_layer(self._companion_first(companion))["stepDirection"] == (
            "hv"
        )

    def test_it_keeps_its_level_names_when_drawn_after(self, companion):
        # What the misclassification actually cost. `MultiLinePlot` has no
        # `_attach_level_labels`, so a chart typed `line` announces the stage
        # code and never the stage.
        schema = self._step_layer(self._companion_first(companion))

        assert [point["label"] for point in schema["data"][0]] == ["N3", "N2", "REM"]

    def test_a_companion_drawn_after_does_not_take_the_direction(self, companion):
        assert self._step_layer(self._step_first(companion))["stepDirection"] == "hv"

    def test_the_step_layer_holds_only_its_own_line(self, companion):
        # The guard against fixing the type by widening what it reads.
        #
        # The first two x arrive as `a` and `b` for the reason the reference
        # line above does: the companion makes the axis categorical and #353's
        # label recovery names the positions the step was drawn at. The third
        # sits past the last category, where there is no tick to name, so it
        # stays numeric.
        schema = self._step_layer(self._companion_first(companion))

        assert [(point["x"], point["y"]) for point in schema["data"][0]] == [
            ("a", 1.0),
            ("b", 2.0),
            (2.0, 3.0),
        ]


class TestWhatMustNotChange:
    def test_a_plain_line_chart_is_unaffected(self):
        _, ax = plt.subplots()
        ax.plot([1, 2, 3], [10, 20, 30])

        assert [(p["x"], p["y"]) for p in line_series(ax)[0]] == [
            (1.0, 10.0),
            (2.0, 20.0),
            (3.0, 30.0),
        ]

    def test_seaborn_lineplot_still_registers(self):
        # `sns.lineplot` returns an Axes rather than its lines, so it takes
        # the before/after path rather than reading the return value.
        _, ax = plt.subplots()
        sns.lineplot(frame(), x="g", y="v", ax=ax)

        assert len(line_series(ax)) == 1

    def test_a_step_chart_is_still_a_step_chart(self):
        # The type is decided from the drawn artists, and this change moves
        # which artists the layer holds -- so the classification is pinned.
        _, ax = plt.subplots()
        ax.step([1, 2, 3], [10, 20, 30])
        maidr = FigureManager.get_maidr(ax.get_figure())

        assert [plot.type.value for plot in maidr._plots] == ["step"]
