"""An Altair chart whose width is its container's fills a notebook's frame.

vega-embed sizes a chart of ``width="container"`` to the element it is
embedded in, which maidr.js makes as wide as what it holds
(``width: fit-content``): the chart grew without end there and drew no
bars. In a notebook's frame such a chart is marked, and
``maidr/assets/frame.css`` makes the element, and vega-embed's own, as wide
as the frame for it.
"""

from __future__ import annotations

import html as html_module

import pytest

alt = pytest.importorskip("altair")
pd = pytest.importorskip("pandas")

import maidr  # noqa: E402
from maidr.altair.altair_maidr import AltairMaidr  # noqa: E402
from maidr.util.environment import Environment  # noqa: E402


def _bar(**properties):
    data = pd.DataFrame({"q": ["Q1", "Q2", "Q3"], "units": [5, 7, 3]})
    return alt.Chart(data).mark_bar().encode(x="q", y="units").properties(**properties)


@pytest.mark.parametrize(
    "properties, fills",
    [
        ({"width": "container", "height": 300}, True),
        ({"width": 400, "height": 300}, False),
        ({}, False),
    ],
)
def test_which_charts_take_the_width_of_their_container(properties, fills):
    assert AltairMaidr(_bar(**properties))._fills_width() is fills


def test_in_a_notebook_a_container_wide_chart_is_marked(monkeypatch):
    monkeypatch.setattr(Environment, "is_notebook", staticmethod(lambda: True))

    container = html_module.unescape(
        str(maidr.render(_bar(width="container", height=300)))
    )
    fixed = html_module.unescape(str(maidr.render(_bar(width=400, height=300))))

    assert 'class="maidr-frame-fill"' in container
    assert 'class="maidr-frame-fill"' not in fixed
    assert "var fitsOutput = true;" in fixed
    assert "var keepsPadding = true;" in fixed
