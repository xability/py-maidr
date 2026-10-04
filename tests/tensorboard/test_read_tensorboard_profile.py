"""A TensorBoard profile read as its step-time graph and top operations.

``fixtures/tf_profile`` holds the XPlane file ``tf.profiler`` wrote for eight
training steps of a small Keras model, and the two ``tf_profile.*.json`` files
beside it are what the profile plugin's converter (``xprof``) made of it. The
charts are tested from those tables, so the tests need no converter; the one
test of the conversion itself runs only where ``xprof`` is installed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from maidr.core.figure_manager import FigureManager
from maidr.tensorboard import profile as profile_module
from maidr.tensorboard.profile import (
    find_profiles,
    profile_charts,
    read_tensorboard_profile,
)

FIXTURES = Path(__file__).parent / "fixtures"
PROFILE = FIXTURES / "tf_profile"
INPUT_PIPELINE = (FIXTURES / "tf_profile.input_pipeline_analyzer.json").read_text()
OP_STATS = (FIXTURES / "tf_profile.framework_op_stats.json").read_text()


def _layers(chart) -> list[dict]:
    schema = json.loads(
        json.dumps(FigureManager.get_maidr(chart.figure)._flatten_maidr())
    )
    return [
        layer for row in schema["subplots"] for cell in row for layer in cell["layers"]
    ]


def test_the_sessions_are_found_with_their_xplane_files():
    sessions = find_profiles(PROFILE)
    assert list(sessions) == ["2026_10_04_12_28_21"]
    assert [Path(p).name for p in sessions["2026_10_04_12_28_21"]] == ["vm.xplane.pb"]


def test_the_step_time_graph_stacks_where_each_step_went():
    step_time, _ = profile_charts(INPUT_PIPELINE, OP_STATS, session="s")
    assert step_time.tag == "profile/step_time"
    (layer,) = _layers(step_time)
    assert layer["type"] == "stacked_bar"
    assert layer["axes"]["x"]["label"] == "Step"
    assert layer["axes"]["y"]["label"] == "Step time (ms)"
    names = [series[0]["z"] for series in layer["data"]]
    assert names == ["Host compute", "All others"]
    assert [point["x"] for point in layer["data"][0]] == [
        f"train {i}" for i in range(8)
    ]
    expected = json.loads(INPUT_PIPELINE)[1]["rows"][0]["c"]
    assert layer["data"][0][0]["y"] == pytest.approx(expected[4]["v"])


def test_the_top_operations_are_the_types_with_the_most_self_time():
    _, top = profile_charts(INPUT_PIPELINE, OP_STATS, top=5)
    (layer,) = _layers(top)
    assert layer["type"] == "bar"
    assert layer["axes"]["x"]["label"] == "Total self time (ms)"
    assert len(layer["data"]) == 5
    rows = json.loads(OP_STATS)[1]["rows"]
    totals: dict[str, float] = {}
    for row in rows:
        cells = [cell["v"] for cell in row["c"]]
        totals[cells[2]] = totals.get(cells[2], 0) + cells[7]
    largest = max((t for k, t in totals.items() if k != "IDLE"))
    assert max(
        point["x"] if isinstance(point["x"], float) else point["y"]
        for point in layer["data"]
    ) == pytest.approx(largest / 1000, rel=1e-3)


def test_a_profile_without_steps_or_operations_says_so():
    empty = json.dumps([{"cols": [], "rows": []}])
    with pytest.warns(UserWarning) as caught:
        assert profile_charts(empty, empty) == []
    assert {str(w.message).split(";")[0] for w in caught} == {
        "The profile records no steps",
        "The profile records no operations",
    }


def test_reading_converts_the_latest_session(monkeypatch):
    calls = []

    def convert(paths, tool):
        calls.append((tuple(Path(p).name for p in paths), tool))
        return {
            "input_pipeline_analyzer": INPUT_PIPELINE,
            "framework_op_stats": OP_STATS,
        }[tool]

    monkeypatch.setattr(profile_module, "_convert", convert)
    charts = read_tensorboard_profile(PROFILE)
    assert [chart.tag for chart in charts] == [
        "profile/step_time",
        "profile/top_operations",
    ]
    assert charts[0].runs == ("2026_10_04_12_28_21",)
    assert [tool for _, tool in calls] == [
        "input_pipeline_analyzer",
        "framework_op_stats",
    ]
    with pytest.raises(FileNotFoundError, match="No profile session 'x'"):
        read_tensorboard_profile(PROFILE, session="x")


def test_a_directory_with_no_profile_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="holds no TensorBoard profile"):
        read_tensorboard_profile(tmp_path)


def test_without_the_converter_reading_says_what_to_install(monkeypatch):
    monkeypatch.setitem(sys.modules, "xprof", None)
    monkeypatch.setitem(sys.modules, "xprof.convert", None)
    monkeypatch.setitem(sys.modules, "tensorboard_plugin_profile", None)
    with pytest.raises(ImportError, match="pip install xprof"):
        read_tensorboard_profile(PROFILE)


def test_the_converter_makes_these_tables_of_the_xplane_file():
    pytest.importorskip("xprof")
    (paths,) = find_profiles(PROFILE).values()
    converted = profile_module._convert(paths, "input_pipeline_analyzer")
    assert json.loads(converted)[1]["rows"] == json.loads(INPUT_PIPELINE)[1]["rows"]
