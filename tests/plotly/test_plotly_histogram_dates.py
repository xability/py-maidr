"""A histogram over a date column announced epoch microseconds (#699).

``px.histogram`` over a ``date_range`` reached the numeric binning as a
``datetime64`` array, and six days came out as bin bounds around
``1.704e15`` on a grid of ``1e11`` microseconds -- about 1.157 days, a width
that is in no date tick sequence of plotly's. Plotly bins a date axis by
rules of its own: a width from the date branch of ``autoTicks``, no
anti-clustering shift, date labels. None of that is ported yet, so a temporal
sample forms no layer -- what #636 settled for every other reading this
cannot make right, and what the two-dimensional path already does with one --
rather than announcing numbers that are nowhere on the chart.

A list of ``Timestamp`` objects took a different wrong turn: it failed the
float coercion and was counted as *categories*, one bar per instant.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

plotly = pytest.importorskip("plotly")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.histogram import is_temporal_sample  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402

DAYS = pd.date_range("2024-01-01", periods=6, freq="D")


def frame() -> pd.DataFrame:
    return pd.DataFrame({"d": DAYS, "v": [1, 3, 2, 5, 4, 6], "g": list("aabbab")})


def layers(fig) -> list[dict]:
    return PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"]


class TestATemporalSampleFormsNoLayer:
    def test_an_express_date_column(self):
        assert layers(px.histogram(frame(), x="d")) == []

    def test_on_a_horizontal_trace(self):
        assert layers(px.histogram(frame(), y="d")) == []

    def test_a_grouped_one(self):
        assert layers(px.histogram(frame(), x="d", color="g")) == []

    def test_a_list_of_timestamps_is_not_a_count_bar_chart(self):
        # Plotly bins these on a date axis like any other; counting each
        # instant as a category described a chart it does not draw.
        assert layers(go.Figure(go.Histogram(x=list(DAYS)))) == []

    def test_a_numeric_sample_is_unaffected(self):
        emitted = layers(px.histogram(frame(), x="v"))

        assert [layer["type"] for layer in emitted] == [PlotType.HIST.value]

    def test_a_numeric_group_is_unaffected(self):
        emitted = layers(px.histogram(frame(), x="v", color="g"))

        assert [layer["type"] for layer in emitted] == [PlotType.STACKED.value]


class TestIsTemporalSample:
    @pytest.mark.parametrize(
        ("values", "expected"),
        [
            (DAYS.to_numpy(), True),
            (DAYS.to_numpy().astype("datetime64[D]"), True),
            (list(DAYS), True),
            ([datetime(2024, 1, 1), datetime(2024, 1, 2)], True),
            ([date(2024, 1, 1), date(2024, 1, 2)], True),
            ([np.datetime64("2024-01-01"), np.datetime64("2024-01-02")], True),
            (np.array([pd.Timestamp("2024-01-01"), None], dtype=object), True),
            ([1.0, 2.0, 3.0], False),
            (np.array([1.0, 2.0, 3.0]), False),
            # A sample the author spelled as strings takes the categorical
            # path as it did before; this reads only what `to_dict` typed.
            (["2024-01-01", "2024-01-02"], False),
            (["a", "b"], False),
            (np.array(["a", None], dtype=object), False),
            ({"dtype": "f8", "bdata": "AAAAAAAA8D8="}, False),
            (None, False),
            ([], False),
        ],
        ids=[
            "datetime64[ns]",
            "datetime64[D]",
            "Timestamps",
            "datetimes",
            "dates",
            "datetime64 scalars",
            "object array",
            "floats",
            "float array",
            "date strings",
            "strings",
            "object strings",
            "typed-array spec",
            "None",
            "empty",
        ],
    )
    def test_it_reads_what_plotly_would_put_on_a_date_axis(self, values, expected):
        assert is_temporal_sample(values) is expected
