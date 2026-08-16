"""An unsupported chart crashed the API and fell back through the backend (#443).

The same figure behaved two completely different ways depending on which door
the user went through:

    plt.show()            ok, warned, drew a static image
    maidr.render()        KeyError: 'No MAIDR found for figure: Figure(...).'
    maidr.show()          KeyError
    maidr.save_html(...)  KeyError

The graceful path existed and worked. It was wired into the matplotlib backend
and nothing else, so the three functions a user is actually told to call were
the ones that crashed.

`KeyError` was also the wrong *shape*. It is what Python raises when you index
a dict wrong, and surfacing it from a documented entry point told a user their
own call did something illegal with a mapping -- when what happened is that
their chart type is not supported yet. "No MAIDR found for figure" describes
maidr's own bookkeeping: no chart type, no supported list, no next step, even
though the backend already computed exactly that sentence a few modules away.

For an accessibility library the asymmetry ran the wrong way: the user who
explicitly asked for accessible output was the one who got nothing. So all
four paths now fall back, which is also what `r-maidr` does through every one
of its entry points.

Two things are asserted beyond "does not raise", because "does not raise" is
satisfiable by returning nothing at all:

* the fallback carries the *image*, so the user still sees their plot;
* it carries the *reason*, in the page and not only in a console warning --
  the warning is seen by whoever ran the code, and the HTML is what reaches
  everyone afterwards.
"""

from __future__ import annotations

import warnings

import numpy as np
import pytest

sns = pytest.importorskip("seaborn")

import matplotlib  # noqa: E402

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

import maidr  # noqa: E402
from maidr.core.figure_manager import FigureManager  # noqa: E402
from maidr.exception.unsupported_plot_error import (  # noqa: E402
    UnsupportedPlotError,
    supported_plot_types,
)


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def data() -> np.ndarray:
    return np.random.default_rng(0).normal(size=20)


def rugplot():
    """A chart maidr does not patch. `sns.rugplot` draws a LineCollection."""
    _, ax = plt.subplots()
    sns.rugplot(x=data(), ax=ax, height=0.1)
    return ax


def quiver():
    """A second unsupported chart, so nothing keys off rugplot specifically."""
    _, ax = plt.subplots()
    ax.quiver([0, 1], [0, 1], [1, 1], [1, 1])
    return ax


def caught(call) -> tuple[object, list[str]]:
    """Run ``call`` and hand back its result with every warning it emitted."""
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        result = call()
    return result, [str(record.message) for record in records]


class TestTheApiNoLongerCrashes:
    """The three functions a user is told to call."""

    @pytest.mark.parametrize("chart", [rugplot, quiver])
    def test_render_returns_something(self, chart):
        chart()
        result, _ = caught(maidr.render)

        assert result is not None

    @pytest.mark.parametrize("chart", [rugplot, quiver])
    def test_render_returns_the_picture(self, chart):
        # The point of falling back rather than raising: the user still sees
        # their plot. A fallback that returned an empty div would pass a
        # "does not raise" test and help nobody.
        chart()
        result, _ = caught(maidr.render)

        assert "data:image/png;base64," in str(result)

    @pytest.mark.parametrize("chart", [rugplot, quiver])
    def test_render_says_why_in_the_page(self, chart):
        chart()
        result, _ = caught(maidr.render)

        assert "not yet supported" in str(result)

    @pytest.mark.parametrize("chart", [rugplot, quiver])
    def test_save_html_writes_a_file(self, chart, tmp_path):
        # Raising here would leave a build step that expected an artefact with
        # nothing on disk and a traceback.
        chart()
        target = tmp_path / "out.html"
        caught(lambda: maidr.save_html(file=str(target)))

        assert target.exists()
        assert "data:image/png;base64," in target.read_text()

    def test_show_does_not_raise(self, monkeypatch):
        # `Tag.show()` would open a browser; the return value is what matters.
        monkeypatch.setattr(
            "htmltools._core.Tag.show", lambda self, *a, **k: "shown"
        )
        rugplot()

        assert caught(maidr.show)[0] == "shown"


