"""Each statistic of a plotly box names a mark of its own.

Plotly draws a box -- its median, its body, both whiskers and both caps -- as
one ``path.box``, and every statistic named that path. So Minimum, 25%, 50%,
75% and Maximum all outlined the whole box and the outline never showed which
of them was being read, as an audit that drove every example with the
keyboard found. The init script now draws each part again, hidden, beside
its box, and each statistic names its part.

These pin the selectors and the init script. What the parts are on a drawn
chart, and that each statistic is outlined where plotly drew it, is measured
in ``tests/browser/test_plotly_box_highlight.py``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("plotly")
np = pytest.importorskip("numpy")

import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

STATISTICS = ("min", "q1", "q2", "q3", "max", "iq")
VALUES = list(np.random.default_rng(3).normal(0, 1, 45))


@pytest.fixture(autouse=True)
def _no_cdn_lookup(monkeypatch):
    """Keep a render from resolving the published maidr.js version online."""
    monkeypatch.setenv("MAIDR_CDN_VERSION", "latest")


def _selectors(fig: go.Figure) -> list[dict]:
    (plot,) = PlotlyMaidr(fig)._plots
    return plot.schema[MaidrKey.SELECTOR]


def _init_script(fig: go.Figure) -> str:
    html = str(
        PlotlyMaidr(fig)._create_html_tag(use_iframe=False, use_cdn=False)
        .get_html_string()
    )
    start = html.index("var maidrSchema = ")
    return html[start : html.index("})();", start)]


def test_every_statistic_names_a_part_of_its_own():
    fig = go.Figure(
        go.Box(x=["a"] * 15 + ["b"] * 15 + ["c"] * 15, y=VALUES, name="t")
    )

    for position, selector in enumerate(_selectors(fig), start=1):
        for statistic in STATISTICS:
            assert selector[statistic] == (
                ".subplot.xy .boxlayer > g:nth-child(1) > "
                f'[data-maidr-box-part="{position} {statistic}"]'
            )


def test_the_outliers_still_name_the_points_plotly_drew():
    fig = go.Figure(go.Box(y=[-100, 1, 2, 3, 4, 5, 6, 7, 8, 100], name="o"))

    (selector,) = _selectors(fig)

    assert selector["lowerOutliers"] == [
        ".subplot.xy .boxlayer > g:nth-child(1) > :nth-child(1 of g.points)"
        " > :nth-child(-n+1 of path.point)"
    ]
    assert selector["upperOutliers"] == [
        ".subplot.xy .boxlayer > g:nth-child(1) > :nth-child(1 of g.points)"
        " > :nth-child(n+2 of path.point)"
    ]


def test_the_parts_are_drawn_before_the_payload_names_them():
    script = _init_script(go.Figure(go.Box(y=VALUES, name="b")))

    assert "function maidrSplitBoxes(svg)" in script
    assert script.index("maidrSplitBoxes(svg);") < script.index(
        "svg.setAttribute('maidr'"
    )


@pytest.mark.parametrize(
    "trace",
    [go.Bar(x=["a", "b"], y=[1, 2]), go.Violin(y=VALUES, box_visible=True)],
    ids=["bar", "violin"],
)
def test_a_figure_without_a_box_layer_draws_no_parts(trace):
    # A violin's box is a layer of its own type, which names its path whole.
    assert "maidrSplitBoxes" not in _init_script(go.Figure(trace))
