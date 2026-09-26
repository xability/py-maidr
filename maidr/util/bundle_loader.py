"""Load ``maidr.js`` into a page whose chart is drawn by another library.

The Plotly and Bokeh renderers both hand a chart to a JavaScript charting
library, wait for it to draw, and only then attach the MAIDR payload and --
under the CDN modes -- fetch ``maidr.js``. Everything here is the part of
that they share: which ``use_cdn`` mode ends up iframed, what the page must
carry for the bundled copy to be reachable, and the JS that loads the
bundle once the payload is in place. It was written for the Plotly path and
moved here unchanged when Bokeh needed the same answers (#813), so the two
cannot drift into loading the bundle two different ways.
"""

from __future__ import annotations

from typing import Any, Literal

from htmltools import tags

from maidr.util.bundle_freshness import warn_if_bundle_is_stale
from maidr.util.cdn import bundled_cdn_url, maidr_js_cdn_url
from maidr.util.dependencies import (
    MAIDR_JS_FILENAME,
    OFFLINE_FALLBACK_REPORT,
    inline_bundle_tags,
    maidr_bundled_files_dependency,
    maidr_bundled_relative_dir,
    maidr_html_dependency,
)
from maidr.util.environment import Environment


def iframe_mode(use_iframe: bool) -> tuple[bool, bool, bool]:
    """
    Decide whether a render is iframed, and where its bundle comes from.

    ``Tag.get_html_string()`` (used by the iframe wrappers) silently drops
    ``HTMLDependency`` children, so an iframed render cannot rely on
    htmltools to inject the bundled script. In a notebook the init script
    evaluates the JS source :func:`maidr.api.init_notebook` stashed on the
    parent ``window``; the stash only exists there, because
    ``init_notebook()`` returns early everywhere else, so any other iframed
    render -- Shiny, Flask -- carries the bundle inline instead. Mirrors the
    matplotlib ``_inject_plot`` logic.

    Parameters
    ----------
    use_iframe : bool
        Whether the caller asked for an iframe where the host needs one.

    Returns
    -------
    tuple of (bool, bool, bool)
        ``(will_iframe, iframe_in_notebook, iframe_inline_bundle)``: whether
        the output is wrapped in a frame at all, whether that frame reads
        the parent-window stash, and whether it carries the bundle inline.
    """
    in_notebook = Environment.is_notebook()
    will_iframe = use_iframe and (
        Environment.is_flask() or in_notebook or Environment.is_shiny()
    )
    return will_iframe, will_iframe and in_notebook, will_iframe and not in_notebook


def maidr_bundle_children(
    use_cdn: bool | Literal["auto"],
    *,
    iframe_in_notebook: bool,
    iframe_inline_bundle: bool,
) -> list[Any]:
    """
    What a page must carry so the loader from :func:`maidr_loader_js` works.

    Also where the bundled copy's age is reported, since each branch here is
    the point at which the bundle is known to be the primary source or the
    fallback.

    Parameters
    ----------
    use_cdn : bool or {"auto"}
        The resolved mode.
    iframe_in_notebook : bool
        The output is a notebook srcdoc iframe; see :func:`iframe_mode`.
    iframe_inline_bundle : bool
        The output is an iframe outside a notebook; see :func:`iframe_mode`.

    Returns
    -------
    list
        Tags and dependencies to place ahead of the chart.
    """
    children: list[Any] = []
    if use_cdn is False:
        # Bundled copy is the only source; surface it if it has aged.
        warn_if_bundle_is_stale()
        if iframe_in_notebook:
            # ``HTMLDependency`` is dropped by ``get_html_string()``
            # during iframe serialization; the init script's
            # parent-source loader carries both the JS and KaTeX, so
            # no extra children are needed here.
            pass
        elif iframe_inline_bundle:
            # An iframe outside a notebook: the dependency below would
            # be dropped by ``get_html_string()`` and there is no
            # parent stash to read, so the bundle travels inline.
            # These tags precede the init script, so ``maidr.js`` is
            # in the document by the time the loader would have run --
            # which is why the loader for this case is empty, exactly
            # as it is for the non-iframe dependency path.
            inline_tags = inline_bundle_tags()
            if inline_tags is None:
                # Bundle unreadable; already warned.  A CDN tag is the
                # only remaining source, and a chart that needs the
                # network beats one that cannot be read at all.
                inline_tags = [tags.script(src=bundled_cdn_url(MAIDR_JS_FILENAME))]
            children.extend(inline_tags)
        else:
            # The dependency copies the whole bundle, so ``maidr.js``
            # finds ``maidr-math.css`` beside itself; no ``<link>``
            # needs emitting.
            children.append(maidr_html_dependency())
    elif use_cdn == "auto":
        # Published version is resolved by now, so the bundled
        # fallback's age is known for free.  Fallback, not primary.
        warn_if_bundle_is_stale(bundle_is_primary=False)
        if not iframe_in_notebook:
            # Copy the bundle alongside the HTML without auto-emitted
            # tags, so the JS loader's ``onerror`` path has something
            # to fall back to.
            children.append(maidr_bundled_files_dependency())
    return children


