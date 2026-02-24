"""Tests for AltairMaidr end-to-end."""

import json
import os
import tempfile

import pandas as pd
import pytest

altair = pytest.importorskip("altair")
import altair as alt

from maidr.altair import AltairMaidr, is_altair_chart
from maidr.api import _is_altair_chart


class TestIsAltairChart:
    def test_altair_chart(self):
        chart = alt.Chart(pd.DataFrame({"x": [1]})).mark_point()
        assert is_altair_chart(chart)
        assert _is_altair_chart(chart)

    def test_layer_chart(self):
        df = pd.DataFrame({"x": [1], "y": [2]})
        c1 = alt.Chart(df).mark_point().encode(x="x:Q", y="y:Q")
        c2 = alt.Chart(df).mark_line().encode(x="x:Q", y="y:Q")
        assert is_altair_chart(c1 + c2)

    def test_non_altair(self):
        assert not is_altair_chart("not a chart")
        assert not is_altair_chart(42)
        assert not is_altair_chart(None)


class TestAltairMaidrSchema:
    def test_bar_schema_structure(self):
        df = pd.DataFrame({"x": ["A", "B"], "y": [10, 20]})
        chart = alt.Chart(df).mark_bar().encode(x="x:N", y="y:Q")

        m = AltairMaidr(chart)
        schema = m._flatten_maidr()

        assert "id" in schema
        assert "subplots" in schema
        assert len(schema["subplots"]) == 1
        assert len(schema["subplots"][0]) == 1

        cell = schema["subplots"][0][0]
        assert "id" in cell
        assert "layers" in cell
        assert len(cell["layers"]) == 1

        layer = cell["layers"][0]
        assert "type" in layer
        assert "title" in layer
        assert "axes" in layer
        assert "data" in layer

    def test_layer_chart_schema(self):
        df = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
        c1 = alt.Chart(df).mark_point().encode(x="x:Q", y="y:Q")
        c2 = alt.Chart(df).mark_line().encode(x="x:Q", y="y:Q")
        chart = c1 + c2

        m = AltairMaidr(chart)
        schema = m._flatten_maidr()

        cell = schema["subplots"][0][0]
        assert len(cell["layers"]) == 2


class TestAltairMaidrSaveHtml:
    def test_save_html(self):
        df = pd.DataFrame({"x": ["A", "B"], "y": [10, 20]})
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(x="x:N", y="y:Q")
            .properties(title="Test Bar")
        )

        m = AltairMaidr(chart)
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.html")
            result = m.save_html(filepath)

            assert os.path.exists(result)
            with open(result, "r", encoding="utf-8") as f:
                html_content = f.read()

            # Check that MAIDR JS is referenced
            assert "maidr" in html_content.lower()
            # Check that SVG is embedded
            assert "<svg" in html_content


class TestAltairMaidrRender:
    def test_render_returns_tag(self):
        df = pd.DataFrame({"x": [1, 2], "y": [3, 4]})
        chart = alt.Chart(df).mark_point().encode(x="x:Q", y="y:Q")

        m = AltairMaidr(chart)
        tag = m.render()

        assert tag is not None
        html_str = str(tag.get_html_string())
        assert "maidr" in html_str.lower()
