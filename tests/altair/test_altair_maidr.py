"""Tests for AltairMaidr end-to-end (bindVegaLite flow).

The Altair adapter no longer pre-renders SVG on the Python side. It embeds
the Vega-Lite spec into an iframe that loads ``vegalite.js`` and calls
``window.maidrVegaLite.embed(container, spec, options)``. These tests
assert the *shape* of the emitted HTML rather than the legacy SVG/MAIDR
JSON pipeline.
"""

import json
import os
import tempfile

import pandas as pd
import pytest

altair = pytest.importorskip("altair")
import altair as alt  # noqa: E402

from maidr.altair import AltairMaidr, is_altair_chart  # noqa: E402
from maidr.altair.altair_maidr import (  # noqa: E402
    _VEGA_CDN,
    _VEGA_EMBED_CDN,
    _VEGA_LITE_CDN,
)
from maidr.util.dependencies import (  # noqa: E402
    MAIDR_VEGALITE_FILENAME,
    cdn_url,
)
from maidr.api import _is_altair_chart  # noqa: E402


def _simple_chart() -> alt.Chart:
    df = pd.DataFrame({"x": ["A", "B"], "y": [10, 20]})
    return alt.Chart(df).mark_bar().encode(x="x:N", y="y:Q")


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


class TestRenderEmbedsSpec:
    def test_iframe_contains_spec_json(self):
        m = AltairMaidr(_simple_chart())
        html_str = str(m._build_inner_html().get_html_string())

        # The spec should be embedded as a JSON.parse(...) payload. The
        # spec_json string is double-JSON-encoded (json.dumps wrap) inside
        # JSON.parse, so we just look for distinctive content.
        assert "JSON.parse" in html_str
        assert "mark" in html_str  # spec key
        assert "encoding" in html_str  # spec key

    def test_iframe_loads_vega_stack_in_order(self):
        m = AltairMaidr(_simple_chart())
        html_str = str(m._build_inner_html().get_html_string())

        # All four script srcs must be present.
        maidr_vegalite_cdn = cdn_url(MAIDR_VEGALITE_FILENAME)
        assert _VEGA_CDN in html_str
        assert _VEGA_LITE_CDN in html_str
        assert _VEGA_EMBED_CDN in html_str
        assert maidr_vegalite_cdn in html_str

        # Order matters: vega before vega-lite before vega-embed before
        # vegalite.js (peer-dep load order).
        idx_vega = html_str.index(_VEGA_CDN)
        idx_vl = html_str.index(_VEGA_LITE_CDN)
        idx_ve = html_str.index(_VEGA_EMBED_CDN)
        idx_maidr = html_str.index(maidr_vegalite_cdn)
        assert idx_vega < idx_vl < idx_ve < idx_maidr

    def test_vegalite_src_carries_the_resolved_version(self):
        """Guard against a tautology.

        Asserting ``cdn_url(...) in html`` is vacuous under the suite's
        ``MAIDR_CDN_VERSION=latest`` fixture, since both sides collapse to
        ``@latest`` whether or not the adapter participates in version
        resolution. Pin a concrete version so the assertion can fail.
        """
        import maidr

        maidr.set_cdn_version("3.74.0")
        try:
            m = AltairMaidr(_simple_chart())
            html_str = str(m._build_inner_html().get_html_string())
        finally:
            maidr.set_cdn_version(None)

        assert "maidr@3.74.0/dist/vegalite.js" in html_str
        # vegalite.js resolves maidr-math.css against its own CDN URL, so
        # the adapter links no stylesheet of its own.
        assert "dist/maidr.css" not in html_str
        assert "maidr@latest" not in html_str

    def test_iframe_calls_maidrvegalite_embed_with_id(self):
        m = AltairMaidr(_simple_chart())
        html_str = str(m._build_inner_html().get_html_string())

        # The bootstrap script must call window.maidrVegaLite.embed and
        # pass the same UUID we generated.
        assert "window.maidrVegaLite.embed" in html_str
        assert m._maidr_id in html_str
        assert m._container_id in html_str

    def test_render_returns_tag(self):
        m = AltairMaidr(_simple_chart())
        tag = m.render()
        assert tag is not None
        # render() may wrap in iframe; either way the maidr UUID is present.
        html_str = str(tag.get_html_string())
        assert m._maidr_id in html_str


