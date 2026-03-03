import matplotlib.pyplot as plt
import seaborn as sns

import maidr

# Load the flights dataset from seaborn
flights = sns.load_dataset("flights")

# Pivot the dataset to wide form to make it easier to plot
flights_wide = flights.pivot(index="year", columns="month", values="passengers")

# Create a time series by taking the sum of passengers per year
flights_wide["Total"] = flights_wide.sum(axis=1)

# Reset index to use 'year' as a column
flights_wide.reset_index(inplace=True)

# Plot the total number of passengers per year
fig, ax = plt.subplots(figsize=(14, 7))
line_plot = ax.plot(flights_wide["year"], flights_wide["Total"], marker="o")

# Adding title and labels
ax.set_title("Total Passengers per Year\nFrom the Flights Dataset", fontsize=16)
ax.set_xlabel("Year", fontsize=12)
ax.set_ylabel("Total Passengers (Thousands)", fontsize=12)

# Add axis formatters for better screen reader output
# Y-axis: Number format with thousands separator
ax.yaxis.set_major_formatter("{x:,.2f}")

# X-axis: Display year as integer (no decimals)
ax.xaxis.set_major_formatter("{x:.0f}")

maidr.show(line_plot)
