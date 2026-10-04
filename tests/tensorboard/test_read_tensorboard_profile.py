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


def test_only_the_tables_the_charts_asked_for_need_are_converted(monkeypatch):
    tools = []

    def convert(paths, tool):
        tools.append(tool)
        return OP_STATS

    monkeypatch.setattr(profile_module, "_convert", convert)
    (chart,) = read_tensorboard_profile(PROFILE, charts=["top_operations"])
    assert chart.tag == "profile/top_operations"
    assert tools == ["framework_op_stats"]
    with pytest.raises(ValueError, match="not \\['memory'\\]"):
        read_tensorboard_profile(PROFILE, charts=["memory"])


def test_the_latest_session_is_chosen_the_same_whatever_the_order(tmp_path):
    for run in ("b", "a"):
        session = tmp_path / run / "plugins" / "profile" / "2026_10_04_12_00_00"
        session.mkdir(parents=True)
        (session / "host.xplane.pb").write_bytes(b"")
    sessions = find_profiles(tmp_path)
    latest = max(sessions, key=lambda name: (name.rsplit("/", 1)[-1], name))
    assert latest == "b/2026_10_04_12_00_00"


def test_the_converter_is_called_and_its_bytes_decoded(monkeypatch):
    import types

    calls = []

    def xspace_to_tool_data(paths, tool, params):
        calls.append((tuple(paths), tool, params))
        return OP_STATS.encode("utf-8"), "application/json"

    convert = types.ModuleType("raw_to_tool_data")
    convert.xspace_to_tool_data = xspace_to_tool_data
    package = types.ModuleType("xprof.convert")
    package.raw_to_tool_data = convert
    monkeypatch.setitem(sys.modules, "xprof", types.ModuleType("xprof"))
    monkeypatch.setitem(sys.modules, "xprof.convert", package)
    monkeypatch.setitem(sys.modules, "xprof.convert.raw_to_tool_data", convert)
    assert profile_module._convert(["a.xplane.pb"], "framework_op_stats") == OP_STATS
    assert calls == [(("a.xplane.pb",), "framework_op_stats", {})]


def test_the_older_profile_plugin_is_used_without_xprof(monkeypatch):
    import types

    convert = types.ModuleType("raw_to_tool_data")
    convert.xspace_to_tool_data = lambda paths, tool, params: (INPUT_PIPELINE, "")
    package = types.ModuleType("tensorboard_plugin_profile.convert")
    package.raw_to_tool_data = convert
    monkeypatch.setitem(sys.modules, "xprof", None)
    monkeypatch.setitem(sys.modules, "xprof.convert", None)
    monkeypatch.setitem(
        sys.modules, "tensorboard_plugin_profile", types.ModuleType("tbpp")
    )
    monkeypatch.setitem(sys.modules, "tensorboard_plugin_profile.convert", package)
    monkeypatch.setitem(
        sys.modules, "tensorboard_plugin_profile.convert.raw_to_tool_data", convert
    )
    assert profile_module._convert(["a"], "input_pipeline_analyzer") == INPUT_PIPELINE


def test_the_gallery_draws_the_same_tables_the_tests_read():
    docs = Path(__file__).parents[2] / "docs" / "tensorboard-profile"
    assert (docs / "input_pipeline_analyzer.json").read_text() == INPUT_PIPELINE
    assert (docs / "framework_op_stats.json").read_text() == OP_STATS
