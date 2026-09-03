"""
A plotly heatmap has to be emitted in the order plotly draws it (#489).

``categoryorder`` sorts a categorical axis and leaves the trace's own ``x``,
``y`` and ``z`` exactly as the author wrote them, so the labels alone do not
say what the chart shows. Reading them straight off the trace produced a
payload whose every label still sat on its own value -- nothing looked broken
-- describing a grid in the wrong place: arrowing across walked one order while
the chart showed another, and the core's highlight, which places a cell purely
by index over the rasterised image, outlined a third.

Measured on plotly.js rendered in Chromium, reading ``xaxis._categories`` --
the resolved drawn order -- for ``x=['charlie','alpha','bravo']`` with column
sums 3 / 30 / 300:

    categoryorder            resolved order
    'trace' (default)        charlie, alpha, bravo
    'category ascending'     alpha, bravo, charlie
    'category descending'    charlie, bravo, alpha
    'total ascending'        charlie, alpha, bravo
    'total descending'       bravo, alpha, charlie
    'sum descending'         bravo, alpha, charlie
    'mean descending'        bravo, alpha, charlie
    'min ascending'          charlie, alpha, bravo
    'max descending'         bravo, alpha, charlie
    'median ascending'       charlie, alpha, bravo

So every form applies to a heatmap, the aggregate ones included. Only the
forms a declared spec can answer exactly are resolved here; the aggregate ones
are declined rather than reimplemented offline, since a sort that is subtly
not plotly's would leave the chart wrong in the same silent way.

The counterpart fix in the core adapter, which reads a rendered
``_fullLayout._categories`` instead, is maidr#985.
"""

from __future__ import annotations

import warnings

import pytest

pytest.importorskip("plotly")
import plotly.graph_objects as go  # noqa: E402

from maidr.plotly.heatmap import PlotlyHeatmapPlot  # noqa: E402

warnings.filterwarnings("ignore")

#: Columns in the order the trace names them.
X = ["charlie", "alpha", "bravo"]
#: Rows in the order the trace names them; plotly draws the first at the bottom.
Y = ["r2", "r3", "r1"]
#: ``z[i][j]`` names its own source coordinates: row i+1, column j+1.
Z = [[11, 12, 13], [21, 22, 23], [31, 32, 33]]


def _emit(layout: dict | None = None) -> dict:
    """The plot data a three-by-three heatmap converts to.

    Parameters
    ----------
    layout : dict, optional
        The figure layout, for declaring a category order or a reversed axis.

    Returns
    -------
    dict
        The extracted plot data, keyed by raw strings.
    """
    fig = go.Figure(go.Heatmap(x=X, y=Y, z=Z))
    trace = fig.to_dict()["data"][0]
    data = PlotlyHeatmapPlot(trace, layout or {})._extract_plot_data()
    return {str(getattr(key, "value", key)): value for key, value in data.items()}


class TestTraceOrder:
    """A heatmap plotly draws in the trace's own order."""

    def test_keeps_the_columns_as_the_trace_names_them(self) -> None:
        assert _emit()["x"] == X

    def test_turns_the_rows_over(self) -> None:
        # Plotly counts a heatmap's rows from the bottom; the schema runs
        # top-first.
        assert _emit()["y"] == ["r1", "r3", "r2"]
        assert _emit()["points"] == [[31, 32, 33], [21, 22, 23], [11, 12, 13]]


