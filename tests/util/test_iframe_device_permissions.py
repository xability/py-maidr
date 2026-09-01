"""
Every iframed render delegates Web Bluetooth and Web Serial to the chart frame.

maidr.js can draw a chart onto a refreshable tactile display -- a Dot Pad --
so a blind reader feels the plot rather than only hearing it. It reaches the
device over Bluetooth or over USB, and both APIs are Permissions-Policy gated.
A frame that is not granted a feature does not merely fail the call: the API is
absent entirely, so maidr reports "this browser cannot reach a DotPad" and the
reader has no way to tell a policy problem from an unsupported browser.

The default allowlist is ``self``, so a same-origin frame already has them and
the attribute changes nothing there. It is the cross-origin embeddings that
need it -- Colab, and any host serving notebook output from a separate origin.
Since both wrappers produce frames that end up in both kinds of page, both
carry the attribute.

Both features are asserted, not just one. They are gated independently, so
granting only Bluetooth would leave a reader on a cable unable to connect for
a reason nothing on the page explains -- and USB is the faster path by a wide
margin, so it is not the marginal case.

Asserted on the rendered HTML rather than on a constant, because the constant
holding the right string is not the claim -- the claim is that the attribute
reaches the tag, on both wrappers, for the whole range of titles a chart
arrives with.

Read back through an HTML parser rather than by substring, because the frame
carries the whole chart document in its ``srcdoc``.  Searching the rendered
string would be searching that payload too: ``maidr.js`` contains ``hid`` 150
times (``aria-hidden``, ``hidden`` -- unsurprising in an accessibility bundle)
and ``usb`` once, so a "no other feature is granted" assertion written as a
substring check passes only for as long as the fixture stays a stub, and then
fails for a reason unrelated to any policy regression.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest
from htmltools import tags

from maidr.util.iframe_utils import (
    wrap_in_iframe_matplotlib,
    wrap_in_iframe_plotly,
)

WRAPPERS = (wrap_in_iframe_matplotlib, wrap_in_iframe_plotly)


def _html(tag) -> str:
    return str(tag.get_html_string())


class _FirstIframe(HTMLParser):
    """Captures the attributes of the first ``iframe`` start tag."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.attrs: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "iframe" and self.attrs is None:
            self.attrs = {name: value or "" for name, value in attrs}


def _iframe_attrs(rendered: str) -> dict[str, str]:
    """
    Reads the chart frame's own attributes out of the rendered HTML.

    Scoped to the tag rather than the document: the frame carries the entire
    chart -- bundle included -- inside ``srcdoc``, so a substring search over
    the rendered string is a search of that payload as well.

    Parameters
    ----------
    rendered
        The wrapper's rendered HTML.

    Returns
    -------
    dict[str, str]
        The ``iframe`` start tag's attributes.
    """
    parser = _FirstIframe()
    parser.feed(rendered)
    assert parser.attrs is not None, "the wrapper rendered no iframe"
    return parser.attrs


def _allowed_features(rendered: str) -> set[str]:
    """
    Splits the frame's ``allow`` attribute into the features it delegates.

    Parameters
    ----------
    rendered
        The wrapper's rendered HTML.

    Returns
    -------
    set[str]
        One entry per delegated feature, without any allowlist that follows it.
    """
    allow = _iframe_attrs(rendered).get("allow", "")
    return {
        re.split(r"\s+", item.strip())[0] for item in allow.split(";") if item.strip()
    }


class TestTheFrameMayReachATactileDisplay:
    """The attribute reaches the tag, by both wrappers."""

    @pytest.mark.parametrize("wrap", WRAPPERS)
    def test_the_chart_frame_is_allowed_bluetooth_and_serial(self, wrap) -> None:
        rendered = _html(wrap(tags.div("chart"), "Body mass by species"))

        features = _allowed_features(rendered)

        # Both, and nothing else. They are independently gated, so dropping
        # one leaves that path dead for a reason nothing on the page
        # explains; and delegating a feature cannot exceed what the embedding
        # page holds, but the list should still be the shortest that works --
        # maidr scans for a display over Bluetooth and over serial only, so
        # `usb`, `hid`, `camera` and the rest have no business here. Compared
        # as parsed features rather than as the exact string, so reformatting
        # the list cannot quietly lose one.
        assert features == {"bluetooth", "serial"}

    @pytest.mark.parametrize("wrap", WRAPPERS)
    def test_an_untitled_chart_is_allowed_them_too(self, wrap) -> None:
        # The delegation has nothing to do with the chart's title, and a
        # reader with a tactile display should not lose it for want of one.
        features = _allowed_features(_html(wrap(tags.div("chart"))))

        assert features == {"bluetooth", "serial"}

    @pytest.mark.parametrize("wrap", WRAPPERS)
    def test_the_frame_is_not_sandboxed_into_an_opaque_origin(self, wrap) -> None:
        attrs = _iframe_attrs(_html(wrap(tags.div("chart"), "Body mass by species")))

        # A `sandbox` without `allow-same-origin` gives the frame an opaque
        # origin, and a policy-controlled feature is never delegated to one --
        # the `allow` attribute above would be inert. Nothing sandboxes these
        # frames today; this fails if that changes without the pairing being
        # thought through.
        assert "sandbox" not in attrs

    @pytest.mark.parametrize("wrap", WRAPPERS)
    def test_the_frame_still_carries_its_own_document(self, wrap) -> None:
        attrs = _iframe_attrs(_html(wrap(tags.div("chart"), "Body mass by species")))

        # `srcdoc` is what keeps the frame same-origin with its host. Serving
        # the same document from a `data:` URL instead would hand it an opaque
        # origin, and no `allow` attribute can grant a feature to one.
        assert "srcdoc" in attrs
        assert "src" not in attrs


class TestNothingElseIsDelegated:
    """What the chart says cannot pass for what the frame was granted."""

    @pytest.mark.parametrize("wrap", WRAPPERS)
    def test_chart_content_cannot_look_like_a_granted_feature(self, wrap) -> None:
        # The frame carries the whole chart document, bundle included, inside
        # `srcdoc`. `maidr.js` alone contains `hid` 150 times (`aria-hidden`,
        # `hidden`) and `usb` once, so reading the delegated features by
        # substring over the rendered string would report features nobody
        # granted -- and would do it only once the fixture grew realistic,
        # long after the test was written. Content that says these words is
        # the case that pins the difference.
        loaded = tags.div(
            "chart",
            tags.span("aria-hidden usb camera microphone geolocation"),
        )

        features = _allowed_features(_html(wrap(loaded, "Body mass by species")))

        assert features == {"bluetooth", "serial"}
