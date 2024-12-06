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
plt.figure(figsize=(14, 7))
line_plot = plt.plot(flights_wide["year"], flights_wide["Total"], marker="o")

# Adding title and labels
plt.title("Total Passengers per Year\nFrom the Flights Dataset", fontsize=16)
plt.xlabel("Year", fontsize=12)
plt.ylabel("Total Passengers (Thousands)", fontsize=12)

# Show the plot
# plt.show()
maidr.show(line_plot)
