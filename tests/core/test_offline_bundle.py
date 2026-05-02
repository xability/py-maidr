"""Tests for the bundled ``maidr.js`` integration and ``use_cdn`` plumbing."""

from __future__ import annotations

import re
from pathlib import Path

import matplotlib.pyplot as plt
import pytest

import maidr
from maidr import api as maidr_api
from maidr.util import dependencies


# ---------------------------------------------------------------------------
# Bundled assets
# ---------------------------------------------------------------------------


def test_bundled_maidr_js_exists():
    """The bundled ``maidr.js`` must ship with the installed package."""
    js_path = dependencies.bundled_js_path()
    assert js_path.is_file()
    assert js_path.stat().st_size > 1_000, "bundled maidr.js looks empty"


def test_bundled_maidr_css_exists():
    """The bundled stylesheet must ship alongside ``maidr.js``."""
    css_path = dependencies.bundled_css_path()
    assert css_path.is_file()
    assert css_path.stat().st_size > 0, "bundled maidr.css looks empty"


def test_bundled_version_file_is_semver_like():
    """VERSION file exists and contains a sensible version string."""
    version = dependencies.maidr_js_version()
    # Anything that looks like ``X.Y.Z`` (optionally with a prerelease tag)
    # passes; ``0.0.0`` is acceptable as a fallback but must not be empty.
    assert re.match(r"^\d+\.\d+\.\d+", version), f"odd version string: {version!r}"


def test_maidr_html_dependency_points_to_package():
    """The ``HTMLDependency`` must reference the installed package."""
    dep = dependencies.maidr_html_dependency()
    assert dep.name == "maidr"
    # htmltools wraps the version string in a ``packaging.version.Version``
    # object, so compare by string form.
    assert str(dep.version) == dependencies.maidr_js_version()
    # htmltools stores the source mapping in ``source``; we only care
    # that the dependency can be materialised to a concrete directory.
    assert any(
        "maidr.js" == Path(s["src"]).name for s in dep.script
    ), "maidr.js is not listed as a dependency script"
    assert any(
        "maidr.css" == Path(s["href"]).name for s in dep.stylesheet
    ), "maidr.css is not listed as a dependency stylesheet"


def test_maidr_bundled_files_dependency_has_no_script_tags():
    """The no-tag dependency must still copy files but emit no tags."""
    dep = dependencies.maidr_bundled_files_dependency()
    assert dep.script == []
    assert dep.stylesheet == []
    assert dep.all_files is True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def bar_plot():
    fig, ax = plt.subplots()
    ax.bar(["A", "B", "C"], [1, 2, 3])
    yield fig
    plt.close(fig)


@pytest.fixture(autouse=True)
def reset_use_cdn_default():
    """Reset the module-level default between tests to keep them isolated."""
    original = maidr_api._use_cdn_default
    yield
    maidr_api._use_cdn_default = original


# ---------------------------------------------------------------------------
# save_html: CDN vs bundled vs auto
# ---------------------------------------------------------------------------


def test_save_html_default_references_cdn(bar_plot, tmp_path):
    """Default behaviour is unchanged: references jsDelivr CDN."""
    out = tmp_path / "plot.html"
    maidr.save_html(bar_plot, file=str(out))

    contents = out.read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net/npm/maidr" in contents, (
        "CDN URL should still appear in the default output"
    )


def test_save_html_use_cdn_false_creates_lib_dir_with_js(bar_plot, tmp_path):
    """use_cdn=False copies the bundled JS/CSS into ``lib_dir``."""
    out = tmp_path / "plot.html"
    maidr.save_html(bar_plot, file=str(out), use_cdn=False)

    lib_dir = tmp_path / "lib"
    assert lib_dir.exists(), "lib directory was not created"

    subdirs = [p for p in lib_dir.iterdir() if p.is_dir() and p.name.startswith("maidr")]
    assert subdirs, f"no maidr-* subdirectory under {lib_dir}"
    js_files = list(subdirs[0].glob("maidr.js"))
    css_files = list(subdirs[0].glob("maidr.css"))
    assert js_files and js_files[0].stat().st_size > 1_000
    assert css_files and css_files[0].stat().st_size > 0


