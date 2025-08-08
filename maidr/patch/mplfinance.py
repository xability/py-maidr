import uuid
import wrapt
import mplfinance as mpf
import numpy as np
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D
from maidr.core.enum import PlotType
from maidr.patch.common import common
from maidr.core.context_manager import ContextManager


def mplfinance_plot_patch(wrapped, instance, args, kwargs):
    """
    Enhanced patch function for `mplfinance.plot` that registers separate layers:
    - CANDLESTICK: For OHLC data (candle bodies and wicks)
    - BAR: For volume data (volume bars)
    - LINE: For moving averages (lines)

    This function intercepts calls to `mplfinance.plot`, identifies the resulting
    candlestick, volume, and moving average components, and registers them with
    maidr using the common patching mechanism.
    """
    # Ensure `returnfig=True` to capture the figure and axes objects.
    original_returnfig = kwargs.get("returnfig", False)
    kwargs["returnfig"] = True

    with ContextManager.set_internal_context():
        result = wrapped(*args, **kwargs)

    # Validate that we received the expected figure and axes tuple
    if not (isinstance(result, tuple) and len(result) >= 2):
        return result if original_returnfig else None

    _, axes = result[0], result[1]
    ax_list = axes if isinstance(axes, list) else [axes]

    # Enhanced axis identification using content-based detection
    price_ax = None
    volume_ax = None

    # Identify axes by their content rather than just labels
    for ax in ax_list:
        # Price axis has candlestick collections (LineCollection for wicks, PolyCollection for bodies)
        if any(isinstance(c, (LineCollection, PolyCollection)) for c in ax.collections):
            price_ax = ax
        # Volume axis has rectangle patches for volume bars
        elif any(isinstance(p, Rectangle) for p in ax.patches):
            volume_ax = ax
        # Fallback: use y-label if content-based detection fails
        elif price_ax is None and "price" in ax.get_ylabel().lower():
            price_ax = ax
        elif volume_ax is None and "volume" in ax.get_ylabel().lower():
            volume_ax = ax

    # Try to extract date numbers from the data
    date_nums = None
    data = None
    if len(args) > 0:
        data = args[0]
    elif "data" in kwargs:
        data = kwargs["data"]

    if data is not None:
        if hasattr(data, "Date_num"):
            date_nums = list(data["Date_num"])
        elif hasattr(data, "index"):
            # fallback: use index if it's a DatetimeIndex
            try:
                import matplotlib.dates as mdates

                date_nums = [mdates.date2num(d) for d in data.index]
            except Exception:
                pass

    # Process and register the Candlestick plot
    if price_ax:
        wick_collection = next(
            (c for c in price_ax.collections if isinstance(c, LineCollection)), None
        )
        body_collection = next(
            (c for c in price_ax.collections if isinstance(c, PolyCollection)), None
        )

        if wick_collection and body_collection:
            wick_gid = f"maidr-{uuid.uuid4()}"
            body_gid = f"maidr-{uuid.uuid4()}"
            wick_collection.set_gid(wick_gid)
            body_collection.set_gid(body_gid)

            candlestick_kwargs = dict(
                kwargs,
                _maidr_wick_collection=wick_collection,
                _maidr_body_collection=body_collection,
                _maidr_date_nums=date_nums,
                _maidr_original_data=data,
                _maidr_wick_gid=wick_gid,
                _maidr_body_gid=body_gid,
            )
            common(
                PlotType.CANDLESTICK,
                lambda *a, **k: price_ax,
                instance,
                args,
                candlestick_kwargs,
            )

    # Process and register the Volume plot
    if volume_ax:
        volume_patches = [p for p in volume_ax.patches if isinstance(p, Rectangle)]

        if not volume_patches:
            # Search in shared axes for volume patches
            for twin_ax in volume_ax.get_shared_x_axes().get_siblings(volume_ax):
                if twin_ax is not volume_ax:
                    volume_patches.extend(
                        [p for p in twin_ax.patches if isinstance(p, Rectangle)]
                    )

        if volume_patches:
            # Set GID for volume patches for highlighting
            for patch in volume_patches:
                if patch.get_gid() is None:
                    gid = f"maidr-{uuid.uuid4()}"
                    patch.set_gid(gid)

            bar_kwargs = dict(
                kwargs,
                _maidr_patches=volume_patches,
                _maidr_date_nums=date_nums,
            )
            common(PlotType.BAR, lambda *a, **k: volume_ax, instance, args, bar_kwargs)

    # Process and register Moving Averages as LINE plots
    if price_ax:
        # Find moving average lines (Line2D objects)
        ma_lines = [line for line in price_ax.get_lines() if isinstance(line, Line2D)]

        # Track processed lines to avoid duplicates
        processed_lines = set()
        valid_lines = []

        for line in ma_lines:
            # Try to identify the moving average period based on NaN count
            xydata = line.get_xydata()

            if xydata is not None:
                xydata_array = np.asarray(xydata)
                nan_count = np.sum(
                    np.isnan(xydata_array[:, 1])
                )  # Count NaN in y-values

                # Map NaN count to likely moving average period
                estimated_period = nan_count + 1

                # Store the period directly on the line for easy access
                setattr(line, "_maidr_ma_period", estimated_period)

                # Create a better label for the line
                label = str(line.get_label())
                if label.startswith("_child"):
                    new_label = f"Moving Average {estimated_period} days"
                    line.set_label(new_label)
                else:
                    # If it's not a _child label, still add the period info
                    new_label = f"{label}_MA{estimated_period}"
                    line.set_label(new_label)

            # Create a unique identifier for this line based on its data
            if xydata is not None:
                xydata_array = np.asarray(xydata)
                if xydata_array.size > 0:
                    # Use shape and first few values to create a unique identifier
                    first_values = (
                        xydata_array[:3].flatten()
                        if xydata_array.size >= 6
                        else xydata_array.flatten()
                    )
                    data_hash = hash(f"{xydata_array.shape}_{str(first_values)}")
                    line_id = f"{line.get_label()}_{data_hash}"
                else:
                    line_id = f"{line.get_label()}"
            else:
                line_id = f"{line.get_label()}"

            if line_id in processed_lines:
                continue

            processed_lines.add(line_id)

            # Validate that the line has valid data
            if xydata is None or xydata_array.size == 0:
                continue

            # Store date numbers on the line for the line plot class to use
            if date_nums is not None:
                setattr(line, "_maidr_date_nums", date_nums)

            # Ensure GID is set for highlighting
            if line.get_gid() is None:
                gid = f"maidr-{uuid.uuid4()}"
                line.set_gid(gid)

            # Add to valid lines list
            valid_lines.append(line)

        # Register all valid lines as a single LINE plot
        if valid_lines:
            line_kwargs = dict(kwargs)
            common(PlotType.LINE, lambda *a, **k: price_ax, instance, args, line_kwargs)

    if not original_returnfig:
        return None

    return result


# Apply the patch to mplfinance.plot
wrapt.wrap_function_wrapper(mpf, "plot", mplfinance_plot_patch)
