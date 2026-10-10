"""One chart as the HTML of a frame of its own, for the framework integrations.

Streamlit, Gradio and an MLflow artifact each show a chart in a document of
its own, built from a string: an iframe's ``srcdoc``, or a page served on its
own. :func:`render` makes that string and reports the chart's title, which
names the frame. Under ``use_cdn=False`` it carries the bundled ``maidr.js``
inside it, since a frame built from a string cannot fetch what the host
serves; it gives an unchanged chart the same string on every call
(:func:`_stable_ids`), and it warns when the string has no way to load
``maidr.js`` at all.
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
from maidr.util.hover_mode import HoverMode
from maidr.util.iframe_utils import chart_title_on
from maidr.util.inline_chart import standalone_document

#: Accepted by ``use_cdn``; ``None`` defers to :func:`maidr.get_use_cdn`.
UseCdn = Optional[Union[bool, Literal["auto"]]]


def render(
    plot: Any,
    use_cdn: UseCdn,
    stacklevel: int,
    *,
    hover_mode: Optional[HoverMode] = None,
) -> tuple[str, str]:
    """
    Render a chart to the HTML of a frame of its own, and report its title.

    Parameters
    ----------
    plot : Any
        Anything :func:`maidr.render` takes. ``None`` is matplotlib's current
        figure, which a caller serving several users should refuse or warn
        about before it gets here.
    use_cdn : bool, {"auto"}, or None
        Where the chart loads ``maidr.js`` from; see :func:`maidr.render`.
        ``None`` defers to :func:`maidr.get_use_cdn`, read once.
    stacklevel : int
        Frames to skip for a warning raised one function deeper than this
        one, so it names the caller's own line.
    hover_mode : {"pointermove", "click", "off"} or None, default None
        The chart's starting hover mode; see :func:`maidr.render`.

    Returns
    -------
    tuple of (str, str)
        The HTML, and the chart's title -- ``""`` when it has none.
    """
    # Resolved once and then passed on, rather than read again inside
    # ``render``.  ``set_use_cdn`` writes process-wide state and Streamlit
    # runs sessions on separate threads, so reading it twice leaves a window
    # in which this function decides whether to inline against one answer
    # while the chart was built from another.
    resolved = maidr.get_use_cdn() if use_cdn is None else use_cdn
    # A document of its own, even when made during a Quarto render: not one
    # of the charts that render writes into its page.
    with standalone_document():
        rendered = maidr.render(plot, use_cdn=resolved, hover_mode=hover_mode)
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
    the frame whatever its integration returned.  When that string differs from
    the last one the browser reloads the frame, and maidr starts over
    inside it; when it is identical, the frame is left alone.  A chart
    differed on every render only in ids nobody reads -- fresh uuids from
    py-maidr, a random hash salt from matplotlib -- and in the time the SVG
    was written, so every rerun reloaded every chart on the page.  What
    that cost a reader, measured, is in the notes of
    ``maidr/widget/streamlit.py``.

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
