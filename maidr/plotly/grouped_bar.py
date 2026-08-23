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

        # Where each drawn category sits in the traces' own arrays, when
        # ``categoryorder`` puts the two in different orders. Filled by
        # ``_extract_plot_data``, which ``render()`` runs before
        # ``_get_selector`` -- so the two cannot disagree about the order
        # (#495).
        self._drawn: list[int] | None = None

    def _get_selector(self) -> str | list[list[str]]:
        """Address the bars, per trace and per drawn category when sorted.

        One string is what an unsorted group has always had, and it stays
        that.

        A sorted one cannot use it, for the reason
        :meth:`~maidr.plotly.bar.PlotlyBarPlot._get_selector` gives: plotly
        writes each trace's bars in the trace's own order, so a single
        selector resolves in the order the points *used* to be emitted in.

        A grid rather than a flat list, because a segmented layer's cells are
        addressed by row and column -- ``selectors[group][category]``, the
        shape ``data`` already has. Measured in Chromium on two traces over
        three categories, in both ``barmode``\ s::

            grouped   traceGroups 2   perGroup [[767, 37, 402], [913, 183, 548]]
            stacked   traceGroups 2   perGroup [[767, 37, 402], [767, 37, 402]]

        Two sibling ``.trace.bars`` groups under ``g.barlayer.mlayer``, one
        per trace and in the traces' own order, each holding its categories in
        that trace's order. ``.trace.bars:nth-of-type(t) .point:nth-of-type(c)``
        matched exactly one element for all six pairs, and the coordinates
        confirm which: dodged puts the two traces side by side at one
        category, stacked puts them one above the other.

        A grid reaches a segmented layer's highlight as of
        xability/maidr#992. An older bundle answers ``[]`` rather than the
        wrong element, so the highlight is lost while the announced order
        stays corrected.
        """
        prefix = f"{self._subplot_css_prefix()}.trace.bars"
        if self._drawn is None:
            return f"{prefix} .point > path"
        return [
            [
                f"{prefix}:nth-of-type({group + 1}) "
                f".point:nth-of-type({index + 1}) > path"
                for index in self._drawn
            ]
            for group in range(len(self._traces))
        ]

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

        Each group is emitted in the order plotly *draws* the categories in,
        which ``categoryorder`` can make different from the order the traces
        carry them in (#495). Resolved once, from the first trace's category
        axis: the traces of a group share that axis by construction, which is
        what makes them one chart rather than several.
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

        # Resolved after the loop and applied to every group alike. Applying
        # it before the normalising pass below would be the same answer --
        # `stack_shares` matches by category rather than by index -- but
        # reordering once, at the end, keeps the two changes independent.
        drawn = self._category_order()

        if not normalising:
            return self._in_drawn_order(data, drawn)

        shares = stack_shares(pairs, self._layout.get("barmode"), scale)
        for group, group_shares, trace in zip(data, shares, self._traces):
            key = MaidrKey.X.value if self._horizontal(trace) else MaidrKey.Y.value
            for point, share in zip(group, group_shares):
                point[key] = share

        return self._in_drawn_order(data, drawn)

    def _category_order(self) -> list[int] | None:
        """Where each drawn category sits in the traces' own arrays.

        Asked of the first trace's category axis -- ``y`` for a horizontal
        group. The traces of a group share that axis by construction, which
        is what makes them one chart rather than several, so one answer
        applies to all of them.

        Returns
        -------
        list of int or None
            Indices into each group's points, in drawn order, or ``None``
            when the sort cannot be resolved or is the order already held.
        """
        first = self._traces[0]
        x_vals, y_vals = paired_axes(first)
        horizontal = self._horizontal(first)
        axis_name = self._yaxis_name if horizontal else self._xaxis_name
        labels = [self._to_native(v) for v in (y_vals if horizontal else x_vals)]

        drawn = self._drawn_category_order(axis_name, labels)
        if drawn is None or drawn == list(range(len(labels))):
            return None
        return drawn

    def _in_drawn_order(
        self, data: list[list[dict]], drawn: list[int] | None
    ) -> list[list[dict]]:
        """Put every group's points in the order plotly draws them.

        Records the permutation for :meth:`_get_selector`, so the data and
        the highlight cannot disagree about it. Declines a group whose length
        does not match -- a trace that carries fewer categories than the
        first would otherwise be indexed out of range, and reordering some
        groups and not others is worse than reordering none.

        Parameters
        ----------
        data : list of list of dict
            One list of points per trace, each in that trace's own order.
        drawn : list of int or None
            What :meth:`_category_order` resolved.

        Returns
        -------
        list of list of dict
            The same groups, reordered or untouched.
        """
        if drawn is None or any(len(group) != len(drawn) for group in data):
            self._drawn = None
            return data

        self._drawn = drawn
        return [[group[index] for index in drawn] for group in data]
