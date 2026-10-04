"""Embeddings read out of an Embedding Projector log directory.

``fixtures/torch_embedding`` was written by PyTorch's ``add_embedding``: three
clusters of eight-dimensional vectors, labelled ``cat``, ``dog`` and ``bird``
in a two-column metadata file. ``torch_embedding.expected.json`` records what
was written.
"""

from __future__ import annotations

import json
import sys
import types
import warnings
from pathlib import Path

import numpy as np
import pytest

from maidr.core.figure_manager import FigureManager
from maidr.tensorboard import load_embeddings, read_tensorboard_projector
from maidr.tensorboard.projector import project

FIXTURES = Path(__file__).parent / "fixtures"
TORCH = FIXTURES / "torch_embedding"


def _layers(chart) -> list[dict]:
    schema = json.loads(
        json.dumps(FigureManager.get_maidr(chart.figure)._flatten_maidr())
    )
    return [
        layer for row in schema["subplots"] for cell in row for layer in cell["layers"]
    ]


def test_the_vectors_and_labels_are_the_ones_written():
    expected = json.loads((FIXTURES / "torch_embedding.expected.json").read_text())
    (embedding,) = load_embeddings(TORCH)
    assert embedding.name == "animals:00000"
    np.testing.assert_allclose(
        embedding.vectors, expected["animals"]["vectors"], rtol=1e-6
    )
    assert embedding.metadata["label"] == expected["animals"]["labels"]
    assert embedding.metadata["index"] == [str(i) for i in range(60)]


def test_one_scatter_layer_per_label_on_the_principal_components():
    (chart,) = read_tensorboard_projector(TORCH)
    assert chart.runs == ("cat", "dog", "bird")
    layers = _layers(chart)
    assert [layer["type"] for layer in layers] == ["point"] * 3
    assert {len(layer["data"]) for layer in layers} == {20}
    assert layers[0]["axes"]["x"]["label"].startswith("Component 1 (")
    assert layers[0]["axes"]["y"]["label"].startswith("Component 2 (")


def test_the_clusters_are_kept_apart_by_the_projection():
    (chart,) = read_tensorboard_projector(TORCH)
    centers = [
        np.mean([[p["x"], p["y"]] for p in layer["data"]], axis=0)
        for layer in _layers(chart)
    ]
    spread = max(
        np.std([[p["x"], p["y"]] for p in layer["data"]]) for layer in _layers(chart)
    )
    gaps = [np.linalg.norm(a - b) for a in centers for b in centers if a is not b]
    assert min(gaps) > 2 * spread


def test_precomputed_coordinates_are_drawn_instead(tmp_path):
    coordinates = np.arange(120, dtype=float).reshape(60, 2)
    (chart,) = read_tensorboard_projector(TORCH, coordinates=coordinates)
    first = _layers(chart)[0]
    assert first["axes"]["x"]["label"] == "Dimension 1"
    assert first["data"][0] == {"x": 0.0, "y": 1.0}
    with pytest.raises(ValueError, match="two values for each"):
        read_tensorboard_projector(TORCH, coordinates=coordinates[:5])


def test_another_metadata_column_groups_the_points():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        (chart,) = read_tensorboard_projector(TORCH, label="index", max_points=None)
    assert len(chart.runs) == 60
    with pytest.warns(UserWarning, match="no metadata column 'kind'"):
        (chart,) = read_tensorboard_projector(TORCH, label="kind")
    assert chart.runs == ("cat", "dog", "bird")


def test_many_points_are_sampled_with_a_warning():
    with pytest.warns(UserWarning, match="60 points; 10 of them"):
        (chart,) = read_tensorboard_projector(TORCH, max_points=10)
    assert sum(len(layer["data"]) for layer in _layers(chart)) == 10


