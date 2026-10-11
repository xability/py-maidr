"""The ``fig-alt`` of the Quarto cell a chart is drawn in.

Quarto takes a cell's ``#|`` options off before the kernel runs it, so
:mod:`maidr.util.quarto_cell` finds the cell in the notebook Quarto executes
-- the ``<stem>.quarto_ipynb`` beside a ``.qmd`` -- by the code the kernel was
sent. These tests build that notebook as Quarto writes it and a kernel whose
history holds the code, as a real render's does (checked against Quarto
1.10: the history holds the cell without its options, and the notebook the
cell with them, includes resolved).
"""

from __future__ import annotations

import json
import os
import re
import sys

import pytest

from maidr.util import quarto_cell


class _History:
    def __init__(self) -> None:
        self.input_hist_raw: list[str] = [""]


class _Kernel:
    """The part of the kernel's IPython shell the reader uses."""

    def __init__(self) -> None:
        self.history_manager = _History()
        self.execution_count = 1

    def run(self, code: str) -> None:
        """Start running a cell: its code is in the history, its count new."""
        self.execution_count += 1
        self.history_manager.input_hist_raw.append(code)


def _cell(source: str) -> dict:
    return {"cell_type": "code", "metadata": {}, "outputs": [], "source": source}


def _notebook(path, *sources: str) -> None:
    cells = [_cell(source) for source in sources]
    path.write_text(json.dumps({"cells": cells, "metadata": {}}), encoding="utf-8")


@pytest.fixture
def kernel(monkeypatch, tmp_path):
    """The kernel of a Quarto render of ``tmp_path/doc.qmd``."""
    kernel = _Kernel()
    monkeypatch.setenv("QUARTO_FIG_FORMAT", "png")
    monkeypatch.delenv("QUARTO_EXECUTE_INFO", raising=False)
    monkeypatch.setenv("QUARTO_DOCUMENT_PATH", str(tmp_path))
    monkeypatch.setenv("QUARTO_DOCUMENT_FILE", "doc.qmd")
    monkeypatch.setattr(quarto_cell, "_shell", lambda: kernel)
    monkeypatch.setattr(quarto_cell, "_notebooks", {})
    monkeypatch.setattr(quarto_cell, "_drawn", [None, 0])
    return kernel


def test_the_cells_fig_alt_is_read(kernel, tmp_path):
    _notebook(
        tmp_path / "doc.quarto_ipynb",
        "import maidr",
        '#| label: fig-sales\n#| fig-alt: "Sales rise every quarter."\nplt.show()',
    )
    kernel.run("plt.show()")

    assert quarto_cell.fig_alt() == "Sales rise every quarter."


def test_a_cell_without_fig_alt_gives_none(kernel, tmp_path):
    _notebook(tmp_path / "doc.quarto_ipynb", '#| fig-cap: "Sales"\nplt.show()')
    kernel.run("plt.show()")

    assert quarto_cell.fig_alt() is None


def test_outside_a_render_there_is_none(kernel, tmp_path, monkeypatch):
    _notebook(tmp_path / "doc.quarto_ipynb", '#| fig-alt: "Sales"\nplt.show()')
    kernel.run("plt.show()")
    monkeypatch.delenv("QUARTO_FIG_FORMAT")

    assert quarto_cell.fig_alt() is None


def test_a_list_gives_each_chart_of_the_cell_its_own_in_turn(kernel, tmp_path):
    """As knitr recycles ``fig.alt`` over a chunk's figures."""
    _notebook(
        tmp_path / "doc.quarto_ipynb",
        '#| fig-alt: ["First chart.", "Second chart."]\ndraw_three()',
    )
    kernel.run("draw_three()")

    drawn = [quarto_cell.fig_alt() for _ in range(3)]

    assert drawn == ["First chart.", "Second chart.", "First chart."]


def test_the_next_cell_starts_its_list_again(kernel, tmp_path):
    _notebook(
        tmp_path / "doc.quarto_ipynb",
        '#| fig-alt: ["First chart.", "Second chart."]\ndraw()',
        '#| fig-alt: ["Third chart.", "Fourth chart."]\ndraw_again()',
    )
    kernel.run("draw()")
    assert quarto_cell.fig_alt() == "First chart."

    kernel.run("draw_again()")

    assert quarto_cell.fig_alt() == "Third chart."


def test_a_later_render_counts_its_charts_afresh(kernel, tmp_path):
    """A kernel kept alive between renders may count executions from 1 again."""
    notebook = tmp_path / "doc.quarto_ipynb"
    _notebook(notebook, '#| fig-alt: ["First chart.", "Second chart."]\ndraw()')
    kernel.run("draw()")
    assert quarto_cell.fig_alt() == "First chart."

    # The next render writes its notebook again and runs the cell as the
    # same execution.
    _notebook(notebook, '#| fig-alt: ["First chart.", "Second chart."]\ndraw()')
    os.utime(notebook, ns=(10**18, 10**18))

    assert quarto_cell.fig_alt() == "First chart."


def test_a_folded_option_is_read_as_yaml(kernel, tmp_path):
    _notebook(
        tmp_path / "doc.quarto_ipynb",
        "#| fig-alt: >\n#|   Sales rise\n#|   every quarter.\nplt.show()",
    )
    kernel.run("plt.show()")

    assert quarto_cell.fig_alt() == "Sales rise every quarter."


