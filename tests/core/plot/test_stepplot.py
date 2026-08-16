"""Tests for step (stairs) plot support.

``matplotlib.axes.Axes.step`` is a thin wrapper that sets
``drawstyle="steps-<where>"`` and calls ``Axes.plot``, which maidr already
patches. These tests pin down the two things that follow from that: exactly
one layer is registered per call (never a STEP *and* a LINE), and the layer
type is decided by the drawstyle of the rendered artists rather than by which
function the user happened to call.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.core.plot.stepplot import StepPlot  # noqa: E402


#: A short hypnogram: numeric sleep-stage codes sampled every half hour.
STAGE_CODES = [0, 1, 2, 3, 4]
STAGE_NAMES = ["N3", "N2", "N1", "REM", "Awake"]
HYPNOGRAM_TIMES = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
HYPNOGRAM_STAGES = [4, 2, 1, 0, 3, 4]


def _stringify_keys(d: dict) -> dict:
    """Normalize MaidrKey/PlotType enum keys and values to plain strings."""
    out = {}
    for k, v in d.items():
        key = k.value if hasattr(k, "value") else k
        if isinstance(v, dict):
            out[key] = _stringify_keys(v)
        elif isinstance(v, list):
            out[key] = [
                _stringify_keys(i)
                if isinstance(i, dict)
                else [_stringify_keys(j) if isinstance(j, dict) else j for j in i]
                if isinstance(i, list)
                else i
                for i in v
            ]
        else:
            out[key] = v.value if hasattr(v, "value") else v
    return out


def _only_layer(fig) -> dict:
    """Assert the figure registered exactly one layer and return its schema."""
    maidr_obj = FigureManager.get_maidr(fig)
    assert len(maidr_obj._plots) == 1, (
        f"expected exactly one layer, got {[p.type for p in maidr_obj._plots]}"
    )
    return _stringify_keys(maidr_obj._plots[0].schema)


def _name_hypnogram_levels(ax) -> None:
    """Name the numeric stage codes the way a user would, after plotting."""
    ax.set_yticks(STAGE_CODES, labels=STAGE_NAMES)


class TestStepClassification:
    """One layer, typed ``step``, whichever entry point drew it."""

    def test_ax_step_registers_one_step_layer(self):
        fig, ax = plt.subplots()
        try:
            ax.step(HYPNOGRAM_TIMES, HYPNOGRAM_STAGES, where="post")
            schema = _only_layer(fig)

            assert schema["type"] == "step"
        finally:
            plt.close(fig)

    def test_ax_plot_with_step_drawstyle_registers_one_step_layer(self):
        fig, ax = plt.subplots()
        try:
            ax.plot(HYPNOGRAM_TIMES, HYPNOGRAM_STAGES, drawstyle="steps-post")
            schema = _only_layer(fig)

            assert schema["type"] == "step"
        finally:
            plt.close(fig)

    def test_seaborn_lineplot_with_step_drawstyle_registers_one_step_layer(self):
        fig, ax = plt.subplots()
        try:
            data = pd.DataFrame({"t": HYPNOGRAM_TIMES, "stage": HYPNOGRAM_STAGES})
            sns.lineplot(data=data, x="t", y="stage", drawstyle="steps-mid", ax=ax)
            schema = _only_layer(fig)

            assert schema["type"] == "step"
        finally:
            plt.close(fig)

    def test_plain_line_plot_is_still_a_line(self):
        # The regression that matters most: adding step detection must not
        # reclassify any ordinary line plot.
        fig, ax = plt.subplots()
        try:
            ax.plot([0, 1, 2, 3], [1, 4, 2, 3])
            schema = _only_layer(fig)

            assert schema["type"] == "line"
            assert "stepDirection" not in schema
        finally:
            plt.close(fig)

    def test_plain_seaborn_lineplot_is_still_a_line(self):
        fig, ax = plt.subplots()
        try:
            data = pd.DataFrame({"t": [0, 1, 2, 3], "v": [1, 4, 2, 3]})
            sns.lineplot(data=data, x="t", y="v", ax=ax)
            schema = _only_layer(fig)

            assert schema["type"] == "line"
        finally:
            plt.close(fig)

    def test_multiline_step_registers_one_layer_with_nested_series(self):
        fig, ax = plt.subplots()
        try:
            ax.step([0, 1, 2], [1, 2, 3], where="post")
            ax.step([0, 1, 2], [3, 2, 1], where="post")
            schema = _only_layer(fig)

            assert schema["type"] == "step"
            assert len(schema["data"]) == 2
        finally:
            plt.close(fig)


class TestStepDataShape:
    """Data stays nested per series and ``y`` stays numeric."""

    def test_data_is_nested_list_of_lists_of_dicts(self):
        fig, ax = plt.subplots()
        try:
            ax.step(HYPNOGRAM_TIMES, HYPNOGRAM_STAGES, where="post")
            data = _only_layer(fig)["data"]

            assert isinstance(data, list)
            assert len(data) == 1
            assert isinstance(data[0], list)
            assert all(isinstance(point, dict) for point in data[0])
            assert len(data[0]) == len(HYPNOGRAM_TIMES)
        finally:
            plt.close(fig)

    def test_y_stays_numeric_even_when_levels_are_named(self):
        # ``y`` drives sonification, braille and min/max on the JS side, so it
        # must not be replaced by the level name.
        fig, ax = plt.subplots()
        try:
            ax.step(HYPNOGRAM_TIMES, HYPNOGRAM_STAGES, where="post")
            _name_hypnogram_levels(ax)
            points = _only_layer(fig)["data"][0]

            assert [point["y"] for point in points] == [
                float(stage) for stage in HYPNOGRAM_STAGES
            ]
        finally:
            plt.close(fig)


class TestStepDirection:
    """``stepDirection`` maps from the matplotlib drawstyle."""

    @pytest.mark.parametrize(
        "where, expected",
        [("post", "hv"), ("pre", "vh"), ("mid", "mid")],
    )
    def test_where_maps_to_direction(self, where, expected):
        fig, ax = plt.subplots()
        try:
            ax.step([0, 1, 2], [1, 2, 3], where=where)
            schema = _only_layer(fig)

            assert schema["stepDirection"] == expected
        finally:
            plt.close(fig)

    def test_bare_steps_drawstyle_is_treated_as_pre(self):
        # matplotlib's bare "steps" is a legacy alias for "steps-pre"; the
        # ``ds`` kwarg alias must work too.
        fig, ax = plt.subplots()
        try:
            ax.plot([0, 1, 2], [1, 2, 3], ds="steps")
            schema = _only_layer(fig)

            assert schema["type"] == "step"
            assert schema["stepDirection"] == "vh"
        finally:
            plt.close(fig)

    def test_direction_omitted_when_series_disagree(self):
        # No single direction was authored, so none is claimed.
        fig, ax = plt.subplots()
        try:
            ax.step([0, 1, 2], [1, 2, 3], where="post")
            ax.step([0, 1, 2], [3, 2, 1], where="pre")
            schema = _only_layer(fig)

            assert schema["type"] == "step"
            assert "stepDirection" not in schema
        finally:
            plt.close(fig)


class TestStepLevelLabels:
    """The hypnogram feature: ordinal level names on each point."""

    def test_label_carries_sleep_stage_names(self):
        fig, ax = plt.subplots()
        try:
            ax.step(HYPNOGRAM_TIMES, HYPNOGRAM_STAGES, where="post")
            _name_hypnogram_levels(ax)
            points = _only_layer(fig)["data"][0]

            assert [point["label"] for point in points] == [
                "Awake",
                "N1",
                "N2",
                "N3",
                "REM",
                "Awake",
            ]
        finally:
            plt.close(fig)

    def test_boundary_levels_are_not_dropped(self):
        # ``LevelExtractorMixin.extract_level`` filters tick labels against
        # ``ax.dataLim``, which loses the outermost levels. StepPlot reads the
        # ticks directly so the top and bottom stages survive.
        fig, ax = plt.subplots()
        try:
            ax.step([0, 1, 2], [0, 2, 4], where="post")
            _name_hypnogram_levels(ax)
            points = _only_layer(fig)["data"][0]

            assert [point["label"] for point in points] == ["N3", "N1", "Awake"]
        finally:
            plt.close(fig)

    def test_labels_resolved_after_plotting(self):
        # Naming the levels only after ax.step() is the idiomatic order and
        # must still be picked up, because resolution happens at render time.
        fig, ax = plt.subplots()
        try:
            ax.step([0, 1], [0, 4], where="post")
            plot = FigureManager.get_maidr(fig)._plots[0]
            assert isinstance(plot, StepPlot)
            _name_hypnogram_levels(ax)
            points = _stringify_keys(plot.schema)["data"][0]

            assert [point["label"] for point in points] == ["N3", "Awake"]
        finally:
            plt.close(fig)

    def test_numeric_step_plot_emits_no_labels(self):
        # Auto tick labels only spell out their own position, so they carry no
        # ordinal information and must not be emitted as level names.
        fig, ax = plt.subplots()
        try:
            ax.step([0, 1, 2], [10, 20, 30], where="post")
            points = _only_layer(fig)["data"][0]

            assert all("label" not in point for point in points)
        finally:
            plt.close(fig)

    @pytest.mark.parametrize(
        "y_values, configure",
        [
            # Default ScalarFormatter factors out an offset, so the tick at
            # y = 1000000 is labelled "0.0". Labelling the point "0.0" would
            # announce a flatly wrong value.
            ([1000000, 1000002, 1000004], lambda ax: None),
            # Scientific notation rescales the same way: "1.00" at y = 1e6.
            (
                [1e6, 2e6, 3e6],
                lambda ax: ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0)),
            ),
            # A log axis typesets its ticks as mathtext; announcing the raw
            # LaTeX ("$\\mathdefault{10^{1}}$") is worse than announcing nothing.
            ([1, 10, 100], lambda ax: ax.set_yscale("log")),
        ],
    )
    def test_rescaled_numeric_axis_emits_no_labels(self, y_values, configure):
        fig, ax = plt.subplots()
        try:
            ax.step([0, 1, 2], y_values, where="post")
            configure(ax)
            points = _only_layer(fig)["data"][0]

            assert all("label" not in point for point in points), points
        finally:
            plt.close(fig)

    def test_point_off_a_named_tick_gets_no_label(self):
        fig, ax = plt.subplots()
        try:
            # 2.5 lies between the named ticks 2 and 3.
            ax.step([0, 1, 2], [4, 2.5, 0], where="post")
            _name_hypnogram_levels(ax)
            points = _only_layer(fig)["data"][0]

            assert points[0]["label"] == "Awake"
            assert "label" not in points[1]
            assert points[2]["label"] == "N3"
        finally:
            plt.close(fig)

    def test_named_levels_recovered_from_shared_y_sibling(self):
        # A faceted hypnogram commonly names the levels on the left panel only.
        fig, axs = plt.subplots(1, 2, sharey=True)
        try:
            axs[0].step([0, 1, 2], [4, 2, 0], where="post")
            axs[1].step([0, 1, 2], [0, 3, 4], where="post")
            axs[0].set_yticks(STAGE_CODES, labels=STAGE_NAMES)

            right = _stringify_keys(FigureManager.get_maidr(fig)._plots[1].schema)

            assert [point["label"] for point in right["data"][0]] == [
                "N3",
                "REM",
                "Awake",
            ]
        finally:
            plt.close(fig)


class TestStepPlotClass:
    """Unit-level checks on the reused MultiLinePlot machinery."""

    def test_step_plot_is_a_multiline_plot(self):
        from maidr.core.plot.lineplot import MultiLinePlot

        assert issubclass(StepPlot, MultiLinePlot)

    def test_step_plot_reports_step_type(self):
        fig, ax = plt.subplots()
        try:
            ax.step([0, 1, 2], [1, 2, 3], where="post")
            plot = FigureManager.get_maidr(fig)._plots[0]

            assert plot.type == PlotType.STEP
        finally:
            plt.close(fig)

    def test_selectors_are_reused_from_multiline_plot(self):
        fig, ax = plt.subplots()
        try:
            ax.step([0, 1, 2], [1, 2, 3], where="post")
            selectors = _only_layer(fig)["selectors"]

            assert isinstance(selectors, list)
            assert len(selectors) == 1
            assert selectors[0].startswith("g[id='maidr-")
        finally:
            plt.close(fig)

    def test_legend_title_still_populates_the_z_axis(self):
        fig, ax = plt.subplots()
        try:
            ax.step([0, 1, 2], [1, 2, 3], where="post", label="night 1")
            ax.step([0, 1, 2], [3, 2, 1], where="post", label="night 2")
            ax.legend(title="Night")
            axes = _only_layer(fig)["axes"]

            assert axes["z"]["label"] == "Night"
        finally:
            plt.close(fig)


class TestStepUtils:
    """Direct coverage for the helpers the classification rule is built on."""

    def test_data_bearing_lines_agrees_with_the_extractor(self):
        """
        Pin ``data_bearing_lines`` to ``MultiLinePlot._extract_line_data``.

        The two apply the same "does this line carry data" predicate from
        opposite ends of the pipeline — one decides the layer's *type*, the
        other decides which lines become *series*. They are separate
        implementations, so if one starts counting a line the other skips,
        an axes could be classified as a step plot whose only step line is
        then dropped from the payload. This test fails the moment they
        disagree.
        """
        from maidr.util.step_utils import data_bearing_lines

        fig, ax = plt.subplots()
        try:
            ax.step([0, 1, 2], [1, 2, 3], where="post")
            ax.plot([], [])  # empty: carries no data, must be ignored by both
            ax.step([0, 1, 2], [3, 2, 1], where="post")

            counted = data_bearing_lines(ax.get_lines())
            extracted = _only_layer(fig)["data"]

            assert len(counted) == len(extracted) == 2
        finally:
            plt.close(fig)

    def test_an_empty_line_does_not_make_a_layer_a_step_plot(self):
        """A layer with no data-bearing line is not a step plot."""
        from maidr.util.step_utils import is_step_layer

        fig, ax = plt.subplots()
        try:
            ax.plot([], [])
            assert is_step_layer(ax.get_lines()) is False
        finally:
            plt.close(fig)

    def test_display_names_read_the_way_a_user_named_the_plot(self):
        """
        The fallback warning names plot types for users, not for the schema.

        ``PlotType.SCATTER.value`` is ``"point"``; someone who called
        ``ax.scatter`` should be told about "scatter".
        """
        assert PlotType.SCATTER.display_name == "scatter"
        assert PlotType.HEAT.display_name == "heatmap"
        assert PlotType.STEP.display_name == "step"
        # Both violin layers collapse to one user-facing name.
        assert PlotType.VIOLIN_KDE.display_name == PlotType.VIOLIN_BOX.display_name

class TestClassificationIsOrderDependent:
    """
    Classification happens once, on the first plotting call for an axes.

    That is the existing one-layer-per-axes model (``_maidr_plot_created``),
    not something step introduced — but it makes a mixed axes asymmetric, and
    these tests pin both directions so the asymmetry cannot drift unnoticed.
    """

    def test_line_drawn_first_keeps_the_axes_a_line(self):
        """The conservative direction: a plain line first wins outright."""
        fig, ax = plt.subplots()
        try:
            ax.plot([0, 1, 2], [1, 2, 3])
            ax.step([0, 1, 2], [3, 2, 1], where="post")
            layer = _only_layer(fig)

            assert layer["type"] == PlotType.LINE
            assert "stepDirection" not in layer
        finally:
            plt.close(fig)

    def test_step_drawn_first_keeps_the_axes_a_step_but_drops_the_direction(self):
        """
        The generous direction, pinned deliberately.

        A step line first classifies the axes ``step``; a plain line added
        afterwards does not re-open that decision, so its points ride in a
        layer typed ``step``. Downgrading at render time would be worse: it
        would strip the ordinal level names, and losing the stage names is a
        bigger accessibility loss than a slightly generous type.

        What the layer does give up is ``stepDirection`` —
        ``resolve_step_direction`` re-reads the artists at render time and
        finds them disagreeing, so no convention is ever claimed that the data
        does not support.
        """
        fig, ax = plt.subplots()
        try:
            ax.step([0, 1, 2], [1, 2, 3], where="post")
            ax.plot([0, 1, 2], [3, 2, 1])
            layer = _only_layer(fig)

            assert layer["type"] == PlotType.STEP
            assert "stepDirection" not in layer
        finally:
            plt.close(fig)
