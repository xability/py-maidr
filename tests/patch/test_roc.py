"""A ``RocCurveDisplay`` reads as a ROC curve rather than as a line.

Every way scikit-learn draws a ROC curve ends in ``RocCurveDisplay.plot``,
which calls ``ax.plot(fpr, tpr)`` -- and ``ax.plot`` is patched, so before
this the chart registered a *line* layer. A line reads the rates correctly
and answers the wrong questions: its min and max are 0 and 1 on every ROC
curve, its pitch is scaled per series so two classifiers sound alike, and
the area under the curve -- the number the chart is quoted by -- sits in the
legend text and reaches no reader. With ``plot_chance_level=True`` the
diagonal was announced as a second series.

So the display is read instead of the line, and the tests that matter are
about what the reading carries (the rates, the area, the name), what it
leaves out (the chance diagonal), and what it must not disturb (a plain
line drawn on the same figure).
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pytest

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.figure_manager import FigureManager

sklearn_metrics = pytest.importorskip("sklearn.metrics")
RocCurveDisplay = sklearn_metrics.RocCurveDisplay

#: Ten labels and scores whose ROC curve has a few distinct operating points.
Y_TRUE = np.array([0, 0, 1, 1, 0, 1, 0, 1, 1, 0])
Y_SCORE = np.array([0.1, 0.4, 0.35, 0.8, 0.2, 0.9, 0.6, 0.7, 0.3, 0.05])


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def display_named(name, **kwargs):
    """A hand-built display named ``name``, on any scikit-learn.

    The constructor's parameter is ``name`` from scikit-learn 1.7 and
    ``estimator_name`` before that; the reading honours both.
    """
    try:
        return RocCurveDisplay(name=name, **kwargs)
    except TypeError:
        return RocCurveDisplay(estimator_name=name, **kwargs)


def layers(fig):
    """The layer schemas of a figure, in registration order."""
    return [plot.schema for plot in FigureManager.get_maidr(fig).plots]


def types(fig):
    """The layer types of a figure, in registration order."""
    return [plot.type for plot in FigureManager.get_maidr(fig).plots]


def test_a_display_is_read_as_a_roc_curve_rather_than_a_line():
    fig, ax = plt.subplots()
    RocCurveDisplay.from_predictions(Y_TRUE, Y_SCORE, ax=ax, name="Logistic")

    assert types(fig) == [PlotType.ROC]


def test_the_curve_is_the_rates_the_display_holds():
    fig, ax = plt.subplots()
    display = RocCurveDisplay.from_predictions(Y_TRUE, Y_SCORE, ax=ax)

    (curve,) = layers(fig)[0][MaidrKey.DATA]

    assert [p[MaidrKey.X] for p in curve] == pytest.approx(list(display.fpr))
    assert [p[MaidrKey.Y] for p in curve] == pytest.approx(list(display.tpr))
    assert curve[0][MaidrKey.X] == 0 and curve[0][MaidrKey.Y] == 0
    assert curve[-1][MaidrKey.X] == 1 and curve[-1][MaidrKey.Y] == 1


def test_the_area_travels_on_the_first_point():
    fig, ax = plt.subplots()
    display = RocCurveDisplay.from_predictions(Y_TRUE, Y_SCORE, ax=ax)

    (curve,) = layers(fig)[0][MaidrKey.DATA]

    assert curve[0][MaidrKey.AUC] == pytest.approx(display.roc_auc)
    assert all(MaidrKey.AUC not in point for point in curve[1:])


def test_the_name_is_the_one_the_caller_gave_not_the_legend_label():
    # The legend reads "Logistic (AUC = 0.75)"; the curve's name is "Logistic".
    fig, ax = plt.subplots()
    RocCurveDisplay.from_predictions(Y_TRUE, Y_SCORE, ax=ax, name="Logistic")

    (curve,) = layers(fig)[0][MaidrKey.DATA]

    assert {point[MaidrKey.Z] for point in curve} == {"Logistic"}


def test_a_name_passed_to_plot_wins_over_the_display_name():
    fig, ax = plt.subplots()
    display = display_named(
        "a", fpr=np.array([0, 0.2, 1]), tpr=np.array([0, 0.8, 1]), roc_auc=0.8
    )
    display.plot(ax=ax, name="b")

    (curve,) = layers(fig)[0][MaidrKey.DATA]

    assert curve[0][MaidrKey.Z] == "b"


def test_the_display_name_names_the_curve_when_plot_is_given_none():
    fig, ax = plt.subplots()
    display_named("a", fpr=np.array([0, 0.2, 1]), tpr=np.array([0, 0.8, 1])).plot(ax=ax)

    (curve,) = layers(fig)[0][MaidrKey.DATA]

    assert curve[0][MaidrKey.Z] == "a"


def test_an_unnamed_curve_carries_no_name_and_a_display_without_an_area_no_area():
    fig, ax = plt.subplots()
    RocCurveDisplay(fpr=np.array([0, 0.2, 1]), tpr=np.array([0, 0.8, 1])).plot(ax=ax)

    (curve,) = layers(fig)[0][MaidrKey.DATA]

    assert all(MaidrKey.Z not in point for point in curve)
    assert all(MaidrKey.AUC not in point for point in curve)
    assert [(p[MaidrKey.X], p[MaidrKey.Y]) for p in curve] == [
        (0, 0),
        (0.2, 0.8),
        (1, 1),
    ]


def test_the_chance_diagonal_is_not_a_curve():
    fig, ax = plt.subplots()
    RocCurveDisplay.from_predictions(Y_TRUE, Y_SCORE, ax=ax, plot_chance_level=True)

    schema = layers(fig)[0]

    assert types(fig) == [PlotType.ROC]
    assert len(schema[MaidrKey.DATA]) == 1
    assert len(schema[MaidrKey.SELECTOR]) == 1


def test_two_classifiers_on_one_axes_are_two_curves_of_one_chart():
    fig, ax = plt.subplots()
    RocCurveDisplay.from_predictions(Y_TRUE, Y_SCORE, ax=ax, name="Logistic")
    RocCurveDisplay.from_predictions(Y_TRUE, 1 - Y_SCORE, ax=ax, name="Inverted")

    schema = layers(fig)[0]

    assert types(fig) == [PlotType.ROC]
    assert [curve[0][MaidrKey.Z] for curve in schema[MaidrKey.DATA]] == [
        "Logistic",
        "Inverted",
    ]
    assert len(schema[MaidrKey.SELECTOR]) == 2


def test_each_curve_gets_a_selector_naming_its_own_line():
    fig, ax = plt.subplots()
    first = RocCurveDisplay.from_predictions(Y_TRUE, Y_SCORE, ax=ax, name="a")
    second = RocCurveDisplay.from_predictions(Y_TRUE, 1 - Y_SCORE, ax=ax, name="b")

    selectors = layers(fig)[0][MaidrKey.SELECTOR]

    assert selectors == [
        f"g[id='{first.line_.get_gid()}'] path",
        f"g[id='{second.line_.get_gid()}'] path",
    ]


def test_the_axes_are_the_rates_the_display_labels():
    fig, ax = plt.subplots()
    RocCurveDisplay.from_predictions(Y_TRUE, Y_SCORE, ax=ax)

    axes = layers(fig)[0][MaidrKey.AXES]

    assert axes[MaidrKey.X]["label"].startswith("False Positive Rate")
    assert axes[MaidrKey.Y]["label"].startswith("True Positive Rate")


def test_a_line_drawn_beside_a_roc_curve_keeps_its_reading():
    fig, (left, right) = plt.subplots(1, 2)
    left.plot([1, 2, 3], [3, 1, 2])
    RocCurveDisplay.from_predictions(Y_TRUE, Y_SCORE, ax=right)

    assert types(fig) == [PlotType.LINE, PlotType.ROC]


def test_a_display_drawn_from_an_estimator_is_read_too():
    datasets = pytest.importorskip("sklearn.datasets")
    linear_model = pytest.importorskip("sklearn.linear_model")
    X, y = datasets.make_classification(n_samples=60, random_state=0)
    model = linear_model.LogisticRegression().fit(X, y)
    fig, ax = plt.subplots()

    RocCurveDisplay.from_estimator(model, X, y, ax=ax)

    (curve,) = layers(fig)[0][MaidrKey.DATA]
    assert curve[0][MaidrKey.Z] == "LogisticRegression"
    assert 0 < curve[0][MaidrKey.AUC] <= 1


def test_a_display_holding_several_curves_reads_each():
    # `from_cv_results` (scikit-learn 1.7) plots one curve per fold from a
    # single display, with the rates, areas and names kept as lists.
    if not hasattr(RocCurveDisplay, "from_cv_results"):
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

    RocCurveDisplay.from_cv_results(results, X, y, ax=ax)

    schema = layers(fig)[0]
    assert types(fig) == [PlotType.ROC]
    assert len(schema[MaidrKey.DATA]) == 3
    assert len(schema[MaidrKey.SELECTOR]) == 3
    for curve in schema[MaidrKey.DATA]:
        assert 0 <= curve[0][MaidrKey.AUC] <= 1
