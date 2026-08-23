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

        # Where each drawn category sits in each trace's own arrays, when
        # ``categoryorder`` puts the two in different orders -- **one list
        # per trace**, not one for the group. Filled by
        # ``_extract_plot_data``, which ``render()`` runs before
        # ``_get_selector`` -- so the two cannot disagree about the order
        # (#495).
        self._drawn: list[list[int]] | None = None

    def _get_selector(self) -> str | list[list[str]]:
        r"""Address the bars, per trace and per drawn category when sorted.

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
                for index in order
            ]
            for group, order in enumerate(self._drawn)
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
        carry them in (#495). Resolved **per trace**: they share the axis, so
        they share the drawn sequence of category *names*, but not the
        positions those names sit at in their own arrays.
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

        # Resolved after the loop, one order per trace. Applying it before
        # the normalising pass below would be the same answer -- `stack_shares`
        # matches by category rather than by index -- but reordering once, at
        # the end, keeps the two changes independent.
        drawn = self._category_orders()

        if not normalising:
            return self._in_drawn_order(data, drawn)

        shares = stack_shares(pairs, self._layout.get("barmode"), scale)
        for group, group_shares, trace in zip(data, shares, self._traces):
            key = MaidrKey.X.value if self._horizontal(trace) else MaidrKey.Y.value
            for point, share in zip(group, group_shares):
                point[key] = share

        return self._in_drawn_order(data, drawn)

    def _category_orders(self) -> list[list[int]] | None:
        """Where each drawn category sits in **each** trace's own arrays.

        One order per trace rather than one for the group, and that
        distinction is the whole correctness of this. The traces share the
        axis -- which is what makes them one chart -- so they share the drawn
        sequence of category *names*. They do not share the positions those
        names sit at: `px.bar(df, x=..., color=...)` builds one trace per
        colour from a filtered slice, and unless the frame happens to be
        sorted the same way in every slice their arrays disagree.

        Resolving from one trace and applying its indices positionally to the
        rest reproduces, one level up, the very defect this fixes. Measured on
        two traces of equal length written in different orders -- A as
        ``charlie, alpha, bravo`` and B as ``alpha, bravo, charlie`` -- A's
        order is ``[1, 2, 0]``, and applying it to B pulls
        ``bravo, charlie, alpha``: every point still carrying its own label
        while the *column* it lands in belongs to another category.

        Declined whole when any trace declines, and when two of them resolve
        to different sequences of names. A grid's column has to mean one
        category in every group, and traces that carry different category
        *sets* -- rather than the same set differently ordered -- cannot give
        it one.

        Returns
        -------
        list of list of int or None
            One list of indices per trace, in drawn order, or ``None`` when
            the sort cannot be resolved or every trace already holds it.
        """
        orders: list[list[int]] = []
        drawn_names: list[str] | None = None

        for trace in self._traces:
            x_vals, y_vals = paired_axes(trace)
            horizontal = self._horizontal(trace)
            axis_name = self._yaxis_name if horizontal else self._xaxis_name
            labels = [self._to_native(v) for v in (y_vals if horizontal else x_vals)]

            order = self._drawn_category_order(axis_name, labels)
            if order is None:
                return None

            names = [str(labels[index]) for index in order]
            if drawn_names is None:
                drawn_names = names
            elif names != drawn_names:
                return None
            orders.append(order)

        if all(order == list(range(len(order))) for order in orders):
            return None
        return orders

    def _in_drawn_order(
        self, data: list[list[dict]], drawn: list[list[int]] | None
    ) -> list[list[dict]]:
        """Put every group's points in the order plotly draws them.

        Each group by its **own** order, and the permutations are recorded
        for :meth:`_get_selector`, so the data and the highlight cannot
        disagree about them.

        Parameters
        ----------
        data : list of list of dict
            One list of points per trace, each in that trace's own order.
        drawn : list of list of int or None
            What :meth:`_category_orders` resolved.

        Returns
        -------
        list of list of dict
            The same groups, reordered or untouched.
        """
        if drawn is None:
            self._drawn = None
            return data

        self._drawn = drawn
        return [[group[index] for index in order] for group, order in zip(data, drawn)]
