import os

import matplotlib.pyplot as plt
import maidr
import seaborn as sns


def get_filepath(filename: str) -> str:
    current_file_path = os.path.abspath(__file__)
    directory = os.path.dirname(current_file_path)
    return os.path.join(directory, filename)


def plot():
    # Load the dataset
    titanic = sns.load_dataset("titanic")

    # Grouping the data by 'class' and 'survived' and then counting the number of occurrences
    grouped = titanic.groupby(["class", "survived"]).size().unstack()

    # Plotting the stacked bar chart
    stacked = grouped.plot(kind="bar", stacked=True)

    # Adding labels and title
    plt.title("Passenger Count by Class and Survival Status on the Titanic")
    plt.xlabel("Class")
    plt.ylabel("Number of Passengers")
    plt.xticks(rotation=0)

    # Add number formatter to y-axis for better screen reader output
    # Count values as integers (no decimals)
    stacked.yaxis.set_major_formatter("{x:.0f}")

    return stacked


def main():
    stacked = plot()
    stacked_maidr = maidr.stacked(stacked)
    stacked_maidr.save_html(get_filepath("example_sns_stacked.html"))
    stacked_maidr.show()


if __name__ == "__main__":
    main()
