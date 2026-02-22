from __future__ import annotations

import numpy as np

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.plotly_plot import PlotlyPlot


class PlotlyHistogramPlot(PlotlyPlot):
    """Extract data from a Plotly histogram trace."""

    def __init__(self, trace: dict, layout: dict) -> None:
        super().__init__(trace, layout, PlotType.HIST)

    def _extract_plot_data(self) -> list[dict]:
        x = self._trace.get("x", None)
        if x is None:
            return []

        arr = np.array(x, dtype=float)
        nbins = self._get_nbins()

        counts, bin_edges = np.histogram(arr, bins=nbins)

        data = []
        for i, count in enumerate(counts):
            x_min = float(bin_edges[i])
            x_max = float(bin_edges[i + 1])
            data.append(
                {
                    MaidrKey.X.value: (x_min + x_max) / 2,
                    MaidrKey.Y.value: int(count),
                    MaidrKey.X_MIN.value: x_min,
                    MaidrKey.X_MAX.value: x_max,
                    MaidrKey.Y_MIN.value: 0,
                    MaidrKey.Y_MAX.value: int(count),
                }
            )
        return data

    def _get_nbins(self) -> int | str:
        """Determine the number of bins from the trace config."""
        nbinsx = self._trace.get("nbinsx", None)
        if nbinsx is not None:
            return int(nbinsx)

        xbins = self._trace.get("xbins", None)
        if xbins is not None and "size" in xbins:
            # Compute bin count from size
            x = np.array(self._trace.get("x", []), dtype=float)
            if len(x) > 0:
                size = float(xbins["size"])
                return max(1, int(np.ceil((x.max() - x.min()) / size)))

        # Default: let numpy decide
        return "auto"