class TestSortedColumns:
    """A heatmap whose columns plotly re-sorts."""

    LAYOUT = {"xaxis": {"categoryorder": "category ascending"}}

    def test_emits_the_columns_left_to_right_as_drawn(self) -> None:
        # Before the fix this was the trace's own order, which is not what the
        # chart shows.
        assert _emit(self.LAYOUT)["x"] == ["alpha", "bravo", "charlie"]

    def test_moves_every_value_with_its_column(self) -> None:
        assert _emit(self.LAYOUT)["points"] == [
            [32, 33, 31],
            [22, 23, 21],
            [12, 13, 11],
        ]

    def test_leaves_the_rows_where_they_were(self) -> None:
        assert _emit(self.LAYOUT)["y"] == ["r1", "r3", "r2"]

    def test_reads_a_descending_sort_too(self) -> None:
        layout = {"xaxis": {"categoryorder": "category descending"}}

        assert _emit(layout)["x"] == ["charlie", "bravo", "alpha"]

    def test_reads_an_explicit_array(self) -> None:
        # What plotly express's `category_orders` compiles to.
        layout = {
            "xaxis": {
                "categoryorder": "array",
                "categoryarray": ["bravo", "charlie", "alpha"],
            }
        }

        assert _emit(layout)["x"] == ["bravo", "charlie", "alpha"]
        assert _emit(layout)["points"][2] == [13, 11, 12]

    def test_reads_an_array_with_no_order_declared(self) -> None:
        # Measured: plotly resolves `categoryorder` to "array" whenever
        # `categoryarray` is non-empty and nothing was declared, and draws in
        # it. A hand-built figure that sets only the array is still sorted.
        layout = {"xaxis": {"categoryarray": ["bravo", "charlie", "alpha"]}}

        assert _emit(layout)["x"] == ["bravo", "charlie", "alpha"]
        assert _emit(layout)["points"][2] == [13, 11, 12]

    def test_lets_a_declared_order_beat_the_array(self) -> None:
        # Measured: the declared order wins; the array is ignored.
        layout = {
            "xaxis": {
                "categoryorder": "category ascending",
                "categoryarray": ["bravo", "charlie", "alpha"],
            }
        }

        assert _emit(layout)["x"] == ["alpha", "bravo", "charlie"]


class TestSortedRows:
    """A heatmap whose rows plotly re-sorts."""

    LAYOUT = {"yaxis": {"categoryorder": "category ascending"}}

    def test_emits_the_rows_top_to_bottom_as_drawn(self) -> None:
        # The resolved order counts from the bottom, so the drawn order is its
        # reverse.
        assert _emit(self.LAYOUT)["y"] == ["r3", "r2", "r1"]

    def test_moves_every_row_of_values_with_its_label(self) -> None:
        assert _emit(self.LAYOUT)["points"] == [
            [21, 22, 23],
            [11, 12, 13],
            [31, 32, 33],
        ]


class TestReversedAxis:
    """An axis the author reversed."""

    def test_draws_the_columns_right_to_left(self) -> None:
        layout = {"xaxis": {"autorange": "reversed"}}

        assert _emit(layout)["x"] == ["bravo", "alpha", "charlie"]
        assert _emit(layout)["points"] == [
            [33, 32, 31],
            [23, 22, 21],
            [13, 12, 11],
        ]

    def test_draws_the_rows_top_first_so_they_are_left_alone(self) -> None:
        layout = {"yaxis": {"autorange": "reversed"}}

        assert _emit(layout)["y"] == Y
        assert _emit(layout)["points"] == Z

    def test_composes_with_a_sort_rather_than_replacing_it(self) -> None:
        # The sort decides which category sits where along the axis; the
        # reversal decides which end that axis starts from. Both apply.
        layout = {
            "xaxis": {
                "categoryorder": "category ascending",
                "autorange": "reversed",
            }
        }

        assert _emit(layout)["x"] == ["charlie", "bravo", "alpha"]
        assert _emit(layout)["points"][2] == [11, 13, 12]

    def test_composes_on_the_rows_too(self) -> None:
        # The x composition above is the one that reads naturally; the y one
        # runs the other way round -- the resolved order counts from the
        # bottom, so a *reversed* y axis is the case where it is left alone --
        # and that asymmetry is exactly what a later change could break.
        layout = {
            "yaxis": {
                "categoryorder": "category ascending",
                "autorange": "reversed",
            }
        }

        assert _emit(layout)["y"] == ["r1", "r2", "r3"]
        assert _emit(layout)["points"] == [
            [31, 32, 33],
            [11, 12, 13],
            [21, 22, 23],
        ]


