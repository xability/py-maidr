"""Two offline charts, mounted under a path prefix, for the served-bundle tests.

``use_cdn=False`` on both, so each chart document loads ``maidr.js`` from
the copy the app serves rather than carrying it (#457). Two of them and a
slider they both depend on, so a test can count how often the bundle
crosses the wire for two charts and a re-render.

Mounted two levels below the server root, the way Posit Connect,
shinyapps.io or a reverse proxy serve an app under a prefix it never sees.
The chart document is fetched from a session route three levels below the
page, so a bundle URL that climbed too far, or not far enough, would miss
``lib/`` here where at the root it might still happen to resolve.
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from shiny import App, ui  # noqa: E402
from starlette.applications import Starlette  # noqa: E402
from starlette.routing import Mount  # noqa: E402

from maidr.widget.shiny import output_maidr, render_maidr  # noqa: E402

#: Where the Shiny app is mounted; kept in step with ``SERVED_BUNDLE_PREFIX``
#: in ``tests/browser/conftest.py``, which the fixture serves it under.
PREFIX = "/deep/prefix"

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


app = Starlette(routes=[Mount(PREFIX, app=App(app_ui, server))])
