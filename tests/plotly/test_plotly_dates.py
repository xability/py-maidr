"""A date axis made ``render()`` raise, or announced epoch nanoseconds (#699).

``Figure.to_dict()`` hands a date column over as a ``datetime64`` array -- it
base64-encodes only the numeric kinds -- and a hand-written one as the
``datetime`` or ``date`` objects the author gave. Neither survived the
schema: ``as_list`` decomposed the array into ``datetime64`` scalars,
``_to_native`` unwrapped those with ``.item()``, and what came out was a
``datetime`` that ``json.dumps`` rejects at microsecond resolution or an
epoch *integer* at nanosecond. So ``px.line`` over a ``date_range`` raised,
and a ``datetime64[ns]`` array announced ``1704067200000000000`` as a day.

Plotly's own ``to_json`` spells the same values as ISO strings, and an ISO
string on an axis is an input every extractor already expects -- see
``PlotlyPlot._looks_like_date``. So that is what both now emit, with one
spelling across an array: the coarsest unit that loses nothing of any entry.
"""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest

plotly = pytest.importorskip("plotly")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402
from maidr.plotly.plotly_plot import PlotlyPlot, as_list  # noqa: E402

DAYS = pd.date_range("2024-01-01", periods=6, freq="D")
SPELLED = [f"2024-01-0{day}" for day in range(1, 7)]
VALUES = [1, 3, 2, 5, 4, 6]


def frame() -> pd.DataFrame:
    return pd.DataFrame({"d": DAYS, "v": VALUES})


def serialised(fig) -> dict:
    """The schema, round-tripped through the JSON the page embeds it as."""
    return json.loads(json.dumps(PlotlyMaidr(fig)._flatten_maidr()))


def points(fig) -> list[dict]:
    """Every point of a single-subplot figure's first layer, series flattened."""
    data = serialised(fig)["subplots"][0][0]["layers"][0]["data"]
    if data and isinstance(data[0], list):
        return [point for series in data for point in series]
    return data


class TestADateAxisRenders:
    @pytest.mark.parametrize("plot", [px.line, px.bar, px.scatter])
    def test_an_express_date_column_serialises(self, plot):
        # Raised `TypeError: Object of type datetime is not JSON serializable`
        # from inside the page template.
        figure = plot(frame(), x="d", y="v")

        assert [point["x"] for point in points(figure)] == SPELLED

    @pytest.mark.parametrize(
        "spelling",
        [
            list(DAYS.to_pydatetime()),
            [day.date() for day in DAYS],
            list(DAYS),
            DAYS.to_numpy().astype("datetime64[D]"),
            DAYS.to_numpy(),
        ],
        ids=["datetime", "date", "Timestamp", "datetime64[D]", "datetime64[ns]"],
    )
    def test_every_spelling_of_a_date_is_a_string_plotly_reads_as_one(self, spelling):
        figure = go.Figure(go.Scatter(x=spelling, y=VALUES))

        emitted = [point["x"] for point in points(figure)]

        assert len(emitted) == len(VALUES)
        assert all(isinstance(x, str) for x in emitted)
        assert all(PlotlyPlot._looks_like_date(x) for x in emitted)

    def test_a_date_on_y_is_spelled_the_same_way(self):
        figure = go.Figure(go.Scatter(x=VALUES, y=DAYS.to_numpy()))

        assert [point["y"] for point in points(figure)] == SPELLED

    def test_the_page_renders(self):
        # `render` is where the schema meets `json.dumps`, so it is the call
        # that raised.
        assert PlotlyMaidr(px.line(frame(), x="d", y="v")).render() is not None


class TestTheSpelling:
    def test_an_array_of_midnights_reads_as_dates(self):
        # Plotly's verbatim rule writes `2024-01-01T00:00:00.000000` for a
        # `datetime64[us]`; nothing of that is a date to a listener.
        assert as_list(DAYS.to_numpy()) == SPELLED

    def test_an_array_with_a_time_carries_it_throughout(self):
        # One unit for the array: `unit="auto"` picks per entry and would
        # spell the midnight and the noon of the same series differently.
        half_days = pd.date_range("2024-01-01", periods=3, freq="12h")

        assert as_list(half_days.to_numpy()) == [
            "2024-01-01T00:00",
            "2024-01-01T12:00",
            "2024-01-02T00:00",
        ]

    def test_a_missing_date_stays_missing(self):
        with_a_gap = np.array(
            ["2024-01-01", "NaT", "2024-01-03"], dtype="datetime64[ns]"
        )

        assert as_list(with_a_gap) == ["2024-01-01", "NaT", "2024-01-03"]

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (np.datetime64("2024-01-01T00:00:00.000000000"), "2024-01-01"),
            (np.datetime64("2024-01-01T12:30"), "2024-01-01T12:30"),
            (datetime(2024, 1, 1, 12, 30), "2024-01-01T12:30:00"),
            (date(2024, 1, 1), "2024-01-01"),
            (pd.Timestamp("2024-01-01"), "2024-01-01T00:00:00"),
        ],
        ids=["datetime64[ns]", "datetime64[m]", "datetime", "date", "Timestamp"],
    )
    def test_a_scalar_is_spelled_as_plotly_would(self, value, expected):
        assert PlotlyPlot._to_native(value) == expected

    def test_a_number_is_still_unwrapped(self):
        unwrapped = PlotlyPlot._to_native(np.float64(1.5))

        assert unwrapped == 1.5
        assert isinstance(unwrapped, float)
        assert PlotlyPlot._to_native(np.int64(3)) == 3