class TestNumericLabels:
    """Categories that look like numbers.

    Measured, and the reason these decline rather than sort. Plotly resolves
    the axis *type* before it resolves any order, and numeric-looking labels
    give it a linear axis, on which ``categoryorder`` and ``categoryarray``
    are ignored outright::

        x                 xaxis                            type      drawn
        [1, 2, 3]         array [3, 1, 2]                   linear    1, 2, 3
        [1, 2, 3]         type category, array [3, 1, 2]    category  3, 1, 2
        ['1', '2', '3']   array ['3', '1', '2']             linear    1, 2, 3
        [1, 3, 'b']       array ['b', 3, 1]                 linear    1, 2, 3
        ['a', 'c', 'b']   array ['c', 'a', 'b']             category  c, a, b

    So a numeric label anywhere sends the axis linear -- all of them or only
    some -- and only a declared ``type: "category"`` brings the order back.
    """

    @staticmethod
    def _emit_numeric(layout: dict) -> dict:
        fig = go.Figure(
            go.Heatmap(x=[1, 2, 3], y=["r1", "r2"], z=[[1, 2, 3], [4, 5, 6]])
        )
        trace = fig.to_dict()["data"][0]
        data = PlotlyHeatmapPlot(trace, layout)._extract_plot_data()
        return {str(getattr(k, "value", k)): v for k, v in data.items()}

    def test_declines_an_array_of_numbers(self) -> None:
        # Plotly draws 1, 2, 3 here regardless of the array, so applying it
        # would reorder a chart that was never reordered.
        layout = {"xaxis": {"categoryorder": "array", "categoryarray": [3, 1, 2]}}
        emitted = self._emit_numeric(layout)

        assert emitted["x"] == [1.0, 2.0, 3.0]
        assert emitted["points"] == [[4.0, 5.0, 6.0], [1.0, 2.0, 3.0]]

    def test_declines_a_numeric_array_with_no_order_declared(self) -> None:
        assert self._emit_numeric({"xaxis": {"categoryarray": [2, 3, 1]}})["x"] == [
            1.0,
            2.0,
            3.0,
        ]

    def test_sorts_them_once_the_axis_is_declared_categorical(self) -> None:
        # ``type: "category"`` is what makes plotly honour the array, and it
        # is also what makes the labels comparable: ``_to_native`` floats an
        # integer, so both sides have to normalise the same way.
        layout = {
            "xaxis": {
                "type": "category",
                "categoryorder": "array",
                "categoryarray": [3, 1, 2],
            }
        }
        emitted = self._emit_numeric(layout)

        assert emitted["x"] == [3.0, 1.0, 2.0]
        assert emitted["points"] == [[6.0, 4.0, 5.0], [3.0, 1.0, 2.0]]

    def test_sorts_labels_named_nan_and_inf(self) -> None:
        # Python parses both, where the coercion plotly tests with does not.
        # Measured: ['nan', 'inf', 'zeta'] gets a *category* axis and honours
        # its array, so reading them as numbers would decline a real sort.
        fig = go.Figure(go.Heatmap(x=["nan", "inf", "zeta"], y=["r1"], z=[[1, 2, 3]]))
        trace = fig.to_dict()["data"][0]
        layout = {
            "xaxis": {
                "categoryorder": "array",
                "categoryarray": ["zeta", "nan", "inf"],
            }
        }
        data = PlotlyHeatmapPlot(trace, layout)._extract_plot_data()
        emitted = {str(getattr(k, "value", k)): v for k, v in data.items()}

        assert emitted["x"] == ["zeta", "nan", "inf"]
        assert emitted["points"] == [[3, 1, 2]]

    def test_declines_labels_in_exponent_form(self) -> None:
        # Measured: these do resolve a linear axis, so they are numbers.
        fig = go.Figure(go.Heatmap(x=["1e10", "2e10", "3e10"], y=["r1"], z=[[1, 2, 3]]))
        trace = fig.to_dict()["data"][0]
        layout = {
            "xaxis": {
                "categoryorder": "array",
                "categoryarray": ["3e10", "1e10", "2e10"],
            }
        }
        data = PlotlyHeatmapPlot(trace, layout)._extract_plot_data()
        emitted = {str(getattr(k, "value", k)): v for k, v in data.items()}

        assert emitted["x"] == ["1e10", "2e10", "3e10"]

    def test_declines_when_only_some_labels_are_numeric(self) -> None:
        # Measured: a mixed set still sends the axis linear.
        fig = go.Figure(go.Heatmap(x=[1, 3, "b"], y=["r1"], z=[[1, 2, 3]]))
        trace = fig.to_dict()["data"][0]
        layout = {"xaxis": {"categoryorder": "array", "categoryarray": ["b", 3, 1]}}
        data = PlotlyHeatmapPlot(trace, layout)._extract_plot_data()
        emitted = {str(getattr(k, "value", k)): v for k, v in data.items()}

        assert emitted["x"] == [1.0, 3.0, "b"]

    def test_still_declines_a_number_the_trace_does_not_carry(self) -> None:
        layout = {
            "xaxis": {
                "type": "category",
                "categoryorder": "array",
                "categoryarray": [3, 1, 9],
            }
        }

        assert self._emit_numeric(layout)["x"] == [1.0, 2.0, 3.0]


