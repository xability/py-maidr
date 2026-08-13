"""Tests for asking the bundle what it can draw, rather than how old it is.

``STALE_MINOR_GAP`` measures drift in minor versions, which answers "how
old is this bundle?" The question a reader needs answered is "can this
bundle draw what I am about to hand it?", and the two come apart in both
directions: a bundle five minors behind may render everything this package
emits, and one minor behind may render none of a newly added type. The gap
that prompted this was a bundle nine minors short of qualifying as stale
while unable to render seven of the layer types being emitted (#358).

The check is also the only one of the two that reaches the audience it is
for. ``warn_if_bundle_is_stale`` compares against a published version it
will not fetch, so a process rendering ``use_cdn=False`` offline — exactly
the user whose bundle is what runs — stays silent however old it is. This
reads the installed file and needs no network at all.
"""

from __future__ import annotations

import warnings

import matplotlib.pyplot as plt
import pytest

import maidr
from maidr.core.enum.plot_type import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.util import dependencies
from maidr.util.dependencies import (
    MaidrBundleTraceWarning,
    bundle_trace_types,
    schema_trace_types,
    warn_if_bundle_cannot_render,
)


@pytest.fixture(autouse=True)
def _fresh_latch(monkeypatch):
    """Give each test its own once-per-process latch.

    The warning fires once per trace type per severity for the life of the
    process, which is the behaviour a user wants and the one that would
    otherwise make every test after the first pass vacuously.
    """
    monkeypatch.setattr(dependencies, "_bundle_trace_warned", set())


@pytest.fixture
def bar_plot():
    fig, ax = plt.subplots()
    ax.bar(["A", "B", "C"], [1.0, 2.0, 3.0])
    yield fig
    plt.close(fig)


#: Stand-ins for "a type this bundle cannot build", spelled so that no
#: release can turn them into types it can.
#:
#: These were `"treemap"` and `"sankey"` -- real types the bundle genuinely
#: lacked when this file was written. maidr 4.2.0 shipped both, the bundle
#: update landed, and five cases here went from testing the warning to
#: asserting that a supported type warns. They failed loudly, which was
#: luck: the same release could as easily have made them pass vacuously.
#:
#: Nothing about the check depends on the name being real. It is a set
#: difference between the types a schema carries and the types the bundle
#: quotes, so an absent name is an absent name. What matters is that these
#: stay absent, which `test_the_stand_ins_are_really_absent` is for.
UNBUILDABLE = "maidr_test_unbuildable_trace"
OTHER_UNBUILDABLE = "maidr_test_second_unbuildable_trace"


def _caught(action) -> list[str]:
    """Run ``action`` and return the capability warnings it raised."""
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        action()
    return [
        str(record.message)
        for record in records
        if issubclass(record.category, MaidrBundleTraceWarning)
    ]


# ---------------------------------------------------------------------------
# Reading the bundle
# ---------------------------------------------------------------------------


def test_the_bundle_names_the_types_it_can_build():
    """
    The scan finds real trace types in the shipped file.

    Not a tautology: the 4.1.0 bundle quotes its identifiers with
    **backticks**, so a scan written for double quotes alone finds nothing
    and every layer of every chart is reported missing. This is the case
    that separates "read the bundle" from "read it correctly".
    """
    types = bundle_trace_types()

    assert len(types) > 100
    for expected in ("bar", "box", "heat", "line", "pie", "scatter"):
        assert expected in types, expected


def test_an_unreadable_bundle_reports_nothing_rather_than_everything():
    """
    A missing file must not become "this bundle renders nothing".

    That would warn about every layer of every chart on the strength of an
    installation problem, which is both wrong and the loudest possible way
    to be wrong.
    """
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        warn_if_bundle_cannot_render(["definitely_not_a_trace_type"])
        loud = [r for r in records if issubclass(r.category, MaidrBundleTraceWarning)]

    # Sanity: the fixture bundle *is* readable, so that call warned.
    assert loud

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(dependencies, "_bundle_tokens", frozenset())
        assert _caught(
            lambda: warn_if_bundle_cannot_render(["definitely_not_a_trace_type"])
        ) == []


