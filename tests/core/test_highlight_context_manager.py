"""``HighlightContextManager`` resolves a drawn artist to its selector by lookup.

Each artist ``draw`` asks the manager which selector, if any, the artist
belongs to. That used to be a scan of the render's tagged list -- ``in``
followed by ``index`` -- so a render with *n* tagged artists cost *n*
squared comparisons, 2 s of a 5 s render at 5000 bars (#695). It is now a
dict keyed by ``id(artist)``, which is what the scan was testing anyway:
``Artist`` has no ``__eq__``.

The rules the scan enforced have to survive the change, and these tests
state them: an artist tagged twice keeps its *first* selector (#376), an
artist never tagged is left alone, and a rendered chart carries exactly one
``maidr`` attribute per bar, with the layer's selector on each. One test
pins the change itself: resolving an artist no longer compares it against
the others, which is the scan that made a render quadratic.
"""

from __future__ import annotations

import re

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pytest  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

import maidr  # noqa: F401,E402  # activates patches
from maidr.core.context_manager import HighlightContextManager  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    """Close every figure a test opened, so state cannot leak between them."""
    yield
    plt.close("all")


def test_resolving_an_artist_does_not_compare_it_against_the_rest():
    """The lookup is by ``id``, so no tagged artist is ever asked ``__eq__``.

    A list scan asks every earlier artist to compare itself to the one being
    drawn -- twice, once for ``in`` and once for ``index`` -- which is the
    quadratic cost of #695. Counting those calls fails on the scan and passes
    on the dict, without timing anything on a shared machine.
    """

    class Counting:
        comparisons = 0

        def __eq__(self, other):
            Counting.comparisons += 1
            return self is other

    tagged = [Counting() for _ in range(100)]
    selectors = [f"selector-{i}" for i in range(100)]

    with HighlightContextManager.set_maidr_elements(tagged, selectors):
        with HighlightContextManager.set_maidr_element(tagged[-1], "gid-last"):
            assert HighlightContextManager.get_selector_id("gid-last") == (
                "selector-99"
            )

    assert Counting.comparisons == 0, (
        f"the lookup compared the drawn artist against {Counting.comparisons} "
        "others -- that is a list scan, not a dict lookup"
    )


def test_an_artist_tagged_twice_keeps_its_first_selector():
    """``list.index`` parity: the first listing wins, which #376 relies on."""
    shared = Rectangle((0, 0), 1, 1)
    other = Rectangle((1, 0), 1, 1)

    with HighlightContextManager.set_maidr_elements(
        [shared, other, shared], ["first", "second", "third"]
    ):
        with HighlightContextManager.set_maidr_element(shared, "gid-shared"):
            assert HighlightContextManager.get_selector_id("gid-shared") == "first"
        with HighlightContextManager.set_maidr_element(other, "gid-other"):
            assert HighlightContextManager.get_selector_id("gid-other") == "second"


def test_an_artist_that_was_never_tagged_is_left_alone():
    tagged = Rectangle((0, 0), 1, 1)
    untagged = Rectangle((1, 0), 1, 1)

    with HighlightContextManager.set_maidr_elements([tagged], ["only"]):
        with HighlightContextManager.set_maidr_element(untagged, "gid-untagged"):
            assert not HighlightContextManager.is_maidr_element("gid-untagged")
        # Leaving the draw removes the entry again, so a gid is only ever
        # resolvable while its artist is being written.
        with HighlightContextManager.set_maidr_element(tagged, "gid-tagged"):
            assert HighlightContextManager.is_maidr_element("gid-tagged")
        assert not HighlightContextManager.is_maidr_element("gid-tagged")


def test_a_mismatched_elements_and_selectors_pair_is_refused():
    """``zip`` would drop the tail silently; the old indexing raised."""
    elements = [Rectangle((0, 0), 1, 1), Rectangle((1, 0), 1, 1)]

    with pytest.raises(ValueError, match=r"2 elements .* 1 selector"):
        with HighlightContextManager.set_maidr_elements(elements, ["only"]):
            pass  # pragma: no cover - never entered


def test_outside_a_render_nothing_is_tagged():
    """The class-wide ``draw`` patch runs for every figure, rendered or not."""
    with HighlightContextManager.set_maidr_element(Rectangle((0, 0), 1, 1), "gid"):
        assert not HighlightContextManager.is_maidr_element("gid")


def test_a_rendered_bar_chart_carries_one_selector_per_bar():
    """End to end: each bar's ``<g>`` gets the layer's selector, and only those."""
    fig, ax = plt.subplots()
    bars = ax.bar(["a", "b", "c", "d"], [1, 2, 3, 4])

    chart = FigureManager.get_maidr(fig)
    html = str(chart._create_html_tag(use_iframe=False, use_cdn=True))

    (selector_id,) = chart.selector_ids
    tagged = re.findall(r'<g id="([^"]+)" maidr="([^"]+)"', html)

    assert [gid for gid, _ in tagged] == [
        bar.get_gid() for bar in bars
    ], "every bar, in draw order, and nothing else"
    assert {selector for _, selector in tagged} == {selector_id}
