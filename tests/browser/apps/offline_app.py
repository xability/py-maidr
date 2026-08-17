"""A Shiny app on the default ``use_cdn`` setting, for the offline report test.

Deliberately *not* ``use_cdn=False``: the point is what a reader sees when
``"auto"`` is left alone and the CDN cannot be reached, which is the
air-gapped deployment that has no other way to find out.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from shiny import App, ui  # noqa: E402

from maidr.widget.shiny import output_maidr, render_maidr  # noqa: E402

app_ui = ui.page_fluid(output_maidr("bars", height="500px"))


def server(input, output, session):
    @render_maidr
    def bars():
        fig, ax = plt.subplots()
        ax.bar(["a", "b", "c"], [1, 2, 3])
        ax.set_title("Sales by region")
        return ax


app = App(app_ui, server)