def test_save_html_use_cdn_false_html_references_relative_path(bar_plot, tmp_path):
    """Saved HTML must load the bundled JS via a relative path, not CDN."""
    out = tmp_path / "plot.html"
    maidr.save_html(bar_plot, file=str(out), use_cdn=False)

    contents = out.read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net/npm/maidr" not in contents, (
        "use_cdn=False output must not reference the CDN"
    )
    assert re.search(r'src="[^"]*maidr\.js"', contents), (
        "use_cdn=False output does not include a <script src='.../maidr.js'> tag"
    )
    assert re.search(r'href="[^"]*maidr\.css"', contents), (
        "use_cdn=False output does not include a <link href='.../maidr.css'> tag"
    )


def test_save_html_use_cdn_false_output_is_portable(bar_plot, tmp_path):
    """Moving the HTML + ``lib`` directory should preserve references."""
    src = tmp_path / "src"
    src.mkdir()

    out = src / "plot.html"
    maidr.save_html(bar_plot, file=str(out), use_cdn=False)

    contents = out.read_text(encoding="utf-8")
    script_src_match = re.search(r'src="([^"]*maidr\.js)"', contents)
    assert script_src_match is not None
    rel_js = script_src_match.group(1)
    resolved = (out.parent / rel_js).resolve()
    assert resolved.exists(), f"{rel_js} does not resolve from {out.parent}"


def test_save_html_auto_emits_cdn_and_fallback(bar_plot, tmp_path):
    """use_cdn="auto" ships the bundle AND references the CDN with onerror."""
    out = tmp_path / "plot.html"
    maidr.save_html(bar_plot, file=str(out), use_cdn="auto")

    contents = out.read_text(encoding="utf-8")

    # CDN must still be referenced so online viewers get the latest version.
    assert "cdn.jsdelivr.net/npm/maidr" in contents, (
        "auto output must reference the CDN"
    )
    # An onerror fallback must be present for offline viewers.
    assert "onerror" in contents, (
        "auto output must include a client-side onerror fallback handler"
    )
    # The bundled path must be mentioned in the fallback (as a string).
    assert f"lib/maidr-{dependencies.maidr_js_version()}/maidr.js" in contents, (
        "auto output does not reference the bundled fallback path"
    )

    # The bundle files must also be materialised under lib/.
    lib_dir = tmp_path / "lib"
    subdirs = [p for p in lib_dir.iterdir() if p.is_dir() and p.name.startswith("maidr")]
    assert subdirs, "auto mode did not copy bundle into lib/"
    assert (subdirs[0] / "maidr.js").stat().st_size > 1_000


# ---------------------------------------------------------------------------
# render()
# ---------------------------------------------------------------------------


def test_render_default_tag_contains_cdn(bar_plot):
    tag = maidr.render(bar_plot)
    rendered = tag.render()["html"]
    assert "cdn.jsdelivr.net" in rendered


def test_render_use_cdn_false_tag_contains_no_cdn(bar_plot):
    tag = maidr.render(bar_plot, use_cdn=False)
    rendered = tag.render()["html"]
    assert "cdn.jsdelivr.net" not in rendered, (
        "use_cdn=False render still references the jsDelivr CDN"
    )


def test_render_auto_tag_contains_cdn_and_fallback(bar_plot):
    tag = maidr.render(bar_plot, use_cdn="auto")
    rendered = tag.render()["html"]
    assert "cdn.jsdelivr.net" in rendered
    assert "onerror" in rendered


# ---------------------------------------------------------------------------
# Module-level default: ``set_use_cdn`` and ``MAIDR_USE_CDN``
# ---------------------------------------------------------------------------


def test_get_use_cdn_defaults_to_auto(monkeypatch):
    """The built-in default is ``"auto"`` — CDN with client-side fallback.

    No Python-side network probing is performed; the browser's
    ``script.onerror`` handler is the authoritative signal for CDN
    reachability.
    """
    monkeypatch.delenv("MAIDR_USE_CDN", raising=False)
    maidr_api._use_cdn_default = None
    assert maidr.get_use_cdn() == "auto"


def test_set_use_cdn_changes_default():
    maidr.set_use_cdn(False)
    assert maidr.get_use_cdn() is False

    maidr.set_use_cdn("auto")
    assert maidr.get_use_cdn() == "auto"

    maidr.set_use_cdn(True)
    assert maidr.get_use_cdn() is True