def _parent_source(on_missing: str, on_unreachable: str | None = None) -> str:
    """Return the parent-window loader, reporting failure as told.

    Snippet that pulls the bundled JS and KaTeX source from the parent
    notebook window.  Reused by ``use_cdn=False`` (primary loader) and
    ``use_cdn="auto"`` (CDN onerror fallback).

    KaTeX travels as a string because ``maidr.js`` resolves
    ``maidr-math.css`` against the URL it was loaded from, and an inline
    script inside a srcdoc iframe has no URL to offer it.

    The two ``use_cdn`` modes reach this for different reasons and so
    need different advice. Under ``False`` the caller asked for the
    bundle and the fix is ``init_notebook()``; under ``"auto"`` the
    CDN was simply unreachable and the fix is ``use_cdn=False``.
    Sharing one message would send half the callers somewhere useless.

    Built by placeholder replacement rather than as an f-string: the JS
    body is full of literal braces, and an f-string would need every one
    of them doubled -- which is how a template like this acquires a
    mismatched brace that only shows up as broken JS in a browser.

    Parameters
    ----------
    on_missing : str
        JS run when the parent is readable but holds no stash.
    on_unreachable : str or None, optional
        JS run when the parent could not be read at all -- a
        cross-origin frame, or no parent. ``None`` reuses
        ``on_missing``, which is right only where the two have the
        same answer; under ``"auto"`` they do not, and reporting a
        missing stash for an unreachable parent sends the reader
        looking in the wrong place. ``None`` rather than ``""`` so
        that "same answer" and "say nothing" stay distinguishable
        if a caller ever wants the latter.

    Returns
    -------
    str
        The loader, as JS.
    """
    return """
            (function() {
                try {
                    var jsSrc = window.parent && window.parent.__maidrJsSource;
                    var mathCss = window.parent && window.parent.__maidrMathCssSource;
                    if (mathCss) {
                        var style = document.createElement('style');
                        style.textContent = mathCss;
                        document.head.appendChild(style);
                        // maidr.js looks for a <link> carrying this attribute
                        // to decide whether the rules are already present; a
                        // <style> never matches, and the miss is reported to
                        // the console as maths rendering unstyled.
                        var mark = document.createElement('link');
                        mark.setAttribute('data-maidr-math', '');
                        document.head.appendChild(mark);
                    }
                    if (jsSrc) {
                        var s = document.createElement('script');
                        s.text = jsSrc;
                        document.head.appendChild(s);
                        return true;
                    }
                    __ON_MISSING__
                    return false;
                } catch (_) {
                    __ON_UNREACHABLE__
                    return false;
                }
            })();
        """.replace("__ON_MISSING__", on_missing).replace(
        "__ON_UNREACHABLE__",
        on_missing if on_unreachable is None else on_unreachable,
    )


#: ``use_cdn=False``: the caller asked for the bundle, so the fix is to
#: stash it, not to change the mode.
_NOTEBOOK_STASH_MISSING = """
                if (window.console) {
                    console.warn(
                        'maidr: use_cdn=False requires maidr.init_notebook() ' +
                        'to be called once per notebook session, or the bundle ' +
                        'to be available on window.parent.__maidrJsSource.'
                    );
                }
        """


