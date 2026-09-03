"""
``kdeplot`` registers the curves and bands its own call drew (#711).

``_register_smooth`` swept the axes: every ``Line2D`` and every
``PolyCollection`` it found, whoever drew them. Whatever was there beforehand
was registered a second time as a fitted curve, and the reader was handed the
consequences without anything saying so. Measured on seaborn 0.13.2::

    kdeplot(fill=True); kdeplot(fill=True)   3 smooth, the first on no artist
    ax.plot(...); kdeplot(...)               2 smooth, and the line dropped
    ax.fill_between(...); kdeplot(...)       1 area, 2 smooth

The filled case is the worst of them. The second call re-registers the first
band under a fresh gid and writes that gid onto the band, so the first layer
now selects a group no artist carries -- a highlight that lands nowhere.

The before/after snapshot ``maidr/patch/regplot.py`` takes for the same
reason (#451) is the fix: what was on the axes beforehand belongs to whichever
call drew it. The cases below pin what each call registers, and the hue chart
that draws its several curves in *one* call is kept as the guard that the
snapshot only excludes what came before.

One caveat, deliberately not asserted here. A line drawn before the kdeplot
is no longer re-announced as a curve, but it is still not rendered:
``Maidr._superseded_line_layers`` drops every ``LINE`` on an axes holding a
``SMOOTH`` (#378), and that is a per-axes rule in the core, not this patch's
to change.
"""

from __future__ import annotations

import re

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _samples(shift: float = 0.0) -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.normal(size=60) + shift


def _registered(fig) -> list:
    return [plot.type for plot in FigureManager.get_maidr(fig).plots]


def _rendered_layers(fig) -> list:
    """The layers of the one subplot, as the HTML would carry them.

    Rendering first, because that is the pass that tags the artists and
    assigns every smooth its gid; the schema read cold has none of them.
    """
    figure = FigureManager.get_maidr(fig)
    figure.render(use_cdn=False)
    return figure._flatten_maidr()["subplots"][0][0]["layers"]


def _gid_of(layer: dict) -> str:
    (selector,) = layer["selectors"]
    match = re.search(r"id='([^']+)'", selector)
    assert match is not None, f"selector carries no gid: {selector!r}"
    return match.group(1)


class TestTwoFilledKdeplots:
    def test_each_call_registers_one_band(self):
        fig, ax = plt.subplots()
        sns.kdeplot(_samples(), fill=True, ax=ax)
        sns.kdeplot(_samples(1.0), fill=True, ax=ax)

        assert _registered(fig) == [PlotType.SMOOTH, PlotType.SMOOTH]

    def test_every_rendered_layer_selects_a_band_that_exists(self):
        # The dangling highlight: three layers, and the first one's gid on
        # no PolyCollection because the second call overwrote it.
        fig, ax = plt.subplots()
        sns.kdeplot(_samples(), fill=True, ax=ax)
        sns.kdeplot(_samples(1.0), fill=True, ax=ax)

        layers = _rendered_layers(fig)
        bands = [c for c in ax.collections if isinstance(c, PolyCollection)]

        assert [layer["type"] for layer in layers] == [PlotType.SMOOTH] * 2
        assert {_gid_of(layer) for layer in layers} == {b.get_gid() for b in bands}


def test_two_unfilled_kdeplots_register_one_curve_each():
    # The rendered HTML hid this one: the duplicate carried the first curve's
    # gid, and `_duplicate_smooth_layers` dropped it on the second pass.
    fig, ax = plt.subplots()
    sns.kdeplot(_samples(), ax=ax)
    sns.kdeplot(_samples(1.0), ax=ax)

    assert _registered(fig) == [PlotType.SMOOTH, PlotType.SMOOTH]


@pytest.mark.parametrize(
    "first_filled", [True, False], ids=["band then curve", "curve then band"]
)
def test_a_filled_and_an_unfilled_kdeplot_register_one_layer_each(first_filled):
    # Lines and bands are filtered independently, so a mixed pair must not
    # let the first call's artist through the second call's other filter.
    fig, ax = plt.subplots()
    sns.kdeplot(_samples(), fill=first_filled, ax=ax)
    sns.kdeplot(_samples(1.0), fill=not first_filled, ax=ax)

    assert _registered(fig) == [PlotType.SMOOTH, PlotType.SMOOTH]


def test_a_line_drawn_beforehand_is_not_announced_as_a_curve():
    fig, ax = plt.subplots()
    ax.plot([0, 1, 2], [1, 2, 1])
    sns.kdeplot(_samples(), ax=ax)

    assert _registered(fig) == [PlotType.LINE, PlotType.SMOOTH]


def test_a_fill_drawn_beforehand_is_not_announced_as_a_curve():
    fig, ax = plt.subplots()
    ax.fill_between([0, 1, 2], [1, 2, 1])
    sns.kdeplot(_samples(), ax=ax)

    assert _registered(fig) == [PlotType.AREA, PlotType.SMOOTH]


class TestOneCallDrawingSeveral:
    """The snapshot must exclude only what was there before, not what the
    call itself drew in several pieces."""

    @staticmethod
    def _frame() -> pd.DataFrame:
        rng = np.random.default_rng(0)
        return pd.DataFrame(
            {"a": rng.normal(size=60), "g": rng.choice(["x", "y"], size=60)}
        )

    def test_a_hue_kdeplot_still_gives_two_named_curves(self):
        fig, ax = plt.subplots()
        sns.kdeplot(data=self._frame(), x="a", hue="g", ax=ax)

        plots = FigureManager.get_maidr(fig).plots
        assert [plot.type for plot in plots] == [PlotType.SMOOTH] * 2
        assert sorted(plot.schema.get("name") for plot in plots) == ["x", "y"]

    def test_a_filled_hue_kdeplot_still_gives_two_named_bands(self):
        fig, ax = plt.subplots()
        sns.kdeplot(data=self._frame(), x="a", hue="g", fill=True, ax=ax)

        plots = FigureManager.get_maidr(fig).plots
        assert [plot.type for plot in plots] == [PlotType.SMOOTH] * 2
        assert sorted(plot.schema.get("name") for plot in plots) == ["x", "y"]