@pytest.mark.parametrize(
    "env_value,expected",
    [
        ("1", True),
        ("true", True),
        ("TRUE", True),
        ("auto", "auto"),
        ("AUTO", "auto"),
        ("0", False),
        ("false", False),
        ("", "auto"),  # empty string falls back to the "auto" default
        ("garbage", "auto"),  # unknown tokens also fall back to "auto"
    ],
)
def test_maidr_use_cdn_env_var(monkeypatch, env_value, expected):
    monkeypatch.setenv("MAIDR_USE_CDN", env_value)
    maidr_api._use_cdn_default = None  # force re-read
    assert maidr.get_use_cdn() == expected


def test_set_use_cdn_changes_save_html_default(bar_plot, tmp_path):
    """Calling ``set_use_cdn(False)`` makes ``save_html()`` bundle by default."""
    maidr.set_use_cdn(False)
    out = tmp_path / "plot.html"
    maidr.save_html(bar_plot, file=str(out))

    contents = out.read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net/npm/maidr" not in contents


# ---------------------------------------------------------------------------
# plt.show(use_cdn=...) integration
# ---------------------------------------------------------------------------


def test_plt_show_forwards_use_cdn_kwarg(bar_plot, mocker):
    """``plt.show(use_cdn=False)`` must reach ``Maidr.show``."""
    from maidr.core.figure_manager import FigureManager as MaidrFigureManager

    # Register the plot with maidr (the bar_plot fixture is matplotlib-only).
    # Importing a patch module is enough via ``import maidr`` in top-of-file,
    # and ``ax.bar(...)`` in the fixture triggers registration.
    maidr_obj = MaidrFigureManager.get_maidr(bar_plot)
    spy = mocker.patch.object(maidr_obj, "show", return_value=None)

    from maidr import backend as maidr_backend

    maidr_backend.show(use_cdn=False)

    spy.assert_called_once()
    _, kwargs = spy.call_args
    assert kwargs.get("use_cdn") is False
    assert kwargs.get("clear_fig") is False


def test_plt_show_uses_module_default_when_no_kwarg(bar_plot, mocker):
    """Without an explicit kwarg, ``plt.show`` falls back to ``get_use_cdn``."""
    from maidr.core.figure_manager import FigureManager as MaidrFigureManager

    maidr.set_use_cdn("auto")
    maidr_obj = MaidrFigureManager.get_maidr(bar_plot)
    spy = mocker.patch.object(maidr_obj, "show", return_value=None)

    from maidr import backend as maidr_backend

    maidr_backend.show()

    spy.assert_called_once()
    _, kwargs = spy.call_args
    assert kwargs.get("use_cdn") == "auto"


# ---------------------------------------------------------------------------
# init_notebook() — load-once pattern (Plotly/Bokeh style)
# ---------------------------------------------------------------------------


@pytest.fixture
def reset_notebook_loaded():
    """Restore the ``_NOTEBOOK_LOADED`` flag around a test."""
    original = maidr_api._NOTEBOOK_LOADED
    yield
    maidr_api._NOTEBOOK_LOADED = original


def test_init_notebook_noop_outside_notebook(mocker, reset_notebook_loaded):
    """Outside notebooks ``init_notebook()`` must not call IPython.display."""
    mocker.patch(
        "maidr.util.environment.Environment.is_notebook", return_value=False
    )
    maidr_api._NOTEBOOK_LOADED = False

    # If IPython were consulted in a non-notebook context this patch would
    # record a call.  Using ``sys.modules`` ensures we would intercept any
    # attempt to import from IPython.display during the call.
    from unittest.mock import MagicMock

    fake_display = MagicMock()
    mocker.patch.dict(
        "sys.modules",
        {"IPython": MagicMock(), "IPython.display": fake_display},
    )

    maidr.init_notebook(use_cdn=False)

    fake_display.display.assert_not_called()
    assert maidr_api._NOTEBOOK_LOADED is False


