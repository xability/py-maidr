"""Kaplan-Meier curves are read as ``survival`` layers rather than as steps.

A survival curve read as a ``step`` layer announces the probability at each
time and loses what the figure is drawn for: which times are censored, the
confidence band, and the median survival maidr.js computes from the curve.
``maidr.plot_survival`` draws a curve from its numbers and registers it as a
``survival`` layer, and lifelines' ``plot_survival_function`` is read the
same way. The lifelines path is tested here against a stand-in fitter that
draws as lifelines does, so it runs without lifelines installed;
``tests/patch/test_survival_lifelines.py`` repeats it against the real one
where it is.
"""

from __future__ import annotations

import io
import json
import re

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
import wrapt
from lxml import etree

import maidr
from maidr.core.enum import MaidrKey, PlotType
from maidr.core.figure_manager import FigureManager
from maidr.patch.survival import kaplan_meier
from maidr.survival import survival_points

TIME = [0, 3, 6, 9, 12, 15, 18]
CONTROL = [1.0, 0.88, 0.71, 0.5, 0.41, 0.34, 0.29]
LOWER = [0.88, 0.76, 0.59, 0.38, 0.29, 0.22, 0.17]
UPPER = [1.0, 1.0, 0.83, 0.62, 0.53, 0.46, 0.41]


def layers(fig) -> list[dict]:
    """The layer schemas of a figure, in registration order."""
    return [plot.schema for plot in FigureManager.get_maidr(fig).plots]


def path_vertices(fig, selector: str) -> int:
    """How many vertices the path a selector names has in the figure's SVG."""
    buffer = io.BytesIO()
    fig.savefig(buffer, format="svg")
    root = etree.fromstring(buffer.getvalue())
    gid = re.search(r"g\[id='([^']+)'\] > path", selector).group(1)
    (group,) = root.xpath("//*[local-name()='g'][@id=$gid]", gid=gid)
    paths = [child for child in group if etree.QName(child).localname == "path"]
    assert len(paths) == 1
    return len(re.findall(r"[ML]", paths[0].get("d")))


# --- survival_points --------------------------------------------------------


def test_a_censoring_time_on_the_curve_flags_that_point():
    points = survival_points([0, 5, 10], [1.0, 0.8, 0.6], censored=[5])

    assert [p.get("censored", False) for p in points] == [False, True, False]
    assert len(points) == 3


def test_a_censoring_time_between_steps_is_a_point_at_the_survival_then():
    points = survival_points([0, 5, 10], [1.0, 0.8, 0.6], censored=[7, 12])

    assert [p["x"] for p in points] == [0, 5, 7, 10, 12]
    assert [p["y"] for p in points] == [1.0, 0.8, 0.8, 0.6, 0.6]
    assert [p.get("censored", False) for p in points] == [
        False,
        False,
        True,
        False,
        True,
    ]


def test_the_band_and_the_arm_ride_on_every_point():
    points = survival_points(
        [0, 5], [1.0, 0.8], lower=[0.9, 0.7], upper=[1.0, 0.9], censored=[6], name="A"
    )

    assert points[-1] == {
        "x": 6.0,
        "y": 0.8,
        "z": "A",
        "yMin": 0.7,
        "yMax": 0.9,
        "censored": True,
    }
    assert all(p["z"] == "A" for p in points)


def test_points_are_plain_json():
    points = survival_points(TIME, CONTROL, censored=[7.5], lower=LOWER, upper=UPPER)

    assert json.loads(json.dumps(points)) == points


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"time": [], "survival": []}, "at least one time"),
        ({"time": [0, 1], "survival": [1.0]}, "pair one to one"),
        ({"time": [0, 2, 1], "survival": [1, 0.9, 0.8]}, "strictly increasing"),
        ({"time": [0, 1], "survival": [1, np.nan]}, "NaN or infinite"),
        ({"time": [0, 1], "survival": [1, 0.9], "lower": [1, 0.8]}, "both"),
        ({"time": [1, 2], "survival": [1, 0.9], "censored": [0]}, "comes before"),
    ],
)
def test_malformed_curves_are_refused(kwargs, message):
    with pytest.raises(ValueError, match=message):
        survival_points(**kwargs)


