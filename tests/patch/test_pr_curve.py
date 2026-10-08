"""A ``PrecisionRecallDisplay`` reads as a PR curve rather than as a step line.

Every way scikit-learn draws a precision-recall curve ends in
``PrecisionRecallDisplay.plot``, which calls ``ax.plot(recall, precision,
drawstyle="steps-post")`` -- and ``ax.plot`` is patched, so before this the
chart registered a *step* layer, with the dashed chance level announced as a
second series when ``plot_chance_level=True`` drew one. The display is read
instead, as the ROC display is: the tests are about what the reading carries
(the rates in reading order, the average precision, the share of positives,
the name), what it leaves out (the chance level), and what it must not
disturb.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pytest

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.figure_manager import FigureManager

sklearn_metrics = pytest.importorskip("sklearn.metrics")
PrecisionRecallDisplay = sklearn_metrics.PrecisionRecallDisplay

#: Ten labels and scores whose PR curve has a few distinct thresholds.
Y_TRUE = np.array([0, 0, 1, 1, 0, 1, 0, 1, 1, 0])
Y_SCORE = np.array([0.1, 0.4, 0.35, 0.8, 0.2, 0.9, 0.6, 0.7, 0.3, 0.05])


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def display_named(name, **kwargs):
    """A hand-built display named ``name``, on any scikit-learn."""
    try:
        return PrecisionRecallDisplay(name=name, **kwargs)
    except TypeError:
        return PrecisionRecallDisplay(estimator_name=name, **kwargs)


def layers(fig):
    """The layer schemas of a figure, in registration order."""
    return [plot.schema for plot in FigureManager.get_maidr(fig).plots]


def types(fig):
    """The layer types of a figure, in registration order."""
    return [plot.type for plot in FigureManager.get_maidr(fig).plots]


def test_a_display_is_read_as_a_pr_curve_rather_than_a_step():
    fig, ax = plt.subplots()
    PrecisionRecallDisplay.from_predictions(Y_TRUE, Y_SCORE, ax=ax, name="Logistic")

    assert types(fig) == [PlotType.PR_CURVE]
    assert layers(fig)[0][MaidrKey.TYPE] == "pr_curve"


def test_the_points_are_the_display_rates_from_low_recall_up():
    fig, ax = plt.subplots()
    display = PrecisionRecallDisplay.from_predictions(Y_TRUE, Y_SCORE, ax=ax)

    (curve,) = layers(fig)[0][MaidrKey.DATA]
    read = [(p[MaidrKey.X], p[MaidrKey.Y]) for p in curve]

    # scikit-learn answers from high recall down; the reading runs the other
    # way, the higher precision first where a recall repeats.
    assert sorted(read) == sorted(zip(display.recall, display.precision))
    assert [x for x, _ in read] == sorted(x for x, _ in read)
    for (x, y), (next_x, next_y) in zip(read, read[1:]):
        assert x < next_x or y >= next_y


def test_the_average_precision_and_share_of_positives_ride_the_first_point():
    fig, ax = plt.subplots()
    display = PrecisionRecallDisplay.from_predictions(Y_TRUE, Y_SCORE, ax=ax)

    (curve,) = layers(fig)[0][MaidrKey.DATA]

    assert curve[0]["ap"] == pytest.approx(display.average_precision)
    assert curve[0]["prevalence"] == pytest.approx(Y_TRUE.mean())
    assert all("ap" not in p and "prevalence" not in p for p in curve[1:])


def test_the_name_is_the_one_the_caller_gave_not_the_legend_label():
    # The legend reads "Logistic (AP = 0.83)"; the curve's name is "Logistic".
    fig, ax = plt.subplots()
    PrecisionRecallDisplay.from_predictions(Y_TRUE, Y_SCORE, ax=ax, name="Logistic")

    (curve,) = layers(fig)[0][MaidrKey.DATA]

    assert {point[MaidrKey.Z] for point in curve} == {"Logistic"}


def test_a_name_passed_to_plot_wins_over_the_display_name():
    fig, ax = plt.subplots()
    display = display_named(
        "a", precision=np.array([1, 0.8, 0.5]), recall=np.array([0, 0.5, 1])
    )
    display.plot(ax=ax, name="b")

    (curve,) = layers(fig)[0][MaidrKey.DATA]

    assert curve[0][MaidrKey.Z] == "b"


def test_a_hand_built_display_without_its_numbers_carries_none_of_them():
    fig, ax = plt.subplots()
    PrecisionRecallDisplay(
        precision=np.array([0.5, 0.8, 1]), recall=np.array([1, 0.5, 0])
    ).plot(ax=ax)

    (curve,) = layers(fig)[0][MaidrKey.DATA]

    assert [(p[MaidrKey.X], p[MaidrKey.Y]) for p in curve] == [
        (0, 1),
        (0.5, 0.8),
        (1, 0.5),
    ]
    assert all(
        key not in point for point in curve for key in (MaidrKey.Z, "ap", "prevalence")
    )


def test_a_non_finite_point_is_left_out():
    fig, ax = plt.subplots()
    PrecisionRecallDisplay(
        precision=np.array([0.5, np.nan, 1]), recall=np.array([1, 0.5, 0])
    ).plot(ax=ax)

    (curve,) = layers(fig)[0][MaidrKey.DATA]

    assert [p[MaidrKey.X] for p in curve] == [0, 1]


def test_the_chance_level_is_not_a_curve():
    fig, ax = plt.subplots()
    PrecisionRecallDisplay.from_predictions(
        Y_TRUE, Y_SCORE, ax=ax, plot_chance_level=True
    )

    schema = layers(fig)[0]

    assert types(fig) == [PlotType.PR_CURVE]
    assert len(schema[MaidrKey.DATA]) == 1
    assert len(schema[MaidrKey.SELECTOR]) == 1


def test_two_classifiers_on_one_axes_are_two_curves_of_one_chart():
    fig, ax = plt.subplots()
    first = PrecisionRecallDisplay.from_predictions(Y_TRUE, Y_SCORE, ax=ax, name="a")
    second = PrecisionRecallDisplay.from_predictions(
        Y_TRUE, 1 - Y_SCORE, ax=ax, name="b"
    )

    schema = layers(fig)[0]

    assert types(fig) == [PlotType.PR_CURVE]
    assert [curve[0][MaidrKey.Z] for curve in schema[MaidrKey.DATA]] == ["a", "b"]
    assert schema[MaidrKey.SELECTOR] == [
        f"g[id='{first.line_.get_gid()}'] path",
        f"g[id='{second.line_.get_gid()}'] path",
    ]


def test_the_axes_are_the_rates_the_display_labels():
    fig, ax = plt.subplots()
    PrecisionRecallDisplay.from_predictions(Y_TRUE, Y_SCORE, ax=ax)

    axes = layers(fig)[0][MaidrKey.AXES]

    assert axes[MaidrKey.X]["label"].startswith("Recall")
    assert axes[MaidrKey.Y]["label"].startswith("Precision")


def test_a_line_drawn_beside_a_pr_curve_keeps_its_reading():
    fig, (left, right) = plt.subplots(1, 2)
    left.plot([1, 2, 3], [3, 1, 2])
    PrecisionRecallDisplay.from_predictions(Y_TRUE, Y_SCORE, ax=right)

    assert types(fig) == [PlotType.LINE, PlotType.PR_CURVE]


def test_a_roc_and_a_pr_curve_side_by_side_are_each_their_own_layer():
    fig, (left, right) = plt.subplots(1, 2)
    sklearn_metrics.RocCurveDisplay.from_predictions(Y_TRUE, Y_SCORE, ax=left)
    PrecisionRecallDisplay.from_predictions(Y_TRUE, Y_SCORE, ax=right)

    assert types(fig) == [PlotType.ROC, PlotType.PR_CURVE]


def test_a_display_drawn_from_an_estimator_is_read_too():
    datasets = pytest.importorskip("sklearn.datasets")
    linear_model = pytest.importorskip("sklearn.linear_model")
    X, y = datasets.make_classification(n_samples=60, random_state=0)
    model = linear_model.LogisticRegression().fit(X, y)
    fig, ax = plt.subplots()

    PrecisionRecallDisplay.from_estimator(model, X, y, ax=ax)

    (curve,) = layers(fig)[0][MaidrKey.DATA]
    assert curve[0][MaidrKey.Z] == "LogisticRegression"
    assert 0 < curve[0]["ap"] <= 1
    assert curve[0]["prevalence"] == pytest.approx(y.mean())


def test_a_display_holding_several_curves_reads_each():
    if not hasattr(PrecisionRecallDisplay, "from_cv_results"):
        pytest.skip("this scikit-learn plots one curve per display")
    datasets = pytest.importorskip("sklearn.datasets")
    linear_model = pytest.importorskip("sklearn.linear_model")
    model_selection = pytest.importorskip("sklearn.model_selection")
    X, y = datasets.make_classification(n_samples=60, random_state=0)
    results = model_selection.cross_validate(
        linear_model.LogisticRegression(),
        X,
        y,
        cv=3,
        return_estimator=True,
        return_indices=True,
    )
    fig, ax = plt.subplots()

    PrecisionRecallDisplay.from_cv_results(results, X, y, ax=ax)

    schema = layers(fig)[0]
    assert types(fig) == [PlotType.PR_CURVE]
    assert len(schema[MaidrKey.DATA]) == 3
    assert len(schema[MaidrKey.SELECTOR]) == 3
    for curve in schema[MaidrKey.DATA]:
        assert 0 <= curve[0]["ap"] <= 1
