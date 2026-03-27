from __future__ import annotations

import warnings

import pytest

import matplotlib
import matplotlib.pyplot as plt
from matplotlib._pylab_helpers import Gcf

from maidr.core.figure_manager import FigureManager


class TestBackendRegistration:
    """Tests that the maidr backend is properly registered."""

    @pytest.fixture(autouse=True)
    def _restore_backend(self):
        """Restore the maidr backend after tests that switch away from it."""
        yield
        plt.switch_backend("module://maidr.backend")

    def test_backend_is_set_when_mplbackend_not_set(self, monkeypatch):
        """Backend activates when MPLBACKEND env var is absent."""
        # Switch away so we can verify _activate_backend actually changes it.
        plt.switch_backend("agg")
        monkeypatch.delenv("MPLBACKEND", raising=False)
        from maidr import _activate_backend

        _activate_backend()
        assert matplotlib.get_backend() == "module://maidr.backend"

    def test_backend_overrides_matplotlib_inline(self, monkeypatch):
        """Backend activates when MPLBACKEND is ipykernel's default inline."""
        monkeypatch.setenv(
            "MPLBACKEND", "module://matplotlib_inline.backend_inline"
        )
        from maidr import _activate_backend

        _activate_backend()
        assert matplotlib.get_backend() == "module://maidr.backend"

    def test_backend_overrides_legacy_inline(self, monkeypatch):
        """Backend activates when MPLBACKEND is ipykernel's legacy inline."""
        monkeypatch.setenv(
            "MPLBACKEND", "module://ipykernel.pylab.backend_inline"
        )
        from maidr import _activate_backend

        _activate_backend()
        assert matplotlib.get_backend() == "module://maidr.backend"

    def test_backend_skips_when_mplbackend_is_non_inline(self, monkeypatch, mocker):
        """_activate_backend() is a no-op when MPLBACKEND is a non-inline value.

        This verifies that user-chosen backends (e.g. TkAgg, Qt5Agg) are
        respected.  We set the active backend to Agg first so we can assert
        that _activate_backend() did not change it.  TkAgg itself is not
        activated (it would fail without a display server).
        """
        plt.switch_backend("agg")
        monkeypatch.setenv("MPLBACKEND", "TkAgg")
        mock_use = mocker.patch("matplotlib.use")
        mock_switch = mocker.patch("matplotlib.pyplot.switch_backend")
        from maidr import _activate_backend

        _activate_backend()
        # Should still be Agg — _activate_backend() should have bailed out.
        assert matplotlib.get_backend() == "agg"
        mock_use.assert_not_called()
        mock_switch.assert_not_called()

    def test_backend_module_has_required_attributes(self):
        from maidr import backend

        assert hasattr(backend, "FigureCanvas")
        assert hasattr(backend, "FigureManager")
        assert hasattr(backend, "show")
        assert callable(backend.show)


