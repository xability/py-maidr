"""
Every iframed render names its frame (#453).

An ``iframe`` with no ``title`` is announced as an unnamed frame, so a screen
reader user arriving at a chart is told a frame is there and nothing else --
not that it holds a chart, and on a page of several, not which one. Every
notebook, Shiny and Flask render goes through one of these two wrappers, so
these are the two places that decide it.

The name is asserted on the rendered HTML rather than on the helper alone,
because the helper returning the right string is not the claim -- the claim is
that the attribute reaches the tag.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest
from htmltools import tags

from maidr.util.iframe_utils import (
    chart_title_of,
    iframe_title,
    wrap_in_iframe_matplotlib,
    wrap_in_iframe_plotly,
)

WRAPPERS = (wrap_in_iframe_matplotlib, wrap_in_iframe_plotly)


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _html(tag) -> str:
    return str(tag.get_html_string())


class TestTheFrameIsNamed:
    """The attribute reaches the tag, by both wrappers."""

    @pytest.mark.parametrize("wrap", WRAPPERS)
    def test_a_titled_chart_names_its_frame_after_itself(self, wrap) -> None:
        rendered = _html(wrap(tags.div("chart"), "Body mass by species"))

        # The chart's own title leads, because that is the part that tells one
        # frame from the next on a page carrying several.
        assert 'title="Body mass by species, accessible chart"' in rendered

    @pytest.mark.parametrize("wrap", WRAPPERS)
    def test_an_untitled_chart_still_names_its_frame(self, wrap) -> None:
        rendered = _html(wrap(tags.div("chart")))

        # Falling back to no name at all is the bug; the bare label at least
        # says what kind of thing the frame is.
        assert 'title="Accessible chart"' in rendered

    @pytest.mark.parametrize("wrap", WRAPPERS)
    def test_the_name_is_never_empty(self, wrap) -> None:
        for chart_title in (None, "", "   ", "\n\t"):
            rendered = _html(wrap(tags.div("chart"), chart_title))
            assert 'title=""' not in rendered
            assert "title=" in rendered


class TestTheNameIsBuilt:
    """What :func:`iframe_title` makes of a title."""

    def test_whitespace_counts_as_no_title(self) -> None:
        # Matching the MAIDR engine's trimmed "authored" check, so a chart
        # titled `"   "` is not announced as `"   , accessible chart"`.
        assert iframe_title("   ") == "Accessible chart"
        assert iframe_title("\n\t") == "Accessible chart"
        assert iframe_title(None) == "Accessible chart"
        assert iframe_title("") == "Accessible chart"

    def test_a_title_is_not_trimmed_away_from_the_middle(self) -> None:
        assert iframe_title("  Two words  ") == "Two words, accessible chart"


class TestTheTitleIsReadOffTheSchema:
    """:func:`chart_title_of` against the shapes a renderer emits."""

    def test_a_figure_level_title_wins(self) -> None:
        schema = {
            "title": "Two panels",
            "subplots": [[{"layers": [{"title": "Left"}, {"title": "Right"}]}]],
        }

        assert chart_title_of(schema) == "Two panels"

    def test_one_shared_layer_title_is_the_figure_name(self) -> None:
        # `ax.set_title()` is the commoner spelling and lands on the layer,
        # so a one-axes figure has no figure-level title to read.
        schema = {"subplots": [[{"layers": [{"title": "Body mass"}]}]]}

        assert chart_title_of(schema) == "Body mass"

    def test_panels_titled_differently_have_no_one_name(self) -> None:
        # Naming the frame after the first panel would name it after a part
        # of what it holds.
        schema = {
            "subplots": [
                [{"layers": [{"title": "Left"}]}, {"layers": [{"title": "Right"}]}]
            ]
        }

        assert chart_title_of(schema) == ""

    def test_layers_agreeing_on_a_title_still_name_the_figure(self) -> None:
        # Two layers on one axes share that axes' title, which is a name for
        # the figure rather than a disagreement.
        schema = {
            "subplots": [[{"layers": [{"title": "Sales"}, {"title": "Sales"}]}]]
        }

        assert chart_title_of(schema) == "Sales"

    def test_an_untitled_figure_reads_as_no_title(self) -> None:
        schema = {"subplots": [[{"layers": [{"title": ""}]}]]}

        assert chart_title_of(schema) == ""

    def test_a_schema_keyed_by_the_enum_reads_the_same(self) -> None:
        # The Plotly renderer keys its top level with `MaidrKey.TITLE` rather
        # than the plain string, and this reads it only because `MaidrKey`
        # subclasses `str` and so hashes equal to its value. Pinned because
        # the failure would be silent: an enum that stopped subclassing `str`
        # would leave every Plotly frame named "Accessible chart" with
        # nothing raising.
        from maidr.core.enum.maidr_key import MaidrKey

        assert chart_title_of({MaidrKey.TITLE: "Revenue"}) == "Revenue"

    def test_a_schema_missing_the_keys_does_not_raise(self) -> None:
        # The renderers build this dict themselves, but a name is not worth
        # failing a whole render over.
        assert chart_title_of({}) == ""
        assert chart_title_of({"subplots": []}) == ""
        assert chart_title_of({"subplots": [[{}]]}) == ""


class TestTheRenderedChartCarriesItsName:
    """End to end, through the matplotlib renderer that builds the schema."""

    def test_a_titled_figure_reaches_the_frame(self) -> None:
        from maidr.core.figure_manager import FigureManager

        fig, ax = plt.subplots()
        ax.bar(["a", "b"], [1, 2])
        ax.set_title("Body mass by species")

        schema = FigureManager.figs[fig]._flatten_maidr()

        # The title the frame is named with is the one the chart announces,
        # which is what keeps a reader's search for it from failing.
        assert chart_title_of(schema) == "Body mass by species"
        assert (
            iframe_title(chart_title_of(schema))
            == "Body mass by species, accessible chart"
        )

    def test_a_suptitle_reaches_the_frame(self) -> None:
        from maidr.core.figure_manager import FigureManager

        fig, axs = plt.subplots(1, 2)
        axs[0].bar(["a"], [1])
        axs[1].bar(["b"], [2])
        fig.suptitle("Two panels")

        schema = FigureManager.figs[fig]._flatten_maidr()

        assert chart_title_of(schema) == "Two panels"
