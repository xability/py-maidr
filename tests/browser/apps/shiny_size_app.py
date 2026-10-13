"""Shiny apps that size a maidr chart, one per case, for the chart-size tests.

Each case is a Shiny app mounted under ``/<case>/``: the chart in a fluid
page with the default figure or a wide one, in outputs of a fixed height,
in a fillable card that can be taken full screen, with a size given to the
renderer (in a card too), in a ``ui.output_ui`` written by hand, with an
announcement three lines long, in a card of a page that is not fillable
and in a sidebar layout, in a card halfway down a long page (one drawn
again as an input changes too, and one emptied while the input ``shown``
is 0), above a slider that draws it again (matplotlib, Plotly and Bokeh;
beside an output that is not in the page too),
as an HTML string a ``render.ui`` returns (one kept from the first session
too, which ``/kept_str.html`` hands out as a download would), Plotly
figures (with no height of their own, in an output with one, and with
``autosize`` off), Bokeh plots (of a fixed width, stretched both ways, and
scaled both ways), Altair charts (of their own size, and their
container's), and string frames of the charts that take their height from
their container and of a body that follows the frame's height.
``tests/browser/test_shiny_chart_size.py`` drives them.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from shiny import App, reactive, render, req, ui  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.responses import PlainTextResponse  # noqa: E402
from starlette.routing import Mount, Route  # noqa: E402

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


def _tall_page(output):
    """A card in the middle of a page much longer than the window."""
    words = "A paragraph of text that makes the page longer than the window."
    filler = [ui.p(words) for _ in range(12)]
    return ui.page_fluid(
        ui.h4("Before the chart"),
        *filler,
        ui.card(ui.card_header("Chart card"), output),
        *filler,
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
    "tall_page": (_tall_page, output_maidr("m", height=300), {}, _bars),
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


#: A frame made into a string once, by the first session, and shown by each.
_KEPT: dict = {}


def _kept_string():
    """``render.ui`` returning a string kept from the session that made it."""

    def server(input, output_, session):
        @render.ui
        def m():
            if "html" not in _KEPT:
                _KEPT["html"] = str(maidr.render(_bars()))
            return ui.HTML(_KEPT["html"])

    return App(_fluid(ui.output_ui("m")), server)


def _kept_string_file(request):
    """The kept string, as a download handler would write it to a file."""
    return PlainTextResponse(_KEPT.get("html", ""))


def _drawn_again():
    """The tall page's chart, drawn again whenever the input ``again`` changes."""

    def server(input, output_, session):
        again = reactive.value(0)

        @reactive.effect
        @reactive.event(input.again)
        def _():
            again.set(again() + 1)

        @render_maidr
        def m():
            again()
            return _bars()

    return App(_tall_page(output_maidr("m", height=300)), server)


def _emptied():
    """The tall page's chart, gone while the input ``shown`` is 0."""

    def server(input, output_, session):
        @render_maidr
        def m():
            req(input.shown() if "shown" in input else True)
            return _bars()

    return App(_tall_page(output_maidr("m", height=300)), server)


def _scaled_bars(n):
    fig, ax = plt.subplots()
    ax.bar(LABELS, [v * n for v in VALUES], color="#4878a8")
    ax.set_title("Fruit sold")
    ax.set_xlabel("Fruit")
    ax.set_ylabel("Boxes sold")
    return ax


def _scaled_plotly(n):
    import plotly.graph_objects as go

    fig = go.Figure(go.Bar(x=LABELS, y=[v * n for v in VALUES]))
    fig.update_layout(title="Fruit sold", xaxis_title="Fruit", yaxis_title="Boxes")
    return fig


def _scaled_bokeh(n):
    from bokeh.plotting import figure

    plot = figure(x_range=LABELS, width=600, height=400, title="Fruit sold")
    plot.vbar(x=LABELS, top=[v * n for v in VALUES], width=0.8)
    return plot


def _under_a_slider(figure, unplaced=False):
    """A chart halfway down a long page, drawn again as the slider below it moves.

    With ``unplaced``, a text output that is not in the page is computed
    first anyway, and one that is says the slider's value.
    """
    words = "A paragraph of text that makes the page longer than the window."
    filler = [ui.p(words) for _ in range(12)]
    page = ui.page_fluid(
        ui.h4("Before the chart"),
        *filler,
        ui.card(ui.card_header("Chart card"), output_maidr("m")),
        ui.input_slider("n", "Scale", 1, 10, 2, width="300px"),
        ui.output_text("said"),
        *filler,
    )

    def server(input, output_, session):
        @render_maidr
        def m():
            return figure(input.n())

        @render.text
        def said():
            return f"Scale {input.n()}"

        if unplaced:
            # Shiny has no binding for it, and sends its value to the
            # document itself.
            @output_(suspend_when_hidden=False, priority=100)
            @render.text
            def nowhere():
                return f"Nowhere {input.n()}"

    return App(page, server)


#: A string frame, as ``render.ui`` returns one, of each chart that takes its
#: height from its container, and of something that follows the frame's
#: height and grows it, as nothing of maidr's should.
def _string_of(make):
    def server(input, output_, session):
        @render.ui
        def m():
            return ui.HTML(str(make()))

    return App(_fluid(ui.output_ui("m")), server)


def _follows_the_frame():
    from htmltools import tags

    from maidr.util.iframe_utils import wrap_in_iframe_plotly

    # As tall as the frame's window, and a little more: measured at the
    # frame's height, it is always taller than the frame.
    body = tags.div(style="height: calc(100vh + 4px); background: #eee")
    return wrap_in_iframe_plotly(body, "Follows", in_shiny=True, fill_height=450)


#: Apps whose output is not ``render_maidr``'s, or is drawn again.
OTHER_APPS = {
    "as_str": _as_string("str"),
    "as_html_string": _as_string("html"),
    "kept_str": _kept_string(),
    "tall_drawn_again": _drawn_again(),
    "tall_emptied": _emptied(),
    "slider_mpl": _under_a_slider(_scaled_bars),
    "slider_plotly": _under_a_slider(_scaled_plotly),
    "slider_bokeh": _under_a_slider(_scaled_bokeh),
    "slider_nowhere": _under_a_slider(_scaled_bars, unplaced=True),
    "str_altair_container": _string_of(lambda: maidr.render(_altair_container())),
    "str_bokeh_stretched": _string_of(lambda: maidr.render(_bokeh_stretched())),
    "str_follows_frame": _string_of(_follows_the_frame),
}

app = Starlette(
    routes=[Route("/kept_str.html", _kept_string_file)]
    + [Mount(f"/{name}", app=_app(*case)) for name, case in CASES.items()]
    + [Mount(f"/{name}", app=other) for name, other in OTHER_APPS.items()]
)
