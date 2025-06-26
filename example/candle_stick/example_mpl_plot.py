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

# Display with maidr
maidr.show(fig)
