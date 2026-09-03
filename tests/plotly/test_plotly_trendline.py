"""A plotly trendline was announced as one more series of the user's data.

``px.scatter(..., trendline="ols")`` appends a second ``scatter`` trace
carrying the fit. Nothing structural separates it from a line the user drew:
same ``type``, same ``mode``, no ``name``, the scatter's own marker colour. So
it was merged into the multi-line layer and read as data, and a blind reader
was told a model's prediction was a measurement -- the remaining sub-item of
#343, after the candlestick and violin halves.

The one thing that separates it is ``hovertemplate``, a display string.
Reading a display string is weaker than reading ``stackgroup``, and it is what
this package already does for the same question: ``SMOOTH_KEYWORDS`` has
matched a matplotlib artist's ``label`` -- equally a display string, equally
user-settable -- to find seaborn's regression lines since long before the
plotly path existed.

The four selectors this emits were resolved against real Plotly.js output in
Chromium: 4 of 4 matched exactly one element, across a lone trendline and a
pair fitted per colour group.
"""

from __future__ import annotations

import pytest

pytest.importorskip("plotly")
pd = pytest.importorskip("pandas")

import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402
from maidr.plotly.trendline import is_trendline_trace  # noqa: E402

FRAME = pd.DataFrame(
    {
        "x": list(range(1, 11)),
        "y": [1, 3, 2, 5, 4, 7, 6, 9, 8, 11],
        "g": ["a"] * 5 + ["b"] * 5,
    }
)


def layers(fig) -> list[dict]:
    return PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"]


def types(fig) -> list:
    return [layer["type"] for layer in layers(fig)]


def trendline_of(fig) -> dict:
    found = [layer for layer in layers(fig) if layer["type"] == PlotType.SMOOTH]
    assert len(found) == 1, f"expected one smooth layer, got {len(found)}"
    return found[0]


class TestEveryTrendlineModeIsRecognised:
    @pytest.mark.parametrize(
        ("kind", "options"),
        [
            ("ols", None),
            ("lowess", None),
            ("rolling", {"window": 3}),
            ("ewm", {"halflife": 2}),
            ("expanding", None),
        ],
    )
    def test_a_fit_becomes_a_smooth_layer(self, kind, options):
        # All five modes `px` offers. Each writes its own name into the
        # template -- "OLS", "LOWESS", "Rolling mean", "Exponentially
        # Weighted mean", "Expanding mean" -- so the rule has to match the
        # shape they share rather than any one of those names.
        extra = {"trendline_options": options} if options else {}
        fig = px.scatter(FRAME, x="x", y="y", trendline=kind, **extra)
        assert PlotType.SMOOTH in types(fig)

    def test_the_scattered_data_is_still_its_own_layer(self):
        # The fit is separated *from* the data, not instead of it. A reader
        # navigates the measurements and the model as two things.
        fig = px.scatter(FRAME, x="x", y="y", trendline="ols")
        assert sorted(str(t) for t in types(fig)) == [
            str(PlotType.SCATTER),
            str(PlotType.SMOOTH),
        ]

    def test_the_fit_carries_its_own_points(self):
        fig = px.scatter(FRAME, x="x", y="y", trendline="ols")
        data = trendline_of(fig)["data"]
        assert len(data) == 1
        assert len(data[0]) == len(FRAME)


class TestOneLayerHoldsEveryFit:
    def test_a_fit_per_colour_group_shares_a_layer(self):
        # `color=` fits one trend per group. They are the same kind of thing
        # and are navigated together, exactly as the multi-line layer holds
        # the series they were fitted to.
        fig = px.scatter(FRAME, x="x", y="y", color="g", trendline="ols")
        data = trendline_of(fig)["data"]
        assert len(data) == 2
        assert [len(series) for series in data] == [5, 5]

    def test_each_fit_addresses_its_own_element(self):
        # Measured in Chromium: the two fits are declared second and fourth
        # among the subplot's scatter traces, and both selectors resolve to
        # exactly one element there.
        fig = px.scatter(FRAME, x="x", y="y", color="g", trendline="ols")
        selectors = trendline_of(fig)["selectors"]
        assert len(selectors) == 2
        assert "nth-child(2)" in selectors[0]
        assert "nth-child(4)" in selectors[1]

    def test_a_lone_fit_is_still_scoped_by_position(self):
        # Not left to the unscoped single-line form, which would also match
        # the scatter's own elements.
        fig = px.scatter(FRAME, x="x", y="y", trendline="ols")
        selectors = trendline_of(fig)["selectors"]
        assert len(selectors) == 1
        assert "nth-child(2)" in selectors[0]