# ---------------------------------------------------------------------------
# Reading the schema
# ---------------------------------------------------------------------------


def test_a_layer_type_is_collected_as_the_string_it_is_emitted_as(bar_plot):
    """
    A schema in memory holds a ``PlotType``, not a string.

    ``PlotType`` subclasses ``str``, so it compares and hashes as its value
    while ``str()`` of it is ``"PlotType.BAR"``. Asking the bundle about
    that name reports every layer missing — which the first draft of this
    did, and which a plain bar chart caught immediately.
    """
    schema = FigureManager.figs.get(bar_plot)._flatten_maidr()

    collected = schema_trace_types(schema)

    # Equality alone would pass on the enum member, which compares equal to
    # its value -- so the point is that what came out is not one.
    assert collected == {"bar"}
    assert not any(isinstance(name, PlotType) for name in collected)
    assert all(str(name) == "bar" for name in collected)


def test_the_enum_is_not_the_source_of_truth():
    """
    ``PlotType`` and the emitted types are different sets.

    A ``seaborn.countplot`` is classified ``PlotType.COUNT`` and emitted as
    ``bar``, so a check driven by the enum would ask the bundle about
    ``count`` — a string no schema carries and no bundle builds — and warn
    about a chart that renders perfectly.
    """
    assert PlotType.COUNT.value == "count"
    assert "count" not in bundle_trace_types()

    frame_x = ["a", "a", "b"]
    fig, ax = plt.subplots()
    try:
        import seaborn as sns

        sns.countplot(x=frame_x, ax=ax)
        schema = FigureManager.figs.get(fig)._flatten_maidr()

        assert schema_trace_types(schema) == {"bar"}
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# Warning
# ---------------------------------------------------------------------------


def test_the_stand_ins_are_really_absent():
    """Every case below is vacuous if the bundle learns to build these.

    The guard that was missing. `"treemap"` and `"sankey"` were real types
    the bundle lacked; maidr 4.2.0 shipped both and five cases silently
    stopped testing what they were named for. They happened to fail, which
    is not the same as being caught -- a release that made them pass
    instead would have left the file green and empty.

    Nothing here rests on the names being real, only on their being
    missing, so this is the whole invariant the rest of the section needs.
    """
    types = bundle_trace_types()

    # Not vacuous itself: an empty set would satisfy the two below.
    assert "bar" in types
    assert UNBUILDABLE not in types
    assert OTHER_UNBUILDABLE not in types


def test_a_type_the_bundle_cannot_build_is_named(bar_plot):
    """The reader is told which type, and what to do about it."""
    messages = _caught(lambda: warn_if_bundle_cannot_render([UNBUILDABLE]))

    assert len(messages) == 1
    assert UNBUILDABLE in messages[0]
    assert "use_cdn" in messages[0]


def test_every_unsupported_type_is_named_at_once():
    """
    Two missing types are one report, not one report about the first.

    A user whose chart needs both should not have to upgrade, re-render and
    discover the second.
    """
    messages = _caught(
        lambda: warn_if_bundle_cannot_render([OTHER_UNBUILDABLE, "bar", UNBUILDABLE])
    )

    assert len(messages) == 1
    assert OTHER_UNBUILDABLE in messages[0]
    assert UNBUILDABLE in messages[0]
    # The supported one is not mentioned as a problem.
    assert "bar," not in messages[0]


def test_a_type_is_reported_once_per_process():
    """A chart rendered in a loop says it once."""
    first = _caught(lambda: warn_if_bundle_cannot_render([UNBUILDABLE]))
    second = _caught(lambda: warn_if_bundle_cannot_render([UNBUILDABLE]))

    assert len(first) == 1
    assert second == []


