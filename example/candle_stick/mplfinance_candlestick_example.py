"""
MODERN MPLFINANCE CANDLESTICK EXAMPLE
=====================================

This example demonstrates how to create candlestick charts using the modern
mplfinance.plot() approach, which provides full MAIDR support including:
- Moving average lines with proper period detection
- Volume data visualization
- Interactive features through MAIDR
- Custom axis formatting for accessibility

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
import matplotlib.dates as mdates
import maidr

daily = pd.read_csv("volcandat.csv", index_col=0, parse_dates=True)

fig, axlist = mpf.plot(
    daily,
    type="candle",
    volume=True,
    mav=(3, 6, 9),
    returnfig=True,
    ylabel="Price",
    ylabel_lower="Volume",
    xlabel="Date",
    figsize=(12, 8),
    title="Stock Price with Volume",
)

# Add axis formatters for better accessibility and screen reader output
# These formatters are detected by MAIDR and converted to JavaScript functions
# for consistent formatting in both visual and audio output.

# Price axis (axlist[0]) - Currency format with dollar sign
axlist[0].yaxis.set_major_formatter("${x:,.2f}")

# Date axis - Short date format (e.g., "Nov 15")
# Note: For mplfinance, DateFormatter on x-axis affects visual display only.
# MAIDR extracts dates directly from the DataFrame for accurate data.
axlist[0].xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))

# Volume axis (axlist[2]) - Number format with thousands separator
axlist[2].yaxis.set_major_formatter("{x:,.0f}")

# Apply tight layout to improve spacing
fig.tight_layout()

# Display with full MAIDR support
# This provides:
# - Automatic moving average line detection (3, 6, 9-day periods)
# - Formatted values for screen reader output (currency, dates, numbers)
maidr.show(fig)
