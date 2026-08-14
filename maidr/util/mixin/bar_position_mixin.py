from __future__ import annotations

from matplotlib.patches import Rectangle


class BarPositionMixin:
    """
    Announce where a bar was drawn when no tick label names it.

    Both ``BarPlot`` and ``GroupedBarPlot`` fall back to this when the
    category axis does not carry one label per bar -- which is every bar chart
    over a numeric x, since matplotlib's tick locator picks its own breaks
    there and has no reason to agree with the bars (#382, #384).

    Shared rather than spelled twice because the two copies would drift: the
    horizontal branch below is the kind of thing that gets corrected in one
    extractor and not the other, and a chart whose bars are announced at the
    wrong positions reads as a working chart.

    Expects the host to define ``_is_horizontal``.
    """

    _is_horizontal: bool

    def _bar_position(self, patch: Rectangle) -> str:
        """
        The centre a bar was drawn at, as the axis would print it.

        Read off the rectangle rather than the caller's argument, because the
        caller's is not available here and the drawn centre is what the value
        became. With matplotlib's default ``align="center"`` the two are the
        same number.

        Whole numbers lose their trailing ``.0``: a bar at x=0 is at ``"0"``,
        not ``"0.0"``, matching what a numeric axis shows. They are also the
        reason this is not simply ``f"{centre:g}"`` -- that is six significant
        figures and goes exponential past them, so a bar at x=1234567 would
        announce ``"1.23457e+06"``, which is both lossy and hard to listen to.
        A large x is overwhelmingly an integer one (an index, an id, a year),
        so integers are formatted exactly and only fractions fall back.

        That scopes the problem rather than solving it: a bar centred at
        1234567.5 still announces ``"1.23457e+06"``. Rounding fractions is not
        incidental, though -- the centre is computed from the rectangle's
        geometry, so ``0.1 + 0.2`` arrives as ``0.30000000000000004`` and
        printing it exactly would be worse than printing it short. Fixing the
        large-fraction case properly means telling float noise from a real
        fraction, which needs more than a format string.

        Parameters
        ----------
        patch : Rectangle
            One bar.

        Returns
        -------
        str
            The bar's position along its label axis.
        """
        if self._is_horizontal:
            centre = patch.get_y() + patch.get_height() / 2
        else:
            centre = patch.get_x() + patch.get_width() / 2
        if float(centre).is_integer():
            return str(int(centre))
        return f"{centre:g}"
