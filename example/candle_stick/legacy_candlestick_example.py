"""
LEGACY CANDLESTICK EXAMPLE
==========================

This example demonstrates how to create candlestick charts using the legacy
matplotlib approach with mplfinance.original_flavor.candlestick_ohlc.

This is the OLD way of creating candlestick charts before mplfinance.plot()
became the standard approach. It requires manual data preparation and
matplotlib date conversion.

For modern candlestick charts with MAIDR support, see:
mplfinance_candlestick_example.py
"""

from typing import Dict, List, Optional, Tuple

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from mplfinance.original_flavor import candlestick_ohlc

import maidr


def generate_candlestick_chart(
    data_dict: Dict[str, List],
    width: float = 0.6,
    colorup: str = "g",
    colordown: str = "r",
    title: str = "Stock Price Candlestick Chart",
    show_volume: bool = True,
) -> Tuple[plt.Figure, plt.Axes]:  # type: ignore
    """
    Generate and save a candlestick chart from OHLC (Open, High, Low, Close) data.

    Parameters
    ----------
    data_dict : Dict[str, List]
        Dictionary with keys 'Date', 'Open', 'High', 'Low', 'Close'
        containing the trading data. Optional key 'Volume' for volume data.
    output_file : str, optional
        Filename to save the chart, by default "candle_stick.svg"
    width : float, optional
        Width of the candlesticks, by default 0.6
    colorup : str, optional
        Color for upward price movements, by default "g"
    colordown : str, optional
        Color for downward price movements, by default "r"
    title : str, optional
        Title for the chart, by default "Stock Price Candlestick Chart"
    show_volume : bool, optional
        Whether to display volume data as a line on the same plot, by default True

    Returns
    -------
    Tuple[plt.Figure, plt.Axes]
        Figure and Axes objects of the created chart

    Examples
    --------
    >>> data = {
    >>>     "Date": ["2021-01-01", "2021-01-02"],
    >>>     "Open": [100, 102],
    >>>     "High": [105, 106],
    >>>     "Low": [99, 101],
    >>>     "Close": [104, 105],
    >>>     "Volume": [100000, 120000]
    >>> }
    >>> fig, ax = generate_candlestick_chart(data)
    """
    array_lengths = [len(arr) for arr in data_dict.values()]
    if len(set(array_lengths)) > 1:
        raise ValueError("All arrays in data_dict must be of the same length")

    df = pd.DataFrame(data_dict)
    # Convert 'Date' column to datetime objects
    df["Date"] = pd.to_datetime(df["Date"])
    # Convert dates to matplotlib date numbers
    df["Date_num"] = df["Date"].apply(mdates.date2num)  # type: ignore

    # Prepare OHLC data in the format required by candlestick_ohlc
    ohlc = df[["Date_num", "Open", "High", "Low", "Close"]].values

    # Create a figure and an axes
    fig, ax = plt.subplots(figsize=(12, 6))

    # Plot the candlestick chart
    candlestick_ohlc(
        ax, ohlc, width=width, colorup=colorup, colordown=colordown, alpha=0.8
    )

    # Add volume as a line on the same plot if requested
    if show_volume and "Volume" in data_dict:
        # Create a secondary y-axis for volume
        ax2 = ax.twinx()

        # Plot volume as a line
        ax2.plot(
            df["Date_num"],
            df["Volume"],
            color="blue",
            linewidth=1,
            alpha=0.7,
            label="Volume",
        )

        # Set volume axis properties
        ax2.set_ylabel("Volume")
        ax2.tick_params(axis="y")
        ax2.set_title("Volume Chart")
        ax2.title.set_visible(False)

        # Add volume legend
        ax2.legend(loc="upper right")

    # Format the x-axis to display dates
    ax.xaxis_date()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    plt.xticks(rotation=45)  # Rotate x-axis labels for better readability

    # Add grid, title, and labels
    ax.grid(True, linestyle="--", alpha=0.6)
    ax.set_title(title, fontsize=14)
    ax.set_xlabel("Date", fontsize=12)
    ax.set_ylabel("Price", fontsize=12)

    # Adjust layout to prevent labels from overlapping
    plt.tight_layout()

    return fig, ax


def generate_sample_data(
    start_date: str = "2021-01-01",
    end_date: str = "2021-01-31",
    start_price: float = 100.0,
    volatility: float = 0.02,
    seed: Optional[int] = 42,
) -> Dict[str, List]:
    """
    Generate sample OHLCV data for stock price simulation.

    Parameters
    ----------
    start_date : str, optional
        Start date for the data in YYYY-MM-DD format, by default "2021-01-01"
    end_date : str, optional
        End date for the data in YYYY-MM-DD format, by default "2021-01-31"
    start_price : float, optional
        Starting price for the simulation, by default 100.0
    volatility : float, optional
        Daily price volatility as a decimal, by default 0.02 (2%)
    seed : Optional[int], optional
        Random seed for reproducibility, by default 42

    Returns
    -------
    Dict[str, List]
        Dictionary with keys 'Date', 'Open', 'High', 'Low', 'Close', 'Volume'
        containing the generated trading data

    Examples
    --------
    >>> data = generate_sample_data(start_date="2021-01-01", end_date="2021-01-10")
    >>> len(data["Date"])  # Number of trading days
    """
    if seed is not None:
        np.random.seed(seed)

    all_dates = pd.date_range(start=start_date, end=end_date)
    trading_dates = all_dates[all_dates.dayofweek < 5]  # 0-4 are Monday to Friday
    dates = [d.strftime("%Y-%m-%d") for d in trading_dates]

    opens = []
    closes = []
    highs = []
    lows = []
    volumes = []

    current_price = start_price
    for i in range(len(dates)):
        if i == 0:
            opens.append(current_price)
        else:
            opens.append(closes[i - 1])

        price_change = np.random.normal(0, volatility * opens[i])

        if opens[i] > start_price * 1.1:
            price_change -= volatility * opens[i] * 0.05
        elif opens[i] < start_price * 0.9:
            price_change += volatility * opens[i] * 0.05

        close = opens[i] + price_change
        closes.append(round(close, 2))

        daily_range = abs(price_change) + (volatility * opens[i])
        high = max(opens[i], close) + abs(np.random.normal(0, daily_range / 2))
        low = min(opens[i], close) - abs(np.random.normal(0, daily_range / 2))

        highs.append(round(high, 2))
        lows.append(round(low, 2))

        base_volume = 100000
        vol_factor = 1.0 + 2.0 * (abs(price_change) / (volatility * opens[i]))
        volume = int(base_volume * vol_factor * np.random.uniform(0.8, 1.2))
        volumes.append(volume)

    return {
        "Date": dates,
        "Open": opens,
        "High": highs,
        "Low": lows,
        "Close": closes,
        "Volume": volumes,
    }


def save_data_to_csv(data: Dict[str, List], filename: str = "stock_data.csv") -> None:
    # Convert the dictionary to a pandas DataFrame
    df = pd.DataFrame(data)

    # Save the DataFrame to a CSV file
    df.to_csv(filename, index=False)
    print(f"Data saved to {filename}")


data = generate_sample_data(
    start_date="2021-01-01",
    end_date="2021-03-31",
    start_price=100.0,
    volatility=0.015,
)

fig, ax = generate_candlestick_chart(data)

# plt.show()

maidr.show(fig)