def test_a_second_unsupported_type_is_not_swallowed_by_the_first():
    """
    Latched per type rather than per process.

    One shared latch would let the first type consume the single report and
    leave a later, differently unbuildable one permanently unmentioned.
    """
    _caught(lambda: warn_if_bundle_cannot_render([UNBUILDABLE]))
    later = _caught(lambda: warn_if_bundle_cannot_render([OTHER_UNBUILDABLE]))

    assert len(later) == 1
    assert OTHER_UNBUILDABLE in later[0]


def test_the_auto_path_reports_to_the_logger_rather_than_warning(caplog):
    """
    Under ``use_cdn="auto"`` the CDN copy normally loads.

    A warning there is about code that did not run, and under ``-W error``
    it would redden a downstream suite over it. Same reasoning the
    staleness warning already applies.
    """
    with caplog.at_level("WARNING", logger="maidr.util.dependencies"):
        messages = _caught(
            lambda: warn_if_bundle_cannot_render([UNBUILDABLE], bundle_is_primary=False)
        )

    assert messages == []
    assert any(UNBUILDABLE in record.message for record in caplog.records)


def test_the_two_severities_do_not_share_a_latch():
    """
    The quiet ``auto`` report must not consume the loud one.

    ``auto`` is the default and so almost always runs first; sharing a
    latch would leave the ``use_cdn=False`` warning — the audience this
    exists for — permanently unreachable.
    """
    warn_if_bundle_cannot_render([UNBUILDABLE], bundle_is_primary=False)
    messages = _caught(lambda: warn_if_bundle_cannot_render([UNBUILDABLE]))

    assert len(messages) == 1


def test_the_env_switch_silences_it(monkeypatch):
    """Same knob as the staleness warning: bundle chatter off means off."""
    monkeypatch.setenv(dependencies.BUNDLE_WARNING_ENV_VAR, "0")

    assert _caught(lambda: warn_if_bundle_cannot_render([UNBUILDABLE])) == []


# ---------------------------------------------------------------------------
# The render path
# ---------------------------------------------------------------------------


def test_a_chart_the_bundle_can_draw_says_nothing(bar_plot):
    """
    The over-correction, guarded.

    A check that warned on a supported chart would be worse than the gap it
    replaces — every user of every chart would learn to ignore it.
    """
    assert _caught(lambda: maidr.render(bar_plot, use_cdn=False)) == []


def test_rendering_asks_the_bundle_about_what_it_is_about_to_emit(
    bar_plot, monkeypatch
):
    """
    The warning reaches the render path, not just its own unit test.

    Asserted by making the bundle claim it cannot draw a bar, which is the
    only way to exercise the wiring without a layer type this package
    cannot yet emit.
    """
    monkeypatch.setattr(dependencies, "_bundle_tokens", frozenset({"line"}))

    messages = _caught(lambda: maidr.render(bar_plot, use_cdn=False))

    assert len(messages) == 1
    assert "bar" in messages[0]


def test_the_cdn_only_path_says_nothing_about_a_bundle_that_will_not_run(
    bar_plot, monkeypatch
):
    """
    ``use_cdn=True`` never loads the bundled copy.

    Warning there would be about a file the page does not reference.
    """
    monkeypatch.setattr(dependencies, "_bundle_tokens", frozenset({"line"}))

    assert _caught(lambda: maidr.render(bar_plot, use_cdn=True)) == []


def test_the_warning_category_is_reachable_from_the_package():
    """
    A dedicated category is only useful if a consumer can name it.

    ``MaidrBundleStaleWarning`` is re-exported from the package root and its
    docstring shows the filter, so this one being reachable only through
    ``maidr.util.dependencies`` would quietly break the same story. Every
    other test here imports from the module, so none of them would notice.
    """
    import maidr as package

    assert package.MaidrBundleTraceWarning is MaidrBundleTraceWarning
    assert "MaidrBundleTraceWarning" in package.__all__
    assert "MaidrBundleStaleWarning" in package.__all__
