import matplotlib.dates as mdates
import numpy as np
from matplotlib.axes import Axes
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.colors import to_rgba
from matplotlib.patches import Rectangle

from maidr.core.enum.plot_type import PlotType
from maidr.core.plot.maidr_plot import MaidrPlot


class CandlestickPlot(MaidrPlot):
    def __init__(self, axes: list[Axes], **kwargs) -> None:
        """
        Initialize the CandlestickPlot.

        Parameters
        ----------
        axes : list[Axes]
            A list of Matplotlib Axes objects. Expected to contain at least
            one Axes for OHLC data, and optionally a second for volume data.
        **kwargs : dict
            Additional keyword arguments.
        """
        self.axes = axes
        # Ensure there's at least one axis for the superclass init
        if not axes:
            raise ValueError("Axes list cannot be empty.")
        super().__init__(axes[0], PlotType.CANDLESTICK)

    def _extract_plot_data(self) -> list[dict]:
        """
        Extracts candlestick (OHLC) and volume data from the plot axes.

        This method assumes that the candlestick chart is structured with
        LineCollection for wicks and PatchCollection of Rectangles for bodies
        on the first axis (self.axes[0]). Volume data is expected as a
        PatchCollection of Rectangles on the second axis (self.axes[1]), if present.
        Open and close prices are inferred from the body rectangle's color.

        Returns
        -------
        list[dict]
            A list of dictionaries, where each dictionary represents a data point
            with 'value' (date string YYYY-MM-DD), 'open', 'high', 'low',
            'close', and 'volume'. Fields that cannot be extracted will be None.

        Examples
        --------
        Assuming a plot has been generated and `plot_instance.axes` is populated:
        >>> data = plot_instance._extract_plot_data()
        >>> print(data[0])
        {
            'value': '2021-01-01',
            'open': 100.0,
            'high': 100.9,
            'low': 99.27,
            'close': 100.75,
            'volume': 171914,
        }
        """
        if not self.axes:
            return []

        plot_data: list[dict] = []
        ax_ohlc: Axes = self.axes[0]

        body_rectangles: list[Rectangle] = []
        wick_collection: LineCollection | None = None

        # Find candlestick body Rectangles from the OHLC axis
        # Prefer PatchCollection containing Rectangles, fallback to individual Rectangles in ax.patches
        for collection in ax_ohlc.collections:
            if isinstance(collection, PatchCollection):
                # Check if the collection's patches are Rectangles
                try:
                    # Iterating a PatchCollection yields its constituent Patch objects
                    patches_are_rects = all(
                        isinstance(p, Rectangle) for p in collection
                    )
                    if (
                        patches_are_rects and len(collection.get_paths()) > 0
                    ):  # Ensure it has paths and they are Rectangles
                        for (
                            patch
                        ) in collection:  # Iterate to get actual Rectangle objects
                            if isinstance(patch, Rectangle):
                                body_rectangles.append(patch)
                        if (
                            body_rectangles
                        ):  # If we found rectangles this way, assume this is the primary body collection
                            break
                except Exception:
                    # Could fail if collection is not iterable in the expected way or patches are not Rectangles
                    pass

        if not body_rectangles:
            for patch in ax_ohlc.patches:
                if isinstance(patch, Rectangle):
                    body_rectangles.append(patch)

        if not body_rectangles:
            pass

        ax_for_wicks: Axes | None = None
        if len(self.axes) > 1:
            ax_for_wicks = self.axes[1]

        if ax_for_wicks:
            # Attempt 1: Find wicks in ax_for_wicks.collections (as a LineCollection)
            for collection in ax_for_wicks.collections:
                if isinstance(collection, LineCollection):
                    segments = collection.get_segments()
                    # Check if the collection contains segments and the first segment looks like a vertical line
                    if segments is not None and len(segments) > 0:
                        first_segment = segments[0]
                        if (
                            len(first_segment) == 2  # Segment consists of two points
                            and len(first_segment[0]) == 2  # First point has (x, y)
                            and len(first_segment[1]) == 2  # Second point has (x, y)
                            and np.isclose(
                                first_segment[0][0], first_segment[1][0]
                            )  # X-coordinates are close (vertical)
                        ):
                            wick_collection = collection
                            break  # Found a suitable LineCollection

            # Attempt 2: If no LineCollection found, try to find wicks from individual Line2D objects in ax_for_wicks.get_lines()
            if not wick_collection and hasattr(ax_for_wicks, "get_lines"):
                potential_wick_segments = []
                for line in ax_for_wicks.get_lines():  # Iterate over Line2D objects
                    x_data, y_data = line.get_data()
                    # A wick is typically a vertical line defined by two points.
                    if len(x_data) == 2 and len(y_data) == 2:
                        if np.isclose(x_data[0], x_data[1]):  # Check for verticality
                            # Create a segment in the format [[x1, y1], [x2, y2]]
                            segment = [
                                [x_data[0], y_data[0]],
                                [x_data[1], y_data[1]],
                            ]
                            potential_wick_segments.append(segment)

                if potential_wick_segments:
                    # If wick segments were found from individual lines,
                    # create a new LineCollection to hold them.
                    # This allows the downstream processing logic
                    # for wicks to remain consistent.
                    # Basic properties are set; color/linestyle
                    # are defaults and may not match
                    # the original plot's styling if that
                    # were relevant for segment extraction.
                    wick_collection = LineCollection(
                        potential_wick_segments,
                        colors="k",  # Default color for the temporary collection
                        linestyles="solid",  # Default linestyle
                    )

        # Process wicks into a map: x_coordinate -> (low_price, high_price)
        wick_segments_map: dict[float, tuple[float, float]] = {}
        if wick_collection:
            for seg in wick_collection.get_segments():
                if len(seg) == 2 and len(seg[0]) == 2 and len(seg[1]) == 2:
                    # Ensure x-coordinates are (nearly) identical for a vertical wick line
                    if np.isclose(seg[0][0], seg[1][0]):
                        x_coord = seg[0][0]  # Matplotlib date number
                        low_price = min(seg[0][1], seg[1][1])
                        high_price = max(seg[0][1], seg[1][1])
                        wick_segments_map[x_coord] = (low_price, high_price)

        body_rectangles.sort(key=lambda r: r.get_x())

        for rect in body_rectangles:
            x_left = rect.get_x()
            width = rect.get_width()
            x_center_num = x_left + width / 2.0

            try:
                date_dt = mdates.num2date(x_center_num)
                date_str = date_dt.strftime("%Y-%m-%d")
            except ValueError:
                date_str = f"raw_date_{x_center_num:.2f}"

            y_bottom = rect.get_y()
            height = rect.get_height()
            face_color = rect.get_facecolor()  # RGBA tuple

            # Infer open and close prices
            # Heuristic: Green component > Red component for an "up" candle (close > open)
            # This assumes standard green for up, red for down.
            # A more robust method would involve knowing the exact up/down colors used.
            is_up_candle = (
                face_color[1] > face_color[0]
            )  # Compare Green and Red components

            if is_up_candle:  # Typically green: price went up
                open_price = y_bottom
                close_price = y_bottom + height
            else:  # Typically red: price went down (or other color)
                close_price = y_bottom
                open_price = y_bottom + height

            matched_wick_data = None
            closest_wick_x = None
            min_diff = float("inf")

            for wick_x, prices in wick_segments_map.items():
                diff = abs(wick_x - x_center_num)
                if diff < min_diff:
                    min_diff = diff
                    closest_wick_x = wick_x

            # Tolerance for matching wick x-coordinate (e.g., 10% of candle width)
            if closest_wick_x is not None and min_diff < (width * 0.1):
                matched_wick_data = wick_segments_map[closest_wick_x]

            if matched_wick_data:
                low_price, high_price = matched_wick_data
                # Ensure high >= max(open,close) and low <= min(open,close)
                high_price = max(high_price, open_price, close_price)
                low_price = min(low_price, open_price, close_price)
            else:
                # Fallback if no wick found: high is max(open,close), low is min(open,close)
                high_price = max(open_price, close_price)
                low_price = min(open_price, close_price)

            # Extract volume data if volume axis (self.axes[1]) exists
            volume: float | None = None
            if len(self.axes) > 1 and self.axes[1]:
                ax_volume: Axes = self.axes[1]
                # Volume is usually a bar chart (Rectangles in
                # PatchCollection or individual patches)
                volume_rects_to_check: list[Rectangle] = []
                for collection in ax_volume.collections:
                    if isinstance(collection, PatchCollection):
                        for (
                            patch
                        ) in collection:  # Iterate through patches in the collection
                            if isinstance(patch, Rectangle):
                                volume_rects_to_check.append(patch)
                for patch in ax_volume.patches:  # Also check individual patches
                    if (
                        isinstance(patch, Rectangle)
                        and patch not in volume_rects_to_check
                    ):
                        volume_rects_to_check.append(patch)

                for vol_rect in volume_rects_to_check:
                    vol_x_left = vol_rect.get_x()
                    vol_width = vol_rect.get_width()
                    vol_x_center_num = vol_x_left + vol_width / 2.0

                    # Match with candlestick's x_center_num using a tolerance
                    if abs(vol_x_center_num - x_center_num) < (
                        width * 0.5
                    ):  # Wider tolerance for volume bar matching
                        volume = (
                            vol_rect.get_height()
                        )  # Volume is the height of the bar
                        break

            plot_data.append(
                {
                    "value": date_str,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "volume": volume,
                }
            )

        return plot_data

    def _extract_axes_data(self) -> dict:
        return {}
