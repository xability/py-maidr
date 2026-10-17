"""A Shiny Express app with a chart made into a string in its page.

Outside any render function, so the frame is made as Express builds the
page, with a stand-in session that serves nothing; for the chart-size
tests.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from shiny.express import ui  # noqa: E402

import maidr  # noqa: E402

LABELS = ["Apples", "Bananas", "Cherries", "Dates", "Elderberries"]
VALUES = [3, 5, 2, 4, 6]



def _bars():
    # In a function: Express shows the value of every bare expression.
    _, ax = plt.subplots()
    ax.bar(LABELS, VALUES, color="#4878a8")
    ax.set_title("Fruit sold")
    ax.set_xlabel("Fruit")
    ax.set_ylabel("Boxes sold")
    return ax


ui.h4("Before the chart")
with ui.div(id="m"):
    ui.HTML(str(maidr.render(_bars())))
ui.p("After the chart")