def test_init_notebook_false_injects_bundled_source(
    mocker, reset_notebook_loaded
):
    """``init_notebook(use_cdn=False)`` stashes JS/CSS on ``window``."""
    from unittest.mock import MagicMock

    mocker.patch(
        "maidr.util.environment.Environment.is_notebook", return_value=True
    )
    maidr_api._NOTEBOOK_LOADED = False

    fake_html_cls = MagicMock()
    fake_display_fn = MagicMock()
    fake_display_mod = MagicMock(HTML=fake_html_cls, display=fake_display_fn)
    mocker.patch.dict(
        "sys.modules",
        {"IPython": MagicMock(), "IPython.display": fake_display_mod},
    )

    maidr.init_notebook(use_cdn=False)

    fake_html_cls.assert_called_once()
    html_arg = fake_html_cls.call_args[0][0]
    assert "window.__maidrJsSource" in html_arg
    assert "window.__maidrCssSource" in html_arg
    # No CDN reference when explicitly offline.
    assert "cdn.jsdelivr.net" not in html_arg
    # Closing </script> must be escaped so an embedded </script> in the
    # bundled source cannot prematurely close the outer <script> tag.
    assert "</script>" in html_arg  # one outer, intentional
    assert "<\\/" in html_arg or "</script>" in html_arg
    assert maidr_api._NOTEBOOK_LOADED is True


def test_init_notebook_true_injects_cdn_only(mocker, reset_notebook_loaded):
    """``init_notebook(use_cdn=True)`` emits CDN tags and no bundle."""
    from unittest.mock import MagicMock

    mocker.patch(
        "maidr.util.environment.Environment.is_notebook", return_value=True
    )
    maidr_api._NOTEBOOK_LOADED = False

    fake_html_cls = MagicMock()
    fake_display_fn = MagicMock()
    fake_display_mod = MagicMock(HTML=fake_html_cls, display=fake_display_fn)
    mocker.patch.dict(
        "sys.modules",
        {"IPython": MagicMock(), "IPython.display": fake_display_mod},
    )

    maidr.init_notebook(use_cdn=True)

    html_arg = fake_html_cls.call_args[0][0]
    assert "cdn.jsdelivr.net/npm/maidr" in html_arg
    assert "window.__maidrJsSource" not in html_arg


def test_init_notebook_auto_emits_both(mocker, reset_notebook_loaded):
    """``init_notebook(use_cdn='auto')`` ships both the bundle and the CDN."""
    from unittest.mock import MagicMock

    mocker.patch(
        "maidr.util.environment.Environment.is_notebook", return_value=True
    )
    maidr_api._NOTEBOOK_LOADED = False

    fake_html_cls = MagicMock()
    fake_display_fn = MagicMock()
    fake_display_mod = MagicMock(HTML=fake_html_cls, display=fake_display_fn)
    mocker.patch.dict(
        "sys.modules",
        {"IPython": MagicMock(), "IPython.display": fake_display_mod},
    )

    maidr.init_notebook(use_cdn="auto")

    html_arg = fake_html_cls.call_args[0][0]
    assert "window.__maidrJsSource" in html_arg
    assert "cdn.jsdelivr.net/npm/maidr" in html_arg


def test_init_notebook_is_idempotent(mocker, reset_notebook_loaded):
    """Second call is a no-op unless ``force=True``."""
    from unittest.mock import MagicMock

    mocker.patch(
        "maidr.util.environment.Environment.is_notebook", return_value=True
    )
    maidr_api._NOTEBOOK_LOADED = False

    fake_html_cls = MagicMock()
    fake_display_fn = MagicMock()
    fake_display_mod = MagicMock(HTML=fake_html_cls, display=fake_display_fn)
    mocker.patch.dict(
        "sys.modules",
        {"IPython": MagicMock(), "IPython.display": fake_display_mod},
    )

    maidr.init_notebook(use_cdn=False)
    assert fake_html_cls.call_count == 1

    # Second call is a no-op while the flag is set.
    maidr.init_notebook(use_cdn=False)
    assert fake_html_cls.call_count == 1

    # ``force=True`` re-injects even when the flag is already set.
    maidr.init_notebook(use_cdn=False, force=True)
    assert fake_html_cls.call_count == 2


# ---------------------------------------------------------------------------
# Iframe-in-notebook fast path for use_cdn=False
# ---------------------------------------------------------------------------


def test_render_in_notebook_uses_parent_source_bootstrap(
    bar_plot, mocker, reset_notebook_loaded
):
    """When rendered inside a notebook, ``use_cdn=False`` must reference
    ``window.parent.__maidrJsSource`` rather than emitting an HTMLDependency
    (which would be lost by the iframe wrapper's ``get_html_string``).
    """
    mocker.patch(
        "maidr.util.environment.Environment.is_notebook", return_value=True
    )
    tag = maidr.render(bar_plot, use_cdn=False)
    rendered = tag.render()["html"]

    assert "window.parent" in rendered
    assert "__maidrJsSource" in rendered
    # The 1.7 MB bundle must NOT be inlined in the srcdoc — that's the
    # whole point of the load-once pattern.
    assert "cdn.jsdelivr.net" not in rendered


