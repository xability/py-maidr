"""The MAIDR payload reaches plotly's drawn svg, after plotly has drawn it.

The init script used to wait for nothing but ``document.querySelector(
'svg.main-svg')``. That is the wrong svg whenever ``maidr.js`` runs first --
``use_cdn=False``, where the bundle is a ``<script src>`` in the head, and the
inline bundle of a Shiny or Flask frame. ``maidr.js`` then finds no payload,
adopts the plotly chart itself and moves the drawn svg out of the document
while it mounts, and the lookup lands on plotly's *other* ``svg.main-svg``:
the overlay with the hover and zoom layers and no trace. A line or step
curve reads its path once when it is built, found none there, and outlined
nothing on any keypress; the reader was also driving the chart ``maidr.js``
had adopted, not the one py-maidr described.

These pin the replacement at the level of the emitted page. That it works --
a line outlined at the point being announced -- is measured in a browser by
``tests/browser/test_plotly_line_highlight.py``.
"""

from __future__ import annotations

import re

import pytest

pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402


def _page(use_cdn: bool | str = False) -> str:
    """Render a line chart outside any iframe and return the markup."""
    fig = go.Figure(go.Scatter(x=[1, 2, 3], y=[4, 6, 5], mode="lines"))
    tag = PlotlyMaidr(fig)._create_html_tag(use_iframe=False, use_cdn=use_cdn)
    return str(tag.get_html_string())


def _graph_div_id(html: str) -> str:
    """The id ``Plotly.newPlot`` draws into."""
    match = re.search(r'Plotly\.newPlot\(\s*"([^"]+)"', html)
    assert match, "no Plotly.newPlot call in the page"
    return match.group(1)


def _init_script(html: str) -> str:
    """The script that attaches the payload."""
    start = html.index("var maidrSchema = ")
    return html[start : html.index("})();", start)]


@pytest.fixture(autouse=True)
def _no_cdn_lookup(monkeypatch):
    """Keep ``use_cdn=True`` from resolving the published version online."""
    monkeypatch.setenv("MAIDR_CDN_VERSION", "latest")


@pytest.mark.parametrize("use_cdn", [False, True, "auto"])
def test_newplot_marks_its_div_once_the_traces_are_drawn(use_cdn):
    html = _page(use_cdn)
    div_id = _graph_div_id(html)

    # Chained onto the promise newPlot returns, which plotly resolves once
    # every trace is in the DOM -- not merely once the svg exists.
    call = html[html.index("Plotly.newPlot(") :]
    then = call[: call.index("</script>")]
    assert ".then(function(){" in then
    assert f"document.getElementById('{div_id}')" in then
    assert "setAttribute('data-maidr-drawn', '')" in then
    assert "dispatchEvent(new Event('maidr:drawn'))" in then


@pytest.mark.parametrize("use_cdn", [False, True, "auto"])
def test_the_payload_waits_for_that_mark(use_cdn):
    html = _page(use_cdn)
    script = _init_script(html)

    assert f'document.getElementById("{_graph_div_id(html)}")' in script
    # Already drawn by the time the script runs -- the usual case, since
    # plotly draws synchronously -- attaches at once; otherwise the script
    # waits for the event, with a bounded fallback for a draw that fails.
    assert "if (gd.hasAttribute('data-maidr-drawn'))" in script
    assert "gd.addEventListener('maidr:drawn', initMaidr)" in script
    assert re.search(r"setTimeout\(initMaidr, \d+\)", script)
    # Attached once, however many of those fire.
    assert "if (_maidrDone) return;" in script


def test_the_svg_is_taken_from_this_charts_own_div():
    script = _init_script(_page())

    assert "(gd || document).querySelector('svg.main-svg')" in script
    # The document-wide lookup is what found plotly's overlay svg.
    assert "var svg = document.querySelector('svg.main-svg')" not in script


def test_the_chart_is_claimed_from_maidr_js_auto_detection():
    # `maidr.js` skips a plotly div carrying this attribute; without it the
    # bundle adopts the chart on its own before the payload lands.
    script = _init_script(_page())

    assert "gd.setAttribute('data-maidr-auto', '1')" in script


def test_each_render_waits_on_a_div_of_its_own():
    # Two charts in one page must not both answer to the first one's draw.
    fig = go.Figure(go.Scatter(x=[1, 2], y=[3, 4], mode="lines"))
    pm = PlotlyMaidr(fig)
    first, second = (
        str(pm._create_html_tag(use_iframe=False, use_cdn=False).get_html_string())
        for _ in range(2)
    )

    assert _graph_div_id(first) != _graph_div_id(second)