class TestDateLabels:
    """Categories that look like dates.

    A date axis ignores ``categoryorder`` exactly as a linear one does.
    Measured, with a ``categoryarray`` declared on each::

        2024-03-01           date        2024/03/01     category
        2024-03              date        03-01-2024     category
        2024-03-01 12:00     date        Mar 2024       category
                                         Q1             category
                                         2024-13-45     category

    Year-first and hyphen-separated is a date, and plotly checks the parts
    rather than the shape -- month 13 and day 45 leave it a category.
    """

    @staticmethod
    def _emit(x: list, layout: dict) -> dict:
        fig = go.Figure(go.Heatmap(x=x, y=["r1"], z=[[1, 2, 3]]))
        trace = fig.to_dict()["data"][0]
        data = PlotlyHeatmapPlot(trace, layout)._extract_plot_data()
        return {str(getattr(k, "value", k)): v for k, v in data.items()}

    @pytest.mark.parametrize(
        "dates",
        [
            ["2024-03-01", "2024-01-01", "2024-02-01"],
            ["2024-03", "2024-01", "2024-02"],
            ["2024-03-01 12:00", "2024-01-01 09:00", "2024-02-01 15:00"],
            ["2024-03-01T12:00:00", "2024-01-01T09:00:00", "2024-02-01T15:00:00"],
            # Plotly accepts a date spelled without zero padding, and one with
            # leading whitespace. Both are the direction that matters: missing
            # them applies an order plotly ignores.
            ["2024-3-1", "2024-1-1", "2024-2-1"],
            [" 2024-03-01", " 2024-01-01", " 2024-02-01"],
        ],
    )
    def test_declines_an_iso_date_axis(self, dates: list) -> None:
        layout = {
            "xaxis": {
                "categoryorder": "array",
                "categoryarray": [dates[2], dates[0], dates[1]],
            }
        }

        assert self._emit(dates, layout)["x"] == dates

    @pytest.mark.parametrize(
        "labels",
        [
            ["2024/03/01", "2024/01/01", "2024/02/01"],
            ["03-01-2024", "01-01-2024", "02-01-2024"],
            ["Mar 2024", "Jan 2024", "Feb 2024"],
            ["2024-13-45", "2024-99-99", "2024-77-77"],
            # Plotly checks the parts make a real day, so a February 30th is a
            # name. A pattern that only bounded the day at 31 let these
            # through and declined a sort that does apply.
            ["2024-02-30", "2024-04-31", "2024-06-31"],
        ],
    )
    def test_sorts_labels_plotly_leaves_as_names(self, labels: list) -> None:
        # These all stay category axes, so their array is honoured.
        order = [labels[2], labels[0], labels[1]]
        layout = {"xaxis": {"categoryorder": "array", "categoryarray": order}}

        assert self._emit(labels, layout)["x"] == order

    def test_sorts_dates_once_the_axis_is_declared_categorical(self) -> None:
        dates = ["2024-03-01", "2024-01-01", "2024-02-01"]
        order = [dates[2], dates[0], dates[1]]
        layout = {
            "xaxis": {
                "type": "category",
                "categoryorder": "array",
                "categoryarray": order,
            }
        }

        assert self._emit(dates, layout)["x"] == order