class TestTheWarningSaysSomethingUseful:
    def test_every_path_warns(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "htmltools._core.Tag.show", lambda self, *a, **k: None
        )
        # The backend path is exercised through `_show_fallback` rather than
        # through `plt.show()`, because this module selects Agg and other test
        # modules switch the global backend around; going through `plt.show()`
        # would be asserting on whichever backend happened to be installed by
        # then rather than on maidr's own fallback.
        monkeypatch.setattr("webbrowser.open", lambda *a, **k: None)
        from maidr.backend import _show_fallback

        calls = {
            "render": maidr.render,
            "save_html": lambda: maidr.save_html(file=str(tmp_path / "o.html")),
            "show": maidr.show,
            "backend": lambda: _show_fallback(plt.gcf()),
        }
        for name, call in calls.items():
            plt.close("all")
            rugplot()
            _, messages = caught(call)

            assert any("not yet supported" in message for message in messages), name

    def test_it_names_the_supported_types(self):
        rugplot()
        _, messages = caught(maidr.render)
        message = next(m for m in messages if "not yet supported" in m)

        # Derived rather than hand-listed, because a hand-listed one drifted
        # before -- it named "kde" and "violin", neither a PlotType, while
        # omitting smooth and the violin variants.
        assert supported_plot_types() in message

    def test_the_supported_list_uses_names_a_user_would_recognise(self):
        # `PlotType.SCATTER.value` is "point"; someone who called ax.scatter
        # should be told about "scatter".
        listed = supported_plot_types()

        assert "scatter" in listed
        assert "heatmap" in listed


class TestAnEmptyFigureIsADifferentProblem:
    """"Your chart type is unsupported" is misleading for someone too early."""

    def test_an_empty_axes_says_so(self):
        plt.subplots()
        _, messages = caught(maidr.render)

        assert any("no plots on it yet" in message for message in messages)

    def test_it_does_not_claim_the_type_is_unsupported(self):
        plt.subplots()
        _, messages = caught(maidr.render)

        assert not any("not yet supported" in message for message in messages)

    def test_a_title_and_labels_do_not_make_it_non_empty(self):
        # They describe a chart that was never drawn.
        _, ax = plt.subplots()
        ax.set_title("Quarterly revenue")
        ax.set_xlabel("quarter")
        _, messages = caught(maidr.render)

        assert any("no plots on it yet" in message for message in messages)

    def test_a_drawn_chart_is_not_empty(self):
        # The guard: the empty test must not swallow the unsupported case.
        rugplot()
        _, messages = caught(maidr.render)

        assert not any("no plots on it yet" in message for message in messages)


class TestTheExceptionItself:
    def test_it_is_still_a_key_error(self):
        # The backend catches KeyError around `get_maidr` to decide whether to
        # fall back, and so may anyone else's code. Narrowing the type without
        # keeping the base would break the working half while fixing the
        # broken half.
        assert issubclass(UnsupportedPlotError, KeyError)

    def test_get_maidr_raises_it(self):
        _, ax = plt.subplots()

        with pytest.raises(UnsupportedPlotError):
            FigureManager.get_maidr(ax.get_figure())

    def test_the_message_is_not_about_maidrs_bookkeeping(self):
        _, ax = plt.subplots()
        sns.rugplot(x=data(), ax=ax, height=0.1)

        with pytest.raises(UnsupportedPlotError) as raised:
            FigureManager.get_maidr(ax.get_figure())

        assert "No MAIDR found for figure" not in raised.value.message
        assert "not yet supported" in raised.value.message


class TestWhatMustNotChange:
    def test_a_supported_chart_still_renders_accessibly(self):
        _, ax = plt.subplots()
        ax.bar(["a", "b"], [1, 2])
        result, messages = caught(maidr.render)

        assert "data:image/png;base64," not in str(result)
        assert not messages

    def test_a_supported_chart_still_saves_a_real_html_file(self, tmp_path):
        _, ax = plt.subplots()
        ax.bar(["a", "b"], [1, 2])
        target = tmp_path / "out.html"
        caught(lambda: maidr.save_html(file=str(target)))
        written = target.read_text()

        assert "maidr" in written
        assert "data:image/png;base64," not in written
