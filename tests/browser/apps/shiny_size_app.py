"""Shiny apps that size a maidr chart, one per case, for the chart-size tests.

Each case is a Shiny app mounted under ``/<case>/``: the chart in a fluid
page with the default figure or a wide one, in outputs of a fixed height,
in a fillable card that can be taken full screen, with a size given to the
renderer (in a card too), in a ``ui.output_ui`` written by hand, with an
announcement three lines long, in a card of a page that is not fillable and
in a sidebar layout, as an HTML string a ``render.ui`` returns, and
Plotly figures (with no height of their
own, in an output with one, and with ``autosize`` off), Bokeh plots (of a
fixed width, stretched both ways, and scaled both ways) and Altair charts (of their own size, and their
container's).
``tests/browser/test_shiny_chart_size.py`` drives them.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from shiny import App, render, ui  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.routing import Mount  # noqa: E402

import maidr  # noqa: E402
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


def _plotly_fixed():
    """A figure plotly.js draws at its layout's 700 by 450, whatever its div."""
    fig = _plotly()
    fig.update_layout(autosize=False)
    return fig


def _bokeh_stretched():
    from bokeh.plotting import figure

    plot = figure(x_range=LABELS, sizing_mode="stretch_both", title="Fruit sold")
    plot.vbar(x=LABELS, top=VALUES, width=0.8)
    return plot


def _bokeh_scaled():
    """A square plot scaled both ways: Bokeh takes its size from the width."""
    from bokeh.plotting import figure

    plot = figure(x_range=LABELS, sizing_mode="scale_both", title="Fruit sold")
    plot.vbar(x=LABELS, top=VALUES, width=0.8)
    return plot


def _long_labels():
    """Bars whose announcement takes three lines on a phone."""
    ax = _bars()
    ax.set_xlabel("The kind of fruit the stall sold over the whole summer")
    ax.set_ylabel("The number of wooden boxes of it sold")
    return ax


def _altair():
    import altair as alt
    import pandas as pd

    data = pd.DataFrame({"fruit": LABELS, "boxes": VALUES})
    return alt.Chart(data, title="Fruit sold").mark_bar().encode(x="fruit", y="boxes")


def _altair_container():
    """A chart as wide and as tall as its container."""
    return _altair().properties(width="container", height="container")


def _fluid(output):
    return ui.page_fluid(ui.h4("Before the chart"), output, ui.p("After the chart"))


def _card(output):
    return ui.page_fillable(
        ui.card(ui.card_header("Chart card"), output, full_screen=True, id="card")
    )


def _card_in_fluid(output):
    """A card in a page that is not fillable: its height is its content's."""
    return ui.page_fluid(
        ui.h4("Before the chart"), ui.card(ui.card_header("Chart card"), output)
    )


def _sidebar(output):
    """A sidebar layout, fillable at 1280px and following its content at 390."""
    return ui.page_fillable(
        ui.layout_sidebar(ui.sidebar(ui.p("Filters"), ui.p("More filters")), output)
    )


def _hand_written(output):
    """The output written by hand, as ``ui.output_ui``, not ``output_maidr``."""
    return _fluid(ui.output_ui("m"))


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
    "h360": (_fluid, output_maidr("m", height=360), {}, _bars),
    "plotly_h400": (_fluid, output_maidr("m", height=400), {}, _plotly),
    "plotly_fixed": (_fluid, output_maidr("m"), {}, _plotly_fixed),
    "bokeh_stretched": (_fluid, output_maidr("m"), {}, _bokeh_stretched),
    "bokeh_stretched_card": (_card, output_maidr("m"), {}, _bokeh_stretched),
    "renderer_card": (_card, output_maidr("m"), {"height": 300}, _bars),
    "long_text": (_fluid, output_maidr("m", height=300), {}, _long_labels),
    "hand_written": (_hand_written, None, {}, _bars),
    "card_fluid_h300": (_card_in_fluid, output_maidr("m", height=300), {}, _bars),
    "sidebar": (_sidebar, output_maidr("m"), {}, _bars),
    "bokeh_scaled": (_fluid, output_maidr("m"), {}, _bokeh_scaled),
    "bokeh_scaled_card": (_card, output_maidr("m"), {}, _bokeh_scaled),
    "altair_container": (_fluid, output_maidr("m"), {}, _altair_container),
    "altair_container_card": (_card, output_maidr("m"), {}, _altair_container),
}


def _app(page, output, sizes, figure) -> App:
    def server(input, output_, session):
        @render_maidr(**sizes)
        def m():
            return figure()

    return App(page(output), server)




def _as_string(how):
    """``render.ui`` returning the frame as a string, which drops its dependency."""

    def server(input, output_, session):
        @render.ui
        def m():
            tag = maidr.render(_bars())
            return ui.HTML(str(tag) if how == "str" else tag.get_html_string())

    return App(_fluid(ui.output_ui("m")), server)


#: Apps whose output is not ``render_maidr``'s.
OTHER_APPS = {"as_str": _as_string("str"), "as_html_string": _as_string("html")}

app = Starlette(
    routes=[Mount(f"/{name}", app=_app(*case)) for name, case in CASES.items()]
    + [Mount(f"/{name}", app=other) for name, other in OTHER_APPS.items()]
)
