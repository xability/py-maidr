"""The ``maidr`` tab TensorBoard shows: its routes, and that TensorBoard finds it."""

from __future__ import annotations

import json
import shutil
import types
from pathlib import Path

import pytest

pytest.importorskip("tensorboard")

from werkzeug.test import Client  # noqa: E402
from werkzeug.wrappers import Response  # noqa: E402

from maidr.tensorboard.plugin import MaidrPlugin, chart_page, list_charts  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def logdir(tmp_path) -> Path:
    """Scalars, histograms, a sweep and an embedding under one log directory."""
    root = tmp_path / "logs"
    for name in ("torch", "tf_histograms", "hparams_sweep"):
        shutil.copytree(FIXTURES / name, root / name)
    for path in (FIXTURES / "torch_embedding").iterdir():
        if path.name.startswith("events"):
            continue
        target = root / path.name
        if path.is_dir():
            shutil.copytree(path, target)
        else:
            shutil.copy(path, target)
    return root


def _client(logdir: Path, route: str) -> Client:
    plugin = MaidrPlugin(types.SimpleNamespace(logdir=str(logdir)))
    return Client(plugin.get_plugin_apps()[route], Response)


def test_tensorboard_finds_the_plugin_through_its_entry_point():
    from tensorboard import default

    assert MaidrPlugin in default.get_dynamic_plugins()


def test_the_tab_is_named_and_drawn_by_its_es_module(logdir):
    plugin = MaidrPlugin(types.SimpleNamespace(logdir=str(logdir)))
    assert plugin.plugin_name == "maidr"
    assert plugin.is_active()
    metadata = plugin.frontend_metadata()
    assert metadata.es_module_path == "/index.js" and metadata.tab_name == "maidr"
    response = _client(logdir, "/index.js").get("/")
    assert response.mimetype == "application/javascript"
    source = response.get_data(as_text=True)
    assert "export async function render()" in source
    assert '<label for="chart">' in source and 'role="status"' in source


def test_without_a_log_directory_the_tab_is_inactive(tmp_path):
    assert not MaidrPlugin(types.SimpleNamespace(logdir=None)).is_active()
    assert not MaidrPlugin(
        types.SimpleNamespace(logdir=str(tmp_path / "nowhere"))
    ).is_active()


def test_every_chart_the_directory_holds_is_listed(logdir):
    response = _client(logdir, "/charts").get("/")
    charts = json.loads(response.get_data(as_text=True))
    titles = [chart["title"] for chart in charts]
    assert "Scalars: Loss/train" in titles
    assert "Distributions: activations (tf_histograms/run)" in titles
    assert "Histograms: activations (tf_histograms/run)" in titles
    assert "HParams: parallel coordinates" in titles
    assert "HParams: scatter matrix" in titles
    assert "Projector: animals:00000" in titles
    assert charts == list_charts(str(logdir))


@pytest.mark.parametrize(
    "query, layer",
    [
        ({"kind": "scalars", "tag": "Loss/train"}, '"type": "line"'),
        (
            {"kind": "histograms", "tag": "activations", "run": "tf_histograms/run"},
            '"type": "ridgeline"',
        ),
        ({"kind": "hparams", "index": "0"}, '"type": "parallel_coordinates"'),
        ({"kind": "projector", "tag": "animals:00000"}, '"type": "point"'),
    ],
)
def test_a_chart_is_a_self_contained_maidr_page(logdir, query, layer):
    response = _client(logdir, "/chart").get("/", query_string=query)
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert page.startswith("<!doctype html>")
    assert "maidrLive" in page  # the bundle is inlined, not fetched
    assert layer in page.replace("&quot;", '"')


def test_a_chart_that_is_not_there_is_a_404(logdir):
    client = _client(logdir, "/chart")
    assert (
        client.get("/", query_string={"kind": "scalars", "tag": "x"}).status_code == 404
    )
    assert client.get("/", query_string={"kind": "images"}).status_code == 404


def test_chart_page_closes_the_figures_it_drew(logdir):
    from maidr.core.figure_manager import FigureManager

    before = len(FigureManager.figs)
    chart_page(str(logdir), "hparams", index="1")
    assert len(FigureManager.figs) == before


def test_importing_maidr_does_not_import_tensorboard():
    import subprocess
    import sys

    code = "import sys, maidr; print('tensorboard' in sys.modules)"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "False"
