"""Show a chart in the page a Pyodide runtime is embedded in."""

from __future__ import annotations

from htmltools import Tag


def show_in_page(tag: Tag) -> None:
    """
    Append a rendered chart to the host page's ``<body>``.

    ``Maidr.show`` has nothing to open in Pyodide -- no browser to launch and
    no file a browser could load -- so the chart goes into the page that is
    running the interpreter.  The tag is the iframe ``show`` builds for every
    embedded render; its ``srcdoc`` document carries its own scripts, which
    run in the frame even though the ones in a fragment set through
    ``innerHTML`` would not.

    Parameters
    ----------
    tag : htmltools.Tag
        The iframe-wrapped chart.
    """
    from js import document  # type: ignore[import-not-found]

    host = document.createElement("div")
    host.innerHTML = tag.get_html_string()
    document.body.appendChild(host)