# --- maidr.plot_survival ----------------------------------------------------


def test_plot_survival_registers_one_survival_layer_per_axes():
    fig, ax = plt.subplots()
    maidr.plot_survival(
        TIME, CONTROL, lower=LOWER, upper=UPPER, censored=[15], label="Control", ax=ax
    )
    maidr.plot_survival([0, 3, 6, 9, 15], [1.0, 0.95, 0.86, 0.79, 0.72], ax=ax)

    # The band, the ticks and the step line register nothing of their own.
    assert [plot.type for plot in FigureManager.get_maidr(fig).plots] == [
        PlotType.SURVIVAL
    ]
    (layer,) = layers(fig)
    assert layer[MaidrKey.TYPE] == "survival"
    assert len(layer[MaidrKey.DATA]) == 2
    assert len(layer[MaidrKey.SELECTOR]) == 2
    assert layer[MaidrKey.STEP_DIRECTION] == "hv"


def test_the_layer_carries_censoring_band_and_arm():
    fig, ax = plt.subplots()
    maidr.plot_survival(
        TIME, CONTROL, lower=LOWER, upper=UPPER, censored=[15], label="Control", ax=ax
    )

    (arm,) = layers(fig)[0][MaidrKey.DATA]
    assert [p["x"] for p in arm] == TIME
    assert [p["y"] for p in arm] == CONTROL
    assert [p["yMin"] for p in arm] == LOWER
    assert [p["yMax"] for p in arm] == UPPER
    assert [p["x"] for p in arm if p.get("censored")] == [15]
    assert {p["z"] for p in arm} == {"Control"}


def test_axes_are_canonical_and_name_the_legend_title():
    fig, ax = plt.subplots()
    maidr.plot_survival(TIME, CONTROL, label="Control", ax=ax)
    ax.set_xlabel("Months")
    ax.set_ylabel("Survival probability")
    ax.legend(title="Arm")

    axes = layers(fig)[0][MaidrKey.AXES]
    assert axes == {
        MaidrKey.X: {MaidrKey.LABEL: "Months"},
        MaidrKey.Y: {MaidrKey.LABEL: "Survival probability"},
        MaidrKey.Z: {MaidrKey.LABEL: "Arm"},
    }


def test_each_selector_names_a_staircase_of_two_vertices_per_point_less_one():
    fig, ax = plt.subplots()
    maidr.plot_survival(TIME, CONTROL, censored=[7, 15], ax=ax)

    (layer,) = layers(fig)
    (points,) = layer[MaidrKey.DATA]
    (selector,) = layer[MaidrKey.SELECTOR]
    assert path_vertices(fig, selector) == 2 * len(points) - 1


def test_a_long_curve_keeps_the_vertices_matplotlib_would_simplify_away():
    # From 128 vertices matplotlib merges collinear segments as it draws, and
    # a censored time is exactly such a segment: the curve does not step.
    rng = np.random.default_rng(0)
    time = np.arange(150.0)
    survival = np.cumprod(np.r_[1.0, 1 - rng.uniform(0, 0.02, 149)])
    survival[50:60] = survival[49]
    fig, ax = plt.subplots()
    maidr.plot_survival(time, survival, censored=[10.5, 55, 70.2], ax=ax)

    (layer,) = layers(fig)
    (points,) = layer[MaidrKey.DATA]
    assert len(points) == 152
    assert path_vertices(fig, layer[MaidrKey.SELECTOR][0]) == 2 * len(points) - 1


def test_plot_survival_draws_on_the_current_axes_by_default():
    fig, ax = plt.subplots()
    assert maidr.plot_survival(TIME, CONTROL) is ax


def test_the_page_renders():
    fig, ax = plt.subplots()
    maidr.plot_survival(TIME, CONTROL, censored=[15], ax=ax)

    assert '"survival"' in str(maidr.render(fig)).replace("&quot;", '"')


# --- lifelines, through a stand-in fitter -----------------------------------


class _Censoring:
    """lifelines' ``CensoringType`` member, as far as the patch reads it."""

    def __init__(self, value: str) -> None:
        self.value = value


