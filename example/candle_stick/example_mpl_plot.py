import mplfinance as mpf
import pandas as pd
import maidr

daily = pd.read_csv("volcandat.csv", index_col=0, parse_dates=True)
fig, ax = mpf.plot(daily, type="candle", mav=(3, 6, 9), volume=True, returnfig=True)
maidr.show(ax)
