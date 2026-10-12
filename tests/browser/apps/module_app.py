"""A chart inside a Shiny module, twice, for the module test.

A module's session names everything as an id, the chart's route included;
the two instances must each serve their own chart.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from shiny import App, module, ui  # noqa: E402

from maidr.widget.shiny import output_maidr, render_maidr  # noqa: E402


@module.ui
def chart_ui():
    return output_maidr("bars")


@module.server
def chart_server(input, output, session, labels, title):
    @render_maidr(use_cdn=False)
    def bars():
        fig, ax = plt.subplots()
        ax.bar(labels, [3, 1, 2])
        ax.set_title(title)
        return ax


app_ui = ui.page_fluid(chart_ui("sales"), chart_ui("costs"))


def server(input, output, session):
    chart_server("sales", ["Apples", "Pears", "Plums"], "Sales")
    chart_server("costs", ["North", "South", "East"], "Costs")


app = App(app_ui, server)
