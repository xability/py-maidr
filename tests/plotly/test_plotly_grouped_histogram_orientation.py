"""
A horizontal grouped plotly histogram pitched its bin position (#482).

`PlotlyGroupedHistogramPlot` declared ``orientation: "horz"`` for a horizontal
layer -- it always had -- but built every point bin-in-``x`` and count-in-``y``,
the vertical arrangement, whichever way the chart was drawn. The core read
``point.x`` as the magnitude and so pitched the bin's *centre* instead of its
count: a number belonging to nothing in the data.

That makes it the third form of one bug. r-maidr #184 declared the key without
the layout and py-maidr #480 emitted the layout without the key -- both went
silent, because the magnitude field held a category name. This one declared the
key *and* a layout contradicting it, so instead of falling silent it announced
the wrong number confidently.

The single-histogram class swaps correctly, and a grouped layer emits
``stacked_bar`` / ``dodged_bar``, so it is in the bar family and reads by the
same rule: ``horz`` means the magnitude is in ``x``.

Bin centres near 10 and 50 against counts of 6 and 0, so no value here can be
mistaken for the other kind.
"""

from __future__ import annotations

import warnings

import pytest

plotly = pytest.importorskip("plotly")
import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.maidr_key import MaidrKey  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

warnings.filterwarnings("ignore")

# Six observations at 10, two at 50 -- and a second series with a different
# split, so a stack has something to stack.
FIRST = [10] * 6 + [50] * 2
SECOND = [10] * 3 + [50] * 5

BIN_CENTRE = 9.5
FIRST_COUNT = 6


def _grouped(horizontal: bool, barmode: str = "stack"):
    axis = "y" if horizontal else "x"
    fig = go.Figure(
        [
            go.Histogram(**{axis: FIRST}, name="u"),
            go.Histogram(**{axis: SECOND}, name="v"),
        ]
    )
    fig.update_layout(barmode=barmode)
    return fig


def _single(horizontal: bool):
    axis = "y" if horizontal else "x"
    return go.Figure(go.Histogram(**{axis: FIRST}))


def _layer(fig) -> dict:
    schema = PlotlyMaidr(fig)._flatten_maidr()
    layer = schema["subplots"][0][0]["layers"][0]
    return {str(getattr(key, "value", key)): value for key, value in layer.items()}


def _first_point(layer: dict) -> dict:
    points = layer["data"]
    if points and isinstance(points[0], list):
        points = points[0]
    return {str(getattr(key, "value", key)): value for key, value in points[0].items()}


@pytest.mark.parametrize("barmode", ["stack", "group"])
class TestTheLayoutFollowsTheDeclaration:
    def test_a_horizontal_group_puts_the_count_in_x(self, barmode) -> None:
        # The defect: `x` held 9.5, the bin's centre, and the core pitched it.
        point = _first_point(_layer(_grouped(True, barmode)))

        assert point["x"] == FIRST_COUNT
        assert point["y"] == BIN_CENTRE

    def test_a_vertical_group_is_unchanged(self, barmode) -> None:
        point = _first_point(_layer(_grouped(False, barmode)))

        assert point["x"] == BIN_CENTRE
        assert point["y"] == FIRST_COUNT

    def test_the_orientation_key_still_says_which(self, barmode) -> None:
        # It was always declared; what changed is that the points now agree.
        key = str(MaidrKey.ORIENTATION.value)

        assert _layer(_grouped(True, barmode)).get(key) == "horz"
        assert _layer(_grouped(False, barmode)).get(key) == "vert"


class TestItAgreesWithTheSingleHistogram:
    @pytest.mark.parametrize(
        "horizontal", [True, False], ids=["horizontal", "vertical"]
    )
    def test_both_classes_put_the_count_in_the_same_field(self, horizontal) -> None:
        # One chart written two ways must read the same way. The single class
        # was right all along, so it is the reference rather than a second
        # opinion.
        single = _first_point(_layer(_single(horizontal)))
        grouped = _first_point(_layer(_grouped(horizontal)))

        magnitude_field = "x" if horizontal else "y"
        category_field = "y" if horizontal else "x"

        assert single[magnitude_field] == grouped[magnitude_field] == FIRST_COUNT
        assert single[category_field] == grouped[category_field] == BIN_CENTRE


class TestTheOtherFieldsSurvive:
    def test_the_series_label_is_kept_through_the_swap(self) -> None:
        # The swap rebuilds each point, so anything it does not name would be
        # dropped -- and `z` is what tells the two series apart.
        point = _first_point(_layer(_grouped(True)))

        assert point["z"] == "u"

    def test_every_point_is_swapped_not_just_the_first(self) -> None:
        layer = _layer(_grouped(True))
        counts = {int(p[str(MaidrKey.X.value)]) for p in layer["data"][0]}

        # Counts, not bin centres: 9.5 and 29.5 are not integers, so a point
        # left unswapped could not produce this set.
        assert counts <= {0, 2, 3, 5, 6}
