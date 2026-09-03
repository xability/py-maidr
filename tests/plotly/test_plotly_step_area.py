"""A stepped area lost its step semantics (#413).

``line.shape`` and ``stackgroup`` are independent plotly attributes, so a
trace can be both a staircase and a filled band. Since #411 the area
classification runs first, so such a trace became a plain ``area`` layer with
no ``stepDirection`` on it; before #411 it fell into the step grouping and
kept the direction but was announced as a line. Neither reading was ever
complete -- one of the two facts was always dropped.

They are orthogonal, so the layer carries both: the area type says the band is
filled and how it stacks, ``stepDirection`` says what happens between samples.
The core reads the pair (xability/maidr#902), and its highlight only lands on
the samples once the path parser reads the ``H``/``V`` commands a staircase is
drawn with (xability/maidr#907).

A stacked step area is the standard way to draw a cumulative count that
changes at discrete events, which is why this is worth carrying rather than
approximating: read as a smoothly interpolated band, every interval tells a
reader the value slid when it in fact held and then jumped.
"""

from __future__ import annotations

import pytest

pytest.importorskip("plotly")

import plotly.graph_objects as go  # noqa: E402

from maidr.core.enum.plot_type import PlotType  # noqa: E402
from maidr.plotly.plotly_maidr import PlotlyMaidr  # noqa: E402
from maidr.plotly.step_shape import shared_step_direction  # noqa: E402

X = [1, 2, 3]


def layers(fig) -> list[dict]:
    return PlotlyMaidr(fig)._flatten_maidr()["subplots"][0][0]["layers"]


def band(shape: str | None = None, name: str = "a", y: list | None = None):
    line = {"shape": shape} if shape is not None else None
    return go.Scatter(
        x=X,
        y=y if y is not None else [1, 2, 3],
        stackgroup="one",
        name=name,
        **({"line": line} if line else {}),
    )


class TestAnAreaCarriesItsStepDirection:
    @pytest.mark.parametrize(
        ("shape", "expected"),
        [("hv", "hv"), ("vh", "vh"), ("hvh", "mid")],
    )
    def test_a_lone_stepped_band(self, shape, expected):
        found = layers(go.Figure([band(shape)]))
        assert len(found) == 1
        assert found[0]["stepDirection"] == expected

    def test_a_stacked_step_area_keeps_both_facts(self):
        # The shape the issue names. Neither fact displaces the other: the
        # type still says the bands are filled and stack, and the direction
        # still says the value holds and then jumps.
        fig = go.Figure([band("hv", "a"), band("hv", "b", [2, 1, 4])])
        found = layers(fig)
        assert len(found) == 1
        assert found[0]["type"] == PlotType.STACKED_AREA
        assert found[0]["stepDirection"] == "hv"

    def test_a_normalized_step_area_keeps_both_facts(self):
        fig = go.Figure(
            [
                go.Scatter(
                    x=X,
                    y=[1, 2, 3],
                    stackgroup="one",
                    groupnorm="percent",
                    line=dict(shape="hv"),
                    name="a",
                ),
                go.Scatter(
                    x=X,
                    y=[2, 1, 4],
                    stackgroup="one",
                    line=dict(shape="hv"),
                    name="b",
                ),
            ]
        )
        found = layers(fig)
        assert found[0]["type"] == PlotType.NORMALIZED_AREA
        assert found[0]["stepDirection"] == "hv"

    def test_the_band_is_still_an_area_and_not_a_step(self):
        # The regression this replaces: before #411 a stepped band kept its
        # direction by being classified as a step, which lost the fill.
        found = layers(go.Figure([band("hv")]))
        assert found[0]["type"] == PlotType.AREA