class TestRaggedGrid:
    """A ``z`` whose rows are not all the same length."""

    @staticmethod
    def _ragged(layout: dict) -> dict:
        fig = go.Figure(go.Heatmap(x=X, y=["r1", "r2"], z=[[1, 2, 3], [4, 5]]))
        trace = fig.to_dict()["data"][0]
        data = PlotlyHeatmapPlot(trace, layout)._extract_plot_data()
        return {str(getattr(k, "value", k)): v for k, v in data.items()}

    def test_survives_a_reversed_x_axis(self) -> None:
        # There is no third value in the short row to move, so nothing touches
        # the columns. Reversing them would have indexed past its end.
        emitted = self._ragged({"xaxis": {"autorange": "reversed"}})

        assert emitted["points"] == [[4, 5], [1, 2, 3]]
        assert emitted["x"] == X

    def test_survives_a_sorted_x_axis(self) -> None:
        emitted = self._ragged({"xaxis": {"categoryorder": "category ascending"}})

        assert emitted["points"] == [[4, 5], [1, 2, 3]]
        assert emitted["x"] == X

    def test_still_sorts_its_rows(self) -> None:
        # Row moves select whole rows, so they stay well defined however
        # ragged the rows themselves are -- which is why the guard covers the
        # columns only.
        emitted = self._ragged({"yaxis": {"categoryorder": "category descending"}})

        assert emitted["y"] == ["r1", "r2"]
        assert emitted["points"] == [[1, 2, 3], [4, 5]]

    def test_still_turns_its_rows_over(self) -> None:
        # The rows are whole even when their contents are not, so the one
        # reordering that is still well defined still happens.
        emitted = self._ragged({})

        assert emitted["y"] == ["r2", "r1"]
        assert emitted["points"] == [[4, 5], [1, 2, 3]]


class TestDeclines:
    """An order this cannot resolve exactly."""

    @pytest.mark.parametrize(
        "order",
        [
            "total ascending",
            "total descending",
            "sum descending",
            "mean descending",
            "min ascending",
            "max descending",
            "median ascending",
        ],
    )
    def test_declines_an_aggregate_order(self, order: str) -> None:
        # Measured: these do re-sort a heatmap. Resolving them offline means
        # reimplementing plotly's aggregation, and a sort that is subtly not
        # plotly's is the same silent wrongness this exists to remove.
        assert _emit({"xaxis": {"categoryorder": order}})["x"] == X

    def test_declines_an_array_naming_more_than_the_trace_draws(self) -> None:
        # Plotly draws empty columns for the extras, which `points` has no way
        # to say. Keeping the trace's order loses the sort; inventing a column
        # would lose the truth.
        layout = {
            "xaxis": {
                "categoryorder": "array",
                "categoryarray": ["zulu", "charlie", "alpha", "bravo"],
            }
        }

        assert _emit(layout)["x"] == X

    def test_declines_an_array_missing_one_the_trace_draws(self) -> None:
        layout = {
            "xaxis": {"categoryorder": "array", "categoryarray": ["alpha", "bravo"]}
        }

        assert _emit(layout)["x"] == X

    def test_declines_an_array_naming_a_category_the_trace_lacks(self) -> None:
        # Same length, so a length check alone would let this past and emit a
        # column of values under a label that is not theirs.
        layout = {
            "xaxis": {
                "categoryorder": "array",
                "categoryarray": ["alpha", "bravo", "delta"],
            }
        }

        assert _emit(layout)["x"] == X

    def test_declines_an_array_order_with_no_array(self) -> None:
        assert _emit({"xaxis": {"categoryorder": "array"}})["x"] == X

    def test_declines_an_empty_array(self) -> None:
        # Measured: an empty `categoryarray` leaves the resolved order at
        # "trace", so there is nothing to apply.
        assert _emit({"xaxis": {"categoryarray": []}})["x"] == X

    def test_declines_an_array_that_repeats_an_entry(self) -> None:
        # Names every label the right number of times without being a
        # permutation of them: 'alpha' twice, 'bravo' never. Honouring it
        # would emit one column's values twice and lose another's.
        layout = {
            "xaxis": {
                "categoryorder": "array",
                "categoryarray": ["charlie", "alpha", "alpha"],
            }
        }

        assert _emit(layout)["x"] == X
        assert _emit(layout)["points"][2] == [11, 12, 13]

    def test_declines_when_the_trace_repeats_a_label(self) -> None:
        # There is no unambiguous cell to send each category to.
        fig = go.Figure(go.Heatmap(x=["a", "a", "b"], y=Y, z=Z))
        trace = fig.to_dict()["data"][0]
        layout = {"xaxis": {"categoryorder": "array", "categoryarray": ["b", "a", "a"]}}

        data = PlotlyHeatmapPlot(trace, layout)._extract_plot_data()
        emitted = {str(getattr(k, "value", k)): v for k, v in data.items()}

        assert emitted["x"] == ["a", "a", "b"]