class TestAFitNeverSharesALayerWithData:
    def test_a_line_and_a_fit_are_two_layers(self):
        # A layer carries one type for every series it holds, so a fit
        # sharing a layer with the lines beside it could only be `line` or
        # make them all `smooth`. Split before either branch sees the group.
        fig = go.Figure(
            [
                go.Scatter(x=[1, 2, 3], y=[1, 2, 3], mode="lines", name="data"),
                go.Scatter(
                    x=[1, 2, 3],
                    y=[1, 2, 3],
                    mode="lines",
                    hovertemplate="<b>OLS trendline</b><br>y = x",
                ),
            ]
        )
        found = layers(fig)
        assert [layer["type"] for layer in found] == [
            PlotType.LINE,
            PlotType.SMOOTH,
        ]

    def test_the_line_beside_a_fit_keeps_its_own_element(self):
        fig = go.Figure(
            [
                go.Scatter(x=[1, 2, 3], y=[1, 2, 3], mode="lines", name="data"),
                go.Scatter(
                    x=[1, 2, 3],
                    y=[1, 2, 3],
                    mode="lines",
                    hovertemplate="<b>OLS trendline</b><br>y = x",
                ),
            ]
        )
        found = layers(fig)
        assert "nth-child(1)" in found[0]["selectors"][0]
        assert "nth-child(2)" in found[1]["selectors"][0]


class TestOrdinaryLinesAreLeftAlone:
    def test_a_px_line_is_a_line(self):
        assert types(px.line(FRAME, x="x", y="y")) == [PlotType.LINE]

    def test_a_hand_built_line_is_a_line(self):
        fig = go.Figure([go.Scatter(x=[1, 2, 3], y=[1, 2, 3], mode="lines")])
        assert types(fig) == [PlotType.LINE]

    def test_a_scatter_without_a_trendline_grows_no_smooth_layer(self):
        assert PlotType.SMOOTH not in types(px.scatter(FRAME, x="x", y="y"))


class TestTheRuleIsNarrowerThanAKeywordScan:
    """What the detector will and will not accept, asked directly.

    The risk of reading a display string is a false positive on prose the
    user wrote. Matching plotly's generated *shape* rather than scanning for
    a word is what bounds it, so the boundary is pinned here rather than
    left to be discovered by someone whose chart got reclassified.
    """

    @pytest.mark.parametrize(
        "template",
        [
            "<b>OLS trendline</b><br>y = 1.02857 * x + 0.0666667",
            "<b>LOWESS trendline</b><br><br>x=%{x}",
            "<b>Rolling mean trendline</b><br><br>x=%{x}",
            "<b>Exponentially Weighted mean trendline</b><br>",
            "<b>Expanding mean trendline</b><br>",
        ],
    )
    def test_plotlys_own_templates_match(self, template):
        assert is_trendline_trace({"hovertemplate": template}) is True

    def test_the_match_is_case_insensitive(self):
        assert is_trendline_trace({"hovertemplate": "<b>OLS TRENDLINE</b>"}) is True

    @pytest.mark.parametrize(
        "template",
        [
            # Prose a user might write about their own chart. None of these is
            # a request to reclassify it.
            "This is the line of best fit",
            "Regression: y = 2x",
            "x=%{x}<br>y=%{y}",
            "<b>Sales</b><br>x=%{x}",
            # The word, but not where plotly puts it -- so not plotly's.
            "x=%{x}<br>see the trendline above",
            # Bold, but the segment is not the whole opening of the template.
            "prefix <b>OLS trendline</b>",
        ],
    )
    def test_prose_does_not_match(self, template):
        assert is_trendline_trace({"hovertemplate": template}) is False

    def test_a_trace_with_no_template_does_not_match(self):
        assert is_trendline_trace({}) is False

    def test_a_non_string_template_does_not_match(self):
        # `to_dict()` can carry a list when the template is set per point.
        assert is_trendline_trace({"hovertemplate": ["<b>OLS trendline</b>"]}) is False