class TestSilenceIsKeptWhereThereIsNothingToSay:
    def test_a_plain_area_authors_no_direction(self):
        assert "stepDirection" not in layers(go.Figure([band()]))[0]

    def test_a_linear_shape_authors_no_direction(self):
        # `linear` interpolates between samples, which is what a step does
        # not do. Naming a direction for it would be a claim about the data.
        assert "stepDirection" not in layers(go.Figure([band("linear")]))[0]

    def test_a_spline_authors_no_direction(self):
        assert "stepDirection" not in layers(go.Figure([band("spline")]))[0]

    def test_vhv_binds_as_an_area_without_claiming_a_convention(self):
        # `vhv` holds a value *between* two samples rather than at one, so
        # MAIDR has no name for it. The band still binds -- the data is
        # piecewise constant -- it just does not claim a convention.
        found = layers(go.Figure([band("vhv")]))
        assert len(found) == 1
        assert found[0]["type"] == PlotType.AREA
        assert "stepDirection" not in found[0]

    def test_a_stack_whose_bands_disagree_says_nothing(self):
        # A stack cannot be split by direction the way the step layers are:
        # its bands are one stack, and separating them would leave the core
        # summing a part of it and announcing that as the total. So the layer
        # stays whole and withholds the key rather than describing one of its
        # bands wrongly.
        fig = go.Figure([band("hv", "a"), band("vh", "b", [2, 1, 4])])
        found = layers(fig)
        assert len(found) == 1
        assert found[0]["type"] == PlotType.STACKED_AREA
        assert "stepDirection" not in found[0]

    def test_a_stack_of_a_stepped_and_a_plain_band_says_nothing(self):
        # The asymmetric case: one band authors `hv`, the other authors
        # nothing. "Nothing" is a real disagreement -- plotly interpolates
        # that band -- so the layer must not adopt its neighbour's direction.
        fig = go.Figure([band("hv", "a"), band(None, "b", [2, 1, 4])])
        assert "stepDirection" not in layers(fig)[0]


class TestTheTwoStackGroupsAreAnsweredSeparately:
    def test_each_group_keeps_its_own_convention(self):
        # Groups are independent stacks, so one being mixed must not silence
        # the other.
        fig = go.Figure(
            [
                go.Scatter(
                    x=X, y=[1, 2, 3], stackgroup="one", line=dict(shape="hv"), name="a"
                ),
                go.Scatter(
                    x=X, y=[2, 1, 4], stackgroup="two", line=dict(shape="vh"), name="b"
                ),
            ]
        )
        found = layers(fig)
        assert len(found) == 2
        assert [entry["stepDirection"] for entry in found] == ["hv", "vh"]


class TestSharedStepDirection:
    """The resolver both layer types read, asked directly."""

    def test_one_shape_resolves(self):
        assert shared_step_direction([{"line": {"shape": "hv"}}]) == "hv"

    def test_agreement_across_traces_resolves(self):
        traces = [{"line": {"shape": "vh"}}, {"line": {"shape": "vh"}}]
        assert shared_step_direction(traces) == "vh"

    def test_disagreement_resolves_to_none(self):
        traces = [{"line": {"shape": "hv"}}, {"line": {"shape": "vh"}}]
        assert shared_step_direction(traces) is None

    def test_no_shape_resolves_to_none(self):
        assert shared_step_direction([{}]) is None

    def test_an_unnamed_convention_resolves_to_none(self):
        assert shared_step_direction([{"line": {"shape": "vhv"}}]) is None

    def test_an_empty_set_resolves_to_none(self):
        # Not reachable through either layer -- both reject an empty trace
        # list in their constructor -- but the resolver is the shared piece,
        # so it answers rather than raising.
        assert shared_step_direction([]) is None


class TestTheStepLayerIsUnchanged:
    """The step path reads the same resolver now; its answers must not move."""

    def test_a_step_line_still_carries_its_direction(self):
        fig = go.Figure(
            [go.Scatter(x=X, y=[1, 2, 3], mode="lines", line=dict(shape="hv"))]
        )
        found = layers(fig)
        assert found[0]["type"] == PlotType.STEP
        assert found[0]["stepDirection"] == "hv"

    def test_a_vhv_step_line_still_withholds_it(self):
        fig = go.Figure(
            [go.Scatter(x=X, y=[1, 2, 3], mode="lines", line=dict(shape="vhv"))]
        )
        found = layers(fig)
        assert found[0]["type"] == PlotType.STEP
        assert "stepDirection" not in found[0]
