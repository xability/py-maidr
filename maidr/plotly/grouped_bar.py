from __future__ import annotations

from maidr.core.enum.maidr_key import MaidrKey
from maidr.core.enum.plot_type import PlotType
from maidr.plotly.barnorm import barnorm_scale, stack_shares
from maidr.plotly.plotly_plot import PlotlyPlot, paired_axes


class PlotlyGroupedBarPlot(PlotlyPlot):
    """Extract data from multiple Plotly bar traces (dodged, stacked or
    normalised).

    The class does not branch on *plot_type*: every combination hands the
    traces' own ``x``/``y``/``fill`` through unchanged, and the type decides
    only how the MAIDR core reads them. Which one applies is worked out from
    ``layout.barmode`` and ``layout.barnorm`` by
    :meth:`~maidr.plotly.plotly_maidr.PlotlyMaidr._extract_plots`.

    Parameters
    ----------
    traces : list[dict]
        All bar trace dicts belonging to the group.
    layout : dict
        The Plotly figure layout.
    plot_type : PlotType
        ``PlotType.DODGED``, ``PlotType.STACKED`` or
        ``PlotType.NORMALIZED``.
    """

    def __init__(
        self,
        traces: list[dict],
        layout: dict,
        plot_type: PlotType,
        **kwargs: str,
    ) -> None:
        # Use the first trace for base class init (title / axes)
        super().__init__(traces[0], layout, plot_type, **kwargs)
        self._traces = traces

    def _get_selector(self) -> str:
        return f"{self._subplot_css_prefix()}.trace.bars .point > path"

    def _horizontal(self, trace: dict) -> bool:
        """Whether this trace's value runs along ``x`` rather than ``y``."""
        return trace.get("orientation") == "h"

    def render(self) -> dict:
        """Add ``orientation`` to the base schema.

        `_extract_plot_data` already puts a horizontal group's measure in
        ``x``, which is the arrangement the core wants -- but only once it has
        been told the layer is horizontal. Without the key it defaults to
        vertical and reads ``point.y``, which on these layers is the category
        name: no magnitude to pitch, so every bar was silent, and the
        announcement gave the measure as the point's identity and the category
        as its value (#480).

        Taken from the first trace, as the axes and title above are. A group
        is one chart drawn one way round; plotly draws a group whose members
        disagree about ``orientation`` as overlapping bars rather than as a
        group, and that is not a shape this class is reached for.
        """
        schema = super().render()
        schema[MaidrKey.ORIENTATION] = (
            "horz" if self._horizontal(self._traces[0]) else "vert"
        )
        return schema

    def _extract_plot_data(self) -> list[list[dict]]:
        """Return grouped bar data as a list-of-lists.

        Each inner list represents one group (hue value).  Every item has
        ``x``, ``fill`` (group name), and ``y`` keys.

        A ``stacked_normalized_bar`` layer carries *shares* rather than the
        traces' own numbers, because that is what plotly draws and what the
        type claims. See :mod:`maidr.plotly.barnorm`.
        """
        # Resolved before the loop so the ordinary, un-normalised layer does
        # not build the `(position, value)` tuples only to discard them.
        scale = barnorm_scale(self._layout.get("barnorm"))
        normalising = scale is not None and self.type == PlotType.NORMALIZED

        data: list[list[dict]] = []
        pairs: list[list[tuple]] = []

        for trace in self._traces:
            x_vals, y_vals = paired_axes(trace)
            fill = trace.get("name", "")
            horizontal = self._horizontal(trace)

            group: list[dict] = []
            group_pairs: list[tuple] = []
            for xv, yv in zip(x_vals, y_vals):
                group.append(
                    {
                        MaidrKey.X.value: self._to_native(xv),
                        MaidrKey.Z.value: str(fill),
                        MaidrKey.Y.value: self._to_native(yv),
                    }
                )
                if normalising:
                    # Keyed by the *category* and valued by the magnitude,
                    # which swap with the orientation. Matched by category
                    # rather than by index so a series that skips one
                    # contributes nothing there instead of shifting every
                    # later position.
                    position, value = (yv, xv) if horizontal else (xv, yv)
                    group_pairs.append(
                        (self._to_native(position), self._to_native(value))
                    )

            data.append(group)
            pairs.append(group_pairs)

        if not normalising:
            return data

        shares = stack_shares(pairs, self._layout.get("barmode"), scale)
        for group, group_shares, trace in zip(data, shares, self._traces):
            key = MaidrKey.X.value if self._horizontal(trace) else MaidrKey.Y.value
            for point, share in zip(group, group_shares):
                point[key] = share

        return data
