"""Streamlit integration for MAIDR.

Provides :func:`render_maidr`, which draws an accessible chart into a
Streamlit app, and :func:`maidr_html`, which returns the same chart as a
self-contained HTML string for callers that want to cache or place it
themselves.

Requires the optional ``streamlit`` extra::

    pip install "maidr[streamlit]"

Notes
-----
The chart is embedded in an iframe, and that is deliberate rather than
incidental.  Streamlit binds ``r`` at the document level -- it reruns the
script -- exempting only form fields, and maidr binds ``r`` for review
mode.  Two listeners on one document cannot both win, and
``preventDefault`` in one does not stop the other.  The iframe is what
keeps maidr's keyboard interface intact, so an embedding that renders the
chart directly into the Streamlit page would take that key away from it.

Measured rather than inferred, on Streamlit 1.61.1 in Chromium.  From the
page, ``r`` reruns the script; from inside the frame, the same keystroke
reaches maidr (``Review is on``) and the script does not rerun.  One
document-level collision is enough to make the frame load-bearing, which
is why this note now claims only the key that was measured: an earlier
version of it also named ``c`` and ``esc``, neither of which produced an
observable rerun.  That is not proof they are unbound -- they may drive
something else that collides just as badly -- but it was more than the
evidence supported.

Streamlit reruns the whole script on every widget interaction and hands
the frame whatever this module returned.  A different string makes the
browser reload the frame, and maidr starts over inside it; an identical
one leaves the frame alone.  So an unchanged chart renders to the same
string on every run (``_stable_ids``), and what a rerun costs the reader
depends on where they are when it happens.  Measured on the same
Streamlit and Chromium, with the reader on the second bar and braille on,
and the chart uncached:

- A rerun that reaches the app while the reader stays in the chart -- a
  ``st.fragment(run_every=...)`` around it, or an auto-refresh calling
  ``st.rerun()`` on a timer.  Before, the frame reloaded, focus fell to its
  ``<body>``, the braille panel closed and the next arrow key did nothing,
  with nothing announced.  Now the frame, focus, braille and position all
  survive, and the next arrow key reads the third bar.
- A reader who leaves the chart to use a widget, and comes back.  They
  start over, before and after this -- and just the same with no rerun at
  all, tabbing out and back in, because maidr.js releases a chart's state
  whenever focus leaves it.  The frame surviving is what would let that
  state survive too, but keeping it is maidr.js's to change, not this
  module's (xability/maidr#1338).

That holds for matplotlib, seaborn, Altair and Plotly charts.  A Bokeh
chart (experimental) still differs between renders and is rebuilt on every
rerun, as before: its model ids come from a process-wide counter, some are
made during the render itself, and they are referenced from Bokeh's
document and from the highlight map in several shapes, beside data that
can hold the very same strings.  Renaming them safely would mean knowing
every place a reference can sit, and one missed would leave a highlight
pointing nowhere.  Caching its HTML (see :func:`maidr_html`) keeps its
frame all the same.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
import warnings
from functools import lru_cache
from typing import Any, Literal, Optional, Union

from htmltools import HTML, tags

import maidr
from maidr.util.dependencies import inline_bundle_tags, read_bundled_js
from maidr.util.iframe_utils import chart_title_on, iframe_title

#: Accepted by ``use_cdn``; ``None`` defers to :func:`maidr.get_use_cdn`.
UseCdn = Optional[Union[bool, Literal["auto"]]]

#: Sizes accepted by :func:`render_maidr`, mirroring ``st.iframe``.
Size = Union[int, Literal["content", "stretch"]]

#: Height used when falling back to ``components.v1.html``, which cannot
#: size itself.  Its own default is ``None``, which Streamlit renders as
#: 150 px -- tall enough to look deliberate and short enough to crop every
#: real chart, which is the most common way a Streamlit embed goes wrong.
_LEGACY_FALLBACK_HEIGHT = 600


def maidr_html(
    plot: Any = None, *, use_cdn: UseCdn = None, _stacklevel: int = 3
) -> str:
    """
    Return an accessible chart as a self-contained HTML string.

    Parameters
    ----------
    plot : Any, optional
        The plot to render -- a matplotlib or seaborn artist, a Plotly
        ``Figure``, a Bokeh figure or layout, or an Altair chart.  ``None``
        uses the current matplotlib figure, and warns: that figure is
        process-global, and Streamlit runs sessions on separate threads, so
        by the time it is rendered it may be another session's.  Pass the
        plot explicitly.
    use_cdn : bool, {"auto"}, or None, default None
        Where the chart loads ``maidr.js`` from; see :func:`maidr.render`.
        ``None`` defers to the process-wide default.
    _stacklevel : int, default 3
        Internal. Frames to skip when warning, so a warning points at the
        caller's own line; :func:`render_maidr` raises it by one because it
        sits a frame further out. Not part of the public API -- the
        underscore is the only thing stopping an IDE from offering it.

    Returns
    -------
    str
        A complete HTML fragment for one iframe.  An unchanged chart is the
        same string on every call, which is what lets Streamlit keep its
        frame across a rerun (the module notes say what that keeps, and why
        a Bokeh chart is the exception).
        Its ids are derived from the chart, so they are unique within the
        string but not between two calls for the same chart: give each its
        own frame.

    Notes
    -----
    Exists as its own entry point so the *string* can be cached, which
    spares rendering the chart again when Streamlit reruns the whole script
    on every widget interaction.  Except for a Bokeh chart, the frame no
    longer depends on it -- an unchanged chart's frame is kept either way --
    so this is about what the render costs, not about the reader::

        @st.cache_data
        def chart_html(_fig, key):
            return maidr_html(_fig)

        html = chart_html(fig, key=selected_day)

    Both arguments are load-bearing.  The underscore on ``_fig`` tells
    Streamlit not to hash it, which a matplotlib ``Figure`` does not
    support -- and ``key`` is then the only thing left to hash.  Without
    it every argument is skipped, the cache key is constant, and the first
    chart is returned for the rest of the session: a chart that silently
    stops matching its own controls.

    Under ``use_cdn=False`` the ~1.9 MB bundle is embedded in the string.
    Serializing to HTML is what makes an embed possible at all, and it
    drops :class:`htmltools.HTMLDependency` children on the way, so a
    reference to the bundle would not survive; the source itself has to.
    """
    html, _title = _render(plot, use_cdn, _stacklevel + 1)
    return html


def _render(plot: Any, use_cdn: UseCdn, stacklevel: int) -> tuple[str, str]:
    """
    Render a chart to HTML, and report the title it is known by.

    :func:`maidr_html` returns only the first; :func:`render_maidr` needs
    both, because Streamlit builds the chart's frame itself and the title is
    what names it.

    Parameters
    ----------
    plot : Any
        As for :func:`maidr_html`.
    use_cdn : bool, {"auto"}, or None
        As for :func:`maidr_html`.
    stacklevel : int
        As ``_stacklevel`` on :func:`maidr_html`, counted from here.

    Returns
    -------
    tuple of (str, str)
        The HTML, and the chart's title -- ``""`` when it has none.
    """
    if plot is None:
        # ``maidr.render(None)`` falls back to ``plt.gcf()``, which is the
        # right default for a script or a notebook and is why it is kept
        # rather than refused.  It is the wrong one here: pyplot's figure
        # registry is process-global and Streamlit runs each session on its
        # own thread, so between one session's ``plt.subplots()`` and its
        # render call another session's figure can become current -- and
        # the render then succeeds, handing a blind reader the wrong chart
        # with nothing to say so.  Streamlit's own ``st.pyplot()`` has
        # warned about the same default since 0.67; this does the same
        # rather than removing a documented default without notice.
        warnings.warn(
            "maidr: maidr_html()/render_maidr() called without a plot uses "
            "matplotlib's current figure, which is process-global; Streamlit "
            "runs sessions on separate threads, so another session's figure "
            "can be rendered in its place. Pass the figure or axes explicitly.",
            UserWarning,
            # Same arithmetic as the ``use_cdn=False`` warning below: raised
            # from inside this function, so one less than
            # ``_warn_if_no_runtime`` gets.
            stacklevel=stacklevel - 1,
        )
    # Resolved once and then passed on, rather than read again inside
    # ``render``.  ``set_use_cdn`` writes process-wide state and Streamlit
    # runs sessions on separate threads, so reading it twice leaves a window
    # in which this function decides whether to inline against one answer
    # while the chart was built from another.
    resolved = maidr.get_use_cdn() if use_cdn is None else use_cdn
    rendered = maidr.render(plot, use_cdn=resolved)
    # Before the bundle is inlined, so the pass reads the chart and not the
    # ~1.9 MB of runtime beside it; see ``_stable_ids`` for why at all.
    html = _stable_ids(str(rendered.get_html_string()))

    if resolved is False:
        if _references_maidr_runtime(html):
            # Altair charts are the case: :func:`maidr.render` hands them to
            # the Vega-Lite adapter before ``use_cdn`` is consulted, so the
            # chart already names a remote runtime and inlining the bundle
            # would add ~1.9 MB the page never loads -- while still needing
            # the network.  Say so rather than doing it.
            warnings.warn(
                "maidr: use_cdn=False cannot be honored for this chart; it "
                "loads maidr.js from the CDN regardless, so the embed still "
                "requires network access.",
                UserWarning,
                # One less than ``_warn_if_no_runtime`` gets: this warns from
                # inside this function, while that one warns from inside its
                # own, a frame deeper.  Sharing the number would point this
                # warning one frame past the caller.
                stacklevel=stacklevel - 1,
            )
        else:
            inline_tags = inline_bundle_tags()
            if inline_tags is not None:
                # Ahead of the rendered tag, so ``maidr.js`` is defined by
                # the time the bootstrap inside it calls ``window.main()``.
                # The chart goes in as the string already made stable, not
                # as ``rendered``, which would serialize the random ids back.
                html = str(tags.div(*inline_tags, HTML(html)).get_html_string())

    _warn_if_no_runtime(html, resolved, stacklevel=stacklevel)
    return html, chart_title_on(rendered)


#: The shape of every id py-maidr mints, ``str(uuid.uuid4())``.
_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

#: The ids matplotlib's SVG backend mints for clip paths, markers, hatches,
#: path collections and images: a type prefix, then ten hex digits of a hash
#: salted with a fresh uuid unless ``svg.hashsalt`` is set.
_MPL_ID = r"(?:[hpm]|(?:Im_)?image|C[0-9a-f]+_[0-9a-f]+_)[0-9a-f]{10}"

#: The places a *minted* id is written, as opposed to a string that merely
#: has the shape of one.  A chart's own data can be a uuid -- an order id on
#: a category axis -- and renaming it would change what the reader hears.
#: Each form here is written by py-maidr or matplotlib and never carries
#: data: an id with a ``maidr-`` prefix (a gid, or the Bokeh and Altair
#: wrappers), the value of an ``id`` or ``maidr`` attribute or attribute
#: selector, a schema ``id`` inside the escaped JSON of the SVG's ``maidr``
#: attribute, and matplotlib's own ``<defs>``.  An id found in one of these
#: is then renamed everywhere it occurs, including where it is referenced.
#:
#: A schema ``id`` in *raw* JSON is deliberately not one of them: raw JSON
#: is also where an Altair dataset keeps a user's column named ``id``, and
#: where a Plotly figure keeps its ``meta``.  Plotly's schema is found by
#: parsing it instead; see :func:`_plotly_schema_ids`.
#:
#: Every branch opens with a literal, and :data:`_TOKEN` with a character
#: class, rather than with ``\b`` or a lookbehind: that is what lets the
#: regex engine skip to the next candidate instead of trying every
#: position, and a large chart is megabytes of numbers.  Written with
#: lookarounds, the pass took longer than the render it followed on a
#: 20,000-point scatter.
_MINTED = re.compile(
    rf"maidr-(?:[a-z]+-)?({_UUID})"
    rf"|id=[\"']({_UUID})"
    rf"|maidr=[\"']({_UUID})"
    rf"|&quot;id&quot;: &quot;({_UUID})"
    rf"|id=\"({_MPL_ID})\""
)

#: Either shape as a whole token -- the character before it is captured
#: rather than looked behind at, for the reason above -- so a match is
#: never a slice of a longer word.  An underscore may come before one, as
#: in the ``axes_<uuid>`` a Plotly subplot's selector names.  Which matches
#: are renamed is decided by :data:`_MINTED` and :func:`_plotly_schema_ids`.
_TOKEN = re.compile(rf"([^0-9A-Za-z])({_UUID}|{_MPL_ID})(?![0-9A-Za-z_])")

#: Where the Plotly path assigns its schema, as raw JSON, in the init script
#: ``maidr/plotly/plotly_maidr.py`` writes.
_PLOTLY_SCHEMA = re.compile(r"var maidrSchema = ")

#: When matplotlib wrote the SVG, to the microsecond, and the line it is on.
_SVG_DATE = re.compile(r"\n[ \t]*<dc:date>[^<]*</dc:date>")

#: A minted id's place in :func:`_stable_ids`' skeleton, by its position.
_BLANK = re.compile("\x00([0-9]+)\x00")

#: The namespace ``uuid5`` needs for the ids :func:`_stable_ids` derives.
_STABLE_ID_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL, "https://github.com/xability/py-maidr"
)


def _stable_ids(html: str) -> str:
    """Make two renders of an unchanged chart the same string.

    Streamlit reruns the whole script on every widget interaction, and hands
    the frame whatever this module returned.  When that string differs from
    the last one the browser reloads the frame, and maidr starts over
    inside it; when it is identical, the frame is left alone.  A chart
    differed on every render only in ids nobody reads -- fresh uuids from
    py-maidr, a random hash salt from matplotlib -- and in the time the SVG
    was written, so every rerun reloaded every chart on the page.  What
    that cost a reader, measured, is in the module notes.

    Each minted id is replaced by one derived from the chart with every
    such id blanked out, and from its place in the document.  So an
    unchanged chart gets the same ids on every render, a changed one gets
    different ids, and ids that were distinct in the document stay
    distinct.  Uniqueness is only per document, which is what a Streamlit
    embed is: one chart to a frame.  The notebook, Shiny, Flask and
    ``save_html`` paths never come through here, and can place several
    charts in one document, so they keep their random ids.

    Parameters
    ----------
    html : str
        One serialized chart, without the inlined bundle.

    Returns
    -------
    str
        The same chart, its minted ids replaced and its timestamp removed.
    """
    html = _SVG_DATE.sub("", html)
    minted = {token for match in _MINTED.finditer(html) for token in match.groups()}
    minted.discard(None)
    minted |= _plotly_schema_ids(html)
    # The blanks below are NUL-delimited, which no serialized chart holds --
    # XML forbids the character -- but one that somehow did is left as it
    # was, rather than have its own text read back as a blank.
    if not minted or "\x00" in html:
        return html

    # First, the chart with each minted id replaced by the order in which
    # it first appears: what stays the same between two renders of it.
    order: dict[str, int] = {}

    def blank(match: re.Match) -> str:
        before, token = match.groups()
        if token not in minted:
            return match.group(0)
        return f"{before}\x00{order.setdefault(token, len(order))}\x00"

    skeleton = _TOKEN.sub(blank, html)
    digest = hashlib.sha256(skeleton.encode("utf-8")).hexdigest()

    # Then each id derived from that and its position, in its own shape: a
    # uuid stays a uuid, and a matplotlib id keeps its type prefix.
    renamed: list[str] = []
    for token, position in order.items():
        name = f"{digest}:{position}"
        if re.fullmatch(_UUID, token):
            renamed.append(str(uuid.uuid5(_STABLE_ID_NAMESPACE, name)))
        else:
            suffix = hashlib.sha256(name.encode("utf-8")).hexdigest()[:10]
            renamed.append(token[:-10] + suffix)

    # Filled into the skeleton rather than found again in ``html``: the
    # blanks are cheap to find, where ``_TOKEN`` has to consider every
    # character of the chart a second time.
    return _BLANK.sub(lambda match: renamed[int(match.group(1))], skeleton)


def _plotly_schema_ids(html: str) -> set[str]:
    """Report the ids py-maidr minted into a Plotly chart's schema.

    Plotly's schema travels as raw JSON in the init script, where a
    pattern cannot tell its ``id`` keys from the figure's own JSON beside
    it.  So it is parsed, and only the fields py-maidr fills with a fresh
    uuid are read: the figure's ``id``, each subplot's ``id`` and the
    ``axes_<uuid>`` its ``selector`` names, and each layer's ``id``.  The
    div the chart is drawn into has a minted id too, but as an ``id``
    attribute, which :data:`_MINTED` already finds.

    Parameters
    ----------
    html : str
        One serialized chart.

    Returns
    -------
    set of str
        The minted ids; empty for a chart that is not Plotly, or whose
        schema does not have the shape this reads -- which leaves those ids
        as they were rather than guessing at them.
    """
    ids: set[str] = set()
    for match in _PLOTLY_SCHEMA.finditer(html):
        try:
            schema, _end = json.JSONDecoder().raw_decode(html, match.end())
            ids.add(schema["id"])
            for cell in (cell for row in schema["subplots"] for cell in row):
                ids.add(cell["id"])
                ids.update(re.findall(_UUID, cell.get("selector", "")))
                ids.update(layer["id"] for layer in cell["layers"])
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    return {id_ for id_ in ids if isinstance(id_, str) and re.fullmatch(_UUID, id_)}


#: Matches a quoted URL naming the ``maidr`` npm package and a ``.js`` file.
#:
#: Deliberately matches a *URL* rather than a ``<script src=...>`` tag,
#: because maidr arrives in two shapes: the Altair adapter emits a literal
#: tag, while the matplotlib and Plotly paths build the element in
#: JavaScript (``s.src = '...'``), where no such tag exists in the markup.
#: Matching the tag alone reports "no runtime" for the two commonest
#: renderers.
#: The ``/`` is load-bearing: without it, any quoted string merely ending in
#: ``...maidr@1.js`` would match -- ``notmaidr@1.js`` among them. Every URL
#: this needs to recognize carries the npm path segment ``/maidr@``.
_MAIDR_RUNTIME_URL = re.compile(r"[\"'][^\"']*/maidr@[^\"']*\.js", re.I)


def _references_maidr_runtime(html: str) -> bool:
    """Report whether the HTML fetches a maidr runtime over the network.

    Names the ``maidr`` package specifically.  Asking only whether *some*
    ``<script>`` and *some* ``src=`` appear would be answered "yes" by any
    Plotly chart, which always carries a ``cdn.plot.ly`` tag of its own --
    vouching for a maidr runtime on the strength of an unrelated one.

    Parameters
    ----------
    html : str
        The serialized chart.

    Returns
    -------
    bool
        True if a maidr runtime URL appears in the document.
    """
    return bool(_MAIDR_RUNTIME_URL.search(html))


@lru_cache(maxsize=1)
def _bundle_marker() -> Optional[str]:
    """Return a slice of the bundled ``maidr.js``, for recognizing it inline.

    Asking whether the bundle is in the string by looking for the bundle
    beats asking whether the string is large, which a big enough chart can
    satisfy on its own.

    Returns ``None`` when the bundle cannot be read at all -- meaning "no
    answer", so the caller falls back to its other checks rather than
    treating absence as presence.  An *empty* bundle deliberately yields a
    sentinel that cannot occur in real HTML: returning ``""`` there would
    match every string and silently vouch for a chart that has no runtime,
    which is the one thing this check exists to catch.
    """
    try:
        source = read_bundled_js()
    except (OSError, ValueError):
        return None
    return source[:200] or "\x00maidr-bundle-is-empty\x00"


def _warn_if_no_runtime(html: str, use_cdn: Any, stacklevel: int = 3) -> None:
    """Warn when the emitted HTML has no way to load ``maidr.js``.

    A chart with no runtime behind it still *looks* right -- it is the SVG,
    unchanged -- while being silently unusable: no sonification, no
    braille, no keyboard navigation.  That failure is invisible to a
    sighted developer testing their own app, which is precisely why it is
    worth an explicit check rather than trusting the branches above.

    Parameters
    ----------
    html : str
        The serialized chart.
    use_cdn : Any
        The resolved mode, quoted back in the message.
    stacklevel : int, default 3
        Frames to skip so the warning points at the user's own call rather
        than at a line inside this module.
    """
    if _references_maidr_runtime(html):
        return
    marker = _bundle_marker()
    if marker is not None and marker in html:
        return
    warnings.warn(
        "maidr: the rendered chart carries no source for maidr.js, so it "
        "will display as a static image with no sonification, braille or "
        f"keyboard navigation (use_cdn={use_cdn!r}). This is a bug in "
        "py-maidr; please report it.",
        UserWarning,
        stacklevel=stacklevel,
    )


def render_maidr(
    plot: Any = None,
    *,
    height: Size = "content",
    width: Size = "stretch",
    tab_index: Optional[int] = None,
    use_cdn: UseCdn = None,
) -> None:
    """
    Draw an accessible MAIDR chart in a Streamlit app.

    Parameters
    ----------
    plot : Any, optional
        The plot to render -- a matplotlib or seaborn artist, a Plotly
        ``Figure``, a Bokeh figure or layout, or an Altair chart.  ``None``
        uses the current matplotlib figure, and warns: that figure is
        process-global, and Streamlit runs sessions on separate threads, so
        by the time it is rendered it may be another session's.  Pass the
        plot explicitly.
    height : int, {"content", "stretch"}, default "content"
        Height of the embed.  ``"content"`` lets Streamlit measure the
        chart, which is what keeps maidr's braille and text panels visible
        when they open.
    width : int, {"content", "stretch"}, default "stretch"
        Width of the embed.
    tab_index : int or None, default None
        Tab order of the *frame*, passed through to Streamlit.  ``None``
        is the browser default and is deliberate: an iframe's contents
        already take part in sequential focus navigation, and maidr gives
        the chart inside its own tab stop, so a keyboard user tabs
        straight onto the chart.  Passing ``0`` makes the frame itself a
        stop as well, which is one extra Tab before the chart -- and on a
        Streamlit whose ``st.iframe`` does not take ``alt``, that stop
        announces as "st.iframe" on every chart on the page.  It is
        exposed for layouts that want a deterministic landing point, not
        because the chart needs it to be reachable.
    use_cdn : bool, {"auto"}, or None, default None
        Where the chart loads ``maidr.js`` from; see :func:`maidr.render`.
        Pass ``False`` for an air-gapped deployment.  Prefer this argument
        over :func:`maidr.set_use_cdn`: the setter writes process-wide
        state, and Streamlit runs sessions on separate threads, so one
        session calling it changes what every other session renders.

    Returns
    -------
    None
        Nothing is returned.  The embed sends no data back, and handing
        back a Streamlit object would suggest an interactivity this does
        not have.

    Notes
    -----
    The frame is named after the chart -- ``"<title>, accessible chart"``,
    or ``"Accessible chart"`` for an untitled one, as py-maidr names its own
    frames -- on a Streamlit whose ``st.iframe`` takes ``alt``.  Older
    releases name every frame ``st.iframe``, which cannot be overridden.

    An unchanged chart reaches Streamlit as the same string on every rerun,
    so its frame is kept rather than reloaded, and a reader still in the
    chart keeps their place; the module notes have the measurement, what it
    does not cover, and why a Bokeh chart is the exception.

    Examples
    --------
    >>> import matplotlib.pyplot as plt
    >>> from maidr.widget.streamlit import render_maidr
    >>>
    >>> fig, ax = plt.subplots()
    >>> ax.bar(["a", "b"], [1, 2])
    >>> render_maidr(ax)
    """
    try:
        import streamlit as st
    except ImportError as error:
        from maidr.widget._extras import missing_extra_error

        raise missing_extra_error(error, "streamlit", "streamlit") from error

    # Called at the depth ``maidr_html`` sits at, so it takes the number
    # ``render_maidr`` used to pass that: one past the default.
    html, chart_title = _render(plot, use_cdn, stacklevel=4)

    # Streamlit builds this frame itself, so maidr cannot put an ``allow``
    # attribute on it the way the notebook wrappers do (see
    # ``_ALLOWED_FEATURES`` in ``maidr/util/iframe_utils.py``).  It does not
    # need to: Streamlit renders a ``srcdoc`` frame sandboxed *with*
    # ``allow-same-origin``, so the frame shares the app's origin, and a
    # feature its fixed ``allow`` list leaves unnamed -- Web Bluetooth and
    # Web Serial both -- falls back to the feature's own default, ``self``,
    # which a same-origin frame satisfies.  A tactile display is reachable
    # from a Streamlit app wherever the app document itself may reach one.
    #
    # Measured on Streamlit 1.61.1, not inferred: ``st.iframe`` and the
    # ``components.v1.html`` fallback below both enqueue the same ``IFrame``
    # element, and its frontend's sandbox list carries ``allow-same-origin``
    # while its feature list names neither ``bluetooth`` nor ``serial``.
    # Nothing in this repository's tests pins that -- it lives in
    # Streamlit's frontend bundle, which only a browser can exercise -- and
    # no older Streamlit has been measured, so on a release where the
    # fallback is what runs this is a reasoned expectation rather than a
    # checked one.  If a Streamlit release tightens that sandbox, tactile
    # displays stop working under it with nothing here to say so.
    if hasattr(st, "iframe"):
        kwargs: dict[str, Any] = {
            "width": width,
            "height": height,
            "tab_index": tab_index,
        }
        # ``alt`` names the frame: Streamlit puts it on the ``title`` a
        # screen reader announces, where otherwise every chart on the page
        # is called "st.iframe" alike (#461).  It is the name py-maidr gives
        # its own frames, so a chart is called the same thing in Streamlit
        # as in a notebook.  Asked of the installed function rather than a
        # version, like ``tab_index`` below; a Streamlit without it keeps
        # its fixed name, and there is nothing to warn the caller about --
        # they passed nothing that was dropped.
        if _accepts(st.iframe, "alt"):
            kwargs["alt"] = iframe_title(chart_title)
        st.iframe(html, **kwargs)
        return

    # Streamlit older than the one that introduced ``st.iframe``.
    # ``components.v1.html`` cannot size itself, and its own default
    # (``None``) renders as 150 px, so a symbolic size has to become a
    # concrete one here rather than silently cropping the chart.
    import streamlit.components.v1 as components

    kwargs = {
        "width": width if isinstance(width, int) else None,
        "height": height if isinstance(height, int) else _LEGACY_FALLBACK_HEIGHT,
        "scrolling": True,
    }
    # ``tab_index`` reached ``components.v1.html`` in Streamlit 1.45, eleven
    # releases before ``st.iframe`` existed, so "no st.iframe" does not mean
    # "no tab_index" -- taking it to mean that would discard a value the
    # caller passed, on every version in between, with nothing said.
    if _accepts(components.html, "tab_index"):
        kwargs["tab_index"] = tab_index
    elif tab_index is not None:
        warnings.warn(
            "maidr: this Streamlit is too old to set tab_index on an embed; "
            "the argument was ignored. Upgrade Streamlit to use it.",
            UserWarning,
            stacklevel=2,
        )

    components.html(html, **kwargs)


def _accepts(fn: Any, parameter: str) -> bool:
    """Report whether a Streamlit embed function takes ``parameter``.

    Asked of the installed function rather than inferred from a version,
    so the answer stays right across the range the extra allows.

    Parameters
    ----------
    fn : Any
        The Streamlit function.
    parameter : str
        The keyword to look for.

    Returns
    -------
    bool
        True if ``fn`` has a parameter of that name.
    """
    import inspect

    try:
        return parameter in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


__all__ = ["maidr_html", "render_maidr"]
