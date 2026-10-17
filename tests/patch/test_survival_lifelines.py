"""lifelines' Kaplan-Meier plot is read as a ``survival`` layer.

lifelines is not a dependency of maidr, nor of its tests: this runs where it
is installed and skips elsewhere. ``tests/core/plot/test_survival.py`` covers
the same reading against a stand-in fitter that draws as lifelines does.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pytest

from maidr.core.enum import MaidrKey, PlotType
from maidr.core.figure_manager import FigureManager

lifelines = pytest.importorskip("lifelines")

DURATIONS = np.array([5, 6, 6, 2.5, 4, 4, 8, 9, 10, 12, 3, 7])
EVENTS = np.array([1, 0, 1, 1, 1, 0, 1, 0, 1, 1, 0, 1])


def test_plot_survival_function_is_read_as_a_survival_layer():
    fitter = lifelines.KaplanMeierFitter().fit(DURATIONS, EVENTS, label="arm")
    fig, ax = plt.subplots()
    fitter.plot_survival_function(ax=ax, show_censors=True)

    plots = FigureManager.get_maidr(fig).plots
    assert [plot.type for plot in plots] == [PlotType.SURVIVAL]
    (arm,) = plots[0].schema[MaidrKey.DATA]
    estimate = fitter.survival_function_["arm"]
    assert [p["x"] for p in arm] == list(estimate.index.astype(float))
    assert [p["y"] for p in arm] == pytest.approx(list(estimate.values))
    assert [p["x"] for p in arm if p.get("censored")] == [3.0, 4.0, 6.0, 9.0]
    assert all("yMin" in p and "yMax" in p for p in arm)