class StandInFitter:
    """
    A fitted ``KaplanMeierFitter`` as far as the patch reads one.

    Its ``plot_survival_function`` draws as lifelines' ``_plot_estimate``
    does: the censoring marks first, then the estimate through
    ``ax.plot(drawstyle="steps-post")``, then the band through
    ``fill_between(step="post")``.
    """

    def __init__(self, label: str = "KM_estimate", censoring: str = "right") -> None:
        timeline = pd.Index([0.0, 7.0, 17.0, 32.0, 40.0], name="timeline")
        self.label = label
        self._censoring_type = _Censoring(censoring)
        self.survival_function_ = pd.DataFrame(
            {label: [1.0, 0.95, 0.9, 0.8, 0.8]}, index=timeline
        )
        self.confidence_interval_ = pd.DataFrame(
            {
                f"{label}_lower_0.95": [1.0, 0.85, 0.8, 0.7, 0.7],
                f"{label}_upper_0.95": [1.0, 0.99, 0.97, 0.9, 0.9],
            },
            index=timeline,
        )
        self.event_table = pd.DataFrame(
            {"censored": [0, 1, 0, 0, 2]}, index=timeline.rename("event_at")
        )

    def plot_survival_function(
        self, ax=None, show_censors: bool = False, ci_show: bool = True
    ):
        ax = ax or plt.gca()
        x = self.survival_function_.index.values
        y = self.survival_function_.iloc[:, 0].values
        if show_censors:
            censored = self.event_table.index[self.event_table["censored"] > 0]
            ax.plot(censored, [0.9, 0.8], linestyle="None", marker="+")
        ax.plot(x, y, drawstyle="steps-post", label=self.label)
        if ci_show:
            band = self.confidence_interval_
            ax.fill_between(
                x, band.iloc[:, 0], band.iloc[:, 1], step="post", alpha=0.25
            )
        return ax


@pytest.fixture
def fitter_class():
    """The stand-in, with ``plot_survival_function`` wrapped as lifelines' is."""

    class Fitter(StandInFitter):
        pass

    wrapt.wrap_function_wrapper(Fitter, "plot_survival_function", kaplan_meier)
    return Fitter


def test_a_fitter_plot_is_read_as_a_survival_layer(fitter_class):
    fig, ax = plt.subplots()
    fitter_class(label="control").plot_survival_function(ax=ax, show_censors=True)

    (layer,) = layers(fig)
    assert layer[MaidrKey.TYPE] == "survival"
    (arm,) = layer[MaidrKey.DATA]
    assert [p["x"] for p in arm] == [0.0, 7.0, 17.0, 32.0, 40.0]
    assert [p["x"] for p in arm if p.get("censored")] == [7.0, 40.0]
    assert [p["yMin"] for p in arm] == [1.0, 0.85, 0.8, 0.7, 0.7]
    assert {p["z"] for p in arm} == {"control"}
    assert path_vertices(fig, layer[MaidrKey.SELECTOR][0]) == 2 * len(arm) - 1


def test_two_fits_on_one_axes_are_two_arms(fitter_class):
    fig, ax = plt.subplots()
    fitter_class(label="a").plot_survival_function(ax=ax)
    fitter_class(label="b").plot_survival_function(ax=ax, show_censors=True)

    (layer,) = layers(fig)
    assert [arm[0]["z"] for arm in layer[MaidrKey.DATA]] == ["a", "b"]


def test_a_fit_drawn_without_its_band_announces_none(fitter_class):
    fig, ax = plt.subplots()
    fitter_class().plot_survival_function(ax=ax, ci_show=False)

    (arm,) = layers(fig)[0][MaidrKey.DATA]
    assert not any("yMin" in p for p in arm)


def test_a_fit_without_an_axes_is_read_on_the_current_one(fitter_class):
    fig, _ = plt.subplots()
    fitter_class().plot_survival_function()

    assert [plot.type for plot in FigureManager.get_maidr(fig).plots] == [
        PlotType.SURVIVAL
    ]


def test_an_interval_censored_fit_keeps_its_ordinary_reading(fitter_class):
    fig, ax = plt.subplots()
    fitter_class(censoring="interval").plot_survival_function(ax=ax, ci_show=False)

    assert [plot.type for plot in FigureManager.get_maidr(fig).plots] == [PlotType.STEP]
