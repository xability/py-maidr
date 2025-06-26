"""
MODERN MPLFINANCE CANDLESTICK EXAMPLE
=====================================

This example demonstrates how to create candlestick charts using the modern
mplfinance.plot() approach, which provides full MAIDR support including:
- Moving average lines with proper period detection
- Volume data visualization
- Interactive features through MAIDR

This is the RECOMMENDED way to create candlestick charts as it:
- Automatically handles date formatting
- Provides built-in moving average support
- Integrates seamlessly with MAIDR for accessibility
- Requires minimal code compared to legacy approaches

For comparison with the legacy approach, see:
legacy_candlestick_example.py
"""

import mplfinance as mpf
import pandas as pd
import maidr

daily = pd.read_csv("volcandat.csv", index_col=0, parse_dates=True)

fig, axlist = mpf.plot(
    daily,
    type="candle",
    volume=True,
    mav=(3, 6, 9),
    returnfig=True,
    ylabel="Price ($)",
    ylabel_lower="Volume",
    xlabel="Date",
    figsize=(12, 8),
    title="Stock Price with Volume",
)

# Apply tight layout to improve spacing
fig.tight_layout()

# Display with full MAIDR support
# This provides:
# - Automatic moving average line detection (3, 6, 9-day periods)
maidr.show(fig)
