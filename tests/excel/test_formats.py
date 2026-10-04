"""How Excel's dates, number formats and range formulas are read."""

from __future__ import annotations

from datetime import datetime

import pytest
from matplotlib.ticker import PercentFormatter, StrMethodFormatter

from maidr.excel.cells import Range, parse_range
from maidr.excel.formats import (
    format_date,
    is_date_format,
    number_formatter,
    serial_to_datetime,
)


@pytest.mark.parametrize(
    ("serial", "expected"),
    [
        (45292, datetime(2024, 1, 1)),
        (45292.5, datetime(2024, 1, 1, 12)),
        (61, datetime(1900, 3, 1)),
        # Excel's 1900-02-29, which never was.
        (60, datetime(1900, 2, 29 - 1)),
        (1, datetime(1900, 1, 1)),
    ],
)
def test_serials_count_days_from_1900(serial, expected):
    assert serial_to_datetime(serial) == expected


def test_serials_count_days_from_1904_when_asked():
    assert serial_to_datetime(0, date1904=True) == datetime(1904, 1, 1)
    assert serial_to_datetime(43830, date1904=True) == datetime(2024, 1, 1)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("mmm-yy", "Jan-24"),
        ("m/d/yyyy", "1/5/2024"),
        ("yyyy-mm-dd", "2024-01-05"),
        ("d mmmm yyyy", "5 January 2024"),
        ("dddd", "Friday"),
        ("h:mm AM/PM", "2:07 PM"),
        ("hh:mm:ss", "14:07:09"),
        ("[$-409]mmm-yy;@", "Jan-24"),
        ('yyyy"年"m"月"', "2024年1月"),
        ("mmmmm", "J"),
    ],
)
def test_dates_are_written_as_their_format_writes_them(code, expected):
    assert format_date(datetime(2024, 1, 5, 14, 7, 9), code) == expected


def test_a_date_without_a_format_is_written_iso_style():
    assert format_date(datetime(2024, 1, 5), None) == "2024-01-05"
    assert format_date(datetime(2024, 1, 5, 9, 30), None) == "2024-01-05 09:30"


@pytest.mark.parametrize(
    ("code", "is_date"),
    [
        ("mmm-yy", True),
        ("h:mm", True),
        ("[$-409]d-mmm;@", True),
        ("General", False),
        ("0.0%", False),
        ("$#,##0", False),
        ('0 "days"', False),
        (None, False),
    ],
)
def test_date_formats_are_told_from_number_formats(code, is_date):
    assert is_date_format(code) is is_date


def test_a_percent_format_reads_fractions_as_percentages():
    formatter = number_formatter("0.0%")

    assert isinstance(formatter, PercentFormatter)
    assert formatter.xmax == 1 and formatter.decimals == 1


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("$#,##0", "${x:,.0f}"),
        ("$#,##0.00;($#,##0.00)", "${x:,.2f}"),
        ('"€"#,##0.00', "€{x:,.2f}"),
        ("[$£-809]#,##0", "£{x:,.0f}"),
        ("#,##0.0", "{x:,.1f}"),
        ("0.00", "{x:.2f}"),
    ],
)
def test_money_and_grouped_numbers_keep_their_symbol_and_decimals(code, expected):
    formatter = number_formatter(code)

    assert isinstance(formatter, StrMethodFormatter)
    assert formatter.fmt == expected


@pytest.mark.parametrize("code", [None, "General", "mmm-yy", "@"])
def test_general_text_and_date_formats_need_no_formatter(code):
    assert number_formatter(code) is None


@pytest.mark.parametrize(
    ("formula", "expected"),
    [
        ("Sales!$B$2:$B$5", Range("Sales", 1, 1, 4, 1)),
        ("'Q1 data'!$A$1", Range("Q1 data", 0, 0, 0, 0)),
        ("'Bob''s'!A2:C2", Range("Bob's", 1, 0, 1, 2)),
        ("Sales!$B$5:$B$2", Range("Sales", 1, 1, 4, 1)),
    ],
)
def test_a_series_formula_names_its_range(formula, expected):
    assert parse_range(formula) == expected


@pytest.mark.parametrize(
    "formula",
    ["Sales!Totals", "[1]Sales!$A$1:$A$3", "(Sales!$A$1,Sales!$A$3)", "", None],
)
def test_a_formula_that_is_not_one_range_names_none(formula):
    assert parse_range(formula) is None


@pytest.mark.parametrize(
    ("area", "header"),
    [
        (Range("S", 1, 0, 4, 0), (0, 0)),  # a column: the cell above
        (Range("S", 0, 1, 0, 4), (0, 0)),  # a row: the cell to the left
        (Range("S", 1, 0, 4, 1), (0, 1)),  # two label columns: above the inner one
        (Range("S", 0, 0, 3, 0), None),  # nothing above the first row
    ],
)
def test_the_header_of_a_range_is_the_cell_that_names_it(area, header):
    assert area.header() == header
