from __future__ import annotations

import matplotlib
import matplotlib.pyplot as plt

from maidr.core.figure_manager import FigureManager


class TestBackendRegistration:
    """Tests that the maidr backend is properly registered."""

    def test_backend_is_set_on_import(self):
        import maidr  # noqa: F401

        assert matplotlib.get_backend() == "module://maidr.backend"

    def test_backend_module_has_required_attributes(self):
        from maidr import backend

        assert hasattr(backend, "FigureCanvas")
        assert hasattr(backend, "FigureManager")
        assert hasattr(backend, "show")
        assert callable(backend.show)


class TestBackendShow:
    """Tests that plt.show() delegates to maidr's accessible renderer."""

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

        from matplotlib._pylab_helpers import Gcf

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

        from matplotlib._pylab_helpers import Gcf

        assert len(Gcf.get_all_fig_managers()) == 0
