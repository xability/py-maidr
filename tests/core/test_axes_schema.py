"""Tests that the canonical ``axes`` payload shape is emitted by real plots.

The MAIDR schema's ``axes`` object must follow the canonical per-axis form:

- Keys are a subset of ``{x, y, z}``.
- Each value is an ``AxisConfig`` dict (never a bare string).
- ``format``/``min``/``max``/``tickStep``/``fill``/``level`` never appear as
  siblings of ``x``/``y``/``z``.

These tests exercise real matplotlib/seaborn emitters end-to-end so the
contract is enforced without a runtime validator.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import seaborn as sns  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402


FORBIDDEN_TOP_LEVEL_KEYS = ("format", "min", "max", "tickStep", "fill", "level")
ALLOWED_AXIS_CONFIG_KEYS = {"label", "min", "max", "tickStep", "format"}


def _stringify_keys(d: dict) -> dict:
    """Normalize MaidrKey enum keys to plain strings for assertions."""
    out = {}
    for k, v in d.items():
        key = k.value if hasattr(k, "value") else k
        out[key] = _stringify_keys(v) if isinstance(v, dict) else v
    return out


def _first_schema(fig) -> dict:
    m = FigureManager.get_maidr(fig)
    plot = m._plots[0]
    return _stringify_keys(plot.schema)


def _assert_canonical_axes(axes: dict) -> None:
    """Assert an ``axes`` dict adheres to the canonical contract."""
    assert isinstance(axes, dict), f"axes must be a dict, got {type(axes).__name__}"

    # Keys are a subset of {x, y, z}.
    assert set(axes.keys()) <= {"x", "y", "z"}, f"unexpected axes keys: {axes.keys()}"

    # No forbidden sibling keys.
    for forbidden in FORBIDDEN_TOP_LEVEL_KEYS:
        assert forbidden not in axes, (
            f"'{forbidden}' must not be a sibling of x/y/z"
        )

    # Each value is an AxisConfig dict with only allowed keys.
    for axis_key, cfg in axes.items():
        assert isinstance(cfg, dict), (
            f"axes['{axis_key}'] must be a dict, got {type(cfg).__name__}"
        )
        for cfg_key in cfg.keys():
            assert cfg_key in ALLOWED_AXIS_CONFIG_KEYS, (
                f"axes['{axis_key}']['{cfg_key}'] is not an allowed AxisConfig key"
            )


class TestMatplotlibCanonicalShape:
    def test_bar(self):
        fig, ax = plt.subplots()
        try:
            ax.bar(["a", "b", "c"], [1, 2, 3])
            ax.set_xlabel("Category")
            ax.set_ylabel("Count")
            axes = _first_schema(fig)["axes"]

            _assert_canonical_axes(axes)
            assert axes["x"]["label"] == "Category"
            assert axes["y"]["label"] == "Count"
        finally:
            plt.close(fig)

    def test_scatter_emits_per_axis_object(self):
        fig, ax = plt.subplots()
        try:
            ax.scatter([1, 2, 3], [4, 5, 6])
            ax.set_xlabel("X")
            ax.set_ylabel("Y")
            axes = _first_schema(fig)["axes"]

            _assert_canonical_axes(axes)
            assert isinstance(axes["x"], dict)
            assert isinstance(axes["y"], dict)
            assert axes["x"]["label"] == "X"
            assert axes["y"]["label"] == "Y"
        finally:
            plt.close(fig)

    def test_heatmap_has_z_axis_config(self):
        fig, ax = plt.subplots()
        try:
            data = np.arange(9).reshape(3, 3)
            sns.heatmap(data, ax=ax)
            ax.set_xlabel("Col")
            ax.set_ylabel("Row")
            axes = _first_schema(fig)["axes"]

            _assert_canonical_axes(axes)
            assert "z" in axes
            if "label" in axes["z"]:
                assert isinstance(axes["z"]["label"], str)
        finally:
            plt.close(fig)

    def test_no_format_sibling_with_currency_axis(self):
        from matplotlib.ticker import FuncFormatter

        fig, ax = plt.subplots()
        try:
            ax.bar(["a", "b"], [1000, 2000])
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"${v:,.0f}"))
            axes = _first_schema(fig)["axes"]

            _assert_canonical_axes(axes)
            # If format was detected, it's nested inside y AxisConfig
            if isinstance(axes.get("y"), dict) and "format" in axes["y"]:
                assert isinstance(axes["y"]["format"], dict)
        finally:
            plt.close(fig)


class TestGroupedBarAxesZ:
    def test_extract_axes_has_z_from_legend(self):
        # Exercise GroupedBarPlot._extract_axes_data directly.
        from maidr.core.enum.plot_type import PlotType
        from maidr.core.plot.grouped_barplot import GroupedBarPlot

        fig, ax = plt.subplots()
        try:
            ax.bar(["A", "B"], [1, 2], label="g1")
            ax.bar(["A", "B"], [3, 4], label="g2")
            ax.set_xlabel("cat")
            ax.set_ylabel("val")
            ax.legend(title="grp")

            plot = GroupedBarPlot(ax, PlotType.DODGED)
            axes = _stringify_keys(plot._extract_axes_data())

            _assert_canonical_axes(axes)
            assert axes["z"]["label"] == "grp"
        finally:
            plt.close(fig)
