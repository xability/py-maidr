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
from maidr.util.dependencies import (  # noqa: E402
    OFFLINE_FALLBACK_REPORT as _OFFLINE_FALLBACK_REPORT,
)


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


class TestThePlotlyRenderReportsToo:
    """The same failure reaches Plotly charts, on both of its loader paths.

    Plotly has the two branches matplotlib has -- the notebook one reading
    the parent-window stash, and the one falling back to a relative path --
    and neither reported. A Plotly chart with no network became an image
    with no runtime and no explanation, which is the matplotlib case on a
    path the fix for it did not reach.
    """

    @staticmethod
    def _rendered(monkeypatch, *, notebook: bool) -> str:
        """Render a Plotly chart as the given environment would."""
        import html as html_module
        import re

        px = pytest.importorskip("plotly.express")
        monkeypatch.setattr(
            "maidr.util.environment.Environment.is_notebook", lambda: notebook
        )
        monkeypatch.setattr(
            "maidr.util.environment.Environment.is_shiny", lambda: not notebook
        )
        monkeypatch.setattr(
            "maidr.util.environment.Environment.is_flask", lambda: False
        )

        tag = maidr.render(px.bar(x=["a", "b"], y=[1, 2]), use_cdn="auto")
        html = str(tag.get_html_string())
        match = re.search(r'srcdoc="(.*?)"\s+width', html, re.S)
        return html_module.unescape(match.group(1)) if match else html

    @pytest.mark.parametrize("notebook", [True, False])
    def test_every_plotly_auto_path_defines_the_reporter(
        self, monkeypatch, notebook
    ) -> None:
        """Parametrized because only one of the two paths was covered.

        Forcing ``is_shiny`` alone leaves ``is_notebook`` false, so a test
        that mocks only that exercises the relative-path branch twice and
        the notebook branch never.
        """
        document = self._rendered(monkeypatch, notebook=notebook)
        assert "function reportNoRuntime" in document

    @pytest.mark.parametrize("notebook", [True, False])
    def test_every_plotly_auto_path_reports(self, monkeypatch, notebook) -> None:
        document = self._rendered(monkeypatch, notebook=notebook)
        called = document.replace("function reportNoRuntime(", "")
        assert "reportNoRuntime(" in called

    def test_the_iframe_path_reports_a_dead_relative_fallback(
        self, monkeypatch
    ) -> None:
        """The branch that had no ``onerror`` at all."""
        document = self._rendered(monkeypatch, notebook=False)
        assert "fb.onerror" in document

    def test_use_cdn_false_still_advises_init_notebook(self, monkeypatch) -> None:
        """The two modes fail for different reasons and need different advice.

        A caller who already passed ``use_cdn=False`` is not helped by being
        told to pass ``use_cdn=False``; what they need is
        ``init_notebook()``. Sharing one message would have cost them that.
        """
        px = pytest.importorskip("plotly.express")
        monkeypatch.setattr(
            "maidr.util.environment.Environment.is_notebook", lambda: True
        )
        monkeypatch.setattr(
            "maidr.util.environment.Environment.is_shiny", lambda: False
        )
        document = str(
            maidr.render(px.bar(x=["a"], y=[1]), use_cdn=False).get_html_string()
        )
        assert "init_notebook()" in document

    def test_both_renderers_say_the_same_thing(self, monkeypatch) -> None:
        """One failure, one wording -- the point of sharing the constant.

        Two diagnostics for one failure is the drift this consolidation
        exists to prevent, and it would be invisible from either file alone.
        """
        marker = "The chart loaded but its runtime did not"
        assert marker in _OFFLINE_FALLBACK_REPORT
        assert marker in self._rendered(monkeypatch, notebook=False)
        assert marker in _rendered(monkeypatch, notebook=False)
