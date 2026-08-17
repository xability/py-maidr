"""Two charts that both re-render, for the focus-isolation test.

Both depend on the slider on purpose. If only one re-rendered, the
restore's ``held.el.isConnected`` check would short-circuit before the
container-id check was ever consulted, and a test built on that asymmetry
would pass with the id scoping deleted -- which is exactly what happened
to the first version of this fixture.

With both replaced at once, the element that had focus really is gone,
focus really is adrift, and both containers' observers fire. Only the id
check decides which chart gets the reader back.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from shiny import App, ui  # noqa: E402

from maidr.widget.shiny import output_maidr, render_maidr  # noqa: E402

app_ui = ui.page_fluid(
    ui.input_slider("n", "Bars", min=2, max=5, value=3),
    output_maidr("first", height="400px"),
    output_maidr("second", height="400px"),
)


def server(input, output, session):
    @render_maidr(use_cdn=False)
    def first():
        fig, ax = plt.subplots()
        n = input.n()
        ax.bar([chr(97 + i) for i in range(n)], range(1, n + 1))
        ax.set_title("Sales by region")
        return ax

    @render_maidr(use_cdn=False)
    def second():
        fig, ax = plt.subplots()
        n = input.n()
        ax.bar([chr(120 - i) for i in range(n)], range(7, 7 + n))
        ax.set_title("Costs by region")
        return ax


app = App(app_ui, server)
