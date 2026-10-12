"""In a real kernel, a figure is shown where and when the inline backend shows it.

``test_notebook_display.py`` runs cells in IPython's shell in this process;
this runs them in a Jupyter kernel of this interpreter, as a notebook
frontend does, so ``import maidr`` sets up what it sets up in a kernel, and
the outputs are the messages the kernel sends.
"""

from __future__ import annotations

import json
import sys

import pytest

nbformat = pytest.importorskip("nbformat")
nbclient = pytest.importorskip("nbclient")
pytest.importorskip("ipykernel")

_CELLS = [
    # 0: each chart loads maidr.js from the CDN, so none puts the bundle in
    # the output beside it.
    "import matplotlib, matplotlib.pyplot as plt, maidr\n"
    "maidr.set_use_cdn(True)\n"
    "print(matplotlib.get_backend(), matplotlib.is_interactive())",
    # 1: no plt.show()
    "fig, ax = plt.subplots()\n_ = ax.bar(['a', 'b'], [1, 2])",
    # 2: the next cell draws on a figure of its own
    "print(plt.get_fignums())\nplt.plot([1, 2, 3])\nplt.show()",
    # 3: a figure as the cell's value
    "fig2, ax2 = plt.subplots()\n_ = ax2.bar(['a', 'b'], [2, 1])\nfig2",
    # 4: and again in a later cell
    "fig2",
    # 5: plt.ioff()
    "with plt.ioff():\n    fig3 = plt.figure()\n    _ = fig3.add_subplot().bar(['a'], [1])",
    # 6: kept open for plt.show()
    "plt.show()",
    # 7: the inline backend again
    "maidr.set_backend(use_maidr=False)\nfig4, ax4 = plt.subplots()\n_ = ax4.bar(['a'], [1])",
    # 8: and maidr's
    "maidr.set_backend(use_maidr=True)\nfig5, ax5 = plt.subplots()\n_ = ax5.bar(['a'], [1])",
    # 9: an ipywidgets interact function, run twice
    "try:\n"
    "    from ipywidgets import interactive\n"
    "except ImportError:\n"
    "    print('no ipywidgets')\n"
    "else:\n"
    "    def draw(n=2):\n"
    "        fig, ax = plt.subplots()\n"
    "        _ = ax.bar(['a', 'b'], [n, 1])\n"
    "    w = interactive(draw, n=(1, 3))\n"
    "    w.update()\n"
    "    w.kwargs_widgets[0].value = 3\n"
    "    print('open', plt.get_fignums())",
]


def _kind(output) -> str:
    if output["output_type"] == "stream":
        return "text"
    if output["output_type"] == "error":
        return "error"
    data = output.get("data", {})
    if "<iframe" in data.get("text/html", ""):
        return "chart"
    if "image/png" in data:
        return "image"
    return "other"


@pytest.fixture(scope="module")
def outputs(tmp_path_factory) -> list[list[dict]]:
    """Run the cells in a kernel of this interpreter, with its maidr."""
    from jupyter_client.kernelspec import KernelSpecManager
    from jupyter_client.manager import KernelManager

    specs = tmp_path_factory.mktemp("kernels")
    spec = specs / "here"
    spec.mkdir()
    (spec / "kernel.json").write_text(
        json.dumps(
            {
                "argv": [
                    sys.executable,
                    "-m",
                    "ipykernel_launcher",
                    "-f",
                    "{connection_file}",
                ],
                "display_name": "this interpreter",
                "language": "python",
            }
        )
    )
    notebook = nbformat.v4.new_notebook(
        cells=[nbformat.v4.new_code_cell(source) for source in _CELLS]
    )
    manager = KernelManager(
        kernel_name="here",
        kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(specs)]),
    )
    client = nbclient.NotebookClient(notebook, timeout=300, km=manager)
    client.execute()
    return [cell["outputs"] for cell in notebook.cells]


def _kinds(cell: list[dict]) -> list[str]:
    return [_kind(output) for output in cell if _kind(output) != "text"]


def test_import_maidr_sets_the_kernel_up_as_the_inline_backend_would(outputs):
    printed = "".join(
        o.get("text", "") for o in outputs[0] if o["output_type"] == "stream"
    )
    assert "module://maidr.backend True" in printed


def test_a_cell_without_show_shows_its_chart(outputs):
    assert _kinds(outputs[1]) == ["chart"]


def test_the_next_cell_starts_with_no_figure_open(outputs):
    printed = "".join(
        o.get("text", "") for o in outputs[2] if o["output_type"] == "stream"
    )
    assert "[]" in printed
    assert _kinds(outputs[2]) == ["chart"]


def test_a_figure_as_the_cells_value_is_its_chart_once(outputs):
    assert _kinds(outputs[3]) == ["chart"]
    assert _kinds(outputs[4]) == ["chart"]


def test_ioff_keeps_a_figure_back_for_show(outputs):
    assert _kinds(outputs[5]) == []
    assert _kinds(outputs[6]) == ["chart"]


def test_set_backend_switches_between_images_and_charts(outputs):
    assert _kinds(outputs[7]) == ["image"]
    assert _kinds(outputs[8]) == ["chart"]


def test_an_interact_function_shows_its_figures_in_its_own_output(outputs):
    """ipywidgets shows them after every run, in the widget's output, not later."""
    printed = "".join(
        o.get("text", "") for o in outputs[9] if o["output_type"] == "stream"
    )
    if "no ipywidgets" in printed:
        pytest.skip("ipywidgets is not installed")
    assert "open []" in printed
    # Shown in the widget's output, which the cell's own does not hold.
    assert _kinds(outputs[9]) == []
