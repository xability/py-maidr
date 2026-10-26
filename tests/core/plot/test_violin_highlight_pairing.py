"""
Each violin's row is outlined on that violin's own marks, in reading order.

maidr.js reverses a horizontal violin layer, its data and its selectors alike,
so that Up moves up the page from the bottom violin. It needs the violins
listed top first. Two things went wrong on the way there:

* the box layer reversed its data for a horizontal violin but not its
  selectors, so each violin was outlined at its mirror image: on seaborn's
  five horizontal violins, reading Ideal (the top one) outlined Fair's box at
  the bottom, and on matplotlib's the first dataset outlined the last;
* both layers reversed whenever the violins ran across the page, which suits
  matplotlib, whose first violin is drawn at the bottom, and not seaborn,
  whose inverted category axis draws the first one at the top. Seaborn's
  violins were listed bottom first, so the reader started on the top violin
  and Up moved down the page.

The matplotlib box layer also named its min-to-max bar as the box's
interquartile element, from whose two ends maidr.js draws the 25% and 75%
outlines, so those landed on the minimum's and maximum's caps.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402

#: Three groups whose ranges do not overlap, so a row and a mark can be
#: matched by value alone.
LOCATIONS = {"low": 0.0, "mid": 10.0, "high": 20.0}


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _frame() -> pd.DataFrame:
    rng = np.random.default_rng(3)
    return pd.DataFrame(
        {
            "group": np.repeat(list(LOCATIONS), 200),
            "value": np.concatenate(
                [rng.normal(loc, 1.0, 200) for loc in LOCATIONS.values()]
            ),
        }
    )


def _schema(plot) -> dict:
    return {(k.value if hasattr(k, "value") else k): v for k, v in plot.schema.items()}


def _layers(fig) -> dict[PlotType, dict]:
    return {plot.type: _schema(plot) for plot in FigureManager.get_maidr(fig).plots}


def _artist_by_gid(ax, gid: str):
    for artist in [*ax.lines, *ax.collections]:
        if artist.get_gid() == gid:
            return artist
    raise AssertionError(f"no artist carries gid {gid!r}")


def _gid(selector: str) -> str:
    return selector.split("id='", 1)[1].split("'", 1)[0]


def _screen_y(ax, value_axis_positions: list[float]) -> list[float]:
    """Display y of each position on the y axis (larger is higher up)."""
    return [ax.transData.transform((0, pos))[1] for pos in value_axis_positions]


def _seaborn(orient: str):
    fig, ax = plt.subplots()
    if orient == "y":
        sns.violinplot(data=_frame(), y="group", x="value", inner="box", ax=ax)
    else:
        sns.violinplot(data=_frame(), x="group", y="value", inner="box", ax=ax)
    return fig, ax


@pytest.mark.parametrize("orient", ["x", "y"])
def test_seaborn_box_selector_names_its_own_violins_whisker(orient: str) -> None:
    """The whisker selector *i* names spans row *i*'s minimum to maximum."""
    fig, ax = _seaborn(orient)
    box = _layers(fig)[PlotType.VIOLIN_BOX]

    assert len(box["selectors"]) == len(box["data"]) == 3
    for row, selector in zip(box["data"], box["selectors"]):
        whisker = _artist_by_gid(ax, _gid(selector["min"]))
        values = whisker.get_ydata() if orient == "x" else whisker.get_xdata()
        assert (min(values), max(values)) == pytest.approx((row["min"], row["max"]))
        iq = _artist_by_gid(ax, _gid(selector["iq"]))
        values = iq.get_ydata() if orient == "x" else iq.get_xdata()
        assert (min(values), max(values)) == pytest.approx((row["q1"], row["q3"]))


def test_seaborn_horizontal_violins_are_listed_top_first() -> None:
    """Both layers list the top violin first, which maidr.js reads last."""
    fig, ax = _seaborn("y")
    layers = _layers(fig)
    labels = [label.get_text() for label in ax.get_yticklabels()]
    positions = dict(zip(labels, ax.get_yticks()))

    box_names = [row["z"] for row in layers[PlotType.VIOLIN_BOX]["data"]]
    kde_names = [rows[0]["x"] for rows in layers[PlotType.VIOLIN_KDE]["data"]]
    heights = _screen_y(ax, [positions[name] for name in box_names])

    assert box_names == ["low", "mid", "high"]
    assert heights == sorted(heights, reverse=True), "not listed top first"
    assert kde_names == box_names


@pytest.mark.parametrize("orient", ["x", "y"])
def test_seaborn_kde_selector_names_its_own_violin(orient: str) -> None:
    """KDE selector *i* names the body drawn at row *i*'s category."""
    fig, ax = _seaborn(orient)
    kde = _layers(fig)[PlotType.VIOLIN_KDE]
    tick_labels = ax.get_yticklabels() if orient == "y" else ax.get_xticklabels()
    ticks = ax.get_yticks() if orient == "y" else ax.get_xticks()
    positions = dict(zip([label.get_text() for label in tick_labels], ticks))

    for rows, selector in zip(kde["data"], kde["selectors"]):
        body = _artist_by_gid(ax, _gid(selector))
        assert isinstance(body, PolyCollection)
        vertices = body.get_paths()[0].vertices
        across = vertices[:, 1] if orient == "y" else vertices[:, 0]
        assert np.mean([across.min(), across.max()]) == pytest.approx(
            positions[rows[0]["x"]]
        )


@pytest.mark.parametrize("vert", [True, False])
def test_matplotlib_box_selector_names_its_own_violin(vert: bool) -> None:
    """Row ``Group j`` is outlined on segment *j* of each LineCollection."""
    fig, ax = plt.subplots()
    frame = _frame()
    ax.violinplot(
        [frame.loc[frame["group"] == group, "value"].to_numpy() for group in LOCATIONS],
        vert=vert,
        showmedians=True,
    )
    box = _layers(fig)[PlotType.VIOLIN_BOX]

    names = [row["z"] for row in box["data"]]
    expected = ["Group 1", "Group 2", "Group 3"]
    # Drawn at ascending positions: bottom first across the page, so listed
    # top first by reversing.
    assert names == (expected if vert else expected[::-1])
    for row, selector in zip(box["data"], box["selectors"]):
        nth = f":nth-child({row['z'].split()[-1]})"
        for part in ("min", "q2", "max"):
            assert selector[part].endswith(nth), (row["z"], part, selector[part])


def test_matplotlib_quartiles_are_not_outlined_on_the_extrema_bar() -> None:
    """Nothing matplotlib draws spans the quartiles, so ``iq`` names nothing.

    Named as the min-to-max bar, it put the 25% outline on the minimum's cap
    and the 75% outline on the maximum's.
    """
    fig, ax = plt.subplots()
    ax.violinplot([[1, 2, 3, 4, 9], [2, 3, 4, 5, 6]], showmeans=True)
    box = _layers(fig)[PlotType.VIOLIN_BOX]

    assert [selector["iq"] for selector in box["selectors"]] == ["", ""]
    assert all(selector["min"] and selector["max"] for selector in box["selectors"])