def test_without_pyyaml_plain_quoted_and_list_values_are_read(
    kernel, tmp_path, monkeypatch
):
    monkeypatch.setitem(sys.modules, "yaml", None)
    _notebook(
        tmp_path / "doc.quarto_ipynb",
        "#| fig-alt: Plain text, unquoted\nfirst()",
        "#| fig-alt: 'It''s quoted'\nsecond()",
        '#| fig-alt: ["Listed."]\nthird()',
    )

    read = []
    for code in ("first()", "second()", "third()"):
        kernel.run(code)
        read.append(quarto_cell.fig_alt())

    assert read == ["Plain text, unquoted", "It's quoted", "Listed."]


@pytest.mark.parametrize(
    "options",
    [
        "#| fig-alt: >\n#|   Sales rise\n#|   every quarter.",
        "#| fig-alt: |-\n#|   Sales rise\n#|   every quarter.",
        "#| fig-alt: Sales rise\n#|   every quarter.",
        '#| fig-alt: "Sales rise\n#|   every quarter."',
        '#| fig-alt:\n#|   - "First chart."\n#|   - Second chart.',
        '#| fig-alt:\n#| - "First chart."\n#| - Second\n#|   chart.',
        '#| fig-alt: ["First chart.",\n#|   "Second chart."]',
    ],
    ids=[
        "folded",
        "literal",
        "plain",
        "double-quoted",
        "list",
        "list-unindented",
        "flow-list",
    ],
)
def test_without_pyyaml_a_value_over_several_lines_is_read_as_yaml_reads_it(
    kernel, tmp_path, monkeypatch, options
):
    """Rather than read ``>`` as the alt text, or only its first line."""
    yaml = pytest.importorskip("yaml")
    written = yaml.safe_load(re.sub(r"^#\| ?", "", options, flags=re.M))["fig-alt"]
    if not isinstance(written, list):
        written = [written]
    expected = [text.strip() for text in written]
    monkeypatch.setitem(sys.modules, "yaml", None)
    _notebook(tmp_path / "doc.quarto_ipynb", options + "\ndraw()")
    kernel.run("draw()")

    read = [quarto_cell.fig_alt() for _ in expected]

    assert read == expected


def test_a_cell_that_is_not_run_is_not_taken_for_the_one_that_is(kernel, tmp_path):
    _notebook(
        tmp_path / "doc.quarto_ipynb",
        '#| eval: false\n#| fig-alt: "Not this one."\nplt.show()',
        '#| fig-alt: "This one."\nplt.show()',
    )
    kernel.run("plt.show()")

    assert quarto_cell.fig_alt() == "This one."


def test_cells_with_the_same_code_and_other_alt_text_give_none(kernel, tmp_path):
    """Rather than the wrong cell's alt text, which would be read as true."""
    _notebook(
        tmp_path / "doc.quarto_ipynb",
        '#| fig-alt: "One."\nplt.show()',
        '#| fig-alt: "Another."\nplt.show()',
    )
    kernel.run("plt.show()")

    assert quarto_cell.fig_alt() is None


def test_cells_with_the_same_code_and_alt_text_give_it(kernel, tmp_path):
    _notebook(
        tmp_path / "doc.quarto_ipynb",
        '#| fig-alt: "Same."\nplt.show()',
        '#| fig-alt: "Same."\nplt.show()',
    )
    kernel.run("plt.show()")

    assert quarto_cell.fig_alt() == "Same."


def test_the_newest_notebook_quarto_wrote_is_read(kernel, tmp_path):
    """Quarto numbers its notebook when an earlier one was left behind."""
    old = tmp_path / "doc.quarto_ipynb"
    _notebook(old, '#| fig-alt: "Left behind."\nplt.show()')
    os.utime(old, (1_000_000, 1_000_000))
    _notebook(tmp_path / "doc.quarto_ipynb_1", '#| fig-alt: "This render."\nplt.show()')
    kernel.run("plt.show()")

    assert quarto_cell.fig_alt() == "This render."


def test_a_notebook_document_is_read_itself(kernel, tmp_path, monkeypatch):
    """A rendered ``.ipynb`` is executed as it is, named by the execute info."""
    document = tmp_path / "analysis.ipynb"
    cell = _cell("")
    cell["source"] = ['#| fig-alt: "From the notebook."\n', "plt.show()"]
    document.write_text(json.dumps({"cells": [cell], "metadata": {}}), encoding="utf-8")
    info = tmp_path / "info.json"
    info.write_text(json.dumps({"document-path": str(document)}), encoding="utf-8")
    monkeypatch.setenv("QUARTO_EXECUTE_INFO", str(info))
    kernel.run("plt.show()")

    assert quarto_cell.fig_alt() == "From the notebook."


def test_a_notebook_that_cannot_be_read_gives_none(kernel, tmp_path):
    (tmp_path / "doc.quarto_ipynb").write_text("{not json", encoding="utf-8")
    kernel.run("plt.show()")

    assert quarto_cell.fig_alt() is None


def test_without_a_notebook_there_is_none(kernel):
    kernel.run("plt.show()")

    assert quarto_cell.fig_alt() is None
