"""Show a chart in the page a Pyodide runtime is embedded in, or say why not."""

from __future__ import annotations

from htmltools import Tag

from maidr.util.caller_warning import warn_at_caller


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


def warn_no_page() -> None:
    """
    Warn that a chart cannot be shown where Pyodide has no page.

    Said instead of showing in a web worker or Node.js (see
    :meth:`maidr.util.environment.Environment.is_pyodide_without_page`),
    where every renderer would end in ``webbrowser.open``, which raises
    there.  The warning names what the host can do instead.
    """
    warn_at_caller(
        "maidr: there is no page to show this chart in: Pyodide is running "
        "in a web worker or Node.js, with no document and no notebook "
        "display. Put the HTML of maidr.render(plot).get_html_string() in "
        "the page instead, for example as an iframe's srcdoc."
    )
