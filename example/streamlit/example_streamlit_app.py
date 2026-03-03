import matplotlib.pyplot as plt
import seaborn as sns
import streamlit as st
import streamlit.components.v1 as components

import maidr

# Streamlit app setup
st.title("Maidr Streamlit Example")
st.header("Interactive Streamlit App to demonstrate Maidr integration")

# Load the dataset using Seaborn
tips = sns.load_dataset("tips")

# Sidebar for user input parameters
st.sidebar.header("Filter Options")

# Dropdown to select day of the week
selected_days = st.sidebar.multiselect(
    "Select day(s) to include in the plot:",
    options=tips["day"].unique(),
    default=tips["day"].unique(),
)

# Dropdown to select plot type
plot_type = st.sidebar.selectbox(
    "Select the type of plot:", options=["Bar Plot", "Scatter Plot"]
)

# Slider to adjust figure size
fig_width = st.sidebar.slider("Figure width", min_value=5, max_value=15, value=10)
fig_height = st.sidebar.slider("Figure height", min_value=3, max_value=10, value=6)

# Filter the dataset based on selected days
filtered_tips = tips[tips["day"].isin(selected_days)]

# Create the plot based on user selection
fig, ax = plt.subplots(figsize=(fig_width, fig_height))

plot = None

if plot_type == "Bar Plot":
    # Calculate the counts of tips per day
    day_counts = filtered_tips["day"].value_counts()

    # Create a bar plot with Matplotlib
    plot = ax.bar(day_counts.index, day_counts.values)
    ax.set_title("Number of Tips by Day")
    ax.set_xlabel("Day")
    ax.set_ylabel("Count")

    # Add number formatter for better screen reader output
    ax.yaxis.set_major_formatter("{x:.0f}")

elif plot_type == "Scatter Plot":
    # Scatter plot of total_bill vs. tip
    plot = ax.scatter(filtered_tips["total_bill"], filtered_tips["tip"], alpha=0.7)
    ax.set_title("Scatter Plot of Total Bill vs. Tip")
    ax.set_xlabel("Total Bill")
    ax.set_ylabel("Tip")

    # Add currency formatters for better screen reader output
    ax.xaxis.set_major_formatter("${x:.2f}")
    ax.yaxis.set_major_formatter("${x:.2f}")

# Display the plot using Streamlit
components.html(
    maidr.render(
        plot,
    ).get_html_string(),
    scrolling=True,
    height=fig_height * 100,
    width=fig_width * 100,
)
