"""Shiny apps that size a maidr chart, one per case, for the chart-size tests.

Each case is a Shiny app mounted under ``/<case>/``: the chart in a fluid
page with the default figure or a wide one, in outputs of a fixed height,
in a fillable card that can be taken full screen, with a size given to the
renderer, and Plotly, Bokeh and Altair charts. ``tests/browser/test_shiny_chart_size.py``
drives them.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from shiny import App, ui  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.routing import Mount  # noqa: E402

from maidr.widget.shiny import output_maidr, render_maidr  # noqa: E402

LABELS = ["Apples", "Bananas", "Cherries", "Dates", "Elderberries"]
VALUES = [3, 5, 2, 4, 6]


def _bars(figsize=None):
    fig, ax = plt.subplots(**({"figsize": figsize} if figsize else {}))
    ax.bar(LABELS, VALUES, color="#4878a8")
    ax.set_title("Fruit sold")
    ax.set_xlabel("Fruit")
    ax.set_ylabel("Boxes sold")
    return ax


def _plotly():
    import plotly.graph_objects as go

    fig = go.Figure(go.Bar(x=LABELS, y=VALUES))
    fig.update_layout(title="Fruit sold", xaxis_title="Fruit", yaxis_title="Boxes")
    return fig


def _bokeh():
    from bokeh.plotting import figure

    plot = figure(x_range=LABELS, width=600, height=400, title="Fruit sold")
    plot.vbar(x=LABELS, top=VALUES, width=0.8)
    return plot


def _altair():
    import altair as alt
    import pandas as pd

    data = pd.DataFrame({"fruit": LABELS, "boxes": VALUES})
    return alt.Chart(data, title="Fruit sold").mark_bar().encode(x="fruit", y="boxes")


def _fluid(output):
    return ui.page_fluid(ui.h4("Before the chart"), output, ui.p("After the chart"))


def _card(output):
    return ui.page_fillable(
        ui.card(ui.card_header("Chart card"), output, full_screen=True, id="card")
    )


#: case -> (page, output, renderer arguments, figure)
CASES = {
    "default": (_fluid, output_maidr("m"), {}, _bars),
    "wide": (_fluid, output_maidr("m"), {}, lambda: _bars((10, 3))),
    "h300": (_fluid, output_maidr("m", height="300px"), {}, _bars),
    "h600": (_fluid, output_maidr("m", height=600), {}, _bars),
    "card": (_card, output_maidr("m"), {}, _bars),
    "renderer": (_fluid, output_maidr("m"), {"width": 500, "height": 300}, _bars),
    "plotly": (_fluid, output_maidr("m"), {}, _plotly),
    "plotly_card": (_card, output_maidr("m"), {}, _plotly),
    "bokeh": (_fluid, output_maidr("m"), {}, _bokeh),
    "altair": (_fluid, output_maidr("m"), {}, _altair),
}


def _app(page, output, sizes, figure) -> App:
    def server(input, output_, session):
        @render_maidr(**sizes)
        def m():
            return figure()

    return App(page(output), server)


app = Starlette(
    routes=[Mount(f"/{name}", app=_app(*case)) for name, case in CASES.items()]
)
