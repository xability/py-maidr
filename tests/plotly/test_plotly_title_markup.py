"""A plotly title is read as the words plotly draws, not as its markup.

Plotly titles and labels take a little HTML -- ``<br>`` to break a line,
``<b>``, ``<i>``, ``<sup>`` and the like to style words, entities such as
``&amp;`` -- and plotly draws the words, not the tags. Every reader took the
string as it was written, so a figure titled
``"Hypnogram<br>Sleep stage across one night"`` was announced with the
``<br>`` in it: in the chart's accessible name, in its description and on the
title key, as an audit that drove every example with the keyboard found.

``plain_text`` follows plotly.js's own reading (``svg_text_utils``). The cases
in ``DRAWN`` were measured in Chromium, by drawing each as an annotation and
reading the text plotly put in the page.
"""

from __future__ import annotations

import pytest

pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402
from maidr.plotly.plotly_plot import plain_text  # noqa: E402

#: A label as written, and the words plotly drew for it. Where plotly draws
#: markup as written -- ``<br/>``, an unknown tag, an entity it does not
#: convert -- so does this; the reader hears what the chart shows.
DRAWN = [
    ("Hypnogram<br>Sleep stage across one night", "Hypnogram Sleep stage across one night"),
    ("a<BR>b", "a b"),
    ("a<br />b", "a b"),
    ("a<br/>b", "a<br/>b"),
    ("<b>x</b> &amp; &copy; <foo> y", "x & &copy; <foo> y"),
    ("m<sup>2</sup> &#36; &#x41; &#X41;", "m2 $ A &#X41;"),
    ("line1\nline2", "line1 line2"),
    ("a  <span style='color:red'>red</span>   b", "a red b"),
    ("x &lt;5 &gt; &deg;", "x <5 > °"),
    ('<a href="https://example.com">site</a>', "site"),
    # Plotly draws these as characters that show nothing, so nothing is read.
    ("a&#0;b", "ab"),
    ("a&#xD800;b", "ab"),
    ("<br>", ""),
    ("", ""),
    (None, ""),
]


def _schema(fig: go.Figure) -> dict:
    return PlotlyMaidr(fig)._flatten_maidr()


def _layers(fig: go.Figure) -> list[dict]:
    grid = _schema(fig)["subplots"]
    return [layer for row in grid for cell in row for layer in cell["layers"]]


def _label(layer: dict, axis: MaidrKey) -> str:
    return layer[MaidrKey.AXES][axis][MaidrKey.LABEL]


@pytest.mark.parametrize(("written", "drawn"), DRAWN)
def test_a_label_reads_as_plotly_draws_it(written, drawn):
    assert plain_text(written) == drawn


class TestTitles:
    """The figure's title, subtitle and the titles of its subplots."""

    def test_a_title_broken_over_two_lines_reads_as_one(self):
        fig = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))
        fig.update_layout(title="Hypnogram<br>Sleep stage across one night")

        schema = _schema(fig)
        (layer,) = _layers(fig)

        assert schema["title"] == "Hypnogram Sleep stage across one night"
        assert layer[MaidrKey.TITLE] == "Hypnogram Sleep stage across one night"

    def test_a_subtitle_loses_its_markup(self):
        fig = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))
        fig.update_layout(
            title={"text": "<b>Sales</b>", "subtitle": {"text": "FY<sup>25</sup>"}}
        )

        schema = _schema(fig)

        assert schema["title"] == "Sales"
        assert schema["subtitle"] == "FY25"

    def test_a_title_that_is_only_markup_counts_as_unauthored(self):
        fig = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))
        fig.update_layout(title="<br>")

        assert "title" not in _schema(fig)

    def test_a_surrogate_entity_still_saves(self, tmp_path, monkeypatch):
        # Read as the lone surrogate plotly draws for it, the title could not
        # be written to the page: `save_html` raised UnicodeEncodeError.
        import maidr

        monkeypatch.setenv("MAIDR_CDN_VERSION", "latest")
        fig = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))
        fig.update_layout(title="Rate &#xD800;today")

        page = tmp_path / "surrogate.html"
        maidr.save_html(fig, file=str(page), use_cdn=True)

        assert "Rate today" in page.read_text(encoding="utf-8")

    def test_each_subplot_title_loses_its_markup(self):
        fig = make_subplots(
            rows=1, cols=2, subplot_titles=("<b>Left</b>", "Right<br>panel")
        )
        fig.add_trace(go.Bar(x=["a", "b"], y=[1, 2]), row=1, col=1)
        fig.add_trace(go.Bar(x=["a", "b"], y=[3, 4]), row=1, col=2)

        assert [layer[MaidrKey.TITLE] for layer in _layers(fig)] == [
            "Left",
            "Right panel",
        ]


class TestAxisLabels:
    """Every reader that names an axis from a title the author wrote."""

    def test_a_cartesian_axis(self):
        fig = go.Figure(go.Bar(x=["a", "b"], y=[1, 2]))
        fig.update_layout(xaxis_title="Time<br>(hours)", yaxis_title="<i>Count</i>")

        (layer,) = _layers(fig)

        assert _label(layer, MaidrKey.X) == "Time (hours)"
        assert _label(layer, MaidrKey.Y) == "Count"

    def test_a_scatter_axis(self):
        fig = go.Figure(go.Scatter(x=[1, 2, 3], y=[3, 1, 2], mode="markers"))
        fig.update_layout(xaxis_title="Width &amp; depth", yaxis_title="m<sup>2</sup>")

        (layer,) = _layers(fig)

        assert _label(layer, MaidrKey.X) == "Width & depth"
        assert _label(layer, MaidrKey.Y) == "m2"

    def test_a_color_bar(self):
        fig = go.Figure(
            go.Heatmap(z=[[1, 2], [3, 4]], colorbar={"title": {"text": "Rate<br>(%)"}})
        )

        (layer,) = _layers(fig)

        assert _label(layer, MaidrKey.Z) == "Rate (%)"

    def test_the_axes_a_pie_borrows(self):
        fig = go.Figure(go.Pie(labels=["a", "b"], values=[1, 2]))
        fig.update_layout(xaxis_title="<b>Fruit</b>", yaxis_title="Count &amp; share")

        (layer,) = _layers(fig)

        assert _label(layer, MaidrKey.X) == "Fruit"
        assert _label(layer, MaidrKey.Y) == "Count & share"

    def test_a_polar_radial_axis(self):
        fig = go.Figure(go.Scatterpolar(r=[1, 2, 3], theta=[0, 120, 240]))
        fig.update_layout(polar={"radialaxis": {"title": {"text": "<i>Score</i>"}}})

        (layer,) = _layers(fig)

        assert _label(layer, MaidrKey.Y) == "Score"

    def test_a_gauge_s_measure(self):
        fig = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=5,
                title={"text": "Speed<br><sub>km/h</sub>"},
                gauge={"axis": {"range": [0, 10]}},
            )
        )

        (layer,) = _layers(fig)

        assert layer[MaidrKey.DATA][MaidrKey.LABEL] == "Speed km/h"