class TestSaveHtml:
    def test_save_html_writes_self_contained_file(self):
        m = AltairMaidr(_simple_chart())
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.html")
            result = m.save_html(filepath)

            assert os.path.exists(result)
            with open(result, "r", encoding="utf-8") as f:
                html_content = f.read()

            # Key invariants: the spec is embedded and the maidrVegaLite
            # adapter script is referenced.
            assert "maidrVegaLite" in html_content
            assert cdn_url(MAIDR_VEGALITE_FILENAME) in html_content
            assert m._maidr_id in html_content


class TestSpecSafety:
    def test_spec_with_script_close_tag_is_escaped(self):
        # A title containing ``</script>`` would break the page if not
        # escaped by ``_spec_to_safe_json``.
        df = pd.DataFrame({"x": ["A"], "y": [1]})
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(x="x:N", y="y:Q")
            .properties(title="evil </script><script>alert(1)</script>")
        )
        m = AltairMaidr(chart)
        html_str = str(m._build_inner_html().get_html_string())

        # The literal ``</script>`` from the title must NOT appear
        # un-escaped inside the embedded JSON payload context. Note: the
        # surrounding HTML has its own real ``</script>`` close tag for
        # the bootstrap; assert the *escaped* form exists.
        assert "<\\/script>" in html_str or "<\\\\/script>" in html_str

    def test_spec_round_trips_through_json(self):
        from maidr.altair.altair_maidr import _spec_to_safe_json

        spec = {"mark": "bar", "title": "hello", "value": 1}
        encoded = _spec_to_safe_json(spec)
        decoded = json.loads(encoded)
        assert decoded == spec


class TestTheFrameIsNamed:
    """An Altair frame is named after its chart (#453).

    Altair builds no MAIDR schema on the Python side -- the JS adapter reads
    the Vega-Lite spec -- so the name is read off the spec instead, and this
    covers the three ways Vega-Lite spells a title.
    """

    def _renderer(self, chart):
        return AltairMaidr(chart)

    def test_a_bare_string_title(self):
        chart = _simple_chart().properties(title="Sales by region")

        assert self._renderer(chart)._spec_title() == "Sales by region"

    def test_a_title_object(self):
        chart = _simple_chart().properties(
            title=alt.Title("Sales by region", subtitle="2026")
        )

        # `alt.Title` emits `{"text": ...}`, and the subtitle is not part of
        # the name -- the frame is named after the chart, not described by it.
        assert self._renderer(chart)._spec_title() == "Sales by region"

    def test_a_multi_line_title(self):
        chart = _simple_chart().properties(title=["Sales by region", "2026"])

        # Joined rather than truncated: the first line alone may not be the
        # name a reader is looking for.
        assert self._renderer(chart)._spec_title() == "Sales by region 2026"

    def test_no_title(self):
        assert self._renderer(_simple_chart())._spec_title() == ""

    def test_the_name_reaches_the_frame(self):
        from htmltools import tags

        renderer = self._renderer(_simple_chart().properties(title="Sales by region"))
        rendered = str(renderer._wrap_in_iframe(tags.div("chart")).get_html_string())

        assert 'title="Sales by region, accessible chart"' in rendered

    def test_an_untitled_chart_still_names_its_frame(self):
        from htmltools import tags

        rendered = str(
            self._renderer(_simple_chart())
            ._wrap_in_iframe(tags.div("chart"))
            .get_html_string()
        )

        assert 'title="Accessible chart"' in rendered
