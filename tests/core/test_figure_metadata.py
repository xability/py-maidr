"""Tests for figure-wide metadata in the top-level MAIDR schema.

The maidr JS engine reads optional top-level ``title`` and
``axes: {x: {label}, y: {label}}`` fields on the ``maidr`` object for
multi-panel figures (announced at the figure "lobby" with figure ->
focused-subplot precedence). These tests verify that matplotlib's
figure-level artists are mapped onto those fields:

- ``Figure.suptitle``  -> ``title``
- ``Figure.supxlabel`` -> ``axes.x.label``
- ``Figure.supylabel`` -> ``axes.y.label``

and that figures without figure-level text keep their prior schema shape
(no ``title`` / ``axes`` keys at the top level).

The Plotly counterpart lives in ``tests/plotly/test_plotly_maidr.py``
(``TestPlotlyFigureMetadata``); note the paths are asymmetric by design —
Plotly maps ``layout.title.subtitle`` to a top-level ``subtitle``, while
matplotlib has no native subtitle/caption artist and never emits either.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.figure_manager import FigureManager  # noqa: E402


def _stringify_keys(d: dict) -> dict:
    """Normalize MaidrKey enum keys to plain strings for assertions."""
    out = {}
    for k, v in d.items():
        key = k.value if hasattr(k, "value") else k
        out[key] = _stringify_keys(v) if isinstance(v, dict) else v
    return out


def _flattened_schema(fig) -> dict:
    m = FigureManager.get_maidr(fig)
    return _stringify_keys(m._flatten_maidr())


def test_multi_panel_emits_figure_wide_title_and_axes():
    fig, axs = plt.subplots(1, 2)
    try:
        axs[0].bar(["a", "b"], [1, 2])
        axs[1].bar(["a", "b"], [3, 4])
        fig.suptitle("Sales by Region")
        fig.supxlabel("Year")
        fig.supylabel("Revenue")

        schema = _flattened_schema(fig)

        assert schema["title"] == "Sales by Region"
        assert schema["axes"] == {
            "x": {"label": "Year"},
            "y": {"label": "Revenue"},
        }
        # Grid structure is unchanged.
        assert len(schema["subplots"]) == 1
        assert len(schema["subplots"][0]) == 2
    finally:
        plt.close(fig)


def test_no_figure_level_text_omits_title_and_axes():
    fig, ax = plt.subplots()
    try:
        ax.bar(["a", "b"], [1, 2])

        schema = _flattened_schema(fig)

        assert "title" not in schema
        assert "axes" not in schema
        assert "id" in schema
        assert "subplots" in schema
    finally:
        plt.close(fig)


def test_only_authored_axis_is_emitted():
    fig, axs = plt.subplots(2, 1)
    try:
        axs[0].bar(["a", "b"], [1, 2])
        axs[1].bar(["a", "b"], [3, 4])
        fig.supxlabel("Quarter")

        schema = _flattened_schema(fig)

        assert "title" not in schema
        assert schema["axes"] == {"x": {"label": "Quarter"}}
    finally:
        plt.close(fig)


def test_only_authored_y_axis_is_emitted():
    fig, axs = plt.subplots(1, 2)
    try:
        axs[0].bar(["a", "b"], [1, 2])
        axs[1].bar(["a", "b"], [3, 4])
        fig.supylabel("Revenue")

        schema = _flattened_schema(fig)

        assert "title" not in schema
        assert schema["axes"] == {"y": {"label": "Revenue"}}
    finally:
        plt.close(fig)


def test_suptitle_alone_emits_title_without_axes():
    fig, ax = plt.subplots()
    try:
        ax.bar(["a", "b"], [1, 2])
        fig.suptitle("Overview")

        schema = _flattened_schema(fig)

        assert schema["title"] == "Overview"
        assert "axes" not in schema
    finally:
        plt.close(fig)


def test_whitespace_only_figure_text_counts_as_unauthored():
    fig, ax = plt.subplots()
    try:
        ax.bar(["a", "b"], [1, 2])
        fig.suptitle("   ")
        fig.supxlabel(" \t ")

        schema = _flattened_schema(fig)

        assert "title" not in schema
        assert "axes" not in schema
    finally:
        plt.close(fig)


def test_figure_and_subplot_axis_labels_coexist():
    """A figure-wide supxlabel/supylabel and per-axes xlabel/ylabel live at
    different nesting levels and must both be emitted unchanged."""
    import json

    fig, ax = plt.subplots()
    try:
        ax.bar(["a", "b"], [1, 2])
        ax.set_xlabel("Local X")
        ax.set_ylabel("Local Y")
        fig.supxlabel("Global X")
        fig.supylabel("Global Y")

        m = FigureManager.get_maidr(fig)
        # JSON round-trip normalizes MaidrKey enum keys to plain strings
        # at every nesting level (dicts inside the subplots lists too).
        schema = json.loads(json.dumps(m._flatten_maidr()))

        assert schema["axes"] == {
            "x": {"label": "Global X"},
            "y": {"label": "Global Y"},
        }
        layer_axes = schema["subplots"][0][0]["layers"][0]["axes"]
        assert layer_axes["x"]["label"] == "Local X"
        assert layer_axes["y"]["label"] == "Local Y"
    finally:
        plt.close(fig)


def test_figure_metadata_survives_svg_embedding():
    """The extra top-level keys must round-trip through the SVG `maidr`
    attribute JSON embedding used by render()/save_html()."""
    import json

    from lxml import etree

    fig, axs = plt.subplots(1, 2)
    try:
        axs[0].bar(["a", "b"], [1, 2])
        axs[1].bar(["a", "b"], [3, 4])
        fig.suptitle("Sales by Region")
        fig.supxlabel("Year")
        fig.supylabel("Revenue")

        m = FigureManager.get_maidr(fig)
        svg = str(m._get_svg(embed_data=True))

        root = etree.fromstring(svg.encode(), parser=None)
        embedded = json.loads(root.attrib["maidr"])

        assert embedded["title"] == "Sales by Region"
        assert embedded["axes"] == {
            "x": {"label": "Year"},
            "y": {"label": "Revenue"},
        }
        assert embedded["id"] == root.attrib["id"]
    finally:
        plt.close(fig)
