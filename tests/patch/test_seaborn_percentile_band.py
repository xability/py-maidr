"""A seaborn median with a percentile interval is read as a percentile band.

``sns.lineplot(estimator="median", errorbar=("pi", w))`` draws, at each x,
the median of the observations there and the band between their
``(100 - w) / 2``-th and ``(100 + w) / 2``-th percentiles: a percentile band
whose levels the arguments name. One such series is a ``percentile_band``;
anything else is the line it always was.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.figure_manager import FigureManager

sns = pytest.importorskip("seaborn")


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


@pytest.fixture
def draws():
    rng = np.random.default_rng(0)
    frame = pd.DataFrame({"week": np.repeat(np.arange(1, 5), 200)})
    frame["sales"] = rng.normal(frame["week"], frame["week"] / 2)
    frame["store"] = np.tile(["a", "b"], len(frame) // 2)
    return frame


def layers(ax):
    return FigureManager.get_maidr(ax.figure).plots


def test_a_median_with_a_percentile_interval_is_a_percentile_band(draws):
    ax = sns.lineplot(
        data=draws, x="week", y="sales", estimator="median", errorbar=("pi", 80)
    )

    (layer,) = layers(ax)
    assert layer.type == PlotType.PERCENTILE_BAND
    schema = layer.schema
    first = schema[MaidrKey.DATA][0]
    assert first["x"] == 1
    at_one = draws.loc[draws["week"] == 1, "sales"]
    assert [q["level"] for q in first["quantiles"]] == [0.1, 0.5, 0.9]
    assert [q["value"] for q in first["quantiles"]] == pytest.approx(
        np.percentile(at_one, [10, 50, 90])
    )
    assert len(schema[MaidrKey.DATA]) == 4
    assert schema[MaidrKey.AXES]["x"]["label"] == "week"
    assert schema[MaidrKey.AXES]["y"]["label"] == "sales"


def test_a_bare_pi_is_seaborns_95(draws):
    ax = sns.lineplot(
        data=draws, x="week", y="sales", estimator=np.median, errorbar="pi"
    )

    (layer,) = layers(ax)
    levels = [q["level"] for q in layer.schema[MaidrKey.DATA][0]["quantiles"]]
    assert levels == pytest.approx([0.025, 0.5, 0.975])


def test_one_selector_for_the_band_then_one_for_the_median(draws):
    ax = sns.lineplot(
        data=draws, x="week", y="sales", estimator="median", errorbar=("pi", 50)
    )

    (layer,) = layers(ax)
    band, median = layer.schema[MaidrKey.SELECTOR]
    (collection,) = ax.collections
    (line,) = ax.get_lines()
    assert f"g[id='{collection.get_gid()}']" in band
    assert median == f"g[id='{line.get_gid()}'] > path"


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"estimator": "median"},
        {"estimator": "mean", "errorbar": ("pi", 80)},
        {"estimator": "median", "errorbar": ("ci", 95)},
        {"estimator": "median", "errorbar": ("pi", 80), "hue": "store"},
        {"estimator": "median", "errorbar": ("pi", 80), "style": "store"},
        {"estimator": "median", "errorbar": ("pi", 80), "size": "store"},
    ],
)
def test_anything_else_keeps_the_line_reading(draws, kwargs):
    ax = sns.lineplot(data=draws, x="week", y="sales", **kwargs)

    assert [layer.type for layer in layers(ax)] == [PlotType.LINE]


def test_a_single_observation_per_x_draws_no_band_and_stays_a_line():
    frame = pd.DataFrame({"week": [1, 2, 3], "sales": [3.0, 1.0, 2.0]})
    ax = sns.lineplot(
        data=frame, x="week", y="sales", estimator="median", errorbar=("pi", 80)
    )

    assert [layer.type for layer in layers(ax)] == [PlotType.LINE]


def test_a_numpy_width_names_the_levels_too(draws):
    ax = sns.lineplot(
        data=draws,
        x="week",
        y="sales",
        estimator="median",
        errorbar=("pi", np.int64(50)),
    )

    (layer,) = layers(ax)
    levels = [q["level"] for q in layer.schema[MaidrKey.DATA][0]["quantiles"]]
    assert levels == [0.25, 0.5, 0.75]


def test_a_date_axis_keeps_the_line_reading(draws):
    draws["day"] = pd.Timestamp("2026-01-01") + pd.to_timedelta(
        draws["week"] * 7, unit="D"
    )
    ax = sns.lineplot(
        data=draws, x="day", y="sales", estimator="median", errorbar=("pi", 80)
    )

    assert [layer.type for layer in layers(ax)] == [PlotType.LINE]


def test_a_band_beside_a_line_on_one_axes_is_each_its_own_layer(draws):
    fig, ax = plt.subplots()
    sns.lineplot(data=draws, x="week", y="sales", ax=ax)
    sns.lineplot(
        data=draws,
        x="week",
        y="sales",
        estimator="median",
        errorbar=("pi", 80),
        ax=ax,
    )

    line, band = layers(ax)
    assert (line.type, band.type) == (PlotType.LINE, PlotType.PERCENTILE_BAND)
    assert len(line.schema[MaidrKey.DATA]) == 1


so = pytest.importorskip("seaborn.objects")


def _objects(frame, band_stat, line_stat, **plot):
    p = (
        so.Plot(frame, x="week", y="sales", **plot)
        .add(so.Band(), band_stat)
        .add(so.Line(), line_stat)
    )
    return p.plot()._figure


def test_objects_band_of_a_median_estimate_and_a_median_line_are_one_band(draws):
    figure = _objects(draws, so.Est("median", errorbar=("pi", 80)), so.Agg("median"))

    (layer,) = FigureManager.get_maidr(figure).plots
    assert layer.type == PlotType.PERCENTILE_BAND
    first = layer.schema[MaidrKey.DATA][0]
    at_one = draws.loc[draws["week"] == 1, "sales"]
    assert [q["level"] for q in first["quantiles"]] == [0.1, 0.5, 0.9]
    assert [q["value"] for q in first["quantiles"]] == pytest.approx(
        np.percentile(at_one, [10, 50, 90])
    )
    assert len(layer.schema[MaidrKey.DATA]) == 4


@pytest.mark.parametrize(
    "band_stat, line_stat, plot",
    [
        # A mean is not the 50th percentile the band is read around.
        (lambda: so.Est("mean", errorbar=("pi", 80)), lambda: so.Agg("mean"), {}),
        # A confidence interval states no percentiles.
        (lambda: so.Est("median", errorbar="ci"), lambda: so.Agg("median"), {}),
        # Two series, a band and a line each.
        (
            lambda: so.Est("median", errorbar=("pi", 80)),
            lambda: so.Agg("median"),
            {"color": "store"},
        ),
    ],
)
def test_objects_anything_else_keeps_its_line_and_interval(
    draws, band_stat, line_stat, plot
):
    figure = _objects(draws, band_stat(), line_stat(), **plot)

    types = {layer.type for layer in FigureManager.get_maidr(figure).plots}
    assert PlotType.PERCENTILE_BAND not in types
    assert PlotType.LINE in types
