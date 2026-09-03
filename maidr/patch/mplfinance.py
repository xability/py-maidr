from __future__ import annotations

import uuid
from typing import Any

import wrapt
import matplotlib.pyplot as plt
import mplfinance as mpf
import numpy as np
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D
from maidr.core.enum import PlotType
from maidr.patch.common import _draw_quietly, common
from maidr.core.context_manager import ContextManager
from maidr.util.datetime_conversion import create_datetime_converter


def mplfinance_plot_patch(wrapped, instance, args, kwargs):
    """
    Enhanced patch function for `mplfinance.plot` that registers separate layers:
    - CANDLESTICK: For OHLC data (candle bodies and wicks)
    - BAR: For volume data (volume bars)
    - LINE: For moving averages (lines)

    This function intercepts calls to `mplfinance.plot`, identifies the resulting
    candlestick, volume, and moving average components, and registers them with
    maidr using the common patching mechanism.

    mplfinance only hands back its figure and axes under ``returnfig=True``, so
    the call is forced into that mode. That mode also skips mplfinance's own
    ``plt.show()`` and ``closefig`` tail, which a caller who did not ask for
    the figure is relying on, so it is replayed here once the layers are
    registered -- see `_finish_as_mplfinance_would`.
    """
    # Ensure `returnfig=True` to capture the figure and axes objects.
    original_returnfig = kwargs.get("returnfig", False)
    kwargs["returnfig"] = True

    # Under a forced `returnfig` mplfinance would still honour `closefig=True`,
    # closing the figure before it can be shown -- and the maidr backend only
    # renders figures that are still open. Hold the close back to the replay,
    # where it follows the show as it does in mplfinance itself.
    closefig = kwargs.get("closefig", "auto")
    if not original_returnfig:
        kwargs["closefig"] = False

    with ContextManager.set_internal_context():
        result = _draw_quietly(wrapped, args, kwargs)

    # Validate that we received the expected figure and axes tuple. Nothing
    # drawable came back (mplfinance returns None when drawing onto external
    # axes), so there is nothing to register and nothing to show: the replay
    # below is deliberately bypassed.
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

    # Try to extract date numbers from the data (existing logic preserved)
    date_nums = None
    data = None
    datetime_converter = None

    if len(args) > 0:
        data = args[0]
    elif "data" in kwargs:
        data = kwargs["data"]

    if data is not None:
        # Existing date_nums logic (preserved)
        if hasattr(data, "Date_num"):
            date_nums = list(data["Date_num"])
        elif hasattr(data, "index"):
            # fallback: use index if it's a DatetimeIndex
            try:
                import matplotlib.dates as mdates

                # The array form gives the same values as a call per
                # element, without the Python call per row (#706).
                date_nums = list(mdates.date2num(data.index))
            except Exception:
                pass

        # Create datetime converter for DatetimeIndex data
        if hasattr(data, "index") and hasattr(data.index, "dtype"):
            if "datetime" in str(data.index.dtype).lower():
                datetime_converter = create_datetime_converter(data)

                # Use enhanced converter's date_nums for mplfinance compatibility
                if date_nums is None and hasattr(datetime_converter, "date_nums"):
                    date_nums = datetime_converter.date_nums

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

            # Add datetime converter
            if datetime_converter is not None:
                candlestick_kwargs["_maidr_datetime_converter"] = datetime_converter
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

            # Add datetime converter
            if datetime_converter is not None:
                bar_kwargs["_maidr_datetime_converter"] = datetime_converter  # type: ignore

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

                # Name an unlabelled moving average after its period. A line
                # the caller labelled (an addplot) keeps that label: it is the
                # series name the schema announces and the legend entry, and
                # the period is already on `_maidr_ma_period` for the line
                # plot to read.
                label = str(line.get_label())
                if label.startswith("_child"):
                    new_label = f"Moving Average {estimated_period} days"
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

            # Store datetime converter
            if datetime_converter is not None:
                setattr(line, "_maidr_datetime_converter", datetime_converter)

            # Ensure GID is set for highlighting
            if line.get_gid() is None:
                gid = f"maidr-{uuid.uuid4()}"
                line.set_gid(gid)

            # Add to valid lines list
            valid_lines.append(line)

        # Register all valid lines as a single LINE plot
        if valid_lines:
            line_kwargs = dict(kwargs)

            # Add datetime converter
            if datetime_converter is not None:
                line_kwargs["_maidr_datetime_converter"] = datetime_converter

            common(PlotType.LINE, lambda *a, **k: price_ax, instance, args, line_kwargs)

    if original_returnfig:
        return result

    _finish_as_mplfinance_would(
        result[0], kwargs.get("savefig"), kwargs.get("block"), closefig
    )
    return None


def _finish_as_mplfinance_would(
    fig: Figure, savefig: Any, block: bool | None, closefig: bool | str
) -> None:
    """
    Replay what `mplfinance.plot` does after drawing when `returnfig` is false.

    This mirrors the tail of ``mplfinance/plotting.py::plot``. The ``savefig``
    write itself has already happened inside mplfinance, so only its close is
    replayed; otherwise the figure is shown and then closed on the same
    conditions mplfinance uses. ``closefig`` is ``True``, ``False`` or
    mplfinance's default ``'auto'``, which counts as set after a save but
    closes after a show only when ``block`` is set.

    Parameters
    ----------
    fig : Figure
        The figure mplfinance drew.
    savefig : Any
        The caller's ``savefig`` argument, or ``None`` if there was none.
    block : bool | None
        The caller's ``block`` argument, forwarded to ``plt.show``.
    closefig : bool | str
        The caller's ``closefig`` argument, or ``'auto'``.
    """
    # mplfinance's validator admits only True and False, so the only other
    # value is its untouched default 'auto'; name both rather than rely on
    # truthiness, which would also close on an unexpected string.
    close_is_set = closefig is True or closefig == "auto"
    if savefig is not None:
        if close_is_set:
            plt.close(fig)
        return

    plt.show(block=block)
    if closefig is True or (block and close_is_set):
        plt.close(fig)


# Apply the patch to mplfinance.plot
wrapt.wrap_function_wrapper(mpf, "plot", mplfinance_plot_patch)