def test_a_one_column_metadata_file_is_labels_without_a_header(tmp_path):
    (tmp_path / "v.tsv").write_text("0\t0\n1\t1\n5\t5\n")
    (tmp_path / "m.tsv").write_text("a\nb\nb\n")
    (tmp_path / "projector_config.pbtxt").write_text(
        'embeddings {\n  tensor_name: "e"\n  tensor_path: "v.tsv"\n'
        '  metadata_path: "m.tsv"\n  sprite {\n    image_path: "s.png"\n  }\n}\n'
    )
    (embedding,) = load_embeddings(tmp_path)
    assert embedding.metadata == {"label": ["a", "b", "b"]}
    (chart,) = read_tensorboard_projector(tmp_path)
    assert chart.runs == ("a", "b")


def test_a_checkpoint_is_read_through_tensorflow_when_installed(tmp_path, monkeypatch):
    (tmp_path / "projector_config.pbtxt").write_text(
        'model_checkpoint_path: "ckpt-1"\n'
        'embeddings {\n  tensor_name: "layer/embeddings"\n}\n'
    )
    calls = []
    fake = types.ModuleType("tensorflow")
    fake.train = types.SimpleNamespace(
        load_variable=lambda where, name: calls.append((where, name)) or np.eye(3),
        latest_checkpoint=lambda path: None,
    )
    monkeypatch.setitem(sys.modules, "tensorflow", fake)
    (embedding,) = load_embeddings(tmp_path)
    assert calls == [(str(tmp_path / "ckpt-1"), "layer/embeddings")]
    assert embedding.vectors.shape == (3, 3)


def test_a_checkpoint_without_tensorflow_is_warned_about(tmp_path, monkeypatch):
    (tmp_path / "projector_config.pbtxt").write_text(
        'embeddings {\n  tensor_name: "layer/embeddings"\n}\n'
    )
    monkeypatch.setitem(sys.modules, "tensorflow", None)
    with pytest.warns(UserWarning, match="only with TensorFlow installed"):
        assert load_embeddings(tmp_path) == []


def test_a_directory_with_no_config_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="projector_config.pbtxt"):
        load_embeddings(tmp_path)


def test_project_returns_the_variance_each_component_explains():
    vectors = np.array([[0.0, 0.0], [2.0, 0.0], [4.0, 0.1], [6.0, 0.0]])
    coordinates, explained = project(vectors)
    assert coordinates.shape == (4, 2)
    assert explained[0] > 0.99 and explained.sum() == pytest.approx(1.0)


def test_metadata_shorter_than_the_vectors_is_padded_with_a_warning(tmp_path):
    (tmp_path / "v.tsv").write_text("0\t0\n1\t1\n5\t5\n")
    (tmp_path / "m.tsv").write_text("a\nb\n")
    (tmp_path / "projector_config.pbtxt").write_text(
        'embeddings {\n  tensor_name: "e"\n  tensor_path: "v.tsv"\n'
        '  metadata_path: "m.tsv"\n}\n'
    )
    with pytest.warns(UserWarning, match="metadata labels fewer"):
        (chart,) = read_tensorboard_projector(tmp_path)
    assert chart.runs == ("a", "b", "")


def test_escaped_and_non_ascii_names_are_read_as_utf8(tmp_path):
    (tmp_path / "café.tsv").write_text("0\t0\n1\t1\n")
    (tmp_path / "projector_config.pbtxt").write_text(
        'embeddings {\n  tensor_name: "caf\\303\\251 \\"x\\""\n'
        '  tensor_path: "café.tsv"\n}\n',
        encoding="utf-8",
    )
    (embedding,) = load_embeddings(tmp_path)
    assert embedding.name == 'café "x"'
    assert embedding.vectors.shape == (2, 2)


def test_a_malformed_tsv_is_warned_about_and_left_out(tmp_path):
    (tmp_path / "v.tsv").write_text("x\ty\n0\t0\n")
    (tmp_path / "projector_config.pbtxt").write_text(
        'embeddings {\n  tensor_name: "e"\n  tensor_path: "v.tsv"\n}\n'
    )
    with pytest.warns(UserWarning, match="could not read 'e'"):
        assert load_embeddings(tmp_path) == []