class TestBackendShow:
    """Tests that plt.show() delegates to maidr's accessible renderer."""

    @pytest.fixture(autouse=True)
    def _cleanup(self):
        """Ensure each test starts and ends with a clean figure state."""
        plt.close("all")
        yield
        plt.close("all")

    def test_show_calls_maidr_show(self, mocker):
        """plt.show() should call Maidr.show() for tracked figures."""
        fig, ax = plt.subplots()
        ax.bar([1, 2, 3], [4, 5, 6])

        maidr_obj = FigureManager.get_maidr(fig)
        mock_show = mocker.patch.object(maidr_obj, "show")

        plt.show()

        mock_show.assert_called_once_with(clear_fig=False)

    def test_show_destroys_figures(self, mocker):
        """plt.show() should clean up figures after displaying."""
        fig, ax = plt.subplots()
        ax.bar([1, 2, 3], [4, 5, 6])

        maidr_obj = FigureManager.get_maidr(fig)
        mocker.patch.object(maidr_obj, "show")

        plt.show()

        assert len(Gcf.get_all_fig_managers()) == 0

    def test_show_with_no_figures(self):
        """plt.show() should not raise when there are no figures."""
        plt.close("all")
        plt.show()  # Should not raise

    def test_show_falls_back_for_untracked_figures(self, mocker):
        """plt.show() should warn and fall back to static image for untracked figures."""
        fig, ax = plt.subplots()
        # Don't add any maidr-tracked plot — just raw text
        ax.text(0.5, 0.5, "hello")

        # Mock the fallback so it doesn't open a browser
        mock_fallback = mocker.patch("maidr.backend._show_fallback")

        plt.show()

        mock_fallback.assert_called_once_with(fig)
        assert len(Gcf.get_all_fig_managers()) == 0

    def test_show_fallback_emits_warning(self, mocker):
        """_show_fallback() should emit a warning about unsupported plot types."""
        from maidr.backend import _show_fallback

        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "hello")

        # Mock webbrowser so it doesn't actually open
        mocker.patch("maidr.backend.webbrowser.open")
        mocker.patch.object(fig, "savefig")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _show_fallback(fig)

            assert len(w) == 1
            assert "not yet supported by maidr" in str(w[0].message)

    def test_show_fallback_notebook_path(self, mocker):
        """_show_fallback() should use IPython.display in notebook environments."""
        from unittest.mock import MagicMock

        from maidr.backend import _show_fallback

        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "hello")

        mocker.patch(
            "maidr.util.environment.Environment.is_notebook", return_value=True
        )
        mock_ipython_display = MagicMock()
        mocker.patch.dict(
            "sys.modules",
            {"IPython": MagicMock(), "IPython.display": mock_ipython_display},
        )
        mocker.patch.object(fig, "savefig")
        mock_browser = mocker.patch("maidr.backend.webbrowser.open")

        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            _show_fallback(fig)

        mock_ipython_display.display.assert_called_once()
        mock_browser.assert_not_called()

    def test_show_cleans_up_maidr_figure_manager(self, mocker):
        """plt.show() should remove figures from maidr's FigureManager.figs."""
        fig, ax = plt.subplots()
        ax.bar([1, 2, 3], [4, 5, 6])

        # Verify figure is tracked before show
        assert fig in FigureManager.figs

        mocker.patch("maidr.core.maidr.Maidr.show")

        plt.show()

        # After show, figure should be cleaned up from maidr's tracking
        assert fig not in FigureManager.figs

    def test_show_multiple_figures(self, mocker):
        """plt.show() should render and clean up all open figures."""
        fig1, ax1 = plt.subplots()
        ax1.bar([1, 2], [3, 4])

        fig2, ax2 = plt.subplots()
        ax2.bar([5, 6], [7, 8])

        maidr_obj1 = FigureManager.get_maidr(fig1)
        maidr_obj2 = FigureManager.get_maidr(fig2)
        mock_show1 = mocker.patch.object(maidr_obj1, "show")
        mock_show2 = mocker.patch.object(maidr_obj2, "show")

        plt.show()

        # Both figures should have been shown
        mock_show1.assert_called_once_with(clear_fig=False)
        mock_show2.assert_called_once_with(clear_fig=False)

        # Both should be cleaned up from matplotlib and maidr
        assert len(Gcf.get_all_fig_managers()) == 0
        assert fig1 not in FigureManager.figs
        assert fig2 not in FigureManager.figs


class TestEnableDisable:
    """Tests for maidr.enable() and maidr.disable()."""

    @pytest.fixture(autouse=True)
    def _restore_backend(self):
        """Restore the maidr backend after each test."""
        yield
        plt.switch_backend("module://maidr.backend")

    def test_disable_switches_away_from_maidr(self):
        """maidr.disable() should switch to the original backend."""
        import maidr

        assert matplotlib.get_backend() == "module://maidr.backend"
        maidr.disable()
        assert matplotlib.get_backend() != "module://maidr.backend"

    def test_enable_restores_maidr_backend(self):
        """maidr.enable() should switch back to the maidr backend."""
        import maidr

        maidr.disable()
        assert matplotlib.get_backend() != "module://maidr.backend"

        maidr.enable()
        assert matplotlib.get_backend() == "module://maidr.backend"

    def test_disable_enable_roundtrip(self):
        """disable() then enable() should return to maidr backend."""
        import maidr

        assert matplotlib.get_backend() == "module://maidr.backend"
        maidr.disable()
        maidr.enable()
        assert matplotlib.get_backend() == "module://maidr.backend"

    def test_original_backend_is_saved(self):
        """_original_backend should be set after import."""
        import maidr

        assert maidr._original_backend is not None

    def test_original_backend_is_not_maidr(self):
        """_original_backend should never be the maidr backend itself."""
        import maidr

        assert maidr._original_backend != "module://maidr.backend"

    def test_disable_twice_does_not_raise(self):
        """Calling disable() twice should not raise."""
        import maidr

        maidr.disable()
        maidr.disable()  # Should not raise

    def test_enable_without_prior_disable(self):
        """Calling enable() without disable() should be a no-op."""
        import maidr

        assert matplotlib.get_backend() == "module://maidr.backend"
        maidr.enable()  # Redundant but should not raise
        assert matplotlib.get_backend() == "module://maidr.backend"

    def test_disable_jupyter_path(self, mocker):
        """disable() should use %matplotlib inline magic in Jupyter."""
        from unittest.mock import MagicMock

        import maidr

        # Pretend the original backend was the inline backend.
        mocker.patch.object(
            maidr,
            "_original_backend",
            "module://matplotlib_inline.backend_inline",
        )
        mock_ip = MagicMock()
        mocker.patch("maidr.get_ipython", create=True, return_value=mock_ip)
        mocker.patch.dict(
            "sys.modules",
            {"IPython": MagicMock(get_ipython=MagicMock(return_value=mock_ip))},
        )

        maidr.disable()

        mock_ip.run_line_magic.assert_called_once_with("matplotlib", "inline")
