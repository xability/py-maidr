"""A Bokeh chart sized by its container fills a notebook's frame.

maidr.js puts a chart in an element as wide as what it holds
(``width: fit-content``), and a plot whose ``sizing_mode`` stretches or
scales its width shrank to its smallest width in it: 73px. In a notebook's
frame such a chart is marked, and ``maidr/assets/frame.css`` makes the
element as wide as the frame for it; a chart of a fixed width is left alone.
"""

from __future__ import annotations

import html as html_module

import pytest

bokeh_plotting = pytest.importorskip("bokeh.plotting")

import maidr  # noqa: E402
from maidr.bokeh.bokeh_maidr import BokehMaidr  # noqa: E402
from maidr.util.environment import Environment  # noqa: E402


def _bar(**kwargs):
    fig = bokeh_plotting.figure(x_range=["Q1", "Q2", "Q3"], **kwargs)
    fig.vbar(x=["Q1", "Q2", "Q3"], top=[5, 7, 3], width=0.8)
    return fig


@pytest.mark.parametrize(
    "kwargs, fills",
    [
        ({"sizing_mode": "stretch_width", "height": 300}, True),
        ({"sizing_mode": "stretch_both"}, True),
        ({"sizing_mode": "scale_width", "width": 400, "height": 300}, True),
        ({"sizing_mode": "scale_both", "width": 400, "height": 300}, True),
        ({"width_policy": "max", "height": 300}, True),
        ({"width": 400, "height": 300}, False),
        ({"sizing_mode": "stretch_height", "width": 400}, False),
        ({"sizing_mode": "fixed", "width": 400, "height": 300}, False),
        ({}, False),
    ],
)
def test_which_charts_take_the_width_of_their_container(kwargs, fills):
    assert BokehMaidr(_bar(**kwargs))._fills_width() is fills


def test_in_a_notebook_a_stretched_chart_is_marked(monkeypatch):
    monkeypatch.setattr(Environment, "is_notebook", staticmethod(lambda: True))

    stretched = html_module.unescape(
        str(maidr.render(_bar(sizing_mode="stretch_width", height=300)))
    )
    fixed = html_module.unescape(str(maidr.render(_bar(width=400, height=300))))

    assert 'class="maidr-frame-fill"' in stretched
    assert 'class="maidr-frame-fill"' not in fixed
    assert "var fitsOutput = true;" in fixed
    # Clear of the output area's padding, as Bokeh's own HTML output is.
    assert "var keepsPadding = true;" in fixed
