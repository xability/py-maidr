from __future__ import annotations

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

    def test_backend_skips_when_mplbackend_is_non_inline(self, monkeypatch):
        """_activate_backend() is a no-op when MPLBACKEND is a non-inline value.

        This verifies that user-chosen backends (e.g. TkAgg, Qt5Agg) are
        respected.  We set the active backend to Agg first so we can assert
        that _activate_backend() did not change it.  TkAgg itself is not
        activated (it would fail without a display server).
        """
        plt.switch_backend("agg")
        monkeypatch.setenv("MPLBACKEND", "TkAgg")
        from maidr import _activate_backend

        _activate_backend()
        # Should still be Agg — _activate_backend() should have bailed out.
        assert matplotlib.get_backend() == "agg"

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

    def test_show_skips_untracked_figures(self):
        """plt.show() should skip figures not tracked by maidr."""
        fig, ax = plt.subplots()
        # Don't add any maidr-tracked plot — just raw text
        ax.text(0.5, 0.5, "hello")

        # Should not raise
        plt.show()

        assert len(Gcf.get_all_fig_managers()) == 0

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
