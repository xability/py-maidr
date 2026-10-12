"""A Shiny Express app that sizes maidr charts, for the chart-size tests.

Express places each renderer's output itself (``render_maidr.auto_output_ui``).
A chart with no size of its own, then, in a fillable card, one given a height
beside ``render.plot`` given the same, which is what it should match.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from shiny import render  # noqa: E402
from shiny.express import ui  # noqa: E402

from maidr.widget.shiny import render_maidr  # noqa: E402

LABELS = ["Apples", "Bananas", "Cherries", "Dates", "Elderberries"]
VALUES = [3, 5, 2, 4, 6]

ui.page_opts(fillable=True)


def _bars():
    _, ax = plt.subplots()
    ax.bar(LABELS, VALUES, color="#4878a8")
    ax.set_title("Fruit sold")
    ax.set_xlabel("Fruit")
    ax.set_ylabel("Boxes sold")
    return ax


with ui.layout_columns():
    with ui.card(full_screen=True, id="auto_card"):
        ui.card_header("No size")

        @render_maidr
        def m():
            return _bars()

    with ui.card(full_screen=True, id="sized_card"):
        ui.card_header("Height 300")

        @render_maidr(height=300)
        def n():
            return _bars()

    with ui.card(full_screen=True, id="plot_card"):
        ui.card_header("render.plot, height 300")

        @render.plot(height=300)
        def p():
            plt.figure()
            plt.bar(LABELS, VALUES)