def maidr_loader_js(
    use_cdn: bool | Literal["auto"], *, iframe_in_notebook: bool
) -> str:
    """
    The JS that brings ``maidr.js`` into the page, run once the payload is in.

    When ``use_cdn=False`` outside an iframe the bundle is already loaded by
    an :class:`htmltools.HTMLDependency` (see :func:`maidr_bundle_children`)
    so no loader is emitted. In ``"auto"`` mode the loader attempts the CDN
    first and falls back to the bundled copy on ``onerror``.

    When ``iframe_in_notebook=True`` the loader instead pulls the bundled
    source strings from ``window.parent.__maidrJsSource`` /
    ``window.parent.__maidrMathCssSource`` (populated by
    :func:`maidr.api.init_notebook`). Relative ``lib/maidr-.../`` paths do
    not resolve inside a srcdoc iframe, and ``HTMLDependency`` children are
    stripped by ``Tag.get_html_string()``, so the parent-window stash is the
    only reliable offline fallback in notebooks.

    Parameters
    ----------
    use_cdn : bool or {"auto"}
        The resolved mode.
    iframe_in_notebook : bool
        ``True`` when the emitted HTML will be wrapped in a notebook srcdoc
        iframe.

    Returns
    -------
    str
        The loader, as JS statements; empty when nothing needs loading.
    """
    if use_cdn is False:
        if iframe_in_notebook:
            # Iframe path: HTMLDependency would be dropped by
            # ``Tag.get_html_string()``.  Pull the bundled source
            # strings from the parent window instead.
            return _parent_source(_NOTEBOOK_STASH_MISSING)
        # Non-iframe path: ``maidr.js`` is already in the DOM
        # via ``HTMLDependency`` (emitted by htmltools as a
        # regular ``<script src>``).  Nothing to do here.
        return ""

    # Resolved lazily and only on the CDN paths: ``use_cdn=False``
    # must never touch the network.
    js_cdn_url = maidr_js_cdn_url()
    if use_cdn == "auto":
        if iframe_in_notebook:
            # Iframe path: try the CDN first, fall back to the
            # parent-window source on ``onerror``.  Relative
            # ``lib/`` paths cannot be resolved inside srcdoc.
            # Under "auto" the CDN was simply unreachable, so the
            # stash being empty too means there is no source left --
            # which is what ``reportNoRuntime`` is for. Under
            # ``use_cdn=False`` the same miss means something else
            # (see ``_parent_source``), hence the separate wording.
            auto_parent_source = _parent_source(
                "reportNoRuntime('the notebook page has no stashed copy');",
                "reportNoRuntime('the parent page is unreachable');",
            )
            return f"""
{OFFLINE_FALLBACK_REPORT}
                    var existing = document.querySelector(
                        'script[src="{js_cdn_url}"]'
                    );
                    if (!existing) {{
                        var s = document.createElement('script');
                        s.src = '{js_cdn_url}';
                        s.onerror = function() {{{auto_parent_source}}};
                        document.head.appendChild(s);
                    }}
                """
        rel_dir = maidr_bundled_relative_dir()
        bundled_js_rel = f"{rel_dir}/{MAIDR_JS_FILENAME}"
        return f"""
{OFFLINE_FALLBACK_REPORT}
                    var existing = document.querySelector(
                        'script[src="{js_cdn_url}"]'
                    );
                    if (!existing) {{
                        var s = document.createElement('script');
                        s.src = '{js_cdn_url}';
                        s.onerror = function() {{
                            var fb = document.createElement('script');
                            fb.src = '{bundled_js_rel}';
                            // The relative path resolves wherever the host
                            // serves the copied bundle -- save_html -- and
                            // cannot inside a srcdoc iframe nobody serves
                            // those files for. Without this the chart is an
                            // image with no runtime and nothing said.
                            fb.onerror = function() {{
                                reportNoRuntime(
                                    'the bundled copy at {bundled_js_rel} '
                                    + 'did not load'
                                );
                            }};
                            document.head.appendChild(fb);
                        }};
                        document.head.appendChild(s);
                    }}
                """
    return f"""
                var existing = document.querySelector(
                    'script[src="{js_cdn_url}"]'
                );
                if (!existing) {{
                    var s = document.createElement('script');
                    s.src = '{js_cdn_url}';
                    document.head.appendChild(s);
                }}
            """
