from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, Callable, Dict, Tuple

import numpy as np
import wrapt

from maidr.core.context_manager import ContextManager
from maidr.core.enum.plot_type import PlotType
from maidr.core.figure_manager import FigureManager
from maidr.patch.common import _argument, _draw_quietly

if TYPE_CHECKING:
    import pandas as pd


def candlestick(
    wrapped: Callable[..., Tuple[list, list]],
    instance: Any,
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
) -> Tuple[list, list]:
    """
    Register a chart drawn by ``mplfinance.original_flavor``'s candlesticks.

    ``candlestick_ohlc`` and ``candlestick_ochl`` both draw through
    ``_candlestick``, one ``Line2D`` wick and one ``Rectangle`` body per quote,
    in the order the quotes are given. The quotes are read into the frame the
    ``mpf.plot`` path reads -- open, high, low and close on a date index -- so
    the candles are labeled, skipped and announced the same way, and each
    candle's own wick and body are handed over to be outlined.

    The layer this registered before carried the prices as a dict of lists,
    which ``CandlestickPlot`` reads only as a frame, and no artists: it held
    no candles at all, and every key on it was silent (py-example-a#5).

    Parameters
    ----------
    wrapped : Callable
        ``mplfinance.original_flavor._candlestick``.
    instance : Any
        Unused: the function is not a method.
    args : tuple
        Positional arguments passed to it.
    kwargs : dict
        Keyword arguments passed to it.

    Returns
    -------
    tuple of (list, list)
        The lines and patches ``_candlestick`` drew, unchanged.
    """
    # Read once and handed on as a list, as `network_graph` hands on its node
    # and edge lists: quotes given as a generator would be spent by the draw
    # and reach the reading below empty.
    if len(args) >= 2 and isinstance(args[1], Iterator):
        args = (args[0], list(args[1]), *args[2:])
    elif isinstance(kwargs.get("quotes"), Iterator):
        kwargs = {**kwargs, "quotes": list(kwargs["quotes"])}

    with ContextManager.set_internal_context():
        drawn = _draw_quietly(wrapped, args, kwargs)

    ax = FigureManager.get_axes(_argument("ax", wrapped, args, kwargs))
    try:
        wicks, bodies = (list(artists) for artists in drawn)
    except (TypeError, ValueError):
        return drawn
    frame = _quotes_frame(
        _argument("quotes", wrapped, args, kwargs),
        ochl=bool(_argument("ochl", wrapped, args, kwargs, default=True)),
    )
    # One wick and one body per quote, or nothing to pair a candle with.
    if ax is None or frame is None or not len(frame) == len(wicks) == len(bodies):
        return drawn

    # Imported here, as `CandlestickPlot` imports pandas: mplfinance has
    # loaded it by now, and `import maidr` should not.
    from maidr.util.datetime_conversion import create_datetime_converter

    FigureManager.create_maidr(
        [ax],
        PlotType.CANDLESTICK,
        _maidr_original_data=frame,
        _maidr_datetime_converter=create_datetime_converter(frame),
        _maidr_candle_artists=(bodies, wicks),
    )
    return drawn


def _quotes_frame(quotes: Any, ochl: bool) -> pd.DataFrame | None:
    """
    The quotes as a frame of prices on a date index.

    ``_candlestick`` reads each quote as ``(time, open, close, high, low)``
    with ``ochl=True`` -- its default, and ``candlestick_ochl``'s -- and as
    ``(time, open, high, low, close)`` otherwise, which is what
    ``candlestick_ohlc`` passes. The time is a matplotlib date number; it is
    read back as the date the axis draws, in the zone matplotlib's
    ``timezone`` setting gives, and kept without the zone, as the
    ``mpf.plot`` path keeps a frame's index. A quote whose time is not a
    number has no date to be read at, so its prices are left out as a gap's
    are.

    Parameters
    ----------
    quotes : Any
        The quotes the caller passed.
    ochl : bool
        Whether each quote is ordered open, close, high, low.

    Returns
    -------
    pandas.DataFrame or None
        One row per quote, in order, with ``Open``, ``High``, ``Low`` and
        ``Close`` columns; ``None`` when the quotes do not each begin with
        five numbers.
    """
    import matplotlib.dates as mdates
    import pandas as pd

    # The first five fields of each quote, which is all `_candlestick` reads:
    # a quote may go on with a volume or anything else.
    try:
        table = np.asarray([tuple(quote)[:5] for quote in quotes], dtype=float)
    except (TypeError, ValueError):
        return None
    if table.ndim != 2 or table.shape[1] != 5 or len(table) == 0:
        return None

    names = ("Open", "High", "Low", "Close")
    order = ("Open", "Close", "High", "Low") if ochl else names
    prices = {name: table[:, column] for column, name in enumerate(order, start=1)}
    frame = pd.DataFrame({name: prices[name] for name in names})

    times = table[:, 0]
    dated = np.isfinite(times)
    stamps = [pd.NaT] * len(times)
    for row, stamp in zip(np.flatnonzero(dated), mdates.num2date(times[dated])):
        stamps[row] = stamp
    index = pd.DatetimeIndex(stamps)
    frame.index = index.tz_localize(None) if index.tz is not None else index
    frame.loc[~dated, :] = np.nan
    return frame


# Applied once `mplfinance.original_flavor` is imported rather than importing it
# here, which would load pandas on every `import maidr`; see
# `maidr/patch/mplfinance.py`.
@wrapt.when_imported("mplfinance.original_flavor")
def _patch_original_flavor(original_flavor: Any) -> None:
    wrapt.wrap_function_wrapper(original_flavor, "_candlestick", candlestick)
