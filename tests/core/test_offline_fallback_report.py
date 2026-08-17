"""
``use_cdn="auto"`` says something when it runs out of sources (#455).

The setting is documented as "try the CDN, fall back to the bundled copy".
Inside a ``srcdoc`` iframe -- what a notebook, Shiny or Flask render produces
-- neither fallback can resolve, and both used to fail in silence: the
notebook one acts only ``if (jsSrc)`` and swallows the miss in a bare
``catch``, and the other never set ``onerror`` at all.

What the reader gets is a chart with no MAIDR runtime. It renders, it looks
like a chart, and nothing anywhere says why it cannot be navigated -- which is
the worst version of this failure, because the person hitting it is on an
air-gapped deployment and the setting that works (``use_cdn=False``) is
otherwise only discoverable by reading the source.

These assert on the emitted script rather than on browser behaviour: what is
in scope here is that every path out of the fallback reports, and that the
report names the fix.
"""

from __future__ import annotations

import matplotlib
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

import maidr  # noqa: E402,F401
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.core.maidr import _OFFLINE_FALLBACK_REPORT  # noqa: E402


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _rendered(monkeypatch, *, notebook: bool) -> str:
    """Render a bar chart as the given environment would."""
    monkeypatch.setattr(
        "maidr.util.environment.Environment.is_notebook", lambda: notebook
    )
    monkeypatch.setattr(
        "maidr.util.environment.Environment.is_shiny", lambda: not notebook
    )
    monkeypatch.setattr("maidr.util.environment.Environment.is_flask", lambda: False)

    fig, ax = plt.subplots()
    ax.bar(["a", "b"], [1, 2])
    return str(FigureManager.figs[fig].render(use_cdn="auto").get_html_string())


class TestTheReportIsWritten:
    def test_it_names_the_setting_that_works(self) -> None:
        # Describing the failure is not enough: the reader needs the answer,
        # and `use_cdn=False` is not guessable from a blank chart.
        assert "use_cdn=False" in _OFFLINE_FALLBACK_REPORT

    def test_it_is_an_error_rather_than_a_log(self) -> None:
        # A console.log is filtered out of most default consoles; this is a
        # dead chart, not a diagnostic.
        assert "console.error" in _OFFLINE_FALLBACK_REPORT

    def test_its_braces_are_not_doubled(self) -> None:
        # It is interpolated into f-strings, so doubling would emit literal
        # `{{` into the page and break the script it is embedded in.
        assert "{{" not in _OFFLINE_FALLBACK_REPORT


class TestEveryAutoPathCanReport:
    def test_the_notebook_render_defines_the_reporter(self, monkeypatch) -> None:
        # The *definition*, not merely the name. The call sites survive on
        # their own, and a script that calls an undefined function throws
        # `ReferenceError` -- which is worse than the silence being fixed,
        # and is what a weaker assertion here let through.
        rendered = _rendered(monkeypatch, notebook=True)

        assert "function reportNoRuntime" in rendered

    def test_the_notebook_render_reports_a_missing_stash(self, monkeypatch) -> None:
        # `init_notebook()` not having run is the reachable case, and the
        # `if (jsSrc)` guard used to drop it on the floor.
        rendered = _rendered(monkeypatch, notebook=True)

        assert "no stashed copy" in rendered

    def test_the_notebook_render_reports_an_unreachable_parent(
        self, monkeypatch
    ) -> None:
        # The bare `catch (_) {}` swallowed a cross-origin parent.
        rendered = _rendered(monkeypatch, notebook=True)

        assert "parent page is unreachable" in rendered

    def test_the_iframe_render_defines_the_reporter(self, monkeypatch) -> None:
        rendered = _rendered(monkeypatch, notebook=False)

        assert "function reportNoRuntime" in rendered

    def test_the_iframe_fallback_script_reports_on_error(self, monkeypatch) -> None:
        # The relative `lib/` path cannot resolve inside a srcdoc iframe, so
        # this is the path an air-gapped Shiny deployment actually takes --
        # and it had no `onerror` at all.
        rendered = _rendered(monkeypatch, notebook=False)

        assert "fb.onerror" in rendered
        assert "did not load" in rendered
