"""A Shiny app for the focus-restore browser tests.

Kept as a file so Shiny runs it the way it runs a real app. The bundle is
inlined (``use_cdn=False``) so the runtime loads with no network, which is
what lets these tests run on an isolated CI runner.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from shiny import App, ui  # noqa: E402

from maidr.widget.shiny import output_maidr, render_maidr  # noqa: E402

app_ui = ui.page_fluid(
    ui.input_slider("n", "Bars", min=2, max=5, value=3),
    ui.input_text("note", "Note", value=""),
    output_maidr("bars", height="500px"),
)


def server(input, output, session):
    @render_maidr(use_cdn=False)
    def bars():
        fig, ax = plt.subplots()
        n = input.n()
        ax.bar([chr(97 + i) for i in range(n)], range(1, n + 1))
        ax.set_title("Sales by region")
        return ax


app = App(app_ui, server)
