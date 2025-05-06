import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

import maidr


def create_sample_data() -> pd.DataFrame:
    """
    Creates a sample dataframe for demonstrating facet plots.

    Returns
    -------
    pd.DataFrame
        A dataframe with product categories, regions, time periods, and metrics.

    Examples
    --------
    >>> df = create_sample_data()
    >>> df.head()
    """
    # Define sample data parameters
    categories = ["Electronics", "Clothing", "Home"]
    regions = ["North", "Central", "South"]
    years = [2020, 2021, 2022]
    quarters = [1, 2, 3, 4]

    # Lists to build dataframe
    cat_list = []
    region_list = []
    year_list = []
    quarter_list = []
    sales_list = []
    profit_list = []
    satisfaction_list = []

    # Generate data with some patterns
    np.random.seed(42)  # For reproducibility
    for cat in categories:
        # Base values differ by category
        base_sales = np.random.randint(100, 200)
        base_profit = np.random.randint(20, 40)
        base_satisfaction = np.random.uniform(3.5, 4.5)

        for region in regions:
            # Region factors
            region_factor = 1.0 + regions.index(region) * 0.1

            for year in years:
                # Growth each year
                year_factor = (year - 2019) * 0.1

                for quarter in quarters:
                    # Seasonal variations
                    quarter_factor = 1.0 + (quarter - 2.5) * 0.05

                    cat_list.append(cat)
                    region_list.append(region)
                    year_list.append(year)
                    quarter_list.append(quarter)

                    # Calculate metrics with some randomness
                    sales = (
                        base_sales
                        * region_factor
                        * (1 + year_factor)
                        * quarter_factor
                        * np.random.uniform(0.9, 1.1)
                    )
                    profit = (
                        base_profit
                        * region_factor
                        * (1 + year_factor)
                        * quarter_factor
                        * np.random.uniform(0.9, 1.1)
                    )
                    satisfaction = (
                        base_satisfaction
                        + year_factor * 0.2
                        + np.random.uniform(-0.2, 0.2)
                    )

                    sales_list.append(int(sales))
                    profit_list.append(int(profit))
                    satisfaction_list.append(round(satisfaction, 1))

    # Create the dataframe
    df = pd.DataFrame(
        {
            "Category": cat_list,
            "Region": region_list,
            "Year": year_list,
            "Quarter": quarter_list,
            "Sales": sales_list,
            "Profit": profit_list,
            "Satisfaction": satisfaction_list,
        }
    )

    # Add derived columns for time visualization
    df["Period"] = df.apply(lambda x: f"{x['Year']}-Q{x['Quarter']}", axis=1)
    df["TimePoint"] = df["Year"] + (df["Quarter"] - 1) / 4

    return df


def create_complex_facet_plot(data: pd.DataFrame) -> None:
    """
    Creates a complex facet plot with bar plots and line plots in the same figure.

    Only the leftmost plot in each row shows axes, while other plots have hidden axes.

    Parameters
    ----------
    data : pd.DataFrame
        Input dataframe containing the data to be plotted.

    Returns
    -------
    None
        This function displays the plot but does not return any value.

    Examples
    --------
    >>> df = create_sample_data()
    >>> create_complex_facet_plot(df)
    """
    # Set the aesthetic style
    sns.set_theme(style="whitegrid")

    # Create the figure with a 2×3 grid of subplots
    fig, axes = plt.subplots(2, 3, figsize=(16, 12))
    # Increase spacing between rows to prevent title overlap
    plt.subplots_adjust(hspace=0.4, top=0.9)

    # Get regions and categories for labeling
    regions = sorted(data["Region"].unique())
    categories = sorted(data["Category"].unique())

    # ------ BAR PLOTS (TOP ROW) ------
    # Aggregate data for bar plots - Average sales by region and category
    bar_data = data.groupby(["Category", "Region"])["Sales"].mean().reset_index()

    # Find max y value for consistent y-axis scaling across bar plots
    y_max = bar_data["Sales"].max() * 1.1

    # Create three bar plots in the top row - one for each region
    for i, region in enumerate(regions):
        # Filter data for current region
        region_data = bar_data[bar_data["Region"] == region]

        # Create the bar plot
        sns.barplot(
            x="Category", y="Sales", data=region_data, palette="Blues_d", ax=axes[0, i]
        )

        # Set consistent y-axis limits and title
        axes[0, i].set_ylim(0, y_max)
        axes[0, i].set_title(f"{region} Region")

        # Hide axes for all but the first plot in the row
        if i > 0:
            axes[0, i].set_ylabel("")
            # Hide y-axis ticks and labels for non-first plots
            axes[0, i].tick_params(axis="y", which="both", left=False, labelleft=False)
            # Keep grid lines for visual continuity
            axes[0, i].grid(axis="y", linestyle="-", alpha=0.2)

    # ------ LINE PLOTS (BOTTOM ROW) ------
    line_data = (
        data.groupby(["Category", "Year", "Quarter"])
        .agg({"Profit": "mean"})
        .reset_index()
    )
    line_data["TimePoint"] = line_data["Year"] + (line_data["Quarter"] - 1) / 4

    # Find min and max y values for consistent y-axis scaling
    y_min = line_data["Profit"].min() * 0.9
    y_max = line_data["Profit"].max() * 1.1

    # Create three line plots in the bottom row - one for each category
    for i, category in enumerate(categories):
        # Filter data for current category
        cat_data = line_data[line_data["Category"] == category]

        # Create the line plot
        sns.lineplot(
            x="TimePoint", y="Profit", data=cat_data, marker="o", ax=axes[1, i]
        )

        # Set consistent y-axis limits and title
        axes[1, i].set_ylim(y_min, y_max)
        axes[1, i].set_title(f"{category} Category")
        axes[1, i].set_xticks([2020, 2021, 2022])
        axes[1, i].set_xticklabels(["2020", "2021", "2022"])

        # Only show axis labels and ticks for the first plot in row
        if i == 0:
            axes[1, i].set_xlabel("Year")
            axes[1, i].set_ylabel("Profit")
        else:
            axes[1, i].set_ylabel("")
            axes[1, i].set_xlabel("Year")
            # Hide y-axis ticks and labels
            axes[1, i].tick_params(axis="y", which="both", left=False, labelleft=False)
            # Keep grid lines for visual continuity
            axes[1, i].grid(axis="y", linestyle="-", alpha=0.2)

    fig.text(
        0.5,
        0.94,
        "Average Sales by Product Category and Region",
        ha="center",
        fontsize=14,
    )
    fig.text(
        0.5,
        0.48,
        "Profit Trends by Product Category Over Time",
        ha="center",
        fontsize=14,
    )

    fig.suptitle(
        "Combined Facet Plots: Sales Distribution and Profit Trends",
        fontsize=18,
        y=1.05,
    )

    # Display the plot
    maidr.show(fig)


# Generate sample data
df = create_sample_data()

create_complex_facet_plot(df)
