import matplotlib.pyplot as plt
import seaborn as sns
from shiny import App, ui

from maidr.widget.shiny import render_maidr

# Load the dataset
iris = sns.load_dataset("iris")

# Define the UI components for the Shiny application
app_ui = ui.page_fluid(
    ui.row(
        ui.column(
            3,
            ui.input_select(
                "x_var",
                "Select X variable:",
                choices=iris.select_dtypes(include=["float64"]).columns.tolist(),
                selected="sepal_length",
            ),
            ui.input_select(
                "y_var",
                "Select Y variable:",
                choices=iris.select_dtypes(include=["float64"]).columns.tolist(),
                selected="sepal_width",
            ),
        ),
        ui.column(9, ui.output_ui("create_barplot")),
    )
)


# Define the server
def server(inp, _, __):
    @render_maidr
    def create_barplot():
        fig, ax = plt.subplots(figsize=(10, 6))
        s_plot = sns.scatterplot(
            data=iris, x=inp.x_var(), y=inp.y_var(), hue="species", ax=ax
        )
        ax.set_title(f"Iris {inp.y_var()} vs {inp.x_var()}")
        ax.set_xlabel(inp.x_var().replace("_", " ").title())
        ax.set_ylabel(inp.y_var().replace("_", " ").title())
        return s_plot


# Create the app
app = App(app_ui, server)

# Run the app
if __name__ == "__main__":
    app.run()