def test_render_in_notebook_auto_uses_parent_source_fallback(
    bar_plot, mocker, reset_notebook_loaded
):
    """``use_cdn='auto'`` in a notebook must fall back to the parent-source
    bootstrap (not to a relative ``lib/maidr.../maidr.js`` path which
    cannot resolve inside an iframe srcdoc)."""
    mocker.patch(
        "maidr.util.environment.Environment.is_notebook", return_value=True
    )
    tag = maidr.render(bar_plot, use_cdn="auto")
    rendered = tag.render()["html"]

    assert "cdn.jsdelivr.net" in rendered
    assert "__maidrJsSource" in rendered


# ---------------------------------------------------------------------------
# Top-level re-exports of bundled-asset helpers
# ---------------------------------------------------------------------------


def test_bundled_js_path_is_top_level_export():
    """Users should be able to read the bundled assets without drilling
    into ``maidr.util.dependencies``."""
    assert callable(maidr.bundled_js_path)
    assert callable(maidr.bundled_css_path)
    assert callable(maidr.read_bundled_js)
    assert callable(maidr.maidr_js_version)

    js_path = maidr.bundled_js_path()
    assert js_path.is_file()
    assert js_path.stat().st_size > 1_000

    css_path = maidr.bundled_css_path()
    assert css_path.is_file()

    version = maidr.maidr_js_version()
    assert re.match(r"^\d+\.\d+\.\d+", version)

    js_source = maidr.read_bundled_js()
    assert len(js_source) > 1_000


# ---------------------------------------------------------------------------
# Default ``"auto"`` mode: browser-side ``onerror`` fallback
# ---------------------------------------------------------------------------


def test_default_save_html_uses_auto_mode(bar_plot, tmp_path, monkeypatch):
    """With no explicit ``use_cdn``, saved HTML must be ``"auto"`` mode.

    That means the HTML references the CDN **and** includes a
    client-side ``onerror`` fallback pointing at the bundled copy.
    Offline browsers transparently swap in the bundle; online browsers
    pay for the CDN request as before.
    """
    monkeypatch.delenv("MAIDR_USE_CDN", raising=False)
    maidr_api._use_cdn_default = None

    out = tmp_path / "plot.html"
    maidr.save_html(bar_plot, file=str(out))

    contents = out.read_text(encoding="utf-8")
    assert "cdn.jsdelivr.net/npm/maidr" in contents, (
        "default (``auto``) mode must still reference the CDN"
    )
    assert "onerror" in contents, (
        "default (``auto``) mode must include a client-side onerror fallback"
    )
    # The bundle must be materialised into ``lib/`` so the fallback can
    # actually load something when the CDN is unreachable.
    lib_dir = tmp_path / "lib"
    subdirs = [
        p for p in lib_dir.iterdir() if p.is_dir() and p.name.startswith("maidr")
    ]
    assert subdirs, "default mode did not copy bundle into lib/"
    assert (subdirs[0] / "maidr.js").stat().st_size > 1_000


def test_default_render_uses_auto_mode(bar_plot, monkeypatch):
    """``maidr.render()`` without an explicit ``use_cdn`` must be ``"auto"``.

    For notebook iframe renders the ``"auto"`` path falls back to the
    parent-document ``window.__maidrJsSource`` string because relative
    lib/ paths don't resolve inside an iframe srcdoc.  Outside notebooks
    the fallback goes to the bundled file.
    """
    monkeypatch.delenv("MAIDR_USE_CDN", raising=False)
    maidr_api._use_cdn_default = None

    tag = maidr.render(bar_plot)
    rendered = tag.render()["html"]

    assert "cdn.jsdelivr.net" in rendered
    assert "onerror" in rendered


def test_no_connectivity_probe_remains():
    """The Python-side TCP probe and its cache must not exist any more.

    This guards against reintroducing the stale-cache bug where an
    import-time probe would cache a stale ``True`` for 5 minutes after
    the user disabled WiFi.
    """
    assert not hasattr(maidr_api, "_check_cdn_connectivity")
    assert not hasattr(maidr_api, "_reset_connectivity_cache")
    assert not hasattr(maidr_api, "_connectivity_cache")
    assert not hasattr(maidr_api, "_connectivity_cache_time")
