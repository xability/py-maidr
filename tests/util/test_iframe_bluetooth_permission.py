"""
Every iframed render delegates Web Bluetooth to the chart frame.

maidr.js can draw a chart onto a refreshable tactile display -- a Dot Pad --
over Web Bluetooth, so a blind reader feels the plot rather than only hearing
it. ``navigator.bluetooth`` is Permissions-Policy gated, and a frame that is
not granted the feature does not merely fail the call: the API is absent
entirely, so maidr reports "this browser cannot reach a DotPad" and the reader
has no way to tell a policy problem from an unsupported browser.

The default allowlist is ``self``, so a same-origin frame already has it and
the attribute changes nothing there. It is the cross-origin embeddings that
need it -- Colab, and any host serving notebook output from a separate origin.
Since both wrappers produce frames that end up in both kinds of page, both
carry the attribute.

Asserted on the rendered HTML rather than on a constant, because the constant
holding the right string is not the claim -- the claim is that the attribute
reaches the tag, on both wrappers, for the whole range of titles a chart
arrives with.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest
from htmltools import tags

from maidr.util.iframe_utils import (
    wrap_in_iframe_matplotlib,
    wrap_in_iframe_plotly,
)

WRAPPERS = (wrap_in_iframe_matplotlib, wrap_in_iframe_plotly)


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _html(tag) -> str:
    return str(tag.get_html_string())


class TestTheFrameMayReachATactileDisplay:
    """The attribute reaches the tag, by both wrappers."""

    @pytest.mark.parametrize("wrap", WRAPPERS)
    def test_the_chart_frame_is_allowed_bluetooth(self, wrap) -> None:
        rendered = _html(wrap(tags.div("chart"), "Body mass by species"))

        assert 'allow="bluetooth"' in rendered

    @pytest.mark.parametrize("wrap", WRAPPERS)
    def test_an_untitled_chart_is_allowed_it_too(self, wrap) -> None:
        # The delegation has nothing to do with the chart's title, and a
        # reader with a tactile display should not lose it for want of one.
        rendered = _html(wrap(tags.div("chart")))

        assert 'allow="bluetooth"' in rendered

    @pytest.mark.parametrize("wrap", WRAPPERS)
    def test_the_frame_is_not_sandboxed_into_an_opaque_origin(self, wrap) -> None:
        rendered = _html(wrap(tags.div("chart"), "Body mass by species"))

        # A `sandbox` without `allow-same-origin` gives the frame an opaque
        # origin, and a policy-controlled feature is never delegated to one --
        # the `allow` attribute above would be inert. Nothing sandboxes these
        # frames today; this fails if that changes without the pairing being
        # thought through.
        assert "sandbox=" not in rendered

    @pytest.mark.parametrize("wrap", WRAPPERS)
    def test_the_frame_still_carries_its_own_document(self, wrap) -> None:
        rendered = _html(wrap(tags.div("chart"), "Body mass by species"))

        # `srcdoc` is what keeps the frame same-origin with its host. Serving
        # the same document from a `data:` URL instead would hand it an opaque
        # origin, and no `allow` attribute can grant a feature to one.
        assert "srcdoc=" in rendered


class TestNothingElseIsDelegated:
    """The frame gets what the tactile display needs, and no more."""

    @pytest.mark.parametrize("wrap", WRAPPERS)
    def test_no_other_feature_is_granted(self, wrap) -> None:
        rendered = _html(wrap(tags.div("chart"), "Body mass by species"))

        # Delegating a feature cannot exceed what the embedding page already
        # holds, but it should still be the shortest list that works. maidr
        # only ever scans for a device over BLE, so `serial`, `usb`, `camera`
        # and the rest have no business here.
        for feature in ("serial", "usb", "camera", "microphone", "geolocation"):
            assert feature not in rendered
